<script lang="ts">
	/**
	 * EEGG editável inline — PLACA TÉCNICA horizontal: uma peça só, com a régua
	 * de rótulos em cima e os valores embaixo (Objetivo · Resultado esperado ·
	 * Indicadores). O número do objetivo é o prefixo da própria descrição do
	 * catálogo ("9- Ampliar…"), exibido como texto comum. Cada valor é editável
	 * de forma INDEPENDENTE clicando direto nele (igual aos demais campos do
	 * detalhe).
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

	// Resultados do objetivo atual — repopula sempre que o objetivo do projeto MUDA.
	// Guarda do último id carregado (var simples, fora da reatividade): o save de
	// QUALQUER nível reatribui `data.project` na página, o que re-dispara estes
	// efeitos mesmo com o id idêntico — sem a guarda, marcar um indicador
	// re-buscava os catálogos e piscava "Carregando indicadores…".
	let loadedResultadosForObjetivo: number | null | undefined = undefined;
	$effect(() => {
		const oid = objetivoId;
		if (oid === loadedResultadosForObjetivo) return;
		loadedResultadosForObjetivo = oid;
		if (oid === null) {
			resultados = [];
			return;
		}
		void fetchResultados(oid)
			.then((r) => (resultados = r))
			.catch(() => (resultados = []));
	});

	// Indicadores do resultado atual — repopula quando o resultado do projeto MUDA.
	let loadedIndicadoresForResultado: number | null | undefined = undefined;
	$effect(() => {
		const rid = resultadoId;
		if (rid === loadedIndicadoresForResultado) return;
		loadedIndicadoresForResultado = rid;
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

	// O `pending` da página vale para a UNIDADE EEGD inteira; o spinner/esmaecer
	// deve aparecer SÓ no nível que disparou o save (marcar um indicador não
	// pode acender "carregando" em Objetivo/Resultado). Limpa quando resolve.
	type SavingLevel = 'objetivo' | 'resultado' | 'indicadores';
	let savingLevel = $state<SavingLevel | null>(null);
	$effect(() => {
		if (!pending) savingLevel = null;
	});

	function saveObjetivo(value: string): void {
		const oid = Number(value);
		if (oid === objetivoId) return;
		savingLevel = 'objetivo';
		void onSave({ objetivo_id: oid, resultado_esperado_id: null, indicadores_ids: [] });
	}

	async function saveResultado(value: string): Promise<void> {
		const rid = Number(value);
		if (rid === resultadoId) return;
		savingLevel = 'resultado';
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
		// NÃO re-sincroniza no MEIO do save: o `error` muda de undefined->null ao
		// iniciar, o que revertia o otimista por um instante (piscada no item).
		if (pending) return;
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
				flash.warning('Você pode selecionar no máximo 4 indicadores.');
				return;
			}
			next = [...selected, id];
		}
		selected = next; // otimista
		savingLevel = 'indicadores';
		void onSave({
			objetivo_id: objetivoId,
			resultado_esperado_id: resultadoId,
			indicadores_ids: next
		});
	}

	// Lista exibida: o catálogo do resultado quando disponível (deixa os NÃO
	// selecionados visíveis, apagados), senão só os escolhidos vindos do projeto.
	const indicadoresExibidos = $derived(
		indicadores.length > 0
			? indicadores.map((ind) => ({ id: ind.id, descricao: ind.descricao, sel: selected.includes(ind.id) }))
			: indicadoresDescricoes.map((descricao, i) => ({ id: -i - 1, descricao, sel: true }))
	);
	const totalSelecionados = $derived(indicadoresExibidos.filter((ind) => ind.sel).length);
</script>

{#snippet caixaMarcada(marcada: boolean)}
	<span
		aria-hidden="true"
		class="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors duration-fast {marcada
			? 'border-brand bg-brand'
			: 'border-border-strong bg-surface'}"
	>
		{#if marcada}
			<svg viewBox="0 0 24 24" class="h-3 w-3 text-on-brand" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
				<path d="M5 13l4 4L19 7" />
			</svg>
		{/if}
	</span>
{/snippet}

{#snippet listaIndicadoresLeitura()}
	{#if indicadoresExibidos.length > 0}
		<ul class="flex flex-col gap-1.5">
			{#each indicadoresExibidos as ind (ind.id)}
				<li
					class="flex items-start gap-2.5 rounded-sm border px-2.5 py-2 text-sm {ind.sel
						? 'border-border-strong bg-wash-neutral text-text-primary'
						: 'border-border-subtle text-text-muted'}"
				>
					{@render caixaMarcada(ind.sel)}
					<span class="leading-snug">{ind.descricao}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<span class="text-sm text-text-muted">Não definido</span>
	{/if}
{/snippet}

<div class="flex flex-col gap-2">
	<div class="eegd-placa">
		<div class="eegd-rotulo eegd-col-objetivo">Objetivo</div>
		<div class="eegd-valor eegd-col-objetivo">
			{#if readonly}
				<span class="eegd-texto {objetivoDescricao ? 'text-text-primary' : 'text-text-muted'}">
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
					pending={pending && savingLevel === 'objetivo'}
					readonly={pending && savingLevel !== 'objetivo'}
					onSelect={saveObjetivo}
				/>
			{/if}
		</div>

		<div class="eegd-rotulo eegd-col-resultado">Resultado esperado</div>
		<div class="eegd-valor eegd-col-resultado">
			{#if readonly}
				<span class="eegd-texto {resultadoDescricao ? 'text-text-primary' : 'text-text-muted'}">
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
					pending={pending && savingLevel === 'resultado'}
					readonly={pending && savingLevel !== 'resultado'}
					onSelect={saveResultado}
				/>
			{/if}
		</div>

		<div class="eegd-rotulo eegd-col-indicadores">
			<span>Indicadores</span>
			{#if indicadoresExibidos.length > 0 && !indicadoresLoading}
				<span class="eegd-contagem">
					{#if indicadores.length > 0}
						{totalSelecionados} de {indicadores.length} selecionados
					{:else}
						{totalSelecionados} selecionados
					{/if}
				</span>
			{/if}
		</div>
		<div class="eegd-valor eegd-col-indicadores">
			{#if readonly}
				{@render listaIndicadoresLeitura()}
			{:else if resultadoId === null}
				<span class="text-sm italic text-text-muted">Defina o resultado primeiro</span>
			{:else if indicadoresLoading}
				<p class="text-sm text-text-muted">
					<i class="fas fa-spinner fa-spin mr-1" aria-hidden="true"></i>Carregando indicadores…
				</p>
			{:else if indicadores.length === 0}
				<p class="text-sm text-text-muted">Nenhum indicador disponível</p>
			{:else}
				<!-- Seleção INLINE: cada toque salva direto (sem Salvar/Cancelar). Os
				     NÃO selecionados continuam visíveis, apagados — mostram o que o
				     resultado oferece sem exigir abrir um seletor. -->
				<div class="flex flex-col gap-1.5" role="group" aria-label="Indicadores do resultado">
					{#each indicadores as ind (ind.id)}
						{@const isSel = selected.includes(ind.id)}
						{@const blocked = atMax && !isSel}
						<button
							type="button"
							role="checkbox"
							aria-checked={isSel}
							disabled={pending || blocked}
							onclick={() => toggleInd(ind.id)}
							class="flex items-start gap-2.5 rounded-sm border px-2.5 py-2 text-left text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed {isSel
								? 'border-border-strong bg-wash-neutral text-text-primary'
								: 'border-border-subtle text-text-muted hover:bg-surface-muted hover:text-text-primary'} {blocked
								? 'opacity-50'
								: ''}"
						>
							{@render caixaMarcada(isSel)}
							<span class="leading-snug">{ind.descricao}</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	{#if error}
		<p id={`${fieldId}-error`} role="alert" class="text-sm text-danger">{error}</p>
	{/if}
</div>

<style>
	/* Placa técnica: uma peça só. No desktop o numeral ocupa a coluna 1 nas duas
	   linhas, os rótulos formam a régua de cima e os valores a faixa de baixo. */
	.eegd-placa {
		display: grid;
		grid-template-columns: 1fr;
		border: 1px solid var(--ds-color-border-base);
		border-radius: var(--ds-radius-lg, 12px);
		background: var(--ds-color-surface-base);
		/* SEM overflow:hidden — recortava o popup do InlineCombobox, que é
		   `absolute` na própria célula (não há portal). Os cantos que pintam
		   fundo arredondam sozinhos abaixo. */
	}

	.eegd-rotulo {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		border-bottom: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
		font-size: var(--ds-font-size-2xs, 0.6875rem);
		font-weight: 600;
		line-height: 1rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ds-color-text-muted);
	}
	/* Empilhado: o rótulo do objetivo é o topo da placa e precisa acompanhar o
	   raio da borda — é o único filho com fundo próprio encostado no canto. */
	.eegd-rotulo.eegd-col-objetivo {
		border-radius: var(--ds-radius-lg, 12px) var(--ds-radius-lg, 12px) 0 0;
	}
	.eegd-contagem {
		font-weight: 400;
		text-transform: none;
		letter-spacing: 0;
		color: var(--ds-color-text-faint);
	}

	.eegd-valor {
		padding: 0.875rem 1rem 1.125rem;
	}
	/* Objetivo e resultado são SEMPRE um item só, então sobem um degrau acima do
	   corpo de UI (sm, 13px) para o md (14px). Vale para os dois modos, e o
	   `.ic-closed`/`.ic-input` do InlineCombobox fixa `text-sm` no próprio
	   componente — daí o :global para vencer a utilitária. */
	.eegd-texto,
	.eegd-valor :global(.ic-closed),
	.eegd-valor :global(.ic-input) {
		font-family: var(--ds-font-family-heading);
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	/* NÃO declarar display aqui: o `.ic-closed` é flex (valor + chevron na mesma
	   linha) e um `display: block` jogava o chevron para a linha de baixo. */
	.eegd-texto {
		display: block;
	}

	/* Empilhado (mobile): rótulo e valor em pares, sem numeral. */
	.eegd-valor:not(:last-child) {
		border-bottom: 1px solid var(--ds-color-border-base);
	}

	@media (min-width: 768px) {
		/* Três colunas IGUAIS, espelhando `.ficha` (projetos/[id]/+page.svelte): os
		   blocos ficam empilhados e as divisórias têm de se alinhar. */
		.eegd-placa {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
		.eegd-rotulo.eegd-col-objetivo {
			border-radius: var(--ds-radius-lg, 12px) 0 0 0;
		}
		.eegd-rotulo.eegd-col-indicadores {
			border-radius: 0 var(--ds-radius-lg, 12px) 0 0;
		}
		.eegd-rotulo {
			grid-row: 1;
		}
		/* Mesma especificidade da regra empilhada (`:not(:last-child)`), senão o
		   divisor de mobile sobrevive no desktop e engrossa a borda de baixo. */
		.eegd-valor,
		.eegd-valor:not(:last-child) {
			grid-row: 2;
			border-bottom: 0;
		}
		.eegd-col-objetivo {
			grid-column: 1;
		}
		.eegd-col-resultado {
			grid-column: 2;
		}
		.eegd-col-indicadores {
			grid-column: 3;
		}
		/* Divisórias verticais entre as três colunas de conteúdo. */
		.eegd-col-objetivo,
		.eegd-col-resultado {
			border-right: 1px solid var(--ds-color-border-base);
		}
	}
</style>
