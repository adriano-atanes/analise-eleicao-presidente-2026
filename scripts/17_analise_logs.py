"""Análise dos logs das urnas (resultado de 16_logs_urnas.py) nos dois turnos.

Responde, por turno, estado e seção:
  - troca de urna (contingência): quantas, onde, em que horário, antes ou durante a votação
  - abertura e encerramento: urna pronta às 8h (horário de Brasília), atrasos, encerramento antes das 17h,
    votos depois das 17h (eleitores na fila)
  - zerésima emitida antes da abertura
  - habilitação dos eleitores por biometria ou manual
  - erros (separando a mensagem de rotina "Problema ao desmontar a MR"), alertas, votos não registrados
  - reinícios da urna durante a votação e tempo de votação por eleitor
  - conferência: votos registrados no log × comparecimento do boletim de urna
  - cruzamentos: ocorrências nas seções atípicas × nas demais; associação com a variação do voto

Saídas: portal/dados/logs.json (resumos) e portal/dados/logs_secoes/<UF>.json (uma linha por seção,
usada no boletim da seção no portal).
"""
import collections
import glob
import json

import numpy as np
import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS, UF_NOME

LOGS = PROCESSADOS / "logs"
FUSO = {"AC": -2, "AM": -1, "RR": -1, "RO": -1, "MT": -1, "MS": -1}


def minutos(col):
    t = col.fillna("").str.split(":", expand=True)
    if t.shape[1] < 2:
        return pd.Series(np.nan, index=col.index)
    return pd.to_numeric(t[0], errors="coerce") * 60 + pd.to_numeric(t[1], errors="coerce")


def carregar():
    partes = [pd.read_parquet(f) for f in sorted(glob.glob(str(LOGS / "*.parquet")))]
    d = pd.concat([p for p in partes if "erros_rotina" in p], ignore_index=True)  # ignora resultados de versão anterior do 16
    for c in ("sem_eventos_no_dia", "erro_leitura"):
        if c not in d:
            d[c] = np.nan
    d["fuso"] = d.uf.map(FUSO).fillna(0)
    # AM (oeste com fuso do Acre) e PE (Fernando de Noronha) têm mais de um fuso: infere por município pela
    # hora típica em que as urnas ficaram prontas (8h de Brasília no horário local)
    multi = d.uf.isin(["AM", "PE"])
    pronta = minutos(d.t_pronta)
    hora_tipica = pronta[multi].groupby([d.uf[multi], d.mun[multi], d.turno[multi]]).transform("median")
    d.loc[multi, "fuso"] = ((hora_tipica - 480) / 60).round().clip(-2, 1)
    d["abertura_min"] = minutos(d.t_pronta) - (8 + d.fuso) * 60
    d["encerr_min"] = minutos(d.t_encerramento) - (17 + d.fuso) * 60
    d["ultimo_min"] = minutos(d.t_ultimo_voto) - (17 + d.fuso) * 60
    d["cont_min"] = minutos(d.t_contingencia) - (8 + d.fuso) * 60
    d["zeresima_ok"] = d.t_zeresima.notna() & (d.t_zeresima <= d.t_pronta)
    d["hab_manual"] = (d.votos_log - d.hab_biometrica).clip(lower=0)
    d["erros_relevantes"] = (d.erros - d.erros_rotina).clip(lower=0)
    d.loc[d.uf == "ZZ", ["abertura_min", "encerr_min", "ultimo_min", "cont_min"]] = np.nan  # exterior: fusos variados
    return d


def resumo_turno(g, s_t):
    n = len(g)
    v = g.votos_log.sum()
    cont = g[g.contingencia.fillna(False)]
    m = g.merge(s_t, on=["uf", "mun", "zona", "secao"], how="left")
    sem_cont = m[~m.contingencia.fillna(False)]
    return {
        "secoes_com_log": int(n), "votos_no_log": int(v),
        "contingencia": int(len(cont)), "contingencia_pct": float(100 * len(cont) / n),
        "contingencia_antes_abertura": int((cont.cont_min < 0).sum()), "contingencia_durante": int((cont.cont_min >= 0).sum()),
        "contingencia_hora": np.histogram(cont.cont_min.dropna() / 60 + 8, bins=np.arange(0, 25, 1))[0].tolist(),
        "abertura_no_horario_pct": float(100 * (g.abertura_min.between(-1, 5)).sum() / g.abertura_min.notna().sum()),
        "abertura_atraso_15": int((g.abertura_min > 15).sum()), "abertura_atraso_60": int((g.abertura_min > 60).sum()),
        "abertura_antes_8h": int((g.abertura_min < -1).sum()),
        "hist_abertura": np.histogram(g.abertura_min.dropna().clip(-30, 179), bins=np.arange(-30, 181, 5))[0].tolist(),
        "encerramento_antes_17h": int((g.encerr_min < 0).sum()),
        "hist_encerramento": np.histogram(g.encerr_min.dropna().clip(-30, 239), bins=np.arange(-30, 241, 5))[0].tolist(),
        "secoes_votos_apos_17h": int((g.votos_apos_17h > 0).sum()), "votos_apos_17h": int(g.votos_apos_17h.sum()),
        "ultimo_voto_p50": float(g.ultimo_min.median()), "ultimo_voto_p99": float(g.ultimo_min.quantile(0.99)),
        "zeresima_ok_pct": float(100 * g.zeresima_ok.mean()), "zeresima_problema": int((~g.zeresima_ok).sum()),
        "hab_biometrica_pct": float(100 * g.hab_biometrica.sum() / v), "hab_manual_pct": float(100 * g.hab_manual.sum() / v),
        "erros_rotina": int(g.erros_rotina.sum()), "erros_relevantes": int(g.erros_relevantes.sum()),
        "secoes_erros_relevantes": int((g.erros_relevantes > 0).sum()), "alertas": int(g.alertas.sum()),
        "voto_nao_registrado": int(g.voto_nao_registrado.sum()), "secoes_voto_nao_registrado": int((g.voto_nao_registrado > 0).sum()),
        "secoes_reiniciadas": int((g.ligadas_apos_pronta > 0).sum()), "reinicios": int(g.ligadas_apos_pronta.sum()),
        "bateria": int((g.bateria > 0).sum()),
        "tempo_votacao_mediano_s": float(g.tempo_mediano_s.median()),
        "log_igual_boletim_pct": float(100 * (sem_cont.votos_log == sem_cont.comp).mean()) if len(sem_cont) else None,
        "log_diferente_boletim": int((sem_cont.votos_log != sem_cont.comp).sum()) if len(sem_cont) else None,
        "modelos": g.modelo.value_counts().to_dict(),
    }


def insights_v3(g, votos_hora):
    """Recortes da extração ampliada (16_logs_urnas.py com catálogo de mensagens)."""
    if "mesario_max_hab" not in g:
        return None
    v = g.votos_log.sum()
    imp = collections.Counter()
    for t in g.impedidos_tipos.dropna():
        imp.update(json.loads(t))
    share_mes = g.mesario_max_hab / g.votos_log.clip(lower=1)
    n = len(g)
    top = g.assign(share=share_mes).nlargest(30, "share")
    return {
        "secoes": int(n),
        "votos_hora": votos_hora,
        "id_cpf_pct": float(100 * g.id_cpf.sum() / max(g.id_cpf.sum() + g.id_titulo.sum(), 1)),
        "biometria_4a_tentativa_por_mil": float(1000 * g.biometria_4a_tentativa.sum() / v),
        "biometria_nao_confere": int(g.biometria_nao_confere.sum()),
        "ano_nasc_confere": int(g.ano_nasc_confere.sum()), "ano_nasc_diferente": int(g.ano_nasc_diferente.sum()),
        "hab_mesario_total": int(g.hab_por_mesario.sum()),
        "mesario_share_hist": np.histogram(share_mes.clip(0, 0.999), bins=np.arange(0, 1.01, 0.05))[0].tolist(),
        "secoes_mesario_30pct": int((share_mes >= 0.3).sum()), "secoes_mesario_50pct": int((share_mes >= 0.5).sum()),
        "mesario_top": [[r.uf, int(r.mun), int(r.zona), int(r.secao), int(r.mesario_max_hab), int(r.votos_log), int(r.mesarios_que_habilitaram)] for r in top.itertuples()],
        "eleitor_ja_votou": int(g.eleitor_ja_votou.sum()), "secoes_ja_votou": int((g.eleitor_ja_votou > 0).sum()),
        "eleitor_nao_encontrado": int(g.eleitor_nao_encontrado.sum()),
        "impedidos": dict(imp.most_common()),
        "correcoes_por_mil": float(1000 * g.correcoes.sum() / v), "suspenso_sem_votar": int(g.suspenso_sem_votar.sum()),
        "sem_atividade": int(g.sem_atividade.sum()),
        "justificativas": int(g.justificativas.sum()), "audio_cadastro": int(g.audio_cadastro.sum()),
        "secoes_bateria": int((g.bateria > 0).sum()), "bateria_min_total": float(g.bateria_min.sum()),
        "bateria_min_p95": float(g.bateria_min[g.bateria > 0].quantile(0.95)) if (g.bateria > 0).any() else 0.0,
        "secoes_bateria_critica": int((g.bateria_critica > 0).sum()),
        "secoes_encerr_cedo_tentativa": int((g.encerr_cedo_tentativa > 0).sum()), "secoes_encerr_abortado": int((g.encerr_abortado > 0).sum()),
        "secoes_encerr_com_presentes": int((g.encerr_com_presentes > 0).sum()),
        "secoes_impressora": int((g.impressora_falha > 0).sum()), "secoes_leitor_biometrico": int((g.leitor_biometrico_erro > 0).sum()),
        "secoes_log_me_corrompido": int((g.log_me_corrompido > 0).sum()),
        "mesarios_registrados_media": float(g.mesarios_registrados.mean()),
    }


def cruzamentos(d, s, aud):
    """Ocorrências nas seções atípicas × demais; associação das ocorrências com a variação do voto (2º turno)."""
    col = {k: i for i, k in enumerate(aud["suspeitas"]["colunas"])}
    atip = {(l[col["uf"]], l[col["mun"]], l[col["zona"]], l[col["secao"]]) for l in aud["suspeitas"]["linhas"]}
    g2 = d[d.turno == 2].copy()
    g2["atipica"] = [(u, m, z, sc) in atip for u, m, z, sc in zip(g2.uf, g2.mun, g2.zona, g2.secao)]
    taxa = lambda x: {"secoes": int(len(x)), "contingencia_pct": float(100 * x.contingencia.fillna(False).mean()),
                      "erros_relevantes_pct": float(100 * (x.erros_relevantes > 0).mean()), "reinicio_pct": float(100 * (x.ligadas_apos_pronta > 0).mean()),
                      "hab_manual_pct": float(100 * x.hab_manual.sum() / max(x.votos_log.sum(), 1)),
                      "voto_nao_registrado_pct": float(100 * (x.voto_nao_registrado > 0).mean())}
    out = {"atipicas": taxa(g2[g2.atipica]), "demais": taxa(g2[~g2.atipica])}
    # variação de Lula entre os finalistas na seção, dentro do município, conforme as ocorrências do log
    m = g2.merge(s, on=["uf", "mun", "zona", "secao"])
    m = m[(m.Lula_1 + m["Flávio_1"] > 0) & (m.Lula_2 + m["Flávio_2"] > 0)]
    m["dl"] = 100 * (m.Lula_2 / (m.Lula_2 + m["Flávio_2"]) - m.Lula_1 / (m.Lula_1 + m["Flávio_1"]))
    m["manual_pct"] = 100 * m.hab_manual / m.votos_log.clip(lower=1)
    l1 = d[d.turno == 1][["uf", "mun", "zona", "secao", "hab_manual", "votos_log"]].rename(columns={"hab_manual": "man1", "votos_log": "v1"})
    m = m.merge(l1, on=["uf", "mun", "zona", "secao"], how="left")
    m["dmanual"] = m.manual_pct - 100 * m.man1 / m.v1.clip(lower=1)
    m["dcomp"] = 100 * (m.Comp_2 / m.Aptos_2.clip(lower=1) - m.Comp_1 / m.Aptos_1.clip(lower=1))
    X = pd.DataFrame({"contingencia": m.contingencia.fillna(False).astype(float), "reinicio": (m.ligadas_apos_pronta > 0).astype(float),
                      "erro_relevante": (m.erros_relevantes > 0).astype(float), "dmanual_10pp": m.dmanual.fillna(0) / 10})
    if "mesario_max_hab" in m:
        X["mesario_30pct"] = (m.mesario_max_hab / m.votos_log.clip(lower=1) >= 0.3).astype(float)
        X["ja_votou"] = (m.eleitor_ja_votou > 0).astype(float)
        X["bateria"] = (m.bateria > 0).astype(float)
    chave = m.uf + "-" + m.mun.astype(str)
    yd = m.dl - m.dl.groupby(chave).transform("mean")
    Xd = X - X.groupby(chave).transform("mean")
    beta, *_ = np.linalg.lstsq(Xd.to_numpy(), yd.to_numpy(), rcond=None)
    res = yd.to_numpy() - Xd.to_numpy() @ beta
    sigma2 = (res ** 2).sum() / (len(res) - X.shape[1])
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(Xd.T.to_numpy() @ Xd.to_numpy())))
    out["efeito_na_variacao_lula"] = {k: {"efeito_pp": float(b), "erro_padrao": float(e)} for k, b, e in zip(X.columns, beta, se)}
    out["variacao_lula_media_pp"] = float(m.dl.mean())
    # habilitação manual × aumento do comparecimento, dentro do município
    a = m.dmanual - m.dmanual.groupby(chave).transform("mean")
    b = m.dcomp - m.dcomp.groupby(chave).transform("mean")
    ok = a.notna() & b.notna()
    out["corr_dmanual_dcomp"] = float(np.corrcoef(a[ok], b[ok])[0, 1])
    return out


def limpar(o):
    """Troca NaN por None e tipos do numpy por tipos do Python, para gravar JSON válido."""
    if isinstance(o, dict):
        return {k: limpar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpar(v) for v in o]
    if hasattr(o, "item"):
        o = o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def main():
    d = carregar()
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet").rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "mun", "NR_ZONA": "zona", "NR_SECAO": "secao"})
    aud = json.load(open(PORTAL_DADOS / "auditoria.json"))
    mensagens = {"1": {}, "2": {}}
    for f in glob.glob(str(LOGS / "*.json")):
        t, uf = f.rsplit("/", 1)[1][:-5].split("_")
        if uf not in set(d.uf):
            continue
        for nivel, msg, n in json.load(open(f))["mensagens"]:
            k = (nivel, msg)
            mensagens[t].setdefault(k, [0, 0])
            mensagens[t][k][0] += n
            mensagens[t][k][1] += 1
    saida = {"ufs_processadas": sorted(d.uf.unique().tolist()), "turnos": {}, "por_uf": {}, "mensagens": {}}
    for t in (1, 2):
        g = d[d.turno == t]
        s_t = s[["uf", "mun", "zona", "secao", f"Comp_{t}"]].rename(columns={f"Comp_{t}": "comp"})
        saida["turnos"][str(t)] = resumo_turno(g, s_t)
        saida["mensagens"][str(t)] = [[k[0], k[1], v[0], v[1]] for k, v in sorted(mensagens[str(t)].items(), key=lambda x: -x[1][0])[:80]]
        for uf, gu in g.groupby("uf"):
            r = resumo_turno(gu, s_t)
            saida["por_uf"].setdefault(uf, {"nome": UF_NOME.get(uf, uf)})[str(t)] = {k: r[k] for k in (
                "secoes_com_log", "contingencia", "contingencia_pct", "abertura_no_horario_pct", "abertura_atraso_15", "encerramento_antes_17h",
                "secoes_votos_apos_17h", "hab_biometrica_pct", "secoes_erros_relevantes", "voto_nao_registrado", "secoes_reiniciadas",
                "tempo_votacao_mediano_s", "log_igual_boletim_pct")}
    saida["cruzamentos"] = cruzamentos(d, s, aud)
    # extração ampliada: só com os estados já reprocessados na versão nova
    saida["ampliada"] = {}
    for t in (1, 2):
        g = d[(d.turno == t)]
        if "mesario_max_hab" in g:
            g = g[g.mesario_max_hab.notna()]
        vh = [0] * 24
        for f in glob.glob(str(LOGS / f"{t}_*.json")):
            j = json.load(open(f))
            if "votos_hora" in j:
                vh = [a + b for a, b in zip(vh, j["votos_hora"])]
        r = insights_v3(g, vh) if len(g) else None
        if r:
            r["ufs"] = sorted(g.uf.unique().tolist())
            saida["ampliada"][str(t)] = r
    # listas para conferência: contingências durante a votação, votos não registrados, erros relevantes, encerramento antes das 17h
    lista = d[(d.contingencia.fillna(False)) | (d.voto_nao_registrado > 0) | (d.erros_relevantes >= 3) | (d.encerr_min < 0) | (d.ligadas_apos_pronta >= 2)]
    nomes = s.drop_duplicates(["uf", "mun"]).set_index(["uf", "mun"]).NM_MUNICIPIO
    saida["ocorrencias"] = {"colunas": ["turno", "uf", "mun", "nome", "zona", "secao", "contingencia", "t_contingencia", "voto_nao_registrado", "erros_relevantes",
                                        "reinicios", "t_pronta", "t_encerramento", "votos_log", "modelo"],
                            "linhas": [[int(r.turno), r.uf, int(r.mun), str(nomes.get((r.uf, r.mun), "")).title(), int(r.zona), int(r.secao), bool(r.contingencia),
                                        r.t_contingencia, int(r.voto_nao_registrado), int(r.erros_relevantes), int(r.ligadas_apos_pronta), r.t_pronta,
                                        r.t_encerramento, int(r.votos_log), r.modelo] for r in lista.itertuples()]}
    with open(PORTAL_DADOS / "logs.json", "w") as f:
        json.dump(limpar(saida), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # por município e turno, para o mapa da página Logs da urna
    g = d.assign(cont=d.contingencia.fillna(False).astype(int), err=(d.erros_relevantes > 0).astype(int), rein=(d.ligadas_apos_pronta > 0).astype(int),
                 fila=(d.votos_apos_17h > 0).astype(int), atraso=(d.abertura_min > 15).astype(int))
    mun = g.groupby(["uf", "mun", "turno"]).agg(secoes=("secao", "size"), cont=("cont", "sum"), err=("err", "sum"), rein=("rein", "sum"), fila=("fila", "sum"),
                                                 atraso=("atraso", "sum"), bio=("hab_biometrica", "sum"), votos=("votos_log", "sum"),
                                                 tempo=("tempo_mediano_s", "median"), nreg=("voto_nao_registrado", "sum"))
    mun["bio_pct"] = 100 * mun.bio / mun.votos.clip(lower=1)
    for c in ("cont", "err", "rein", "fila", "atraso"):
        mun[c + "_pct"] = 100 * mun[c] / mun.secoes
    cols_m = ["secoes", "cont", "cont_pct", "err_pct", "rein_pct", "fila_pct", "atraso_pct", "bio_pct", "tempo", "nreg"]
    lm = {}
    for (uf, m, t), r in mun[cols_m].iterrows():
        lm.setdefault(f"{uf}-{m}", {})[str(t)] = [None if pd.isna(v) else round(float(v), 2) for v in r]
    with open(PORTAL_DADOS / "logs_municipios.json", "w") as f:
        json.dump({"colunas": cols_m, "municipios": lm}, f, separators=(",", ":"), allow_nan=False)

    # por seção, para o boletim no portal
    (PORTAL_DADOS / "logs_secoes").mkdir(parents=True, exist_ok=True)
    campos = ["turno", "mun", "zona", "secao", "urnas", "modelo", "t_zeresima", "t_pronta", "t_primeiro_voto", "t_ultimo_voto", "t_encerramento",
              "votos_log", "hab_biometrica", "hab_manual", "contingencia", "t_contingencia", "erros_relevantes", "alertas", "voto_nao_registrado",
              "ligadas_apos_pronta", "votos_apos_17h", "tempo_mediano_s"]
    campos += [c for c in ("id_cpf", "ano_nasc_confere", "ano_nasc_diferente", "hab_por_mesario", "mesario_max_hab", "mesarios_que_habilitaram", "eleitor_ja_votou",
                           "eleitor_impedido", "correcoes", "justificativas", "bateria_min", "encerr_cedo_tentativa", "encerr_com_presentes") if c in d]
    for uf, g in d.groupby("uf"):
        linhas = g[campos].astype(object).where(g[campos].notna(), None).values.tolist()
        with open(PORTAL_DADOS / "logs_secoes" / f"{uf}.json", "w") as f:
            json.dump({"colunas": campos, "linhas": limpar(linhas)}, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for t in ("1", "2"):
        r = saida["turnos"][t]
        print(f"turno {t}:", {k: r[k] for k in ("secoes_com_log", "contingencia", "contingencia_durante", "abertura_no_horario_pct", "abertura_atraso_15",
                                               "encerramento_antes_17h", "secoes_votos_apos_17h", "zeresima_problema", "hab_biometrica_pct", "secoes_erros_relevantes",
                                               "voto_nao_registrado", "secoes_reiniciadas", "tempo_votacao_mediano_s", "log_igual_boletim_pct")})
    print(json.dumps(saida["cruzamentos"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
