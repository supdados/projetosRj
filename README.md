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
A autenticação é local (usuário e senha), com login federado **Gov.br (OpenID
Connect)** opcional.

### Stack
- **Backend:** Python 3.12+ · Flask 3 · SQLAlchemy 2 · Flask-Migrate (Alembic) ·
  MySQL 8 em produção / SQLite em dev · Flask-WTF (CSRF) · Flask-Limiter ·
  `cryptography` · Gunicorn.
- **Frontend:** SvelteKit (Svelte 5) + Tailwind, compilado como SPA (Node 22.12+).
- **Auth:** login local (usuário e senha) e, opcionalmente, Gov.br OIDC.
- **Integrações opcionais:** Google Calendar, IBM watsonx.ai, SIORG-RJ, chatbot.
- **Testes:** `pytest` (backend) · `vitest` (frontend).

### Versões (branches)
- **`main`** — única branch do projeto; contém a v5.0 (SPA em SvelteKit + API Flask).
- As versões anteriores ficam preservadas nas tags `legado/main-2026-10-14`
  (antiga `main`, Flask + Jinja), `legado/v4.5` e `legado/v5.0-pre-main`.

### Rodando pela primeira vez (dev local)
Pré-requisitos: **Python 3.12+**, **Node 22.12+** (com npm) e git. Não precisa de
MySQL, Docker nem de nenhuma conta externa: o dev local usa SQLite e login com
usuário e senha.

```bash
git clone https://github.com/supdados/projetosRj.git && cd projetosRj
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements -r requirements-dev.txt
python scripts/dev/setup_local.py                    # .env, banco, admin e frontend
python app.py
```

Abra **http://localhost:5002/login** e entre com o usuário e a senha de admin
que o `setup_local.py` pediu. O script:
- cria o `.env` com `SECRET_KEY` aleatória, cookie aceito em `http://` e **todas
  as integrações desligadas** (nunca sobrescreve um `.env` existente);
- aplica as migrações num SQLite em `instance/projetosrj.db`;
- sincroniza o catálogo de objetivos e cria o primeiro administrador;
- roda `npm ci` + `npm run build` (a SPA vai para `static/spa/`).

Pode rodar de novo sem medo: o que já existe é mantido. Para o frontend com
recarga automática durante o desenvolvimento: `cd frontend && npm run dev`.

Outro administrador depois: `python scripts/admin/gerar_senha.py`.
Dados fictícios para demonstração (apaga o SQLite atual):
`python scripts/seed_fake_data.py` (usuário `admin_seed` / `seed123`).

### Integrações opcionais
Cada uma liga e desliga por uma variável no `.env`. Ligada sem credencial, ela
fica desligada e o boot avisa no log. Ao subir, o app loga uma linha com o
estado de todas, ex.: `Integrações: Gov.br=OFF · Google Calendar=OFF · ...`.

| Integração | Liga/desliga | Precisa de |
|---|---|---|
| Login Gov.br | `GOVBR_OIDC_ENABLED` | cliente OIDC cadastrado no Gov.br |
| Google Calendar | `GOOGLE_CALENDAR_ENABLED` | `config/client_secret.json` (OAuth Google) |
| Sugestão de coleções por IA | `WATSONX_ENABLED` | `WATSONX_API_KEY` e `WATSONX_PROJECT_ID` |
| SIORG-RJ | `SIORG_ENABLED` | `SIORG_API_KEY` |
| Chatbot | `CHATBOT_ENABLED` | `CHATBOT_BASE_URL` |
| Convites por projeto | `CONVITES_HABILITADOS` | — |

Em `WATSONX_ENABLED` e `SIORG_ENABLED`, deixar vazio liga a integração sozinha
quando a credencial existe.

### Produção
MySQL 8 (`DATABASE_URL` ou `DB_*` no `.env`) servido por gunicorn:
```bash
pip install --require-hashes -r requirements.lock    # verificação de hash (supply chain)
(cd frontend && npm ci && npm run build)
flask db upgrade
gunicorn wsgi:app
```
Mantenha `SESSION_COOKIE_SECURE=1` e `FLASK_DEBUG=0`.

### Banco de dados e migrações
O boot da aplicação **não aplica migrações**: ele apenas verifica se o
`alembic_version` do banco está no head de `migrations/versions` e aborta com
instrução acionável se divergir. `SKIP_SCHEMA_CHECK=1` pula a verificação
(somente emergência, ex.: subir uma instância enquanto o banco é corrigido).

```bash
# Instalação limpa (banco vazio)
flask db upgrade                                          # cria o schema completo
python scripts/catalog/sync_objectives_catalog.py         # catálogo de objetivos
python scripts/admin/gerar_senha.py                       # primeiro admin (vira o super admin)
# (scripts/migrations/elect_super_admin.py --apply só elege entre admins já existentes)

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
Todas estão documentadas em [`.env.example`](.env.example), separadas em
mínimo para rodar, integrações opcionais e produção. Nenhum segredo real vai no
repositório.

### Testes
```bash
pytest -n auto              # backend (em paralelo)
cd frontend && npm test     # frontend (vitest)
```

---

## 🇬🇧 English

### Overview
Full-stack web app to track public-sector projects: a **Project → Stage → Task**
hierarchy with assignees, comments and attachments, a Kanban board, dashboards,
global search and **Google Calendar** integration. Authentication is local
(username and password), with optional **Gov.br (OpenID Connect)** federated login.

### Stack
- **Backend:** Python 3.12+ · Flask 3 · SQLAlchemy 2 · Flask-Migrate (Alembic) ·
  MySQL 8 in production / SQLite in dev · Flask-WTF (CSRF) · Flask-Limiter ·
  `cryptography` · Gunicorn.
- **Frontend:** SvelteKit (Svelte 5) + Tailwind, built as an SPA (Node 22.12+).
- **Auth:** local login (username and password) and, optionally, Gov.br OIDC.
- **Optional integrations:** Google Calendar, IBM watsonx.ai, SIORG-RJ, chatbot.
- **Tests:** `pytest` (backend) · `vitest` (frontend).

### Versions (branches)
- **`main`** — the project's only branch; contains v5.0 (SvelteKit SPA + Flask API).
- Earlier versions are preserved in the tags `legado/main-2026-10-14`
  (former `main`, Flask + Jinja), `legado/v4.5` and `legado/v5.0-pre-main`.

### First run (local development)
Requirements: **Python 3.12+**, **Node 22.12+** (with npm) and git. No MySQL,
Docker or external accounts needed: local dev uses SQLite and username/password
login.

```bash
git clone https://github.com/supdados/projetosRj.git && cd projetosRj
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements -r requirements-dev.txt
python scripts/dev/setup_local.py                    # .env, database, admin, frontend
python app.py
```

Open **http://localhost:5002/login** and sign in with the admin username and
password that `setup_local.py` asked for. The script writes `.env` (random
`SECRET_KEY`, cookie allowed over `http://`, **all integrations off**; never
overwrites an existing `.env`), migrates a SQLite database in
`instance/projetosrj.db`, syncs the objectives catalog, creates the first admin
and runs `npm ci` + `npm run build`. It is safe to run again.

Another admin later: `python scripts/admin/gerar_senha.py`. Demo data (wipes the
current SQLite database): `python scripts/seed_fake_data.py` (user `admin_seed` /
`seed123`).

### Optional integrations
Each one is switched on/off by a `.env` variable. Switched on without
credentials, it stays off and the boot log warns about it. On startup the app
logs one line with every integration's state, e.g.
`Integrações: Gov.br=OFF · Google Calendar=OFF · ...`.

| Integration | On/off switch | Requires |
|---|---|---|
| Gov.br login | `GOVBR_OIDC_ENABLED` | OIDC client registered with Gov.br |
| Google Calendar | `GOOGLE_CALENDAR_ENABLED` | `config/client_secret.json` (Google OAuth) |
| AI collection suggestions | `WATSONX_ENABLED` | `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` |
| SIORG-RJ | `SIORG_ENABLED` | `SIORG_API_KEY` |
| Chatbot | `CHATBOT_ENABLED` | `CHATBOT_BASE_URL` |
| Per-project invitations | `CONVITES_HABILITADOS` | — |

For `WATSONX_ENABLED` and `SIORG_ENABLED`, leaving the value empty turns the
integration on automatically when its credential is present.

### Production
MySQL 8 (`DATABASE_URL` or `DB_*` in `.env`) served by gunicorn:
```bash
pip install --require-hashes -r requirements.lock    # hash-verified install
(cd frontend && npm ci && npm run build)
flask db upgrade
gunicorn wsgi:app
```
Keep `SESSION_COOKIE_SECURE=1` and `FLASK_DEBUG=0`.

### Database and migrations
App boot **never applies migrations**: it only checks that the database
`alembic_version` matches the head of `migrations/versions`, aborting with an
actionable message on divergence. `SKIP_SCHEMA_CHECK=1` skips the check
(emergency only).

```bash
# Clean install (empty database)
flask db upgrade                                          # creates the full schema
python scripts/catalog/sync_objectives_catalog.py         # objectives catalog
python scripts/admin/gerar_senha.py                       # first admin (becomes super admin)
# (scripts/migrations/elect_super_admin.py --apply only elects among existing admins)

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
All documented in [`.env.example`](.env.example), grouped into minimum to run,
optional integrations and production. No real secrets are stored in the repo.

### Tests
```bash
pytest -n auto              # backend (parallel)
cd frontend && npm test     # frontend (vitest)
```

---

## Licença / License
Distribuído sob a licença **Apache-2.0** — veja [`LICENSE`](LICENSE).
_Distributed under the **Apache-2.0** license — see [`LICENSE`](LICENSE)._

© 2026 José Hudson de Oliveira Guimarães Junior
