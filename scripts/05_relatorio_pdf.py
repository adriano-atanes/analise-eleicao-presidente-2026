"""Gera o relatório em PDF com as análises (relatorio/relatorio_eleicao_presidente_2026.pdf).

Lê os mesmos arquivos do portal (portal/dados/resumo.json) e os da migração
(dados/processados/), desenha os gráficos com matplotlib e monta o documento com reportlab.
"""
import io
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from comum import DESTINOS, ORIGENS, PORTAL_DADOS, PROCESSADOS, RAIZ

SAIDA = RAIZ / "relatorio" / "relatorio_eleicao_presidente_2026.pdf"
FONTES = RAIZ / "relatorio" / "fontes"

# ---------- identidade visual (mesma paleta do portal) ----------
COR = {"Lula": "#e34948", "Flávio": "#2a78d6", "Renan": "#1baf7a", "Cury": "#eda100", "Caiado": "#6250d6",
       "Zema": "#e87ba4", "Outros": "#a29f95", "Branco": "#cfcdc4", "Nulo": "#8f8c84", "Abst": "#4f4d48"}
INK, INK2, MUTED, GRID, ACCENT, SURF2 = "#111512", "#4b524c", "#7d847e", "#e3e6e1", "#1d7a4c", "#eef0ec"
UP, DOWN = "#b4501f", "#12796a"
ROT = {"Lula": "Lula", "Flávio": "Flávio", "Renan": "Renan Santos", "Cury": "Augusto Cury", "Caiado": "Ronaldo Caiado",
       "Zema": "Zema", "Outros": "Outros 6 candidatos", "Branco": "Brancos", "Nulo": "Nulos", "Abst": "Abstenção"}
NOME_URNA = {22: "Flávio Bolsonaro", 13: "Lula", 70: "Augusto Cury", 14: "Renan Santos", 55: "Ronaldo Caiado", 30: "Zema"}
COR_NUM = {13: "Lula", 22: "Flávio", 14: "Renan", 70: "Cury", 55: "Caiado", 30: "Zema"}
ELIM = ["Renan", "Cury", "Caiado", "Zema", "Outros"]

for nome, arq in [("Plex", "Plex-R"), ("Plex-SB", "Plex-SB"), ("Plex-B", "Plex-B"), ("Plex-I", "Plex-I"),
                  ("PlexC-B", "PlexC-B"), ("PlexC-SB", "PlexC-SB"), ("PlexM", "PlexM-R")]:
    pdfmetrics.registerFont(TTFont(nome, str(FONTES / f"{arq}.ttf")))
    font_manager.fontManager.addfont(str(FONTES / f"{arq}.ttf"))
pdfmetrics.registerFont(TTFont("Simbolos", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFontFamily("Plex", normal="Plex", bold="Plex-B", italic="Plex-I", boldItalic="Plex-B")
plt.rcParams.update({"font.family": "IBM Plex Sans", "font.size": 8.5, "axes.edgecolor": "#c3c8c1", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True})


# ---------- formatação ----------
def n0(v):
    return f"{round(v):,}".replace(",", ".")


def p1(v, d=1):
    return f"{v:.{d}f}".replace(".", ",") + "%"


def pp(v):
    s = "+" if v > 0 else "−" if v < 0 else "±"
    return f"{s}{abs(v):.1f}".replace(".", ",") + " p.p."


def mi(v):
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}".replace(".", ",") + " mi"
    if abs(v) >= 1e4:
        return f"{v / 1e3:.1f}".replace(".", ",") + " mil"
    return n0(v)


def sinal(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + n0(abs(v))


def agregado(t1, t2):
    val1, val2 = sum(t1[:7]), t2[0] + t2[1]
    comp1, comp2 = t1[10] - t1[9], t2[5] - t2[4]
    return dict(t1=t1, t2=t2, val1=val1, val2=val2, comp1=comp1, comp2=comp2,
                abst1=100 * t1[9] / t1[10], abst2=100 * t2[4] / t2[5],
                br1=100 * t1[7] / comp1, br2=100 * t2[2] / comp2, nu1=100 * t1[8] / comp1, nu2=100 * t2[3] / comp2,
                lula1=100 * t1[0] / val1, fla1=100 * t1[1] / val1, lula2=100 * t2[0] / val2, fla2=100 * t2[1] / val2,
                comparec1=100 * comp1 / t1[10], comparec2=100 * comp2 / t2[5])


def destino_de(F, origens):
    """Soma dos fluxos de um grupo de origens, em votos e em % por destino."""
    ks = [ORIGENS.index(o) for o in origens]
    v = [sum(F[k][j] for k in ks) for j in range(len(DESTINOS))]
    tot = sum(v)
    return v, [100 * x / tot if tot else 0 for x in v]


# ---------- estilos ----------
def estilo(nome, **kw):
    base = dict(fontName="Plex", fontSize=9.5, leading=13.5, textColor=colors.HexColor(INK))
    base.update(kw)
    return ParagraphStyle(nome, **base)


S = {
    "olho": estilo("olho", fontName="PlexM", fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED)),
    "titulo": estilo("titulo", fontName="PlexC-B", fontSize=26, leading=29),
    "h1": estilo("h1", fontName="PlexC-B", fontSize=16, leading=20, spaceBefore=4, spaceAfter=4),
    "h2": estilo("h2", fontName="PlexC-SB", fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=2),
    "corpo": estilo("corpo", spaceAfter=5),
    "lead": estilo("lead", fontSize=10.5, leading=15, textColor=colors.HexColor(INK2), spaceAfter=6),
    "nota": estilo("nota", fontSize=7.8, leading=10.5, textColor=colors.HexColor(MUTED), spaceAfter=4),
    "bullet": estilo("bullet", leftIndent=10, bulletIndent=0, spaceAfter=3),
    "cel": estilo("cel", fontSize=8, leading=10),
    "celn": estilo("celn", fontSize=8, leading=10, alignment=TA_RIGHT),
    "cab": estilo("cab", fontName="Plex-SB", fontSize=7.8, leading=10, textColor=colors.HexColor(INK2)),
    "cabn": estilo("cabn", fontName="Plex-SB", fontSize=7.8, leading=10, textColor=colors.HexColor(INK2), alignment=TA_RIGHT),
    "kpi_rot": estilo("kpi_rot", fontSize=8, leading=10, textColor=colors.HexColor(INK2)),
    "kpi_val": estilo("kpi_val", fontName="PlexC-B", fontSize=17, leading=20),
    "kpi_sub": estilo("kpi_sub", fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED)),
}
LARGURA = A4[0] - 36 * mm


def P(txt, s="corpo"):
    return Paragraph(txt, S[s])


def tabela(linhas, larguras, numericas=(), destaque_linhas=(), cab=1, zebra=True):
    """Tabela com cabeçalho; colunas em `numericas` alinhadas à direita."""
    dados = []
    for i, linha in enumerate(linhas):
        cel = []
        for j, v in enumerate(linha):
            if isinstance(v, Paragraph):
                cel.append(v)
                continue
            st = ("cabn" if j in numericas else "cab") if i < cab else ("celn" if j in numericas else "cel")
            cel.append(Paragraph(str(v), S[st]))
        dados.append(cel)
    t = Table(dados, colWidths=larguras, repeatRows=cab)
    cmds = [("BACKGROUND", (0, 0), (-1, cab - 1), colors.HexColor(SURF2)),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(GRID)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for i in destaque_linhas:
        cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f4f6f2")))
    t.setStyle(TableStyle(cmds))
    return t


def figura(fig, largura=LARGURA):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    w, h = fig.get_size_inches()
    img = Image(buf, width=largura, height=largura * h / w)
    return img


def ponto(cor_hex):
    return f'<font name="Simbolos" color="{cor_hex}">■</font> '


# ---------- gráficos ----------
def g_primeiro_turno(R):
    cand, votos = R["candidatos"], R["brasil"]["cand1"]
    tot = sum(votos)
    pares = sorted(zip(cand, votos), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    nomes = [NOME_URNA.get(c["numero"], c["nome"]) + f" ({c['partido']})" for c, _ in pares]
    cores = [COR.get(COR_NUM.get(c["numero"], "Outros")) for c, _ in pares]
    ax.barh(nomes, [v for _, v in pares], color=cores, height=0.62)
    for i, (_, v) in enumerate(pares):
        ax.text(v + tot * 0.006, i, f"{p1(100 * v / tot, 2)}  ·  {mi(v)}", va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, max(votos) * 1.28)
    ax.xaxis.set_major_formatter(lambda x, _: mi(x))
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    return fig


def g_migracao(mig):
    linhas = ["Renan", "Cury", "Caiado", "Zema", "Outros", "Branco", "Nulo", "Abst", "Lula", "Flávio"][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    esq = [0] * len(linhas)
    for j, d in enumerate(DESTINOS):
        vals = [mig["pct"][ORIGENS.index(o)][j] for o in linhas]
        ax.barh([ROT[o] for o in linhas], vals, left=esq, color=COR[d], height=0.62, label=ROT[d], edgecolor="white", linewidth=0.8)
        for i, v in enumerate(vals):
            if v >= 7:
                cor_txt = INK if d == "Branco" else "white"
                ax.text(esq[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=7.2, color=cor_txt)
        esq = [a + b for a, b in zip(esq, vals)]
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.legend(ncol=5, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=7.8, handlelength=1, columnspacing=1.2)
    return fig


def g_ganhos(F):
    origens = [o for o in ORIGENS if o not in ("Lula", "Flávio")][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    y = range(len(origens))
    for desloc, nome, j in [(0.19, "Lula", 0), (-0.19, "Flávio", 1)]:
        vals = [F[ORIGENS.index(o)][j] for o in origens]
        ax.barh([i + desloc for i in y], vals, height=0.36, color=COR[nome], label=nome)
        for i, v in zip(y, vals):
            if v > 0:
                ax.text(v + 25000, i + desloc, mi(v), va="center", fontsize=6.8, color=INK2)
    ax.set_yticks(list(y), [ROT[o] for o in origens])
    ax.xaxis.set_major_formatter(lambda x, _: mi(x))
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(max(F[ORIGENS.index(o)][0], F[ORIGENS.index(o)][1]) for o in origens) * 1.15)
    ax.legend(loc="upper right", frameon=False)
    return fig


def g_histograma(R):
    b, h = R["hist_comparecimento"]["bordas"], R["hist_comparecimento"]["brasil"]
    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    ax.bar([x + 1 for x in b[:-1]], h, width=1.8, color=[ACCENT if x >= 0 else MUTED for x in b[:-1]])
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_xlabel("variação do comparecimento na seção, 2º turno menos 1º turno (pontos percentuais dos aptos)")
    ax.yaxis.set_major_formatter(lambda x, _: mi(x))
    ax.grid(axis="x", visible=False)
    ax.set_xlim(-22, 22)
    return fig


def g_abstencao_uf(R):
    linhas = sorted(((uf, agregado(u["t1"], u["t2"])) for uf, u in R["ufs"].items()), key=lambda x: x[1]["abst2"])
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i, (uf, a) in enumerate(linhas):
        ax.plot([a["abst1"], a["abst2"]], [i, i], color=UP if a["abst2"] > a["abst1"] else DOWN, linewidth=1.6, zorder=1)
    ax.scatter([a["abst1"] for _, a in linhas], range(len(linhas)), s=22, facecolor="white", edgecolor=MUTED, linewidth=1.2, label="1º turno", zorder=2)
    ax.scatter([a["abst2"] for _, a in linhas], range(len(linhas)), s=24, color=INK, label="2º turno", zorder=3)
    ax.set_yticks(range(len(linhas)), ["Exterior" if uf == "ZZ" else uf for uf, _ in linhas], fontsize=7.4)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right", frameon=False)
    return fig


def g_elim_uf(R):
    linhas = []
    for uf, u in R["ufs"].items():
        v, pct = destino_de(u["migracao"]["votos"], ELIM)
        linhas.append((uf, pct))
    linhas.sort(key=lambda x: x[1][0] / max(x[1][0] + x[1][1], 1e-9))
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    esq = [0] * len(linhas)
    for j, d in enumerate(DESTINOS):
        vals = [p[j] for _, p in linhas]
        ax.barh(range(len(linhas)), vals, left=esq, color=COR[d], height=0.7, label=ROT[d], edgecolor="white", linewidth=0.6)
        esq = [a + b for a, b in zip(esq, vals)]
    ax.set_yticks(range(len(linhas)), ["Exterior" if uf == "ZZ" else uf for uf, _ in linhas], fontsize=7.4)
    ax.set_xlim(0, 100)
    ax.axvline(50, color=INK, linewidth=0.6, alpha=0.5)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.legend(ncol=5, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=7.8, handlelength=1, columnspacing=1.2)
    return fig


# ---------- página ----------
def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Plex", 7)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(18 * mm, 10 * mm, "Eleição Presidencial 2026 · análise do 1º e do 2º turno · dados oficiais do TSE")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
    canvas.setStrokeColor(colors.HexColor(ACCENT))
    canvas.setLineWidth(2)
    canvas.line(18 * mm, A4[1] - 12 * mm, 40 * mm, A4[1] - 12 * mm)
    canvas.restoreState()


def kpis(a):
    def cel(rot, v1, v2, invert, sub):
        d = v2 - v1
        cor_d = UP if (d > 0) != invert else DOWN
        return [P(rot, "kpi_rot"), P(p1(v2), "kpi_val"),
                P(f'1º turno: {p1(v1)} · <font color="{cor_d}">{pp(d)}</font>', "kpi_sub"), P(sub, "kpi_sub")]
    cels = [cel("Comparecimento", a["comparec1"], a["comparec2"], True, f"{sinal(a['comp2'] - a['comp1'])} eleitores"),
            cel("Abstenção", a["abst1"], a["abst2"], False, f"{mi(a['t2'][4])} de {mi(a['t2'][5])} aptos"),
            cel("Votos brancos", a["br1"], a["br2"], False, f"{n0(a['t1'][7])} → {n0(a['t2'][2])}"),
            cel("Votos nulos", a["nu1"], a["nu2"], False, f"{n0(a['t1'][8])} → {n0(a['t2'][3])}")]
    t = Table([[c] for c in cels], colWidths=[LARGURA / 4 - 3 * mm])
    linhas = [[Table([[x] for x in c], colWidths=[LARGURA / 4 - 8 * mm]) for c in cels]]
    t = Table(linhas, colWidths=[LARGURA / 4] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.5, colors.HexColor(GRID)), ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor(GRID)),
                           ("BOX", (2, 0), (2, 0), 0.5, colors.HexColor(GRID)), ("BOX", (3, 0), (3, 0), 0.5, colors.HexColor(GRID)),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def placar(a):
    larg_l = LARGURA * a["lula2"] / 100
    barra = Table([["", ""]], colWidths=[larg_l, LARGURA - larg_l], rowHeights=[9])
    barra.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.HexColor(COR["Lula"])),
                               ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(COR["Flávio"])),
                               ("LINEAFTER", (0, 0), (0, 0), 1.5, colors.white)]))
    grande = ParagraphStyle("grande", parent=S["corpo"], fontName="PlexC-B", fontSize=24, leading=28)
    nomes = Table([[Paragraph(f'<font color="{COR["Lula"]}">{p1(a["lula2"], 2)}</font>', grande),
                    Paragraph(f'<font color="{COR["Flávio"]}">{p1(a["fla2"], 2)}</font>', ParagraphStyle("g2", parent=grande, alignment=TA_RIGHT))],
                   [P(f"Lula (PT) · {n0(a['t2'][0])} votos", "kpi_rot"),
                    Paragraph(f"Flávio Bolsonaro (PL) · {n0(a['t2'][1])} votos", ParagraphStyle("d", parent=S["kpi_rot"], alignment=TA_RIGHT))]],
                  colWidths=[LARGURA / 2] * 2)
    nomes.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    return [nomes, Spacer(1, 4), barra]


# ---------- documento ----------
def main():
    R = json.load(open(PORTAL_DADOS / "resumo.json"))
    mig = R["migracao"]["brasil"]
    sens = R["migracao"]["sensibilidade"]
    F = mig["votos"]
    B = R["brasil"]
    a = agregado(B["t1"], B["t2"])
    t1, t2 = B["t1"], B["t2"]
    cand, cand1 = R["candidatos"], B["cand1"]
    tot1 = sum(cand1)
    v_elim, p_elim = destino_de(F, ELIM)
    tot_elim = sum(t1[ORIGENS.index(o)] for o in ELIM)
    v_bn, p_bn = destino_de(F, ["Branco", "Nulo"])
    v_ab, p_ab = destino_de(F, ["Abst"])
    ganho_l, ganho_f = t2[0] - t1[0], t2[1] - t1[1]
    lula_de = {o: F[ORIGENS.index(o)][0] for o in ORIGENS}
    fla_de = {o: F[ORIGENS.index(o)][1] for o in ORIGENS}

    story = []
    # --- capa e resumo ---
    story += [Spacer(1, 6 * mm), P("ELEIÇÃO GERAL FEDERAL 2026 · PRESIDENTE DA REPÚBLICA", "olho"), Spacer(1, 3),
              P("Como o Brasil votou nos dois turnos", "titulo"), Spacer(1, 4),
              P(f"Resultado oficial do TSE para {n0(t1[10])} eleitores aptos em {n0(R['secoes'])} seções eleitorais: votos de todos os "
                f"candidatos no 1º turno (04/10/2026), resultado do 2º turno (25/10/2026), comparecimento, abstenção, brancos e nulos, "
                f"e a estimativa de como os votos migraram de um turno para o outro.", "lead"),
              Spacer(1, 4), P("2º TURNO · 25/10/2026 · BRASIL", "olho")]
    story += placar(a)
    story += [Spacer(1, 3), P(f"No 1º turno, Flávio liderou com {p1(a['fla1'])} dos votos válidos, contra {p1(a['lula1'])} de Lula. "
                              f"No 2º turno, Lula venceu por {n0(t2[0] - t2[1])} votos.", "nota"), Spacer(1, 6), kpis(a), Spacer(1, 8)]
    story += [P("Principais conclusões", "h1")]
    k = lambda o: ORIGENS.index(o)
    conclusoes = [
        f"<b>Virada no 2º turno.</b> Flávio terminou o 1º turno {n0(t1[1] - t1[0])} votos à frente. No 2º, Lula ganhou {sinal(ganho_l)} votos "
        f"e Flávio {sinal(ganho_f)}, uma vantagem de {n0(ganho_l - ganho_f)} votos no crescimento a favor de Lula.",
        f"<b>Mais gente votou no 2º turno.</b> O comparecimento subiu de {p1(a['comparec1'])} para {p1(a['comparec2'])} ({sinal(a['comp2'] - a['comp1'])} eleitores) "
        f"e os votos brancos e nulos caíram de {mi(t1[7] + t1[8])} para {mi(t2[2] + t2[3])}. Os votos válidos cresceram {mi(a['val2'] - a['val1'])}.",
        f"<b>Eleitores dos eliminados se dividiram.</b> Dos {mi(tot_elim)} votos dos {len(cand) - 2} candidatos eliminados, estima-se que "
        f"{p1(p_elim[0], 0)} foram para Lula, {p1(p_elim[1], 0)} para Flávio, {p1(p_elim[2] + p_elim[3], 0)} para branco ou nulo e {p1(p_elim[4], 0)} não votaram.",
        f"<b>Cada eliminado teve um padrão.</b> Eleitores de Augusto Cury foram mais para Lula ({p1(mig['pct'][k('Cury')][0], 0)} contra {p1(mig['pct'][k('Cury')][1], 0)}); "
        f"os de Ronaldo Caiado e de Zema, mais para Flávio ({p1(mig['pct'][k('Caiado')][1], 0)} e {p1(mig['pct'][k('Zema')][1], 0)}). "
        f"Os de Renan Santos ficaram divididos ({p1(mig['pct'][k('Renan')][0], 0)} Lula, {p1(mig['pct'][k('Renan')][1], 0)} Flávio), estimativa menos estável.",
        f"<b>O que decidiu.</b> Lula captou a maior parte de quem votou branco ou nulo no 1º turno ({mi(v_bn[0])} votos, {p1(p_bn[0], 0)}) e de quem "
        f"não tinha votado e passou a votar ({mi(v_ab[0])} contra {mi(v_ab[1])} de Flávio).",
        f"<b>Lealdade quase total.</b> Cerca de {p1(mig['pct'][0][0], 0)} dos eleitores de Lula e {p1(mig['pct'][1][1], 0)} dos de Flávio repetiram o voto.",
    ]
    story += [Paragraph(c, S["bullet"], bulletText="•") for c in conclusoes]
    story += [Spacer(1, 4), P("A migração de votos é uma estimativa estatística. O voto é secreto e não há registro de como cada eleitor votou nos dois "
                              "turnos; a metodologia e as limitações estão na seção 6.", "nota"), PageBreak()]

    # --- 1. primeiro turno ---
    story += [P("SEÇÃO 1", "olho"), P("1º turno: votos em todos os candidatos", "h1"),
              P(f"{n0(a['val1'])} votos válidos em 04/10/2026. Lula e Flávio somaram {p1(a['lula1'] + a['fla1'])}; os outros "
                f"{len(cand) - 2} candidatos tiveram {n0(tot_elim)} votos ({p1(100 * tot_elim / a['val1'])}).", "lead"),
              figura(g_primeiro_turno(R)), Spacer(1, 4)]
    linhas = [["#", "Candidato", "Partido", "Número", "Votos", "% válidos"]]
    for i, (c, v) in enumerate(sorted(zip(cand, cand1), key=lambda x: -x[1]), 1):
        linhas.append([i, ponto(COR.get(COR_NUM.get(c["numero"], "Outros"))) + NOME_URNA.get(c["numero"], c["nome"]), c["partido"], c["numero"], n0(v), p1(100 * v / tot1, 2)])
    linhas += [["", "Votos válidos", "", "", n0(a["val1"]), "100,00%"],
               ["", "Brancos", "", "", n0(t1[7]), p1(a["br1"], 2) + " do comp."],
               ["", "Nulos", "", "", n0(t1[8]), p1(a["nu1"], 2) + " do comp."],
               ["", "Abstenção", "", "", n0(t1[9]), p1(a["abst1"], 2) + " dos aptos"]]
    story += [tabela(linhas, [8 * mm, 62 * mm, 25 * mm, 18 * mm, 30 * mm, 31 * mm], numericas=(0, 3, 4, 5),
                     destaque_linhas=range(len(linhas) - 4, len(linhas))), PageBreak()]

    # --- 2. segundo turno e participação ---
    story += [P("SEÇÃO 2", "olho"), P("2º turno, comparecimento, abstenção, brancos e nulos", "h1"),
              P(f"O eleitorado apto foi o mesmo nos dois turnos ({n0(t1[10])}). O que mudou foi quantos votaram e como.", "lead")]
    linhas = [["Indicador", "1º turno (04/10)", "2º turno (25/10)", "Diferença"],
              ["Eleitores aptos", n0(t1[10]), n0(t2[5]), sinal(t2[5] - t1[10])],
              ["Comparecimento", f"{n0(a['comp1'])} ({p1(a['comparec1'])})", f"{n0(a['comp2'])} ({p1(a['comparec2'])})", sinal(a["comp2"] - a["comp1"])],
              ["Abstenção", f"{n0(t1[9])} ({p1(a['abst1'])})", f"{n0(t2[4])} ({p1(a['abst2'])})", sinal(t2[4] - t1[9])],
              ["Votos brancos", f"{n0(t1[7])} ({p1(a['br1'])})", f"{n0(t2[2])} ({p1(a['br2'])})", sinal(t2[2] - t1[7])],
              ["Votos nulos", f"{n0(t1[8])} ({p1(a['nu1'])})", f"{n0(t2[3])} ({p1(a['nu2'])})", sinal(t2[3] - t1[8])],
              ["Votos válidos", n0(a["val1"]), n0(a["val2"]), sinal(a["val2"] - a["val1"])],
              [ponto(COR["Lula"]) + "Lula", f"{n0(t1[0])} ({p1(a['lula1'])})", f"{n0(t2[0])} ({p1(a['lula2'])})", sinal(ganho_l)],
              [ponto(COR["Flávio"]) + "Flávio Bolsonaro", f"{n0(t1[1])} ({p1(a['fla1'])})", f"{n0(t2[1])} ({p1(a['fla2'])})", sinal(ganho_f)]]
    story += [tabela(linhas, [44 * mm, 44 * mm, 44 * mm, 42 * mm], numericas=(1, 2, 3)),
              P("Brancos e nulos em % do comparecimento; abstenção e comparecimento em % dos aptos; candidatos em % dos votos válidos.", "nota"),
              Spacer(1, 6), P("Variação do comparecimento em cada seção", "h2"),
              P(f"Distribuição das {n0(R['secoes'])} seções pela variação do comparecimento entre os turnos. Em verde, seções onde mais eleitores votaram no 2º turno.", "corpo"),
              figura(g_histograma(R)), Spacer(1, 4),
              KeepTogether([P("Abstenção por estado", "h2"),
                            P("Abstenção no 1º turno (círculo vazado) e no 2º (círculo cheio). Linha verde: a abstenção caiu; laranja: subiu.", "corpo"),
                            figura(g_abstencao_uf(R), LARGURA * 0.72)]),
              PageBreak()]

    # --- 3. migração ---
    story += [P("SEÇÃO 3", "olho"), P("Migração de votos do 1º para o 2º turno", "h1"),
              P("Para cada escolha no 1º turno (linhas), a porcentagem estimada que votou em Lula, em Flávio, branco, nulo ou não votou no 2º turno.", "lead"),
              figura(g_migracao(mig)), Spacer(1, 4)]
    linhas = [["Votou no 1º turno em…", "Eleitores", "→ Lula", "→ Flávio", "→ Branco/nulo", "→ Não votou"]]
    for nome, grupo in [("Todos os eliminados", ELIM), ("Renan Santos", ["Renan"]), ("Augusto Cury", ["Cury"]), ("Ronaldo Caiado", ["Caiado"]),
                        ("Zema", ["Zema"]), ("Outros 6 candidatos", ["Outros"]), ("Branco ou nulo", ["Branco", "Nulo"]), ("Não votou", ["Abst"])]:
        v, p = destino_de(F, grupo)
        n = sum(t1[ORIGENS.index(o)] for o in grupo)
        linhas.append([f"<b>{nome}</b>" if nome == "Todos os eliminados" else nome, n0(n),
                       f"{p1(p[0])} · {mi(v[0])}", f"{p1(p[1])} · {mi(v[1])}", f"{p1(p[2] + p[3])} · {mi(v[2] + v[3])}", f"{p1(p[4])} · {mi(v[4])}"])
    story += [tabela(linhas, [40 * mm, 24 * mm, 28 * mm, 28 * mm, 28 * mm, 26 * mm], numericas=(1, 2, 3, 4, 5), destaque_linhas=[1]), Spacer(1, 6)]

    story += [KeepTogether([P("De onde vieram os votos novos de cada finalista", "h2"),
                            P(f"Lula passou de {mi(t1[0])} para {mi(t2[0])} votos; Flávio, de {mi(t1[1])} para {mi(t2[1])}. "
                              "O gráfico mostra os votos estimados que cada um recebeu vindos de quem, no 1º turno, fez outra escolha.", "corpo"),
                            figura(g_ganhos(F))])]
    dec = [["Origem dos votos no 2º turno", "Lula", "Flávio"],
           ["Repetiram o voto do 1º turno", n0(lula_de["Lula"]), n0(fla_de["Flávio"])],
           ["Vieram do outro finalista", n0(lula_de["Flávio"]), n0(fla_de["Lula"])]]
    for o in ELIM + ["Branco", "Nulo", "Abst"]:
        dec.append([f"Vieram de {ROT[o].lower() if o in ('Branco', 'Nulo') else ROT[o]}" if o != "Abst" else "Não tinham votado no 1º turno",
                    n0(lula_de[o]), n0(fla_de[o])])
    dec.append(["<b>Total estimado</b>", n0(sum(lula_de.values())), n0(sum(fla_de.values()))])
    dec.append(["Total oficial", n0(t2[0]), n0(t2[1])])
    story += [Spacer(1, 4), tabela(dec, [90 * mm, 42 * mm, 42 * mm], numericas=(1, 2), destaque_linhas=[len(dec) - 2]),
              P("A soma estimada difere do total oficial em menos de 0,1%, porque o modelo é um ajuste estatístico.", "nota"), PageBreak()]

    # matriz completa + sensibilidade
    story += [P("Matriz de migração completa", "h2"),
              P("Porcentagem de cada linha (escolha no 1º turno) que foi para cada coluna (escolha no 2º turno). Abaixo de cada valor, o intervalo de 90% do bootstrap.", "corpo")]
    linhas = [["1º turno ↓   2º turno →", "Eleitores"] + [ROT[d] for d in DESTINOS]]
    for i, o in enumerate(ORIGENS):
        linhas.append([ponto(COR[o]) + ROT[o], n0(t1[i])] +
                      [f"<b>{p1(mig['pct'][i][j])}</b><br/><font size='6.5' color='{MUTED}'>{p1(mig['ic90'][0][i][j])}–{p1(mig['ic90'][1][i][j])}</font>"
                       for j in range(len(DESTINOS))])
    story += [tabela(linhas, [38 * mm, 24 * mm] + [22.4 * mm] * 5, numericas=(1, 2, 3, 4, 5, 6)), Spacer(1, 8)]
    story += [P("Teste de sensibilidade: seções × zonas eleitorais", "h2"),
              P(f"A mesma estimativa refeita com as {n0(sens['unidades'])} zonas eleitorais em vez das seções. Onde as duas concordam, o resultado é robusto; "
                "onde divergem, a estimativa depende mais da premissa do modelo e deve ser lida como uma faixa.", "corpo")]
    linhas = [["Votou no 1º turno em…", "Lula (seções)", "Lula (zonas)", "Flávio (seções)", "Flávio (zonas)", "Diferença máx."]]
    for o in ["Renan", "Cury", "Caiado", "Zema", "Outros", "Branco", "Nulo", "Abst"]:
        i = ORIGENS.index(o)
        d = max(abs(mig["pct"][i][0] - sens["pct"][i][0]), abs(mig["pct"][i][1] - sens["pct"][i][1]))
        linhas.append([ROT[o], p1(mig["pct"][i][0]), p1(sens["pct"][i][0]), p1(mig["pct"][i][1]), p1(sens["pct"][i][1]),
                       f'<font color="{UP if d > 10 else INK}">{d:.1f} p.p.</font>'.replace(".", ",", 1)])
    story += [tabela(linhas, [44 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm], numericas=(1, 2, 3, 4, 5)),
              P("Diferenças acima de 10 p.p. em laranja. Os eleitores de Renan Santos são o caso menos estável.", "nota"), PageBreak()]

    # --- 4. regiões ---
    story += [P("SEÇÃO 4", "olho"), P("Resultados e migração por região", "h1")]
    linhas = [["Região", "Aptos", "Lula 1º", "Flávio 1º", "Lula 2º", "Flávio 2º", "Abst. 1º", "Abst. 2º"]]
    reg_mig = [["Região", "Votos dos eliminados", "→ Lula", "→ Flávio", "→ Br./nulo", "→ Não votou", "Br./nulo → Lula", "Abst. → Lula"]]
    for reg, ufs in R["regioes"].items():
        t1r = [sum(R["ufs"][u]["t1"][i] for u in ufs) for i in range(11)]
        t2r = [sum(R["ufs"][u]["t2"][i] for u in ufs) for i in range(6)]
        ar = agregado(t1r, t2r)
        linhas.append([reg, n0(t1r[10]), p1(ar["lula1"]), p1(ar["fla1"]), p1(ar["lula2"]), p1(ar["fla2"]), p1(ar["abst1"]), p1(ar["abst2"])])
        Fr = R["migracao"]["regioes"][reg]["votos"]
        v, p = destino_de(Fr, ELIM)
        _, pbn = destino_de(Fr, ["Branco", "Nulo"])
        _, pab = destino_de(Fr, ["Abst"])
        reg_mig.append([reg, mi(sum(t1r[ORIGENS.index(o)] for o in ELIM)), p1(p[0]), p1(p[1]), p1(p[2] + p[3]), p1(p[4]), p1(pbn[0]), p1(pab[0])])
    story += [tabela(linhas, [28 * mm, 26 * mm] + [20 * mm] * 6, numericas=range(1, 8)),
              P("Lula e Flávio em % dos votos válidos; abstenção em % dos aptos.", "nota"), Spacer(1, 6),
              P("Para onde foram os votos, por região", "h2"),
              tabela(reg_mig, [26 * mm, 28 * mm, 18 * mm, 19 * mm, 20 * mm, 22 * mm, 22 * mm, 19 * mm], numericas=range(1, 8)),
              P("Br./nulo → Lula: % de quem votou branco ou nulo no 1º turno que votou em Lula no 2º. Abst. → Lula: % de quem não votou no 1º turno e votou em Lula no 2º.", "nota"),
              Spacer(1, 6),
              KeepTogether([P("Eleitores dos eliminados, por estado", "h2"),
                            P("Destino estimado, no 2º turno, dos votos dados aos candidatos eliminados no 1º, ordenado pela fatia de Lula entre os dois finalistas.", "corpo"),
                            figura(g_elim_uf(R), LARGURA * 0.92)]),
              PageBreak()]

    # --- 5. estados ---
    story += [P("SEÇÃO 5", "olho"), P("Resultados por estado", "h1"),
              P("Ordenado pelo eleitorado. Δ comparec.: variação do comparecimento entre os turnos, em pontos percentuais dos aptos.", "lead")]
    linhas = [["UF", "Aptos", "Lula 1º", "Flávio 1º", "Lula 2º", "Flávio 2º", "Abst. 1º", "Abst. 2º", "Δ comparec.", "Br+Nu 2º"]]
    for uf, u in sorted(R["ufs"].items(), key=lambda x: -x[1]["t1"][10]):
        au = agregado(u["t1"], u["t2"])
        venc = COR["Lula"] if au["lula2"] > au["fla2"] else COR["Flávio"]
        linhas.append([f'<font name="Simbolos" color="{venc}">■</font> {"Exterior" if uf == "ZZ" else uf}', n0(u["t1"][10]), p1(au["lula1"]), p1(au["fla1"]),
                       p1(au["lula2"]), p1(au["fla2"]), p1(au["abst1"]), p1(au["abst2"]), pp(au["comparec2"] - au["comparec1"]), p1(au["br2"] + au["nu2"])])
    story += [tabela(linhas, [17 * mm, 22 * mm] + [16.5 * mm] * 6, numericas=range(1, 10)),
              P("O quadrado indica o vencedor do 2º turno no estado (vermelho: Lula; azul: Flávio).", "nota"), PageBreak()]
    story += [P("Migração por estado", "h1"),
              P("Destino estimado dos votos dos candidatos eliminados, dos brancos e nulos e de quem não votou no 1º turno, com as seções de cada estado.", "lead")]
    linhas = [["UF", "Votos dos eliminados", "→ Lula", "→ Flávio", "→ Br./nulo", "→ Não votou", "Br./nulo → Lula", "Abst. → Lula", "Seções", "R² Lula"]]
    for uf, u in sorted(R["ufs"].items(), key=lambda x: -x[1]["t1"][10]):
        Fu = u["migracao"]["votos"]
        _, p = destino_de(Fu, ELIM)
        _, pbn = destino_de(Fu, ["Branco", "Nulo"])
        _, pab = destino_de(Fu, ["Abst"])
        linhas.append(["Exterior" if uf == "ZZ" else uf, mi(sum(u["t1"][ORIGENS.index(o)] for o in ELIM)), p1(p[0]), p1(p[1]), p1(p[2] + p[3]), p1(p[4]),
                       p1(pbn[0]), p1(pab[0]), n0(u["migracao"]["secoes"]), f'{u["migracao"]["r2"]["Lula"]:.2f}'.replace(".", ",")])
    story += [tabela(linhas, [15 * mm, 21 * mm, 15 * mm, 16 * mm, 17 * mm, 18 * mm, 19 * mm, 17 * mm, 16 * mm, 14 * mm], numericas=range(1, 10)),
              P("R² Lula: fração da variação do voto em Lula entre as seções do estado explicada pelo modelo (1 = ajuste perfeito). "
                "Valores de 0,0% em estados com poucas seções (Exterior, AP, RR, AC, TO) são limites do modelo, que não admite fluxos negativos: "
                "nesses casos, leia o número como \"pequeno\", não como zero exato.", "nota"), PageBreak()]

    # --- 6. metodologia ---
    metodo = [
        ("Fonte dos dados", f"Portal de Dados Abertos do TSE, arquivos de Presidente: <font name='PlexM' size='8'>votacao_secao_2026_BR</font>, "
         f"<font name='PlexM' size='8'>detalhe_votacao_secao_2026_BR</font>, <font name='PlexM' size='8'>votacao_candidato_munzona_2026_BR</font> e "
         f"<font name='PlexM' size='8'>detalhe_votacao_munzona_2026_BR</font>. A soma das {n0(R['secoes'])} seções confere exatamente com os totais oficiais por "
         "município e zona. Os 5.246 nulos técnicos do 1º turno (votos para número sem candidato válido) são contados como nulos."),
        ("Por que a migração é uma estimativa", "O voto é secreto: o boletim de urna registra só os totais de cada seção, nunca quem trocou de opção. "
         "A migração é estimada por inferência ecológica, comparando como a composição do voto mudou de seção para seção."),
        ("Modelo", "Em cada seção, a proporção do eleitorado em cada opção do 2º turno (Lula, Flávio, branco, nulo, abstenção) é escrita como uma combinação "
         "das proporções do 1º turno (Lula, Flávio, Renan Santos, Augusto Cury, Ronaldo Caiado, Zema, outros, branco, nulo, abstenção). Os pesos dessa "
         "combinação formam a matriz de transição, estimada por mínimos quadrados ponderados pelo eleitorado da seção, com cada linha somando 100% e "
         "sem valores negativos."),
        ("Estados, regiões e municípios", "Cada estado tem sua própria matriz, estimada com as suas seções. As matrizes do Brasil e das regiões somam os "
         "fluxos estimados de cada estado. No portal, os municípios têm matriz própria, puxada para a do estado quando há poucas seções."),
        ("Incerteza", "Os intervalos de 90% vêm de 100 reamostragens (bootstrap) das seções de cada estado e medem só a variação amostral, por isso são estreitos. "
         "A principal fonte de incerteza é a premissa de que eleitores com a mesma escolha no 1º turno se comportam de modo parecido dentro do estado. "
         "O teste de sensibilidade com zonas eleitorais (seção 3) indica quanto as estimativas dependem dessa premissa: os fluxos dos finalistas, de brancos, "
         "nulos e abstenção e o total dos eliminados são estáveis; o destino dos eleitores de Renan Santos é o menos estável."),
        ("Reprodutibilidade", "Código, dados processados e portal interativo: github.com/adriano-atanes/analise-eleicao-presidente-2026. "
         f"Dados gerados em {R['gerado_em']}."),
    ]
    story += [P("SEÇÃO 6", "olho"), P("Metodologia, fontes e limitações", "h1")]
    for t, txt in metodo:
        story += [P(t, "h2"), P(txt, "corpo")]

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm,
                            title="Eleição Presidencial 2026: análise do 1º e do 2º turno", author="Análise com dados oficiais do TSE",
                            subject="Resultados, migração de votos, comparecimento, abstenção, brancos e nulos")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    print(f"PDF salvo em {SAIDA}")


if __name__ == "__main__":
    main()
