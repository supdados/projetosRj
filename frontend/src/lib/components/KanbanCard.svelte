<script lang="ts">
	/**
	 * Card de tarefa no Kanban — arrastável e clicável.
	 *
	 * Anatomia (Variação B da referência de design, jun/2026): título da tarefa
	 * em primeiro, link azul para o projeto, e rodapé com prioridade em ponto
	 * colorido + rótulo, tipo como ícone (bloco T-A), contadores de comentários
	 * (balão) e anexos (clipe) e avatares dos responsáveis.
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
	import { getContext, tick, untrack } from 'svelte';
	import type { BoardCard } from '$lib/types/board';
	import { priorityDotColor, priorityIconId } from '$lib/utils/taskLabels';
	import StateIcon from '$lib/components/StateIcon.svelte';
	import { flash } from '$lib/stores/flash';
	import AssigneeAvatar from '$lib/components/AssigneeAvatar.svelte';
	import InlineConfirm from '$lib/components/InlineConfirm.svelte';
	import TaskTipoIcon from '$lib/components/TaskTipoIcon.svelte';
	import {
		KANBAN_COLUMN_MOTION,
		type KanbanColumnMotionSignal
	} from '$lib/utils/kanbanColumnMotion';

	/**
	 * Abertura do drawer: fornecida via contexto pela página, para não exigir
	 * prop drilling por KanbanBoard/KanbanColumn. Ausente quando o board é
	 * usado sem drawer.
	 */
	const openTaskDrawer = getContext<((taskId: number) => void) | undefined>('openTaskDrawer');

	/**
	 * Exclusão de card: fornecida via contexto pela página. O card coordena o
	 * `InlineConfirm` local; a página executa a chamada e remove o card da
	 * store. Abrir um confirm fecha os demais via `registerDeleteConfirm`.
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
	/** Cor do ponto de prioridade (cai em "media" p/ valor desconhecido). */
	const prioridadeDotColor = $derived(
		priorityDotColor(card.prioridade) ?? 'var(--ds-color-priority-media)'
	);
	const tipoLabel = $derived(
		card.tipo_pedido ? (TIPO_LABEL[card.tipo_pedido] ?? card.tipo_pedido) : null
	);

	// RESPONSÁVEIS: avatares de iniciais (mesma linguagem do picker da lista).
	// A fonte é SÓ a relação `assignees` — o texto livre legado (`responsavel`)
	// foi convertido em task_assignee pelo backfill e não é mais exibido, para
	// o card nunca divergir do drawer/lista.
	const assignees = $derived(card.assignees ?? []);
	const MAX_CARD_AVATARS = 3;
	const assigneeNames = $derived(assignees.map((a) => a.name).join(', '));

	/**
	 * Rodapé adaptativo por medição: nível 0 = tudo; 1 = suprime o tipo; 2 =
	 * agrega avatares em "+N". Sobe um degrau enquanto há overflow horizontal;
	 * `refitToken` descarta rodadas obsoletas. A medição nunca roda direto no
	 * ResizeObserver: coalesce por rAF e suspende durante morph de largura
	 * (KANBAN_COLUMN_MOTION) — ver docs/refinamento-animacao-kanban-expandir.md.
	 */
	let footerEl = $state<HTMLElement | null>(null);
	let fitLevel = $state(0);
	let refitToken = 0;

	const columnMotion = getContext<KanbanColumnMotionSignal | undefined>(KANBAN_COLUMN_MOTION);
	let rafPending = false;
	let needsRefit = $state(false);

	function scheduleFooterRefit(): void {
		if (columnMotion?.active) {
			needsRefit = true;
			return;
		}
		if (rafPending) return;
		rafPending = true;
		requestAnimationFrame(() => {
			rafPending = false;
			void refitFooter();
		});
	}

	const overflowAvatarNames = $derived(
		assignees
			.slice(1)
			.map((a) => a.name)
			.join(', ')
	);

	function footerOverflowing(): boolean {
		return !!footerEl && footerEl.scrollWidth - footerEl.clientWidth > 1;
	}

	async function refitFooter(): Promise<void> {
		const token = ++refitToken;
		if (fitLevel !== 0) {
			fitLevel = 0;
			await tick();
		}
		while (token === refitToken && fitLevel < 2 && footerOverflowing()) {
			fitLevel += 1;
			await tick();
		}
	}

	$effect(() => {
		if (!footerEl) return;
		// Dependências de CONTEÚDO: qualquer mudança que altere a largura
		// necessária do rodapé dispara uma nova rodada de medição.
		void card.prioridade;
		void card.tipo_pedido;
		void card.comments_count;
		void card.anexos_count;
		void assignees.length;
		const observer = new ResizeObserver(() => {
			scheduleFooterRefit();
		});
		observer.observe(footerEl);
		// CRÍTICO: `refitFooter` lê e escreve `fitLevel`. Sem `untrack`, a leitura
		// síncrona registraria `fitLevel` como dependência DESTE efeito — cada
		// escrita re-dispararia o efeito, em loop infinito
		// (effect_update_depth_exceeded derruba o board inteiro).
		untrack(() => scheduleFooterRefit());
		return () => observer.disconnect();
	});

	// Re-medição única quando o sinal de morph desliga.
	$effect(() => {
		if (!columnMotion || columnMotion.active || !needsRefit) return;
		needsRefit = false;
		untrack(() => scheduleFooterRefit());
	});

	// Exclusão pequena e frequente no próprio card: InlineConfirm (spec Grupo 4).
	let confirmingDelete = $state(false);
	let deleting = $state(false);
	let cardEl = $state<HTMLElement | null>(null);

	function openDeleteConfirm(): void {
		// Abrir um confirm fecha os demais (paridade board-dnd.js).
		registerDeleteConfirm?.(() => {
			confirmingDelete = false;
		});
		confirmingDelete = true;
	}
	async function cancelDeleteConfirm(): Promise<void> {
		confirmingDelete = false;
		// Depois do desmonte: a faixa restaura o foco do gatilho (já removido do
		// DOM) ao sair, e sem o `tick` esse restore anularia o foco no card.
		await tick();
		cardEl?.focus();
	}
	async function confirmDelete(): Promise<void> {
		if (!deleteTask) return;
		deleting = true;
		const ok = await deleteTask(card.id);
		if (!ok) {
			deleting = false;
			// Sem espaço ancorável dentro da faixa: o motivo vai por toast.
			flash.danger('Não foi possível excluir a tarefa.', { key: 'tarefa-excluir-falha' });
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
		// Tecla vinda de um descendente focável (link do projeto, excluir, confirm)
		// pertence ao controle: interceptar aqui roubaria o Enter/Espaço dele para
		// abrir o drawer (e as setas moveriam o card com o foco num botão).
		if (event.target !== event.currentTarget) return;
		if ((event.key === 'Enter' || event.key === ' ') && openTaskDrawer) {
			event.preventDefault();
			openTaskDrawer(card.id);
			return;
		}
		onkeydown?.(event);
	}
</script>

<!--
	Card de tarefa (Variação B) — superfície branca SEM borda, flutuando em
	sombra suave; no hover o card "sobe" 1px e a sombra aprofunda
	(microinteração de affordance de arrasto/clique). `is-dragging` colapsa o
	card-fonte (opacity:0, height:0) enquanto o placeholder de inserção mostra
	o destino. `is-drop-settling` roda a animação de assentamento pós-drop.
	Focus-visible com ring triplo acessível.
-->
<div
	bind:this={cardEl}
	class="kanban-card group relative flex cursor-pointer flex-col gap-2 rounded-lg bg-surface px-3.5 pb-3 pt-3 [contain:layout] shadow-sm outline-none transition-[transform,box-shadow,background-color] duration-fast hover:-translate-y-px hover:shadow-md focus-visible:ring-2 focus-visible:ring-brand active:cursor-grabbing {dragging
		? 'is-dragging'
		: ''} {settled ? 'is-drop-settling' : ''} {confirmingDelete ? 'min-h-[9rem]' : ''}"
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
	<!-- max-height em vez de line-clamp: dentro de -webkit-box o float (que
	     reserva o canto da 1ª linha p/ a lixeira) não flutua. -->
	<p class="m-0 max-h-[3.75em] overflow-hidden break-words text-xs font-normal leading-snug text-text-primary 2xl:text-sm">
		{#if deleteTask}<span aria-hidden="true" class="float-right h-3.5 w-7"></span>{/if}{card.descricao}
	</p>

	{#if card.project_id && card.project_titulo}
		<!-- Link do projeto: navega para a página do projeto sem abrir o drawer
		     (o handler de clique do card ignora cliques originados em <a>). -->
		<a
			href={`/projetos/${card.project_id}`}
			draggable="false"
			class="-mt-1 w-fit max-w-full truncate rounded-sm text-2xs font-medium text-brand transition-colors duration-fast hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			title={card.project_titulo}
		>
			{card.project_titulo}
		</a>
	{/if}

	<!--
		Rodapé (Variação B): prioridade vira PONTO colorido + rótulo e o tipo vira
		ícone (TaskTipoIcon, rótulo no title/sr-only), à esquerda; contadores (só
		quando > 0) e avatares dos responsáveis, à direita. Quando falta largura,
		degrada por medição: nível 1 suprime o tipo, nível 2 agrega os avatares
		(ver `refitFooter`).
	-->
	<div bind:this={footerEl} class="mt-auto flex min-w-0 items-center gap-1.5 pt-0.5">
		{#if prioridadeLabel}
			<span class="kc-chip kc-chip--prio">
				<span class="flex flex-none" style:color={prioridadeDotColor}>
					<StateIcon id={priorityIconId(card.prioridade)} size={12} />
				</span>{prioridadeLabel}
			</span>
		{/if}
		{#if prioridadeLabel && tipoLabel && fitLevel < 1}
			<!-- Separador "·" bem sutil, centralizado na vertical pela linha. -->
			<span aria-hidden="true" class="text-2xs font-bold leading-none text-text-muted opacity-60"
				>·</span
			>
		{/if}
		{#if tipoLabel && fitLevel < 1}
			<span class="inline-flex flex-none items-center" title={tipoLabel}>
				<TaskTipoIcon tipo={card.tipo_pedido} size={14} />
				<span class="sr-only">{tipoLabel}</span>
			</span>
		{/if}

		<span class="ml-auto flex shrink-0 items-center gap-2 text-xs tabular-nums">
			{#if card.comments_count > 0}
				<span
					class="inline-flex items-center gap-1 font-semibold text-text-muted transition-colors duration-fast hover:text-brand"
					title={card.comments_count === 1 ? '1 comentário' : `${card.comments_count} comentários`}
				>
					<svg viewBox="0 0 24 24" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 8.5-8.5 8.38 8.38 0 0 1 8.5 8.5Z" />
					</svg>
					{card.comments_count}
				</span>
			{/if}
			{#if card.anexos_count > 0}
				<span
					class="inline-flex items-center gap-1 font-semibold text-text-muted transition-colors duration-fast hover:text-brand"
					title={card.anexos_count === 1 ? '1 anexo' : `${card.anexos_count} anexos`}
				>
					<svg viewBox="0 0 24 24" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
					</svg>
					{card.anexos_count}
				</span>
			{/if}

			{#if assignees.length > 0}
				<span
					class="flex items-center gap-1 pl-0.5"
					title={`Responsáve${assignees.length === 1 ? 'l' : 'is'}: ${assigneeNames}`}
				>
					{#if fitLevel < 2 || assignees.length === 1}
						<span class="flex shrink-0 -space-x-1">
							{#each assignees.slice(0, MAX_CARD_AVATARS) as a, i (a.id)}
								<!-- z decrescente: o 1º avatar fica na frente dos seguintes. -->
								<span
									class="relative rounded-full ring-2 ring-surface"
									style="z-index: {MAX_CARD_AVATARS - i}"
								>
									<AssigneeAvatar name={a.name} initials={a.initials} size="xs" />
								</span>
							{/each}
						</span>
						{#if assignees.length > MAX_CARD_AVATARS}
							<span class="shrink-0 text-2xs font-semibold text-text-muted"
								>+{assignees.length - MAX_CARD_AVATARS}</span
							>
						{/if}
					{:else}
						<!-- Nível 2: só o 1º responsável + bolinha agregada "+N" (os
						     demais nomes aparecem no hover via title). -->
						<span class="flex shrink-0 -space-x-1">
							<span class="relative z-[2] rounded-full ring-2 ring-surface">
								<AssigneeAvatar
									name={assignees[0].name}
									initials={assignees[0].initials}
									size="xs"
								/>
							</span>
							<span
								class="kc-avatar-overflow relative z-[1] inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-2xs font-semibold leading-none ring-2 ring-surface"
								title={overflowAvatarNames}
							>
								+{assignees.length - 1}
							</span>
						</span>
					{/if}
				</span>
			{/if}
		</span>
	</div>

	{#if deleteTask && !confirmingDelete}
		<!-- Botão excluir revelado no hover/focus do card, canto superior direito. -->
		<button
			type="button"
			onclick={openDeleteConfirm}
			aria-label="Excluir tarefa"
			title="Excluir tarefa"
			class="kc-delete-btn absolute right-1.5 top-1.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs text-danger opacity-0 transition-[opacity,color] duration-fast focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger group-hover:opacity-100 group-focus-within:opacity-100"
		>
			<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
				<path d="M10 11v6M14 11v6" />
			</svg>
		</button>
	{/if}

	{#if confirmingDelete}
		<!-- Abaixo do conteúdo, em fluxo: o card cresce e nada fica encoberto. -->
		<div class="kanban-delete-confirm mt-2">
			<InlineConfirm
				question="Excluir esta tarefa? Comentários e anexos serão apagados."
				tone="danger"
				icon="trash"
				confirmLabel="Excluir tarefa"
				cancelLabel="Cancelar"
				busy={deleting}
				onConfirm={confirmDelete}
				onCancel={cancelDeleteConfirm}
			/>
		</div>
	{/if}
</div>

<style>
	/*
	 * Rótulos do rodapé (Variação B). Prioridade = PONTO SÓLIDO + rótulo em
	 * texto normal (inversão de forma, plano-regua-de-cor §7.4); a cor do ponto
	 * vem das vars `--ds-color-priority-*` (dark-safe).
	 */
	.kc-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.32rem;
		font-size: 0.6875rem;
		font-weight: 600;
		line-height: 1.4;
		white-space: nowrap;
		flex: none;
	}
	.kc-chip--prio {
		color: var(--ds-color-text-secondary);
	}
	/* Bolinha agregada de responsáveis ("+N", nível 2 do rodapé adaptativo). */
	.kc-avatar-overflow {
		background-color: var(--ds-color-wash-neutral);
		color: var(--ds-color-text-secondary);
	}

	/* Lixeira sem fundo (só o ícone): o hover acende o vermelho (token puro). */
	.kc-delete-btn:hover {
		color: var(--ds-color-text-danger);
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
			box-shadow: var(--ds-shadow-lg);
		}
		50% {
			transform: scale(0.99) translateY(1px);
		}
		100% {
			transform: scale(1) translateY(0);
			box-shadow: var(--ds-shadow-sm);
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
