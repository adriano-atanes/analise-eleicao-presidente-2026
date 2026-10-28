"""Testes estatísticos (forense eleitoral) sobre as seções do 1º e do 2º turno de 2026.

Os testes procuram padrões que costumam aparecer quando há votos adicionados ou alterados
em parte das seções. Nenhum deles prova fraude ou ausência de fraude; servem para dizer se
os números têm o comportamento esperado de uma eleição limpa ou se há algo a investigar.

1. Integridade aritmética de cada boletim de seção
2. Contabilidade da virada: de onde vieram, em termos líquidos, os votos novos dos finalistas
3. Resíduos do modelo de migração: votos que o 1º turno da própria seção não explica
4. Limites por seção: seções em que o ganho de um finalista supera todas as fontes possíveis
   além do eleitor do adversário
5. Comparecimento × voto (impressão digital de Klimek et al., 2012)
6. Último dígito e segundo dígito (Benford) das contagens por seção
7. Modelo de urna: a variação do voto muda com o modelo, dentro do mesmo município?
8. A variação entre turnos acompanha o voto dos eliminados?

Saídas: dados/processados/forense.json e figuras em relatorio/figuras/.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from comum import ARQUIVOS, BRUTOS, CHAVE_SECAO, DESTINOS, ORIGENS, PROCESSADOS, RAIZ, ler_csv_tse

FIG = RAIZ / "relatorio" / "figuras"
ELIM = ["Renan", "Cury", "Caiado", "Zema", "Outros"]
LULA, FLA, INK, MUTED, ACCENT = "#e34948", "#2a78d6", "#111512", "#7d847e", "#1d7a4c"
plt.rcParams.update({"font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e3e6e1", "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.edgecolor": "#c3c8c1"})
for f in (RAIZ / "relatorio" / "fontes").glob("Plex-*.ttf"):
    matplotlib.font_manager.fontManager.addfont(str(f))
plt.rcParams["font.family"] = "IBM Plex Sans"


def salvar(fig, nome):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{nome}.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def carregar():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    meta = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1],
                       usecols=CHAVE_SECAO + ["NR_TURNO", "DS_MODELO_URNA", "DS_ORIGEM_VOTO"])
    meta = meta.pivot_table(index=CHAVE_SECAO, columns="NR_TURNO", values=["DS_MODELO_URNA", "DS_ORIGEM_VOTO"], aggfunc="first")
    meta.columns = [f"{a}_{b}" for a, b in meta.columns]
    s = s.merge(meta.reset_index(), on=CHAVE_SECAO, how="left")
    s["Elim_1"] = s[[f"{o}_1" for o in ELIM]].sum(axis=1)
    s["BN_1"], s["BN_2"] = s.Branco_1 + s.Nulo_1, s.Branco_2 + s.Nulo_2
    s["Val_1"] = s[[f"{o}_1" for o in ["Lula", "Flávio"] + ELIM]].sum(axis=1)
    s["Val_2"] = s["Lula_2"] + s["Flávio_2"]
    s["mun"] = s.SG_UF + "-" + s.CD_MUNICIPIO.astype(str)
    return s


def integridade(s):
    ok = s[(s.Aptos_1 > 0)]
    return {
        "secoes": int(len(s)),
        "secoes_nao_instaladas": int((s.Aptos_1 > 0).sum() - (s.Comp_1 > 0).sum()),
        "aptos_diferentes_entre_turnos": int((s.Aptos_1 != s.Aptos_2).sum()),
        "comparecimento_maior_que_aptos": int(((s.Comp_1 > s.Aptos_1) | (s.Comp_2 > s.Aptos_2)).sum()),
        "soma_votos_diferente_do_comparecimento_t1": int((s.Val_1 + s.BN_1 != s.Comp_1).sum()),
        "soma_votos_diferente_do_comparecimento_t2": int((s.Val_2 + s.BN_2 != s.Comp_2).sum()),
        "aptos_mais_abstencao_inconsistente": int(((ok.Comp_1 + ok.Abst_1 != ok.Aptos_1) | (ok.Comp_2 + ok.Abst_2 != ok.Aptos_2)).sum()),
        "origem_do_voto_t2": s.DS_ORIGEM_VOTO_2.value_counts().to_dict(),
    }


def contabilidade(s):
    tot = s.sum(numeric_only=True)
    ganho_l, ganho_f = tot.Lula_2 - tot.Lula_1, tot.Flávio_2 - tot.Flávio_1
    fontes = {"votos dos eliminados": tot.Elim_1, "queda de brancos e nulos": tot.BN_1 - tot.BN_2,
              "aumento do comparecimento": tot.Comp_2 - tot.Comp_1}
    pool = ganho_l + ganho_f
    vantagem = tot.Flávio_1 - tot.Lula_1
    return {
        "lula_1": int(tot.Lula_1), "flavio_1": int(tot.Flávio_1), "lula_2": int(tot.Lula_2), "flavio_2": int(tot.Flávio_2),
        "ganho_lula": int(ganho_l), "ganho_flavio": int(ganho_f), "ganho_total": int(pool),
        "fontes_liquidas": {k: int(v) for k, v in fontes.items()}, "soma_fontes": int(sum(fontes.values())),
        "vantagem_flavio_1": int(vantagem),
        "parcela_lula_do_ganho": float(100 * ganho_l / pool),
        "parcela_minima_para_virar": float(100 * (pool + vantagem) / 2 / pool),
    }


def residuos(s):
    """Diferença entre o 2º turno real e o previsto pela matriz de migração do estado."""
    mig = json.load(open(PROCESSADOS / "migracao.json"))
    s = s[(s.Aptos_1 > 0) & (s.Aptos_2 > 0) & (s.Comp_2 > 0)].copy()
    X = s[[f"{o}_1" for o in ORIGENS]].to_numpy(float) / s.Aptos_1.to_numpy(float)[:, None]
    pred = np.zeros((len(s), len(DESTINOS)))
    for uf, idx in s.groupby("SG_UF").indices.items():
        B = np.array(mig["ufs"][uf]["pct"]) / 100
        pred[idx] = X[idx] @ B
    real = s[[f"{d}_2" for d in DESTINOS]].to_numpy(float) / s.Aptos_2.to_numpy(float)[:, None]
    r = 100 * (real - pred)  # pontos percentuais do eleitorado da seção
    s["res_lula"], s["res_fla"] = r[:, 0], r[:, 1]
    s["res_lula_votos"] = r[:, 0] / 100 * s.Aptos_2
    s["res_fla_votos"] = r[:, 1] / 100 * s.Aptos_2
    out = {}
    for nome, col in [("Lula", "res_lula"), ("Flávio", "res_fla")]:
        v = s[col]
        out[nome] = {
            "media_pp": float(v.mean()), "desvio_pp": float(v.std()), "assimetria": float(stats.skew(v)),
            "acima_10pp": int((v > 10).sum()), "abaixo_10pp": int((v < -10).sum()),
            "acima_20pp": int((v > 20).sum()), "abaixo_20pp": int((v < -20).sum()),
            "votos_excedentes_acima_10pp": int(s.loc[v > 10, col + "_votos"].sum()),
            "votos_faltantes_abaixo_10pp": int(-s.loc[v < -10, col + "_votos"].sum()),
        }
    # gráfico: distribuição dos resíduos
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    bins = np.arange(-30, 30.5, 1)
    ax.hist(np.clip(s.res_lula, -30, 30), bins=bins, histtype="step", color=LULA, linewidth=1.6, label="Lula")
    ax.hist(np.clip(s.res_fla, -30, 30), bins=bins, histtype="step", color=FLA, linewidth=1.6, label="Flávio")
    ax.set_yscale("log")
    ax.set_xlabel("2º turno real menos o previsto pelo 1º turno da seção (pontos percentuais do eleitorado)")
    ax.set_ylabel("seções (escala log)")
    ax.legend(frameon=False)
    salvar(fig, "residuos")
    return out, s


def limites(s):
    """Seções em que o ganho de um finalista não cabe nas fontes que não são o eleitor do adversário."""
    novos = (s.Comp_2 - s.Comp_1).clip(lower=0)
    fontes = s.Elim_1 + s.BN_1 + novos
    out = {}
    for nome, a, b in [("Lula", "Lula", "Flávio"), ("Flávio", "Flávio", "Lula")]:
        excesso = (s[f"{a}_2"] - s[f"{a}_1"]) - fontes
        m = excesso > 0
        out[nome] = {"secoes": int(m.sum()), "pct_secoes": float(100 * m.mean()), "votos_excedentes": int(excesso[m].sum()),
                     "perdas_do_adversario_nessas_secoes": int((s.loc[m, f"{b}_1"] - s.loc[m, f"{b}_2"]).clip(lower=0).sum()),
                     "excesso_mediano": float(excesso[m].median()) if m.any() else 0.0}
    return out


def comparecimento(s):
    s = s[(s.Aptos_1 > 0) & (s.Val_1 > 0) & (s.Val_2 > 0)]
    t1, t2 = 100 * s.Comp_1 / s.Aptos_1, 100 * s.Comp_2 / s.Aptos_2
    out = {"secoes_comparecimento_100pct": {"1": int((t1 >= 100).sum()), "2": int((t2 >= 100).sum())},
           "secoes_comparecimento_95pct": {"1": int((t1 >= 95).sum()), "2": int((t2 >= 95).sum())}}
    # efeito marginal do comparecimento extra, dentro do município
    d = pd.DataFrame({"mun": s.mun, "dcomp": s.Comp_2 - s.Comp_1, "dl": s.Lula_2 - s.Lula_1, "df": s["Flávio_2"] - s["Flávio_1"],
                      "dbn": s.BN_2 - s.BN_1})
    dm = d[["dcomp", "dl", "df", "dbn"]] - d.groupby("mun")[["dcomp", "dl", "df", "dbn"]].transform("mean")
    for k in ("dl", "df", "dbn"):
        out[f"inclinacao_{k}"] = float((dm.dcomp * dm[k]).sum() / (dm.dcomp ** 2).sum())
    out["corr_dcomp_dlula_share"] = float(np.corrcoef(t2 - t1, 100 * s.Lula_2 / s.Val_2 - 100 * s.Lula_1 / s.Val_1)[0, 1])
    # impressão digital: comparecimento × % do candidato, ponderado pelos votos
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 6.2), sharex=True, sharey=True)
    for i, (t, comp) in enumerate([(1, t1), (2, t2)]):
        for j, (nome, cor) in enumerate([("Lula", "Reds"), ("Flávio", "Blues")]):
            share = 100 * s[f"{nome}_{t}"] / s[f"Val_{t}"]
            ax = axs[j, i]
            ax.hist2d(comp, share, bins=[np.arange(40, 101, 1), np.arange(0, 101, 1)], weights=s[f"{nome}_{t}"], cmap=cor, cmin=1)
            ax.set_title(f"{nome} · {t}º turno", fontsize=9)
            ax.grid(False)
            if j == 1:
                ax.set_xlabel("comparecimento da seção (%)")
            if i == 0:
                ax.set_ylabel(f"% de {nome} nos válidos")
    fig.tight_layout()
    salvar(fig, "impressao_digital")
    fig, ax = plt.subplots(figsize=(7.2, 2.4))
    b = np.arange(40, 101, 1)
    ax.hist(t1, bins=b, histtype="step", color=MUTED, linewidth=1.5, label="1º turno")
    ax.hist(t2, bins=b, histtype="step", color=INK, linewidth=1.5, label="2º turno")
    ax.set_xlabel("comparecimento da seção (% dos aptos)")
    ax.set_ylabel("seções")
    ax.legend(frameon=False, loc="upper left")
    salvar(fig, "comparecimento_secoes")
    return out


BENFORD2 = np.array([sum(np.log10(1 + 1 / (10 * k + d)) for k in range(1, 10)) for d in range(10)])


def digitos(s):
    out = {}
    for col in ["Lula_1", "Flávio_1", "Lula_2", "Flávio_2"]:
        v = s[col][s[col] >= 10].astype(int)
        ult = np.bincount(v % 10, minlength=10)
        chi_u, p_u = stats.chisquare(ult)
        seg = np.bincount(v.astype(str).str[1].astype(int), minlength=10)
        chi_s, p_s = stats.chisquare(seg, BENFORD2 * seg.sum())
        out[col] = {"n": int(len(v)), "ultimo_digito_pct": np.round(100 * ult / ult.sum(), 3).tolist(),
                    "ultimo_chi2": float(chi_u), "ultimo_p": float(p_u), "ultimo_desvio_max_pp": float(np.abs(100 * ult / ult.sum() - 10).max()),
                    "segundo_media": float((seg * np.arange(10)).sum() / seg.sum()), "segundo_media_benford": float((BENFORD2 * np.arange(10)).sum()),
                    "segundo_chi2": float(chi_s), "segundo_p": float(p_s)}
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.4), sharey=True)
    for ax, t in zip(axs, (1, 2)):
        x = np.arange(10)
        ax.bar(x - 0.2, out[f"Lula_{t}"]["ultimo_digito_pct"], width=0.38, color=LULA, label="Lula")
        ax.bar(x + 0.2, out[f"Flávio_{t}"]["ultimo_digito_pct"], width=0.38, color=FLA, label="Flávio")
        ax.axhline(10, color=INK, linewidth=0.8)
        ax.set_ylim(9.5, 10.5)
        ax.set_xticks(x)
        ax.set_title(f"{t}º turno · último dígito dos votos por seção", fontsize=9)
        ax.grid(axis="x", visible=False)
    axs[0].set_ylabel("% das seções")
    axs[1].legend(frameon=False, loc="upper right", bbox_to_anchor=(1, 1.32), ncol=2)
    salvar(fig, "ultimo_digito")
    return out


def urnas(s):
    s = s[(s.Val_1 > 0) & (s.Val_2 > 0) & s.DS_MODELO_URNA_2.str.startswith("UE")].copy()
    s["l1"] = 100 * s.Lula_1 / s.Val_1
    s["dl"] = 100 * s.Lula_2 / s.Val_2 - s.l1
    out = {"secoes_por_modelo": s.DS_MODELO_URNA_2.value_counts().to_dict(), "sem_controle": {}, "dentro_do_municipio": {}, "nivel_1_turno": {}}
    modelos = sorted(s.DS_MODELO_URNA_2.unique())
    ref = "UE 2020"
    D = pd.get_dummies(s.DS_MODELO_URNA_2).astype(float)[[m for m in modelos if m != ref]]
    for k, y in [("dentro_do_municipio", "dl"), ("nivel_1_turno", "l1")]:
        yd = s[y] - s.groupby("mun")[y].transform("mean")
        Xd = D - D.groupby(s.mun).transform("mean")
        beta, *_ = np.linalg.lstsq(Xd.to_numpy(), yd.to_numpy(), rcond=None)
        res = yd.to_numpy() - Xd.to_numpy() @ beta
        # erro-padrão agrupado por município
        g = s.mun.to_numpy()
        XtX_inv = np.linalg.inv(Xd.T.to_numpy() @ Xd.to_numpy())
        meat = sum(np.outer(Xd.to_numpy()[i].T @ res[i], Xd.to_numpy()[i].T @ res[i])
                   for i in pd.Series(range(len(g))).groupby(g).apply(list).values)
        se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv))
        out[k] = {m: {"efeito_pp": float(b), "erro_padrao": float(e)} for m, b, e in zip(D.columns, beta, se)}
    out["sem_controle"] = s.groupby("DS_MODELO_URNA_2").dl.mean().round(3).to_dict()
    return out


def eliminados(s):
    """Variação de Lula entre turnos por município × composição do 1º turno."""
    m = s.groupby("mun")[["Lula_1", "Lula_2", "Flávio_1", "Flávio_2", "Val_1", "Val_2", "Elim_1", "Cury_1", "Renan_1", "Caiado_1", "Zema_1",
                         "BN_1", "BN_2", "Comp_1", "Comp_2", "Aptos_1"]].sum()
    m = m[m.Val_1 > 200]
    y = 100 * (m.Lula_2 / m.Val_2 - m.Lula_1 / m.Val_1)
    cols = {"Cury": m.Cury_1, "Renan": m.Renan_1, "Caiado": m.Caiado_1, "Zema": m.Zema_1}
    X = pd.DataFrame({k: 100 * v / m.Val_1 for k, v in cols.items()})
    X["BrancoNulo"] = 100 * m.BN_1 / m.Comp_1
    X["DeltaComp"] = 100 * (m.Comp_2 - m.Comp_1) / m.Aptos_1
    X["Lula1"] = 100 * m.Lula_1 / m.Val_1
    w = np.sqrt(m.Val_1.to_numpy(float))
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    beta, *_ = np.linalg.lstsq(A * w[:, None], y.to_numpy() * w, rcond=None)
    pred = A @ beta
    r2 = 1 - np.average((y - pred) ** 2, weights=m.Val_1) / np.average((y - np.average(y, weights=m.Val_1)) ** 2, weights=m.Val_1)
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.scatter(X.Cury, y, s=np.clip(m.Val_1 / 3000, 2, 60), color=LULA, alpha=0.35, linewidths=0)
    ax.set_xlabel("% de Augusto Cury nos válidos do 1º turno (município)")
    ax.set_ylabel("variação de Lula (p.p. dos válidos)")
    salvar(fig, "cury_x_lula")
    return {"municipios": int(len(m)), "r2": float(r2), "coeficientes": dict(zip(["constante"] + list(X.columns), map(float, beta))),
            "variacao_lula_pp_mediana": float(y.median()), "municipios_lula_caiu": int((y < 0).sum())}


def main():
    s = carregar()
    out = {"integridade": integridade(s), "contabilidade": contabilidade(s)}
    out["residuos"], s_res = residuos(s)
    out["limites"] = limites(s)
    out["comparecimento"] = comparecimento(s)
    out["digitos"] = digitos(s)
    out["urnas"] = urnas(s)
    out["eliminados"] = eliminados(s)
    # seções com maiores resíduos a favor de cada um (para auditoria)
    out["maiores_residuos"] = {
        nome: s_res.nlargest(15, col)[["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "Aptos_2", "Lula_1", "Flávio_1", "Elim_1",
                                       "BN_1", "Comp_1", "Lula_2", "Flávio_2", "BN_2", "Comp_2", col]].to_dict("records")
        for nome, col in [("Lula", "res_lula"), ("Flávio", "res_fla")]}
    with open(PROCESSADOS / "forense.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps({k: v for k, v in out.items() if k != "maiores_residuos"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
