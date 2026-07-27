<script lang="ts">
	/**
	 * Modal "Compartilhar" do Detalhe de Projeto (S4/F3-19).
	 *
	 * Convida um usuário JÁ existente e ativo para o projeto (sem token, sem
	 * aceite — §7), lista os convites diretos com status (ativo/expirado/
	 * revogado) e os membros HERDADOS pelo vínculo de área, estes read-only:
	 * herdado não é linha de `project_member` e só muda na tela de admin.
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
	import {
		createProjectMember,
		fetchProjectMembers,
		revokeProjectMember,
		searchInvitableUsers,
		updateProjectMember
	} from '$lib/api/projectMembers';
	import { focusTrap } from '$lib/actions/focusTrap';
	import Badge from '$lib/components/Badge.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import DatePickerPanel from '$lib/components/DatePickerPanel.svelte';
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
		conviteErrorMessage,
		conviteStatusLabel,
		conviteStatusTone,
		convitePapelLabel,
		expiracaoPadraoIso,
		normalizeConvitePapel
	} from '$lib/utils/projectMembers';

	interface Props {
		projectId: number;
		projectTitulo: string;
		onClose: () => void;
	}

	let { projectId, projectTitulo, onClose }: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let diretos = $state<ProjectMemberDireto[]>([]);
	let herdados = $state<ProjectMemberHerdado[]>([]);
	let loadError = $state<string>('');

	// Formulário de convite
	let termo = $state<string>('');
	let resultados = $state<UsuarioConvidavel[]>([]);
	let buscando = $state<boolean>(false);
	let listaAberta = $state<boolean>(false);
	let destaque = $state<number>(-1);
	let selecionado = $state<UsuarioConvidavel | null>(null);
	let papel = $state<ConvitePapel>(CONVITE_PAPEL_PADRAO);
	let expiraEm = $state<string>(expiracaoPadraoIso());
	let dataAnchorEl = $state<HTMLElement | null>(null);
	let dataAberta = $state<boolean>(false);
	let enviando = $state<boolean>(false);
	let formError = $state<string>('');

	/** Id da linha em mutação — desabilita só aquela linha. */
	let linhaOcupada = $state<number | null>(null);

	const papelOptions: SelectMenuOption[] = CONVITE_PAPEL_OPTIONS.map((o) => ({
		value: o.value,
		label: o.label
	}));
	const podeConvidar = $derived(selecionado !== null && !enviando);

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
		if (q.length < 2 || selecionado !== null) {
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

	async function convidar(): Promise<void> {
		if (!selecionado) return;
		enviando = true;
		formError = '';
		try {
			await createProjectMember(projectId, {
				user_id: selecionado.id,
				papel,
				expires_at: expiraEm || null
			});
			limparSelecao();
			papel = CONVITE_PAPEL_PADRAO;
			expiraEm = expiracaoPadraoIso();
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
			() => updateProjectMember(projectId, membro.id, { expires_at: expiracaoPadraoIso() }),
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
					expires_at: expiracaoPadraoIso()
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

	function formatarData(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
	}

	function textoExpiracao(membro: ProjectMemberDireto): string {
		if (membro.status === 'revogado') return 'Acesso revogado';
		if (!membro.expires_at) return 'Sem expiração';
		const prefixo = membro.status === 'expirado' ? 'Expirou em' : 'Expira em';
		return `${prefixo} ${formatarData(membro.expires_at)}`;
	}

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
		class="flex w-full max-w-2xl flex-col gap-5 rounded-xl border border-border-subtle bg-surface p-5 shadow-lg"
	>
		<header class="flex items-start justify-between gap-3">
			<div class="flex items-start gap-3">
				<span
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-100 text-primary-700"
					aria-hidden="true"
				>
					<i class="fas fa-user-plus"></i>
				</span>
				<div class="flex min-w-0 flex-col gap-1">
					<h2
						id="compartilhar-titulo"
						class="font-heading text-lg font-semibold text-text-primary"
					>
						Compartilhar projeto
					</h2>
					<p class="line-clamp-1 text-xs text-text-secondary">{projectTitulo}</p>
				</div>
			</div>
			<button
				type="button"
				onclick={onClose}
				aria-label="Fechar"
				class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-times" aria-hidden="true"></i>
			</button>
		</header>

		<!-- Convite: busca de usuário + papel + expiração -->
		<section class="flex flex-col gap-3" aria-labelledby="compartilhar-convite-titulo">
			<h3 id="compartilhar-convite-titulo" class="text-sm font-semibold text-text-primary">
				Convidar pessoa
			</h3>

			<div class="flex flex-col gap-2 sm:flex-row sm:items-end">
				<div class="relative flex min-w-0 flex-1 flex-col gap-1">
					<label for="compartilhar-busca" class="text-xs font-medium text-text-secondary">
						Pessoa
					</label>
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
						class="h-9 w-full rounded-md border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					/>
					{#if listaAberta && resultados.length > 0}
						<ul
							id="compartilhar-resultados"
							role="listbox"
							aria-label="Usuários encontrados"
							class="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-md border border-border-subtle bg-surface py-1 shadow-lg"
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
						<p class="absolute top-full mt-1 text-xs text-text-muted" role="status">
							Buscando…
						</p>
					{/if}
				</div>

				<div class="flex w-full shrink-0 flex-col gap-1 sm:w-32">
					<span class="text-xs font-medium text-text-secondary">Papel</span>
					<SelectMenu
						options={papelOptions}
						value={papel}
						onSelect={(v) => (papel = normalizeConvitePapel(v))}
						size="sm"
						ariaLabel="Papel do convite"
					/>
				</div>

				<div class="flex w-full shrink-0 flex-col gap-1 sm:w-40">
					<label for="compartilhar-expira" class="text-xs font-medium text-text-secondary">
						Expira em
					</label>
					<button
						id="compartilhar-expira"
						type="button"
						bind:this={dataAnchorEl}
						aria-haspopup="dialog"
						aria-expanded={dataAberta}
						onclick={() => (dataAberta = !dataAberta)}
						class="h-9 rounded-md border border-border-subtle bg-surface px-2.5 text-left text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<span class={expiraEm ? '' : 'text-text-muted'}>
							{expiraEm ? formatarData(expiraEm) : 'Sem expiração'}
						</span>
					</button>
					{#if dataAberta && dataAnchorEl}
						<DatePickerPanel
							anchor={dataAnchorEl}
							value={expiraEm || null}
							ariaLabel="Data de expiração do convite"
							onPick={(iso) => {
								expiraEm = iso;
								dataAberta = false;
							}}
							onClose={() => (dataAberta = false)}
						/>
					{/if}
				</div>

				<button
					type="button"
					onclick={convidar}
					disabled={!podeConvidar}
					class="h-9 shrink-0 rounded-md bg-primary-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors duration-fast hover:bg-primary-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{enviando ? 'Convidando…' : 'Convidar'}
				</button>
			</div>

			<p class="flex items-center gap-2 text-xs text-text-secondary">
				<i class="fas fa-circle-info text-primary-700" aria-hidden="true"></i>
				<span>Esta pessoa verá todo o conteúdo deste projeto.</span>
			</p>

			{#if formError}
				<p role="alert" class="text-sm text-danger">{formError}</p>
			{/if}
		</section>

		<!-- Convites diretos -->
		<section class="flex flex-col gap-2" aria-labelledby="compartilhar-diretos-titulo">
			<h3 id="compartilhar-diretos-titulo" class="text-sm font-semibold text-text-primary">
				Convidados
			</h3>

			{#if loadState === 'loading'}
				<p role="status" aria-live="polite" class="text-sm text-text-secondary">
					Carregando membros…
				</p>
			{:else if loadState === 'error'}
				<p role="alert" class="text-sm text-danger">{loadError}</p>
			{:else if diretos.length === 0}
				<p class="text-sm text-text-muted">Nenhuma pessoa convidada até agora.</p>
			{:else}
				<ul class="flex flex-col gap-1.5">
					{#each diretos as membro (membro.id)}
						<li
							class="flex flex-wrap items-center gap-3 rounded-lg border border-border-subtle bg-surface-muted px-3 py-2"
						>
							<div class="flex min-w-0 flex-1 flex-col">
								<span class="truncate text-sm font-medium text-text-primary">
									{membro.user_name}
									<span class="font-normal text-text-muted">@{membro.user_username}</span>
								</span>
								<span class="text-xs text-text-secondary">
									{membro.user_orgao_sigla ?? 'Sem órgão'} · {textoExpiracao(membro)}
								</span>
							</div>

							<Badge tone={conviteStatusTone(membro.status)}>
								{conviteStatusLabel(membro.status)}
							</Badge>

							{#if membro.status === 'revogado'}
								<span class="text-xs font-semibold uppercase tracking-wide text-text-secondary">
									{convitePapelLabel(membro.papel)}
								</span>
							{:else}
								<div class="w-28 shrink-0">
									<SelectMenu
										options={papelOptions}
										value={membro.papel}
										onSelect={(v) => trocarPapel(membro, v)}
										size="sm"
										disabled={linhaOcupada === membro.id}
										ariaLabel={`Papel de ${membro.user_name}`}
									/>
								</div>
							{/if}

							<div class="flex shrink-0 items-center gap-1.5">
								{#if membro.status === 'expirado'}
									<button
										type="button"
										onclick={() => renovar(membro)}
										disabled={linhaOcupada === membro.id}
										class="rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										Renovar
									</button>
								{/if}
								{#if membro.status === 'revogado'}
									<button
										type="button"
										onclick={() => reativar(membro)}
										disabled={linhaOcupada === membro.id}
										class="rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										Reativar
									</button>
								{:else}
									<button
										type="button"
										onclick={() => revogar(membro)}
										disabled={linhaOcupada === membro.id}
										class="rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
									>
										Revogar
									</button>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<!-- Herdados por área: read-only (mudam só na administração de usuários) -->
		{#if loadState === 'ready' && herdados.length > 0}
			<section class="flex flex-col gap-2" aria-labelledby="compartilhar-herdados-titulo">
				<h3 id="compartilhar-herdados-titulo" class="text-sm font-semibold text-text-primary">
					Acesso por área
				</h3>
				<ul class="flex max-h-52 flex-col gap-1.5 overflow-y-auto pr-1">
					{#each herdados as membro (membro.user_id + '-' + membro.orgao_id)}
						<li
							class="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border-subtle px-3 py-2"
						>
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
				<p class="text-xs text-text-muted">
					O acesso por área vem do vínculo do usuário e só muda na administração de usuários.
				</p>
			</section>
		{/if}
	</div>
</div>
