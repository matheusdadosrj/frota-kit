"""Siglas do diário de bordo (ou de qualquer grade placa x dia).

O significado de cada sigla fica em config/dicionario_status.csv, editável pela operação:

    sigla;significado;grupo
    M;Manutenção;manutencao
    F;Folga;parado

Grupos: `rodou` (conta como atividade), `manutencao` (veículo indisponível), `parado` (não rodou,
mas está disponível: folga, sem rota, sem motorista). Números (1, 2, 3...) são quantidade de rotas
e contam como `rodou`; 0 é "sem rota" (`parado`).

Sigla que não está no dicionário não quebra nada: vira grupo `?`, o veículo fica "A confirmar" e
a sigla entra na lista de pendências para alguém da operação definir o significado.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .regras import chave

GRUPOS = {"rodou", "manutencao", "parado"}


def carregar_dicionario(regras: dict) -> pd.DataFrame:
    caminho = Path(regras["diario"]["dicionario"])
    if not caminho.is_absolute():
        caminho = Path(__file__).resolve().parents[1] / caminho
    if not caminho.exists():
        return pd.DataFrame(columns=["significado", "grupo"])
    d = pd.read_csv(caminho, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    d["sigla"] = d["sigla"].map(chave)
    d["grupo"] = d["grupo"].map(lambda g: chave(g).lower())
    invalidos = set(d["grupo"]) - GRUPOS - {""}
    if invalidos:
        raise ValueError(f"{caminho}: grupo(s) desconhecido(s) {sorted(invalidos)}; use {sorted(GRUPOS)}")
    return d.drop_duplicates("sigla").set_index("sigla")[["significado", "grupo"]]


def classificar(uso: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Acrescenta `grupo` e `significado` a cada linha de uso."""
    uso = uso.copy()
    dic = carregar_dicionario(regras)
    cod = uso["codigo"].map(chave)
    numero = cod.str.fullmatch(r"\d+", na=False)
    grupo = cod.map(dic["grupo"]) if len(dic) else pd.Series(pd.NA, index=uso.index)
    grupo = grupo.where(~numero, cod.where(numero, "0").astype(int).gt(0).map({True: "rodou", False: "parado"}))
    grupo = grupo.where(cod != "", "rodou")             # sem código (viagem, rota): rodou
    uso["grupo"] = grupo.fillna("?").replace("", "?")
    uso["significado"] = cod.map(dic["significado"]) if len(dic) else pd.NA
    uso.loc[numero, "significado"] = cod[numero].map(lambda n: f"{n} rota(s)" if int(n) else "sem rota")
    return uso


def ultimo_codigo(uso: pd.DataFrame, data_ref: pd.Timestamp, validade_dias: int) -> pd.DataFrame:
    """Último código de diário de cada placa até a data, se não for mais velho que `validade_dias`."""
    d = uso[uso["codigo"].fillna("").ne("") & (uso["data"] <= data_ref)]
    d = d[(data_ref.normalize() - d["data"].dt.normalize()).dt.days <= validade_dias]
    ult = d.sort_values("data").groupby("placa").tail(1)
    return ult.rename(columns={"data": "data_codigo", "codigo": "ultimo_codigo", "grupo": "grupo_codigo",
                               "origem": "origem_codigo"})[
        ["placa", "data_codigo", "ultimo_codigo", "grupo_codigo", "significado", "origem_codigo"]]


def siglas_pendentes(uso: pd.DataFrame) -> pd.DataFrame:
    """Siglas sem significado no dicionário: a lista para mandar à operação."""
    p = uso[uso["grupo"] == "?"]
    if p.empty:
        return pd.DataFrame(columns=["sigla", "ocorrencias", "placas", "primeira", "ultima", "onde"])
    return (p.groupby("codigo").agg(ocorrencias=("placa", "size"),
                                     placas=("placa", lambda s: ", ".join(sorted(s.unique())[:10])),
                                     primeira=("data", "min"), ultima=("data", "max"),
                                     onde=("origem", lambda s: ", ".join(sorted(s.dropna().unique()))))
            .reset_index().rename(columns={"codigo": "sigla"}).sort_values("ocorrencias", ascending=False))
