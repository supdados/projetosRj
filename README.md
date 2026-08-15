# ProjetosRJ

Gerenciador de projetos para órgãos do Estado do Rio de Janeiro — controle de
projetos, etapas, tarefas, equipes e calendário, com login federado **Gov.br**.

> _Project management app for agencies of the State of Rio de Janeiro — projects,
> stages, tasks, teams and calendar, with **Gov.br** federated login._

Licença / License: **Apache-2.0** · Autor / Author: **José Hudson de Oliveira Guimarães Junior** (@jhogj)

---

## 🇧🇷 Português

### Visão geral
Aplicação web full-stack para acompanhamento de projetos públicos: hierarquia
**Projeto → Etapa → Tarefa**, atribuição de responsáveis, comentários e anexos,
quadro Kanban, dashboards, busca global e integração com **Google Calendar**.
A autenticação usa **Gov.br (OpenID Connect)**.

### Stack
- **Backend:** Python · Flask 3 · SQLAlchemy 2 · Flask-Migrate (Alembic) ·
  MySQL (PyMySQL) · Flask-WTF (CSRF) · Flask-Limiter · `cryptography` · Gunicorn.
- **Frontend (v5.0):** SvelteKit (Svelte 5) + Tailwind, compilado como SPA.
- **Auth:** Gov.br OIDC · **Integrações:** Google Calendar.
- **Testes:** `pytest` (backend) · `vitest` (frontend).

### Versões (branches)
- **`main`** — versão em produção (Flask + templates Jinja).
- **`v4.5`** — versão estável/homologação (refinamentos sobre a main).
- **`v5.0`** — reescrita moderna: SPA em SvelteKit + API Flask (em evolução).

### Como rodar (desenvolvimento)
```bash
# 1) Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements -r requirements-dev.txt
# Produção: instale com verificação de hash (defesa supply chain):
#   pip install --require-hashes -r requirements.lock
cp .env.example .env        # preencha as variáveis (veja .env.example)
flask db upgrade            # aplica as migrações
python app.py               # ou: gunicorn wsgi:app

# 2) Frontend (apenas na v5.0)
cd frontend
npm install
npm run build               # gera a SPA em static/spa/
# durante o dev: npm run dev
```

### Banco de dados e migrações
O boot da aplicação **não aplica migrações**: ele apenas verifica se o
`alembic_version` do banco está no head de `migrations/versions` e aborta com
instrução acionável se divergir. `SKIP_SCHEMA_CHECK=1` pula a verificação
(somente emergência, ex.: subir uma instância enquanto o banco é corrigido).

```bash
# Instalação limpa (banco vazio)
flask db upgrade                                          # cria o schema completo
python scripts/catalog/sync_objectives_catalog.py         # catálogo de objetivos
python scripts/migrations/elect_super_admin.py --apply    # super admin inicial

# Upgrade de versão (banco existente já migrado)
flask db upgrade
python scripts/catalog/sync_objectives_catalog.py         # se o release mudou catalogs/

# Adoção da baseline (banco legado pré-sprint-5: schema materializado com
# alembic_version órfão — ex. '7c1d9e4a2b3f' — ou sem a tabela; é o estado
# da produção atual). `flask db upgrade` direto FALHA nesses bancos.
cp caminho/do/banco.db caminho/do/banco.db.bak            # backup obrigatório
flask db stamp --purge head                               # adota a baseline (--purge: o stamp órfão impede o stamp comum)
flask db upgrade                                          # no-op de confirmação

# Backfills/one-shots de DADOS (dry-run por default; --apply grava)
python scripts/migrations/encrypt_oauth_tokens.py --apply
python scripts/migrations/backfill_task_assignees.py --apply
python scripts/migrations/backfill_sei_processes.py --apply
```

O schema tem **um produtor só**: `alembic upgrade head`. Nenhum script da app
emite DDL (a exceção é `scripts/seed_fake_data.py`, que cria o schema apenas em
banco descartável e vazio). O runner pré-Alembic foi removido na Sprint 5.4 e
sobrevive no histórico (`git show aa99ff6:scripts/migrations/run_migrations.py`)
caso algum dump antigo precise ser resgatado.

### Variáveis de ambiente
Todas estão documentadas em [`.env.example`](.env.example) (banco, `SECRET_KEY`,
Gov.br OIDC, Google Calendar, rate limiting). Nenhum segredo real vai no repositório.

### Testes
```bash
pytest                      # backend
cd frontend && npm test     # frontend (vitest)
```

---

## 🇬🇧 English

### Overview
Full-stack web app to track public-sector projects: a **Project → Stage → Task**
hierarchy with assignees, comments and attachments, a Kanban board, dashboards,
global search and **Google Calendar** integration. Authentication uses
**Gov.br (OpenID Connect)**.

### Stack
- **Backend:** Python · Flask 3 · SQLAlchemy 2 · Flask-Migrate (Alembic) ·
  MySQL (PyMySQL) · Flask-WTF (CSRF) · Flask-Limiter · `cryptography` · Gunicorn.
- **Frontend (v5.0):** SvelteKit (Svelte 5) + Tailwind, built as an SPA.
- **Auth:** Gov.br OIDC · **Integrations:** Google Calendar.
- **Tests:** `pytest` (backend) · `vitest` (frontend).

### Versions (branches)
- **`main`** — production (Flask + Jinja templates).
- **`v4.5`** — stable / staging (refinements over `main`).
- **`v5.0`** — modern rewrite: SvelteKit SPA + Flask API (work in progress).

### Running locally (development)
```bash
# 1) Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements -r requirements-dev.txt
# Production: install with hash verification (supply-chain defense):
#   pip install --require-hashes -r requirements.lock
cp .env.example .env        # fill in the variables (see .env.example)
flask db upgrade            # apply migrations
python app.py               # or: gunicorn wsgi:app

# 2) Frontend (v5.0 only)
cd frontend
npm install
npm run build               # outputs the SPA to static/spa/
# during dev: npm run dev
```

### Database and migrations
App boot **never applies migrations**: it only checks that the database
`alembic_version` matches the head of `migrations/versions`, aborting with an
actionable message on divergence. `SKIP_SCHEMA_CHECK=1` skips the check
(emergency only).

```bash
# Clean install (empty database)
flask db upgrade                                          # creates the full schema
python scripts/catalog/sync_objectives_catalog.py         # objectives catalog
python scripts/migrations/elect_super_admin.py --apply    # initial super admin

# Version upgrade (already-migrated database)
flask db upgrade

# One-shot DATA backfills (dry-run by default; --apply writes)
python scripts/migrations/encrypt_oauth_tokens.py --apply
python scripts/migrations/backfill_task_assignees.py --apply
python scripts/migrations/backfill_sei_processes.py --apply
```

Schema has **a single producer**: `alembic upgrade head`. No application script
emits DDL (the one exception is `scripts/seed_fake_data.py`, which creates the
schema only on a throwaway, empty database). The pre-Alembic runner was removed
in Sprint 5.4 and lives on in history
(`git show aa99ff6:scripts/migrations/run_migrations.py`) should an old dump
ever need rescuing.

### Environment variables
All documented in [`.env.example`](.env.example) (database, `SECRET_KEY`, Gov.br
OIDC, Google Calendar, rate limiting). No real secrets are stored in the repo.

### Tests
```bash
pytest                      # backend
cd frontend && npm test     # frontend (vitest)
```

---

## Licença / License
Distribuído sob a licença **Apache-2.0** — veja [`LICENSE`](LICENSE).
_Distributed under the **Apache-2.0** license — see [`LICENSE`](LICENSE)._

© 2026 José Hudson de Oliveira Guimarães Junior
