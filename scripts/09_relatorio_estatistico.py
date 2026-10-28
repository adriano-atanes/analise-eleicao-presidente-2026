"""Relatório em PDF da análise estatística da virada (relatorio/analise_estatistica_2026.pdf).

Usa dados/processados/consistencia.json (08_consistencia.py), historico.json (07_historico.py) e as figuras
de relatorio/figuras/. Reaproveita estilos e funções do relatório principal (05_relatorio_pdf.py).
"""
import importlib
import json

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from comum import PROCESSADOS, RAIZ

R = importlib.import_module("05_relatorio_pdf")
P, S, tabela, figura, LARGURA = R.P, R.S, R.tabela, R.figura, R.LARGURA
n0, p1, pp, mi, sinal = R.n0, R.p1, R.pp, R.mi, R.sinal
SAIDA = RAIZ / "relatorio" / "analise_estatistica_2026.pdf"
FIG = RAIZ / "relatorio" / "figuras"


def img(nome, largura=LARGURA):
    from PIL import Image as PILImage
    caminho = FIG / f"{nome}.png"
    w, h = PILImage.open(caminho).size
    return Image(str(caminho), width=largura, height=largura * h / w)


def historico_linhas(h, c26):
    linhas = []
    for ano, d in h.items():
        c1 = d["1"]["candidatos"]
        c2 = {x[2]: x[3] for x in d["2"]["candidatos"]}
        lid, seg = c1[0], c1[1]
        val = sum(x[3] for x in c1)
        g_l, g_s = c2[lid[2]] - lid[3], c2[seg[2]] - seg[3]
        pool, gap = g_l + g_s, lid[3] - seg[3]
        venc = lid[0] if c2[lid[2]] > c2[seg[2]] else seg[0]
        linhas.append(dict(ano=int(ano), lider=lid[0], segundo=seg[0], gap_pp=100 * gap / val, gap=gap, elim_pct=100 * (val - lid[3] - seg[3]) / val,
                           g_l=g_l, g_s=g_s, parcela=100 * g_s / pool, necessaria=100 * (pool + gap) / 2 / pool,
                           dcomp=d["2"]["comparecimento"] - d["1"]["comparecimento"], vencedor=venc))
    val = c26["lula_1"] + c26["flavio_1"] + c26["fontes_liquidas"]["votos dos eliminados"]
    linhas.append(dict(ano=2026, lider="Flávio Bolsonaro", segundo="Lula", gap_pp=100 * c26["vantagem_flavio_1"] / val, gap=c26["vantagem_flavio_1"],
                       elim_pct=100 * c26["fontes_liquidas"]["votos dos eliminados"] / val, g_l=c26["ganho_flavio"], g_s=c26["ganho_lula"],
                       parcela=c26["parcela_lula_do_ganho"], necessaria=c26["parcela_minima_para_virar"],
                       dcomp=c26["fontes_liquidas"]["aumento do comparecimento"], vencedor="Lula"))
    return linhas


def g_historico(linhas):
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    anos = [str(l["ano"]) for l in linhas]
    x = range(len(anos))
    ax.bar([i - 0.2 for i in x], [l["necessaria"] for l in linhas], width=0.38, color="#c3c8c1", label="parcela necessária para virar")
    cores = ["#1d7a4c" if l["parcela"] > l["necessaria"] else "#4b524c" for l in linhas]
    ax.bar([i + 0.2 for i in x], [max(l["parcela"], 0) for l in linhas], width=0.38, color=cores, label="parcela obtida pelo 2º colocado")
    for i, l in enumerate(linhas):
        ax.text(i + 0.2, max(l["parcela"], 0) + 1.5, f"{l['parcela']:.0f}%" if l["parcela"] > 0 else "perdeu\nvotos", ha="center", fontsize=7, color="#111512")
        ax.text(i - 0.2, l["necessaria"] + 1.5, f"{l['necessaria']:.0f}%", ha="center", fontsize=7, color="#7d847e")
    ax.axhline(50, color="#111512", linewidth=0.6, alpha=0.4)
    ax.set_xticks(list(x), anos)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.16), ncol=2, fontsize=7.8)
    return fig


def quadro(cor, titulo, texto):
    t = Table([[Paragraph(f"<b>{titulo}</b><br/>{texto}", S["corpo"])]], colWidths=[LARGURA])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef0ec")), ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(cor)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def montar():
    """Monta o conteúdo do relatório (lista de flowables); usado também por 11_relatorio_auditoria.py."""
    f = json.load(open(PROCESSADOS / "consistencia.json"))
    h = json.load(open(PROCESSADOS / "historico.json"))
    c, integ, res, lim, comp, dig, urn, elim = (f[k] for k in ["contabilidade", "integridade", "residuos", "limites", "comparecimento", "digitos", "urnas", "eliminados"])
    hist = historico_linhas(h, c)
    h22 = next(l for l in hist if l["ano"] == 2022)
    h14 = next(l for l in hist if l["ano"] == 2014)
    menor_gap_anterior = min(l["gap_pp"] for l in hist if l["ano"] < 2026)
    story = []

    # --- capa ---
    story += [Spacer(1, 6 * mm), P("ELEIÇÃO PRESIDENCIAL 2026 · ANÁLISE ESTATÍSTICA", "olho"), Spacer(1, 3),
              P("Consistência estatística da virada no 2º turno", "titulo"), Spacer(1, 4),
              P(f"Flávio Bolsonaro liderou o 1º turno com {n0(c['vantagem_flavio_1'])} votos de vantagem e Lula venceu o 2º. É a primeira vez, desde 1989, "
                "que o líder do 1º turno perde a eleição presidencial no Brasil. Este relatório examina se o volume de votos que mudou de lado tem comportamento "
                "estatístico normal, usando o histórico das eleições anteriores e testes de consistência estatística aplicados às 499.248 seções de 2026.", "lead"),
              Spacer(1, 4),
              quadro("#1d7a4c", "Conclusão",
                     "Todos os testes de consistência deram resultado dentro do esperado. A virada se explica por dois fatos verificáveis: "
                     f"a diferença no 1º turno foi a menor da história ({p1(hist[-1]['gap_pp'])} dos válidos, contra {p1(menor_gap_anterior)} na menor anterior), "
                     f"e Lula captou {p1(c['parcela_lula_do_ganho'], 0)} dos votos novos do 2º turno, pouco acima dos {p1(h22['parcela'], 0)} que o 2º colocado "
                     "captou em 2022. Desde 2010, o 2º colocado sempre captou a maior parte dos votos novos; antes de 2026, a diferença de 1º turno é que era grande demais para virar."),
              Spacer(1, 8), P("Resumo dos testes", "h1")]
    resumo = [["Teste", "O que detectaria", "Resultado"],
              ["1. Integridade dos boletins", "boletins com contas que não fecham", f"0 seções com votos ≠ comparecimento ou comparecimento > aptos"],
              ["2. Contabilidade da virada", "votos sem origem possível", f"ganho dos finalistas = soma exata das fontes ({mi(c['ganho_total'])})"],
              ["3. Histórico 2002–2022", "conversão fora do padrão", f"Lula {p1(c['parcela_lula_do_ganho'], 0)} × 2º colocado em 2022 {p1(h22['parcela'], 0)} e 2014 {p1(h14['parcela'], 0)}"],
              ["4. Resíduos do modelo", "votos acima do que o 1º turno explica", f"simétricos; excedentes a favor de Lula: {n0(res['Lula']['votos_excedentes_acima_10pp'])} votos"],
              ["5. Limites por seção", "ganhos impossíveis sem trocas", f"{n0(lim['Lula']['secoes'])} seções, mediana {lim['Lula']['excesso_mediano']:.0f} votos; total {n0(lim['Lula']['votos_excedentes'])}"],
              ["6. Comparecimento × voto", "comparecimento concentrado (Klimek)", f"seções com 100%: {comp['secoes_comparecimento_100pct']['1']} (1º) e {comp['secoes_comparecimento_100pct']['2']} (2º)"],
              ["7. Último dígito", "padrão não aleatório", f"uniforme nos dois turnos (p = {dig['Lula_2']['ultimo_p']:.2f} Lula, {dig['Flávio_2']['ultimo_p']:.2f} Flávio)".replace("0.", "0,")],
              ["8. Modelo de urna", "efeito de equipamento", "diferenças ≤ 0,17 p.p. dentro do município"],
              ["9. Voto dos eliminados", "variação sem relação com o 1º turno", f"composição do 1º turno explica {p1(100 * elim['r2'], 0)} da variação municipal"]]
    story += [tabela(resumo, [44 * mm, 52 * mm, 78 * mm]), PageBreak()]

    # --- 1. histórico ---
    story += [P("SEÇÃO 1", "olho"), P("O que diz o histórico", "h1"),
              P("É verdade que, de 1989 a 2022, o líder do 1º turno sempre venceu o 2º na eleição presidencial. Mas isso diz pouco sobre 2026, por um motivo: "
                "nas eleições anteriores, a vantagem do líder era grande demais para ser revertida, mesmo quando o 2º colocado captou a maior parte dos votos novos.", "lead")]
    linhas = [["Ano", "Líder no 1º turno", "2º colocado", "Diferença 1º turno", "Votos dos eliminados", "Cresc. do líder", "Cresc. do 2º", "Parcela do 2º", "Necessária p/ virar"]]
    for l in hist:
        linhas.append([f"<b>{l['ano']}</b>" if l["ano"] == 2026 else l["ano"], l["lider"], l["segundo"], f"{p1(l['gap_pp'])}<br/>{mi(l['gap'])}", p1(l["elim_pct"]),
                       ("+" if l["g_l"] > 0 else "") + mi(l["g_l"]), ("+" if l["g_s"] > 0 else "") + mi(l["g_s"]), p1(l["parcela"]) if l["parcela"] > 0 else "—", p1(l["necessaria"])])
    story += [tabela(linhas, [11 * mm, 25 * mm, 25 * mm, 23 * mm, 18 * mm, 19 * mm, 19 * mm, 16 * mm, 18 * mm], numericas=range(3, 9), destaque_linhas=[len(linhas) - 1]),
              P("Diferença e votos dos eliminados em % dos votos válidos do 1º turno. Parcela do 2º: fatia do crescimento somado dos dois finalistas que ficou com o "
                "2º colocado. Necessária p/ virar: fatia mínima que o 2º colocado precisaria captar para passar o líder. Em 2006, Alckmin perdeu votos entre os turnos. "
                "Fonte: TSE, votacao_candidato_munzona de cada ano.", "nota"),
              figura(g_historico(hist)),
              P(f"<b>Leitura.</b> A parcela captada pelo 2º colocado cresceu eleição após eleição: 57% (2010), 59% (2014), 65% (2018), 70% (2022). "
                f"Em 2026, Lula captou {p1(c['parcela_lula_do_ganho'], 0)}, {pp(c['parcela_lula_do_ganho'] - h22['parcela'])} acima de 2022. A diferença é que, em 2026, "
                f"bastavam {p1(c['parcela_minima_para_virar'], 0)} para virar; em 2022 eram {p1(h22['necessaria'], 0)} e em 2014, {p1(h14['necessaria'], 0)}. "
                f"Com a parcela de 2022, Lula também teria virado em 2026.", "corpo"),
              P("<b>Fora da eleição presidencial brasileira</b>, viradas do 1º para o 2º turno são frequentes. Exemplos conhecidos (fora dos dados deste relatório): "
                "governos estaduais do Rio Grande do Sul e de Pernambuco em 2022, e as eleições presidenciais do Chile em 2021, da Argentina em 2023 e da Polônia em 2025, "
                "todas vencidas por quem ficou em 2º no 1º turno.", "corpo"),
              PageBreak()]

    # --- 2. contabilidade ---
    fl = c["fontes_liquidas"]
    story += [P("SEÇÃO 2", "olho"), P("Contabilidade da virada", "h1"),
              P("Antes de qualquer modelo, os números oficiais permitem fechar a conta: todo voto que os finalistas ganharam no 2º turno precisa ter vindo de algum lugar.", "lead")]
    linhas = [["Item", "Votos"],
              ["Lula no 1º turno", n0(c["lula_1"])], ["Flávio no 1º turno", n0(c["flavio_1"])], ["Vantagem de Flávio no 1º turno", n0(c["vantagem_flavio_1"])],
              ["Crescimento de Lula", sinal(c["ganho_lula"])], ["Crescimento de Flávio", sinal(c["ganho_flavio"])],
              ["<b>Crescimento somado dos finalistas</b>", f"<b>{sinal(c['ganho_total'])}</b>"],
              ["   vindo dos votos dos 10 eliminados", n0(fl["votos dos eliminados"])],
              ["   vindo da queda de brancos e nulos", n0(fl["queda de brancos e nulos"])],
              ["   vindo do aumento do comparecimento", n0(fl["aumento do comparecimento"])],
              ["<b>Soma das fontes</b>", f"<b>{n0(c['soma_fontes'])}</b>"]]
    story += [tabela(linhas, [120 * mm, 54 * mm], numericas=(1,), destaque_linhas=[6, 10]), Spacer(1, 6),
              P(f"<b>A conta fecha exatamente</b>: o crescimento dos finalistas é igual, voto a voto, à soma dos votos dos eliminados, da queda de brancos e nulos e "
                f"do aumento do comparecimento. Não há votos sem origem. Para virar, Lula precisava de pelo menos {p1(c['parcela_minima_para_virar'])} desse total "
                f"({n0(c['ganho_total'] * c['parcela_minima_para_virar'] / 100)} votos); ficou com {p1(c['parcela_lula_do_ganho'])}.", "corpo"),
              P(f"<b>O que foi incomum.</b> O comparecimento subiu {n0(fl['aumento do comparecimento'])} eleitores no 2º turno. Na série 2002–2022 ele caiu em cinco "
                f"eleições e subiu só em 2022 (+{n0(h22['dcomp'])}). Dentro de cada município, as seções onde o comparecimento mais aumentou deram a Lula, em média, "
                f"{p1(100 * comp['inclinacao_dl'], 0)} dos votos extras e a Flávio {p1(100 * comp['inclinacao_df'], 0)}. Isso é compatível com mobilização de eleitores; "
                "a seção 4 testa se o aumento se concentrou em poucas seções, e não se concentrou.", "corpo"),
              Spacer(1, 4), P("Integridade dos boletins de urna", "h2"),
              P(f"Verificado em cada uma das {n0(integ['secoes'])} seções e nos dois turnos: comparecimento maior que o eleitorado em "
                f"{integ['comparecimento_maior_que_aptos']} seções; soma dos votos diferente do comparecimento em {integ['soma_votos_diferente_do_comparecimento_t1']} (1º turno) e "
                f"{integ['soma_votos_diferente_do_comparecimento_t2']} (2º turno). O eleitorado nacional é idêntico nos dois turnos; {n0(integ['aptos_diferentes_entre_turnos'])} seções "
                "têm diferenças pequenas (em geral 1 ou 2 eleitores) por remanejamentos que se compensam. No 2º turno, "
                f"{n0(integ['origem_do_voto_t2'].get('Urna Eletrônica', 0))} boletins vieram da urna eletrônica, 16 de recuperação de dados da urna, "
                f"{integ['origem_do_voto_t2'].get('Sistema de apuração', 0)} do sistema de apuração e {integ['origem_do_voto_t2'].get('Totalização', 0)} de seções não instaladas.", "corpo"),
              PageBreak()]

    # --- 3. resíduos e limites ---
    rl, rf = res["Lula"], res["Flávio"]
    story += [P("SEÇÃO 3", "olho"), P("Os votos de cada seção são explicados pelo 1º turno?", "h1"),
              P("Se houvesse excesso sistemático de votos para um candidato em parte das seções, essas seções teriam no 2º turno mais votos para ele do que o seu próprio "
                "1º turno permite prever. O modelo de migração do estado prevê o 2º turno de cada seção a partir do 1º; a diferença entre o real e o previsto é o resíduo.", "lead"),
              img("residuos"),
              tabela([["", "Lula", "Flávio"],
                      ["Desvio-padrão do resíduo", f"{rl['desvio_pp']:.2f}".replace(".", ",") + " p.p.", f"{rf['desvio_pp']:.2f}".replace(".", ",") + " p.p."],
                      ["Assimetria (positiva = cauda a favor)", f"{rl['assimetria']:.2f}".replace(".", ","), f"{rf['assimetria']:.2f}".replace(".", ",")],
                      ["Seções com mais de 10 p.p. acima do previsto", n0(rl["acima_10pp"]), n0(rf["acima_10pp"])],
                      ["Seções com mais de 10 p.p. abaixo do previsto", n0(rl["abaixo_10pp"]), n0(rf["abaixo_10pp"])],
                      ["Votos acima do previsto nessas seções", n0(rl["votos_excedentes_acima_10pp"]), n0(rf["votos_excedentes_acima_10pp"])]],
                     [100 * mm, 37 * mm, 37 * mm], numericas=(1, 2)),
              P(f"<b>Leitura.</b> Os resíduos são estreitos e quase simétricos, e a cauda é ligeiramente <i>contra</i> os dois candidatos, não a favor. As seções muito acima "
                f"do previsto para Lula somam {n0(rl['votos_excedentes_acima_10pp'])} votos, 0,1% da margem de {n0(c['lula_2'] - c['flavio_2'])}. As maiores estão "
                "no Pará (Parauapebas e Altamira), onde o comparecimento subiu e quase todos os votos já eram de Lula no 1º turno.", "corpo"),
              Spacer(1, 4), P("Ganhos que exigem eleitores do adversário", "h2"),
              P(f"Em cada seção, comparamos o ganho de cada finalista com tudo o que ele poderia receber sem tirar eleitores do adversário: votos dos eliminados, brancos, "
                f"nulos e o aumento do comparecimento. Em {n0(lim['Lula']['secoes'])} seções ({p1(lim['Lula']['pct_secoes'])}) o ganho de Lula passa desse limite, e em "
                f"{n0(lim['Flávio']['secoes'])} o de Flávio. O excesso mediano é de {lim['Lula']['excesso_mediano']:.0f} votos, que se explica pela troca de eleitores entre turnos "
                f"(quem votou no 1º e faltou no 2º, substituído por quem fez o contrário) ou por eleitores de Flávio que votaram em Lula. Somado, o excesso é de "
                f"{n0(lim['Lula']['votos_excedentes'])} votos; só 109 seções passam de 10 votos. A assimetria é coerente com o modelo de migração, que estima que "
                "0,2% dos eleitores de Flávio no 1º turno votaram em Lula no 2º, mas o volume é irrelevante para o resultado.", "corpo"),
              PageBreak()]

    # --- 4. comparecimento ---
    story += [P("SEÇÃO 4", "olho"), P("Comparecimento e voto: há concentração atípica?", "h1"),
              P("O teste de Klimek et al. (2012) cruza o comparecimento de cada seção com o voto do candidato. Quando o comparecimento cresce de forma atípica e concentrada num candidato, aparece uma "
                "concentração de seções com comparecimento perto de 100% e quase todos os votos para o mesmo candidato, separada da nuvem principal. "
                "Os mapas abaixo mostram onde estão os votos de cada candidato, nos dois turnos.", "lead"),
              img("impressao_digital", LARGURA * 0.86),
              P(f"<b>Leitura.</b> As nuvens do 2º turno têm a mesma forma das do 1º, deslocadas como esperado, sem aglomerado no canto superior direito. Seções com "
                f"comparecimento de 100%: {comp['secoes_comparecimento_100pct']['1']} no 1º turno e {comp['secoes_comparecimento_100pct']['2']} no 2º; com 95% ou mais: "
                f"{n0(comp['secoes_comparecimento_95pct']['1'])} e {n0(comp['secoes_comparecimento_95pct']['2'])}, em quase 500 mil seções.", "corpo"),
              img("comparecimento_secoes"),
              P("A distribuição do comparecimento por seção se desloca inteira para a direita no 2º turno, sem cauda nova nem picos: o aumento foi espalhado, não concentrado em poucas seções.", "nota"),
              PageBreak()]

    # --- 5. dígitos e urnas ---
    story += [P("SEÇÃO 5", "olho"), P("Dígitos e modelos de urna", "h1"), P("Último dígito dos votos por seção", "h2"),
              P("Contagens produzidas por processos não aleatórios tendem a repetir alguns dígitos finais. Em contagens reais com dezenas ou centenas de votos, cada dígito final "
                "(0 a 9) aparece em cerca de 10% das seções.", "corpo"), img("ultimo_digito")]
    linhas = [["Contagem", "Seções (≥ 10 votos)", "Maior desvio de 10%", "Qui-quadrado", "p-valor", "2º dígito: média", "Benford"]]
    for col, nome in [("Lula_1", "Lula · 1º turno"), ("Flávio_1", "Flávio · 1º turno"), ("Lula_2", "Lula · 2º turno"), ("Flávio_2", "Flávio · 2º turno")]:
        d = dig[col]
        linhas.append([nome, n0(d["n"]), f"{d['ultimo_desvio_max_pp']:.2f}".replace(".", ",") + " p.p.", f"{d['ultimo_chi2']:.1f}".replace(".", ","),
                       f"{d['ultimo_p']:.2f}".replace(".", ","), f"{d['segundo_media']:.2f}".replace(".", ","), f"{d['segundo_media_benford']:.2f}".replace(".", ",")])
    story += [tabela(linhas, [32 * mm, 26 * mm, 26 * mm, 22 * mm, 18 * mm, 26 * mm, 24 * mm], numericas=range(1, 7)),
              P("<b>Leitura.</b> O último dígito é uniforme para os dois candidatos nos dois turnos (p-valores altos: nenhuma evidência de desvio). O 2º dígito fica abaixo "
                "da lei de Benford para todos, inclusive no 1º turno, o que é conhecido em seções eleitorais pequenas e de tamanho limitado (Mebane); o que importaria seria "
                "uma diferença entre candidatos ou turnos, e ela não aparece.", "corpo"), Spacer(1, 6),
              P("Modelo de urna", "h2"),
              P("Alegações sobre urnas costumam mirar modelos específicos. Comparamos a variação de Lula entre os turnos (em pontos percentuais dos válidos) entre modelos, "
                "sempre dentro do mesmo município, para não confundir o modelo com a região onde ele está.", "corpo")]
    linhas = [["Modelo (2º turno)", "Seções", "Variação média de Lula", "Diferença vs. UE 2020 no mesmo município", "Erro-padrão"]]
    for m, n in sorted(urn["secoes_por_modelo"].items()):
        ef = urn["dentro_do_municipio"].get(m)
        linhas.append([m, n0(n), pp(urn["sem_controle"][m]), pp(ef["efeito_pp"]) if ef else "referência",
                       f"{ef['erro_padrao']:.2f}".replace(".", ",") if ef else "—"])
    story += [tabela(linhas, [32 * mm, 24 * mm, 34 * mm, 54 * mm, 30 * mm], numericas=range(1, 5)),
              P(f"<b>Leitura.</b> Lula ganhou cerca de 6,4 pontos em todos os modelos. Dentro do município, as diferenças entre modelos ficam entre 0,03 e 0,17 ponto, "
                "menos de 3% da variação total e no limite da significância estatística; não há efeito de equipamento relevante.", "corpo"),
              PageBreak()]

    # --- 6. eliminados ---
    co = elim["coeficientes"]
    story += [P("SEÇÃO 6", "olho"), P("A variação acompanha o voto dos eliminados?", "h1"),
              P("Se a virada veio dos eleitores dos eliminados, Lula deveria crescer mais onde esses candidatos foram fortes. Uma regressão entre os "
                f"{n0(elim['municipios'])} municípios relaciona o crescimento de Lula com a composição do voto no 1º turno.", "lead"),
              img("cury_x_lula"),
              tabela([["Variável do 1º turno (em p.p.)", "Efeito sobre o crescimento de Lula"],
                      ["Augusto Cury", f"+{co['Cury']:.2f}".replace(".", ",") + " p.p. por ponto"],
                      ["Renan Santos", f"+{co['Renan']:.2f}".replace(".", ",") + " p.p. por ponto"],
                      ["Ronaldo Caiado", f"+{co['Caiado']:.2f}".replace(".", ",") + " p.p. por ponto"],
                      ["Zema", f"+{co['Zema']:.2f}".replace(".", ",") + " p.p. por ponto"],
                      ["Brancos e nulos", f"+{co['BrancoNulo']:.2f}".replace(".", ",") + " p.p. por ponto"]],
                     [100 * mm, 74 * mm], numericas=(1,)),
              P(f"<b>Leitura.</b> A composição do 1º turno explica {p1(100 * elim['r2'], 0)} da variação de Lula entre municípios. Lula cresceu em quase todos "
                f"(caiu em {elim['municipios_lula_caiu']} de {n0(elim['municipios'])}; crescimento mediano de {pp(elim['variacao_lula_pp_mediana'])}), e cresceu mais "
                "onde Augusto Cury teve mais votos, em linha com o modelo de migração (53% dos eleitores de Cury foram para Lula). Uma alteração artificial de votos "
                "tenderia a produzir variação sem relação com o 1º turno de cada lugar.", "corpo"),
              Spacer(1, 6), P("O que esta análise não cobre", "h1"),
              P("Testes estatísticos detectam inconsistências nos dados, como excesso de votos em parte das seções, contagens com padrão não aleatório ou efeitos concentrados "
                "num tipo de equipamento. Eles não substituem a conferência documental: uma alteração pequena e espalhada de modo proporcional por todas as seções "
                "seria difícil de distinguir de mudança real de voto. A verificação desse tipo de hipótese é feita por auditoria (teste de integridade das urnas, conferência "
                "dos boletins impressos com os publicados, registros digitais de voto), que está fora do alcance deste relatório.", "corpo"),
              P("Os dados usados são os boletins de urna publicados pelo TSE. Todo o código está em github.com/adriano-atanes/analise-eleicao-presidente-2026 "
                "(scripts 07_historico.py, 08_consistencia.py e 09_relatorio_estatistico.py), e os resultados podem ser reproduzidos por qualquer pessoa.", "corpo")]

    return story


def main():
    story = montar()
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                            title="Eleição Presidencial 2026: análise estatística da virada", author="Análise com dados oficiais do TSE")
    doc.build(story, onFirstPage=R.rodape, onLaterPages=R.rodape)
    print(f"PDF salvo em {SAIDA}")


if __name__ == "__main__":
    main()
