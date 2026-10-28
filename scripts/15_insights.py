"""Novos recortes para o portal: mapas municipais, perfil do eleitorado, 2022 × 2026 e curva da apuração.

Saídas
  portal/dados/mapa/indicadores.json   indicadores por município (código TSE) para os mapas
  portal/dados/insights.json           perfil, abstenção por perfil, 2022 × 2026 e curva da apuração
  dados/processados/locais.parquet     coordenadas dos locais de votação (usadas por 04_gerar_portal.py)

Fontes TSE: perfil_comparecimento_abstencao_2026 (perfil dos aptos e abstenção; até a geração deste
arquivo o TSE publicou só o 1º turno), eleitorado_local_votacao_2026 (coordenadas dos locais),
detalhe_votacao_secao (horário de totalização de cada seção) e os arquivos já processados.
"""
import json
import zipfile

import numpy as np
import pandas as pd

from comum import ARQUIVOS, BRUTOS, CHAVE_SECAO, PORTAL_DADOS, PROCESSADOS, ler_csv_tse

ELIM = ["Renan", "Cury", "Caiado", "Zema", "Outros"]
DIREITA = ["Renan", "Caiado", "Zema"]
FAIXAS = [("16 a 24", ["16 anos", "17 anos", "18 anos", "19 anos", "20 anos", "21 a 24 anos"]), ("25 a 34", ["25 a 29 anos", "30 a 34 anos"]),
          ("35 a 44", ["35 a 39 anos", "40 a 44 anos"]), ("45 a 59", ["45 a 49 anos", "50 a 54 anos", "55 a 59 anos"]),
          ("60 a 69", ["60 a 64 anos", "65 a 69 anos"]), ("70 ou mais", ["70 a 74 anos", "75 a 79 anos", "80 a 84 anos", "85 a 89 anos",
                                                                         "90 a 94 anos", "95 a 99 anos", "100 anos ou mais"])]
ESCOL = [("Analfabeto ou lê e escreve", ["ANALFABETO", "LÊ E ESCREVE"]), ("Fundamental", ["ENSINO FUNDAMENTAL INCOMPLETO", "ENSINO FUNDAMENTAL COMPLETO"]),
         ("Médio", ["ENSINO MÉDIO INCOMPLETO", "ENSINO MÉDIO COMPLETO"]), ("Superior", ["SUPERIOR INCOMPLETO", "SUPERIOR COMPLETO"])]


def grupo(valor, grupos):
    for nome, lista in grupos:
        if valor in lista:
            return nome
    return None


def perfil():
    """Aptos e comparecimento por município e categoria (idade, escolaridade, gênero)."""
    z = zipfile.ZipFile(BRUTOS / "perfil_comparecimento_abstencao_2026.zip")
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_GENERO", "DS_FAIXA_ETARIA", "DS_GRAU_INSTRUCAO", "QT_APTOS", "QT_COMPARECIMENTO"]
    partes = []
    for nome in z.namelist():
        if not nome.endswith(".csv") or "BRASIL" in nome:
            continue
        for b in pd.read_csv(z.open(nome), sep=";", encoding="latin1", usecols=cols, chunksize=2_000_000):
            b["idade"] = b.DS_FAIXA_ETARIA.str.strip().map(lambda v: grupo(v, FAIXAS))
            b["escol"] = b.DS_GRAU_INSTRUCAO.str.strip().map(lambda v: grupo(v, ESCOL))
            partes.append(b.groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_GENERO", "idade", "escol"], dropna=False)[["QT_APTOS", "QT_COMPARECIMENTO"]].sum())
    return pd.concat(partes).groupby(level=list(range(6)), dropna=False).sum().reset_index()


def abstencao_por_perfil(p):
    out = {}
    for t, g in p.groupby("NR_TURNO"):
        r = {}
        for dim, ordem in [("idade", [n for n, _ in FAIXAS]), ("escol", [n for n, _ in ESCOL]), ("DS_GENERO", ["FEMININO", "MASCULINO"])]:
            x = g.groupby(dim)[["QT_APTOS", "QT_COMPARECIMENTO"]].sum().reindex(ordem)
            r[dim] = {"categorias": [c.title() if dim == "DS_GENERO" else c for c in ordem],
                      "aptos": x.QT_APTOS.astype(int).tolist(),
                      "abstencao_pct": (100 * (1 - x.QT_COMPARECIMENTO / x.QT_APTOS)).round(2).tolist()}
        out[str(int(t))] = r
    return out


def municipios(s, p, h, aud):
    num = [c for c in s.columns if c[-2:] in ("_1", "_2")]
    m = s.groupby(["SG_UF", "CD_MUNICIPIO"])[num].sum()
    v1 = m[[f"{o}_1" for o in ["Lula", "Flávio"] + ELIM]].sum(axis=1)
    v2 = m.Lula_2 + m["Flávio_2"]
    d = pd.DataFrame(index=m.index)
    d["aptos"] = m.Aptos_2
    d["lula1"] = 100 * m.Lula_1 / v1
    d["fla1"] = 100 * m["Flávio_1"] / v1
    d["lula2"] = 100 * m.Lula_2 / v2
    d["margem1"] = d.lula1 - d.fla1
    d["margem2"] = 2 * d.lula2 - 100
    d["dlula"] = d.lula2 - 100 * m.Lula_1 / (m.Lula_1 + m["Flávio_1"])   # variação entre os finalistas
    d["dcomp"] = 100 * (m.Comp_2 / m.Aptos_2 - m.Comp_1 / m.Aptos_1)
    d["abst2"] = 100 * m.Abst_2 / m.Aptos_2
    d["bn2"] = 100 * (m.Branco_2 + m.Nulo_2) / m.Comp_2
    d["elim1"] = 100 * m[[f"{o}_1" for o in ELIM]].sum(axis=1) / v1
    d["direita1"] = 100 * m[[f"{o}_1" for o in DIREITA]].sum(axis=1) / v1
    d["cury1"] = 100 * m.Cury_1 / v1
    # 2022: Lula no 2º turno (lider de 2022), em % dos votos nos finalistas
    h22 = h[(h.ano == 2022) & (h.NR_TURNO == 2)].set_index(["SG_UF", "CD_MUNICIPIO"])
    d["lula2022"] = 100 * h22.lider / (h22.lider + h22.segundo)
    d["d2022"] = d.lula2 - d.lula2022
    # seções atípicas da auditoria
    col = {k: i for i, k in enumerate(aud["suspeitas"]["colunas"])}
    atip = pd.Series([(l[col["uf"]], l[col["mun"]]) for l in aud["suspeitas"]["linhas"]]).value_counts()
    d["atipicas"] = [int(atip.get(k, 0)) for k in d.index]
    # perfil (1º turno)
    p1 = p[p.NR_TURNO == 1].groupby(["SG_UF", "CD_MUNICIPIO", "idade", "escol", "DS_GENERO"], dropna=False).QT_APTOS.sum().reset_index()
    tot = p1.groupby(["SG_UF", "CD_MUNICIPIO"]).QT_APTOS.sum()
    share = lambda mask: 100 * p1[mask].groupby(["SG_UF", "CD_MUNICIPIO"]).QT_APTOS.sum().reindex(tot.index, fill_value=0) / tot
    d["jovens"] = share(p1.idade == "16 a 24")
    d["idosos"] = share(p1.idade.isin(["60 a 69", "70 ou mais"]))
    d["superior"] = share(p1.escol == "Superior")
    d["baixa_escol"] = share(p1.escol.isin(["Analfabeto ou lê e escreve", "Fundamental"]))
    d["mulheres"] = share(p1.DS_GENERO == "FEMININO")
    return d


def por_perfil(d):
    """Variação de Lula e do comparecimento por quintil de cada característica do município."""
    d = d[d.index.get_level_values(0) != "ZZ"].dropna(subset=["jovens", "dlula"])
    out = {}
    for var, rot in [("superior", "Eleitores com ensino superior"), ("baixa_escol", "Eleitores com até o fundamental"), ("jovens", "Eleitores de 16 a 24 anos"),
                     ("idosos", "Eleitores com 60 anos ou mais"), ("aptos", "Tamanho do eleitorado"), ("direita1", "Voto nos eliminados de direita (1º turno)"),
                     ("cury1", "Voto em Augusto Cury (1º turno)"), ("lula2022", "Voto em Lula em 2022 (2º turno)")]:
        q = pd.qcut(d[var].rank(method="first"), 5, labels=False)
        g = d.groupby(q)
        w = lambda x, c: np.average(x[c], weights=x.aptos)
        out[var] = {"rotulo": rot,
                    "faixas": [f"{g[var].min().iloc[i]:.0f}–{g[var].max().iloc[i]:.0f}" if var != "aptos" else f"{int(g[var].min().iloc[i]):,}–{int(g[var].max().iloc[i]):,}".replace(",", ".")
                               for i in range(5)],
                    "dlula": [round(w(x, "dlula"), 2) for _, x in g], "dcomp": [round(w(x, "dcomp"), 2) for _, x in g],
                    "lula2": [round(w(x, "lula2"), 2) for _, x in g], "municipios": g.size().astype(int).tolist()}
    # regressão padronizada: o que mais explica a variação de Lula entre municípios
    d = d.dropna(subset=["superior", "jovens", "idosos", "direita1", "cury1", "dcomp", "lula2022", "aptos"])
    X = d[["superior", "jovens", "idosos", "direita1", "cury1", "dcomp", "lula2022"]].copy()
    X["log_aptos"] = np.log(d.aptos)
    Z = (X - X.mean()) / X.std()
    A = np.column_stack([np.ones(len(Z)), Z.to_numpy()])
    wt = np.sqrt(d.aptos.to_numpy(float))
    beta, *_ = np.linalg.lstsq(A * wt[:, None], d.dlula.to_numpy() * wt, rcond=None)
    pred = A @ beta
    r2 = 1 - np.average((d.dlula - pred) ** 2, weights=d.aptos) / np.average((d.dlula - np.average(d.dlula, weights=d.aptos)) ** 2, weights=d.aptos)
    out["_regressao"] = {"r2": float(r2), "coef_padronizados": dict(zip(X.columns, map(float, beta[1:])))}
    return out


def comparacao_2022(d, h):
    h22 = h[(h.ano == 2022)]
    tot22 = h22.groupby("NR_TURNO")[["lider", "segundo"]].sum()
    ufs = {}
    for uf, g in d.groupby(level=0):
        if uf == "ZZ":
            continue
        w = g.aptos
        ufs[uf] = {"lula2022": float(np.average(g.lula2022.dropna(), weights=w[g.lula2022.notna()])), "lula2026": float(np.average(g.lula2, weights=w))}
    ok = d.dropna(subset=["d2022"])
    ok = ok[ok.index.get_level_values(0) != "ZZ"]
    porte = []
    for lo, hi, rot in [(0, 10_000, "até 10 mil eleitores"), (10_000, 50_000, "10 mil a 50 mil"), (50_000, 200_000, "50 mil a 200 mil"), (200_000, 1e12, "mais de 200 mil")]:
        g = ok[(ok.aptos >= lo) & (ok.aptos < hi)]
        porte.append({"faixa": rot, "municipios": int(len(g)), "mediana": float(g.d2022.median()), "pct_melhorou": float(100 * (g.d2022 > 0).mean()),
                      "eleitores": int(g.aptos.sum())})
    return {"por_porte": porte, "brasil_2022": float(100 * tot22.loc[2, "lider"] / tot22.loc[2].sum()),
            "municipios_lula_ganhou": int((ok.d2022 > 0).sum()), "municipios_lula_perdeu": int((ok.d2022 < 0).sum()),
            "hist_d2022": np.histogram(np.clip(ok.d2022, -20, 19.99), bins=np.arange(-20, 21, 1))[0].tolist(),
            "mediana_d2022": float(ok.d2022.median()), "ufs": ufs}


def curva_apuracao(s):
    """Evolução da contagem pela hora da 1ª totalização de cada seção, com a região de origem dos votos."""
    cols = CHAVE_SECAO + ["NR_TURNO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"]
    t = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=cols)
    t["hora"] = pd.to_datetime(t.DT_PRIM_TOT_PARCIAL_HOR_TSE, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    out = {}
    for turno in (1, 2):
        x = t[t.NR_TURNO == turno].merge(s[CHAVE_SECAO + ["REGIAO", f"Lula_{turno}", f"Flávio_{turno}"]], on=CHAVE_SECAO).dropna(subset=["hora"])
        x["minuto"] = x.hora.dt.floor("min")
        x["ne"] = (x.REGIAO == "Nordeste") * (x[f"Lula_{turno}"] + x[f"Flávio_{turno}"])
        m = x.groupby("minuto").agg(l=(f"Lula_{turno}", "sum"), f=(f"Flávio_{turno}", "sum"), ne=("ne", "sum"), n=("NR_SECAO", "size")).cumsum()
        m["lula"] = 100 * m.l / (m.l + m.f)
        m["fla"] = 100 - m.lula
        m["pct_secoes"] = 100 * m.n / len(x)
        m["pct_nordeste"] = 100 * m["ne"] / (m.l + m.f)
        estavel = m[m.pct_secoes >= 2]  # ignora o comecinho, quando poucas seções decidem o sinal
        lider = (estavel.lula > estavel.fla).astype(int)
        trocas = estavel[lider.ne(lider.shift()) & lider.shift().notna()]
        amostra = m.iloc[np.unique(np.linspace(0, len(m) - 1, 300).astype(int))]
        tot_ne = 100 * x["ne"].sum() / (x[f"Lula_{turno}"] + x[f"Flávio_{turno}"]).sum()
        out[str(turno)] = {"hora": [h.strftime("%H:%M") for h in amostra.index], "pct_secoes": amostra.pct_secoes.round(2).tolist(),
                           "lula": amostra.lula.round(3).tolist(), "fla": amostra.fla.round(3).tolist(), "pct_nordeste": amostra.pct_nordeste.round(2).tolist(),
                           "nordeste_no_total": round(float(tot_ne), 2),
                           "trocas_lideranca": [{"hora": h.strftime("%H:%M"), "pct_secoes": round(float(r.pct_secoes), 1), "lider": "Lula" if r.lula > r.fla else "Flávio"}
                                                for h, r in trocas.iterrows()]}
        print(f"turno {turno}: {len(x)} seções; trocas de liderança após 2% apurado: {out[str(turno)]['trocas_lideranca']}")
    return out


def locais():
    z = zipfile.ZipFile(BRUTOS / "eleitorado_local_votacao_2026.zip")
    nome = next(n for n in z.namelist() if n.endswith("BRASIL.csv"))
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE", "NM_BAIRRO"]
    partes = [b[b.NR_TURNO == 2] for b in pd.read_csv(z.open(nome), sep=";", encoding="latin1", usecols=cols, dtype={"NR_LATITUDE": str, "NR_LONGITUDE": str},
                                                       chunksize=1_000_000)]
    l = pd.concat(partes).drop_duplicates(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"])
    for c in ("NR_LATITUDE", "NR_LONGITUDE"):
        l[c] = pd.to_numeric(l[c].str.replace(",", "."), errors="coerce")
    l.loc[(l.NR_LATITUDE == -1) | (l.NR_LONGITUDE == -1) | l.NR_LATITUDE.abs().gt(40), ["NR_LATITUDE", "NR_LONGITUDE"]] = np.nan
    l = l[["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE", "NM_BAIRRO"]]
    l.to_parquet(PROCESSADOS / "locais.parquet", index=False)
    print(f"{len(l)} locais de votação; com coordenadas: {l.NR_LATITUDE.notna().mean():.1%}")


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    h = pd.read_parquet(PROCESSADOS / "historico_municipios.parquet")
    aud = json.load(open(PORTAL_DADOS / "auditoria.json"))
    locais()
    p = perfil()
    d = municipios(s, p, h, aud)
    cols = ["aptos", "lula1", "fla1", "lula2", "margem1", "margem2", "dlula", "dcomp", "abst2", "bn2", "elim1", "direita1", "cury1", "lula2022", "d2022",
            "atipicas", "jovens", "idosos", "superior", "baixa_escol", "mulheres"]
    ind = {f"{uf}-{mun}": [None if pd.isna(v) else (int(v) if c in ("aptos", "atipicas") else round(float(v), 2)) for c, v in zip(cols, r)]
           for (uf, mun), r in d[cols].iterrows()}
    (PORTAL_DADOS / "mapa").mkdir(parents=True, exist_ok=True)
    with open(PORTAL_DADOS / "mapa" / "indicadores.json", "w") as f:
        json.dump({"colunas": cols, "municipios": ind}, f, separators=(",", ":"))
    ins = {"abstencao_perfil": abstencao_por_perfil(p), "por_perfil": por_perfil(d), "comparacao_2022": comparacao_2022(d, h),
           "curva_apuracao": curva_apuracao(s), "turnos_perfil": sorted(int(t) for t in p.NR_TURNO.unique())}
    with open(PORTAL_DADOS / "insights.json", "w") as f:
        json.dump(ins, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: v for k, v in ins["por_perfil"].items() if k == "_regressao"}, indent=1))
    for k, v in ins["por_perfil"].items():
        if k != "_regressao":
            print(k, v["faixas"], "dlula", v["dlula"], "dcomp", v["dcomp"])
    c22 = ins["comparacao_2022"]
    print("2022:", round(c22["brasil_2022"], 2), "ganhou", c22["municipios_lula_ganhou"], "perdeu", c22["municipios_lula_perdeu"], "mediana", round(c22["mediana_d2022"], 2))
    print("abstenção 1º turno por idade:", ins["abstencao_perfil"]["1"]["idade"]["abstencao_pct"])


if __name__ == "__main__":
    main()
