"""Monta uma tabela com uma linha por seção eleitoral e os dois turnos lado a lado.

Colunas por turno t (sufixo _1 / _2): votos de cada candidato, Branco, Nulo,
Abst (abstenções), Aptos e Comp (comparecimento). Também guarda o local de votação.
Confere os totais contra o arquivo agregado por município/zona.
Saída: dados/processados/secoes.parquet
"""
import pandas as pd

from comum import ARQUIVOS, BRANCO, BRUTOS, CANDIDATOS, CHAVE_SECAO, NULO, PROCESSADOS, UF_REGIAO, VALIDOS, ler_csv_tse


def votos_por_secao():
    cols = CHAVE_SECAO + ["NR_TURNO", "NR_VOTAVEL", "QT_VOTOS"]
    partes = []
    for bloco in ler_csv_tse(BRUTOS / ARQUIVOS["votacao_secao"][1], usecols=cols, chunksize=3_000_000):
        bloco["opcao"] = bloco.NR_VOTAVEL.map({**CANDIDATOS, BRANCO: "Branco", NULO: "Nulo"}).fillna("Outros")
        bloco.loc[~bloco.NR_VOTAVEL.isin(VALIDOS | {BRANCO, NULO}), "opcao"] = "Nulo"
        partes.append(bloco.groupby(CHAVE_SECAO + ["NR_TURNO", "opcao"]).QT_VOTOS.sum())
    v = pd.concat(partes).groupby(level=list(range(6))).sum()
    return v.unstack(["NR_TURNO", "opcao"], fill_value=0)


def detalhe_por_secao():
    cols = CHAVE_SECAO + ["NM_MUNICIPIO", "NR_TURNO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
                          "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]
    d = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_secao"][1], usecols=cols)
    locais = d.drop_duplicates(CHAVE_SECAO).set_index(CHAVE_SECAO)[["NM_MUNICIPIO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]]
    num = d.groupby(CHAVE_SECAO + ["NR_TURNO"])[["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]].sum()
    return locais, num.unstack("NR_TURNO", fill_value=0)


def main():
    votos = votos_por_secao()
    locais, num = detalhe_por_secao()
    s = locais.copy()
    for t in (1, 2):
        for opcao in votos[t].columns:
            s[f"{opcao}_{t}"] = votos[t][opcao]
        s[f"Aptos_{t}"] = num[("QT_APTOS", t)]
        s[f"Comp_{t}"] = num[("QT_COMPARECIMENTO", t)]
        s[f"Abst_{t}"] = num[("QT_ABSTENCOES", t)]
    s = s.fillna(0)
    numericas = [c for c in s.columns if c[-2:] in ("_1", "_2")]
    s[numericas] = s[numericas].astype("int64")
    s = s.reset_index()
    s.insert(0, "REGIAO", s.SG_UF.map(UF_REGIAO))

    # Conferência com os totais oficiais por município/zona
    cand = ler_csv_tse(BRUTOS / ARQUIVOS["votacao_candidato_munzona"][1])
    det = ler_csv_tse(BRUTOS / ARQUIVOS["detalhe_votacao_munzona"][1])
    for t in (1, 2):
        oficial = cand[cand.NR_TURNO == t].groupby(cand.NR_CANDIDATO.map(CANDIDATOS).fillna("Outros")).QT_VOTOS_NOMINAIS_VALIDOS.sum()
        dt = det[det.NR_TURNO == t]
        oficial["Branco"], oficial["Nulo"] = dt.QT_VOTOS_BRANCOS.sum(), dt.QT_TOTAL_VOTOS_NULOS.sum()
        oficial["Abst"], oficial["Aptos"] = dt.QT_ABSTENCOES.sum(), dt.QT_APTOS.sum()
        for k, val in oficial.items():
            secao = s[f"{k}_{t}"].sum() if f"{k}_{t}" in s else 0
            flag = "ok" if secao == val else f"DIFERENÇA {secao - val:+,}"
            print(f"turno {t} {k:7s} oficial={val:>12,} seções={secao:>12,}  {flag}")

    PROCESSADOS.mkdir(parents=True, exist_ok=True)
    s.to_parquet(PROCESSADOS / "secoes.parquet", index=False)
    print(f"{len(s):,} seções salvas em {PROCESSADOS / 'secoes.parquet'}")


if __name__ == "__main__":
    main()
