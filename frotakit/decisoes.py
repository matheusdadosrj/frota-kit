"""Decisões manuais: o que uma pessoa decidiu na conferência, com responsável e data.

Regra automática nenhuma resolve tudo: placa digitada errada num diário, linha "RESERVA" que não
é veículo, carro batido que ainda não tem OS. Em vez de mexer no código ou na fonte, a pessoa
registra a decisão (config/decisoes.csv) e ela vale em todas as rodadas seguintes:

    placa;acao;valor;motivo;quem;data
    ABC1D28;ligar;ABC1D23;placa digitada errada no diário de novembro;Coordenação Base Sul;18/11/2026
    RESERVA;ignorar;;linha de veículo reserva, sem placa;Coordenação Base Sul;18/11/2026
    XYZ9A88;situacao;Manutenção;aguardando vistoria da seguradora;Gestão de frota;19/11/2026

* ligar     - todas as fontes passam a usar a placa de `valor` no lugar da placa informada;
* ignorar   - as linhas com essa placa são retiradas das fontes de eventos;
* situacao  - a partir de `data`, o veículo fica na categoria de `valor` (Em operação, Ocioso,
              Manutenção, Fora da frota ou A confirmar), com o motivo e o responsável à vista.

Toda decisão aparece no relatório com o status (aplicada / placa não encontrada), para que nenhuma
fique esquecida valendo para sempre sem ninguém ver.
"""
from __future__ import annotations

import pandas as pd

from .modelo import EVENTOS
from .regras import chave

CATEGORIAS = {"EM OPERACAO": "Em operação", "OCIOSO": "Ocioso", "MANUTENCAO": "Manutenção",
              "FORA DA FROTA": "Fora da frota", "A CONFIRMAR": "A confirmar"}


def aplicar_nas_fontes(tabelas: dict, decisoes: pd.DataFrame | None) -> tuple[dict, pd.DataFrame]:
    """Aplica `ligar` e `ignorar` em todas as fontes de eventos. Devolve as tabelas e o status de cada decisão."""
    if decisoes is None or decisoes.empty:
        return tabelas, pd.DataFrame()
    dec = decisoes.copy()
    dec["acao"] = dec["acao"].map(lambda a: chave(a).lower())
    dec["valor_norm"] = dec["valor"].fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    cadastro = set(tabelas["veiculos"]["placa"]) if "veiculos" in tabelas else set()
    tabelas = dict(tabelas)
    afetados = {i: 0 for i in dec.index}
    for nome in EVENTOS:
        t = tabelas.get(nome)
        if t is None or t.empty:
            continue
        t = t.copy()
        for i, d in dec.iterrows():
            alvo = t["placa"] == d["placa"]
            if d["acao"] == "ligar" and d["valor_norm"]:
                t.loc[alvo, "placa"] = d["valor_norm"]
            elif d["acao"] == "ignorar":
                t = t[~alvo]
            else:
                continue
            afetados[i] += int(alvo.sum())
        tabelas[nome] = t
    status = []
    for i, d in dec.iterrows():
        if d["acao"] == "situacao":
            ok = d["placa"] in cadastro and chave(d["valor"]) in CATEGORIAS
            status.append("aplicada" if ok else "placa fora do cadastro ou categoria inválida")
        elif d["acao"] == "ligar" and d["valor_norm"] not in cadastro:
            status.append(f"placa de destino {d['valor']} não está no cadastro")
        elif d["acao"] in ("ligar", "ignorar"):
            status.append(f"aplicada ({afetados[i]} registros)" if afetados[i] else "nenhum registro com essa placa")
        else:
            status.append("ação desconhecida (use ligar, ignorar ou situacao)")
    dec["status"] = status
    return tabelas, dec.drop(columns=["valor_norm"])


def situacoes_forcadas(decisoes: pd.DataFrame | None, data_ref) -> dict:
    """placa -> (categoria, texto do motivo) das decisões `situacao` já válidas na data."""
    if decisoes is None or decisoes.empty:
        return {}
    d = decisoes[(decisoes["acao"].map(lambda a: chave(a).lower()) == "situacao")
                 & decisoes["valor"].map(chave).isin(CATEGORIAS)]
    d = d[d["data"].isna() | (d["data"] <= pd.Timestamp(data_ref))].sort_values("data")
    saida = {}
    for _, r in d.iterrows():
        quem = ", ".join(x for x in [r["quem"] if pd.notna(r["quem"]) else "",
                                     r["data"].strftime("%d/%m/%Y") if pd.notna(r["data"]) else ""] if x)
        saida[r["placa"]] = (CATEGORIAS[chave(r["valor"])], r["data"],
                             f"decisão manual: {r['motivo'] if pd.notna(r['motivo']) else ''} ({quem})")
    return saida
