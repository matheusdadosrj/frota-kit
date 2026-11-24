"""Painel interativo do frota-kit.

    streamlit run app/streamlit_app.py
    streamlit run app/streamlit_app.py -- --fontes config/fontes.local.yaml

Usa as mesmas fontes, regras e cálculos da linha de comando; só muda a forma de ver.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from frotakit import adaptadores, pipeline, regras, relatorio  # noqa: E402

arg = argparse.ArgumentParser()
arg.add_argument("--fontes", default=str(RAIZ / "config" / "fontes.yaml"))
arg.add_argument("--regras", default=str(RAIZ / "config" / "regras.yaml"))
ARGS, _ = arg.parse_known_args()

st.set_page_config(page_title="Controle de frota", page_icon="🚚", layout="wide")


@st.cache_data(show_spinner="Lendo as fontes...")
def carregar(fontes: str):
    if not (RAIZ / "dados_exemplo" / "erp.sqlite").exists() and fontes.endswith("config/fontes.yaml"):
        import runpy
        runpy.run_path(str(RAIZ / "exemplos" / "gerar_dados.py"), run_name="__main__")
    return adaptadores.carregar(fontes)


@st.cache_data(show_spinner="Calculando...")
def calcular(fontes: str, arquivo_regras: str, data_ref, ajustes: tuple):
    r = regras.carregar(arquivo_regras)
    for secao, chave, valor in ajustes:
        r[secao][chave] = valor
    res = pipeline.executar(carregar(fontes), r, data_ref)
    res.pop("tabelas", None)
    return res


tabelas = carregar(ARGS.fontes)
datas = [t[c].max() for t in tabelas.values() for c in ("data_hora", "data") if c in t and t[c].notna().any()]
ultima = max(datas).date()

with st.sidebar:
    st.header("Parâmetros")
    data_ref = st.date_input("Data de referência", ultima, max_value=ultima, format="DD/MM/YYYY")
    base_cfg = regras.carregar(ARGS.regras)
    dias_ocioso = st.slider("Dias sem atividade para 'ocioso'", 1, 30, base_cfg["disponibilidade"]["dias_ocioso"])
    sobrepreco = st.slider("Sobrepreço de posto que merece atenção (%)", 0, 15,
                           int(100 * base_cfg["analise"]["sobrepreco_minimo"]))
    st.caption("Os padrões ficam em config/regras.yaml.")

res = calcular(ARGS.fontes, ARGS.regras, pd.Timestamp(data_ref),
               (("disponibilidade", "dias_ocioso", dias_ocioso), ("analise", "sobrepreco_minimo", sobrepreco / 100)))
bases = sorted(res["disponibilidade"]["base"].dropna().unique()) if "disponibilidade" in res else []
with st.sidebar:
    filtro_base = st.multiselect("Bases", bases, default=bases)


def por_base(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["base"].isin(filtro_base)] if "base" in df and filtro_base else df


st.title("Controle de frota")
st.caption(f"Situação em {data_ref:%d/%m/%Y}")

k = res["indicadores"]
cols = st.columns(3) + st.columns(3)
for col, chave in zip(cols, ["disponibilidade_%", "disponibilidade_media_periodo", "em_manutencao",
                             "gasto_combustivel", "desperdicio_estimado", "valor_bloqueado"]):
    if chave in k:
        rotulo, texto = relatorio.formatar_kpi(chave, k[chave])
        col.metric(rotulo, texto)

abas = st.tabs(["Disponibilidade", "Histórico", "Consumo", "Motoristas e postos", "Pedidos de PIX", "Rastreadores",
               "Qualidade dos dados"])

with abas[0]:
    d = por_base(res["disponibilidade"])
    c1, c2 = st.columns([2, 3])
    with c1:
        st.subheader("Por base")
        st.dataframe(res["resumo_disponibilidade"], hide_index=True, width="stretch")
    with c2:
        st.subheader("Veículos fora de operação")
        st.bar_chart(d[d["categoria"] != "Em operação"].groupby(["base", "categoria"]).size().unstack(fill_value=0))
    categorias = st.multiselect("Categorias", d["categoria"].unique().tolist(), default=d["categoria"].unique().tolist())
    so_alerta = st.toggle("Só veículos com alerta")
    v = d[d["categoria"].isin(categorias)]
    if so_alerta:
        v = v[v["alertas"] != ""]
    st.dataframe(v, hide_index=True, width="stretch")

with abas[1]:
    if "serie_disponibilidade" in res:
        st.subheader("Disponibilidade por dia")
        st.caption("A mesma regra de hoje aplicada a cada dia do período. 'A confirmar' conta como não disponível.")
        serie = res["serie_disponibilidade"]
        longa = serie.melt("data", [c for c in serie.columns if c in filtro_base] + ["TOTAL"],
                           var_name="base", value_name="disponibilidade_%")
        st.altair_chart(
            alt.Chart(longa).mark_line(point=True).encode(
                x=alt.X("data:T", title=None, axis=alt.Axis(format="%d/%m")),
                y=alt.Y("disponibilidade_%:Q", title="disponibilidade (%)", scale=alt.Scale(zero=False)),
                color=alt.Color("base:N", title=None), tooltip=["data:T", "base:N", "disponibilidade_%:Q"]),
            width="stretch")
        pv = por_base(res["dias_por_veiculo"])
        st.subheader("Dias parados por veículo")
        st.dataframe(pv, hide_index=True, width="stretch")
        h = res["historico_diario"]
        conflitos = por_base(h[h["conflito"]])
        if len(conflitos):
            st.subheader("Dias com conflito entre fontes")
            st.caption("O veículo rodou num dia em que alguma fonte dizia que estava em manutenção.")
            st.dataframe(conflitos, hide_index=True, width="stretch")

with abas[2]:
    if "consumo" in res:
        c = por_base(res["consumo"])
        st.subheader("Onde está o gasto a mais (R$ acima da mediana do grupo)")
        top = c[c["reais_a_mais"] > 0].head(15)
        st.bar_chart(top, x="placa", y="reais_a_mais", color="grupo", horizontal=True, sort="-reais_a_mais")
        st.dataframe(c, hide_index=True, width="stretch",
                     column_config={"vs_grupo_%": st.column_config.NumberColumn(format="%.1f%%")})
        placa = st.selectbox("Histórico de uma placa", c["placa"])
        iv = res["intervalos"]
        h = iv[(iv["placa"] == placa) & ~iv["substituido"]]
        st.line_chart(h.set_index("fim")["km_l"])
        st.dataframe(h, hide_index=True, width="stretch")

with abas[3]:
    if "motoristas" in res:
        st.subheader("Motoristas")
        st.caption("Comparados com outros motoristas nos mesmos veículos. Só é conclusivo quando o IC 95% inteiro fica de um lado do zero.")
        st.dataframe(res["motoristas"], hide_index=True, width="stretch")
        st.subheader("Postos")
        st.dataframe(res["postos"], hide_index=True, width="stretch")

with abas[4]:
    if "solicitacoes" in res:
        s = res["solicitacoes"]
        st.metric("Retidos para conferência", f"{(~s['liberado']).sum()} de {len(s)}")
        st.dataframe(s.sort_values("liberado"), hide_index=True, width="stretch")

with abas[5]:
    if "rastreamento" in res:
        r = res["rastreamento"]
        st.map(r.dropna(subset=["latitude", "longitude"]), latitude="latitude", longitude="longitude")
        st.dataframe(r, hide_index=True, width="stretch")

with abas[6]:
    if "alertas_abastecimento" in res:
        a = res["alertas_abastecimento"]
        st.subheader("Alertas por tipo")
        st.bar_chart(a["alerta"].value_counts())
        st.dataframe(a, hide_index=True, width="stretch")
    if len(res.get("placas_desconhecidas", [])):
        st.subheader("Placas fora do cadastro")
        st.caption("Nada é ligado automaticamente. Para resolver, registre a decisão (ligar ou ignorar) no decisoes.csv.")
        st.dataframe(res["placas_desconhecidas"], hide_index=True, width="stretch")
    if res.get("placas_corrigidas") is not None and len(res["placas_corrigidas"]):
        st.subheader("Placas corrigidas automaticamente")
        st.dataframe(res["placas_corrigidas"], hide_index=True)
    if res.get("siglas_pendentes") is not None and len(res["siglas_pendentes"]):
        st.subheader("Siglas do diário sem legenda")
        st.dataframe(res["siglas_pendentes"], hide_index=True)
    if res.get("decisoes") is not None and len(res["decisoes"]):
        st.subheader("Decisões manuais")
        st.dataframe(res["decisoes"], hide_index=True, width="stretch")
