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


def test_project_header_date_spans_stay_transparent_in_dark_mode():
    root = Path(__file__).resolve().parents[2]
    detail_dark_css = _read(
        root / "static" / "css" / "projects" / "detail" / "04-dark-mode.css"
    )

    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header p:not(.project-header-dates) span {\n"
        "    background: rgba(38, 59, 85, 0.76);"
    ) in detail_dark_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header p span {\n"
        "    background: rgba(38, 59, 85, 0.76);"
    ) not in detail_dark_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header p.project-header-dates .hd-date-item,\n"
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header p.project-header-dates .hd-date-sep {\n"
        "    background: transparent;"
    ) in detail_dark_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-compact-dates span {\n"
        "    background: transparent;"
    ) in detail_dark_css


def test_project_header_dates_render_with_scoped_date_classes(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    header_start = html.index('class="project-header"')
    header_end = html.index('id="projectHeaderSentinel"')
    project_header_html = html[header_start:header_end]

    assert "css/projects/detail.css" in html
    assert "css/theme-dark.css" in html
    assert html.index("css/projects/detail.css") < html.index("css/theme-dark.css")
    assert 'class="mb-0 project-header-dates"' in project_header_html
    assert project_header_html.count('class="hd-date-item"') == 2
    assert 'class="hd-date-sep"' in project_header_html

    compact_start = html.index('id="projectCompactHeader"')
    compact_end = html.index("<!-- Cartão de detalhes do projeto -->")
    project_compact_html = html[compact_start:compact_end]
    assert 'class="project-compact-dates"' in project_compact_html
    assert project_compact_html.count("<span><i") == 2
