"""Resultados de Presidente, 1º e 2º turno, nas eleições de 2002 a 2022 (TSE).

Baixa votacao_candidato_munzona_<ano>.zip e detalhe_votacao_munzona_<ano>.zip, lê só as linhas
de Presidente e grava:
  - dados/processados/historico.json: totais nacionais por candidato
  - dados/processados/historico_municipios.parquet: por município e turno, votos dos dois
    primeiros colocados nacionais no 1º turno ("lider" e "segundo"), demais válidos, brancos,
    nulos, aptos e comparecimento
Os ZIPs são apagados depois de lidos.
"""
import io
import json
import shutil
import urllib.request
import zipfile

import pandas as pd

from comum import BRUTOS, PROCESSADOS, URL_BASE

ANOS = [2002, 2006, 2010, 2014, 2018, 2022]


def ler_zip(pasta, ano, colunas):
    caminho = BRUTOS / f"{pasta}_{ano}.zip"
    if not caminho.exists():
        with urllib.request.urlopen(f"{URL_BASE}/{pasta}/{pasta}_{ano}.zip") as r, open(caminho, "wb") as f:
            shutil.copyfileobj(r, f)
    partes = []
    with zipfile.ZipFile(caminho) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
        # quando existe o arquivo nacional só de Presidente (_BR), basta ele
        br = [n for n in nomes if n.upper().endswith("_BR.CSV")]
        for nome in br or [n for n in nomes if "BRASIL" not in n.upper()]:
            with z.open(nome) as f:
                df = pd.read_csv(io.TextIOWrapper(f, encoding="latin1"), sep=";", usecols=lambda c: c in colunas, dtype=str)
            partes.append(df[df.CD_CARGO == "1"])
    caminho.unlink()
    return pd.concat(partes)


def por_municipio(ano, c, d, ano_d):
    lider, segundo = (str(x[2]) for x in ano_d["1"]["candidatos"][:2])
    c = c.assign(papel=c.NR_CANDIDATO.map({lider: "lider", segundo: "segundo"}).fillna("outros"))
    v = c.pivot_table(index=["SG_UF", "CD_MUNICIPIO", "NR_TURNO"], columns="papel", values="QT_VOTOS_NOMINAIS", aggfunc="sum", fill_value=0)
    nulos = "QT_TOTAL_VOTOS_NULOS" if "QT_TOTAL_VOTOS_NULOS" in d else "QT_VOTOS_NULOS"
    dd = d.groupby(["SG_UF", "CD_MUNICIPIO", "NR_TURNO"])[["QT_APTOS", "QT_COMPARECIMENTO", "QT_VOTOS_BRANCOS", nulos]].sum()
    dd.columns = ["aptos", "comparecimento", "brancos", "nulos"]
    m = v.join(dd, how="outer").fillna(0).reset_index()
    m.insert(0, "ano", ano)
    m["CD_MUNICIPIO"] = m.CD_MUNICIPIO.astype(int)
    m["NR_TURNO"] = m.NR_TURNO.astype(int)
    if "outros" not in m:
        m["outros"] = 0
    return m


def por_zona(ano, c, d):
    """Votos de cada candidato e totais por zona eleitoral (unidade da migração histórica)."""
    chave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_TURNO"]
    zc = c.groupby(chave + ["NR_CANDIDATO"]).QT_VOTOS_NOMINAIS.sum().reset_index()
    nulos = "QT_TOTAL_VOTOS_NULOS" if "QT_TOTAL_VOTOS_NULOS" in d else "QT_VOTOS_NULOS"
    zd = d.groupby(chave)[["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", nulos]].sum().reset_index()
    zd.columns = chave + ["aptos", "comparecimento", "abstencoes", "brancos", "nulos"]
    for z in (zc, zd):
        z.insert(0, "ano", ano)
        for k in ("CD_MUNICIPIO", "NR_ZONA", "NR_TURNO"):
            z[k] = z[k].astype(int)
    zc["NR_CANDIDATO"] = zc.NR_CANDIDATO.astype(int)
    return zc, zd


def main():
    saida, municipios, zonas_cand, zonas_det = {}, [], [], []
    for ano in ANOS:
        c = ler_zip("votacao_candidato_munzona", ano, {"NR_TURNO", "CD_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO", "QT_VOTOS_NOMINAIS",
                                                       "SG_UF", "CD_MUNICIPIO", "NR_ZONA"})
        c["QT_VOTOS_NOMINAIS"] = c.QT_VOTOS_NOMINAIS.astype(int)
        d = ler_zip("detalhe_votacao_munzona", ano, {"NR_TURNO", "CD_CARGO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
                                                     "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS", "QT_TOTAL_VOTOS_NULOS"})
        num = [x for x in d.columns if x.startswith("QT_")]
        d[num] = d[num].astype(int)
        ano_d = {}
        for t in ("1", "2"):
            ct = c[c.NR_TURNO == t]
            if ct.empty:
                continue
            cand = (ct.groupby(["NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO"]).QT_VOTOS_NOMINAIS.sum()
                    .sort_values(ascending=False).reset_index())
            dt = d[d.NR_TURNO == t][num].sum()
            ano_d[t] = {"candidatos": [[r.NM_URNA_CANDIDATO.title(), r.SG_PARTIDO, int(r.NR_CANDIDATO), int(r.QT_VOTOS_NOMINAIS)] for r in cand.itertuples()],
                        "aptos": int(dt.QT_APTOS), "comparecimento": int(dt.QT_COMPARECIMENTO), "abstencoes": int(dt.QT_ABSTENCOES),
                        "brancos": int(dt.QT_VOTOS_BRANCOS),
                        "nulos": int(dt.get("QT_TOTAL_VOTOS_NULOS", dt.get("QT_VOTOS_NULOS", 0)))}
        saida[ano] = ano_d
        municipios.append(por_municipio(ano, c, d, ano_d))
        zc, zd = por_zona(ano, c, d)
        zonas_cand.append(zc)
        zonas_det.append(zd)
        top = ano_d["1"]["candidatos"][:2]
        print(ano, "1º:", top, "2º:", ano_d.get("2", {}).get("candidatos", [])[:2], flush=True)
    pd.concat(municipios).to_parquet(PROCESSADOS / "historico_municipios.parquet", index=False)
    pd.concat(zonas_cand).to_parquet(PROCESSADOS / "historico_zonas_candidatos.parquet", index=False)
    pd.concat(zonas_det).to_parquet(PROCESSADOS / "historico_zonas_detalhe.parquet", index=False)
    with open(PROCESSADOS / "historico.json", "w") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
