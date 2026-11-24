"""Banco de dados (ERP, data warehouse, sistema de frota).

    ordens_servico:
      tipo: sql
      conexao: ${ERP_URL}            # ex.: postgresql+psycopg://usuario:senha@host/erp
      consulta: |
        SELECT numero AS os_id, placa, dt_abertura AS abertura, dt_fechamento AS fechamento, situacao AS status
        FROM manutencao.ordens WHERE dt_abertura >= CURRENT_DATE - 365

Para SQLite basta 'sqlite:///caminho/arquivo.sqlite' (sem dependência extra). Para outros bancos
instale SQLAlchemy e o driver (psycopg, pyodbc, oracledb...). A melhor prática é pedir ao time do
ERP uma *view* só de leitura com os nomes de colunas do modelo canônico: aí a consulta vira
`SELECT * FROM vw_frota_ordens_servico` e o mapeamento fica vazio.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def ler(cfg: dict, base: Path) -> pd.DataFrame:
    conexao, consulta = cfg["conexao"], cfg["consulta"]
    if conexao.startswith("sqlite:///"):
        caminho = Path(conexao.removeprefix("sqlite:///"))
        if not caminho.is_absolute():
            caminho = base / caminho
        with sqlite3.connect(caminho) as con:
            return pd.read_sql_query(consulta, con, params=cfg.get("parametros"))
    from sqlalchemy import create_engine, text   # só é exigido para bancos que não são SQLite

    with create_engine(conexao).connect() as con:
        return pd.read_sql_query(text(consulta), con, params=cfg.get("parametros"))
