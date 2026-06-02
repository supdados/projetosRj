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
</script>

<div
	class="flex cursor-grab flex-col gap-2 rounded-md border border-border-subtle bg-surface px-3 py-2.5 shadow-sm transition-opacity duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:cursor-grabbing {dragging
		? 'opacity-40'
		: ''}"
	draggable="true"
	tabindex="0"
	data-item-id={card.id}
	data-can-finalize={card.permissions.can_finalize}
	role="button"
	aria-roledescription="Tarefa movível"
	aria-label={`${card.descricao}${columnLabel ? `, em ${columnLabel}` : ''}${
		position && setSize ? ` (${position} de ${setSize})` : ''
	}. Use as setas esquerda e direita para mover entre colunas.`}
	ondragstart={(event) => ondragstart?.(event)}
	ondragend={(event) => ondragend?.(event)}
	onkeydown={(event) => onkeydown?.(event)}
>
	<p class="text-sm text-text-primary">{card.descricao}</p>

	<div class="flex flex-wrap items-center gap-2">
		{#if prioridadeLabel(card.prioridade)}
			<Badge tone={prioridadeTone(card.prioridade)}>
				{prioridadeLabel(card.prioridade)}
			</Badge>
		{/if}
		{#if tipoLabel(card.tipo_pedido)}
			<span class="text-xs text-text-secondary">{tipoLabel(card.tipo_pedido)}</span>
		{/if}
	</div>

	{#if card.responsavel}
		<p class="text-xs text-text-muted">Responsável: {card.responsavel}</p>
	{/if}

	<div class="flex items-center gap-3">
		{#if openTaskDrawer}
			<button
				type="button"
				onclick={() => openTaskDrawer?.(card.id)}
				class="w-fit text-xs font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Abrir
			</button>
		{/if}
		{#if deleteTask && !confirmingDelete}
			<button
				type="button"
				onclick={openDeleteConfirm}
				aria-label="Excluir tarefa"
				title="Excluir tarefa"
				class="w-fit text-xs font-medium text-danger hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
			>
				Excluir
			</button>
		{/if}
	</div>

	{#if confirmingDelete}
		<!-- Mini-confirm inline no card (não window.confirm) -->
		<div
			role="alertdialog"
			aria-label="Confirmar exclusão da tarefa"
			class="flex flex-col gap-2 rounded-md border border-danger bg-surface px-2 py-2"
		>
			<p class="text-xs text-text-primary">Excluir esta tarefa?</p>
			{#if deleteError}
				<p role="alert" class="text-xs text-danger">{deleteError}</p>
			{/if}
			<div class="flex gap-2">
				<button
					type="button"
					onclick={cancelDeleteConfirm}
					disabled={deleting}
					class="rounded-md border border-border-subtle px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={() => void confirmDelete()}
					disabled={deleting}
					class="rounded-md bg-danger px-2 py-1 text-xs font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
				>
					{deleting ? 'Excluindo…' : 'Excluir'}
				</button>
			</div>
		</div>
	{/if}
</div>
