ROUTE_CASES = [
    # Auth and home
    {
        "id": "home_get",
        "method": "GET",
        "rule": "/",
        "path": "/",
        "role": "user",
        "expected_status": 302,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "login_get",
        "method": "GET",
        "rule": "/login",
        "path": "/login",
        "role": "anon",
        "expected_status": 200,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "login_post",
        "method": "POST",
        "rule": "/login",
        "path": "/login",
        "role": "anon",
        "data": {"username": "{user_username}", "password": "{user_password}"},
        "expected_status": 302,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "login_govbr_get",
        "method": "GET",
        "rule": "/login/govbr",
        "path": "/login/govbr",
        "role": "anon",
        "expected_status": 302,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "login_govbr_callback_get",
        "method": "GET",
        "rule": "/auth/govbr/callback",
        "path": "/auth/govbr/callback",
        "role": "anon",
        "expected_status": 302,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "logout_get",
        "method": "GET",
        "rule": "/logout",
        "path": "/logout",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "change_password_get",
        "method": "GET",
        "rule": "/profile/change-password",
        "path": "/profile/change-password",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "change_password_post",
        "method": "POST",
        "rule": "/profile/change-password",
        "path": "/profile/change-password",
        "role": "user",
        "data": {
            "current_password": "{user_password}",
            "new_password": "novaSenha123",
            "confirm_new_password": "novaSenha123",
        },
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    # Dashboard
    {
        "id": "dashboard_get",
        "method": "GET",
        "rule": "/dashboard",
        "path": "/dashboard",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "chatbot_token_get",
        "method": "GET",
        "rule": "/api/chatbot-token",
        "path": "/api/chatbot-token",
        "role": "user",
        "expected_status": 404,
        "requires_login": True,
        "requires_admin": False,
    },
    # Projects
    {
        "id": "projects_get",
        "method": "GET",
        "rule": "/projects",
        "path": "/projects",
        "role": "user",
        # KEEP-ENDPOINT: /projects virou redirect 302 -> /projetos (SPA).
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "projects_download_get",
        "method": "GET",
        "rule": "/projects/download",
        "path": "/projects/download",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "project_detail_get",
        "method": "GET",
        "rule": "/project/<int:project_id>",
        "path": "/project/{project_id}",
        "role": "user",
        # KEEP-ENDPOINT: redireciona (302) para /projetos/<id> na SPA — preserva
        # target_url persistido em notificações e links da busca.
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    # Etapas
    {
        "id": "etapa_add_post",
        "method": "POST",
        "rule": "/project/<int:project_id>/etapa/add",
        "path": "/project/{project_id}/etapa/add",
        "role": "user",
        "data": {
            "etapa_descricao": "Nova etapa de teste",
            "etapa_data_inicio": "2026-03-01",
            "etapa_data_fim": "2026-03-05",
            "etapa_responsavel": "Usuario Auditoria",
        },
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "project_meeting_add_post",
        "method": "POST",
        "rule": "/project/<int:project_id>/meeting/add",
        "path": "/project/{project_id}/meeting/add",
        "role": "user",
        "data": {
            "title": "Reuniao de teste",
            "starts_at": "2026-03-10T09:00",
            "ends_at": "2026-03-10T10:00",
            "location": "Sala 2",
        },
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "project_meeting_edit_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/meeting/edit",
        "path": "/etapa/{etapa_id}/meeting/edit",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "import_model_post",
        "method": "POST",
        "rule": "/project/<int:project_id>/import_model",
        "path": "/project/{project_id}/import_model",
        "role": "user",
        "data": {"template_id": "{template_id}", "start_date": "2026-03-10"},
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapa_delete_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/delete",
        "path": "/etapa/{etapa_id}/delete",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapas_reorder_post",
        "method": "POST",
        "rule": "/project/<int:project_id>/etapas/reordenar",
        "path": "/project/{project_id}/etapas/reordenar",
        "role": "user",
        "json": {"etapa_ids": ["{etapa_id}", "{etapa_started_id}"]},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapa_toggle_iniciada_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/toggle_iniciada",
        "path": "/etapa/{etapa_id}/toggle_iniciada",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapa_toggle_done_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/toggle",
        "path": "/etapa/{etapa_started_id}/toggle",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapa_update_field_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/update_field",
        "path": "/etapa/{etapa_id}/update_field",
        "role": "user",
        "json": {"field": "descricao", "value": "Descricao inline"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "etapa_comment_post",
        "method": "POST",
        "rule": "/etapa/<int:etapa_id>/comentario",
        "path": "/etapa/{etapa_id}/comentario",
        "role": "user",
        "json": {"comentario": "Comentario via modal"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "cascade_update_post",
        "method": "POST",
        "rule": "/project/<int:project_id>/cascade_update",
        "path": "/project/{project_id}/cascade_update",
        "role": "user",
        "json": {"etapa_id": "{etapa_id}", "days_diff": 2},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # Tasks
    {
        "id": "tasks_get",
        "method": "GET",
        "rule": "/tarefas",
        "path": "/tarefas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "tasks_archived_get",
        "method": "GET",
        "rule": "/tarefas/arquivadas",
        "path": "/tarefas/arquivadas",
        "role": "user",
        # Redirect resolver 302 -> /tarefas?modo=arquivadas (a SPA nao tem rota
        # client-side /tarefas/arquivadas; o modo e lido do query param).
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "tasks_finalized_get",
        "method": "GET",
        "rule": "/tarefas/finalizadas",
        "path": "/tarefas/finalizadas",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_add_post",
        "method": "POST",
        "rule": "/tarefas/add",
        "path": "/tarefas/add",
        "role": "user",
        "data": {"titulo": "Tarefa criada no teste", "project_id": "{project_id}"},
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_detail_get",
        "method": "GET",
        "rule": "/tarefas/<int:task_id>",
        "path": "/tarefas/{task_id}",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_edit_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/edit",
        "path": "/tarefas/{task_id}/edit",
        "role": "user",
        "data": {"titulo": "Tarefa editada", "project_id": "{project_id}"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_move_etapa_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/mover-etapa",
        "path": "/tarefas/{task_id}/mover-etapa",
        "role": "user",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "json": {"etapa_id": "sem_etapa"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_delete_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/delete",
        "path": "/tarefas/{task_id}/delete",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_finalize_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/finalizar",
        "path": "/tarefas/{task_id}/finalizar",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_reactivate_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/reativar",
        "path": "/tarefas/{task_id}/reativar",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_update_status_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/update_status",
        "path": "/tarefas/{task_item_id}/update_status",
        "role": "user",
        "json": {"status": "em_andamento"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_update_prioridade_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/update_prioridade",
        "path": "/tarefas/{task_item_id}/update_prioridade",
        "role": "user",
        "json": {"prioridade": "alta"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_update_tipo_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/update_tipo",
        "path": "/tarefas/{task_item_id}/update_tipo",
        "role": "user",
        "json": {"tipo_pedido": "bug"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "tasks_reorder_post",
        "method": "POST",
        "rule": "/tarefas/reordenar",
        "path": "/tarefas/reordenar",
        "role": "user",
        "json": {"ordem": ["{task_id}"]},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_comment_add_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/comentarios/add",
        "path": "/tarefas/{task_item_id}/comentarios/add",
        "role": "user",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"content": "Comentario canonico"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_comment_edit_post",
        "method": "POST",
        "rule": "/tarefas/comentarios/<int:comment_id>/edit",
        "path": "/tarefas/comentarios/{comment_id}/edit",
        "role": "user",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"content": "Comentario editado"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_comment_delete_post",
        "method": "POST",
        "rule": "/tarefas/comentarios/<int:comment_id>/delete",
        "path": "/tarefas/comentarios/{comment_id}/delete",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "project_tasks_get",
        "method": "GET",
        "rule": "/projeto/<int:project_id>/tarefas",
        "path": "/projeto/{project_id}/tarefas",
        "role": "user",
        # Redirect resolver 302 -> /tarefas?project=<id> (a SPA nao tem rota
        # client-side /projeto/<id>/tarefas; o filtro e lido do query param).
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_project_etapas_get",
        "method": "GET",
        "rule": "/tarefas/projeto/<int:project_id>/etapas",
        "path": "/tarefas/projeto/{project_id}/etapas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_assignable_users_get",
        "method": "GET",
        "rule": "/tarefas/<int:task_id>/sugestoes-responsavel",
        "path": "/tarefas/{task_id}/sugestoes-responsavel",
        "role": "user",
        "query_string": {"q": "Usuario"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_hub_assignable_users_get",
        "method": "GET",
        "rule": "/tarefas/sugestoes-responsavel",
        "path": "/tarefas/sugestoes-responsavel",
        "role": "user",
        "query_string": {"project": "{project_id}", "q": "Usuario"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_anexos_list_get",
        "method": "GET",
        "rule": "/tarefas/<int:task_id>/anexos",
        "path": "/tarefas/{task_item_id}/anexos",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_anexo_add_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/anexos/add",
        "path": "/tarefas/{task_item_id}/anexos/add",
        "role": "user",
        "expected_status": 400,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_archive_finalizadas_post",
        "method": "POST",
        "rule": "/tarefas/arquivar-finalizadas",
        "path": "/tarefas/arquivar-finalizadas",
        "role": "user",
        "data": {"project": "{project_id}"},
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_desarquivar_post",
        "method": "POST",
        "rule": "/tarefas/<int:task_id>/desarquivar",
        "path": "/tarefas/{task_item_id}/desarquivar",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_item_anexo_view_get",
        "method": "GET",
        "rule": "/tarefas/anexos/<int:anexo_id>",
        "path": "/tarefas/anexos/999999",
        "role": "user",
        "expected_status": 404,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "task_item_anexo_delete_post",
        "method": "POST",
        "rule": "/tarefas/anexos/<int:anexo_id>/delete",
        "path": "/tarefas/anexos/999999/delete",
        "role": "user",
        "expected_status": 404,
        "requires_login": True,
        "requires_admin": False,
    },
    # Calendars
    {
        "id": "calendars_hub_get",
        "method": "GET",
        "rule": "/calendarios",
        "path": "/calendarios",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_oauth_start_get",
        "method": "GET",
        "rule": "/calendar/oauth/start",
        "path": "/calendar/oauth/start",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_oauth_callback_get",
        "method": "GET",
        "rule": "/calendar/oauth/callback",
        "path": "/calendar/oauth/callback",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_google_disconnect_post",
        "method": "POST",
        "rule": "/calendarios/google/disconnect",
        "path": "/calendarios/google/disconnect",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_google_sync_post",
        "method": "POST",
        "rule": "/calendarios/google/sync",
        "path": "/calendarios/google/sync",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_google_watch_renew_post",
        "method": "POST",
        "rule": "/calendarios/google/watch/renew",
        "path": "/calendarios/google/watch/renew",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_event_create_post",
        "method": "POST",
        "rule": "/calendarios/eventos",
        "path": "/calendarios/eventos",
        "role": "user",
        "data": {
            "title": "Evento de teste",
            "location": "Auditorio",
            "starts_at": "2026-03-20T09:00",
            "ends_at": "2026-03-20T10:00",
            "description": "Gerado pela matriz de rotas",
        },
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_event_edit_post",
        "method": "POST",
        "rule": "/calendarios/eventos/<int:event_id>/editar",
        "path": "/calendarios/eventos/{calendar_event_id}/editar",
        "role": "user",
        "data": {
            "title": "Evento alterado",
            "location": "Sala de reuniao",
            "starts_at": "2026-03-20T11:00",
            "ends_at": "2026-03-20T12:00",
            "description": "Atualizacao via matriz",
        },
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_event_delete_post",
        "method": "POST",
        "rule": "/calendarios/eventos/<int:event_id>/excluir",
        "path": "/calendarios/eventos/{calendar_event_id}/excluir",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "calendar_webhook_post",
        "method": "POST",
        "rule": "/webhook",
        "path": "/webhook",
        "role": "anon",
        "expected_status": 400,
        "requires_login": False,
        "requires_admin": False,
    },
    # SPA API (envelope canônico)
    {
        "id": "api_me_get",
        "method": "GET",
        "rule": "/api/me",
        "path": "/api/me",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_csrf_token_get",
        "method": "GET",
        "rule": "/api/csrf-token",
        "path": "/api/csrf-token",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_dashboard_get",
        "method": "GET",
        "rule": "/api/dashboard",
        "path": "/api/dashboard",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projetos_pendentes_get",
        "method": "GET",
        "rule": "/api/projetos-pendentes",
        "path": "/api/projetos-pendentes",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_historico_get",
        "method": "GET",
        "rule": "/api/projetos/<int:project_id>/historico",
        "path": "/api/projetos/{project_id}/historico",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projetos_get",
        "method": "GET",
        "rule": "/api/projetos",
        "path": "/api/projetos",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_detalhe_get",
        "method": "GET",
        "rule": "/api/projetos/<int:project_id>/detalhe",
        "path": "/api/projetos/{project_id}/detalhe",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_inline_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/inline",
        "path": "/api/projetos/{project_id}/inline",
        "role": "user",
        "json": {"titulo": "Projeto Inline API"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_tarefas_etapa_get",
        "method": "GET",
        "rule": "/api/projetos/<int:project_id>/tarefas-etapa",
        "path": "/api/projetos/{project_id}/tarefas-etapa",
        "role": "user",
        "query_string": {"etapa_id": "{etapa_id}"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_add_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/etapas",
        "path": "/api/projetos/{project_id}/etapas",
        "role": "user",
        "json": {
            "descricao": "Etapa via API",
            "data_inicio": "2026-03-02",
            "data_fim": "2026-03-06",
            "responsavel": "Usuario Auditoria",
            "responsaveis": [{"area_id": None, "label": "Outras"}],
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_edit_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>",
        "path": "/api/etapas/{etapa_id}",
        "role": "user",
        "json": {
            "descricao": "Etapa editada via API",
            "data_inicio": "2026-01-12",
            "data_fim": "2026-01-16",
            "responsavel": "Usuario Auditoria",
            "iniciada": False,
            "done": False,
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_delete_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/delete",
        "path": "/api/etapas/{etapa_id}/delete",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_update_field_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/update-field",
        "path": "/api/etapas/{etapa_id}/update-field",
        "role": "user",
        "json": {"field": "descricao", "value": "Descricao inline API"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_comentario_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/comentario",
        "path": "/api/etapas/{etapa_id}/comentario",
        "role": "user",
        "json": {"comentario": "Comentario via API"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_toggle_iniciada_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/toggle-iniciada",
        "path": "/api/etapas/{etapa_id}/toggle-iniciada",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_toggle_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/toggle",
        "path": "/api/etapas/{etapa_id}/toggle",
        "role": "user",
        "expected_status": 422,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_responsaveis_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/responsaveis",
        "path": "/api/etapas/{etapa_id}/responsaveis",
        "role": "user",
        "json": {"areas": [{"area_id": None, "label": "Outras"}]},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_areas_get",
        "method": "GET",
        "rule": "/api/areas",
        "path": "/api/areas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapas_reordenar_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/etapas/reordenar",
        "path": "/api/projetos/{project_id}/etapas/reordenar",
        "role": "user",
        "json": {
            "etapa_ids": ["{etapa_id}", "{etapa_started_id}"],
            "etapa_id": "{etapa_id}",
            "days_diff": 2,
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_cascade_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/cascade",
        "path": "/api/projetos/{project_id}/cascade",
        "role": "user",
        "json": {"etapa_id": "{etapa_id}", "days_diff": 2},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_projeto_importar_modelo_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/importar-modelo",
        "path": "/api/projetos/{project_id}/importar-modelo",
        "role": "user",
        "json": {"template_id": "{template_id}", "start_date": "2026-03-10"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapas_templates_get",
        "method": "GET",
        "rule": "/api/etapas/templates",
        "path": "/api/etapas/templates",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefas_get",
        "method": "GET",
        "rule": "/api/tarefas",
        "path": "/api/tarefas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefas_board_get",
        "method": "GET",
        "rule": "/api/tarefas/board",
        "path": "/api/tarefas/board",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_status_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/status",
        "path": "/api/tarefas/{task_id}/status",
        "role": "user",
        "json": {"status": "em_andamento"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefas_board_reordenar_post",
        "method": "POST",
        "rule": "/api/tarefas/board/reordenar",
        "path": "/api/tarefas/board/reordenar",
        "role": "user",
        "json": {
            "columns": [
                {"status": "nao_iniciada", "task_ids": ["{task_id}"]},
            ]
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # Fase 5b-2 (Drawer de Tarefa): detalhe + edicao inline (autosave) + lifecycle.
    {
        "id": "api_tarefa_detalhe_get",
        "method": "GET",
        "rule": "/api/tarefas/<int:task_id>/detalhe",
        "path": "/api/tarefas/{task_id}/detalhe",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_campos_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/campos",
        "path": "/api/tarefas/{task_id}/campos",
        "role": "user",
        "json": {"descricao": "Tarefa editada via drawer"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_finalizar_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/finalizar",
        "path": "/api/tarefas/{task_id}/finalizar",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_arquivar_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/arquivar",
        "path": "/api/tarefas/{task_id}/arquivar",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_desarquivar_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/desarquivar",
        "path": "/api/tarefas/{task_id}/desarquivar",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_reativar_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/reativar",
        "path": "/api/tarefas/{task_id}/reativar",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_sugestoes_responsavel_get",
        "method": "GET",
        "rule": "/api/tarefas/<int:task_id>/sugestoes-responsavel",
        "path": "/api/tarefas/{task_id}/sugestoes-responsavel",
        "role": "user",
        "query_string": {"q": "Usuario"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        # Responsáveis MÚLTIPLOS da tarefa (autor/admin). Lista vazia limpa os
        # responsáveis e ainda commita -> 200 (mesma regra de finalizar/campos).
        "id": "api_tarefa_responsaveis_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/responsaveis",
        "path": "/api/tarefas/{task_id}/responsaveis",
        "role": "user",
        "json": {"user_ids": []},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # Fase 5b-2 (Drawer de Tarefa): comentarios (add/editar/excluir) + anexos
    # (listar/upload multipart/download binario/excluir). Anexados ao main_bp em
    # routes/api/task_comments.py e routes/api/task_attachments.py, no envelope
    # (EXCETO o download binario), com api_login_required + permissoes reusadas.
    {
        "id": "api_tarefa_comentario_add_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/comentarios",
        "path": "/api/tarefas/{task_id}/comentarios",
        "role": "user",
        "json": {"content": "Comentario via drawer"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_comentario_edit_post",
        "method": "POST",
        "rule": "/api/comentarios/<int:comment_id>",
        "path": "/api/comentarios/{comment_id}",
        "role": "user",
        "json": {"content": "Comentario editado via drawer"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_comentario_delete_post",
        "method": "POST",
        "rule": "/api/comentarios/<int:comment_id>/delete",
        "path": "/api/comentarios/{comment_id}/delete",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_anexos_list_get",
        "method": "GET",
        "rule": "/api/tarefas/<int:task_id>/anexos",
        "path": "/api/tarefas/{task_id}/anexos",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_anexo_upload_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/anexos",
        "path": "/api/tarefas/{task_id}/anexos",
        "role": "user",
        # Magic bytes "%PDF-" casam a extensao .pdf em _file_content_matches_extension.
        "files": {"file": (b"%PDF-1.4\n%fake pdf body for smoke", "doc.pdf")},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_anexo_download_get",
        "method": "GET",
        "rule": "/api/anexos/<int:anexo_id>",
        "path": "/api/anexos/{anexo_id}",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_anexo_delete_post",
        "method": "POST",
        "rule": "/api/anexos/<int:anexo_id>/delete",
        "path": "/api/anexos/{anexo_id}/delete",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_busca_get",
        "method": "GET",
        "rule": "/api/busca",
        "path": "/api/busca",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # SPA shell (catch-all servido via Jinja + csp_nonce; routes/spa.py).
    # Raiz da SPA e subpaths client-side (ex.: /spa/dashboard) rendam o index.
    # Nao exige login: o guard de auth e client-side (carrega /api/me no boot).
    {
        "id": "spa_index_get",
        "method": "GET",
        "rule": "/spa",
        "path": "/spa",
        "role": "anon",
        "expected_status": 200,
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "spa_index_subpath_get",
        "method": "GET",
        "rule": "/spa/<path:subpath>",
        "path": "/spa/dashboard",
        "role": "anon",
        "expected_status": 200,
        "requires_login": False,
        "requires_admin": False,
    },
    # SPA nos PATHS NATIVOS (item #1): catch-all dinamico que serve o index
    # (Jinja + csp_nonce) nos paths das telas migradas sem rota Jinja propria
    # (ex.: /projetos, /admin/usuarios). Paths nao migrados -> 404.
    {
        "id": "spa_native_path_get",
        "method": "GET",
        "rule": "/<path:spa_path>",
        "path": "/projetos",
        "role": "anon",
        "expected_status": 200,
        "requires_login": False,
        "requires_admin": False,
    },
    # Assets imutaveis do bundle SvelteKit. Com paths.base='' o cliente os pede
    # em /_app/...; esta rota serve a partir de static/spa/_app/.
    {
        "id": "spa_app_asset_get",
        "method": "GET",
        "rule": "/_app/<path:asset_path>",
        "path": "/_app/version.json",
        "role": "anon",
        "expected_status": 200,
        "requires_login": False,
        "requires_admin": False,
    },
    # API and search
    {
        "id": "api_resultados_get",
        "method": "GET",
        "rule": "/api/resultados/<int:objetivo_id>",
        "path": "/api/resultados/1",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_indicadores_get",
        "method": "GET",
        "rule": "/api/indicadores/<int:resultado_id>",
        "path": "/api/indicadores/1",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_templates_get",
        "method": "GET",
        "rule": "/api/templates",
        "path": "/api/templates",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_template_stages_get",
        "method": "GET",
        "rule": "/api/templates/<int:template_id>",
        "path": "/api/templates/{template_id}",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_busca_global_get",
        "method": "GET",
        "rule": "/api/busca-global",
        "path": "/api/busca-global",
        "role": "user",
        "query_string": {"q": "Projeto"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # /busca: rota Jinja canonica CORTADA (Grupo B). Agora servida pela SPA via
    # catch-all (_MIGRATED_EXACT_PATHS); a API de busca permanece em /api/busca e
    # /api/busca-global (widget da topnav).
    {
        "id": "notifications_dropdown_post",
        "method": "POST",
        "rule": "/api/notificacoes/dropdown",
        "path": "/api/notificacoes/dropdown",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # Admin users (Jinja): rotas CORTADAS na migracao SPA — o CRUD vive em
    # /admin/usuarios* (SPA) + /api/admin/usuarios* (envelope).
    # Admin templates/orgaos/tipos: rotas Jinja canonicas CORTADAS (Grupo B).
    # /admin/templates, /admin/orgaos e /admin/orgaos/tipos agora servem a SPA via
    # catch-all (_MIGRATED_EXACT_PATHS em routes/spa.py); o CRUD vive em
    # /api/admin/templates*, /api/admin/orgaos* e /api/admin/orgaos/tipos*.
    # Maintenance
    {
        "id": "favicon_get",
        "method": "GET",
        "rule": "/favicon.ico",
        "path": "/favicon.ico",
        "role": "anon",
        "expected_status": [200, 404],
        "requires_login": False,
        "requires_admin": False,
    },
    {
        "id": "setup_db_get",
        "method": "GET",
        "rule": "/setup_db",
        "path": "/setup_db",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "calendar_event_generate_meet_post",
        "method": "POST",
        "rule": "/calendarios/eventos/<int:event_id>/gerar-meet",
        "path": "/calendarios/eventos/{calendar_event_id}/gerar-meet",
        "role": "user",
        "expected_status": 302,
        "requires_login": True,
        "requires_admin": False,
    },
    # SPA API — Admin usuarios (envelope canônico; api_admin_required)
    {
        "id": "api_admin_usuarios_list_get",
        "method": "GET",
        "rule": "/api/admin/usuarios",
        "path": "/api/admin/usuarios",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_usuarios_detail_get",
        "method": "GET",
        "rule": "/api/admin/usuarios/<int:user_id>",
        "path": "/api/admin/usuarios/{editable_user_id}",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_usuarios_create_post",
        "method": "POST",
        "rule": "/api/admin/usuarios",
        "path": "/api/admin/usuarios",
        "role": "admin",
        "json": {
            "username": "novo_usuario_api",
            "name": "Novo Usuario API",
            "password": "senhaNova123",
            "orgao": "Orgao Novo",
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_usuarios_update_post",
        "method": "PUT",
        "rule": "/api/admin/usuarios/<int:user_id>",
        "path": "/api/admin/usuarios/{editable_user_id}",
        "role": "admin",
        "json": {"name": "Usuario Editado API", "orgao": "Orgao Editado"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_usuarios_remove_cpf_post",
        "method": "POST",
        "rule": "/api/admin/usuarios/<int:user_id>/remover-cpf",
        "path": "/api/admin/usuarios/{editable_user_id}/remover-cpf",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_usuarios_delete_post",
        "method": "DELETE",
        "rule": "/api/admin/usuarios/<int:user_id>",
        "path": "/api/admin/usuarios/{deletable_user_id}",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    # SPA API — Admin orgaos (arvore) + tipos (envelope; api_admin_required)
    {
        "id": "api_admin_orgaos_tree_get",
        "method": "GET",
        "rule": "/api/admin/orgaos",
        "path": "/api/admin/orgaos",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_orgaos_opcoes_get",
        "method": "GET",
        "rule": "/api/admin/orgaos/opcoes",
        "path": "/api/admin/orgaos/opcoes",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_orgaos_detail_get",
        "method": "GET",
        "rule": "/api/admin/orgaos/<int:orgao_id>",
        "path": "/api/admin/orgaos/{orgao_child_id}",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    # SPA API — Integração SIORG (contrato cru, sem envelope; api_admin_required)
    {
        "id": "api_admin_siorg_status_get",
        "method": "GET",
        "rule": "/api/admin/siorg/status",
        "path": "/api/admin/siorg/status",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        # Sem SIORG_API_KEY no app de teste: a rota curto-circuita em 503
        # "não configurada" antes de construir o client (sem backoff/retry).
        "id": "api_admin_siorg_sync_post",
        "method": "POST",
        "rule": "/api/admin/siorg/sync",
        "path": "/api/admin/siorg/sync",
        "role": "admin",
        "expected_status": 503,
        "requires_login": True,
        "requires_admin": True,
    },
    # SPA API — Admin templates de etapas (envelope; api_admin_required)
    {
        "id": "api_admin_templates_list_get",
        "method": "GET",
        "rule": "/api/admin/templates",
        "path": "/api/admin/templates",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_templates_detail_get",
        "method": "GET",
        "rule": "/api/admin/templates/<int:template_id>",
        "path": "/api/admin/templates/{template_id}",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_templates_create_post",
        "method": "POST",
        "rule": "/api/admin/templates",
        "path": "/api/admin/templates",
        "role": "admin",
        "json": {
            "name": "Template Novo API",
            "description": "Criado nos testes via API",
            "stages": [{"name": "Etapa A", "duration_days": 2}],
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_templates_update_post",
        "method": "PUT",
        "rule": "/api/admin/templates/<int:template_id>",
        "path": "/api/admin/templates/{template_id}",
        "role": "admin",
        "json": {
            "name": "Template Editado API",
            "description": "Atualizado nos testes via API",
            "stages": [{"name": "Etapa B", "duration_days": 4}],
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_templates_duplicate_post",
        "method": "POST",
        "rule": "/api/admin/templates/<int:template_id>/duplicate",
        "path": "/api/admin/templates/{template_id}/duplicate",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_admin_templates_delete_post",
        "method": "DELETE",
        "rule": "/api/admin/templates/<int:template_id>",
        "path": "/api/admin/templates/{template_id}",
        "role": "admin",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": True,
    },
    # Fase 6 (Google Calendar): hub JSON + acoes de conexao Google no envelope.
    {
        "id": "api_calendarios_hub_get",
        "method": "GET",
        "rule": "/api/calendarios",
        "path": "/api/calendarios",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        # Membros do Time visíveis no calendário (usuários do mesmo órgão + admins).
        "id": "api_calendarios_membros_get",
        "method": "GET",
        "rule": "/api/calendarios/membros",
        "path": "/api/calendarios/membros",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendarios_google_disconnect_post",
        "method": "POST",
        "rule": "/api/calendarios/google/disconnect",
        "path": "/api/calendarios/google/disconnect",
        "role": "user",
        "expected_status": 404,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendarios_google_sync_post",
        "method": "POST",
        "rule": "/api/calendarios/google/sync",
        "path": "/api/calendarios/google/sync",
        "role": "user",
        "expected_status": 409,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendarios_google_watch_renew_post",
        "method": "POST",
        "rule": "/api/calendarios/google/watch/renew",
        "path": "/api/calendarios/google/watch/renew",
        "role": "user",
        "expected_status": 409,
        "requires_login": True,
        "requires_admin": False,
    },
]

LOGIN_REQUIRED_CASES = [case for case in ROUTE_CASES if case["requires_login"]]
ADMIN_REQUIRED_CASES = [case for case in ROUTE_CASES if case["requires_admin"]]

# Segurança adicional para garantir escopo fechado do plano.
# 134 rotas originais + 6 endpoints JSON da SPA da Fase 2 (/api/me,
# /api/csrf-token, /api/dashboard, /api/projetos-pendentes,
# /api/projetos/<id>/historico, /api/busca) + 2 endpoints JSON da Fase 3
# (/api/projetos, /api/tarefas) + 2 rotas do shell SPA (/spa e
# /spa/<path:subpath>).
# As telas /spa/* (Lista de Projetos e Hub de Tarefas em modo lista) NAO
# adicionam rota Flask: são servidas pelo catch-all /spa/<path:subpath>
# (client-side routing). O filtro de orgao de Pendentes também NAO adiciona rota
# (só estende o payload de /api/projetos-pendentes com orgaos_options).
# + 6 endpoints JSON da Fase 4 (Admin Usuarios): GET /api/admin/usuarios,
# GET /api/admin/usuarios/<id>, POST /api/admin/usuarios (criar),
# PUT /api/admin/usuarios/<id> (editar — RESTificado), POST .../remover-cpf
# (acao) e DELETE /api/admin/usuarios/<id> (excluir — RESTificado).
# + 14 endpoints JSON da Fase 4 (Admin Orgaos/Tipos): GET /api/admin/orgaos
# (arvore), GET /api/admin/orgaos/<id>, POST /api/admin/orgaos (criar), PUT
# /api/admin/orgaos/<id> (editar), DELETE /api/admin/orgaos/<id> (excluir),
# POST .../move, .../reorder, .../toggle-ativo (acoes); GET /api/admin/orgaos/
# tipos (lista), GET .../tipos/<id>, POST .../tipos (criar), PUT .../tipos/<id>
# (editar), POST .../tipos/<id>/toggle-ativo (acao) e DELETE .../tipos/<id>
# (excluir). CRUD de recurso RESTificado (PUT/DELETE); reorder/move/toggle-ativo
# permanecem POST (acoes/comandos).
# + 6 endpoints JSON da Fase 4 (Admin Templates de etapas): GET
# /api/admin/templates (lista com metricas + ?order=/?q=/?page=), GET
# /api/admin/templates/<id> (form + etapas), POST /api/admin/templates (criar),
# PUT /api/admin/templates/<id> (editar — RESTificado), POST .../duplicate
# (acao) e DELETE /api/admin/templates/<id> (excluir — RESTificado).
# + 3 endpoints JSON da Fase 5a (Detalhe de Projeto): GET
# /api/projetos/<id>/detalhe (payload completo do detalhe: projeto + etapas com
# contagem de tarefas read-only + derivados + opcoes + permissions), POST
# /api/projetos/<id>/inline (edicao inline reusando apply_project_inline_changes;
# 422 validation / 403 forbidden) e GET /api/projetos/<id>/tarefas-etapa (lista
# SOMENTE LEITURA das tarefas de uma etapa).
# + 10 endpoints JSON da Fase 5a (Etapas — mutacao): POST
# /api/projetos/<id>/etapas (adicionar), POST /api/etapas/<id> (editar), POST
# /api/etapas/<id>/delete, POST /api/etapas/<id>/update-field (inline; cascata
# de datas em dias uteis server-side), POST /api/etapas/<id>/comentario, POST
# /api/etapas/<id>/toggle-iniciada, POST /api/etapas/<id>/toggle, POST
# /api/projetos/<id>/etapas/reordenar (reordena e dispara cascade_subsequent_dates
# server-side; devolve as etapas atualizadas), POST /api/projetos/<id>/cascade
# (recalculo de datas em cascata) e POST /api/projetos/<id>/importar-modelo
# (aplica template reusando import_template_stages). Todos no envelope, com
# api_login_required + user_can_access_project (404/403).
#
# Fase 5b-1 (Kanban): GET /api/tarefas/board (5 colunas por status), POST
# /api/tarefas/<id>/status (transição autoritativa via _can_transition_task_to_status)
# e POST /api/tarefas/board/reordenar (ordem + status entre colunas). Anexados ao
# main_bp em routes/api/board.py, no envelope, com api_login_required + escopo de
# órgão. Total: 186.
#
# Fase 5b-2 (Drawer de Tarefa): GET /api/tarefas/<id>/detalhe (payload completo do
# drawer: campos editaveis + status/prioridade/tipo/responsavel + contexto
# etapa/projeto + comentarios + anexos + permissions), POST /api/tarefas/<id>/campos
# (edicao inline AUTOSAVE de descricao/prioridade/tipo/responsavel; status continua
# em /api/tarefas/<id>/status da 5b-1), POST /api/tarefas/<id>/finalizar (respeita
# _can_manage_task_restricted_actions -> 403), POST /api/tarefas/<id>/arquivar, POST
# /api/tarefas/<id>/desarquivar, POST /api/tarefas/<id>/reativar (alias) e GET
# /api/tarefas/<id>/sugestoes-responsavel (picker). Anexados ao main_bp em
# routes/api/task_drawer.py, no envelope, com api_login_required + permissoes
# server-side (reusa _can_view_task / _can_manage_task_restricted_actions). +7.
#
# Fase 5b-2 (etapa backend 2/2 — Comentarios + Anexos): POST
# /api/tarefas/<id>/comentarios (add), POST /api/comentarios/<id> (editar autor),
# POST /api/comentarios/<id>/delete (excluir autor); GET /api/tarefas/<id>/anexos
# (listar), POST /api/tarefas/<id>/anexos (UPLOAD multipart request.files["file"],
# valida tipo/conteudo + limite 10MB -> 413), GET /api/anexos/<id> (DOWNLOAD
# binario send_file — NAO envelopado, mas api_login_required + _can_view_task) e
# POST /api/anexos/<id>/delete (excluir; autor/admin). Anexados ao main_bp em
# routes/api/task_comments.py e routes/api/task_attachments.py, reusando as regras
# legadas (_can_view_task para comentar; autoria para editar/excluir comentario;
# _can_manage_task_restricted_actions para excluir anexo). +7.
#
# Fase 6 (Google Calendar): GET /api/calendarios (hub: eventos do usuario
# ordenados + estado da conexao SEM tokens + google_calendar_enabled +
# last_sync_display) e tres acoes de conexao que reusam EXATAMENTE os helpers do
# fluxo Jinja (routes/calendars/helpers.py), porem no envelope: POST
# /api/calendarios/google/disconnect (_stop_watch_channel + delete), POST
# /api/calendarios/google/sync (_sync_events_from_google -> summary
# {upserted,deleted,ignored}) e POST /api/calendarios/google/watch/renew
# (_renew_watch_channel -> {expires_at_display}). Token expirado e tratado igual
# ao legado (_describe_calendar_issue + _EXPIRED_TOKEN_CODES -> _auto_disconnect).
# O CRUD de evento NAO ganha endpoint /api: o frontend reusa POST
# /calendarios/eventos[/...] com Accept: application/json. Anexados ao main_bp em
# routes/api/calendars.py, com api_login_required. +4.
#
# Debito tecnico de backend (enveloped, aditivos; nao alteram os legados):
# + GET /api/etapas/templates (#13): espelho enveloped do legado GET /api/templates
#   (que devolve array cru e HTML em 401) para o modal de importacao de modelos;
#   reusa a MESMA query/serializacao (_stage_templates_payload em
#   routes/api/etapas.py), com api_login_required. role=user.
# + GET /api/admin/orgaos/opcoes (#10): opcoes de orgaos ATIVOS ja achatadas
#   (id/sigla/nome/pai_id) para o seletor do form de usuario, reusando
#   _list_orgaos_with_parent (routes/admin_users.py). Anexado em
#   routes/api/admin_orgaos.py, com api_admin_required. role=admin.
# Total: 206.
#
# Fase 0a (corte SPA): removidas as 11 rotas shim orfas /tarefas/itens/* (legacy.py
# deletado). 206 - 11 = 195. Cobertura preservada nas rotas canonicas /tarefas/<id>/*.
#
# Item #1 (SPA em PATHS NATIVOS): +2 rotas em routes/spa.py.
# + GET /<path:spa_path>: catch-all dinamico (rank < rotas estaticas) que serve o
#   index da SPA (Jinja + csp_nonce) nos paths nativos das telas migradas SEM rota
#   Jinja propria (/projetos, /projetos/pendentes, /projetos/<id>, /admin/usuarios,
#   /admin/orgaos/novo, /admin/orgaos/<id>, /admin). Paths nao migrados -> 404.
# + GET /_app/<path:asset_path>: serve os assets imutaveis do SvelteKit a partir
#   de static/spa/_app/ (com paths.base='' o cliente os pede em /_app/...).
# Os paths migrados que colidem com rotas Jinja de mesma URL (/dashboard, /tarefas,
# /busca, /calendarios, /admin/orgaos, /admin/orgaos/tipos, /admin/templates) NAO
# adicionam rota: sao servidos via before_app_request que curto-circuita o GET.
# 195 + 2 = 197.
#
# Features de paridade (mutacoes da SPA no envelope canonico, aditivas; NAO
# alteram os legados Jinja, que continuam servindo flash+redirect):
# + POST /api/projetos (criar projeto, reusa services/project_creation).
# + POST /api/projetos/<id>/concluir (concluir projeto, reusa
#   services/project_completion).
# + GET  /api/catalogos/objetivos (catalogo de objetivos para o modal).
# + GET  /api/projetos/<pid>/etapas/<eid>/tarefas (tarefas da etapa, quick-add).
# + POST /api/tarefas (criar tarefa, reusa _create_task_common).
# + POST /api/tarefas/<id>/excluir (excluir tarefa, reusa notify_task_deleted).
# + POST /api/tarefas/<id>/mover-etapa (mover etapa, reusa move_task_to_etapa).
# + POST /api/tarefas/arquivar-finalizadas (lote, reusa bulk_archive_finalized).
# + GET  /api/tarefas/sugestoes-responsavel (picker do hub).
# Reunioes Google (Detalhe do Projeto) + CRUD de evento dedicado (#20):
# + POST /api/projetos/<id>/reunioes (criar reuniao, reusa create_stage_meeting).
# + POST /api/etapas/<id>/reuniao (editar reuniao, reusa update_stage_meeting).
# + POST /api/etapas/<id>/reuniao/excluir (excluir reuniao, reusa delete_meeting_etapa).
# + POST /api/calendarios/eventos (criar evento, reusa helpers de events.py).
# + POST /api/calendarios/eventos/<id>/editar (editar evento).
# + POST /api/calendarios/eventos/<id>/excluir (excluir evento).
# + POST /api/calendarios/eventos/<id>/gerar-meet (gerar link do Meet).
# 197 + 16 = 213.
ROUTE_CASES += [
    {
        "id": "api_projeto_criar_post",
        "method": "POST",
        "rule": "/api/projetos",
        "path": "/api/projetos",
        "role": "user",
        "json": {
            "titulo": "Projeto via API",
            "orgao_id": "{auditoria_orgao_id}",
            "prioridade": "media",
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        # Import de projetos via CSV (Admin) — sucessor de /projects/import.
        # Sem corpo, o handler valida e devolve 422 (órgão obrigatório).
        "id": "api_projetos_importar_csv_post",
        "method": "POST",
        "rule": "/api/projetos/importar-csv",
        "path": "/api/projetos/importar-csv",
        "role": "admin",
        "expected_status": 422,
        "requires_login": True,
        "requires_admin": True,
    },
    {
        "id": "api_projeto_concluir_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/concluir",
        "path": "/api/projetos/{project_complete_id}/concluir",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_catalogo_objetivos_get",
        "method": "GET",
        "rule": "/api/catalogos/objetivos",
        "path": "/api/catalogos/objetivos",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_etapa_tarefas_get",
        "method": "GET",
        "rule": "/api/projetos/<int:project_id>/etapas/<int:etapa_id>/tarefas",
        "path": "/api/projetos/{project_id}/etapas/{etapa_id}/tarefas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_criar_post",
        "method": "POST",
        "rule": "/api/tarefas",
        "path": "/api/tarefas",
        "role": "user",
        "json": {
            "project": "{project_id}",
            "descricao": "Tarefa via API",
            "status": "nao_iniciada",
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_excluir_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/excluir",
        "path": "/api/tarefas/{task_id}/excluir",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefa_mover_etapa_post",
        "method": "POST",
        "rule": "/api/tarefas/<int:task_id>/mover-etapa",
        "path": "/api/tarefas/{task_id}/mover-etapa",
        "role": "user",
        "json": {"etapa_id": "{etapa_started_id}"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_tarefas_arquivar_finalizadas_post",
        "method": "POST",
        "rule": "/api/tarefas/arquivar-finalizadas",
        "path": "/api/tarefas/arquivar-finalizadas",
        "role": "user",
        "json": {},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_hub_sugestoes_responsavel_get",
        "method": "GET",
        "rule": "/api/tarefas/sugestoes-responsavel",
        "path": "/api/tarefas/sugestoes-responsavel",
        "role": "user",
        "query_string": {"project": "{project_id}"},
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_project_meeting_create_post",
        "method": "POST",
        "rule": "/api/projetos/<int:project_id>/reunioes",
        "path": "/api/projetos/{project_id}/reunioes",
        "role": "user",
        "json": {
            "title": "Reuniao via API",
            "starts_at": "2026-04-01T10:00",
            "ends_at": "2026-04-01T11:00",
        },
        # Sem conexao Google ativa no seed => 400 (mesma regra do legado).
        "expected_status": 400,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_project_meeting_edit_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/reuniao",
        "path": "/api/etapas/{etapa_id}/reuniao",
        "role": "user",
        "json": {
            "title": "Reuniao editada via API",
            "starts_at": "2026-04-01T10:00",
            "ends_at": "2026-04-01T11:00",
        },
        # Etapa regular do seed nao e reuniao Google editavel => 400.
        "expected_status": 400,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_project_meeting_delete_post",
        "method": "POST",
        "rule": "/api/etapas/<int:etapa_id>/reuniao/excluir",
        "path": "/api/etapas/{etapa_id}/reuniao/excluir",
        "role": "user",
        # Etapa regular do seed nao e reuniao Google => 422 (mesma regra do
        # legado: exclusao de reuniao so vale para etapas-reuniao Google).
        "expected_status": 422,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendar_event_create_post",
        "method": "POST",
        "rule": "/api/calendarios/eventos",
        "path": "/api/calendarios/eventos",
        "role": "user",
        "json": {
            "title": "Evento via API",
            "starts_at": "2026-04-02T09:00",
            "ends_at": "2026-04-02T10:00",
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendar_event_edit_post",
        "method": "POST",
        "rule": "/api/calendarios/eventos/<int:event_id>/editar",
        "path": "/api/calendarios/eventos/{calendar_event_id}/editar",
        "role": "user",
        "json": {
            "title": "Evento editado via API",
            "starts_at": "2026-04-02T09:00",
            "ends_at": "2026-04-02T10:00",
        },
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendar_event_generate_meet_post",
        "method": "POST",
        "rule": "/api/calendarios/eventos/<int:event_id>/gerar-meet",
        "path": "/api/calendarios/eventos/{calendar_event_id}/gerar-meet",
        "role": "user",
        # Sem conexao Google ativa no seed => 409 (mesma regra do legado).
        "expected_status": 409,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_calendar_event_delete_post",
        "method": "POST",
        "rule": "/api/calendarios/eventos/<int:event_id>/excluir",
        "path": "/api/calendarios/eventos/{calendar_event_id}/excluir",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    # SPA aditivos (Fase atual): exclusao real de projeto, notificacoes enveloped
    # e arvore de orgao do escopo (seletor da topnav).
    {
        "id": "api_projeto_excluir_delete",
        "method": "DELETE",
        "rule": "/api/projetos/<int:project_id>",
        "path": "/api/projetos/{project_id}",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_notificacoes_list_get",
        "method": "GET",
        "rule": "/api/notificacoes",
        "path": "/api/notificacoes",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_notificacoes_marcar_lidas_post",
        "method": "POST",
        "rule": "/api/notificacoes/marcar-lidas",
        "path": "/api/notificacoes/marcar-lidas",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
    {
        "id": "api_orgaos_escopo_get",
        "method": "GET",
        "rule": "/api/orgaos/escopo",
        "path": "/api/orgaos/escopo",
        "role": "user",
        "expected_status": 200,
        "requires_login": True,
        "requires_admin": False,
    },
]

# Corte Grupo B (rotas Jinja canonicas -> SPA via catch-all):
# - Admin Tipos de orgao: 7 casos removidos (/admin/orgaos/tipos*).
# - Admin Templates de etapa: 7 casos removidos (/admin/templates*).
# - Admin Orgaos (arvore): 9 casos removidos (/admin/orgaos*, exceto /api/*).
# - Busca: 1 caso removido (/busca).
# Total removido: 24. 205 - 24 = 181. Cobertura de regras de negocio preservada
# nos contratos /api/admin/* e /api/busca. As telas Dashboard, Tarefas/Hub e
# Calendarios Hub NAO foram cortadas: seus endpoints (main.dashboard,
# main.list_tasks*/task_detail/project_tasks, main.calendars_hub) sao alvo de
# url_for vivos em arquivos IMUTAVEIS (auth.py/decorators.py/calendars/oauth.py)
# e em rotas/templates Jinja ainda vivos.
#
# +4 aditivos da SPA (Fase atual): DELETE /api/projetos/<id> (exclusao real),
# GET /api/notificacoes, POST /api/notificacoes/marcar-lidas e GET
# /api/orgaos/escopo. 181 + 4 = 185.
# +2 rotas antes sem cobertura: POST /api/tarefas/<id>/responsaveis e
# GET /api/calendarios/membros. 186 + 2 = 188.
# -1 da lane de limpeza de codigo morto: GET /api/projetos_usuario removido
# (rota sem consumidor em static/, templates/ ou frontend/). 188 - 1 = 187.
# -2 da lane de migracao SPA (corte de duplicata Jinja): GET/POST
# /etapa/<id>/edit removidos (edicao de etapa 100% coberta inline na SPA via
# /api/etapas/<id>). 187 - 2 = 185.
# -1 da lane 2: GET /project/<id>/history removido (historico vira modal na SPA
# via /api/projetos/<id>/historico; build_project_history_context preservada).
# 185 - 1 = 184.
# -7 da lane 3: /admin/users* (Jinja) cortado — list/add(GET+POST)/edit(GET+POST)/
# delete/remove-cpf. CRUD 100% na SPA (/admin/usuarios* + /api/admin/usuarios*).
# 184 - 7 = 177.
# -2 da lane 4 (sub-passo edit): GET/POST /project/<id>/edit removidos (edição de
# projeto 100% inline na SPA via /api/projetos/<id>/inline, que reusa
# apply_project_inline_changes). 177 - 2 = 175.
# -1 da lane 4 (sub-passo pendentes): GET /projetos_pendentes removido (tela SPA
# /projetos/pendentes via /api/projetos/pendentes; build_projetos_pendentes_context
# preservada). 175 - 1 = 174.
# +1 da lane 4 (migração CSV import p/ SPA): POST /api/projetos/importar-csv
# (sucessor de /projects/import). 174 + 1 = 175.
# -8 da varredura final do /projects (cluster Jinja cortado): import_projects,
# add_project, project_edit_data, project_update_inline, project_delete,
# project_concluir, project_stage_tasks_panel, project_legacy_tasks_panel.
# /projects vira redirect (projects_get permanece, status 200->302). 175 - 8 = 167.
# +2 da mudança #3 (responsáveis de etapa por área): GET /api/areas e
# POST /api/etapas/<id>/responsaveis. 167 + 2 = 169.
# -10 da integração SIORG (estrutura vira espelho read-only): rotas de escrita
# de /api/admin/orgaos* cortadas — POST/PUT/DELETE de unidades, /move, /reorder,
# /toggle-ativo e POST/PUT/DELETE//toggle-ativo de tipos (GETs preservados).
# +2 endpoints SIORG: GET /api/admin/siorg/status e POST /api/admin/siorg/sync.
# 169 - 10 + 2 = 161.
# -2 do corte do catálogo local de tipos (sem consumidor em frontend/src): GET
# /api/admin/orgaos/tipos e GET /api/admin/orgaos/tipos/<id>. 161 - 2 = 159.
assert len(ROUTE_CASES) == 159
