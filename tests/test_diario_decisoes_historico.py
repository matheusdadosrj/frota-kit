import pandas as pd
from openpyxl import Workbook

from frotakit import disponibilidade, regras
from frotakit.adaptadores import grade
from frotakit.decisoes import aplicar_nas_fontes
from frotakit.diario import classificar, siglas_pendentes
from frotakit.modelo import corrigir_placa, padronizar, parecidas

R = regras.carregar()


def tab(entidade, linhas):
    return padronizar(pd.DataFrame(linhas), entidade)


# ---------------------------------------------------------------- placas
def test_correcao_pela_posicao_so_quando_resolve():
    entrada = pd.Series(["ABCO123", "1BC1D23", "ABC1D23", "RESERVA", "AB1"])
    assert corrigir_placa(entrada).tolist() == ["ABC0123", "IBC1D23", "ABC1D23", "RESERVA", "AB1"]


def test_sugestao_de_placa_parecida():
    assert parecidas("ABC1D28", {"ABC1D23", "XYZ9A88"}) == ["ABC1D23"]
    assert parecidas("ABC1D28", {"ABC9D99"}) == []


def test_placa_desconhecida_tem_diagnostico_e_nunca_e_ligada_sozinha():
    veic = tab("veiculos", [{"placa": "ABC1D23"}])
    uso = tab("uso", [{"placa": "ABC1D28", "data": "2026-11-01"}, {"placa": "SAIU", "data": "2026-11-01"}])
    d = disponibilidade.placas_desconhecidas(veic, uso=uso).set_index("placa")
    assert d.loc["ABC1D28", "sugestao"] == "ABC1D23"
    assert d.loc["SAIU", "diagnostico"].startswith("formato inválido")


# ---------------------------------------------------------------- diário
def test_siglas_do_dicionario_numeros_e_sigla_nova():
    uso = tab("uso", [{"placa": "A", "data": "2026-11-01", "codigo": c} for c in ["2", "0", "m", "F", "RIO", None]])
    c = classificar(uso, R)
    assert c["grupo"].tolist() == ["rodou", "parado", "manutencao", "parado", "?", "rodou"]
    assert siglas_pendentes(c)["sigla"].tolist() == ["RIO"]


def test_sigla_do_diario_decide_a_situacao():
    veic = tab("veiculos", [{"placa": p} for p in ["AAA1A11", "BBB2B22", "CCC3C33"]])
    uso = tab("uso", [{"placa": "AAA1A11", "data": "2026-11-19", "codigo": "M"},
                      {"placa": "BBB2B22", "data": "2026-11-19", "codigo": "XPTO"},
                      {"placa": "CCC3C33", "data": "2026-11-19", "codigo": "F"},
                      {"placa": "CCC3C33", "data": "2026-11-18", "codigo": "1"}])
    d = disponibilidade.calcular(veic, R, "2026-11-20", uso=uso).set_index("placa")
    assert d.loc["AAA1A11", "categoria"] == "Manutenção" and "abrir OS" in d.loc["AAA1A11", "alertas"]
    assert d.loc["AAA1A11", "confirmacao"].startswith("só 1 fonte")
    assert d.loc["BBB2B22", "situacao"] == "A confirmar"
    assert d.loc["CCC3C33", "categoria"] == "Em operação"          # folga não é atividade, mas rodou no dia 18


def test_leitor_de_grade(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "NOV"
    ws.append(["DIÁRIO DE BORDO - BASE X"])
    ws.append([])
    dias = pd.date_range("2026-11-01", periods=10).to_pydatetime().tolist()
    ws.append(["PLACA", "MODELO", "TOTAL"] + dias)
    ws.append(["abc-1d23", "Van", 3, 1, 2, "M", None, "F", 0, 0, 0, 0, 0])
    ws.append(["XYZ9A88", "Van", 1, 1, None, None, None, None, 0, 0, 0, 0, 0])
    wb.create_sheet("LEGENDA").append(["SIGLA", "SIGNIFICADO"])
    wb.save(tmp_path / "d.xlsx")
    df = grade.ler({"caminho": "d.xlsx"}, tmp_path)
    assert df["data"].max() == pd.Timestamp("2026-11-05")           # dias futuros com 0 cortados
    assert df[df["placa"] == "abc-1d23"]["codigo"].tolist() == ["1", "2", "M", "F"]
    assert set(df["origem"]) == {"diário (NOV)"}


# ---------------------------------------------------------------- decisões
def test_decisoes_ligar_ignorar_e_situacao():
    veic = tab("veiculos", [{"placa": "ABC1D23"}, {"placa": "XYZ9A88"}])
    uso = tab("uso", [{"placa": "ABC1D28", "data": "2026-11-19"}, {"placa": "RESERVA", "data": "2026-11-19"},
                      {"placa": "XYZ9A88", "data": "2026-11-19"}])
    dec = tab("decisoes", [
        {"placa": "ABC1D28", "acao": "ligar", "valor": "ABC1D23", "quem": "Ana", "data": "18/11/2026"},
        {"placa": "RESERVA", "acao": "ignorar"},
        {"placa": "XYZ9A88", "acao": "situacao", "valor": "Manutenção", "motivo": "batido", "quem": "Ana",
         "data": "18/11/2026"}])
    t, status = aplicar_nas_fontes({"veiculos": veic, "uso": uso}, dec)
    assert sorted(t["uso"]["placa"]) == ["ABC1D23", "XYZ9A88"]
    assert status["status"].str.startswith("aplicada").all()
    d = disponibilidade.calcular(veic, R, "2026-11-20", uso=t["uso"], decisoes=dec).set_index("placa")
    assert d.loc["XYZ9A88", "categoria"] == "Manutenção" and "Ana" in d.loc["XYZ9A88", "motivo"]
    assert "rever a decisão" in d.loc["XYZ9A88", "alertas"]          # rodou depois da decisão
    antes = disponibilidade.calcular(veic, R, "2026-11-17", uso=t["uso"], decisoes=dec).set_index("placa")
    assert antes.loc["XYZ9A88", "categoria"] != "Manutenção"         # a decisão só vale a partir da data


# ---------------------------------------------------------------- duas fontes e histórico
def test_confirmacao_por_duas_fontes():
    veic = tab("veiculos", [{"placa": "AAA1A11", "status_cadastro": "vendido", "data_status": "2026-10-01"},
                            {"placa": "BBB2B22", "status_cadastro": "vendido", "data_status": "2026-10-01"}])
    uso = tab("uso", [{"placa": "AAA1A11", "data": "2026-09-20"}, {"placa": "BBB2B22", "data": "2026-10-20"}])
    d = disponibilidade.calcular(veic, R, "2026-11-20", uso=uso).set_index("placa")
    assert d.loc["AAA1A11", "confirmacao"] == "confirmada por 2 fontes"
    assert d.loc["BBB2B22", "confirmacao"] == "conflito entre fontes"


def test_historico_aplica_a_regra_dia_a_dia_e_marca_conflito():
    veic = tab("veiculos", [{"placa": "AAA1A11", "base": "B"}, {"placa": "BBB2B22", "base": "B"}])
    os_ = tab("ordens_servico", [{"os_id": "1", "placa": "AAA1A11", "abertura": "2026-11-15", "status": "aberta"}])
    uso = tab("uso", [{"placa": p, "data": d} for p in ["AAA1A11", "BBB2B22"]
                      for d in pd.date_range("2026-11-10", "2026-11-20")])
    h = disponibilidade.historico(veic, R, "2026-11-20", dias=10, ordens_servico=os_, uso=uso)
    serie = h["serie"].set_index("data")["TOTAL"]
    assert serie["2026-11-14"] == 100 and serie["2026-11-15"] == 50
    assert h["diario"]["conflito"].sum() == 6                       # rodou de 15 a 20 com a OS aberta
    assert h["por_veiculo"].set_index("placa").loc["AAA1A11", "dias_manutencao"] == 6
