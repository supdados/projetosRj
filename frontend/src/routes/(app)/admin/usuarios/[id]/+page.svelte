<script lang="ts">
	/**
	 * Tela "Admin > Usuários > Editar". Form de EDIÇÃO, consumindo
	 * `GET /api/admin/usuarios/<id>` (detalhe + opções de órgãos) e
	 * `POST /api/admin/usuarios/<id>` via `$lib/api/adminUsers` (`client.post`).
	 * Suporta também "Retirar CPF" (POST .../remover-cpf).
	 *
	 * Regras: `username` imutável, senha opcional
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
		peekAdminUserDetail,
		updateAdminUser,
		removeAdminUserCpf
	} from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type {
		AdminOrgaoOption,
		AdminUser,
		AdminUserUpdatePayload
	} from '$lib/types/adminUsers';
	import UserForm from '../UserForm.svelte';
	import { buildOrgaoTree, minimizeOrgaoSelection } from '$lib/utils/orgaoTree';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import AdminUsuarioEditSkeleton from '$lib/components/skeletons/AdminUsuarioEditSkeleton.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	const userId = $derived(Number($page.params.id));

	// SWR: reabre com o ultimo detalhe bom deste id (cache de modulo em
	// $lib/api/adminUsers) e revalida em background — sem flash de loading ao
	// voltar para a rota. O skeleton so aparece sem cache (1a visita do id).
	const initialDetail = peekAdminUserDetail(Number($page.params.id));

	let loadState = $state<LoadState>(initialDetail ? 'ready' : 'loading');
	let loadError = $state<string>('');
	let errorKind = $state<'not_found' | 'generic'>('generic');

	let usuario = $state<AdminUser | null>(initialDetail?.usuario ?? null);
	let orgaosOptions = $state<AdminOrgaoOption[]>(initialDetail?.orgaos_options ?? []);

	let saving = $state<boolean>(false);
	let removingCpf = $state<boolean>(false);
	let formError = $state<string>('');

	/**
	 * Normaliza vínculos legados redundantes (pai+filho salvos pela grade
	 * antiga): mantém só os ancestrais — mesma cobertura, payload mínimo.
	 * Só chega ao backend se o usuário submeter o form.
	 */
	function minimizeIds(orgaoIds: number[], options: AdminOrgaoOption[]): number[] {
		const tree = buildOrgaoTree(options.map((o) => ({ value: o.id, pai_id: o.pai_id })));
		return minimizeOrgaoSelection(tree, orgaoIds);
	}

	/** Monta os valores do form a partir do usuário carregado (função pura). */
	function valuesFromUser(user: AdminUser, orgaoIds: number[]) {
		return {
			name: user.name ?? '',
			username: user.username ?? '',
			orgao: user.orgao ?? '',
			cpf_govbr: user.cpf_govbr ?? '',
			password: '',
			is_admin: user.is_admin,
			orgaos_responsavel: [...orgaoIds]
		};
	}

	const initialValues = initialDetail
		? valuesFromUser(
				initialDetail.usuario,
				minimizeIds(initialDetail.orgao_ids, initialDetail.orgaos_options)
			)
		: {
				name: '',
				username: '',
				orgao: '',
				cpf_govbr: '',
				password: '',
				is_admin: false,
				orgaos_responsavel: [] as number[]
			};
	let values = $state(initialValues);

	let inFlight: AbortController | null = null;

	const listHref = `${base}/admin/usuarios`;

	function hydrate(user: AdminUser, orgaoIds: number[]): void {
		usuario = user;
		values = valuesFromUser(user, minimizeIds(orgaoIds, orgaosOptions));
	}

	async function load(): Promise<void> {
		loadError = '';
		errorKind = 'generic';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		// SWR: com cache deste id mostra o dado antigo ja (sem skeleton) e a
		// revalidacao abaixo troca em silencio; sem cache, skeleton.
		const cached = peekAdminUserDetail(userId);
		if (cached) {
			orgaosOptions = cached.orgaos_options;
			hydrate(cached.usuario, cached.orgao_ids);
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
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
			const message = err instanceof Error ? err.message : 'Falha ao carregar o usuário.';
			// Revalidacao falhou com dado stale na tela: mantem o dado e avisa via
			// flash, em vez de trocar o form inteiro pelo painel de erro.
			if (cached) {
				flash.danger(message);
				return;
			}
			loadError = message;
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

<section aria-labelledby="editar-usuario-title" class="mx-auto flex w-full max-w-[1220px] flex-col gap-4">
	<!-- Header-card padrão das telas (mesmo chrome de Projetos/Tarefas/Usuários). -->
	<PageHeader compact class="min-h-[3.5rem]" labelId="editar-usuario-title">
		{#snippet titleContent()}
			<span class="align-middle">
				{#if usuario}Editar — {usuario.name}{:else}Editar Usuário{/if}
			</span>
		{/snippet}
		{#snippet actions()}
			<Button size="sm" variant="secondary" href={listHref}>
				{#snippet icon()}<i class="fas fa-arrow-left" aria-hidden="true"></i>{/snippet}
				Voltar
			</Button>
		{/snippet}
	</PageHeader>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="sr-only">Carregando usuário…</p>
		<AdminUsuarioEditSkeleton />
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
