"""Saídas: um relatório HTML único (abre em qualquer navegador, sem servidor) e um Excel com uma aba por tabela."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

ABAS = [  # chave do resultado, título, descrição
    ("disponibilidade", "Disponibilidade", "Situação de cada veículo, com o motivo e as fontes que discordam (alertas)."),
    ("resumo_disponibilidade", "Por base", "Veículos por categoria e taxa de disponibilidade da frota ativa."),
    ("serie_disponibilidade", "Histórico", "Disponibilidade de cada dia do período, por base (a mesma regra aplicada dia a dia)."),
    ("dias_por_veiculo", "Dias parados", "Dias de cada veículo em cada categoria no período; dias_com_conflito = rodou num dia em que estava em manutenção."),
    ("consumo", "Consumo", "km/L real entre tanques cheios e gasto a mais em relação à mediana do grupo."),
    ("alertas_abastecimento", "Alertas de abastecimento", "Registros com problema de qualidade ou suspeita."),
    ("motoristas", "Motoristas", "Cada motorista comparado com outros motoristas nos mesmos veículos (IC 95% por bootstrap)."),
    ("postos", "Postos", "Preço pago comparado com a mediana dos postos da mesma cidade, combustível e mês."),
    ("solicitacoes", "Pedidos de PIX", "Pedidos de pagamento fora do cartão, conferidos antes de pagar."),
    ("rastreamento", "Rastreadores", "Última posição de cada veículo entre todos os fornecedores."),
    ("placas_desconhecidas", "Placas fora do cadastro", "Placas que aparecem nas fontes e não existem no cadastro, com o diagnóstico provável. Nada é ligado automaticamente: registre a decisão em decisoes.csv."),
    ("placas_corrigidas", "Placas corrigidas", "Placas corrigidas automaticamente pela posição (O→0, I→1...) ao ler as fontes."),
    ("siglas_pendentes", "Siglas sem legenda", "Siglas do diário que não estão no dicionário: mande para a operação definir o significado."),
    ("decisoes", "Decisões manuais", "Decisões registradas na conferência e se cada uma foi aplicada."),
]
ROTULOS_KPI = {
    "frota_ativa": ("Frota ativa", "{:.0f}"), "disponiveis": ("Disponíveis", "{:.0f}"),
    "litros": ("Litros abastecidos", "{:,.0f}"), "solicitacoes": ("Pedidos de PIX", "{:.0f}"),
    "disponibilidade_%": ("Disponibilidade", "{:.1f}%"),
    "em_manutencao": ("Em manutenção", "{:.0f}"), "ociosos": ("Ociosos", "{:.0f}"),
    "veiculos_com_alerta": ("Veículos com alerta", "{:.0f}"), "a_confirmar": ("A confirmar", "{:.0f}"),
    "disponibilidade_media_periodo": ("Disponibilidade média do período", "{:.1f}%"),
    "dias_com_conflito": ("Dias com conflito entre fontes", "{:.0f}"),
    "siglas_sem_legenda": ("Siglas sem legenda", "{:.0f}"), "gasto_combustivel": ("Gasto com combustível", "R$ {:,.0f}"),
    "desperdicio_estimado": ("Consumo acima do grupo", "R$ {:,.0f}"), "pago_a_mais_postos": ("Pago a mais em postos caros", "R$ {:,.0f}"),
    "abastecimentos_com_alerta": ("Abastecimentos com alerta", "{:.0f}"),
    "solicitacoes_bloqueadas": ("Pedidos de PIX retidos", "{:.0f}"), "valor_bloqueado": ("Valor retido para conferência", "R$ {:,.0f}"),
}


def formatar_kpi(chave: str, valor) -> tuple[str, str]:
    rotulo, fmt = ROTULOS_KPI.get(chave, (chave, "{}"))
    if valor is None:
        return rotulo, "-"
    texto = fmt.format(valor)
    # padrão brasileiro: 1.234,5
    return rotulo, texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _tabela(df: pd.DataFrame, limite: int = 2000) -> str:
    df = df.head(limite).copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%d/%m/%Y %H:%M").str.replace(" 00:00", "", regex=False)
    cab = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    linhas = []
    for _, r in df.iterrows():
        cel = []
        for c, v in r.items():
            t = "" if pd.isna(v) else (f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                       if isinstance(v, float) else str(v))
            classe = ""
            if c in ("situacao", "categoria", "conclusao", "confianca"):
                classe = f' class="tag t-{html.escape(t.split()[0].lower()) if t else "x"}"'
            if c in ("alertas", "motivo_descarte") and t:
                classe = ' class="alerta"'
            cel.append(f"<td{classe}>{html.escape(t)}</td>")
        linhas.append("<tr>" + "".join(cel) + "</tr>")
    return f'<table><thead><tr>{cab}</tr></thead><tbody>{"".join(linhas)}</tbody></table>'


def _grafico_linha(serie: pd.DataFrame, largura: int = 760, altura: int = 180) -> str:
    """Linha da disponibilidade total por dia, em SVG puro (sem biblioteca)."""
    v = serie["TOTAL"].astype(float).tolist()
    if len(v) < 2:
        return ""
    lo, hi = min(min(v) - 2, 80), 100
    x = lambda i: 40 + i * (largura - 50) / (len(v) - 1)
    y = lambda val: 10 + (hi - val) * (altura - 40) / (hi - lo)
    pontos = " ".join(f"{x(i):.1f},{y(val):.1f}" for i, val in enumerate(v))
    grade = "".join(f'<line x1="40" x2="{largura - 10}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="g"/>'
                    f'<text x="34" y="{y(t) + 4:.1f}" text-anchor="end">{t:.0f}%</text>'
                    for t in range(int(lo) // 5 * 5 + 5, hi + 1, 5))
    datas = serie["data"].dt.strftime("%d/%m").tolist()
    rotulos = "".join(f'<text x="{x(i):.1f}" y="{altura - 8}" text-anchor="middle">{datas[i]}</text>'
                      for i in range(0, len(v), max(1, len(v) // 6)))
    return (f'<svg viewBox="0 0 {largura} {altura}" class="linha" role="img" aria-label="Disponibilidade total por dia">'
            f'{grade}{rotulos}<polyline points="{pontos}"/></svg>')


def gerar_html(res: dict, caminho: str | Path, titulo: str = "Controle de frota") -> Path:
    caminho = Path(caminho)
    data = pd.Timestamp(res["data_ref"]).strftime("%d/%m/%Y")
    kpis = "".join(
        f'<div class="kpi"><span>{html.escape(r)}</span><b>{html.escape(v)}</b></div>'
        for r, v in (formatar_kpi(k, val) for k, val in res["indicadores"].items() if k in ROTULOS_KPI))
    botoes, paineis = [], []
    for n, (chave, nome, desc) in enumerate(a for a in ABAS if isinstance(res.get(a[0]), pd.DataFrame) and len(res[a[0]])):
        df = res[chave]
        ativo = " ativo" if n == 0 else ""
        botoes.append(f'<button class="aba{ativo}" data-alvo="p{n}">{html.escape(nome)} <small>{len(df)}</small></button>')
        grafico = _grafico_linha(df) if chave == "serie_disponibilidade" else ""
        paineis.append(f'<section id="p{n}" class="painel{ativo}"><p class="desc">{html.escape(desc)}</p>{grafico}'
                       f'<input class="busca" placeholder="Filtrar (placa, base, motorista...)">{_tabela(df)}</section>')
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(titulo)}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mut:#5d6677;--bd:#e2e5ea;--ac:#1f6feb;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1218;--card:#171b23;--tx:#e6e8ec;--mut:#9aa3b2;--bd:#2a303b;--ac:#4c8dff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}}}}
*{{box-sizing:border-box}}body{{margin:0;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--tx)}}
header{{padding:20px 24px 8px}}h1{{margin:0;font-size:22px}}header p{{margin:4px 0 0;color:var(--mut)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;padding:12px 24px}}
.kpi{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px}}.kpi span{{display:block;color:var(--mut);font-size:12px}}.kpi b{{font-size:20px}}
nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 24px;border-bottom:1px solid var(--bd)}}
.aba{{border:1px solid var(--bd);background:var(--card);color:var(--tx);border-radius:999px;padding:6px 12px;cursor:pointer}}
.aba.ativo{{background:var(--ac);border-color:var(--ac);color:#fff}}.aba small{{opacity:.7}}
.painel{{display:none;padding:12px 24px 40px}}.painel.ativo{{display:block}}.desc{{color:var(--mut);margin:4px 0 10px}}
.busca{{width:min(420px,100%);padding:8px 10px;border:1px solid var(--bd);border-radius:8px;background:var(--card);color:var(--tx);margin-bottom:10px}}
section{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;background:var(--card);font-size:13px}}
th,td{{border-bottom:1px solid var(--bd);padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}}
td.alerta{{white-space:normal;min-width:260px;color:var(--warn)}}th{{position:sticky;top:0;background:var(--card);cursor:pointer}}
.tag{{font-weight:600}}.t-disponível,.t-em,.t-alta,.t-dentro{{color:var(--ok)}}.t-indisponível,.t-manutenção,.t-consome{{color:var(--bad)}}
.t-ocioso,.t-média,.t-baixa,.t-a{{color:var(--warn)}}
svg.linha{{display:block;width:min(760px,100%);height:auto;background:var(--card);border:1px solid var(--bd);border-radius:10px;margin-bottom:12px}}
svg.linha polyline{{fill:none;stroke:var(--ac);stroke-width:2.5}}svg.linha .g{{stroke:var(--bd)}}svg.linha text{{fill:var(--mut);font-size:11px}}footer{{color:var(--mut);padding:0 24px 24px;font-size:12px}}
</style></head><body>
<header><h1>{html.escape(titulo)}</h1><p>Situação em {data}. Gerado pelo frota-kit.</p></header>
<div class="kpis">{kpis}</div><nav>{"".join(botoes)}</nav>{"".join(paineis)}
<footer>Clique no cabeçalho de uma coluna para ordenar.</footer>
<script>
document.querySelectorAll('.aba').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.aba,.painel').forEach(e=>e.classList.remove('ativo'));b.classList.add('ativo');document.getElementById(b.dataset.alvo).classList.add('ativo')}});
document.querySelectorAll('.busca').forEach(i=>i.oninput=()=>{{const q=i.value.toLowerCase();i.parentElement.querySelectorAll('tbody tr').forEach(tr=>tr.style.display=tr.textContent.toLowerCase().includes(q)?'':'none')}});
const num=t=>{{const v=t.replace(/[R$%\\s]/g,'').replace(/\\./g,'').replace(',','.');return isNaN(v)||v===''?null:+v}};
document.querySelectorAll('th').forEach((th,_)=>th.onclick=()=>{{const tb=th.closest('table').tBodies[0],i=[...th.parentNode.children].indexOf(th),asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
[...tb.rows].sort((a,b)=>{{const x=a.cells[i].textContent,y=b.cells[i].textContent,nx=num(x),ny=num(y);const r=(nx!==null&&ny!==null)?nx-ny:x.localeCompare(y,'pt');return asc?r:-r}}).forEach(r=>tb.appendChild(r))}});
</script></body></html>"""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(pagina, encoding="utf-8")
    return caminho


def gerar_excel(res: dict, caminho: str | Path) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(caminho, engine="openpyxl") as xl:
        pd.DataFrame([{"indicador": formatar_kpi(k, v)[0], "valor": v} for k, v in res["indicadores"].items()]) \
            .to_excel(xl, sheet_name="Indicadores", index=False)
        for chave, nome, _ in ABAS:
            df = res.get(chave)
            if isinstance(df, pd.DataFrame) and len(df):
                df.to_excel(xl, sheet_name=nome[:31], index=False)
        for ws in xl.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                largura = max(len(str(c.value or "")) for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, largura + 2), 60)
    return caminho
