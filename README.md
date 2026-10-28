# Eleição Presidencial 2026: análise do 1º e do 2º turno

Análise dos resultados oficiais do TSE para Presidente da República em 2026 (1º turno em 04/10, 2º turno em 25/10), com:

- votos de todos os candidatos no 1º turno;
- estimativa de **migração de votos** do 1º para o 2º turno (para onde foram os eleitores de cada candidato eliminado, dos brancos, dos nulos e de quem se absteve);
- comparecimento, abstenção, brancos e nulos nos dois turnos;
- detalhamento por estado, município, local de votação e seção eleitoral.

O resultado é um portal estático (`portal/`) com gráficos interativos e um relatório em PDF (`relatorio/relatorio_eleicao_presidente_2026.pdf`). As fontes IBM Plex em `relatorio/fontes/` são licenciadas sob a SIL Open Font License.

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
```

Para abrir o portal localmente: `python -m http.server -d portal` e acesse <http://localhost:8000>.

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
