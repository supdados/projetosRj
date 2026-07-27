<script lang="ts">
	/**
	 * Modal "Compartilhar" do Detalhe de Projeto (S4/F3-19, layout 2a "refino direto").
	 *
	 * Convida um usuário JÁ existente e ativo para o projeto (sem token, sem
	 * aceite — §7). O convite é um bloco único: modo + busca + papel + expiração
	 * + ação costurados numa moldura segmentada. Convidados ganham avatar, papel
	 * editável inline e expiração legível; o acesso HERDADO por área desce para
	 * uma linha recolhível no rodapé (read-only: herdado não é linha de
	 * `project_member` e só muda na tela de admin).
	 *
	 * O modo ÁREA convida em LOTE (POST .../membros/lote): snapshot de HOJE dos
	 * vínculos diretos do órgão, sem subárvore e sem dinamismo — cada pessoa vira
	 * uma linha comum na lista de Convidados, então nada muda daqui para baixo.
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
		conviteErrorMessage,
		conviteLoteResumo,
		convitePapelLabel,
		convitePeriodoDias,
		convitePeriodoValue,
		expiracaoDoPeriodo,
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

	/** `AreaOption` no formato que `buildOrgaoTree` espera (`value` + `pai_id`). */
	type OrgaoCandidato = AreaOption & { value: number };

	let loadState = $state<LoadState>('loading');
	let diretos = $state<ProjectMemberDireto[]>([]);
	let herdados = $state<ProjectMemberHerdado[]>([]);
	let loadError = $state<string>('');

	// Formulário de convite
	let modo = $state<ConviteModo>('pessoa');
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
	let areaAberta = $state<boolean>(false);

	// Modo Área: catálogo de órgãos (GET /api/areas, busca client-side).
	let orgaos = $state<AreaOption[]>([]);
	let orgaosCarregando = $state<boolean>(false);
	let termoOrgao = $state<string>('');
	let orgaoSelecionado = $state<AreaOption | null>(null);
	let listaOrgaoAberta = $state<boolean>(false);
	let destaqueOrgao = $state<number>(-1);
	/** Resumo do último lote — ocupa o lugar do `formError` quando dá certo. */
	let resumoLote = $state<string>('');
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

	const consequenciaPapel = $derived(
		papel === 'editor'
			? 'pode ver e editar etapas, tarefas e anexos deste projeto'
			: 'visualiza todo o conteúdo deste projeto sem alterar nada'
	);
	const sujeitoPapel = $derived(modo === 'pessoa' ? 'a pessoa' : 'cada pessoa da área');

	const orgaoCandidatos = $derived<OrgaoCandidato[]>(orgaos.map((a) => ({ ...a, value: a.id })));

	// Lista achatada com o caminho hierárquico (mesma leitura do AreaResponsavelPicker).
	const linhasOrgao = $derived.by<OrgaoTreeRow<OrgaoCandidato>[]>(() =>
		flattenTreeWithPath(buildOrgaoTree(orgaoCandidatos), termoOrgao, { omitRootAncestor: true })
	);

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
		void tick().then(() => document.getElementById('compartilhar-busca')?.focus());
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
		resumoLote = '';
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

	// A lista de órgãos abre no foco (para navegar a árvore), então precisa fechar
	// no clique fora — a de pessoas só abre digitando e fecha ao escolher.
	$effect(() => {
		if (!listaOrgaoAberta) return;
		const fecharSeFora = (event: PointerEvent): void => {
			if (campoConvite && !campoConvite.contains(event.target as Node)) listaOrgaoAberta = false;
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
		resumoLote = '';
		try {
			const contagens = await bulkInviteOrgao(projectId, {
				orgao_id: orgaoSelecionado.id,
				papel,
				expires_at: expiracaoDoPeriodo(periodoDias)
			});
			resumoLote = conviteLoteResumo(contagens);
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
		resumoLote = '';
		try {
			await createProjectMember(projectId, {
				user_id: selecionado.id,
				papel,
				expires_at: expiracaoDoPeriodo(periodoDias)
			});
			limparSelecao();
			papel = CONVITE_PAPEL_PADRAO;
			periodoDias = CONVITE_PERIODO_PADRAO_DIAS;
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
		resumoLote = '';
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

	const resumoArea = $derived.by<string>(() => {
		const n = herdados.length;
		if (n === 0) return '';
		const base = n === 1 ? '1 pessoa' : `${n} pessoas`;
		const siglas = new Set(herdados.map((h) => h.orgao_sigla ?? h.orgao_nome ?? ''));
		const unica = siglas.size === 1 ? [...siglas][0] : '';
		return unica ? `${base} da ${unica}` : base;
	});

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			onClose();
		}
	}
</script>

<div
	class="fixed inset-0 z-[1050] flex items-start justify-center overflow-y-auto bg-overlay p-4 py-10"
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
		class="flex w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
	>
		<header class="flex items-start justify-between gap-4 px-5 pb-4 pt-5">
			<div class="flex min-w-0 flex-col gap-0.5">
				<h2 id="compartilhar-titulo" class="font-heading text-lg font-semibold text-text-primary">
					Compartilhar projeto
				</h2>
				<p class="line-clamp-1 text-[13px] text-text-secondary">{projectTitulo}</p>
			</div>
			<button
				type="button"
				onclick={onClose}
				aria-label="Fechar"
				class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-surface text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-times" aria-hidden="true"></i>
			</button>
		</header>

		<div class="h-px bg-border-subtle" aria-hidden="true"></div>

		<!-- Convite: busca + papel + expiração + ação num bloco único -->
		<section class="flex flex-col gap-2.5 px-5 py-4" aria-labelledby="compartilhar-convite-titulo">
			<h3
				id="compartilhar-convite-titulo"
				class="text-[11px] font-bold uppercase tracking-wider text-text-secondary"
			>
				{modo === 'pessoa' ? 'Convidar pessoa' : 'Convidar área'}
			</h3>

			<div bind:this={campoConvite} class="relative">
				<div
					class="flex items-stretch overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm transition-colors duration-fast focus-within:border-primary-500"
				>
					<div
						class="flex shrink-0 items-center gap-0.5 py-[5px] pl-[5px]"
						role="group"
						aria-label="Convidar por"
					>
						{@render modoBotao('pessoa', 'Pessoa', 'fa-user')}
						{@render modoBotao('area', 'Área', 'fa-sitemap')}
					</div>

					<div class="my-2 w-px self-stretch bg-border-subtle" aria-hidden="true"></div>

					{#if modo === 'pessoa'}
						<div class="flex min-h-[44px] min-w-0 flex-1 items-center gap-2.5 pl-3.5 pr-2">
							<i
								class="fas fa-magnifying-glass shrink-0 text-[12px] text-text-faint"
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
									class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									<i class="fas fa-times" aria-hidden="true"></i>
								</button>
							{/if}
						</div>
					{:else}
						<div class="flex min-h-[44px] min-w-0 flex-1 items-center gap-2.5 pl-3.5 pr-2">
							<i class="fas fa-sitemap shrink-0 text-[12px] text-text-faint" aria-hidden="true"></i>
							<input
								id="compartilhar-orgao"
								type="text"
								autocomplete="off"
								role="combobox"
								aria-expanded={listaOrgaoAberta && linhasOrgao.length > 0}
								aria-controls="compartilhar-orgaos"
								aria-autocomplete="list"
								placeholder={orgaosCarregando ? 'Carregando áreas…' : 'Sigla ou nome do órgão…'}
								bind:value={termoOrgao}
								oninput={() => {
									orgaoSelecionado = null;
									listaOrgaoAberta = true;
									destaqueOrgao = 0;
								}}
								onfocus={() => (listaOrgaoAberta = true)}
								onkeydown={onOrgaoKeydown}
								class="min-w-0 flex-1 border-none bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
							/>
							{#if orgaoSelecionado}
								<button
									type="button"
									onclick={limparOrgao}
									aria-label="Limpar área selecionada"
									class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									<i class="fas fa-times" aria-hidden="true"></i>
								</button>
							{/if}
						</div>
					{/if}

					<div class="my-2 w-px self-stretch bg-border-subtle" aria-hidden="true"></div>

					<div class="shrink-0">
						<SelectMenu
							options={papelOptions}
							value={papel}
							onSelect={(v) => (papel = normalizeConvitePapel(v))}
							unstyled
							ariaLabel="Papel do convite"
						>
							{#snippet trigger({ open, label })}
								<span
									class="flex min-h-[44px] items-center gap-1.5 whitespace-nowrap px-3.5 text-[13.5px] font-semibold text-text-primary transition-colors duration-fast hover:bg-surface-muted"
								>
									{label}
									<i
										class="fas fa-chevron-down text-[9px] text-text-faint transition-transform duration-fast"
										style:transform={open ? 'rotate(180deg)' : 'none'}
										aria-hidden="true"
									></i>
								</span>
							{/snippet}
						</SelectMenu>
					</div>

					<div class="my-2 w-px self-stretch bg-border-subtle" aria-hidden="true"></div>

					<div class="shrink-0">
						<SelectMenu
							id="compartilhar-expira"
							options={periodoOptions}
							value={convitePeriodoValue(periodoDias)}
							onSelect={(v) => (periodoDias = convitePeriodoDias(v))}
							unstyled
							align="right"
							ariaLabel="Período de validade do convite"
						>
							{#snippet trigger({ open, label })}
								<span
									class="flex min-h-[44px] items-center gap-1.5 whitespace-nowrap px-3.5 text-[13.5px] font-semibold tabular-nums text-text-primary transition-colors duration-fast hover:bg-surface-muted"
								>
									{label}
									<i
										class="fas fa-chevron-down text-[9px] text-text-faint transition-transform duration-fast"
										style:transform={open ? 'rotate(180deg)' : 'none'}
										aria-hidden="true"
									></i>
								</span>
							{/snippet}
						</SelectMenu>
					</div>

					<button
						type="button"
						onclick={convidar}
						disabled={!podeConvidar}
						class="shrink-0 self-stretch rounded-none bg-primary-600 px-[18px] text-sm font-semibold text-white transition-colors duration-fast hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
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
									aria-selected={index === destaqueOrgao}
									onclick={() => escolherOrgao(linha.option)}
									onmouseenter={() => (destaqueOrgao = index)}
									class="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-muted {index ===
									destaqueOrgao
										? 'bg-surface-muted'
										: ''}"
								>
									<span class="shrink-0 truncate">
										{#if linha.path}<span class="font-mono text-[11px] text-text-muted"
												>{linha.path} › </span
											>{/if}<span class="font-mono text-[12px] font-semibold text-text-primary"
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

			<p class="text-[13px] leading-relaxed text-text-secondary">
				Como {convitePapelLabel(papel)}, {sujeitoPapel} {consequenciaPapel}.
			</p>

			{#if formError}
				<p role="alert" class="text-sm text-danger">{formError}</p>
			{:else if resumoLote}
				<p role="status" aria-live="polite" class="text-[13px] font-medium text-text-secondary">
					<i class="fas fa-check text-[11px] text-success" aria-hidden="true"></i>
					{resumoLote}
				</p>
			{/if}
		</section>

		<div class="h-px bg-border-subtle" aria-hidden="true"></div>

		<!-- Convites diretos -->
		<section class="flex flex-col gap-2.5 px-5 py-4" aria-labelledby="compartilhar-diretos-titulo">
			<h3
				id="compartilhar-diretos-titulo"
				class="flex items-baseline gap-2 text-[11px] font-bold uppercase tracking-wider text-text-secondary"
			>
				Convidados
				{#if loadState === 'ready'}
					<span class="text-xs font-semibold normal-case tracking-normal text-text-muted">
						{diretos.length}
					</span>
				{/if}
			</h3>

			{#if loadState === 'loading'}
				<p role="status" aria-live="polite" class="text-sm text-text-secondary">
					Carregando membros…
				</p>
			{:else if loadState === 'error'}
				<p role="alert" class="text-sm text-danger">{loadError}</p>
			{:else if diretos.length === 0}
				<p class="text-sm text-text-muted">
					Nenhuma pessoa convidada até agora. Quem você convida entra na hora e aparece aqui.
				</p>
			{:else}
				<ul class="flex flex-col gap-1.5">
					{#each diretos as membro (membro.id)}
						<li
							class="flex flex-wrap items-center gap-3 rounded-lg border border-border-subtle bg-surface px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/50"
						>
							<span
								class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 text-[11px] font-bold text-primary-700 {membro.status ===
								'revogado'
									? 'opacity-60'
									: ''}"
								aria-hidden="true"
							>
								{iniciais(membro.user_name)}
							</span>

							<div
								class="flex min-w-0 flex-1 flex-col {membro.status === 'revogado' ? 'opacity-60' : ''}"
							>
								<span class="truncate text-sm font-medium text-text-primary">
									{membro.user_name}
									<span class="font-normal text-text-muted">@{membro.user_username}</span>
								</span>
								<span class="truncate text-xs text-text-secondary">{metaConvidado(membro)}</span>
							</div>

							<span
								class="flex shrink-0 items-center gap-1.5 text-xs font-medium tabular-nums text-text-secondary"
							>
								<span
									class="h-1.5 w-1.5 rounded-full {corExpiracao(membro)}"
									aria-hidden="true"
								></span>
								{textoExpiracao(membro)}
							</span>

							{#if membro.status === 'revogado'}
								<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-text-muted">
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
										align="right"
										ariaLabel={`Papel de ${membro.user_name}`}
									>
										{#snippet trigger({ open, label })}
											<span
												class="flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-[13px] font-semibold text-text-primary transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted"
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
					{/each}
				</ul>
			{/if}
		</section>

		<!-- Herdados por área: linha recolhível (read-only, muda só no admin) -->
		{#if loadState === 'ready' && herdados.length > 0}
			<button
				type="button"
				onclick={() => (areaAberta = !areaAberta)}
				aria-expanded={areaAberta}
				aria-controls="compartilhar-herdados-lista"
				class="flex w-full items-center gap-2.5 border-t border-border-subtle bg-surface-muted px-5 py-3 text-left transition-colors duration-fast hover:bg-surface-chip focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
			>
				<i
					class="fas fa-chevron-right text-[10px] text-text-muted transition-transform duration-fast"
					style:transform={areaAberta ? 'rotate(90deg)' : 'none'}
					aria-hidden="true"
				></i>
				<span class="text-[13px] font-semibold text-text-primary">Acesso por área</span>
				<span class="min-w-0 truncate text-[13px] text-text-secondary">{resumoArea}</span>
				<span class="ml-auto flex shrink-0 pl-2" aria-hidden="true">
					{#each herdados.slice(0, 3) as membro (membro.user_id + '-' + membro.orgao_id)}
						<span
							class="-mr-2 flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface-muted bg-primary-100 text-[9px] font-bold text-primary-700"
						>
							{iniciais(membro.user_name)}
						</span>
					{/each}
					{#if herdados.length > 3}
						<span
							class="flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface-muted bg-surface-chip text-[9px] font-bold text-text-secondary"
						>
							+{herdados.length - 3}
						</span>
					{:else}
						<span class="-mr-2 w-0"></span>
					{/if}
				</span>
			</button>

			{#if areaAberta}
				<div
					id="compartilhar-herdados-lista"
					class="flex flex-col gap-2 border-t border-border-subtle bg-surface-muted px-5 pb-4 pt-3"
				>
					<ul class="flex max-h-52 flex-col gap-1.5 overflow-y-auto pr-1">
						{#each herdados as membro (membro.user_id + '-' + membro.orgao_id)}
							<li
								class="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border-subtle bg-surface px-3 py-2"
							>
								<span
									class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-[10px] font-bold text-primary-700"
									aria-hidden="true"
								>
									{iniciais(membro.user_name)}
								</span>
								<div class="flex min-w-0 flex-1 flex-col">
									<span class="truncate text-sm text-text-primary">
										{membro.user_name}
										<span class="text-text-muted">@{membro.user_username}</span>
									</span>
									<span class="text-xs text-text-secondary">
										via área {membro.orgao_sigla ?? membro.orgao_nome ?? '—'}
									</span>
								</div>
								<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-text-secondary">
									{membro.papel}
								</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		{/if}
	</div>
</div>

<!-- Toggle do alvo do convite: troca só o primeiro campo da barra. -->
{#snippet modoBotao(alvo: ConviteModo, rotulo: string, icone: string)}
	<button
		type="button"
		aria-pressed={modo === alvo}
		onclick={() => trocarModo(alvo)}
		class="flex h-[34px] items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {modo ===
		alvo
			? 'bg-surface-chip text-text-primary'
			: 'text-text-muted hover:bg-surface-muted hover:text-text-secondary'}"
	>
		<i class="fas {icone} text-[10px]" aria-hidden="true"></i>
		{rotulo}
	</button>
{/snippet}
