"""Votos do exterior: resultado por cidade, país e continente nos dois turnos de 2026, com 2022 para comparação.

País, continente e coordenadas aproximadas das 186 cidades vêm de dados/referencia/cidades_exterior.csv (o arquivo do TSE só traz
o nome da cidade). 2022: historico_municipios.parquet (Lula = líder do 1º turno, Bolsonaro = 2º).
Saída: portal/dados/exterior.json
"""
import json

import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS, RAIZ

C1 = ["Lula_1", "Flávio_1", "Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1"]


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    z = s[s.SG_UF == "ZZ"]
    ref = pd.read_csv(RAIZ / "dados" / "referencia" / "cidades_exterior.csv", sep=";")
    g = z.groupby(["CD_MUNICIPIO", "NM_MUNICIPIO"]).sum(numeric_only=True).reset_index()
    g = g.merge(ref, left_on="NM_MUNICIPIO", right_on="cidade", how="left")
    faltam = g[g.pais.isna()].NM_MUNICIPIO.tolist()
    assert not faltam, f"cidades sem país: {faltam}"
    h = pd.read_parquet(PROCESSADOS / "historico_municipios.parquet")
    h22 = h[(h.ano == 2022) & (h.SG_UF == "ZZ")]
    t2_22 = h22[h22.NR_TURNO == 2].set_index("CD_MUNICIPIO")
    g["lula22"] = g.CD_MUNICIPIO.map(t2_22.lider)
    g["bolso22"] = g.CD_MUNICIPIO.map(t2_22.segundo)
    g["aptos22"] = g.CD_MUNICIPIO.map(t2_22.aptos)
    g["comp22"] = g.CD_MUNICIPIO.map(t2_22.comparecimento)

    def resumo(d):
        v1 = d[C1].sum().sum()
        fin2 = d.Lula_2.sum() + d["Flávio_2"].sum()
        tem22 = d.lula22.notna()
        f22 = (d.lula22[tem22].sum() + d.bolso22[tem22].sum())
        return {"aptos": int(d.Aptos_2.sum()), "comparecimento2": int(d.Comp_2.sum()), "comp2_pct": round(100 * d.Comp_2.sum() / max(1, d.Aptos_2.sum()), 2),
                "comp1_pct": round(100 * d.Comp_1.sum() / max(1, d.Aptos_1.sum()), 2),
                "lula1": round(100 * d.Lula_1.sum() / max(1, v1), 2), "flavio1": round(100 * d["Flávio_1"].sum() / max(1, v1), 2),
                "lula2": round(100 * d.Lula_2.sum() / max(1, fin2), 2), "votos_lula2": int(d.Lula_2.sum()), "votos_flavio2": int(d["Flávio_2"].sum()),
                "lula22": round(100 * d.lula22[tem22].sum() / f22, 2) if f22 else None,
                "comp22_pct": round(100 * d.comp22[tem22].sum() / d.aptos22[tem22].sum(), 2) if tem22.any() and d.aptos22[tem22].sum() else None,
                "secoes": None}
    secoes = z.groupby("CD_MUNICIPIO").size()
    cidades = []
    for r in g.itertuples():
        d = g[g.CD_MUNICIPIO == r.CD_MUNICIPIO]
        x = resumo(d)
        x.update({"cod": int(r.CD_MUNICIPIO), "cidade": r.NM_MUNICIPIO.title(), "pais": r.pais, "continente": r.continente, "lat": float(r.lat), "lon": float(r.lon),
                  "secoes": int(secoes.get(r.CD_MUNICIPIO, 0))})
        cidades.append(x)
    paises = []
    for p, d in g.groupby("pais"):
        x = resumo(d); x.update({"pais": p, "continente": d.continente.iloc[0], "cidades": int(len(d)), "secoes": int(secoes[d.CD_MUNICIPIO].sum())})
        paises.append(x)
    conts = []
    for c, d in g.groupby("continente"):
        x = resumo(d); x.update({"continente": c, "paises": int(d.pais.nunique()), "cidades": int(len(d)), "secoes": int(secoes[d.CD_MUNICIPIO].sum())})
        conts.append(x)
    tot = resumo(g); tot.update({"cidades": int(len(g)), "paises": int(g.pais.nunique()), "secoes": int(len(z))})
    out = {"total": tot, "continentes": sorted(conts, key=lambda x: -x["aptos"]), "paises": sorted(paises, key=lambda x: -x["aptos"]),
           "cidades": sorted(cidades, key=lambda x: -x["aptos"]),
           "nota": "Coordenadas aproximadas do centro de cada cidade; país e continente atribuídos pelo nome da cidade no arquivo do TSE."}
    with open(PORTAL_DADOS / "exterior.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(tot)
    print([(p["pais"], p["aptos"], p["lula2"], p["lula22"]) for p in out["paises"][:8]])


if __name__ == "__main__":
    main()
