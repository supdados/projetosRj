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
	import { stickyHeader } from '$lib/actions/stickyHeader';
	import type {
		ProjectDetail,
		ProjectDetailOptions,
		ProjectDetailPermissions,
		ProjectDetailDerived
	} from '$lib/types/projectDetail';
	import { base } from '$app/paths';

	type HeaderField = 'titulo' | 'status' | 'prioridade' | 'delivery_type' | 'special_project';

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
			<h1 id="project-detail-title" class="ph-title">{project.id} - {project.titulo}</h1>
			{#if project.short_description}
				<p class="ph-description">{project.short_description}</p>
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
			<h2 class="project-compact-title">{project.id} - {project.titulo}</h2>
			{#if project.short_description}
				<p class="project-compact-description">{project.short_description}</p>
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
		overflow: hidden;
		white-space: pre-line;
		overflow-wrap: anywhere;
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
