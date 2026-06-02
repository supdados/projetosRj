<script lang="ts">
	/**
	 * Tela "Admin > Usuários > Editar" (FASE 4). Form de EDIÇÃO, consumindo
	 * `GET /api/admin/usuarios/<id>` (detalhe + opções de órgãos) e
	 * `POST /api/admin/usuarios/<id>` via `$lib/api/adminUsers` (`client.post`).
	 * Suporta também "Retirar CPF" (POST .../remover-cpf).
	 *
	 * Espelha templates/admin/user_form.html: `username` imutável, senha opcional
	 * (só altera se preenchida), CPF não editável quando o vínculo gov.br está
	 * travado. O `id` vem do parâmetro de rota (`[id]`). Erros 404/422/genérico
	 * tratados explicitamente; 401 já redireciona em `client.ts`. Links
	 * base-aware (`$app/paths`).
	 */
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import {
		fetchAdminUserDetail,
		updateAdminUser,
		removeAdminUserCpf
	} from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import type {
		AdminOrgaoOption,
		AdminUser,
		AdminUserUpdatePayload
	} from '$lib/types/adminUsers';
	import UserForm from '../UserForm.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	const userId = $derived(Number($page.params.id));

	let loadState = $state<LoadState>('loading');
	let loadError = $state<string>('');
	let errorKind = $state<'not_found' | 'generic'>('generic');

	let usuario = $state<AdminUser | null>(null);
	let orgaosOptions = $state<AdminOrgaoOption[]>([]);

	let saving = $state<boolean>(false);
	let removingCpf = $state<boolean>(false);
	let formError = $state<string>('');

	let values = $state({
		name: '',
		username: '',
		orgao: '',
		cpf_govbr: '',
		password: '',
		is_admin: false,
		orgaos_responsavel: [] as number[]
	});

	let inFlight: AbortController | null = null;

	const listHref = `${base}/admin/usuarios`;

	/** Preenche o estado do form a partir do usuário carregado. */
	function hydrate(user: AdminUser, orgaoIds: number[]): void {
		usuario = user;
		values = {
			name: user.name ?? '',
			username: user.username ?? '',
			orgao: user.orgao ?? '',
			cpf_govbr: user.cpf_govbr ?? '',
			password: '',
			is_admin: user.is_admin,
			orgaos_responsavel: [...orgaoIds]
		};
	}

	async function load(): Promise<void> {
		loadState = 'loading';
		loadError = '';
		errorKind = 'generic';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const detail = await fetchAdminUserDetail(userId, controller.signal);
			if (controller.signal.aborted) return;
			orgaosOptions = detail.orgaos_options;
			hydrate(detail.usuario, detail.orgao_ids);
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError) {
				if (err.code === 'unauthenticated') return;
				if (err.code === 'not_found') {
					errorKind = 'not_found';
					loadError = 'Usuário não encontrado.';
					loadState = 'error';
					return;
				}
			}
			loadError = err instanceof Error ? err.message : 'Falha ao carregar o usuário.';
			loadState = 'error';
		}
	}

	async function submit(): Promise<void> {
		if (saving) return;
		saving = true;
		formError = '';
		const payload: AdminUserUpdatePayload = {
			name: values.name.trim(),
			orgao: values.orgao.trim() || undefined,
			is_admin: values.is_admin,
			orgaos_responsavel: values.orgaos_responsavel
		};
		// Senha só é enviada quando preenchida (preserva a existente).
		if (values.password) payload.password = values.password;
		// CPF só é editável quando o vínculo gov.br NÃO está travado.
		if (usuario && !usuario.govbr_link_locked) {
			payload.cpf_govbr = values.cpf_govbr.trim();
		}
		try {
			const result = await updateAdminUser(userId, payload);
			// Reidrata com o estado canônico do backend (CPF/órgãos resolvidos).
			hydrate(result.usuario, values.orgaos_responsavel);
			saving = false;
			await goto(listHref);
		} catch (err) {
			saving = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = err instanceof Error ? err.message : 'Falha ao salvar o usuário.';
		}
	}

	async function removeCpf(): Promise<void> {
		if (removingCpf) return;
		const ok = window.confirm(
			'Tem certeza que deseja retirar o CPF e o vínculo gov.br deste usuário? Esta ação não pode ser desfeita.'
		);
		if (!ok) return;
		removingCpf = true;
		formError = '';
		try {
			const result = await removeAdminUserCpf(userId);
			hydrate(result.usuario, values.orgaos_responsavel);
			removingCpf = false;
		} catch (err) {
			removingCpf = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = err instanceof Error ? err.message : 'Falha ao retirar o CPF.';
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	onDestroy(() => inFlight?.abort());
</script>

<svelte:head>
	<title>Editar Usuário — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="editar-usuario-title" class="mx-auto flex w-full max-w-[1220px] flex-col gap-3">
	<nav class="text-sm text-text-muted" aria-label="Trilha de navegação">
		<a href={listHref} class="text-primary-700 no-underline hover:underline">Usuários</a>
		<span aria-hidden="true"> / </span>
		<span>Editar</span>
	</nav>

	<!--
		Cabeçalho "glass" do form (.account-page-header-main): faixa translúcida
		com ícone fa-user-cog arredondado, título grande e subtítulo.
	-->
	<header
		class="flex items-center gap-3 rounded-lg border border-primary-500/30 bg-glass-card px-3.5 py-3 shadow-md"
	>
		<span
			class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary-500/20 bg-glass-card text-lg text-primary-700"
			aria-hidden="true"
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" fill="currentColor" class="h-5 w-5">
				<path d="M224 256A128 128 0 1 0 224 0a128 128 0 1 0 0 256zm-45.7 48C79.8 304 0 383.8 0 482.3C0 498.7 13.3 512 29.7 512l268.6 0c-3.5-7.2-5.5-15.3-5.5-23.8l0-3.6c-8.3-3.6-15.5-9.8-20.3-18.2-9.8 1.9-19.9 3-30.4 3l-14.2 0zm370.7-71.7l-13.9 13.9-13-13c-8.1-8.1-21.3-8.1-29.4 0s-8.1 21.3 0 29.4l13 13-13.9 13.9c-7.1 7.1-9.2 17.8-5.4 27.1s12.9 15.4 23 15.4l19.7 0 0 19.7c0 10.1 6.1 19.2 15.4 23s19.9 1.7 27.1-5.4l13.9-13.9 13 13c8.1 8.1 21.3 8.1 29.4 0s8.1-21.3 0-29.4l-13-13 13.9-13.9c7.1-7.1 9.2-17.8 5.4-27.1s-12.9-15.4-23-15.4l-19.7 0 0-19.7c0-10.1-6.1-19.2-15.4-23s-19.9-1.7-27.1 5.4z"/>
			</svg>
		</span>
		<div class="min-w-0">
			<h1 id="editar-usuario-title" class="truncate font-heading text-3xl font-bold leading-tight text-primary-700">
				{#if usuario}Editar — {usuario.name}{:else}Editar Usuário{/if}
			</h1>
			<p class="text-md font-medium text-text-secondary">
				Atualize os dados, órgãos e permissões deste usuário.
			</p>
		</div>
	</header>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando usuário…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{loadError}</p>
			{#if errorKind === 'not_found'}
				<a
					href={listHref}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar à lista
				</a>
			{:else}
				<button
					type="button"
					onclick={() => load()}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else if usuario}
		<UserForm
			mode="edit"
			bind:values
			{orgaosOptions}
			govbrLinkLocked={usuario.govbr_link_locked}
			hasCpf={Boolean(usuario.cpf_govbr)}
			{saving}
			errorMessage={formError}
			cancelHref={listHref}
			onSubmit={() => submit()}
			onRemoveCpf={() => removeCpf()}
			{removingCpf}
		/>
	{/if}
</section>
