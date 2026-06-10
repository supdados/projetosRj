<script lang="ts">
	/**
	 * Card de tarefa no Kanban — arrastável e clicável.
	 *
	 * Anatomia (referência de design do board, jun/2026): chips de prioridade e
	 * tipo no topo, título da tarefa, link azul para o projeto, e rodapé com
	 * responsável + contadores de comentários (balão) e anexos (clipe).
	 *
	 * Interações:
	 *   - CLIQUE em qualquer área do card abre o drawer de detalhes (o link do
	 *     projeto e os botões internos interrompem a propagação);
	 *   - Enter/Espaço no card focado também abre o drawer; setas ←/→ movem entre
	 *     colunas (tratadas pelo board via `onkeydown`);
	 *   - o botão Excluir só aparece no hover/focus (canto superior direito).
	 *
	 * ESTADO CANÔNICO NA STORE: este componente é puramente derivado do `card`
	 * recebido por prop. O atributo `data-can-finalize` exposto aqui é só uma
	 * dica para inspeção/teste — a regra de DnD usa o objeto `card` da store
	 * (`canItemMoveToStatus`), nunca o DOM.
	 *
	 * O drag em si é coordenado pelo `KanbanBoard` (HTML5 nativo); aqui só
	 * expomos `draggable` e propagamos os eventos `dragstart`/`dragend`.
	 */
	import { getContext } from 'svelte';
	import type { BoardCard } from '$lib/types/board';

	/**
	 * Abertura do drawer: fornecida via contexto pela página, para não exigir
	 * prop drilling por KanbanBoard/KanbanColumn. Ausente quando o board é
	 * usado sem drawer.
	 */
	const openTaskDrawer = getContext<((taskId: number) => void) | undefined>('openTaskDrawer');

	/**
	 * Exclusão de card: fornecida via contexto pela página. O card coordena o
	 * MINI-CONFIRM INLINE local; a página executa a chamada e remove o card da
	 * store. Abrir um confirm fecha os demais via `closeOtherDeletes`.
	 */
	const deleteTask =
		getContext<((taskId: number) => Promise<boolean>) | undefined>('deleteTaskCard');
	const registerDeleteConfirm =
		getContext<((close: () => void) => void) | undefined>('registerDeleteConfirm');

	interface Props {
		card: BoardCard;
		/** Indica que este card é o que está sendo arrastado (feedback visual). */
		dragging?: boolean;
		/** Card recém-aterrissado: roda a animação `is-drop-settling` (0.28s). */
		settled?: boolean;
		/** Rótulo da coluna atual (para o aria-label do card focável). */
		columnLabel?: string;
		/** Posição do card na coluna (1-based) para `aria-posinset`. */
		position?: number;
		/** Total de cards na coluna para `aria-setsize`. */
		setSize?: number;
		ondragstart?: (event: DragEvent) => void;
		ondragend?: (event: DragEvent) => void;
		/** Teclado no card focado: setas movem entre colunas (alternativa ao DnD). */
		onkeydown?: (event: KeyboardEvent) => void;
	}

	let {
		card,
		dragging = false,
		settled = false,
		columnLabel = '',
		position,
		setSize,
		ondragstart,
		ondragend,
		onkeydown
	}: Props = $props();

	/** Rótulos PT das prioridades (espelham `prioridade_labels` do hub Jinja). */
	const PRIORIDADE_LABEL: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};

	/** Rótulos PT dos tipos de pedido (espelham `tipo_labels` do hub Jinja). */
	const TIPO_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida',
		outros: 'Outros',
		implementacao: 'Implementação'
	};

	const prioridadeLabel = $derived(
		card.prioridade ? (PRIORIDADE_LABEL[card.prioridade] ?? card.prioridade) : null
	);
	/** Classe da variante de cor do chip (cai em "media" p/ valor desconhecido). */
	const prioridadeChipClass = $derived(
		card.prioridade && card.prioridade in PRIORIDADE_LABEL
			? `kc-chip--${card.prioridade}`
			: 'kc-chip--media'
	);
	const tipoLabel = $derived(
		card.tipo_pedido ? (TIPO_LABEL[card.tipo_pedido] ?? card.tipo_pedido) : null
	);

	// MINI-CONFIRM INLINE de exclusão (paridade com .task-items-kanban-delete-confirm).
	let confirmingDelete = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);

	function openDeleteConfirm(): void {
		// Abrir um confirm fecha os demais (paridade board-dnd.js).
		registerDeleteConfirm?.(() => {
			confirmingDelete = false;
		});
		confirmingDelete = true;
		deleteError = null;
	}
	function cancelDeleteConfirm(): void {
		confirmingDelete = false;
	}
	async function confirmDelete(): Promise<void> {
		if (!deleteTask) return;
		deleting = true;
		deleteError = null;
		const ok = await deleteTask(card.id);
		if (!ok) {
			deleteError = 'Não foi possível excluir a tarefa.';
			deleting = false;
		}
		// Em sucesso o card é removido da store (some do DOM); nada a fazer aqui.
	}

	/**
	 * Bloqueia o início do drag quando o gesto nasce em um controle interativo
	 * (botão Excluir, link do projeto ou o mini-confirm). Sem isso, arrastar a
	 * partir de um botão moveria o card por engano.
	 */
	function handleDragStart(event: DragEvent): void {
		const target = event.target as HTMLElement | null;
		if (target?.closest('button, a, input, textarea, select, [role="alertdialog"]')) {
			event.preventDefault();
			return;
		}
		suppressClick = true;
		ondragstart?.(event);
	}

	/**
	 * Guarda contra o clique fantasma pós-drag: alguns browsers disparam `click`
	 * no card após um drag muito curto (mousedown/mouseup no mesmo elemento), o
	 * que abriria o drawer sem intenção. O flag arma no dragstart e desarma um
	 * tick depois do dragend.
	 */
	let suppressClick = false;

	function handleDragEnd(event: DragEvent): void {
		setTimeout(() => {
			suppressClick = false;
		}, 0);
		ondragend?.(event);
	}

	/** Clique no corpo do card abre o drawer (controles internos não propagam). */
	function handleCardClick(event: MouseEvent): void {
		if (suppressClick || !openTaskDrawer) return;
		const target = event.target as HTMLElement | null;
		if (target?.closest('button, a, [role="alertdialog"]')) return;
		openTaskDrawer(card.id);
	}

	/** Enter/Espaço abre o drawer; demais teclas vão para o board (setas movem). */
	function handleKeydown(event: KeyboardEvent): void {
		if ((event.key === 'Enter' || event.key === ' ') && openTaskDrawer) {
			event.preventDefault();
			openTaskDrawer(card.id);
			return;
		}
		onkeydown?.(event);
	}
</script>

<!--
	Card de tarefa — superfície branca com sombra suave; no hover o card "sobe"
	1px e a sombra aprofunda (microinteração de affordance de arrasto/clique).
	`is-dragging` colapsa o card-fonte (opacity:0, height:0) enquanto o
	placeholder de inserção mostra o destino. `is-drop-settling` roda a animação
	de assentamento pós-drop. Focus-visible com ring triplo acessível.
-->
<div
	class="kanban-card group relative flex cursor-pointer flex-col gap-2 rounded-[10px] border border-border-subtle bg-surface px-3 pb-2.5 pt-2.5 shadow-[0_1px_3px_rgba(18,56,91,0.07),0_4px_12px_rgba(18,56,91,0.05)] outline-none transition-[transform,box-shadow,border-color,background-color] duration-fast hover:-translate-y-px hover:border-border-strong hover:shadow-[0_2px_6px_rgba(16,53,87,0.08),0_10px_22px_rgba(16,53,87,0.12)] focus-visible:border-primary-500 focus-visible:shadow-[0_0_0_3px_rgba(31,92,168,0.16),0_10px_22px_rgba(16,53,87,0.12)] active:cursor-grabbing {dragging
		? 'is-dragging'
		: ''} {settled ? 'is-drop-settling' : ''}"
	draggable="true"
	tabindex="0"
	data-item-id={card.id}
	data-can-finalize={card.permissions.can_finalize}
	role="button"
	aria-roledescription="Tarefa movível"
	aria-label={`${card.descricao}${columnLabel ? `, em ${columnLabel}` : ''}${
		position && setSize ? ` (${position} de ${setSize})` : ''
	}. Enter abre os detalhes; setas esquerda e direita movem entre colunas.`}
	ondragstart={handleDragStart}
	ondragend={handleDragEnd}
	onclick={handleCardClick}
	onkeydown={handleKeydown}
>
	{#if prioridadeLabel || tipoLabel}
		<div class="flex flex-wrap items-center gap-1.5 pr-7">
			{#if prioridadeLabel}
				<span class="kc-chip {prioridadeChipClass}">{prioridadeLabel}</span>
			{/if}
			{#if tipoLabel}
				<span class="kc-chip kc-chip--tipo">{tipoLabel}</span>
			{/if}
		</div>
	{/if}

	<p class="m-0 line-clamp-3 break-words text-md font-semibold leading-snug text-text-primary">
		{card.descricao}
	</p>

	{#if card.project_id && card.project_titulo}
		<!-- Link do projeto: navega para a página do projeto sem abrir o drawer
		     (o handler de clique do card ignora cliques originados em <a>). -->
		<a
			href={`/projetos/${card.project_id}`}
			draggable="false"
			class="-mt-1 w-fit max-w-full truncate rounded-sm text-sm font-semibold text-primary-600 transition-colors duration-fast hover:text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			title={card.project_titulo}
		>
			{card.project_titulo}
		</a>
	{/if}

	<div class="mt-auto flex items-center justify-between gap-2 pt-0.5">
		{#if card.responsavel}
			<span class="truncate text-xs text-text-secondary" title={`Responsável: ${card.responsavel}`}
				>{card.responsavel}</span
			>
		{:else}
			<span class="truncate text-xs italic text-text-muted">Responsável não informado</span>
		{/if}

		<!-- Contadores: apagados quando zerados, destacados quando há conteúdo. -->
		<span class="flex shrink-0 items-center gap-2.5 text-xs tabular-nums">
			<span
				class="inline-flex items-center gap-1 {card.comments_count > 0
					? 'font-semibold text-text-secondary'
					: 'text-text-muted opacity-60'}"
				title={card.comments_count === 1 ? '1 comentário' : `${card.comments_count} comentários`}
			>
				<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5Z" />
				</svg>
				{card.comments_count}
			</span>
			<span
				class="inline-flex items-center gap-1 {card.anexos_count > 0
					? 'font-semibold text-text-secondary'
					: 'text-text-muted opacity-60'}"
				title={card.anexos_count === 1 ? '1 anexo' : `${card.anexos_count} anexos`}
			>
				<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
				</svg>
				{#if card.anexos_count > 0}{card.anexos_count}{/if}
			</span>
		</span>
	</div>

	{#if deleteTask && !confirmingDelete}
		<!-- Botão excluir revelado no hover/focus do card, canto superior direito. -->
		<button
			type="button"
			onclick={openDeleteConfirm}
			aria-label="Excluir tarefa"
			title="Excluir tarefa"
			class="kc-delete-btn absolute right-1.5 top-1.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border bg-surface text-xs text-danger opacity-0 shadow-sm transition-[opacity,background-color,border-color] duration-fast focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger group-hover:opacity-100 group-focus-within:opacity-100"
		>
			<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
				<path d="M10 11v6M14 11v6" />
			</svg>
		</button>
	{/if}

	{#if confirmingDelete}
		<!-- Mini-confirm inline no card (animação de entrada). -->
		<div
			role="alertdialog"
			aria-label="Confirmar exclusão da tarefa"
			class="kanban-delete-confirm mt-[0.12rem] flex flex-col gap-2 rounded-[9px] border px-[0.46rem] py-[0.42rem]"
		>
			<p class="m-0 text-xs font-semibold text-danger">Excluir esta tarefa?</p>
			{#if deleteError}
				<p role="alert" class="text-xs text-danger">{deleteError}</p>
			{/if}
			<div class="flex justify-end gap-[0.24rem]">
				<button
					type="button"
					onclick={cancelDeleteConfirm}
					disabled={deleting}
					class="h-[26px] rounded-[7px] border border-border-subtle bg-surface px-[0.44rem] text-2xs font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={() => void confirmDelete()}
					disabled={deleting}
					class="kc-confirm-delete-btn h-[26px] rounded-[7px] border px-[0.44rem] text-2xs font-semibold text-danger transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
				>
					{deleting ? 'Excluindo…' : 'Excluir'}
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	/*
	 * Chips do topo do card. As cores de prioridade usam as MESMAS vars dos
	 * badges do hub (`--ds-color-priority-*`, dark-safe) via color-mix — o
	 * Tailwind 3 NÃO gera modificadores de opacidade (`bg-x/10`) para cores
	 * definidas como var() sem <alpha-value>, então a tinta vive aqui.
	 */
	.kc-chip {
		display: inline-flex;
		align-items: center;
		border-radius: 6px;
		border: 1px solid transparent;
		padding: 0.1rem 0.45rem;
		font-size: 0.6875rem;
		font-weight: 600;
		line-height: 1.35;
		white-space: nowrap;
	}
	.kc-chip--baixa {
		color: var(--ds-color-priority-baixa);
		border-color: color-mix(in srgb, var(--ds-color-priority-baixa) 38%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-priority-baixa) 10%, transparent);
	}
	.kc-chip--media {
		color: var(--ds-color-priority-media);
		border-color: color-mix(in srgb, var(--ds-color-priority-media) 38%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-priority-media) 10%, transparent);
	}
	.kc-chip--alta {
		color: var(--ds-color-priority-alta);
		border-color: color-mix(in srgb, var(--ds-color-priority-alta) 38%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-priority-alta) 10%, transparent);
	}
	.kc-chip--urgente {
		color: var(--ds-color-priority-urgente);
		border-color: color-mix(in srgb, var(--ds-color-priority-urgente) 38%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-priority-urgente) 10%, transparent);
	}
	/* Tipo de pedido: tinta azul-clara da marca (referência: chip "Melhoria"). */
	.kc-chip--tipo {
		color: var(--ds-color-primary-700);
		border-color: color-mix(in srgb, var(--ds-color-primary-500) 32%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-primary-500) 8%, transparent);
	}

	/*
	 * Tons de perigo do excluir/confirm: o Tailwind 3 não gera `bg-danger/10`
	 * (cor via var sem <alpha-value>) — as tintas vivem aqui via color-mix.
	 */
	.kc-delete-btn {
		border-color: color-mix(in srgb, var(--ds-color-danger-600) 38%, transparent);
	}
	.kc-delete-btn:hover {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 10%, transparent);
	}
	.kanban-delete-confirm {
		border-color: color-mix(in srgb, var(--ds-color-danger-600) 38%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 5%, transparent);
	}
	.kc-confirm-delete-btn {
		border-color: color-mix(in srgb, var(--ds-color-danger-600) 48%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 10%, transparent);
	}
	.kc-confirm-delete-btn:hover:not(:disabled) {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 18%, transparent);
	}

	/*
	 * `.is-dragging`: o card-fonte colapsa enquanto arrastado — opacity:0 +
	 * altura zero + sem borda/sombra. Mantém o elemento no fluxo (a board usa
	 * data-item-id para calcular o índice de drop).
	 */
	.is-dragging {
		opacity: 0;
		height: 0;
		min-height: 0;
		margin: 0;
		padding-top: 0;
		padding-bottom: 0;
		border-width: 0;
		box-shadow: none;
		transform: none;
		cursor: grabbing;
		overflow: hidden;
		pointer-events: none;
	}

	/* Animação de assentamento pós-drop (`td-kanban-drop-settle`, 0.28s ease). */
	@keyframes td-kanban-drop-settle {
		0% {
			transform: scale(1.03) translateY(-2px);
			box-shadow: 0 12px 28px rgba(13, 48, 80, 0.18);
		}
		50% {
			transform: scale(0.99) translateY(1px);
		}
		100% {
			transform: scale(1) translateY(0);
			box-shadow: 0 1px 3px rgba(18, 56, 91, 0.07);
		}
	}
	:global(.kanban-card.is-drop-settling) {
		animation: td-kanban-drop-settle 0.28s ease;
	}

	/* Entrada do mini-confirm de exclusão (`td-kanban-delete-confirm-in`). */
	@keyframes td-kanban-delete-confirm-in {
		from {
			opacity: 0;
			transform: translateY(-3px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	.kanban-delete-confirm {
		animation: td-kanban-delete-confirm-in 0.16s ease;
	}

	@media (prefers-reduced-motion: reduce) {
		:global(.kanban-card.is-drop-settling) {
			animation: none;
		}
		.kanban-delete-confirm {
			animation: none;
		}
		.kanban-card,
		.kanban-card:hover {
			transform: none;
		}
	}
</style>
