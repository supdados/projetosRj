# projetosRj
código fonte para o gerenciador de projetos do estado do rio de janeiro.

Todos os caminhos deste README são relativos à raiz do repositório `projetosRj/`, e os comandos assumem execução dentro desse diretório.

## Mapa rapido da pasta

Arquivos que ficam na raiz:
- `app.py`, `wsgi.py`: ponto de entrada da aplicação.
- `models.py`, `time_utils.py`: base de dados e utilitários centrais.
- `objective_catalog.py`, `abep_catalog.py`: catálogos canônicos usados pelo backend.
- `README.md`, `requirements`, `requirements-dev.txt`: documentação e dependências.

Pastas principais:
- `routes/`: rotas modulares da aplicação. O arquivo legado foi preservado em `routes/legacy_monolith.py`.
- `scripts/`: utilitários operacionais, agora separados por domínio.
- `docs/`: documentação e ativos de apoio, incluindo capturas em `docs/assets/capturas/`.
- `templates/`, `static/`, `services/`, `tests/`, `migrations/`, `instance/`: camadas funcionais da app.

Detalhamento adicional:
- `docs/estrutura-do-projeto.md`

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
- `projetosRj/scripts/catalog/sync_objectives_catalog.py`

Exemplos:
```bash
python3 scripts/catalog/sync_objectives_catalog.py
python3 scripts/catalog/sync_objectives_catalog.py --dry-run
python3 scripts/catalog/sync_objectives_catalog.py --skip-create-all
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
- `projetosRj/abep_catalog.py`

Migracao para bancos existentes:
- Script dedicado: `python3 scripts/migrations/migrate_add_abep_indicator.py`
- `scripts/migrations/run_migrations.py` tambem inclui esta etapa.
- O startup da app garante automaticamente a coluna quando ela nao existe.

## Organizacao de rotas (modular)

As rotas foram refatoradas para um pacote dedicado:
- `projetosRj/routes/`

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

## Testes automatizados

Dependencias de desenvolvimento:

```bash
./.venv/bin/pip install -r requirements-dev.txt
```

Executar a suite de testes:

```bash
./.venv/bin/python -m pytest -q
```

A cobertura de rotas fica em:
- `tests/routes/route_cases.py`: matriz unica com metodo+URL.
- `tests/routes/test_routes_smoke.py`: smoke test por rota.
- `tests/routes/test_routes_permissions.py`: cenarios de permissao.
- `tests/routes/test_route_inventory.py`: garante 100% das rotas registradas cobertas na matriz.

## Seed fake (dados para visualizacao)

Script:
- `projetosRj/scripts/seed_fake_data.py`

Execucao padrao (reseta e recria o banco atual):

```bash
./scripts/seed_fake_data.py --yes
```

Padrao de volume:
- 100 projetos
- 5 etapas por projeto
- 2 tarefas por projeto
- 4 itens por tarefa
- 1 comentario por item

Exemplo com volume customizado:

```bash
./scripts/seed_fake_data.py \
  --yes \
  --projects 150 \
  --stages-per-project 6 \
  --tasks-per-project 3 \
  --items-per-task 4 \
  --comments-per-item 1
```

## Scripts operacionais

- Criar admin: `python3 scripts/admin/gerar_senha.py`
- Sincronizar catalogo: `python3 scripts/catalog/sync_objectives_catalog.py`
- Rodar migracoes locais: `python3 scripts/migrations/run_migrations.py`
- Garantir campo ABEP: `python3 scripts/migrations/migrate_add_abep_indicator.py`
- Migracao incremental MySQL: `python3 scripts/migrations/migrate_production.py`
- Migracao de unificacao de tarefas: `./scripts/migrations/migration_unificacao_tarefas`
