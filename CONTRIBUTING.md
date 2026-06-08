# Contribuindo / Contributing

Obrigado pelo interesse em contribuir com o **ProjetosRJ**! / _Thanks for your
interest in contributing to **ProjetosRJ**!_

---

## 🇧🇷 Português

### Ambiente
Siga o passo a passo de instalação no [`README.md`](README.md) (backend em
Python/Flask e, na `v5.0`, frontend em SvelteKit). Copie `.env.example` para
`.env` e preencha as variáveis. **Nunca** commite segredos, `.env`, bancos
(`*.db`/`*.sql`) ou arquivos de `instance/`.

### Branches
- `main` — produção · `v4.5` — estável/homologação · `v5.0` — reescrita ativa.
- Baseie novas contribuições na branch que você está alterando (em geral `v5.0`).
- Crie uma branch a partir dela: `git checkout -b feat/minha-mudanca`.

### Padrões de código
- **Python:** formate com `black .`; use type hints; funções curtas e com uma
  responsabilidade; evite `except Exception` silencioso.
- **Frontend (v5.0):** rode `npm run check` (svelte-check) sem erros.

### Testes (obrigatório antes do PR)
```bash
pytest                      # backend (use -n auto para paralelo)
cd frontend && npm test     # frontend (vitest)  + npm run check
```
Toda correção de bug deve vir com um teste de regressão; toda função nova, com teste.

### Commits e Pull Requests
- Mensagens no padrão **Conventional Commits**: `feat:`, `fix:`, `docs:`,
  `chore:`, `refactor:`, `test:`…
- Abra um PR descrevendo **o que** mudou e **por quê**, com os testes passando.

### Reportando bugs / sugestões
Abra uma *issue* com passos para reproduzir, comportamento esperado x obtido e,
se possível, ambiente (SO, versões).

---

## 🇬🇧 English

### Environment
Follow the setup steps in [`README.md`](README.md) (Python/Flask backend and, on
`v5.0`, a SvelteKit frontend). Copy `.env.example` to `.env` and fill in the
variables. **Never** commit secrets, `.env`, databases (`*.db`/`*.sql`) or
anything under `instance/`.

### Branches
- `main` — production · `v4.5` — stable/staging · `v5.0` — active rewrite.
- Base new work on the branch you're changing (usually `v5.0`).
- Branch off from it: `git checkout -b feat/my-change`.

### Code style
- **Python:** format with `black .`; use type hints; small, single-purpose
  functions; avoid silent `except Exception`.
- **Frontend (v5.0):** `npm run check` (svelte-check) must pass with no errors.

### Tests (required before a PR)
```bash
pytest                      # backend (use -n auto for parallel)
cd frontend && npm test     # frontend (vitest)  + npm run check
```
Bug fixes must include a regression test; new functions must include tests.

### Commits and Pull Requests
- Use **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`…
- Open a PR describing **what** changed and **why**, with passing tests.

### Reporting bugs / suggestions
Open an *issue* with steps to reproduce, expected vs. actual behavior and, if
possible, your environment (OS, versions).
