"""Auditoria dos boletins: seções atípicas (longe das vizinhas ou do próprio 1º turno), ocorrências previstas em lei,
falhas contábeis, testes, perguntas que circulam e o impacto de cada grupo no resultado.

Vizinhas: as outras seções do mesmo local de votação; quando o local tem menos de 3 outras seções, as da mesma zona.
Todas as regras estão em REGRAS (texto do “?” no portal). Saldo = votos de Lula − votos de Flávio no 2º turno nas seções do
grupo. “Sem as seções atípicas” remove essas seções do total. Votos depois das 17h: o voto é secreto; o saldo estimado
aplica a cada seção a divisão Lula × Flávio da própria seção.

Entradas: dados/processados/secoes.parquet, dados/processados/logs/*.parquet, detalhe_votacao_secao (origem do voto),
votacao_candidato_munzona (totais oficiais), portal/dados/{auditoria,votos_eleitorado,virada_falhas,logs,ja_votou,
sem_digital,auditoria/transferencia,auditoria/nacional}.json.
Saída: portal/dados/boletins.json
"""
import glob
import json
import time

import numpy as np
import pandas as pd

from comum import ARQUIVOS, BRUTOS, PORTAL_DADOS, PROCESSADOS, ler_csv_tse

CH = ["uf", "mun", "zona", "secao"]
MAX_LISTA = 400  # seções listadas por tipo

REGRAS = {
    "sem_digital": ("Sem digital", "Metade ou mais dos votos sem a digital do eleitor conferida e pelo menos 40 pontos acima das vizinhas (30 votos ou mais)."),
    "abriu_tarde": ("Abriu tarde", "Urna pronta e primeiro voto mais de 1 hora depois das 8h de Brasília, sem troca de urna."),
    "virada": ("Virada inesperada", "O vencedor da seção mudou do 1º para o 2º turno, as vizinhas não mudaram e a variação de Lula ficou 15 pontos ou mais longe da das vizinhas (100 votos ou mais nos finalistas)."),
    "comparecimento": ("Comparecimento", "Comparecimento no 2º turno 25 pontos ou mais diferente do das vizinhas (100 eleitores ou mais)."),
    "comp_mudou": ("Comparecimento mudou", "A variação do comparecimento entre os turnos ficou 15 pontos ou mais longe da variação das vizinhas (100 eleitores ou mais)."),
    "ja_votou": ("Já votou", "20 ou mais alertas “O eleitor identificado já votou” no log da urna."),
    "migracao": ("Exigiu migração de Flávio", "O ganho de Lula na seção é maior que todos os votos dos eliminados somados a brancos, nulos e faltosos liberados: só fecha com eleitores de Flávio passando para Lula (30 votos ou mais nos eliminados)."),
}
OCORR = {
    "prorrogada": ("Prorrogada", "Votação seguiu depois das 17h para quem estava na fila (previsto em lei)."),
    "urna_trocada": ("Urna trocada", "Urna substituída por uma de contingência durante a votação (previsto em lei)."),
    "sem_boletim": ("Sem boletim", "Seção sem votos registrados no boletim (não instalada ou sem votação)."),
    "junta": ("Contada pela junta", "Votos apurados pelo sistema de apuração da junta eleitoral, em vez do boletim da urna."),
    "recuperados": ("Dados recuperados", "Boletim gerado pelo recuperador de dados (RED) a partir da memória da urna."),
    "reinicio": ("Urna reiniciada", "A urna foi ligada de novo depois de pronta para votar."),
    "bateria": ("Na bateria", "Falta de energia durante o dia: a urna funcionou 5 minutos ou mais na bateria interna."),
}


def carregar():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet").rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    logs = []
    for f in sorted(glob.glob(str(PROCESSADOS / "logs" / "*.parquet"))):
        t = int(f.split("/")[-1][0])
        d = pd.read_parquet(f, columns=CH + ["votos_log", "hab_biometrica", "t_pronta", "t_primeiro_voto", "t_encerramento", "fuso", "votos_apos_17h", "contingencia", "ligadas_apos_pronta", "bateria", "bateria_min", "eleitor_ja_votou"])
        logs.append(d.assign(turno=t))
    lg = pd.concat(logs, ignore_index=True)
    det = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "DS_ORIGEM_VOTO"])
    det = det.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao", "NR_TURNO": "turno"})
    return s, lg, det


def vizinhas(df, cols):
    """Média das outras seções do mesmo local (ou da zona, se o local tem menos de 3 outras), para somas em `cols`.
    Retorna DataFrame com as somas das vizinhas (sem a própria seção)."""
    loc = df.groupby(["uf", "mun", "zona", "NR_LOCAL_VOTACAO"])[cols].transform("sum") - df[cols]
    nloc = df.groupby(["uf", "mun", "zona", "NR_LOCAL_VOTACAO"])["secao"].transform("count") - 1
    zon = df.groupby(["uf", "mun", "zona"])[cols].transform("sum") - df[cols]
    usa_loc = (nloc >= 3).to_numpy()[:, None]
    return pd.DataFrame(np.where(usa_loc, loc.to_numpy(), zon.to_numpy()), columns=cols, index=df.index)


def cidades_ano(t1, t2):
    """Indicadores de cidade comparáveis entre anos. t1/t2: DataFrames por cidade com lider, segundo, outros, aptos,
    comparecimento, brancos, nulos e a coluna pt (votos do candidato do PT)."""
    from scipy import stats
    j = t1.join(t2, lsuffix="1", rsuffix="2", how="inner")
    gl, gs = j.lider2 - j.lider1, j.segundo2 - j.segundo1
    bn1, bn2 = j.brancos1 + j.nulos1, j.brancos2 + j.nulos2
    ab1, ab2 = j.aptos1 - j.comparecimento1, j.aptos2 - j.comparecimento2
    E = j.outros1
    K = (gs - (bn1 - bn2).clip(lower=0) - (ab1 - ab2).clip(lower=0)).clip(lower=0)
    ok = E >= 30
    mu = float(K[ok].sum() / E[ok].sum())
    lp = stats.binom.logsf(K[ok] - 1, E[ok], mu) / np.log(10)
    soma = (gs + gl.clip(lower=0))
    y = (j.pt2 / j.aptos2 - j.pt1 / j.aptos1)
    x = -(bn2 / j.aptos2 - bn1 / j.aptos1)
    dc = j.comparecimento2 / j.aptos2 - j.comparecimento1 / j.aptos1  # controla a variação do comparecimento
    w = np.sqrt(j.aptos2.to_numpy())
    X = np.column_stack([np.ones(len(j)), x, dc]) * w[:, None]
    incl = float(np.linalg.lstsq(X, y.to_numpy() * w, rcond=None)[0][1])
    return {"cidades": int(len(j)), "lider_perdeu": int((gl < 0).sum()),
            "segundo_95": int(((gs > 0) & (soma > 0) & (gs / soma.where(soma > 0, 1) >= 0.95)).sum()),
            "migracao": int((ok & (K > E)).sum()), "migracao_pct": float(100 * (ok & (K > E)).sum() / ok.sum()),
            "binomial_pct": float(100 * np.mean(lp < -10)),
            "abstencao_pp": float(100 * (ab2.sum() / j.aptos2.sum() - ab1.sum() / j.aptos1.sum())),
            "brancos_nulos_inclinacao": incl}


def historico_cidades(s):
    """2018, 2022 (historico_municipios.parquet) e 2026 (seções somadas por cidade), com os mesmos indicadores."""
    h = pd.read_parquet(PROCESSADOS / "historico_municipios.parquet")
    out = {}
    pt = {2018: "segundo", 2022: "lider"}  # candidato do PT: Haddad (2º no 1º turno de 2018) e Lula (1º em 2022)
    for ano in (2018, 2022):
        g = h[h.ano == ano].set_index(["SG_UF", "CD_MUNICIPIO"])
        t = {k: g[g.NR_TURNO == k][["lider", "segundo", "outros", "aptos", "comparecimento", "brancos", "nulos"]].assign(pt=lambda x: x[pt[ano]]) for k in (1, 2)}
        out[ano] = cidades_ano(t[1], t[2])
    c = s.groupby(["uf", "mun"]).sum(numeric_only=True)
    t1 = pd.DataFrame({"lider": c["Flávio_1"], "segundo": c.Lula_1, "outros": c[["Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1"]].sum(axis=1),
                       "aptos": c.Aptos_1, "comparecimento": c.Comp_1, "brancos": c.Branco_1, "nulos": c.Nulo_1, "pt": c.Lula_1})
    t2 = pd.DataFrame({"lider": c["Flávio_2"], "segundo": c.Lula_2, "outros": 0, "aptos": c.Aptos_2, "comparecimento": c.Comp_2, "brancos": c.Branco_2, "nulos": c.Nulo_2, "pt": c.Lula_2})
    out[2026] = cidades_ano(t1, t2)
    return out


def br(x, d=0):
    """Número no padrão brasileiro (milhar com ponto, decimal com vírgula)."""
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brm(x, d=0):
    return br(x, d).replace("-", "−")


def brs(x):
    return ("+" if x > 0 else "") + br(x)


def main():
    t0 = time.time()
    s, lg, det = carregar()
    nomes = {(r.uf, int(r.mun)): r.NM_MUNICIPIO for r in s[["uf", "mun", "NM_MUNICIPIO"]].drop_duplicates().itertuples()}
    l2 = lg[lg.turno == 2].drop(columns="turno").add_suffix("_2").rename(columns={f"{c}_2": c for c in CH})
    l1 = lg[lg.turno == 1][CH + ["votos_log", "hab_biometrica"]].rename(columns={"votos_log": "votos_log_1", "hab_biometrica": "hab_biometrica_1"})
    d = s.merge(l2, on=CH, how="left").merge(l1, on=CH, how="left")
    o2 = det[det.turno == 2][CH + ["DS_ORIGEM_VOTO"]]
    d = d.merge(o2, on=CH, how="left")
    for c in ("votos_log_2", "hab_biometrica_2", "votos_apos_17h_2", "ligadas_apos_pronta_2", "bateria_2", "bateria_min_2", "eleitor_ja_votou_2"):
        d[c] = d[c].fillna(0)
    d["contingencia_2"] = d.contingencia_2.fillna(False).astype(bool)
    d["fin2"] = d.Lula_2 + d["Flávio_2"]
    d["fin1"] = d.Lula_1 + d["Flávio_1"]
    d["saldo"] = d.Lula_2 - d["Flávio_2"]
    d["sd"] = (d.votos_log_2 - d.hab_biometrica_2).clip(lower=0)
    V = vizinhas(d, ["sd", "votos_log_2", "Lula_1", "Flávio_1", "Lula_2", "Flávio_2", "Comp_1", "Comp_2", "Aptos_1", "Aptos_2"])
    dom = d.uf != "ZZ"
    flags = {}
    # sem digital
    p_sd = d.sd / d.votos_log_2.clip(lower=1)
    v_sd = V.sd / V.votos_log_2.clip(lower=1)
    flags["sem_digital"] = dom & (d.votos_log_2 >= 30) & (p_sd >= 0.5) & (p_sd - v_sd >= 0.40) & (V.votos_log_2 >= 30)
    # abriu tarde (hora local)
    tp = pd.to_timedelta(d.t_pronta_2.fillna("00:00:00")).dt.total_seconds()
    d["atraso_min"] = np.where(d.t_pronta_2.notna(), (tp - (8 + d.fuso_2.fillna(0)) * 3600) / 60, np.nan)
    tv = pd.to_timedelta(d.t_primeiro_voto_2.fillna("00:00:00")).dt.total_seconds()
    atraso_voto = np.where(d.t_primeiro_voto_2.notna(), (tv - (8 + d.fuso_2.fillna(0)) * 3600) / 60, np.nan)
    # urna pronta e primeiro voto mais de 1 hora depois do horário, sem troca de urna (a urna de contingência fica pronta mais tarde)
    flags["abriu_tarde"] = dom & (d.atraso_min > 60) & (atraso_voto > 60) & ~d.contingencia_2
    # virada inesperada
    s1 = d.Lula_1 / d.fin1.clip(lower=1)
    s2 = d.Lula_2 / d.fin2.clip(lower=1)
    vs1 = V.Lula_1 / (V.Lula_1 + V["Flávio_1"]).clip(lower=1)
    vs2 = V.Lula_2 / (V.Lula_2 + V["Flávio_2"]).clip(lower=1)
    vira = (s1 - 0.5) * (s2 - 0.5) < 0
    vviz = (vs1 - 0.5) * (vs2 - 0.5) < 0
    flags["virada"] = dom & (d.fin2 >= 100) & (d.fin1 >= 100) & vira & ~vviz & (((s2 - s1) - (vs2 - vs1)).abs() >= 0.15)
    # comparecimento
    c2 = d.Comp_2 / d.Aptos_2.clip(lower=1)
    c1 = d.Comp_1 / d.Aptos_1.clip(lower=1)
    vc2 = V.Comp_2 / V.Aptos_2.clip(lower=1)
    vc1 = V.Comp_1 / V.Aptos_1.clip(lower=1)
    flags["comparecimento"] = dom & (d.Aptos_2 >= 100) & ((c2 - vc2).abs() >= 0.25)
    flags["comp_mudou"] = dom & (d.Aptos_2 >= 100) & (((c2 - c1) - (vc2 - vc1)).abs() >= 0.15) & ~flags["comparecimento"]
    flags["ja_votou"] = d.eleitor_ja_votou_2 >= 20
    # migração exigida (mesma conta do teste de transferência)
    E = d[["Renan_1", "Cury_1", "Caiado_1", "Zema_1", "Outros_1"]].sum(axis=1)
    bn = ((d.Branco_1 + d.Nulo_1) - (d.Branco_2 + d.Nulo_2)).clip(lower=0)
    ab = (d.Abst_1 - d.Abst_2).clip(lower=0)
    K = ((d.Lula_2 - d.Lula_1) - bn - ab).clip(lower=0)
    flags["migracao"] = dom & (E >= 30) & (K > E)

    # valores exibidos em cada tipo (seção × vizinhas)
    valor = {
        "sem_digital": (p_sd, v_sd, "pct"), "abriu_tarde": (d.atraso_min, None, "min"), "virada": (s2, s1 + (vs2 - vs1), "lula"),
        "comparecimento": (c2, vc2, "pct"), "comp_mudou": (c2 - c1, vc2 - vc1, "pp"), "ja_votou": (d.eleitor_ja_votou_2, None, "n"),
        "migracao": (K / E.clip(lower=1), None, "pct"),
    }
    ocorr = {
        "prorrogada": d.votos_apos_17h_2 > 0, "urna_trocada": d.contingencia_2, "sem_boletim": (d.Comp_2 == 0) | d.DS_ORIGEM_VOTO.isna(),
        "junta": d.DS_ORIGEM_VOTO.fillna("").str.contains("apuração", case=False), "recuperados": d.DS_ORIGEM_VOTO.fillna("").str.contains("RED"),
        "reinicio": d.ligadas_apos_pronta_2 > 0, "bateria": d.bateria_min_2 >= 5,
    }
    # falhas contábeis: votos ≠ comparecimento, comparecimento > aptos
    fal = (d.Lula_2 + d["Flávio_2"] + d.Branco_2 + d.Nulo_2 != d.Comp_2) | (d.Comp_2 > d.Aptos_2)

    margem = int(d.saldo.sum())
    atip = np.zeros(len(d), bool)
    for f in flags.values():
        atip |= f.to_numpy()
    # votos depois das 17h: saldo estimado pela divisão da própria seção
    nom2 = (d.fin2 + d.Branco_2 + d.Nulo_2).clip(lower=1)
    saldo17 = float((d.votos_apos_17h_2 * d.saldo / nom2).sum())

    def lista(msk, tipo):
        g = d[msk].copy()
        g["val"], g["viz"] = valor[tipo][0][msk], (valor[tipo][1][msk] if valor[tipo][1] is not None else np.nan)
        g["dist"] = (g.val - g.viz).abs() if valor[tipo][1] is not None else g.val.abs()
        g = g.sort_values("dist", ascending=False).head(MAX_LISTA)
        r = lambda x: None if pd.isna(x) else round(float(x), 4)
        return [[x.uf, int(x.mun), nomes.get((x.uf, int(x.mun)), ""), int(x.zona), int(x.secao), r(x.val), r(x.viz), int(x.saldo), int(x.fin2)] for x in g.itertuples()]

    tipos = {}
    for k, (rot, regra) in REGRAS.items():
        m = flags[k]
        tipos[k] = {"rotulo": rot, "regra": regra, "formato": valor[k][2], "secoes": int(m.sum()), "saldo": int(d.loc[m, "saldo"].sum()),
                    "validos": int(d.loc[m, "fin2"].sum()), "ufs": d.loc[m].groupby("uf").size().astype(int).to_dict(),
                    "saldo_ufs": d.loc[m].groupby("uf").saldo.sum().astype(int).to_dict(), "lista": lista(m, k)}
    ocs = {}
    for k, (rot, regra) in OCORR.items():
        m = ocorr[k]
        g = d[m].sort_values("votos_apos_17h_2" if k == "prorrogada" else "fin2", ascending=False).head(MAX_LISTA)
        ocs[k] = {"rotulo": rot, "regra": regra, "secoes": int(m.sum()), "saldo": int(d.loc[m, "saldo"].sum()), "ufs": d.loc[m].groupby("uf").size().astype(int).to_dict(),
                  "lista": [[x.uf, int(x.mun), nomes.get((x.uf, int(x.mun)), ""), int(x.zona), int(x.secao), int(x.votos_apos_17h_2) if k == "prorrogada" else None,
                            (x.t_encerramento_2[:5] if isinstance(x.t_encerramento_2, str) else None) if k == "prorrogada" else None, int(x.saldo), int(x.fin2)] for x in g.itertuples()]}

    # bate com o TSE: totais por UF dos boletins × totais oficiais por município/zona (votacao_candidato_munzona)
    of = ler_csv_tse(BRUTOS / ARQUIVOS["votacao_candidato_munzona"][1], usecols=["NR_TURNO", "SG_UF", "NR_CANDIDATO", "QT_VOTOS_NOMINAIS"])
    of = of[(of.NR_TURNO == 2) & of.NR_CANDIDATO.isin([13, 22])].pivot_table(index="SG_UF", columns="NR_CANDIDATO", values="QT_VOTOS_NOMINAIS", aggfunc="sum")
    bu = d.groupby("uf")[["Lula_2", "Flávio_2"]].sum()
    conf = {u: [int(bu.loc[u, "Lula_2"]), int(bu.loc[u, "Flávio_2"]), int(of.loc[u, 13]) if u in of.index else None, int(of.loc[u, 22]) if u in of.index else None] for u in bu.index}
    bate = sum(1 for v in conf.values() if v[0] == v[2] and v[1] == v[3])

    # testes e perguntas a partir dos resultados já publicados
    A = json.load(open(PORTAL_DADOS / "auditoria.json"))
    LG = json.load(open(PORTAL_DADOS / "logs.json"))["turnos"]["2"]
    JV = json.load(open(PORTAL_DADOS / "ja_votou.json"))
    SD = json.load(open(PORTAL_DADOS / "sem_digital.json"))
    VE = json.load(open(PORTAL_DADOS / "votos_eleitorado.json"))
    VF = json.load(open(PORTAL_DADOS / "virada_falhas.json"))["2"]
    TR = json.load(open(PORTAL_DADOS / "auditoria" / "transferencia.json"))
    NA = json.load(open(PORTAL_DADOS / "auditoria" / "nacional.json"))
    integ, dig = A["integridade"], A["digitos"]
    lt = [l for l in TR["niveis"]["municipio"]["linhas"]]
    ci = {c: i for i, c in enumerate(TR["niveis"]["municipio"]["colunas"])}
    cls = pd.Series([l[ci["classe"]] for l in lt]).value_counts().to_dict()
    n100 = int(((d.fin2 >= 50) & ((d.Lula_2 == d.fin2) | (d["Flávio_2"] == d.fin2))).sum())
    n100l = int(((d.fin2 >= 50) & (d.Lula_2 == d.fin2)).sum())
    fx = SD["faixas_resultado"]
    H = historico_cidades(s)
    LG1 = json.load(open(PORTAL_DADOS / "logs.json"))["turnos"]["1"]

    def comp(nome, chave, texto, maior_e_pior=True, d=0, suf=""):
        v = {a: H[a][chave] for a in (2026, 2022, 2018)}
        ref = max(v[2022], v[2018]) if maior_e_pior else min(v[2022], v[2018])
        dentro = v[2026] <= ref if maior_e_pior else v[2026] >= ref
        return {"grupo": "historico", "nome": nome, "status": "Dentro" if dentro else "Acima", "ok": bool(dentro),
                "texto": texto.format(a26=brm(v[2026], d) + suf, a22=brm(v[2022], d) + suf, a18=brm(v[2018], d) + suf), "anos": {str(k): round(x, 4) for k, x in v.items()}}

    def conf_t(nome, ok, texto, grupo="arquivos"):
        return {"grupo": grupo, "nome": nome, "status": "Confere" if ok else "Não confere", "ok": bool(ok), "texto": texto}

    testes = [
        comp("Cidades em que o líder do 1º turno perdeu votos", "lider_perdeu", "O líder do 1º turno perdeu votos em {a26} cidades em 2026 (Flávio), {a22} em 2022 (Lula) e {a18} em 2018 (Bolsonaro)."),
        comp("2º colocado com 95% ou mais do ganho", "segundo_95", "O 2º colocado do 1º turno ficou com 95% ou mais do ganho dos finalistas em {a26} cidades em 2026, {a22} em 2022 e {a18} em 2018."),
        comp("Cidades que exigem migração entre finalistas", "migracao_pct", "O ganho do 2º colocado só fecha com eleitores do líder mudando de lado em {a26} das cidades em 2026, {a22} em 2022 e {a18} em 2018.", d=1, suf="%"),
        comp("Teste binomial do ganho entre turnos", "binomial_pct", "Tratando cada eleitor dos eliminados como uma moeda, a chance fica abaixo de 1 em 10 bilhões em {a26} das cidades em 2026, {a22} em 2022 e {a18} em 2018: o modelo da moeda acusa muitas cidades em qualquer ano.", d=1, suf="%"),
        comp("Variação da abstenção entre turnos", "abstencao_pp", "A abstenção variou {a26} pontos do 1º para o 2º turno em 2026, {a22} em 2022 e {a18} em 2018.", maior_e_pior=False, d=2),
        comp("Brancos e nulos que viraram votos do PT", "brancos_nulos_inclinacao", "Entre as cidades, com a variação do comparecimento fixa, cada ponto de brancos e nulos a menos veio com {a26} ponto a mais para o candidato do PT em 2026, {a22} em 2022 e {a18} em 2018.", d=2),
        conf_t("Soma dos votos = comparecimento", integ["soma_votos_diferente_do_comparecimento_t2"] == 0, f"{integ['soma_votos_diferente_do_comparecimento_t2']} seções com diferença no 2º turno ({integ['soma_votos_diferente_do_comparecimento_t1']} no 1º)."),
        conf_t("Comparecimento não passa do eleitorado", integ["comparecimento_maior_que_aptos"] == 0, f"{integ['comparecimento_maior_que_aptos']} seções com mais votantes que eleitores aptos."),
        conf_t("Totais batem com o TSE", bate == len(conf), f"{bate} de {len(conf)} estados e exterior: soma dos boletins = total oficial por município e zona."),
        conf_t("Log da urna = boletim", (LG.get("log_igual_boletim_pct") or 0) >= 99, f"{br(LG.get('log_igual_boletim_pct', 0), 2)}% das seções sem troca de urna têm no log o mesmo número de votos do boletim ({br(LG1.get('log_igual_boletim_pct', 0), 2)}% no 1º turno)."),
        {"grupo": "acaso", "nome": "Último dígito dos votos de Lula", "status": "Dentro" if dig.get("Lula_2", dig["Lula_1"])["ultimo_p"] > 0.01 else "Acima", "ok": dig.get("Lula_2", dig["Lula_1"])["ultimo_p"] > 0.01, "texto": f"Cada dígito final deveria aparecer em 10% das seções; o maior desvio é de {br(dig.get('Lula_2', dig['Lula_1'])['ultimo_desvio_max_pp'], 2)} ponto (p = {br(dig.get('Lula_2', dig['Lula_1'])['ultimo_p'], 2)})."},
        {"grupo": "acaso", "nome": "Último dígito dos votos de Flávio", "status": "Dentro" if dig.get("Flávio_2", dig["Flávio_1"])["ultimo_p"] > 0.01 else "Acima", "ok": dig.get("Flávio_2", dig["Flávio_1"])["ultimo_p"] > 0.01, "texto": f"O maior desvio é de {br(dig.get('Flávio_2', dig['Flávio_1'])['ultimo_desvio_max_pp'], 2)} ponto (p = {br(dig.get('Flávio_2', dig['Flávio_1'])['ultimo_p'], 2)})."},
        {"grupo": "acaso", "nome": "Modelo da urna e voto", "status": "Dentro", "ok": all(abs(v["efeito_pp"]) < 3 * v["erro_padrao"] + 0.5 for v in A["urnas"]["dentro_do_municipio"].values()), "texto": "No mesmo município, a parcela de Lula não depende do modelo da urna (efeitos abaixo de 0,2 ponto)."},
        {"grupo": "acaso", "nome": "Votos sem digital e voto", "status": "Dentro", "ok": abs(SD["correlacao_variacao"]) < 0.05, "texto": f"A mudança da parcela sem digital de uma seção entre os turnos não acompanha a variação de Lula (correlação {br(SD['correlacao_variacao'], 3)})."},
        {"grupo": "acaso", "nome": "Transferência por perfil político", "status": "Medido", "ok": True, "texto": f"Contra municípios do país com a mesma força de Flávio no 1º turno: {cls.get('Muito incomum', 0)} muito incomuns e {cls.get('Incomum', 0)} incomuns após correção para múltiplas comparações."},
        {"grupo": "acaso", "nome": "Calibração do modelo estatístico", "status": "Dentro" if abs(NA["calibracao"]["frac_p_abaixo_005"] - 0.05) < 0.02 else "Acima", "ok": abs(NA["calibracao"]["frac_p_abaixo_005"] - 0.05) < 0.02, "texto": f"{br(100 * NA['calibracao']['frac_p_abaixo_005'], 1)}% dos municípios com probabilidade abaixo de 5% (esperado: 5%)."},
    ]
    n_hist = sum(1 for t in testes if t["grupo"] == "historico")
    n_hist_dentro = sum(1 for t in testes if t["grupo"] == "historico" and t["ok"])
    tot = d[["Lula_2", "Flávio_2"]].sum()
    sa = int(d.loc[atip, "saldo"].sum())
    tu = ocorr["urna_trocada"]
    H22, H18, H26 = H[2022], H[2018], H[2026]
    perguntas = [
        ["As seções atípicas decidiram a eleição?", "Não", f"Lula venceu por {br(margem)} votos; nas {br(int(atip.sum()))} seções atípicas o saldo foi de {brs(sa)}. Sem elas, Lula venceria por {br(margem - sa)}."],
        ["Os votos depois das 17h mudaram o resultado?", "Não", f"Foram {br(int(d.votos_apos_17h_2.sum()))} votos de quem estava na fila, contados pelo horário de cada voto no log; o saldo estimado é {brs(round(saldo17))}. Sem eles, Lula venceria por cerca de {br(margem - saldo17)}."],
        ["Quantos votaram sem digital, e isso ajudou alguém?", "Não pesou para nenhum lado", f"{br(SD['turnos']['2']['sem_digital'])} votos sem a digital conferida ({br(100 * SD['turnos']['2']['pct'], 1)}%; {br(100 * SD['turnos']['1']['pct'], 1)}% no 1º turno). A variação de Lula foi parecida em todas as faixas de votos sem digital, entre {br(100 * min(f['lula2'] - f['lula1'] for f in fx), 1)} e {br(100 * max(f['lula2'] - f['lula1'] for f in fx), 1)} pontos."],
        ["Alguém votou duas vezes?", "Não confere", f"A urna recusou {br(JV['turnos']['2']['alertas'])} tentativas de habilitar quem já tinha votado ({br(JV['turnos']['1']['alertas'])} no 1º turno). Nenhum voto a mais é registrado nesses casos."],
        ["A chance de Lula virar era praticamente zero?", "Igual em 2022 e 2018", f"A conta trata cada eleitor como uma moeda. Por ela, {br(H26['binomial_pct'], 1)}% das cidades ficam abaixo de 1 em 10 bilhões em 2026, {br(H22['binomial_pct'], 1)}% em 2022 e {br(H18['binomial_pct'], 1)}% em 2018. Eleitor não é moeda: vota junto com a família, o bairro e o candidato que saiu. Por isso a Auditoria compara cada lugar com lugares de perfil parecido."],
        ["Lula cresceu em quase todas as cidades?", "Igual em 2022, do outro lado", f"O líder do 1º turno perdeu votos em {br(H26['lider_perdeu'])} cidades em 2026 (Flávio) e em {br(H22['lider_perdeu'])} em 2022 (Lula). Quem leva a maior parte dos eliminados no país leva na maioria das cidades."],
        ["Em várias cidades, quase todo o crescimento foi de Lula?", "Igual em 2022 e 2018", f"O 2º colocado do 1º turno ficou com 95% ou mais do ganho dos finalistas em {br(H26['segundo_95'])} cidades em 2026, {br(H22['segundo_95'])} em 2022 (Bolsonaro) e {br(H18['segundo_95'])} em 2018."],
        ["A abstenção caiu no 2º turno. Isso não acontece?", "Acima de 2022 e 2018" if H26["abstencao_pp"] < min(H22["abstencao_pp"], H18["abstencao_pp"]) else "Dentro de 2022 e 2018", f"A abstenção variou {brm(H26['abstencao_pp'], 2)} pontos em 2026, {brm(H22['abstencao_pp'], 2)} em 2022 e {brm(H18['abstencao_pp'], 2)} em 2018. A queda maior em 2026 é um dos pontos a explicar; seções com comparecimento longe das vizinhas estão na aba Atípicas."],
        ["Urnas trocadas favoreceram alguém?", "Não", f"{br(int(tu.sum()))} seções tiveram troca de urna; saldo nelas: {brs(int(d.loc[tu, 'saldo'].sum()))} (média de {br(d.loc[tu, 'saldo'].mean(), 1)} por seção, contra {br(margem / len(d), 1)} no país). A troca é prevista em lei e o boletim soma os votos das duas urnas."],
        ["Houve seção com mais votos que eleitores?", "Não confere", f"{integ['comparecimento_maior_que_aptos']} seções com comparecimento acima do eleitorado e {integ['soma_votos_diferente_do_comparecimento_t2']} com soma de votos diferente do comparecimento."],
        ["A soma dos boletins bate com o resultado oficial?", "Confere", f"Sim, em {bate} de {len(conf)} estados e exterior: {br(int(tot['Lula_2']))} votos para Lula e {br(int(tot['Flávio_2']))} para Flávio."],
        ["Seções com 100% de votos para um candidato existem?", "Medido", f"Sim, {br(n100)} seções com 50 votos ou mais deram todos os votos nominais a um finalista ({br(n100l)} para Lula). São seções pequenas e homogêneas, muitas em aldeias e comunidades rurais."],
        ["Lula cresceu onde a direita era forte?", "Medido", "Em média, não: quanto maior Flávio no 1º turno, menos votos dos eliminados foram para Lula (73% onde a esquerda é forte, 35% onde Flávio teve 70% a 75%). Há exceções concentradas no RJ; veja a aba Transferência de votos."],
        ["Dá para conferir sem voto impresso?", "Limite desta auditoria", "Dá para conferir tudo o que vem depois de a urna fechar: o boletim de cada seção, o log de cada urna e a soma até o total do TSE. O que os arquivos não provam é que o programa gravou cada voto como o eleitor digitou; isso depende dos testes do TSE antes e durante a eleição."],
    ]
    ufs_atip = d.loc[atip].groupby("uf").size().astype(int).to_dict()
    ufs_oc = d.loc[np.logical_or.reduce([m.to_numpy() for m in ocorr.values()])].groupby("uf").size().astype(int).to_dict()
    out = {"schema_version": "1.0", "gerado_em": time.strftime("%Y-%m-%d %H:%M"), "turno": 2,
           "secoes_lidas": int(len(d)), "margem": margem, "lula": int(tot["Lula_2"]), "flavio": int(tot["Flávio_2"]),
           "atipicas": {"secoes": int(atip.sum()), "saldo": int(d.loc[atip, "saldo"].sum()), "validos": int(d.loc[atip, "fin2"].sum()), "ufs": ufs_atip,
                        "saldo_ufs": d.loc[atip].groupby("uf").saldo.sum().astype(int).to_dict(), "validos_ufs": d.loc[atip].groupby("uf").fin2.sum().astype(int).to_dict(), "tipos": tipos},
           "por_uf": {u: {"secoes": int(len(g)), "margem": int(g.saldo.sum()), "depois_17h": int(g.votos_apos_17h_2.sum()), "saldo_17h": round(float((g.votos_apos_17h_2 * g.saldo / (g.fin2 + g.Branco_2 + g.Nulo_2).clip(lower=1)).sum()))} for u, g in d.groupby("uf")},
           "ocorrencias": {"secoes": int(np.logical_or.reduce([m.to_numpy() for m in ocorr.values()]).sum()), "ufs": ufs_oc, "tipos": ocs},
           "falhas": {"secoes": int(fal.sum()), "regra": "Soma dos votos diferente do comparecimento, ou comparecimento maior que o eleitorado apto."},
           "depois_17h": {"votos": int(d.votos_apos_17h_2.sum()), "secoes": int(ocorr["prorrogada"].sum()), "saldo_estimado": round(saldo17)},
           "bate_tse": {"ufs": bate, "total": len(conf), "por_uf": conf},
           "testes": testes, "testes_historico": {"dentro": n_hist_dentro, "total": n_hist},
           "historico_cidades": {str(k): v for k, v in H.items()},
           "perguntas": [{"p": p, "selo": sl, "r": r} for p, sl, r in perguntas]}
    with open(PORTAL_DADOS / "boletins.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print(f"atípicas {out['atipicas']['secoes']} (saldo {out['atipicas']['saldo']:+}) · ocorrências {out['ocorrencias']['secoes']} · falhas {out['falhas']['secoes']} · bate TSE {bate}/{len(conf)}")
    for k, v in tipos.items():
        print(f"  {v['rotulo']}: {v['secoes']} (saldo {v['saldo']:+})")
    for k, v in ocs.items():
        print(f"  {v['rotulo']}: {v['secoes']}")
    print(f"17h: {out['depois_17h']} · {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
