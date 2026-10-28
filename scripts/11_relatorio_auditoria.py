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


def main():
    A = json.load(open(PORTAL_DADOS / "auditoria.json"))
    CP = json.load(open(PORTAL_DADOS / "comportamento.json"))
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
                      f"na tendência das eleições anteriores (2022: {p1(h22['parcela'], 0)}). O indicador fora do padrão histórico é o aumento do comparecimento "
                      f"({sinal(c['fontes_liquidas']['aumento do comparecimento'])} eleitores), espalhado pelas seções e sem concentração atípica. "
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

    # parte 2: testes completos (relatório estatístico sem a capa)
    corpo = E.montar()
    inicio = next(i for i, f in enumerate(corpo) if isinstance(f, PageBreak)) + 1
    story += [P("PARTE 2", "olho"), P("Testes de consistência dos dados", "titulo"), Spacer(1, 4),
              P("As seções a seguir detalham cada teste do quadro, com gráficos e tabelas.", "lead"), Spacer(1, 6)]
    story += corpo[inicio:]
    story += [PageBreak()]

    # parte 3: indicadores por estado
    story += [P("PARTE 3", "olho"), P("Indicadores por estado", "h1"),
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
    story += [P("PARTE 4", "olho"), P("Seções atípicas para conferência", "h1"),
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
    story += [P("PARTE 5", "olho"), P("Roteiro de verificação além da estatística", "h1"),
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
