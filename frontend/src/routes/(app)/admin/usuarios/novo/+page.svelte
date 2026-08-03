<script lang="ts">
	/**
	 * Tela "Admin > Usuários > Novo" (FASE 4). Form de CRIAÇÃO de usuário,
	 * consumindo `POST /api/admin/usuarios` via `$lib/api/adminUsers`
	 * (`client.post` injeta X-CSRFToken). As opções de órgãos vêm da árvore de
	 * órgãos (`fetchOrgaoOptionsForUser`), já que não há `usuario/<id>` cujo
	 * detalhe as traga na criação.
	 *
	 * Em sucesso navega para a lista (`/admin/usuarios`). Erros de validação
	 * (422) do backend são exibidos no form (role=alert). Links base-aware.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import {
		fetchOrgaoOptionsForUser,
		peekOrgaoOptionsForUser,
		createAdminUser
	} from '$lib/api/adminUsers';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import { podeConcederAdmin } from '$lib/stores/auth';
	import type {
		AdminOrgaoOption,
		AdminUserCreatePayload,
		AdminUserOrgaoVinculo
	} from '$lib/types/adminUsers';
	import UserForm from '../UserForm.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import AdminUsuarioNovoSkeleton from '$lib/components/skeletons/AdminUsuarioNovoSkeleton.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	// SWR: reabre com as ultimas opcoes de orgao boas (cache de modulo em
	// $lib/api/adminUsers, compartilhado com a tela de edicao) e revalida em
	// background — sem flash de loading ao voltar para a rota. O skeleton so
	// aparece sem cache (1a visita).
	const initialOptions = peekOrgaoOptionsForUser();

	let loadState = $state<LoadState>(initialOptions ? 'ready' : 'loading');
	let loadError = $state<string>('');
	let orgaosOptions = $state<AdminOrgaoOption[]>(initialOptions ?? []);

	let saving = $state<boolean>(false);
	let formError = $state<string>('');

	let values = $state({
		name: '',
		username: '',
		orgao: '',
		cpf_govbr: '',
		password: '',
		is_admin: false,
		orgaos: [] as AdminUserOrgaoVinculo[]
	});

	let inFlight: AbortController | null = null;

	const listHref = `${base}/admin/usuarios`;

	async function loadOptions(): Promise<void> {
		loadError = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		// SWR: com cache mostra as opcoes antigas ja (sem skeleton) e a
		// revalidacao abaixo troca em silencio; sem cache, skeleton.
		const cached = peekOrgaoOptionsForUser();
		if (cached) {
			orgaosOptions = cached;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
		try {
			const result = await fetchOrgaoOptionsForUser(controller.signal);
			if (controller.signal.aborted) return;
			orgaosOptions = result;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar as opções de órgãos.';
			// Revalidacao falhou com dado stale na tela: mantem as opcoes e avisa
			// via flash, em vez de trocar o form inteiro pelo painel de erro.
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
		const payload: AdminUserCreatePayload = {
			username: values.username.trim(),
			name: values.name.trim(),
			password: values.password,
			orgao: values.orgao.trim() || undefined,
			is_admin: values.is_admin,
			cpf_govbr: values.cpf_govbr.trim() || undefined,
			orgaos: values.orgaos
		};
		try {
			await createAdminUser(payload);
			await goto(listHref);
		} catch (err) {
			saving = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = err instanceof Error ? err.message : 'Falha ao criar o usuário.';
		}
	}

	onMount(() => {
		void loadOptions();
		return () => inFlight?.abort();
	});

	onDestroy(() => inFlight?.abort());
</script>

<svelte:head>
	<title>ProjetosRJ — Novo Usuário</title>
</svelte:head>

<section aria-labelledby="novo-usuario-title" class="mx-auto flex w-full max-w-[1220px] flex-col gap-4">
	<!-- Header-card padrão das telas (mesmo chrome de Projetos/Tarefas/Usuários). -->
	<PageHeader compact class="min-h-[3.5rem]" labelId="novo-usuario-title" title="Novo Usuário">
		{#snippet actions()}
			<Button size="sm" variant="secondary" href={listHref}>
				{#snippet icon()}<i class="fas fa-arrow-left" aria-hidden="true"></i>{/snippet}
				Voltar
			</Button>
		{/snippet}
	</PageHeader>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="sr-only">Carregando…</p>
		<AdminUsuarioNovoSkeleton />
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{loadError}</p>
			<button
				type="button"
				onclick={() => loadOptions()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				Tentar novamente
			</button>
		</div>
	{:else}
		<UserForm
			mode="create"
			bind:values
			{orgaosOptions}
			govbrLinkLocked={false}
			hasCpf={false}
			{saving}
			errorMessage={formError}
			canGrantAdmin={$podeConcederAdmin}
			cancelHref={listHref}
			onSubmit={() => submit()}
		/>
	{/if}
</section>
