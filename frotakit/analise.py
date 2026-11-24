"""Análises sobre o consumo: motoristas e postos.

Motoristas
    Cada intervalo entre tanques cheios é comparado com o km/L mediano **do mesmo veículo quando
    dirigido por outros motoristas**. Assim o efeito do veículo sai da conta e sobra o do motorista.
    O intervalo de confiança (bootstrap) diz se a diferença é real ou pode ser acaso: só vale
    conversar com o motorista quando o intervalo inteiro está abaixo de zero.

Postos
    Preço por litro de cada abastecimento comparado com a mediana dos outros postos da mesma
    cidade, combustível e mês. Mostra quanto se pagou a mais por abastecer ali.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def motoristas(iv: pd.DataFrame, regras: dict, semente: int = 7) -> pd.DataFrame:
    cfg = regras["analise"]
    v = iv[iv["valido"] & ~iv["substituido"] & iv["motorista"].notna()].copy()
    if v.empty:
        return pd.DataFrame()
    v = v[v.groupby("placa")["km_l"].transform("size") >= 3]          # placa com histórico mínimo
    # referência de cada intervalo: km/L do MESMO veículo com OS OUTROS motoristas. Usa a mediana das
    # medianas de cada motorista, para que um titular que dirige o carro quase sempre não vire o "normal".
    ref = pd.Series(np.nan, index=v.index)
    for _, g in v.groupby("placa"):
        por_motorista = g.groupby("motorista")["km_l"].median()
        for nome, idx in g.groupby("motorista").groups.items():
            outros = por_motorista.drop(nome)
            if len(outros) >= 2:
                ref[idx] = outros.median()
    v["referencia"] = ref
    v = v.dropna(subset=["referencia"])
    v["desvio"] = v["km_l"] / v["referencia"] - 1
    v["litros_esperados"] = v["km"] / v["referencia"]
    rnd = np.random.default_rng(semente)
    relevante = cfg.get("desvio_relevante", 0.05)   # diferença pequena, mesmo que "significativa", não é assunto
    linhas = []
    for nome, g in v.groupby("motorista"):
        if len(g) < cfg["minimo_intervalos_motorista"]:
            continue
        d = g["desvio"].to_numpy()
        boot = rnd.choice(d, size=(cfg["reamostragens"], len(d)), replace=True).mean(axis=1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        linhas.append({
            "motorista": nome, "veiculos": g["placa"].nunique(), "intervalos": len(g),
            "km": g["km"].sum(), "desvio_medio_%": round(100 * d.mean(), 1),
            "ic95_inferior_%": round(100 * lo, 1), "ic95_superior_%": round(100 * hi, 1),
            "litros_a_mais": round((g["litros"] - g["litros_esperados"]).sum(), 1),
            "conclusao": ("consome mais que o normal do veículo" if hi < 0 and d.mean() <= -relevante
                          else "consome menos que o normal do veículo" if lo > 0 and d.mean() >= relevante
                          else "dentro do normal"),
        })
    return pd.DataFrame(linhas).sort_values("desvio_medio_%").reset_index(drop=True)


def postos(transacoes: pd.DataFrame, regras: dict) -> pd.DataFrame:
    t = transacoes[~transacoes["duplicado"] & (transacoes["litros"] > 0) & transacoes["valor"].notna()].copy()
    if t.empty:
        return pd.DataFrame()
    t["preco"] = t["valor"] / t["litros"]
    t["mes"] = t["data_hora"].dt.to_period("M").astype(str)
    chaves = ["cidade", "combustivel", "mes"]
    t["mediana_local"] = t.groupby(chaves, dropna=False)["preco"].transform("median")
    t["pago_a_mais"] = (t["preco"] - t["mediana_local"]) * t["litros"]
    r = t.groupby(["posto", "cidade"], dropna=False).agg(
        abastecimentos=("id", "size"), litros=("litros", "sum"), preco_medio=("preco", "mean"),
        mediana_local=("mediana_local", "mean"), pago_a_mais=("pago_a_mais", "sum")).reset_index()
    r["sobrepreco_%"] = (100 * (r["preco_medio"] / r["mediana_local"] - 1)).round(1)
    r = r.round({"litros": 1, "preco_medio": 3, "mediana_local": 3, "pago_a_mais": 2})
    r["atencao"] = r["sobrepreco_%"] >= 100 * regras["analise"]["sobrepreco_minimo"]
    return r.sort_values("pago_a_mais", ascending=False).reset_index(drop=True)
