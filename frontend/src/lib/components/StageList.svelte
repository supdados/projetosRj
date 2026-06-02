<script lang="ts">
	/**
	 * Lista de etapas com reordenação por DnD (HTML5 drag nativo).
	 *
	 * Espelha static/js/.../detail/07-stage-dnd.js no que tange à reordenação:
	 * `draggable`, classes `is-dragging`/`is-drop-target-top|bottom`. Porém a
	 * CASCATA DE DATAS É SERVER-SIDE — ao soltar, este componente apenas emite
	 * `onReorder(novaOrdemIds)`; a PÁGINA chama o endpoint reordenar (que pode
	 * disparar a cascata) e RE-BUSCA o estado. NÃO recalculamos datas no cliente.
	 *
	 * svelte-dnd-action NÃO está no package.json (ver nota do resumo) — por isso
	 * usamos HTML5 DnD nativo, sem instalar dependências.
	 *
	 * CONTROLADO: recebe `etapas` + repassa todos os callbacks de StageRow. As
	 * reuniões Google não são arrastáveis (read-only/Fase 6).
	 *
	 * Acessibilidade: cada item é arrastável via `draggable`; também oferecemos
	 * botões "mover para cima/baixo" como alternativa por teclado (emitem a mesma
	 * `onReorder`). Lista rotulada; estado vazio anunciado.
	 */
	import StageRow from './StageRow.svelte';
	import type { EtapaDetail, EtapaTask, EtapaInlineField } from '$lib/types/projectDetail';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}

	interface Props {
		etapas: EtapaDetail[];
		readonly?: boolean;
		/** Reordenação em andamento (desabilita o DnD). */
		reordering?: boolean;
		/** Erro da última reordenação. */
		reorderError?: string | null;
		/** Estados por etapa: `{ [etapaId]: { fields, busy, error } }`. */
		rowStates?: Record<
			number,
			{
				fields?: Partial<Record<EtapaInlineField, FieldState>>;
				busy?: boolean;
				error?: string | null;
			}
		>;
		/** Tarefas read-only por etapa (`{ [etapaId]: tasks | null }`). */
		tasksByEtapa?: Record<number, EtapaTask[] | null>;
		/** Etapas com lista de tarefas carregando. */
		tasksLoading?: Record<number, boolean>;
		/** Emite a nova ordem (IDs) ao soltar/mover; a página chama o endpoint. */
		onReorder: (orderedIds: number[]) => void;
		onUpdateField: (etapaId: number, field: EtapaInlineField, value: string) => void;
		onToggleIniciada: (etapaId: number) => void;
		onToggleDone: (etapaId: number) => void;
		onSaveComentario: (etapaId: number, comentario: string) => void;
		onEdit: (etapaId: number) => void;
		onDelete: (etapaId: number) => void;
		onLoadTasks?: (etapaId: number) => void;
	}

	let {
		etapas,
		readonly = false,
		reordering = false,
		reorderError = null,
		rowStates = {},
		tasksByEtapa = {},
		tasksLoading = {},
		onReorder,
		onUpdateField,
		onToggleIniciada,
		onToggleDone,
		onSaveComentario,
		onEdit,
		onDelete,
		onLoadTasks
	}: Props = $props();

	let dragIndex = $state<number | null>(null);
	let overIndex = $state<number | null>(null);

	const canReorder = $derived(!readonly && !reordering && etapas.length > 1);

	/** True quando a etapa pode ser arrastada (não é reunião Google). */
	function isDraggable(etapa: EtapaDetail): boolean {
		return canReorder && !etapa.is_google_meeting;
	}

	function handleDragStart(event: DragEvent, index: number): void {
		if (!isDraggable(etapas[index])) {
			event.preventDefault();
			return;
		}
		dragIndex = index;
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			// Necessário em Firefox para iniciar o arraste.
			event.dataTransfer.setData('text/plain', String(etapas[index].id));
		}
	}

	function handleDragOver(event: DragEvent, index: number): void {
		if (dragIndex === null) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		overIndex = index;
	}

	function handleDrop(event: DragEvent, index: number): void {
		event.preventDefault();
		if (dragIndex === null || dragIndex === index) {
			resetDrag();
			return;
		}
		emitReorderMove(dragIndex, index);
		resetDrag();
	}

	function resetDrag(): void {
		dragIndex = null;
		overIndex = null;
	}

	/** Calcula a nova ordem movendo `from` para a posição `to` e emite os IDs. */
	function emitReorderMove(from: number, to: number): void {
		const ids = etapas.map((e) => e.id);
		const [moved] = ids.splice(from, 1);
		ids.splice(to, 0, moved);
		onReorder(ids);
	}

	/** Alternativa por teclado: move a etapa uma posição na direção dada. */
	function move(index: number, delta: number): void {
		const target = index + delta;
		if (target < 0 || target >= etapas.length) return;
		emitReorderMove(index, target);
	}

	function rowState(etapaId: number) {
		return rowStates[etapaId] ?? {};
	}
</script>

{#if reorderError}
	<p role="alert" class="mb-2 text-sm text-danger">{reorderError}</p>
{/if}

{#if etapas.length === 0}
	<div class="flex flex-col gap-1 py-4 text-center">
		<p class="font-medium text-text-primary">Nenhuma etapa cadastrada</p>
		<p class="text-sm text-text-muted">
			Adicione etapas manualmente ou importe um modelo de etapas.
		</p>
	</div>
{:else}
	<ol class="flex flex-col gap-3" aria-label="Etapas do projeto" aria-busy={reordering}>
		{#each etapas as etapa, index (etapa.id)}
			{@const st = rowState(etapa.id)}
			<li
				draggable={isDraggable(etapa)}
				ondragstart={(e) => handleDragStart(e, index)}
				ondragover={(e) => handleDragOver(e, index)}
				ondrop={(e) => handleDrop(e, index)}
				ondragend={resetDrag}
				class="relative {dragIndex === index ? 'opacity-50' : ''} {overIndex === index &&
				dragIndex !== null &&
				dragIndex !== index
					? 'ring-2 ring-primary-500'
					: ''}"
			>
				{#if canReorder && !etapa.is_google_meeting}
					<div class="absolute right-2 top-2 z-10 flex flex-col gap-0.5">
						<button
							type="button"
							onclick={() => move(index, -1)}
							disabled={index === 0}
							aria-label={`Mover etapa "${etapa.descricao ?? ''}" para cima`}
							class="rounded border border-border-subtle bg-surface px-1 text-xs text-text-secondary hover:bg-surface-muted disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							▲
						</button>
						<button
							type="button"
							onclick={() => move(index, 1)}
							disabled={index === etapas.length - 1}
							aria-label={`Mover etapa "${etapa.descricao ?? ''}" para baixo`}
							class="rounded border border-border-subtle bg-surface px-1 text-xs text-text-secondary hover:bg-surface-muted disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							▼
						</button>
					</div>
				{/if}

				<StageRow
					{etapa}
					{readonly}
					fieldStates={st.fields}
					busy={st.busy}
					rowError={st.error}
					tasks={tasksByEtapa[etapa.id] ?? null}
					tasksLoading={tasksLoading[etapa.id] ?? false}
					onUpdateField={(field, value) => onUpdateField(etapa.id, field, value)}
					onToggleIniciada={() => onToggleIniciada(etapa.id)}
					onToggleDone={() => onToggleDone(etapa.id)}
					onSaveComentario={(c) => onSaveComentario(etapa.id, c)}
					onEdit={() => onEdit(etapa.id)}
					onDelete={() => onDelete(etapa.id)}
					onLoadTasks={onLoadTasks ? () => onLoadTasks(etapa.id) : undefined}
				/>
			</li>
		{/each}
	</ol>
{/if}
