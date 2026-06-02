<script lang="ts">
	/**
	 * Modal para importar um modelo de etapas ao projeto. CONTROLADO por callbacks.
	 *
	 * Referência: static/js/.../detail/02-import-model.js — seleciona um modelo,
	 * define a data de início e confirma. Aqui o componente NÃO chama API: recebe a
	 * lista de `templates` (carregada pela página via fetchStageTemplates) e emite
	 * `onConfirm({ template_id, start_date })`; a página chama importStageModel e
	 * RE-BUSCA as etapas. As datas de cada etapa do modelo são calculadas
	 * server-side (dias úteis) — o front NÃO recalcula.
	 *
	 * Acessibilidade: diálogo modal (`role="dialog"`, `aria-modal`), título
	 * rotulando o diálogo, foco inicial no seletor, Escape fecha, fundo clicável
	 * fecha. Estados loading/erro/vazio anunciados; confirmar desabilita sem
	 * seleção válida.
	 */
	import { tick } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import type { StageTemplateOption } from '$lib/types/projectDetail';

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
	let startDate = $state<string>(defaultStartDate ?? today());
	let selectEl = $state<HTMLSelectElement | null>(null);

	const selectedTemplate = $derived(
		templates.find((t) => String(t.id) === selectedId) ?? null
	);
	const canConfirm = $derived(!submitting && selectedId !== '' && startDate !== '');

	// Ao abrir, reseta seleção/data e foca o seletor.
	$effect(() => {
		if (open) {
			selectedId = '';
			startDate = defaultStartDate ?? today();
			void tick().then(() => selectEl?.focus());
		}
	});

	function confirm(): void {
		if (!canConfirm) return;
		onConfirm({ template_id: Number(selectedId), start_date: startDate });
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			onClose();
		}
	}
</script>

{#if open}
	<!-- Fundo: clicar fora fecha. Fade ~280ms ease-out (paridade .modal). -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		role="presentation"
		transition:fade={{ duration: 280, easing: cubicOut }}
		onclick={onClose}
		onkeydown={onKeydown}
	>
		<!--
			Diálogo: para o clique de borbulhar para o fundo. Raio 16px (rounded-2xl)
			e entrada translateY+escala em ~320ms cubic-bezier(0.22,1,0.36,1) (cubicOut)
			como o .modal-content do detalhe.
		-->
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="import-model-title"
			class="flex w-full max-w-lg flex-col gap-4 rounded-2xl border border-border-subtle bg-surface p-5 shadow-lg"
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
			onclick={(e) => e.stopPropagation()}
			onkeydown={onKeydown}
			tabindex="-1"
		>
			<header class="flex items-center justify-between gap-3">
				<h2 id="import-model-title" class="font-heading text-lg font-semibold text-text-primary">
					Importar modelo de etapas
				</h2>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					✕
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
					<select
						bind:this={selectEl}
						bind:value={selectedId}
						id="import-model-select"
						disabled={submitting}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<option value="">Selecione um modelo…</option>
						{#each templates as template (template.id)}
							<option value={String(template.id)}>{template.name}</option>
						{/each}
					</select>
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
					<input
						bind:value={startDate}
						id="import-model-start"
						type="date"
						disabled={submitting}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					/>
					<p class="text-xs text-text-muted">
						As datas das etapas são calculadas em dias úteis pelo servidor.
					</p>
				</div>
			{/if}

			{#if error}
				<p role="alert" class="text-sm text-danger">{error}</p>
			{/if}

			<footer class="flex items-center justify-end gap-2">
				<button
					type="button"
					onclick={onClose}
					disabled={submitting}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={confirm}
					disabled={!canConfirm}
					class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{submitting ? 'Importando…' : 'Importar'}
				</button>
			</footer>
		</div>
	</div>
{/if}
