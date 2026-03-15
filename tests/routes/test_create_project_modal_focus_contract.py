from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_create_project_buttons_use_focus_visible_instead_of_focus_hover_lock():
    projects_list_css = (PROJECT_ROOT / 'static' / 'css' / 'projects' / 'list.css').read_text(encoding='utf-8')
    dashboard_css = (PROJECT_ROOT / 'static' / 'css' / 'index.css').read_text(encoding='utf-8')

    assert '.btn-projects-v4-primary:focus-visible' in projects_list_css
    assert '.btn-projects-v4-secondary:focus-visible' in projects_list_css
    assert '.btn-projects-v4-primary:focus {' not in projects_list_css
    assert '.btn-projects-v4-secondary:focus {' not in projects_list_css

    assert '.dashboard-page-v2 .glass-btn.dashboard-new-project-btn:focus-visible' in dashboard_css
    assert '.dashboard-page-v2 .glass-btn.dashboard-new-project-btn:focus,' not in dashboard_css
    assert '.dashboard-page-v2 .dashboard-new-project-btn:focus-visible' in dashboard_css
    assert '.dashboard-page-v2 .dashboard-new-project-btn:focus {' not in dashboard_css


def test_add_project_modal_tracks_trigger_and_clears_pointer_focus_on_close():
    modal_js = (PROJECT_ROOT / 'templates' / 'projects' / 'add_form_js.html').read_text(encoding='utf-8')

    required_fragments = [
        'let modalTriggerElement = null;',
        'let lastInteractionWasKeyboard = false;',
        "addProjectModal.addEventListener('show.bs.modal', function (event) {",
        'event.relatedTarget',
        "if (modalTriggerElement && !lastInteractionWasKeyboard && typeof modalTriggerElement.blur === 'function') {",
    ]

    for fragment in required_fragments:
        assert fragment in modal_js
