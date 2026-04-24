"""Garante que cada step do tutorial aponta para um ID/seletor que existe
no bundle de templates.

Contexto (achado #9 do ultrareview em 2026-04-24): um step apontava para
`#project_area_responsavel`, elemento removido na migração de `area` →
hierarquia de órgãos. O tutorial falhava silencioso ao chegar nesse passo.

Este teste faz uma varredura simples: extrai os seletores `#id` usados em
`attachTo.element` de `static/js/tutorial/steps.js` e confirma que cada um
aparece no HTML de algum template. É regex-heurístico (não parser JS), mas
pega regressões equivalentes ao #9.
"""

from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEPS_FILE = PROJECT_ROOT / "static" / "js" / "tutorial" / "steps.js"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Seletores de elemento genéricos (tag/classe) que não precisam ser id-matched.
_IGNORED_ELEMENT_SELECTORS = {"h1", "body", "main"}


def _extract_id_selectors(source):
    """Lista os IDs referenciados como `#foo` em `attachTo.element`."""
    pattern = re.compile(r"element:\s*'([^']+)'")
    selectors = []
    for match in pattern.finditer(source):
        value = match.group(1).strip()
        if value.startswith("#"):
            selectors.append(value[1:])
        elif value in _IGNORED_ELEMENT_SELECTORS:
            continue
    return selectors


def _collect_template_html():
    chunks = []
    for path in TEMPLATES_DIR.rglob("*.html"):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_tutorial_ids_exist_in_templates():
    steps_source = STEPS_FILE.read_text(encoding="utf-8")
    selectors = _extract_id_selectors(steps_source)
    assert selectors, "não conseguiu extrair selectors do tutorial"

    html_bundle = _collect_template_html()
    missing = [s for s in selectors if f'id="{s}"' not in html_bundle]
    assert not missing, (
        f"Steps do tutorial referenciam IDs que não existem em nenhum template: "
        f"{missing}"
    )
