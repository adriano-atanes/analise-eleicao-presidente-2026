"""Motor estatístico da Auditoria: reconciliação, limites de transferência, cenários e Monte Carlo.

Unidade de análise: qualquer conjunto de seções (Brasil, região, UF, município, zona ou seção), sempre com 100% das
seções do recorte. As contagens seguem a ordem do portal:
  1º turno (11): Lula, Flávio, Renan, Cury, Caiado, Zema, Outros, Branco, Nulo, Abstenção, Aptos
  2º turno (6):  Lula, Flávio, Branco, Nulo, Abstenção, Aptos

Origens do modelo de transferência (6): Lula, Flávio, Demais (os 10 eliminados), Branco, Nulo, Abstenção.
Destinos (5): Lula, Flávio, Branco, Nulo, Abstenção. A matriz de referência de cada unidade é a do nível acima
(estimada por 03_migracao.py): Brasil para região e UF, UF para município, município para zona e seção.

Evento avaliado (estatística S): parcela de Lula entre os finalistas no 2º turno, L2 / (L2 + F2).
Probabilidade bicaudal: P(|S_sim − E[S]| ≥ |S_obs − E[S]|) sob o modelo. Também se calcula a probabilidade
do valor exato (P(L2 = observado)), que é sempre pequena e não deve ser confundida com a anterior.

Modelos:
  multinomial      cada eleitor de cada origem segue a matriz de referência, sem dispersão extra;
  dirichlet        Dirichlet-Multinomial: a matriz da unidade varia em torno da referência com concentração α,
                   calibrada para que os desvios padronizados das unidades irmãs tenham variância 1 (principal);
  hierarquico      como o Dirichlet, com incerteza no hiperparâmetro α (α sorteado da distribuição bootstrap
                   da calibração entre unidades irmãs);
  bootstrap        empírico: posição do desvio padronizado da unidade entre os das unidades irmãs.
"""
import math

import numpy as np
from scipy import stats

MEGA = 1 / 50_063_860  # aposta simples de 6 dezenas
ORIGENS = ["Lula", "Flávio", "Demais", "Branco", "Nulo", "Abstenção"]
DESTINOS = ["Lula", "Flávio", "Branco", "Nulo", "Abstenção"]


# ---------------------------------------------------------------- reconciliação e limites
def categorias(t1, t2):
    """Contagens agregadas por categoria nos dois turnos (a partir dos vetores do portal)."""
    t1, t2 = [int(x) for x in t1], [int(x) for x in t2]
    c1 = {"Lula": t1[0], "Flávio": t1[1], "Demais": sum(t1[2:7]), "Branco": t1[7], "Nulo": t1[8], "Abstenção": t1[9]}
    c2 = {"Lula": t2[0], "Flávio": t2[1], "Demais": 0, "Branco": t2[2], "Nulo": t2[3], "Abstenção": t2[4]}
    return c1, c2, t1[10], t2[5]


def reconciliar(t1, t2):
    """Identidades contábeis e variação de cada categoria entre os turnos."""
    c1, c2, ap1, ap2 = categorias(t1, t2)
    comp1, comp2 = ap1 - c1["Abstenção"], ap2 - c2["Abstenção"]
    nom1, nom2 = c1["Lula"] + c1["Flávio"] + c1["Demais"], c2["Lula"] + c2["Flávio"]
    return {
        "turno1": {**c1, "comparecimento": comp1, "aptos": ap1, "nominais": nom1},
        "turno2": {**c2, "comparecimento": comp2, "aptos": ap2, "nominais": nom2},
        "variacao": {k: c2[k] - c1[k] for k in c1} | {"comparecimento": comp2 - comp1, "aptos": ap2 - ap1},
        "identidades": {
            "comparecimento_1_confere": comp1 == nom1 + c1["Branco"] + c1["Nulo"],
            "comparecimento_2_confere": comp2 == nom2 + c2["Branco"] + c2["Nulo"],
            "aptos_1_confere": ap1 == comp1 + c1["Abstenção"],
            "aptos_2_confere": ap2 == comp2 + c2["Abstenção"],
        },
        "ganho_finalistas": (c2["Lula"] - c1["Lula"]) + (c2["Flávio"] - c1["Flávio"]),
        "variacao_demais_categorias": sum(c2[k] - c1[k] for k in ("Demais", "Branco", "Nulo")),
    }


def limites(t1, t2):
    """Limites matemáticos das transferências (problema de transporte com totais de linha e coluna fixos).

    Origens agregadas: Lula (L1), Flávio (F1) e R = demais + brancos + nulos + abstenção + novos aptos.
    Destinos agregados: Lula (L2), Flávio (F2) e T = brancos + nulos + abstenção.
    Sem migração entre finalistas, o resultado é atingível se e só se ganho⁺(L) + ganho⁺(F) ≤ R.
    """
    c1, c2, ap1, ap2 = categorias(t1, t2)
    L1, F1, L2, F2 = c1["Lula"], c1["Flávio"], c2["Lula"], c2["Flávio"]
    novos = max(0, ap2 - ap1)
    R = c1["Demais"] + c1["Branco"] + c1["Nulo"] + c1["Abstenção"] + novos
    gL, gF = L2 - L1, F2 - F1
    gLp, gFp = max(0, gL), max(0, gF)
    cruz_min_FL = max(0, gLp - R) if gF < 0 else 0
    cruz_min_LF = max(0, gFp - R) if gL < 0 else 0
    # saldo líquido: brancos/nulos e abstenção só liberam votos se diminuíram entre os turnos
    E = c1["Demais"]
    bn_liberado = max(0, -((c2["Branco"] - c1["Branco"]) + (c2["Nulo"] - c1["Nulo"])))
    abst_liberada = max(0, -(c2["Abstenção"] - c1["Abstenção"]))
    return {
        "votos_eliminados": int(E), "brancos_nulos_liberados": int(bn_liberado), "abstencao_liberada": int(abst_liberada),
        # parte mínima dos votos dos eliminados que precisa ter ido para Lula, no saldo, sem migração entre finalistas
        "lula_minimo_dos_eliminados": ((gL - bn_liberado - abst_liberada) / E) if E else None,
        "lula_ganho_sobre_eliminados": (gL / E) if E else None, "flavio_ganho_sobre_eliminados": (gF / E) if E else None,
        "disponivel_sem_finalistas": int(R),
        "novos_aptos": int(novos),
        "ganho_lula": int(gL), "ganho_flavio": int(gF),
        "transferencia_minima_para_lula": int(gLp), "transferencia_minima_para_flavio": int(gFp),
        "captacao_necessaria_lula": (gLp / R) if R else None,
        "captacao_necessaria_conjunta": ((gLp + gFp) / R) if R else None,
        "possivel_sem_migracao_entre_finalistas": bool(gLp + gFp <= R),
        "migracao_minima_flavio_para_lula": int(cruz_min_FL),
        "migracao_minima_lula_para_flavio": int(cruz_min_LF),
        "migracao_maxima_flavio_para_lula": int(min(F1, L2)),
        "migracao_maxima_lula_para_flavio": int(min(L1, F2)),
        # limites de Fréchet da célula de retenção (eleitores que ficaram com o mesmo finalista)
        "retencao_minima_lula": int(max(0, L1 + L2 - (ap1 + novos))), "retencao_maxima_lula": int(min(L1, L2)),
        "retencao_minima_flavio": int(max(0, F1 + F2 - (ap1 + novos))), "retencao_maxima_flavio": int(min(F1, F2)),
        "saida_minima_flavio": int(max(0, -gF)), "saida_minima_lula": int(max(0, -gL)),
    }


def frechet(linhas, colunas):
    """Intervalo possível de cada célula de uma tabela com totais de linha e coluna (limites de Fréchet)."""
    tot = sum(linhas)
    return [[[max(0, r + c - tot), min(r, c)] for c in colunas] for r in linhas]


def mil(v):
    return f"{int(v):,}".replace(",", ".")


def cenarios(t1, t2):
    """Cenários extremos e de referência (hipóteses), com viabilidade sob as restrições explícitas."""
    c1, c2, ap1, ap2 = categorias(t1, t2)
    L1, F1, L2, F2 = c1["Lula"], c1["Flávio"], c2["Lula"], c2["Flávio"]
    lim = limites(t1, t2)
    R = lim["disponivel_sem_finalistas"]
    vot = c1["Demais"] + c1["Branco"] + c1["Nulo"]  # votos de 1º turno fora dos finalistas
    out = []
    # A: tudo o que está disponível vai para Lula (finalistas retêm seus eleitores)
    out.append({"id": "A", "nome": "Transferência integral para Lula", "hipotese": "Finalistas retêm todos os eleitores; todos os votos disponíveis vão para Lula.",
                "lula_max": L1 + R, "flavio_resultante": F1, "explica_lula": L2 <= L1 + R, "explica_flavio": F2 == F1,
                "suficiente": bool(max(0, L2 - L1) <= R), "viavel": bool(max(0, L2 - L1) <= R),
                "nota": f"Lula poderia chegar a {mil(L1 + R)} votos; obteve {mil(L2)}."})
    out.append({"id": "B", "nome": "Transferência integral para Flávio", "hipotese": "Finalistas retêm todos os eleitores; todos os votos disponíveis vão para Flávio.",
                "flavio_max": F1 + R, "lula_resultante": L1, "explica_flavio": F2 <= F1 + R, "explica_lula": L2 == L1,
                "suficiente": bool(max(0, F2 - F1) <= R), "viavel": bool(max(0, F2 - F1) <= R),
                "nota": f"Flávio poderia chegar a {mil(F1 + R)} votos; obteve {mil(F2)}."})
    # C: proporcional aos votos dos finalistas no 1º turno
    sh = L1 / (L1 + F1) if L1 + F1 else 0.5
    comp_extra = (ap2 - c2["Abstenção"]) - (ap1 - c1["Abstenção"])
    novos_fin = max(0, vot + comp_extra - (c2["Branco"] + c2["Nulo"]))
    out.append({"id": "C", "nome": "Transferência proporcional", "hipotese": "Os votos que deixam eliminados, brancos e nulos se dividem entre os finalistas na proporção do 1º turno.",
                "lula_esperado": round(L1 + sh * novos_fin), "flavio_esperado": round(F1 + (1 - sh) * novos_fin),
                "desvio_lula": round(L2 - (L1 + sh * novos_fin)), "viavel": True})
    out.append({"id": "D", "nome": "Migração entre finalistas", "hipotese": "Parte dos eleitores troca de finalista entre os turnos.",
                "minimo_flavio_para_lula": lim["migracao_minima_flavio_para_lula"], "minimo_lula_para_flavio": lim["migracao_minima_lula_para_flavio"],
                "maximo_flavio_para_lula": lim["migracao_maxima_flavio_para_lula"], "maximo_lula_para_flavio": lim["migracao_maxima_lula_para_flavio"],
                "necessaria": not lim["possivel_sem_migracao_entre_finalistas"], "viavel": True})
    out.append({"id": "E", "nome": "Participação variável", "hipotese": "Eleitores que faltaram no 1º turno votam no 2º e vice-versa.",
                "variacao_comparecimento": int(comp_extra), "abstencao_1": c1["Abstenção"], "abstencao_2": c2["Abstenção"],
                "entrada_minima": int(max(0, c1["Abstenção"] - c2["Abstenção"])), "saida_minima": int(max(0, c2["Abstenção"] - c1["Abstenção"])),
                "viavel": True})
    return out


# ---------------------------------------------------------------- modelos estatísticos
def matriz_6(pct10, pesos10):
    """Reduz a matriz 10×5 (origens do portal) para 6×5, juntando os eliminados pelo peso de cada um."""
    P = np.asarray(pct10, float) / 100.0
    P = P / np.clip(P.sum(1, keepdims=True), 1e-12, None)
    w = np.asarray(pesos10[2:7], float)
    dem = (w @ P[2:7]) / w.sum() if w.sum() > 0 else P[2:7].mean(0)
    return np.vstack([P[0], P[1], dem, P[7], P[8], P[9]])


def origens_6(t1):
    t1 = np.asarray(t1, float)
    return np.array([t1[0], t1[1], t1[2:7].sum(), t1[7], t1[8], t1[9]])


def momentos(c, P, alpha):
    """Média e variância (delta method) da parcela de Lula entre os finalistas sob o modelo.
    alpha=None → multinomial; caso contrário Dirichlet-Multinomial com concentração alpha em cada origem."""
    pL, pF = P[:, 0], P[:, 1]
    infl = np.ones_like(c) if alpha is None else 1 + np.clip(c - 1, 0, None) / (alpha + 1)
    EL, EF = (c * pL).sum(), (c * pF).sum()
    VL = (c * pL * (1 - pL) * infl).sum()
    VF = (c * pF * (1 - pF) * infl).sum()
    CLF = -(c * pL * pF * infl).sum()
    tot = EL + EF
    if tot <= 0:
        return 0.5, 0.0
    m = EL / tot
    var = (EF ** 2 * VL + EL ** 2 * VF - 2 * EL * EF * CLF) / tot ** 4
    return float(m), float(math.sqrt(max(var, 1e-18)))


def calibrar_alpha(unidades, lo=1.0, hi=1e7):
    """α tal que a média de z² das unidades irmãs seja 1 (método dos momentos). unidades: [(c, P, s_obs)]."""
    def f(a):
        z2 = [((s - m) / sd) ** 2 for c, P, s in unidades for m, sd in [momentos(c, P, a)] if sd > 0]
        return float(np.mean(z2)) - 1 if z2 else 0.0
    if not unidades:
        return None
    if f(hi) <= 0:  # sem dispersão extra: o multinomial já explica
        return hi
    if f(lo) >= 0:
        return lo
    a, b = math.log(lo), math.log(hi)
    for _ in range(60):
        mid = (a + b) / 2
        if f(math.exp(mid)) > 0:
            b = mid
        else:
            a = mid
    return math.exp((a + b) / 2)


def alpha_bootstrap(unidades, n=60, seed=0):
    """Distribuição do α calibrado reamostrando as unidades irmãs (incerteza do hiperparâmetro)."""
    rng = np.random.default_rng(seed)
    if len(unidades) < 5:
        return []
    out = []
    for _ in range(n):
        idx = rng.integers(0, len(unidades), len(unidades))
        out.append(calibrar_alpha([unidades[i] for i in idx]))
    return [float(x) for x in out if x is not None]


def simular(c, P, alpha, S, rng, lote=50_000):
    """Simula a parcela de Lula entre os finalistas (e Lula em votos) sob o modelo. alpha: None, escalar ou vetor (S,)."""
    sh, LL = np.empty(S), np.empty(S)
    feitos = 0
    while feitos < S:
        n = min(lote, S - feitos)
        L = np.zeros(n)
        F = np.zeros(n)
        a = None if alpha is None else (alpha[feitos:feitos + n, None] if np.ndim(alpha) else alpha)
        for k in range(len(c)):
            ck = int(c[k])
            if ck <= 0:
                continue
            p3 = np.array([P[k, 0], P[k, 1], max(0.0, 1 - P[k, 0] - P[k, 1])])
            if a is None:
                pL = np.full(n, p3[0])
                pF = np.full(n, p3[1])
            else:
                g = rng.gamma(np.clip(a * p3, 1e-6, None), size=(n, 3))
                g /= g.sum(1, keepdims=True)
                pL, pF = g[:, 0], g[:, 1]
            xL = rng.binomial(ck, np.clip(pL, 0, 1))
            q = np.clip(pF / np.clip(1 - pL, 1e-12, None), 0, 1)
            xF = rng.binomial(ck - xL, q)
            L += xL
            F += xF
        sh[feitos:feitos + n] = L / np.clip(L + F, 1, None)
        LL[feitos:feitos + n] = L
        feitos += n
    return sh, LL


def prob_extrema(sim, s_obs, centro=None):
    """Probabilidade bicaudal de um resultado tão ou mais extremo, com intervalo e tratamento de eventos raros."""
    S = len(sim)
    m = float(np.mean(sim)) if centro is None else centro
    sd = float(np.std(sim))
    k = int(np.sum(np.abs(sim - m) >= abs(s_obs - m) - 1e-15))
    lo, hi = (stats.beta.ppf(0.025, k, S - k + 1) if k > 0 else 0.0), stats.beta.ppf(0.975, k + 1, S - k)
    z = (s_obs - m) / sd if sd > 0 else 0.0
    p_norm = float(2 * stats.norm.sf(abs(z)))
    if k >= 10:
        p, metodo = k / S, "monte_carlo"
    elif k > 0:
        p, metodo = k / S, "monte_carlo_impreciso"
    else:
        p, metodo = p_norm, "extrapolacao_normal"
    return {"p": float(p), "p_lo": float(lo), "p_hi": float(hi), "extremos": k, "simulacoes": S, "metodo": metodo,
            "p_normal": p_norm, "z": float(z), "media": m, "dp": sd, "sentido": "Lula acima" if s_obs > m else "Lula abaixo"}


def prob_valor_exato(LL, L_obs):
    """P(L2 = valor observado) estimada pelas simulações (frequência ou densidade normal se não houver ocorrência)."""
    k = int(np.sum(LL == L_obs))
    if k > 0:
        return k / len(LL)
    sd = float(np.std(LL))
    return float(stats.norm.pdf(L_obs, np.mean(LL), sd)) if sd > 0 else 0.0


def histograma(sim, s_obs, bins=40):
    lo, hi = min(float(sim.min()), s_obs), max(float(sim.max()), s_obs)
    pad = (hi - lo) * 0.03 or 1e-4
    h, e = np.histogram(sim, bins=bins, range=(lo - pad, hi + pad))
    return {"contagens": h.tolist(), "inicio": float(e[0]), "passo": float(e[1] - e[0])}


def bh_fdr(p):
    """Valores q de Benjamini–Hochberg."""
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    acc = 1.0
    for r, i in enumerate(o[::-1]):
        rank = n - r
        acc = min(acc, p[i] * n / rank)
        q[i] = acc
    return np.clip(q, 0, 1)


def classificar(q, finalistas, identidades_ok, sem_votacao=False):
    if sem_votacao:
        return "Inconclusivo"
    if not identidades_ok:
        return "Matematicamente inviável sob restrições explícitas"
    if finalistas < 300:
        return "Inconclusivo"
    if q < 0.01:
        return "Muito incomum"
    if q < 0.10:
        return "Incomum"
    return "Compatível com o modelo"


# ---------------------------------------------------------------- apresentação
def um_em_n(p):
    """Texto '1 em N' para uma probabilidade."""
    if p is None or p <= 0:
        return None
    n = 1 / p
    if n < 1.05:
        return "quase certo"
    if n < 10:
        return f"1 em {n:.1f}".replace(".", ",")
    if n < 1000:
        return f"1 em {n:,.0f}".replace(",", ".")
    for lim, nome, div in ((1e3, "mil", 1e3), (1e6, "milhão", 1e6), (1e9, "bilhão", 1e9), (1e12, "trilhão", 1e12)):
        if n < lim * 1000:
            v = n / div
            plural = {"milhão": "milhões", "bilhão": "bilhões", "trilhão": "trilhões"}.get(nome, nome) if round(v, 1) >= 2 else nome
            txt = f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
            return f"1 em {txt} {plural}"
    return "1 em mais de 1 quatrilhão"


def mega(p):
    """Comparação com a Mega-Sena (aposta simples): razão R = P_mega / P_evento e expoente n."""
    if p is None or p <= 0:
        return None
    return {"razao": MEGA / p, "n": math.log(p) / math.log(MEGA)}
