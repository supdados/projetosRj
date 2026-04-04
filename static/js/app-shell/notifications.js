// === notifications.js — Dropdown de notificações ===
// Nota: insertAdjacentHTML usado com conteúdo sanitizado via escapeHtml()
(function (global) {
    document.addEventListener('DOMContentLoaded', function () {
        var notificationsMenu = document.querySelector('.app-notifications-menu');
        if (!notificationsMenu) return;

        var navigateWithSkeleton = global.AppShellSkeleton && global.AppShellSkeleton.navigateWithSkeleton;
        var baseAppConfig = global.__BASE_APP_CONFIG__ || {};

        var notificationsTrigger = document.getElementById('appNotificationsDesktop');
        var notificationsBadge = document.getElementById('appNotificationsBadge');
        var notificationsUnreadCounter = document.getElementById('appNotificationsUnreadCount');
        var notificationsList = document.getElementById('appNotificationsList');
        var notificationsApiUrl = baseAppConfig.notificationsApiUrl || '';
        var isLoadingNotifications = false;

        function escapeNotificationHtml(value) {
            var helper = document.createElement('div');
            helper.textContent = value == null ? '' : String(value);
            return helper.innerHTML;
        }

        var notifStatusEntries = [
            { label: 'Em andamento', css: 'app-notif-status app-notif-status-em-andamento' },
            { label: 'Não iniciada', css: 'app-notif-status app-notif-status-nao-iniciada' },
            { label: 'Para validação', css: 'app-notif-status app-notif-status-para-validacao' },
            { label: 'Para ajustes', css: 'app-notif-status app-notif-status-para-ajustes' },
            { label: 'Finalizada', css: 'app-notif-status app-notif-status-finalizada' },
        ];

        function colorizeNotificationSubline(escapedSubline, escapedActorName) {
            var result = escapedSubline;
            if (escapedActorName) {
                var actorIdx = result.indexOf(escapedActorName);
                if (actorIdx !== -1) {
                    result = result.substring(0, actorIdx)
                        + '<span class="app-notif-actor">' + escapedActorName + '</span>'
                        + result.substring(actorIdx + escapedActorName.length);
                }
            }
            notifStatusEntries.forEach(function (entry) {
                var escapedLabel = escapeNotificationHtml(entry.label);
                result = result.split(escapedLabel).join(
                    '<span class="' + entry.css + '">' + escapedLabel + '</span>'
                );
            });
            return result;
        }

        function updateNotificationsBadge(count) {
            if (!notificationsBadge) return;
            var safeCount = Number.isFinite(count) ? Math.max(0, count) : 0;
            notificationsBadge.textContent = safeCount > 99 ? '99+' : String(safeCount);
            notificationsBadge.classList.toggle('is-hidden', safeCount === 0);
        }

        function updateNotificationsCounter(count) {
            if (!notificationsUnreadCounter) return;
            var safeCount = Number.isFinite(count) ? Math.max(0, count) : 0;
            notificationsUnreadCounter.textContent = safeCount + ' não lida(s)';
        }

        function renderNotificationsState(message) {
            notificationsList.textContent = '';
            var stateDiv = document.createElement('div');
            stateDiv.className = 'app-notifications-state';
            stateDiv.textContent = message;
            notificationsList.appendChild(stateDiv);
        }

        function resolveNotificationVisual(eventType) {
            var safeEventType = (eventType || '').toString().trim().toLowerCase();

            if (
                safeEventType.endsWith('_deleted') ||
                safeEventType === 'task_deleted' ||
                safeEventType === 'project_delete'
            ) {
                return { kind: 'deleted', icon: 'fa-trash-can' };
            }
            if (
                safeEventType === 'task_finalized' ||
                safeEventType === 'project_finalize' ||
                safeEventType === 'project_toggle_done'
            ) {
                return { kind: 'finalized', icon: 'fa-check-circle' };
            }
            if (
                safeEventType === 'task_assignment' ||
                safeEventType === 'task_item_assignment'
            ) {
                return { kind: 'assignment', icon: 'fa-user-check' };
            }
            if (
                safeEventType.startsWith('task_comment_') ||
                safeEventType.startsWith('task_item_comment_')
            ) {
                return { kind: 'comment', icon: 'fa-comments' };
            }
            if (safeEventType.startsWith('project_')) {
                return { kind: 'project', icon: 'fa-folder-tree' };
            }
            if (safeEventType.startsWith('task_')) {
                return { kind: 'task', icon: 'fa-list-check' };
            }
            return { kind: 'update', icon: 'fa-bell' };
        }

        function renderNotificationsItems(items) {
            if (!Array.isArray(items) || !items.length) {
                renderNotificationsState('Sem notificações no momento.');
                return;
            }

            var html = items.map(function (item) {
                var notificationVisual = resolveNotificationVisual(item && item.event_type ? item.event_type : '');
                var targetUrl = escapeNotificationHtml(item && item.target_url ? item.target_url : '#');
                var titleRaw = item && item.title ? item.title : 'Atualização';
                var title = escapeNotificationHtml(titleRaw);
                var messageRaw = item && item.message ? item.message : '';
                var createdAt = item && item.created_at ? escapeNotificationHtml(item.created_at) : '';
                var actorNameRaw = item && item.actor_name ? item.actor_name : '';
                var sublineRaw = messageRaw || actorNameRaw || '';
                var subline = colorizeNotificationSubline(
                    escapeNotificationHtml(sublineRaw),
                    actorNameRaw ? escapeNotificationHtml(actorNameRaw) : ''
                );
                var isUnread = Boolean(item && item.is_unread);
                var unreadClass = isUnread ? ' is-unread' : '';
                var unreadDotClass = isUnread ? '' : ' is-hidden';
                return '<a' +
                    ' href="' + targetUrl + '"' +
                    ' class="app-notification-item' + unreadClass + '"' +
                    ' data-notification-kind="' + escapeNotificationHtml(notificationVisual.kind) + '"' +
                    ' data-notification-url="' + targetUrl + '"' +
                    '>' +
                        '<span class="app-notification-leading" aria-hidden="true">' +
                            '<span class="app-notification-unread-dot' + unreadDotClass + '"></span>' +
                            '<span class="app-notification-icon-wrap">' +
                                '<i class="fas ' + notificationVisual.icon + ' app-notification-icon"></i>' +
                            '</span>' +
                        '</span>' +
                        '<span class="app-notification-main">' +
                            '<span class="app-notification-row">' +
                                '<span class="app-notification-title">' + title + '</span>' +
                                '<span class="app-notification-time">' + createdAt + '</span>' +
                            '</span>' +
                            '<span class="app-notification-subline">' + subline + '</span>' +
                        '</span>' +
                    '</a>';
            }).join('');

            notificationsList.textContent = '';
            notificationsList.insertAdjacentHTML('afterbegin', html);
        }

        function loadNotifications() {
            if (isLoadingNotifications) return;
            isLoadingNotifications = true;
            renderNotificationsState('Carregando notificações...');

            fetch(notificationsApiUrl, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Erro HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                var unreadAfter = Number(payload && payload.unread_after);
                updateNotificationsBadge(Number.isFinite(unreadAfter) ? unreadAfter : 0);
                renderNotificationsItems(payload && payload.items ? payload.items : []);
            })
            .catch(function () {
                renderNotificationsState('Não foi possível carregar as notificações.');
            })
            .finally(function () {
                isLoadingNotifications = false;
            });
        }

        if (notificationsTrigger) {
            notificationsTrigger.addEventListener('show.bs.dropdown', loadNotifications);
        }

        notificationsList.addEventListener('mousedown', function (event) {
            var itemLink = event.target.closest('.app-notification-item[data-notification-url]');
            if (!itemLink) return;
            event.preventDefault();
            var targetUrl = itemLink.getAttribute('data-notification-url');
            if (targetUrl && navigateWithSkeleton) {
                navigateWithSkeleton(targetUrl);
            }
        });
    });
})(window);
