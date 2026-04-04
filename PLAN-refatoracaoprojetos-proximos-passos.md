# Refatoração projetosRj — Próximos passos

## Concluídos

| # | Arquivo | Resultado |
|---|---------|-----------|
| 1 | `static/js/pages/projects/detail/01-main.js` | 3.535 → 843 linhas. Desmembrado em 9 módulos (`02-import-model` a `10-compact-header`). |
| 2 | `static/js/modules/kanban-manager.js` | 3.231 → 541 linhas. Desmembrado em 7 módulos em `kanban/`. |
| 3 | `routes/tasks/helpers.py` | 969 → 58 linhas (fachada). Desmembrado em `constants.py`, `permissions.py`, `queries.py`, `hub.py`, `creation.py`. |
| 4 | `templates/base.html` | 1.123 → 277 linhas. Extraído `partials/app_topnav.html` (273 linhas) e `partials/skeleton_macros.html` (576 linhas). |
| 5 | `templates/calendars/calendars.html` | 986 → 128 linhas. JS inline movido para `static/js/pages/calendars.js` (870 linhas). Config via `window.__CALENDAR_PAGE_CONFIG__`. |

---

## Passo 6 — `static/js/modules/add-item-inline.js` (Prioridade 2)

**O que é:** 1.075 linhas misturando fábrica de markup, project picker, inserção ordenada e controle de formulário.

**Corte sugerido:**
1. `dom-factories.js` — criação de elementos HTML
2. `project-picker.js` — seletor de projeto
3. `group-manager.js` — inserção ordenada em grupos
4. `inline-form-controller.js` — lógica de formulário inline
5. `add-item-inline.js` vira orquestrador leve

**Cuidados:**
- Fluxo de criação inline e global no hub de tarefas

---

## Passo 7 — `routes/etapas/crud.py` (Prioridade 2)

**O que é:** 712 linhas misturando endpoints, validação, reativação, exclusão com Google, update inline e cascata de datas.

**Corte sugerido:**
1. Manter rotas finas em `crud.py`
2. Extrair `services/etapas_mutation.py` — lógica de criação/edição/exclusão
3. Extrair `services/etapas_cascade.py` — cascata e recalculo de datas

**Cuidados:**
- Preservar transações de banco e rollback
- Testar fluxo completo: add/edit/delete etapa, reorder, cascata, reunião Google

---

## Passo 8 — `static/js/app-shell.js` (Prioridade 2)

**O que é:** 945 linhas misturando tema, flash, skeleton navigation, busca global, notificações e interceptação de navegação.

**Corte sugerido:**
1. `theme.js` — alternância de tema
2. `flash.js` — mensagens flash
3. `skeleton-navigation.js` — navegação com skeleton
4. `global-search.js` — busca global
5. `notifications.js` — polling e dropdown de notificações
6. `app-shell.js` vira orquestrador

**Cuidados:**
- **Fazer depois do passo 4** (`base.html`) para não cortar a UI em dois lugares ao mesmo tempo
- Preservar IDs e `data-*` do template

---

## Passos posteriores (Prioridade 3)

- **`templates/tasks/hub.html`** — parciais para group-list, kanban-column, drawer, anexo-preview
- **CSS monolítico** (`theme-dark.css`, `tasks/detail/dark.css`, `10-skeleton.css`, `20-glass-forms-and-admin.css`) — cortar por componente/página, não por tamanho

---

## Regras gerais

- Nunca alterar URLs Flask nem nomes de endpoints
- Preservar IDs, classes-chave e `data-*` consumidos por JS
- Manter `window.__*_CONFIG__` como ponte template→JS
- Não introduzir bundler/ESM neste ciclo
- Máximo 2 arquivos por vez para controlar área de regressão
