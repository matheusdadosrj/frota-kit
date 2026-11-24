"""Rastreadores: última posição por veículo, consolidando vários fornecedores.

Cada fornecedor exporta um relatório diferente (colunas, formato de data, às vezes identifica o
veículo pelo apelido ou pelo chassi em vez da placa). O mapeamento de colunas fica em
config/fontes.yaml; aqui só ficam as regras comuns:

* o veículo é identificado pela placa; se a fonte trouxer outro identificador, `resolver_placa`
  procura uma placa válida dentro do texto (ex.: "VAN 12 - ABC1D23");
* vale a posição mais recente entre todos os fornecedores;
* sem endereço, `geocodificar` faz a geocodificação reversa no OpenStreetMap (Nominatim), com
  cache em disco e no máximo 1 consulta por segundo, como pede a política de uso do serviço.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd

PLACA = re.compile(r"[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}")


def resolver_placa(serie: pd.Series) -> pd.Series:
    """Extrai a placa de textos como 'Van 12 - ABC-1D23' ou 'abc1d23 (motorista)'."""
    achado = serie.astype("string").str.upper().str.extract(f"({PLACA.pattern})", expand=False)
    return achado.str.replace("-", "", regex=False)


def ultima_posicao(posicoes: pd.DataFrame, data_ref=None) -> pd.DataFrame:
    p = posicoes.dropna(subset=["placa", "data_hora"])
    ult = p.sort_values("data_hora").groupby("placa").tail(1).copy()
    ref = pd.Timestamp(data_ref or pd.Timestamp.today()).normalize()
    ult["dias_sem_sinal"] = (ref - ult["data_hora"].dt.normalize()).dt.days
    ult["fornecedores"] = ult["placa"].map(p.groupby("placa")["fornecedor"].agg(lambda s: ", ".join(sorted(s.dropna().unique()))))
    return ult.sort_values("dias_sem_sinal", ascending=False).reset_index(drop=True)


def geocodificar(df: pd.DataFrame, cache: str | Path = "saida/geocache.json", contato: str = "",
                 limite: int = 200) -> pd.DataFrame:
    """Preenche `endereco` vazio a partir de latitude/longitude (Nominatim). Requer internet."""
    import requests

    cache = Path(cache)
    memoria = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    df = df.copy()
    faltando = df[df["endereco"].isna() & df["latitude"].notna()].head(limite)
    for i, r in faltando.iterrows():
        k = f"{r['latitude']:.4f},{r['longitude']:.4f}"
        if k not in memoria:
            resp = requests.get("https://nominatim.openstreetmap.org/reverse",
                                params={"lat": r["latitude"], "lon": r["longitude"], "format": "json", "zoom": 16},
                                headers={"User-Agent": f"frota-kit/1.0 {contato}".strip()}, timeout=20)
            memoria[k] = resp.json().get("display_name", "") if resp.ok else ""
            time.sleep(1.1)
        df.at[i, "endereco"] = memoria[k]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(memoria, ensure_ascii=False, indent=0), encoding="utf-8")
    return df
