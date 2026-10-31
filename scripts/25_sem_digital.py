"""Indicador “eleitor que votou sem digital”: votos cujo eleitor não foi habilitado pela biometria.

O log da urna grava “Tipo de habilitação do eleitor [biométrica]” quando a digital confere. Os demais votos foram
habilitados sem a digital do eleitor: eleitor sem biometria no cadastro, digital que não conferiu após as tentativas
(o mesário libera com o código e o ano de nascimento) ou seção sem biometria (exterior). Votos sem digital = votos no
log − habilitações biométricas, por seção e turno, com 100% das seções com log.

Entradas: dados/processados/logs/<turno>_<UF>.parquet (16_logs_urnas.py) e dados/processados/secoes.parquet.
Saídas:   portal/dados/sem_digital.json e portal/dados/sem_digital/<UF>.json (zonas e seções com 25% ou mais sem digital)
"""
import glob
import json
import time

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS

FAIXAS = [(0, .05, "até 5%"), (.05, .10, "5% a 10%"), (.10, .20, "10% a 20%"), (.20, .30, "20% a 30%"), (.30, .50, "30% a 50%"), (.50, .90, "50% a 90%"), (.90, 1.01, "90% ou mais")]
MIN_VOTOS = 30  # seções com poucos votos têm percentuais instáveis
CORTE_SECAO = 0.25  # seções listadas por UF


def carregar_logs():
    partes = []
    for f in sorted(glob.glob(str(PROCESSADOS / "logs" / "*.parquet"))):
        t = int(f.split("/")[-1][0])
        d = pd.read_parquet(f, columns=["uf", "mun", "zona", "secao", "votos_log", "hab_biometrica", "hab_por_mesario", "ano_nasc_confere", "ano_nasc_diferente", "biometria_nao_confere", "leitor_biometrico_erro", "contingencia"])
        partes.append(d.assign(turno=t))
    d = pd.concat(partes, ignore_index=True)
    for c in ("votos_log", "hab_biometrica", "hab_por_mesario", "ano_nasc_confere", "ano_nasc_diferente", "biometria_nao_confere"):
        d[c] = d[c].fillna(0).astype(int)
    d["leitor"] = d.leitor_biometrico_erro.fillna(0).astype(int)
    d["cont"] = d.contingencia.fillna(False).astype(int)
    d["sd"] = (d.votos_log - d.hab_biometrica).clip(lower=0)
    d["mes"] = np.minimum(d.hab_por_mesario, d.sd)
    w = d.pivot_table(index=["uf", "mun", "zona", "secao"], columns="turno", values=["votos_log", "sd", "mes", "leitor", "cont"], aggfunc="sum")
    w.columns = [f"{ {'votos_log': 'v', 'sd': 's', 'mes': 'm', 'leitor': 'l', 'cont': 'c'}[c] }{t}" for c, t in w.columns]
    w = w.reset_index()
    for t in (1, 2):
        w[f"log{t}"] = w[f"v{t}"].notna()
        for c in ("v", "s", "m", "l", "c"):
            w[f"{c}{t}"] = w[f"{c}{t}"].fillna(0).astype(int)
    return d, w


def faixa(p):
    for lo, hi, rot in FAIXAS:
        if lo <= p < hi:
            return rot
    return FAIXAS[-1][2]


def agregar(w, chaves):
    g = w.groupby(chaves)
    out = pd.DataFrame({f"{c}{t}": g[f"{c}{t}"].sum() for t in (1, 2) for c in ("v", "s", "m")})
    for t in (1, 2):
        out[f"n{t}"] = g[f"log{t}"].sum()
    out = out.reset_index()
    for c in out.columns:
        if c not in chaves:
            out[c] = out[c].astype(int)
    return out


COLS = ["v1", "s1", "m1", "n1", "v2", "s2", "m2", "n2"]


def main():
    t0 = time.time()
    d, w = carregar_logs()
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet").rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    nomes = {(r.uf, int(r.mun)): r.NM_MUNICIPIO for r in s[["uf", "mun", "NM_MUNICIPIO"]].drop_duplicates().itertuples()}
    m = w.merge(s[["uf", "mun", "zona", "secao", "NM_LOCAL_VOTACAO", "Lula_1", "Flávio_1", "Lula_2", "Flávio_2"]], on=["uf", "mun", "zona", "secao"], how="left")

    # esperado pelo próprio município (taxa do município sem a seção) e excesso
    M = agregar(w, ["uf", "mun"])
    for t in (1, 2):
        taxa = M.set_index(["uf", "mun"])[[f"v{t}", f"s{t}"]]
        j = m[["uf", "mun"]].merge(taxa, left_on=["uf", "mun"], right_index=True, how="left")
        vo, so = (j[f"v{t}"] - m[f"v{t}"]).clip(lower=0), (j[f"s{t}"] - m[f"s{t}"]).clip(lower=0)
        p = np.where(vo > 0, so / vo.clip(lower=1), np.nan)
        m[f"esp{t}"] = p * m[f"v{t}"]
        m[f"exc{t}"] = m[f"s{t}"] - m[f"esp{t}"]
        sd = np.sqrt(m[f"v{t}"] * p * (1 - p))
        m[f"z{t}"] = np.where(sd > 0, m[f"exc{t}"] / np.where(sd > 0, sd, 1), np.nan)

    N = {"schema_version": "1.0", "gerado_em": time.strftime("%Y-%m-%d %H:%M"),
         "fonte": "Logs das urnas (Arquivos transmitidos para totalização, TSE) e boletins de urna (votacao_secao)",
         "definicao": "votos no log − habilitações “Tipo de habilitação do eleitor [biométrica]”", "min_votos": MIN_VOTOS,
         "faixas": [f[2] for f in FAIXAS], "turnos": {}}
    for t in (1, 2):
        g = m[m[f"log{t}"]]
        gd = d[d.turno == t]
        gb = g[(g[f"v{t}"] >= MIN_VOTOS)]
        pct = gb[f"s{t}"] / gb[f"v{t}"]
        dom = gb[gb.uf != "ZZ"]
        pdom = dom[f"s{t}"] / dom[f"v{t}"]
        topz = dom.nlargest(1, f"exc{t}").iloc[0]
        N["turnos"][str(t)] = {
            "votos": int(g[f"v{t}"].sum()), "sem_digital": int(g[f"s{t}"].sum()), "pct": float(g[f"s{t}"].sum() / max(1, g[f"v{t}"].sum())),
            "liberados_mesario": int(g[f"m{t}"].sum()),
            "exterior": int(g.loc[g.uf == "ZZ", f"s{t}"].sum()),
            "pct_brasil_sem_exterior": float(g.loc[g.uf != "ZZ", f"s{t}"].sum() / max(1, g.loc[g.uf != "ZZ", f"v{t}"].sum())),
            "digital_nao_confere": int(gd.biometria_nao_confere.sum()), "ano_nasc_confere": int(gd.ano_nasc_confere.sum()), "ano_nasc_diferente": int(gd.ano_nasc_diferente.sum()),
            "secoes": int(len(g)), "secoes_base": int(len(gb)),
            "secoes_50": int((pdom >= .5).sum()), "secoes_90": int((pdom >= .9).sum()),
            "secoes_z5": int((dom[f"z{t}"] >= 5).sum()),
            "faixas": [int(((pct >= lo) & (pct < hi)).sum()) for lo, hi, _ in FAIXAS],
            "maior_excesso": [topz.uf, int(topz.mun), nomes.get((topz.uf, int(topz.mun)), ""), int(topz.zona), int(topz.secao), int(topz[f"s{t}"]), int(topz[f"v{t}"]), float(topz[f"esp{t}"])],
        }

    # faixas do 2º turno × resultado (sem o exterior, onde todos votam sem digital)
    mm = m[m.log2 & m.Lula_2.notna() & (m.v2 >= MIN_VOTOS) & (m.uf != "ZZ")].copy()
    mm["faixa"] = (mm.s2 / mm.v2).map(faixa)
    N["faixas_resultado"] = []
    for _, _, rot in FAIXAS:
        g = mm[mm.faixa == rot]
        if len(g):
            L1, F1, L2, F2 = g.Lula_1.sum(), g["Flávio_1"].sum(), g.Lula_2.sum(), g["Flávio_2"].sum()
            N["faixas_resultado"].append({"faixa": rot, "secoes": int(len(g)), "lula1": float(L1 / max(1, L1 + F1)), "lula2": float(L2 / max(1, L2 + F2))})
    # mudança da seção entre os turnos × variação de Lula
    mm["dsd"] = mm.s2 / mm.v2 - mm.s1 / mm.v1.clip(lower=1)
    mm["dl"] = mm.Lula_2 / (mm.Lula_2 + mm["Flávio_2"]).clip(lower=1) - mm.Lula_1 / (mm.Lula_1 + mm["Flávio_1"]).clip(lower=1)
    ok = mm.v1 >= MIN_VOTOS
    N["correlacao_variacao"] = float(np.corrcoef(mm.loc[ok, "dsd"], mm.loc[ok, "dl"])[0, 1])

    U = agregar(w, ["uf"])
    N["ufs"] = {r.uf: [int(getattr(r, c)) for c in COLS] for r in U.itertuples()}
    M["nome"] = [nomes.get((u, int(c)), "") for u, c in zip(M.uf, M.mun)]
    N["municipios"] = {"colunas": ["uf", "mun", "nome"] + COLS, "linhas": M[["uf", "mun", "nome"] + COLS].values.tolist()}
    # seções mais acima do esperado pelo próprio município (Brasil, sem o exterior), nos dois turnos
    dom = m[(m.uf != "ZZ")]
    idx = set(dom[dom.v1 >= MIN_VOTOS].nlargest(300, "exc1").index) | set(dom[dom.v2 >= MIN_VOTOS].nlargest(300, "exc2").index)
    top = m.loc[sorted(idx)]
    r1 = lambda x: None if pd.isna(x) else round(float(x), 1)
    N["maiores_secoes"] = {"colunas": ["uf", "mun", "nome", "zona", "secao", "local", "v1", "s1", "m1", "esp1", "v2", "s2", "m2", "esp2", "leitor1", "cont1", "leitor2", "cont2"],
                           "linhas": [[r.uf, int(r.mun), nomes.get((r.uf, int(r.mun)), ""), int(r.zona), int(r.secao), r.NM_LOCAL_VOTACAO if isinstance(r.NM_LOCAL_VOTACAO, str) else "",
                                       int(r.v1), int(r.s1), int(r.m1), r1(r.esp1), int(r.v2), int(r.s2), int(r.m2), r1(r.esp2), int(r.l1 > 0), int(r.c1 > 0), int(r.l2 > 0), int(r.c2 > 0)] for r in top.itertuples()]}
    for t in (1, 2):
        g = dom[(dom[f"v{t}"] >= MIN_VOTOS)]
        alto = g[g[f"z{t}"] >= 5]
        N["turnos"][str(t)]["z5_com_leitor_ou_troca"] = int(((alto[f"l{t}"] > 0) | (alto[f"c{t}"] > 0)).sum())
        N["turnos"][str(t)]["base_com_leitor_ou_troca"] = float(((g[f"l{t}"] > 0) | (g[f"c{t}"] > 0)).mean())
    # persistência: seções muito acima do esperado no 2º turno que já estavam assim no 1º (sinal de causa no cadastro, não no dia)
    g = dom[(dom.v1 >= MIN_VOTOS) & (dom.v2 >= MIN_VOTOS)]
    N["persistencia"] = {"z5_t2": int((g.z2 >= 5).sum()), "z5_t2_e_t1": int(((g.z2 >= 5) & (g.z1 >= 5)).sum()),
                         "correlacao_pct": float(np.corrcoef(g.s1 / g.v1, g.s2 / g.v2)[0, 1])}
    with open(PORTAL_DADOS / "sem_digital.json", "w") as f:
        json.dump(N, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    pasta = PORTAL_DADOS / "sem_digital"
    pasta.mkdir(exist_ok=True)
    Z = agregar(w, ["uf", "mun", "zona"])
    for uf, gz in Z.groupby("uf"):
        g = m[m.uf == uf]
        alta = ((g.v1 >= MIN_VOTOS) & (g.s1 >= CORTE_SECAO * g.v1)) | ((g.v2 >= MIN_VOTOS) & (g.s2 >= CORTE_SECAO * g.v2))
        sec = g[alta]
        doc = {"corte": CORTE_SECAO,
               "zonas": {"colunas": ["mun", "zona"] + COLS, "linhas": gz[["mun", "zona"] + COLS].values.tolist()},
               "secoes": {"colunas": ["mun", "zona", "secao", "v1", "s1", "m1", "esp1", "v2", "s2", "m2", "esp2"],
                          "linhas": [[int(r.mun), int(r.zona), int(r.secao), int(r.v1), int(r.s1), int(r.m1), r1(r.esp1), int(r.v2), int(r.s2), int(r.m2), r1(r.esp2)] for r in sec.itertuples()]}}
        with open(pasta / f"{uf}.json", "w") as f:
            json.dump(doc, f, separators=(",", ":"), allow_nan=False)
    T = N["turnos"]
    for t in ("1", "2"):
        print(f"{t}º turno: {T[t]['sem_digital']:,} de {T[t]['votos']:,} votos sem digital ({100 * T[t]['pct']:.1f}%); mesário {T[t]['liberados_mesario']:,}")
    print(f"ok em {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
