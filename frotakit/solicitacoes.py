"""Conferência de pedidos de pagamento de abastecimento feitos fora do cartão frota.

Muitas operações ainda pagam combustível por PIX a partir de um formulário (WhatsApp, Forms,
e-mail). Antes de pagar, cada pedido passa por estas regras:

* placa inválida ou fora do cadastro;
* veículo baixado ou com OS aberta (quem abasteceu um carro que está na oficina?);
* sem odômetro / sem chave PIX;
* reenvio: mesma placa e mesmo odômetro em poucas horas (pagaria duas vezes);
* odômetro repetido em outro dia (foto/valor copiado);
* odômetro menor que o último pedido da placa;
* mesmo motorista e mesmo odômetro em outra placa (placa digitada errada).
"""
from __future__ import annotations

import re

import pandas as pd


def conferir(solic: pd.DataFrame, regras: dict, veiculos: pd.DataFrame | None = None,
             disponibilidade: pd.DataFrame | None = None) -> pd.DataFrame:
    cfg = regras["solicitacoes"]
    df = solic.sort_values("data_hora").reset_index(drop=True).copy()
    padrao = re.compile(cfg["regex_placa"])
    conhecidas = set(veiculos["placa"]) if veiculos is not None else None
    indisp = ({} if disponibilidade is None else
              disponibilidade.set_index("placa").query("situacao == 'Indisponível'")["motivo"].to_dict())
    janela = pd.Timedelta(hours=cfg["horas_reenvio"])
    alertas = []
    for i, r in df.iterrows():
        a = []
        placa = r["placa"] if isinstance(r["placa"], str) else ""
        if not padrao.match(placa):
            a.append("placa inválida/incompleta")
        elif conhecidas is not None and placa not in conhecidas:
            a.append("placa fora do cadastro")
        if placa in indisp:
            a.append(f"veículo indisponível ({indisp[placa]})")
        if pd.isna(r["odometro"]):
            a.append("sem odômetro")
        if not (isinstance(r["chave_pix"], str) and r["chave_pix"].strip()):
            a.append("sem chave PIX")
        mesma = df[(df.index != i) & (df["placa"] == placa)]
        if pd.notna(r["odometro"]):
            iguais = mesma[mesma["odometro"] == r["odometro"]]
            if ((iguais["data_hora"] - r["data_hora"]).abs() <= janela).any():
                a.append("provável reenvio (mesma placa e odômetro em poucas horas)")
            elif len(iguais):
                a.append("mesmo odômetro de outro dia: valor possivelmente copiado")
            anteriores = mesma[(mesma.index < i) & mesma["odometro"].notna()]
            if len(anteriores) and r["odometro"] < anteriores["odometro"].max():
                a.append("odômetro menor que o de um pedido anterior")
            outra = df[(df["placa"] != placa) & (df["odometro"] == r["odometro"]) & (df["motorista"] == r["motorista"])]
            if len(outra):
                a.append("mesmo motorista e odômetro em outra placa: conferir a placa")
        alertas.append("; ".join(a))
    df["alertas"] = alertas
    df["liberado"] = df["alertas"] == ""
    return df
