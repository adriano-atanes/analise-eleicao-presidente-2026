# Auditoria — relatório de cobertura e desempenho

Processado em 2026-10-31T16:57:26+00:00 · motor 1.0.0 · esquema 1.0 · semente 2026.

## Cobertura

| Item | Processado |
|---|---|
| UFs (com exterior) | 28 |
| Municípios | 5.571 |
| Cidades no exterior | 186 |
| Zonas | 6.292 |
| Seções (100% do universo) | 499.248 |
| Seções com contas fechando | 499.207 |
| Seções sem votação registrada | 41 |

## Simulações

- 100.000 por região, UF e município (Dirichlet-Multinomial); 20.000 nos modelos multinomial e hierárquico.
- 20.000 por zona; 1.000.000 no passe profundo.

## Calibração

- Municípios com p < 0,05: 4,83% (esperado 5%).
- Municípios com p < 0,01: 0,90% (esperado 1%).

## Classificação dos municípios

| Classe | Municípios |
|---|---|
| Compatível com o modelo | 5641 |
| Inconclusivo | 112 |
| Incomum | 3 |
| Muito incomum | 1 |

## Desempenho

Tempo total: 73.9 s (4 processos).

| UF | Municípios | Zonas | Tempo (s) |
|---|---|---|---|
| MG | 853 | 898 | 306.03 |
| SP | 645 | 779 | 233.15 |
| RS | 497 | 522 | 174.02 |
| BA | 417 | 450 | 151.74 |
| PR | 399 | 421 | 149.15 |
| SC | 295 | 315 | 113.53 |
| PI | 224 | 230 | 86.63 |
| GO | 246 | 259 | 85.28 |
| MA | 217 | 223 | 84.52 |
| PB | 223 | 230 | 82.6 |
| CE | 184 | 205 | 73.42 |
| PE | 185 | 209 | 68.12 |
| RN | 167 | 172 | 62.9 |
| TO | 139 | 140 | 55.21 |
| PA | 144 | 160 | 52.69 |
| MT | 142 | 147 | 50.58 |
| ZZ | 186 | 186 | 47.37 |
| AL | 102 | 107 | 38.17 |
| RJ | 92 | 183 | 37.8 |
| MS | 79 | 88 | 33.86 |
| ES | 78 | 85 | 33.44 |
| SE | 75 | 77 | 29.88 |
| AM | 62 | 74 | 25.0 |
| RO | 52 | 56 | 21.38 |
| AC | 22 | 23 | 8.35 |
| RR | 15 | 16 | 5.89 |
| AP | 16 | 18 | 5.84 |
| DF | 1 | 19 | 1.97 |

## Testes

```
Ran 19 tests in 4.559s

OK
```
