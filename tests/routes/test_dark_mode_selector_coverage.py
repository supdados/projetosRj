from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DETAIL_CSS_BUNDLE = [
    PROJECT_ROOT / "static" / "css" / "projects" / "detail.css",
    *sorted((PROJECT_ROOT / "static" / "css" / "projects" / "detail").glob("*.css")),
]
# NOTA (corte Grupo B): search/results.css, admin/template-list.css e
# admin/template-form.css foram removidos no corte (telas /busca e
# /admin/templates viraram SPA). O dark mode dessas telas agora vive nos
# componentes Svelte; este contrato cobre apenas os assets Jinja remanescentes.
DARK_MODE_CSS_ASSETS = [
    PROJECT_ROOT / "static" / "css" / "theme-dark.css",
    PROJECT_ROOT / "static" / "css" / "tasks" / "hub.css",
    PROJECT_ROOT / "static" / "css" / "tasks" / "detail" / "dark.css",
    *PROJECT_DETAIL_CSS_BUNDLE,
    PROJECT_ROOT / "static" / "css" / "projects" / "history.css",
]


def test_dark_mode_stylesheet_contains_critical_interaction_selectors():
    missing_assets = [
        str(path.relative_to(PROJECT_ROOT))
        for path in DARK_MODE_CSS_ASSETS
        if not path.exists()
    ]
    assert not missing_assets, f"Assets CSS ausentes: {missing_assets}"

    # O dark mode foi modularizado por página; o contrato precisa cobrir o bundle real.
    css = "\n".join(path.read_text(encoding="utf-8") for path in DARK_MODE_CSS_ASSETS)

    required_fragments = [
        "Interaction Hardening",
        ".main-content .btn",
        ".btn-primary",
        ".btn-task-primary",
        ".btn-projects-v4-primary",
        ".btn-pending-primary",
        ".btn-template-primary",
        ".project-create-btn-primary",
        ".btn-task-danger",
        ".projects-v4-action-btn.is-delete",
        ".badge",
        ".priority-badge",
        ".projects-v4-badge",
        ".pending-chip-atrasada",
        ".tasks-chip",
        ".task-item-priority-chip",
        ".task-items-kanban-badge",
        ".task-items-list",
        ".task-item-header-row",
        ".task-item-row",
        ".task-item-add-row",
        ".task-items-kanban-column",
        ".task-items-kanban-dropzone",
        ".task-items-kanban-card",
        ".task-items-view-toggle",
        ".task-item-drawer",
        ".task-item-drawer-header",
        ".task-item-drawer-textarea",
        ".task-item-drawer-select",
        ".task-item-drawer-comments",
        ".task-item-drawer-comment-form",
        ".task-item-drawer-anexos",
        ".task-item-drawer-anexos-upload-btn",
        ".task-item-drawer-delete-confirm",
        ".task-anexo-preview-modal",
        ".task-anexo-preview-dialog",
        ".task-anexo-preview-link",
        ".project-compact-inner",
        ".project-compact-dates span",
        ".objective-section",
        ".additional-info-box",
        ".etapa-v4-table-card",
        ".etapa-v4-table thead th",
        ".etapa-inline-entry-btn",
        ".etapa-inline-input",
        ".bg-success-light",
        ".comentario-textarea-inline",
        "#importModelModal .modal-content",
        ".custom-context-menu",
        ".confirm-modal",
        ".task-comment-btn",
        ".etapa-inline-icon-btn",
        ".history-field input",
        ".history-list-header",
        ".history-action-pill.tone-success",
        ".header-count",
        ".account-page-header-main",
        ".account-input",
        ".account-area-item",
        ".account-admin-panel",
        ".app-notification-leading",
        ".app-notification-main",
        ".app-notification-row",
        ".app-notification-time",
        ".app-notification-subline",
        ".app-notification-unread-dot",
        ".app-notification-icon-wrap",
        ".app-notification-item.is-unread",
        ".task-item-row:hover",
        ":focus-visible",
        ":disabled",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in css]
    assert not missing, f"Selectors obrigatórios ausentes no dark mode: {missing}"
