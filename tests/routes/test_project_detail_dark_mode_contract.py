from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_project_detail_dark_mode_contains_refined_action_overrides():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'theme-dark.css'
    content = _read(file_path)

    required_fragments = [
        '.main-content .info-card .btn-edit-project',
        '.main-content .info-card .btn-conclude-project',
        '.main-content .section-divider h2',
        '.main-content .etapa-v4-actions-cell .btn-floating',
        '.main-content .etapa-v4-actions-cell .btn-floating:hover',
        '.main-content .info-card .detail-item .badge.bg-info',
        '.main-content .info-card .detail-item .badge.bg-secondary',
    ]

    for fragment in required_fragments:
        assert fragment in content


def test_project_detail_dark_mode_import_button_matches_secondary_pattern():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'theme-dark.css'
    content = _read(file_path)

    assert '.main-content .btn-import-model,' in content
    assert '.main-content .btn-add-etapa,' in content
    assert '.main-content .btn-import-model:hover,' in content
    assert '.main-content .btn-add-etapa:hover,' in content
