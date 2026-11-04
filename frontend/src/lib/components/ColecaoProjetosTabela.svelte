<script lang="ts">
	/**
	 * Painel "Projetos da coleção" da página interna: busca + Todos/Atrasados
	 * client-side, estados vazios e a tabela. Extraído de
	 * `routes/(app)/colecoes/[id]/+page.svelte` (passava de 1000 linhas).
	 *
	 * Curadoria compartilhada: a lixeira aparece SÓ nas linhas com
	 * `pode_remover` (decidido no servidor — dono remove tudo, editor só o que
	 * incluiu, leitor nada) e a coluna de ações só existe se alguma linha a usa.
	 * Projeto incluído por outra pessoa que não o dono ganha a etiqueta
	 * "Incluído por X" ("por você" em destaque, para o editor achar o que é
	 * dele); o caso comum (item do dono ou legado) fica limpo.
	 */
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import Button from '$lib/components/Button.svelte';
	import FilterChipGroup from '$lib/components/FilterChipGroup.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { rotuloIncluidoPor } from '$lib/utils/colecaoShares';
	import { formatIsoDateBR } from '$lib/utils/dateFormat';
	import { projectStatusChipClass } from '$lib/utils/projectLabels';
	import type { ColecaoResumo, ProjetoColecaoRow } from '$lib/types/collections';

	type FiltroLinhas = 'todos' | 'atrasados';

	interface Props {
		colecao: ColecaoResumo;
		rows: ProjetoColecaoRow[];
		/** Revalidando em segundo plano (`aria-busy` na tabela). */
		ocupado: boolean;
		/** Dono/editor: oferece "Adicionar projetos" no vazio. */
		podeIncluir: boolean;
		/** Id do usuário logado — distingue "Incluído por você". */
		meuId: number | null;
		onAdicionar: () => void;
		onRemover: (row: ProjetoColecaoRow) => void;
	}

	let { colecao, rows, ocupado, podeIncluir, meuId, onAdicionar, onRemover }: Props = $props();

	const FILTRO_OPTIONS = [
		{ id: 'todos', label: 'Todos' },
		{ id: 'atrasados', label: 'Atrasados' }
	];

	let busca = $state('');
	let filtroLinhas = $state<FiltroLinhas>('todos');

	const isFavoritos = $derived(colecao.tipo === 'favoritos');
	// Dono da coleção: `owner` só vem preenchido para quem a recebeu.
	const donoId = $derived(colecao.owner?.id ?? (colecao.papel === 'dono' ? meuId : null));
	const temRemovivel = $derived(rows.some((r) => r.pode_remover));

	const COMBINING_MARKS = /[̀-ͯ]/g;
	const norm = (s: string): string =>
		s.normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();

	const linhasVisiveis = $derived.by<ProjetoColecaoRow[]>(() => {
		const termo = norm(busca.trim());
		return rows.filter((r) => {
			if (filtroLinhas === 'atrasados' && !r.atrasado) return false;
			if (!termo) return true;
			return (
				norm(r.nome).includes(termo) ||
				norm(r.orgao_sigla ?? '').includes(termo) ||
				String(r.id).includes(termo)
			);
		});
	});

	/** Linha inteira navega ao projeto; cliques em controles internos não. */
	function abrirProjeto(event: MouseEvent, projectId: number): void {
		const alvo = event.target as HTMLElement | null;
		if (alvo?.closest('a, button')) return;
		void goto(`${base}/projetos/${projectId}`);
	}

	const thCls =
		'border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-sm font-bold uppercase tracking-caps whitespace-nowrap';
	const tdCls = 'border-t border-border-subtle px-2.5 py-2.5 align-middle';
</script>

<div class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
	<div class="flex flex-wrap items-center gap-3 px-4 py-3">
		<h2 class="m-0 text-base font-bold text-text-primary">Projetos da coleção</h2>
		<div class="ml-auto flex flex-wrap items-center gap-2">
			<FilterChipGroup
				label="Filtrar projetos da coleção"
				options={FILTRO_OPTIONS}
				value={filtroLinhas}
				onchange={(id) => (filtroLinhas = id as FiltroLinhas)}
			/>
			<div class="relative w-52">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="colecaoProjetosSearch"
					type="search"
					autocomplete="off"
					bind:value={busca}
					aria-label="Buscar projeto na coleção"
					placeholder="Buscar projeto"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
			</div>
		</div>
	</div>

	{#if rows.length === 0}
		<!-- Coleção vazia: mensagem curta com CTA único. -->
		<div class="border-t border-border-subtle px-4 py-8 text-center">
			<div
				class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-xl text-brand"
			>
				<AppIcon id="projetos" size={28} />
			</div>
			<h3 class="m-0 font-heading text-xl font-bold text-text-primary">
				{isFavoritos ? 'Nenhum projeto favoritado ainda' : 'Nenhum projeto nesta coleção'}
			</h3>
			<p class="mb-3.5 mt-1.5 text-sm text-text-muted">
				{#if isFavoritos}
					Marque a estrela em qualquer projeto e ele entra aqui.
				{:else if podeIncluir}
					Adicione projetos para acompanhar o andamento agrupado.
				{:else}
					Quem compartilhou esta coleção ainda não adicionou projetos a ela.
				{/if}
			</p>
			{#if podeIncluir}
				<Button size="sm" onclick={onAdicionar}>
					{#snippet icon()}
						<i class="fas fa-plus" aria-hidden="true"></i>
					{/snippet}
					Adicionar projetos
				</Button>
			{/if}
		</div>
	{:else if linhasVisiveis.length === 0}
		<p
			role="status"
			aria-live="polite"
			class="m-0 border-t border-border-subtle px-4 py-6 text-center text-sm text-text-muted"
		>
			{filtroLinhas === 'atrasados' && !busca.trim()
				? 'Nenhum projeto atrasado nesta coleção.'
				: 'Nenhum projeto corresponde aos filtros aplicados.'}
		</p>
	{:else}
		<div class="overflow-x-auto" aria-busy={ocupado}>
			<table class="m-0 w-full min-w-[1040px] border-separate border-spacing-0 text-sm">
				<caption class="sr-only">Projetos da coleção {colecao.nome}</caption>
				<thead>
					<tr class="text-left text-text-muted">
						<th scope="col" class="w-16 {thCls}">ID</th>
						<th scope="col" class="min-w-[220px] {thCls}">Projeto</th>
						<th scope="col" class={thCls}>Área responsável</th>
						<th scope="col" class="{thCls} text-center">Etapas</th>
						<th scope="col" class="{thCls} text-center">Tarefas</th>
						<th scope="col" class="min-w-[140px] {thCls}">Progresso</th>
						<th scope="col" class={thCls}>Início</th>
						<th scope="col" class={thCls}>Fim previsto</th>
						<th scope="col" class="{thCls} text-center">Status</th>
						{#if temRemovivel}
							<th scope="col" class="w-16 {thCls}">
								<span class="sr-only">Ações</span>
							</th>
						{/if}
					</tr>
				</thead>
				<tbody>
					{#each linhasVisiveis as row (row.id)}
						{@const incluidoPor = rotuloIncluidoPor(row, { meuId, donoId })}
						<!-- Clique na linha navega; o teclado usa o link do título. -->
						<!-- svelte-ignore a11y_click_events_have_key_events -->
						<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
						<tr
							onclick={(e) => abrirProjeto(e, row.id)}
							class="cursor-pointer transition-colors duration-fast hover:bg-surface-muted"
						>
							<td class="{tdCls} font-mono text-sm text-text-muted">{row.id}</td>
							<td class={tdCls}>
								<a
									href={`${base}/projetos/${row.id}`}
									class="text-md font-medium text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									{row.nome}
								</a>
								{#if incluidoPor}
									<span
										class="mt-1 block w-fit max-w-full truncate rounded-sm border px-1.5 py-0.5 text-2xs font-medium {row
											.adicionado_por?.id === meuId
											? 'border-brand-soft bg-wash-brand text-brand'
											: 'border-border-subtle bg-wash-neutral text-text-secondary'}"
										title={incluidoPor}
									>
										{incluidoPor}
									</span>
								{/if}
							</td>
							<td class="{tdCls} text-text-secondary">
								{#if row.orgao_sigla}
									<span class="text-sm font-medium uppercase tracking-wide">
										{row.orgao_sigla}
									</span>
								{:else}
									<span class="italic text-text-muted">—</span>
								{/if}
							</td>
							<td
								class="{tdCls} whitespace-nowrap text-center font-mono text-sm text-text-secondary"
							>
								{row.etapas_concluidas} / {row.etapas_total}
							</td>
							<td
								class="{tdCls} whitespace-nowrap text-center font-mono text-sm text-text-secondary"
							>
								{row.tarefas_concluidas} / {row.tarefas_total}
							</td>
							<td class={tdCls}>
								<div class="flex items-center gap-2">
									<!-- Decorativa: o % é o texto ao lado. -->
									<div
										class="h-1.5 flex-1 overflow-hidden rounded-full bg-progress-track"
										aria-hidden="true"
									>
										<div
											class="h-full rounded-full bg-brand"
											style:width={`${row.progresso_pct}%`}
										></div>
									</div>
									<span class="shrink-0 font-mono text-xs text-text-secondary">
										{row.progresso_pct}%
									</span>
								</div>
							</td>
							<td class="{tdCls} whitespace-nowrap font-mono text-sm text-text-secondary">
								{#if row.data_inicio}
									<time datetime={row.data_inicio}>{formatIsoDateBR(row.data_inicio)}</time>
								{:else}
									<span class="italic text-text-muted">—</span>
								{/if}
							</td>
							<td class="{tdCls} whitespace-nowrap font-mono text-sm text-text-secondary">
								{#if row.data_fim}
									<time datetime={row.data_fim}>{formatIsoDateBR(row.data_fim)}</time>
								{:else}
									<span class="italic text-text-muted">—</span>
								{/if}
							</td>
							<td class="{tdCls} whitespace-nowrap text-center">
								<!-- Atrasado implica Vigente: mostrar só um chip. -->
								{#if row.atrasado}
									<span class="chip chip--danger">Atrasado</span>
								{:else}
									<span class="chip {projectStatusChipClass(row.status)}">{row.status}</span>
								{/if}
							</td>
							{#if temRemovivel}
								<td class="{tdCls} text-center">
									{#if row.pode_remover}
										<button
											type="button"
											onclick={() => onRemover(row)}
											title="Remover da coleção"
											aria-label={`Remover ${row.nome} da coleção`}
											class="inline-flex h-8 w-8 items-center justify-center text-sm text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-danger"
										>
											<AppIcon id="exclusao" size={16} />
										</button>
									{/if}
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
