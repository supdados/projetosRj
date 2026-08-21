<script lang="ts">
	/**
	 * Tela "Conta > Ajustes" — sucessora do Jinja `/profile/change-password`
	 * (que virou redirect 302 para cá). Layout em duas colunas: card de
	 * identidade (iniciais, nome, username, sigla do órgão) à esquerda e os
	 * cards de ação à direita (nome de exibição, vínculo gov.br, senha).
	 * O username NUNCA é editável aqui (fica com o admin).
	 *
	 * Estados do vínculo gov.br (`GET /api/conta`): `nenhum` mostra o campo de
	 * CPF; `cpf_pendente` mostra a máscara (3 dígitos + `*`) com botão remover;
	 * `vinculado` mostra o chip "Vinculado" com botão remover — nenhum dígito.
	 *
	 * A troca de senha não pede a senha atual (decisão de produto): o corpo é só
	 * `{ nova_senha, confirmacao }`. Consome `$lib/api/account` (o `client.ts`
	 * injeta o X-CSRFToken). Réguas de validação são do backend: a mensagem do
	 * envelope `fail` é exibida como está.
	 */
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import {
		fetchConta,
		trocarNome,
		vincularGovbr,
		removerGovbr,
		trocarSenha,
		type GovbrVinculo
	} from '$lib/api/account';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';

	let carregando = $state(true);
	let erroCarga = $state('');

	let nome = $state('');
	let nomeSalvo = $state('');
	let username = $state('');
	let orgaoSigla = $state<string | null>(null);
	let salvandoNome = $state(false);
	let erroNome = $state('');

	let govbr = $state<GovbrVinculo>({ status: 'nenhum', cpf_mascarado: null });
	let cpf = $state('');
	let salvandoGovbr = $state(false);
	let erroGovbr = $state('');

	let novaSenha = $state('');
	let confirmacao = $state('');
	let salvandoSenha = $state(false);
	let erroSenha = $state('');

	const inputClass =
		'h-10 w-full rounded-lg border border-border-subtle bg-surface-muted px-3 text-sm text-text-primary transition-colors duration-fast placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-brand focus:bg-surface focus:outline-none disabled:opacity-60';
	const labelClass = 'text-xs font-bold uppercase tracking-caps text-text-muted';
	const cardClass =
		'flex flex-col gap-3.5 rounded-xl border border-border-subtle bg-surface px-6 py-5 shadow-sm';
	// Anatomia do .chip canônico (app.css) em 18px/11px, aprovados no mockup.
	// Vars --chip-* setadas direto nos tokens de família (sem a classe
	// .chip--*): chip decorativo não pode herdar o hover das famílias.
	const chipMiniClass =
		'inline-flex h-[18px] items-center whitespace-nowrap rounded-sm border border-[var(--chip-border)] bg-[var(--chip-bg)] px-1.5 text-2xs font-medium leading-none text-[var(--chip-fg)]';
	const chipSuccessVars =
		'[--chip-bg:var(--ds-color-success-100)] [--chip-border:var(--ds-color-success-200)] [--chip-fg:var(--ds-color-success-600)]';
	const chipWarningVars =
		'[--chip-bg:var(--ds-color-warning-100)] [--chip-border:var(--ds-color-warning-200)] [--chip-fg:var(--ds-color-warning-600)]';

	/** Duas iniciais para o avatar: 1ª letra do primeiro e do último nome. */
	function iniciaisDoNome(valor: string): string {
		const partes = valor.trim().split(/\s+/).filter(Boolean);
		if (partes.length === 0) return '?';
		if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
		return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
	}

	const iniciais = $derived(iniciaisDoNome(nomeSalvo || username));

	$effect(() => {
		const controller = new AbortController();
		fetchConta(controller.signal)
			.then((conta) => {
				nome = conta.name;
				nomeSalvo = conta.name;
				username = conta.username;
				orgaoSigla = conta.orgao_sigla;
				govbr = conta.govbr;
				carregando = false;
			})
			.catch((err) => {
				if (controller.signal.aborted) return;
				if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
				erroCarga = err instanceof Error ? err.message : 'Falha ao carregar a conta.';
				carregando = false;
			});
		return () => controller.abort();
	});

	/** Traduz erro de API em mensagem exibível; 401 já navegou para /login. */
	function mensagemDe(err: unknown, fallback: string): string {
		if (err instanceof ApiClientError && err.code === 'unauthenticated') return '';
		return err instanceof Error ? err.message : fallback;
	}

	async function submeterNome(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (salvandoNome) return;
		erroNome = nome.trim() ? '' : 'O nome é obrigatório.';
		if (erroNome) return;

		salvandoNome = true;
		try {
			nome = await trocarNome(nome.trim());
			nomeSalvo = nome;
			flash.success('Nome atualizado.');
		} catch (err) {
			erroNome = mensagemDe(err, 'Falha ao trocar o nome.');
		} finally {
			salvandoNome = false;
		}
	}

	async function submeterCpf(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (salvandoGovbr) return;
		erroGovbr = cpf.trim() ? '' : 'Informe o CPF a vincular.';
		if (erroGovbr) return;

		salvandoGovbr = true;
		try {
			govbr = await vincularGovbr(cpf.trim());
			cpf = '';
			flash.success('CPF gov.br vinculado.');
		} catch (err) {
			erroGovbr = mensagemDe(err, 'Falha ao vincular o CPF.');
		} finally {
			salvandoGovbr = false;
		}
	}

	async function removerVinculo(): Promise<void> {
		if (salvandoGovbr) return;
		salvandoGovbr = true;
		erroGovbr = '';
		try {
			govbr = await removerGovbr();
			flash.success('Vínculo gov.br removido.');
		} catch (err) {
			erroGovbr = mensagemDe(err, 'Falha ao remover o vínculo.');
		} finally {
			salvandoGovbr = false;
		}
	}

	/** Erro de senha detectável sem ida ao servidor, ou '' quando ok. */
	function erroSenhaLocal(): string {
		if (!novaSenha || !confirmacao) {
			return 'Preencha a nova senha e a confirmação.';
		}
		if (novaSenha !== confirmacao) {
			return 'A nova senha e a confirmação não correspondem.';
		}
		return '';
	}

	async function submeterSenha(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (salvandoSenha) return;
		erroSenha = erroSenhaLocal();
		if (erroSenha) return;

		salvandoSenha = true;
		try {
			await trocarSenha({ nova_senha: novaSenha, confirmacao });
			novaSenha = '';
			confirmacao = '';
			flash.success('Senha alterada com sucesso.');
		} catch (err) {
			erroSenha = mensagemDe(err, 'Falha ao trocar a senha.');
		} finally {
			salvandoSenha = false;
		}
	}
</script>

<svelte:head>
	<title>ProjetosRJ — Ajustes</title>
</svelte:head>

<section
	aria-label="Ajustes da conta"
	class="mx-auto grid w-full max-w-[1160px] grid-cols-[300px_minmax(0,1fr)] items-stretch gap-4"
>
	{#if erroCarga}
		<div class="col-span-full">
			<StateBanner tone="danger" title={erroCarga} />
		</div>
	{:else if !carregando}
		<div
			class="flex flex-col items-center justify-center gap-3 rounded-xl border border-border-subtle bg-surface px-5 py-7 shadow-sm"
		>
			<div
				aria-hidden="true"
				class="grid h-[72px] w-[72px] place-items-center rounded-full bg-wash-brand text-2xl font-bold text-brand"
			>
				{iniciais}
			</div>
			<div class="flex flex-col items-center gap-0.5">
				<span class="text-lg font-bold text-text-primary">{nomeSalvo}</span>
				<span class="text-sm text-text-muted">{username}</span>
				{#if orgaoSigla}
					<span class="text-sm font-semibold text-text-secondary">{orgaoSigla}</span>
				{/if}
			</div>
		</div>

		<div class="flex flex-col gap-4">
			<div class="grid grid-cols-2 gap-4">
				<form class={cardClass} onsubmit={submeterNome} novalidate>
					<div class="flex flex-col gap-1">
						<h2 class="text-base font-bold text-text-primary">Nome de exibição</h2>
						<p class="text-sm text-text-muted">Aparece nos projetos, tarefas e comentários.</p>
					</div>
					{#if erroNome}
						<StateBanner tone="danger" title={erroNome} />
					{/if}
					<div class="mt-auto flex items-center gap-3">
						<input
							id="conta-nome"
							type="text"
							required
							aria-label="Nome de exibição"
							disabled={salvandoNome}
							autocomplete="name"
							bind:value={nome}
							class="{inputClass} flex-1"
						/>
						<div class="shrink-0">
							<Button type="submit" size="sm" disabled={salvandoNome}>
								{salvandoNome ? 'Salvando…' : 'Salvar'}
							</Button>
						</div>
					</div>
				</form>

				<div class={cardClass}>
					<div class="flex flex-col gap-1">
						<h2 class="flex items-center gap-2 text-base font-bold text-text-primary">
							Acesso gov.br
							{#if govbr.status === 'vinculado'}
								<span class="{chipMiniClass} {chipSuccessVars}">Vinculado</span>
							{:else if govbr.status === 'cpf_pendente'}
								<span class="{chipMiniClass} {chipWarningVars}">CPF pendente</span>
							{/if}
						</h2>
						<p class="text-sm text-text-muted">
							{#if govbr.status === 'vinculado'}
								Conta vinculada — você pode entrar pelo gov.br.
							{:else if govbr.status === 'cpf_pendente'}
								CPF {govbr.cpf_mascarado} aguardando o primeiro login gov.br.
							{:else}
								Vincule seu CPF para entrar pelo gov.br.
							{/if}
						</p>
					</div>
					{#if erroGovbr}
						<StateBanner tone="danger" title={erroGovbr} />
					{/if}
					{#if govbr.status === 'nenhum'}
						<form class="mt-auto flex items-center gap-3" onsubmit={submeterCpf} novalidate>
							<input
								id="conta-cpf"
								type="text"
								required
								inputmode="numeric"
								aria-label="CPF gov.br"
								placeholder="Somente números (11 dígitos)"
								disabled={salvandoGovbr}
								autocomplete="off"
								bind:value={cpf}
								class="{inputClass} flex-1"
							/>
							<div class="shrink-0">
								<Button type="submit" variant="secondary" size="sm" disabled={salvandoGovbr}>
									{salvandoGovbr ? 'Vinculando…' : 'Vincular'}
								</Button>
							</div>
						</form>
					{:else}
						<div class="mt-auto flex justify-center">
							<Button variant="danger" size="sm" disabled={salvandoGovbr} onclick={removerVinculo}>
								{#if salvandoGovbr}
									Removendo…
								{:else if govbr.status === 'vinculado'}
									Remover vínculo
								{:else}
									Remover CPF
								{/if}
							</Button>
						</div>
					{/if}
				</div>
			</div>

			<form class="{cardClass} flex-1" onsubmit={submeterSenha} novalidate>
				<div class="flex flex-col gap-1">
					<h2 class="text-base font-bold text-text-primary">Senha</h2>
					<p class="text-sm text-text-muted">Mínimo de 8 e máximo de 128 caracteres.</p>
				</div>
				{#if erroSenha}
					<StateBanner tone="danger" title={erroSenha} />
				{/if}
				<div class="mt-auto flex items-end gap-3">
					<div class="grid flex-1 grid-cols-2 gap-3">
						<div class="flex flex-col gap-1.5">
							<label for="conta-senha-nova" class={labelClass}>Nova senha</label>
							<input
								id="conta-senha-nova"
								type="password"
								required
								minlength={8}
								disabled={salvandoSenha}
								autocomplete="new-password"
								bind:value={novaSenha}
								class={inputClass}
							/>
						</div>
						<div class="flex flex-col gap-1.5">
							<label for="conta-senha-confirmacao" class={labelClass}>Confirmar nova senha</label>
							<input
								id="conta-senha-confirmacao"
								type="password"
								required
								minlength={8}
								disabled={salvandoSenha}
								autocomplete="new-password"
								bind:value={confirmacao}
								class={inputClass}
							/>
						</div>
					</div>
					<div class="flex h-10 shrink-0 items-center">
						<Button type="submit" size="sm" disabled={salvandoSenha}>
							{salvandoSenha ? 'Salvando…' : 'Trocar senha'}
						</Button>
					</div>
				</div>
			</form>
		</div>
	{/if}
</section>
