import sqlite3

import pandas as pd
import pytest
import yaml

from frotakit import adaptadores
from frotakit.adaptadores import api


def escrever_config(tmp_path, cfg):
    (tmp_path / "config").mkdir()
    caminho = tmp_path / "config" / "fontes.yaml"
    caminho.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return caminho


def test_csv_com_mapeamento_de_colunas(tmp_path):
    (tmp_path / "cartao.csv").write_text("Placa;Data;Qtd Litros\nabc1d23;01/11/2026 10:00;40,5\n", encoding="utf-8")
    cfg = escrever_config(tmp_path, {"abastecimentos": {
        "tipo": "arquivo", "caminho": "cartao.csv", "separador": ";",
        "colunas": {"Placa": "placa", "Data": "data_hora", "Qtd Litros": "litros"}}})
    t = adaptadores.carregar(cfg)["abastecimentos"]
    assert t.loc[0, "placa"] == "ABC1D23" and t.loc[0, "litros"] == 40.5


def test_sql_sqlite_e_varias_fontes_concatenadas(tmp_path):
    with sqlite3.connect(tmp_path / "erp.sqlite") as con:
        con.execute("CREATE TABLE v (PLACA TEXT)")
        con.execute("INSERT INTO v VALUES ('AAA1A11')")
    (tmp_path / "extra.csv").write_text("placa\nBBB2B22\n", encoding="utf-8")
    cfg = escrever_config(tmp_path, {"veiculos": [
        {"tipo": "sql", "conexao": "sqlite:///erp.sqlite", "consulta": "SELECT PLACA AS placa FROM v"},
        {"tipo": "arquivo", "caminho": "extra.csv"}]})
    assert adaptadores.carregar(cfg)["veiculos"]["placa"].tolist() == ["AAA1A11", "BBB2B22"]


def test_placa_extraida_do_apelido_do_rastreador(tmp_path):
    (tmp_path / "r.csv").write_text("Veiculo,Quando\nVan 03 - ABC-1D23,2026-11-20 10:00\n", encoding="utf-8")
    cfg = escrever_config(tmp_path, {"posicoes": {"tipo": "arquivo", "caminho": "r.csv", "placa_de": "Veiculo",
                                                  "colunas": {"Quando": "data_hora"}, "fixos": {"fornecedor": "B"}}})
    p = adaptadores.carregar(cfg)["posicoes"]
    assert p.loc[0, "placa"] == "ABC1D23" and p.loc[0, "fornecedor"] == "B"


def test_segredo_ausente_falha_com_mensagem_clara(tmp_path, monkeypatch):
    monkeypatch.delenv("TOKEN_INEXISTENTE", raising=False)
    cfg = escrever_config(tmp_path, {"abastecimentos": {"tipo": "api", "url": "https://x", "token": "${TOKEN_INEXISTENTE}"}})
    with pytest.raises(KeyError, match="TOKEN_INEXISTENTE"):
        adaptadores.carregar(cfg)


def test_whatsapp(tmp_path):
    (tmp_path / "c.txt").write_text(
        "20/11/2026 08:00 - Supervisor: FORMULÁRIO DE ABASTECIMENTO\nPLACA: abc1d23\nVALOR: R$ 150,00\nKM: 45.120\n"
        "PIX DO POSTO: 00.000.000/0001-00\n20/11/2026 08:05 - Financeiro: Pago\n"
        "[20/11/2026, 09:10:00] Outro: formulario de abastecimento\nPLACA: XYZ9A88\nKM: 1000\n", encoding="utf-8")
    cfg = escrever_config(tmp_path, {"solicitacoes": {"tipo": "whatsapp", "caminho": "c.txt",
                                                      "gatilho": "FORMULARIO DE ABASTECIMENTO"}})
    s = adaptadores.carregar(cfg)["solicitacoes"]
    assert len(s) == 2
    assert s.loc[0, "odometro"] == 45120 and s.loc[0, "valor"] == 150 and s.loc[0, "placa"] == "ABC1D23"
    assert s.loc[1, "enviado_por"] == "Outro"


class SessaoFalsa:
    """Imita requests.Session: 2 páginas de 2 registros e uma vazia."""
    def __init__(self):
        self.chamadas = []

    def get(self, url, params, headers, timeout):
        self.chamadas.append((dict(params), headers))
        pagina = params["page"]
        dados = [{"plate": f"AAA1A1{pagina}", "liters": 10 * pagina}] * (2 if pagina < 3 else 0)

        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"data": {"items": dados}}
        return Resp()


def test_api_pagina_e_envia_token(tmp_path):
    s = SessaoFalsa()
    cfg = {"url": "https://x", "token": "segredo", "registros_em": "data.items",
           "paginacao": {"parametro": "page", "inicio": 1, "tamanho_parametro": "size", "tamanho": 2}}
    df = api.ler(cfg, tmp_path, sessao=s)
    assert len(df) == 4 and len(s.chamadas) == 3
    assert s.chamadas[0][1]["Authorization"] == "Bearer segredo"
