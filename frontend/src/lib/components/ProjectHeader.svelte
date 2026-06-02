<script lang="ts">
	/**
	 * Cabeçalho do Detalhe de Projeto — sticky/compacto ao rolar.
	 *
	 * Referências visuais: templates/projects/detail.html (cabeçalho principal +
	 * cabeçalho compacto) e static/js/.../detail/10-compact-header.js (comportamento
	 * de compactar). Aqui o compactar é feito por `use:stickyHeader` sobre um
	 * sentinela; quando o sentinela sai da viewport, o cabeçalho vira compacto.
	 *
	 * CONTROLADO: recebe `project` + `options` + `permissions` e emite callbacks de
	 * edição inline (status/prioridade/título) via `onEditField` — NÃO chama API. A
	 * página orquestra a chamada e devolve o estado atualizado. Edição inline de
	 * campos individuais usa <InlineEditField>; aqui o título e os seletores de
	 * status/prioridade ficam no cabeçalho.
	 *
	 * Acessibilidade: heading de nível 1 para o título; status/prioridade com
	 * Badge; região rotulada; sentinela aria-hidden. Datas derivadas (read-only)
	 * via <time datetime>.
	 */
	import { stickyHeader } from '$lib/actions/stickyHeader';
	import Badge from './Badge.svelte';
	import InlineEditField from './InlineEditField.svelte';
	import type {
		ProjectDetail,
		ProjectDetailOptions,
		ProjectDetailPermissions,
		ProjectDetailDerived
	} from '$lib/types/projectDetail';

	type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';
	/** Campos editáveis pelo cabeçalho (subconjunto do projeto). */
	type HeaderField = 'titulo' | 'status' | 'prioridade';

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
		/** Estados pending/erro por campo, controlados pela página. */
		fieldStates?: Partial<Record<HeaderField, FieldState>>;
		/** Emite a intenção de salvar um campo; a página chama a API. */
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

	const statusTone: Record<string, Tone> = {
		Vigente: 'primary',
		Finalizado: 'success',
		Suspenso: 'warning'
	};

	const prioridadeTone: Record<string, Tone> = {
		baixa: 'neutral',
		media: 'info',
		alta: 'warning',
		urgente: 'danger'
	};

	const prioridadeLabel: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};

	const orgaoLabel = $derived(project.orgao_sigla ?? project.orgao ?? 'Não informado');

	function tone(map: Record<string, Tone>, key: string | null): Tone {
		return (key && map[key]) || 'neutral';
	}

	function fieldStateFor(field: HeaderField): FieldState {
		return fieldStates[field] ?? {};
	}

	/** Formata data ISO (YYYY-MM-DD) em pt-BR; vazio vira travessão. */
	function formatDateBr(iso: string | null): string {
		if (!iso) return '—';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '—';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}
</script>

<!-- Sentinela: enquanto visível, o cabeçalho fica expandido; ao sair, compacta. -->
<div
	aria-hidden="true"
	class="h-px w-full"
	use:stickyHeader={{ topOffset, onChange: (isCompact) => (compact = isCompact) }}
></div>

<header
	aria-labelledby="project-detail-title"
	class="sticky top-0 z-20 flex flex-col gap-3 border-b border-border-subtle bg-surface px-5 transition-[padding] duration-fast {compact
		? 'py-2'
		: 'py-4'}"
	style={`top: ${topOffset}px`}
	data-compact={compact ? 'true' : 'false'}
>
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div class="flex min-w-0 flex-col gap-1">
			{#if canEdit}
				<div class="flex items-center gap-2">
					<h1
						id="project-detail-title"
						class="truncate font-heading font-bold text-text-primary {compact
							? 'text-lg'
							: 'text-2xl'}"
					>
						{project.titulo}
					</h1>
				</div>
				{#if !compact}
					<InlineEditField
						fieldId="project-titulo"
						label="Título do projeto"
						value={project.titulo}
						kind="text"
						pending={fieldStateFor('titulo').pending}
						error={fieldStateFor('titulo').error}
						onSave={(v) => onEditField('titulo', v)}
					/>
				{/if}
			{:else}
				<h1
					id="project-detail-title"
					class="truncate font-heading font-bold text-text-primary {compact
						? 'text-lg'
						: 'text-2xl'}"
				>
					{project.titulo}
				</h1>
			{/if}

			{#if !compact}
				<p class="text-xs text-text-muted">
					Órgão: <strong class="font-medium text-text-secondary">{orgaoLabel}</strong>
				</p>
			{/if}
		</div>

		<div class="flex flex-wrap items-center gap-2">
			<Badge tone={tone(statusTone, project.status)}>{project.status}</Badge>
			{#if project.prioridade}
				<Badge tone={tone(prioridadeTone, project.prioridade)}>
					{prioridadeLabel[project.prioridade] ?? project.prioridade}
				</Badge>
			{/if}
		</div>
	</div>

	{#if !compact}
		<div class="flex flex-wrap items-end gap-4">
			{#if canEdit}
				<div class="min-w-40">
					<InlineEditField
						fieldId="project-status"
						label="Status"
						value={project.status}
						kind="select"
						options={options.status}
						pending={fieldStateFor('status').pending}
						error={fieldStateFor('status').error}
						onSave={(v) => onEditField('status', v)}
					/>
				</div>
				<div class="min-w-40">
					<InlineEditField
						fieldId="project-prioridade"
						label="Prioridade"
						value={project.prioridade ?? ''}
						kind="select"
						options={options.prioridade}
						pending={fieldStateFor('prioridade').pending}
						error={fieldStateFor('prioridade').error}
						onSave={(v) => onEditField('prioridade', v)}
					/>
				</div>
			{/if}

			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
					Início (derivado)
				</span>
				<time
					class="text-sm text-text-secondary"
					datetime={derivedData.data_inicio_projeto ?? undefined}
				>
					{formatDateBr(derivedData.data_inicio_projeto)}
				</time>
			</div>
			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
					Fim (derivado)
				</span>
				<time
					class="text-sm text-text-secondary"
					datetime={derivedData.data_fim_projeto ?? undefined}
				>
					{formatDateBr(derivedData.data_fim_projeto)}
				</time>
			</div>
			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
					Etapas
				</span>
				<span class="text-sm text-text-secondary">
					{derivedData.total_workflow_etapas}
					{#if derivedData.todas_etapas_concluidas}
						<span class="text-success">· todas concluídas</span>
					{/if}
				</span>
			</div>
		</div>
	{/if}
</header>
