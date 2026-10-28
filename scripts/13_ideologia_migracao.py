"""Para onde foram, no 2º turno, os eleitores dos candidatos eliminados de cada campo ideológico.

De 2002 a 2026 o candidato do PT esteve em todos os 2º turnos, o que permite comparar as
eleições entre si: para cada ano, estima-se que fração dos eleitores dos eliminados de esquerda,
de centro e de direita votou no candidato do PT, no outro finalista, branco/nulo ou se absteve.

Classificação ideológica: por partido, nos três grandes campos usados na ciência política
brasileira (esquerda inclui centro-esquerda; direita inclui centro-direita). É uma escolha
do analista e está explícita em CAMPO abaixo; candidatos sem classificação vão para "centro"
só se listados, senão ficam em "outros" e entram no grupo de direita ou esquerda conforme o
partido. A tabela completa vai para o JSON de saída.

Método: o mesmo de 03_migracao.py (mínimos quadrados com linhas no simplex, estados puxados
para a matriz nacional), com zonas eleitorais como unidade em todos os anos, para que as
eleições sejam comparáveis. Para 2026 também se reporta a versão com seções.
Saída: dados/processados/ideologia.json e portal/dados/ideologia.json.
"""
import importlib
import json

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS

M = importlib.import_module("03_migracao")

# número do candidato → (nome, partido, campo). Finalistas marcados com campo "finalista".
CAMPO = {
    2002: {13: ("Lula", "PT", "PT"), 45: ("José Serra", "PSDB", "outro"), 40: ("Garotinho", "PSB", "esquerda"),
           23: ("Ciro Gomes", "PPS", "esquerda"), 16: ("Zé Maria", "PSTU", "esquerda"), 29: ("Rui Costa Pimenta", "PCO", "esquerda")},
    2006: {13: ("Lula", "PT", "PT"), 45: ("Geraldo Alckmin", "PSDB", "outro"), 50: ("Heloísa Helena", "PSOL", "esquerda"),
           12: ("Cristovam Buarque", "PDT", "esquerda"), 44: ("Ana Maria Rangel", "PRP", "direita"), 27: ("José Maria Eymael", "PSDC", "direita"),
           17: ("Luciano Bivar", "PSL", "direita")},
    2010: {13: ("Dilma", "PT", "PT"), 45: ("José Serra", "PSDB", "outro"), 43: ("Marina Silva", "PV", "centro"),
           50: ("Plínio de Arruda Sampaio", "PSOL", "esquerda"), 27: ("José Maria Eymael", "PSDC", "direita"), 28: ("Levy Fidelix", "PRTB", "direita"),
           16: ("Zé Maria", "PSTU", "esquerda"), 21: ("Ivan Pinheiro", "PCB", "esquerda"), 29: ("Rui Costa Pimenta", "PCO", "esquerda")},
    2014: {13: ("Dilma", "PT", "PT"), 45: ("Aécio Neves", "PSDB", "outro"), 40: ("Marina Silva", "PSB", "centro"),
           50: ("Luciana Genro", "PSOL", "esquerda"), 20: ("Pastor Everaldo", "PSC", "direita"), 43: ("Eduardo Jorge", "PV", "esquerda"),
           28: ("Levy Fidelix", "PRTB", "direita"), 16: ("Zé Maria", "PSTU", "esquerda"), 27: ("José Maria Eymael", "PSDC", "direita"),
           21: ("Mauro Iasi", "PCB", "esquerda"), 29: ("Rui Costa Pimenta", "PCO", "esquerda")},
    2018: {13: ("Fernando Haddad", "PT", "PT"), 17: ("Jair Bolsonaro", "PSL", "outro"), 12: ("Ciro Gomes", "PDT", "esquerda"),
           45: ("Geraldo Alckmin", "PSDB", "direita"), 30: ("João Amoêdo", "NOVO", "direita"), 51: ("Cabo Daciolo", "PATRIOTA", "direita"),
           15: ("Henrique Meirelles", "MDB", "centro"), 18: ("Marina Silva", "REDE", "centro"), 19: ("Alvaro Dias", "PODE", "direita"),
           50: ("Guilherme Boulos", "PSOL", "esquerda"), 54: ("João Goulart Filho", "PPL", "esquerda"), 27: ("José Maria Eymael", "DC", "direita"),
           16: ("Vera Lúcia", "PSTU", "esquerda")},
    2022: {13: ("Lula", "PT", "PT"), 22: ("Jair Bolsonaro", "PL", "outro"), 15: ("Simone Tebet", "MDB", "centro"),
           12: ("Ciro Gomes", "PDT", "esquerda"), 44: ("Soraya Thronicke", "UNIÃO", "direita"), 30: ("Felipe d'Ávila", "NOVO", "direita"),
           14: ("Padre Kelmon", "PTB", "direita"), 80: ("Léo Péricles", "UP", "esquerda"), 16: ("Vera Lúcia", "PSTU", "esquerda"),
           21: ("Sofia Manzano", "PCB", "esquerda"), 27: ("Constituinte Eymael", "DC", "direita")},
    2026: {13: ("Lula", "PT", "PT"), 22: ("Flávio Bolsonaro", "PL", "outro"), 70: ("Augusto Cury", "AVANTE", "centro"),
           14: ("Renan Santos", "MISSÃO", "direita"), 55: ("Ronaldo Caiado", "PSD", "direita"), 30: ("Zema", "NOVO", "direita"),
           80: ("Samara", "UP", "esquerda"), 16: ("Hertz Dias", "PSTU", "esquerda"), 21: ("Edmilson Costa", "PCB", "esquerda"),
           29: ("Rui Costa Pimenta", "PCO", "esquerda"), 27: ("Clariana Barao", "DC", "direita"), 35: ("Wilson Grassi", "DEMOCRATA", "direita")},
}
ORIG = ["PT", "outro", "esquerda", "centro", "direita", "BN", "Abst"]
DEST = ["PT", "outro", "BN", "Abst"]
LAMBDA = 30.0


def unidades_historicas():
    zc = pd.read_parquet(PROCESSADOS / "historico_zonas_candidatos.parquet")
    zd = pd.read_parquet(PROCESSADOS / "historico_zonas_detalhe.parquet")
    chave = ["ano", "SG_UF", "CD_MUNICIPIO", "NR_ZONA"]
    camp = {(a, n): v[2] for a, d in CAMPO.items() for n, v in d.items()}
    zc["campo"] = [camp.get((a, n), "fora") for a, n in zip(zc.ano, zc.NR_CANDIDATO)]
    fora = zc[(zc.campo == "fora") & (zc.NR_TURNO == 1)].groupby(["ano", "NR_CANDIDATO"]).QT_VOTOS_NOMINAIS.sum()
    if len(fora):
        print("candidatos sem classificação (ficam fora da análise):", fora.to_dict())
    v = zc.pivot_table(index=chave + ["NR_TURNO"], columns="campo", values="QT_VOTOS_NOMINAIS", aggfunc="sum", fill_value=0)
    d = zd.set_index(chave + ["NR_TURNO"])
    u = v.join(d, how="inner").reset_index()
    for g in ("PT", "outro", "esquerda", "centro", "direita"):
        if g not in u:
            u[g] = 0
    u["BN"] = u.brancos + u.nulos
    u["Abst"] = u.aptos - u.comparecimento
    return u


def unidades_2026(nivel):
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    chave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA"] + (["NR_SECAO"] if nivel == "secao" else [])
    linhas = []
    for t in (1, 2):
        g = s.groupby(chave).agg(PT=(f"Lula_{t}", "sum"), outro=(f"Flávio_{t}", "sum"), aptos=(f"Aptos_{t}", "sum"), comparecimento=(f"Comp_{t}", "sum"),
                                 brancos=(f"Branco_{t}", "sum"), nulos=(f"Nulo_{t}", "sum"))
        if t == 1:
            g["centro"] = s.groupby(chave).Cury_1.sum()
            # "Outros" de 2026 junta seis candidatos pequenos: separa esquerda e direita pela proporção nacional
            outros = s.groupby(chave).Outros_1.sum()
            g["direita"] = s.groupby(chave)[["Renan_1", "Caiado_1", "Zema_1"]].sum().sum(axis=1) + outros * FRAC_DIREITA_OUTROS
            g["esquerda"] = outros * (1 - FRAC_DIREITA_OUTROS)
        else:
            g["centro"] = g["direita"] = g["esquerda"] = 0
        g["NR_TURNO"] = t
        linhas.append(g.reset_index())
    u = pd.concat(linhas)
    u["BN"] = u.brancos + u.nulos
    u["Abst"] = u.aptos - u.comparecimento
    u.insert(0, "ano", 2026)
    return u


# 2026: entre os "Outros", DC (40.043) e Democrata (16.881) são de direita; UP, PSTU, PCB e PCO (203.731), de esquerda
FRAC_DIREITA_OUTROS = (40043 + 16881) / (40043 + 16881 + 122911 + 43103 + 22693 + 15024)


def estimar(u):
    """Matriz de migração por estado (unidades = zonas ou seções), somada em votos para o Brasil."""
    w = u.pivot_table(index=[c for c in u.columns if c in ("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")], columns="NR_TURNO",
                      values=[c for c in ORIG if c != "Abst"] + ["Abst", "aptos"], aggfunc="sum").fillna(0)
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w[(w.aptos_1 > 0) & (w.aptos_2 > 0)].reset_index()
    X = w[[f"{o}_1" for o in ORIG]].to_numpy(float) / w.aptos_1.to_numpy(float)[:, None]
    Y = w[[f"{d}_2" for d in DEST]].to_numpy(float) / w.aptos_2.to_numpy(float)[:, None]
    peso = w.aptos_1.to_numpy(float)
    peso = peso / peso.mean()
    XtX, XtY, _ = M.suficientes(X, Y, peso)
    B_br = M.resolver(XtX, XtY)
    total = np.zeros((len(ORIG), len(DEST)))
    for uf, idx in w.groupby("SG_UF").indices.items():
        xtx, xty, n = M.suficientes(X[idx], Y[idx], peso[idx] / peso[idx].mean())
        B = M.resolver(xtx, xty, B_br, LAMBDA, n)
        total += B * w.iloc[idx][[f"{o}_1" for o in ORIG]].sum().to_numpy(float)[:, None]
    votos1 = w[[f"{o}_1" for o in ORIG]].sum().to_numpy(float)
    pct = 100 * total / np.maximum(total.sum(1, keepdims=True), 1)
    return {"votos_1t": dict(zip(ORIG, votos1.round().astype(int).tolist())), "fluxo": np.round(total).astype(int).tolist(),
            "pct": np.round(pct, 2).tolist(), "unidades": int(len(w))}


def main():
    hist = unidades_historicas()
    saida = {"origens": ORIG, "destinos": DEST, "classificacao": {str(a): {str(n): v for n, v in d.items()} for a, d in CAMPO.items()},
             "anos": {}, "metodo": __doc__.strip()}
    for ano in sorted(CAMPO):
        u = unidades_2026("zona") if ano == 2026 else hist[hist.ano == ano]
        r = estimar(u)
        pct = np.array(r["pct"])
        info = {}
        for g in ("esquerda", "centro", "direita"):
            k = ORIG.index(g)
            pt, out = pct[k][0], pct[k][1]
            if r["votos_1t"][g] < 100_000:  # grupo sem candidato relevante naquele ano
                info[g] = {"votos": r["votos_1t"][g], "pct_pt": None, "pct_outro": None, "pct_bn": None, "pct_abst": None, "pt_entre_finalistas": None}
                continue
            info[g] = {"votos": r["votos_1t"][g], "pct_pt": pt, "pct_outro": out, "pct_bn": pct[k][2], "pct_abst": pct[k][3],
                       "pt_entre_finalistas": 100 * pt / (pt + out) if pt + out > 0 else None}
        fl = np.array(r["fluxo"])
        ganho_pt = fl[:, 0].sum() - fl[0, 0]
        info["composicao_ganho_pt"] = {o: float(100 * fl[k, 0] / ganho_pt) for k, o in enumerate(ORIG) if o != "PT"}
        saida["anos"][str(ano)] = {**r, "grupos": info,
                                   "pt": CAMPO[ano][next(n for n, v in CAMPO[ano].items() if v[2] == "PT")][0],
                                   "outro": CAMPO[ano][next(n for n, v in CAMPO[ano].items() if v[2] == "outro")][0]}
        print(ano, {g: (round(info[g]["votos"] / 1e6, 2), info[g]["pct_pt"] and round(info[g]["pct_pt"], 1), info[g]["pct_outro"] and round(info[g]["pct_outro"], 1),
                        None if info[g]["pt_entre_finalistas"] is None else round(info[g]["pt_entre_finalistas"], 1))
                    for g in ("esquerda", "centro", "direita")}, flush=True)
    r = estimar(unidades_2026("secao"))
    pct = np.array(r["pct"])
    saida["secoes_2026"] = {**r, "grupos": {g: {"pct_pt": pct[ORIG.index(g)][0], "pct_outro": pct[ORIG.index(g)][1],
                                                "pct_bn": pct[ORIG.index(g)][2], "pct_abst": pct[ORIG.index(g)][3]} for g in ("esquerda", "centro", "direita")}}
    print("2026 por seção:", {g: (round(v["pct_pt"], 1), round(v["pct_outro"], 1)) for g, v in saida["secoes_2026"]["grupos"].items()})
    # cenários: eleitores de direita de 2026 com o comportamento de anos anteriores
    a26 = saida["anos"]["2026"]
    fl = np.array(a26["fluxo"], float)
    k = ORIG.index("direita")
    n_dir = fl[k].sum()
    margem = float(fl[:, 0].sum() - fl[:, 1].sum())
    cen = []
    for ano_ref, rot in [("2018", "como em 2018"), ("2022", "como em 2022")]:
        p_ref = np.array(saida["anos"][ano_ref]["pct"])[k] / 100
        novo = n_dir * p_ref
        cen.append({"cenario": rot, "pct_pt": float(100 * p_ref[0]), "pct_outro": float(100 * p_ref[1]),
                    "margem_pt": margem - (fl[k, 0] - fl[k, 1]) + (novo[0] - novo[1])})
    cen.append({"cenario": "todos para Flávio", "pct_pt": 0.0, "pct_outro": 100.0, "margem_pt": margem - (fl[k, 0] - fl[k, 1]) - n_dir})
    nulos_max = margem - (fl[k, 0] - fl[k, 1]) - (fl[k, 0] + fl[k, 1])  # quem foi para um finalista indo todo para Flávio
    cen.append({"cenario": "quem escolheu um finalista, todos para Flávio", "pct_pt": 0.0, "pct_outro": float(100 * (fl[k, 0] + fl[k, 1]) / n_dir),
                "margem_pt": float(nulos_max)})
    saida["cenarios_direita"] = {"margem_real_estimada": margem, "eleitores_direita": float(n_dir), "lista": cen}
    print("cenários direita:", [(c["cenario"], round(c["margem_pt"])) for c in cen], "margem estimada", round(margem))
    for destino in (PROCESSADOS / "ideologia.json", PORTAL_DADOS / "ideologia.json"):
        with open(destino, "w") as f:
            json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
