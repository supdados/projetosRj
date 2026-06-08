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
cp .env.example .env        # preencha as variáveis (veja .env.example)
flask db upgrade            # aplica as migrações
python app.py               # ou: gunicorn wsgi:app

# 2) Frontend (apenas na v5.0)
cd frontend
npm install
npm run build               # gera a SPA em static/spa/
# durante o dev: npm run dev
```

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
cp .env.example .env        # fill in the variables (see .env.example)
flask db upgrade            # apply migrations
python app.py               # or: gunicorn wsgi:app

# 2) Frontend (v5.0 only)
cd frontend
npm install
npm run build               # outputs the SPA to static/spa/
# during dev: npm run dev
```

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
