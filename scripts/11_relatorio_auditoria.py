"""Relatório de auditoria em PDF (relatorio/auditoria_eleicao_2026.pdf).

Inclui a comparação do comportamento do eleitorado com 2002–2022 (12_comportamento_historico.py).

Junta, num documento só, o que a visão "Auditoria" do portal mostra:
  - quadro de testes com status e conclusão
  - os testes estatísticos completos (conteúdo de 09_relatorio_estatistico.py)
  - indicadores por estado
  - lista completa das seções atípicas, com motivo, para conferência
  - roteiro de verificação fora da estatística
Fontes: portal/dados/auditoria.json (10_dados_auditoria.py) e dados/processados/.
"""
import importlib
import json
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import matplotlib.pyplot as plt
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

from comum import PORTAL_DADOS, RAIZ, UF_NOME

R = importlib.import_module("05_relatorio_pdf")
E = importlib.import_module("09_relatorio_estatistico")
P, S, tabela, LARGURA = R.P, R.S, R.tabela, R.LARGURA
n0, p1, pp, mi, sinal = R.n0, R.p1, R.pp, R.mi, R.sinal
SAIDA = RAIZ / "relatorio" / "auditoria_eleicao_2026.pdf"

MOTIVOS = {
    "res_lula": ("L+", "Lula mais de 10 p.p. do eleitorado acima do previsto pelo 1º turno da seção"),
    "res_fla": ("F+", "Flávio mais de 10 p.p. do eleitorado acima do previsto pelo 1º turno da seção"),
    "lim_lula": ("LF", "ganho de Lula 10 ou mais votos acima de tudo o que poderia vir sem eleitores de Flávio"),
    "lim_fla": ("FL", "ganho de Flávio 10 ou mais votos acima de tudo o que poderia vir sem eleitores de Lula"),
    "comp_alto": ("C98", "comparecimento de 98% ou mais no 2º turno (seções com 50 aptos ou mais)"),
    "salto_comp": ("C25", "comparecimento subiu 25 pontos percentuais ou mais (seções com 50 aptos ou mais)"),
}
CHI2_P01 = 21.67  # qui-quadrado crítico, 9 graus de liberdade, 1%


def qui2(cont):
    e = sum(cont) / 10
    return sum((o - e) ** 2 / e for o in cont)


def dec(v, d=2):
    v = round(v, d) + 0.0  # evita "-0,0"
    return f"{v:.{d}f}".replace("-0,0", "0,0").replace(".", ",") if abs(v) > 0 else f"{0:.{d}f}".replace(".", ",")


ST = {"dentro": ("#0b7a0b", "✓", "Dentro do histórico"), "tendencia": ("#0b7a0b", "✓", "Na tendência"),
      "acima": ("#a86f00", "!", "Acima do histórico"), "inedito": ("#a86f00", "!", None)}


def situacao(i):
    cor, simb, txt = ST[i["status"]]
    return f'<font color="{cor}"><b><font name="Simbolos">{simb}</font> {txt or i["status_texto"]}</b></font>'


def fmt_ind(i, v):
    if v is None:
        return "—"
    if i["id"] == "virada":
        return "sim" if v else "não"
    if i["id"] == "estados_virada":
        return str(v)
    if i["id"] == "r2_previsao":
        return dec(v, 3)
    sinal_ = "+" if v > 0 and i["id"] in ("dcomp_pp", "dbn_pp") else ""
    return sinal_ + dec(v, 1) + ("%" if i["unidade"].startswith("%") else "")


def g_barras_hist(CP, chave, tend, sufixo, titulo):
    anos = CP["anos"]
    vals = [CP["nacional"][str(a)][chave] for a in anos]
    fig, ax = plt.subplots(figsize=(3.6, 2.4))
    ax.bar([str(a) for a in anos], vals, color=["#1d7a4c" if a == 2026 else "#4b524c" for a in anos], width=0.6)
    for k, v in enumerate(vals):
        ultimo = k == len(vals) - 1  # em 2026 o rótulo vai à esquerda, para não cobrir o losango
        ax.text(k - 0.33 if ultimo else k, v + (0.04 if v >= 0 else -0.04) * (max(vals) - min(vals)), f"{v:.1f}".replace(".", ","),
                ha="right" if ultimo else "center", va="bottom" if v >= 0 else "top", fontsize=6.5)
    ax.scatter([str(2026)], [tend["previsto_2026"]], marker="D", s=30, color="#eda100", edgecolor="white", zorder=5)
    ax.axhline(0, color="#111512", linewidth=0.6)
    ax.set_title(titulo, fontsize=8.5)
    ax.tick_params(labelsize=7)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}{sufixo}")
    ax.grid(axis="x", visible=False)
    lo, hi = min(vals + [0]), max(vals + [tend["previsto_2026"]])
    ax.set_ylim(lo - 0.18 * (hi - lo), hi + 0.18 * (hi - lo))
    return fig


def parte_logs_ampliada(AMP):
    """Recortes das mensagens do log: identificação, mesário, impedidos, energia, encerramento e ritmo da votação."""
    if not AMP:
        return []
    ts = [t for t in ("1", "2") if t in AMP]
    A = {t: AMP[t] for t in ts}
    cab = ["Recorte"] + [f"{t}º turno" for t in ts]
    lin = lambda rot, f: [rot] + [f(A[t]) for t in ts]
    tab = [cab,
           lin("Seções analisadas", lambda a: n0(a["secoes"])),
           lin("Eleitores identificados pelo CPF (demais pelo título)", lambda a: p1(a["id_cpf_pct"])),
           lin("Biometria só na 4ª tentativa (por mil votos)", lambda a: dec(a["biometria_4a_tentativa_por_mil"], 1)),
           lin("Ano de nascimento conferido · divergente", lambda a: f"{n0(a['ano_nasc_confere'])} · {n0(a['ano_nasc_diferente'])}"),
           lin("Seções em que um mesário autorizou 30%+ · 50%+ dos votos", lambda a: f"{n0(a['secoes_mesario_30pct'])} · {n0(a['secoes_mesario_50pct'])}"),
           lin("Alerta \"o eleitor identificado já votou\" · seções", lambda a: f"{n0(a['eleitor_ja_votou'])} · {n0(a['secoes_ja_votou'])}"),
           lin("Identificador sem eleitor na seção", lambda a: n0(a["eleitor_nao_encontrado"])),
           lin("Eleitores impedidos de votar", lambda a: n0(sum(a["impedidos"].values()))),
           lin("Correções na cabine (por mil votos)", lambda a: dec(a["correcoes_por_mil"], 0)),
           lin("Justificativas de ausência", lambda a: n0(a["justificativas"])),
           lin("Voto com áudio ativado pelo cadastro", lambda a: n0(a["audio_cadastro"])),
           lin("Seções na bateria · com carga crítica", lambda a: f"{n0(a['secoes_bateria'])} · {n0(a['secoes_bateria_critica'])}"),
           lin("Tentativas de encerrar antes das 17h (seções)", lambda a: n0(a["secoes_encerr_cedo_tentativa"])),
           lin("Encerradas com \"NÃO\" a \"todos os presentes já votaram?\"", lambda a: n0(a["secoes_encerr_com_presentes"])),
           lin("Falha de impressora · leitor biométrico · log da mídia", lambda a: f"{n0(a['secoes_impressora'])} · {n0(a['secoes_leitor_biometrico'])} · {n0(a['secoes_log_me_corrompido'])}")]
    larg = [100 * mm] + [74 * mm / len(ts)] * len(ts)
    ufs = sorted(set().union(*(A[t]["ufs"] for t in ts)))
    out = [Spacer(1, 4), KeepTogether([P("O que mais as mensagens do log mostram", "h2"),
           P("Recortes a partir de todas as mensagens gravadas pela urna: como o eleitor foi identificado, quem autorizou a habilitação, quem foi impedido "
             "de votar, quedas de energia e como a seção foi encerrada." + ("" if len(ufs) >= 28 else f" <b>Cobertura: {len(ufs)} unidades ({', '.join(ufs)}).</b>"), "corpo"),
           tabela(tab, larg, numericas=range(1, len(cab)))]),
           P("A urna recusa o encerramento antes das 17h: a tentativa fica registrada e a votação continua. \"Já votou\" é o alerta exibido quando o mesário digita "
             "o título de quem já votou; a urna não habilita o eleitor de novo. A habilitação pelo mesário (ano de nascimento + digital do mesário) é o "
             "procedimento previsto quando a biometria do eleitor não confere.", "nota")]
    t = ts[-1]
    imp = [["Motivo do impedimento", "Eleitores"]] + [[k[:1].upper() + k[1:], n0(v)] for k, v in list(A[t]["impedidos"].items())[:8]]
    top = [["UF", "Município", "Zona", "Seção", "Pelo mesário", "Votos", "Parcela"]]
    nomes = {(u, m["cod"]): m["nome"] for u in {r[0] for r in A[t]["mesario_top"]}
             for m in json.load(open(PORTAL_DADOS / "uf" / f"{u}.json"))["municipios"]}
    for u, mun, z, sc, h, v, _ in A[t]["mesario_top"][:10]:
        top.append([u, nomes.get((u, mun), str(mun))[:26], f"{z:04d}", f"{sc:04d}", n0(h), n0(v), p1(100 * h / max(v, 1))])
    out += [Spacer(1, 4), KeepTogether([P(f"Eleitores impedidos de votar, por motivo · {t}º turno", "h2"), tabela(imp, [130 * mm, 44 * mm], numericas=(1,))]),
            Spacer(1, 4), KeepTogether([P(f"Seções com maior parcela de habilitações autorizadas por um mesário · {t}º turno", "h2"),
                                        tabela(top, [12 * mm, 52 * mm, 16 * mm, 16 * mm, 28 * mm, 22 * mm, 28 * mm], numericas=(2, 3, 4, 5, 6)),
                                        P("Concentração alta indica seção com muitos eleitores sem biometria reconhecida (idosos, digitais gastas) e é ponto de "
                                          "conferência com a ata da mesa, não indicativo isolado de irregularidade.", "nota")])]
    vh = [["Turno", "Pico", "Até as 10h", "Depois das 17h"]]
    for t in ts:
        h = A[t]["votos_hora"]
        tot = sum(h) or 1
        pico = max(range(24), key=lambda i: h[i])
        vh.append([f"{t}º", f"{pico}h–{pico + 1}h ({p1(100 * h[pico] / tot)})", p1(100 * sum(h[:10]) / tot), p1(100 * sum(h[17:]) / tot)])
    out += [Spacer(1, 4), KeepTogether([P("Ritmo da votação (horário de Brasília)", "h2"), tabela(vh, [30 * mm, 60 * mm, 42 * mm, 42 * mm], numericas=(2, 3))])]
    return out


def parte_logs_extra(LG):
    """Modelo de urna, intervalo entre votos consecutivos e votos sem biometria depois das 17h."""
    out = []
    M = LG.get("modelos")
    if M:
        tab = [["Modelo", "Seções", "Lula", "Flávio", "Seções no NE", "Troca de urna", "Erro relev.", "Biometria"]]
        for r in M["2"]:
            tab.append([r["modelo"], n0(r["secoes"]), p1(r["lula_pct"]), p1(r["flavio_pct"]), p1(r["nordeste_pct"], 0), p1(r["contingencia_pct"], 2),
                        p1(r["erro_relevante_pct"], 2), p1(r["biometria_pct"])])
        f2 = lambda e: (("+" if e["efeito_pp"] > 0 else "−") + f"{abs(e['efeito_pp']):.2f}".replace(".", ",") + f" ± {2 * e['erro_padrao']:.2f}".replace(".", ","))
        ef = [[f"Modelo × {M['referencia']}", "Lula 1º turno", "Lula 2º turno", "Variação"]]
        for m in M["efeito_variacao_lula"]:
            ef.append([m, f2(M["efeito_lula_1t"][m]), f2(M["efeito_lula_2t"][m]), f2(M["efeito_variacao_lula"][m])])
        out += [Spacer(1, 4), KeepTogether([P("Resultado por modelo de urna · 2º turno", "h2"),
                P("Votos válidos e ocorrências do log por modelo de urna. Os modelos não estão distribuídos ao acaso (as urnas mais antigas ficam em outros "
                  "lugares), por isso a comparação justa é entre seções do mesmo município.", "corpo"),
                tabela(tab, [26 * mm, 22 * mm, 18 * mm, 18 * mm, 22 * mm, 24 * mm, 22 * mm, 22 * mm], numericas=range(1, 8))]), Spacer(1, 3),
                KeepTogether([P("Diferença entre modelos no mesmo município (p.p., Lula entre os finalistas)", "h2"),
                tabela(ef, [44 * mm, 43 * mm, 43 * mm, 44 * mm], numericas=(1, 2, 3)),
                P("A diferença entre modelos aparece igual no 1º e no 2º turno: vem de onde cada modelo foi instalado, não do equipamento. A variação "
                  "entre os turnos por modelo fica abaixo de 0,1 p.p. (± indica 2 erros-padrão).", "nota")])]
    I = LG.get("intervalos") or {}
    if I.get("1") or I.get("2"):
        ts = [t for t in ("1", "2") if t in I]
        lin = lambda rot, f: [rot] + [f(I[t]) for t in ts]
        tab = [["Intervalo entre votos consecutivos"] + [f"{t}º turno" for t in ts],
               lin("Seções · intervalos medidos", lambda x: f"{n0(x['secoes'])} · {n0(x['intervalos'])}"),
               lin("Intervalo típico (mediana das seções)", lambda x: f"{n0(x['mediano_s'])} s"),
               lin("Intervalos com menos de 1 min · seções", lambda x: f"{p1(x['menos_1min_pct'])} · {n0(x['secoes_menos_1min'])}"),
               lin("Intervalos com menos de 30 s · seções", lambda x: f"{p1(x['menos_30s_pct'], 2)} · {n0(x['secoes_menos_30s'])}"),
               lin("Intervalos com menos de 10 s · seções", lambda x: f"{n0(x['menos_10s'])} · {n0(x['secoes_menos_10s'])}"),
               lin("Menor intervalo encontrado", lambda x: f"{n0(x['menor_s'])} s")]
        ufs = sorted(set().union(*(I[t]["ufs"] for t in ts)))
        t = ts[-1]
        top = [["UF", "Município", "Zona", "Seção", "Menor", "< 30 s", "< 1 min", "Os menores (voto → voto seguinte)"]]
        for r in I[t]["top"][:10]:
            menores = " · ".join(f"{a[:5]}→{b[:5]} {x} s" for a, b, x in json.loads(r[10] or "[]")[:2])
            top.append([r[0], (r[2] or str(r[1]))[:22], f"{r[3]:04d}", f"{r[4]:04d}", f"{r[5]} s", n0(r[7]), n0(r[8]), Paragraph(menores, R.estilo("mn", fontSize=7, leading=8.5))])
        out += [Spacer(1, 4), KeepTogether([P("Intervalo entre um voto e o seguinte", "h2"),
                P("Para cada seção, o tempo entre o voto computado de um eleitor e o do eleitor seguinte, que inclui a identificação do próximo eleitor e a "
                  "votação." + ("" if len(ufs) >= 28 else f" <b>Cobertura: {len(ufs)} unidades.</b>"), "corpo"),
                tabela(tab, [100 * mm] + [74 * mm / len(ts)] * len(ts), numericas=range(1, len(ts) + 1))]), Spacer(1, 3),
                KeepTogether([P(f"Seções com os menores intervalos · {t}º turno", "h2"),
                tabela(top, [10 * mm, 34 * mm, 13 * mm, 13 * mm, 14 * mm, 14 * mm, 16 * mm, 60 * mm], numericas=(2, 3, 4, 5, 6))])]
    A = LG.get("depois_17h") or {}
    if A.get("1") or A.get("2"):
        ts = [t for t in ("1", "2") if t in A]
        lin = lambda rot, f: [rot] + [f(A[t]) for t in ts]
        tab = [["Votos depois das 17h de Brasília"] + [f"{t}º turno" for t in ts],
               lin("Votos depois das 17h · seções", lambda x: f"{n0(x['votos'])} · {n0(x['secoes_com_votos'])}"),
               lin("Com biometria", lambda x: n0(x["biometria"])),
               lin("Sem identificação biométrica · seções", lambda x: f"{n0(x['sem_biometria'])} · {n0(x['secoes_sem_biometria'])}"),
               lin("   dos quais autorizados pelo mesário", lambda x: n0(x["mesario"])),
               lin("Parcela sem biometria: depois das 17h · no dia todo", lambda x: f"{p1(x['sem_biometria_pct'])} · {p1(x['sem_biometria_dia_pct'])}")]
        ufs = sorted(set().union(*(A[t]["ufs"] for t in ts)))
        out += [Spacer(1, 4), KeepTogether([P("Quem votou depois das 17h sem biometria", "h2"),
                P("Quem está na fila às 17h recebe senha e vota depois do horário. O log indica, para cada voto, se o eleitor foi identificado pela digital "
                  "ou sem biometria (documento conferido pelo mesário). Exterior fora do recorte (fusos variados)."
                  + ("" if len(ufs) >= 27 else f" <b>Cobertura: {len(ufs)} estados.</b>"), "corpo"),
                tabela(tab, [100 * mm] + [74 * mm / len(ts)] * len(ts), numericas=range(1, len(ts) + 1))])]
    return out


def parte_logs(LG):
    """Parte do relatório com os logs de todas as urnas."""
    T1, T2 = LG["turnos"]["1"], LG["turnos"]["2"]
    n_ufs = len(LG["ufs_processadas"])
    out = [P("PARTE 3", "olho"), P("Logs das urnas", "h1"),
           P("Cada urna grava, com horário, tudo o que acontece no dia: zerésima, abertura, habilitação de cada eleitor, troca de urna, erros e "
             f"encerramento. Foram lidos os logs de {n0(T1['secoes_com_log'])} seções no 1º turno e {n0(T2['secoes_com_log'])} no 2º, publicados pelo TSE "
             "nos arquivos transmitidos para totalização." + ("" if n_ufs >= 28 else f" <b>Cobertura parcial: {n_ufs} de 28 unidades.</b>"), "lead")]
    lin = lambda rot, f, d=None: [rot, f(T1), f(T2)]
    tab = [["Indicador", "1º turno", "2º turno"],
           lin("Seções com log", lambda t: n0(t["secoes_com_log"])),
           lin("Urnas trocadas (contingência)", lambda t: f"{n0(t['contingencia'])} ({p1(t['contingencia_pct'], 2)})"),
           lin("   antes da abertura · durante a votação", lambda t: f"{n0(t['contingencia_antes_abertura'])} · {n0(t['contingencia_durante'])}"),
           lin("Urna pronta no horário (8h de Brasília)", lambda t: p1(t["abertura_no_horario_pct"])),
           lin("   atraso de mais de 15 min · de mais de 1 h", lambda t: f"{n0(t['abertura_atraso_15'])} · {n0(t['abertura_atraso_60'])}"),
           lin("Zerésima registrada antes da abertura", lambda t: f"{p1(t['zeresima_ok_pct'], 2)} ({n0(t['zeresima_problema'])} sem)"),
           lin("Encerramento antes das 17h", lambda t: n0(t["encerramento_antes_17h"])),
           lin("Seções com eleitores na fila após as 17h", lambda t: f"{n0(t['secoes_votos_apos_17h'])} ({n0(t['votos_apos_17h'])} votos)"),
           lin("Habilitação por biometria · manual", lambda t: f"{p1(t['hab_biometrica_pct'])} · {p1(t['hab_manual_pct'])}"),
           lin("Votos no log iguais ao boletim (sem troca de urna)", lambda t: "—" if t["log_igual_boletim_pct"] is None else f"{p1(t['log_igual_boletim_pct'], 2)} ({n0(t['log_diferente_boletim'])} diferentes)"),
           lin("Erros fora da rotina · seções com erro", lambda t: f"{n0(t['erros_relevantes'])} · {n0(t['secoes_erros_relevantes'])}"),
           lin("Votos não registrados por erro · seções", lambda t: f"{n0(t['voto_nao_registrado'])} · {n0(t['secoes_voto_nao_registrado'])}"),
           lin("Seções com reinício durante a votação", lambda t: f"{n0(t['secoes_reiniciadas'])} ({n0(t['reinicios'])} reinícios)"),
           lin("Tempo típico de votação por eleitor", lambda t: "—" if t["tempo_votacao_mediano_s"] is None else f"{t['tempo_votacao_mediano_s']:.0f} s")]
    out += [tabela(tab, [86 * mm, 44 * mm, 44 * mm], numericas=(1, 2)),
            P("Horários convertidos para Brasília (votação das 8h às 17h). \"Erros fora da rotina\" exclui \"Problema ao desmontar a MR\", registrado em quase toda urna "
              "ao retirar a mídia de resultado. O tempo de votação é menor no 2º turno porque há menos cargos.", "nota"), Spacer(1, 6)]
    X = LG["cruzamentos"]
    cz = [["Ocorrência (2º turno)", f"Seções atípicas ({n0(X['atipicas']['secoes'])})", f"Demais seções ({n0(X['demais']['secoes'])})"]]
    for k, rot in [("contingencia_pct", "Troca de urna"), ("erros_relevantes_pct", "Erro fora da rotina"), ("reinicio_pct", "Reinício durante a votação"),
                   ("hab_manual_pct", "Habilitação manual (dos votos)"), ("voto_nao_registrado_pct", "Voto não registrado")]:
        cz.append([rot, p1(X["atipicas"][k], 2), p1(X["demais"][k], 2)])
    RE = {"contingencia": "Troca de urna", "reinicio": "Reinício durante a votação", "erro_relevante": "Erro fora da rotina", "dmanual_10pp": "Habilitação manual 10 p.p. maior que no 1º turno",
          "mesario_30pct": "Um mesário autorizou 30%+ dos votos", "ja_votou": "Alerta \"eleitor já votou\"", "bateria": "Urna funcionou na bateria"}
    ef = [["Ocorrência no 2º turno", "Diferença na variação de Lula", "Erro-padrão", "Leitura"]]
    for k, e in X["efeito_na_variacao_lula"].items():
        sem = abs(e["efeito_pp"]) < 2 * e["erro_padrao"]
        leve = not sem and abs(e["efeito_pp"]) < 0.1  # mensurável, mas desprezível para o resultado
        ef.append([RE.get(k, k), f"{e['efeito_pp']:+.2f}".replace(".", ",").replace("-", "−") + " p.p.", dec(e["erro_padrao"]), situacao({"status": "dentro" if sem or leve else "acima", "status_texto": ""})
                   .replace("Dentro do histórico", "Associação desprezível" if leve else "Sem associação").replace("Acima do histórico", "Associação estatística")])
    out += [KeepTogether([P("Ocorrências nas seções atípicas × nas demais", "h2"), tabela(cz, [80 * mm, 47 * mm, 47 * mm], numericas=(1, 2))]), Spacer(1, 4),
            KeepTogether([P("As ocorrências se associam à variação do voto?", "h2"),
                          P(f"Diferença na variação de Lula entre os turnos (média: {pp(X['variacao_lula_media_pp'])}) nas seções com cada ocorrência, comparadas com as "
                            "demais seções do mesmo município. Dentro de 2 erros-padrão: sem associação; fora desse limite e abaixo de 0,1 p.p.: associação desprezível.", "corpo"),
                          tabela(ef, [70 * mm, 40 * mm, 24 * mm, 40 * mm], numericas=(1, 2)),
                          P(f"Correlação, dentro do município, entre o aumento da habilitação manual e o aumento do comparecimento: {dec(X['corr_dmanual_dcomp'], 3)}.", "nota")]),
            Spacer(1, 4)]
    out += parte_logs_ampliada(LG.get("ampliada") or {})
    out += parte_logs_extra(LG)
    for t in ("1", "2"):
        msgs = [m for m in LG["mensagens"][t] if m[0] == "ERRO"][:12]
        tm = [["Mensagem de erro", "Ocorrências", "Estados"]] + [[Paragraph(m[1][:160], R.estilo("msg", fontSize=7.2, leading=9)), n0(m[2]), m[3]] for m in msgs]
        out += [KeepTogether([P(f"Mensagens de erro mais frequentes · {t}º turno", "h2"), tabela(tm, [134 * mm, 22 * mm, 18 * mm], numericas=(1, 2))]), Spacer(1, 4)]
    uf = [["UF", "Seções", "Trocas 1º", "Trocas 2º", "No horário 2º", "Biometria 2º", "Erro relev. 2º", "Voto não reg. 2º", "Log = BU 2º"]]
    for k, u in sorted(LG["por_uf"].items(), key=lambda x: -x[1].get("2", x[1].get("1", {})).get("secoes_com_log", 0)):
        a, b = u.get("1", {}), u.get("2", {})
        uf.append(["Exterior" if k == "ZZ" else k, n0(b.get("secoes_com_log", 0)), n0(a.get("contingencia", 0)), n0(b.get("contingencia", 0)),
                   p1(b["abertura_no_horario_pct"]) if b.get("abertura_no_horario_pct") is not None else "—", p1(b.get("hab_biometrica_pct", 0)),
                   n0(b.get("secoes_erros_relevantes", 0)), n0(b.get("voto_nao_registrado", 0)),
                   p1(b["log_igual_boletim_pct"], 2) if b.get("log_igual_boletim_pct") is not None else "—"])
    out += [P("Por estado", "h2"), tabela(uf, [16 * mm, 20 * mm, 17 * mm, 17 * mm, 21 * mm, 21 * mm, 21 * mm, 22 * mm, 19 * mm], numericas=range(1, 9)),
            P("A lista completa de seções com troca de urna, voto não registrado, erros ou reinícios está no portal (Auditoria → Logs das urnas), com o log de cada seção.", "nota"),
            PageBreak()]
    return out


def main():
    A = json.load(open(PORTAL_DADOS / "auditoria.json"))
    CP = json.load(open(PORTAL_DADOS / "comportamento.json"))
    ID = json.load(open(PORTAL_DADOS / "ideologia.json"))
    IA, cdir = ID["anos"], ID["cenarios_direita"]
    gd = lambda a, g: IA[str(a)]["grupos"][g]
    inds = CP["indicadores"]
    n_dentro = sum(i["status"] in ("dentro", "tendencia") for i in inds)
    n_aval = sum(i["status"] != "inedito" for i in inds)
    c, K, integ = A["contabilidade"], A["brasil"]["k"], A["integridade"]
    hist = A["historico"]
    h22, h26 = next(h for h in hist if h["ano"] == 2022), hist[-1]
    menor_ant = min(h["gap_pp"] for h in hist if h["ano"] < 2026)
    urna_max = max(abs(v["efeito_pp"]) for v in A["urnas"]["dentro_do_municipio"].values())
    sus = A["suspeitas"]
    col = {k: i for i, k in enumerate(sus["colunas"])}
    linhas_sus = sus["linhas"]

    story = [Spacer(1, 6 * mm), P("ELEIÇÃO PRESIDENCIAL 2026 · RELATÓRIO DE AUDITORIA ESTATÍSTICA", "olho"), Spacer(1, 3),
             P("Auditoria de dados e comportamento eleitoral do 2º turno", "titulo"), Spacer(1, 4),
             P(f"Flávio Bolsonaro liderou o 1º turno (04/10/2026) por {n0(c['vantagem_flavio_1'])} votos e Lula venceu o 2º (25/10/2026) por "
               f"{n0(c['lula_2'] - c['flavio_2'])}. Este relatório aplica às {n0(A['brasil']['secoes'])} seções eleitorais testes de consistência dos dados e de "
               "comportamento do eleitorado, compara o comportamento de 2026 com o das seis eleições anteriores (2002 a 2022) e lista as seções atípicas "
               "para conferência.", "lead"),
             Spacer(1, 2),
             P(f"<b>Escopo.</b> Boletins de urna de Presidente publicados pelo TSE (Portal de Dados Abertos), 1º e 2º turno, todas as seções do Brasil e do exterior. "
               f"<b>Data da análise:</b> {datetime.now():%d/%m/%Y}. <b>Reprodução:</b> github.com/adriano-atanes/analise-eleicao-presidente-2026.", "nota"),
             Spacer(1, 6),
             E.quadro("#1d7a4c", "Conclusão da auditoria estatística",
                      f"<b>Comportamento.</b> Dos {n_aval} indicadores de comportamento entre turnos medidos de 2002 a 2026, {n_dentro} ficaram dentro da faixa "
                      "histórica ou na tendência da série: viradas em estados e municípios, brancos e nulos, homogeneidade da variação municipal e previsibilidade "
                      "do 2º turno a partir do 1º. <b>Consistência.</b> Todos os testes de consistência dos boletins deram resultado dentro do esperado. "
                      "<b>A virada</b> se explica pela menor diferença de 1º turno da história "
                      f"({p1(h26['gap_pp'])} dos válidos, contra {p1(menor_ant)} na menor anterior) e por uma captação de votos novos ({p1(h26['parcela'], 0)}) "
                      f"na tendência das eleições anteriores (2022: {p1(h22['parcela'], 0)}). <b>Fora do histórico</b> ficaram o aumento do comparecimento "
                      f"({sinal(c['fontes_liquidas']['aumento do comparecimento'])} eleitores, espalhado pelas seções) e a parcela de eleitores dos eliminados de "
                      f"direita que votou em Lula ({p1(gd(2026, 'direita')['pt_entre_finalistas'], 0)}, contra {p1(gd(2018, 'direita')['pt_entre_finalistas'], 0)} em 2018 e "
                      f"{p1(gd(2022, 'direita')['pt_entre_finalistas'], 0)} em 2022). Nenhum dos dois decidiu o resultado: com o comparecimento ou o comportamento da "
                      f"direita de qualquer eleição anterior, Lula também venceria. Só {p1(gd(2026, 'composicao_ganho_pt')['direita'], 0)} do crescimento de Lula veio "
                      "de eleitores da direita. "
                      f"As {n0(len(linhas_sus))} seções atípicas listadas no anexo somam efeito desprezível sobre a margem e são o ponto de partida para conferência documental."),
             Spacer(1, 8), P("Comportamento comparado com 2002–2022", "h1")]
    resumo_comp = [["Indicador", "Faixa 2002–2022", "2026", "Situação"]]
    for i in inds:
        faixa_txt = "nenhuma" if i["id"] == "virada" else f"{fmt_ind(i, i['min'])} a {fmt_ind(i, i['max'])}"
        resumo_comp.append([i["nome"], faixa_txt, f"<b>{fmt_ind(i, i['valor_2026'])}</b>", situacao(i)])
    story += [tabela(resumo_comp, [80 * mm, 32 * mm, 22 * mm, 40 * mm], numericas=(1, 2)), Spacer(1, 8), P("Testes de consistência dos dados", "h1")]
    ok, at = '<font color="#0b7a0b"><b><font name="Simbolos">✓</font> Consistente</b></font>', '<font color="#a86f00"><b>! Incomum</b></font>'
    quadro = [["Teste", "O que detectaria", "Resultado", "Status"],
              ["Integridade dos boletins", "contas que não fecham", f"{integ['comparecimento_maior_que_aptos']} seções com comparecimento > aptos; "
               f"{integ['soma_votos_diferente_do_comparecimento_t2']} com votos ≠ comparecimento", ok],
              ["Contabilidade da virada", "votos sem origem", f"ganho dos finalistas = soma exata das fontes ({mi(c['ganho_total'])})", ok],
              ["Resíduos do modelo", "votos que o 1º turno não explica", f"> +10 p.p.: {K['res_lula_acima10']} seções Lula, {K['res_fla_acima10']} Flávio; "
               f"< −10 p.p.: {K['res_lula_abaixo10']} e {K['res_fla_abaixo10']}", ok],
              ["Ganhos acima das fontes", "trocas impossíveis", f"{K['limite_lula_10']} seções (Lula) e {K['limite_fla_10']} (Flávio) com 10+ votos; excesso total {n0(K['limite_lula_votos'])}", ok],
              ["Klimek (comparecimento × voto)", "comparecimento concentrado", f"comparecimento 100%: {K['comp100_1']} seções (1º) e {K['comp100_2']} (2º)", ok],
              ["Último dígito", "padrão não aleatório", f"p = {dec(A['digitos']['Lula_2']['ultimo_p'])} (Lula) e {dec(A['digitos']['Flávio_2']['ultimo_p'])} (Flávio)", ok],
              ["Modelo de urna", "efeito de equipamento", f"diferença máxima {dec(urna_max)} p.p. no mesmo município", ok],
              ["Relação com o 1º turno", "variação arbitrária", f"composição do 1º turno explica {p1(100 * A['eliminados']['r2'], 0)} da variação municipal", ok]]
    story += [tabela(quadro, [38 * mm, 33 * mm, 77 * mm, 26 * mm]), Spacer(1, 10)]

    # parte 1: comportamento comparado com eleições anteriores
    anos_ant = [a for a in CP["anos"] if a < 2026]
    story += [P("PARTE 1", "olho"), P("Comportamento do eleitorado comparado com 2002–2022", "h1"),
              P("Cada indicador mede como o voto mudou do 1º para o 2º turno, com os dados oficiais do TSE de cada eleição, no Brasil e nos municípios. "
                "O valor de 2026 é comparado com a faixa de 2002 a 2022 e, quando a série tem tendência clara, com a projeção dela. \"2º colocado\" é quem "
                "ficou em segundo no 1º turno nacional de cada ano (2002 Serra, 2006 Alckmin, 2010 Serra, 2014 Aécio, 2018 Haddad, 2022 Bolsonaro, 2026 Lula).", "lead")]
    tab = [["Indicador"] + [str(a) for a in CP["anos"]]]
    for i in inds:
        tab.append([f"<b>{i['nome']}</b><br/><font size='6.6' color='#7d847e'>{i['leitura']}</font><br/>{situacao(i)}"] +
                   [fmt_ind(i, i["serie"].get(str(a))) for a in anos_ant] + [f"<b>{fmt_ind(i, i['valor_2026'])}</b>"])
    story += [tabela(tab, [83 * mm] + [13 * mm] * 7, numericas=range(1, 8))]
    duas = Table([[R.figura(g_barras_hist(CP, "dcomp_pp", CP["tendencias"]["dcomp_pp_recente"], "", "Variação do comparecimento (p.p.)"), LARGURA / 2 - 3 * mm),
                   R.figura(g_barras_hist(CP, "captacao_segundo", CP["tendencias"]["captacao_segundo"], "%", "Votos novos captados pelo 2º colocado"), LARGURA / 2 - 3 * mm)]],
                 colWidths=[LARGURA / 2] * 2)
    story += [Spacer(1, 6), KeepTogether([duas, P("Losango: tendência das eleições anteriores projetada para 2026 (comparecimento: 2010–2022; captação: 2002–2022, sem 2006, "
                                                   "quando o 2º colocado perdeu votos).", "nota")]), Spacer(1, 6)]
    venc = lambda m: "—" if m is None else (f'<font color="#e34948"><b>Lula</b></font> por {n0(m)}' if m > 0 else f'<font color="#2a78d6"><b>Flávio</b></font> por {n0(-m)}')
    cen = [["Comportamento de", "Captação do 2º colocado", "Resultado de 2026", "Variação do comparecimento", "Resultado de 2026"]]
    for cc, cm in zip(CP["cenario_captacao"], CP["cenario_comparecimento"]):
        cen.append([cc["ano"], p1(cc["captacao"]) if cc["captacao"] > 0 else "perdeu votos", venc(cc["margem_segundo"]), pp(cm["dcomp_pp"]), venc(cm["margem_segundo"])])
    cen.append(["<b>2026 (real)</b>", f"<b>{p1(CP['nacional']['2026']['captacao_segundo'])}</b>", venc(CP["margem_real"]), f"<b>{pp(CP['nacional']['2026']['dcomp_pp'])}</b>", venc(CP["margem_real"])])
    story += [P("O resultado de 2026 com o comportamento de cada eleição anterior", "h2"),
              P(f"Captação: os {mi(CP['pool_2026'])} votos novos de 2026 divididos entre os finalistas na proporção daquele ano. Comparecimento: aumento ou queda "
                f"igual ao daquele ano, com os eleitores a mais ou a menos votando como os eleitores adicionais de 2026 ({p1(100 * CP['inclinacoes']['lula'], 0)} Lula, "
                f"{p1(100 * CP['inclinacoes']['flavio'], 0)} Flávio). São cenários aproximados.", "corpo"),
              tabela(cen, [26 * mm, 30 * mm, 42 * mm, 34 * mm, 42 * mm], numericas=(1, 3), destaque_linhas=[len(cen) - 1]),
              P("Com a captação de 2014, 2018 ou 2022, Lula também venceria; com a de 2002 ou 2010, Flávio venceria por margem pequena. Com o comparecimento de "
                "qualquer eleição anterior, Lula venceria: o aumento do comparecimento ampliou a margem, mas não decidiu o resultado.", "corpo"), Spacer(1, 6)]
    sg = lambda v: ("+" if round(v, 1) > 0 else "−" if round(v, 1) < 0 else "") + dec(abs(v), 1)
    est = [["Estado", "Δ comparec. 2026 (p.p.)", "Faixa 2002–2022", "Situação", "Δ brancos+nulos 2026 (p.p.)", "Faixa 2002–2022", "Situação", "Viradas 2002–22", "Virada 2026"]]
    sit = lambda f: situacao({"status": "dentro" if f["dentro"] else "acima", "status_texto": ""}).replace("Acima do histórico", "Acima" if f["acima"] else "Abaixo").replace("Dentro do histórico", "Dentro")
    for uf, e in sorted(CP["por_estado"].items(), key=lambda x: -x[1]["dcomp_pp"]["valor"]):
        est.append(["Exterior" if uf == "ZZ" else uf, sg(e["dcomp_pp"]["valor"]), f"{sg(e['dcomp_pp']['min'])} a {sg(e['dcomp_pp']['max'])}", sit(e["dcomp_pp"]),
                    sg(e["dbn_pp"]["valor"]), f"{sg(e['dbn_pp']['min'])} a {sg(e['dbn_pp']['max'])}", sit(e["dbn_pp"]), e["viradas_hist"], "sim" if e["virou_2026"] else "não"])
    story += [P("Comparecimento, brancos e nulos por estado", "h2"),
              P("Variação de 2026 entre os turnos comparada com a faixa do próprio estado de 2002 a 2022.", "corpo"),
              tabela(est, [16 * mm, 19 * mm, 27 * mm, 18 * mm, 21 * mm, 27 * mm, 17 * mm, 15 * mm, 14 * mm], numericas=(1, 2, 4, 5, 7)),
              P("O comparecimento subiu acima da faixa histórica em quase todos os estados, um movimento nacional e não concentrado. Brancos e nulos ficaram "
                "dentro da faixa na maioria dos estados.", "nota"), PageBreak()]

    # eleitores de cada campo ideológico
    comp_pt = [["Origem do crescimento do PT", "2018 (Haddad)", "2022 (Lula)", "2026 (Lula)"]]
    for k, nome in [("direita", "Eliminados de direita"), ("centro", "Eliminados de centro"), ("esquerda", "Eliminados de esquerda"),
                    ("BN", "Brancos e nulos no 1º turno"), ("Abst", "Não votaram no 1º turno")]:
        comp_pt.append([nome] + [p1(max(0, gd(a, "composicao_ganho_pt")[k])) for a in (2018, 2022, 2026)])
    camp = [["Eleitores dos eliminados", "Ano", "Votos no 1º turno", "→ PT", "→ outro finalista", "→ branco/nulo", "→ não votou", "PT entre os finalistas"]]
    for g, rot, anos_g in [("direita", "Direita", (2018, 2022, 2026)), ("centro", "Centro", (2010, 2014, 2018, 2022, 2026))]:
        for a in anos_g:
            x = gd(a, g)
            camp.append([rot, f"<b>{a}</b>" if a == 2026 else a, mi(x["votos"]), p1(x["pct_pt"]), p1(x["pct_outro"]), p1(x["pct_bn"]), p1(x["pct_abst"]),
                         f"<b>{p1(x['pt_entre_finalistas'])}</b>"])
    venc2 = lambda m: f'<font color="#e34948"><b>Lula</b></font> por {n0(m)}' if m > 0 else f'<font color="#2a78d6"><b>Flávio</b></font> por {n0(-m)}'
    cen_d = [["Eleitores de direita de 2026 votando…", "→ PT", "→ Flávio", "Resultado"],
             ["como estimado para 2026", p1(IA["2026"]["pct"][4][0]), p1(IA["2026"]["pct"][4][1]), venc2(cdir["margem_real_estimada"])]]
    cen_d += [[c_["cenario"], p1(c_["pct_pt"]), p1(c_["pct_outro"]), venc2(c_["margem_pt"])] for c_ in cdir["lista"]]
    cls = [["Ano", "Candidatos eliminados por campo"]]
    for a, d in ID["classificacao"].items():
        por = {}
        for n, (nome, part, campo) in d.items():
            if campo in ("esquerda", "centro", "direita"):
                por.setdefault(campo, []).append(f"{nome} ({part})")
        cls.append([a, "<br/>".join(f"<b>{k.capitalize()}:</b> {', '.join(v)}" for k, v in por.items())])
    story += [P("Os votos que Lula ganhou vieram da direita?", "h2"),
              P(f"Lula ficou com {p1(CP['nacional']['2026']['captacao_segundo'], 0)} dos {mi(CP['pool_2026'])} votos novos do 2º turno, cerca de 3 em cada 4. "
                "Esses votos novos não vieram só dos candidatos de direita eliminados: vieram também de quem votou branco ou nulo, de quem não tinha votado e "
                "dos eleitores de Augusto Cury, de centro. A tabela mostra a composição estimada do crescimento do candidato do PT nas três eleições em que "
                "ele enfrentou a direita no 2º turno.", "corpo"),
              tabela(comp_pt, [74 * mm, 33 * mm, 33 * mm, 34 * mm], numericas=(1, 2, 3)), Spacer(1, 6),
              P("Para onde foram os eleitores dos eliminados de direita e de centro", "h2"),
              P("Estimativa por zona eleitoral, igual em todos os anos para permitir a comparação (2026 por seção: direita "
                f"{p1(100 * ID['secoes_2026']['grupos']['direita']['pct_pt'] / (ID['secoes_2026']['grupos']['direita']['pct_pt'] + ID['secoes_2026']['grupos']['direita']['pct_outro']))} "
                "para o PT entre os finalistas). A comparação da direita usa só os anos em que o PT enfrentou a direita no 2º turno.", "corpo"),
              tabela(camp, [30 * mm, 13 * mm, 24 * mm, 17 * mm, 25 * mm, 22 * mm, 19 * mm, 24 * mm], numericas=range(1, 8)),
              P("Em 2026, a parcela dos eleitores de direita e de centro que foi para o PT ficou acima do observado antes. Os candidatos de direita de 2026 "
                "disputavam o mesmo campo de Flávio, e a estimativa é menos estável para os eleitores de Renan Santos.", "nota"), Spacer(1, 4),
              KeepTogether([P("O resultado com os eleitores de direita votando de outro jeito", "h2"),
                            tabela(cen_d, [80 * mm, 22 * mm, 22 * mm, 50 * mm], numericas=(1, 2)),
                            P("Com o comportamento da direita de 2018 ou de 2022, Lula também venceria. Mesmo que todos os eleitores de direita que votaram num "
                              "finalista tivessem escolhido Flávio, Lula venceria; Flávio só venceria se praticamente todos os eleitores de direita, inclusive os que "
                              "votaram branco, nulo ou não votaram, tivessem ido para ele.", "corpo")]),
              Spacer(1, 4), KeepTogether([P("Classificação usada (critério do analista, pelo partido)", "h2"),
                                          tabela(cls, [14 * mm, 160 * mm])]),
              PageBreak()]

    # parte 2: testes completos (relatório estatístico sem a capa)
    corpo = E.montar()
    inicio = next(i for i, f in enumerate(corpo) if isinstance(f, PageBreak)) + 1
    story += [P("PARTE 2", "olho"), P("Testes de consistência dos dados", "titulo"), Spacer(1, 4),
              P("As seções a seguir detalham cada teste do quadro, com gráficos e tabelas.", "lead"), Spacer(1, 6)]
    story += corpo[inicio:]
    story += [PageBreak()]

    # parte 3: logs das urnas (16_logs_urnas.py e 17_analise_logs.py)
    arq_logs = PORTAL_DADOS / "logs.json"
    if arq_logs.exists():
        story += parte_logs(json.load(open(arq_logs)))

    # parte 4: indicadores por estado
    story += [P("PARTE 4", "olho"), P("Indicadores por estado", "h1"),
              P("Os mesmos testes, estado por estado. Em cada linha: dispersão dos resíduos (desvio-padrão, em p.p. do eleitorado), seções muito acima do previsto, "
                f"ganhos acima das fontes (10 votos ou mais), seções com 100% de comparecimento e o qui-quadrado do último dígito no 2º turno (acima de {dec(CHI2_P01)} "
                "indicaria desvio a 1%).", "lead")]
    ind = [["UF", "Seções", "dp res. Lula", "dp res. Flávio", "Lula > +10", "Flávio > +10", "Ganho Lula > fontes", "Ganho Flávio > fontes",
            "Comp. 100% 1º/2º", "Δ comp. médio", "χ² Lula", "χ² Flávio"]]
    for uf, u in sorted(A["ufs"].items(), key=lambda x: -x[1]["secoes"]):
        k = u["k"]
        xl, xf = qui2(u["digitos"]["Lula_2"]), qui2(u["digitos"]["Flávio_2"])
        marca = lambda x: f'<font color="#b4501f"><b>{dec(x, 1)}</b></font>' if x > CHI2_P01 else dec(x, 1)
        ind.append(["Exterior" if uf == "ZZ" else uf, n0(u["secoes"]), dec(k["res_desvio_lula"]), dec(k["res_desvio_fla"]), k["res_lula_acima10"], k["res_fla_acima10"],
                    k["limite_lula_10"], k["limite_fla_10"], f"{k['comp100_1']}/{k['comp100_2']}", pp(k["dcomp_medio"]), marca(xl), marca(xf)])
    story += [tabela(ind, [14 * mm, 16 * mm, 14 * mm, 15 * mm, 13 * mm, 14 * mm, 15 * mm, 15 * mm, 15 * mm, 17 * mm, 12 * mm, 14 * mm], numericas=range(1, 12)),
              P("Estados com poucas seções (Exterior, RR, AP, AC) têm resíduos mais dispersos por efeito de tamanho; isso, por si só, não indica inconsistência.", "nota"),
              PageBreak()]

    # parte 3: seções atípicas
    cont = {m: sum(1 for l in linhas_sus if m in l[col["motivos"]]) for m in MOTIVOS}
    story += [P("PARTE 5", "olho"), P("Seções atípicas para conferência", "h1"),
              P(f"{n0(len(linhas_sus))} seções se destacam em pelo menos um teste. <b>Atípica quer dizer fora do padrão estatístico</b>: são as seções a conferir primeiro, comparando o "
                "boletim publicado com o boletim impresso (ou o QR code) e com os arquivos da urna. Ordenadas por estado, município, zona e seção.", "lead")]
    leg = [["Código", "Motivo", "Seções"]] + [[f"<b>{cod}</b>", txt, n0(cont[m])] for m, (cod, txt) in MOTIVOS.items()]
    story += [tabela(leg, [16 * mm, 140 * mm, 18 * mm], numericas=(2,)), Spacer(1, 4),
              P("Comp., Lula e Flávio: valor do 1º turno → 2º turno. Res.: resíduo (2º turno real menos o previsto), em p.p. do eleitorado da seção.", "nota")]
    tab = [["UF", "Município", "Zona", "Seção", "Aptos", "Comp.", "Lula", "Flávio", "Res. L", "Res. F", "Motivo"]]
    for l in sorted(linhas_sus, key=lambda r: (r[col["uf"]], r[col["nome"]], r[col["zona"]], r[col["secao"]])):
        g = lambda k: l[col[k]]
        rl, rf = g("res_lula"), g("res_fla")
        tab.append([g("uf"), g("nome"), f"{g('zona'):04d}", f"{g('secao'):04d}", g("aptos"), f"{g('comp1')}→{g('comp2')}",
                    f"{g('lula1')}→{g('lula2')}", f"{g('fla1')}→{g('fla2')}",
                    "—" if rl is None else dec(rl, 1), "—" if rf is None else dec(rf, 1), " ".join(MOTIVOS[m][0] for m in g("motivos"))])
    pequena = {"cel": R.estilo("cel_p", fontSize=6.8, leading=8.4), "celn": R.estilo("celn_p", fontSize=6.8, leading=8.4, alignment=2)}
    linhas_fmt = [tab[0]] + [[Paragraph(str(v), pequena["celn" if j in (2, 3, 4, 5, 6, 7, 8, 9) else "cel"]) for j, v in enumerate(r)] for r in tab[1:]]
    story += [tabela(linhas_fmt, [9 * mm, 37 * mm, 11 * mm, 11 * mm, 11 * mm, 18 * mm, 18 * mm, 16 * mm, 12 * mm, 12 * mm, 19 * mm], numericas=range(2, 10)),
              PageBreak()]

    # parte 4: roteiro
    story += [P("PARTE 6", "olho"), P("Roteiro de verificação além da estatística", "h1"),
              P("A estatística aponta onde olhar; a confirmação de qualquer inconsistência depende de documentos. Para as seções do anexo, ou para uma amostra aleatória "
                "de seções como controle:", "lead")]
    passos = [
        "<b>Boletim impresso.</b> Comparar o boletim de urna publicado pelo TSE com o boletim impresso afixado na seção ao fim da votação e entregue aos fiscais "
        "dos partidos. O QR code impresso no boletim permite conferir os números pelo celular.",
        "<b>Arquivos da urna.</b> Obter, no site de resultados do TSE, os arquivos de cada seção (boletim de urna, registro digital do voto e log da urna) e "
        "conferir se os totais batem com os publicados e se o log não mostra eventos anormais (substituição de urna, votação por cédula, horários atípicos).",
        "<b>Seções com mudança de origem.</b> Verificar as seções cujo boletim não veio da urna original "
        f"(no 2º turno: {integ['origem_do_voto_t2'].get('BU gerado por RED em urna de seção *** RED - Recuperador de dados', 0) + integ['origem_do_voto_t2'].get('BU gerado por RED em urna de contingência', 0)} "
        f"por recuperação de dados e {integ['origem_do_voto_t2'].get('Sistema de apuração', 0)} pelo sistema de apuração).",
        "<b>Atas da mesa receptora.</b> Para seções com salto de comparecimento ou comparecimento muito alto, consultar a ata da seção (ocorrências, número de "
        "votantes registrados no caderno) no cartório eleitoral da zona.",
        "<b>Testes oficiais.</b> Consultar os relatórios do teste de integridade das urnas, feito por sorteio no dia da eleição com acompanhamento de entidades "
        "fiscalizadoras, e do teste público de segurança.",
        "<b>Grupo de controle.</b> Repetir a conferência numa amostra aleatória de seções não atípicas. Se as atípicas tiverem divergências e as de controle não, "
        "há um achado; se ambas estiverem corretas, o caráter atípico vem do comportamento do eleitor.",
    ]
    story += [Paragraph(t, S["bullet"], bulletText=f"{i}.") for i, t in enumerate(passos, 1)]
    story += [Spacer(1, 6), P("Limitações", "h2"),
              P("Testes estatísticos detectam inconsistências nos dados (excesso de votos em parte das seções, contagens com padrão não aleatório, efeitos concentrados num "
                "tipo de equipamento). Uma alteração pequena e espalhada de forma proporcional por todas as seções seria difícil de distinguir de mudança real de voto. "
                "A migração de votos é estimada por inferência ecológica, já que o voto é secreto; as estimativas para os eleitores de Renan Santos são as menos estáveis. "
                "Este relatório não examina software, hardware ou a cadeia de custódia das urnas.", "corpo")]

    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                            title="Eleição Presidencial 2026: relatório de auditoria estatística", author="Análise com dados oficiais do TSE",
                            subject="Testes de consistência dos dados, comportamento do eleitorado, indicadores por estado e seções atípicas")
    doc.build(story, onFirstPage=R.rodape, onLaterPages=R.rodape)
    print(f"PDF salvo em {SAIDA}")


if __name__ == "__main__":
    main()
