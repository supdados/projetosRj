<script lang="ts">
	/**
	 * Form compartilhado de Usuário (Admin), usado pelas telas de CRIAR
	 * (.../usuarios/novo) e EDITAR (.../usuarios/[id]). Seções em cards no
	 * padrão visual das demais telas (rounded-xl + border-subtle + shadow-sm).
	 *
	 * As regras de campo seguem o backend:
	 *   - `username` imutável na edição (readonly);
	 *   - senha obrigatória ao criar, opcional ao editar;
	 *   - CPF gov.br não editável quando o vínculo está travado
	 *     (`govbr_link_locked`) — nesse caso oferece "Retirar CPF".
	 *
	 * O seletor de órgãos responsáveis é o OrgaoPapelRepeater: uma linha por
	 * vínculo (área × papel) sobre a árvore de seleção com herança descendente.
	 *
	 * A submissão é delegada ao pai via `onSubmit` (que chama o módulo
	 * `adminUsers.ts` com `client.post`). Acessível: labels associadas,
	 * `required`/`aria-invalid`, erro em `role=alert`.
	 */
	import OrgaoPapelRepeater from '$lib/components/OrgaoPapelRepeater.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import { buildOrgaoTree, computeOrgaoCoverage } from '$lib/utils/orgaoTree';
	import { MSG_SO_SUPER_ADMIN_ALTERA_PERFIL } from '$lib/utils/adminGrant';
	import type { AdminOrgaoOption, AdminUserOrgaoVinculo } from '$lib/types/adminUsers';

	type Mode = 'create' | 'edit';

	interface UserFormValues {
		name: string;
		username: string;
		orgao: string;
		cpf_govbr: string;
		password: string;
		is_admin: boolean;
		orgaos: AdminUserOrgaoVinculo[];
	}

	interface Props {
		mode: Mode;
		values: UserFormValues;
		orgaosOptions: AdminOrgaoOption[];
		/** Vínculo Gov.br travado: esconde o campo de CPF editável (edição). */
		govbrLinkLocked: boolean;
		/** Indica se há CPF cadastrado (habilita "Retirar CPF" na edição). */
		hasCpf: boolean;
		/** True enquanto a submissão está em voo (desabilita os controles). */
		saving: boolean;
		/** Mensagem de erro vinda do backend (validação 422 etc.). */
		errorMessage: string;
		/** Só o administrador principal altera `is_admin` (backend devolve 403). */
		canGrantAdmin: boolean;
		cancelHref: string;
		onSubmit: (values: UserFormValues) => void;
		/** Callback do "Retirar CPF" (apenas no modo edição com CPF). */
		onRemoveCpf?: () => void;
		removingCpf?: boolean;
	}

	let {
		mode,
		values = $bindable(),
		orgaosOptions,
		govbrLinkLocked,
		hasCpf,
		saving,
		errorMessage,
		canGrantAdmin,
		cancelHref,
		onSubmit,
		onRemoveCpf,
		removingCpf = false
	}: Props = $props();

	const isCreate = $derived(mode === 'create');
	const submitLabel = $derived(isCreate ? 'Criar Usuário' : 'Salvar Alterações');

	// Foco discreto: só a borda muda de cor (sem ring — inputs de texto sempre
	// casam com :focus-visible, então o anel piscava forte a cada clique).
	const inputClass =
		'h-10 w-full rounded-lg border border-border-subtle bg-surface-muted px-3 text-sm text-text-primary transition-colors duration-fast placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-brand focus:bg-surface focus:outline-none disabled:opacity-60';
	const labelClass = 'text-2xs font-bold uppercase tracking-caps text-text-muted';

	// --- Vínculos de área (repeater área × papel) --------------------------
	// Contador "N vínculos · cobre M unidades": M = vinculados + cobertos pela
	// herança descendente (mesma conta do backend).
	const orgaoTree = $derived.by(() =>
		buildOrgaoTree(orgaosOptions.map((o) => ({ value: o.id, pai_id: o.pai_id })))
	);
	const coveredCount = $derived.by(() => {
		const ids = new Set(values.orgaos.map((v) => v.orgao_id));
		const coverage = computeOrgaoCoverage(orgaoTree, ids);
		return [...coverage.values()].filter((c) => c.state !== 'none').length;
	});

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (saving) return;
		onSubmit(values);
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit} novalidate>
	{#if errorMessage}
		<StateBanner tone="danger" title={errorMessage} />
	{/if}

	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4"
	>
		<legend class="sr-only">Identificação</legend>
		<div class="flex flex-col gap-0.5">
			<h2 class="font-heading text-base font-bold text-text-primary">Identificação</h2>
			<p class="text-xs text-text-muted">Quem é o usuário e como ele entra no sistema.</p>
		</div>

		<div class="grid gap-4 md:grid-cols-2">
			<div class="flex flex-col gap-1.5">
				<label for="user-name" class={labelClass}>
					Nome Completo <span class="text-danger">*</span>
				</label>
				<input
					id="user-name"
					type="text"
					required
					disabled={saving}
					bind:value={values.name}
					placeholder="Ex.: Maria da Silva"
					class={inputClass}
				/>
			</div>

			<div class="flex flex-col gap-1.5">
				<label for="user-username" class={labelClass}>
					Nome de Usuário (Login) <span class="text-danger">*</span>
				</label>
				<input
					id="user-username"
					type="text"
					required={isCreate}
					readonly={!isCreate}
					disabled={saving}
					bind:value={values.username}
					placeholder="Ex.: maria.silva"
					class="{inputClass} {isCreate ? '' : 'cursor-not-allowed text-text-muted hover:border-border-subtle hover:bg-surface-muted'}"
				/>
				{#if !isCreate}
					<p class="text-xs text-text-muted">
						O nome de usuário não pode ser alterado após a criação.
					</p>
				{/if}
			</div>

			<div class="flex flex-col gap-1.5">
				<label for="user-orgao" class={labelClass}>Órgão</label>
				<input
					id="user-orgao"
					type="text"
					disabled={saving}
					bind:value={values.orgao}
					placeholder="Ex.: SEPLAG"
					class={inputClass}
				/>
			</div>

			<!-- CPF gov.br -->
			<div class="flex flex-col gap-1.5">
				<span class={labelClass}>CPF gov.br</span>
				{#if !isCreate && govbrLinkLocked}
					<div class="flex flex-wrap items-center gap-2">
						<span
							class="inline-flex h-10 items-center rounded-lg border border-border-subtle bg-surface-muted px-3 text-sm text-text-secondary"
						>
							<i class="fas fa-lock mr-2 text-xs text-text-muted" aria-hidden="true"></i>
							CPF já cadastrado — vinculado por gov.br
						</span>
						{#if hasCpf && onRemoveCpf}
							<button
								type="button"
								onclick={onRemoveCpf}
								disabled={removingCpf || saving}
								class="inline-flex h-10 items-center rounded-lg border border-danger-soft bg-surface px-3 text-xs font-semibold text-danger transition-colors duration-fast hover:bg-wash-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
							>
								{removingCpf ? 'Retirando…' : 'Retirar CPF'}
							</button>
						{/if}
					</div>
					<p class="text-xs text-text-muted">
						Ao retirar, o CPF e o vínculo gov.br serão apagados.
					</p>
				{:else}
					<div class="flex flex-wrap items-center gap-2">
						<input
							id="user-cpf"
							type="text"
							disabled={saving}
							bind:value={values.cpf_govbr}
							placeholder="Somente números ou com máscara"
							class="{inputClass} min-w-0 flex-1"
						/>
						{#if !isCreate && hasCpf && onRemoveCpf}
							<button
								type="button"
								onclick={onRemoveCpf}
								disabled={removingCpf || saving}
								class="inline-flex h-10 shrink-0 items-center rounded-lg border border-danger-soft bg-surface px-3 text-xs font-semibold text-danger transition-colors duration-fast hover:bg-wash-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
							>
								{removingCpf ? 'Retirando…' : 'Retirar CPF'}
							</button>
						{/if}
					</div>
					<p class="text-xs text-text-muted">
						Opcional. CPF com 11 dígitos habilita o login gov.br.
					</p>
				{/if}
			</div>
		</div>
	</fieldset>

	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4"
	>
		<legend class="sr-only">Credenciais</legend>
		<div class="flex flex-col gap-0.5">
			<h2 class="font-heading text-base font-bold text-text-primary">Credenciais</h2>
			<p class="text-xs text-text-muted">
				{isCreate
					? 'Defina a senha inicial de acesso.'
					: 'Preencha apenas se desejar trocar a senha.'}
			</p>
		</div>

		<div class="flex max-w-md flex-col gap-1.5">
			<label for="user-password" class={labelClass}>
				Senha {#if isCreate}<span class="text-danger">*</span>{/if}
			</label>
			<input
				id="user-password"
				type="password"
				required={isCreate}
				minlength={8}
				disabled={saving}
				autocomplete="new-password"
				bind:value={values.password}
				placeholder={isCreate ? 'Crie uma senha forte' : 'Deixe em branco para manter a atual'}
				class={inputClass}
			/>
			<p class="text-xs text-text-muted">Mínimo de 8 caracteres.</p>
		</div>
	</fieldset>

	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4"
	>
		<legend class="sr-only">Vínculo e Permissões</legend>
		<div class="flex flex-col gap-0.5">
			<h2 class="font-heading text-base font-bold text-text-primary">Vínculo e Permissões</h2>
			<p class="text-xs text-text-muted">
				Áreas que o usuário pode acessar e o papel dele em cada uma. A herança é descendente:
				vincular um órgão-pai dá o mesmo papel em todos os filhos.
			</p>
		</div>

		<!-- Permissão de administrador como cartão de opção destacado. -->
		<label
			class="flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors duration-fast {canGrantAdmin
				? 'cursor-pointer'
				: 'cursor-not-allowed'} {values.is_admin
				? 'border-brand-soft bg-surface-elevated'
				: 'border-border-subtle bg-surface-muted hover:border-border-strong hover:bg-surface-muted'}"
		>
			<input
				type="checkbox"
				disabled={saving || !canGrantAdmin}
				aria-describedby={canGrantAdmin ? undefined : 'user-is-admin-lock'}
				bind:checked={values.is_admin}
				class="mt-0.5 h-4 w-4 rounded border-border-subtle text-brand focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-brand"
			/>
			<span class="flex min-w-0 flex-col gap-0.5">
				<span class="text-sm font-semibold text-text-primary">
					<i class="fas fa-shield-halved mr-1.5 text-brand" aria-hidden="true"></i>
					Administrador
				</span>
				<span class="text-xs text-text-muted">
					Acesso total ao sistema, incluindo gerenciamento de usuários. Administradores sem
					órgãos selecionados visualizam todos.
				</span>
				{#if !canGrantAdmin}
					<span id="user-is-admin-lock" class="text-xs text-text-muted">
						<i class="fas fa-lock mr-1" aria-hidden="true"></i>
						{MSG_SO_SUPER_ADMIN_ALTERA_PERFIL}
					</span>
				{/if}
			</span>
		</label>

		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<span class={labelClass}>Áreas e Papéis</span>
				<span class="text-xs text-text-muted" aria-live="polite">
					{values.orgaos.length}
					{values.orgaos.length === 1 ? 'vínculo' : 'vínculos'} · cobre {coveredCount}
					{coveredCount === 1 ? 'unidade' : 'unidades'}
				</span>
			</div>

			{#if orgaosOptions.length === 0}
				<p class="text-sm text-text-muted">Nenhum órgão ativo disponível.</p>
			{:else}
				<OrgaoPapelRepeater
					options={orgaosOptions}
					value={values.orgaos}
					onChange={(next) => (values.orgaos = next)}
					disabled={saving}
					id="user-orgaos"
				/>
			{/if}
		</div>
	</fieldset>

	<div class="flex items-center justify-end gap-2">
		<a
			href={cancelHref}
			class="inline-flex h-9 items-center rounded-md border border-border-strong bg-surface px-3.5 text-sm font-semibold text-text-secondary no-underline transition-all duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
		>
			Cancelar
		</a>
		<button
			type="submit"
			disabled={saving}
			class="inline-flex h-9 items-center rounded-md bg-brand px-3.5 text-sm font-semibold text-on-brand shadow-token transition-all duration-fast hover:bg-brand-hover hover:shadow-token-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-50 disabled:shadow-none"
		>
			{saving ? 'Salvando…' : submitLabel}
		</button>
	</div>
</form>
