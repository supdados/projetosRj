<script lang="ts">
	/**
	 * Modal "Compartilhar coleção" (Fase 2, §5.1) — SÓ O DONO abre: as rotas de
	 * compartilhamento respondem 403 para qualquer outro papel, e a página é quem
	 * decide mostrar o item de menu (`papel === 'dono'`).
	 *
	 * Molde: `CompartilharProjetoModal.svelte` (alvo pessoa|área, autocomplete,
	 * lista de vínculos com revogação confirmada), reduzido a uma tela só — a
	 * coleção tem bem menos concessões que um projeto e não há expiração nem
	 * herança para exibir. O chrome (backdrop/Esc/focus-trap) é o `Modal` base.
	 *
	 * Compartilhar CONCEDE ACESSO aos projetos da coleção (acesso derivado, não
	 * convite materializado): por isso o aviso fica sempre visível, acima do
	 * formulário. Área = órgão EXATO, sem subárvore (decisão de produto 2026-08-07).
	 *
	 * Re-busca a lista após cada mutação (o backend faz upsert de papel) e avisa
	 * o chamador por `onChanged` — o resumo da coleção (`compartilhada`) muda.
	 */
	import { onMount, tick } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import { ApiClientError } from '$lib/api/client';
	import { criarShare, fetchShares, revogarShare } from '$lib/api/collections';
	import { fetchAreas, type AreaOption } from '$lib/api/areas';
	import { searchInvitableUsers } from '$lib/api/projectMembers';
	import { confirmAction } from '$lib/stores/confirm';
	import { buildOrgaoTree, flattenTreeWithPath, type OrgaoTreeRow } from '$lib/utils/orgaoTree';
	import { formatIsoDateBR } from '$lib/utils/dateFormat';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { UsuarioConvidavel } from '$lib/types/projectMembers';
	import type {
		ColecaoResumo,
		ColecaoShare,
		ColecaoShareCreatePayload,
		PapelCompartilhamento
	} from '$lib/types/collections';

	interface Props {
		/** Coleção do dono (Favoritos nunca é compartilhável — 422 no backend). */
		colecao: ColecaoResumo;
		/** Fecha o modal (✕, Esc, backdrop, "Concluir"). */
		onClose: () => void;
		/** Houve concessão/revogação — a página deve re-buscar o índice. */
		onChanged?: () => void;
	}

	let { colecao, onClose, onChanged }: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';
	/** Alvo da concessão: uma pessoa (busca) ou um órgão exato. */
	type AlvoModo = 'pessoa' | 'area';
	/** `AreaOption` no formato que `buildOrgaoTree` espera (`value` + `pai_id`). */
	type OrgaoCandidato = AreaOption & { value: number };

	const PAPEL_OPCOES: { id: PapelCompartilhamento; label: string; hint: string }[] = [
		{ id: 'viewer', label: 'Leitor', hint: 'Vê a coleção e seus projetos' },
		{ id: 'editor', label: 'Editor', hint: 'Também adiciona e remove projetos' }
	];
	const PAPEL_MENU: SelectMenuOption[] = PAPEL_OPCOES.map((o) => ({ value: o.id, label: o.label }));

	const isFavoritos = $derived(colecao.tipo === 'favoritos');

	let loadState = $state<LoadState>('loading');
	let shares = $state<ColecaoShare[]>([]);
	let loadError = $state('');

	let modo = $state<AlvoModo>('pessoa');
	let papel = $state<PapelCompartilhamento>('viewer');
	let enviando = $state(false);
	let formError = $state('');
	let resumoAcao = $state('');
	/** Id do share em mutação — desabilita só aquela linha. */
	let linhaOcupada = $state<number | null>(null);

	let termo = $state('');
	let resultados = $state<UsuarioConvidavel[]>([]);
	let buscando = $state(false);
	let listaAberta = $state(false);
	let destaque = $state(-1);
	let pessoa = $state<UsuarioConvidavel | null>(null);

	let orgaos = $state<AreaOption[]>([]);
	let orgaosCarregando = $state(false);
	let termoOrgao = $state('');
	let listaOrgaoAberta = $state(false);
	let destaqueOrgao = $state(-1);
	let orgao = $state<AreaOption | null>(null);

	let campoAlvo = $state<HTMLDivElement | null>(null);

	const orgaoCandidatos = $derived<OrgaoCandidato[]>(orgaos.map((a) => ({ ...a, value: a.id })));
	const linhasOrgao = $derived.by<OrgaoTreeRow<OrgaoCandidato>[]>(() =>
		flattenTreeWithPath(buildOrgaoTree(orgaoCandidatos), termoOrgao, { omitRootAncestor: true })
	);
	const alvoEscolhido = $derived(modo === 'pessoa' ? pessoa !== null : orgao !== null);
	const podeCompartilhar = $derived(alvoEscolhido && !enviando);

	function mensagemDeErro(err: unknown, fallback: string): string {
		if (err instanceof ApiClientError) return err.message;
		return err instanceof Error ? err.message : fallback;
	}

	async function carregar(): Promise<void> {
		loadState = 'loading';
		loadError = '';
		try {
			shares = await fetchShares(colecao.id);
			loadState = 'ready';
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			loadError = mensagemDeErro(err, 'Falha ao carregar os compartilhamentos.');
			loadState = 'error';
		}
	}

	async function recarregar(): Promise<void> {
		try {
			shares = await fetchShares(colecao.id);
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = mensagemDeErro(err, 'Falha ao recarregar os compartilhamentos.');
		}
		onChanged?.();
	}

	onMount(() => {
		if (isFavoritos) {
			loadState = 'ready';
			return;
		}
		void carregar();
		void focarCampoDoModo();
	});

	// Autocomplete de pessoas: 250ms de folga e aborto da busca anterior a cada tecla.
	$effect(() => {
		const q = termo.trim();
		if (modo !== 'pessoa' || q.length < 2 || pessoa !== null) {
			resultados = [];
			buscando = false;
			return;
		}
		const controller = new AbortController();
		const timer = setTimeout(() => {
			buscando = true;
			searchInvitableUsers(q, controller.signal)
				.then((achados) => {
					resultados = achados;
					listaAberta = true;
					destaque = achados.length > 0 ? 0 : -1;
				})
				.catch((err: unknown) => {
					if (controller.signal.aborted) return;
					resultados = [];
					formError = mensagemDeErro(err, 'Falha ao buscar pessoas.');
				})
				.finally(() => {
					if (!controller.signal.aborted) buscando = false;
				});
		}, 250);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	// Clique fora do campo fecha os dois autocompletes (pessoas e áreas).
	$effect(() => {
		if (!listaAberta && !listaOrgaoAberta) return;
		const fecharSeFora = (event: PointerEvent): void => {
			if (campoAlvo?.contains(event.target as Node)) return;
			listaAberta = false;
			listaOrgaoAberta = false;
		};
		window.addEventListener('pointerdown', fecharSeFora, true);
		return () => window.removeEventListener('pointerdown', fecharSeFora, true);
	});

	async function focarCampoDoModo(): Promise<void> {
		if (modo === 'area') await carregarOrgaos();
		await tick();
		document.getElementById(modo === 'area' ? 'cc-area' : 'cc-pessoa')?.focus();
	}

	function trocarModo(alvo: AlvoModo): void {
		if (modo === alvo) return;
		modo = alvo;
		formError = '';
		listaAberta = false;
		listaOrgaoAberta = false;
		void focarCampoDoModo();
	}

	/** Catálogo completo de órgãos, uma vez por abertura do modal (busca client-side). */
	async function carregarOrgaos(): Promise<void> {
		if (orgaos.length > 0 || orgaosCarregando) return;
		orgaosCarregando = true;
		try {
			orgaos = (await fetchAreas()).areas;
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = mensagemDeErro(err, 'Falha ao carregar as áreas.');
		} finally {
			orgaosCarregando = false;
		}
	}

	function escolherPessoa(usuario: UsuarioConvidavel): void {
		pessoa = usuario;
		termo = usuario.name;
		resultados = [];
		listaAberta = false;
		formError = '';
	}

	function limparPessoa(): void {
		pessoa = null;
		termo = '';
		resultados = [];
		listaAberta = false;
		destaque = -1;
	}

	function escolherOrgao(opcao: AreaOption): void {
		orgao = opcao;
		termoOrgao = opcao.sigla || opcao.nome;
		listaOrgaoAberta = false;
		formError = '';
	}

	function limparOrgao(): void {
		orgao = null;
		termoOrgao = '';
		listaOrgaoAberta = false;
		destaqueOrgao = -1;
	}

	function onPessoaKeydown(event: KeyboardEvent): void {
		if (!listaAberta || resultados.length === 0) return;
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			destaque = (destaque + 1) % resultados.length;
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			destaque = (destaque - 1 + resultados.length) % resultados.length;
		} else if (event.key === 'Enter' && destaque >= 0) {
			event.preventDefault();
			escolherPessoa(resultados[destaque]);
		} else if (event.key === 'Escape') {
			event.stopPropagation();
			listaAberta = false;
		}
	}

	function onOrgaoKeydown(event: KeyboardEvent): void {
		if (!listaOrgaoAberta || linhasOrgao.length === 0) return;
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			destaqueOrgao = (destaqueOrgao + 1) % linhasOrgao.length;
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			destaqueOrgao = (destaqueOrgao - 1 + linhasOrgao.length) % linhasOrgao.length;
		} else if (event.key === 'Enter' && destaqueOrgao >= 0) {
			event.preventDefault();
			escolherOrgao(linhasOrgao[destaqueOrgao].option);
		} else if (event.key === 'Escape') {
			event.stopPropagation();
			listaOrgaoAberta = false;
		}
	}

	/** Alvo atual como corpo XOR da rota (`user_id` OU `orgao_id`, nunca os dois). */
	function payloadDoAlvo(alvo: PapelCompartilhamento): ColecaoShareCreatePayload | null {
		if (modo === 'pessoa') return pessoa ? { user_id: pessoa.id, papel: alvo } : null;
		return orgao ? { orgao_id: orgao.id, papel: alvo } : null;
	}

	async function compartilhar(): Promise<void> {
		const payload = payloadDoAlvo(papel);
		if (!payload || enviando) return;
		const nome = modo === 'pessoa' ? (pessoa?.name ?? '') : (orgao?.sigla ?? orgao?.nome ?? '');
		enviando = true;
		formError = '';
		resumoAcao = '';
		try {
			await criarShare(colecao.id, payload);
			limparPessoa();
			limparOrgao();
			resumoAcao = `${nome} agora tem acesso como ${papelLabel(papel)}.`;
			await recarregar();
		} catch (err) {
			formError = mensagemDeErro(err, 'Falha ao compartilhar a coleção.');
		} finally {
			enviando = false;
		}
	}

	/** Troca de papel é o MESMO POST (upsert no backend) com o alvo da linha. */
	function trocarPapel(share: ColecaoShare, valor: string | null): void {
		const novo: PapelCompartilhamento = valor === 'editor' ? 'editor' : 'viewer';
		if (novo === share.papel) return;
		if (share.user_id === null && share.orgao_id === null) {
			formError = 'Não foi possível identificar o destinatário deste compartilhamento.';
			return;
		}
		const payload: ColecaoShareCreatePayload =
			share.user_id !== null
				? { user_id: share.user_id, papel: novo }
				: { orgao_id: share.orgao_id as number, papel: novo };
		void mutarLinha(share.id, () => criarShare(colecao.id, payload).then(() => undefined), 'Falha ao alterar o papel.');
	}

	async function mutarLinha(
		id: number,
		acao: () => Promise<void>,
		fallback: string,
		sucesso?: string
	): Promise<void> {
		linhaOcupada = id;
		formError = '';
		resumoAcao = '';
		try {
			await acao();
			await recarregar();
			if (sucesso) resumoAcao = sucesso;
		} catch (err) {
			formError = mensagemDeErro(err, fallback);
		} finally {
			linhaOcupada = null;
		}
	}

	/** Revogar corta o acesso derivado na hora — confirma citando o destinatário. */
	async function revogar(share: ColecaoShare): Promise<void> {
		const nome = nomeDoShare(share);
		const ok = await confirmAction({
			title: `Revogar o acesso de ${nome}?`,
			description: `${nome} perde o acesso a esta coleção e aos projetos dela imediatamente. Dá para compartilhar de novo depois.`,
			tone: 'danger',
			confirmLabel: 'Revogar acesso',
			cancelLabel: 'Cancelar'
		});
		if (!ok) return;
		void mutarLinha(
			share.id,
			() => revogarShare(colecao.id, share.id),
			'Falha ao revogar o compartilhamento.',
			`Acesso de ${nome} revogado.`
		);
	}

	function papelLabel(valor: PapelCompartilhamento): string {
		return valor === 'editor' ? 'Editor' : 'Leitor';
	}

	function nomeDoShare(share: ColecaoShare): string {
		if (share.user) return share.user.nome;
		return share.orgao ? share.orgao.sigla || share.orgao.nome : 'Destinatário';
	}

	function metaDoShare(share: ColecaoShare): string {
		const origem = share.user ? 'Pessoa' : (share.orgao?.nome ?? 'Área');
		const desde = formatIsoDateBR(share.created_at);
		return desde ? `${origem} · desde ${desde}` : origem;
	}

	function iniciais(nome: string): string {
		const partes = nome.trim().split(/\s+/).filter(Boolean);
		if (partes.length === 0) return '?';
		const primeira = partes[0][0] ?? '';
		const segunda = partes.length > 1 ? (partes[partes.length - 1][0] ?? '') : (partes[0][1] ?? '');
		return (primeira + segunda).toUpperCase();
	}

	function requestClose(): void {
		if (enviando) return;
		onClose();
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
</script>

<Modal labelId="compartilhar-colecao-title" maxWidth="max-w-[600px]" onBackdrop={requestClose}>
	<div class="flex max-h-[80vh] flex-col gap-4">
		<div class="flex items-center gap-3">
			<ColecaoIconTile icone={colecao.icone} cor={colecao.cor} size={36} />
			<div class="flex min-w-0 flex-1 flex-col">
				<h2
					id="compartilhar-colecao-title"
					class="font-heading text-lg font-bold text-text-primary"
				>
					Compartilhar coleção
				</h2>
				<p class="truncate text-xs text-text-muted">{colecao.nome}</p>
			</div>
			<button
				type="button"
				onclick={requestClose}
				disabled={enviando}
				aria-label="Fechar"
				class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<svg
					viewBox="0 0 20 20"
					class="h-4 w-4"
					fill="none"
					stroke="currentColor"
					stroke-width="1.6"
					aria-hidden="true"
				>
					<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
				</svg>
			</button>
		</div>

		{#if isFavoritos}
			<StateBanner
				tone="warning"
				title="Favoritos não pode ser compartilhada"
				description="É uma coleção pessoal do sistema. Crie uma coleção própria para compartilhar projetos."
			/>
			<footer class="flex justify-end border-t border-border-hairline pt-4">
				<Button variant="secondary" onclick={onClose}>Fechar</Button>
			</footer>
		{:else}
			<form
				class="flex flex-col gap-3"
				onsubmit={(e) => {
					e.preventDefault();
					void compartilhar();
				}}
			>
				<div class="flex flex-col gap-1.5">
					<span id="cc-alvo-label" class={labelCls}>Compartilhar com</span>
					<div bind:this={campoAlvo} class="relative">
						<div
							class="flex items-stretch overflow-hidden rounded-control border border-border-strong bg-surface transition-colors duration-fast focus-within:border-brand"
						>
							<div
								class="flex shrink-0 items-stretch border-r border-border-subtle bg-surface-muted"
								role="group"
								aria-labelledby="cc-alvo-label"
							>
								{@render modoBotao('pessoa', 'Pessoa')}
								{@render modoBotao('area', 'Área')}
							</div>

							{#if modo === 'pessoa'}
								<div class="flex min-w-0 flex-1 items-center gap-2 px-3">
									<input
										id="cc-pessoa"
										type="text"
										autocomplete="off"
										role="combobox"
										aria-expanded={listaAberta && resultados.length > 0}
										aria-controls="cc-pessoa-lista"
										aria-autocomplete="list"
										aria-activedescendant={destaque >= 0 && listaAberta
											? `cc-pessoa-op-${destaque}`
											: undefined}
										placeholder="Nome ou usuário…"
										bind:value={termo}
										oninput={() => {
											pessoa = null;
											listaAberta = true;
										}}
										onkeydown={onPessoaKeydown}
										class="min-w-0 flex-1 border-none bg-transparent py-2 text-md text-text-primary outline-none placeholder:text-text-faint"
									/>
									{#if pessoa}
										{@render limparBotao('Limpar pessoa selecionada', limparPessoa)}
									{/if}
								</div>
							{:else}
								<div class="flex min-w-0 flex-1 items-center gap-2 px-3">
									<input
										id="cc-area"
										type="text"
										autocomplete="off"
										role="combobox"
										aria-expanded={listaOrgaoAberta && linhasOrgao.length > 0}
										aria-controls="cc-area-lista"
										aria-autocomplete="list"
										aria-activedescendant={destaqueOrgao >= 0 && listaOrgaoAberta
											? `cc-area-op-${destaqueOrgao}`
											: undefined}
										placeholder={orgaosCarregando ? 'Carregando áreas…' : 'Sigla ou nome da área…'}
										bind:value={termoOrgao}
										oninput={() => {
											orgao = null;
											listaOrgaoAberta = true;
											destaqueOrgao = 0;
										}}
										onclick={() => (listaOrgaoAberta = true)}
										onkeydown={onOrgaoKeydown}
										class="min-w-0 flex-1 border-none bg-transparent py-2 text-md text-text-primary outline-none placeholder:text-text-faint"
									/>
									{#if orgao}
										{@render limparBotao('Limpar área selecionada', limparOrgao)}
									{/if}
								</div>
							{/if}
						</div>

						{#if modo === 'pessoa' && listaAberta && resultados.length > 0}
							<ul
								id="cc-pessoa-lista"
								role="listbox"
								aria-label="Pessoas encontradas"
								class="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-control border border-border-subtle bg-surface-elevated py-1 shadow-lg"
							>
								{#each resultados as usuario, index (usuario.id)}
									<li role="none">
										<button
											type="button"
											role="option"
											id="cc-pessoa-op-{index}"
											aria-selected={index === destaque}
											onclick={() => escolherPessoa(usuario)}
											onmouseenter={() => (destaque = index)}
											class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm text-text-primary hover:bg-surface-muted {index ===
											destaque
												? 'bg-surface-muted'
												: ''}"
										>
											<span class="min-w-0 truncate">
												{usuario.name}
												<span class="text-text-muted">@{usuario.username}</span>
											</span>
											{#if usuario.orgao_sigla}
												<span class="shrink-0 text-xs text-text-secondary">{usuario.orgao_sigla}</span>
											{/if}
										</button>
									</li>
								{/each}
							</ul>
						{:else if modo === 'pessoa' && buscando}
							<p class="text-xs text-text-muted" role="status">Buscando…</p>
						{/if}

						{#if modo === 'area' && listaOrgaoAberta && linhasOrgao.length > 0}
							<ul
								id="cc-area-lista"
								role="listbox"
								aria-label="Áreas encontradas"
								class="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-control border border-border-subtle bg-surface-elevated py-1 shadow-lg"
							>
								{#each linhasOrgao as linha, index (linha.value)}
									<li role="none">
										<button
											type="button"
											role="option"
											id="cc-area-op-{index}"
											aria-selected={index === destaqueOrgao}
											onclick={() => escolherOrgao(linha.option)}
											onmouseenter={() => (destaqueOrgao = index)}
											class="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-muted {index ===
											destaqueOrgao
												? 'bg-surface-muted'
												: ''}"
										>
											<span class="shrink-0 truncate">
												{#if linha.path}<span class="mr-1 text-xs text-text-muted">{linha.path} ›</span
													>{/if}<span class="text-xs font-semibold text-text-primary"
													>{linha.option.sigla}</span
												>
											</span>
											<span class="min-w-0 flex-1 truncate text-xs text-text-secondary">
												{linha.option.nome}
											</span>
										</button>
									</li>
								{/each}
							</ul>
						{/if}
					</div>

				</div>

				<fieldset class="flex flex-col gap-1.5">
					<legend class="{labelCls} mb-1.5">Papel</legend>
					<div class="grid grid-cols-2 gap-2">
						{#each PAPEL_OPCOES as opcao (opcao.id)}
							{@const ativo = papel === opcao.id}
							<label
								class="flex cursor-pointer flex-col gap-0.5 rounded-control border px-3 py-2 transition-colors duration-fast focus-within:ring-2 focus-within:ring-brand {ativo
									? 'border-brand bg-wash-brand'
									: 'border-border-subtle hover:bg-surface-muted'}"
							>
								<span class="flex items-center gap-2">
									<input
										type="radio"
										name="cc-papel"
										value={opcao.id}
										checked={ativo}
										onchange={() => (papel = opcao.id)}
										class="sr-only"
									/>
									<span
										class="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border {ativo
											? 'border-brand'
											: 'border-border-strong'}"
										aria-hidden="true"
									>
										{#if ativo}
											<span class="h-2 w-2 rounded-full bg-brand"></span>
										{/if}
									</span>
									<span class="text-sm font-semibold text-text-primary">{opcao.label}</span>
								</span>
								<span class="text-xs text-text-muted">{opcao.hint}</span>
							</label>
						{/each}
					</div>
				</fieldset>

				<div class="flex items-center gap-3">
					<Button type="submit" size="sm" disabled={!podeCompartilhar}>
						{enviando ? 'Compartilhando…' : 'Compartilhar'}
					</Button>
					{#if formError}
						<p role="alert" class="min-w-0 flex-1 text-xs text-danger">{formError}</p>
					{:else if resumoAcao}
						<p role="status" aria-live="polite" class="min-w-0 flex-1 text-xs text-text-secondary">
							{resumoAcao}
						</p>
					{/if}
				</div>
			</form>

			<section class="flex min-h-0 flex-col gap-2 border-t border-border-hairline pt-3">
				<h3 class={labelCls}>Com acesso</h3>
				<div class="thin-scroll min-h-0 max-h-[240px] overflow-y-auto">
					{#if loadState === 'loading'}
						<p role="status" aria-live="polite" class="py-4 text-sm text-text-secondary">
							Carregando compartilhamentos…
						</p>
					{:else if loadState === 'error'}
						<p role="alert" class="py-4 text-sm text-danger">{loadError}</p>
					{:else if shares.length === 0}
						<p class="py-4 text-sm text-text-muted">
							Ninguém além de você tem acesso a esta coleção.
						</p>
					{:else}
						<ul class="flex flex-col">
							{#each shares as share (share.id)}
								{@render linhaShare(share)}
							{/each}
						</ul>
					{/if}
				</div>
			</section>

			<footer class="flex justify-end border-t border-border-hairline pt-4">
				<Button variant="secondary" onclick={requestClose}>Concluir</Button>
			</footer>
		{/if}
	</div>
</Modal>

<!-- Segmento do alvo: pessoa | área, colado à borda do campo. -->
{#snippet modoBotao(alvo: AlvoModo, rotulo: string)}
	<button
		type="button"
		aria-pressed={modo === alvo}
		onclick={() => trocarModo(alvo)}
		class="grid w-[76px] place-items-center text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {modo ===
		alvo
			? 'bg-brand font-semibold text-on-brand'
			: 'font-medium text-text-muted hover:text-text-primary'}"
	>
		{rotulo}
	</button>
{/snippet}

{#snippet limparBotao(rotulo: string, acao: () => void)}
	<button
		type="button"
		onclick={acao}
		aria-label={rotulo}
		class="grid h-6 w-6 shrink-0 place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<svg
			viewBox="0 0 20 20"
			class="h-3 w-3"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			aria-hidden="true"
		>
			<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
		</svg>
	</button>
{/snippet}

<!-- Linha de concessão: pessoa (iniciais) ou área (sigla), papel editável e revogação. -->
{#snippet linhaShare(share: ColecaoShare)}
	<li
		class="flex items-center gap-3 border-b border-border-hairline py-2 last:border-b-0 {linhaOcupada ===
		share.id
			? 'opacity-60'
			: ''}"
	>
		<span
			class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-wash-neutral text-2xs font-bold text-brand"
			aria-hidden="true"
		>
			{share.user ? iniciais(share.user.nome) : (share.orgao?.sigla ?? '').slice(0, 3)}
		</span>

		<div class="flex min-w-0 flex-1 flex-col">
			<span class="truncate text-sm font-medium text-text-primary">{nomeDoShare(share)}</span>
			<span class="truncate text-xs text-text-muted">{metaDoShare(share)}</span>
		</div>

		<div class="shrink-0">
			<SelectMenu
				options={PAPEL_MENU}
				value={share.papel}
				onSelect={(v) => trocarPapel(share, v)}
				disabled={linhaOcupada === share.id}
				unstyled
				hideCheck
				align="right"
				ariaLabel={`Papel de ${nomeDoShare(share)}`}
			>
				{#snippet trigger({ open, label })}
					<span
						class="flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-semibold text-text-primary transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted"
					>
						{label}
						<svg
							viewBox="0 0 20 20"
							class="h-2.5 w-2.5 text-text-muted transition-transform duration-fast"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							style:transform={open ? 'rotate(180deg)' : 'none'}
							aria-hidden="true"
						>
							<path d="m4 7 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
					</span>
				{/snippet}
			</SelectMenu>
		</div>

		<button
			type="button"
			onclick={() => void revogar(share)}
			disabled={linhaOcupada === share.id}
			aria-label={`Revogar o acesso de ${nomeDoShare(share)}`}
			class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-wash-danger hover:text-danger disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
		>
			<AppIcon id="exclusao" />
		</button>
	</li>
{/snippet}
