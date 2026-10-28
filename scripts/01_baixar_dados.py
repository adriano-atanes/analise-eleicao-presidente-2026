"""Baixa os ZIPs do Portal de Dados Abertos do TSE e extrai só os CSVs de Presidente (_BR.csv).

Os ZIPs somam ~1 GB; os CSVs extraídos ficam em dados/brutos/ (fora do git).
"""
import shutil
import urllib.request
import zipfile

from comum import ARQUIVOS, BRUTOS, URL_BASE


def main():
    BRUTOS.mkdir(parents=True, exist_ok=True)
    for pasta, (zip_nome, csv) in ARQUIVOS.items():
        if (BRUTOS / csv).exists():
            print(f"já existe: {csv}")
            continue
        url = f"{URL_BASE}/{pasta}/{zip_nome}"
        zip_path = BRUTOS / zip_nome
        print(f"baixando {url}")
        with urllib.request.urlopen(url) as r, open(zip_path, "wb") as f:
            shutil.copyfileobj(r, f)
        with zipfile.ZipFile(zip_path) as z:
            z.extract(csv, BRUTOS)
        zip_path.unlink()
        print(f"extraído: {csv}")


if __name__ == "__main__":
    main()
