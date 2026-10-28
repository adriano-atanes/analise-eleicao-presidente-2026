"""Gera portal/dados/auditoria.json, usado pela visão "Auditoria" do portal.

Reúne, para o Brasil e para cada estado: impressão digital comparecimento × voto, resíduos do
modelo de migração, último dígito, variação do comparecimento e indicadores por estado. Também
monta a lista de seções atípicas para conferência (maiores resíduos, ganhos acima das fontes
possíveis e comparecimento muito alto), com motivo e link para o boletim no portal.
"""
import importlib
import json

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS

F = importlib.import_module("08_forense")
B_COMP = np.arange(40, 101, 2)      # comparecimento, %
B_SHARE = np.arange(0, 101, 2)      # % do candidato nos válidos
B_RES = np.arange(-30, 31, 1)       # resíduo, p.p. do eleitorado
B_DCOMP = np.arange(-30, 31, 2)     # variação do comparecimento, p.p.


def hist2d(comp, share, peso):
    h, _, _ = np.histogram2d(np.clip(comp, 40, 99.99), np.clip(share, 0, 99.99), bins=[B_COMP, B_SHARE], weights=peso)
    return np.round(h).astype(int).tolist()


def hist1d(v, bordas):
    return np.histogram(np.clip(v, bordas[0], bordas[-1] - 1e-9), bins=bordas)[0].astype(int).tolist()


def indicadores(g):
    """Painel por recorte (Brasil ou estado)."""
    ok = g[(g.Aptos_1 > 0) & (g.Val_1 > 0) & (g.Val_2 > 0)]
    t1, t2 = 100 * ok.Comp_1 / ok.Aptos_1, 100 * ok.Comp_2 / ok.Aptos_2
    novos = (g.Comp_2 - g.Comp_1).clip(lower=0)
    fontes = g.Elim_1 + g.BN_1 + novos
    exl = (g.Lula_2 - g.Lula_1) - fontes
    exf = (g["Flávio_2"] - g["Flávio_1"]) - fontes
    dig = {}
    for col in ["Lula_1", "Flávio_1", "Lula_2", "Flávio_2"]:
        v = g[col][g[col] >= 10].astype(int)
        dig[col] = np.bincount(v % 10, minlength=10).tolist()
    out = {
        "secoes": int(len(g)),
        "fp": {f"{c}_{t}": hist2d(t1 if t == 1 else t2, 100 * ok[f"{c}_{t}"] / ok[f"Val_{t}"], ok[f"{c}_{t}"])
               for c in ("Lula", "Flávio") for t in (1, 2)},
        "res": {"Lula": hist1d(g.res_lula.dropna(), B_RES), "Flávio": hist1d(g.res_fla.dropna(), B_RES)},
        "dcomp": hist1d(t2 - t1, B_DCOMP),
        "digitos": dig,
        "k": {
            "res_desvio_lula": float(g.res_lula.std()), "res_desvio_fla": float(g.res_fla.std()),
            "res_lula_acima10": int((g.res_lula > 10).sum()), "res_lula_abaixo10": int((g.res_lula < -10).sum()),
            "res_fla_acima10": int((g.res_fla > 10).sum()), "res_fla_abaixo10": int((g.res_fla < -10).sum()),
            "limite_lula": int((exl > 0).sum()), "limite_lula_votos": int(exl[exl > 0].sum()), "limite_lula_10": int((exl >= 10).sum()),
            "limite_fla": int((exf > 0).sum()), "limite_fla_votos": int(exf[exf > 0].sum()), "limite_fla_10": int((exf >= 10).sum()),
            "comp100_1": int((t1 >= 100).sum()), "comp100_2": int((t2 >= 100).sum()),
            "comp95_1": int((t1 >= 95).sum()), "comp95_2": int((t2 >= 95).sum()),
            "dcomp_medio": float((t2 - t1).mean()),
        },
    }
    return out


def suspeitas(s):
    """Seções atípicas, com o motivo. Atípico não quer dizer irregular: é onde conferir primeiro."""
    novos = (s.Comp_2 - s.Comp_1).clip(lower=0)
    fontes = s.Elim_1 + s.BN_1 + novos
    s = s.assign(exl=(s.Lula_2 - s.Lula_1) - fontes, exf=(s["Flávio_2"] - s["Flávio_1"]) - fontes,
                 c1=100 * s.Comp_1 / s.Aptos_1.clip(lower=1), c2=100 * s.Comp_2 / s.Aptos_2.clip(lower=1))
    motivos = {}

    def marcar(idx, motivo):
        for i in idx:
            motivos.setdefault(i, []).append(motivo)

    marcar(s.index[s.res_lula > 10], "res_lula")
    marcar(s.index[s.res_fla > 10], "res_fla")
    marcar(s.index[s.exl >= 10], "lim_lula")
    marcar(s.index[s.exf >= 10], "lim_fla")
    marcar(s.index[(s.c2 >= 98) & (s.Aptos_2 >= 50)], "comp_alto")
    marcar(s.index[(s.c2 - s.c1 >= 25) & (s.Aptos_2 >= 50)], "salto_comp")
    sel = s.loc[list(motivos)]
    linhas = []
    for i, r in sel.iterrows():
        linhas.append([r.SG_UF, int(r.CD_MUNICIPIO), r.NM_MUNICIPIO.title(), int(r.NR_ZONA), int(r.NR_SECAO), int(r.Aptos_2),
                       int(r.Lula_1), int(r["Flávio_1"]), int(r.Elim_1), int(r.BN_1), int(r.Comp_1),
                       int(r.Lula_2), int(r["Flávio_2"]), int(r.BN_2), int(r.Comp_2),
                       round(float(r.res_lula), 1) if pd.notna(r.res_lula) else None,
                       round(float(r.res_fla), 1) if pd.notna(r.res_fla) else None,
                       int(r.exl), int(r.exf), motivos[i], r.DS_MODELO_URNA_2, r.DS_ORIGEM_VOTO_2])
    return {"colunas": ["uf", "mun", "nome", "zona", "secao", "aptos", "lula1", "fla1", "elim1", "bn1", "comp1", "lula2", "fla2", "bn2", "comp2",
                        "res_lula", "res_fla", "exc_lula", "exc_fla", "motivos", "urna", "origem"],
            "linhas": linhas}


def main():
    s = F.carregar()
    _, sr = F.residuos(s)
    s = s.join(sr[["res_lula", "res_fla"]])
    fz = json.load(open(PROCESSADOS / "forense.json"))
    h = json.load(open(PROCESSADOS / "historico.json"))
    hist = []
    for ano, d in h.items():
        c1, c2 = d["1"]["candidatos"], {x[2]: x[3] for x in d["2"]["candidatos"]}
        lid, seg = c1[0], c1[1]
        val = sum(x[3] for x in c1)
        g_l, g_s = c2[lid[2]] - lid[3], c2[seg[2]] - seg[3]
        hist.append({"ano": int(ano), "lider": lid[0], "segundo": seg[0], "gap_pp": 100 * (lid[3] - seg[3]) / val, "gap": lid[3] - seg[3],
                     "elim_pct": 100 * (val - lid[3] - seg[3]) / val, "g_lider": g_l, "g_seg": g_s,
                     "parcela": 100 * g_s / (g_l + g_s), "necessaria": 100 * (g_l + g_s + lid[3] - seg[3]) / 2 / (g_l + g_s),
                     "dcomp": d["2"]["comparecimento"] - d["1"]["comparecimento"]})
    c = fz["contabilidade"]
    val26 = c["lula_1"] + c["flavio_1"] + c["fontes_liquidas"]["votos dos eliminados"]
    hist.append({"ano": 2026, "lider": "Flávio Bolsonaro", "segundo": "Lula", "gap_pp": 100 * c["vantagem_flavio_1"] / val26, "gap": c["vantagem_flavio_1"],
                 "elim_pct": 100 * c["fontes_liquidas"]["votos dos eliminados"] / val26, "g_lider": c["ganho_flavio"], "g_seg": c["ganho_lula"],
                 "parcela": c["parcela_lula_do_ganho"], "necessaria": c["parcela_minima_para_virar"],
                 "dcomp": c["fontes_liquidas"]["aumento do comparecimento"]})
    saida = {
        "bordas": {"comp": B_COMP.tolist(), "share": B_SHARE.tolist(), "res": B_RES.tolist(), "dcomp": B_DCOMP.tolist()},
        "historico": hist, "contabilidade": c, "integridade": fz["integridade"], "digitos": fz["digitos"], "urnas": fz["urnas"],
        "eliminados": fz["eliminados"], "comparecimento": fz["comparecimento"],
        "brasil": indicadores(s), "ufs": {uf: indicadores(g) for uf, g in s.groupby("SG_UF")},
        "suspeitas": suspeitas(s),
    }
    caminho = PORTAL_DADOS / "auditoria.json"
    with open(caminho, "w") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{caminho}: {caminho.stat().st_size / 1e6:.1f} MB, {len(saida['suspeitas']['linhas'])} seções atípicas")
    m = pd.Series([x for l in saida["suspeitas"]["linhas"] for x in l[19]]).value_counts()
    print(m.to_dict())


if __name__ == "__main__":
    main()
