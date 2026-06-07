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
	 *
	 * CONTROLADO: recebe `project` + `options` + `permissions` + `derivedData`; emite
	 * `onEditField(field, value)` — NÃO chama API.
	 */
	import { tick } from 'svelte';
	import { stickyHeader } from '$lib/actions/stickyHeader';
	import type {
		ProjectDetail,
		ProjectDetailOptions,
		ProjectDetailPermissions,
		ProjectDetailDerived
	} from '$lib/types/projectDetail';
	import { base } from '$app/paths';

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
		onEditField: (field: HeaderField, value: string) => void;
	}

	let {
		project,
		options,
		permissions,
		derivedData,
		topOffset = 0,
		fieldStates = {},
		onEditField
	}: Props = $props();

	let compact = $state(false);
	const canEdit = $derived(permissions.can_edit);

	// Folga (px) entre a base do topnav e o header compacto, para que ele não
	// fique colado no topo. O GATILHO usa `topOffset` puro (sincronia exata com
	// o sumiço do header); só a POSIÇÃO do compacto recebe esta folga.
	const COMPACT_TOP_GAP = 12;
	const compactTop = $derived(topOffset + COMPACT_TOP_GAP);

	// --- Edição inline de chip (status/prioridade/tipo/especial) -------------
	// Um <select> nativo INVISÍVEL fica sobreposto ao chip: o clique cai direto
	// no select e o dropdown nativo abre de primeira (sem swap de elemento nem
	// timing de showPicker, que exigia cliques extras). O chip estilizado por
	// baixo dá o visual rico (ícone/cor); o select por cima captura o clique.
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
	function measureTextWidth(ta: HTMLTextAreaElement): number {
		const style = window.getComputedStyle(ta);
		measureCanvas ??= document.createElement('canvas');
		const ctx = measureCanvas.getContext('2d');
		if (!ctx) return 240;
		ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
		const text = ta.value || ta.placeholder || '';
		const longest = text
			.split(/\r?\n/)
			.reduce((max, line) => Math.max(max, ctx.measureText(line || ' ').width), 0);
		return Math.ceil(longest + 26);
	}

	// Título E descrição abraçam o conteúdo (paridade v4.5). A LARGURA é ajustada
	// PRIMEIRO e só então a ALTURA — assim a caixa cresce/encolhe junto com o texto e
	// NÃO sobra espaço embaixo quando o conteúdo cabe em menos linhas que a largura
	// inicial. O teto é o espaço livre à direita do textarea: medimos o quanto já foi
	// consumido à esquerda dele (ex.: o prefixo fixo "ID - " do título) e reservamos
	// uma folga p/ o botão lápis/ok, que agora fica FORA da caixa.
	function autoSizeText(): void {
		const ta = textEditorEl;
		if (!ta) return;
		const container = ta.closest('.ph-main-content');
		if (container) {
			const cRect = (container as HTMLElement).getBoundingClientRect();
			// `left` do textarea não depende da sua largura (alinhado à esquerda) =>
			// mede com segurança o que está à esquerda (prefixo + paddings da caixa).
			const leftConsumed = ta.getBoundingClientRect().left - cRect.left;
			const cap = Math.max(72, Math.floor(cRect.width - leftConsumed - 60));
			const measured = measureTextWidth(ta);
			ta.style.width = `${Math.min(cap, Math.max(72, measured))}px`;
		} else {
			ta.style.width = `${Math.max(72, measureTextWidth(ta))}px`;
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
		textEditorEl?.select();
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
			     p/ o botão morfar suave pen<->check; vazia => "Adicionar descrição". -->
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
					<i class="fas fa-pen" aria-hidden="true"></i>Adicionar descrição
				</button>
			{/if}
			{#if fieldStates.short_description?.error}
				<p id="project-desc-error" class="ph-text-error" role="alert">
					{fieldStates.short_description.error}
				</p>
			{/if}
		</div>
		<a href={`${base}/projetos`} class="ph-back-button">
			<i class="fas fa-arrow-left" aria-hidden="true"></i>
			<span>Voltar</span>
		</a>
	</div>

	<div class="project-header-chips">
		<!-- Status (editável inline: select nativo invisível sobre o chip) -->
		<div class="ph-field">
			<span class="ph-field-label">Status</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				<span
					class="ph-chip ph-chip--status ph-chip--status-{statusKey}"
					data-value={project.status ?? ''}
				>
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
				{#if canEdit}
					<select
						class="ph-chip-overlay"
						aria-label="Status do projeto"
						onchange={(e) => selectChip('status', e.currentTarget.value)}
					>
						{#each options.status as opt (opt.value)}
							<option value={opt.value} selected={opt.value === (project.status ?? '')}
								>{opt.label}</option
							>
						{/each}
					</select>
				{/if}
			</div>
		</div>

		<!-- Prioridade (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Prioridade</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
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
				{#if canEdit}
					<select
						class="ph-chip-overlay"
						aria-label="Prioridade do projeto"
						onchange={(e) => selectChip('prioridade', e.currentTarget.value)}
					>
						<option value="" selected={!project.prioridade}>Sem prioridade</option>
						{#each options.prioridade as opt (opt.value)}
							<option value={opt.value} selected={opt.value === project.prioridade}>{opt.label}</option>
						{/each}
					</select>
				{/if}
			</div>
		</div>

		<!-- Tipo de entrega (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Tipo de entrega</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				<span class="ph-chip ph-chip--delivery" data-value={project.delivery_type ?? ''}>
					<i class="fas fa-box" aria-hidden="true"></i>{project.delivery_type || 'Sem tipo'}
					{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
				</span>
				{#if canEdit}
					<select
						class="ph-chip-overlay"
						aria-label="Tipo de entrega do projeto"
						onchange={(e) => selectChip('delivery_type', e.currentTarget.value)}
					>
						<option value="" selected={!project.delivery_type}>Sem tipo</option>
						{#each options.delivery_type as opt (opt)}
							<option value={opt} selected={opt === project.delivery_type}>{opt}</option>
						{/each}
					</select>
				{/if}
			</div>
		</div>

		<!-- Projeto especial (editável inline) -->
		<div class="ph-field">
			<span class="ph-field-label">Projeto especial</span>
			<div class="ph-chip-wrap" class:ph-chip-wrap--editable={canEdit}>
				<span class="ph-chip ph-chip--special" data-value={project.special_project ?? ''}>
					<i class="fas fa-star" aria-hidden="true"></i>{project.special_project || 'Sem categoria'}
					{#if canEdit}<i class="ph-chip-caret fas fa-chevron-down" aria-hidden="true"></i>{/if}
				</span>
				{#if canEdit}
					<select
						class="ph-chip-overlay"
						aria-label="Projeto especial"
						onchange={(e) => selectChip('special_project', e.currentTarget.value)}
					>
						<option value="" selected={!project.special_project}>Sem categoria</option>
						{#each options.special_project as opt (opt)}
							<option value={opt} selected={opt === project.special_project}>{opt}</option>
						{/each}
					</select>
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
		position: relative;
		overflow: hidden;
		border-radius: 12px;
		padding: 1.25rem 1.5rem;
		color: #fff;
		background: linear-gradient(
			135deg,
			rgba(0, 90, 146, 0.95) 0%,
			rgba(0, 75, 121, 0.92) 50%,
			rgba(0, 90, 146, 0.88) 100%
		);
		border: 1px solid rgba(255, 255, 255, 0.1);
		box-shadow:
			0 8px 32px rgba(0, 90, 146, 0.15),
			inset 0 1px 0 rgba(255, 255, 255, 0.2);
	}
	.project-header::before {
		content: '';
		position: absolute;
		inset: 0;
		background-image:
			radial-gradient(circle at 20% 80%, rgba(255, 255, 255, 0.1) 1px, transparent 1px),
			radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.08) 1px, transparent 1px);
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
	.ph-title {
		margin: 0 0 0.12rem;
		font-weight: 700;
		font-size: 1.5rem;
		line-height: 1.2;
		background: linear-gradient(135deg, #ffffff 0%, rgba(255, 255, 255, 0.9) 100%);
		-webkit-background-clip: text;
		background-clip: text;
		-webkit-text-fill-color: transparent;
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 5;
		line-clamp: 5;
		overflow: hidden;
		overflow-wrap: anywhere;
	}
	.ph-description {
		margin: 0;
		opacity: 0.9;
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
	/* Caixa do TÍTULO: só existe ao editar (envolve apenas o textarea), depois do
	   prefixo fixo. Pequeno padding p/ folga dentro da moldura. */
	.ph-title-field {
		display: flex;
		align-items: flex-start;
		min-width: 0;
		max-width: 100%;
		box-sizing: border-box;
		border-radius: 9px;
		padding: 0 0.3rem;
	}
	/* Caixa da DESCRIÇÃO: persiste exibir/editar; margem-esquerda negativa mantém o
	   texto alinhado aos chips e a moldura aparece sem salto. */
	.ph-description-field {
		display: flex;
		align-items: flex-start;
		min-width: 0;
		max-width: 100%;
		box-sizing: border-box;
		border-radius: 9px;
		padding: 0 0.32rem;
		margin-left: -0.32rem;
		background: transparent;
		box-shadow: 0 0 0 1px transparent;
		transition:
			background-color 0.18s ease,
			box-shadow 0.18s ease;
	}
	.ph-title-row > .ph-title,
	.ph-description-field .ph-description {
		flex: 0 1 auto;
		min-width: 0;
		margin: 0;
	}
	/* Moldura (shell) ao editar: borda via box-shadow p/ NÃO empurrar nada. */
	.ph-edit-shell {
		background: rgba(255, 255, 255, 0.08);
		box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.5);
	}
	/* Prefixo "ID - " FIXO (não editável), FORA da caixa, na mesma posição/tipografia
	   do título. */
	.ph-title-id-prefix {
		flex-shrink: 0;
		color: #fff;
		font-size: 1.5rem;
		font-weight: 700;
		line-height: 1.2;
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
		border-radius: 50%;
		background: transparent;
		color: rgba(255, 255, 255, 0.82);
		font-size: 0.6rem;
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
		margin-top: 0.02rem;
		font-size: 0.54rem;
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
		background: rgba(255, 255, 255, 0.2);
		color: #fff;
		outline: none;
	}
	/* Estado "confirmar" (editando): SEMPRE visível, botão branco com check escuro. */
	.ph-edit-pen--confirm {
		opacity: 1;
		pointer-events: auto;
		background: #fff;
		color: #14365a;
		box-shadow: 0 2px 8px rgba(0, 20, 40, 0.28);
		transform: scale(1.06);
	}
	.ph-edit-pen--confirm:hover,
	.ph-edit-pen--confirm:focus-visible {
		background: #eaf3ff;
		color: #0f2c4a;
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
	.ph-add-description {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin-top: 0.1rem;
		padding: 0.18rem 0.55rem;
		border-radius: 6px;
		border: 1px dashed rgba(255, 255, 255, 0.32);
		background: rgba(255, 255, 255, 0.06);
		color: rgba(255, 255, 255, 0.82);
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		transition:
			background 0.16s ease,
			border-color 0.16s ease,
			color 0.16s ease;
	}
	.ph-add-description:hover {
		background: rgba(255, 255, 255, 0.15);
		border-color: rgba(255, 255, 255, 0.5);
		color: #fff;
	}

	/* Editor: herda a tipografia do display; SEM moldura própria (o shell da linha é
	   quem desenha borda+fundo). A largura/altura crescem com o conteúdo (via JS). */
	.ph-text-editor {
		display: block;
		margin: 0;
		padding: 0;
		color: #fff;
		background: transparent;
		border: 0;
		font-family: inherit;
		box-sizing: border-box;
		overflow: hidden;
		overflow-wrap: anywhere;
		white-space: pre-wrap;
		resize: none;
		transition:
			width 0.12s ease,
			height 0.12s ease;
	}
	.ph-text-editor:focus {
		outline: none;
	}
	.ph-text-editor::placeholder {
		color: rgba(255, 255, 255, 0.6);
	}
	.ph-text-editor--title {
		max-width: 100%;
		font-size: 1.5rem;
		font-weight: 700;
		line-height: 1.2;
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
		color: #fecaca;
	}

	.ph-back-button {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
		margin-left: 0.75rem;
		padding: 0.4rem 0.85rem;
		border-radius: 8px;
		font-size: 0.82rem;
		font-weight: 600;
		text-decoration: none;
		color: #fff;
		background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0.1) 100%);
		border: 1px solid rgba(255, 255, 255, 0.25);
		transition: background 0.16s ease;
	}
	.ph-back-button:hover {
		background: rgba(255, 255, 255, 0.28);
	}

	/* ----- Chips ----- */
	.project-header-chips {
		position: relative;
		z-index: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.42rem 0.5rem;
		margin-top: 0.95rem;
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
		font-size: 0.58rem;
		font-weight: 700;
		line-height: 1;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		white-space: nowrap;
		color: rgba(255, 255, 255, 0.7);
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
	.ph-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.42rem;
		padding: 0.36rem 0.7rem;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.08);
		border: 1px solid rgba(255, 255, 255, 0.2);
		color: #fff;
		font-size: 0.78rem;
		font-weight: 600;
		line-height: 1;
		white-space: nowrap;
	}
	/* Wrapper do chip editável: um <select> invisível por cima captura o clique
	   e abre o dropdown nativo de primeira (sem swap de elemento). */
	.ph-chip-wrap {
		position: relative;
		display: inline-flex;
	}
	.ph-chip-wrap--editable .ph-chip {
		cursor: pointer;
		transition:
			background 0.16s ease,
			border-color 0.16s ease;
	}
	.ph-chip-wrap--editable:hover .ph-chip,
	.ph-chip-wrap:focus-within .ph-chip {
		background: rgba(255, 255, 255, 0.2);
		border-color: rgba(255, 255, 255, 0.4);
	}
	.ph-chip-overlay {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		margin: 0;
		padding: 0;
		border: 0;
		opacity: 0;
		cursor: pointer;
		font: inherit;
	}
	/* Popup nativo legível (o select em si fica invisível, mas as opções não). */
	.ph-chip-overlay option {
		color: #1f2d3d;
		background-color: #fff;
	}
	.ph-chip-caret {
		margin-left: 0.05rem;
		font-size: 0.55rem !important;
		color: rgba(255, 255, 255, 0.7) !important;
		opacity: 0;
		transition: opacity 0.16s ease;
	}
	.ph-chip-wrap--editable:hover .ph-chip-caret,
	.ph-chip-wrap:focus-within .ph-chip-caret {
		opacity: 1;
	}
	.ph-chip i {
		font-size: 0.74rem;
		opacity: 0.92;
	}
	.ph-chip-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: #10b981;
		box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.35);
	}
	.ph-chip--status-suspenso {
		background: rgba(234, 88, 12, 0.32);
		border-color: rgba(234, 88, 12, 0.65);
	}
	.ph-chip--prio-urgente i {
		color: #ef4444;
	}
	.ph-chip--prio-alta i {
		color: #f97316;
	}
	.ph-chip--prio-media i {
		color: #f59e0b;
	}
	.ph-chip--prio-baixa i {
		color: #22c55e;
	}
	.ph-chip--delivery[data-value]:not([data-value='']) i {
		color: #3b82f6;
	}
	.ph-chip--special[data-value]:not([data-value='']) i {
		color: #8b5cf6;
	}

	.ph-chip-dates {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.35rem 0.18rem 0.35rem 0.4rem;
		color: rgba(255, 255, 255, 0.92);
		font-size: 0.82rem;
		line-height: 1;
	}
	.ph-chip-dates > i {
		font-size: 0.92rem;
		opacity: 0.85;
	}
	.ph-date-range {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-variant-numeric: tabular-nums;
	}
	.ph-date-arrow {
		color: rgba(255, 255, 255, 0.55);
		margin: 0 0.05rem;
	}
	.ph-date-sep {
		color: rgba(255, 255, 255, 0.4);
		user-select: none;
	}
	.ph-duration {
		color: #fff;
		font-weight: 700;
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
		border: 1px solid rgba(183, 213, 242, 0.9);
		background: rgba(233, 244, 255, 0.96);
		backdrop-filter: blur(14px);
		-webkit-backdrop-filter: blur(14px);
		box-shadow: 0 10px 24px rgba(37, 87, 138, 0.18);
		padding: 0.55rem 0.8rem;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.85rem;
	}
	.project-compact-main {
		min-width: 0;
		flex: 1;
	}
	.project-compact-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: #1f2f45;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.project-compact-description {
		margin: 0.3rem 0 0;
		font-size: 0.875rem;
		color: #4f6680;
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
		border: 1px solid #d8e6f4;
		background: #f4f9ff;
		color: #45617f;
		border-radius: 999px;
		padding: 0.18rem 0.55rem;
		font-size: 0.72rem;
		font-weight: 600;
		line-height: 1;
		white-space: nowrap;
	}
	.pc-chip i {
		font-size: 0.62rem;
		opacity: 0.92;
	}
	.pc-chip-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: #16a34a;
	}
	.pc-chip--status-suspenso i {
		color: #9a6212;
	}
	.pc-chip--prio-urgente i {
		color: #b42323;
	}
	.pc-chip--prio-alta i {
		color: #b45309;
	}
	.pc-chip--prio-media i {
		color: #8f6200;
	}
	.pc-chip--prio-baixa i {
		color: #167a44;
	}
	.pc-chip--delivery i {
		color: #1e40af;
	}
	.pc-chip--special i {
		color: #6d28d9;
	}
	.project-compact-back {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border-radius: 8px;
		padding: 0.38rem 0.74rem;
		font-size: 0.72rem;
		font-weight: 600;
		border: 1px solid #d7e4f1;
		background: #fff;
		color: #415970;
		text-decoration: none;
		white-space: nowrap;
		transition: background 0.16s ease;
	}
	.project-compact-back:hover {
		background: #f4f8fc;
		color: #2f455d;
	}

	@media (max-width: 991.98px) {
		.project-compact-header {
			display: none;
		}
	}
</style>
