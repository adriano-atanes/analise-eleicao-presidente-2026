"""Caminhos e constantes compartilhados pelos scripts."""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos"
PROCESSADOS = RAIZ / "dados" / "processados"
PORTAL_DADOS = RAIZ / "portal" / "dados"

ANO = 2026
URL_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
# pasta no CDN do TSE -> (zip, CSV de Presidente dentro do zip)
ARQUIVOS = {
    "votacao_secao": (f"votacao_secao_{ANO}_BR.zip", f"votacao_secao_{ANO}_BR.csv"),
    "detalhe_votacao_secao": (f"detalhe_votacao_secao_{ANO}.zip", f"detalhe_votacao_secao_{ANO}_BR.csv"),
    "votacao_candidato_munzona": (f"votacao_candidato_munzona_{ANO}.zip", f"votacao_candidato_munzona_{ANO}_BR.csv"),
    "detalhe_votacao_munzona": (f"detalhe_votacao_munzona_{ANO}.zip", f"detalhe_votacao_munzona_{ANO}_BR.csv"),
}

# Candidatos do 1º turno pelo número de urna. Os demais viram "Outros".
CANDIDATOS = {13: "Lula", 22: "Flávio", 14: "Renan", 70: "Cury", 55: "Caiado", 30: "Zema"}
NOMES_COMPLETOS = {
    "Lula": "Lula (PT)", "Flávio": "Flávio Bolsonaro (PL)", "Renan": "Renan Santos (Missão)",
    "Cury": "Augusto Cury (Avante)", "Caiado": "Ronaldo Caiado (PSD)", "Zema": "Zema (Novo)",
    "Outros": "Outros 6 candidatos",
}
BRANCO, NULO = 95, 96
# Todos os números válidos no 1º turno; qualquer outro (ex.: candidatura anulada) é nulo técnico.
VALIDOS = {13, 14, 16, 21, 22, 27, 29, 30, 35, 55, 70, 80}

# Opções de cada turno, na ordem usada na matriz de migração.
ORIGENS = ["Lula", "Flávio", "Renan", "Cury", "Caiado", "Zema", "Outros", "Branco", "Nulo", "Abst"]
DESTINOS = ["Lula", "Flávio", "Branco", "Nulo", "Abst"]

CHAVE_SECAO = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]

REGIOES = {
    "Norte": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MT", "MS"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
    "Exterior": ["ZZ"],
}
UF_REGIAO = {uf: r for r, ufs in REGIOES.items() for uf in ufs}
UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará",
    "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins", "ZZ": "Exterior",
}


def ler_csv_tse(caminho, **kw):
    return pd.read_csv(caminho, sep=";", encoding="latin1", **kw)
