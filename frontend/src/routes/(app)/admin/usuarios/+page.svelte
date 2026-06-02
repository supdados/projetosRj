<script lang="ts">
	/**
	 * Tela "Admin > Usuários" (FASE 4 — CRUD). Lista paginada de usuários via
	 * `GET /api/admin/usuarios` (módulo `$lib/api/adminUsers`), com ações de
	 * editar/excluir. Espelha templates/admin/list_users.html: ID, nome,
	 * login, órgão legado, órgãos vinculados (chips), CPF gov.br, perfil.
	 *
	 * Padrão espelhado de (app)/projetos/+page.svelte: estados loading/erro/
	 * vazio anunciados via aria-live/role=alert, paginação server-side, links
	 * base-aware (`$app/paths`), componentes Card/Badge reusados (não editados).
	 * Mutations (exclusão) usam `client.post` via adminUsers.ts e pedem
	 * confirmação antes de executar.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { fetchAdminUsers, deleteAdminUser } from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import type { AdminUser, AdminUsersPageMeta } from '$lib/types/adminUsers';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';

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

	const total = $derived(meta?.total ?? 0);
	const totalPages = $derived(meta?.total_pages ?? 1);

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
		page = target;
		void load();
	}

	async function confirmDelete(user: AdminUser): Promise<void> {
		const ok = window.confirm(
			`Tem certeza que deseja excluir o usuário "${user.name}"? Esta ação não pode ser desfeita.`
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

	onDestroy(() => inFlight?.abort());

	function editHref(user: AdminUser): string {
		return `${base}/admin/usuarios/${user.id}`;
	}
</script>

<svelte:head>
	<title>Gerenciar Usuários — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="admin-usuarios-title" class="flex flex-col gap-6">
	<header class="flex flex-wrap items-center justify-between gap-3">
		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center gap-3">
				<h1
					id="admin-usuarios-title"
					class="font-heading text-2xl font-bold text-text-primary"
				>
					Gerenciar Usuários
				</h1>
				{#if meta}
					<span
						class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
					>
						{total} usuário{total === 1 ? '' : 's'}
					</span>
				{/if}
			</div>
			<p class="text-sm text-text-secondary">
				Administre acessos, órgãos responsáveis e permissões.
			</p>
		</div>
		<a
			href={`${base}/admin/usuarios/novo`}
			class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 no-underline transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Novo Usuário
		</a>
	</header>

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
			<div class="rounded-lg border border-border-subtle bg-surface px-5 py-12 text-center">
				<h2 class="font-heading text-lg font-semibold text-text-primary">
					Nenhum usuário cadastrado
				</h2>
				<p class="mt-2 text-sm text-text-muted">
					Cadastre o primeiro usuário para iniciar o gerenciamento de acesso.
				</p>
				<a
					href={`${base}/admin/usuarios/novo`}
					class="mt-4 inline-block rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 no-underline transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Criar Primeiro Usuário
				</a>
			</div>
		{:else}
			<Card>
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="w-full border-collapse text-sm">
						<caption class="sr-only">Lista de usuários do sistema</caption>
						<thead>
							<tr class="border-b border-border-subtle text-left text-text-muted">
								<th scope="col" class="px-3 py-2 font-semibold">ID</th>
								<th scope="col" class="px-3 py-2 font-semibold">Nome</th>
								<th scope="col" class="px-3 py-2 font-semibold">Login</th>
								<th scope="col" class="px-3 py-2 font-semibold">Órgão</th>
								<th scope="col" class="px-3 py-2 font-semibold">Órgãos Vinculados</th>
								<th scope="col" class="px-3 py-2 font-semibold">CPF gov.br</th>
								<th scope="col" class="px-3 py-2 font-semibold">Perfil</th>
								<th scope="col" class="px-3 py-2 font-semibold text-right">Ações</th>
							</tr>
						</thead>
						<tbody>
							{#each usuarios as user (user.id)}
								<tr class="border-b border-border-subtle last:border-0">
									<td class="px-3 py-2 text-text-muted">#{user.id}</td>
									<td class="px-3 py-2 font-medium text-text-primary">{user.name}</td>
									<td class="px-3 py-2 text-text-secondary">{user.username}</td>
									<td class="px-3 py-2 text-text-secondary">
										{user.orgao ?? '—'}
									</td>
									<td class="px-3 py-2">
										{#if user.orgaos.length > 0}
											<div class="flex flex-wrap gap-1">
												{#each user.orgaos as orgao (orgao.id)}
													<span
														class="inline-flex items-center rounded-sm border border-border-subtle bg-surface-muted px-2 py-0.5 text-xs text-text-secondary"
														title={orgao.nome}
													>
														{orgao.sigla}
													</span>
												{/each}
											</div>
										{:else}
											<span class="text-text-muted">Sem órgão definido</span>
										{/if}
									</td>
									<td class="px-3 py-2">
										{#if user.cpf_govbr}
											<Badge tone={user.has_govbr_link ? 'success' : 'warning'}>
												{user.has_govbr_link ? 'Vinculado' : 'Pendente'}
											</Badge>
										{:else}
											<span class="text-text-muted">Não vinculado</span>
										{/if}
									</td>
									<td class="px-3 py-2">
										<Badge tone={user.is_admin ? 'primary' : 'neutral'}>
											{user.is_admin ? 'Admin' : 'Padrão'}
										</Badge>
									</td>
									<td class="px-3 py-2">
										<div class="flex items-center justify-end gap-2">
											<a
												href={editHref(user)}
												class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											>
												Editar
											</a>
											<button
												type="button"
												onclick={() => confirmDelete(user)}
												disabled={deletingId === user.id}
												class="rounded-md border border-danger bg-surface px-3 py-1.5 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
											>
												{deletingId === user.id ? 'Excluindo…' : 'Excluir'}
											</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</Card>

			{#if totalPages > 1}
				<nav class="flex items-center justify-center gap-3" aria-label="Paginação de usuários">
					<button
						type="button"
						onclick={() => goToPage(page - 1)}
						disabled={page <= 1}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Anterior
					</button>
					<span class="text-sm text-text-secondary" aria-live="polite">
						Página {page} de {totalPages}
					</span>
					<button
						type="button"
						onclick={() => goToPage(page + 1)}
						disabled={page >= totalPages}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Próxima
					</button>
				</nav>
			{/if}
		{/if}
	{/if}
</section>
