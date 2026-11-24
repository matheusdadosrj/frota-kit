"""Disponibilidade da frota: situação de cada veículo numa data, sempre com o motivo.

Regra (configurável em config/regras.yaml -> disponibilidade.ordem):

1. decisao_manual     - decisão registrada por uma pessoa (config/decisoes.csv)      -> a categoria decidida
2. fora_da_frota      - cadastro com status de baixa (vendido, devolvido, sinistro)   -> Indisponível
3. os_aberta          - ordem de serviço ainda aberta                                 -> Indisponível
4. diario_manutencao  - última sigla do diário é de manutenção, mesmo sem OS          -> Indisponível
5. a_confirmar        - última sigla do diário não está no dicionário                 -> A confirmar
6. ocioso             - sem uso, abastecimento ou ignição há mais de N dias           -> Disponível (ocioso)
7. em_operacao        - todo o resto                                                  -> Disponível

A primeira regra que se aplica decide. As fontes que discordam da decisão não são descartadas:
viram alertas ("OS aberta, mas o veículo abasteceu depois da abertura"), que é onde mora o
problema de processo que vale corrigir na origem.

Cada situação de indisponibilidade diz também **quantas fontes a confirmam** (coluna
`confirmacao`): uma baixa no cadastro sem nenhuma atividade depois dela é "confirmada por 2
fontes"; uma manutenção que só existe no diário, sem OS, é "só 1 fonte" e pede que alguém abra a OS.
"""
from __future__ import annotations

import pandas as pd

from . import diario
from .decisoes import situacoes_forcadas
from .modelo import PLACA_VALIDA, parecidas
from .regras import chave

INDISPONIVEL, DISPONIVEL, A_CONFIRMAR = "Indisponível", "Disponível", "A confirmar"
SITUACAO_DA_CATEGORIA = {"Em operação": DISPONIVEL, "Ocioso": DISPONIVEL, "Manutenção": INDISPONIVEL,
                         "Fora da frota": INDISPONIVEL, "A confirmar": A_CONFIRMAR}
CATEGORIAS = ["Em operação", "Ocioso", "A confirmar", "Manutenção", "Fora da frota"]
COLUNAS = ["placa", "modelo", "grupo", "base", "situacao", "categoria", "motivo", "confirmacao", "alertas",
           "ultima_atividade", "fonte_ultima_atividade", "dias_sem_atividade", "ultimo_codigo", "data_codigo",
           "os_aberta", "os_abertura", "dias_na_oficina", "oficina", "ultima_posicao", "dias_sem_sinal", "endereco"]


def _fmt(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m/%Y") if pd.notna(d) else "-"


def _ultima_atividade(uso, abastecimentos, posicoes) -> pd.DataFrame:
    """Data mais recente em que há prova de que o veículo rodou, e de qual fonte ela veio."""
    partes = []
    if uso is not None and len(uso):
        rodou = uso[uso["grupo"] == "rodou"]           # folga, sem rota e manutenção não são atividade
        partes.append(rodou[["placa", "data"]].rename(columns={"data": "quando"})
                      .assign(fonte=rodou["origem"].fillna("uso/viagem").values))
    if abastecimentos is not None and len(abastecimentos):
        partes.append(abastecimentos[["placa", "data_hora"]].rename(columns={"data_hora": "quando"})
                      .assign(fonte="abastecimento"))
    if posicoes is not None and len(posicoes):
        lig = posicoes[posicoes["ignicao"].fillna(False).astype(bool)]
        partes.append(lig[["placa", "data_hora"]].rename(columns={"data_hora": "quando"})
                      .assign(fonte="rastreador (ignição ligada)"))
    if not partes:
        return pd.DataFrame(columns=["placa", "ultima_atividade", "fonte_ultima_atividade"])
    tudo = pd.concat(partes).dropna(subset=["quando"]).sort_values("quando")
    ult = tudo.groupby("placa").tail(1)
    return ult.rename(columns={"quando": "ultima_atividade", "fonte": "fonte_ultima_atividade"})


def _os_abertas(os_: pd.DataFrame | None, regras: dict, data_ref) -> pd.DataFrame:
    vazio = pd.DataFrame(columns=["placa", "os_aberta", "os_abertura", "oficina", "descricao_os"])
    if os_ is None or os_.empty:
        return vazio
    abertos = {chave(s) for s in regras["disponibilidade"]["status_os_aberta"]}
    st = os_["status"].map(chave)
    aberta = (st.isin(abertos) | (st.eq("") & os_["fechamento"].isna())) & (os_["abertura"] <= data_ref)
    a = os_[aberta].sort_values("abertura").groupby("placa").tail(1)
    return a.rename(columns={"os_id": "os_aberta", "abertura": "os_abertura", "descricao": "descricao_os"})[
        ["placa", "os_aberta", "os_abertura", "oficina", "descricao_os"]]


def _ultima_posicao(posicoes) -> pd.DataFrame:
    if posicoes is None or posicoes.empty:
        return pd.DataFrame(columns=["placa", "ultima_posicao", "endereco"])
    p = posicoes.dropna(subset=["data_hora"]).sort_values("data_hora").groupby("placa").tail(1)
    return p.rename(columns={"data_hora": "ultima_posicao"})[["placa", "ultima_posicao", "endereco"]]


def calcular(veiculos: pd.DataFrame, regras: dict, data_ref=None, ordens_servico=None, uso=None,
             abastecimentos=None, posicoes=None, decisoes=None) -> pd.DataFrame:
    cfg = regras["disponibilidade"]
    data_ref = pd.Timestamp(data_ref or pd.Timestamp.today()).normalize() + pd.Timedelta(hours=23, minutes=59)
    if uso is not None and "grupo" not in uso:
        uso = diario.classificar(uso, regras)
    # só conta o que aconteceu até a data de referência (permite recalcular o passado)
    corte = lambda df, col: None if df is None else df[df[col] <= data_ref]
    uso, abastecimentos, posicoes = corte(uso, "data"), corte(abastecimentos, "data_hora"), corte(posicoes, "data_hora")

    df = veiculos.drop_duplicates("placa").copy()
    df = df.merge(_ultima_atividade(uso, abastecimentos, posicoes), on="placa", how="left")
    ult_cod = (diario.ultimo_codigo(uso, data_ref, regras["diario"]["validade_dias"]) if uso is not None and len(uso)
               else pd.DataFrame(columns=["placa", "data_codigo", "ultimo_codigo", "grupo_codigo", "significado", "origem_codigo"]))
    df = df.merge(ult_cod, on="placa", how="left")
    df = df.merge(_os_abertas(ordens_servico, regras, data_ref), on="placa", how="left")
    df = df.merge(_ultima_posicao(posicoes), on="placa", how="left")
    for c in ("ultimo_codigo", "grupo_codigo", "significado", "origem_codigo"):
        df[c] = df[c].astype(object).where(df[c].notna(), "")
    for c in ("ultima_atividade", "os_abertura", "ultima_posicao", "data_status", "data_codigo"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["dias_sem_atividade"] = (data_ref.normalize() - df["ultima_atividade"].dt.normalize()).dt.days
    df["dias_na_oficina"] = (data_ref.normalize() - df["os_abertura"].dt.normalize()).dt.days
    df["dias_sem_sinal"] = (data_ref.normalize() - df["ultima_posicao"].dt.normalize()).dt.days

    fora = {chave(s) for s in cfg["status_fora_da_frota"]}
    forcadas = situacoes_forcadas(decisoes, data_ref)

    def regra_decisao_manual(r):
        if r["placa"] in forcadas:
            categoria, _, motivo = forcadas[r["placa"]]
            return SITUACAO_DA_CATEGORIA[categoria], categoria, motivo

    def regra_diario_manutencao(r):
        if r["grupo_codigo"] == "manutencao":
            return (INDISPONIVEL, "Manutenção", f"{r['origem_codigo'] or 'diário'}: '{r['ultimo_codigo']}' "
                    f"({r['significado']}) em {_fmt(r['data_codigo'])}")

    def regra_a_confirmar(r):
        if r["grupo_codigo"] == "?":
            return (A_CONFIRMAR, "A confirmar", f"sigla '{r['ultimo_codigo']}' sem significado no dicionário "
                    f"({r['origem_codigo'] or 'diário'}, {_fmt(r['data_codigo'])})")

    def regra_fora_da_frota(r):
        if chave(r["status_cadastro"]) in fora:
            desde = f" desde {_fmt(r['data_status'])}" if pd.notna(r["data_status"]) else ""
            return INDISPONIVEL, "Fora da frota", f"cadastro: {r['status_cadastro']}{desde}"

    def regra_os_aberta(r):
        if pd.notna(r["os_aberta"]):
            onde = f" em {r['oficina']}" if pd.notna(r["oficina"]) and r["oficina"] else ""
            return (INDISPONIVEL, "Manutenção",
                    f"OS {r['os_aberta']} aberta em {_fmt(r['os_abertura'])}{onde} ({int(r['dias_na_oficina'])} dias)")

    def regra_ocioso(r):
        if pd.isna(r["ultima_atividade"]):
            return DISPONIVEL, "Ocioso", "nenhum registro de uso, abastecimento ou ignição"
        if r["dias_sem_atividade"] > cfg["dias_ocioso"]:
            return (DISPONIVEL, "Ocioso", f"sem atividade há {int(r['dias_sem_atividade'])} dias "
                    f"(último: {r['fonte_ultima_atividade']} em {_fmt(r['ultima_atividade'])})")

    def regra_em_operacao(r):
        return DISPONIVEL, "Em operação", f"{r['fonte_ultima_atividade']} em {_fmt(r['ultima_atividade'])}"

    funcoes = {"decisao_manual": regra_decisao_manual, "fora_da_frota": regra_fora_da_frota,
               "os_aberta": regra_os_aberta, "diario_manutencao": regra_diario_manutencao,
               "a_confirmar": regra_a_confirmar, "ocioso": regra_ocioso, "em_operacao": regra_em_operacao}
    desconhecidas = set(cfg["ordem"]) - set(funcoes)
    if desconhecidas:
        raise ValueError(f"Regra(s) desconhecida(s) em disponibilidade.ordem: {sorted(desconhecidas)}")

    resultado = []
    for _, r in df.iterrows():
        decisao, regra = None, ""
        for nome in cfg["ordem"]:
            decisao = funcoes[nome](r)
            if decisao:
                regra = nome
                break
        decisao = decisao or (DISPONIVEL, "Em operação", "")
        resultado.append((*decisao, _confirmacao(regra, r), "; ".join(_alertas(r, cfg, regra, forcadas))))
    df[["situacao", "categoria", "motivo", "confirmacao", "alertas"]] = pd.DataFrame(resultado, index=df.index)
    ordem_cat = {"Manutenção": 0, "A confirmar": 1, "Fora da frota": 2, "Ocioso": 3, "Em operação": 4}
    df = df.sort_values(["categoria", "dias_na_oficina", "dias_sem_atividade"],
                        key=lambda s: s.map(ordem_cat) if s.name == "categoria" else s, ascending=[True, False, False])
    return df[COLUNAS].reset_index(drop=True)


def _depois(ativ, quando) -> bool:
    return pd.notna(ativ) and pd.notna(quando) and ativ.normalize() > pd.Timestamp(quando).normalize()


def _confirmacao(regra: str, r) -> str:
    """Quantas fontes independentes sustentam a indisponibilidade."""
    ativ = r["ultima_atividade"]
    if regra == "decisao_manual":
        return "decisão manual"
    if regra == "fora_da_frota":
        if pd.isna(r["data_status"]):
            return "só 1 fonte (cadastro sem data da baixa)"
        return "conflito entre fontes" if _depois(ativ, r["data_status"]) else "confirmada por 2 fontes"
    if regra == "os_aberta":
        if _depois(ativ, r["os_abertura"]):
            return "conflito entre fontes"
        return "confirmada por 2 fontes" if r["grupo_codigo"] == "manutencao" or pd.notna(ativ) else "só 1 fonte"
    if regra == "diario_manutencao":
        return "conflito entre fontes" if _depois(ativ, r["data_codigo"]) else "só 1 fonte (diário, sem OS)"
    return ""


def _alertas(r, cfg, regra: str = "", forcadas: dict | None = None) -> list[str]:
    """Fontes que discordam da situação: é aqui que aparecem os erros de processo."""
    a = []
    ativ = r["ultima_atividade"]
    if regra == "decisao_manual":
        categoria, desde, _ = forcadas[r["placa"]]
        if categoria in ("Manutenção", "Fora da frota") and _depois(ativ, desde):
            a.append(f"decisão manual diz {categoria}, mas houve {r['fonte_ultima_atividade']} em {_fmt(ativ)}: "
                     "rever a decisão")
    if regra == "diario_manutencao":
        a.append("manutenção só no diário de bordo, sem OS no sistema: abrir OS?")
        if _depois(ativ, r["data_codigo"]):
            a.append(f"diário marca manutenção, mas houve {r['fonte_ultima_atividade']} em {_fmt(ativ)}")
    if pd.notna(r["os_aberta"]) and pd.notna(ativ) and ativ.normalize() > r["os_abertura"].normalize():
        a.append(f"OS aberta, mas houve {r['fonte_ultima_atividade']} em {_fmt(ativ)}: OS esquecida aberta?")
    if pd.notna(r["dias_na_oficina"]) and r["dias_na_oficina"] > 30:
        a.append(f"na oficina há {int(r['dias_na_oficina'])} dias")
    if chave(r["status_cadastro"]) in {chave(s) for s in cfg["status_fora_da_frota"]} and pd.notna(ativ) \
            and pd.notna(r["data_status"]) and ativ > r["data_status"]:
        a.append(f"baixado no cadastro, mas houve {r['fonte_ultima_atividade']} em {_fmt(ativ)}")
    if pd.notna(r["dias_sem_sinal"]) and r["dias_sem_sinal"] > cfg["dias_sem_sinal"] \
            and chave(r["status_cadastro"]) not in {chave(s) for s in cfg["status_fora_da_frota"]}:
        a.append(f"rastreador sem sinal há {int(r['dias_sem_sinal'])} dias")
    return a


def taxa(categorias: pd.Series) -> float | None:
    """Disponibilidade da frota ativa: (em operação + ocioso) / (tudo menos fora da frota).
    'A confirmar' entra no denominador e não no numerador: na dúvida, não conta como disponível."""
    ativa = categorias[categorias != "Fora da frota"]
    return round(100 * ativa.isin(["Em operação", "Ocioso"]).mean(), 1) if len(ativa) else None


def resumo(disp: pd.DataFrame) -> pd.DataFrame:
    """Quantidade por base e categoria, com a taxa de disponibilidade da frota ativa."""
    t = pd.crosstab(disp["base"].fillna("(sem base)"), disp["categoria"]).reindex(columns=CATEGORIAS, fill_value=0)
    t.loc["TOTAL"] = t.sum()
    t["disponibilidade_%"] = [taxa(disp["categoria"] if b == "TOTAL" else disp.loc[disp["base"].fillna("(sem base)") == b, "categoria"])
                              for b in t.index]
    t = t.reset_index().rename(columns={"index": "base"})
    t.columns.name = None
    return t


def historico(veiculos: pd.DataFrame, regras: dict, data_ref, dias: int | None = None, **fontes) -> dict:
    """Situação de cada veículo em cada dia do período, aplicando exatamente a mesma regra do dia.

    Devolve:
      diario      placa x dia com categoria, se rodou no dia e `conflito` (rodou no mesmo dia em que
                  estava em manutenção: alguma fonte está errada);
      serie       disponibilidade por dia, por base e total (o indicador do mês);
      por_veiculo dias em cada categoria por veículo (quem fica mais tempo parado).
    """
    dias = dias or regras["disponibilidade"]["dias_historico"]
    fim = pd.Timestamp(data_ref).normalize()
    if fontes.get("uso") is not None and "grupo" not in fontes["uso"]:
        fontes["uso"] = diario.classificar(fontes["uso"], regras)
    partes = []
    for dia in pd.date_range(fim - pd.Timedelta(days=dias - 1), fim, freq="D"):
        d = calcular(veiculos, regras, dia, **fontes)
        d["data"] = dia
        partes.append(d[["data", "placa", "base", "categoria", "situacao", "ultima_atividade"]])
    h = pd.concat(partes, ignore_index=True)
    h["rodou_no_dia"] = h["ultima_atividade"].dt.normalize().eq(h["data"])
    h["conflito"] = h["rodou_no_dia"] & h["categoria"].eq("Manutenção")
    h = h.drop(columns="ultima_atividade")

    serie = h.groupby(["data", "base"])["categoria"].apply(taxa).unstack("base")
    serie["TOTAL"] = h.groupby("data")["categoria"].apply(taxa)
    serie = serie.reset_index()
    serie.columns.name = None

    pv = pd.crosstab([h["placa"], h["base"]], h["categoria"]).reindex(columns=CATEGORIAS, fill_value=0)
    pv.columns = [f"dias_{c.lower().replace(' ', '_').replace('ç', 'c').replace('ã', 'a')}" for c in pv.columns]
    pv["dias_rodou"] = h.groupby(["placa", "base"])["rodou_no_dia"].sum()
    pv["dias_com_conflito"] = h.groupby(["placa", "base"])["conflito"].sum()
    pv = pv.reset_index().sort_values(["dias_manutencao", "dias_ocioso"], ascending=False)
    return {"diario": h, "serie": serie, "por_veiculo": pv.reset_index(drop=True)}


def placas_desconhecidas(veiculos: pd.DataFrame, **tabelas) -> pd.DataFrame:
    """Placas que aparecem em outras fontes e não estão no cadastro, com o diagnóstico provável.

    Nada é ligado automaticamente: quem confere decide e registra em config/decisoes.csv
    (acao = ligar ou ignorar). Ligar "no chute" contaminaria a situação de outro veículo.
    """
    conhecidas = set(veiculos["placa"].dropna())
    linhas = []
    for nome, t in tabelas.items():
        if t is None or t.empty:
            continue
        cont = t.loc[~t["placa"].isin(conhecidas) & t["placa"].notna() & (t["placa"] != ""), "placa"].value_counts()
        for p, n in cont.items():
            sugestao = parecidas(p, conhecidas)
            if not pd.Series([p]).str.fullmatch(PLACA_VALIDA).iloc[0]:
                diag = "formato inválido (texto ou placa incompleta)"
            elif sugestao:
                diag = "provável erro de digitação"
            else:
                diag = "placa válida fora do cadastro (veículo novo, alugado ou de terceiro?)"
            linhas.append({"placa": p, "fonte": nome, "registros": int(n), "diagnostico": diag,
                           "sugestao": ", ".join(sugestao)})
    return pd.DataFrame(linhas, columns=["placa", "fonte", "registros", "diagnostico", "sugestao"])
