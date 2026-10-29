"""Dados da animação da apuração: a parcial na ordem real de chegada dos boletins × a parcial com as mesmas seções em ordem sorteada.

Entrada: secoes.parquet (votos por seção) e detalhe_votacao_secao (DT_PRIM_TOT_PARCIAL_HOR_TSE, hora de Brasília em que o boletim
da seção entrou na totalização).
Saída: portal/dados/apuracao.json

1º turno: percentual dos votos válidos (todos os candidatos). 2º turno: percentual dos votos válidos (Lula + Flávio).
A ordem sorteada é repetida 200 vezes; a faixa guarda os percentis 2,5 e 97,5 de cada ponto.
"""
import json

import numpy as np
import pandas as pd

from comum import ARQUIVOS, BRUTOS, PORTAL_DADOS, PROCESSADOS, ler_csv_tse

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
CANDS = {1: ["Flávio", "Lula", "Renan", "Cury", "Caiado", "Zema", "Outros"], 2: ["Flávio", "Lula"]}
REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Exterior"]
N_PONTOS, N_SORTEIOS = 400, 200


def turno(s, t, horas):
    cands = CANDS[t]
    x = s.merge(horas[horas.NR_TURNO == t][CHAVE + ["hora"]], on=CHAVE).dropna(subset=["hora"]).sort_values("hora", kind="stable")
    validos = x[[f"{c}_{t}" for c in cands]].sum(axis=1).to_numpy(float)
    fla, lula = x[f"Flávio_{t}"].to_numpy(float), x[f"Lula_{t}"].to_numpy(float)
    n = len(x)
    # pontos da curva por nº de seções apuradas (mais densos no começo, quando a parcial muda rápido)
    minuto = x.hora.dt.floor("min").to_numpy()
    idx = np.unique(np.r_[np.geomspace(20, 0.05 * n, 80), np.linspace(0, n - 1, N_PONTOS)].astype(int))
    cv, cf, cl = validos.cumsum(), fla.cumsum(), lula.cumsum()
    reg = {r: np.cumsum(validos * (x.REGIAO == r).to_numpy())[idx] / cv[idx] * 100 for r in REGIOES}
    real = {"hora": [pd.Timestamp(minuto[i]).strftime("%H:%M") for i in idx], "pct_secoes": (100 * (idx + 1) / n).round(2).tolist(),
            "flavio": (100 * cf[idx] / cv[idx]).round(3).tolist(), "lula": (100 * cl[idx] / cv[idx]).round(3).tolist(),
            "regioes": {r: v.round(2).tolist() for r, v in reg.items()}}
    # ordem sorteada: mesma posição (nº de seções apuradas) da curva real
    rng = np.random.default_rng(2026 + t)
    sf, sl = np.empty((N_SORTEIOS, len(idx))), np.empty((N_SORTEIOS, len(idx)))
    for k in range(N_SORTEIOS):
        p = rng.permutation(n)
        v, f, l = validos[p].cumsum()[idx], fla[p].cumsum()[idx], lula[p].cumsum()[idx]
        sf[k], sl[k] = 100 * f / v, 100 * l / v
    q = lambda a, z: np.percentile(a, z, axis=0).round(3).tolist()
    sorteio = {"flavio": sf[0].round(3).tolist(), "lula": sl[0].round(3).tolist(),
               "flavio_lo": q(sf, 2.5), "flavio_hi": q(sf, 97.5), "lula_lo": q(sl, 2.5), "lula_hi": q(sl, 97.5)}
    # largura da faixa com 1.000 seções sorteadas (meia amplitude do intervalo de 95%)
    meia = []
    for k in range(N_SORTEIOS):
        p = rng.choice(n, 1000, replace=False)
        meia.append(100 * fla[p].sum() / validos[p].sum())
    final_f, final_l = 100 * cf[-1] / cv[-1], 100 * cl[-1] / cv[-1]
    rf = np.array(real["flavio"])
    estavel = np.array(real["pct_secoes"]) >= 2
    i_pico = int(np.argmax(np.where(estavel, rf, -1)))
    momentos = {"pico_flavio": {"i": i_pico, "hora": real["hora"][i_pico], "pct_secoes": real["pct_secoes"][i_pico], "valor": real["flavio"][i_pico]}}
    if t == 1:  # momento em que Flávio fica abaixo de 50% dos válidos depois do pico
        abaixo = [i for i in range(i_pico, len(rf)) if rf[i] < 50]
        if abaixo:
            i = abaixo[0]
            momentos["abaixo_50"] = {"i": i, "hora": real["hora"][i], "pct_secoes": real["pct_secoes"][i], "valor": real["flavio"][i]}
    dif = np.array(real["lula"]) - rf
    trocas = [i for i in range(1, len(dif)) if estavel[i] and estavel[i - 1] and np.sign(dif[i]) != np.sign(dif[i - 1])]
    momentos["trocas_lideranca"] = [{"i": i, "hora": real["hora"][i], "pct_secoes": real["pct_secoes"][i], "lider": "Lula" if dif[i] > 0 else "Flávio"} for i in trocas]
    # quantas seções sorteadas bastam para ficar a ±0,5 p.p. do resultado final (em 95% dos sorteios)
    desvio = np.percentile(np.abs(sf - final_f), 95, axis=0)
    ok = np.flatnonzero(desvio <= 0.5)
    return {"secoes": n, "inicio": real["hora"][0], "fim": real["hora"][-1], "real": real, "sorteio": sorteio,
            "final": {"flavio": round(final_f, 3), "lula": round(final_l, 3)}, "momentos": momentos,
            "erro_1000_secoes_pp": round(float(np.percentile(np.abs(np.array(meia) - final_f), 95)), 2),
            "secoes_para_05pp": int(idx[ok[0]] + 1) if len(ok) else None,
            "regioes_no_total": {r: round(float(100 * validos[(x.REGIAO == r).to_numpy()].sum() / validos.sum()), 2) for r in REGIOES}}


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    s.loc[s.SG_UF == "ZZ", "REGIAO"] = "Exterior"
    h = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=CHAVE + ["NR_TURNO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"])
    h["hora"] = pd.to_datetime(h.DT_PRIM_TOT_PARCIAL_HOR_TSE, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    out = {str(t): turno(s, t, h) for t in (1, 2)}
    out["regioes"] = REGIOES
    with open(PORTAL_DADOS / "apuracao.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for t in ("1", "2"):
        o = out[t]
        print(t, o["secoes"], o["inicio"], o["fim"], o["final"], o["momentos"], "erro 1000:", o["erro_1000_secoes_pp"], "seções p/ 0,5pp:", o["secoes_para_05pp"])
        print("   início real:", [(o["real"]["hora"][i], o["real"]["pct_secoes"][i], o["real"]["flavio"][i]) for i in (5, 50, 100, 200, 300, -1)])
        print("   regiões no 1º décimo:", {r: o["real"]["regioes"][r][40] for r in out["regioes"]}, "total:", o["regioes_no_total"])


if __name__ == "__main__":
    main()
