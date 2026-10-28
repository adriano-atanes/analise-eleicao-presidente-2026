"""Teste de sensibilidade da migração: repete a estimativa agregando as seções em zonas.

Se o comportamento do eleitor variasse pouco dentro de cada estado, os dois níveis
dariam o mesmo resultado. Onde divergem, a estimativa depende mais da premissa do modelo
do que dos dados; o portal mostra os dois valores.
Saída: dados/processados/sensibilidade.json
"""
import importlib
import json

import numpy as np
import pandas as pd

from comum import DESTINOS, ORIGENS, PROCESSADOS

m = importlib.import_module("03_migracao")


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    num = [c for c in s.columns if c[-2:] in ("_1", "_2")]
    zonas = s.groupby(["SG_UF", "CD_MUNICIPIO", "NR_ZONA"], as_index=False)[num].sum()
    X, Y, w, _ = m.matrizes(zonas)
    XtX, XtY, _ = m.suficientes(X, Y, w)
    B_br = m.resolver(XtX, XtY)
    total = 0
    for uf, g in zonas.groupby("SG_UF"):
        X, Y, w, g = m.matrizes(g)
        XtX, XtY, n = m.suficientes(X, Y, w)
        total = total + m.fluxo(m.resolver(XtX, XtY, B_br, m.LAMBDA_UF, n), g)
    pct = 100 * total / total.sum(1, keepdims=True)
    with open(PROCESSADOS / "sensibilidade.json", "w") as f:
        json.dump({"nivel": "zona eleitoral", "unidades": len(zonas), "pct": np.round(pct, 2).tolist()}, f)
    print(pd.DataFrame(pct, index=ORIGENS, columns=DESTINOS).round(1))


if __name__ == "__main__":
    main()
