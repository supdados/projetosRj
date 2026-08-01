<script lang="ts">
	/**
	 * Cabeçalho do Detalhe de Projeto — paridade VISUAL + INTERAÇÃO com o v4.5.
	 *
	 * Reproduz fielmente:
	 *  - O HEADER GLASS (gradiente azul, padrão de pontos, título com gradient-clip,
	 *    descrição com clamp) de css/projects/detail/01-shell-and-header.css.
	 *  - Os CHIPS (.ph-chip) de status/prioridade/tipo de entrega/categoria + datas
	 *    com seta e duração (.ph-chip-dates / .ph-duration).
	 *  - O COMPACT HEADER fixo que aparece ao rolar (10-compact-header.js): fixed,
	 *    fade + translateY/scale, com os mesmos campos em paleta clara (.pc-chip).
	 *  - Edição INLINE dos chips de status/prioridade (clique-para-editar -> select),
	 *    igual ao 09-project-inline-editor.js; emite onEditField (a página chama a API).
	 *  - O SELETOR de abas Detalhes/Etapas na base do header (estado na página;
	 *    emite onTabChange).
	 *
	 * CONTROLADO: recebe `project` + `options` + `permissions` + `derivedData`; emite
	 * `onEditField(field, value)` — NÃO chama API.
	 */
	import { tick } from 'svelte';
	import { stickyHeader } from '$lib/actions/stickyHeader';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type {
		ProjectDetail,
		ProjectDetailOptions,
		ProjectDetailPermissions,
		ProjectDetailDerived,
		ProjectDetailTab
	} from '$lib/types/projectDetail';
	import { base } from '$app/paths';
	import { isAcessoPorConvite } from '$lib/utils/projectMembers';

	type HeaderField =
		| 'titulo'
		| 'short_description'
		| 'status'
		| 'prioridade'
		| 'delivery_type'
		| 'special_project';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}

	interface Props {
		project: ProjectDetail;
		options: ProjectDetailOptions;
		permissions: ProjectDetailPermissions;
		derivedData: ProjectDetailDerived;
		/** Altura do topnav fixo (px) para o offset do sticky. */
		topOffset?: number;
		fieldStates?: Partial<Record<HeaderField, FieldState>>;
		/** Projeto finalizado: header inteiro vira somente leitura (reabrir só pelo botão). */
		locked?: boolean;
		onEditField: (field: HeaderField, value: string) => void;
		/** Abre o modal "Compartilhar" (S4). Ausente = botão não aparece. */
		onShare?: () => void;
		/** Aba ativa do seletor Detalhes/Etapas (estado mora na página). */
		activeTab: ProjectDetailTab;
		onTabChange: (tab: ProjectDetailTab) => void;
	}

	let {
		project,
		options,
		permissions,
		derivedData,
		topOffset = 0,
		fieldStates = {},
		locked = false,
		onEditField,
		onShare,
		activeTab,
		onTabChange
	}: Props = $props();

	const TABS: { id: ProjectDetailTab; label: string }[] = [
		{ id: 'detalhes', label: 'Detalhes' },
		{ id: 'etapas', label: 'Etapas' }
	];

	// Gate autoritativo do servidor; ausente (release anterior) = negado.
	const canShare = $derived(Boolean(onShare && permissions.can_manage_members));
	const isConvidado = $derived(isAcessoPorConvite(project.access_via));

	let compact = $state(false);
	const canEdit = $derived(permissions.can_edit && !locked);

	// Folga (px) entre a base do topnav e o header compacto, para que ele não
	// fique colado no topo. O GATILHO usa `topOffset` puro (sincronia exata com
	// o sumiço do header); só a POSIÇÃO do compacto recebe esta folga.
	const COMPACT_TOP_GAP = 12;
	const compactTop = $derived(topOffset + COMPACT_TOP_GAP);

	// --- Edição inline de chip (status/prioridade/tipo/especial) -------------
	// SelectMenu unstyled: o trigger é o próprio chip (snippet), painel custom.
	function selectChip(field: HeaderField, value: string): void {
		onEditField(field, value);
	}

	// --- Edição inline de TÍTULO e DESCRIÇÃO (paridade com v4.5) --------------
	// Réplica do 09-project-inline-editor.js: clicar no lápis troca o texto por um
	// <textarea> que HERDA a tipografia do display (sem salto visual), com fundo
	// translúcido e SEM borda, altura auto-crescente e — na descrição — largura que
	// abraça o conteúdo (mín..máx = largura do container). Blur/Enter salvam;
	// Shift+Enter quebra linha na descrição; Escape cancela. A página recebe
	// onEditField(field, value) e chama a API; o valor otimista segura o texto novo
	// no display até o servidor confirmar (sem piscar de volta no valor antigo).
	type TextField = 'titulo' | 'short_description';

	let editingField = $state<TextField | null>(null);
	let draft = $state('');
	let textEditorEl = $state<HTMLTextAreaElement | null>(null);
	// `undefined` => sem valor otimista; string/null => exibe o valor pendente.
	let optTitulo = $state<string | null | undefined>(undefined);
	let optDesc = $state<string | null | undefined>(undefined);
	let sawPendingTitulo = $state(false);
	let sawPendingDesc = $state(false);

	const shownTitulo = $derived(optTitulo !== undefined ? optTitulo : project.titulo);
	const shownDescription = $derived(optDesc !== undefined ? optDesc : project.short_description);

	// Solta o valor otimista quando a gravação se resolve (paridade InlineEditField):
	// o prop alcançou o valor salvo, houve erro (reverte), ou o pending caiu após ter
	// sido true.
	$effect(() => {
		if (optTitulo === undefined) {
			sawPendingTitulo = false;
			return;
		}
		const fs = fieldStates.titulo;
		if (fs?.pending) {
			sawPendingTitulo = true;
			return;
		}
		if ((project.titulo ?? '') === (optTitulo ?? '') || fs?.error || sawPendingTitulo) {
			optTitulo = undefined;
			sawPendingTitulo = false;
		}
	});
	$effect(() => {
		if (optDesc === undefined) {
			sawPendingDesc = false;
			return;
		}
		const fs = fieldStates.short_description;
		if (fs?.pending) {
			sawPendingDesc = true;
			return;
		}
		if ((project.short_description ?? '') === (optDesc ?? '') || fs?.error || sawPendingDesc) {
			optDesc = undefined;
			sawPendingDesc = false;
		}
	});

	// Mede a largura do texto p/ o campo abraçar o conteúdo (canvas, fonte REAL do
	// próprio textarea — adapta-se a título 1.5rem/bold e descrição 0.875rem).
	let measureCanvas: HTMLCanvasElement | null = null;
	function measureTextWidth(ta: HTMLTextAreaElement, slack: number): number {
		const style = window.getComputedStyle(ta);
		measureCanvas ??= document.createElement('canvas');
		const ctx = measureCanvas.getContext('2d');
		if (!ctx) return 240;
		ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
		const text = ta.value || ta.placeholder || '';
		const longest = text
			.split(/\r?\n/)
			.reduce((max, line) => Math.max(max, ctx.measureText(line || ' ').width), 0);
		return Math.ceil(longest + slack);
	}

	/* Folga à direita do texto (espaço do cursor). Na descrição ela é curta para o
	   editor nascer do mesmo tamanho do chip "Adicionar descrição". */
	const TITLE_WIDTH_SLACK = 26;
	const DESCRIPTION_WIDTH_SLACK = 8;

	// Título E descrição abraçam o conteúdo (paridade v4.5). A LARGURA é ajustada
	// PRIMEIRO e só então a ALTURA — assim a caixa cresce/encolhe junto com o texto e
	// NÃO sobra espaço embaixo quando o conteúdo cabe em menos linhas que a largura
	// inicial. O teto é o espaço livre à direita do textarea: medimos o quanto já foi
	// consumido à esquerda dele (ex.: o prefixo fixo "ID - " do título) e reservamos
	// uma folga p/ o botão lápis/ok, que agora fica FORA da caixa.
	function autoSizeText(): void {
		const ta = textEditorEl;
		if (!ta) return;
		const slack =
			editingField === 'short_description' ? DESCRIPTION_WIDTH_SLACK : TITLE_WIDTH_SLACK;
		const container = ta.closest('.ph-main-content');
		if (container) {
			const cRect = (container as HTMLElement).getBoundingClientRect();
			// `left` do textarea não depende da sua largura (alinhado à esquerda) =>
			// mede com segurança o que está à esquerda (prefixo + paddings da caixa).
			const leftConsumed = ta.getBoundingClientRect().left - cRect.left;
			const cap = Math.max(72, Math.floor(cRect.width - leftConsumed - 60));
			const measured = measureTextWidth(ta, slack);
			ta.style.width = `${Math.min(cap, Math.max(72, measured))}px`;
		} else {
			ta.style.width = `${Math.max(72, measureTextWidth(ta, slack))}px`;
		}
		ta.style.height = 'auto';
		// border-box: soma a borda p/ não recortar a última linha (igual InlineEditField).
		const borderY = ta.offsetHeight - ta.clientHeight;
		ta.style.height = `${ta.scrollHeight + borderY}px`;
	}

	async function enterTextEdit(field: TextField): Promise<void> {
		if (!canEdit || fieldStates[field]?.pending) return;
		editingField = field;
		draft = (field === 'titulo' ? shownTitulo : shownDescription) ?? '';
		await tick();
		textEditorEl?.focus();
		// Cursor no FIM (sem selecionar tudo): quem edita geralmente quer
		// acrescentar, e a seleção total forçava desfazer antes de digitar.
		if (textEditorEl) {
			const len = textEditorEl.value.length;
			textEditorEl.setSelectionRange(len, len);
		}
		autoSizeText();
	}

	function commitText(): void {
		const field = editingField;
		if (!field) return;
		editingField = null;
		const trimmed = draft.trim();
		const current = (field === 'titulo' ? project.titulo : project.short_description) ?? '';
		// Título é obrigatório: blur/Enter com vazio apenas cancela (paridade legado).
		if (field === 'titulo' && trimmed === '') return;
		if (trimmed === current) return;
		if (field === 'titulo') optTitulo = trimmed;
		else optDesc = trimmed === '' ? null : trimmed;
		onEditField(field, trimmed);
	}

	function cancelText(): void {
		editingField = null;
	}

	function onTextKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			cancelText();
			return;
		}
		if (event.key === 'Enter') {
			// Descrição: Shift+Enter quebra linha; Enter salva. Título: Enter salva.
			if (editingField === 'short_description' && event.shiftKey) return;
			event.preventDefault();
			commitText();
		}
	}

	// O lápis/ok é um ÚNICO botão que PERSISTE entre exibir/editar — por isso a
	// transição pen<->check é suave (mesmo elemento, só muda classe/ícone). Em modo
	// edição, o preventDefault no pointerdown evita que o textarea perca o foco ANTES
	// do clique (assim o clique confirma); clicar FORA do botão também salva (blur).
	function onPenPointerDown(field: TextField, event: MouseEvent): void {
		if (editingField === field) event.preventDefault();
	}
	function onPenClick(field: TextField): void {
		if (editingField === field) commitText();
		else void enterTextEdit(field);
	}

	// "Finalizado" NUNCA é selecionável no dropdown: a única transição para
	// Finalizado é o botão Concluir (POST /api/projetos/<id>/concluir). Filtro
	// defensivo caso o backend ainda oferte a opção.
	const statusOptions = $derived(options.status.filter((opt) => opt.value !== 'Finalizado'));

	const statusKey = $derived((project.status ?? '').toLowerCase() || 'na');
	const prioKey = $derived(project.prioridade ?? 'na');

	const PRIO_LABEL: Record<string, string> = {
		urgente: 'Urgente',
		alta: 'Alta',
		media: 'Média',
		baixa: 'Baixa'
	};
	const PRIO_ICON: Record<string, string> = {
		urgente: 'fa-exclamation-triangle',
		alta: 'fa-angle-double-up',
		media: 'fa-minus',
		baixa: 'fa-angle-double-down'
	};
	const PRIO_DOT: Record<string, string> = {
		urgente: 'var(--ds-color-priority-urgente)',
		alta: 'var(--ds-color-priority-alta)',
		media: 'var(--ds-color-priority-media)',
		baixa: 'var(--ds-color-priority-baixa)'
	};
	const STATUS_DOT: Record<string, string> = {
		Vigente: 'var(--ds-color-fill-success)',
		Suspenso: 'var(--ds-color-fill-warning)',
		Finalizado: 'var(--ds-color-status-finalizada)'
	};

	// --- Opções dos 4 SelectMenu de chip (mapeadas das constantes existentes) --
	const statusMenuOptions = $derived<SelectMenuOption[]>(
		statusOptions.map((opt) => ({ value: opt.value, label: opt.label, dot: STATUS_DOT[opt.value] }))
	);
	const prioMenuOptions = $derived<SelectMenuOption[]>(
		options.prioridade.map((opt) => ({ value: opt.value, label: opt.label, dot: PRIO_DOT[opt.value] }))
	);
	const deliveryMenuOptions = $derived<SelectMenuOption[]>(
		options.delivery_type.map((opt) => ({ value: opt, label: opt }))
	);
	const specialMenuOptions = $derived<SelectMenuOption[]>(
		options.special_project.map((opt) => ({ value: opt, label: opt }))
	);

	/** Formata ISO (YYYY-MM-DD) em pt-BR; null => vazio. */
	function formatDateBr(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	const startBr = $derived(formatDateBr(derivedData.data_inicio_projeto));
	const endBr = $derived(formatDateBr(derivedData.data_fim_projeto));

	/** Duração total em dias (inclusiva como o legado: (fim - inicio).days). */
	const durationLabel = $derived.by(() => {
		const a = derivedData.data_inicio_projeto;
		const b = derivedData.data_fim_projeto;
		if (!a || !b) return '';
		const da = new Date(a);
		const db = new Date(b);
		if (Number.isNaN(da.getTime()) || Number.isNaN(db.getTime())) return '';
		const days = Math.round((db.getTime() - da.getTime()) / 86_400_000);
		return `${days} ${days === 1 ? 'dia' : 'dias'}`;
	});

	const hasDates = $derived(Boolean(startBr || endBr));
</script>

<!-- ===================== HEADER PRINCIPAL (glass) =====================
     A action observa o PRÓPRIO header: o compacto aparece exatamente quando a
     base do header passa acima da linha do topnav (sem depender de um sentinela
     separado, que sofria o gap-6 do flex container e atrasava o gatilho). -->
<header
	class="project-header"
	aria-labelledby="project-detail-title"
	use:stickyHeader={{ topOffset, onChange: (isCompact) => (compact = isCompact) }}
>
	<div class="ph-main-row">
		<div class="ph-main-content">
			<!-- Título: o lápis troca o texto por um textarea fluido (paridade v4.5). O
			     <h1> fica SEMPRE no DOM (oculto visualmente ao editar) para preservar o
			     heading de nível 1 e o nome da região (header/section aria-labelledby);
			     o textarea tem id próprio para não roubar o id do heading. -->
			{#if isConvidado}
				<span class="ph-guest-badge" title="Você acessa este projeto por convite">
					<i class="fas fa-user-check" aria-hidden="true"></i>
					Convidado
				</span>
			{/if}
			<div class="ph-title-row">
				<h1
					id="project-detail-title"
					class="ph-title"
					class:ph-visually-hidden={editingField === 'titulo'}
				>
					{project.id} - {shownTitulo}
				</h1>
				{#if editingField === 'titulo'}
					<!-- O ID fica FORA da caixa de edição, FIXO e na mesma posição; só o título
					     vira campo. String única p/ o Svelte não aparar o espaço final. -->
					<span class="ph-title-id-prefix" aria-hidden="true">{`${project.id} - `}</span>
					<div class="ph-title-field ph-edit-shell">
						<textarea
							bind:this={textEditorEl}
							bind:value={draft}
							class="ph-text-editor ph-text-editor--title"
							rows="1"
							placeholder="Nome do projeto"
							aria-label="Título do projeto"
							aria-invalid={fieldStates.titulo?.error ? 'true' : undefined}
							aria-describedby={fieldStates.titulo?.error ? 'project-title-error' : undefined}
							disabled={fieldStates.titulo?.pending}
							oninput={autoSizeText}
							onblur={commitText}
							onkeydown={onTextKeydown}
						></textarea>
					</div>
				{/if}
				{#if canEdit}
					<button
						type="button"
						class="ph-edit-pen"
						class:ph-edit-pen--confirm={editingField === 'titulo'}
						aria-label={editingField === 'titulo'
							? 'Salvar título do projeto'
							: 'Editar título do projeto'}
						disabled={fieldStates.titulo?.pending}
						onmousedown={(e) => onPenPointerDown('titulo', e)}
						onclick={() => onPenClick('titulo')}
					>
						<i
							class="fas {fieldStates.titulo?.pending
								? 'fa-spinner fa-spin'
								: editingField === 'titulo'
									? 'fa-check'
									: 'fa-pen'}"
							aria-hidden="true"
						></i>
					</button>
				{/if}
			</div>
			{#if fieldStates.titulo?.error}
				<p id="project-title-error" class="ph-text-error" role="alert">
					{fieldStates.titulo.error}
				</p>
			{/if}

			<!-- Descrição: a linha PERSISTE entre exibir/editar (quando há descrição)
			     p/ o botão morfar suave pen<->check; vazia => "Adicionar descrição".
			     O slot reserva a altura de uma linha nos TRÊS estados (botão, exibição
			     e edição) p/ o header não mudar de tamanho ao alternar entre eles. -->
			<div class="ph-description-slot">
				{#if editingField === 'short_description' || shownDescription}
				<div class="ph-description-row">
					<div
						class="ph-description-field"
						class:ph-edit-shell={editingField === 'short_description'}
					>
						{#if editingField === 'short_description'}
							<textarea
								bind:this={textEditorEl}
								bind:value={draft}
								class="ph-text-editor ph-text-editor--description"
								rows="1"
								placeholder="Descrição do projeto"
								aria-label="Descrição do projeto"
								aria-invalid={fieldStates.short_description?.error ? 'true' : undefined}
								aria-describedby={fieldStates.short_description?.error
									? 'project-desc-error'
									: undefined}
								disabled={fieldStates.short_description?.pending}
								oninput={autoSizeText}
								onblur={commitText}
								onkeydown={onTextKeydown}
							></textarea>
						{:else}
							<p class="ph-description">{shownDescription}</p>
						{/if}
					</div>
					{#if canEdit}
						<button
							type="button"
							class="ph-edit-pen ph-edit-pen--description"
							class:ph-edit-pen--confirm={editingField === 'short_description'}
							aria-label={editingField === 'short_description'
								? 'Salvar descrição do projeto'
								: 'Editar descrição do projeto'}
							disabled={fieldStates.short_description?.pending}
							onmousedown={(e) => onPenPointerDown('short_description', e)}
							onclick={() => onPenClick('short_description')}
						>
							<i
								class="fas {fieldStates.short_description?.pending
									? 'fa-spinner fa-spin'
									: editingField === 'short_description'
										? 'fa-check'
										: 'fa-pen'}"
								aria-hidden="true"
							></i>
						</button>
					{/if}
				</div>
			{:else if canEdit}
				<button
					type="button"
					class="ph-add-description"
					onclick={() => enterTextEdit('short_description')}
				>
					Adicionar descrição
				</button>
			{/if}
			</div>
			{#if fieldStates.short_description?.error}
				<p id="project-desc-error" class="ph-text-error" role="alert">
					{fieldStates.short_description.error}
				</p>
			{/if}
		</div>
		<div class="ph-header-actions">
			{#if canShare}
				<button type="button" class="ph-back-button" onclick={() => onShare?.()}>
					<i class="fas fa-user-plus" aria-hidden="true"></i>
					<span>Compartilhar</span>
				</button>
			{/if}
			<a href={`${base}/projetos`} class="ph-back-button">
				<i class="fas fa-arrow-left" aria-hidden="true"></i>
				<span>Voltar</span>
			</a>
		</div>
	</div>

	<div class="project-header-chips">
		<!-- Status (editável inline: SelectMenu unstyled com o chip como trigger) -->
		<div class="ph-field">
			<span class="ph-field-label">Status</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				{#if canEdit}
					<SelectMenu
						options={statusMenuOptions}
						value={project.status}
						onSelect={(v) => selectChip('status', v ?? '')}
						unstyled
						ariaLabel="Status do projeto"
						trigger={statusChipContent}
					/>
				{:else}
					{@render statusChipContent()}
				{/if}
			</div>
		</div>

		<!-- Prioridade (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Prioridade</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				{#if canEdit}
					<SelectMenu
						options={prioMenuOptions}
						value={project.prioridade}
						onSelect={(v) => selectChip('prioridade', v ?? '')}
						allowAll
						allLabel="Sem prioridade"
						unstyled
						ariaLabel="Prioridade do projeto"
						trigger={prioChipContent}
					/>
				{:else}
					{@render prioChipContent()}
				{/if}
			</div>
		</div>

		<!-- Tipo de entrega (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Tipo de entrega</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				{#if canEdit}
					<SelectMenu
						options={deliveryMenuOptions}
						value={project.delivery_type}
						onSelect={(v) => selectChip('delivery_type', v ?? '')}
						allowAll
						allLabel="Sem tipo"
						unstyled
						ariaLabel="Tipo de entrega do projeto"
						trigger={deliveryChipContent}
					/>
				{:else}
					{@render deliveryChipContent()}
				{/if}
			</div>
		</div>

		<!-- Projeto especial (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Projeto especial</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				{#if canEdit}
					<SelectMenu
						options={specialMenuOptions}
						value={project.special_project}
						onSelect={(v) => selectChip('special_project', v ?? '')}
						allowAll
						allLabel="Sem categoria"
						unstyled
						ariaLabel="Projeto especial"
						trigger={specialChipContent}
					/>
				{:else}
					{@render specialChipContent()}
				{/if}
			</div>
		</div>

		<!-- Datas + duração -->
		{#if hasDates}
			<span class="ph-chip-dates">
				<i class="far fa-calendar-alt" aria-hidden="true"></i>
				<span class="ph-date-range">
					{#if startBr && endBr}
						{startBr}<span class="ph-date-arrow" aria-hidden="true">→</span>{endBr}
					{:else if startBr}
						Início {startBr}
					{:else}
						Fim {endBr}
					{/if}
				</span>
				{#if durationLabel}
					<span class="ph-date-sep" aria-hidden="true">·</span>
					<strong class="ph-duration">{durationLabel}</strong>
				{/if}
			</span>
		{/if}
	</div>

	<!-- Seletor Detalhes/Etapas: alterna as seções da página (estado na página). -->
	<nav class="ph-tabs" aria-label="Seções do projeto">
		{#each TABS as tab (tab.id)}
			<button
				type="button"
				class="ph-tab"
				class:ph-tab--active={activeTab === tab.id}
				aria-current={activeTab === tab.id ? 'true' : undefined}
				onclick={() => onTabChange(tab.id)}
			>
				{tab.label}
			</button>
		{/each}
	</nav>

	{#snippet statusChipContent()}
		<span class="ph-chip ph-chip--status ph-chip--status-{statusKey}" data-value={project.status ?? ''}>
			{#if project.status === 'Vigente'}
				<span class="ph-chip-dot" aria-hidden="true"></span>Vigente
			{:else if project.status === 'Finalizado'}
				<i class="fas fa-flag-checkered" aria-hidden="true"></i>Finalizado
			{:else if project.status === 'Suspenso'}
				<i class="fas fa-pause" aria-hidden="true"></i>Suspenso
			{:else}
				{project.status || 'Sem status'}
			{/if}
			{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
		</span>
	{/snippet}

	{#snippet prioChipContent()}
		<span class="ph-chip ph-chip--prio ph-chip--prio-{prioKey}">
			{#if project.prioridade && PRIO_ICON[project.prioridade]}
				<i class="fas {PRIO_ICON[project.prioridade]}" aria-hidden="true"></i>{PRIO_LABEL[
					project.prioridade
				]}
			{:else}
				Sem prioridade
			{/if}
			{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
		</span>
	{/snippet}

	{#snippet deliveryChipContent()}
		<span class="ph-chip ph-chip--delivery" data-value={project.delivery_type ?? ''}>
			<i class="fas fa-box" aria-hidden="true"></i>{project.delivery_type || 'Sem tipo'}
			{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
		</span>
	{/snippet}

	{#snippet specialChipContent()}
		<span class="ph-chip ph-chip--special" data-value={project.special_project ?? ''}>
			<i class="fas fa-star" aria-hidden="true"></i>{project.special_project || 'Sem categoria'}
			{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
		</span>
	{/snippet}
</header>

<!-- ===================== COMPACT HEADER (sticky) ===================== -->
<div
	class="project-compact-header"
	class:is-visible={compact}
	style={`--project-compact-top:${compactTop}px`}
	aria-hidden={compact ? 'false' : 'true'}
>
	<div class="project-compact-inner">
		<div class="project-compact-main">
			<h2 class="project-compact-title">{project.id} - {shownTitulo}</h2>
			{#if shownDescription}
				<p class="project-compact-description">{shownDescription}</p>
			{/if}
			<div class="project-compact-meta">
				<span class="pc-chip pc-chip--status pc-chip--status-{statusKey}">
					{#if project.status === 'Vigente'}
						<span class="pc-chip-dot" aria-hidden="true"></span>Vigente
					{:else if project.status === 'Finalizado'}
						<i class="fas fa-flag-checkered" aria-hidden="true"></i>Finalizado
					{:else if project.status === 'Suspenso'}
						<i class="fas fa-pause" aria-hidden="true"></i>Suspenso
					{:else}
						{project.status || 'Sem status'}
					{/if}
				</span>
				<span class="pc-chip pc-chip--prio pc-chip--prio-{prioKey}">
					{#if project.prioridade && PRIO_ICON[project.prioridade]}
						<i class="fas {PRIO_ICON[project.prioridade]}" aria-hidden="true"></i>{PRIO_LABEL[
							project.prioridade
						]}
					{:else}
						Sem prioridade
					{/if}
				</span>
				<span class="pc-chip" class:pc-chip--delivery={project.delivery_type}>
					<i class="fas fa-box" aria-hidden="true"></i>{project.delivery_type || 'Sem tipo'}
				</span>
				<span class="pc-chip" class:pc-chip--special={project.special_project}>
					<i class="fas fa-star" aria-hidden="true"></i>{project.special_project ||
						'Sem categoria'}
				</span>
				<span class="pc-chip"
					><i class="far fa-calendar-alt" aria-hidden="true"></i> Início: {startBr ||
						'Não definida'}</span
				>
				<span class="pc-chip"
					><i class="far fa-calendar-check" aria-hidden="true"></i> Fim: {endBr ||
						'Não definida'}</span
				>
				{#if durationLabel}
					<span class="pc-chip"
						><i class="far fa-hourglass" aria-hidden="true"></i> {durationLabel}</span
					>
				{/if}
			</div>
		</div>
		<a href={`${base}/projetos`} class="project-compact-back">
			<i class="fas fa-arrow-left" aria-hidden="true"></i>
			<span>Voltar</span>
		</a>
	</div>
</div>

<style>
	/* ----- Header glass ----- */
	.project-header {
		/* Caixa ÚNICA da descrição: chip "Adicionar descrição", texto exibido e editor
		   compartilham linha, padding e borda — mesma geometria nos três estados. */
		--ph-desc-line: 1.3125rem;
		--ph-desc-pad-y: 0.25rem;
		--ph-desc-pad-x: 0.45rem;
		--ph-desc-border: 1px;
		--ph-desc-box: calc(
			var(--ph-desc-line) + 2 * var(--ph-desc-pad-y) + 2 * var(--ph-desc-border)
		);
		position: relative;
		overflow: hidden;
		border-radius: 12px;
		/* Sem padding-bottom: a régua de abas encosta na base do header (o header
		   ganhou altura para comportar o seletor Detalhes/Etapas). */
		padding: 1.25rem 1.5rem 0;
		color: var(--ds-color-on-brand-strong);
		background: linear-gradient(
			135deg,
			color-mix(in srgb, var(--ds-color-surface-topnav) 95%, transparent) 0%,
			color-mix(in srgb, var(--ds-color-surface-topnav) 92%, transparent) 50%,
			color-mix(in srgb, var(--ds-color-surface-topnav) 92%, transparent) 100%
		);
		border: 1px solid var(--ds-color-on-brand-divider);
		box-shadow:
			0 8px 32px color-mix(in srgb, var(--ds-color-surface-topnav) 15%, transparent),
			inset 0 1px 0 var(--ds-color-on-brand-divider);
	}
	.project-header::before {
		content: '';
		position: absolute;
		inset: 0;
		background-image:
			radial-gradient(circle at 20% 80%, var(--ds-color-on-brand-hover) 1px, transparent 1px),
			radial-gradient(circle at 80% 20%, var(--ds-color-on-brand-hover) 1px, transparent 1px);
		background-size:
			50px 50px,
			80px 80px;
		opacity: 0.7;
		pointer-events: none;
	}

	.ph-main-row {
		position: relative;
		z-index: 1;
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.ph-main-content {
		flex: 1;
		min-width: 0;
		max-width: calc(100% - 120px);
	}
	/* Peso 600 e branco SÓLIDO (o degradê com clip de texto deixava o título
	   pesado/borrado); a família vem do base layer (Chivo, como todo heading). */
	.ph-title {
		margin: 0 0 0.12rem;
		font-weight: 600;
		font-size: 1.5rem;
		line-height: 1.25;
		color: var(--ds-color-on-brand-strong);
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 5;
		line-clamp: 5;
		overflow: hidden;
		overflow-wrap: anywhere;
	}
	.ph-description {
		margin: 0;
		color: var(--ds-color-on-brand-muted);
		font-size: 0.875rem;
		line-height: 1.5;
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 15;
		line-clamp: 15;
		overflow: hidden;
		white-space: pre-line;
		overflow-wrap: anywhere;
	}

	/* ----- Edição inline de título/descrição (lápis ⇄ ok) ----- */
	/* A LINHA (*-row) é só um contêiner flex. No TÍTULO, o prefixo "ID - " e o botão
	   ficam FORA da caixa; a caixa (.ph-title-field) envolve só o título editável. Na
	   DESCRIÇÃO a caixa (.ph-description-field) envolve o texto e usa margem-esquerda
	   negativa p/ alinhar aos chips sem salto (a moldura/box-shadow não desloca nada). */
	.ph-title-row,
	.ph-description-row {
		display: flex;
		align-items: flex-start;
		gap: 0.3rem;
		width: fit-content;
		max-width: 100%;
	}
	/* Slot da descrição: reserva SEMPRE a caixa de uma linha, então botão "Adicionar
	   descrição", texto exibido e editor ocupam o mesmo espaço — o header não muda de
	   tamanho ao entrar/sair da edição. */
	.ph-description-slot {
		display: flex;
		align-items: flex-start;
		margin-top: 0.35rem;
		min-height: var(--ph-desc-box);
	}
	/* Caixa do TÍTULO: só existe ao editar (envolve apenas o textarea), depois do
	   prefixo fixo. Pequeno padding p/ folga dentro da moldura. */
	.ph-title-field {
		display: flex;
		align-items: flex-start;
		min-width: 0;
		max-width: 100%;
		box-sizing: border-box;
		border-radius: 5px;
		padding: 0 0.3rem;
	}
	/* Caixa da DESCRIÇÃO: a MESMA caixa sempre — exibir e editar só trocam as cores da
	   borda/fundo, nunca a geometria. A borda é real (não box-shadow) para o chip vazio
	   poder repetir exatamente estas medidas; a margem negativa compensa padding+borda
	   e mantém o texto alinhado ao título e aos chips. */
	.ph-description-field {
		display: flex;
		align-items: flex-start;
		min-width: 0;
		max-width: 100%;
		box-sizing: border-box;
		border-radius: 5px;
		border: var(--ph-desc-border) solid transparent;
		padding: var(--ph-desc-pad-y) var(--ph-desc-pad-x);
		margin-left: calc(-1 * (var(--ph-desc-pad-x) + var(--ph-desc-border)));
		background: transparent;
		transition:
			background-color 0.18s ease,
			border-color 0.18s ease;
	}
	.ph-title-row > .ph-title,
	.ph-description-field .ph-description {
		flex: 0 1 auto;
		min-width: 0;
		margin: 0;
	}
	/* Moldura (shell) ao editar: borda via box-shadow p/ NÃO empurrar nada.
	   Tinta -muted (não -divider): com .ph-text-editor:focus em outline:none esta moldura
	   é o único indicador de foco, e precisa dos 3:1 de WCAG 1.4.11/2.4.11. */
	.ph-edit-shell {
		background: var(--ds-color-on-brand-hover);
		box-shadow: 0 0 0 1px var(--ds-color-on-brand-muted);
	}
	/* Em EDIÇÃO só as CORES mudam: a borda transparente que já existia vira visível e o
	   fundo acende. Zero mudança de padding/margem => zero salto de tamanho. */
	.ph-description-field.ph-edit-shell {
		border-color: var(--ds-color-on-brand-muted);
		box-shadow: none;
	}
	/* Prefixo "ID - " FIXO (não editável), FORA da caixa, na mesma posição/tipografia
	   do título. */
	.ph-title-id-prefix {
		flex-shrink: 0;
		color: var(--ds-color-on-brand-strong);
		font-size: 1.5rem;
		font-weight: 600;
		line-height: 1.25;
		white-space: pre;
	}
	/* Oculta o <h1> ao editar mantendo-o acessível (heading nível 1 + nome da
	   região via aria-labelledby) e FORA do fluxo p/ o textarea ocupar a linha. */
	.ph-visually-hidden {
		position: absolute !important;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
	/* Lápis/ok: FORA da caixa, MENOR e visível só no hover/foco (instrução do usuário).
	   Sem badge no repouso; o fundo circular aparece no hover. Ao editar vira um "ok"
	   branco com check escuro + leve "pop" — MESMO botão nos dois estados => troca
	   lápis⇄check suave. */
	.ph-edit-pen {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.4rem;
		height: 1.4rem;
		margin-top: 0.16rem;
		padding: 0;
		border: 0;
		border-radius: 5px;
		background: transparent;
		color: var(--ds-color-on-brand-muted);
		font-size: 0.6875rem;
		line-height: 1;
		cursor: pointer;
		opacity: 0;
		pointer-events: none;
		transition:
			opacity 0.16s ease,
			background-color 0.18s ease,
			color 0.18s ease,
			box-shadow 0.18s ease,
			transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
	}
	.ph-edit-pen--description {
		width: 1.25rem;
		height: 1.25rem;
		/* Centralizado VERTICALMENTE em relação à caixa da descrição (a linha
		   usa align-items: flex-start; sem isto o botão ficava acima do campo). */
		align-self: center;
		margin-top: 0;
		font-size: 0.6875rem;
	}
	/* Aparece só no hover/foco da linha. */
	.ph-title-row:hover .ph-edit-pen,
	.ph-title-row:focus-within .ph-edit-pen,
	.ph-description-row:hover .ph-edit-pen,
	.ph-description-row:focus-within .ph-edit-pen {
		opacity: 1;
		pointer-events: auto;
	}
	/* Fundo (badge) só no hover/foco — instrução do usuário. */
	.ph-edit-pen:hover,
	.ph-edit-pen:focus-visible {
		background: var(--ds-color-on-brand-hover-strong);
		color: var(--ds-color-on-brand-strong);
	}
	/* O fundo sozinho fica em 1,60:1 sobre a marca; o anel é o que entrega os 3:1
	   exigidos pelo WCAG 2.4.11 (e separa foco de hover). */
	.ph-edit-pen:focus-visible {
		outline: var(--ds-focus-ring-width) solid var(--ds-color-focus-ring-onbrand);
		outline-offset: var(--ds-focus-ring-offset);
	}
	/* Estado "confirmar" (editando): SEMPRE visível, leve — fundo translúcido
	   discreto (sem badge branco/sombra/pop) e canto mais quadrado. */
	.ph-edit-pen--confirm {
		opacity: 1;
		pointer-events: auto;
		background: var(--ds-color-on-brand-hover);
		color: var(--ds-color-on-brand-strong);
		border-radius: 5px;
		box-shadow: none;
		transform: none;
	}
	.ph-edit-pen--confirm:hover,
	.ph-edit-pen--confirm:focus-visible {
		background: var(--ds-color-on-brand-hover-strong);
	}
	.ph-edit-pen:disabled {
		cursor: default;
	}
	/* Touch / sem hover: mantém o lápis acessível (senão não dá p/ editar no toque). */
	@media (hover: none) {
		.ph-edit-pen {
			opacity: 1;
			pointer-events: auto;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.ph-title-field,
		.ph-description-field,
		.ph-edit-pen {
			transition-duration: 1ms;
		}
		.ph-edit-pen--confirm {
			transform: none;
		}
	}
	/* Sem ícone de caneta (só o texto) e raio igual ao do shell de edição,
	   para preview e edição terem o MESMO desenho de canto. */
	.ph-add-description {
		display: inline-flex;
		align-items: center;
		box-sizing: border-box;
		/* MESMAS medidas de .ph-description-field (padding, borda, margem negativa e
		   tipografia): o chip e o editor são a mesma caixa, só muda o traço da borda. */
		padding: var(--ph-desc-pad-y) var(--ph-desc-pad-x);
		margin-left: calc(-1 * (var(--ph-desc-pad-x) + var(--ph-desc-border)));
		border-radius: 5px;
		border: var(--ph-desc-border) dashed var(--ds-color-on-brand-divider);
		background: var(--ds-color-on-brand-hover);
		color: var(--ds-color-on-brand-muted);
		font-size: 0.875rem;
		line-height: var(--ph-desc-line);
		font-weight: 500;
		cursor: pointer;
		transition:
			background 0.16s ease,
			border-color 0.16s ease,
			color 0.16s ease;
	}
	.ph-add-description:hover {
		background: var(--ds-color-on-brand-hover-strong);
		border-color: var(--ds-color-on-brand-muted);
		color: var(--ds-color-on-brand-strong);
	}

	/* Editor: herda a tipografia do display; SEM moldura própria (o shell da linha é
	   quem desenha borda+fundo). A largura/altura crescem com o conteúdo (via JS). */
	.ph-text-editor {
		display: block;
		margin: 0;
		padding: 0;
		color: var(--ds-color-on-brand-strong);
		background: transparent;
		border: 0;
		font-family: inherit;
		box-sizing: border-box;
		overflow: hidden;
		overflow-wrap: anywhere;
		white-space: pre-wrap;
		resize: none;
	}
	.ph-text-editor:focus {
		outline: none;
	}
	.ph-text-editor::placeholder {
		color: var(--ds-color-on-brand-muted);
	}
	.ph-text-editor--title {
		max-width: 100%;
		/* Mesma família dos headings (o inherit pegaria a fonte do corpo). */
		font-family: 'ChivoVariable', 'Chivo', system-ui, sans-serif;
		font-size: 1.5rem;
		font-weight: 600;
		line-height: 1.25;
	}
	.ph-text-editor--description {
		max-width: 100%;
		font-size: 0.875rem;
		font-weight: 400;
		line-height: 1.5;
	}
	.ph-text-error {
		margin: 0.25rem 0 0;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--ds-color-danger-200);
	}

	/* Badge "Convidado": acesso por convite (access_via), sobre o header glass. */
	.ph-guest-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		align-self: flex-start;
		margin-bottom: 0.4rem;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ds-color-on-brand-strong);
		background: var(--ds-color-on-brand-hover);
		border: 1px solid var(--ds-color-on-brand-divider);
	}

	.ph-header-actions {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
		margin-left: 0.75rem;
	}

	.ph-back-button {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
		padding: 0.4rem 0.85rem;
		font-family: inherit;
		cursor: pointer;
		border-radius: 8px;
		font-size: 0.8125rem;
		font-weight: 600;
		text-decoration: none;
		color: var(--ds-color-on-brand-strong);
		background: var(--ds-color-on-brand-hover);
		border: 1px solid var(--ds-color-on-brand-divider);
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease;
	}
	.ph-back-button:hover {
		background: var(--ds-color-on-brand-hover-strong);
		border-color: var(--ds-color-on-brand-muted);
	}

	/* ----- Chips ----- */
	.project-header-chips {
		position: relative;
		z-index: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.42rem 0.5rem;
		margin-top: 1.5rem;
	}

	/* Campo do cabeçalho: legenda minimalista (título) que SÓ aparece ao passar o
	   mouse / focar AQUELE campo. Posicionada em absoluto p/ não empurrar o chip
	   (sem reserva de espaço nem salto de layout). */
	.ph-field {
		position: relative;
		display: inline-flex;
		flex-direction: column;
	}
	.ph-field-label {
		position: absolute;
		bottom: 100%;
		left: 0;
		margin-bottom: 0.2rem;
		padding-left: 0.15rem;
		font-size: 0.6875rem;
		font-weight: 700;
		line-height: 1;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		white-space: nowrap;
		color: var(--ds-color-on-brand-muted);
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.16s ease;
	}
	.ph-field:hover .ph-field-label,
	.ph-field:focus-within .ph-field-label {
		opacity: 1;
	}
	@media (prefers-reduced-motion: reduce) {
		.ph-field-label {
			transition-duration: 1ms;
		}
	}
	/* Só no CLARO: aqui o header é superfície invertida (azul primary-700) e a régua
	   clara não serve — sobre o chip (#1c5779) ela mede 1,11:1 a 1,87:1. No escuro o
	   header é carvão e a régua global já é dessa superfície (6,3:1 a 12:1), e
	   sobrescrevê-la aqui dessincronizava o ícone do chip do ponto do dropdown.
	   Escopo é .ph-chip e não .project-header de propósito: o painel do SelectMenu é
	   descendente do header e herdaria estes valores sobre fundo claro. */
	:global(:root:not([data-theme='dark'])) .ph-chip {
		--ds-color-priority-baixa: var(--ds-color-neutral-400);
		--ds-color-priority-media: var(--ds-color-danger-400);
		--ds-color-priority-alta: var(--ds-color-danger-300);
		--ds-color-priority-urgente: var(--ds-color-danger-200);
		--ds-color-text-brand: var(--ds-color-primary-300);
		--ds-color-text-warning: var(--ds-color-warning-300);
		--ds-color-text-attention: var(--ds-color-attention-300);
		--ds-color-fill-success: var(--ds-color-success-300);
	}
	.ph-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.42rem;
		padding: 0.36rem 0.7rem;
		border-radius: 6px;
		background: color-mix(in srgb, var(--ds-color-neutral-1000) 8%, transparent);
		border: 1px solid var(--ds-color-on-brand-divider);
		color: var(--ds-color-on-brand-strong);
		font-size: 0.75rem;
		font-weight: 600;
		line-height: 1;
		white-space: nowrap;
	}
	/* Wrapper do chip editável: o SelectMenu unstyled usa o chip como trigger. */
	.ph-chip-wrap {
		position: relative;
		display: inline-flex;
		/* Anel azul sobre header azul dá 1,87:1; o contexto de marca pede anel branco. */
		--ds-color-focus-ring-context: var(--ds-color-focus-ring-onbrand);
	}
	.ph-chip-wrap--editable .ph-chip {
		cursor: pointer;
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease;
	}
	/* O hover APROFUNDA o chip (8% → 16% de neutral-1000) em vez de clareá-lo: clarear
	   derrubava a tinta dos ícones abaixo de 3:1 justamente sob o ponteiro. */
	.ph-chip-wrap--editable:hover .ph-chip,
	.ph-chip-wrap:focus-within .ph-chip {
		background: color-mix(in srgb, var(--ds-color-neutral-1000) 16%, transparent);
		border-color: var(--ds-color-on-brand-muted);
	}
	/* .ph-chip .ph-chip-caret (0,2,0) vence .ph-chip i (0,1,1) sem !important. */
	.ph-chip .ph-chip-caret {
		margin-left: 0.05rem;
		font-size: 0.6875rem;
		color: var(--ds-color-on-brand-muted) !important;
		opacity: 0;
		transition: opacity 0.16s ease;
	}
	.ph-chip-wrap--editable:hover .ph-chip-caret,
	.ph-chip-wrap:focus-within .ph-chip-caret {
		opacity: 1;
	}
	.ph-chip i {
		font-size: 0.75rem;
	}
	.ph-chip-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--ds-color-fill-success);
		box-shadow: 0 0 0 2px color-mix(in srgb, var(--ds-color-fill-success) 35%, transparent);
	}
	.ph-chip--status-suspenso {
		background: color-mix(in srgb, var(--ds-color-warning-500) 32%, transparent);
		border-color: color-mix(in srgb, var(--ds-color-warning-500) 65%, transparent);
	}
	.ph-chip--prio-urgente i {
		color: var(--ds-color-priority-urgente);
	}
	.ph-chip--prio-alta i {
		color: var(--ds-color-priority-alta);
	}
	.ph-chip--prio-media i {
		color: var(--ds-color-priority-media);
	}
	.ph-chip--prio-baixa i {
		color: var(--ds-color-priority-baixa);
	}
	.ph-chip--delivery[data-value]:not([data-value='']) i {
		color: var(--ds-color-text-brand);
	}
	/* attention (5ª família) e não warning: warning já é "suspenso" no mesmo par de chips. */
	.ph-chip--special[data-value]:not([data-value='']) i {
		color: var(--ds-color-text-attention);
	}

	.ph-chip-dates {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.35rem 0.18rem 0.35rem 0.4rem;
		color: var(--ds-color-on-brand-strong);
		font-size: 0.8125rem;
		line-height: 1;
	}
	.ph-chip-dates > i {
		font-size: 0.875rem;
		color: var(--ds-color-on-brand-muted);
	}
	.ph-date-range {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-variant-numeric: tabular-nums;
	}
	.ph-date-arrow {
		color: var(--ds-color-on-brand-muted);
		margin: 0 0.05rem;
	}
	.ph-date-sep {
		color: var(--ds-color-on-brand-muted);
		user-select: none;
	}
	.ph-duration {
		color: var(--ds-color-on-brand-strong);
		font-weight: 700;
	}

	/* ----- Abas Detalhes/Etapas (base do header) ----- */
	.ph-tabs {
		position: relative;
		z-index: 1;
		display: flex;
		gap: 0.25rem;
		margin-top: 1.1rem;
		border-top: 1px solid var(--ds-color-on-brand-divider);
	}
	.ph-tab {
		position: relative;
		border: 0;
		background: transparent;
		cursor: pointer;
		padding: 0.7rem 1rem 0.8rem;
		font-family: inherit;
		font-size: 0.875rem;
		font-weight: 600;
		line-height: 1;
		color: var(--ds-color-on-brand-muted);
		transition:
			color 0.16s ease,
			background-color 0.16s ease;
	}
	.ph-tab:hover {
		color: var(--ds-color-on-brand-strong);
		background: var(--ds-color-on-brand-hover);
	}
	.ph-tab:focus-visible {
		outline: var(--ds-focus-ring-width) solid var(--ds-color-focus-ring-onbrand);
		outline-offset: calc(-1 * var(--ds-focus-ring-width));
	}
	.ph-tab--active {
		color: var(--ds-color-on-brand-strong);
	}
	.ph-tab--active::after {
		content: '';
		position: absolute;
		left: 0.55rem;
		right: 0.55rem;
		bottom: 0;
		height: 2.5px;
		border-radius: 999px 999px 0 0;
		background: var(--ds-color-on-brand-strong);
	}
	@media (prefers-reduced-motion: reduce) {
		.ph-tab {
			transition-duration: 1ms;
		}
	}

	/* ----- Compact header ----- */
	.project-compact-header {
		position: fixed;
		top: var(--project-compact-top, 74px);
		left: 1rem;
		right: 1rem;
		z-index: 40;
		opacity: 0;
		transform: translateY(-10px) scale(0.985);
		pointer-events: none;
		transition:
			opacity 0.22s ease,
			transform 0.24s cubic-bezier(0.4, 0, 0.2, 1);
		will-change: opacity, transform;
	}
	.project-compact-header.is-visible {
		opacity: 1;
		transform: translateY(0) scale(1);
		pointer-events: auto;
	}
	.project-compact-inner {
		width: min(1080px, calc((100vw - 2rem) * 0.85));
		margin: 0 auto;
		border-radius: 12px;
		border: 1px solid color-mix(in srgb, var(--ds-color-border-brand-soft) 90%, transparent);
		background: color-mix(in srgb, var(--ds-color-wash-brand) 96%, transparent);
		backdrop-filter: blur(14px);
		-webkit-backdrop-filter: blur(14px);
		box-shadow: 0 10px 24px color-mix(in srgb, var(--ds-color-surface-topnav) 18%, transparent);
		padding: 0.55rem 0.8rem;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.85rem;
	}
	:global([data-theme='dark']) .project-compact-inner {
		background: var(--ds-color-surface-raised);
		border-color: var(--ds-color-border-base);
		box-shadow: 0 10px 24px color-mix(in srgb, var(--ds-color-neutral-1000) 40%, transparent);
	}
	.project-compact-main {
		min-width: 0;
		flex: 1;
	}
	.project-compact-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: var(--ds-color-text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.project-compact-description {
		margin: 0.3rem 0 0;
		font-size: 0.875rem;
		color: var(--ds-color-text-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.project-compact-meta {
		margin-top: 0.6rem;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.45rem;
	}
	.pc-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		border: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-secondary);
		border-radius: 6px;
		padding: 0.18rem 0.55rem;
		font-size: 0.6875rem;
		font-weight: 600;
		line-height: 1;
		white-space: nowrap;
	}
	.pc-chip i {
		font-size: 0.6875rem;
	}
	.pc-chip-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--ds-color-fill-success);
	}
	.pc-chip--status-suspenso i {
		color: var(--ds-color-text-warning);
	}
	.pc-chip--prio-urgente i {
		color: var(--ds-color-priority-urgente);
	}
	.pc-chip--prio-alta i {
		color: var(--ds-color-priority-alta);
	}
	.pc-chip--prio-media i {
		color: var(--ds-color-priority-media);
	}
	.pc-chip--prio-baixa i {
		color: var(--ds-color-priority-baixa);
	}
	.pc-chip--delivery i {
		color: var(--ds-color-text-brand);
	}
	/* Mesma decisão do header expandido: attention separa "especial" de suspenso (warning). */
	.pc-chip--special i {
		color: var(--ds-color-text-attention);
	}
	.project-compact-back {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border-radius: 8px;
		padding: 0.38rem 0.74rem;
		font-size: 0.6875rem;
		font-weight: 600;
		border: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-base);
		color: var(--ds-color-text-primary);
		text-decoration: none;
		white-space: nowrap;
		transition:
			background 0.16s ease,
			color 0.16s ease;
	}
	/* O fundo sozinho dá 1,07:1 no claro — é a troca de tinta que torna o hover visível. */
	.project-compact-back:hover {
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-brand);
	}
	:global([data-theme='dark']) .project-compact-back {
		background: var(--ds-color-surface-muted);
		border-color: var(--ds-color-border-base);
		color: var(--ds-color-text-primary);
	}
	:global([data-theme='dark']) .project-compact-back:hover {
		background: var(--ds-color-surface-raised);
		color: var(--ds-color-text-brand);
	}

	@media (max-width: 991.98px) {
		.project-compact-header {
			display: none;
		}
	}
</style>
