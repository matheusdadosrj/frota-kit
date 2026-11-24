"""Roda todos os módulos sobre as tabelas canônicas. Cada módulo só roda se tiver os dados que precisa."""
from __future__ import annotations

import pandas as pd

from . import analise, consumo, diario, disponibilidade, rastreamento, solicitacoes
from .decisoes import aplicar_nas_fontes
from .modelo import EVENTOS


def executar(tabelas: dict[str, pd.DataFrame], regras: dict, data_ref=None, historico: bool = True) -> dict:
    data_ref = pd.Timestamp(data_ref) if data_ref else _data_mais_recente(tabelas)
    # 1. decisões manuais (ligar / ignorar placas) valem antes de qualquer regra
    tabelas, status_decisoes = aplicar_nas_fontes(tabelas, tabelas.get("decisoes"))
    if tabelas.get("uso") is not None and len(tabelas["uso"]):
        tabelas["uso"] = diario.classificar(tabelas["uso"], regras)
    veic = tabelas.get("veiculos")
    r: dict = {"data_ref": data_ref, "tabelas": tabelas, "decisoes": status_decisoes,
               "placas_corrigidas": tabelas.get("placas_corrigidas")}
    fontes = {k: tabelas.get(k) for k in ("ordens_servico", "uso", "abastecimentos", "posicoes", "decisoes")}

    if veic is not None:
        disp = disponibilidade.calcular(veic, regras, data_ref, **fontes)
        r["disponibilidade"] = disp
        r["resumo_disponibilidade"] = disponibilidade.resumo(disp)
        r["placas_desconhecidas"] = disponibilidade.placas_desconhecidas(
            veic, **{k: tabelas.get(k) for k in EVENTOS})
        if historico:
            h = disponibilidade.historico(veic, regras, data_ref, **fontes)
            r["historico_diario"], r["serie_disponibilidade"], r["dias_por_veiculo"] = h["diario"], h["serie"], h["por_veiculo"]
    if tabelas.get("uso") is not None and len(tabelas["uso"]):
        r["siglas_pendentes"] = diario.siglas_pendentes(tabelas["uso"])

    if tabelas.get("abastecimentos") is not None and len(tabelas["abastecimentos"]):
        c = consumo.calcular(tabelas["abastecimentos"], veic, regras)
        r["consumo"] = c["por_placa"]
        r["intervalos"] = c["intervalos"]
        r["alertas_abastecimento"] = c["alertas"]
        r["motoristas"] = analise.motoristas(c["intervalos"], regras)
        r["postos"] = analise.postos(c["transacoes"], regras)

    if tabelas.get("solicitacoes") is not None and len(tabelas["solicitacoes"]):
        r["solicitacoes"] = solicitacoes.conferir(tabelas["solicitacoes"], regras, veic, r.get("disponibilidade"))

    if tabelas.get("posicoes") is not None and len(tabelas["posicoes"]):
        r["rastreamento"] = rastreamento.ultima_posicao(tabelas["posicoes"], data_ref)

    r["indicadores"] = indicadores(r)
    return r


def _data_mais_recente(tabelas) -> pd.Timestamp:
    datas = [t[c].max() for n, t in tabelas.items() if n in EVENTOS
             for c in ("data_hora", "data") if c in t and t[c].notna().any()]
    return max(datas) if datas else pd.Timestamp.today()


def indicadores(r: dict) -> dict:
    k = {}
    if "disponibilidade" in r:
        d = r["disponibilidade"]
        ativa = d[d["categoria"] != "Fora da frota"]
        k["frota_ativa"] = len(ativa)
        k["disponiveis"] = int((ativa["situacao"] == "Disponível").sum())
        k["disponibilidade_%"] = round(100 * k["disponiveis"] / len(ativa), 1) if len(ativa) else None
        k["em_manutencao"] = int((d["categoria"] == "Manutenção").sum())
        k["ociosos"] = int((d["categoria"] == "Ocioso").sum())
        k["a_confirmar"] = int((d["categoria"] == "A confirmar").sum())
        k["veiculos_com_alerta"] = int((d["alertas"] != "").sum())
    if r.get("serie_disponibilidade") is not None:
        s = r["serie_disponibilidade"]
        k["disponibilidade_media_periodo"] = round(float(s["TOTAL"].mean()), 1)
        k["dias_com_conflito"] = int(r["historico_diario"]["conflito"].sum())
    if r.get("siglas_pendentes") is not None:
        k["siglas_sem_legenda"] = len(r["siglas_pendentes"])
    if "consumo" in r:
        c = r["consumo"]
        k["gasto_combustivel"] = round(float(c["valor"].sum()), 2)
        k["litros"] = round(float(c["litros"].sum()), 1)
        k["desperdicio_estimado"] = round(float(c["reais_a_mais"].sum()), 2)
        k["abastecimentos_com_alerta"] = int(r["alertas_abastecimento"]["id"].nunique())
    if r.get("postos") is not None and len(r["postos"]):
        k["pago_a_mais_postos"] = round(float(r["postos"].loc[r["postos"]["pago_a_mais"] > 0, "pago_a_mais"].sum()), 2)
    if "solicitacoes" in r:
        s = r["solicitacoes"]
        k["solicitacoes"] = len(s)
        k["solicitacoes_bloqueadas"] = int((~s["liberado"]).sum())
        k["valor_bloqueado"] = round(float(s.loc[~s["liberado"], "valor"].sum()), 2)
    return k
