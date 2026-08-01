<script lang="ts">
	/**
	 * Modal "Compartilhar" do Detalhe de Projeto (S4/F3-19, layout em 2 telas).
	 *
	 * Convida um usuário JÁ existente e ativo para o projeto (sem token, sem
	 * aceite — §7). Convidar e gerenciar são tarefas de tempos diferentes, então
	 * moram em telas distintas do MESMO painel: a tela 1 é a barra de convite
	 * compacta (modo + busca + ação, com papel/período em seletores inline) e um
	 * rodapé-resumo clicável; a tela 2 ("Gerenciar acesso") traz busca e a lista
	 * de concessões diretas, com os revogados recolhidos no fim da lista.
	 *
	 * O modo ÁREA convida em LOTE (POST .../membros/lote): snapshot de HOJE dos
	 * vínculos diretos do órgão, sem subárvore e sem dinamismo — cada pessoa vira
	 * uma linha comum na tela 2, então nada muda daqui para baixo.
	 *
	 * O componente consome `routes/api/project_members.py` diretamente (como o
	 * ProjectHistoryDrawer) e RE-BUSCA a lista após cada mutação. Quem pode
	 * abri-lo é decidido pelo servidor (`permissions.can_manage_members`); aqui
	 * nada de permissão é recalculado.
	 */
	import { onMount, tick } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { ApiClientError } from '$lib/api/client';
	import { fetchAreas, type AreaOption } from '$lib/api/areas';
	import {
		bulkInviteOrgao,
		createProjectMember,
		fetchProjectMembers,
		revokeProjectMember,
		searchInvitableUsers,
		updateProjectMember
	} from '$lib/api/projectMembers';
	import { focusTrap } from '$lib/actions/focusTrap';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type {
		ConvitePapel,
		ProjectMemberDireto,
		ProjectMemberHerdado,
		UsuarioConvidavel
	} from '$lib/types/projectMembers';
	import {
		CONVITE_PAPEL_OPTIONS,
		CONVITE_PAPEL_PADRAO,
		CONVITE_PERIODO_OPTIONS,
		CONVITE_PERIODO_PADRAO_DIAS,
		contarAreasHerdadas,
		conviteErrorMessage,
		conviteLoteResumo,
		convitePapelLabel,
		convitePeriodoDias,
		convitePeriodoValue,
		expiracaoDoPeriodo,
		filtrarConcessoes,
		normalizeConvitePapel
	} from '$lib/utils/projectMembers';
	import { buildOrgaoTree, flattenTreeWithPath, type OrgaoTreeRow } from '$lib/utils/orgaoTree';

	interface Props {
		projectId: number;
		projectTitulo: string;
		onClose: () => void;
	}

	let { projectId, projectTitulo, onClose }: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';

	/** Alvo do convite: uma pessoa (busca) ou um órgão inteiro (lote). */
	type ConviteModo = 'pessoa' | 'area';

	/** Telas do painel: convidar (default) e gerenciar as concessões. */
	type Tela = 'convite' | 'gerenciar';

	/** `AreaOption` no formato que `buildOrgaoTree` espera (`value` + `pai_id`). */
	type OrgaoCandidato = AreaOption & { value: number };

	let loadState = $state<LoadState>('loading');
	let diretos = $state<ProjectMemberDireto[]>([]);
	let herdados = $state<ProjectMemberHerdado[]>([]);
	let loadError = $state<string>('');

	let tela = $state<Tela>('convite');

	// Formulário de convite
	let modo = $state<ConviteModo>('area');
	let termo = $state<string>('');
	let resultados = $state<UsuarioConvidavel[]>([]);
	let buscando = $state<boolean>(false);
	let listaAberta = $state<boolean>(false);
	let destaque = $state<number>(-1);
	let selecionado = $state<UsuarioConvidavel | null>(null);
	let papel = $state<ConvitePapel>(CONVITE_PAPEL_PADRAO);
	// Período (em dias, null = indeterminado); a data ISO só nasce no envio.
	let periodoDias = $state<number | null>(CONVITE_PERIODO_PADRAO_DIAS);
	let enviando = $state<boolean>(false);
	let formError = $state<string>('');

	// Tela 2: busca livre (client-side); revogados ficam recolhidos no fim da lista.
	let filtroTermo = $state<string>('');
	let revogadosAbertos = $state<boolean>(false);

	// Modo Área: catálogo de órgãos (GET /api/areas, busca client-side).
	let orgaos = $state<AreaOption[]>([]);
	let orgaosCarregando = $state<boolean>(false);
	let termoOrgao = $state<string>('');
	let orgaoSelecionado = $state<AreaOption | null>(null);
	let listaOrgaoAberta = $state<boolean>(false);
	let destaqueOrgao = $state<number>(-1);
	/** Recibo da última ação de convite — ocupa o lugar do `formError` quando dá certo. */
	let resumoAcao = $state<string>('');
	let campoConvite = $state<HTMLDivElement | null>(null);

	/** Id da linha em mutação — desabilita só aquela linha. */
	let linhaOcupada = $state<number | null>(null);

	const papelOptions: SelectMenuOption[] = CONVITE_PAPEL_OPTIONS.map((o) => ({
		value: o.value,
		label: o.label
	}));
	const periodoOptions: SelectMenuOption[] = CONVITE_PERIODO_OPTIONS.map((o) => ({
		value: o.value,
		label: o.label
	}));
	const alvoEscolhido = $derived(modo === 'pessoa' ? selecionado !== null : orgaoSelecionado !== null);
	const podeConvidar = $derived(alvoEscolhido && !enviando);

	/** Data em que o convite vai expirar com o período escolhido (null = nunca). */
	const expiracaoPrevista = $derived(expiracaoDoPeriodo(periodoDias));

	const orgaoCandidatos = $derived<OrgaoCandidato[]>(orgaos.map((a) => ({ ...a, value: a.id })));

	// Lista achatada com o caminho hierárquico (mesma leitura do AreaResponsavelPicker).
	const linhasOrgao = $derived.by<OrgaoTreeRow<OrgaoCandidato>[]>(() =>
		flattenTreeWithPath(buildOrgaoTree(orgaoCandidatos), termoOrgao, { omitRootAncestor: true })
	);

	// Expirado não abre porta: o resumo conta só quem entra hoje.
	const diretosComAcesso = $derived(diretos.filter((m) => m.status === 'ativo'));
	const pessoasComAcesso = $derived(diretosComAcesso.length);
	const areasHerdadas = $derived(contarAreasHerdadas(herdados));
	const concessoesVisiveis = $derived(filtrarConcessoes(diretos, filtroTermo, 'ativos'));
	const revogadosVisiveis = $derived(filtrarConcessoes(diretos, filtroTermo, 'revogados'));
	const sufixoAreas = $derived(
		areasHerdadas > 0 ? ` e ${contagem(areasHerdadas, 'área', 'áreas')} com acesso` : ' com acesso'
	);
	const subtituloGerenciar = $derived.by<string>(() => {
		if (loadState !== 'ready' || diretos.length === 0) return projectTitulo;
		return `${contagem(diretos.length, 'concessão', 'concessões')} · ${projectTitulo}`;
	});

	/** Traduz qualquer falha da API para PT-BR (404/403 do §6.3). */
	function mensagemDeErro(err: unknown, fallback: string): string {
		if (err instanceof ApiClientError) return conviteErrorMessage(err.status, err.code);
		return err instanceof Error ? err.message : fallback;
	}

	async function carregar(): Promise<void> {
		loadState = 'loading';
		loadError = '';
		try {
			const data = await fetchProjectMembers(projectId);
			diretos = data.diretos;
			herdados = data.herdados;
			loadState = 'ready';
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			loadError = mensagemDeErro(err, 'Falha ao carregar os membros do projeto.');
			loadState = 'error';
		}
	}

	async function recarregar(): Promise<void> {
		try {
			const data = await fetchProjectMembers(projectId);
			diretos = data.diretos;
			herdados = data.herdados;
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = mensagemDeErro(err, 'Falha ao recarregar os membros.');
		}
	}

	onMount(() => {
		void carregar();
		void focarCampoDoModo();
	});

	// Autocomplete: 250ms de folga e aborto da busca anterior a cada tecla.
	$effect(() => {
		const q = termo.trim();
		if (modo !== 'pessoa' || q.length < 2 || selecionado !== null) {
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
					formError = mensagemDeErro(err, 'Falha ao buscar usuários.');
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

	function escolher(usuario: UsuarioConvidavel): void {
		selecionado = usuario;
		termo = usuario.name;
		resultados = [];
		listaAberta = false;
		formError = '';
	}

	function limparSelecao(): void {
		selecionado = null;
		termo = '';
		resultados = [];
		listaAberta = false;
	}

	function onBuscaKeydown(event: KeyboardEvent): void {
		if (!listaAberta || resultados.length === 0) return;
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			destaque = (destaque + 1) % resultados.length;
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			destaque = (destaque - 1 + resultados.length) % resultados.length;
		} else if (event.key === 'Enter' && destaque >= 0) {
			event.preventDefault();
			escolher(resultados[destaque]);
		} else if (event.key === 'Escape') {
			event.stopPropagation();
			listaAberta = false;
		}
	}

	function trocarModo(alvo: ConviteModo): void {
		if (modo === alvo) return;
		modo = alvo;
		formError = '';
		resumoAcao = '';
		listaAberta = false;
		listaOrgaoAberta = false;
		void focarCampoDoModo();
	}

	async function focarCampoDoModo(): Promise<void> {
		if (modo === 'area') await carregarOrgaos();
		await tick();
		const campo = modo === 'area' ? 'compartilhar-orgao' : 'compartilhar-busca';
		document.getElementById(campo)?.focus();
	}

	/** Tela 2 abre com o cursor no filtro; a volta devolve o foco ao convite. */
	async function abrirGerenciar(): Promise<void> {
		tela = 'gerenciar';
		await tick();
		document.getElementById('compartilhar-filtro')?.focus();
	}

	function voltarParaConvite(): void {
		tela = 'convite';
		void focarCampoDoModo();
	}

	/** Catálogo completo de órgãos, uma vez por abertura do modal. */
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

	function escolherOrgao(orgao: AreaOption): void {
		orgaoSelecionado = orgao;
		termoOrgao = orgao.sigla || orgao.nome;
		listaOrgaoAberta = false;
		formError = '';
	}

	function limparOrgao(): void {
		orgaoSelecionado = null;
		termoOrgao = '';
		listaOrgaoAberta = false;
		destaqueOrgao = -1;
	}

	// Clique fora do campo fecha os dois autocompletes (pessoas e órgãos).
	$effect(() => {
		if (!listaOrgaoAberta && !listaAberta) return;
		const fecharSeFora = (event: PointerEvent): void => {
			if (campoConvite?.contains(event.target as Node)) return;
			listaOrgaoAberta = false;
			listaAberta = false;
		};
		window.addEventListener('pointerdown', fecharSeFora, true);
		return () => window.removeEventListener('pointerdown', fecharSeFora, true);
	});

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

	function convidar(): void {
		if (modo === 'area') void convidarArea();
		else void convidarPessoa();
	}

	/** Convite em lote: sucesso vira resumo de contagens, não linha na tela. */
	async function convidarArea(): Promise<void> {
		if (!orgaoSelecionado) return;
		enviando = true;
		formError = '';
		resumoAcao = '';
		try {
			const contagens = await bulkInviteOrgao(projectId, {
				orgao_id: orgaoSelecionado.id,
				papel,
				expires_at: expiracaoDoPeriodo(periodoDias)
			});
			resumoAcao = conviteLoteResumo(contagens);
			limparOrgao();
			await recarregar();
		} catch (err) {
			formError = mensagemDeErro(err, 'Falha ao convidar a área.');
		} finally {
			enviando = false;
		}
	}

	async function convidarPessoa(): Promise<void> {
		if (!selecionado) return;
		enviando = true;
		formError = '';
		resumoAcao = '';
		try {
			const nome = selecionado.name;
			await createProjectMember(projectId, {
				user_id: selecionado.id,
				papel,
				expires_at: expiracaoDoPeriodo(periodoDias)
			});
			limparSelecao();
			resumoAcao = `${nome} agora tem acesso como ${convitePapelLabel(papel)}.`;
			await recarregar();
		} catch (err) {
			formError = mensagemDeErro(err, 'Falha ao criar o convite.');
		} finally {
			enviando = false;
		}
	}

	/** Roda uma mutação de linha marcando-a como ocupada e re-buscando a lista. */
	async function mutarLinha(id: number, acao: () => Promise<void>, fallback: string): Promise<void> {
		linhaOcupada = id;
		formError = '';
		resumoAcao = '';
		try {
			await acao();
			await recarregar();
		} catch (err) {
			formError = mensagemDeErro(err, fallback);
		} finally {
			linhaOcupada = null;
		}
	}

	function trocarPapel(membro: ProjectMemberDireto, novo: string | null): void {
		const alvo = normalizeConvitePapel(novo);
		if (alvo === membro.papel) return;
		void mutarLinha(
			membro.id,
			() => updateProjectMember(projectId, membro.id, { papel: alvo }),
			'Falha ao alterar o papel.'
		);
	}

	function renovar(membro: ProjectMemberDireto): void {
		void mutarLinha(
			membro.id,
			() =>
				updateProjectMember(projectId, membro.id, {
					expires_at: expiracaoDoPeriodo(CONVITE_PERIODO_PADRAO_DIAS)
				}),
			'Falha ao renovar o convite.'
		);
	}

	// Reativação reusa a MESMA linha no backend (unique constraint): é um POST.
	function reativar(membro: ProjectMemberDireto): void {
		void mutarLinha(
			membro.id,
			() =>
				createProjectMember(projectId, {
					user_id: membro.user_id,
					papel: membro.papel,
					expires_at: expiracaoDoPeriodo(CONVITE_PERIODO_PADRAO_DIAS)
				}),
			'Falha ao reativar o convite.'
		);
	}

	function revogar(membro: ProjectMemberDireto): void {
		void mutarLinha(
			membro.id,
			() => revokeProjectMember(projectId, membro.id),
			'Falha ao revogar o convite.'
		);
	}

	function acaoOptions(membro: ProjectMemberDireto): SelectMenuOption[] {
		if (membro.status === 'revogado') return [{ value: 'reativar', label: 'Reativar convite' }];
		if (membro.status === 'expirado') {
			return [
				{ value: 'renovar', label: `Renovar por ${CONVITE_PERIODO_PADRAO_DIAS} dias` },
				{ value: 'revogar', label: 'Revogar acesso' }
			];
		}
		return [{ value: 'revogar', label: 'Revogar acesso' }];
	}

	function executarAcao(membro: ProjectMemberDireto, acao: string | null): void {
		if (acao === 'revogar') revogar(membro);
		else if (acao === 'renovar') renovar(membro);
		else if (acao === 'reativar') reativar(membro);
	}

	function iniciais(nome: string): string {
		const partes = nome.trim().split(/\s+/).filter(Boolean);
		if (partes.length === 0) return '?';
		const primeira = partes[0][0] ?? '';
		const segunda = partes.length > 1 ? (partes[partes.length - 1][0] ?? '') : (partes[0][1] ?? '');
		return (primeira + segunda).toUpperCase();
	}

	function formatarData(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
	}

	function textoExpiracao(membro: ProjectMemberDireto): string {
		if (membro.status === 'revogado') return 'Revogado';
		if (!membro.expires_at) return 'Sem expiração';
		if (membro.status === 'expirado') return `Expirou em ${formatarData(membro.expires_at)}`;
		return `Até ${formatarData(membro.expires_at)}`;
	}

	function corExpiracao(membro: ProjectMemberDireto): string {
		if (membro.status === 'revogado') return 'bg-danger';
		if (membro.status === 'expirado') return 'bg-warning';
		return 'bg-success';
	}

	function metaConvidado(membro: ProjectMemberDireto): string {
		const partes = [membro.user_orgao_sigla ?? 'Sem órgão'];
		if (membro.granted_by_name) partes.push(`convidado por ${membro.granted_by_name}`);
		return partes.join(' · ');
	}

	/** "1 pessoa" / "4 pessoas" — usado nos resumos das duas telas. */
	function contagem(n: number, singular: string, plural: string): string {
		return `${n} ${n === 1 ? singular : plural}`;
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			onClose();
		}
	}
</script>

<div
	class="fixed inset-0 z-modal flex items-start justify-center overflow-y-auto bg-overlay p-4 py-10"
	role="presentation"
	transition:fade={{ duration: 200, easing: cubicOut }}
	onclick={onClose}
>
	<div
		role="dialog"
		aria-modal="true"
		aria-labelledby="compartilhar-titulo"
		tabindex="-1"
		use:focusTrap
		onkeydown={onKeydown}
		onclick={(e) => e.stopPropagation()}
		transition:fly={{ y: 18, duration: 280, easing: cubicOut }}
		class="flex w-full max-w-2xl flex-col rounded-xl border border-border-subtle bg-surface shadow-modal"
	>
		{#if tela === 'convite'}
			<header class="flex items-center justify-between gap-3 px-5 py-3">
				<div class="flex min-w-0 items-baseline gap-2">
					<h2
						id="compartilhar-titulo"
						class="shrink-0 font-heading text-base font-semibold text-text-primary"
					>
						Compartilhar
					</h2>
					<span class="shrink-0 text-text-faint" aria-hidden="true">·</span>
					<p class="truncate text-sm text-text-secondary">{projectTitulo}</p>
				</div>
				{@render fecharBotao()}
			</header>

			<div class="h-px bg-border-subtle" aria-hidden="true"></div>

			<!-- Tela 1: modo + busca + ação numa moldura só; papel/período embaixo -->
			<section class="flex flex-col gap-2.5 px-5 py-3.5" aria-label="Convidar para o projeto">
				<div bind:this={campoConvite} class="relative">
					<div
						class="flex items-stretch overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm transition-colors duration-fast focus-within:border-brand"
					>
						<div
							class="flex shrink-0 items-stretch border-r border-border-subtle bg-surface-muted"
							role="group"
							aria-label="Convidar por"
						>
							{@render modoBotao('area', 'Área')}
							{@render modoBotao('pessoa', 'Usuário')}
						</div>

						{#if modo === 'pessoa'}
							<div class="flex min-h-[40px] min-w-0 flex-1 items-center gap-2.5 pl-3 pr-2">
								<i
									class="fas fa-magnifying-glass shrink-0 text-xs text-text-faint"
									aria-hidden="true"
								></i>
								<input
									id="compartilhar-busca"
									type="text"
									autocomplete="off"
									role="combobox"
									aria-expanded={listaAberta && resultados.length > 0}
									aria-controls="compartilhar-resultados"
									aria-autocomplete="list"
									aria-activedescendant={destaque >= 0 && listaAberta
										? `compartilhar-resultado-${destaque}`
										: undefined}
									placeholder="Nome ou usuário…"
									bind:value={termo}
									oninput={() => {
										selecionado = null;
										listaAberta = true;
									}}
									onkeydown={onBuscaKeydown}
									class="min-w-0 flex-1 border-none bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
								/>
								{#if selecionado}
									<button
										type="button"
										onclick={limparSelecao}
										aria-label="Limpar pessoa selecionada"
										class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									>
										<i class="fas fa-times" aria-hidden="true"></i>
									</button>
								{/if}
							</div>
						{:else}
							<div class="flex min-h-[40px] min-w-0 flex-1 items-center gap-2.5 pl-3 pr-2">
								<i
									class="fas fa-magnifying-glass shrink-0 text-xs text-text-faint"
									aria-hidden="true"
								></i>
								<input
									id="compartilhar-orgao"
									type="text"
									autocomplete="off"
									role="combobox"
									aria-expanded={listaOrgaoAberta && linhasOrgao.length > 0}
									aria-controls="compartilhar-orgaos"
									aria-autocomplete="list"
									aria-activedescendant={destaqueOrgao >= 0 && listaOrgaoAberta
										? `compartilhar-orgao-${destaqueOrgao}`
										: undefined}
									placeholder={orgaosCarregando ? 'Carregando áreas…' : 'Sigla ou nome do órgão…'}
									bind:value={termoOrgao}
									oninput={() => {
										orgaoSelecionado = null;
										listaOrgaoAberta = true;
										destaqueOrgao = 0;
									}}
									onclick={() => (listaOrgaoAberta = true)}
									onkeydown={onOrgaoKeydown}
									class="min-w-0 flex-1 border-none bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
								/>
								{#if orgaoSelecionado}
									<button
										type="button"
										onclick={limparOrgao}
										aria-label="Limpar área selecionada"
										class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									>
										<i class="fas fa-times" aria-hidden="true"></i>
									</button>
								{/if}
							</div>
						{/if}

						<button
							type="button"
							onclick={convidar}
							disabled={!podeConvidar}
							class="shrink-0 self-stretch rounded-none bg-brand px-[18px] text-sm font-semibold text-white transition-colors duration-fast hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
						>
							{enviando ? 'Convidando…' : 'Convidar'}
						</button>
					</div>

					{#if modo === 'area' && listaOrgaoAberta && linhasOrgao.length > 0}
						<ul
							id="compartilhar-orgaos"
							role="listbox"
							aria-label="Órgãos encontrados"
							class="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-lg border border-border-subtle bg-surface py-1 shadow-lg"
						>
							{#each linhasOrgao as linha, index (linha.value)}
								<li role="none">
									<button
										type="button"
										role="option"
										id="compartilhar-orgao-{index}"
										aria-selected={index === destaqueOrgao}
										onclick={() => escolherOrgao(linha.option)}
										onmouseenter={() => (destaqueOrgao = index)}
										class="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-muted {index ===
										destaqueOrgao
											? 'bg-surface-muted'
											: ''}"
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

					{#if listaAberta && resultados.length > 0}
						<ul
							id="compartilhar-resultados"
							role="listbox"
							aria-label="Usuários encontrados"
							class="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-lg border border-border-subtle bg-surface py-1 shadow-lg"
						>
							{#each resultados as usuario, index (usuario.id)}
								<li role="none">
									<button
										type="button"
										role="option"
										id="compartilhar-resultado-{index}"
										aria-selected={index === destaque}
										onclick={() => escolher(usuario)}
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
											<span class="shrink-0 text-xs text-text-secondary">
												{usuario.orgao_sigla}
											</span>
										{/if}
									</button>
								</li>
							{/each}
						</ul>
					{:else if buscando}
						<p class="absolute top-full mt-1 text-xs text-text-muted" role="status">Buscando…</p>
					{/if}
				</div>

				<!-- Papel e período viram texto editável: leem como uma frase -->
				<div class="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
					<span>como</span>
					<div class="shrink-0">
						<SelectMenu
							options={papelOptions}
							value={papel}
							onSelect={(v) => (papel = normalizeConvitePapel(v))}
							unstyled
							hideCheck
							ariaLabel="Papel do convite"
						>
							{#snippet trigger({ open, label })}
								{@render gatilhoInline(label, open, false)}
							{/snippet}
						</SelectMenu>
					</div>
					<span class="h-3.5 w-px bg-border-subtle" aria-hidden="true"></span>
					<span>por</span>
					<div class="shrink-0">
						<SelectMenu
							id="compartilhar-expira"
							options={periodoOptions}
							value={convitePeriodoValue(periodoDias)}
							onSelect={(v) => (periodoDias = convitePeriodoDias(v))}
							unstyled
							hideCheck
							ariaLabel="Período de validade do convite"
						>
							{#snippet trigger({ open, label })}
								{@render gatilhoInline(label, open, true)}
							{/snippet}
						</SelectMenu>
					</div>
					{#if expiracaoPrevista}
						<span class="text-xs tabular-nums text-text-muted"
							>· até {formatarData(expiracaoPrevista)}</span
						>
					{/if}
				</div>

				{#if formError}
					<p role="alert" class="text-sm text-danger">{formError}</p>
				{:else if resumoAcao}
					<p role="status" aria-live="polite" class="text-sm font-medium text-text-secondary">
						<i class="fas fa-check text-2xs text-success" aria-hidden="true"></i>
						{resumoAcao}
					</p>
				{/if}

				{#if loadState === 'error'}
					<p role="alert" class="text-sm text-danger">{loadError}</p>
				{/if}
			</section>

			<!-- Rodapé-resumo: único caminho para a tela de gerenciar -->
			<button
				type="button"
				onclick={abrirGerenciar}
				class="group flex w-full items-center gap-3 rounded-b-xl border-t border-border-subtle bg-surface-muted px-5 py-2.5 text-left transition-colors duration-fast hover:bg-surface-chip focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
			>
				{#if pessoasComAcesso > 0}
					<span class="flex shrink-0 items-center pl-2" aria-hidden="true">
						{#each diretosComAcesso.slice(0, 5) as membro (membro.id)}
							<span
								class="-ml-2 flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface-muted bg-wash-neutral text-[9px] font-bold text-brand transition-colors duration-fast group-hover:border-surface-chip"
							>
								{iniciais(membro.user_name)}
							</span>
						{/each}
					</span>
				{/if}

				<span class="min-w-0 flex-1 truncate text-sm text-text-secondary">
					{#if loadState === 'loading'}
						Carregando acessos…
					{:else if loadState === 'error'}
						<span class="text-danger">Não foi possível carregar os acessos</span>
					{:else if pessoasComAcesso === 0 && areasHerdadas === 0}
						Ninguém com acesso ainda
					{:else if pessoasComAcesso === 0}
						<strong class="font-semibold text-text-primary"
							>{contagem(areasHerdadas, 'área', 'áreas')}</strong
						>{' com acesso'}
					{:else}
						<strong class="font-semibold text-text-primary"
							>{contagem(pessoasComAcesso, 'pessoa', 'pessoas')}</strong
						>{sufixoAreas}
					{/if}
				</span>

				<span class="shrink-0 text-sm font-semibold text-brand">Gerenciar acesso →</span>
			</button>
		{:else}
			<header class="flex items-center justify-between gap-3 px-5 py-3">
				<div class="flex min-w-0 items-center gap-2.5">
					<button
						type="button"
						onclick={voltarParaConvite}
						aria-label="Voltar para o convite"
						class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-surface text-xs text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-arrow-left" aria-hidden="true"></i>
					</button>
					<h2
						id="compartilhar-titulo"
						class="shrink-0 font-heading text-base font-semibold text-text-primary"
					>
						Gerenciar acesso
					</h2>
					<span class="shrink-0 text-text-faint" aria-hidden="true">·</span>
					<p class="truncate text-sm text-text-secondary">{subtituloGerenciar}</p>
				</div>
				{@render fecharBotao()}
			</header>

			<div class="h-px bg-border-subtle" aria-hidden="true"></div>

			<!-- Filtros da lista (client-side; nada volta ao servidor) -->
			<div class="flex flex-wrap items-center gap-2.5 px-5 py-3">
				<div
					class="flex h-[34px] min-w-0 flex-1 items-center gap-2 rounded-lg border border-border-subtle bg-surface px-3 transition-colors duration-fast focus-within:border-brand"
				>
					<i
						class="fas fa-magnifying-glass shrink-0 text-2xs text-text-faint"
						aria-hidden="true"
					></i>
					<input
						id="compartilhar-filtro"
						type="text"
						autocomplete="off"
						placeholder="Filtrar por nome, área…"
						aria-label="Filtrar concessões"
						bind:value={filtroTermo}
						class="min-w-0 flex-1 border-none bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
					/>
					{#if filtroTermo}
						<button
							type="button"
							onclick={() => (filtroTermo = '')}
							aria-label="Limpar filtro"
							class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-2xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							<i class="fas fa-times" aria-hidden="true"></i>
						</button>
					{/if}
				</div>
			</div>

			<!-- Concessões diretas: uma linha por convite, ações por linha -->
			<div class="max-h-[300px] overflow-auto border-t border-border-subtle">
				{#if loadState === 'loading'}
					<p role="status" aria-live="polite" class="px-5 py-6 text-sm text-text-secondary">
						Carregando membros…
					</p>
				{:else if loadState === 'error'}
					<p role="alert" class="px-5 py-6 text-sm text-danger">{loadError}</p>
				{:else if diretos.length === 0}
					<p class="px-5 py-6 text-sm text-text-muted">
						Nenhuma pessoa convidada até agora. Quem você convida entra na hora e aparece aqui.
					</p>
				{:else if concessoesVisiveis.length === 0}
					<p class="px-5 py-6 text-sm text-text-muted">
						{#if filtroTermo.trim()}
							Nenhuma concessão encontrada para «{filtroTermo.trim()}».
						{:else}
							Nenhuma concessão ativa.
						{/if}
					</p>
				{:else}
					<ul class="flex flex-col">
						{#each concessoesVisiveis as membro (membro.id)}
							{@render linhaConcessao(membro)}
						{/each}
					</ul>
				{/if}

				{#if loadState === 'ready' && revogadosVisiveis.length > 0}
					<button
						type="button"
						onclick={() => (revogadosAbertos = !revogadosAbertos)}
						aria-expanded={revogadosAbertos}
						aria-controls="compartilhar-revogados"
						class="flex w-full items-center gap-2 border-t border-border-subtle bg-surface-muted px-5 py-2.5 text-left text-sm text-text-secondary transition-colors duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
					>
						<i
							class="fas fa-chevron-right text-[10px] text-text-muted transition-transform duration-fast"
							style:transform={revogadosAbertos ? 'rotate(90deg)' : 'none'}
							aria-hidden="true"
						></i>
						{contagem(revogadosVisiveis.length, 'revogado', 'revogados')}
					</button>
					{#if revogadosAbertos}
						<ul id="compartilhar-revogados" class="flex flex-col border-t border-border-subtle">
							{#each revogadosVisiveis as membro (membro.id)}
								{@render linhaConcessao(membro)}
							{/each}
						</ul>
					{/if}
				{/if}
			</div>

			{#if formError}
				<p role="alert" class="border-t border-border-subtle px-5 py-2.5 text-sm text-danger">
					{formError}
				</p>
			{/if}

		{/if}
	</div>
</div>

<!-- Fechar: o mesmo botão nas duas telas (Escape também fecha, nunca volta). -->
{#snippet fecharBotao()}
	<button
		type="button"
		onclick={onClose}
		aria-label="Fechar"
		class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-surface text-xs text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<i class="fas fa-times" aria-hidden="true"></i>
	</button>
{/snippet}

<!-- Toggle do alvo do convite: segmento chato colado à borda, sem ícone (design 43194251). -->
{#snippet modoBotao(alvo: ConviteModo, rotulo: string)}
	<button
		type="button"
		aria-pressed={modo === alvo}
		onclick={() => trocarModo(alvo)}
		class="grid w-[82px] place-items-center text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {modo ===
		alvo
			? 'bg-brand font-semibold text-white'
			: 'font-medium text-text-muted hover:text-text-primary'}"
	>
		{rotulo}
	</button>
{/snippet}

<!-- Gatilho textual de papel/período: parece palavra da frase, não campo. -->
{#snippet gatilhoInline(rotulo: string, aberto: boolean, numerico: boolean)}
	<span
		class="flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-sm font-semibold text-text-primary transition-colors duration-fast hover:bg-surface-muted {numerico
			? 'tabular-nums'
			: ''}"
	>
		{rotulo}
		<i
			class="fas fa-chevron-down text-[9px] text-text-faint transition-transform duration-fast"
			style:transform={aberto ? 'rotate(180deg)' : 'none'}
			aria-hidden="true"
		></i>
	</span>
{/snippet}

<!-- Linha de concessão direta: usada na lista principal e na seção recolhida de revogados. -->
{#snippet linhaConcessao(membro: ProjectMemberDireto)}
	<li
		class="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-2.5 transition-colors duration-fast last:border-b-0 hover:bg-surface-muted"
	>
		<span
			class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-wash-neutral text-2xs font-bold text-brand {membro.status ===
			'revogado'
				? 'opacity-60'
				: ''}"
			aria-hidden="true"
		>
			{iniciais(membro.user_name)}
		</span>

		<div class="flex min-w-0 flex-1 flex-col {membro.status === 'revogado' ? 'opacity-60' : ''}">
			<span class="truncate text-md font-medium text-text-primary">
				{membro.user_name}
				<span class="font-normal text-text-muted">@{membro.user_username}</span>
			</span>
			<span class="truncate text-xs text-text-secondary">
				{metaConvidado(membro)}
			</span>
		</div>

		<span
			class="flex shrink-0 items-center gap-1.5 text-xs font-medium tabular-nums text-text-secondary"
		>
			<span class="h-1.5 w-1.5 rounded-full {corExpiracao(membro)}" aria-hidden="true"></span>
			{textoExpiracao(membro)}
		</span>

		{#if membro.status === 'revogado'}
			<span class="shrink-0 px-2 py-1 text-sm font-semibold text-text-muted">
				{convitePapelLabel(membro.papel)}
			</span>
		{:else}
			<div class="shrink-0">
				<SelectMenu
					options={papelOptions}
					value={membro.papel}
					onSelect={(v) => trocarPapel(membro, v)}
					disabled={linhaOcupada === membro.id}
					unstyled
					hideCheck
					align="right"
					ariaLabel={`Papel de ${membro.user_name}`}
				>
					{#snippet trigger({ open, label })}
						<span
							class="flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-semibold text-text-primary transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted"
						>
							{label}
							<i
								class="fas fa-chevron-down text-[9px] text-text-muted transition-transform duration-fast"
								style:transform={open ? 'rotate(180deg)' : 'none'}
								aria-hidden="true"
							></i>
						</span>
					{/snippet}
				</SelectMenu>
			</div>
		{/if}

		<div class="shrink-0">
			<SelectMenu
				options={acaoOptions(membro)}
				value={null}
				onSelect={(v) => executarAcao(membro, v)}
				disabled={linhaOcupada === membro.id}
				unstyled
				hideCheck
				align="right"
				ariaLabel={`Ações do convite de ${membro.user_name}`}
			>
				{#snippet trigger()}
					<span
						class="flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary"
					>
						<i class="fas fa-ellipsis" aria-hidden="true"></i>
					</span>
				{/snippet}
			</SelectMenu>
		</div>
	</li>
{/snippet}
