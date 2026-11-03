"""Monta o site estático do portal em site/ (para o GitHub Pages).

portal/index.html é escrito sem o esqueleto HTML (doctype, <head>, reset), que o visualizador
de artifacts acrescenta. Aqui o esqueleto é acrescentado e os dados são copiados ao lado.
"""
import shutil
from pathlib import Path

# só biblioteca padrão: o site pode ser montado sem instalar nada
RAIZ = Path(__file__).resolve().parent.parent

PORTAL = RAIZ / "portal"
SITE = RAIZ / "site"

CABECALHO = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Presidente 2026 · resultado, auditoria dos boletins e logs das urnas</title>
<meta name="description" content="Resultado oficial do TSE para Presidente 2026 nos dois turnos, auditoria dos 499.248 boletins de urna, logs das urnas e detalhamento até a seção eleitoral.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Presidente 2026">
<meta property="og:locale" content="pt_BR">
<meta property="og:url" content="https://adriano-atanes.github.io/analise-eleicao-presidente-2026/">
<meta property="og:title" content="Presidente 2026: resultado, auditoria dos boletins e logs das urnas">
<meta property="og:description" content="Lula 51,79% × Flávio 48,21%. Os 499.248 boletins conferidos seção por seção: seções atípicas, ocorrências, testes e as perguntas que circulam.">
<meta property="og:image" content="https://adriano-atanes.github.io/analise-eleicao-presidente-2026/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Presidente 2026: Lula 51,79% e Flávio 48,21%, com 499.248 boletins conferidos.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Presidente 2026: resultado, auditoria dos boletins e logs das urnas">
<meta name="twitter:description" content="Os 499.248 boletins conferidos seção por seção: seções atípicas, ocorrências, testes e perguntas que circulam.">
<meta name="twitter:image" content="https://adriano-atanes.github.io/analise-eleicao-presidente-2026/og.png">
<meta name="theme-color" content="#f5f4f0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141413" media="(prefers-color-scheme: dark)">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%23141413%22/%3E%3Ctext x=%2216%22 y=%2222%22 font-family=%22Arial%22 font-weight=%22800%22 font-size=%2216%22 fill=%22%23fff%22 text-anchor=%22middle%22%3EP%3C/text%3E%3C/svg%3E">
<style>
:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
body { margin: 0; font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
img { max-width: 100%; }
[hidden] { display: none !important; }
</style>
</head>
<body>
"""


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(PORTAL / "dados", SITE / "dados")
    (SITE / "index.html").write_text(CABECALHO + (PORTAL / "index.html").read_text() + "\n</body>\n</html>\n")
    (SITE / ".nojekyll").touch()
    for img in ("og.png", "apple-touch-icon.png"):  # imagem de compartilhamento e ícone da tela inicial
        if (PORTAL / img).exists():
            shutil.copy(PORTAL / img, SITE / img)
    for video in PORTAL.glob("*.mp4"):  # animações da apuração (18_apuracao_animada.py + render do modo vídeo)
        shutil.copy(video, SITE / video.name)
    print(f"site montado em {SITE}")


if __name__ == "__main__":
    main()
