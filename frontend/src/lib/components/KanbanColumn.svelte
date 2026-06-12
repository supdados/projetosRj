<script lang="ts">
	/**
	 * Coluna do Kanban (status ativo): header tingido + dropzone + composer
	 * opcional. A Finalizada tem componente próprio (KanbanDoneColumn).
	 */
	import type { Snippet } from 'svelte';
	import KanbanColumnHeader from '$lib/components/KanbanColumnHeader.svelte';
	import KanbanDropzone from '$lib/components/KanbanDropzone.svelte';
	import type { BoardColumn } from '$lib/types/board';
	import type { KanbanDndProps } from '$lib/types/kanbanDnd';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props extends KanbanDndProps {
		column: BoardColumn;
		/** Composer inline opcional, renderizado no rodapé da coluna. */
		composer?: Snippet<[TaskStatus]>;
	}

	let { column, composer, ...dnd }: Props = $props();
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

	{#if composer}
		<div class="shrink-0 px-1 pb-1">
			{@render composer(column.status)}
		</div>
	{:else}
		<!-- Rodapé fantasma na altura do "+ adicionar": alinha o fim das colunas. -->
		<div aria-hidden="true" class="shrink-0 px-1 pb-1">
			<div class="h-[31px]"></div>
		</div>
	{/if}
</section>
