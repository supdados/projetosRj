from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_notifications_dropdown_contains_semantic_render_hooks(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    app_shell_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'app-shell.js'
    app_shell_content = _read(app_shell_path)

    required_fragments = [
        'function resolveNotificationVisual(eventType)',
        'app-notification-leading',
        'app-notification-main',
        'app-notification-row',
        'app-notification-time',
        'app-notification-subline',
        'app-notification-unread-dot',
        'app-notification-icon-wrap',
        'is-unread',
        'item && item.event_type',
        'item && item.is_unread',
        "safeEventType.endsWith('_deleted')",
        "safeEventType === 'task_finalized'",
        "safeEventType === 'task_item_assignment'",
        "safeEventType.startsWith('task_item_comment_')",
        "safeEventType.startsWith('project_')",
        "safeEventType.startsWith('task_')",
        'fa-bell',
        'const titleRaw = item && item.title ? item.title : \'Atualização\';',
        '<span class="app-notification-title">${title}</span>',
    ]

    for fragment in required_fragments:
        assert fragment in app_shell_content

    assert "static/js/app-shell.js" in html
    assert 'app-notification-chip' not in app_shell_content
    assert 'app-notification-tone-' not in app_shell_content


def test_notifications_dropdown_navigation_contract_is_preserved(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    app_shell_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'app-shell.js'
    app_shell_content = _read(app_shell_path)

    assert '.app-notification-item[data-notification-url]' in app_shell_content
    assert "notificationsList.addEventListener('mousedown'" in app_shell_content
    assert 'navigateWithSkeleton(targetUrl);' in app_shell_content
    assert "window.__BASE_APP_CONFIG__" in html
