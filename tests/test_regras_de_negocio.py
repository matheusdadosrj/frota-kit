import pandas as pd
import pytest

from frotakit import consumo, disponibilidade, regras, solicitacoes
from frotakit.modelo import ErroDeEsquema, padronizar

R = regras.carregar()


def tab(entidade, linhas):
    return padronizar(pd.DataFrame(linhas), entidade)


# ---------------------------------------------------------------- modelo
def test_padronizar_converte_formatos_brasileiros():
    df = tab("abastecimentos", [{"placa": "abc-1d23", "data_hora": "05/11/2026 08:30", "litros": "1.234,50",
                                 "tanque_cheio": "Sim", "valor": "R$ 80,00"}])
    r = df.iloc[0]
    assert r["placa"] == "ABC1D23" and r["litros"] == 1234.5 and r["valor"] == 80.0
    assert r["tanque_cheio"] and r["data_hora"] == pd.Timestamp(2026, 11, 5, 8, 30)


def test_coluna_obrigatoria_faltando_explica_o_que_fazer():
    with pytest.raises(ErroDeEsquema, match="fontes.yaml"):
        padronizar(pd.DataFrame({"modelo": ["X"]}), "veiculos")


# ---------------------------------------------------------------- disponibilidade
VEIC = tab("veiculos", [
    {"placa": "AAA1A11", "base": "B1", "status_cadastro": "ativo"},
    {"placa": "BBB2B22", "base": "B1", "status_cadastro": "Vendido", "data_status": "2026-10-01"},
    {"placa": "CCC3C33", "base": "B2", "status_cadastro": "ativo"},
    {"placa": "DDD4D44", "base": "B2", "status_cadastro": "ativo"},
])
OS = tab("ordens_servico", [{"os_id": "1", "placa": "CCC3C33", "abertura": "2026-11-01", "status": "Aberta"}])
USO = tab("uso", [{"placa": "AAA1A11", "data": "2026-11-19"}, {"placa": "CCC3C33", "data": "2026-11-10"},
                  {"placa": "DDD4D44", "data": "2026-10-20"}, {"placa": "BBB2B22", "data": "2026-10-15"}])


def test_situacao_segue_a_ordem_e_explica_o_motivo():
    d = disponibilidade.calcular(VEIC, R, "2026-11-20", OS, USO).set_index("placa")
    assert d.loc["AAA1A11", "categoria"] == "Em operação"
    assert d.loc["BBB2B22", "categoria"] == "Fora da frota" and "Vendido" in d.loc["BBB2B22", "motivo"]
    assert d.loc["CCC3C33", "situacao"] == "Indisponível" and "OS 1" in d.loc["CCC3C33", "motivo"]
    assert d.loc["DDD4D44", "categoria"] == "Ocioso"


def test_fontes_que_discordam_viram_alerta():
    d = disponibilidade.calcular(VEIC, R, "2026-11-20", OS, USO).set_index("placa")
    assert "OS esquecida" in d.loc["CCC3C33", "alertas"]        # rodou depois de abrir a OS
    assert "baixado no cadastro" in d.loc["BBB2B22", "alertas"]   # rodou depois de vendido


def test_ordem_das_regras_e_configuravel():
    r = regras.carregar()
    r["disponibilidade"]["ordem"] = ["fora_da_frota", "em_operacao"]
    d = disponibilidade.calcular(VEIC, r, "2026-11-20", OS, USO).set_index("placa")
    assert d.loc["CCC3C33", "categoria"] == "Em operação"


def test_data_de_referencia_ignora_o_futuro():
    d = disponibilidade.calcular(VEIC, R, "2026-10-25", OS, USO).set_index("placa")
    assert d.loc["CCC3C33", "categoria"] == "Ocioso"       # OS e uso são posteriores a 25/10


# ---------------------------------------------------------------- consumo
VEIC_C = tab("veiculos", [{"placa": "AAA1A11", "grupo": "carro", "capacidade_tanque": 50}])


def abastecer(linhas):
    base = pd.Timestamp("2026-10-01 08:00")
    return tab("abastecimentos", [{"id": str(i), "placa": "AAA1A11", "data_hora": base + pd.Timedelta(days=3 * i),
                                   "litros": l, "odometro": o, "tanque_cheio": c, "valor": l * 6.1}
                                  for i, (l, o, c) in enumerate(linhas)])


def test_km_por_litro_entre_tanques_cheios_inclui_parciais():
    c = consumo.calcular(abastecer([(40, 10_000, True), (10, 10_200, False), (30, 10_480, True)]), VEIC_C, R)
    iv = c["intervalos"].iloc[0]
    assert iv["km"] == 480 and iv["litros"] == 40 and iv["km_l"] == 12.0


def test_registro_em_dobro_nao_entra_na_conta():
    t = abastecer([(40, 10_000, True), (35.2, 10_420, True), (33.1, 10_820, True)])
    dup = t.iloc[[1]].assign(id="x", data_hora=t.iloc[1]["data_hora"] + pd.Timedelta(minutes=3))
    c = consumo.calcular(pd.concat([t, dup]), VEIC_C, R)
    assert c["transacoes"]["duplicado"].sum() == 1
    assert c["intervalos"]["litros"].tolist() == [35.2, 33.1]


def test_salto_de_digitacao_e_trecho_longo_sao_diferentes():
    # 10.400 -> 40.800 -> 11.200: erro de digitação (o seguinte desmente o salto)
    c = consumo.calcular(abastecer([(40, 10_000, True), (35, 10_400, True), (34, 40_800, True), (33, 11_200, True)]),
                         VEIC_C, R)
    assert c["transacoes"].loc[2, "salto_odometro"]
    # 10.400 -> 11.700 -> 12.100: rodou 1.300 km sem registro (o seguinte confirma)
    c = consumo.calcular(abastecer([(40, 10_000, True), (35, 10_400, True), (34, 11_700, True), (33, 12_100, True)]),
                         VEIC_C, R)
    assert c["transacoes"].loc[2, "trecho_longo"] and not c["transacoes"].loc[2, "salto_odometro"]


def test_odometro_com_digito_a_mais_e_corrigido():
    c = consumo.calcular(abastecer([(40, 10_000, True), (35, 104_000, True), (33, 10_800, True)]), VEIC_C, R)
    t = c["transacoes"]
    assert t.loc[1, "odometro_corrigido"] and t.loc[1, "odometro"] == 10_400


def test_serrote_junta_os_intervalos_e_devolve_o_km_l_certo():
    linhas, odo = [(40, 10_000, True)], 10_000
    for i in range(8):                       # 12 km/L, 420 km por intervalo
        odo += 420
        linhas.append((35, odo, True))
    odo += 420
    linhas.append((19, odo, True))           # "cheio" que parou na metade
    odo += 420
    linhas.append((51, odo, True))           # o que faltou entra no seguinte
    c = consumo.calcular(abastecer(linhas), VEIC_C, R)
    assert c["transacoes"]["cheio_serrote"].sum() == 1
    comb = c["intervalos"].query("tipo == 'combinado (serrote)'").iloc[0]
    assert comb["km_l"] == pytest.approx(12.0, abs=0.01)
    assert c["por_placa"].iloc[0]["km_l"] == pytest.approx(12.0, abs=0.01)


# ---------------------------------------------------------------- pedidos de PIX
def test_conferencia_de_pedidos():
    s = tab("solicitacoes", [
        {"data_hora": "2026-11-20 08:00", "placa": "AAA1A11", "odometro": 5000, "chave_pix": "x", "motorista": "M1"},
        {"data_hora": "2026-11-20 08:40", "placa": "AAA1A11", "odometro": 5000, "chave_pix": "x", "motorista": "M1"},
        {"data_hora": "2026-11-21 08:00", "placa": "AAA1A11", "odometro": 5000, "chave_pix": "x", "motorista": "M1"},
        {"data_hora": "2026-11-21 09:00", "placa": "AAA1A", "odometro": 7000, "chave_pix": "x"},
        {"data_hora": "2026-11-21 10:00", "placa": "ZZZ9Z99", "odometro": 9000, "chave_pix": ""},
    ])
    c = solicitacoes.conferir(s, R, VEIC_C)
    assert "reenvio" in c.loc[1, "alertas"]
    assert "outro dia" in c.loc[2, "alertas"]
    assert "placa inválida" in c.loc[3, "alertas"]
    assert "fora do cadastro" in c.loc[4, "alertas"] and "sem chave PIX" in c.loc[4, "alertas"]
