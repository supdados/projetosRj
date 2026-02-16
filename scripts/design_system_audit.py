#!/usr/bin/env python3
"""Audit Design System constraints for ProjetosRJ."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHASE1_TEMPLATES = [
    Path("templates/base.html"),
    Path("templates/index.html"),
    Path("templates/projects_list.html"),
    Path("templates/project_detail.html"),
    Path("templates/task_list.html"),
    Path("templates/task_detail.html"),
    Path("templates/projetos_pendentes.html"),
]

EXPECTED_LINKS = {
    Path("templates/base.html"): "design-system.css",
    Path("templates/index.html"): "pages/index.css",
    Path("templates/projects_list.html"): "pages/projects-list.css",
    Path("templates/project_detail.html"): "pages/project-detail.css",
    Path("templates/projetos_pendentes.html"): "pages/projetos-pendentes.css",
    Path("templates/login.html"): "pages/login.css",
    Path("templates/search_results.html"): "pages/search-results.css",
    Path("templates/project_history.html"): "pages/project-history.css",
    Path("templates/project_tasks.html"): "pages/project-tasks.css",
    Path("templates/template_form.html"): "pages/template-form.css",
    Path("templates/template_list.html"): "pages/template-list.css",
}

EXPECTED_FILES = [
    Path("static/design-system.css"),
    Path("static/pages/index.css"),
    Path("static/pages/projects-list.css"),
    Path("static/pages/project-detail.css"),
    Path("static/pages/projetos-pendentes.css"),
    Path("static/pages/login.css"),
    Path("static/pages/search-results.css"),
    Path("static/pages/project-history.css"),
    Path("static/pages/project-tasks.css"),
    Path("static/pages/template-form.css"),
    Path("static/pages/template-list.css"),
    Path("docs/design-system.md"),
    Path("docs/design-system-inventory.md"),
]

INLINE_STYLE_THRESHOLD = 20
TOKEN_MIN_COUNT = 20
GLOBAL_STYLE_TAG_THRESHOLD = 0


STYLE_TAG_RE = re.compile(r"<style(?:\s[^>]*)?>", re.IGNORECASE)
INLINE_STYLE_RE = re.compile(r"\bstyle\s*=\s*\"", re.IGNORECASE)
TOKEN_RE = re.compile(r"--ds-[a-z0-9-]+\s*:", re.IGNORECASE)

DESKTOP_ONLY_TEMPLATE_PATTERNS = [
    ("app-mobile", re.compile(r"app-mobile", re.IGNORECASE)),
    ("mobile-", re.compile(r"mobile-", re.IGNORECASE)),
    ("d-md-none", re.compile(r"\bd-md-none\b", re.IGNORECASE)),
    ("d-lg-none", re.compile(r"\bd-lg-none\b", re.IGNORECASE)),
    ("d-none d-md", re.compile(r"\bd-none\s+d-md", re.IGNORECASE)),
    ("d-none d-lg", re.compile(r"\bd-none\s+d-lg", re.IGNORECASE)),
    ("view-cards", re.compile(r"view-cards", re.IGNORECASE)),
    ("view-table", re.compile(r"view-table", re.IGNORECASE)),
    ("window.innerWidth < 768", re.compile(r"window\.innerWidth\s*<\s*768")),
    ("matchMedia('(max-width", re.compile(r"matchMedia\(\s*['\"]\(max-width", re.IGNORECASE)),
]

DESKTOP_ONLY_CSS_PATTERNS = [
    ("@media (max-width: 991.98px)", re.compile(r"@media\s*\(\s*max-width:\s*991\.98px\s*\)", re.IGNORECASE)),
    ("@media (max-width: 992px)", re.compile(r"@media\s*\(\s*max-width:\s*992px\s*\)", re.IGNORECASE)),
    ("@media (max-width: 768px)", re.compile(r"@media\s*\(\s*max-width:\s*768px\s*\)", re.IGNORECASE)),
    ("@media (max-width: 767.98px)", re.compile(r"@media\s*\(\s*max-width:\s*767\.98px\s*\)", re.IGNORECASE)),
    ("@media (max-width: 576px)", re.compile(r"@media\s*\(\s*max-width:\s*576px\s*\)", re.IGNORECASE)),
    ("@media (max-width: 575.98px)", re.compile(r"@media\s*\(\s*max-width:\s*575\.98px\s*\)", re.IGNORECASE)),
    ("mobile selector", re.compile(r"\.mobile-[a-z0-9_-]*", re.IGNORECASE)),
    ("app-mobile selector", re.compile(r"\.app-mobile-[a-z0-9_-]*", re.IGNORECASE)),
]


def read_text(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def find_line_number(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def scan_forbidden_patterns(
    rel: Path, content: str, checks: list[tuple[str, re.Pattern[str]]], failures: list[str]
) -> None:
    for label, pattern in checks:
        match = pattern.search(content)
        if match:
            line = find_line_number(content, match.start())
            failures.append(f"{rel}:{line} contem padrao proibido: {label}")


def main() -> int:
    failures: list[str] = []

    # Check required files
    for rel in EXPECTED_FILES:
        if not (ROOT / rel).exists():
            failures.append(f"Arquivo obrigatorio ausente: {rel}")

    # Check template-level constraints (phase 1)
    inline_total = 0
    template_counts: list[tuple[Path, int, int]] = []
    for rel in PHASE1_TEMPLATES:
        if not (ROOT / rel).exists():
            failures.append(f"Template da Fase 1 ausente: {rel}")
            continue

        content = read_text(rel)
        style_tag_count = len(STYLE_TAG_RE.findall(content))
        inline_count = len(INLINE_STYLE_RE.findall(content))
        inline_total += inline_count
        template_counts.append((rel, style_tag_count, inline_count))

        if style_tag_count != 0:
            failures.append(f"{rel}: possui {style_tag_count} bloco(s) <style> (esperado 0)")

    if inline_total > INLINE_STYLE_THRESHOLD:
        failures.append(
            f"Inline style total da Fase 1 = {inline_total} (limite {INLINE_STYLE_THRESHOLD})"
        )

    # Check global style-tag hygiene
    all_templates = sorted((ROOT / "templates").glob("*.html"))
    global_style_tags = 0
    for tpl in all_templates:
        content = tpl.read_text(encoding="utf-8")
        global_style_tags += len(STYLE_TAG_RE.findall(content))
    if global_style_tags > GLOBAL_STYLE_TAG_THRESHOLD:
        failures.append(
            f"Total de <style> em templates = {global_style_tags} (limite {GLOBAL_STYLE_TAG_THRESHOLD})"
        )

    # Desktop-only template contract
    for tpl in all_templates:
        content = tpl.read_text(encoding="utf-8")
        scan_forbidden_patterns(tpl.relative_to(ROOT), content, DESKTOP_ONLY_TEMPLATE_PATTERNS, failures)

    # Desktop-only CSS contract
    css_files = [
        Path("static/style.css"),
        Path("static/design-system.css"),
        *sorted(path.relative_to(ROOT) for path in (ROOT / "static/pages").glob("*.css")),
    ]
    for rel in css_files:
        full_path = ROOT / rel
        if not full_path.exists():
            continue
        content = full_path.read_text(encoding="utf-8")
        scan_forbidden_patterns(rel, content, DESKTOP_ONLY_CSS_PATTERNS, failures)

    # Check link wiring
    for rel, expected_fragment in EXPECTED_LINKS.items():
        if not (ROOT / rel).exists():
            continue
        content = read_text(rel)
        if expected_fragment not in content:
            failures.append(f"{rel}: nao referencia {expected_fragment}")

    # Check token density
    ds_file = ROOT / "static/design-system.css"
    if ds_file.exists():
        token_count = len(TOKEN_RE.findall(ds_file.read_text(encoding="utf-8")))
        if token_count < TOKEN_MIN_COUNT:
            failures.append(
                f"static/design-system.css possui {token_count} tokens --ds-* (minimo {TOKEN_MIN_COUNT})"
            )
    else:
        token_count = 0

    # Report
    print("Design System Audit")
    print("===================")
    for rel, style_tags, inline_styles in template_counts:
        print(f"{rel}: style_tags={style_tags} inline_styles={inline_styles}")
    print(f"TOTAL inline styles (Fase 1): {inline_total}")
    print(f"TOTAL <style> em templates: {global_style_tags}")
    print(f"TOKENS --ds-* encontrados: {token_count}")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("\nAudit concluida sem violacoes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
