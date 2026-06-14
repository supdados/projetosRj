<script lang="ts">
	/**
	 * Tela "Admin > Usuários" (FASE 4 — CRUD). Lista paginada de usuários via
	 * `GET /api/admin/usuarios` (módulo `$lib/api/adminUsers`), com ações de
	 * editar/excluir. Espelha templates/admin/list_users.html: ID, nome,
	 * login, órgão legado, órgãos vinculados (chips), CPF gov.br, perfil.
	 *
	 * Paridade v4.5 (templates/admin/list_users.html + 20-glass-forms-and-admin.css):
	 *   - Ícones Font Awesome (fas fa-*) idênticos ao markup original (fa-users-cog,
	 *     fa-user-plus, fa-users, fa-copy, fa-user-shield, fa-user, fa-pen, fa-trash).
	 *   - Coluna CPF com DOIS chips ("CPF cadastrado" + "Vinculado"/"Pendente").
	 *   - Tag "Você" no usuário corrente (via store `auth`), e botão excluir
	 *     desabilitado para o próprio usuário (não pode excluir a si mesmo).
	 *   - Paginação NUMERADA com janela (left/right edge + current) e setas «/».
	 *
	 * Mutations (exclusão) usam `client.post`/`del` via adminUsers.ts e pedem
	 * confirmação antes de executar.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { fetchAdminUsers, deleteAdminUser, fetchOrgaoOptionsForUser } from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import type { AdminUser, AdminUsersPageMeta, AdminOrgaoOption } from '$lib/types/adminUsers';
	import { auth } from '$lib/stores/auth';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let usuarios = $state<AdminUser[]>([]);
	let meta = $state<AdminUsersPageMeta | null>(null);
	let errorMessage = $state<string>('');
	let page = $state<number>(1);

	/** Busca de texto livre (nome/login/CPF) — debounced antes de recarregar. */
	let searchText = $state<string>('');
	/** Área (órgão) selecionada para filtrar; `null` = todas. */
	let areaId = $state<number | null>(null);
	let areaOptions = $state<AdminOrgaoOption[]>([]);

	// Combobox de área (botão → input de busca + listbox), espelhando o filtro de
	// projeto da tela /tarefas.
	let areaOpen = $state<boolean>(false);
	let areaQuery = $state<string>('');
	let areaActiveIndex = $state<number>(0);
	let areaInputEl = $state<HTMLInputElement | null>(null);

	let searchDebounce: ReturnType<typeof setTimeout> | null = null;

	const hasActiveFilters = $derived(searchText.trim() !== '' || areaId !== null);

	const selectedAreaLabel = $derived(
		areaId === null
			? 'Todas as áreas'
			: (areaOptions.find((o) => o.id === areaId)?.sigla ?? 'Todas as áreas')
	);

	/** Lista filtrada do combobox: "Todas" + órgãos casando com a busca. */
	const areaFilterList = $derived.by<{ id: number | null; label: string }[]>(() => {
		const q = areaQuery.trim().toLowerCase();
		const matches = (o: AdminOrgaoOption) =>
			!q || o.sigla.toLowerCase().includes(q) || o.nome.toLowerCase().includes(q);
		const items = areaOptions
			.filter(matches)
			.map((o) => ({ id: o.id as number | null, label: o.sigla }));
		return q ? items : [{ id: null, label: 'Todas as áreas' }, ...items];
	});

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
		loadState = usuarios.length ? loadState : 'loading';
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

	function openAreaFilter(): void {
		areaOpen = true;
		areaQuery = '';
		areaActiveIndex = 0;
		setTimeout(() => areaInputEl?.focus(), 0);
	}

	function closeAreaFilter(): void {
		areaOpen = false;
	}

	function pickArea(value: number | null): void {
		areaId = value;
		areaOpen = false;
		areaQuery = '';
		reloadFiltered();
	}

	function onAreaKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			areaActiveIndex = Math.min(areaActiveIndex + 1, areaFilterList.length - 1);
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			areaActiveIndex = Math.max(areaActiveIndex - 1, 0);
		} else if (event.key === 'Enter') {
			event.preventDefault();
			const opt = areaFilterList[areaActiveIndex];
			if (opt) pickArea(opt.id);
		} else if (event.key === 'Escape') {
			closeAreaFilter();
		}
	}

	function clearFilters(): void {
		searchText = '';
		areaId = null;
		areaQuery = '';
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
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
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
				class="h-9 w-full max-w-sm shrink-0 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast hover:bg-surface-muted focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			/>

			<!-- Seletor de área (combobox: botão → busca + listbox). Largura fixa
			     pequena; nenhum campo cresce → sobra espaço vazio à direita. -->
			<div class="relative w-56 shrink-0">
				{#if areaOpen}
					<input
						bind:this={areaInputEl}
						type="text"
						bind:value={areaQuery}
						oninput={() => (areaActiveIndex = 0)}
						onkeydown={onAreaKeydown}
						onblur={() => setTimeout(closeAreaFilter, 120)}
						role="combobox"
						aria-expanded="true"
						aria-controls="filter_area_listbox"
						aria-autocomplete="list"
						aria-label="Filtrar por área"
						placeholder="Buscar área…"
						autocomplete="off"
						class="h-9 w-full rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
					/>
					<ul
						id="filter_area_listbox"
						role="listbox"
						class="thin-scroll absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-lg border border-border-subtle bg-surface py-1 shadow-md"
					>
						{#each areaFilterList as opt, i (opt.id ?? 'all')}
							<li class="contents">
								<button
									type="button"
									role="option"
									aria-selected={opt.id === areaId}
									onmousedown={(e) => {
										e.preventDefault();
										pickArea(opt.id);
									}}
									class="block w-full truncate px-3 py-1.5 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted {i ===
									areaActiveIndex
										? 'bg-surface-muted'
										: ''}"
								>
									{opt.label}
								</button>
							</li>
						{/each}
						{#if areaFilterList.length === 0}
							<li class="px-3 py-1.5 text-sm text-text-muted">Nenhuma área encontrada</li>
						{/if}
					</ul>
				{:else}
					<button
						type="button"
						onclick={openAreaFilter}
						aria-haspopup="listbox"
						aria-label="Filtrar por área"
						class="flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<span class="min-w-0 flex-1 truncate text-left {areaId === null ? 'text-text-muted' : ''}"
							>{selectedAreaLabel}</span
						>
						<i class="fas fa-chevron-down shrink-0 text-xs text-text-muted" aria-hidden="true"></i>
					</button>
				{/if}
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

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando usuários…</p>
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
				class="mt-1 rounded-[13px] border border-dashed border-primary-500/40 bg-surface-muted px-4 py-8 text-center"
			>
				<p class="text-md text-text-secondary">
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
				class="mt-1 rounded-[13px] border border-dashed border-primary-500/40 bg-surface-muted px-4 py-8 text-center"
			>
				<span
					class="mx-auto mb-2.5 inline-flex h-[52px] w-[52px] items-center justify-center rounded-[14px] border border-primary-500/25 bg-primary-100 text-primary-700"
					aria-hidden="true"
				>
					<i class="fas fa-user-plus text-xl"></i>
				</span>
				<h2 class="mb-1.5 font-heading text-xl font-bold text-primary-700">
					Nenhum usuário cadastrado
				</h2>
				<p class="mb-3.5 text-md text-text-secondary">
					Cadastre o primeiro usuário para iniciar o gerenciamento de acesso da aplicação.
				</p>
				<a
					href={`${base}/admin/usuarios/novo`}
					class="inline-flex items-center gap-2 rounded-[9px] border border-primary-700 bg-topnav-gradient px-3.5 py-2 text-md font-semibold text-white no-underline shadow-md transition-all duration-slow ease-[cubic-bezier(0.4,0,0.2,1)] hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:translate-y-0"
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
			<div class="overflow-hidden rounded-[13px] border border-primary-500/30 bg-glass-card shadow-md">
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="w-full border-collapse align-middle text-sm">
						<caption class="sr-only">Lista de usuários do sistema</caption>
						<thead>
							<tr class="text-left">
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">ID</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">Nome Completo</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">Login</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">Órgão</th>
								<th scope="col" class="w-[160px] whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">Órgãos Vinculados</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">CPF gov.br</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-center text-2xs font-bold uppercase tracking-caps text-text-muted">Perfil</th>
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-center text-2xs font-bold uppercase tracking-caps text-text-muted">Ações</th>
							</tr>
						</thead>
						<tbody>
							{#each usuarios as user (user.id)}
								{@const isSelf = currentUserId !== null && user.id === currentUserId}
								<tr class="border-t border-border-subtle transition-colors duration-fast hover:bg-primary-100/40">
									<td class="px-3 py-2.5 align-middle">
										<span class="text-sm font-semibold text-text-secondary">{user.id}</span>
									</td>
									<td class="px-3 py-2.5 align-middle">
										<div class="flex flex-wrap items-center gap-1.5">
											<span class="font-semibold text-text-primary">{user.name}</span>
											{#if isSelf}
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-primary-100 px-2 py-0.5 text-xs font-bold text-primary-700"
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
												title={user.orgaos.map((o) => o.nome).join(', ')}
											>
												{user.orgaos.map((o) => o.sigla).join(', ')}
											</span>
										{:else}
											<span class="text-sm italic text-text-muted">Sem órgão definido</span>
										{/if}
									</td>
									<td class="px-3 py-2.5 align-middle">
										{#if user.cpf_govbr}
											<!-- Original: dois chips ("CPF cadastrado" + estado do vínculo). -->
											<div class="flex flex-wrap items-center gap-1.5">
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-primary-100 px-2 py-0.5 text-xs font-bold text-primary-700"
												>
													CPF cadastrado
												</span>
												<span
													class="inline-flex items-center rounded-full border border-primary-500/30 bg-primary-100 px-2 py-0.5 text-xs font-bold text-primary-700"
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
