from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_projects_filter_density_uses_notebook_breakpoint_without_resize_observer_feedback():
    projects_list_css = (PROJECT_ROOT / 'static' / 'css' / 'projects' / 'list.css').read_text(encoding='utf-8')
    projects_list_template = (PROJECT_ROOT / 'templates' / 'projects' / 'list.html').read_text(encoding='utf-8')
    foundation_css = (PROJECT_ROOT / 'static' / 'css' / 'legacy' / '00-foundation.css').read_text(encoding='utf-8')

    assert '@media (max-width: 1360px)' in projects_list_css
    assert '.projects-v4-filter-essential {' in projects_list_css
    assert 'flex-wrap: wrap;' in projects_list_css
    assert 'var densityWrapBreakpoint = 1360;' in projects_list_template
    assert 'shouldUseWrappedFiltersLayout()' in projects_list_template
    assert 'ResizeObserver' not in projects_list_template
    assert 'scrollbar-gutter: stable;' in foundation_css
