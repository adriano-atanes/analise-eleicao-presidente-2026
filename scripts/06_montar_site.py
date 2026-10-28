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
<meta name="description" content="Resultado oficial do TSE para Presidente 2026 nos dois turnos, migração estimada de votos e detalhamento até a seção eleitoral.">
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
    for pdf in ("relatorio_eleicao_presidente_2026.pdf", "analise_estatistica_2026.pdf", "auditoria_eleicao_2026.pdf"):
        shutil.copy(RAIZ / "relatorio" / pdf, SITE / pdf)
    print(f"site montado em {SITE}")


if __name__ == "__main__":
    main()
