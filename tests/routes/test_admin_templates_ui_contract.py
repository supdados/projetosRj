# NOTA (corte Grupo B): a tela /admin/templates (lista + form de criar/editar)
# virou SPA, servida via catch-all em routes/spa.py. O CRUD/listagem vive em
# /api/admin/templates* (coberto por test_api_admin_templates_contract.py).
#
# Os antigos contratos de UI deste arquivo afirmavam o ciclo de vida do
# template_form.js e do template-form.css (assets vanilla da era Jinja). Esses
# assets foram REMOVIDOS no corte (static/js/admin/template_form.js e
# static/css/admin/template-form.css), portanto os contratos ficaram obsoletos
# e foram apagados. O comportamento equivalente agora vive no componente Svelte
# da rota /admin/templates (frontend/), com cobertura no front (npm run check /
# vitest).
