"""Projeção durante a apuração do 2º turno e hora em que cada município teve metade das seções apuradas.

Projeção: em cada momento, a parcela de Lula entre os finalistas em cada UF (seções já apuradas) é ponderada pelo peso que
a UF tinha no 1º turno (votos nos dois finalistas, conhecido antes do 2º turno). UF ainda sem seções usa a parcela de Lula
no 1º turno mais a variação média já observada. Faixa de 98%: erro amostral das seções apuradas em cada UF (variância entre
seções da UF) e, para UFs sem seções, 3 pontos.

Saída: portal/dados/projecao.json
"""
import json

import numpy as np
import pandas as pd

from comum import ARQUIVOS, BRUTOS, PORTAL_DADOS, PROCESSADOS, ler_csv_tse

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
Z98 = 2.326
N_PONTOS = 240


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    h = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=CHAVE + ["NR_TURNO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"])
    h = h[h.NR_TURNO == 2]
    h["hora"] = pd.to_datetime(h.DT_PRIM_TOT_PARCIAL_HOR_TSE, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    x = s.merge(h[CHAVE + ["hora"]], on=CHAVE).dropna(subset=["hora"]).sort_values("hora", kind="stable").reset_index(drop=True)
    x["fin"] = x.Lula_2 + x["Flávio_2"]
    x = x[x.fin > 0].reset_index(drop=True)
    # modelo de variação: cada seção ainda não apurada recebe a parcela de Lula que teve no 1º turno mais a variação média
    # das seções já apuradas do mesmo município (3 ou mais), senão da UF, senão do país; o total de votos segue a razão 2º/1º
    x["fin1"] = x.Lula_1 + x["Flávio_1"]
    x = x[x.fin1 > 0].reset_index(drop=True)
    n = len(x)
    fin, lula = x.fin.to_numpy(float), x.Lula_2.to_numpy(float)
    f1 = x.fin1.to_numpy(float)
    s1 = x.Lula_1.to_numpy(float) / f1
    s2 = lula / fin
    sw = s2 - s1
    mun = pd.factorize(x.SG_UF + "-" + x.CD_MUNICIPIO.astype(str))[0]
    uf = pd.factorize(x.SG_UF)[0]
    M, U = mun.max() + 1, uf.max() + 1
    idx = np.unique(np.r_[np.geomspace(30, 0.05 * n, 60), np.linspace(0, n - 1, N_PONTOS)].astype(int))
    pontos = []
    for i in idx:
        c = np.zeros(n, bool); c[: i + 1] = True
        def media(g, G, v, peso):
            num = np.bincount(g[c], weights=(v * peso)[c], minlength=G); den = np.bincount(g[c], weights=peso[c], minlength=G); cnt = np.bincount(g[c], minlength=G)
            return num / np.where(den > 0, den, 1), cnt, den
        swm, cm, _ = media(mun, M, sw, f1)
        swu, cu, _ = media(uf, U, sw, f1)
        swb = float(np.average(sw[c], weights=f1[c]))
        # razão de comparecimento nos finalistas (2º/1º) pelo mesmo critério
        rm_n = np.bincount(mun[c], weights=fin[c], minlength=M); rm_d = np.bincount(mun[c], weights=f1[c], minlength=M)
        ru_n = np.bincount(uf[c], weights=fin[c], minlength=U); ru_d = np.bincount(uf[c], weights=f1[c], minlength=U)
        rb = fin[c].sum() / f1[c].sum()
        usa_m = cm[mun] >= 3
        usa_u = cu[uf] >= 3
        swp = np.where(usa_m, swm[mun], np.where(usa_u, swu[uf], swb))
        rp = np.where(usa_m, rm_n[mun] / np.where(rm_d[mun] > 0, rm_d[mun], 1), np.where(usa_u, ru_n[uf] / np.where(ru_d[uf] > 0, ru_d[uf], 1), rb))
        nc = ~c
        fin_p = f1[nc] * rp[nc]
        lula_p = fin_p * np.clip(s1[nc] + swp[nc], 0, 1)
        L = lula[c].sum() + lula_p.sum(); F = fin[c].sum() + fin_p.sum()
        proj = L / F
        # incerteza: variação média de cada grupo estimada com poucas seções (desvio entre seções / raiz do nº apurado)
        sd = float(np.sqrt(np.average((sw[c] - swb) ** 2, weights=f1[c]))) if c.sum() > 1 else 0.1
        ngrp = np.where(usa_m, cm[mun], np.where(usa_u, cu[uf], max(int(c.sum()), 1)))[nc]
        peso = fin_p / F
        # erro do grupo: soma dos pesos não apurados por grupo × sd/√n
        gk = np.where(usa_m[nc], mun[nc], M + np.where(usa_u[nc], uf[nc], U))
        wg = np.bincount(gk, weights=peso, minlength=M + U + 1)
        ng = np.bincount(gk, weights=ngrp, minlength=M + U + 1) / np.maximum(np.bincount(gk, minlength=M + U + 1), 1)
        se = float(np.sqrt(np.sum((wg * sd / np.sqrt(np.maximum(ng, 1))) ** 2) + 0.0005 ** 2))
        pontos.append([round(100 * (i + 1) / n, 3), x.hora[i].strftime("%H:%M"), round(100 * lula[c].sum() / fin[c].sum(), 3), round(100 * proj, 3),
                       round(100 * (proj - Z98 * se), 3), round(100 * (proj + Z98 * se), 3)])
    final = 100 * lula.sum() / fin.sum()
    P = np.array([p[3] for p in pontos]); LO = np.array([p[4] for p in pontos]); HI = np.array([p[5] for p in pontos])
    # primeiro momento a partir do qual a projeção não sai mais de ±0,5 ponto do resultado final
    fora = np.abs(P - final) > 0.5
    k0 = int(np.max(np.flatnonzero(fora)) + 1) if fora.any() else 0
    k0 = min(k0, len(pontos) - 1)
    fora1 = np.abs(P - final) > 0.1
    k1 = min(int(np.max(np.flatnonzero(fora1)) + 1) if fora1.any() else 0, len(pontos) - 1)
    dentro_faixa = int(((LO <= final) & (final <= HI)).sum())
    # metade das seções de cada município apurada (minutos desde o primeiro boletim)
    t0 = x.hora.min()
    x["min"] = ((x.hora - t0).dt.total_seconds() / 60).round().astype(int)
    m50 = x.groupby(["SG_UF", "CD_MUNICIPIO"])["min"].median().round().astype(int)
    tot_min = int(x["min"].max())
    out = {"turno": 2, "inicio": t0.strftime("%H:%M"), "fim": x.hora.max().strftime("%H:%M"), "minutos": tot_min, "final": round(final, 3),
           "pontos": pontos, "colunas": ["pct_secoes", "hora", "parcial", "projecao", "lo98", "hi98"],
           "marco": {"pct_secoes": float(pontos[k0][0]), "hora": pontos[k0][1], "projecao": float(pontos[k0][3]), "tolerancia_pp": 0.5},
           "marco_01": {"pct_secoes": float(pontos[k1][0]), "hora": pontos[k1][1], "projecao": float(pontos[k1][3]), "tolerancia_pp": 0.1},
           "faixa_contem_final": [dentro_faixa, len(pontos)],
           "mun_meia": {f"{u}-{c}": int(v) for (u, c), v in m50.items()},
           "metodo": "Parcela de Lula de cada UF nas seções apuradas, ponderada pelo peso da UF no 1º turno; UF sem seções usa o 1º turno mais a variação média observada. Faixa de 98% pelo erro amostral entre seções."}
    with open(PORTAL_DADOS / "projecao.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"final {final:.3f} · marco {out['marco']} · faixa contém o final em {dentro_faixa}/{len(pontos)} · {len(out['mun_meia'])} municípios")


if __name__ == "__main__":
    main()
