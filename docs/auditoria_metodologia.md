# Auditoria — metodologia (Fase 1)

A Auditoria investiga matematicamente os resultados do 1º e do 2º turno da eleição presidencial de 2026 em qualquer
recorte geográfico: Brasil, região, estado, município, zona ou seção. Todo cálculo usa **100% das seções do recorte**.
A aleatoriedade existe apenas na geração dos cenários do Monte Carlo, nunca na seleção dos dados.

Nada aqui é, isoladamente, evidência de irregularidade. Probabilidades valem sob as premissas de cada modelo.

## 1. Dados

- Boletins de urna por seção do TSE (`votacao_secao`), preparados por `scripts/02_preparar_secoes.py`.
- Matrizes de transferência estimadas por `scripts/03_migracao.py`: inferência ecológica com restrição de simplex e
  encolhimento hierárquico (Brasil → UF → município), com bootstrap e análise de sensibilidade em `03b_sensibilidade.py`.
- Contagens por seção no portal (`portal/dados/secoes/<UF>.json`) e por município (`portal/dados/uf/<UF>.json`).

Categorias:

| 1º turno | 2º turno |
|---|---|
| Lula, Flávio Bolsonaro, demais candidatos (10), brancos, nulos, abstenção, aptos | Lula, Flávio Bolsonaro, brancos, nulos, abstenção, aptos |

## 2. Reconciliação

Para cada recorte valida-se

- comparecimento = votos nominais + brancos + nulos;
- eleitorado apto = comparecimento + abstenção;

e calcula-se a variação de cada categoria. A identidade-chave é: ganho conjunto dos finalistas + variação de
eliminados, brancos e nulos = variação do comparecimento.

## 3. Limites matemáticos

Modelo de transporte com totais de linha (origens do 1º turno) e de coluna (destinos do 2º turno) fixos.

- **Votos disponíveis sem tocar nos finalistas:** R = demais + brancos + nulos + abstenção do 1º turno + novos aptos.
- **Transferência mínima para cada finalista:** max(0, ganho).
- **Captação necessária:** ganho⁺ de Lula ÷ R.
- **Possível sem migração entre finalistas** se e só se ganho⁺(Lula) + ganho⁺(Flávio) ≤ R. Caso contrário, a migração
  mínima entre finalistas é ganho⁺ − R (verificado contra programação linear em `tests/test_auditoria.py`).
- **Retenção e células da matriz:** limites de Fréchet [max(0, linha + coluna − total), min(linha, coluna)].

## 4. Cenários extremos (hipóteses)

| Cenário | Hipótese |
|---|---|
| A | Transferência integral para Lula. |
| B | Transferência integral para Flávio. |
| C | Transferência proporcional aos finalistas no 1º turno. |
| D | Migração entre finalistas: mínimos necessários e máximos compatíveis. |
| E | Participação variável: entradas e saídas mínimas de eleitores entre turnos. |

“Viável” significa apenas que o cenário não contradiz a aritmética dos totais.

## 5. Modelos estatísticos e Monte Carlo

- **Evento avaliado:** parcela de Lula entre os finalistas no 2º turno, S = L₂ / (L₂ + F₂).
- **Probabilidade reportada:** P(|S_sim − E[S]| ≥ |S_obs − E[S]|), bicaudal, tão ou mais extremo.
- **Probabilidade do valor exato:** P(L₂ = observado), também calculada para mostrar a diferença. Todo valor exato é
  improvável em eleições grandes.

**Referência.** Cada unidade é comparada com a matriz do nível acima:

| Unidade | Matriz de referência |
|---|---|
| Região e UF | Brasil |
| Município | UF |
| Zona e seção | Município |

Origens do modelo: Lula, Flávio, demais (eliminados combinados pelo peso de cada um no recorte), brancos, nulos e
abstenção. Destinos: Lula, Flávio e outros (brancos, nulos e abstenção).

| Modelo | Descrição |
|---|---|
| Multinomial | Cada eleitor de cada origem segue a matriz de referência, sem dispersão extra. Ignora diferenças entre lugares e exagera a raridade. |
| Dirichlet-Multinomial (principal) | Em cada simulação, a linha da matriz de cada origem é sorteada de Dirichlet(α · p_ref). α é calibrado por método dos momentos para que os desvios padronizados das unidades irmãs (os municípios da mesma UF, as zonas da UF, as seções da UF) tenham variância 1. |
| Bayesiano hierárquico | Como o Dirichlet, mas com incerteza no hiperparâmetro: α é sorteado da distribuição bootstrap da calibração entre unidades irmãs. |
| Bootstrap | Empírico: proporção das unidades irmãs com desvio padronizado tão ou mais extremo. |

**Execução.**

- Simulações: 100.000 por região, UF e município; 20.000 por zona; 1.000.000 no passe profundo (Silva Jardim e os 20
  municípios mais distantes do esperado).
- Vetorizado com NumPy, paralelo por UF, semente configurável e semente por unidade derivada de SHA-256 (reprodutível
  independentemente da ordem).
- Cache incremental por UF em `dados/processados/auditoria_cache/`.

**Eventos raros.** Se nenhuma simulação for tão extrema, a probabilidade é extrapolada pela aproximação normal (marcada
com \*) e o limite superior de 95% de Clopper–Pearson é reportado. Nunca se reporta probabilidade zero. Intervalos de
95% acompanham todas as estimativas.

**Seções.** Simuladas no navegador (100.000 simulações, semente 2026), com α calibrado entre as seções da UF.

**Calibração (posterior predictive check).** Distribuição dos valores de probabilidade dos municípios. Sob um modelo
bem especificado ela é aproximadamente uniforme: cerca de 5% abaixo de 0,05 e 1% abaixo de 0,01.

## 6. Classificação e múltiplas comparações

Valores q de Benjamini–Hochberg entre os municípios do país (e, separadamente, entre zonas e entre UFs):

| Classe | Critério |
|---|---|
| Muito incomum | q < 0,01 |
| Incomum | q < 0,10 |
| Compatível com o modelo | demais |
| Inconclusivo | menos de 300 votos nos finalistas, ou unidade sem votação registrada (seções no exterior sem boletim) |
| Matematicamente inviável sob restrições explícitas | identidade contábil que não confere |

## 7. Apresentação

- Probabilidade em **1 em N** (1/p), com o valor numérico guardado no JSON.
- **Mega-Sena:** P_mega = 1 / 50.063.860 (aposta simples). Razão R = P_mega / P_evento e expoente n = log P_evento / log P_mega.
  A comparação só é exibida quando o evento ocorreu ao menos 10 vezes nas simulações (erro relativo ≲ 30%).

## 8. Contrato de dados (schema 1.0)

| Arquivo | Conteúdo |
|---|---|
| `portal/dados/auditoria/nacional.json` | metadados (fonte, versão do motor, data, tempo, semente, simulações, regras); Brasil, regiões e UFs (reconciliação, limites, cenários, Monte Carlo com os quatro modelos, histograma, sensibilidade, FDR, classificação); calibração; qualidade dos dados; ranking de todos os municípios. |
| `portal/dados/auditoria/uf/<UF>.json` | os mesmos campos para cada município e cada zona da UF, mais o α calibrado das seções. |
| `portal/dados/auditoria/municipios.csv` e `ufs.csv` | exportação tabular. |

Identificadores estáveis: sigla da UF, código TSE do município, `<código>-<zona>` para zonas. A estrutura está pronta
para leitura por agentes em uma fase futura; nenhuma integração com IA foi feita nesta fase.

## 9. Testes

`python -m unittest discover -s tests` cobre:

- identidades contábeis (Silva Jardim);
- limites em forma fechada contra programação linear (300 tabelas aleatórias);
- limites de Fréchet;
- reprodutibilidade com semente;
- momentos analíticos contra simulação;
- calibração (recupera α e produz valores p uniformes, teste KS);
- eventos raros sem probabilidade zero;
- valor exato contra extremo;
- formatação 1 em N, Mega-Sena e FDR (contra `scipy`);
- contrato do JSON publicado.

## 10. Limitações conhecidas

- A matriz de referência é uma estimativa ecológica. Desvios grandes podem refletir características locais que a
  matriz do nível acima não captura (perfil do eleitorado, lideranças locais), não necessariamente problemas nos dados.
- O backtesting com eleições anteriores no nível de seção não foi feito nesta fase. A calibração é verificada
  internamente pela distribuição dos valores p.
