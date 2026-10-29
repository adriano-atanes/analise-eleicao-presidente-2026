"""Verificação: há municípios em que Lula teve mais votos que eleitores (ou habitantes)?

Para cada município: eleitores aptos, comparecimento e votos de Lula nos dois turnos (boletins de urna do TSE).
O teto de votos de um município é o eleitorado apto: só vota quem está inscrito na seção, e em cada seção
votos ≤ comparecimento ≤ aptos. Na maioria dos municípios, a população (IBGE) é bem maior que o eleitorado apto.

Também confere, nome a nome, a lista de cidades que circula nas redes ("cidades que até os mortos votaram em Lula").

Saída: portal/dados/votos_eleitorado.json
"""
import json
import unicodedata

import pandas as pd

from comum import PORTAL_DADOS, PROCESSADOS

# lista como circula (nome e UF como escritos, habitantes e votos de Lula alegados)
ALEGADO = [("Nossa Senhora da Glória", "SE", 3053, 4615), ("Porto da Pedra", "PE", 6122, 8090), ("Poço das Antas", "PE", 4342, 5873),
           ("Xique Xique", "BA", 43548, 64805), ("Barragem", "BA", 25687, 31338), ("Nova Liberdade", "BA", 11026, 16192),
           ("Novaçores", "BA", 9622, 12351), ("Guananbim", "BA", 19764, 22538), ("Joaçaba", "BA", 6142, 6984), ("Antas", "BA", 11434, 18001)]
# grafias que correspondem a um município existente
GRAFIA = {"guananbim": "guanambi"}


def norm(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().replace("-", " ")
    return " ".join(s.split())


def main():
    s = pd.read_parquet(PROCESSADOS / "secoes.parquet")
    cols = ["Aptos_1", "Comp_1", "Lula_1", "Aptos_2", "Comp_2", "Lula_2", "Flávio_2"]
    m = s.groupby(["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"], as_index=False)[cols].sum()
    m = m[m.SG_UF != "ZZ"]
    m["lula2_aptos_pct"] = 100 * m.Lula_2 / m.Aptos_2
    m["comp2_pct"] = 100 * m.Comp_2 / m.Aptos_2
    # checagens nacionais (municípios e seções)
    sec = s[s.SG_UF != "ZZ"]
    checks = {
        "municipios": int(len(m)),
        "mun_lula_maior_que_aptos": int((m.Lula_2 > m.Aptos_2).sum() + (m.Lula_1 > m.Aptos_1).sum()),
        "mun_comp_maior_que_aptos": int((m.Comp_2 > m.Aptos_2).sum() + (m.Comp_1 > m.Aptos_1).sum()),
        "secoes": int(len(sec)),
        "secoes_comp_maior_que_aptos": int((sec.Comp_2 > sec.Aptos_2).sum() + (sec.Comp_1 > sec.Aptos_1).sum()),
        "secoes_lula_maior_que_comp": int((sec.Lula_2 > sec.Comp_2).sum() + (sec.Lula_1 > sec.Comp_1).sum()),
        "max_lula2_aptos_pct": float(m.lula2_aptos_pct.max()),
        "max_comp2_pct": float(m.comp2_pct.max()),
    }
    top = m.sort_values("lula2_aptos_pct", ascending=False).head(25)
    checks["top_lula_aptos"] = [[r.SG_UF, int(r.CD_MUNICIPIO), r.NM_MUNICIPIO, int(r.Aptos_2), int(r.Comp_2), int(r.Lula_2), float(r.lula2_aptos_pct)] for r in top.itertuples()]
    # lista alegada
    idx = {}
    for r in m.itertuples():
        idx.setdefault(norm(r.NM_MUNICIPIO), []).append(r)
    lista = []
    for nome, uf, hab, votos in ALEGADO:
        n = GRAFIA.get(norm(nome), norm(nome))
        cands = idx.get(n, [])
        no_uf = [c for c in cands if c.SG_UF == uf]
        item = {"nome": nome, "uf": uf, "habitantes_alegado": hab, "lula_alegado": votos}
        if no_uf:
            c = no_uf[0]
            item.update({"situacao": "existe" if n == norm(nome) else "grafia", "nome_tse": c.NM_MUNICIPIO, "cod": int(c.CD_MUNICIPIO), "aptos": int(c.Aptos_2),
                         "comparecimento": int(c.Comp_2), "lula_1": int(c.Lula_1), "lula_2": int(c.Lula_2), "flavio_2": int(c.Flávio_2)})
        else:
            item["situacao"] = "outro_estado" if cands else "nao_existe"
            item["outros"] = [[c.SG_UF, int(c.CD_MUNICIPIO), c.NM_MUNICIPIO, int(c.Aptos_2), int(c.Lula_2)] for c in cands]
        lista.append(item)
    out = {"checagens": checks, "lista": lista}
    with open(PORTAL_DADOS / "votos_eleitorado.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    print({k: v for k, v in checks.items() if k != "top_lula_aptos"})
    print(checks["top_lula_aptos"][:5])
    for i in lista:
        print(i)


if __name__ == "__main__":
    main()
