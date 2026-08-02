# Conhecimentos de animação / micro-interações — índice

Cada conhecimento vive em **um arquivo próprio** em [`docs/`](./docs), para escalar
conforme forem surgindo novos. Este README é só o índice.

| Conhecimento | Arquivo | Resumo |
|---|---|---|
| Micro-interações dos KPIs | [`docs/micro-interacoes-kpis.md`](./docs/micro-interacoes-kpis.md) | Hover dos cartões de KPI do dashboard: princípios, anti hover-loop/flicker, transitions enter/leave, canvas+rAF (FSM), `prefers-reduced-motion`, assets webp, checklist. |
| Transição do topnav (pílula deslizante) | [`docs/transicao-topnav.md`](./docs/transicao-topnav.md) | Indicador único que desliza entre os itens da nav (sliding tab indicator): técnica escolhida, por que NÃO crossfade/flip/View Transitions/grid, easing e armadilhas. |

> **Ao adicionar um novo conhecimento:** crie um `.md` em `docs/` e registre a linha
> correspondente na tabela acima. Não acumular tudo num arquivo só.
