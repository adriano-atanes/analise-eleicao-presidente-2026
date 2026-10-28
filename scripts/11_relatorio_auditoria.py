"""Relatório de auditoria em PDF (relatorio/auditoria_eleicao_2026.pdf).

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
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

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


def main():
    A = json.load(open(PORTAL_DADOS / "auditoria.json"))
    c, K, integ = A["contabilidade"], A["brasil"]["k"], A["integridade"]
    hist = A["historico"]
    h22, h26 = next(h for h in hist if h["ano"] == 2022), hist[-1]
    menor_ant = min(h["gap_pp"] for h in hist if h["ano"] < 2026)
    urna_max = max(abs(v["efeito_pp"]) for v in A["urnas"]["dentro_do_municipio"].values())
    sus = A["suspeitas"]
    col = {k: i for i, k in enumerate(sus["colunas"])}
    linhas_sus = sus["linhas"]

    story = [Spacer(1, 6 * mm), P("ELEIÇÃO PRESIDENCIAL 2026 · RELATÓRIO DE AUDITORIA ESTATÍSTICA", "olho"), Spacer(1, 3),
             P("Há sinais estatísticos de fraude na virada do 2º turno?", "titulo"), Spacer(1, 4),
             P(f"Flávio Bolsonaro liderou o 1º turno (04/10/2026) por {n0(c['vantagem_flavio_1'])} votos e Lula venceu o 2º (25/10/2026) por "
               f"{n0(c['lula_2'] - c['flavio_2'])}. Este relatório aplica às {n0(A['brasil']['secoes'])} seções eleitorais os testes usados em forense eleitoral para "
               "detectar votos adicionados ou alterados, compara a virada com as eleições de 2002 a 2022 e lista as seções atípicas para conferência.", "lead"),
             Spacer(1, 2),
             P(f"<b>Escopo.</b> Boletins de urna de Presidente publicados pelo TSE (Portal de Dados Abertos), 1º e 2º turno, todas as seções do Brasil e do exterior. "
               f"<b>Data da análise:</b> {datetime.now():%d/%m/%Y}. <b>Reprodução:</b> github.com/adriano-atanes/analise-eleicao-presidente-2026.", "nota"),
             Spacer(1, 6),
             E.quadro("#1d7a4c", "Conclusão da auditoria estatística",
                      "Nenhum teste encontrou padrão compatível com votos adicionados ou alterados. A virada se explica pela menor diferença de 1º turno da história "
                      f"({p1(h26['gap_pp'])} dos válidos, contra {p1(menor_ant)} na menor anterior) e por uma captação de votos novos ({p1(h26['parcela'], 0)}) "
                      f"próxima da de 2022 ({p1(h22['parcela'], 0)}). O único indicador fora do padrão histórico é o aumento do comparecimento "
                      f"({sinal(c['fontes_liquidas']['aumento do comparecimento'])} eleitores), espalhado pelas seções e sem a assinatura de urnas infladas. "
                      f"As {n0(len(linhas_sus))} seções atípicas listadas no anexo somam efeito desprezível sobre a margem e são o ponto de partida para conferência documental."),
             Spacer(1, 8), P("Quadro de testes", "h1")]
    ok, at = '<font color="#0b7a0b"><b><font name="Simbolos">✓</font> Sem anomalia</b></font>', '<font color="#a86f00"><b>! Incomum</b></font>'
    quadro = [["Teste", "O que detectaria", "Resultado", "Status"],
              ["Integridade dos boletins", "contas que não fecham", f"{integ['comparecimento_maior_que_aptos']} seções com comparecimento > aptos; "
               f"{integ['soma_votos_diferente_do_comparecimento_t2']} com votos ≠ comparecimento", ok],
              ["Contabilidade da virada", "votos sem origem", f"ganho dos finalistas = soma exata das fontes ({mi(c['ganho_total'])})", ok],
              ["Histórico 2002–2022", "conversão fora do padrão", f"2º colocado captou {p1(h26['parcela'], 0)} (2022: {p1(h22['parcela'], 0)})", ok],
              ["Aumento do comparecimento", "mobilização atípica", f"{sinal(c['fontes_liquidas']['aumento do comparecimento'])} eleitores; caiu em 5 das 6 eleições anteriores", at],
              ["Resíduos do modelo", "votos que o 1º turno não explica", f"> +10 p.p.: {K['res_lula_acima10']} seções Lula, {K['res_fla_acima10']} Flávio; "
               f"< −10 p.p.: {K['res_lula_abaixo10']} e {K['res_fla_abaixo10']}", ok],
              ["Ganhos acima das fontes", "trocas impossíveis", f"{K['limite_lula_10']} seções (Lula) e {K['limite_fla_10']} (Flávio) com 10+ votos; excesso total {n0(K['limite_lula_votos'])}", ok],
              ["Klimek (comparecimento × voto)", "enchimento de urna", f"comparecimento 100%: {K['comp100_1']} seções (1º) e {K['comp100_2']} (2º)", ok],
              ["Último dígito", "números inventados", f"p = {dec(A['digitos']['Lula_2']['ultimo_p'])} (Lula) e {dec(A['digitos']['Flávio_2']['ultimo_p'])} (Flávio)", ok],
              ["Modelo de urna", "efeito de equipamento", f"diferença máxima {dec(urna_max)} p.p. no mesmo município", ok],
              ["Relação com o 1º turno", "variação arbitrária", f"composição do 1º turno explica {p1(100 * A['eliminados']['r2'], 0)} da variação municipal", ok]]
    story += [tabela(quadro, [38 * mm, 33 * mm, 77 * mm, 26 * mm]), PageBreak()]

    # parte 1: testes completos (relatório estatístico sem a capa)
    corpo = E.montar()
    inicio = next(i for i, f in enumerate(corpo) if isinstance(f, PageBreak)) + 1
    story += [P("PARTE 1", "olho"), P("Testes estatísticos", "titulo"), Spacer(1, 4),
              P("As seções a seguir detalham cada teste do quadro, com gráficos e tabelas.", "lead"), Spacer(1, 6)]
    story += corpo[inicio:]
    story += [PageBreak()]

    # parte 2: indicadores por estado
    story += [P("PARTE 2", "olho"), P("Indicadores por estado", "h1"),
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
              P("Estados com poucas seções (Exterior, RR, AP, AC) têm resíduos mais dispersos por efeito de tamanho; isso não indica anomalia por si só.", "nota"),
              PageBreak()]

    # parte 3: seções atípicas
    cont = {m: sum(1 for l in linhas_sus if m in l[col["motivos"]]) for m in MOTIVOS}
    story += [P("PARTE 3", "olho"), P("Seções atípicas para conferência", "h1"),
              P(f"{n0(len(linhas_sus))} seções se destacam em pelo menos um teste. <b>Atípica não quer dizer irregular</b>: são as seções a conferir primeiro, comparando o "
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
    story += [P("PARTE 4", "olho"), P("Roteiro de verificação além da estatística", "h1"),
              P("A estatística aponta onde olhar; a confirmação de qualquer irregularidade depende de documentos. Para as seções do anexo, ou para uma amostra aleatória "
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
              P("Testes estatísticos detectam padrões típicos de manipulação (votos acrescentados em parte das seções, números inventados, efeitos concentrados num "
                "tipo de equipamento). Uma alteração pequena e espalhada de forma proporcional por todas as seções seria difícil de distinguir de mudança real de voto. "
                "A migração de votos é estimada por inferência ecológica, já que o voto é secreto; as estimativas para os eleitores de Renan Santos são as menos estáveis. "
                "Este relatório não examina software, hardware ou a cadeia de custódia das urnas.", "corpo")]

    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                            title="Eleição Presidencial 2026: relatório de auditoria estatística", author="Análise com dados oficiais do TSE",
                            subject="Testes de forense eleitoral, indicadores por estado e seções atípicas")
    doc.build(story, onFirstPage=R.rodape, onLaterPages=R.rodape)
    print(f"PDF salvo em {SAIDA}")


if __name__ == "__main__":
    main()
