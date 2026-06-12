/**
 * Contratos entre o `KanbanBoard` (dono do estado de drag) e as colunas/zonas,
 * que leem esse estado via `zoneView(status)`.
 */
import type { BoardCard } from '$lib/types/board';
import type { TaskStatus } from '$lib/utils/taskStatus';

/** Recorte reativo do estado de drag do board para UMA zona de status. */
export interface KanbanZoneView {
	/** A zona aceita o card em drag? (`canItemMoveToStatus`, UX-only). */
	canDrop: boolean;
	/** O ponteiro do drag está sobre esta zona? */
	isOver: boolean;
	/** Índice de inserção do placeholder entre os cards visíveis, ou `null`. */
	placeholderIndex: number | null;
}

/**
 * Callbacks de DnD do board + estado de drag compartilhado. `zoneView` é uma
 * função de leitura (não snapshot): chamada no template da zona, lê os runes
 * do board e mantém a reatividade.
 */
export interface KanbanDndProps {
	zoneView: (status: TaskStatus) => KanbanZoneView;
	/** Id do card-fonte colapsado durante o drag (classe `is-dragging`). */
	draggingId: number | null;
	/** Id do card recém-aterrissado (animação `is-drop-settling`). */
	settledId: number | null;
	/** Altura (px) do card arrastado, para o vão do placeholder. */
	placeholderHeight: number | null;
	onCardDragStart: (event: DragEvent, card: BoardCard, status: TaskStatus) => void;
	onCardDragEnd: (event: DragEvent) => void;
	onZoneDragEnter: (event: DragEvent, status: TaskStatus) => void;
	onZoneDragOver: (event: DragEvent, status: TaskStatus) => void;
	onZoneDragLeave: (event: DragEvent, status: TaskStatus) => void;
	onZoneDrop: (event: DragEvent, status: TaskStatus) => void;
	onCardKeydown: (event: KeyboardEvent, card: BoardCard, status: TaskStatus) => void;
}
