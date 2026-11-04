<script lang="ts">
	/**
	 * Índice de Coleções (tela 3a). Consome `GET /api/colecoes` via
	 * `$lib/api/collections` (SWR) e renderiza o grid de ColecaoCard —
	 * Favoritos sempre primeiro — com busca e ordenação client-side (o teto é
	 * 20 coleções por usuário; não há filtro server-side).
	 *
	 * Mutações: criar via NovaColecaoModal (2 passos, POST atômico), editar
	 * identidade num modal próprio (mesmo formulário do passo 1), compartilhar
	 * (CompartilharColecaoModal) e apagar com confirmação destrutiva
	 * (`confirmAction`). Toda escrita invalida o cache no client de API; a tela
	 * só re-busca.
	 *
	 * Fase 2: o GET já devolve as coleções compartilhadas comigo depois das
	 * minhas — os chips de escopo apenas ESTREITAM a lista (nenhum ativo = tudo)
	 * e só aparecem quando existe alguma coleção alheia. Editar/compartilhar/
	 * apagar seguem exclusivos do dono.
	 *
	 * Convites PENDENTES (`GET /api/colecoes/convites`) ficam num painel próprio
	 * no topo (ColecaoConvitesPainel), fora do grid, das contagens e do
	 * catálogo de `/projetos`. A lista se re-busca quando o sino percebe que o
	 * conjunto de convites mudou (convite novo chegou ou foi revogado).
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import {
		apagarColecao,
		fetchColecoes,
		fetchConvites,
		peekColecoes,
		peekConvites,
		peekIaSugestoesDisponivel
	} from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import type {
		ColecaoResumo,
		ColecaoSugerida,
		ConviteColecao
	} from '$lib/types/collections';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import FilterChipGroup from '$lib/components/FilterChipGroup.svelte';
	import ColecaoCard from '$lib/components/ColecaoCard.svelte';
	import ColecaoConvitesPainel from '$lib/components/ColecaoConvitesPainel.svelte';
	import NovaColecaoModal from '$lib/components/NovaColecaoModal.svelte';
	import SugerirColecoesModal from '$lib/components/SugerirColecoesModal.svelte';
	import CompartilharColecaoModal from '$lib/components/CompartilharColecaoModal.svelte';
	import EditarColecaoModal from '$lib/components/EditarColecaoModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import ColecoesSkeleton from '$lib/components/skeletons/ColecoesSkeleton.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TopnavIcon from '$lib/components/TopnavIcon.svelte';
	import { confirmAction } from '$lib/stores/confirm';
	import { flash } from '$lib/stores/flash';
	import { notificationSummary } from '$lib/stores/notificationSummary';
	import { indiceRecarregaApos, type DesfechoConvite } from '$lib/utils/conviteColecao';

	type LoadState = 'loading' | 'ready' | 'error';
	type Ordenacao = 'criacao' | 'nome';
	/** `''` = nenhum chip ativo, isto é, minhas + compartilhadas comigo. */
	type Escopo = '' | 'minhas' | 'compartilhadas';

	const initialData = peekColecoes();
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let colecoes = $state<ColecaoResumo[] | null>(initialData);
	let errorMessage = $state<string>('');

	// Filtros client-side (dataset completo já está na tela).
	let busca = $state('');
	let ordenacao = $state<Ordenacao>('criacao');
	let escopo = $state<Escopo>('');

	const ORDENACAO_OPTIONS: SelectMenuOption[] = [
		{ value: 'criacao', label: 'Data de criação' },
		{ value: 'nome', label: 'Nome' }
	];

	const ESCOPO_OPTIONS = [
		{ id: 'minhas', label: 'Minhas coleções' },
		{ id: 'compartilhadas', label: 'Compartilhadas comigo' }
	];

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		const cached = peekColecoes();
		if (cached) {
			colecoes = cached;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await fetchColecoes(controller.signal);
			if (controller.signal.aborted) return;
			colecoes = next;
			iaDisponivel = peekIaSugestoesDisponivel() ?? false;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message = err instanceof Error ? err.message : 'Falha ao carregar as coleções.';
			// Revalidação falhou com dado stale na tela: mantém o grid e avisa.
			if (colecoes) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			loadState = 'error';
		}
	}

	// ── Convites pendentes (painel próprio no topo; fora do grid e das contagens) ─
	let convites = $state<ConviteColecao[]>(peekConvites() ?? []);
	let convitesInFlight: AbortController | null = null;

	/** Falha aqui é silenciosa: o painel é extra e o sino continua avisando. */
	async function loadConvites(): Promise<void> {
		convitesInFlight?.abort();
		const controller = new AbortController();
		convitesInFlight = controller;
		try {
			const next = await fetchConvites(controller.signal);
			if (!controller.signal.aborted) convites = next;
		} catch {
			// Mantém a última lista boa.
		}
	}

	function onConviteRespondido(convite: ConviteColecao, desfecho: DesfechoConvite): void {
		if (desfecho.tipo === 'cancelado' || desfecho.tipo === 'erro') return;
		convites = convites.filter((c) => c.id !== convite.id);
		if (indiceRecarregaApos(desfecho)) void load();
	}

	// O sino vê convite novo (ou revogado) antes desta tela: re-busca quando o
	// CONJUNTO de ids muda. A 1ª leitura só registra a base (o mount já buscou).
	let assinaturaConvites: string | null = null;
	$effect(() => {
		const resumo = $notificationSummary;
		if (!resumo) return;
		const assinatura = resumo.convites
			.map((c) => c.collection_id)
			.sort((a, b) => a - b)
			.join(',');
		const anterior = assinaturaConvites;
		assinaturaConvites = assinatura;
		if (anterior !== null && anterior !== assinatura) void loadConvites();
	});

	onMount(() => {
		void load();
		void loadConvites();
		return () => {
			inFlight?.abort();
			convitesInFlight?.abort();
		};
	});

	const COMBINING_MARKS = /[̀-ͯ]/g;
	const norm = (s: string): string =>
		s.normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();

	const temCompartilhada = $derived((colecoes ?? []).some((c) => c.papel !== 'dono'));
	// Sem coleção alheia não há o que estreitar: os chips somem e o escopo é neutro.
	const escopoAtivo = $derived<Escopo>(temCompartilhada ? escopo : '');

	function noEscopo(colecao: ColecaoResumo): boolean {
		if (escopoAtivo === 'minhas') return colecao.papel === 'dono';
		if (escopoAtivo === 'compartilhadas') return colecao.papel !== 'dono';
		return true;
	}

	const visiveis = $derived.by<ColecaoResumo[]>(() => {
		if (!colecoes) return [];
		const termo = norm(busca.trim());
		const filtradas = colecoes.filter((c) => {
			if (!noEscopo(c)) return false;
			if (!termo) return true;
			return norm(c.nome).includes(termo) || norm(c.descricao ?? '').includes(termo);
		});
		filtradas.sort((a, b) => {
			// Favoritos sempre primeiro, independentemente da ordenação.
			if (a.tipo !== b.tipo) return a.tipo === 'favoritos' ? -1 : 1;
			if (ordenacao === 'nome') return a.nome.localeCompare(b.nome, 'pt-BR');
			const porCriacao = b.created_at.localeCompare(a.created_at);
			return porCriacao !== 0 ? porCriacao : b.id - a.id;
		});
		return filtradas;
	});

	const totalColecoes = $derived(colecoes?.length ?? 0);
	const totalProjetos = $derived(
		(colecoes ?? []).reduce((soma, c) => soma + c.projetos, 0)
	);

	// ── Criar ────────────────────────────────────────────────────────────────
	let createOpen = $state(false);
	/** Sugestão de IA aceita: pré-preenche o modal de criação até ele fechar. */
	let sugestaoAceita = $state<ColecaoSugerida | null>(null);

	function fecharCriacao(): void {
		createOpen = false;
		sugestaoAceita = null;
	}

	function onColecaoCriada(colecao: ColecaoResumo): void {
		// Compartilhamento inicial nasce convite pendente: o recibo diz isso.
		const convidados = colecao.destinatarios_total ?? 0;
		flash.success(`Coleção "${colecao.nome}" criada.`, {
			description:
				convidados > 0
					? `Convite enviado para ${convidados} ${convidados === 1 ? 'destinatário' : 'destinatários'}.`
					: undefined
		});
		// Aceite de sugestão: fecha o modal de sugestões; reabrir refaz o GET
		// barato e o cartão aceito já não volta (deixou de ser pendente).
		if (sugestaoAceita) sugerirOpen = false;
		void load();
	}

	// ── Sugerir com IA ───────────────────────────────────────────────────────
	let sugerirOpen = $state(false);
	// Flag vem do GET /api/colecoes; oculto até o servidor confirmar. O 503 em
	// runtime (onIndisponivel) segue como fallback caso a feature caia no meio.
	let iaDisponivel = $state(peekIaSugestoesDisponivel() ?? false);

	function criarDaSugestao(sugestao: ColecaoSugerida): void {
		sugestaoAceita = sugestao;
		createOpen = true;
	}

	// ── Editar (modal próprio: mesmo formulário do passo 1 da criação) ───────
	let editTarget = $state<ColecaoResumo | null>(null);

	function onColecaoEditada(atualizada: ColecaoResumo): void {
		editTarget = null;
		flash.success(`Coleção "${atualizada.nome}" atualizada.`);
		void load();
	}


	// ── Compartilhar (só dono; o modal cuida das concessões) ─────────────────
	let shareTarget = $state<ColecaoResumo | null>(null);

	// ── Apagar ───────────────────────────────────────────────────────────────
	async function confirmarApagar(colecao: ColecaoResumo): Promise<void> {
		const ok = await confirmAction({
			title: `Apagar a coleção "${colecao.nome}"?`,
			description:
				'Os projetos continuam intactos — apenas a coleção deixa de existir. Esta ação não pode ser desfeita.',
			confirmLabel: 'Apagar coleção',
			busyLabel: 'Apagando…',
			run: async () => {
				await apagarColecao(colecao.id);
			}
		});
		if (!ok) return;
		flash.success(`Coleção "${colecao.nome}" apagada.`);
		void load();
	}
</script>

<svelte:head>
	<title>ProjetosRJ — Coleções</title>
</svelte:head>

<section aria-labelledby="colecoes-title" class="flex flex-col gap-4">
	<!-- CARD ÚNICO header + toolbar (padrão de Projetos/Pendentes/Tarefas). -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="colecoes-title">
			{#snippet titleContent()}
				<span>Coleções</span>
				{#if colecoes}
					<CountBadge class="ml-2">
						{totalColecoes}
						{totalColecoes === 1 ? 'coleção' : 'coleções'} · {totalProjetos}
						{totalProjetos === 1 ? 'projeto' : 'projetos'}
					</CountBadge>
				{/if}
			{/snippet}
			{#snippet actions()}
				{#if iaDisponivel}
					<Button variant="secondary" size="sm" onclick={() => (sugerirOpen = true)}>
						{#snippet icon()}
							<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>
						{/snippet}
						Sugerir com IA
					</Button>
				{/if}
				<Button size="sm" onclick={() => (createOpen = true)}>
					{#snippet icon()}
						<i class="fas fa-plus" aria-hidden="true"></i>
					{/snippet}
					Nova coleção
				</Button>
			{/snippet}
		</PageHeader>

		<!-- Toolbar embutida: busca + ordenação client-side + escopo do MVP. -->
		<form
			class="flex flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5"
			role="search"
			aria-label="Filtros de coleções"
			onsubmit={(e) => e.preventDefault()}
		>
			<div class="relative w-full min-w-[14rem] max-w-[26rem]">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="colecoesSearch"
					name="search"
					type="search"
					autocomplete="off"
					bind:value={busca}
					aria-label="Buscar coleção"
					placeholder="Buscar coleção"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
			</div>

			<div class="min-w-[13rem]">
				<SelectMenu
					id="colecoesOrdenacao"
					options={ORDENACAO_OPTIONS}
					value={ordenacao}
					onSelect={(v) => (ordenacao = (v ?? 'criacao') as Ordenacao)}
					ariaLabel="Ordenar coleções"
				/>
			</div>

			{#if temCompartilhada}
				<div class="ml-auto">
					<!-- Clicar no chip ativo desliga o filtro e volta a mostrar tudo. -->
					<FilterChipGroup
						label="Escopo das coleções"
						options={ESCOPO_OPTIONS}
						value={escopoAtivo}
						onchange={(id) => (escopo = id === escopoAtivo ? '' : (id as Escopo))}
					/>
				</div>
			{/if}
		</form>
	</div>

	{#if convites.length > 0}
		<ColecaoConvitesPainel {convites} onRespondido={onConviteRespondido} />
	{/if}

	{#if loadState === 'loading' && !colecoes}
		<p role="status" aria-live="polite" class="sr-only">Carregando coleções…</p>
		<ColecoesSkeleton />
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if colecoes}
		{#if visiveis.length === 0}
			<!-- Busca sem resultado (mesmo quadro do estado vazio de Projetos). -->
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-xl text-brand"
				>
					<AppIcon id="projetos" size={28} />
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					Nenhuma coleção encontrada
				</h2>
				<p class="mb-0 mt-1.5 text-sm text-text-muted">
					{#if busca.trim()}
						Nenhuma coleção corresponde a "{busca.trim()}". Ajuste a busca ou crie uma nova.
					{:else if escopoAtivo === 'compartilhadas'}
						Ninguém compartilhou uma coleção com você ainda.
					{:else}
						Você ainda não tem coleções próprias. Crie a primeira.
					{/if}
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-busy={loadState !== 'ready'}>
				{#each visiveis as colecao (colecao.id)}
					{@const gerenciavel = colecao.tipo === 'custom' && colecao.papel === 'dono'}
					<ColecaoCard
						{colecao}
						href={`${base}/colecoes/${colecao.id}`}
						onEditar={gerenciavel ? () => (editTarget = colecao) : undefined}
						onCompartilhar={gerenciavel ? () => (shareTarget = colecao) : undefined}
						onApagar={gerenciavel ? () => void confirmarApagar(colecao) : undefined}
					/>
				{/each}

				<!-- Card fantasma: cria coleção (button tracejado, a11y de verdade). -->
				<button
					type="button"
					onclick={() => (createOpen = true)}
					class="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface p-4 text-center transition-ui duration-fast hover:border-brand hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<span
						class="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-wash-brand text-brand"
						aria-hidden="true"
					>
						<TopnavIcon kind="colecoes" active={false} />
					</span>
					<span class="text-sm font-semibold text-text-primary">Criar uma nova coleção</span>
				</button>
			</div>
		{/if}
	{/if}
</section>

<!-- Antes do NovaColecaoModal no DOM: o de criação empilha por cima e fica com o Esc. -->
<SugerirColecoesModal
	open={sugerirOpen}
	onClose={() => (sugerirOpen = false)}
	onCriar={criarDaSugestao}
	onIndisponivel={() => (iaDisponivel = false)}
/>

<NovaColecaoModal
	open={createOpen}
	nomeInicial={sugestaoAceita?.nome}
	descricaoInicial={sugestaoAceita?.descricao ?? undefined}
	projectIdsIniciais={sugestaoAceita?.project_ids}
	sugestaoId={sugestaoAceita?.id}
	onClose={fecharCriacao}
	onCreated={onColecaoCriada}
/>

{#if shareTarget}
	<CompartilharColecaoModal
		colecao={shareTarget}
		onClose={() => (shareTarget = null)}
		onChanged={() => void load()}
	/>
{/if}

<!-- Edição de identidade: mesmo formulário do passo 1 do modal de criação. -->
{#if editTarget}
	<EditarColecaoModal
		colecao={editTarget}
		onClose={() => (editTarget = null)}
		onSalva={onColecaoEditada}
	/>
{/if}
