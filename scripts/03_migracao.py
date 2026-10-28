"""Estima a migração de votos do 1º para o 2º turno (inferência ecológica).

O voto é secreto: não se sabe como cada eleitor votou nos dois turnos. A migração é
estimada a partir das ~500 mil seções eleitorais. Para cada seção i,

    proporção no 2º turno (destino j) = Σ_k proporção no 1º turno (origem k) · B[k, j]

onde B é a matriz de transição: B[k, j] = fração dos eleitores da origem k (ex.: quem
votou em Renan) que foi para o destino j (ex.: Lula). Restrições: B ≥ 0 e cada linha
soma 1. B é estimada por mínimos quadrados ponderados pelo eleitorado da seção.

Hierarquia: Brasil → estado → município. Cada nível é puxado para o nível acima por
uma penalidade (encolhimento), proporcional a LAMBDA seções "fictícias". Assim,
municípios com poucas seções ficam próximos da matriz do estado e os grandes são
estimados pelos próprios dados. Os totais de região e Brasil somam os fluxos estimados
de cada estado. Intervalos de 90% por bootstrap das seções dentro de cada estado.

Saída: dados/processados/migracao.json
"""
import json

import numpy as np
import pandas as pd

from comum import DESTINOS, ORIGENS, PROCESSADOS, UF_REGIAO

LAMBDA_UF = 30.0
LAMBDA_MUN = 30.0
N_BOOT = 100
rng = np.random.default_rng(2026)


def projetar_simplex(B):
    """Projeta cada linha de B no simplex {b ≥ 0, Σ b = 1}."""
    u = -np.sort(-B, axis=1)
    css = np.cumsum(u, axis=1) - 1
    idx = np.arange(1, B.shape[1] + 1)
    rho = (u - css / idx > 0).sum(axis=1)
    theta = css[np.arange(B.shape[0]), rho - 1] / rho
    return np.maximum(B - theta[:, None], 0)


def resolver(XtX, XtY, prior=None, lam=0.0, n=1.0, iters=4000):
    """Mínimos quadrados com linhas de B no simplex (FISTA).

    Com prior, soma a penalidade (lam/n)·‖X(B − prior)‖²: equivale a lam seções
    fictícias, com a mesma composição média das n seções reais, votando como o prior.
    """
    A, C = XtX.copy(), XtY.copy()
    if prior is not None and lam > 0:
        A += (lam / n) * XtX
        C += (lam / n) * XtX @ prior
    L = 2 * np.linalg.eigvalsh(A).max()
    B = projetar_simplex(np.full(C.shape, 1 / C.shape[1])) if prior is None else prior.copy()
    Z, t = B.copy(), 1.0
    for _ in range(iters):
        Bn = projetar_simplex(Z - (2 * (A @ Z) - 2 * C) / L)
        tn = (1 + np.sqrt(1 + 4 * t * t)) / 2
        Z = Bn + (t - 1) / tn * (Bn - B)
        if np.abs(Bn - B).max() < 1e-9:
            B = Bn
            break
        B, t = Bn, tn
    return B


def matrizes(df):
    """Proporções por seção e pesos (eleitorado, normalizado para média 1)."""
    df = df[(df.Aptos_1 > 0) & (df.Aptos_2 > 0)]
    X = df[[f"{o}_1" for o in ORIGENS]].to_numpy(float) / df.Aptos_1.to_numpy(float)[:, None]
    Y = df[[f"{d}_2" for d in DESTINOS]].to_numpy(float) / df.Aptos_2.to_numpy(float)[:, None]
    w = df.Aptos_1.to_numpy(float)
    return X, Y, w / w.mean(), df


def suficientes(X, Y, w):
    Xw = X * w[:, None]
    return Xw.T @ X, Xw.T @ Y, w.sum()


def r2(X, Y, w, B):
    res = ((Y - X @ B) ** 2 * w[:, None]).sum(0)
    tot = ((Y - np.average(Y, axis=0, weights=w)) ** 2 * w[:, None]).sum(0)
    return dict(zip(DESTINOS, np.round(1 - res / tot, 3).tolist()))


def fluxo(B, df):
    """Converte a matriz de proporções em votos: origem k × destino j."""
    return B * df[[f"{o}_1" for o in ORIGENS]].sum().to_numpy(float)[:, None]


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")

    X, Y, w, _ = matrizes(s)
    XtX, XtY, _ = suficientes(X, Y, w)
    B_br = resolver(XtX, XtY)
    print("Brasil (modelo único), R²:", r2(X, Y, w, B_br))

    ufs, fluxos_uf, boot = {}, {}, {}
    for uf, g in s.groupby("SG_UF"):
        X, Y, w, g = matrizes(g)
        XtX, XtY, n = suficientes(X, Y, w)
        B = resolver(XtX, XtY, B_br, LAMBDA_UF, n)
        ufs[uf] = {"B": B, "r2": r2(X, Y, w, B), "secoes": len(g)}
        fluxos_uf[uf] = fluxo(B, g)
        # bootstrap: reamostra seções do estado (pesos multinomiais)
        votos1 = g[[f"{o}_1" for o in ORIGENS]].to_numpy(float)
        boot[uf] = []
        for _ in range(N_BOOT):
            c = rng.multinomial(len(g), np.full(len(g), 1 / len(g))).astype(float)
            XtXb, XtYb, nb = suficientes(X, Y, w * c)
            Bb = resolver(XtXb, XtYb, B_br, LAMBDA_UF, nb, iters=1500)
            boot[uf].append(Bb * (votos1 * c[:, None]).sum(0)[:, None] / c.mean())
        print(f"{uf}: {len(g):>6} seções  R² Lula={ufs[uf]['r2']['Lula']:.3f} Flávio={ufs[uf]['r2']['Flávio']:.3f}")

    def resumo(F, amostras):
        """Fluxo em votos + % por origem, com intervalo de 90% do bootstrap."""
        pct = F / F.sum(1, keepdims=True)
        P = np.array([a / a.sum(1, keepdims=True) for a in amostras])
        return {
            "votos": np.round(F).astype(int).tolist(),
            "pct": np.round(100 * pct, 2).tolist(),
            "ic90": [np.round(100 * np.percentile(P, 5, axis=0), 2).tolist(),
                     np.round(100 * np.percentile(P, 95, axis=0), 2).tolist()],
        }

    saida = {"origens": ORIGENS, "destinos": DESTINOS, "metodo": __doc__.strip(),
             "brasil": {}, "regioes": {}, "ufs": {}, "municipios": {}}
    todas = np.array([sum(boot[uf][b] for uf in boot) for b in range(N_BOOT)])
    saida["brasil"] = resumo(sum(fluxos_uf.values()), todas)
    for reg in sorted(set(UF_REGIAO.values())):
        membros = [uf for uf in fluxos_uf if UF_REGIAO[uf] == reg]
        saida["regioes"][reg] = resumo(sum(fluxos_uf[u] for u in membros),
                                       [sum(boot[u][b] for u in membros) for b in range(N_BOOT)])
    for uf in ufs:
        saida["ufs"][uf] = {**resumo(fluxos_uf[uf], boot[uf]), "r2": ufs[uf]["r2"], "secoes": ufs[uf]["secoes"]}

    # municípios: encolhidos para a matriz do estado (sem bootstrap, para caber no tempo)
    for (uf, mun), g in s.groupby(["SG_UF", "CD_MUNICIPIO"]):
        X, Y, w, g = matrizes(g)
        if len(g) == 0:
            continue
        XtX, XtY, n = suficientes(X, Y, w)
        B = resolver(XtX, XtY, ufs[uf]["B"], LAMBDA_MUN, n, iters=2000)
        F = fluxo(B, g)
        saida["municipios"][f"{uf}-{mun}"] = {
            "votos": np.round(F).astype(int).tolist(),
            "pct": np.round(100 * F / np.maximum(F.sum(1, keepdims=True), 1), 1).tolist(),
            "secoes": len(g),
            "peso_dados": round(len(g) / (len(g) + LAMBDA_MUN), 2),
        }

    with open(PROCESSADOS / "migracao.json", "w") as f:
        json.dump(saida, f, ensure_ascii=False)

    P = pd.DataFrame(saida["brasil"]["pct"], index=ORIGENS, columns=DESTINOS)
    lo = pd.DataFrame(saida["brasil"]["ic90"][0], index=ORIGENS, columns=DESTINOS)
    hi = pd.DataFrame(saida["brasil"]["ic90"][1], index=ORIGENS, columns=DESTINOS)
    print("\nBrasil — % de cada origem (1º turno) que foi para cada destino (2º turno):")
    print(P.round(1).to_string())
    print("\nIC 90%:")
    print((lo.round(1).astype(str) + "–" + hi.round(1).astype(str)).to_string())
    F = pd.DataFrame(saida["brasil"]["votos"], index=ORIGENS, columns=DESTINOS)
    print("\nDestinos estimados vs. oficiais:")
    print(pd.DataFrame({"estimado": F.sum(), "oficial": [s[f"{d}_2"].sum() for d in DESTINOS]}))


if __name__ == "__main__":
    main()
