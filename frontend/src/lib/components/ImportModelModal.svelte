<script lang="ts">
	/**
	 * Modal para importar um modelo de etapas ao projeto. CONTROLADO por callbacks.
	 *
	 * Referência: static/js/.../detail/02-import-model.js — seleciona um modelo,
	 * define a data de início, vê o PREVIEW das etapas e confirma. A página passa a
	 * lista de `templates` (resumo) e o componente emite
	 * `onConfirm({ template_id, start_date })`; a página chama importStageModel e
	 * RE-BUSCA as etapas.
	 *
	 * Preview: ao escolher um modelo, o componente busca o detalhe das etapas
	 * (`fetchTemplateStages` → GET /api/templates/<id>: nome, ordem, duração) e
	 * acumula as durações a partir da data de início para mostrar as DATAS
	 * CALCULADAS de cada etapa. O cálculo é em DIAS ÚTEIS (pula sábado/domingo)
	 * como estimativa cliente; as datas REAIS — incluindo feriados — são gravadas
	 * pelo servidor na importação. Por isso o rodapé do preview avisa que são
	 * datas estimadas.
	 *
	 * Chrome: `Modal.svelte` (backdrop `z-modal`, Esc/backdrop fecham, foco preso).
	 * Estados loading/erro/vazio anunciados; confirmar desabilita sem seleção
	 * válida. Sucesso emite toast com a contagem de etapas criadas.
	 */
	import { tick } from 'svelte';
	import type { StageTemplateOption } from '$lib/types/projectDetail';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import { fetchTemplateStages, type TemplateStage } from '$lib/api/projects';
	import { addBusinessDays, nextBusinessDay } from '$lib/utils/businessDays';
	import Modal from '$lib/components/Modal.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import DatePickerPanel from '$lib/components/DatePickerPanel.svelte';

	interface Props {
		/** Diálogo aberto? (controlado pela página). */
		open: boolean;
		/** Modelos de etapas disponíveis (carregados pela página). */
		templates: StageTemplateOption[];
		/** Carregando a lista de modelos. */
		loading?: boolean;
		/** Importação em andamento (controlada pela página). */
		submitting?: boolean;
		/** Erro do carregamento de modelos ou da importação. */
		error?: string | null;
		/** Data inicial sugerida (YYYY-MM-DD); default = hoje. */
		defaultStartDate?: string;
		/** Confirma a importação; a página chama o endpoint. */
		onConfirm: (payload: { template_id: number; start_date: string }) => void;
		/** Fecha o modal sem importar. */
		onClose: () => void;
	}

	let {
		open,
		templates,
		loading = false,
		submitting = false,
		error = null,
		defaultStartDate,
		onConfirm,
		onClose
	}: Props = $props();

	function today(): string {
		return new Date().toISOString().slice(0, 10);
	}

	let selectedId = $state<string>('');
	// Semente inicial do campo editável; mudanças do prop são refletidas no $effect
	// de abertura (re-seeda startDate = defaultStartDate ?? today()). A captura do
	// valor inicial aqui é intencional.
	// svelte-ignore state_referenced_locally
	let startDate = $state<string>(defaultStartDate ?? today());
	let startDateAnchorEl = $state<HTMLElement | null>(null);
	let startDatePickerOpen = $state(false);

	// Etapas do modelo selecionado (detalhe). Buscadas sob demanda para o preview.
	let stages = $state<TemplateStage[]>([]);
	let stagesLoading = $state<boolean>(false);
	let stagesError = $state<string | null>(null);

	const selectedTemplate = $derived(
		templates.find((t) => String(t.id) === selectedId) ?? null
	);
	const canConfirm = $derived(!submitting && selectedId !== '' && startDate !== '');
	const templateMenuOptions = $derived<SelectMenuOption[]>(
		templates.map((t) => ({ value: String(t.id), label: t.name }))
	);

	// Ao abrir, reseta seleção/data/preview e foca o seletor.
	$effect(() => {
		if (open) {
			selectedId = '';
			startDate = defaultStartDate ?? today();
			startDatePickerOpen = false;
			stages = [];
			stagesError = null;
			void tick().then(() => document.getElementById('import-model-select')?.focus());
		}
	});

	// Busca o detalhe das etapas quando um modelo é escolhido (preview). Aborta a
	// busca anterior se a seleção mudar antes de concluir.
	$effect(() => {
		const id = selectedId;
		if (id === '') {
			stages = [];
			stagesError = null;
			stagesLoading = false;
			return;
		}
		const controller = new AbortController();
		stagesLoading = true;
		stagesError = null;
		fetchTemplateStages(id, controller.signal)
			.then((result) => {
				stages = [...result].sort((a, b) => a.order - b.order);
			})
			.catch((err: unknown) => {
				if (controller.signal.aborted) return;
				stages = [];
				stagesError =
					err instanceof Error ? err.message : 'Não foi possível carregar as etapas do modelo.';
			})
			.finally(() => {
				if (!controller.signal.aborted) stagesLoading = false;
			});
		return () => controller.abort();
	});

	function formatDateBr(date: Date): string {
		return date.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** dd/mm/aaaa para exibição no trigger; startDate continua ISO. */
	function startDateLabel(iso: string): string {
		if (!iso) return '';
		const [y, m, d] = iso.split('-');
		return `${d}/${m}/${y}`;
	}

	/** Uma linha do preview: número, nome, datas calculadas e duração. */
	interface PreviewStage {
		order: number;
		name: string;
		duration: number;
		startLabel: string;
		endLabel: string;
	}

	/**
	 * Etapas com datas calculadas, acumulando as durações (em dias úteis) a partir
	 * da data de início. Cada etapa começa no próximo dia útil após o fim da
	 * anterior; a duração D ocupa D dias úteis (início inclusive). Estimativa — o
	 * servidor grava as datas reais considerando feriados.
	 */
	const previewStages = $derived.by<PreviewStage[]>(() => {
		if (stages.length === 0 || !startDate) return [];
		const parsed = new Date(`${startDate}T00:00:00Z`);
		if (Number.isNaN(parsed.getTime())) return [];

		const rows: PreviewStage[] = [];
		let cursor = nextBusinessDay(parsed);
		for (const stage of stages) {
			const duration = stage.duration > 0 ? stage.duration : 1;
			const start = cursor;
			// Duração inclui o dia de início, logo o fim soma (duração - 1) dias úteis.
			const end = addBusinessDays(start, duration - 1);
			rows.push({
				order: stage.order,
				name: stage.name,
				duration,
				startLabel: formatDateBr(start),
				endLabel: formatDateBr(end)
			});
			// Próxima etapa começa no dia útil seguinte ao fim desta.
			cursor = addBusinessDays(end, 1);
		}
		return rows;
	});

	const previewTotalDays = $derived(
		previewStages.reduce((sum, row) => sum + row.duration, 0)
	);

	// O toast de sucesso é da página, que tem a contagem real do servidor
	// (`etapas_criadas`); aqui só se dispara a ação.
	function confirm(): void {
		if (!canConfirm) return;
		onConfirm({ template_id: Number(selectedId), start_date: startDate });
	}
</script>

{#if open}
	<Modal labelId="import-model-title" maxWidth="max-w-lg" onBackdrop={onClose}>
		<div class="flex flex-col gap-4">
			<header class="flex items-start justify-between gap-3">
				<div class="flex items-start gap-3">
					<span
						class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-wash-brand text-brand"
						aria-hidden="true"
					>
						<i class="fas fa-file-import"></i>
					</span>
					<div class="flex flex-col gap-1">
						<h2 id="import-model-title" class="font-heading text-lg font-semibold text-text-primary">
							Importar Modelo de Etapas
						</h2>
						<p class="text-xs text-text-secondary">
							Selecione um modelo e a data de início para criar as etapas automaticamente.
						</p>
					</div>
				</div>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<i class="fas fa-times" aria-hidden="true"></i>
				</button>
			</header>

			{#if loading}
				<p role="status" aria-live="polite" class="text-sm text-text-secondary">
					Carregando modelos…
				</p>
			{:else if templates.length === 0}
				<p class="text-sm text-text-muted">Nenhum modelo de etapas disponível.</p>
			{:else}
				<div class="flex flex-col gap-2">
					<label for="import-model-select" class="text-sm font-medium text-text-primary">
						Modelo
					</label>
					<SelectMenu
						id="import-model-select"
						options={templateMenuOptions}
						value={selectedId || null}
						onSelect={(v) => (selectedId = v ?? '')}
						disabled={submitting}
						placeholder="Selecione um modelo…"
						searchable
						ariaLabel="Modelo"
					/>
				</div>

				{#if selectedTemplate}
					<p class="text-sm text-text-secondary">
						{selectedTemplate.stage_count} etapa(s) · {selectedTemplate.total_duration_days} dia(s)
						de duração total.
					</p>
				{/if}

				<div class="flex flex-col gap-2">
					<label for="import-model-start" class="text-sm font-medium text-text-primary">
						Data de início
					</label>
					<button
						id="import-model-start"
						type="button"
						bind:this={startDateAnchorEl}
						disabled={submitting}
						aria-haspopup="dialog"
						aria-expanded={startDatePickerOpen}
						onclick={() => (startDatePickerOpen = !startDatePickerOpen)}
						class="flex w-full items-center rounded-md border border-border-subtle bg-surface px-3 py-2 text-left text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
					>
						<span class={startDate ? '' : 'text-text-muted'}>
							{startDateLabel(startDate) || 'Selecionar data'}
						</span>
					</button>
					{#if startDatePickerOpen && startDateAnchorEl}
						<DatePickerPanel
							anchor={startDateAnchorEl}
							value={startDate || null}
							ariaLabel="Data de início"
							onPick={(iso) => {
								startDate = iso;
								startDatePickerOpen = false;
							}}
							onClose={() => (startDatePickerOpen = false)}
						/>
					{/if}
				</div>

				<!-- Preview das etapas com datas calculadas a partir da data de início. -->
				{#if selectedId !== ''}
					<section class="flex flex-col gap-2" aria-labelledby="import-model-preview-title">
						<h3
							id="import-model-preview-title"
							class="text-sm font-medium text-text-primary"
						>
							Etapas do modelo
						</h3>

						{#if stagesLoading}
							<p role="status" aria-live="polite" class="text-sm text-text-secondary">
								Carregando etapas…
							</p>
						{:else if stagesError}
							<p role="alert" class="text-sm text-danger">{stagesError}</p>
						{:else if previewStages.length === 0}
							<p class="text-sm text-text-muted">Este modelo não possui etapas cadastradas.</p>
						{:else}
							<ol class="flex max-h-60 flex-col gap-1.5 overflow-y-auto pr-1">
								{#each previewStages as stage (stage.order)}
									<li
										class="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface-muted px-3 py-2"
									>
										<span
											class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-wash-neutral text-xs font-semibold text-brand"
											aria-hidden="true"
										>
											{stage.order}
										</span>
										<span class="min-w-0 flex-1 truncate text-sm text-text-primary" title={stage.name}>
											{stage.name}
										</span>
										<span class="shrink-0 text-right text-xs text-text-secondary">
											<span class="block whitespace-nowrap">
												{stage.startLabel} – {stage.endLabel}
											</span>
											<span class="block text-text-muted">
												{stage.duration} dia{stage.duration > 1 ? 's' : ''}
											</span>
										</span>
									</li>
								{/each}
							</ol>

							<p class="flex items-center gap-2 text-xs text-text-secondary">
								<i class="fas fa-info-circle text-brand" aria-hidden="true"></i>
								<span>
									<strong>Total:</strong>
									{previewStages.length} etapa{previewStages.length > 1 ? 's' : ''} ·
									{previewTotalDays} dia{previewTotalDays > 1 ? 's' : ''}
								</span>
							</p>
							<p class="text-xs text-text-muted">
								Datas estimadas em dias úteis. O servidor grava as datas finais
								considerando feriados.
							</p>
						{/if}
					</section>
				{/if}
			{/if}

			{#if error}
				<StateBanner tone="danger" title={error} />
			{/if}

			<footer class="flex items-center justify-end gap-2">
				<button
					type="button"
					onclick={onClose}
					disabled={submitting}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={confirm}
					disabled={!canConfirm}
					class="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-on-brand shadow-sm transition-colors duration-fast hover:bg-brand-hover hover:shadow-md disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					{submitting ? 'Importando…' : 'Importar'}
				</button>
			</footer>
		</div>
	</Modal>
{/if}
