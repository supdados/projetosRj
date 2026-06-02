<script lang="ts">
	/**
	 * Form compartilhado de Usuário (Admin), usado pelas telas de CRIAR
	 * (.../usuarios/novo) e EDITAR (.../usuarios/[id]). Espelha
	 * templates/admin/user_form.html: identificação, credenciais, vínculo de
	 * órgãos (checkboxes com indentação por profundidade) e flag de admin.
	 *
	 * É um componente local da própria tela (não compartilhado entre tarefas).
	 * As regras de campo seguem o backend:
	 *   - `username` imutável na edição (readonly);
	 *   - senha obrigatória ao criar, opcional ao editar;
	 *   - CPF gov.br não editável quando o vínculo está travado
	 *     (`govbr_link_locked`) — nesse caso oferece "Retirar CPF".
	 *
	 * A submissão é delegada ao pai via `onSubmit` (que chama o módulo
	 * `adminUsers.ts` com `client.post`). Acessível: labels associadas,
	 * `required`/`aria-invalid`, erro em `role=alert`.
	 */
	import type { AdminOrgaoOption } from '$lib/types/adminUsers';

	type Mode = 'create' | 'edit';

	interface UserFormValues {
		name: string;
		username: string;
		orgao: string;
		cpf_govbr: string;
		password: string;
		is_admin: boolean;
		orgaos_responsavel: number[];
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
		cancelHref,
		onSubmit,
		onRemoveCpf,
		removingCpf = false
	}: Props = $props();

	const isCreate = $derived(mode === 'create');
	const submitLabel = $derived(isCreate ? 'Criar Usuário' : 'Salvar Alterações');

	function toggleOrgao(orgaoId: number, checked: boolean): void {
		if (checked) {
			if (!values.orgaos_responsavel.includes(orgaoId)) {
				values.orgaos_responsavel = [...values.orgaos_responsavel, orgaoId];
			}
		} else {
			values.orgaos_responsavel = values.orgaos_responsavel.filter((id) => id !== orgaoId);
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (saving) return;
		onSubmit(values);
	}
</script>

<form class="flex flex-col gap-6" onsubmit={handleSubmit} novalidate>
	{#if errorMessage}
		<div role="alert" class="rounded-lg border border-danger bg-surface px-5 py-3 text-sm text-text-primary">
			{errorMessage}
		</div>
	{/if}

	<!-- Identificação -->
	<fieldset class="flex flex-col gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4">
		<legend class="px-1 text-sm font-semibold uppercase tracking-wide text-text-muted">
			Identificação
		</legend>

		<div class="flex flex-col gap-1">
			<label for="user-name" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Nome Completo <span class="text-danger">*</span>
			</label>
			<input
				id="user-name"
				type="text"
				required
				disabled={saving}
				bind:value={values.name}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			/>
		</div>

		<div class="flex flex-col gap-1">
			<label
				for="user-username"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Nome de Usuário (Login) <span class="text-danger">*</span>
			</label>
			<input
				id="user-username"
				type="text"
				required={isCreate}
				readonly={!isCreate}
				disabled={saving}
				bind:value={values.username}
				class="rounded-md border border-border-subtle px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60 {isCreate
					? 'bg-surface'
					: 'cursor-not-allowed bg-surface-muted text-text-muted'}"
			/>
			{#if !isCreate}
				<p class="text-xs text-text-muted">
					O nome de usuário não pode ser alterado após a criação.
				</p>
			{/if}
		</div>

		<div class="flex flex-col gap-1">
			<label for="user-orgao" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Órgão
			</label>
			<input
				id="user-orgao"
				type="text"
				disabled={saving}
				bind:value={values.orgao}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			/>
		</div>

		<!-- CPF gov.br -->
		<div class="flex flex-col gap-1">
			<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">CPF gov.br</span>
			{#if !isCreate && govbrLinkLocked}
				<div class="flex flex-wrap items-center gap-3">
					<span class="rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-secondary">
						CPF já cadastrado — Vinculado por gov.br
					</span>
					{#if hasCpf && onRemoveCpf}
						<button
							type="button"
							onclick={onRemoveCpf}
							disabled={removingCpf || saving}
							class="rounded-md border border-danger bg-surface px-3 py-2 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
						>
							{removingCpf ? 'Retirando…' : 'Retirar CPF'}
						</button>
					{/if}
				</div>
				<p class="text-xs text-text-muted">
					Ao retirar, o CPF e o vínculo gov.br serão apagados.
				</p>
			{:else}
				<div class="flex flex-wrap items-center gap-3">
					<input
						id="user-cpf"
						type="text"
						disabled={saving}
						bind:value={values.cpf_govbr}
						placeholder="Somente números ou com máscara"
						class="flex-1 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					/>
					{#if !isCreate && hasCpf && onRemoveCpf}
						<button
							type="button"
							onclick={onRemoveCpf}
							disabled={removingCpf || saving}
							class="rounded-md border border-danger bg-surface px-3 py-2 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
						>
							{removingCpf ? 'Retirando…' : 'Retirar CPF'}
						</button>
					{/if}
				</div>
				<p class="text-xs text-text-muted">
					Campo opcional. Use CPF com 11 dígitos para habilitar login gov.br.
				</p>
			{/if}
		</div>
	</fieldset>

	<!-- Credenciais -->
	<fieldset class="flex flex-col gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4">
		<legend class="px-1 text-sm font-semibold uppercase tracking-wide text-text-muted">
			Credenciais
		</legend>
		<div class="flex flex-col gap-1">
			<label for="user-password" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
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
				placeholder={isCreate
					? 'Crie uma senha forte'
					: 'Deixe em branco para não alterar a senha existente'}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			/>
			<p class="text-xs text-text-muted">
				Mínimo de 8 caracteres.{#if !isCreate}
					Preencha apenas se desejar alterar.{/if}
			</p>
		</div>
	</fieldset>

	<!-- Vínculo e Permissões -->
	<fieldset class="flex flex-col gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4">
		<legend class="px-1 text-sm font-semibold uppercase tracking-wide text-text-muted">
			Vínculo e Permissões
		</legend>

		<div class="flex flex-col gap-2">
			<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Órgãos Responsáveis
			</span>
			<p class="text-xs text-text-muted">
				Selecione os órgãos que o usuário pode acessar (herança descendente: órgão-pai dá
				acesso aos filhos). Administradores sem órgãos selecionados visualizam todos.
			</p>
			{#if orgaosOptions.length === 0}
				<p class="text-sm text-text-muted">Nenhum órgão ativo disponível.</p>
			{:else}
				<ul class="flex flex-col gap-1" aria-label="Órgãos responsáveis">
					{#each orgaosOptions as orgao (orgao.id)}
						<li style={`padding-left: ${(orgao.depth - 1) * 16}px;`}>
							<label class="flex items-center gap-2 text-sm text-text-primary">
								<input
									type="checkbox"
									disabled={saving}
									checked={values.orgaos_responsavel.includes(orgao.id)}
									onchange={(e) => toggleOrgao(orgao.id, e.currentTarget.checked)}
									class="h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-2 focus:ring-primary-500"
								/>
								<span>
									{orgao.sigla}{#if orgao.nome && orgao.nome !== orgao.sigla}
										<span class="text-text-secondary"> — {orgao.nome}</span>{/if}
								</span>
							</label>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<label class="flex items-center gap-2 text-sm text-text-primary">
			<input
				type="checkbox"
				disabled={saving}
				bind:checked={values.is_admin}
				class="h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-2 focus:ring-primary-500"
			/>
			<span>Conceder permissões de administrador</span>
		</label>
		<p class="text-xs text-text-muted">
			Permite acesso total ao sistema, incluindo gerenciamento de usuários.
		</p>
	</fieldset>

	<div class="flex items-center justify-end gap-3">
		<a
			href={cancelHref}
			class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Cancelar
		</a>
		<button
			type="submit"
			disabled={saving}
			class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
		>
			{saving ? 'Salvando…' : submitLabel}
		</button>
	</div>
</form>
