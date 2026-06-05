<script lang="ts">
	/**
	 * EEGG editável inline — três cartões LADO A LADO (Objetivo · Resultado
	 * esperado · Indicadores), cada um editável de forma INDEPENDENTE clicando
	 * direto no valor (igual aos demais campos do detalhe).
	 *
	 * No backend os três são uma unidade coesa (`normalize_goal_selection`): cada
	 * salvamento envia a seleção inteira via `onSave`. A CASCATA limpa os níveis
	 * abaixo do que mudou:
	 *   - escolher Objetivo  → zera Resultado + Indicadores;
	 *   - escolher Resultado → zera Indicadores;
	 *   - Resultado só edita com Objetivo definido; Indicadores só com Resultado.
	 *
	 * Objetivo/Resultado reusam `InlineCombobox` (single-select pesquisável, salva
	 * na escolha). Indicadores é multi-select (≤4) com Salvar/Cancelar explícitos.
	 * O catálogo vem das funções já expostas em `$lib/api/projects` (mesmas do
	 * CriarProjetoModal). A página orquestra a API e devolve `pending`/`error`.
	 */
	import InlineCombobox from './InlineCombobox.svelte';
	import {
		fetchObjetivosCatalogo,
		fetchResultados,
		fetchIndicadores,
		type ObjetivoCatalogo,
		type ResultadoCatalogo,
		type IndicadorCatalogo
	} from '$lib/api/projects';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';

	interface GoalSelection {
		objetivo_id: number | null;
		resultado_esperado_id: number | null;
		indicadores_ids: number[];
	}

	interface Props {
		fieldId: string;
		objetivoId: number | null;
		resultadoId: number | null;
		indicadoresIds: number[];
		objetivoDescricao: string | null;
		resultadoDescricao: string | null;
		indicadoresDescricoes: string[];
		readonly?: boolean;
		pending?: boolean;
		error?: string | null;
		/** Salva a unidade coesa. Aguardável; a página propaga falha via `error`. */
		onSave: (sel: GoalSelection) => Promise<void>;
	}

	let {
		fieldId,
		objetivoId,
		resultadoId,
		indicadoresIds,
		objetivoDescricao,
		resultadoDescricao,
		indicadoresDescricoes,
		readonly = false,
		pending = false,
		error = null,
		onSave
	}: Props = $props();

	const MAX_INDICADORES = 4;

	let objetivos = $state<ObjetivoCatalogo[]>([]);
	let objetivosLoaded = $state(false);
	let resultados = $state<ResultadoCatalogo[]>([]);
	let indicadores = $state<IndicadorCatalogo[]>([]);
	let indicadoresLoading = $state(false);

	// Catálogo de objetivos: carrega uma única vez.
	$effect(() => {
		if (objetivosLoaded) return;
		void loadObjetivos();
	});

	async function loadObjetivos(): Promise<void> {
		try {
			objetivos = await fetchObjetivosCatalogo();
			objetivosLoaded = true;
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			objetivos = [];
		}
	}

	// Resultados do objetivo atual — repopula sempre que o objetivo do projeto muda.
	$effect(() => {
		const oid = objetivoId;
		if (oid === null) {
			resultados = [];
			return;
		}
		void fetchResultados(oid)
			.then((r) => (resultados = r))
			.catch(() => (resultados = []));
	});

	// Indicadores do resultado atual — repopula quando o resultado do projeto muda.
	$effect(() => {
		const rid = resultadoId;
		if (rid === null) {
			indicadores = [];
			indicadoresLoading = false;
			return;
		}
		indicadoresLoading = true;
		void fetchIndicadores(rid)
			.then((r) => (indicadores = r))
			.catch(() => (indicadores = []))
			.finally(() => (indicadoresLoading = false));
	});

	const objetivoOptions = $derived(objetivos.map((o) => ({ value: String(o.id), label: o.descricao })));
	const resultadoOptions = $derived(
		resultados.map((r) => ({ value: String(r.id), label: r.descricao }))
	);

	// --- Salvar cada nível (cascata limpa os de baixo) ---------------------------

	function saveObjetivo(value: string): void {
		const oid = Number(value);
		if (oid === objetivoId) return;
		void onSave({ objetivo_id: oid, resultado_esperado_id: null, indicadores_ids: [] });
	}

	async function saveResultado(value: string): Promise<void> {
		const rid = Number(value);
		if (rid === resultadoId) return;
		// "Carregando…" já no clique evita flash da lista antiga; o $effect recarrega
		// e os checkboxes do novo resultado aparecem inline (sem clique extra).
		indicadoresLoading = true;
		await onSave({ objetivo_id: objetivoId, resultado_esperado_id: rid, indicadores_ids: [] });
		// Em erro o resultado não muda (o $effect não roda): libera o estado aqui.
		if (error) indicadoresLoading = false;
	}

	// --- Indicadores: multi-select INLINE (≤4) — cada toque salva, sem botões ----
	// `selected` é otimista: reflete o clique na hora e re-sincroniza com o servidor
	// (prop `indicadoresIds`) em sucesso; em erro, o efeito reverte para a prop.
	let selected = $state<number[]>([]);
	$effect(() => {
		void error; // re-sincroniza também quando um save falha (reverte o otimista)
		selected = [...indicadoresIds];
	});
	const atMax = $derived(selected.length >= MAX_INDICADORES);

	function toggleInd(id: number): void {
		if (readonly || resultadoId === null) return;
		let next: number[];
		if (selected.includes(id)) {
			next = selected.filter((x) => x !== id);
		} else {
			if (selected.length >= MAX_INDICADORES) {
				flash.warning('Você pode selecionar no máximo 4 indicadores');
				return;
			}
			next = [...selected, id];
		}
		selected = next; // otimista
		void onSave({
			objetivo_id: objetivoId,
			resultado_esperado_id: resultadoId,
			indicadores_ids: next
		});
	}

	const cardClass =
		'flex flex-col gap-2 rounded-md border border-border-subtle bg-surface px-4 py-3 shadow-sm';
	const labelClass =
		'flex items-center gap-1.5 border-b border-border-subtle pb-2 text-xs font-semibold uppercase tracking-wide text-text-muted';
</script>

{#snippet indReadList()}
	{#if indicadoresDescricoes.length > 0}
		<ul class="flex flex-col gap-1">
			{#each indicadoresDescricoes as desc, i (i)}
				<li class="flex items-start gap-2 text-sm text-text-primary">
					<i class="fas fa-check mt-0.5 shrink-0 text-xs text-primary-600" aria-hidden="true"></i>
					<span>{desc}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<span class="text-sm text-text-muted">Não definido</span>
	{/if}
{/snippet}

<div class="flex flex-col gap-2">
	<div class="grid gap-4 sm:grid-cols-3">
		<!-- Objetivo -->
		<div class={cardClass}>
			<span class={labelClass}>
				<i class="fas fa-bullseye text-primary-600" aria-hidden="true"></i>Objetivo
			</span>
			{#if readonly}
				<span class="text-sm {objetivoDescricao ? 'text-text-primary' : 'text-text-muted'}">
					{objetivoDescricao ?? 'Não definido'}
				</span>
			{:else}
				<InlineCombobox
					fieldId={`${fieldId}-objetivo`}
					label="Objetivo, editar"
					value={objetivoId !== null ? String(objetivoId) : null}
					displayLabel={objetivoDescricao}
					options={objetivoOptions}
					emptyLabel="Não definido"
					wrap
					{pending}
					onSelect={saveObjetivo}
				/>
			{/if}
		</div>

		<!-- Resultado esperado -->
		<div class={cardClass}>
			<span class={labelClass}>
				<i class="fas fa-chart-line text-primary-600" aria-hidden="true"></i>Resultado esperado
			</span>
			{#if readonly}
				<span class="text-sm {resultadoDescricao ? 'text-text-primary' : 'text-text-muted'}">
					{resultadoDescricao ?? 'Não definido'}
				</span>
			{:else if objetivoId === null}
				<span class="text-sm italic text-text-muted">Defina o objetivo primeiro</span>
			{:else}
				<InlineCombobox
					fieldId={`${fieldId}-resultado`}
					label="Resultado esperado, editar"
					value={resultadoId !== null ? String(resultadoId) : null}
					displayLabel={resultadoDescricao}
					options={resultadoOptions}
					emptyLabel="Não definido"
					wrap
					{pending}
					onSelect={saveResultado}
				/>
			{/if}
		</div>

		<!-- Indicadores -->
		<div class={cardClass}>
			<span class={labelClass}>
				<i class="fas fa-list-check text-primary-600" aria-hidden="true"></i>Indicadores
				{#if !readonly && resultadoId !== null && !indicadoresLoading && indicadores.length > 0}
					<!-- selecionados / TOTAL disponível neste resultado (limite de 4 ainda
					     vale e atenua/avisa quando há mais de 4 opções). -->
					<span class="ml-1 normal-case text-text-muted">({selected.length}/{indicadores.length})</span>
				{/if}
			</span>
			{#if readonly}
				{@render indReadList()}
			{:else if resultadoId === null}
				<span class="text-sm italic text-text-muted">Defina o resultado primeiro</span>
			{:else if indicadoresLoading}
				<p class="text-sm text-text-muted">
					<i class="fas fa-spinner fa-spin mr-1" aria-hidden="true"></i>Carregando indicadores…
				</p>
			{:else if indicadores.length === 0}
				<p class="text-sm text-text-muted">Nenhum indicador disponível</p>
			{:else}
				<!-- Seleção INLINE: cada toque salva direto (sem Salvar/Cancelar). -->
				<div class="flex flex-col gap-2">
					{#each indicadores as ind (ind.id)}
						{@const isSel = selected.includes(ind.id)}
						{@const blocked = atMax && !isSel}
						<label
							class="flex items-start gap-2 text-sm text-text-primary {blocked ? 'opacity-50' : ''}"
						>
							<input
								type="checkbox"
								checked={isSel}
								disabled={pending || blocked}
								onchange={() => toggleInd(ind.id)}
								class="mt-0.5 h-4 w-4 shrink-0 rounded border-border-subtle text-primary-600 focus:ring-primary-500"
							/>
							<span>{ind.descricao}</span>
						</label>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	{#if error}
		<p id={`${fieldId}-error`} role="alert" class="text-sm text-danger">{error}</p>
	{/if}
</div>
