"""Teste de transferência dos eleitores eliminados, com o 1º e o 2º turno do próprio recorte
(estado, município, zona e seção), para identificar anomalias em todo o país.

Para cada recorte:
  E  = votos dos candidatos eliminados no 1º turno;
  K  = mínimo desses votos que precisa ter ido para Lula, no saldo:
       K = ganho de Lula − brancos/nulos liberados − abstenção liberada (se negativo, 0),
       supondo que nenhum eleitor de Flávio migrou para Lula (é o cenário mais favorável a "poucos movimentos").
  μ  = probabilidade de um eleitor dos eliminados votar em Lula no 2º turno sob a referência:
       f × q, com f = fração dos eleitores dos eliminados que escolhe um finalista (matriz do estado em 2026)
       e q = parcela de Lula entre os que escolhem um finalista:
         "2022":   comportamento de 2022 por campo (direita, centro, esquerda), ponderado pelos eliminados do recorte;
         "estado": comportamento do próprio estado em 2026 (matriz estimada por 03_migracao.py).
Probabilidade de Lula receber K ou mais desses votos, P(X ≥ K):
  independente: X ~ Binomial(E, μ)            (cada eleitor decide sozinho, como moedas independentes);
  com dispersão: X ~ Beta-Binomial(E, μ, ρ)    (eleitores do mesmo lugar tendem a decidir parecido; ρ é calibrado
                 por UF e por nível com a variação observada entre os municípios, zonas ou seções do estado).
Valores guardados em log10 (probabilidades muito pequenas não cabem em ponto flutuante).
Comparação com a Mega-Sena: n = log10(P) / log10(1/50.063.860) = número de acertos seguidos com aposta simples.

Saída: portal/dados/auditoria/transferencia.json
"""
import json
import math

import numpy as np
import pandas as pd
from scipy import stats

from comum import PORTAL_DADOS, PROCESSADOS

LOG10_MEGA = math.log10(1 / 50_063_860)
T1C = ["Lula_1", "Flávio_1", "Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1", "Branco_1", "Nulo_1", "Abst_1", "Aptos_1"]
T2C = ["Lula_2", "Flávio_2", "Branco_2", "Nulo_2", "Abst_2", "Aptos_2"]


def minimos(t1, t2):
    """E, K e ganho de Flávio sobre E para matrizes (n,11) e (n,6)."""
    E = t1[:, 2:7].sum(1)
    bn = np.maximum(0, -((t2[:, 2] - t1[:, 7]) + (t2[:, 3] - t1[:, 8])))
    ab = np.maximum(0, -(t2[:, 4] - t1[:, 9]))
    K = np.maximum(0, (t2[:, 0] - t1[:, 0]) - bn - ab)
    return E, K, (t2[:, 1] - t1[:, 1])


def cauda_binom(K, E, mu):
    """log10 P(X ≥ K), X ~ Bin(E, μ), estável para caudas extremas."""
    K, E, mu = np.asarray(K, float), np.asarray(E, float), np.clip(np.asarray(mu, float), 1e-9, 1 - 1e-9)
    out = np.zeros_like(K)
    ok = (E > 0) & (K > 0)
    imp = ok & (K > E)
    out[imp] = -np.inf
    m = ok & ~imp
    ln = stats.binom.logsf(K[m] - 1, E[m], mu[m])
    ruim = ~np.isfinite(ln)
    if ruim.any():  # aproximação geométrica da cauda a partir do termo K (válida quando K está acima da média)
        k, n, p = K[m][ruim], E[m][ruim], mu[m][ruim]
        r = (n - k) / (k + 1) * p / (1 - p)
        ln[ruim] = stats.binom.logpmf(k, n, p) - np.log1p(-np.clip(r, 0, 0.999999))
    out[m] = ln / math.log(10)
    return np.minimum(out, 0)


def cauda_betabinom(K, E, mu, rho):
    """log10 P(X ≥ K), X ~ Beta-Binomial(E, μ, ρ) (ρ = correlação entre eleitores do mesmo recorte)."""
    K, E, mu = np.asarray(K, float), np.asarray(E, float), np.clip(np.asarray(mu, float), 1e-9, 1 - 1e-9)
    rho = np.clip(np.broadcast_to(np.asarray(rho, float), K.shape), 1e-7, 0.95)
    s = 1 / rho - 1
    a, b = mu * s, (1 - mu) * s
    out = np.zeros_like(K)
    ok = (E > 0) & (K > 0)
    imp = ok & (K > E)
    out[imp] = -np.inf
    m = ok & ~imp
    ln = stats.betabinom.logsf(K[m] - 1, E[m], a[m], b[m])
    ruim = ~np.isfinite(ln)
    if ruim.any():
        k, n, aa, bb = K[m][ruim], E[m][ruim], a[m][ruim], b[m][ruim]
        r = (n - k) / (k + 1) * (k + aa) / (n - k - 1 + bb)
        ln[ruim] = stats.betabinom.logpmf(k, n, aa, bb) - np.log1p(-np.clip(r, 0, 0.999999))
    out[m] = ln / math.log(10)
    return np.minimum(out, 0)


def calibrar_rho(K, E, mu):
    """ρ por método dos momentos: variância de K/E em torno de μ além da binomial (unidades com E ≥ 30)."""
    ok = E >= 30
    if ok.sum() < 5:
        return 0.05
    r, e, m = K[ok] / E[ok], E[ok], mu[ok]
    num = np.mean((r - m) ** 2 - m * (1 - m) / e)
    den = np.mean(m * (1 - m) * (e - 1) / e)
    return float(np.clip(num / den, 1e-5, 0.9))


def main():
    R = json.load(open(PORTAL_DADOS / "resumo.json"))
    ID = json.load(open(PORTAL_DADOS / "ideologia.json"))
    g22 = ID["anos"]["2022"]["grupos"]
    q22 = {"dir": g22["direita"]["pt_entre_finalistas"] / 100, "cen": g22["centro"]["pt_entre_finalistas"] / 100, "esq": g22["esquerda"]["pt_entre_finalistas"] / 100}
    sec = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    sec = sec[sec.SG_UF != "ZZ"]
    # f e q do estado (linha dos eliminados da matriz de 2026, ponderada pelos eliminados do estado)
    ref = {}
    for uf, u in R["ufs"].items():
        if uf == "ZZ":
            continue
        P = np.asarray(u["migracao"]["pct"], float) / 100
        w = np.asarray(u["t1"][2:7], float)
        dem = (w @ P[2:7]) / w.sum()
        ref[uf] = {"f": float(dem[0] + dem[1]), "q": float(dem[0] / (dem[0] + dem[1]))}

    def mu_2022(t1, uf):
        dirv = t1[:, 2] + t1[:, 4] + t1[:, 5] + t1[:, 6] / 2
        cen, esq = t1[:, 3], t1[:, 6] / 2
        tot = np.clip(dirv + cen + esq, 1, None)
        q = (dirv * q22["dir"] + cen * q22["cen"] + esq * q22["esq"]) / tot
        return np.array([ref[u]["f"] for u in uf]) * q

    def mu_estado(uf):
        return np.array([ref[u]["f"] * ref[u]["q"] for u in uf])

    saida = {"schema_version": "1.0", "metadados": {
        "evento": "Lula recebe pelo menos K dos votos dos eliminados (K = mínimo exigido pelo saldo do próprio recorte, sem migração entre finalistas)",
        "referencias": {"2022": "comportamento de 2022 por campo ideológico (Brasil)", "estado": "comportamento do próprio estado em 2026 (matriz estimada)"},
        "modelos": {"independente": "Binomial: cada eleitor decide de forma independente", "disperso": "Beta-Binomial com ρ calibrado por UF e nível"},
        "q2022": q22, "referencia_estado": ref, "log10_mega": LOG10_MEGA}, "rho": {}, "niveis": {}}
    niveis = {
        "uf": sec.groupby("SG_UF")[T1C + T2C].sum().reset_index(),
        "municipio": sec.groupby(["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"])[T1C + T2C].sum().reset_index(),
        "zona": sec.groupby(["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA"])[T1C + T2C].sum().reset_index(),
        "secao": sec[["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"] + T1C + T2C].copy(),
    }
    for nivel, d in niveis.items():
        t1, t2 = d[T1C].to_numpy(float), d[T2C].to_numpy(float)
        uf = d.SG_UF.to_numpy()
        E, K, dF = minimos(t1, t2)
        m22, mest = mu_2022(t1, uf), mu_estado(uf)
        # ρ por UF neste nível (no nível UF, um único ρ entre os estados)
        rho = np.zeros(len(d))
        saida["rho"][nivel] = {}
        grupos = [("BR", np.ones(len(d), bool))] if nivel == "uf" else [(u, uf == u) for u in np.unique(uf)]
        for u, msk in grupos:
            r_ = calibrar_rho(K[msk], E[msk], mest[msk])
            rho[msk] = r_
            saida["rho"][nivel][u] = r_
        cols = {"E": E, "K": K, "dF": dF, "mu22": m22, "muUF": mest,
                "ind22": cauda_binom(K, E, m22), "dis22": cauda_betabinom(K, E, m22, rho),
                "indUF": cauda_binom(K, E, mest), "disUF": cauda_betabinom(K, E, mest, rho)}
        df = d.drop(columns=T1C + T2C).copy()
        for k, v in cols.items():
            df[k] = v
        df["apto"] = t2[:, 5]
        # percentil do mínimo exigido (K/E) entre as unidades do mesmo nível e UF
        df["r"] = np.where(E > 0, K / np.clip(E, 1, None), np.nan)
        df["pct"] = df.groupby("SG_UF")["r"].rank(pct=True) if nivel != "uf" else df["r"].rank(pct=True)
        # FDR (BH) sobre o modelo disperso com referência do estado, entre unidades com E ≥ 30
        ok = (E >= 30)
        p = np.power(10.0, np.where(np.isfinite(df["disUF"]), df["disUF"], -300))
        q = np.ones(len(df))
        if ok.sum():
            idx = np.where(ok)[0]
            o = np.argsort(p[idx])
            n = len(idx)
            acc = 1.0
            qq = np.empty(n)
            for rnk, j in enumerate(o[::-1]):
                acc = min(acc, p[idx][j] * n / (n - rnk))
                qq[j] = acc
            q[idx] = qq
        df["q"] = q
        df["classe"] = np.select([~ok, df["K"] > df["E"], q < 0.01, q < 0.10], ["Inconclusivo", "Requer migração entre finalistas", "Muito incomum", "Incomum"], "Compatível")
        print(nivel, len(df), df.classe.value_counts().to_dict(), "ρ mediano:", round(float(np.median(list(saida["rho"][nivel].values()))), 4))
        # exportação: tudo para UF, município e zona; seções só as 2.000 mais extremas e o ρ por UF (o portal calcula as demais)
        if nivel == "secao":
            df = df[ok].sort_values("disUF").head(2000)
        rnd = {"mu22": 5, "muUF": 5, "ind22": 3, "dis22": 3, "indUF": 3, "disUF": 3, "r": 4, "pct": 4, "q": 6}
        lin = []
        for rr in df.itertuples(index=False):
            dd = rr._asdict()
            lin.append([None if (isinstance(v, float) and not math.isfinite(v)) else (round(v, rnd[k]) if k in rnd and isinstance(v, float) else (int(v) if isinstance(v, (np.integer,)) or (isinstance(v, float) and k in ("E", "K", "dF", "apto")) else v))
                        for k, v in dd.items()])
        saida["niveis"][nivel] = {"colunas": list(df.columns), "linhas": lin}
    sj = niveis["municipio"]
    print("Silva Jardim:", [l for l in saida["niveis"]["municipio"]["linhas"] if l[1] == 59110])
    with open(PORTAL_DADOS / "auditoria" / "transferencia.json", "w") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
