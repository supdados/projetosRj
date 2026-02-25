def test_notifications_dropdown_contains_semantic_render_hooks(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

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
        assert fragment in html

    assert 'app-notification-chip' not in html
    assert 'app-notification-tone-' not in html


def test_notifications_dropdown_navigation_contract_is_preserved(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert '.app-notification-item[data-notification-url]' in html
    assert "notificationsList.addEventListener('mousedown'" in html
    assert 'navigateWithSkeleton(targetUrl);' in html
