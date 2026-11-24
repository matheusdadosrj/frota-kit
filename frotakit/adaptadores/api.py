"""API REST genérica (cartão frota, telemetria, sistema de manutenção).

    abastecimentos:
      tipo: api
      url: https://api.fornecedor.com/v1/transacoes
      token: ${CARTAO_FROTA_TOKEN}       # vai no cabeçalho Authorization: Bearer ...
      parametros: {dataInicio: "2026-01-01"}
      registros_em: data.items          # caminho até a lista dentro do JSON
      paginacao: {parametro: page, inicio: 1, tamanho_parametro: size, tamanho: 200}
      colunas: {licensePlate: placa, transactionDate: data_hora, liters: litros}

Para OAuth2 (client credentials) informe `token_url`, `client_id` e `client_secret` no lugar de `token`.
Cada página bruta pode ser guardada em `salvar_bruto` para auditoria e reprocessamento.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


def _token(cfg: dict, sessao) -> str | None:
    if cfg.get("token"):
        return cfg["token"]
    if cfg.get("token_url"):
        r = sessao.post(cfg["token_url"], data={"grant_type": "client_credentials",
                                               "client_id": cfg["client_id"], "client_secret": cfg["client_secret"]},
                        timeout=30)
        r.raise_for_status()
        return r.json()["access_token"]
    return None


def _extrair(dado, caminho: str | None):
    for parte in (caminho or "").split("."):
        if parte:
            dado = dado.get(parte, []) if isinstance(dado, dict) else []
    return dado if isinstance(dado, list) else []


def ler(cfg: dict, base: Path, sessao=None) -> pd.DataFrame:
    import requests

    sessao = sessao or requests.Session()
    token = _token(cfg, sessao)
    cabecalho = {"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    pag = cfg.get("paginacao")
    params = dict(cfg.get("parametros") or {})
    pasta_bruto = (base / cfg["salvar_bruto"]) if cfg.get("salvar_bruto") else None
    registros, pagina = [], (pag or {}).get("inicio", 1)
    while True:
        if pag:
            params[pag["parametro"]] = pagina
            if pag.get("tamanho_parametro"):
                params[pag["tamanho_parametro"]] = pag.get("tamanho", 100)
        for tentativa in range(4):
            r = sessao.get(cfg["url"], params=params, headers=cabecalho, timeout=60)
            if r.status_code not in (429, 502, 503, 504):
                break
            time.sleep(2 ** tentativa)          # limite de requisições / instabilidade: espera e tenta de novo
        r.raise_for_status()
        corpo = r.json()
        if pasta_bruto:
            pasta_bruto.mkdir(parents=True, exist_ok=True)
            (pasta_bruto / f"{datetime.now():%Y%m%d_%H%M%S}_p{pagina}.json").write_text(
                json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
        lote = _extrair(corpo, cfg.get("registros_em"))
        registros += lote
        if not pag or len(lote) < pag.get("tamanho", 100) or pagina >= pag.get("max_paginas", 1000):
            break
        pagina += 1
    return pd.json_normalize(registros) if registros else pd.DataFrame()
