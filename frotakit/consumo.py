"""Consumo real (km/L) por veículo a partir das transações de abastecimento.

Método
------
* **km/L só entre dois tanques cheios.** Entre dois cheios, o que foi abastecido é exatamente o que
  foi gasto: km rodados ÷ litros abastecidos no intervalo (inclusive os parciais do meio).
* **km/L acumulado por veículo** = soma dos km ÷ soma dos litros dos intervalos válidos. Quando um
  "cheio" não encheu, os litros que faltaram num intervalo aparecem no seguinte e o erro se anula;
  só as pontas de cada sequência erram, no máximo (1 - tanque_referencia) × capacidade. Esse limite
  vira a **margem** informada junto do número.
* **Qualidade do dado antes da conta:** registro em dobro, odômetro ausente, que volta, que salta
  além da autonomia (erro de digitação) ou que salta e se confirma (rodou sem abastecer no cartão),
  litros acima do tanque, odômetro digitado com um dígito a mais, "cheio" com valor redondo e o
  padrão **serrote** (km/L alto num intervalo e baixo no seguinte = o cheio do meio não encheu; os
  dois intervalos são juntados).
* **Desperdício estimado** = litros reais − litros que o veículo gastaria no km/L mediano do seu
  grupo (mesmo tipo de veículo), em litros e em R$.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .regras import parametros_grupo

ALERTAS = {
    "duplicado": "Mesma placa, litros e odômetro em poucos minutos: provável registro em dobro",
    "odometro_ausente": "Odômetro não informado ou zerado",
    "odometro_regrediu": "Odômetro menor que o de um abastecimento anterior",
    "salto_odometro": "Odômetro saltou além da autonomia e o abastecimento seguinte não confirmou: provável erro de digitação",
    "trecho_longo": "Rodou além da autonomia sem abastecer (confirmado pelo registro seguinte): abastecimento fora do controle ou registro faltando",
    "acima_tanque": "Litros acima da capacidade do tanque",
    "odometro_corrigido": "Odômetro com um dígito a mais ou a menos: corrigido para a escala do veículo",
    "cheio_valor_redondo": "Marcado como cheio com litros ou valor redondo: a bomba pode ter sido travada num valor",
    "cheio_abaixo_esperado": "Marcado como cheio, mas colocou bem menos litros do que o veículo gastou",
    "cheio_serrote": "Padrão serrote: km/L alto antes deste 'cheio' e baixo depois; os intervalos foram juntados",
}


# ---------------------------------------------------------------------------- preparação
def preparar(abastecimentos: pd.DataFrame, veiculos: pd.DataFrame | None, regras: dict) -> pd.DataFrame:
    df = abastecimentos.dropna(subset=["placa", "data_hora"]).copy()
    if df["id"].isna().all():
        df["id"] = [f"T{i:06d}" for i in range(len(df))]
    cad = (veiculos[["placa", "grupo", "capacidade_tanque", "modelo", "base"]].drop_duplicates("placa")
           if veiculos is not None else pd.DataFrame(columns=["placa", "grupo", "capacidade_tanque", "modelo", "base"]))
    df = df.merge(cad, on="placa", how="left")
    par = df["grupo"].map(lambda g: parametros_grupo(regras, g))
    df["kml_min"] = par.map(lambda p: p["kml_min"])
    df["kml_max"] = par.map(lambda p: p["kml_max"])
    df["autonomia_km"] = par.map(lambda p: p["autonomia_km"])
    df["litros"] = df["litros"].fillna(0.0)
    return df.sort_values(["placa", "data_hora", "id"]).reset_index(drop=True)


def corrigir_escala_odometro(df: pd.DataFrame) -> pd.DataFrame:
    """Registros soltos com um dígito a mais/a menos (181.592 digitado 1.815.920) voltam à escala da placa."""
    df = df.copy()
    df["odometro_corrigido"] = False
    validos = df[df["odometro"] > 0]
    mediana = validos.groupby("placa")["odometro"].transform("median")
    razao = validos["odometro"] / mediana
    maior = razao.index[(razao > 5) & (razao < 20)]
    menor = razao.index[(razao > 0.05) & (razao < 0.2)]
    df.loc[maior, "odometro"] = df.loc[maior, "odometro"] / 10
    df.loc[menor, "odometro"] = df.loc[menor, "odometro"] * 10
    df.loc[maior.union(menor), "odometro_corrigido"] = True
    return df


# ---------------------------------------------------------------------------- alertas por transação
def marcar_alertas(df: pd.DataFrame, regras: dict) -> pd.DataFrame:
    cfg = regras["consumo"]
    df = df.copy()
    for col in ALERTAS:
        if col not in df:
            df[col] = False
    for _, bloco in df.groupby("placa", sort=False):
        ult = None                  # registro anterior (para duplicidade)
        maior_odo = None            # maior odômetro confiável até aqui
        candidato = None            # (índice, odômetro) de um salto que ainda pode se confirmar
        sem_leitura = 0             # abastecimentos sem odômetro desde a última leitura confiável
        for i, r in bloco.iterrows():
            odo = r["odometro"]
            if ult is not None and round(r["litros"], 2) == round(ult["litros"], 2) \
                    and (r["data_hora"] - ult["data_hora"]) <= pd.Timedelta(minutes=cfg["minutos_duplicado"]) \
                    and (pd.isna(odo) or pd.isna(ult["odometro"]) or odo == ult["odometro"]):
                df.at[i, "duplicado"] = True
                continue
            ult = r
            # autonomia: tanque cheio no melhor km/L do grupo; cada registro sem odômetro no meio soma uma
            cap = r["capacidade_tanque"]
            autonomia = cap * r["kml_max"] if pd.notna(cap) else r["autonomia_km"]
            limite = autonomia * (1 + sem_leitura)
            if pd.isna(odo) or odo <= 0:
                df.at[i, "odometro_ausente"] = True
                sem_leitura += 1
                continue
            elif maior_odo is not None and odo < maior_odo:
                df.at[i, "odometro_regrediu"] = True
            elif maior_odo is not None and odo - maior_odo > limite:
                if candidato is not None and 0 <= odo - candidato[1] <= limite:
                    # o salto anterior se confirmou: rodou de verdade sem abastecer no controle
                    df.at[candidato[0], "salto_odometro"] = False
                    df.at[candidato[0], "trecho_longo"] = True
                    maior_odo, candidato, sem_leitura = odo, None, 0
                else:
                    df.at[i, "salto_odometro"] = True
                    candidato = (i, odo)
            else:
                maior_odo, candidato, sem_leitura = odo, None, 0
            if pd.notna(cap) and r["litros"] > cap * cfg["folga_tanque"]:
                df.at[i, "acima_tanque"] = True

    redondo_l = (df["litros"] - (df["litros"] / 5).round() * 5).abs() < 0.005
    redondo_v = df["valor"].notna() & (df["valor"] > 0) & ((df["valor"] - (df["valor"] / 10).round() * 10).abs() < 0.005)
    df["cheio_valor_redondo"] = df["tanque_cheio"] & ~df["duplicado"] & (redondo_l | redondo_v)
    df["odometro_valido"] = ~(df["duplicado"] | df["odometro_ausente"] | df["odometro_regrediu"] | df["salto_odometro"])
    return df


# ---------------------------------------------------------------------------- intervalos
def intervalos(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for placa, bloco in df[~df["duplicado"]].groupby("placa", sort=False):
        ancora, litros, n, fora, ressalva = None, 0.0, 0, False, False
        for _, r in bloco.iterrows():
            if ancora is not None:
                litros += r["litros"]
                n += 1
                fora |= bool(r["trecho_longo"])
                ressalva |= not r["odometro_valido"]
            if not r["tanque_cheio"]:
                continue
            if not r["odometro_valido"]:
                ancora = None
                continue
            if ancora is not None:
                km = r["odometro"] - ancora["odometro"]
                kml = km / litros if litros > 0 else np.nan
                motivo = ""
                if km <= 0:
                    motivo = "km zero ou negativo"
                elif fora:
                    motivo = "trecho rodado sem abastecimento registrado no meio"
                elif kml > r["kml_max"]:
                    motivo = (f"km/L acima do máximo do grupo ({r['kml_max']:g}): abastecimento fora do controle "
                              "ou odômetro errado")
                elif kml < r["kml_min"]:
                    motivo = f"km/L abaixo do mínimo do grupo ({r['kml_min']:g}): litros que não foram para este veículo?"
                linhas.append({"placa": placa, "inicio": ancora["data_hora"], "fim": r["data_hora"],
                               "id_inicio": ancora["id"], "id_fim": r["id"], "tipo": "tanque cheio",
                               "km": km, "litros": round(litros, 2), "abastecimentos": n,
                               "km_l": round(kml, 2), "valido": motivo == "", "motivo_descarte": motivo,
                               "ressalva": "registro com odômetro inválido no meio" if ressalva else "",
                               "motorista": r["motorista"], "kml_min": r["kml_min"], "kml_max": r["kml_max"]})
            ancora, litros, n, fora, ressalva = r, 0.0, 0, False, False
    iv = pd.DataFrame(linhas, columns=["placa", "inicio", "fim", "id_inicio", "id_fim", "tipo", "km", "litros",
                                       "abastecimentos", "km_l", "valido", "motivo_descarte", "ressalva",
                                       "motorista", "kml_min", "kml_max"])
    iv["valido"] = iv["valido"].astype(bool)
    iv["substituido"] = False
    return iv


def verificar_serrote(iv: pd.DataFrame, df: pd.DataFrame, regras: dict):
    """Procura 'cheios' que não encheram: intervalo com km/L alto seguido de um com km/L baixo."""
    cfg = regras["consumo"]
    df, iv, novos = df.copy(), iv.copy(), []
    # entram também os intervalos descartados só por km/L fora da faixa: é justamente o que um
    # "cheio" que não encheu provoca (um alto demais seguido de um baixo demais)
    candidatos = iv["valido"] | iv["motivo_descarte"].str.startswith("km/L")
    for placa, g in iv[candidatos].groupby("placa"):
        validos = g[g["valido"]]
        if len(validos) < 3:
            continue
        tipico = validos["km_l"].median()
        # limite proporcional à variação normal da própria placa (troca de motorista, rota), com um mínimo
        variacao = (validos["km_l"] / tipico - 1).abs().median()
        limiar = max(cfg["limiar_serrote"], 3 * variacao)
        alto, baixo = tipico * (1 + limiar), tipico * (1 - limiar)
        cap = df.loc[df["placa"] == placa, "capacidade_tanque"].iloc[0]
        idx = list(g.sort_values("inicio").index)
        usados = set()
        for pos, i in enumerate(idx):
            if i in usados or iv.at[i, "km_l"] <= alto:
                continue
            faltou = iv.at[i, "km"] / tipico - iv.at[i, "litros"]
            if pd.notna(cap) and faltou <= (1 - cfg["tanque_referencia"]) * cap:
                continue        # encheu ao menos 90% do tanque: aceito
            id_meio = iv.at[i, "id_fim"]
            prox = idx[pos + 1] if pos + 1 < len(idx) else None
            if prox is not None and iv.at[prox, "id_inicio"] == id_meio and iv.at[prox, "km_l"] < baixo:
                df.loc[df["id"] == id_meio, "cheio_serrote"] = True
                iv.loc[[i, prox], "substituido"] = True
                usados.update([i, prox])
                km, litros = iv.at[i, "km"] + iv.at[prox, "km"], iv.at[i, "litros"] + iv.at[prox, "litros"]
                kml = km / litros
                novos.append({**iv.loc[prox].to_dict(), "inicio": iv.at[i, "inicio"], "id_inicio": iv.at[i, "id_inicio"],
                              "tipo": "combinado (serrote)", "km": km, "litros": round(litros, 2), "motivo_descarte": "",
                              "abastecimentos": iv.at[i, "abastecimentos"] + iv.at[prox, "abastecimentos"],
                              "km_l": round(kml, 2), "substituido": False,
                              "valido": bool(iv.at[i, "kml_min"] <= kml <= iv.at[i, "kml_max"])})
            elif iv.at[i, "km_l"] > tipico * (1 + 2 * limiar):
                # sem o par baixo para confirmar, só acusa quando a diferença é grande
                df.loc[df["id"] == id_meio, "cheio_abaixo_esperado"] = True
    if novos:
        iv = pd.concat([iv, pd.DataFrame(novos)], ignore_index=True)
    return iv.sort_values(["placa", "inicio"]).reset_index(drop=True), df


# ---------------------------------------------------------------------------- resumos
def _acumulado(v: pd.DataFrame, cap, ref: float):
    v = v.sort_values("inicio")
    sequencias = int((v["id_inicio"].values[1:] != v["id_fim"].values[:-1]).sum()) + 1
    kml = v["km"].sum() / v["litros"].sum()
    margem = (1 - ref) * cap * sequencias / v["litros"].sum() if pd.notna(cap) else np.nan
    return round(kml, 2), margem


def _confianca(n: int, margem) -> str:
    if n == 0:
        return "sem cálculo"
    if n == 1:
        return "baixa"
    if pd.notna(margem) and margem <= 0.02:
        return "alta"
    return "alta" if n >= 5 else "média"


def resumo_por_placa(df: pd.DataFrame, iv: pd.DataFrame, regras: dict) -> pd.DataFrame:
    ref = regras["consumo"]["tanque_referencia"]
    usaveis = iv[iv["valido"] & ~iv["substituido"]]
    linhas = []
    for placa, g in df[~df["duplicado"]].groupby("placa"):
        v = usaveis[usaveis["placa"] == placa]
        cap = g["capacidade_tanque"].iloc[0]
        kml, margem = _acumulado(v, cap, ref) if len(v) else (np.nan, np.nan)
        alertas = int(g[[c for c in ALERTAS if c in g]].any(axis=1).sum())
        linhas.append({
            "placa": placa, "modelo": g["modelo"].iloc[0], "grupo": g["grupo"].iloc[0], "base": g["base"].iloc[0],
            "abastecimentos": len(g), "litros": round(g["litros"].sum(), 1), "valor": round(g["valor"].sum(), 2),
            "preco_medio": round(g["valor"].sum() / g["litros"].sum(), 3) if g["litros"].sum() else np.nan,
            "intervalos_validos": len(v), "km_medidos": v["km"].sum(), "litros_medidos": v["litros"].sum(),
            "km_l": kml, "margem_%": round(100 * margem, 1) if pd.notna(margem) else np.nan,
            "confianca": _confianca(len(v), margem), "registros_com_alerta": alertas,
        })
    return pd.DataFrame(linhas)


def estimar_desperdicio(rp: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Compara cada veículo com a mediana do seu grupo e estima os litros (e R$) gastos a mais."""
    rp = rp.copy()
    base = rp[rp["confianca"].isin(["alta", "média"])]
    medianas = base.groupby("grupo")["km_l"].agg(["median", "count"])
    medianas = medianas[medianas["count"] >= regras["consumo"]["minimo_grupo"]]["median"]
    rp["km_l_grupo"] = rp["grupo"].map(medianas).round(2)
    esperado = rp["km_medidos"] / rp["km_l_grupo"]
    rp["litros_a_mais"] = (rp["litros_medidos"] - esperado).where(rp["km_l"] < rp["km_l_grupo"], 0).round(1)
    rp["reais_a_mais"] = (rp["litros_a_mais"] * rp["preco_medio"]).round(2)
    rp["vs_grupo_%"] = (100 * (rp["km_l"] / rp["km_l_grupo"] - 1)).round(1)
    return rp.sort_values("reais_a_mais", ascending=False).reset_index(drop=True)


def tabela_alertas(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for col, texto in ALERTAS.items():
        for _, r in df[df[col]].iterrows():
            linhas.append({"placa": r["placa"], "data_hora": r["data_hora"], "litros": r["litros"],
                           "valor": r["valor"], "odometro": r["odometro"], "posto": r["posto"],
                           "motorista": r["motorista"], "alerta": col, "descricao": texto, "id": r["id"]})
    cols = ["placa", "data_hora", "litros", "valor", "odometro", "posto", "motorista", "alerta", "descricao", "id"]
    return pd.DataFrame(linhas, columns=cols).sort_values(["placa", "data_hora"]).reset_index(drop=True)


def calcular(abastecimentos: pd.DataFrame, veiculos: pd.DataFrame | None, regras: dict) -> dict:
    df = preparar(abastecimentos, veiculos, regras)
    df = corrigir_escala_odometro(df)
    df = marcar_alertas(df, regras)
    iv = intervalos(df)
    iv, df = verificar_serrote(iv, df, regras)
    rp = estimar_desperdicio(resumo_por_placa(df, iv, regras), regras)
    return {"transacoes": df, "intervalos": iv, "por_placa": rp, "alertas": tabela_alertas(df)}
