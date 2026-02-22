from pathlib import Path


def test_dark_mode_stylesheet_contains_critical_interaction_selectors():
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'theme-dark.css'
    css = css_path.read_text(encoding='utf-8')

    required_fragments = [
        'Interaction Hardening',
        '.main-content .btn',
        '.btn-primary',
        '.btn-task-primary',
        '.btn-projects-v4-primary',
        '.btn-pending-primary',
        '.btn-template-primary',
        '.project-create-btn-primary',
        '.btn-task-danger',
        '.projects-v4-action-btn.is-delete',
        '.badge',
        '.priority-badge',
        '.projects-v4-badge',
        '.pending-chip-atrasada',
        '.tasks-chip',
        '.task-item-priority-chip',
        '.task-items-kanban-badge',
        '.search-result-badge-project',
        '.task-comment-btn',
        '.etapa-inline-icon-btn',
        '.task-item-row:hover',
        '.task-card:hover',
        ':focus-visible',
        ':disabled',
    ]

    missing = [fragment for fragment in required_fragments if fragment not in css]
    assert not missing, f'Selectors obrigatórios ausentes no dark mode: {missing}'
