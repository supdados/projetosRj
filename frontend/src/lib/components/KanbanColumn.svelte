<script lang="ts">
	/**
	 * Coluna do Kanban: header tingido + dropzone + rodapé opcional. Serve os 5
	 * status, inclusive a Finalizada (mesma largura, sem caso especial).
	 */
	import type { Snippet } from 'svelte';
	import KanbanColumnHeader from '$lib/components/KanbanColumnHeader.svelte';
	import KanbanDropzone from '$lib/components/KanbanDropzone.svelte';
	import type { BoardColumn } from '$lib/types/board';
	import type { KanbanDndProps } from '$lib/types/kanbanDnd';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props extends KanbanDndProps {
		column: BoardColumn;
		/** Rodapé opcional da coluna (composer inline, ação de arquivar…). */
		footer?: Snippet<[TaskStatus]>;
	}

	let { column, footer, ...dnd }: Props = $props();
</script>

<section
	class="flex h-full min-h-0 min-w-[220px] flex-1 flex-col gap-2 rounded-xl border border-border-subtle [contain:layout]"
	aria-labelledby={`kanban-col-${column.status}`}
>
	<KanbanColumnHeader
		status={column.status}
		headingId={`kanban-col-${column.status}`}
		label={column.label}
		count={column.tasks.length}
	/>

	<KanbanDropzone status={column.status} label={column.label} tasks={column.tasks} {...dnd} />

	{#if footer}
		<div class="shrink-0 px-1 pb-1">
			{@render footer(column.status)}
		</div>
	{:else}
		<!-- Rodapé fantasma na altura do "+ adicionar": alinha o fim das colunas. -->
		<div aria-hidden="true" class="shrink-0 px-1 pb-1">
			<div class="h-[31px]"></div>
		</div>
	{/if}
</section>
