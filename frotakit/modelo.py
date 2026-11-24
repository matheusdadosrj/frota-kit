"""Modelo de dados canônico.

Toda fonte (planilha, ERP via SQL, API de fornecedor) é convertida para estas tabelas antes de
qualquer regra rodar. Assim as regras não sabem — nem precisam saber — de onde o dado veio.

Cada entidade lista suas colunas, o tipo de cada uma e quais são obrigatórias. `padronizar()`
converte tipos, normaliza placas e acusa coluna obrigatória faltando com uma mensagem clara.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Entidade:
    nome: str
    descricao: str
    colunas: dict[str, str]                 # coluna -> tipo (texto, numero, data, booleano)
    obrigatorias: tuple[str, ...]
    exemplo: dict = field(default_factory=dict)


ENTIDADES: dict[str, Entidade] = {e.nome: e for e in [
    Entidade(
        "veiculos", "Cadastro da frota: uma linha por veículo.",
        {"placa": "texto", "modelo": "texto", "grupo": "texto", "combustivel": "texto",
         "capacidade_tanque": "numero", "base": "texto", "status_cadastro": "texto",
         "data_status": "data"},
        ("placa",),
        {"placa": "ABC1D23", "modelo": "Fiorino", "grupo": "utilitario", "combustivel": "flex",
         "capacidade_tanque": 48, "base": "Base Norte", "status_cadastro": "ativo"},
    ),
    Entidade(
        "ordens_servico", "Ordens de serviço de manutenção (ERP, sistema de frota ou planilha da oficina).",
        {"os_id": "texto", "placa": "texto", "abertura": "data", "fechamento": "data",
         "tipo": "texto", "status": "texto", "oficina": "texto", "descricao": "texto", "valor": "numero"},
        ("placa", "abertura"),
    ),
    Entidade(
        "abastecimentos", "Transações de combustível (cartão frota, ERP ou bomba interna).",
        {"id": "texto", "placa": "texto", "data_hora": "data", "litros": "numero", "valor": "numero",
         "odometro": "numero", "tanque_cheio": "booleano", "combustivel": "texto", "posto": "texto",
         "cidade": "texto", "motorista": "texto"},
        ("placa", "data_hora", "litros"),
    ),
    Entidade(
        "uso", "Evidência de uso por dia: viagens, rotas, check-list de saída ou diário de bordo. Com `codigo` "
        "(sigla do diário: 1, M, F...), o significado vem do dicionário de siglas; sem `codigo`, a linha conta como 'rodou'.",
        {"placa": "texto", "data": "data", "codigo": "texto", "motorista": "texto", "km": "numero", "origem": "texto"},
        ("placa", "data"),
    ),
    Entidade(
        "posicoes", "Posições de rastreador (uma ou várias por veículo; vale a mais recente).",
        {"placa": "texto", "data_hora": "data", "latitude": "numero", "longitude": "numero",
         "endereco": "texto", "ignicao": "booleano", "fornecedor": "texto"},
        ("placa", "data_hora"),
    ),
    Entidade(
        "solicitacoes", "Pedidos de pagamento/reembolso de abastecimento feitos fora do cartão "
        "(formulário, WhatsApp, e-mail).",
        {"id": "texto", "data_hora": "data", "placa": "texto", "motorista": "texto", "valor": "numero",
         "odometro": "numero", "posto": "texto", "chave_pix": "texto", "enviado_por": "texto"},
        ("data_hora", "placa"),
    ),
    Entidade(
        "decisoes", "Decisões tomadas por pessoas na conferência, com responsável e data. "
        "acao = ligar (placa digitada errada -> placa do cadastro em `valor`), ignorar (linha que não é veículo) "
        "ou situacao (força a categoria em `valor` a partir de `data`).",
        {"placa": "texto", "acao": "texto", "valor": "texto", "motivo": "texto", "quem": "texto", "data": "data"},
        ("placa", "acao"),
    ),
]}
# entidades que descrevem veículos e eventos (decisoes é configuração, não evento)
EVENTOS = ["ordens_servico", "abastecimentos", "uso", "posicoes", "solicitacoes"]


def normalizar_placa(serie: pd.Series) -> pd.Series:
    """'abc-1d23 ' -> 'ABC1D23'."""
    return serie.astype("string").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


PLACA_VALIDA = r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$"          # Mercosul (ABC1D23) e antiga (ABC1234)
_LETRA = {"0": "O", "1": "I", "5": "S", "8": "B"}            # número digitado onde deveria haver letra
_NUMERO = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1"}  # letra digitada onde deveria haver número


def corrigir_placa(serie: pd.Series) -> pd.Series:
    """Corrige troca de letra por número (e vice-versa) **pela posição** na placa.

    No padrão brasileiro as posições 1-3 são letras e 4, 6 e 7 são números (a 5ª pode ser os dois).
    'ABCO123' -> 'ABC0123'; '1BC1D23' -> 'IBC1D23'. Só corrige quando a placa original é inválida e
    a corrigida fica válida; o resto fica como está, para ir à conferência.
    """
    s = normalizar_placa(serie)
    invalida = s.notna() & ~s.str.fullmatch(PLACA_VALIDA, na=False) & (s.str.len() == 7)

    def corrigir(p: str) -> str:
        c = [(_LETRA.get(ch, ch) if i < 3 else _NUMERO.get(ch, ch) if i in (3, 5, 6) else ch) for i, ch in enumerate(p)]
        nova = "".join(c)
        return nova if pd.Series([nova]).str.fullmatch(PLACA_VALIDA).iloc[0] else p

    return s.where(~invalida, s[invalida].map(corrigir))


def parecidas(placa: str, candidatas) -> list[str]:
    """Placas do mesmo tamanho que diferem em exatamente 1 caractere (provável erro de digitação)."""
    if not isinstance(placa, str):
        return []
    return sorted(c for c in candidatas if len(c) == len(placa) and sum(a != b for a, b in zip(c, placa)) == 1)


VERDADEIRO = {"1", "1.0", "S", "SIM", "Y", "YES", "TRUE", "VERDADEIRO", "X", "LIGADO", "LIGADA", "ON"}


def _booleano(serie: pd.Series) -> pd.Series:
    if serie.dtype == bool:
        return serie
    return serie.astype("string").str.strip().str.upper().isin(VERDADEIRO)


def _numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    t = serie.astype("string").str.strip().str.replace(r"[^0-9,.\-]", "", regex=True)
    # "1.234,56" (padrão brasileiro) -> "1234.56"
    br = t.str.contains(",", na=False)
    t = t.where(~br, t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    # "45.120" ou "1.234.567" sem vírgula: ponto de milhar (ex.: odômetro digitado à mão)
    milhar = ~br & t.str.fullmatch(r"\d{1,3}(\.\d{3})+", na=False)
    t = t.where(~milhar, t.str.replace(".", "", regex=False))
    return pd.to_numeric(t, errors="coerce")


class ErroDeEsquema(ValueError):
    pass


def padronizar(df: pd.DataFrame, entidade: str) -> pd.DataFrame:
    """Converte um DataFrame já com os nomes canônicos para os tipos do modelo."""
    ent = ENTIDADES[entidade]
    faltando = [c for c in ent.obrigatorias if c not in df.columns]
    if faltando:
        raise ErroDeEsquema(
            f"{entidade}: coluna(s) obrigatória(s) ausente(s): {', '.join(faltando)}. "
            f"Colunas recebidas: {', '.join(map(str, df.columns))}. Ajuste o mapeamento em config/fontes.yaml.")
    df = df.copy()
    for col, tipo in ent.colunas.items():
        if col not in df.columns:
            df[col] = pd.NA
            continue
        if tipo == "numero":
            df[col] = _numero(df[col])
        elif tipo == "data":
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=not _parece_iso(df[col]))
        elif tipo == "booleano":
            df[col] = _booleano(df[col])
        else:
            df[col] = df[col].astype("string").str.strip()
    saida = df[list(ent.colunas)].copy()      # colunas que não são do modelo ficam na fonte
    if "placa" in saida.columns and entidade != "decisoes":
        original = normalizar_placa(saida["placa"])
        saida["placa"] = corrigir_placa(saida["placa"])
        mudou = original.ne(saida["placa"]).fillna(False)
        # quais placas foram corrigidas: vira a aba "Placas corrigidas" do relatório
        # (lista simples, não DataFrame: o pandas compara attrs ao juntar tabelas)
        saida.attrs["placas_corrigidas"] = (
            pd.DataFrame({"placa_informada": original[mudou], "placa_corrigida": saida.loc[mudou, "placa"]})
            .value_counts().rename("registros").reset_index().assign(fonte=entidade).to_dict("records"))
    elif "placa" in saida.columns:
        saida["placa"] = normalizar_placa(saida["placa"])
    return saida


def _parece_iso(serie: pd.Series) -> bool:
    amostra = serie.dropna().astype(str).head(20)
    return bool(len(amostra)) and amostra.str.match(r"^\d{4}-\d{2}-\d{2}").all()
