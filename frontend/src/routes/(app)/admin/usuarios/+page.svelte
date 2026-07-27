<script lang="ts">
	/**
	 * Tela "Admin > Usuários". Lista paginada via `GET /api/admin/usuarios`
	 * (módulo `$lib/api/adminUsers`), com ações de editar/excluir.
	 *
	 * O botão excluir fica desabilitado para o próprio usuário (não pode
	 * excluir a si mesmo); a exclusão pede confirmação antes de executar.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import {
		fetchAdminUsers,
		peekAdminUsers,
		deleteAdminUser,
		fetchOrgaoOptionsForUser,
		peekOrgaoOptionsForUser
	} from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import type { AdminUser, AdminUsersPageMeta, AdminOrgaoOption } from '$lib/types/adminUsers';
	import { auth } from '$lib/stores/auth';
	import { papelLabel } from '$lib/utils/orgaoPapel';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import AdminUsuariosSkeleton from '$lib/components/skeletons/AdminUsuariosSkeleton.svelte';
	import OrgaoTreeSelect from '$lib/components/OrgaoTreeSelect.svelte';
	import GrantsOrfaosPanel from '$lib/components/GrantsOrfaosPanel.svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';

	type LoadState = 'loading' | 'ready' | 'error';

	let page = $state<number>(1);
	/** Busca de texto livre (nome/login/CPF) — debounced antes de recarregar. */
	let searchText = $state<string>('');
	/** Área (órgão) selecionada para filtrar; `null` = todas. */
	let areaId = $state<number | null>(null);

	// SWR: reabre com o ultimo dado bom dos filtros correntes (cache de modulo em
	// $lib/api/adminUsers) e revalida em background — sem flash de loading ao
	// voltar para a rota. O skeleton so aparece quando NAO ha cache (1a visita
	// ou filtros nunca carregados).
	// Chave inicial = defaults literais dos filtros acima (page 1, sem busca/área).
	const initialUsers = peekAdminUsers({ page: 1, q: '', areaId: undefined });
	let loadState = $state<LoadState>(initialUsers ? 'ready' : 'loading');
	let usuarios = $state<AdminUser[]>(initialUsers?.usuarios ?? []);
	let meta = $state<AdminUsersPageMeta | null>(initialUsers?.meta ?? null);
	let errorMessage = $state<string>('');

	let areaOptions = $state<AdminOrgaoOption[]>(peekOrgaoOptionsForUser() ?? []);

	/** Opções no shape esperado pelo `OrgaoTreeSelect` (mesmo padrão de UserForm/CriarProjetoModal). */
	const areaTreeOptions = $derived<OrgaoSelectOption[]>(
		areaOptions.map((o) => ({
			value: o.id,
			label: o.sigla,
			sigla: o.sigla,
			nome: o.nome,
			pai_id: o.pai_id
		}))
	);

	let searchDebounce: ReturnType<typeof setTimeout> | null = null;

	const hasActiveFilters = $derived(searchText.trim() !== '' || areaId !== null);

	/** Id em exclusão (desabilita o botão e evita duplo clique). */
	let deletingId = $state<number | null>(null);
	/** Mensagem de erro de exclusão (separada do erro de carregamento). */
	let actionError = $state<string>('');

	let inFlight: AbortController | null = null;

	/** Id do usuário autenticado (para tag "Você" e travar auto-exclusão). */
	let currentUserId = $state<number | null>(null);
	const unsubAuth = auth.subscribe((state) => {
		currentUserId = state.user?.id ?? null;
	});

	const total = $derived(meta?.total ?? 0);
	const totalPages = $derived(meta?.total_pages ?? 1);

	async function load(): Promise<void> {
		// SWR: com cache dos filtros correntes mostra o dado antigo ja (sem
		// skeleton) e a revalidacao abaixo troca em silencio; sem cache, skeleton.
		const cached = peekAdminUsers({ page, q: searchText, areaId: areaId ?? undefined });
		if (cached) {
			usuarios = cached.usuarios;
			meta = cached.meta;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const result = await fetchAdminUsers(
				{ page, q: searchText, areaId: areaId ?? undefined },
				controller.signal
			);
			if (controller.signal.aborted) return;
			usuarios = result.usuarios;
			meta = result.meta;
			page = result.meta.page;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar os usuários.';
			loadState = 'error';
		}
	}

	function goToPage(target: number): void {
		if (target < 1 || target > totalPages || target === page) return;
		page = target;
		void load();
	}

	/** Recarrega a partir da página 1 sempre que um filtro muda. */
	function reloadFiltered(): void {
		page = 1;
		void load();
	}

	function onSearchInput(): void {
		if (searchDebounce) clearTimeout(searchDebounce);
		searchDebounce = setTimeout(reloadFiltered, 300);
	}

	function pickArea(value: number | null): void {
		areaId = value;
		reloadFiltered();
	}

	function clearFilters(): void {
		searchText = '';
		areaId = null;
		reloadFiltered();
	}

	async function confirmDelete(user: AdminUser): Promise<void> {
		const ok = window.confirm(
			`Tem certeza que deseja excluir este usuário? Esta ação não pode ser desfeita.`
		);
		if (!ok) return;
		actionError = '';
		deletingId = user.id;
		try {
			await deleteAdminUser(user.id);
			deletingId = null;
			// Recarrega a página atual; recua se a página esvaziou.
			if (usuarios.length === 1 && page > 1) page -= 1;
			await load();
		} catch (err) {
			deletingId = null;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			actionError =
				err instanceof Error ? err.message : 'Falha ao excluir o usuário.';
		}
	}

	onMount(() => {
		void load();
		void fetchOrgaoOptionsForUser()
			.then((opts) => {
				areaOptions = opts;
			})
			.catch(() => {
				// Sem opções de área o seletor apenas oferece "Todas"; não bloqueia a tela.
			});
		return () => inFlight?.abort();
	});

	onDestroy(() => {
		inFlight?.abort();
		if (searchDebounce) clearTimeout(searchDebounce);
		unsubAuth();
	});

	function editHref(user: AdminUser): string {
		return `${base}/admin/usuarios/${user.id}`;
	}
</script>

<svelte:head>
	<title>Gerenciar Usuários — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="admin-usuarios-title" class="mx-auto flex w-full max-w-[1400px] flex-col gap-4">
	<!--
		Card superior unificado (header + filtros) no mesmo padrão da tela /tarefas:
		PageHeader embedded + linha de filtros separada por borda.
	-->
	<div class="rounded-xl border border-border-subtle bg-surface">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="admin-usuarios-title">
			{#snippet titleContent()}
				<span class="align-middle">Gerenciar Usuários</span>
				{#if loadState !== 'loading'}
					<CountBadge class="ml-2">{total} usuário{total === 1 ? '' : 's'}</CountBadge>
				{/if}
			{/snippet}
			{#snippet actions()}
				<Button size="sm" href={`${base}/admin/usuarios/novo`}>
					{#snippet icon()}<i class="fas fa-user-plus" aria-hidden="true"></i>{/snippet}
					Novo Usuário
				</Button>
			{/snippet}
		</PageHeader>

		<form
			class="flex items-center gap-2 border-t border-border-subtle px-4 py-2.5"
			aria-label="Filtros de usuários"
			onsubmit={(e) => e.preventDefault()}
		>
			<!-- Busca de texto livre (nome ou login). -->
			<input
				type="text"
				bind:value={searchText}
				oninput={onSearchInput}
				placeholder="Buscar por nome ou login…"
				aria-label="Buscar usuários por nome ou login"
				autocomplete="off"
				class="h-9 w-full max-w-sm shrink-0 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast hover:bg-surface-muted focus:border-primary-500 focus:outline-none"
			/>

			<!-- Seletor de área em árvore (mesmo componente de UserForm/CriarProjetoModal).
			     Largura fixa pequena; nenhum campo cresce → sobra espaço vazio à direita. -->
			<div class="w-56 shrink-0">
				<OrgaoTreeSelect
					id="admin-usuarios-area-filter"
					options={areaTreeOptions}
					value={areaId}
					onSelect={pickArea}
					allowTodos
					todosLabel="Todas as áreas"
					ariaLabel="Filtrar por área"
				/>
			</div>

			{#if hasActiveFilters}
				<button
					type="button"
					onclick={clearFilters}
					class="h-9 shrink-0 rounded-lg border border-border-subtle bg-surface px-3.5 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Limpar
				</button>
			{/if}
		</form>
	</div>

	{#if actionError}
		<div role="alert" class="rounded-lg border border-danger bg-surface px-5 py-3 text-sm text-text-primary">
			{actionError}
		</div>
	{/if}

	<GrantsOrfaosPanel />

	{#if loadState === 'loading'}
		<p role="status" class="sr-only">Carregando usuários…</p>
		<AdminUsuariosSkeleton />
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={() => load()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else}
		<div role="status" aria-live="polite" class="sr-only">
			{total} usuário{total === 1 ? '' : 's'} encontrado{total === 1 ? '' : 's'}.
		</div>

		{#if usuarios.length === 0 && hasActiveFilters}
			<!-- Vazio por filtro: mensagem dedicada (não é "primeiro cadastro"). -->
			<div
				class="mt-1 rounded-xl border border-dashed border-primary-500/40 bg-surface-muted px-4 py-8 text-center"
			>
				<p class="text-sm text-text-secondary">
					Nenhum usuário encontrado para os filtros aplicados.
				</p>
				<button
					type="button"
					onclick={clearFilters}
					class="mt-3 inline-flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-3.5 py-2 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Limpar filtros
				</button>
			</div>
		{:else if usuarios.length === 0}
			<!-- Estado vazio (.admin-users-empty-state): cartão tracejado centralizado. -->
			<div
				class="mt-1 rounded-xl border border-dashed border-primary-500/40 bg-surface-muted px-4 py-8 text-center"
			>
				<span
					class="mx-auto mb-2.5 inline-flex h-[52px] w-[52px] items-center justify-center rounded-xl border border-primary-500/25 bg-surface-elevated text-primary-500"
					aria-hidden="true"
				>
					<i class="fas fa-user-plus text-xl"></i>
				</span>
				<h2 class="mb-1.5 font-heading text-xl font-bold text-primary-500">
					Nenhum usuário cadastrado
				</h2>
				<p class="mb-3.5 text-sm text-text-secondary">
					Cadastre o primeiro usuário para iniciar o gerenciamento de acesso da aplicação.
				</p>
				<a
					href={`${base}/admin/usuarios/novo`}
					class="inline-flex h-9 items-center gap-2 rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-primary-fg no-underline transition-all duration-fast hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
				>
					<i class="fas fa-plus"></i>
					Criar Primeiro Usuário
				</a>
			</div>
		{:else}
			<!--
				Cartão de tabela "glass" (.admin-users-table-card): superfície
				translúcida com cabeçalho em maiúsculas e linhas com hover sutil.
			-->
			<div class="overflow-hidden rounded-xl border border-border-subtle bg-surface">
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="w-full border-collapse align-middle text-sm">
						<caption class="sr-only">Lista de usuários do sistema</caption>
						<thead>
							<tr class="border-b border-border-subtle bg-surface-muted text-left">
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">ID</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">Nome Completo</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">Login</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">Órgão</th>
								<th scope="col" class="w-[160px] whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">Órgãos Vinculados</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-caps text-text-muted">CPF gov.br</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-center text-2xs font-semibold uppercase tracking-caps text-text-muted">Perfil</th>
								<th scope="col" class="whitespace-nowrap px-3 py-2.5 text-center text-2xs font-semibold uppercase tracking-caps text-text-muted">Ações</th>
							</tr>
						</thead>
						<tbody>
							{#each usuarios as user (user.id)}
								{@const isSelf = currentUserId !== null && user.id === currentUserId}
								<tr class="border-t border-border-subtle transition-colors duration-fast hover:bg-surface-muted">
									<td class="px-3 py-2.5 align-middle">
										<span class="text-sm font-semibold text-text-secondary">{user.id}</span>
									</td>
									<td class="px-3 py-2.5 align-middle">
										<div class="flex flex-wrap items-center gap-1.5">
											<span class="font-semibold text-text-primary">{user.name}</span>
											{#if isSelf}
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-surface-muted px-2 py-0.5 text-xs font-bold text-primary-500"
												>
													Você
												</span>
											{/if}
										</div>
									</td>
									<td class="px-3 py-2.5 align-middle">
										<span class="font-mono text-sm font-semibold text-text-secondary">{user.username}</span>
									</td>
									<td class="px-3 py-2.5 align-middle">
										<span class="text-sm font-medium text-text-secondary">
											{user.orgao ?? 'Não informado'}
										</span>
									</td>
									<td class="max-w-[160px] px-3 py-2.5 align-middle">
										{#if user.orgaos.length > 0}
											<span
												class="block truncate text-sm text-text-secondary"
												title={user.orgaos
													.map((o) => `${o.nome} — ${papelLabel(o.papel)}`)
													.join(', ')}
											>
												{user.orgaos.map((o) => `${o.sigla} (${papelLabel(o.papel)})`).join(', ')}
											</span>
										{:else}
											<span class="text-sm italic text-text-muted">Sem órgão definido</span>
										{/if}
									</td>
									<td class="px-3 py-2.5 align-middle">
										{#if user.cpf_govbr}
											<div class="flex flex-wrap items-center gap-1.5">
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-surface-muted px-2 py-0.5 text-xs font-bold text-primary-500"
												>
													CPF cadastrado
												</span>
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-surface-muted px-2 py-0.5 text-xs font-bold text-primary-500"
												>
													{user.has_govbr_link ? 'Vinculado' : 'Pendente'}
												</span>
											</div>
										{:else}
											<span class="text-sm italic text-text-muted">Não vinculado</span>
										{/if}
									</td>
									<td class="px-3 py-2.5 text-center align-middle">
										{#if user.is_admin}
											<span
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-md border border-success/40 bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-success"
											>
												<i class="fas fa-user-shield"></i>
												Admin
											</span>
										{:else}
											<span
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-md border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-text-secondary"
											>
												<i class="fas fa-user"></i>
												Padrão
											</span>
										{/if}
									</td>
									<td class="px-3 py-2.5 text-center align-middle">
										<div class="inline-flex items-center gap-1">
											<a
												href={editHref(user)}
												title="Editar Usuário"
												aria-label="Editar usuário {user.name}"
												class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-muted no-underline transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											>
												<i class="fas fa-pen"></i>
											</a>
											{#if isSelf}
												<button
													type="button"
													disabled
													title="Não é possível excluir o próprio usuário"
													aria-label="Não é possível excluir o próprio usuário"
													class="inline-flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-md text-text-muted"
												>
													<i class="fas fa-trash"></i>
												</button>
											{:else}
												<button
													type="button"
													onclick={() => confirmDelete(user)}
													disabled={deletingId === user.id}
													title="Excluir Usuário"
													aria-label="Excluir usuário {user.name}"
													class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-50"
												>
													<i class="fas {deletingId === user.id ? 'fa-spinner fa-spin' : 'fa-trash'}"></i>
												</button>
											{/if}
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			{#if totalPages > 1}
				<PaginationBar
					page={meta?.page ?? page}
					totalPages={totalPages}
					total={total}
					perPage={meta?.per_page}
					itemLabel="usuários"
					label="Paginação de usuários"
					disabled={loadState !== 'ready'}
					onChange={goToPage}
				/>
			{/if}
		{/if}
	{/if}
</section>
