# Eleição Presidencial 2026: análise do 1º e do 2º turno

Análise dos resultados oficiais do TSE para Presidente da República em 2026 (1º turno em 04/10, 2º turno em 25/10), com:

- votos de todos os candidatos no 1º turno;
- estimativa de **migração de votos** do 1º para o 2º turno (para onde foram os eleitores de cada candidato eliminado, dos brancos, dos nulos e de quem se absteve);
- comparecimento, abstenção, brancos e nulos nos dois turnos;
- detalhamento por estado, município, local de votação e seção eleitoral.

O resultado é um portal estático (`portal/`) com gráficos interativos. Os relatórios em PDF (`relatorio/`, scripts 05, 09 e 11) foram descontinuados: o portal é a versão atualizada da análise. As fontes IBM Plex em `relatorio/fontes/` são licenciadas sob a SIL Open Font License.

## Como reproduzir

```bash
pip install -r requirements.txt
cd scripts
python 01_baixar_dados.py      # ~1 GB do CDN do TSE → dados/brutos/ (fora do git)
python 02_preparar_secoes.py   # uma linha por seção, dois turnos lado a lado; confere com os totais oficiais
python 03_migracao.py          # matriz de migração Brasil/estados/municípios (~10 min)
python 03b_sensibilidade.py    # mesma estimativa com zonas eleitorais, para comparação
python 04_gerar_portal.py      # JSONs do portal → portal/dados/
python 05_relatorio_pdf.py     # relatório em PDF → relatorio/relatorio_eleicao_presidente_2026.pdf
python 07_historico.py         # Presidente 2002–2022 (TSE), Brasil e municípios → dados/processados/historico*.{json,parquet}
python 08_consistencia.py           # testes de consistência por seção → dados/processados/consistencia.json
python 09_relatorio_estatistico.py  # análise estatística da virada → relatorio/analise_estatistica_2026.pdf
python 10_dados_auditoria.py   # dados da visão Auditoria do portal → portal/dados/auditoria.json
python 13_ideologia_migracao.py       # eleitores dos eliminados por campo ideológico, 2002–2026 → portal/dados/ideologia.json
python 12_comportamento_historico.py  # comportamento 2026 × 2002–2022 → portal/dados/comportamento.json
python 11_relatorio_auditoria.py    # relatório de auditoria → relatorio/auditoria_eleicao_2026.pdf
python 14_malha.py                  # malha dos municípios (IBGE via geodata-br; requer mapshaper) → portal/dados/mapa/brasil.json
python 15_insights.py               # perfil do eleitorado, 2022 × 2026, curva da apuração, coordenadas dos locais
python 16_logs_urnas.py             # logs de todas as urnas (~220 GB lidos em stream, 1 a 3 horas)
python 17_analise_logs.py           # consolida os logs → portal/dados/logs*.json
python 18_apuracao_animada.py       # parcial na ordem de chegada × ordem sorteada → portal/dados/apuracao.json
python 19_virada_falhas.py          # verificação: virada da apuração × falhas no log das urnas → portal/dados/virada_falhas.json
python 20_votos_eleitorado.py       # verificação: votos de Lula × eleitorado por município e lista que circula nas redes → portal/dados/votos_eleitorado.json
python 21_boletins.py               # boletim de urna: votos dos demais candidatos do 1º turno e endereço dos locais → portal/dados/bu/<UF>.json
python 22_auditoria.py              # Auditoria: reconciliação, limites, cenários e Monte Carlo de todas as UFs, municípios e zonas
                                   #   (opções: --sim 100000 --sim-zona 20000 --seed 2026 --forcar; cache em dados/processados/auditoria_cache)
python 23_transferencia.py          # teste de transferência dos eliminados (1º × 2º turno de cada UF, município, zona e seção) → portal/dados/auditoria/transferencia.json
python -m unittest discover -s tests   # testes do motor da Auditoria (scripts/auditoria_motor.py)
node 18b_video_apuracao.js apuracao-video-1-sorteio <pasta> 600 90   # quadros do vídeo (portal servido em localhost:8765);
#   depois: ffmpeg -framerate 30 -i <pasta>/q%04d.png -c:v libx264 -pix_fmt yuv420p portal/apuracao_1turno.mp4
```

## Rodar o portal localmente

Os dados do portal já estão no repositório; não é preciso baixar nada do TSE nem instalar pacotes (só Python 3).

```bash
git clone https://github.com/adriano-atanes/analise-eleicao-presidente-2026.git
cd analise-eleicao-presidente-2026
python3 scripts/06_montar_site.py        # monta o site em site/
python3 -m http.server 8000 -d site      # serve o site
```

Abra <http://localhost:8000> (auditoria em <http://localhost:8000/#auditoria>). No Windows, use `python` no lugar de `python3`.
O portal precisa ser servido por HTTP: abrir o `index.html` direto pelo navegador (`file://`) não carrega os dados.

## GitHub Pages

O workflow `.github/workflows/pages.yml` publica o portal a cada push na `main` que altere `portal/` ou o relatório. Ele roda `scripts/06_montar_site.py`, que acrescenta o esqueleto HTML ao `portal/index.html` e copia os dados e o PDF para `site/`.

Para ativar: **Settings → Pages → Build and deployment → Source: GitHub Actions**. Depois, rode o workflow em **Actions → Publicar portal no GitHub Pages → Run workflow**.

## Fontes

Portal de Dados Abertos do TSE (`https://cdn.tse.jus.br/estatistica/sead/odsele/`), só os arquivos de Presidente (`*_BR.csv`):

| Arquivo | Conteúdo |
|---|---|
| `votacao_secao_2026_BR.csv` | votos por candidato, branco e nulo em cada seção |
| `detalhe_votacao_secao_2026_BR.csv` | aptos, comparecimento e abstenção por seção, local de votação |
| `votacao_candidato_munzona_2026_BR.csv` | votos por candidato por município/zona (conferência e lista completa de candidatos) |
| `detalhe_votacao_munzona_2026_BR.csv` | totais oficiais por município/zona (conferência) |

A soma das 499.248 seções confere exatamente com os totais oficiais. Os 5.246 "nulos técnicos" do 1º turno são contados como nulos.

## Metodologia da migração

O voto é secreto, então a migração é uma **estimativa** (inferência ecológica). Para cada seção *i*:

```
proporção no 2º turno (destino j)  =  Σₖ  proporção no 1º turno (origem k) × B[k, j]
```

`B[k, j]` é a fração dos eleitores da origem *k* (Lula, Flávio, Renan, Cury, Caiado, Zema, outros, branco, nulo, abstenção) que foi para o destino *j* (Lula, Flávio, branco, nulo, abstenção). B é estimada por mínimos quadrados ponderados pelo eleitorado, com cada linha somando 1 e sem valores negativos.

- **Estados:** uma matriz por estado, com as suas seções. Brasil e regiões somam os fluxos estaduais.
- **Municípios:** a matriz é puxada para a do estado em proporção ao número de seções (equivale a 30 seções fictícias com a composição do município votando como o estado).
- **Incerteza:** bootstrap das seções (intervalo de 90%), que mede só a variação amostral. A premissa do modelo é a maior fonte de incerteza; por isso o portal também mostra a estimativa feita com zonas eleitorais. Onde as duas divergem, leia o valor como uma faixa.

## Auditoria (Fase 1)

A página Auditoria tem quatro visões que compartilham o mesmo recorte geográfico (Brasil → região → estado → município → zona → seção):
Panorama nacional, Reconciliação e fluxo, Monte Carlo e Simulador de cenários. O processamento pesado roda offline em
`scripts/22_auditoria.py` (motor em `scripts/auditoria_motor.py`) e é publicado como JSON versionado em `portal/dados/auditoria/`.
Metodologia completa em [docs/auditoria_metodologia.md](docs/auditoria_metodologia.md).
