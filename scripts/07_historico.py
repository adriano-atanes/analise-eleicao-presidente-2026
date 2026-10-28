"""Totais nacionais de Presidente, 1º e 2º turno, nas eleições de 2002 a 2022 (TSE).

Baixa votacao_candidato_munzona_<ano>.zip e detalhe_votacao_munzona_<ano>.zip, lê só as linhas
de Presidente e grava dados/processados/historico.json. Os ZIPs são apagados depois de lidos.
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


def main():
    saida = {}
    for ano in ANOS:
        c = ler_zip("votacao_candidato_munzona", ano, {"NR_TURNO", "CD_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO", "QT_VOTOS_NOMINAIS"})
        c["QT_VOTOS_NOMINAIS"] = c.QT_VOTOS_NOMINAIS.astype(int)
        d = ler_zip("detalhe_votacao_munzona", ano, {"NR_TURNO", "CD_CARGO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
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
        top = ano_d["1"]["candidatos"][:2]
        print(ano, "1º:", top, "2º:", ano_d.get("2", {}).get("candidatos", [])[:2], flush=True)
    with open(PROCESSADOS / "historico.json", "w") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
