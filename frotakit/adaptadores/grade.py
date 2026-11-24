"""Planilha em grade: uma linha por veículo, uma coluna por dia (diário de bordo, escala, controle de pátio).

    uso:
      tipo: grade
      caminho: diarios/diario_base_sul.xlsx      # aceita padrão: diarios/*.xlsx
      abas: todas                                # ou uma lista: [OUT-26, NOV-26]
      coluna_placa: PLACA                        # texto do cabeçalho da coluna de placas

         A                B         C           D           ...  AF          AG
    1    DIÁRIO DE BORDO - BASE SUL - NOVEMBRO
    2
    3    PLACA            MODELO    01/11/2026  02/11/2026  ...  30/11/2026  TOTAL
    4    ABC1D23          Van       1           2           ...  0           23
    5    ABC0123          Furgão    M           M           ...  0           0

Cada aba vira linhas (placa, data, codigo). O leitor procura sozinho a linha que tem "PLACA" e a
linha com as datas (a mesma ou uma acima), então títulos, linhas em branco e colunas extras
(modelo, total) no meio não atrapalham. Abas sem esse formato (legenda, resumo) são ignoradas.

Dias futuros já preenchidos com 0 são cortados: a aba vale até o último dia com algum código
diferente de 0.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..regras import chave

MIN_DATAS = 7          # uma linha com pelo menos isso de datas é o cabeçalho de dias


def _eh_data(v) -> bool:
    return isinstance(v, (datetime, date, pd.Timestamp)) and not pd.isna(v)


def localizar(topo: pd.DataFrame, rotulo_placa: str = "PLACA"):
    """(linha da placa, coluna da placa, linha das datas, colunas das datas) ou None se não é grade."""
    alvo = chave(rotulo_placa)
    for i in range(len(topo)):
        textos = [chave(v) for v in topo.iloc[i]]
        if alvo in textos:
            linha_placa, col_placa = i, textos.index(alvo)
            break
    else:
        return None
    for i in range(linha_placa, -1, -1):          # mesma linha da PLACA ou acima dela
        colunas = [j for j, v in enumerate(topo.iloc[i]) if _eh_data(v)]
        if len(colunas) >= MIN_DATAS:
            return linha_placa, col_placa, i, colunas
    return None


def _codigo(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip().upper()


def ler_aba(bruto: pd.DataFrame, nome_aba: str, rotulo_placa: str = "PLACA") -> pd.DataFrame | None:
    pos = localizar(bruto.head(30), rotulo_placa)
    if pos is None:
        return None
    linha_placa, col_placa, linha_datas, col_datas = pos
    corpo = bruto.iloc[linha_placa + 1:]
    datas = {j: pd.Timestamp(bruto.iat[linha_datas, j]).normalize() for j in col_datas}
    linhas = []
    for _, r in corpo.iterrows():
        placa = r.iloc[col_placa]
        if placa is None or (isinstance(placa, float) and pd.isna(placa)) or not str(placa).strip():
            continue
        for j, dia in datas.items():
            cod = _codigo(r.iloc[j])
            if cod:
                linhas.append((str(placa).strip(), dia, cod))
    df = pd.DataFrame(linhas, columns=["placa", "data", "codigo"])
    preenchido = df[df["codigo"] != "0"]
    if preenchido.empty:
        return None
    df = df[df["data"] <= preenchido["data"].max()]      # corta os dias futuros preenchidos com 0
    return df.assign(origem=f"diário ({nome_aba})")


def ler(cfg: dict, base: Path) -> pd.DataFrame:
    caminho = Path(cfg["caminho"])
    caminho = caminho if caminho.is_absolute() else base / caminho
    arquivos = sorted(caminho.parent.glob(caminho.name)) if any(c in caminho.name for c in "*?[") else [caminho]
    abas = cfg.get("abas", "todas")
    partes = []
    for arq in arquivos:
        planilhas = pd.read_excel(arq, sheet_name=None if abas == "todas" else abas, header=None)
        for nome, bruto in planilhas.items():
            df = ler_aba(bruto, nome, cfg.get("coluna_placa", "PLACA"))
            if df is not None:
                partes.append(df)
    if not partes:
        raise ValueError(f"Nenhuma aba em formato de grade (placa x dia) em {caminho}")
    return pd.concat(partes, ignore_index=True)
