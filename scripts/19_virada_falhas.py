"""Verificação: a virada da apuração coincidiu com falhas operacionais das urnas?

Cruza a hora em que o boletim de cada seção entrou na totalização (DT_PRIM_TOT_PARCIAL_HOR_TSE) com as ocorrências
registradas no log da urna da mesma seção e do mesmo turno:
  - troca de urna (contingência), erro fora da rotina, reinício durante a votação e voto não registrado.

Perguntas:
  1. As seções que chegaram durante a virada (entre as trocas de liderança) tiveram mais falhas que as demais?
  2. Nas seções com falha, o voto foi diferente do das seções sem falha do mesmo município?
  3. Quanto da margem final vem das seções com falha? O resultado muda se elas forem retiradas?

Saída: portal/dados/virada_falhas.json
"""
import glob
import json

import numpy as np
import pandas as pd

from comum import ARQUIVOS, BRUTOS, PORTAL_DADOS, PROCESSADOS, ler_csv_tse

CHAVE = ["uf", "mun", "zona", "secao"]
COLS_LOG = ["turno", "uf", "mun", "zona", "secao", "contingencia", "erros", "erros_rotina", "ligadas_apos_pronta", "voto_nao_registrado"]
FALHAS = {"contingencia": "Troca de urna", "erro": "Erro fora da rotina", "reinicio": "Reinício durante a votação", "nao_registrado": "Voto não registrado"}


def carregar_logs():
    d = pd.concat([pd.read_parquet(f, columns=COLS_LOG) for f in glob.glob(str(PROCESSADOS / "logs" / "*.parquet"))], ignore_index=True)
    d["contingencia"] = d.contingencia.fillna(False).astype(bool)
    d["erro"] = (d.erros - d.erros_rotina).clip(lower=0) > 0
    d["reinicio"] = d.ligadas_apos_pronta > 0
    d["nao_registrado"] = d.voto_nao_registrado > 0
    d["falha"] = d[list(FALHAS)].any(axis=1)
    return d[["turno"] + CHAVE + list(FALHAS) + ["falha"]]


def efeito_no_municipio(x, y, dummy):
    """Diferença de y entre seções com e sem a ocorrência, dentro do município (efeito fixo), com erro-padrão."""
    chave = x.uf + "-" + x.mun.astype(str)
    yd = x[y] - x[y].groupby(chave).transform("mean")
    xd = x[dummy].astype(float) - x[dummy].astype(float).groupby(chave).transform("mean")
    den = (xd ** 2).sum()
    if den == 0:
        return None
    b = (xd * yd).sum() / den
    res = yd - b * xd
    se = np.sqrt((res ** 2).sum() / (len(x) - 1) / den)
    return {"efeito_pp": float(b), "erro_padrao": float(se)}


def analisar(t, s, h, logs, mom):
    x = s.merge(h[h.NR_TURNO == t][CHAVE + ["hora"]], on=CHAVE).merge(logs[logs.turno == t], on=CHAVE, how="left")
    x = x.dropna(subset=["hora"])
    x["com_log"] = x.falha.notna()
    for c in list(FALHAS) + ["falha"]:
        x[c] = x[c].fillna(False).astype(bool)
    x["L"], x["F"] = x[f"Lula_{t}"], x[f"Flávio_{t}"]
    x["lula"] = 100 * x.L / (x.L + x.F).where(x.L + x.F > 0)
    x["min"] = (x.hora.dt.hour * 60 + x.hora.dt.minute).where(x.hora.dt.hour >= 12, x.hora.dt.hour * 60 + x.hora.dt.minute + 1440)
    x = x.sort_values("hora", kind="stable")
    x["pct_apurado"] = 100 * np.arange(1, len(x) + 1) / len(x)
    hm = lambda s_: int(s_[:2]) * 60 + int(s_[3:5])
    trocas = mom["trocas_lideranca"]
    if len(trocas) >= 2:
        ini, fim = hm(trocas[0]["hora"]), hm(trocas[-1]["hora"])
        rot_janela = f"entre {trocas[0]['hora'].replace(':', 'h')} e {trocas[-1]['hora'].replace(':', 'h')}"
    else:  # 1º turno: do pico de Flávio até ele ficar abaixo de 50%
        ini, fim = hm(mom["pico_flavio"]["hora"]), hm(mom.get("abaixo_50", mom["pico_flavio"])["hora"])
        rot_janela = f"entre {mom['pico_flavio']['hora'].replace(':', 'h')} e {mom.get('abaixo_50', mom['pico_flavio'])['hora'].replace(':', 'h')}"
    x["janela"] = x["min"].between(ini, fim)
    resumo = lambda g: {"secoes": int(len(g)), "com_log_pct": float(100 * g.com_log.mean()),
                        **{f"{k}_pct": float(100 * g[k].mean()) for k in list(FALHAS) + ["falha"]},
                        "lula_pct": float(100 * g.L.sum() / (g.L + g.F).sum()), "nordeste_pct": float(100 * (g.REGIAO == "Nordeste").mean())}
    # por faixa de 10 minutos de chegada, entre 17h e 23h
    x["faixa"] = (x["min"] // 10) * 10
    faixas = []
    for f, g in x[(x["min"] >= 17 * 60) & (x["min"] < 23 * 60)].groupby("faixa"):
        if len(g) < 30:
            continue
        gf = g[g.falha]
        faixas.append({"hora": f"{f // 60:02d}:{f % 60:02d}", "secoes": int(len(g)), "falha_pct": float(100 * g.falha.mean()),
                       "secoes_falha": int(len(gf)), "votos": int((g.L + g.F).sum()), "votos_falha": int((gf.L + gf.F).sum()),
                       "lula_falha": int(gf.L.sum()), "flavio_falha": int(gf.F.sum()),
                       "contingencia_pct": float(100 * g.contingencia.mean()), "erro_pct": float(100 * g.erro.mean()),
                       "lula_pct": float(100 * g.L.sum() / max((g.L + g.F).sum(), 1)), "nordeste_pct": float(100 * (g.REGIAO == "Nordeste").mean()),
                       "janela": bool(ini <= f + 9 and f <= fim)})
    jan, fora = x[x.janela], x[~x.janela]
    falha_jan = jan[jan.falha]
    total_margem = int((x.L - x.F).sum())
    sem_falha = x[~x.falha]
    efeitos = {k: efeito_no_municipio(x.dropna(subset=["lula"]), "lula", k) for k in list(FALHAS) + ["falha"]}
    efeitos_jan = efeito_no_municipio(jan.dropna(subset=["lula"]), "lula", "falha")
    return {
        "janela": {"inicio": f"{ini // 60:02d}:{ini % 60:02d}", "fim": f"{fim // 60:02d}:{fim % 60:02d}", "rotulo": rot_janela,
                   "pct_apurado_inicio": float(x[x.janela].pct_apurado.min()) if len(jan) else None,
                   "pct_apurado_fim": float(x[x.janela].pct_apurado.max()) if len(jan) else None},
        "na_janela": resumo(jan), "fora_da_janela": resumo(fora), "total": resumo(x),
        "faixas": faixas,
        "falha_na_janela": {"secoes": int(len(falha_jan)), "lula": int(falha_jan.L.sum()), "flavio": int(falha_jan.F.sum()),
                            "margem_lula": int((falha_jan.L - falha_jan.F).sum())},
        "falha_total": {"secoes": int(x.falha.sum()), "lula": int(x[x.falha].L.sum()), "flavio": int(x[x.falha].F.sum()),
                        "margem_lula": int((x[x.falha].L - x[x.falha].F).sum())},
        # votos (Lula e Flávio) por tipo de falha: durante a virada e no total
        "votos_por_tipo": {k: {"janela": [int(len(jan[jan[k]])), int(jan[jan[k]].L.sum()), int(jan[jan[k]].F.sum())],
                               "total": [int(x[k].sum()), int(x[x[k]].L.sum()), int(x[x[k]].F.sum())]} for k in list(FALHAS) + ["falha"]},
        "votos_janela": int((jan.L + jan.F).sum()), "votos_total": int((x.L + x.F).sum()),
        "margem_final_lula": total_margem,
        "sem_secoes_com_falha": {"lula_pct": float(100 * sem_falha.L.sum() / (sem_falha.L + sem_falha.F).sum()),
                                 "margem_lula": int((sem_falha.L - sem_falha.F).sum()), "secoes": int(len(sem_falha))},
        "efeito_falha_no_municipio": efeitos, "efeito_falha_na_janela": efeitos_jan,
        "rotulos": FALHAS,
    }


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet").rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    h = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_TURNO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"])
    h = h.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    h["hora"] = pd.to_datetime(h.DT_PRIM_TOT_PARCIAL_HOR_TSE, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    logs = carregar_logs()
    ap = json.load(open(PORTAL_DADOS / "apuracao.json"))
    out = {str(t): analisar(t, s, h, logs, ap[str(t)]["momentos"]) for t in (1, 2)}
    with open(PORTAL_DADOS / "virada_falhas.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for t in ("1", "2"):
        o = out[t]
        print(t, o["janela"])
        print("  janela:", {k: round(v, 2) for k, v in o["na_janela"].items()})
        print("  fora:  ", {k: round(v, 2) for k, v in o["fora_da_janela"].items()})
        print("  falha na janela:", o["falha_na_janela"], "| falha total:", o["falha_total"], "| margem final:", o["margem_final_lula"])
        print("  sem seções com falha:", o["sem_secoes_com_falha"])
        print("  efeito (município):", {k: (round(v["efeito_pp"], 2), round(v["erro_padrao"], 2)) for k, v in o["efeito_falha_no_municipio"].items() if v},
              "| na janela:", o["efeito_falha_na_janela"])


if __name__ == "__main__":
    main()
