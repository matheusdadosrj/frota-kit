"""CSV / Excel. Aceita um arquivo ou um padrão (ex.: 'exportacoes/*.xlsx'), que são concatenados."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def ler(cfg: dict, base: Path) -> pd.DataFrame:
    caminho = Path(cfg["caminho"])
    if not caminho.is_absolute():
        caminho = base / caminho
    arquivos = sorted(caminho.parent.glob(caminho.name)) if any(c in caminho.name for c in "*?[") else [caminho]
    if not arquivos or not arquivos[0].exists():
        raise FileNotFoundError(f"Nenhum arquivo em {caminho}")
    partes = []
    for a in arquivos:
        if a.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            partes.append(pd.read_excel(a, sheet_name=cfg.get("aba", 0), skiprows=cfg.get("pular_linhas", 0), dtype=str))
        else:
            partes.append(pd.read_csv(a, sep=cfg.get("separador") or _separador(a),
                                      encoding=cfg.get("codificacao", "utf-8-sig"),
                                      skiprows=cfg.get("pular_linhas", 0), dtype=str))
    return pd.concat(partes, ignore_index=True)


def _separador(arquivo: Path) -> str:
    """Exportações brasileiras costumam usar ';'. Olha a primeira linha para decidir."""
    with open(arquivo, encoding="utf-8-sig", errors="ignore") as f:
        primeira = f.readline()
    return max([";", ",", "\t", "|"], key=primeira.count) if any(c in primeira for c in ";,\t|") else ","
