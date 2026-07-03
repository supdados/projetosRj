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
	 * O seletor de órgãos responsáveis tem busca (sem acentos), chips removíveis
	 * dos selecionados e grade rolável em até 3 colunas — filhos são marcados
	 * com "↳"; a busca inclui os ancestrais dos resultados para dar contexto.
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

	// Foco discreto: só a borda muda de cor (sem ring — inputs de texto sempre
	// casam com :focus-visible, então o anel piscava forte a cada clique).
	const inputClass =
		'h-10 w-full rounded-lg border border-border-subtle bg-surface-muted px-3 text-sm text-text-primary transition-colors duration-fast placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-primary-500 focus:bg-surface focus:outline-none disabled:opacity-60';
	const labelClass = 'text-2xs font-bold uppercase tracking-caps text-text-muted';

	// --- Seletor de órgãos responsáveis ------------------------------------

	let orgaoSearch = $state<string>('');

	/** Normaliza para busca sem acentos e sem caixa. */
	function normalize(value: string): string {
		return value
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '')
			.toLowerCase();
	}

	/**
	 * Órgãos visíveis na lista: sem busca, a árvore inteira; com busca, os que
	 * batem com sigla/nome MAIS seus ancestrais (para a indentação fazer
	 * sentido). Os ancestrais são reconstruídos pela pilha de profundidade,
	 * já que a lista chega achatada em pré-ordem.
	 */
	const visibleOrgaos = $derived.by(() => {
		const query = normalize(orgaoSearch.trim());
		if (!query) return orgaosOptions;
		const keep = new Set<number>();
		const ancestors: AdminOrgaoOption[] = [];
		for (const orgao of orgaosOptions) {
			ancestors[orgao.depth - 1] = orgao;
			ancestors.length = orgao.depth;
			if (normalize(`${orgao.sigla} ${orgao.nome}`).includes(query)) {
				for (const ancestor of ancestors) keep.add(ancestor.id);
			}
		}
		return orgaosOptions.filter((orgao) => keep.has(orgao.id));
	});

	const selectedOrgaos = $derived(
		orgaosOptions.filter((orgao) => values.orgaos_responsavel.includes(orgao.id))
	);

	function toggleOrgao(orgaoId: number, checked: boolean): void {
		if (checked) {
			if (!values.orgaos_responsavel.includes(orgaoId)) {
				values.orgaos_responsavel = [...values.orgaos_responsavel, orgaoId];
			}
		} else {
			values.orgaos_responsavel = values.orgaos_responsavel.filter((id) => id !== orgaoId);
		}
	}

	function clearOrgaos(): void {
		values.orgaos_responsavel = [];
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (saving) return;
		onSubmit(values);
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit} novalidate>
	{#if errorMessage}
		<div
			role="alert"
			class="rounded-lg border border-danger bg-danger/10 px-4 py-3 text-sm font-medium text-danger"
		>
			{errorMessage}
		</div>
	{/if}

	<!-- Identificação -->
	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4 shadow-sm"
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
								class="inline-flex h-10 items-center rounded-lg border border-danger/40 bg-surface px-3 text-xs font-semibold text-danger transition-colors duration-fast hover:bg-danger/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
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
								class="inline-flex h-10 shrink-0 items-center rounded-lg border border-danger/40 bg-surface px-3 text-xs font-semibold text-danger transition-colors duration-fast hover:bg-danger/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
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

	<!-- Credenciais -->
	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4 shadow-sm"
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

	<!-- Vínculo e Permissões -->
	<fieldset
		class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4 shadow-sm"
	>
		<legend class="sr-only">Vínculo e Permissões</legend>
		<div class="flex flex-col gap-0.5">
			<h2 class="font-heading text-base font-bold text-text-primary">Vínculo e Permissões</h2>
			<p class="text-xs text-text-muted">
				Órgãos que o usuário pode acessar. A herança é descendente: marcar um órgão-pai dá
				acesso a todos os filhos.
			</p>
		</div>

		<!-- Permissão de administrador como cartão de opção destacado. -->
		<label
			class="flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition-colors duration-fast {values.is_admin
				? 'border-primary-500/50 bg-primary-100/40'
				: 'border-border-subtle bg-surface-muted/40 hover:border-border-strong hover:bg-surface-muted'}"
		>
			<input
				type="checkbox"
				disabled={saving}
				bind:checked={values.is_admin}
				class="mt-0.5 h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-primary-500"
			/>
			<span class="flex min-w-0 flex-col gap-0.5">
				<span class="text-sm font-semibold text-text-primary">
					<i class="fas fa-shield-halved mr-1.5 text-primary-700" aria-hidden="true"></i>
					Administrador
				</span>
				<span class="text-xs text-text-muted">
					Acesso total ao sistema, incluindo gerenciamento de usuários. Administradores sem
					órgãos selecionados visualizam todos.
				</span>
			</span>
		</label>

		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<span class={labelClass}>Órgãos Responsáveis</span>
				<span class="text-xs text-text-muted" aria-live="polite">
					{selectedOrgaos.length} de {orgaosOptions.length} selecionado{selectedOrgaos.length ===
					1
						? ''
						: 's'}
				</span>
			</div>

			{#if orgaosOptions.length === 0}
				<p class="text-sm text-text-muted">Nenhum órgão ativo disponível.</p>
			{:else}
				<div class="overflow-hidden rounded-lg border border-border-subtle">
					<!-- Busca do seletor -->
					<div class="relative border-b border-border-subtle bg-surface-muted/40">
						<i
							class="fas fa-search pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted"
							aria-hidden="true"
						></i>
						<input
							type="search"
							bind:value={orgaoSearch}
							disabled={saving}
							placeholder="Buscar órgão por sigla ou nome…"
							aria-label="Buscar órgão por sigla ou nome"
							autocomplete="off"
							class="h-10 w-full border-none bg-transparent pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
						/>
					</div>

					<!-- Chips dos selecionados: visão imediata + remoção em 1 clique. -->
					{#if selectedOrgaos.length > 0}
						<div
							class="flex flex-wrap items-center gap-1.5 border-b border-border-subtle bg-surface-muted/40 px-3 py-2"
						>
							{#each selectedOrgaos as orgao (orgao.id)}
								<span
									class="inline-flex items-center gap-1 rounded-full border border-primary-500/30 bg-primary-100 py-0.5 pl-2.5 pr-1 text-xs font-semibold text-primary-700"
								>
									{orgao.sigla}
									<button
										type="button"
										onclick={() => toggleOrgao(orgao.id, false)}
										disabled={saving}
										aria-label={`Remover ${orgao.sigla}`}
										class="inline-flex h-4 w-4 items-center justify-center rounded-full text-primary-700/70 transition-colors duration-fast hover:bg-primary-500/20 hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<i class="fas fa-times text-[10px]" aria-hidden="true"></i>
									</button>
								</span>
							{/each}
							<button
								type="button"
								onclick={clearOrgaos}
								disabled={saving}
								class="ml-1 text-xs font-semibold text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Limpar tudo
							</button>
						</div>
					{/if}

					<!-- Grade de órgãos (3 colunas no desktop). Filhos ganham o marcador
					     "↳" no lugar da indentação da árvore, que não sobrevive à grade. -->
					<ul
						class="thin-scroll grid max-h-80 grid-cols-1 gap-1 overflow-y-auto p-2 sm:grid-cols-2 lg:grid-cols-3"
						aria-label="Órgãos responsáveis"
					>
						{#each visibleOrgaos as orgao (orgao.id)}
							<li class="min-w-0">
								<label
									title={orgao.nome && orgao.nome !== orgao.sigla
										? `${orgao.sigla} — ${orgao.nome}`
										: orgao.sigla}
									class="flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm text-text-primary transition-colors duration-fast {values.orgaos_responsavel.includes(
										orgao.id
									)
										? 'border-primary-500/40 bg-primary-100/40'
										: 'border-transparent hover:bg-surface-muted'}"
								>
									<input
										type="checkbox"
										disabled={saving}
										checked={values.orgaos_responsavel.includes(orgao.id)}
										onchange={(e) => toggleOrgao(orgao.id, e.currentTarget.checked)}
										class="h-4 w-4 shrink-0 rounded border-border-subtle text-primary-700 focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-primary-500"
									/>
									{#if orgao.depth > 1}
										<span class="shrink-0 text-xs text-text-muted" aria-hidden="true">↳</span>
									{/if}
									<span class="min-w-0 truncate">
										<span class="font-semibold">{orgao.sigla}</span
										>{#if orgao.nome && orgao.nome !== orgao.sigla}
											<span class="text-text-muted"> — {orgao.nome}</span>{/if}
									</span>
								</label>
							</li>
						{:else}
							<li class="col-span-full px-3 py-4 text-center text-sm text-text-muted">
								Nenhum órgão encontrado para "{orgaoSearch.trim()}".
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		</div>
	</fieldset>

	<div class="flex items-center justify-end gap-2">
		<a
			href={cancelHref}
			class="inline-flex h-9 items-center rounded-md border border-border-strong bg-surface px-3.5 text-sm font-semibold text-text-secondary no-underline transition-all duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Cancelar
		</a>
		<button
			type="submit"
			disabled={saving}
			class="inline-flex h-9 items-center rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-white shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:shadow-none"
		>
			{saving ? 'Salvando…' : submitLabel}
		</button>
	</div>
</form>
