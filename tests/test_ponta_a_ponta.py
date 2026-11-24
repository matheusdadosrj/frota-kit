"""Gera a frota fictícia e confere que o kit encontra cada problema plantado em exemplos/gerar_dados.py."""
import runpy
from pathlib import Path

import pytest

from frotakit import adaptadores, pipeline, regras, relatorio

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def res():
    runpy.run_path(str(RAIZ / "exemplos" / "gerar_dados.py"), run_name="__main__")
    return pipeline.executar(adaptadores.carregar(RAIZ / "config" / "fontes.yaml"), regras.carregar())


def test_disponibilidade(res):
    d = res["disponibilidade"]
    assert (d["categoria"] == "Fora da frota").sum() == 3
    assert (d["categoria"] == "Manutenção").sum() == 7        # 5 por OS, 1 só no diário, 1 por decisão
    assert (d["categoria"] == "Ocioso").sum() == 3
    assert (d["categoria"] == "A confirmar").sum() == 1       # sigla RIO
    assert d["motivo"].str.contains("decisão manual").sum() == 1
    assert d["confirmacao"].str.startswith("só 1 fonte (diário").sum() == 1
    assert d["alertas"].str.contains("OS esquecida").sum() == 1
    assert d["alertas"].str.contains("na oficina há").sum() == 1
    assert d["alertas"].str.contains("baixado no cadastro").sum() == 1
    assert d["alertas"].str.contains("sem sinal").sum() == 1


def test_qualidade_do_abastecimento(res):
    tipos = res["alertas_abastecimento"]["alerta"].value_counts()
    for alerta, minimo in [("duplicado", 2), ("odometro_corrigido", 1), ("salto_odometro", 1),
                           ("trecho_longo", 1), ("acima_tanque", 1), ("cheio_serrote", 4)]:
        assert tipos.get(alerta, 0) >= minimo, alerta


def test_motoristas_e_postos(res):
    m = res["motoristas"].set_index("motorista")
    assert m.loc["Motorista 07", "conclusao"] == "consome mais que o normal do veículo"
    assert m.loc["Motorista 12", "conclusao"] == "consome menos que o normal do veículo"
    assert (m["conclusao"] != "dentro do normal").sum() == 2          # sem falsos positivos
    assert res["postos"].iloc[0]["posto"] == "Posto Delta"


def test_pedidos_de_pix(res):
    alertas = " | ".join(res["solicitacoes"]["alertas"])
    for trecho in ["reenvio", "outro dia", "placa inválida", "fora do cadastro", "sem chave PIX", "indisponível"]:
        assert trecho in alertas, trecho


def test_rastreadores_de_dois_fornecedores(res):
    assert set(res["rastreamento"]["fornecedor"]) == {"Rastreador A", "Rastreador B"}


def test_relatorios(res, tmp_path):
    h = relatorio.gerar_html(res, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Disponibilidade" in h and "ZZ" in h
    assert relatorio.gerar_excel(res, tmp_path / "r.xlsx").stat().st_size > 10_000


def test_diario_placas_e_decisoes(res):
    assert res["siglas_pendentes"]["sigla"].tolist() == ["RIO"]
    assert len(res["placas_corrigidas"]) == 1                      # O no lugar do zero
    desc = res["placas_desconhecidas"]
    assert desc["diagnostico"].eq("provável erro de digitação").sum() == 1 and desc["sugestao"].str.len().max() == 7
    assert "RESERVA" not in set(desc["placa"])                     # ignorada por decisão
    assert res["decisoes"]["status"].str.startswith("aplicada").all()


def test_historico(res):
    s = res["serie_disponibilidade"]
    assert len(s) == 30 and s["TOTAL"].iloc[-1] == res["indicadores"]["disponibilidade_%"]
    conflitos = res["historico_diario"].query("conflito")["placa"].unique()
    assert len(conflitos) == 1                                     # o veículo da OS esquecida
