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
- **Saldo líquido dos eliminados (indicador principal da origem dos votos).** Brancos, nulos e abstenção só fornecem
  votos, no saldo, se diminuíram entre os turnos.

  ```
  mínimo dos eleitores dos eliminados que precisa ter ido para Lula =
      (ganho de Lula − brancos/nulos liberados − abstenção liberada) ÷ votos dos eliminados
  ```

  A conta supõe que nenhum eleitor de Flávio migrou. Também se calcula ganho de Flávio ÷ votos dos eliminados e a posição
  do recorte entre os municípios do estado e do país. O total bruto R (que soma todos os faltosos do 1º turno) continua
  disponível, mas superestima os votos que de fato estavam livres quando a abstenção sobe.

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

> **No portal:** a Auditoria mostra apenas o resultado pronto e exato de cada recorte (seção 5b). O Monte Carlo
> abaixo continua no processamento offline (`22_auditoria.py`) e no contrato JSON, mas não é exibido nem executado no navegador.

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

**Referência contrafactual histórica.** A matriz de referência é estimada com os dados de 2026; ela responde se a
unidade se comporta como o resto do nível acima, não se esse nível se comporta como em eleições anteriores. Por isso a
visão Monte Carlo permite trocar a referência: a linha “demais” é refeita com a parcela dos eleitores dos eliminados
que escolheu o candidato do PT entre os finalistas em 2022 ou 2018 (Brasil, `scripts/13_ideologia_migracao.py`).

| Grupo | Candidatos de 2026 |
|---|---|
| Direita | Renan Santos, Ronaldo Caiado, Zema |
| Centro | Augusto Cury |
| Outros | metade esquerda, metade direita |

Retenção, brancos, nulos e abstenção continuam vindo da matriz de 2026. A tabela “esperado × observado” mostra os
votos esperados de cada categoria sob a referência escolhida.

**Execução.**

- Simulações: 100.000 por região, UF e município; 20.000 por zona; 1.000.000 no passe profundo (os 20
  municípios mais distantes do esperado).
- Vetorizado com NumPy, paralelo por UF, semente configurável e semente por unidade derivada de SHA-256 (reprodutível
  independentemente da ordem).
- Cache incremental por UF em `dados/processados/auditoria_cache/`.

**Eventos raros.** Se nenhuma simulação for tão extrema, a probabilidade é extrapolada pela aproximação normal (marcada
com \*) e o limite superior de 95% de Clopper–Pearson é reportado. Nunca se reporta probabilidade zero. Intervalos de
95% acompanham todas as estimativas.

**Calibração (posterior predictive check).** Distribuição dos valores de probabilidade dos municípios. Sob um modelo
bem especificado ela é aproximadamente uniforme: cerca de 5% abaixo de 0,05 e 1% abaixo de 0,01.

## 5b. Teste de transferência dos eliminados (1º × 2º turno do próprio recorte)

`scripts/23_transferencia.py`, para todos os estados, municípios, zonas e seções. No portal, o teste é recalculado na
hora, de forma exata, para qualquer recorte e aparece no topo da visão “Resultado do recorte” como uma ficha pronta: variação
de Lula, Flávio e comparecimento; votos dos eliminados; mínimo que precisa ter ido para Lula; chance sob eleitores
independentes (referência 2026 do nível acima) e a posição no país; e chance com a variação real
(referência do estado). O segundo cartão da ficha não mostra essa chance: mostra a contagem direta, sem modelo, da posição do
recorte entre as unidades do mesmo nível no estado (por exemplo, “15º de 92 municípios”), contando quantas tiveram K/E igual
ou maior. A chance com variação real fica na tabela de detalhes.

**Contagens.**

- E = votos dos eliminados no 1º turno.
- K = mínimo desses votos que precisa ter ido para Lula, pelo saldo:

  ```
  K = ganho de Lula − brancos/nulos liberados − abstenção liberada
  ```

  A conta supõe que nenhum eleitor de Flávio migrou. Se K > E, o saldo só se explica com migração entre finalistas.

> **Referência principal: perfil político (2026).** Cada unidade é comparada com os municípios do país que tiveram a mesma
> parcela de Flávio nos votos válidos do 1º turno (faixas de 5 pontos). μ da faixa = soma de K ÷ soma de E entre esses
> municípios (com E ≥ 200). Onde a direita é forte, espera-se que os eleitores dos eliminados vão menos para Lula; a referência
> do próprio estado mistura lugares de perfis diferentes e por isso diluía esse efeito. A ficha mostra a chance (Binomial com
> o μ da faixa), a posição entre as unidades do mesmo nível e da mesma faixa (contagem direta; para seções fora da lista, pelos
> percentis da faixa) e, como comparação secundária, a posição entre as unidades do estado. A classificação (FDR) usa a
> Beta-Binomial com o μ da faixa e ρ calibrado entre as unidades da mesma faixa. Campos: `f1`, `muPerf`, `posPerf`, `nPerf`,
> `indPerf`, `disPerf`; metadados `perfil` e `perfil_quantis`.

> **No portal, a referência é sempre 2026:** município, zona e seção são comparados com o padrão do próprio estado no
> 2º turno de 2026 (μ do estado); estado e região, com o padrão do Brasil em 2026. A referência de 2022 continua no JSON
> (`ind22`, `dis22`), mas não é exibida.

**Probabilidade avaliada.** μ é a probabilidade de um eleitor dos eliminados votar em Lula: a fração que escolhe um
finalista (matriz do estado em 2026) vezes a parcela de Lula entre esses. Referências: comportamento de 2022 por campo
ideológico, ou do próprio estado em 2026. Calcula-se P(X ≥ K) por duas leituras:

| Leitura | Modelo |
|---|---|
| Eleitor independente | Binomial(E, μ). |
| Com variação real | Beta-Binomial(E, μ, ρ), com ρ (correlação entre eleitores do mesmo recorte) calibrado por método dos momentos por UF e por nível, com a variação observada de K/E entre as unidades irmãs. |

Classificação com FDR sobre a leitura com variação real (referência: estado).

**Limites.** K é um mínimo, não uma contagem observada: as mesmas variações líquidas aparecem com fluxos brutos
compensatórios (eleitores de Flávio que faltaram no 2º turno, faltosos do 1º turno que votaram em Lula). A leitura
independente ignora a correlação entre eleitores do mesmo lugar e por isso produz probabilidades extremamente pequenas
para quase qualquer desvio.

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
- Probabilidades muito pequenas aparecem como potência de 10 (por exemplo, 1 em 10¹⁵⁶), com o log10 guardado no JSON.

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

- identidades contábeis;
- limites em forma fechada contra programação linear (300 tabelas aleatórias);
- limites de Fréchet;
- reprodutibilidade com semente;
- momentos analíticos contra simulação;
- calibração (recupera α e produz valores p uniformes, teste KS);
- eventos raros sem probabilidade zero;
- valor exato contra extremo;
- formatação 1 em N e FDR (contra `scipy`);
- contrato do JSON publicado.

## 10. Limitações conhecidas

- A matriz de referência é uma estimativa ecológica. Desvios grandes podem refletir características locais que a
  matriz do nível acima não captura (perfil do eleitorado, lideranças locais), não necessariamente problemas nos dados.
- O backtesting com eleições anteriores no nível de seção não foi feito nesta fase. A calibração é verificada
  internamente pela distribuição dos valores p.
