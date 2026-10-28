"""Gera os arquivos JSON consumidos pelo portal (portal/dados/).

- resumo.json        Brasil, regiões e estados: resultados dos dois turnos, migração, histogramas
- uf/<UF>.json       municípios do estado: resultados (todos os candidatos) e migração estimada
- secoes/<UF>.json   uma linha por seção eleitoral, com local de votação (carregado sob demanda)
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd

from comum import (ARQUIVOS, BRUTOS, DESTINOS, NOMES_COMPLETOS, ORIGENS, PORTAL_DADOS, PROCESSADOS,
                   REGIOES, UF_NOME, UF_REGIAO, ler_csv_tse)

T1 = ORIGENS[:-1] + ["Abst", "Aptos"]          # Lula … Nulo, Abst, Aptos
T2 = DESTINOS + ["Aptos"]                       # Lula, Flávio, Branco, Nulo, Abst, Aptos


def salvar(caminho, obj):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return caminho.stat().st_size


def candidatos_todos():
    """Votos de todos os 12 candidatos do 1º turno, por município (arquivo oficial munzona)."""
    c = ler_csv_tse(BRUTOS / ARQUIVOS["votacao_candidato_munzona"][1])
    c = c[c.NR_TURNO == 1]
    info = (c.groupby("NR_CANDIDATO").agg(nome=("NM_URNA_CANDIDATO", "first"), partido=("SG_PARTIDO", "first"),
                                           votos=("QT_VOTOS_NOMINAIS_VALIDOS", "sum"))
             .sort_values("votos", ascending=False))
    ordem = info.index.tolist()
    por_mun = c.pivot_table(index=["SG_UF", "CD_MUNICIPIO"], columns="NR_CANDIDATO",
                            values="QT_VOTOS_NOMINAIS_VALIDOS", aggfunc="sum", fill_value=0)[ordem]
    lista = [{"numero": int(n), "nome": r.nome.title(), "partido": r.partido} for n, r in info.iterrows()]
    return lista, ordem, por_mun


def vetores(df):
    return ([int(df[f"{k}_1"].sum()) for k in T1], [int(df[f"{k}_2"].sum()) for k in T2])


def histograma(valores, pesos, bordas):
    h, _ = np.histogram(np.clip(valores, bordas[0], bordas[-1] - 1e-9), bins=bordas, weights=pesos)
    return np.round(h).astype(int).tolist()


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    mig = json.load(open(PROCESSADOS / "migracao.json"))
    sens = json.load(open(PROCESSADOS / "sensibilidade.json"))
    lista_cand, ordem_cand, cand_mun = candidatos_todos()
    # coordenadas dos locais de votação (15_insights.py); sem o arquivo, os locais ficam sem mapa
    arq_coords = PROCESSADOS / "locais.parquet"
    coords = (pd.read_parquet(arq_coords) if arq_coords.exists()
              else pd.DataFrame(columns=["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_LATITUDE", "NR_LONGITUDE", "NM_BAIRRO"]))
    cand_uf = cand_mun.groupby(level=0).sum()

    # variação do comparecimento por seção, em pontos percentuais
    ok = (s.Aptos_1 > 0) & (s.Aptos_2 > 0)
    dcomp = 100 * (s.Comp_2 / s.Aptos_2.where(ok) - s.Comp_1 / s.Aptos_1.where(ok))
    bordas = np.arange(-30, 31, 2)

    resumo = {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonte": "TSE — Portal de Dados Abertos (votacao_secao, detalhe_votacao_secao, votacao_candidato_munzona, 2026)",
        "datas": {"1": "04/10/2026", "2": "25/10/2026"},
        "t1_campos": T1, "t2_campos": T2,
        "nomes": NOMES_COMPLETOS,
        "candidatos": lista_cand,
        "secoes": int(len(s)),
        "migracao": {"origens": ORIGENS, "destinos": DESTINOS, "brasil": mig["brasil"], "regioes": mig["regioes"],
                     "sensibilidade": sens},
        "hist_comparecimento": {"bordas": bordas.tolist(), "brasil": histograma(dcomp[ok], None, bordas)},
        "regioes": {r: ufs for r, ufs in REGIOES.items()},
        "brasil": {}, "ufs": {},
        # índice para a busca de municípios: [UF, código TSE, nome]
        "indice_municipios": [[uf, int(m), n.title()] for (uf, m, n) in
                              s[["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"]].drop_duplicates().itertuples(index=False)],
    }
    resumo["brasil"]["t1"], resumo["brasil"]["t2"] = vetores(s)
    resumo["brasil"]["cand1"] = cand_uf.sum().astype(int).tolist()

    tamanhos = {}
    for uf, g in s.groupby("SG_UF"):
        t1, t2 = vetores(g)
        resumo["ufs"][uf] = {"nome": UF_NOME[uf], "regiao": UF_REGIAO[uf], "t1": t1, "t2": t2,
                             "cand1": cand_uf.loc[uf].astype(int).tolist(), "migracao": mig["ufs"][uf],
                             "municipios": int(g.CD_MUNICIPIO.nunique()), "secoes": int(len(g))}
        resumo["hist_comparecimento"][uf] = histograma(dcomp[g.index][ok[g.index]], None, bordas)

        # municípios
        muns = []
        for (mun, nome), gm in g.groupby(["CD_MUNICIPIO", "NM_MUNICIPIO"]):
            m1, m2 = vetores(gm)
            mm = mig["municipios"].get(f"{uf}-{mun}")
            muns.append({"cod": int(mun), "nome": nome.title(), "t1": m1, "t2": m2,
                         "cand1": cand_mun.loc[(uf, mun)].astype(int).tolist() if (uf, mun) in cand_mun.index else None,
                         "zonas": sorted(int(z) for z in gm.NR_ZONA.unique()), "secoes": int(len(gm)),
                         "mig": mm and {"pct": mm["pct"], "peso_dados": mm["peso_dados"]}})
        tamanhos[f"uf/{uf}"] = salvar(PORTAL_DADOS / "uf" / f"{uf}.json", {"uf": uf, "municipios": muns})

        # seções
        # o número do local de votação é único só dentro da zona
        chave_local = ["CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"]
        locais = g[chave_local + ["NM_LOCAL_VOTACAO"]].drop_duplicates(chave_local)
        locais = locais.merge(coords[coords.SG_UF == uf].drop(columns="SG_UF"), on=chave_local, how="left")
        idx_local = {k: i for i, k in enumerate(zip(locais.CD_MUNICIPIO, locais.NR_ZONA, locais.NR_LOCAL_VOTACAO))}
        cols = ([f"{k}_1" for k in T1] + [f"{k}_2" for k in T2])
        g = g.sort_values(["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"])
        linhas = np.column_stack([
            g.CD_MUNICIPIO.to_numpy(), g.NR_ZONA.to_numpy(), g.NR_SECAO.to_numpy(),
            [idx_local[k] for k in zip(g.CD_MUNICIPIO, g.NR_ZONA, g.NR_LOCAL_VOTACAO)],
            g[cols].to_numpy()]).astype(int).tolist()
        tamanhos[f"secoes/{uf}"] = salvar(PORTAL_DADOS / "secoes" / f"{uf}.json", {
            "colunas": ["mun", "zona", "secao", "local"] + cols,
            # [município, zona, nº do local, nome, latitude, longitude, bairro]
            "locais": [[int(r.CD_MUNICIPIO), int(r.NR_ZONA), int(r.NR_LOCAL_VOTACAO), r.NM_LOCAL_VOTACAO.title(),
                        None if pd.isna(r.NR_LATITUDE) else round(float(r.NR_LATITUDE), 5), None if pd.isna(r.NR_LONGITUDE) else round(float(r.NR_LONGITUDE), 5),
                        "" if pd.isna(r.NM_BAIRRO) else str(r.NM_BAIRRO).title()] for r in locais.itertuples()],
            "linhas": linhas})

    tamanhos["resumo"] = salvar(PORTAL_DADOS / "resumo.json", resumo)
    total = sum(tamanhos.values())
    print(f"{len(tamanhos)} arquivos, {total / 1e6:.1f} MB no total; maiores:")
    for k, v in sorted(tamanhos.items(), key=lambda x: -x[1])[:6]:
        print(f"  {k}: {v / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
