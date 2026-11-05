<script lang="ts">
	/**
	 * Modal "Nova coleção" no conceito de CAPA (design "Coleções 3a"): o topo é
	 * a própria capa da coleção (`ColecaoCapaEditavel`) — nome e descrição digitados
	 * nela; cor, ícone e as áreas dos projetos marcados a atualizam na hora.
	 * Embaixo, à esquerda, "Aparência" e "Quem enxerga"; à direita, o
	 * ColecaoProjectPicker com "N de M · Limpar". Chrome (backdrop/Esc/
	 * focus-trap) é o Modal base, em modo `flush` para a capa sangrar.
	 *
	 * A criação é ATÔMICA: "Criar coleção" faz um único POST /api/colecoes com
	 * `project_ids` e `compartilhamentos`. Depois dela o modal NÃO fecha: vira a
	 * tela de sucesso (`NovaColecaoSucesso`) com a capa pronta, os números e
	 * "Criar outra" / "Abrir coleção". `onCreated` avisa a página para
	 * re-buscar o grid por trás.
	 *
	 * "Quem enxerga": a coleção NASCE PESSOAL ("Só eu"); compartilhando, cada
	 * destinatário recebe um CONVITE pendente (`ColecaoQuemEnxerga`).
	 * Favoritos nunca passa por aqui — este modal só cria coleções `custom`.
	 *
	 * O picker lista só o que o backend aceita na criação (`visibilidade:
	 * propria` — área ou convite, sem a visibilidade derivada de outra coleção):
	 * um projeto recusado derrubaria a criação inteira.
	 *
	 * Pode abrir PRÉ-PREENCHIDO (`nomeInicial`/`descricaoInicial`/
	 * `projectIdsIniciais`) no aceite de uma sugestão de IA — daí em diante o
	 * fluxo é o mesmo de sempre, com o usuário revisando ícone, cor e quem
	 * enxerga antes de confirmar. Nesse caso `sugestaoId` viaja no POST para o
	 * backend marcar a sugestão como aceita.
	 */
	import { tick } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { base } from '$app/paths';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoAparencia from '$lib/components/ColecaoAparencia.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import ColecaoQuemEnxerga from '$lib/components/ColecaoQuemEnxerga.svelte';
	import ColecaoCapaEditavel from '$lib/components/ColecaoCapaEditavel.svelte';
	import NovaColecaoSucesso from '$lib/components/NovaColecaoSucesso.svelte';
	import { criarColecao } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { areasDasSiglas } from '$lib/utils/colecaoCapa';
	import {
		compartilhamentosDaCriacao,
		reciboDeVisibilidade,
		type DestinatarioNovo
	} from '$lib/utils/novaColecaoDestinatarios';
	import type { Project } from '$lib/types/entities';
	import type { ColecaoResumo, CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		/** Modal aberto? (controlado pela página). */
		open: boolean;
		/** Fecha o modal (✕, Esc, backdrop, Cancelar — também na tela de sucesso). */
		onClose: () => void;
		/** Coleção criada; o modal segue aberto, na tela de sucesso. */
		onCreated: (colecao: ColecaoResumo) => void;
		/** Nome inicial (aceite de sugestão de IA); ausente = campo em branco. */
		nomeInicial?: string;
		/** Descrição inicial (aceite de sugestão de IA). */
		descricaoInicial?: string;
		/** Projetos já marcados (aceite de sugestão de IA). */
		projectIdsIniciais?: number[];
		/** Sugestão de IA que originou a coleção; ausente = criação avulsa. */
		sugestaoId?: number;
	}

	let {
		open,
		onClose,
		onCreated,
		nomeInicial,
		descricaoInicial,
		projectIdsIniciais,
		sugestaoId
	}: Props = $props();

	const TITULO_ID = 'nova-colecao-title';
	// Espelham o backend (`NOME_MAX_COLECAO`, `_validar_descricao`).
	const NOME_MAX = 100;
	const DESCRICAO_MAX = 200;

	let nome = $state('');
	let descricao = $state('');
	let icone = $state<CollectionIconId>('camadas');
	let cor = $state<CollectionColorId>('primary');
	let selecionados = $state<number[]>([]);
	let totalProjetos = $state<number | null>(null);
	let soEu = $state(true);
	let destinatarios = $state<DestinatarioNovo[]>([]);
	let triedSubmit = $state(false);
	let submitting = $state(false);
	let erro = $state<string | null>(null);
	let nomeInputEl = $state<HTMLInputElement | null>(null);

	/** Coleção recém-criada: presente = tela de sucesso no lugar do formulário. */
	let criada = $state<ColecaoResumo | null>(null);
	let recibo = $state('');
	let criadaPessoal = $state(true);

	// Sigla de cada projeto já visto no picker: alimenta a pílula da capa ao vivo.
	const siglaPorProjeto = new SvelteMap<number, string | null>();
	const areasSelecionadas = $derived(
		areasDasSiglas(
			selecionados.filter((id) => siglaPorProjeto.has(id)).map((id) => siglaPorProjeto.get(id) ?? null)
		)
	);

	const nomeInvalido = $derived(triedSubmit && !nome.trim());

	function guardarSiglas(projetos: Project[]): void {
		for (const projeto of projetos) siglaPorProjeto.set(projeto.id, projeto.orgao_sigla);
	}

	let prevOpen = false;
	$effect(() => {
		if (open && !prevOpen) resetar();
		prevOpen = open;
	});

	function resetar(): void {
		nome = nomeInicial ?? '';
		descricao = descricaoInicial ?? '';
		icone = 'camadas';
		cor = 'primary';
		selecionados = projectIdsIniciais ? [...projectIdsIniciais] : [];
		soEu = true;
		destinatarios = [];
		triedSubmit = false;
		submitting = false;
		erro = null;
		criada = null;
		focusAfterTick(() => nomeInputEl);
	}

	// offsetParent null = display:none; focar alvo invisível derrubaria o trap.
	function focusAfterTick(getEl: () => HTMLElement | null): void {
		void tick().then(() => {
			const el = getEl();
			if (el && el.offsetParent !== null) el.focus();
		});
	}

	function requestClose(): void {
		if (submitting) return;
		onClose();
	}

	async function criar(): Promise<void> {
		if (submitting) return;
		triedSubmit = true;
		if (!nome.trim()) {
			nomeInputEl?.focus();
			return;
		}
		submitting = true;
		erro = null;
		try {
			const colecao = await criarColecao({
				nome: nome.trim(),
				descricao: descricao.trim() || null,
				icone,
				cor,
				project_ids: selecionados.length > 0 ? selecionados : undefined,
				compartilhamentos: compartilhamentosDaCriacao(soEu, destinatarios),
				sugestao_id: sugestaoId
			});
			recibo = reciboDeVisibilidade(soEu, destinatarios);
			criadaPessoal = soEu || destinatarios.length === 0;
			criada = colecao;
			onCreated(colecao);
		} catch (err) {
			erro =
				err instanceof ApiClientError ? err.message : 'Não foi possível criar a coleção.';
		} finally {
			submitting = false;
		}
	}
</script>

{#if open}
	<Modal
		labelId={TITULO_ID}
		flush
		maxWidth={criada ? 'max-w-[520px]' : 'max-w-[1000px]'}
		onBackdrop={requestClose}
	>
		{#if criada}
			<NovaColecaoSucesso
				titleId={TITULO_ID}
				colecao={criada}
				{recibo}
				pessoal={criadaPessoal}
				href={`${base}/colecoes/${criada.id}`}
				onFechar={requestClose}
				onCriarOutra={resetar}
			/>
		{:else}
			<div class="flex max-h-[calc(100dvh-2rem)] flex-col">
				<ColecaoCapaEditavel
					titleId={TITULO_ID}
					titulo="Nova coleção"
					{icone}
					{cor}
					bind:nome
					bind:descricao
					bind:nomeInputEl
					areas={areasSelecionadas}
					{nomeInvalido}
					nomeMax={NOME_MAX}
					descricaoMax={DESCRICAO_MAX}
					fecharDesabilitado={submitting}
					onFechar={requestClose}
				/>

				<div class="thin-scroll min-h-0 flex-1 overflow-y-auto">
					<div class="grid gap-6 px-5 py-6 sm:px-7 md:grid-cols-[350px_minmax(0,1fr)] md:gap-8">
						<div class="flex min-w-0 flex-col gap-5">
							<ColecaoAparencia bind:icone bind:cor idPrefix="nc" />
							<ColecaoQuemEnxerga bind:soEu bind:destinatarios idPrefix="nc" />
						</div>

						<!-- md+: conteúdo fora do fluxo para a lista não inflar a linha do grid — a
						     altura vem da coluna esquerda (com piso), e as bases alinham. -->
						<div class="relative min-w-0 md:min-h-[400px]">
							<div class="flex min-w-0 flex-col gap-2.5 md:absolute md:inset-0">
								<div class="flex items-baseline justify-between gap-3">
									<span class="text-sm font-semibold text-text-secondary">Projetos da sua área</span>
									<span class="shrink-0 text-xs text-text-muted">
										{selecionados.length}{totalProjetos !== null ? ` de ${totalProjetos}` : ''}
										{#if selecionados.length > 0}
											·
											<button
												type="button"
												onclick={() => (selecionados = [])}
												class="font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
											>
												Limpar
											</button>
										{/if}
									</span>
								</div>
								<ColecaoProjectPicker
									{selecionados}
									visibilidade="propria"
									preencher
									mostrarTodosInicial={(projectIdsIniciais?.length ?? 0) > 0}
									onchange={(ids) => (selecionados = ids)}
									ontotal={(total) => (totalProjetos = total)}
									onprojetosCarregados={guardarSiglas}
								/>
							</div>
						</div>
					</div>
				</div>

				{#if erro}
					<div class="px-5 pb-3 sm:px-7">
						<StateBanner tone="danger" title={erro} />
					</div>
				{/if}

				<footer
					class="flex items-center justify-end gap-2.5 border-t border-border-subtle px-5 py-4 sm:px-7"
				>
					<Button variant="secondary" onclick={requestClose} disabled={submitting}>Cancelar</Button>
					<!-- Sem nome o botão fica esmaecido mas clicável: o clique explica o que
					     falta. Opacidade no wrapper — `class` no Button troca as classes dele. -->
					<div class="transition-opacity duration-slow {nome.trim() ? '' : 'opacity-50'}">
						<Button onclick={() => void criar()} disabled={submitting}>
							{submitting ? 'Criando…' : 'Criar coleção'}
						</Button>
					</div>
				</footer>
			</div>
		{/if}
	</Modal>
{/if}
