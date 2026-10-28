"""Malha dos municípios e estados para os mapas do portal (portal/dados/mapa/brasil.json).

Fontes: geometria municipal do IBGE redistribuída pelo projeto geodata-br (github.com/tbrugz/geodata-br)
e tabela de correspondência entre códigos do TSE e do IBGE (github.com/betafcc/Municipios-Brasileiros-TSE).
Simplifica as fronteiras com o mapshaper (Node.js: `npm install -g mapshaper` ou defina a variável
MAPSHAPER) e grava um TopoJSON com duas camadas: municipios (propriedade tse = código TSE) e estados.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import urllib.request

from comum import BRUTOS, PORTAL_DADOS

UF_IBGE = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB",
           26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR", 42: "SC", 43: "RS", 50: "MS",
           51: "MT", 52: "GO", 53: "DF"}
URL_GEO = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-{}-mun.json"
URL_COD = "https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/master/municipios_brasileiros_tse.csv"
GEO = BRUTOS / "geo"


def baixar(url):
    with urllib.request.urlopen(url) as r:
        return r.read()


def main():
    GEO.mkdir(parents=True, exist_ok=True)
    cod = {r["codigo_ibge"]: (int(r["codigo_tse"]), r["uf"]) for r in csv.DictReader(io.StringIO(baixar(URL_COD).decode("utf-8")))}
    feats, sem = [], []
    for ibge_uf, uf in UF_IBGE.items():
        arq = GEO / f"{ibge_uf}.json"
        if not arq.exists():
            arq.write_bytes(baixar(URL_GEO.format(ibge_uf)))
        for f in json.loads(arq.read_text())["features"]:
            ibge = f["properties"]["id"]
            if ibge not in cod:
                sem.append((uf, f["properties"]["name"]))
                continue
            f["properties"] = {"tse": cod[ibge][0], "uf": uf, "nome": f["properties"]["name"]}
            feats.append(f)
    print(f"{len(feats)} municípios com geometria; sem código TSE: {sem}")
    entrada = GEO / "municipios.geojson"
    entrada.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    saida = PORTAL_DADOS / "mapa" / "brasil.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    ms = os.environ.get("MAPSHAPER") or shutil.which("mapshaper") or "mapshaper"
    subprocess.run([ms, str(entrada), "-simplify", "5%", "weighted", "keep-shapes", "-rename-layers", "municipios",
                    "-dissolve", "uf", "+", "name=estados", "-o", "format=topojson", "quantization=100000", "target=*", str(saida)], check=True)
    print(f"{saida}: {saida.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
