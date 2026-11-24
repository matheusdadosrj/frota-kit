"""Linha de comando.

    python -m frotakit exemplo                         gera a frota fictícia em dados_exemplo/
    python -m frotakit rodar                           roda tudo com config/fontes.yaml e config/regras.yaml
    python -m frotakit rodar --fontes config/fontes.local.yaml --data 2026-11-20 --saida saida/
    python -m frotakit validar --fontes ...            só lê as fontes e mostra o que encontrou
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(prog="frotakit", description="Kit de controle de frota")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("exemplo", help="gera dados fictícios em dados_exemplo/")
    for nome in ("rodar", "validar"):
        s = sub.add_parser(nome)
        s.add_argument("--fontes", default=str(RAIZ / "config" / "fontes.yaml"))
        s.add_argument("--regras", default=str(RAIZ / "config" / "regras.yaml"))
        s.add_argument("--data", help="data de referência (AAAA-MM-DD); padrão: data mais recente nos dados")
        s.add_argument("--saida", default="saida")
    a = p.parse_args(argv)

    if a.comando == "exemplo":
        runpy.run_path(str(RAIZ / "exemplos" / "gerar_dados.py"), run_name="__main__")
        return

    from . import adaptadores, pipeline, regras, relatorio

    tabelas = adaptadores.carregar(a.fontes)
    for nome, df in tabelas.items():
        print(f"  {nome:<16} {len(df):>7} linhas")
    if a.comando == "validar":
        return
    res = pipeline.executar(tabelas, regras.carregar(a.regras), a.data)
    saida = Path(a.saida)
    h = relatorio.gerar_html(res, saida / "relatorio.html")
    x = relatorio.gerar_excel(res, saida / "relatorio.xlsx")
    print("\nIndicadores:")
    for k, v in res["indicadores"].items():
        rot, txt = relatorio.formatar_kpi(k, v)
        print(f"  {rot:<32} {txt}")
    print(f"\n-> {h}\n-> {x}")


if __name__ == "__main__":
    sys.exit(main())
