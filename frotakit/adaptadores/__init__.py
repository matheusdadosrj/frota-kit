"""Adaptadores: levam qualquer fonte para o modelo canônico (frotakit.modelo).

config/fontes.yaml diz, para cada entidade, de onde ler e como renomear as colunas:

    abastecimentos:
      tipo: arquivo                 # arquivo | grade | sql | api | whatsapp
      caminho: dados/transacoes.xlsx
      colunas: {Placa: placa, "Data/Hora": data_hora, Litros: litros}

Uma entidade pode ter uma lista de fontes (ex.: dois fornecedores de rastreador); elas são
concatenadas. Textos no formato ${VARIAVEL} são lidos do ambiente / arquivo .env, para que
senhas e tokens nunca fiquem no YAML nem no Git.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import yaml

from ..modelo import ENTIDADES, padronizar
from ..rastreamento import resolver_placa
from . import api, arquivo, grade, sql, whatsapp

LEITORES = {"arquivo": arquivo.ler, "grade": grade.ler, "sql": sql.ler, "api": api.ler, "whatsapp": whatsapp.ler}
_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expandir(valor):
    if isinstance(valor, str):
        def troca(m):
            if m.group(1) not in os.environ:
                raise KeyError(f"Variável de ambiente {m.group(1)} não definida (veja .env.example)")
            return os.environ[m.group(1)]
        return _VAR.sub(troca, valor)
    if isinstance(valor, dict):
        return {k: _expandir(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_expandir(v) for v in valor]
    return valor


def ler_fonte(cfg: dict, entidade: str, base: Path) -> pd.DataFrame:
    cfg = _expandir(cfg)
    tipo = cfg.get("tipo", "arquivo")
    if tipo not in LEITORES:
        raise ValueError(f"{entidade}: tipo de fonte desconhecido '{tipo}' (use {', '.join(LEITORES)})")
    df = LEITORES[tipo](cfg, base)
    df = df.rename(columns=cfg.get("colunas") or {})
    if cfg.get("placa_de"):            # ex.: rastreador que identifica o veículo pelo apelido
        df["placa"] = resolver_placa(df[cfg["placa_de"]])
    for col, valor in (cfg.get("fixos") or {}).items():   # ex.: fornecedor: "Rastreador A"
        df[col] = valor
    return padronizar(df, entidade)


def carregar(caminho_yaml: str | Path) -> dict[str, pd.DataFrame]:
    caminho_yaml = Path(caminho_yaml)
    try:
        from dotenv import load_dotenv
        load_dotenv(caminho_yaml.parent.parent / ".env")
    except ImportError:
        pass
    config = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}
    base = caminho_yaml.parent.parent if config.get("relativo_a", "projeto") == "projeto" else caminho_yaml.parent
    tabelas, corrigidas = {}, []
    for entidade in ENTIDADES:
        fontes = config.get(entidade)
        if not fontes:
            continue
        fontes = fontes if isinstance(fontes, list) else [fontes]
        partes = [ler_fonte(f, entidade, base) for f in fontes]
        corrigidas += [p.attrs.pop("placas_corrigidas", None) for p in partes]   # tira antes de juntar
        tabelas[entidade] = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]
    # não é uma entidade: é o registro das placas que o kit corrigiu ao ler (O->0, I->1...)
    tabelas["placas_corrigidas"] = pd.DataFrame([linha for c in corrigidas if c for linha in c],
                                                columns=["placa_informada", "placa_corrigida", "registros", "fonte"])
    return tabelas
