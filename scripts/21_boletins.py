"""Complemento do boletim de urna para o portal: votos de cada um dos "outros" candidatos do 1º turno por seção
e endereço de cada local de votação.

O portal já tem, por seção, os votos dos seis principais candidatos, brancos, nulos, abstenção e aptos
(portal/dados/secoes/<UF>.json). Este script acrescenta o que falta para mostrar o boletim completo.

Saída: portal/dados/bu/<UF>.json
  {"candidatos": [[número, nome], ...], "colunas": ["mun", "zona", "secao", <números>], "linhas": [...],
   "enderecos": {"mun-zona-local": endereço}}
"""
import json

import pandas as pd

from comum import ARQUIVOS, BRUTOS, CANDIDATOS, PORTAL_DADOS, VALIDOS, ler_csv_tse

OUTROS = sorted(VALIDOS - set(CANDIDATOS))


def main():
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"]
    d = ler_csv_tse(BRUTOS / ARQUIVOS["votacao_secao"][1], usecols=cols)
    nomes = d[d.NR_VOTAVEL.isin(OUTROS)].drop_duplicates("NR_VOTAVEL").set_index("NR_VOTAVEL").NM_VOTAVEL.to_dict()
    end = d.drop_duplicates(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"])
    o = d[(d.NR_TURNO == 1) & d.NR_VOTAVEL.isin(OUTROS)]
    p = o.pivot_table(index=["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"], columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum", fill_value=0)
    p = p.reindex(columns=OUTROS, fill_value=0).reset_index()
    (PORTAL_DADOS / "bu").mkdir(parents=True, exist_ok=True)
    for uf, g in p.groupby("SG_UF"):
        e = end[end.SG_UF == uf]
        out = {"candidatos": [[n, nomes.get(n, str(n)).title()] for n in OUTROS],
               "colunas": ["mun", "zona", "secao"] + [str(n) for n in OUTROS],
               "linhas": g.drop(columns="SG_UF").astype(int).values.tolist(),
               "enderecos": {f"{r.CD_MUNICIPIO}-{r.NR_ZONA}-{r.NR_LOCAL_VOTACAO}": str(r.DS_LOCAL_VOTACAO_ENDERECO).strip() for r in e.itertuples()}}
        with open(PORTAL_DADOS / "bu" / f"{uf}.json", "w") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(len(p), "seções;", {n: nomes.get(n) for n in OUTROS})


if __name__ == "__main__":
    main()
