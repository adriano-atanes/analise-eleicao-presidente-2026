"""Comportamento do eleitorado entre os turnos: 2026 comparado com 2002–2022.

Para cada eleição, mede no Brasil, nos estados e nos municípios como o voto mudou do 1º para o
2º turno e verifica se 2026 ficou dentro da faixa observada nas eleições anteriores:

  1. Viradas: estados e municípios onde o finalista que liderou o 1º turno perdeu o 2º
  2. Captação: parcela do crescimento dos finalistas que ficou com o 2º colocado nacional
  3. Comparecimento, brancos e nulos: variação entre os turnos
  4. Variação municipal do 2º colocado: média, dispersão e extremos
  5. Previsibilidade: quanto do 2º turno de cada município o 1º turno explica (R²)
  6. Cenários: o resultado de 2026 com a captação e o comparecimento de eleições anteriores

"lider" e "segundo" são os dois primeiros colocados nacionais no 1º turno de cada ano
(em 2026: Flávio e Lula). Saída: dados/processados/comportamento.json e portal/dados/comportamento.json.
"""
import json

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS, UF_NOME

ELIM = ["Renan", "Cury", "Caiado", "Zema", "Outros"]


def municipios_2026():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    linhas = []
    for t in (1, 2):
        g = s.groupby(["SG_UF", "CD_MUNICIPIO"]).agg(
            lider=(f"Flávio_{t}", "sum"), segundo=(f"Lula_{t}", "sum"), brancos=(f"Branco_{t}", "sum"), nulos=(f"Nulo_{t}", "sum"),
            aptos=(f"Aptos_{t}", "sum"), comparecimento=(f"Comp_{t}", "sum"))
        g["outros"] = s.groupby(["SG_UF", "CD_MUNICIPIO"])[[f"{o}_{t}" for o in ELIM]].sum().sum(axis=1) if t == 1 else 0
        g["NR_TURNO"] = t
        linhas.append(g.reset_index())
    m = pd.concat(linhas)
    m.insert(0, "ano", 2026)
    return m


def largo(m):
    """Uma linha por (ano, UF, município) com o 1º e o 2º turno lado a lado."""
    m = m.copy()
    m["validos"] = m.lider + m.segundo + m.outros
    w = m.pivot_table(index=["ano", "SG_UF", "CD_MUNICIPIO"], columns="NR_TURNO",
                      values=["lider", "segundo", "outros", "validos", "brancos", "nulos", "aptos", "comparecimento"], aggfunc="sum")
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    return w.dropna().reset_index()


def indicadores(w):
    """Indicadores de um recorte (soma das linhas)."""
    t = w.sum(numeric_only=True)
    g_l, g_s = t.lider_2 - t.lider_1, t.segundo_2 - t.segundo_1
    pool = g_l + g_s
    gap = t.lider_1 - t.segundo_1
    return {
        "gap_pp": 100 * gap / t.validos_1,
        "elim_pct": 100 * t.outros_1 / t.validos_1,
        "captacao_segundo": 100 * g_s / pool if pool > 0 else None,
        "necessaria": 100 * (pool + gap) / 2 / pool if pool > 0 else None,
        "dcomp_pp": 100 * (t.comparecimento_2 / t.aptos_2 - t.comparecimento_1 / t.aptos_1),
        "dcomp_votos": float(t.comparecimento_2 - t.comparecimento_1),
        "dbn_pp": 100 * ((t.brancos_2 + t.nulos_2) / t.comparecimento_2 - (t.brancos_1 + t.nulos_1) / t.comparecimento_1),
        "segundo_1": 100 * t.segundo_1 / (t.lider_1 + t.segundo_1),
        "segundo_2": 100 * t.segundo_2 / (t.lider_2 + t.segundo_2),
        "virou": bool((t.segundo_2 > t.lider_2) != (t.segundo_1 > t.lider_1)),
    }


def municipais(w):
    w = w[(w.validos_1 > 0) & (w.lider_2 + w.segundo_2 > 0) & (w.aptos_1 > 0) & (w.aptos_2 > 0)]
    w = w[w.SG_UF != "ZZ"]
    fin1 = w.lider_1 + w.segundo_1
    fin2 = w.lider_2 + w.segundo_2
    s1 = 100 * w.segundo_1 / fin1          # % do 2º colocado entre os finalistas, 1º turno
    s2 = 100 * w.segundo_2 / fin2
    ds = s2 - s1
    dcomp = 100 * (w.comparecimento_2 / w.aptos_2 - w.comparecimento_1 / w.aptos_1)
    virada = ((w.segundo_1 > w.lider_1) != (w.segundo_2 > w.lider_2)) & (w.lider_1 != w.segundo_1)
    # previsibilidade: % do 2º colocado no 2º turno explicado pela composição do 1º turno
    X = np.column_stack([np.ones(len(w)), 100 * w.segundo_1 / w.comparecimento_1, 100 * w.lider_1 / w.comparecimento_1,
                         100 * w.outros_1 / w.comparecimento_1, 100 * (w.brancos_1 + w.nulos_1) / w.comparecimento_1,
                         100 * w.comparecimento_1 / w.aptos_1])
    peso = np.sqrt(w.validos_1.to_numpy(float))
    beta, *_ = np.linalg.lstsq(X * peso[:, None], s2.to_numpy() * peso, rcond=None)
    res = s2 - X @ beta
    r2 = 1 - np.average(res ** 2, weights=w.validos_1) / np.average((s2 - np.average(s2, weights=w.validos_1)) ** 2, weights=w.validos_1)
    q = lambda v, p: float(np.percentile(v, p))
    return {
        "municipios": int(len(w)), "viradas": int(virada.sum()), "viradas_pct": float(100 * virada.mean()),
        "eleitores_em_viradas_pct": float(100 * w.aptos_2[virada].sum() / w.aptos_2.sum()),
        "dseg_media": float(np.average(ds, weights=w.validos_1)), "dseg_dp": float(ds.std()),
        "dseg_p1": q(ds, 1), "dseg_p99": q(ds, 99), "dseg_negativa_pct": float(100 * (ds < 0).mean()),
        "dcomp_media": float(dcomp.mean()), "dcomp_dp": float(dcomp.std()), "dcomp_p1": q(dcomp, 1), "dcomp_p99": q(dcomp, 99),
        "dcomp_acima5_pct": float(100 * (dcomp > 5).mean()),
        "r2_previsao": float(r2), "residuo_dp": float(np.sqrt(np.average(res ** 2, weights=w.validos_1))),
        "hist_dseg": np.histogram(np.clip(ds, -20, 39.99), bins=np.arange(-20, 41, 1))[0].tolist(),
        "hist_dcomp": np.histogram(np.clip(dcomp, -20, 19.99), bins=np.arange(-20, 21, 1))[0].tolist(),
    }


def faixa(valores_hist, v):
    lo, hi = min(valores_hist), max(valores_hist)
    return {"min": lo, "max": hi, "valor": v, "dentro": bool(lo <= v <= hi), "acima": bool(v > hi), "abaixo": bool(v < lo)}


def main():
    h = pd.read_parquet(PROCESSADOS / "historico_municipios.parquet")
    hj = json.load(open(PROCESSADOS / "historico.json"))
    m = pd.concat([h, municipios_2026()], ignore_index=True)
    w = largo(m)
    anos = sorted(w.ano.unique())
    nomes = {int(a): (d["1"]["candidatos"][0][0], d["1"]["candidatos"][1][0]) for a, d in hj.items()}
    nomes[2026] = ("Flávio Bolsonaro", "Lula")

    nacional, estados, mun = {}, {}, {}
    for a in anos:
        wa = w[w.ano == a]
        nacional[int(a)] = {**indicadores(wa), "lider": nomes[int(a)][0], "segundo": nomes[int(a)][1]}
        est = {}
        for uf, g in wa.groupby("SG_UF"):
            est[uf] = indicadores(g)
        estados[int(a)] = est
        nacional[int(a)]["estados_virada"] = [uf for uf, e in est.items() if e["virou"] and uf != "ZZ"]
        mun[int(a)] = municipais(wa)
        print(a, nomes[int(a)], f"captação {nacional[int(a)]['captacao_segundo']:.1f}%", f"Δcomp {nacional[int(a)]['dcomp_pp']:+.2f}",
              f"estados virada {len(nacional[int(a)]['estados_virada'])}", f"mun. viradas {mun[int(a)]['viradas_pct']:.1f}%",
              f"R² {mun[int(a)]['r2_previsao']:.3f}", flush=True)

    passados = [a for a in nacional if a < 2026]
    n26, m26 = nacional[2026], mun[2026]
    comp = {
        "captacao_segundo": faixa([nacional[a]["captacao_segundo"] for a in passados if nacional[a]["captacao_segundo"] > 0], n26["captacao_segundo"]),
        "gap_pp": faixa([nacional[a]["gap_pp"] for a in passados], n26["gap_pp"]),
        "dcomp_pp": faixa([nacional[a]["dcomp_pp"] for a in passados], n26["dcomp_pp"]),
        "dbn_pp": faixa([nacional[a]["dbn_pp"] for a in passados], n26["dbn_pp"]),
        "estados_virada": faixa([len(nacional[a]["estados_virada"]) for a in passados], len(n26["estados_virada"])),
        "mun_viradas_pct": faixa([mun[a]["viradas_pct"] for a in passados], m26["viradas_pct"]),
        "dseg_dp": faixa([mun[a]["dseg_dp"] for a in passados], m26["dseg_dp"]),
        "dcomp_dp": faixa([mun[a]["dcomp_dp"] for a in passados], m26["dcomp_dp"]),
        "r2_previsao": faixa([mun[a]["r2_previsao"] for a in passados], m26["r2_previsao"]),
        "residuo_dp": faixa([mun[a]["residuo_dp"] for a in passados], m26["residuo_dp"]),
    }

    # estados: 2026 comparado com a faixa do próprio estado em 2002–2022
    por_estado = {}
    for uf in estados[2026]:
        hist_uf = [estados[a][uf] for a in passados if uf in estados[a]]
        if not hist_uf:
            continue
        e = estados[2026][uf]
        por_estado[uf] = {"nome": UF_NOME.get(uf, uf),
                          "dcomp_pp": faixa([x["dcomp_pp"] for x in hist_uf], e["dcomp_pp"]),
                          "dbn_pp": faixa([x["dbn_pp"] for x in hist_uf], e["dbn_pp"]),
                          "captacao_segundo": faixa([x["captacao_segundo"] for x in hist_uf if x["captacao_segundo"] is not None and x["captacao_segundo"] > 0],
                                                    e["captacao_segundo"]) if e["captacao_segundo"] is not None else None,
                          "viradas_hist": sum(x["virou"] for x in hist_uf), "virou_2026": e["virou"]}

    # cenários: 2026 com o comportamento de cada eleição anterior
    t26 = w[w.ano == 2026].sum(numeric_only=True)
    pool = (t26.lider_2 - t26.lider_1) + (t26.segundo_2 - t26.segundo_1)
    cen_cap = []
    for a in passados:
        cap = nacional[a]["captacao_segundo"]
        if cap <= 0:
            cen_cap.append({"ano": a, "captacao": cap, "margem_segundo": None})
            continue
        seg = t26.segundo_1 + pool * cap / 100
        lid = t26.lider_1 + pool * (1 - cap / 100)
        cen_cap.append({"ano": a, "captacao": cap, "margem_segundo": float(seg - lid)})
    cons = json.load(open(PROCESSADOS / "consistencia.json"))["comparecimento"]
    a_l, a_f = cons["inclinacao_dl"], cons["inclinacao_df"]   # votos extras para Lula e Flávio por eleitor adicional
    margem_real = float(t26.segundo_2 - t26.lider_2)
    cen_comp = []
    for a in passados:
        extra_real = n26["dcomp_votos"]
        extra_hist = nacional[a]["dcomp_pp"] / 100 * t26.aptos_2
        delta = extra_hist - extra_real
        cen_comp.append({"ano": a, "dcomp_pp": nacional[a]["dcomp_pp"], "margem_segundo": float(margem_real + delta * (a_l - a_f))})

    # tendências lineares das eleições anteriores, projetadas para 2026
    def tendencia(chave, anos_fit):
        x = np.array(anos_fit, float)
        y = np.array([nacional[a][chave] for a in anos_fit])
        coef = np.polyfit(x, y, 1)
        res = y - np.polyval(coef, x)
        return {"anos": anos_fit, "inclinacao_por_eleicao": float(coef[0] * 4), "previsto_2026": float(np.polyval(coef, 2026)),
                "erro": float(np.sqrt((res ** 2).sum() / (len(y) - 2)))}
    tend = {"captacao_segundo": tendencia("captacao_segundo", [2002, 2010, 2014, 2018, 2022]),
            "dcomp_pp": tendencia("dcomp_pp", [2002, 2006, 2010, 2014, 2018, 2022]),
            "dcomp_pp_recente": tendencia("dcomp_pp", [2010, 2014, 2018, 2022])}

    f1 = lambda v: f"{v:.1f}".replace(".", ",")
    def item(id_, nome, unid, serie, v26, status, texto, leitura):
        return {"id": id_, "nome": nome, "unidade": unid, "serie": {int(k): v for k, v in serie.items()}, "valor_2026": v26,
                "min": min(serie.values()), "max": max(serie.values()), "status": status, "status_texto": texto, "leitura": leitura}
    tc, td, tdr = tend["captacao_segundo"], tend["dcomp_pp"], tend["dcomp_pp_recente"]
    cap_hist = {a: nacional[a]["captacao_segundo"] for a in passados if nacional[a]["captacao_segundo"] > 0}
    ind = [
        item("virada", "Virada nacional no 2º turno", "", {a: int(nacional[a]["virou"]) for a in passados}, int(n26["virou"]), "inedito", "Primeira da série",
             "Nenhuma das seis eleições anteriores teve virada. Nelas, a vantagem do líder no 1º turno ia de "
             f"{f1(comp['gap_pp']['min'])} a {f1(comp['gap_pp']['max'])} pontos; em 2026 foi de {f1(n26['gap_pp'])}."),
        item("gap_pp", "Diferença entre os finalistas no 1º turno", "p.p. dos válidos", {a: nacional[a]["gap_pp"] for a in passados}, n26["gap_pp"],
             "inedito", "Menor da série", "A menor diferença de 1º turno desde 2002, menos da metade da menor anterior (2022)."),
        item("captacao_segundo", "Parcela dos votos novos captada pelo 2º colocado", "%", cap_hist, n26["captacao_segundo"], "tendencia",
             "Na tendência", f"Acima do máximo anterior ({f1(max(cap_hist.values()))}% em 2022), mas a parcela sobe a cada eleição desde 2002: a tendência "
             f"previa {f1(tc['previsto_2026'])}% (± {f1(tc['erro'])}). Em 2006 o 2º colocado perdeu votos e fica fora da série."),
        item("dcomp_pp", "Variação do comparecimento entre os turnos", "p.p. dos aptos", {a: nacional[a]["dcomp_pp"] for a in passados}, n26["dcomp_pp"],
             "acima", "Acima do histórico", f"O comparecimento caiu entre os turnos de 2002 a 2018 e subiu {f1(nacional[2022]['dcomp_pp'])} ponto em 2022. "
             f"Em 2026 subiu {f1(n26['dcomp_pp'])}. A tendência de 2010 a 2022 previa {f1(tdr['previsto_2026'])} (± {f1(tdr['erro'])}); a da série inteira, "
             f"{f1(td['previsto_2026'])} (± {f1(td['erro'])}). Indicador mais fora do padrão, generalizado pelos estados."),
        item("dbn_pp", "Variação de brancos e nulos entre os turnos", "p.p. do comparecimento", {a: nacional[a]["dbn_pp"] for a in passados}, n26["dbn_pp"],
             "dentro", "Dentro do histórico", "Brancos e nulos caíram entre os turnos, como em 2002, 2006, 2010 e 2014."),
        item("estados_virada", "Estados com virada entre os finalistas", "estados", {a: len(nacional[a]["estados_virada"]) for a in passados},
             len(n26["estados_virada"]), "dentro", "Dentro do histórico", f"Em 2026, só {', '.join(n26['estados_virada'])}. De 2002 a 2022 foram de 0 a 4 por eleição."),
        item("mun_viradas_pct", "Municípios com virada entre os finalistas", "% dos municípios", {a: mun[a]["viradas_pct"] for a in passados}, m26["viradas_pct"],
             "dentro", "Dentro do histórico", f"{mun[2026]['viradas']} municípios, entre os menores percentuais da série (2,6% em 2018 a 16,4% em 2006)."),
        item("dseg_dp", "Dispersão da variação do 2º colocado entre municípios", "p.p.", {a: mun[a]["dseg_dp"] for a in passados}, m26["dseg_dp"],
             "dentro", "Dentro do histórico", "A variação foi homogênea entre os municípios, como em 2022: não há grupo de municípios com mudança destoante."),
        item("r2_previsao", "Quanto o 1º turno explica o 2º (por município)", "R²", {a: mun[a]["r2_previsao"] for a in passados}, m26["r2_previsao"],
             "dentro", "Dentro do histórico", "O resultado de cada município no 2º turno é tão previsível pelo 1º quanto em 2022, a eleição mais previsível da série."),
        item("residuo_dp", "Erro da previsão do 2º turno pelo 1º", "p.p.", {a: mun[a]["residuo_dp"] for a in passados}, m26["residuo_dp"],
             "dentro", "Dentro do histórico", "Diferença típica entre o 2º turno real e o previsto em cada município, próxima da menor da série."),
    ]

    # eleitores dos eliminados por campo ideológico (13_ideologia_migracao.py), se já calculado
    arq_ideo = PROCESSADOS / "ideologia.json"
    if arq_ideo.exists():
        ideo = json.load(open(arq_ideo))
        G = lambda a, g: ideo["anos"][str(a)]["grupos"][g]["pt_entre_finalistas"]
        dir_hist = {a: G(a, "direita") for a in (2018, 2022)}
        cen_hist = {a: G(a, "centro") for a in (2010, 2014, 2018, 2022)}
        cd = ideo["cenarios_direita"]["lista"]
        ind.insert(4, item("direita_pt", "Eleitores dos eliminados de direita que votaram no PT", "% dos que escolheram um finalista", dir_hist,
                           G(2026, "direita"), "acima", "Acima do histórico",
                           f"Em 2018 e 2022, anos com o PT contra a direita no 2º turno, {f1(dir_hist[2018])}% e {f1(dir_hist[2022])}% foram para o PT; em 2026, "
                           f"{f1(G(2026, 'direita'))}% (estimativa por zona; por seção, {f1(100 * ideo['secoes_2026']['grupos']['direita']['pct_pt'] / (ideo['secoes_2026']['grupos']['direita']['pct_pt'] + ideo['secoes_2026']['grupos']['direita']['pct_outro']))}%). "
                           f"Com o comportamento de 2018 ou 2022, Lula ainda venceria por {f1(cd[0]['margem_pt'] / 1e6)} e {f1(cd[1]['margem_pt'] / 1e6)} milhões."))
        ind.insert(5, item("centro_pt", "Eleitores dos eliminados de centro que votaram no PT", "% dos que escolheram um finalista", cen_hist,
                           G(2026, "centro"), "acima" if G(2026, "centro") > max(cen_hist.values()) else "dentro",
                           "Acima do histórico" if G(2026, "centro") > max(cen_hist.values()) else "Dentro do histórico",
                           f"Centro: Marina (2010, 2014), Meirelles e Marina (2018), Tebet (2022) e Augusto Cury (2026). Por seção, 2026 fica em "
                           f"{f1(100 * ideo['secoes_2026']['grupos']['centro']['pct_pt'] / (ideo['secoes_2026']['grupos']['centro']['pct_pt'] + ideo['secoes_2026']['grupos']['centro']['pct_outro']))}%."))

    saida = {"anos": [int(a) for a in anos], "indicadores": ind, "tendencias": tend, "nacional": nacional, "municipal": mun, "estados": estados, "comparacao": comp,
             "por_estado": por_estado, "cenario_captacao": cen_cap, "cenario_comparecimento": cen_comp,
             "inclinacoes": {"lula": a_l, "flavio": a_f}, "margem_real": margem_real, "pool_2026": float(pool),
             "bordas": {"dseg": list(range(-20, 41, 1)), "dcomp": list(range(-20, 21, 1))}}
    conv = lambda o: o.item() if hasattr(o, "item") else (bool(o) if isinstance(o, np.bool_) else str(o))
    for destino in (PROCESSADOS / "comportamento.json", PORTAL_DADOS / "comportamento.json"):
        with open(destino, "w") as f:
            json.dump(saida, f, ensure_ascii=False, default=conv, separators=(",", ":"))
    print(json.dumps(comp, indent=1, default=conv))
    print("cenários captação:", [(c["ano"], round(c["margem_segundo"] or 0)) for c in cen_cap])
    print("cenários comparecimento:", [(c["ano"], round(c["margem_segundo"])) for c in cen_comp])
    fora = {uf: [k for k in ("dcomp_pp", "dbn_pp", "captacao_segundo") if e.get(k) and not e[k]["dentro"]] for uf, e in por_estado.items()}
    print("estados fora da faixa:", {k: v for k, v in fora.items() if v})


if __name__ == "__main__":
    main()
