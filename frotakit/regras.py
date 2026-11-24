"""Carrega config/regras.yaml sobre os valores padrão."""
from __future__ import annotations

import copy
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

PADRAO: dict = {
    "disponibilidade": {
        "status_fora_da_frota": ["DESMOBILIZADO", "VENDIDO", "DEVOLVIDO", "SINISTRO", "BAIXADO"],
        "status_os_aberta": ["ABERTA", "EM ANDAMENTO", "AGUARDANDO PECA", "AGUARDANDO APROVACAO"],
        "dias_ocioso": 7,
        "dias_sem_sinal": 3,
        "ordem": ["decisao_manual", "fora_da_frota", "os_aberta", "diario_manutencao", "a_confirmar",
                  "ocioso", "em_operacao"],
        "dias_historico": 30,
    },
    "consumo": {
        "grupos": {"padrao": {"kml_min": 1.5, "kml_max": 25, "autonomia_km": 1000}},
        "tanque_referencia": 0.90,
        "minutos_duplicado": 30,
        "folga_tanque": 1.10,
        "limiar_serrote": 0.20,
        "minimo_grupo": 4,
    },
    "diario": {"dicionario": "config/dicionario_status.csv", "validade_dias": 3},
    "solicitacoes": {"horas_reenvio": 2, "regex_placa": r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$"},
    "analise": {"reamostragens": 1000, "minimo_intervalos_motorista": 4, "desvio_relevante": 0.05, "sobrepreco_minimo": 0.03},
}


def _mesclar(base: dict, novo: dict) -> dict:
    saida = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        saida[k] = _mesclar(saida[k], v) if isinstance(v, dict) and isinstance(saida.get(k), dict) else v
    return saida


def carregar(caminho: str | Path | None = None) -> dict:
    if caminho is None:
        caminho = Path(__file__).resolve().parents[1] / "config" / "regras.yaml"
    caminho = Path(caminho)
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    return _mesclar(PADRAO, dados)


def chave(texto) -> str:
    """Texto para comparação: sem acento, maiúsculo, espaços simples."""
    if texto is None or (not isinstance(texto, str) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFD", str(texto))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.upper().replace("_", " ").split())


def parametros_grupo(regras: dict, grupo) -> dict:
    grupos = regras["consumo"]["grupos"]
    nome = grupo.strip().lower() if isinstance(grupo, str) else ""
    return grupos.get(nome, grupos.get("padrao", PADRAO["consumo"]["grupos"]["padrao"]))
