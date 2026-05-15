from pathlib import Path


def _read(path):
    return path.read_text(encoding="utf-8")


def test_project_detail_dark_mode_contains_refined_action_overrides():
    file_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "theme-dark.css"
    )
    content = _read(file_path)

    required_fragments = [
        ".main-content .info-card .btn-edit-project",
        ".main-content .info-card .btn-conclude-project",
        ".main-content .section-divider h2",
        ".main-content .etapa-v4-actions-cell .btn-floating",
        ".main-content .etapa-v4-actions-cell .btn-floating:hover",
        ".main-content .info-card .detail-item .badge.bg-info",
        ".main-content .info-card .detail-item .badge.bg-secondary",
    ]

    for fragment in required_fragments:
        assert fragment in content


def test_project_detail_dark_mode_import_button_matches_secondary_pattern():
    file_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "theme-dark.css"
    )
    content = _read(file_path)

    assert ".main-content .btn-import-model," in content
    assert ".main-content .btn-add-etapa," in content
    assert ".main-content .btn-import-model:hover," in content
    assert ".main-content .btn-add-etapa:hover," in content


def test_project_stage_task_modal_dark_mode_uses_single_surface_base():
    root = Path(__file__).resolve().parents[2]
    quick_add_css = _read(
        root / "static" / "css" / "projects" / "detail" / "05-stage-task-quick-add.css"
    )
    scoped_css = _read(
        root
        / "static"
        / "css"
        / "projects"
        / "detail"
        / "stage-task-modal-scoped.css"
    )

    assert "--stage-task-modal-bg: #273447;" in quick_add_css
    assert "background: #0f1c2c;" not in quick_add_css
    assert "height: auto;" in quick_add_css
    assert "max-height: clamp(420px, 64vh, 620px);" in quick_add_css
    assert "--tasks-bg: var(--stage-task-modal-bg);" in scoped_css
    assert "--tasks-card: var(--stage-task-modal-bg);" in scoped_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".stage-task-quick-add__panel .task-hub-page .task-hub-group {\n"
        "    background: var(--stage-task-modal-bg);"
    ) in scoped_css
