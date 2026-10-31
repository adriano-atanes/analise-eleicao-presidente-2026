# Auditoria — relatório de cobertura e desempenho

Processado em 2026-10-31T10:24:51+00:00 · motor 1.0.0 · esquema 1.0 · semente 2026.

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

Tempo total: 569.8 s (4 processos).

| UF | Municípios | Zonas | Tempo (s) |
|---|---|---|---|
| MG | 853 | 898 | 306.15 |
| SP | 645 | 779 | 221.23 |
| RS | 497 | 522 | 173.98 |
| BA | 417 | 450 | 150.35 |
| PR | 399 | 421 | 144.39 |
| SC | 295 | 315 | 113.52 |
| PI | 224 | 230 | 86.46 |
| GO | 246 | 259 | 82.96 |
| MA | 217 | 223 | 77.47 |
| PB | 223 | 230 | 75.69 |
| CE | 184 | 205 | 67.16 |
| PE | 185 | 209 | 59.52 |
| RN | 167 | 172 | 58.77 |
| PA | 144 | 160 | 51.01 |
| TO | 139 | 140 | 50.73 |
| MT | 142 | 147 | 48.56 |
| ZZ | 186 | 186 | 40.87 |
| RJ | 92 | 183 | 34.57 |
| AL | 102 | 107 | 33.35 |
| MS | 79 | 88 | 31.52 |
| ES | 78 | 85 | 30.59 |
| SE | 75 | 77 | 27.38 |
| AM | 62 | 74 | 22.36 |
| RO | 52 | 56 | 20.35 |
| AC | 22 | 23 | 7.81 |
| AP | 16 | 18 | 5.99 |
| RR | 15 | 16 | 5.4 |
| DF | 1 | 19 | 1.9 |

## Testes

```
Ran 15 tests in 1.725s

OK
```
