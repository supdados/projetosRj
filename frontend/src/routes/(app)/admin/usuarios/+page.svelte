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

<section aria-labelledby="admin-usuarios-title" class="mx-auto flex w-full max-w-[1400px] flex-col gap-3">
	<!--
		Cabeçalho "glass" do original (.admin-users-header): faixa com gradiente
		translúcido, borda azul suave e sombra; ícone arredondado à esquerda,
		título/subtítulo ao centro e botão "Novo Usuário" (gradiente) à direita.
	-->
	<header
		class="flex items-center justify-between gap-4 rounded-lg border border-primary-500/30 bg-glass-card px-4 py-3.5 shadow-md"
	>
		<div class="flex min-w-0 items-center gap-3">
			<span
				class="inline-flex h-[43px] w-[43px] shrink-0 items-center justify-center rounded-[11px] border border-primary-500/20 bg-glass-card text-lg text-primary-700"
				aria-hidden="true"
			>
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" fill="currentColor" class="h-5 w-5">
					<path d="M144 0a80 80 0 1 1 0 160A80 80 0 1 1 144 0M512 0a80 80 0 1 1 0 160A80 80 0 1 1 512 0M0 298.7C0 239.8 47.8 192 106.7 192l42.7 0c15.9 0 31 3.5 44.6 9.7c-1.3 7.2-1.9 14.7-1.9 22.3c0 38.2 16.8 72.5 43.3 96c-.2 0-.4 0-.7 0L21.3 320C9.6 320 0 310.4 0 298.7M405.3 320c-.2 0-.4 0-.7 0c26.6-23.5 43.3-57.8 43.3-96c0-7.6-.7-15-1.9-22.3c13.6-6.3 28.7-9.7 44.6-9.7l42.7 0C592.2 192 640 239.8 640 298.7c0 11.8-9.6 21.3-21.3 21.3l-213.3 0zM224 224a96 96 0 1 1 192 0 96 96 0 1 1 -192 0M128 485.3C128 411.7 187.7 352 261.3 352l117.3 0C452.3 352 512 411.7 512 485.3c0 14.7-11.9 26.7-26.7 26.7l-330.7 0c-14.7 0-26.7-11.9-26.7-26.7z"/>
				</svg>
			</span>
			<div class="min-w-0">
				<h1
					id="admin-usuarios-title"
					class="font-heading text-2xl font-bold leading-tight text-primary-700"
				>
					Gerenciar Usuários
				</h1>
				<p class="text-md font-medium text-text-secondary">
					Administre acessos, órgãos responsáveis e permissões.
				</p>
			</div>
		</div>
		<a
			href={`${base}/admin/usuarios/novo`}
			class="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-[9px] border border-primary-700 bg-topnav-gradient px-3.5 py-2 text-md font-semibold text-white no-underline shadow-md transition-all duration-slow ease-[cubic-bezier(0.4,0,0.2,1)] hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:translate-y-0"
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" fill="currentColor" class="h-4 w-4">
				<path d="M96 128a128 128 0 1 1 256 0A128 128 0 1 1 96 128zM0 482.3C0 383.8 79.8 304 178.3 304l91.4 0C368.2 304 448 383.8 448 482.3c0 16.4-13.3 29.7-29.7 29.7L29.7 512C13.3 512 0 498.7 0 482.3zM504 312l0-64-64 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l64 0 0-64c0-13.3 10.7-24 24-24s24 10.7 24 24l0 64 64 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-64 0 0 64c0 13.3-10.7 24-24 24s-24-10.7-24-24z"/>
			</svg>
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
			<!-- Estado vazio (.admin-users-empty-state): cartão tracejado centralizado. -->
			<div
				class="mt-1 rounded-[13px] border border-dashed border-primary-500/40 bg-surface-muted px-4 py-8 text-center"
			>
				<span
					class="mx-auto mb-2.5 inline-flex h-[52px] w-[52px] items-center justify-center rounded-[14px] border border-primary-500/25 bg-primary-100 text-primary-700"
					aria-hidden="true"
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" fill="currentColor" class="h-6 w-6">
						<path d="M96 128a128 128 0 1 1 256 0A128 128 0 1 1 96 128zM0 482.3C0 383.8 79.8 304 178.3 304l91.4 0C368.2 304 448 383.8 448 482.3c0 16.4-13.3 29.7-29.7 29.7L29.7 512C13.3 512 0 498.7 0 482.3zM504 312l0-64-64 0c-13.3 0-24-10.7-24-24s10.7-24 24-24l64 0 0-64c0-13.3 10.7-24 24-24s24 10.7 24 24l0 64 64 0c13.3 0 24 10.7 24 24s-10.7 24-24 24l-64 0 0 64c0 13.3-10.7 24-24 24s-24-10.7-24-24z"/>
					</svg>
				</span>
				<h2 class="mb-1.5 font-heading text-xl font-bold text-primary-700">
					Nenhum usuário cadastrado
				</h2>
				<p class="mb-3.5 text-md text-text-secondary">
					Cadastre o primeiro usuário para iniciar o gerenciamento de acesso.
				</p>
				<a
					href={`${base}/admin/usuarios/novo`}
					class="inline-flex items-center gap-2 rounded-[9px] border border-primary-700 bg-topnav-gradient px-3.5 py-2 text-md font-semibold text-white no-underline shadow-md transition-all duration-slow ease-[cubic-bezier(0.4,0,0.2,1)] hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:translate-y-0"
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" fill="currentColor" class="h-4 w-4">
						<path d="M256 80c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 144L48 224c-17.7 0-32 14.3-32 32s14.3 32 32 32l144 0 0 144c0 17.7 14.3 32 32 32s32-14.3 32-32l0-144 144 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l-144 0 0-144z"/>
					</svg>
					Criar Primeiro Usuário
				</a>
			</div>
		{:else}
			<!--
				Linha de metadados (.admin-users-meta-row): chips arredondados com
				contagem total e paginação atual, espelhando o original.
			-->
			<div class="flex flex-wrap items-center gap-1.5">
				<span
					class="inline-flex items-center gap-1 rounded-full border border-primary-500/50 bg-surface px-2.5 py-1 text-xs font-semibold text-text-secondary"
				>
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" fill="currentColor" class="h-3 w-3">
						<path d="M144 0a80 80 0 1 1 0 160A80 80 0 1 1 144 0M512 0a80 80 0 1 1 0 160A80 80 0 1 1 512 0M0 298.7C0 239.8 47.8 192 106.7 192l42.7 0c15.9 0 31 3.5 44.6 9.7c-1.3 7.2-1.9 14.7-1.9 22.3c0 38.2 16.8 72.5 43.3 96c-.2 0-.4 0-.7 0L21.3 320C9.6 320 0 310.4 0 298.7M405.3 320c-.2 0-.4 0-.7 0c26.6-23.5 43.3-57.8 43.3-96c0-7.6-.7-15-1.9-22.3c13.6-6.3 28.7-9.7 44.6-9.7l42.7 0C592.2 192 640 239.8 640 298.7c0 11.8-9.6 21.3-21.3 21.3l-213.3 0zM224 224a96 96 0 1 1 192 0 96 96 0 1 1 -192 0M128 485.3C128 411.7 187.7 352 261.3 352l117.3 0C452.3 352 512 411.7 512 485.3c0 14.7-11.9 26.7-26.7 26.7l-330.7 0c-14.7 0-26.7-11.9-26.7-26.7z"/>
					</svg>
					{total} usuário{total === 1 ? '' : 's'}
				</span>
				<span
					class="inline-flex items-center gap-1 rounded-full border border-primary-500/50 bg-surface px-2.5 py-1 text-xs font-semibold text-text-secondary"
				>
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
								<tr class="border-t border-border-subtle transition-colors duration-fast hover:bg-primary-100/40">
									<td class="px-3 py-2.5 align-middle">
										<span
											class="inline-flex items-center rounded-full border border-primary-500/40 bg-surface px-1.5 py-0.5 text-xs font-bold text-text-secondary"
										>
											#{user.id}
										</span>
									</td>
									<td class="px-3 py-2.5 align-middle">
										<span class="font-semibold text-text-primary">{user.name}</span>
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
											<Badge tone={user.has_govbr_link ? 'success' : 'warning'}>
												{user.has_govbr_link ? 'Vinculado' : 'Pendente'}
											</Badge>
										{:else}
											<span class="text-sm italic text-text-muted">Não vinculado</span>
										{/if}
									</td>
									<td class="px-3 py-2.5 text-center align-middle">
										{#if user.is_admin}
											<span
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-full border border-success/40 bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-success"
											>
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" fill="currentColor" class="h-3 w-3">
													<path d="M224 0c-17.7 0-32 14.3-32 32l0 19.2C119 66 64 130.6 64 208l0 25.4c0 45.4-15.5 89.5-43.8 124.9L5.3 377c-5.8 7.2-6.9 17.1-2.9 25.4S14.8 416 24 416l400 0c9.2 0 17.6-5.3 21.6-13.6s2.9-18.2-2.9-25.4l-14.9-18.6C399.5 322.9 384 278.8 384 233.4l0-25.4c0-77.4-55-142-128-156.8L256 32c0-17.7-14.3-32-32-32zm45.3 493.3c12-12 18.7-28.3 18.7-45.3l-64 0-64 0c0 17 6.7 33.3 18.7 45.3s28.3 18.7 45.3 18.7s33.3-6.7 45.3-18.7z"/>
												</svg>
												Admin
											</span>
										{:else}
											<span
												class="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-bold leading-tight text-text-secondary"
											>
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" fill="currentColor" class="h-3 w-3">
													<path d="M224 256A128 128 0 1 0 224 0a128 128 0 1 0 0 256zm-45.7 48C79.8 304 0 383.8 0 482.3C0 498.7 13.3 512 29.7 512l388.6 0c16.4 0 29.7-13.3 29.7-29.7C448 383.8 368.2 304 269.7 304l-91.4 0z"/>
												</svg>
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
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="currentColor" class="h-3.5 w-3.5">
													<path d="M410.3 231l11.3-11.3-33.9-33.9-62.1-62.1L301.5 100l-11.3 11.3-22.6 22.6L58.6 343.1c-10.4 10.4-18 23.3-22.2 37.4L1 499.1c-2.3 7.6-.2 15.9 5.4 21.5s13.9 7.7 21.5 5.4l118.7-35.6c14.1-4.2 27-11.8 37.4-22.2L411.7 256.3 410.3 231zM160 399.4l-9.1 22.7c-4 3.1-8.5 5.4-13.3 6.9L59.4 452l23-78.1c1.4-4.9 3.8-9.4 6.9-13.3l22.7-9.1 0 32c0 8.8 7.2 16 16 16l32 0zM362.7 18.7L348.3 33.2 325.7 55.8 314.3 67.1l33.9 33.9 62.1 62.1 33.9 33.9 11.3-11.3 22.6-22.6 14.5-14.5c25-25 25-65.5 0-90.5L453.3 18.7c-25-25-65.5-25-90.5 0zm-47.4 168l-144 144c-6.2 6.2-16.4 6.2-22.6 0s-6.2-16.4 0-22.6l144-144c6.2-6.2 16.4-6.2 22.6 0s6.2 16.4 0 22.6z"/>
												</svg>
											</a>
											<button
												type="button"
												onclick={() => confirmDelete(user)}
												disabled={deletingId === user.id}
												title="Excluir Usuário"
												aria-label="Excluir usuário {user.name}"
												class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-danger/30 bg-surface-muted text-danger transition-colors duration-fast hover:border-danger/50 hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-50"
											>
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" fill="currentColor" class="h-3.5 w-3.5">
													<path d="M135.2 17.7L128 32 32 32C14.3 32 0 46.3 0 64S14.3 96 32 96l384 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l-96 0-7.2-14.3C307.4 6.8 296.3 0 284.2 0L163.8 0c-12.1 0-23.2 6.8-28.6 17.7zM416 128L32 128 53.2 467c1.6 25.3 22.6 45 47.9 45l245.8 0c25.3 0 46.3-19.7 47.9-45L416 128z"/>
												</svg>
											</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			{#if totalPages > 1}
				<!-- Paginação (.admin-users-pagination): chips com estado ativo em gradiente. -->
				<nav class="mt-1 flex items-center justify-center gap-1.5" aria-label="Paginação de usuários">
					<button
						type="button"
						onclick={() => goToPage(page - 1)}
						disabled={page <= 1}
						aria-label="Página anterior"
						class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-500/40 bg-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-primary-100/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:bg-surface-muted disabled:text-text-muted disabled:opacity-70"
					>
						<span aria-hidden="true">«</span>
					</button>
					<span
						class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-700 bg-topnav-gradient px-3 py-1.5 text-sm font-semibold text-white"
						aria-current="page"
						aria-live="polite"
					>
						{page}
					</span>
					<span class="px-1 text-sm font-semibold text-text-muted">de {totalPages}</span>
					<button
						type="button"
						onclick={() => goToPage(page + 1)}
						disabled={page >= totalPages}
						aria-label="Próxima página"
						class="inline-flex min-w-[35px] items-center justify-center rounded-md border border-primary-500/40 bg-surface px-3 py-1.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-primary-100/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:bg-surface-muted disabled:text-text-muted disabled:opacity-70"
					>
						<span aria-hidden="true">»</span>
					</button>
				</nav>
			{/if}
		{/if}
	{/if}
</section>
