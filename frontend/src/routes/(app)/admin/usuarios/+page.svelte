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
	import { fetchAdminUsers, deleteAdminUser } from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import type { AdminUser, AdminUsersPageMeta } from '$lib/types/adminUsers';
	import { auth } from '$lib/stores/auth';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let usuarios = $state<AdminUser[]>([]);
	let meta = $state<AdminUsersPageMeta | null>(null);
	let errorMessage = $state<string>('');
	let page = $state<number>(1);

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

	/**
	 * Janela de paginação no estilo Flask-SQLAlchemy `iter_pages`
	 * (left_edge=1, right_edge=1, left_current=1, right_current=2),
	 * espelhando o markup original. `null` representa as reticências "…".
	 */
	const pageWindow = $derived.by<(number | null)[]>(() => {
		const pages: (number | null)[] = [];
		let last = 0;
		for (let p = 1; p <= totalPages; p += 1) {
			const nearEdge = p <= 1 || p > totalPages - 1;
			const nearCurrent = p >= page - 1 && p <= page + 2;
			if (nearEdge || nearCurrent) {
				if (last && p - last > 1) pages.push(null);
				pages.push(p);
				last = p;
			}
		}
		return pages;
	});

	async function load(): Promise<void> {
		loadState = usuarios.length ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const result = await fetchAdminUsers(page, controller.signal);
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
		return () => inFlight?.abort();
	});

	onDestroy(() => {
		inFlight?.abort();
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
	<PageHeader compact class="min-h-[3.5rem]" labelId="admin-usuarios-title">
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

		{#if usuarios.length === 0}
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
			<!-- Paginação atual (a contagem total agora vive no CountBadge do header). -->
			<div class="mb-1 flex flex-wrap items-center gap-1.5">
				<span
					class="inline-flex items-center gap-1.5 rounded-full border border-primary-500/50 bg-surface px-2.5 py-1 text-xs font-semibold text-text-secondary"
				>
					<i class="fas fa-copy"></i>
					Página {page} de {totalPages}
				</span>
			</div>

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
								<th scope="col" class="whitespace-nowrap border-b border-primary-500/40 bg-surface-muted px-3 py-2.5 text-2xs font-bold uppercase tracking-caps text-text-muted">Órgãos Vinculados</th>
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
										<span
											class="inline-flex items-center rounded-full border border-primary-500/40 bg-surface px-1.5 py-0.5 text-xs font-bold text-text-secondary"
										>
											#{user.id}
										</span>
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
									<td class="px-3 py-2.5 align-middle">
										{#if user.orgaos.length > 0}
											<div class="flex flex-wrap gap-1">
												{#each user.orgaos as orgao (orgao.id)}
													<span
														class="inline-flex items-center rounded-full border border-primary-500/40 bg-surface px-2 py-0.5 text-xs font-semibold leading-snug text-text-secondary"
														title={orgao.nome}
													>
														{orgao.sigla}
													</span>
												{/each}
											</div>
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
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-full border border-success/40 bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-success"
											>
												<i class="fas fa-user-shield"></i>
												Admin
											</span>
										{:else}
											<span
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-text-secondary"
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
												class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-primary-500/30 bg-primary-100/60 text-primary-700 no-underline transition-colors duration-fast hover:border-primary-500/50 hover:bg-primary-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											>
												<i class="fas fa-pen"></i>
											</a>
											{#if isSelf}
												<button
													type="button"
													disabled
													title="Não é possível excluir o próprio usuário"
													aria-label="Não é possível excluir o próprio usuário"
													class="inline-flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-md border border-border-subtle bg-surface-muted text-text-muted"
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
													class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-danger/30 bg-surface-muted text-danger transition-colors duration-fast hover:border-danger/50 hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-50"
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
				<!--
					Paginação NUMERADA (.admin-users-pagination): janela com reticências,
					setas «/», item ativo em gradiente — espelha iter_pages do original.
				-->
				<nav class="mt-2 flex items-center justify-center gap-1" aria-label="Paginação de usuários">
					<button
						type="button"
						onclick={() => goToPage(page - 1)}
						disabled={page <= 1}
						aria-label="Página anterior"
						class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-500/40 bg-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-primary-100/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-muted disabled:opacity-70"
					>
						<span aria-hidden="true">«</span>
					</button>
					{#each pageWindow as p, i (p ?? `gap-${i}`)}
						{#if p === null}
							<span class="inline-flex min-w-[35px] items-center justify-center px-2 py-1.5 text-sm font-semibold text-text-muted" aria-hidden="true">…</span>
						{:else if p === page}
							<span
								class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-700 bg-topnav-gradient px-3 py-1.5 text-sm font-semibold text-white"
								aria-current="page"
							>
								{p}
							</span>
						{:else}
							<button
								type="button"
								onclick={() => goToPage(p)}
								aria-label={`Página ${p}`}
								class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-500/40 bg-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-primary-100/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								{p}
							</button>
						{/if}
					{/each}
					<button
						type="button"
						onclick={() => goToPage(page + 1)}
						disabled={page >= totalPages}
						aria-label="Próxima página"
						class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-500/40 bg-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-primary-100/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-muted disabled:opacity-70"
					>
						<span aria-hidden="true">»</span>
					</button>
				</nav>
			{/if}
		{/if}
	{/if}
</section>
