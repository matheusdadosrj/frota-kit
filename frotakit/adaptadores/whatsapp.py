"""Formulários de pagamento postados num grupo de WhatsApp -> entidade `solicitacoes`.

Entrada: a conversa exportada pelo próprio WhatsApp (Mais opções > Exportar conversa > Sem mídia).
Nada é lido direto do WhatsApp. Funciona com os formatos de exportação do Android e do iPhone.

    solicitacoes:
      tipo: whatsapp
      caminho: exportacoes/conversa.txt
      gatilho: "FORMULARIO DE ABASTECIMENTO"      # texto que identifica a mensagem (sem acento)
      rotulos:                                     # início do rótulo (sem acento) -> coluna
        PLACA: placa
        MOTORISTA: motorista
        VALOR: valor
        KM: odometro
        PIX: chave_pix
        POSTO: posto

Exemplo de mensagem reconhecida:

    FORMULÁRIO DE ABASTECIMENTO
    PLACA: ABC1D23
    MOTORISTA: Fulano
    VALOR: 150,00
    KM: 45.120
    PIX DO POSTO: 00.000.000/0001-00
    POSTO: Posto Exemplo
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

# "23/11/2026 08:23 - Nome: texto" (Android) | "[23/11/2026, 08:23:10] Nome: texto" (iPhone)
CABECALHO = re.compile(
    r"^\[?(?P<data>\d{2}/\d{2}/\d{2,4}),? (?P<hora>\d{1,2}:\d{2})(?::\d{2})?\]?(?: -)? (?P<autor>[^:]{1,60}): (?P<texto>.*)$")
ROTULOS_PADRAO = {"PLACA": "placa", "MOTORISTA": "motorista", "VALOR": "valor", "KM": "odometro",
                  "HODOMETRO": "odometro", "ODOMETRO": "odometro", "PIX": "chave_pix", "POSTO": "posto",
                  "BANDEIRA": "posto"}


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").upper()


def mensagens(texto: str):
    atual = None
    for linha in texto.splitlines():
        m = CABECALHO.match(linha.strip("‎﻿"))
        if m:
            if atual:
                yield atual
            d = m["data"]
            ano = d[-4:] if len(d) == 10 else "20" + d[-2:]
            atual = {"data_hora": datetime.strptime(f"{d[:6]}{ano} {m['hora']}", "%d/%m/%Y %H:%M"),
                     "enviado_por": m["autor"].strip(), "texto": m["texto"]}
        elif atual:
            atual["texto"] += "\n" + linha
    if atual:
        yield atual


def ler_formulario(texto: str, rotulos: dict) -> dict:
    campos = {}
    for linha in texto.splitlines():
        linha = linha.strip(" -•·*\t")
        if ":" not in linha:
            continue
        rotulo, valor = linha.split(":", 1)
        r = sem_acento(rotulo).strip()
        for inicio, coluna in rotulos.items():
            if r.startswith(inicio) and coluna not in campos:
                campos[coluna] = valor.strip()
                break
    return campos


def ler(cfg: dict, base: Path) -> pd.DataFrame:
    caminho = Path(cfg["caminho"])
    caminho = caminho if caminho.is_absolute() else base / caminho
    gatilho = sem_acento(cfg.get("gatilho", "FORMULARIO"))
    rotulos = {sem_acento(k): v for k, v in (cfg.get("rotulos") or ROTULOS_PADRAO).items()}
    linhas = []
    for n, msg in enumerate(mensagens(caminho.read_text(encoding="utf-8"))):
        if gatilho not in sem_acento(msg["texto"]):
            continue
        campos = ler_formulario(msg["texto"], rotulos)
        linhas.append({"id": f"W{n:05d}", "data_hora": msg["data_hora"], "enviado_por": msg["enviado_por"], **campos})
    df = pd.DataFrame(linhas)
    # quilometragem escrita como "45.120" é milhar, não decimal
    if "odometro" in df:
        df["odometro"] = df["odometro"].astype("string").str.replace(r"[.\s]", "", regex=True).str.replace(",", ".")
    return df
