# projetosRj
código fonte para o gerenciador de projetos do estado do rio de janeiro.

## Catalogo de Objetivos, Resultados e Indicadores

Este projeto agora usa um **catalogo canonico em codigo** para:
- Objetivo
- Resultado esperado
- Indicadores

### O que mudou

1. As opcoes do formulario nao dependem mais de dados previamente inseridos no banco.
2. As APIs de cascata usam o catalogo fixo:
- `GET /api/resultados/<objetivo_id>`
- `GET /api/indicadores/<resultado_id>`
3. O backend valida combinacao de objetivo/resultado/indicadores antes de salvar.
4. O banco continua com as tabelas relacionais, mas agora elas sao sincronizadas automaticamente com o catalogo.

### Sincronizacao automatica

Na inicializacao da aplicacao (`app.py`):
1. `db.create_all()` cria tabelas faltantes.
2. `sync_goal_catalog_to_db()` faz upsert no catalogo (idempotente).

Tambem existe sincronizacao na rota operacional:
- `GET /setup_db`

### Script para producao (MySQL) e local (SQLite)

Arquivo:
- `/projetosRj/sync_objectives_catalog.py`

Exemplos:
```bash
python3 sync_objectives_catalog.py
python3 sync_objectives_catalog.py --dry-run
python3 sync_objectives_catalog.py --skip-create-all
```

Comportamento:
1. Usa o banco definido pelas variaveis de ambiente da app.
2. Cria tabelas faltantes (a menos que `--skip-create-all`).
3. Faz upsert do catalogo em `objetivo`, `resultado_esperado` e `indicador`.
4. Nao remove registros extras existentes.

### Ordem de configuracao de banco

Definida em `app.py`:
1. `DATABASE_URL` (prioridade maxima)
2. MySQL via `DB_USER`, `DB_PASSWORD`, `DB_NAME`
3. SQLite local em `instance/projetosrj.db` (padrao local)

## Novo campo: Indicadores ABEP

Foi adicionado o campo `project.abep_indicator`:
1. Aparece no formulario de criacao (`project_add_form`) com dropdown e busca por numero/titulo.
2. Aparece no formulario de edicao (`project_form`) com dropdown e busca por numero/titulo.
3. Aparece na tela de detalhe do projeto (inclusive edicao inline).
4. Aparece como filtro na listagem de todos os projetos.

Catalogo fixo:
- `/projetosRj/abep_catalog.py`

Migracao para bancos existentes:
- Script dedicado: `python3 migrate_add_abep_indicator.py`
- `run_migrations.py` tambem inclui esta etapa.
- O startup da app garante automaticamente a coluna quando ela nao existe.

## Organizacao de rotas (modular)

As rotas foram refatoradas para um pacote dedicado:
- `/projetosRj/routes/`

Estrutura principal:
- `routes/blueprint.py`: blueprint unico `main_bp` (mantem endpoints `main.*`).
- `routes/decorators.py`: `login_required`, `admin_required`.
- `routes/shared.py`: helpers/constantes compartilhadas e `inject_current_year`.
- `routes/auth.py`: login/logout/home/senha.
- `routes/dashboard.py`: dashboard.
- `routes/search.py`: busca global (`/api/busca-global`, `/busca`) e helpers de busca.
- `routes/projects.py`: projetos e historico de projeto.
- `routes/etapas.py`: etapas e operacoes relacionadas.
- `routes/tasks.py`: tarefas, itens e comentarios.
- `routes/admin_users.py`: administracao de usuarios.
- `routes/admin_templates.py`: modelos de etapas.
- `routes/api.py`: APIs auxiliares (objetivo/resultado/indicador/templates/projetos usuario).
- `routes/maintenance.py`: rotas operacionais (`/setup_db`, favicon).

Ponto de entrada:
- `routes/__init__.py` exporta `main_bp` e `inject_current_year` e importa os modulos para registrar as rotas.

Compatibilidade:
- URLs e endpoint names foram preservados.
- `url_for('main.*')` continua igual.
