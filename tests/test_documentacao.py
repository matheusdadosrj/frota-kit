"""Todo link relativo dos .md precisa apontar para um arquivo que existe no repositório.

Pega o erro clássico de README no GitHub: imagem ou documento citado que não foi versionado.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def test_links_relativos_dos_markdown_existem():
    quebrados = []
    for md in RAIZ.rglob("*.md"):
        if any(p in md.parts for p in (".git", ".venv", "dados_exemplo", "saida")):
            continue
        for alvo in LINK.findall(md.read_text(encoding="utf-8")):
            if alvo.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if alvo.startswith("../../issues"):     # página de issues do próprio repositório no GitHub
                continue
            caminho = (md.parent / alvo.split("#")[0]).resolve()
            if not caminho.exists():
                quebrados.append(f"{md.relative_to(RAIZ)} -> {alvo}")
    assert not quebrados, "Links quebrados:\n" + "\n".join(quebrados)
