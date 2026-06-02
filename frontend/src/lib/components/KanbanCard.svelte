<script lang="ts">
	/**
	 * Card de tarefa no Kanban (Fase 5b-1) — SOMENTE LEITURA + arrastável.
	 *
	 * Mostra descrição, responsável, prioridade/tipo (via Badge) e o contexto de
	 * projeto/etapa. NÃO edita, não abre drawer, não tem ações (isso é 5b-2).
	 *
	 * ESTADO CANÔNICO NA STORE: este componente é puramente derivado do `card`
	 * recebido por prop. O atributo `data-can-finalize` exposto aqui é só uma
	 * dica para inspeção/teste — NÃO é fonte de estado; a regra de DnD usa o
	 * objeto `card` da store (`canItemMoveToStatus`), nunca o DOM.
	 *
	 * O drag em si é coordenado pelo `KanbanBoard` (HTML5 nativo); aqui só
	 * expomos `draggable` e propagamos os eventos `dragstart`/`dragend`.
	 */
	import { getContext } from 'svelte';
	import Badge from '$lib/components/Badge.svelte';
	import type { BoardCard } from '$lib/types/board';

	/**
	 * Abertura do drawer (Fase 5b-2): fornecida via contexto pela página, para não
	 * exigir prop drilling por KanbanBoard/KanbanColumn. Ausente quando o board é
	 * usado sem drawer.
	 */
	const openTaskDrawer = getContext<((taskId: number) => void) | undefined>('openTaskDrawer');

	/**
	 * Exclusão de card (Fase 5b-3): fornecida via contexto pela página. O card
	 * coordena o MINI-CONFIRM INLINE local; a página executa a chamada e remove o
	 * card da store (paridade com `deleteKanbanItem`). Abrir um confirm fecha os
	 * demais via o sinal `closeOtherDeletes` (também por contexto).
	 */
	const deleteTask =
		getContext<((taskId: number) => Promise<boolean>) | undefined>('deleteTaskCard');
	const registerDeleteConfirm =
		getContext<((close: () => void) => void) | undefined>('registerDeleteConfirm');

	type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

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
	const PRIORIDADE_TONE: Record<string, BadgeTone> = {
		baixa: 'neutral',
		media: 'info',
		alta: 'warning',
		urgente: 'danger'
	};

	/** Rótulos PT dos tipos de pedido (espelham `tipo_labels` do hub Jinja). */
	const TIPO_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida',
		outros: 'Outros',
		implementacao: 'Implementação'
	};

	function prioridadeLabel(value: string | null): string | null {
		if (!value) return null;
		return PRIORIDADE_LABEL[value] ?? value;
	}
	function prioridadeTone(value: string | null): BadgeTone {
		if (!value) return 'neutral';
		return PRIORIDADE_TONE[value] ?? 'neutral';
	}
	function tipoLabel(value: string | null): string | null {
		if (!value) return null;
		return TIPO_LABEL[value] ?? value;
	}

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
	 * (botão Excluir/Abrir ou o mini-confirm) — paridade com `board-dnd.js`, que
	 * dá `preventDefault()` no dragstart originado nesses alvos. Sem isso, arrastar
	 * a partir de um botão moveria o card por engano.
	 */
	function handleDragStart(event: DragEvent): void {
		const target = event.target as HTMLElement | null;
		if (target?.closest('button, a, input, textarea, select, [role="alertdialog"]')) {
			event.preventDefault();
			return;
		}
		ondragstart?.(event);
	}
</script>

<!--
	Card de tarefa — fidelidade a static/css/tasks/detail/kanban.css
	(`.task-items-kanban-card`): radius 10px, sombra 0 6px 16px, hover sobe para
	0 10px 22px + borda mais clara, focus-visible com ring triplo, transição
	0.16s ease (transform/box-shadow/border/bg). `cursor: grab` (e `grabbing` no
	active). `is-dragging` colapsa o card (opacity:0, height:0). `is-drop-settling`
	roda a animação de assentamento (`td-kanban-drop-settle` 0.28s ease). O botão
	de excluir só aparece no hover/focus (paridade com `.task-items-kanban-delete-btn`).
-->
<div
	class="kanban-card group flex cursor-grab flex-col gap-[0.52rem] rounded-[10px] border border-border-subtle bg-surface px-[0.6rem] pb-[0.6rem] pt-[0.56rem] shadow-[0_6px_16px_rgba(18,56,91,0.08)] outline-none transition-[transform,box-shadow,border-color,background-color] duration-fast hover:border-border-strong hover:shadow-[0_10px_22px_rgba(16,53,87,0.12)] focus-visible:border-primary-500 focus-visible:shadow-[0_0_0_3px_rgba(31,92,168,0.14),0_10px_22px_rgba(16,53,87,0.12)] active:cursor-grabbing {dragging
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
	}. Use as setas esquerda e direita para mover entre colunas.`}
	ondragstart={handleDragStart}
	ondragend={(event) => ondragend?.(event)}
	onkeydown={(event) => onkeydown?.(event)}
>
	<div class="flex flex-wrap items-center justify-between gap-1">
		<div class="flex flex-wrap items-center gap-[0.3rem]">
			{#if prioridadeLabel(card.prioridade)}
				<Badge tone={prioridadeTone(card.prioridade)}>
					{prioridadeLabel(card.prioridade)}
				</Badge>
			{/if}
			{#if tipoLabel(card.tipo_pedido)}
				<span
					class="rounded-[4px] border border-border-subtle bg-surface-muted px-1.5 py-px text-[10px] font-semibold text-text-secondary"
					>{tipoLabel(card.tipo_pedido)}</span
				>
			{/if}
		</div>
		{#if deleteTask && !confirmingDelete}
			<!-- Botão excluir revelado no hover/focus do card (paridade is-delete-btn) -->
			<button
				type="button"
				onclick={openDeleteConfirm}
				aria-label="Excluir tarefa"
				title="Excluir tarefa"
				class="inline-flex h-7 w-7 shrink-0 -translate-y-px items-center justify-center rounded-md border border-danger/40 bg-surface text-xs text-danger opacity-0 transition-[opacity,transform,background-color,border-color] duration-fast hover:bg-danger/10 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100"
			>
				<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
					<path d="M10 11v6M14 11v6" />
				</svg>
			</button>
		{/if}
	</div>

	<p class="m-0 break-words text-sm leading-normal text-text-primary">{card.descricao}</p>

	<div class="mt-auto flex items-center justify-between gap-2">
		{#if card.responsavel}
			<span class="truncate text-xs text-text-secondary">Responsável: {card.responsavel}</span>
		{:else}
			<span class="truncate text-xs italic text-text-muted">Sem responsável</span>
		{/if}
		{#if openTaskDrawer}
			<button
				type="button"
				onclick={() => openTaskDrawer?.(card.id)}
				class="shrink-0 rounded-md px-1.5 py-0.5 text-xs font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Abrir
			</button>
		{/if}
	</div>

	{#if confirmingDelete}
		<!-- Mini-confirm inline no card (paridade .task-items-kanban-delete-confirm:
		     borda/fundo de perigo + animação de entrada td-kanban-delete-confirm-in) -->
		<div
			role="alertdialog"
			aria-label="Confirmar exclusão da tarefa"
			class="kanban-delete-confirm mt-[0.12rem] flex flex-col gap-2 rounded-[9px] border border-danger/40 bg-danger/5 px-[0.46rem] py-[0.42rem]"
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
					class="h-[26px] rounded-[7px] border border-danger/50 bg-danger/10 px-[0.44rem] text-2xs font-semibold text-danger transition-colors duration-fast hover:bg-danger/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
				>
					{deleting ? 'Excluindo…' : 'Excluir'}
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	/*
	 * `.is-dragging` (kanban.css): o card-fonte colapsa enquanto arrastado —
	 * opacity:0 + altura zero + sem borda/sombra + cursor grabbing. Mantém o
	 * elemento no fluxo (a board usa data-item-id para calcular o índice de drop).
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
			box-shadow: 0 6px 16px rgba(18, 56, 91, 0.08);
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
	}
</style>
