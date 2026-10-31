"""Auditoria (Fase 1): processamento offline de reconciliação, limites de transferência, cenários e Monte Carlo
para todas as unidades geográficas (Brasil, regiões, UFs, municípios e zonas), com calibração das seções.

Uso:
  python 22_auditoria.py [--sim 100000] [--sim-zona 20000] [--sim-profundo 1000000] [--seed 2026] [--forcar]

Entradas: dados/processados/secoes.parquet; portal/dados/resumo.json (matrizes Brasil, regiões, UFs) e
portal/dados/uf/<UF>.json (matriz de cada município), ambos gerados por 03_migracao.py e 04_gerar_portal.py.
Saídas (contrato versionado, schema_version abaixo):
  portal/dados/auditoria/nacional.json   Brasil, regiões, UFs, calibração, qualidade e ranking municipal
  portal/dados/auditoria/uf/<UF>.json    municípios e zonas da UF (modelos, histograma, sensibilidade, cenários)
  portal/dados/auditoria/municipios.csv, ufs.csv  exportação tabular
Cache incremental: dados/processados/auditoria_cache/<UF>.json, reaproveitado quando entradas e parâmetros não mudam.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy import stats

import auditoria_motor as M
from comum import PORTAL_DADOS, PROCESSADOS

SCHEMA = "1.0"
VERSAO_MOTOR = "1.0.0"
CACHE = PROCESSADOS / "auditoria_cache"
SAIDA = PORTAL_DADOS / "auditoria"
T1C = ["Lula_1", "Flávio_1", "Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1", "Branco_1", "Nulo_1", "Abst_1", "Aptos_1"]
T2C = ["Lula_2", "Flávio_2", "Branco_2", "Nulo_2", "Abst_2", "Aptos_2"]


# ---------------------------------------------------------------- utilitários vetorizados
def p6_de(pct10, t1):
    return M.matriz_6(pct10, t1)


def momentos_vec(C, P, alpha):
    """Versão vetorizada de M.momentos para n unidades: C (n,6), P (n,6,5)."""
    pL, pF = P[:, :, 0], P[:, :, 1]
    infl = 1.0 if alpha is None else 1 + np.clip(C - 1, 0, None) / (alpha + 1)
    EL, EF = (C * pL).sum(1), (C * pF).sum(1)
    VL = (C * pL * (1 - pL) * infl).sum(1)
    VF = (C * pF * (1 - pF) * infl).sum(1)
    CLF = -(C * pL * pF * infl).sum(1)
    tot = np.clip(EL + EF, 1e-9, None)
    m = EL / tot
    var = (EF ** 2 * VL + EL ** 2 * VF - 2 * EL * EF * CLF) / tot ** 4
    return m, np.sqrt(np.clip(var, 1e-18, None))


def calibrar_vec(C, P, s, lo=1.0, hi=1e7):
    """α tal que mean(z²) = 1 entre as unidades (bissecção em log α)."""
    if len(s) < 3:
        return None
    f = lambda a: float(np.mean(((s - momentos_vec(C, P, a)[0]) / momentos_vec(C, P, a)[1]) ** 2)) - 1
    if f(hi) <= 0:
        return hi
    if f(lo) >= 0:
        return lo
    a, b = np.log(lo), np.log(hi)
    for _ in range(50):
        mid = (a + b) / 2
        if f(np.exp(mid)) > 0:
            b = mid
        else:
            a = mid
    return float(np.exp((a + b) / 2))


def alpha_boot_vec(C, P, s, n=60, seed=0):
    rng = np.random.default_rng(seed)
    if len(s) < 5:
        return []
    out = []
    for _ in range(n):
        i = rng.integers(0, len(s), len(s))
        a = calibrar_vec(C[i], P[i], s[i])
        if a is not None:
            out.append(a)
    return out


def semente(base, *partes):
    h = hashlib.sha256(("|".join(map(str, (base,) + partes))).encode()).hexdigest()
    return int(h[:16], 16)


def share2(t2):
    return t2[0] / max(t2[0] + t2[1], 1)


# ---------------------------------------------------------------- análise de uma unidade
def analisar_unidade(uid, nivel, nome, t1, t2, P10_ref, alpha, alphas_boot, irmaos_z, S, seed, profundo=False):
    """Reconciliação, limites, cenários e os quatro modelos para uma unidade."""
    t1 = [int(x) for x in t1]
    t2 = [int(x) for x in t2]
    c = M.origens_6(t1)
    P = p6_de(P10_ref, t1)
    s_obs = share2(t2)
    rec = M.reconciliar(t1, t2)
    lim = M.limites(t1, t2)
    rng = np.random.default_rng(semente(seed, nivel, uid))
    t0 = time.time()
    modelos = {}
    # multinomial
    sim_m, _ = M.simular(c, P, None, max(S // 5, 2_000), rng)
    modelos["multinomial"] = M.prob_extrema(sim_m, s_obs)
    # Dirichlet-Multinomial (principal)
    Sd = S * 10 if profundo else S
    sim_d, LL = M.simular(c, P, alpha, Sd, rng)
    md = M.prob_extrema(sim_d, s_obs)
    md["valor_exato"] = M.prob_valor_exato(LL, t2[0])
    modelos["dirichlet"] = md
    # hierárquico: α sorteado da distribuição bootstrap da calibração
    if alphas_boot:
        av = rng.choice(np.asarray(alphas_boot), size=max(S // 5, 2_000))
        sim_h, _ = M.simular(c, P, av, len(av), rng)
        modelos["hierarquico"] = M.prob_extrema(sim_h, s_obs)
    # bootstrap empírico entre unidades irmãs
    z = md["z"]
    if irmaos_z is not None and len(irmaos_z) >= 10:
        k = int(np.sum(np.abs(irmaos_z) >= abs(z)))
        modelos["bootstrap"] = {"p": max(k, 1) / len(irmaos_z), "extremos": k, "simulacoes": int(len(irmaos_z)), "metodo": "empirico_irmaos",
                                "p_lo": None, "p_hi": None, "z": z}
    # sensibilidade: α/2 e 2α (aproximação normal)
    sens = {}
    for rot, fa in (("alpha_metade", 0.5), ("alpha_dobro", 2.0)):
        m, sd = M.momentos(c, P, alpha * fa)
        sens[rot] = float(2 * stats.norm.sf(abs((s_obs - m) / sd))) if sd > 0 else None
    return {
        "id": uid, "nivel": nivel, "nome": nome,
        "contagens": {"turno1": t1, "turno2": t2},
        "reconciliacao": rec, "limites": lim, "cenarios": M.cenarios(t1, t2),
        "monte_carlo": {"evento": "Parcela de Lula entre os finalistas no 2º turno tão ou mais distante do esperado (bicaudal)",
                        "observado": s_obs, "esperado": md["media"], "alpha": alpha, "modelos": modelos,
                        "histograma": M.histograma(sim_d, s_obs), "sensibilidade": sens, "profundo": profundo,
                        "tempo_s": round(time.time() - t0, 3)},
        "matriz_referencia_6x5": [[round(float(v), 5) for v in r] for r in P],
    }


def compacto(u):
    """Resumo por unidade para rankings e mapa."""
    md = u["monte_carlo"]["modelos"]["dirichlet"]
    r, l = u["reconciliacao"], u["limites"]
    return {"id": u["id"], "nome": u["nome"], "aptos": r["turno2"]["aptos"], "dL": r["variacao"]["Lula"], "dF": r["variacao"]["Flávio"],
            "obs": u["monte_carlo"]["observado"], "esp": md["media"], "dp": md["dp"], "z": md["z"], "p": md["p"], "p_lo": md["p_lo"], "p_hi": md["p_hi"],
            "metodo": md["metodo"], "ext": md["extremos"], "sims": md["simulacoes"], "capt": l["captacao_necessaria_lula"],
            "cruz": l["migracao_minima_flavio_para_lula"] + l["migracao_minima_lula_para_flavio"],
            "ident_ok": all(r["identidades"].values()), "fin": r["turno2"]["Lula"] + r["turno2"]["Flávio"],
            "elim": l["votos_eliminados"], "lmin": l["lula_minimo_dos_eliminados"], "fel": l["flavio_ganho_sobre_eliminados"],
            "sem_votacao": r["turno2"]["comparecimento"] > 0 and r["turno2"]["nominais"] + r["turno2"]["Branco"] + r["turno2"]["Nulo"] == 0 and r["turno2"]["Abstenção"] == 0}


# ---------------------------------------------------------------- processamento de uma UF (municípios e zonas)
def processar_uf(args):
    uf, dados, params = args
    chave = hashlib.sha256(json.dumps([dados["hash"], {k: v for k, v in params.items() if k != "forcar"}], sort_keys=True).encode()).hexdigest()
    arq = CACHE / f"{uf}.json"
    if arq.exists() and not params["forcar"]:
        c = json.loads(arq.read_text())
        if c.get("chave") == chave:
            return uf, c["resultado"], True
    t0 = time.time()
    S, Sz, seed = params["sim"], params["sim_zona"], params["seed"]
    mun = dados["municipios"]
    # calibração entre municípios da UF (referência: matriz da UF)
    C = np.array([M.origens_6(m["t1"]) for m in mun])
    P = np.array([p6_de(dados["P_uf"], m["t1"]) for m in mun])
    s = np.array([share2(m["t2"]) for m in mun])
    a_mun = calibrar_vec(C, P, s) or 1e5
    boot_mun = alpha_boot_vec(C, P, s, seed=semente(seed, "boot_mun", uf) % 2**32)
    zm = (s - momentos_vec(C, P, a_mun)[0]) / momentos_vec(C, P, a_mun)[1]
    municipios = []
    for i, m in enumerate(mun):
        u = analisar_unidade(m["cod"], "municipio", m["nome"], m["t1"], m["t2"], dados["P_uf"], a_mun, boot_mun, np.delete(zm, i), S, seed)
        municipios.append(u)
    # zonas: referência é a matriz do município
    zon = dados["zonas"]
    zonas = []
    if zon:
        Cz = np.array([M.origens_6(z["t1"]) for z in zon])
        Pz = np.array([p6_de(dados["P_mun"][str(z["mun"])], z["t1"]) for z in zon])
        sz = np.array([share2(z["t2"]) for z in zon])
        a_zon = calibrar_vec(Cz, Pz, sz) or 1e5
        boot_zon = alpha_boot_vec(Cz, Pz, sz, seed=semente(seed, "boot_zon", uf) % 2**32)
        zz = (sz - momentos_vec(Cz, Pz, a_zon)[0]) / momentos_vec(Cz, Pz, a_zon)[1]
        for i, z in enumerate(zon):
            u = analisar_unidade(f"{z['mun']}-{z['zona']}", "zona", f"Zona {z['zona']:04d}", z["t1"], z["t2"], dados["P_mun"][str(z["mun"])], a_zon, boot_zon,
                                 np.delete(zz, i), Sz, seed)
            u["mun"] = z["mun"]
            zonas.append(u)
    else:
        a_zon, boot_zon = None, []
    # seções: só a calibração (o portal calcula a análise da seção no navegador com este α)
    sec = dados["secoes"]
    Cs = np.array([M.origens_6(x) for x in sec["t1"]])
    Ps = np.array([p6_de(dados["P_mun"][str(mm)], x) for mm, x in zip(sec["mun"], sec["t1"])])
    ss = np.array([share2(x) for x in sec["t2"]])
    ok = (np.array([x[0] + x[1] for x in sec["t2"]]) >= 20)
    a_sec = calibrar_vec(Cs[ok], Ps[ok], ss[ok]) if ok.sum() >= 30 else None
    res = {"uf": uf, "alpha": {"municipio": a_mun, "zona": a_zon, "secao": a_sec}, "alpha_boot": {"municipio": boot_mun, "zona": boot_zon},
           "municipios": municipios, "zonas": zonas, "tempo_s": round(time.time() - t0, 2), "secoes": int(len(ss))}
    arq.write_text(json.dumps({"chave": chave, "resultado": res}, ensure_ascii=False))
    return uf, res, False


def evidencias(u, uf=None):
    """Evidências estruturadas da unidade (para leitura por pessoas e, numa fase futura, por agentes)."""
    r, l = u["reconciliacao"], u["limites"]
    ev = [{"tipo": "identidade_contabil", "confere": all(r["identidades"].values()), "detalhe": r["identidades"]},
          {"tipo": "reconciliacao", "ganho_finalistas": r["ganho_finalistas"], "variacao_demais_categorias": r["variacao_demais_categorias"],
           "variacao_comparecimento": r["variacao"]["comparecimento"]},
          {"tipo": "limite_transferencia", "disponivel": l["disponivel_sem_finalistas"], "minimo_para_lula": l["transferencia_minima_para_lula"],
           "captacao_necessaria_lula": l["captacao_necessaria_lula"], "possivel_sem_migracao_entre_finalistas": l["possivel_sem_migracao_entre_finalistas"],
           "migracao_minima_entre_finalistas": l["migracao_minima_flavio_para_lula"] + l["migracao_minima_lula_para_flavio"]}]
    mc = u.get("monte_carlo")
    if mc:
        for nome, m in mc["modelos"].items():
            ev.append({"tipo": "monte_carlo", "modelo": nome, "p": m["p"], "um_em_n": M.um_em_n(m["p"]), "intervalo_95": [m.get("p_lo"), m.get("p_hi")],
                       "extremos": m.get("extremos"), "simulacoes": m.get("simulacoes"), "metodo": m.get("metodo"),
                       "mega_sena": M.mega(m["p"]) if m.get("metodo") == "monte_carlo" and m["p"] <= 1e-3 else None})
    if "classificacao" in u:
        ev.append({"tipo": "classificacao", "classe": u["classificacao"], "fdr_q": u.get("fdr_q")})
    return ev


def localidade(u, uf=None):
    loc = {"nivel": u["nivel"], "id": u["id"], "nome": u["nome"]}
    if uf:
        loc["uf"] = uf
    if u["nivel"] == "zona":
        loc["municipio_tse"], loc["zona"] = int(str(u["id"]).split("-")[0]), int(str(u["id"]).split("-")[1])
    if u["nivel"] == "municipio":
        loc["municipio_tse"] = u["id"]
    return loc


mil = lambda v: f"{int(v):,}".replace(",", ".")
dec = lambda v: f"{v:.2f}".replace(".", ",")


def relatorio(nacional, resultados, testes_txt):
    """docs/auditoria_relatorio.md: cobertura e desempenho do processamento."""
    m, K, q = nacional["metadados"], nacional["contagens"], nacional["qualidade"]
    linhas = ["# Auditoria — relatório de cobertura e desempenho", "",
              f"Processado em {m['processado_em']} · motor {m['versao_motor']} · esquema {m['schema_version']} · semente {m['seed']}.", "",
              "## Cobertura", "",
              f"| Item | Processado |", "|---|---|",
              f"| UFs (com exterior) | {K['ufs']} |", f"| Municípios | {K['municipios']:,} |".replace(",", "."), f"| Cidades no exterior | {K['cidades_exterior']} |",
              f"| Zonas | {K['zonas']:,} |".replace(",", "."), f"| Seções (100% do universo) | {K['secoes']:,} |".replace(",", "."),
              f"| Seções com contas fechando | {q['comparecimento_2_confere']:,} |".replace(",", "."), f"| Seções sem votação registrada | {q['secoes_sem_votacao_registrada']} |", "",
              "## Simulações", "",
              f"- {mil(m['simulacoes']['uf_regiao_municipio'])} por região, UF e município (Dirichlet-Multinomial); {mil(m['simulacoes']['multinomial_hierarquico'])} nos modelos multinomial e hierárquico.",
              f"- {mil(m['simulacoes']['zona'])} por zona; {mil(m['simulacoes']['profundo'])} no passe profundo.", "",
              "## Calibração", "",
              f"- Municípios com p < 0,05: {dec(100 * nacional['calibracao']['frac_p_abaixo_005'])}% (esperado 5%).",
              f"- Municípios com p < 0,01: {dec(100 * nacional['calibracao']['frac_p_abaixo_001'])}% (esperado 1%).", "",
              "## Classificação dos municípios", "", "| Classe | Municípios |", "|---|---|"] + [f"| {k} | {v} |" for k, v in nacional["classes"].items()] + ["",
              "## Desempenho", "", f"Tempo total: {m['tempo_total_s']} s (4 processos).", "", "| UF | Municípios | Zonas | Tempo (s) |", "|---|---|---|---|"] + \
             [f"| {uf} | {len(r['municipios'])} | {len(r['zonas'])} | {r['tempo_s']} |" for uf, r in sorted(resultados.items(), key=lambda x: -x[1]["tempo_s"])] + ["",
              "## Testes", "", "```", testes_txt.strip(), "```", ""]
    (PORTAL_DADOS.parent.parent / "docs" / "auditoria_relatorio.md").write_text("\n".join(linhas))


def limpar(o):
    if isinstance(o, dict):
        return {k: limpar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpar(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return None if not np.isfinite(v) else v
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=int, default=100_000)
    ap.add_argument("--sim-zona", type=int, default=20_000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--processos", type=int, default=4)
    args = ap.parse_args()
    t_ini = time.time()
    CACHE.mkdir(parents=True, exist_ok=True)
    (SAIDA / "uf").mkdir(parents=True, exist_ok=True)
    R = json.load(open(PORTAL_DADOS / "resumo.json"))
    MIG = R["migracao"]
    sec = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    # qualidade dos dados (todas as seções)
    v1 = sec[["Lula_1", "Flávio_1", "Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1", "Branco_1", "Nulo_1"]].sum(1)
    v2 = sec[["Lula_2", "Flávio_2", "Branco_2", "Nulo_2"]].sum(1)
    qualidade = {"secoes": int(len(sec)),
                 "secoes_com_os_dois_turnos": int(((sec.Aptos_1 > 0) & (sec.Aptos_2 > 0)).sum()),
                 "comparecimento_1_confere": int((v1 == sec.Aptos_1 - sec.Abst_1).sum()),
                 "comparecimento_2_confere": int((v2 == sec.Aptos_2 - sec.Abst_2).sum()),
                 "comparecimento_acima_aptos": int(((sec.Aptos_1 - sec.Abst_1) > sec.Aptos_1).sum() + ((sec.Aptos_2 - sec.Abst_2) > sec.Aptos_2).sum()),
                 "secoes_sem_votacao_registrada": int(((v2 == 0) & (sec.Abst_2 == 0)).sum()),
                 "aptos_diferentes_entre_turnos": int((sec.Aptos_1 != sec.Aptos_2).sum()),
                 "variacao_aptos_total": int(sec.Aptos_2.sum() - sec.Aptos_1.sum())}
    zon = sec.groupby(["SG_UF", "CD_MUNICIPIO", "NR_ZONA"])[T1C + T2C].sum().reset_index()
    # unidades com seções suficientes para calibrar
    tarefas, ufs_info = [], {}
    profundos = {}
    for uf, u in R["ufs"].items():
        U = json.load(open(PORTAL_DADOS / "uf" / f"{uf}.json"))
        mun = [{"cod": m["cod"], "nome": m["nome"], "t1": m["t1"][:11], "t2": m["t2"][:6]} for m in U["municipios"]]
        P_mun = {str(m["cod"]): m["mig"]["pct"] for m in U["municipios"]}
        zs = zon[zon.SG_UF == uf]
        zonas = [{"mun": int(r.CD_MUNICIPIO), "zona": int(r.NR_ZONA), "t1": [int(getattr(r, c)) for c in T1C], "t2": [int(getattr(r, c)) for c in T2C]}
                 for r in zs.itertuples() if str(int(r.CD_MUNICIPIO)) in P_mun]
        su = sec[sec.SG_UF == uf]
        secs = {"mun": su.CD_MUNICIPIO.astype(int).tolist(), "t1": su[T1C].astype(int).values.tolist(), "t2": su[T2C].astype(int).values.tolist()}
        dados = {"municipios": mun, "P_uf": u["migracao"]["pct"], "P_mun": P_mun, "zonas": zonas, "secoes": secs}
        dados["hash"] = hashlib.sha256(json.dumps([mun, dados["P_uf"], zonas[:5], len(zonas), len(secs["mun"])]).encode()).hexdigest()
        ufs_info[uf] = {"nome": u["nome"], "regiao": u["regiao"], "t1": u["t1"][:11], "t2": u["t2"][:6]}
        tarefas.append([uf, dados])
    params = {"sim": args.sim, "sim_zona": args.sim_zona, "seed": args.seed, "forcar": args.forcar, "profundos": profundos, "versao": VERSAO_MOTOR}
    resultados, usados_cache = {}, []
    with Pool(args.processos) as pool:
        for uf, res, cache in pool.imap_unordered(processar_uf, [(uf, d, params) for uf, d in sorted(tarefas, key=lambda x: -len(x[1]["municipios"]))]):
            resultados[uf] = res
            if cache:
                usados_cache.append(uf)
            print(time.strftime("%H:%M:%S"), uf, "cache" if cache else f"{res['tempo_s']}s", len(res["municipios"]), "mun", len(res["zonas"]), "zonas", flush=True)
    # reconciliação, limites e cenários são baratos: recalculados sempre (o cache guarda só o Monte Carlo)
    for r in resultados.values():
        for u in r["municipios"] + r["zonas"]:
            t1, t2 = u["contagens"]["turno1"], u["contagens"]["turno2"]
            u["reconciliacao"], u["limites"], u["cenarios"] = M.reconciliar(t1, t2), M.limites(t1, t2), M.cenarios(t1, t2)
    # passe profundo: 10× simulações (Dirichlet) para os 20 municípios mais distantes do esperado
    cand = sorted(((uf, m) for uf, r in resultados.items() for m in r["municipios"] if compacto(m)["fin"] >= 300),
                  key=lambda x: -abs(x[1]["monte_carlo"]["modelos"]["dirichlet"]["z"]))[:20]
    t_p = time.time()
    for uf, m in cand:
        r = resultados[uf]
        P10 = json.load(open(PORTAL_DADOS / "resumo.json"))["ufs"][uf]["migracao"]["pct"]
        irm = np.array([x["monte_carlo"]["modelos"]["dirichlet"]["z"] for x in r["municipios"] if x["id"] != m["id"]])
        novo = analisar_unidade(m["id"], "municipio", m["nome"], m["contagens"]["turno1"], m["contagens"]["turno2"], P10, r["alpha"]["municipio"],
                                r["alpha_boot"]["municipio"], irm, args.sim, args.seed, profundo=True)
        r["municipios"][[x["id"] for x in r["municipios"]].index(m["id"])] = novo
    print("passe profundo:", len(cand), "municípios em", round(time.time() - t_p, 1), "s", flush=True)
    # UFs e regiões: referência Brasil, α calibrado entre UFs
    P_br = MIG["brasil"]["pct"]
    uf_lista = sorted(ufs_info)
    Cu = np.array([M.origens_6(ufs_info[u]["t1"]) for u in uf_lista])
    Pu = np.array([p6_de(P_br, ufs_info[u]["t1"]) for u in uf_lista])
    su_ = np.array([share2(ufs_info[u]["t2"]) for u in uf_lista])
    a_uf = calibrar_vec(Cu, Pu, su_) or 1e5
    boot_uf = alpha_boot_vec(Cu, Pu, su_, seed=7)
    zu = (su_ - momentos_vec(Cu, Pu, a_uf)[0]) / momentos_vec(Cu, Pu, a_uf)[1]
    ufs_res = {}
    for i, u in enumerate(uf_lista):
        ufs_res[u] = analisar_unidade(u, "uf", ufs_info[u]["nome"], ufs_info[u]["t1"], ufs_info[u]["t2"], P_br, a_uf, boot_uf, np.delete(zu, i), args.sim, args.seed)
    reg_res = {}
    for reg, membros in R["regioes"].items():
        t1 = np.sum([ufs_info[u]["t1"] for u in membros], 0).tolist()
        t2 = np.sum([ufs_info[u]["t2"] for u in membros], 0).tolist()
        reg_res[reg] = analisar_unidade(reg, "regiao", reg, t1, t2, P_br, a_uf, boot_uf, None, args.sim, args.seed)
        reg_res[reg]["ufs"] = membros
    brasil = {"id": "BR", "nivel": "brasil", "nome": "Brasil", "contagens": {"turno1": R["brasil"]["t1"][:11], "turno2": R["brasil"]["t2"][:6]},
              "reconciliacao": M.reconciliar(R["brasil"]["t1"][:11], R["brasil"]["t2"][:6]), "limites": M.limites(R["brasil"]["t1"][:11], R["brasil"]["t2"][:6]),
              "cenarios": M.cenarios(R["brasil"]["t1"][:11], R["brasil"]["t2"][:6]),
              "monte_carlo": None, "nota_monte_carlo": "O Brasil é o nível de referência das matrizes; a análise probabilística começa nas regiões e UFs."}
    # FDR nacional entre municípios e entre zonas
    todos = [(uf, m) for uf, r in resultados.items() for m in r["municipios"]]
    q = M.bh_fdr([m["monte_carlo"]["modelos"]["dirichlet"]["p"] for _, m in todos])
    ranking = []
    for (uf, m), qq in zip(todos, q):
        c = compacto(m)
        c["q"] = float(qq)
        c["classe"] = M.classificar(qq, c["fin"], c["ident_ok"], c["sem_votacao"])
        m["fdr_q"], m["classificacao"] = float(qq), c["classe"]
        c["uf"] = uf
        ranking.append(c)
    zt = [(uf, z) for uf, r in resultados.items() for z in r["zonas"]]
    qz = M.bh_fdr([z["monte_carlo"]["modelos"]["dirichlet"]["p"] for _, z in zt]) if zt else []
    for (uf, z), qq in zip(zt, qz):
        z["fdr_q"] = float(qq)
        cz = compacto(z)
        z["classificacao"] = M.classificar(qq, cz["fin"], cz["ident_ok"], cz["sem_votacao"])
    qu = M.bh_fdr([ufs_res[u]["monte_carlo"]["modelos"]["dirichlet"]["p"] for u in uf_lista])
    for u, qq in zip(uf_lista, qu):
        ufs_res[u]["fdr_q"] = float(qq)
        ufs_res[u]["classificacao"] = M.classificar(qq, 10**6, all(ufs_res[u]["reconciliacao"]["identidades"].values()))
        ufs_res[u]["municipios_incomuns"] = int(sum(1 for c in ranking if c["uf"] == u and c["classe"] in ("Incomum", "Muito incomum")))
        ufs_res[u]["municipios"] = int(sum(1 for c in ranking if c["uf"] == u))
        ufs_res[u]["secoes"] = resultados[u]["secoes"]
        ufs_res[u]["zonas"] = len(resultados[u]["zonas"])
    # verificação de calibração (posterior predictive): distribuição dos valores p municipais
    pm = np.array([c["p"] for c in ranking])
    calib = {"hist_p": np.histogram(pm, bins=20, range=(0, 1))[0].tolist(), "frac_p_abaixo_005": float((pm < 0.05).mean()),
             "frac_p_abaixo_001": float((pm < 0.01).mean()), "esperado_005": 0.05, "esperado_001": 0.01}
    classes = pd.Series([c["classe"] for c in ranking]).value_counts().to_dict()
    meta = {"fonte": "TSE — boletins de urna por seção (votacao_secao) e matrizes de 03_migracao.py", "schema_version": SCHEMA, "versao_motor": VERSAO_MOTOR,
            "processado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tempo_total_s": None, "seed": args.seed,
            "simulacoes": {"uf_regiao_municipio": args.sim, "zona": args.sim_zona, "profundo": args.sim * 10, "multinomial_hierarquico": max(args.sim // 5, 2_000)},
            "modelo_principal": "dirichlet", "evento": "Parcela de Lula entre os finalistas no 2º turno tão ou mais distante do esperado (bicaudal)",
            "referencias": {"regiao": "Brasil", "uf": "Brasil", "municipio": "UF", "zona": "município", "secao": "município"},
            "classificacao": {"Muito incomum": "q < 0,01 (FDR de Benjamini–Hochberg entre municípios)", "Incomum": "q < 0,10",
                              "Inconclusivo": "menos de 300 votos nos finalistas no 2º turno", "Matematicamente inviável sob restrições explícitas": "identidade contábil não confere"},
            "mega_sena": {"probabilidade": M.MEGA, "regra": "comparação exibida só quando o evento ocorreu ao menos 10 vezes nas simulações"},
            "cache_reaproveitado": sorted(usados_cache)}
    alfas = {u: resultados[u]["alpha"] for u in resultados}
    nacional = {"schema_version": SCHEMA, "metadados": meta, "brasil": brasil, "regioes": reg_res, "ufs": ufs_res,
                "alpha": {"uf": a_uf, "por_uf": alfas}, "calibracao": calib, "qualidade": qualidade, "classes": classes,
                "contagens": {"ufs": len(uf_lista), "municipios": sum(1 for c in ranking if c["uf"] != "ZZ"), "cidades_exterior": sum(1 for c in ranking if c["uf"] == "ZZ"),
                              "zonas": len(zt), "secoes": int(len(sec))},
                "ranking_municipios": {"colunas": ["uf", "id", "nome", "aptos", "dL", "dF", "obs", "esp", "dp", "z", "p", "p_lo", "p_hi", "metodo", "ext", "sims", "q", "classe", "capt", "cruz", "fin", "elim", "lmin", "fel"],
                                       "linhas": [[c[k] for k in ["uf", "id", "nome", "aptos", "dL", "dF", "obs", "esp", "dp", "z", "p", "p_lo", "p_hi", "metodo", "ext", "sims", "q", "classe", "capt", "cruz", "fin", "elim", "lmin", "fel"]] for c in ranking]}}
    for u in list(reg_res.values()) + list(ufs_res.values()) + [brasil]:
        u["localidade"], u["evidencias"] = localidade(u), evidencias(u)
    for uf, r in resultados.items():
        for u in r["municipios"] + r["zonas"]:
            u["localidade"], u["evidencias"] = localidade(u, uf), evidencias(u, uf)
    meta["tempo_total_s"] = round(time.time() - t_ini, 1)
    with open(SAIDA / "nacional.json", "w") as f:
        json.dump(limpar(nacional), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for uf, r in resultados.items():
        doc = {"schema_version": SCHEMA, "metadados": {**meta, "uf": uf, "tempo_uf_s": r["tempo_s"]}, "localidade": {"uf": uf, "nome": ufs_info[uf]["nome"]},
               "alpha": r["alpha"], "municipios": r["municipios"], "zonas": r["zonas"]}
        with open(SAIDA / "uf" / f"{uf}.json", "w") as f:
            json.dump(limpar(doc), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    pd.DataFrame(ranking).to_csv(SAIDA / "municipios.csv", index=False)
    pd.DataFrame([{"uf": u, **compacto(ufs_res[u]), "q": ufs_res[u]["fdr_q"], "classe": ufs_res[u]["classificacao"]} for u in uf_lista]).to_csv(SAIDA / "ufs.csv", index=False)
    import subprocess
    testes = subprocess.run(["python3", "-m", "unittest", "discover", "-s", str(PORTAL_DADOS.parent.parent / "tests")], capture_output=True, text=True, cwd=PORTAL_DADOS.parent.parent)
    relatorio(nacional, resultados, (testes.stderr or testes.stdout).splitlines()[-3:] and "\n".join((testes.stderr or testes.stdout).splitlines()[-3:]))
    print("classes:", classes)
    print("calibração:", calib["frac_p_abaixo_005"], calib["frac_p_abaixo_001"])
    print("tempo total:", meta["tempo_total_s"], "s")


if __name__ == "__main__":
    main()
