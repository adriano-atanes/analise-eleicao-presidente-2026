"""Processa os logs de todas as urnas (1º e 2º turno) publicados pelo TSE.

Fonte: "Arquivos transmitidos para totalização" (dadosabertos.tse.jus.br), um ZIP por estado e
turno com boletim, imagem do boletim, log, registro digital do voto e assinaturas de cada seção:
  https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_<t>t_<UF>.zip

Os ZIPs somam ~220 GB. Para não precisar de disco, cada ZIP é lido enquanto é baixado (stream) e
só os logs são abertos. De cada log, apenas os eventos do dia da eleição do turno são usados.

Por seção e turno grava: urnas (números de série) e modelo, reinícios, contingência (troca de urna),
horários (ligada, zerésima, pronta, primeiro e último voto, encerramento, boletim), votos
registrados no log, tipo de habilitação dos eleitores, tempo de votação, votos após o horário e
quantidade de alertas e erros. Também acumula, por estado e turno, todas as mensagens de alerta e
erro. Saída: dados/processados/logs/<turno>_<UF>.parquet e .json (retoma de onde parou).

Uso: python 16_logs_urnas.py [UF ...]   (padrão: todos os estados, os dois turnos, 4 em paralelo)
"""
import collections
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from multiprocessing import Pool

import pandas as pd
from stream_unzip import stream_unzip

from comum import PROCESSADOS

URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_{t}t_{uf}.zip"
DIA = {1: "04/10/2026", 2: "25/10/2026"}
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR",
       "RS", "SC", "SE", "SP", "TO", "ZZ"]
# diferença do horário local para o de Brasília (votação das 8h às 17h de Brasília em todo o país)
FUSO = {"AC": -2, "AM": -1, "RR": -1, "RO": -1, "MT": -1, "MS": -1}
SAIDA = PROCESSADOS / "logs"
NOME = re.compile(r"o\d{5}([a-z]{2})(\d{5})(\d{4})(\d{4})-log\.jez$")
HAB = re.compile(r"Tipo de habilitação do eleitor \[(.+?)\]")
MODELO = re.compile(r"Identificação do Modelo de Urna: (UE\d+)")
NUM = re.compile(r"\d+")


def segundos(hhmmss):
    h, m, s = hhmmss.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


# contadores de mensagens do dia (nome → teste sobre a mensagem); a lista vem do catálogo de mensagens dos logs
CONTA = {
    "id_cpf": lambda m: m == "Identificador digitado pelo mesário foi: (CPF)",
    "id_titulo": lambda m: m == "Identificador digitado pelo mesário foi: (Título de eleitor)",
    "biometria_nao_confere": lambda m: m.startswith("Digital capturada não corresponde a digital do eleitor"),
    "biometria_4a_tentativa": lambda m: m.startswith("Número de tentativas de reconhecimento do dedo. Tentativa [4]"),
    "ano_nasc_confere": lambda m: m == "Ano de nascimento digitado é igual ao do cadastro" or m == "Dado digitado confere",
    "ano_nasc_diferente": lambda m: m == "Ano de nascimento digitado é diferente do cadastro" or m == "Dado digitado não confere",
    "eleitor_ja_votou": lambda m: m == "O eleitor identificado já votou",
    "eleitor_nao_encontrado": lambda m: m == "Eleitor não encontrado para o identificador informado",
    "eleitor_impedido": lambda m: m.startswith("Eleitor impedido"),
    "correcoes": lambda m: m == "Eleitor corrigiu na tela de confirmação de candidato",
    "suspenso_sem_votar": lambda m: m == "Eleitor foi suspenso e não confirmou nenhum voto",
    "sem_atividade": lambda m: m.startswith("Eleitor sem atividade"),
    "justificativas": lambda m: m == "Justificativa recebida",
    "audio_cadastro": lambda m: m == "Áudio ativado conforme cadastro",
    "bateria_critica": lambda m: "CRÍTICA" in m or "carga crítica" in m or m.startswith("Tempo limite de espera usando bateria"),
    "encerr_cedo_tentativa": lambda m: m.startswith("Encerramento só pode ser solicitado"),
    "encerr_abortado": lambda m: m == "Procedimento de encerramento abortado" or m == "Operador cancelou o encerramento da votação",
    "encerr_com_presentes": lambda m: m == "Todas as pessoas presentes já votaram? NÃO",
    "impressora_falha": lambda m: m.startswith("Impressora atolada") or m.startswith("Impressora com falha") or m.startswith("Impressora desconectada"),
    "leitor_biometrico_erro": lambda m: "biometric reader" in m or "image acquisition" in m or "Falha na captura da digital" in m or "/dev/uescan" in m,
    "log_me_corrompido": lambda m: m.startswith("Identificado arquivo de log corrompido"),
    "mesarios_registrados": lambda m: m.startswith("Mesário ") and m.endswith(" registrado"),
}
# mensagens exatas → contador (consulta em dicionário); as demais regras de CONTA só rodam para mensagens raras
EXATAS = {"Identificador digitado pelo mesário foi: (CPF)": "id_cpf", "Identificador digitado pelo mesário foi: (Título de eleitor)": "id_titulo",
          "Ano de nascimento digitado é igual ao do cadastro": "ano_nasc_confere", "Dado digitado confere": "ano_nasc_confere",
          "Ano de nascimento digitado é diferente do cadastro": "ano_nasc_diferente", "Dado digitado não confere": "ano_nasc_diferente",
          "O eleitor identificado já votou": "eleitor_ja_votou", "Eleitor não encontrado para o identificador informado": "eleitor_nao_encontrado",
          "Eleitor corrigiu na tela de confirmação de candidato": "correcoes", "Eleitor foi suspenso e não confirmou nenhum voto": "suspenso_sem_votar",
          "Justificativa recebida": "justificativas", "Áudio ativado conforme cadastro": "audio_cadastro",
          "Procedimento de encerramento abortado": "encerr_abortado", "Operador cancelou o encerramento da votação": "encerr_abortado",
          "Todas as pessoas presentes já votaram? NÃO": "encerr_com_presentes"}
FREQUENTES = {"Aguardando digitação do identificador do eleitor", "Identificador do eleitor digitado pelo mesário", "Tipo de habilitação do eleitor [biométrica]",
              "Eleitor foi habilitado", "O voto do eleitor foi computado", "Foto do eleitor apresentada", "Tecla indevida pressionada",
              "Voto confirmado para [Presidente]", "Voto confirmado para [Governador]", "Voto confirmado para [Senador]", "Voto confirmado para [Deputado Federal]",
              "Voto confirmado para [Deputado Estadual]", "Voto confirmado para [Deputado Distrital]"}
RARAS = {k: v for k, v in CONTA.items() if k not in set(EXATAS.values())}
MESARIO_HAB = re.compile(r"Mesário (\d+) habilitou o eleitor")
IMPEDIDO = re.compile(r"Eleitor impedido - (.+)")


def analisar(texto, dia, uf):
    """Extrai os indicadores de um log para o dia da eleição."""
    ini = texto.find(dia)
    if ini < 0:
        return None
    linhas = texto[ini:].split("\n")
    r = {"urnas": set(), "modelo": None, "ligada_n": 0, "contingencia": False, "t_ligada": None, "t_zeresima": None, "t_pronta": None,
         "t_primeiro_voto": None, "t_ultimo_voto": None, "t_encerramento": None, "t_bu": None, "votos_log": 0, "hab": collections.Counter(),
         "hab_manual_pedido": 0, "hab_por_mesario": 0, "alertas": 0, "erros": 0, "erros_rotina": 0, "voto_nao_registrado": 0, "ligadas_apos_pronta": 0,
         "t_contingencia": None, "bateria": 0, "bateria_min": 0.0, "duracoes": []}
    r.update({k: 0 for k in CONTA})
    msgs, por_mesario, impedidos = collections.Counter(), collections.Counter(), collections.Counter()
    t_hab, t_bat, votos_s = None, None, []
    for l in linhas:
        if not l.startswith(dia):
            continue
        p = l.split("\t")
        if len(p) < 5:
            continue
        hora, nivel, urna, msg = p[0][11:19], p[1], p[2], p[4]
        if nivel in ("ALERTA", "ERRO"):
            r["alertas" if nivel == "ALERTA" else "erros"] += 1
            msgs[(nivel, NUM.sub("#", msg)[:140])] += 1
            if nivel == "ERRO" and msg.startswith("Problema ao desmontar a MR"):
                r["erros_rotina"] += 1  # ocorre em quase toda urna ao retirar a mídia de resultado
            if "NÃO foi registrado" in msg:
                r["voto_nao_registrado"] += 1
        if nivel == "EXTERNO":
            continue  # trecho do log de outra urna anexado (contingência)
        r["urnas"].add(urna)
        k = EXATAS.get(msg)
        if k:
            r[k] += 1
        elif msg not in FREQUENTES and not msg.startswith(("Solicita digital", "Capturada a digital", "Batimento de digitais")):
            for k, teste in RARAS.items():
                if teste(msg):
                    r[k] += 1
        if msg.startswith("Urna ligada em"):
            r["ligada_n"] += 1
            r["t_ligada"] = r["t_ligada"] or hora
            if r["t_pronta"] is not None and r["t_encerramento"] is None:
                r["ligadas_apos_pronta"] += 1  # urna religada durante a votação
        elif msg == "O voto do eleitor foi computado":
            r["votos_log"] += 1
            r["t_primeiro_voto"] = r["t_primeiro_voto"] or hora
            r["t_ultimo_voto"] = hora
            sec = segundos(hora)
            votos_s.append(sec)
            if t_hab is not None and 0 <= sec - t_hab < 1800:
                r["duracoes"].append(sec - t_hab)
            t_hab = None
        elif msg == "Eleitor foi habilitado":
            t_hab = segundos(hora)
        elif msg.startswith("Tipo de habilitação do eleitor"):
            m = HAB.search(msg)
            if m:
                r["hab"][m.group(1)] += 1
        elif "habilitação manual" in msg:
            r["hab_manual_pedido"] += 1
        elif "habilitou o eleitor" in msg:
            r["hab_por_mesario"] += 1
            m = MESARIO_HAB.search(msg)
            if m:
                por_mesario[m.group(1)] += 1
        elif msg.startswith("Eleitor impedido"):
            m = IMPEDIDO.search(msg)
            if m:
                impedidos[m.group(1)] += 1
        elif msg.startswith("Imprimindo relatório [ZERÉSIMA]") and r["t_zeresima"] is None:
            r["t_zeresima"] = hora
        elif msg == "Urna pronta para receber votos" and r["t_pronta"] is None:
            r["t_pronta"] = hora
        elif msg == "Inicio do Encerramento" or msg == "Procedimento de encerramento confirmado":
            r["t_encerramento"] = r["t_encerramento"] or hora
        elif msg.startswith("Gerando arquivo de resultado [bu.dat] + [Término]"):
            r["t_bu"] = hora
        elif "contingência" in msg.lower():
            r["contingencia"] = True
            r["t_contingencia"] = r["t_contingencia"] or hora
        elif msg in ("Urna operando na bateria interna", "Urna operando com bateria interna") or msg.startswith("Urna ligada desconectada da rede"):
            r["bateria"] += 1
            t_bat = t_bat if t_bat is not None else segundos(hora)
        elif msg in ("Urna operando na rede elétrica", "Urna operando com rede elétrica") and t_bat is not None:
            r["bateria_min"] += (segundos(hora) - t_bat) / 60
            t_bat = None
        elif r["modelo"] is None:
            m = MODELO.search(msg)
            if m:
                r["modelo"] = m.group(1)
    # fuso da urna: pelo estado; em AM e PE (mais de um fuso), pela hora em que a urna ficou pronta (8h de Brasília)
    fuso = FUSO.get(uf, 0)
    if uf in ("AM", "PE") and r["t_pronta"]:
        fuso = max(-2, min(1, round((segundos(r["t_pronta"]) / 3600) - 8)))
    r["fuso"] = fuso
    fim = (17 + fuso) * 3600
    r["votos_apos_17h"] = sum(1 for x in votos_s if x > fim)
    r["votos_hora"] = [0] * 24  # por hora de Brasília
    for x in votos_s:
        r["votos_hora"][min(23, max(0, x // 3600 - fuso))] += 1
    d = sorted(r["duracoes"])
    r["tempo_mediano_s"] = d[len(d) // 2] if d else None
    r["n_urnas"] = len(r["urnas"])
    r["urnas"] = ",".join(sorted(r["urnas"]))
    r["hab_biometrica"] = r["hab"].get("biométrica", 0)
    r["hab_outras"] = sum(v for k, v in r["hab"].items() if k != "biométrica")
    r["hab_tipos"] = json.dumps(dict(r["hab"]), ensure_ascii=False)
    r["mesario_max_hab"] = max(por_mesario.values()) if por_mesario else 0
    r["mesarios_que_habilitaram"] = len(por_mesario)
    r["impedidos_tipos"] = json.dumps(dict(impedidos), ensure_ascii=False)
    r["bateria_min"] = round(r["bateria_min"], 1)
    del r["hab"], r["duracoes"]
    return r, msgs


def baixar_em_blocos(url, tamanho=1 << 20):
    with urllib.request.urlopen(url, timeout=120) as resp:
        while True:
            b = resp.read(tamanho)
            if not b:
                break
            yield b


def processar(tarefa):
    turno, uf = tarefa
    destino = SAIDA / f"{turno}_{uf}.parquet"
    if destino.exists() and "mesario_max_hab" in pd.read_parquet(destino).columns:  # já processado nesta versão
        return f"{turno}_{uf}: já processado"
    url = URL.format(t=turno, uf=uf)
    for tentativa in range(5):
        try:
            linhas, msgs, n_arq, t0 = [], collections.Counter(), 0, time.time()
            votos_hora = [0] * 24
            for nome, _, blocos in stream_unzip(baixar_em_blocos(url)):
                nome = nome.decode("latin1")
                m = NOME.search(nome)
                if not m:
                    for _ in blocos:  # descarta boletim, imagem, RDV, assinatura
                        pass
                    continue
                dados = b"".join(blocos)
                n_arq += 1
                try:
                    texto = zipfile.ZipFile(io.BytesIO(dados)).read("logd.dat").decode("latin1")
                except Exception as e:  # log corrompido: registra e segue
                    linhas.append({"uf": m.group(1).upper(), "mun": int(m.group(2)), "zona": int(m.group(3)), "secao": int(m.group(4)), "erro_leitura": str(e)[:80]})
                    continue
                res = analisar(texto, DIA[turno], uf)
                base = {"uf": m.group(1).upper(), "mun": int(m.group(2)), "zona": int(m.group(3)), "secao": int(m.group(4))}
                if res is None:
                    linhas.append({**base, "sem_eventos_no_dia": True})
                    continue
                r, mm = res
                for h, v in enumerate(r.pop("votos_hora")):
                    votos_hora[h] += v
                linhas.append({**base, **r})
                msgs.update(mm)
            df = pd.DataFrame(linhas)
            df["turno"] = turno
            SAIDA.mkdir(parents=True, exist_ok=True)
            with open(SAIDA / f"{turno}_{uf}.json", "w") as f:
                json.dump({"logs": n_arq, "votos_hora": votos_hora, "mensagens": [[k[0], k[1], v] for k, v in msgs.most_common()]}, f, ensure_ascii=False)
            df.to_parquet(destino, index=False)  # gravado por último: marca a tarefa como concluída
            return f"{turno}_{uf}: {n_arq} logs em {time.time() - t0:.0f}s"
        except Exception as e:  # inclui limite de requisições do servidor (HTTP 429): espera e tenta de novo
            erro = e
            time.sleep(90 * (tentativa + 1))
    return f"{turno}_{uf}: FALHOU ({erro})"


def main():
    ufs = sys.argv[1:] or UFS
    # estados grandes primeiro, para equilibrar os processos
    tarefas = sorted([(t, uf) for t in (1, 2) for uf in ufs], key=lambda x: x[1] not in ("SP", "MG", "RJ", "BA", "RS", "PR"))
    with Pool(3) as pool:
        for msg in pool.imap_unordered(processar, tarefas):
            print(time.strftime("%H:%M:%S"), msg, flush=True)


if __name__ == "__main__":
    main()
