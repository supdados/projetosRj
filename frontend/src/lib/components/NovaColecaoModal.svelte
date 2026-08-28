<script lang="ts">
	/**
	 * Modal "Nova coleção" em TELA ÚNICA, duas colunas: identidade à esquerda
	 * (nome, descrição, ícone, cor, "Quem enxerga") e ColecaoProjectPicker à
	 * direita, com contador "N de M · Limpar". A criação é ATÔMICA: "Criar
	 * coleção" faz um único POST /api/colecoes com `project_ids` e
	 * `compartilhamentos`. Chrome (backdrop/Esc/focus-trap) é o Modal base.
	 *
	 * "Quem enxerga": a coleção NASCE PESSOAL — o toggle "Só eu" começa
	 * LIGADO e só quem o desliga escolhe destinatários (pessoa ou órgão exato).
	 * Versão compacta do formulário de `CompartilharColecaoModal.svelte`, que é
	 * quem gerencia as concessões depois de a coleção existir (só o dono).
	 * Favoritos nunca passa por aqui — este modal só cria coleções `custom`.
	 *
	 * Pode abrir PRÉ-PREENCHIDO (`nomeInicial`/`descricaoInicial`/
	 * `projectIdsIniciais`) no aceite de uma sugestão de IA — daí em diante o
	 * fluxo é o mesmo de sempre, com o usuário revisando ícone, cor e quem
	 * enxerga antes de confirmar. Nesse caso `sugestaoId` viaja no POST para o
	 * backend marcar a sugestão como aceita.
	 */
	import { tick } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import { criarColecao } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { fetchAreas, type AreaOption } from '$lib/api/areas';
	import { searchInvitableUsers } from '$lib/api/projectMembers';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import { buildOrgaoTree, flattenTreeWithPath, type OrgaoTreeRow } from '$lib/utils/orgaoTree';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { UsuarioConvidavel } from '$lib/types/projectMembers';
	import type {
		ColecaoResumo,
		ColecaoShareCreatePayload,
		CollectionColorId,
		CollectionIconId,
		PapelCompartilhamento
	} from '$lib/types/collections';

	interface Props {
		/** Modal aberto? (controlado pela página). */
		open: boolean;
		/** Fecha o modal sem criar (✕, Esc, backdrop, Cancelar). */
		onClose: () => void;
		/** Coleção criada com sucesso; o modal fecha sozinho em seguida. */
		onCreated: (colecao: ColecaoResumo) => void;
		/** Nome inicial (aceite de sugestão de IA); ausente = campo em branco. */
		nomeInicial?: string;
		/** Descrição inicial (aceite de sugestão de IA). */
		descricaoInicial?: string;
		/** Projetos já marcados no passo 2 (aceite de sugestão de IA). */
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

	const DESCRICAO_MAX = 200;

	const ICONE_OPTIONS: { id: CollectionIconId; label: string }[] = [
		{ id: 'camadas', label: 'Camadas' },
		{ id: 'servidores', label: 'Servidores' },
		{ id: 'pessoas', label: 'Pessoas' },
		{ id: 'documento', label: 'Documento' },
		{ id: 'estrela', label: 'Estrela' },
		{ id: 'rede', label: 'Rede' },
		{ id: 'capacitacao', label: 'Capacitação' },
		{ id: 'calendario', label: 'Calendário' }
	];

	// Mapas ESTÁTICOS por família: classe montada em runtime não compila.
	const COR_OPTIONS: {
		id: CollectionColorId;
		label: string;
		wash: string;
		dot: string;
		ativo: string;
	}[] = [
		{ id: 'primary', label: 'Azul', wash: 'bg-wash-brand', dot: 'bg-primary-600', ativo: 'border-primary-600' },
		{ id: 'success', label: 'Verde', wash: 'bg-wash-success', dot: 'bg-success-600', ativo: 'border-success-600' },
		{ id: 'warning', label: 'Âmbar', wash: 'bg-wash-warning', dot: 'bg-warning-600', ativo: 'border-warning-600' },
		{ id: 'attention', label: 'Laranja', wash: 'bg-wash-attention', dot: 'bg-attention-600', ativo: 'border-attention-600' },
		{ id: 'danger', label: 'Vermelho', wash: 'bg-wash-danger', dot: 'bg-danger-600', ativo: 'border-danger-600' },
		{ id: 'neutral', label: 'Cinza', wash: 'bg-wash-neutral', dot: 'bg-neutral-600', ativo: 'border-neutral-600' }
	];

	const ICONE_ATIVO_CLASS: Record<CollectionColorId, string> = {
		primary: 'border-primary-600 bg-wash-brand text-brand',
		success: 'border-success-600 bg-wash-success text-success',
		warning: 'border-warning-600 bg-wash-warning text-warning',
		attention: 'border-attention-600 bg-wash-attention text-attention',
		danger: 'border-danger-600 bg-wash-danger text-danger',
		neutral: 'border-neutral-600 bg-wash-neutral text-text-secondary'
	};

	let nome = $state('');
	let descricao = $state('');
	let icone = $state<CollectionIconId>('camadas');
	let cor = $state<CollectionColorId>('primary');
	let selecionados = $state<number[]>([]);
	let totalProjetos = $state<number | null>(null);
	let triedSubmit = $state(false);
	let submitting = $state(false);
	let erro = $state<string | null>(null);

	let nomeInputEl = $state<HTMLInputElement | null>(null);

	const nomeInvalido = $derived(triedSubmit && !nome.trim());

	// ── "Quem enxerga" ───────────────────────────────────────────────────────
	/** Alvo da concessão: uma pessoa (busca) ou um órgão EXATO (sem subárvore). */
	type AlvoModo = 'pessoa' | 'area';
	/** `AreaOption` no formato que `buildOrgaoTree` espera (`value` + `pai_id`). */
	type OrgaoCandidato = AreaOption & { value: number };

	/** Destinatário já escolhido; vira um item de `compartilhamentos` no POST. */
	interface Destinatario {
		/** "u:12"/"o:3" — chave do `{#each}` e trava de duplicata. */
		chave: string;
		nome: string;
		detalhe: string;
		user_id: number | null;
		orgao_id: number | null;
		papel: PapelCompartilhamento;
	}

	const PAPEL_MENU: SelectMenuOption[] = [
		{ value: 'viewer', label: 'Leitor' },
		{ value: 'editor', label: 'Editor' }
	];
	const PAPEL_HINT: Record<PapelCompartilhamento, string> = {
		viewer: 'Vê a coleção e seus projetos',
		editor: 'Também adiciona e remove projetos'
	};

	let soEu = $state(true);
	let destinatarios = $state<Destinatario[]>([]);
	let alvoModo = $state<AlvoModo>('pessoa');
	let alvoPapel = $state<PapelCompartilhamento>('viewer');

	let termoPessoa = $state('');
	let pessoas = $state<UsuarioConvidavel[]>([]);
	let pessoaListaAberta = $state(false);
	let pessoa = $state<UsuarioConvidavel | null>(null);

	let orgaos = $state<AreaOption[]>([]);
	let termoOrgao = $state('');
	let orgaoListaAberta = $state(false);
	let orgao = $state<AreaOption | null>(null);

	let compartilharErro = $state('');
	let alvoBoxEl = $state<HTMLDivElement | null>(null);

	const orgaoCandidatos = $derived<OrgaoCandidato[]>(orgaos.map((a) => ({ ...a, value: a.id })));
	const linhasOrgao = $derived.by<OrgaoTreeRow<OrgaoCandidato>[]>(() =>
		flattenTreeWithPath(buildOrgaoTree(orgaoCandidatos), termoOrgao, { omitRootAncestor: true })
	);
	const alvoEscolhido = $derived(alvoModo === 'pessoa' ? pessoa !== null : orgao !== null);

	// Autocomplete de pessoas: 250ms de folga e aborto da busca anterior a cada tecla.
	$effect(() => {
		const q = termoPessoa.trim();
		if (soEu || alvoModo !== 'pessoa' || q.length < 2 || pessoa !== null) {
			pessoas = [];
			return;
		}
		const controller = new AbortController();
		const timer = setTimeout(() => {
			searchInvitableUsers(q, controller.signal)
				.then((achados) => {
					pessoas = achados;
					pessoaListaAberta = true;
				})
				.catch(() => {
					if (!controller.signal.aborted) pessoas = [];
				});
		}, 250);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	// Clique fora do campo fecha os dois autocompletes (pessoas e áreas).
	$effect(() => {
		if (!pessoaListaAberta && !orgaoListaAberta) return;
		const fecharSeFora = (event: PointerEvent): void => {
			if (alvoBoxEl?.contains(event.target as Node)) return;
			pessoaListaAberta = false;
			orgaoListaAberta = false;
		};
		window.addEventListener('pointerdown', fecharSeFora, true);
		return () => window.removeEventListener('pointerdown', fecharSeFora, true);
	});

	function alternarSoEu(): void {
		soEu = !soEu;
		compartilharErro = '';
		if (soEu) return;
		void carregarOrgaos();
	}

	/** Catálogo completo de órgãos, uma vez por abertura do modal (busca client-side). */
	async function carregarOrgaos(): Promise<void> {
		if (orgaos.length > 0) return;
		try {
			orgaos = (await fetchAreas()).areas;
		} catch {
			compartilharErro = 'Não foi possível carregar as áreas.';
		}
	}

	function trocarAlvoModo(alvo: AlvoModo): void {
		if (alvoModo === alvo) return;
		alvoModo = alvo;
		compartilharErro = '';
		pessoaListaAberta = false;
		orgaoListaAberta = false;
	}

	function escolherPessoa(usuario: UsuarioConvidavel): void {
		pessoa = usuario;
		termoPessoa = usuario.name;
		pessoas = [];
		pessoaListaAberta = false;
	}

	function escolherOrgao(opcao: AreaOption): void {
		orgao = opcao;
		termoOrgao = opcao.sigla || opcao.nome;
		orgaoListaAberta = false;
	}

	function limparAlvo(): void {
		pessoa = null;
		termoPessoa = '';
		pessoas = [];
		orgao = null;
		termoOrgao = '';
	}

	/** Destinatário atual como linha da lista (XOR pessoa/órgão preservado). */
	function novoDestinatario(): Destinatario | null {
		if (alvoModo === 'pessoa' && pessoa) {
			const detalhe = pessoa.orgao_sigla ? `Pessoa · ${pessoa.orgao_sigla}` : 'Pessoa';
			return { chave: `u:${pessoa.id}`, nome: pessoa.name, detalhe, user_id: pessoa.id, orgao_id: null, papel: alvoPapel };
		}
		if (alvoModo === 'area' && orgao) {
			const nome = orgao.sigla || orgao.nome;
			return { chave: `o:${orgao.id}`, nome, detalhe: orgao.nome, user_id: null, orgao_id: orgao.id, papel: alvoPapel };
		}
		return null;
	}

	function adicionarDestinatario(): void {
		const alvo = novoDestinatario();
		if (!alvo) return;
		if (destinatarios.some((d) => d.chave === alvo.chave)) {
			compartilharErro = `${alvo.nome} já está na lista.`;
			return;
		}
		destinatarios = [...destinatarios, alvo];
		compartilharErro = '';
		limparAlvo();
	}

	// Enter na busca adiciona o alvo escolhido — nunca avança o passo do formulário.
	function onAlvoEnter(event: KeyboardEvent): void {
		if (event.key !== 'Enter') return;
		event.preventDefault();
		adicionarDestinatario();
	}

	function removerDestinatario(chave: string): void {
		destinatarios = destinatarios.filter((d) => d.chave !== chave);
	}

	function trocarPapelDestinatario(chave: string, valor: string | null): void {
		const papel: PapelCompartilhamento = valor === 'editor' ? 'editor' : 'viewer';
		destinatarios = destinatarios.map((d) => (d.chave === chave ? { ...d, papel } : d));
	}

	/** Nada escolhido (ou "Só eu" ligado) = coleção pessoal: o campo nem vai no POST. */
	function compartilhamentosPayload(): ColecaoShareCreatePayload[] | undefined {
		if (soEu || destinatarios.length === 0) return undefined;
		return destinatarios.map((d) =>
			d.user_id !== null
				? { user_id: d.user_id, papel: d.papel }
				: { orgao_id: d.orgao_id ?? 0, papel: d.papel }
		);
	}

	let prevOpen = false;
	$effect(() => {
		if (open && !prevOpen) {
			resetar();
			focusAfterTick(() => nomeInputEl);
		}
		prevOpen = open;
	});

	function resetar(): void {
		nome = nomeInicial ?? '';
		descricao = descricaoInicial ?? '';
		icone = 'camadas';
		cor = 'primary';
		selecionados = projectIdsIniciais ? [...projectIdsIniciais] : [];
		triedSubmit = false;
		submitting = false;
		erro = null;
		soEu = true;
		destinatarios = [];
		alvoModo = 'pessoa';
		alvoPapel = 'viewer';
		compartilharErro = '';
		limparAlvo();
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
				compartilhamentos: compartilhamentosPayload(),
				sugestao_id: sugestaoId
			});
			onCreated(colecao);
			onClose();
		} catch (err) {
			erro =
				err instanceof ApiClientError ? err.message : 'Não foi possível criar a coleção.';
		} finally {
			submitting = false;
		}
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
	const fieldCls =
		'h-[var(--control-h-md)] w-full rounded-control border bg-surface px-3.5 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:outline-none';
</script>

{#if open}
	<Modal labelId="nova-colecao-title" maxWidth="max-w-[880px]" onBackdrop={requestClose}>
		<div class="flex max-h-[85vh] flex-col gap-4">
			<div class="flex items-center gap-3">
				<h2 id="nova-colecao-title" class="font-heading text-xl font-bold text-text-primary">
					Nova coleção
				</h2>
				<button
					type="button"
					onclick={requestClose}
					disabled={submitting}
					aria-label="Fechar"
					class="ml-auto grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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

			<div class="thin-scroll min-h-0 flex-1 overflow-y-auto">
				<div class="grid gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
					<div class="flex min-w-0 flex-col gap-4">
						<div class="flex items-end gap-3">
							<ColecaoIconTile {icone} {cor} size={52} />
							<div class="flex min-w-0 flex-1 flex-col gap-1.5">
								<label for="nc-nome" class={labelCls}>Nome da coleção</label>
								<input
									id="nc-nome"
									bind:this={nomeInputEl}
									bind:value={nome}
									type="text"
									aria-invalid={nomeInvalido}
									placeholder="Ex.: Modernização Digital 2026"
									class="{fieldCls} {nomeInvalido
										? 'border-danger'
										: 'border-border-strong focus:border-brand'}"
								/>
							</div>
						</div>
						{#if nomeInvalido}
							<p class="text-xs text-danger">Informe o nome da coleção.</p>
						{/if}

						<div class="flex flex-col gap-1.5">
							<label for="nc-descricao" class={labelCls}>Descrição (opcional)</label>
							<input
								id="nc-descricao"
								bind:value={descricao}
								type="text"
								maxlength={DESCRICAO_MAX}
								placeholder="Para que serve esta coleção"
								class="{fieldCls} border-border-strong focus:border-brand"
							/>
						</div>

						<div class="flex flex-col gap-2">
							<span id="nc-icone-label" class={labelCls}>Ícone</span>
							<div role="group" aria-labelledby="nc-icone-label" class="grid grid-cols-8 gap-2">
								{#each ICONE_OPTIONS as opcao (opcao.id)}
									{@const ativo = icone === opcao.id}
									<button
										type="button"
										aria-pressed={ativo}
										aria-label={opcao.label}
										onclick={() => (icone = opcao.id)}
										class="grid aspect-square place-items-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativo
											? ICONE_ATIVO_CLASS[cor]
											: 'border-border-subtle text-text-secondary hover:bg-surface-muted'}"
									>
										<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
											{#each COLLECTION_ICONS[opcao.id] as p (p.d)}
												<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
											{/each}
										</svg>
									</button>
								{/each}
							</div>
						</div>

						<div class="flex flex-col gap-2">
							<span id="nc-cor-label" class={labelCls}>Cor</span>
							<div role="group" aria-labelledby="nc-cor-label" class="flex gap-2">
								{#each COR_OPTIONS as opcao (opcao.id)}
									{@const ativo = cor === opcao.id}
									<button
										type="button"
										aria-pressed={ativo}
										aria-label={opcao.label}
										onclick={() => (cor = opcao.id)}
										class="grid h-8 w-8 place-items-center rounded-md border-2 transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 {opcao.wash} {ativo
											? opcao.ativo
											: 'border-transparent hover:border-border-subtle'}"
									>
										<span class="h-3.5 w-3.5 rounded-full {opcao.dot}" aria-hidden="true"></span>
									</button>
								{/each}
							</div>
						</div>

						<div class="flex flex-col gap-2">
							<span class={labelCls}>Quem enxerga</span>
							<div
								class="flex items-center gap-3 rounded-control border border-border-subtle px-3 py-2.5"
							>
								<div class="flex min-w-0 flex-1 flex-col">
									<span id="nc-soeu-label" class="text-sm font-medium text-text-primary">
										Só eu
									</span>
									{#if !soEu}
										<span class="text-xs text-text-muted">Escolha abaixo quem recebe acesso.</span>
									{/if}
								</div>
								<button
									type="button"
									aria-pressed={soEu}
									aria-labelledby="nc-soeu-label"
									onclick={alternarSoEu}
									class="grid h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 {soEu
										? 'bg-brand'
										: 'bg-border-strong'}"
								>
									<span
										class="h-3.5 w-3.5 rounded-full bg-surface-elevated shadow-sm transition-transform duration-fast {soEu
											? 'translate-x-[1.125rem]'
											: 'translate-x-[0.1875rem]'}"
										aria-hidden="true"
									></span>
								</button>
							</div>

							{#if !soEu}
								<div bind:this={alvoBoxEl} class="relative flex flex-col gap-2">
									<div
										class="flex items-stretch overflow-hidden rounded-control border border-border-strong bg-surface transition-colors duration-fast focus-within:border-brand"
									>
										<div
											class="flex shrink-0 items-stretch border-r border-border-subtle bg-surface-muted"
											role="group"
											aria-label="Compartilhar com"
										>
											{@render alvoModoBotao('pessoa', 'Pessoa')}
											{@render alvoModoBotao('area', 'Área')}
										</div>
										{#if alvoModo === 'pessoa'}
											<input
												id="nc-pessoa"
												type="text"
												autocomplete="off"
												role="combobox"
												aria-expanded={pessoaListaAberta && pessoas.length > 0}
												aria-controls="nc-pessoa-lista"
												aria-autocomplete="list"
												aria-label="Buscar pessoa"
												placeholder="Nome ou usuário…"
												bind:value={termoPessoa}
												oninput={() => {
													pessoa = null;
													pessoaListaAberta = true;
												}}
												onkeydown={onAlvoEnter}
												class="min-w-0 flex-1 border-none bg-transparent px-3 py-2 text-md text-text-primary outline-none placeholder:text-text-faint"
											/>
										{:else}
											<input
												id="nc-area"
												type="text"
												autocomplete="off"
												role="combobox"
												aria-expanded={orgaoListaAberta && linhasOrgao.length > 0}
												aria-controls="nc-area-lista"
												aria-autocomplete="list"
												aria-label="Buscar área"
												placeholder="Sigla ou nome da área…"
												bind:value={termoOrgao}
												oninput={() => {
													orgao = null;
													orgaoListaAberta = true;
												}}
												onclick={() => (orgaoListaAberta = true)}
												onkeydown={onAlvoEnter}
												class="min-w-0 flex-1 border-none bg-transparent px-3 py-2 text-md text-text-primary outline-none placeholder:text-text-faint"
											/>
										{/if}
									</div>

									{#if alvoModo === 'pessoa' && pessoaListaAberta && pessoas.length > 0}
										<ul
											id="nc-pessoa-lista"
											role="listbox"
											aria-label="Pessoas encontradas"
											class="absolute left-0 right-0 top-[calc(var(--control-h-md)+0.25rem)] z-10 max-h-48 overflow-y-auto rounded-control border border-border-subtle bg-surface-elevated py-1 shadow-lg"
										>
											{#each pessoas as usuario (usuario.id)}
												<li role="none">
													<button
														type="button"
														role="option"
														aria-selected={pessoa?.id === usuario.id}
														onclick={() => escolherPessoa(usuario)}
														class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm text-text-primary hover:bg-surface-muted"
													>
														<span class="min-w-0 truncate">
															{usuario.name}
															<span class="text-text-muted">@{usuario.username}</span>
														</span>
														{#if usuario.orgao_sigla}
															<span class="shrink-0 text-xs text-text-secondary">
																{usuario.orgao_sigla}
															</span>
														{/if}
													</button>
												</li>
											{/each}
										</ul>
									{/if}

									{#if alvoModo === 'area' && orgaoListaAberta && linhasOrgao.length > 0}
										<ul
											id="nc-area-lista"
											role="listbox"
											aria-label="Áreas encontradas"
											class="absolute left-0 right-0 top-[calc(var(--control-h-md)+0.25rem)] z-10 max-h-48 overflow-y-auto rounded-control border border-border-subtle bg-surface-elevated py-1 shadow-lg"
										>
											{#each linhasOrgao as linha (linha.value)}
												<li role="none">
													<button
														type="button"
														role="option"
														aria-selected={orgao?.id === linha.value}
														onclick={() => escolherOrgao(linha.option)}
														class="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-muted"
													>
														<span class="shrink-0 truncate">
															{#if linha.path}<span class="mr-1 text-xs text-text-muted"
																	>{linha.path} ›</span
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

									<div class="flex items-center gap-2">
										<SelectMenu
											options={PAPEL_MENU}
											value={alvoPapel}
											onSelect={(v) => (alvoPapel = v === 'editor' ? 'editor' : 'viewer')}
											size="sm"
											ariaLabel="Papel do compartilhamento"
										/>
										<span class="min-w-0 flex-1 truncate text-xs text-text-muted">
											{PAPEL_HINT[alvoPapel]}
										</span>
										<Button
											variant="secondary"
											size="sm"
											onclick={adicionarDestinatario}
											disabled={!alvoEscolhido}
										>
											Adicionar
										</Button>
									</div>

									{#if compartilharErro}
										<p role="alert" class="text-xs text-danger">{compartilharErro}</p>
									{/if}
								</div>

								{#if destinatarios.length > 0}
									<ul class="flex flex-col rounded-control border border-border-subtle">
										{#each destinatarios as alvo (alvo.chave)}
											<li
												class="flex items-center gap-2 border-b border-border-hairline px-3 py-2 last:border-b-0"
											>
												<div class="flex min-w-0 flex-1 flex-col">
													<span class="truncate text-sm font-medium text-text-primary">
														{alvo.nome}
													</span>
													<span class="truncate text-xs text-text-muted">{alvo.detalhe}</span>
												</div>
												<SelectMenu
													options={PAPEL_MENU}
													value={alvo.papel}
													onSelect={(v) => trocarPapelDestinatario(alvo.chave, v)}
													size="sm"
													align="right"
													ariaLabel={`Papel de ${alvo.nome}`}
												/>
												<button
													type="button"
													onclick={() => removerDestinatario(alvo.chave)}
													aria-label={`Remover ${alvo.nome}`}
													class="grid h-7 w-7 shrink-0 place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-wash-danger hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
											</li>
										{/each}
									</ul>
								{/if}
							{/if}
						</div>
					</div>

					<!-- md+: conteúdo fora do fluxo para a lista não inflar a linha do grid — a altura vem só da coluna esquerda e as bases alinham. -->
					<div class="relative min-w-0 md:border-l md:border-border-subtle">
						<div class="flex min-w-0 flex-col gap-1.5 md:absolute md:inset-0 md:pl-6">
							<div class="flex items-baseline justify-between gap-3">
								<span class={labelCls}>Projetos da sua área</span>
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
								preencher
								onchange={(ids) => (selecionados = ids)}
								ontotal={(total) => (totalProjetos = total)}
							/>
						</div>
					</div>
				</div>
			</div>

			{#if erro}
				<StateBanner tone="danger" title={erro} />
			{/if}

			<footer class="flex items-center justify-end gap-3 border-t border-border-hairline pt-4">
				<Button variant="secondary" onclick={requestClose} disabled={submitting}>Cancelar</Button>
				<Button onclick={() => void criar()} disabled={submitting}>
					{submitting
						? 'Criando…'
						: selecionados.length > 0
							? `Criar coleção · ${selecionados.length}`
							: 'Criar coleção'}
				</Button>
			</footer>
		</div>
	</Modal>
{/if}

<!-- Segmento do alvo do compartilhamento: pessoa | área, colado à borda do campo. -->
{#snippet alvoModoBotao(alvo: AlvoModo, rotulo: string)}
	<button
		type="button"
		aria-pressed={alvoModo === alvo}
		onclick={() => trocarAlvoModo(alvo)}
		class="grid w-[72px] place-items-center text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {alvoModo ===
		alvo
			? 'bg-brand font-semibold text-on-brand'
			: 'font-medium text-text-muted hover:text-text-primary'}"
	>
		{rotulo}
	</button>
{/snippet}
