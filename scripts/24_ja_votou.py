"""Indicador “O eleitor identificado já votou”: quantas vezes a urna recusou habilitar um eleitor que já tinha votado.

A mensagem aparece no log da urna quando o mesário digita o título ou o CPF de um eleitor que já votou naquela seção.
A urna não habilita o eleitor de novo: nenhum voto a mais é registrado. Este script consolida a contagem por turno,
estado, município, zona e seção (100% das seções com log) e cruza com o resultado da seção.

Entradas: dados/processados/logs/<turno>_<UF>.parquet (16_logs_urnas.py) e dados/processados/secoes.parquet.
Saídas:   portal/dados/ja_votou.json (Brasil, estados, municípios, maiores seções, faixas)
          portal/dados/ja_votou/<UF>.json (zonas e todas as seções com ao menos um alerta)
"""
import glob
import json
import time

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS

FAIXAS = [(0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3 a 4"), (5, 9, "5 a 9"), (10, 19, "10 a 19"), (20, 49, "20 a 49"), (50, 10**9, "50 ou mais")]


def carregar_logs():
    partes = []
    for f in sorted(glob.glob(str(PROCESSADOS / "logs" / "*.parquet"))):
        t = int(f.split("/")[-1][0])
        d = pd.read_parquet(f, columns=["uf", "mun", "zona", "secao", "votos_log", "eleitor_ja_votou"])
        partes.append(d.assign(turno=t))
    d = pd.concat(partes, ignore_index=True)
    d["eleitor_ja_votou"] = d.eleitor_ja_votou.fillna(0).astype(int)
    d["votos_log"] = d.votos_log.fillna(0).astype(int)
    w = d.pivot_table(index=["uf", "mun", "zona", "secao"], columns="turno", values=["eleitor_ja_votou", "votos_log"], aggfunc="sum")
    w.columns = [f"{'a' if c == 'eleitor_ja_votou' else 'v'}{t}" for c, t in w.columns]
    w = w.reset_index()
    for t in (1, 2):
        w[f"log{t}"] = w[f"v{t}"].notna()
        w[f"a{t}"] = w[f"a{t}"].fillna(0).astype(int)
        w[f"v{t}"] = w[f"v{t}"].fillna(0).astype(int)
    return w


def faixa(n):
    for lo, hi, rot in FAIXAS:
        if lo <= n <= hi:
            return rot
    return FAIXAS[-1][2]


def resumo_turno(w, t, nomes):
    g = w[w[f"log{t}"]]
    a, v = g[f"a{t}"], g[f"v{t}"]
    top = g.nlargest(1, f"a{t}").iloc[0]
    hist = [int(((a >= lo) & (a <= hi)).sum()) for lo, hi, _ in FAIXAS]
    return {
        "alertas": int(a.sum()), "secoes_com_log": int(len(g)), "secoes_com_alerta": int((a > 0).sum()),
        "votos_log": int(v.sum()), "por_mil": float(1000 * a.sum() / max(1, v.sum())),
        "secoes_10mais": int((a >= 10).sum()), "secoes_50mais": int((a >= 50).sum()),
        "media_com_alerta": float(a[a > 0].mean()) if (a > 0).any() else 0.0,
        "maior": [top.uf, int(top.mun), nomes.get((top.uf, int(top.mun)), ""), int(top.zona), int(top.secao), int(top[f"a{t}"]), int(top[f"v{t}"])],
        "faixas": hist,
    }


def agregar(w, chaves):
    g = w.groupby(chaves)
    out = pd.DataFrame({
        "a1": g.a1.sum(), "s1": g.log1.sum(), "sa1": g.a1.apply(lambda s: int((s > 0).sum())), "v1": g.v1.sum(),
        "a2": g.a2.sum(), "s2": g.log2.sum(), "sa2": g.a2.apply(lambda s: int((s > 0).sum())), "v2": g.v2.sum(),
    }).reset_index()
    for c in ("a1", "s1", "sa1", "v1", "a2", "s2", "sa2", "v2"):
        out[c] = out[c].astype(int)
    return out


def main():
    t0 = time.time()
    w = carregar_logs()
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    s = s.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    nomes = {(r.uf, int(r.mun)): r.NM_MUNICIPIO for r in s[["uf", "mun", "NM_MUNICIPIO"]].drop_duplicates().itertuples()}
    m = w.merge(s[["uf", "mun", "zona", "secao", "NM_LOCAL_VOTACAO", "Lula_1", "Flávio_1", "Lula_2", "Flávio_2", "Aptos_2", "Comp_1", "Comp_2"]],
                on=["uf", "mun", "zona", "secao"], how="left")

    N = {"schema_version": "1.0", "gerado_em": time.strftime("%Y-%m-%d %H:%M"),
         "fonte": "Logs das urnas (Arquivos transmitidos para totalização, TSE) e boletins de urna (votacao_secao)",
         "mensagem": "O eleitor identificado já votou", "faixas": [f[2] for f in FAIXAS], "turnos": {}}
    for t in (1, 2):
        N["turnos"][str(t)] = resumo_turno(w, t, nomes)
    ambos = w[w.log1 & w.log2]
    N["ambos"] = {"secoes": int(len(ambos)), "alerta_nos_dois": int(((ambos.a1 > 0) & (ambos.a2 > 0)).sum()),
                  "correlacao": float(np.corrcoef(ambos.a1, ambos.a2)[0, 1]),
                  "correlacao_por_mil": float(np.corrcoef(1000 * ambos.a1 / ambos.v1.clip(lower=1), 1000 * ambos.a2 / ambos.v2.clip(lower=1))[0, 1])}

    # faixas do 2º turno × resultado da seção
    mm = m[m.log2 & m.Lula_2.notna()].copy()
    mm["faixa"] = mm.a2.map(faixa)
    grupos = []
    for _, _, rot in FAIXAS:
        g = mm[mm.faixa == rot]
        if not len(g):
            continue
        L1, F1, L2, F2 = g.Lula_1.sum(), g["Flávio_1"].sum(), g.Lula_2.sum(), g["Flávio_2"].sum()
        grupos.append({"faixa": rot, "secoes": int(len(g)), "aptos": int(g.Aptos_2.sum()), "alertas": int(g.a2.sum()),
                       "lula1": float(L1 / max(1, L1 + F1)), "lula2": float(L2 / max(1, L2 + F2)),
                       "comparecimento2": float(g.Comp_2.sum() / max(1, g.Aptos_2.sum()))})
    N["faixas_resultado"] = grupos

    # estados e municípios
    U = agregar(w, ["uf"])
    N["ufs"] = {r.uf: [int(r.a1), int(r.s1), int(r.sa1), int(r.v1), int(r.a2), int(r.s2), int(r.sa2), int(r.v2)] for r in U.itertuples()}
    M = agregar(w, ["uf", "mun"])
    M["nome"] = [nomes.get((u, int(c)), "") for u, c in zip(M.uf, M.mun)]
    N["municipios"] = {"colunas": ["uf", "mun", "nome", "a1", "s1", "sa1", "v1", "a2", "s2", "sa2", "v2"],
                       "linhas": M[["uf", "mun", "nome", "a1", "s1", "sa1", "v1", "a2", "s2", "sa2", "v2"]].values.tolist()}
    # maiores seções (em qualquer turno)
    m["amax"] = m[["a1", "a2"]].max(axis=1)
    top = m.nlargest(300, "amax")
    N["maiores_secoes"] = {"colunas": ["uf", "mun", "nome", "zona", "secao", "local", "a1", "v1", "a2", "v2"],
                           "linhas": [[r.uf, int(r.mun), nomes.get((r.uf, int(r.mun)), ""), int(r.zona), int(r.secao), r.NM_LOCAL_VOTACAO if isinstance(r.NM_LOCAL_VOTACAO, str) else "",
                                       int(r.a1), int(r.v1), int(r.a2), int(r.v2)] for r in top.itertuples()]}
    PORTAL_DADOS.mkdir(parents=True, exist_ok=True)
    with open(PORTAL_DADOS / "ja_votou.json", "w") as f:
        json.dump(N, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    # por UF: zonas e todas as seções com ao menos um alerta
    pasta = PORTAL_DADOS / "ja_votou"
    pasta.mkdir(exist_ok=True)
    Z = agregar(w, ["uf", "mun", "zona"])
    for uf, gz in Z.groupby("uf"):
        sec = w[(w.uf == uf) & ((w.a1 > 0) | (w.a2 > 0))]
        doc = {"zonas": {"colunas": ["mun", "zona", "a1", "s1", "sa1", "v1", "a2", "s2", "sa2", "v2"],
                         "linhas": gz[["mun", "zona", "a1", "s1", "sa1", "v1", "a2", "s2", "sa2", "v2"]].values.tolist()},
               "secoes": {"colunas": ["mun", "zona", "secao", "a1", "v1", "a2", "v2"],
                          "linhas": sec[["mun", "zona", "secao", "a1", "v1", "a2", "v2"]].values.tolist()}}
        with open(pasta / f"{uf}.json", "w") as f:
            json.dump(doc, f, separators=(",", ":"))
    T = N["turnos"]
    print(f"1º turno: {T['1']['alertas']:,} alertas em {T['1']['secoes_com_alerta']:,} seções · 2º turno: {T['2']['alertas']:,} em {T['2']['secoes_com_alerta']:,}")
    print(f"ok em {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
