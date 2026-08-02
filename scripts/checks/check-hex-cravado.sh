#!/usr/bin/env bash
# Grep-gate contra hex/rgba cravado no frontend (plano-regua-de-cor.md §6 commit 9).
# Cor deve vir da régua via var(--ds-color-*); exceções: app.css (define a régua),
# micro/ (ilustração com literais próprios), AdminMenuIcon (duotone hover com paleta
# ilustrativa própria), #B45A45 (disco de não lidas do sino, AppTopnav), confetti,
# avatarPalette, `#each` (sintaxe Svelte, não hex), brand Google e paleta categórica
# de órgão (§7.11/§7.12).
#
# FERRAMENTA MANUAL DE AUDITORIA — não é gate de CI. Hoje acusa 93 achados que são
# dívida conhecida (pré-existente ao script). Só ligar em CI (package.json/workflow)
# depois que a dívida for zerada ou os achados restantes forem allowlistados aqui.
#
# Uso: scripts/checks/check-hex-cravado.sh
# Sai 1 (imprimindo os achados) se houver hex/rgba fora da allowlist; 0 se limpo.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

MATCHES="$(grep -rnE '#[0-9a-fA-F]{3,8}\b|rgba?\(|\b(bg|text|border|ring|fill|stroke|divide|outline|shadow|from|via|to)-[a-zA-Z0-9-]+/[0-9]+\b' frontend/src --include='*.svelte' --include='*.ts' --include='*.css' \
	| grep -v 'app.css\|/micro/\|AdminMenuIcon.svelte\|#B45A45\|confetti\|avatarPalette\|#each\|0f9d58\|4285f4\|OrgaoTreeNode.svelte' \
	|| true)"

if [ -n "$MATCHES" ]; then
	echo "Hex/rgba cravado fora da allowlist:"
	echo "$MATCHES"
	exit 1
fi

exit 0
