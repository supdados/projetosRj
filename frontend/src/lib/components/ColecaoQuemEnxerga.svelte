<script lang="ts">
	/**
	 * "Quem enxerga" do modal Nova coleção (design "Coleções 3a"): dois cartões
	 * de rádio — "Só eu" (padrão: a coleção NASCE pessoal) e "Compartilhar".
	 * Compartilhando, um campo ÚNICO "Pessoa ou sigla da área" sugere pessoas
	 * (busca no servidor) e áreas (catálogo, filtrado aqui) na mesma lista; o
	 * papel vem do seletor ao lado e o "+" põe o alvo na lista.
	 *
	 * Cada destinatário recebe um CONVITE pendente (nada é visto antes do
	 * aceite). Versão compacta do formulário de `CompartilharColecaoModal`, que
	 * gerencia os convites depois de a coleção existir (só o dono). Área é o
	 * órgão EXATO, sem subárvore.
	 *
	 * Rádios nativos (`sr-only`) dão a navegação por setas de graça. O que cada
	 * papel permite fica no tooltip do seletor (o texto corrido saiu da tela).
	 */
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { buscarDestinatarios } from '$lib/api/collections';
	import { fetchAreas, type AreaOption } from '$lib/api/areas';
	import { buildOrgaoTree, flattenTreeWithPath, type OrgaoTreeRow } from '$lib/utils/orgaoTree';
	import { PAPEIS_COMPARTILHAMENTO } from '$lib/utils/colecaoShares';
	import {
		comPendenteIncluido,
		destinatarioDeArea,
		destinatarioDePessoa,
		type DestinatarioNovo
	} from '$lib/utils/novaColecaoDestinatarios';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { PapelCompartilhamento, PessoaDestinavel } from '$lib/types/collections';

	interface Props {
		/** `true` = "Só eu" (nenhum compartilhamento vai no POST). */
		soEu: boolean;
		destinatarios: DestinatarioNovo[];
		/** Prefixo dos ids (listbox/rádios). */
		idPrefix: string;
	}

	let { soEu = $bindable(), destinatarios = $bindable(), idPrefix }: Props = $props();

	/** `AreaOption` no formato que `buildOrgaoTree` espera (`value` + `pai_id`). */
	type OrgaoCandidato = AreaOption & { value: number };
	type Alvo = { tipo: 'pessoa'; pessoa: PessoaDestinavel } | { tipo: 'area'; orgao: AreaOption };

	const MAX_AREAS_SUGERIDAS = 6;
	const PAPEL_MENU: SelectMenuOption[] = PAPEIS_COMPARTILHAMENTO.map((o) => ({
		value: o.id,
		label: o.label
	}));
	const PAPEL_INFO = Object.fromEntries(PAPEIS_COMPARTILHAMENTO.map((o) => [o.id, o])) as Record<
		PapelCompartilhamento,
		(typeof PAPEIS_COMPARTILHAMENTO)[number]
	>;

	const OPCOES = [
		{ soEu: true, label: 'Só eu', hint: 'Apenas você vê esta coleção', icone: 'fa-lock' },
		{ soEu: false, label: 'Compartilhar', hint: 'Escolha pessoas ou áreas', icone: 'fa-user-group' }
	] as const;

	let termo = $state('');
	let alvo = $state<Alvo | null>(null);
	let papel = $state<PapelCompartilhamento>('viewer');
	let pessoas = $state<PessoaDestinavel[]>([]);
	let orgaos = $state<AreaOption[]>([]);
	let listaAberta = $state(false);
	let erro = $state('');
	let caixaEl = $state<HTMLDivElement | null>(null);

	const orgaoCandidatos = $derived<OrgaoCandidato[]>(orgaos.map((a) => ({ ...a, value: a.id })));
	// Áreas só aparecem com algo digitado: o catálogo inteiro afogaria as pessoas.
	const linhasOrgao = $derived.by<OrgaoTreeRow<OrgaoCandidato>[]>(() => {
		if (!termo.trim() || alvo) return [];
		const linhas = flattenTreeWithPath(buildOrgaoTree(orgaoCandidatos), termo, {
			omitRootAncestor: true
		});
		return linhas.slice(0, MAX_AREAS_SUGERIDAS);
	});
	const temSugestao = $derived(pessoas.length > 0 || linhasOrgao.length > 0);

	// Autocomplete de pessoas: 250ms de folga e aborto da busca anterior a cada tecla.
	$effect(() => {
		const q = termo.trim();
		if (soEu || q.length < 2 || alvo !== null) {
			pessoas = [];
			return;
		}
		const controller = new AbortController();
		const timer = setTimeout(() => {
			buscarDestinatarios(q, controller.signal)
				.then((achados) => (pessoas = achados))
				.catch(() => {
					if (!controller.signal.aborted) pessoas = [];
				});
		}, 250);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	// Clique fora do campo fecha as sugestões.
	$effect(() => {
		if (!listaAberta) return;
		const fecharSeFora = (event: PointerEvent): void => {
			if (caixaEl?.contains(event.target as Node)) return;
			listaAberta = false;
		};
		window.addEventListener('pointerdown', fecharSeFora, true);
		return () => window.removeEventListener('pointerdown', fecharSeFora, true);
	});

	function escolherVisibilidade(valor: boolean): void {
		soEu = valor;
		erro = '';
		if (!valor) void carregarOrgaos();
	}

	/** Catálogo completo de órgãos, uma vez por abertura do modal (busca client-side). */
	async function carregarOrgaos(): Promise<void> {
		if (orgaos.length > 0) return;
		try {
			orgaos = (await fetchAreas()).areas;
		} catch {
			erro = 'Não foi possível carregar as áreas.';
		}
	}

	function onDigitar(): void {
		alvo = null;
		listaAberta = true;
		erro = '';
	}

	function escolherPessoa(pessoa: PessoaDestinavel): void {
		alvo = { tipo: 'pessoa', pessoa };
		termo = pessoa.name;
		pessoas = [];
		listaAberta = false;
	}

	function escolherOrgao(orgao: AreaOption): void {
		alvo = { tipo: 'area', orgao };
		termo = orgao.sigla || orgao.nome;
		listaAberta = false;
	}

	function destinatarioDoAlvo(escolhido: Alvo): DestinatarioNovo {
		return escolhido.tipo === 'pessoa'
			? destinatarioDePessoa(escolhido.pessoa, papel)
			: destinatarioDeArea(escolhido.orgao, papel);
	}

	function limparCampo(): void {
		erro = '';
		alvo = null;
		termo = '';
	}

	/**
	 * Chamado pelo modal no "Criar coleção": quem ficou escolhido no campo sem
	 * o "+" entra na lista (antes era descartado em silêncio e a coleção nascia
	 * pessoal). Texto digitado sem escolher da lista barra a criação com aviso.
	 * Ex.: `quemEnxerga.confirmarPendente()` → `false` = não criar ainda.
	 */
	export function confirmarPendente(): boolean {
		if (soEu) return true;
		if (alvo) {
			destinatarios = comPendenteIncluido(destinatarios, destinatarioDoAlvo(alvo));
			limparCampo();
			return true;
		}
		if (!termo.trim()) return true;
		erro = 'Escolha uma pessoa ou área da lista, ou apague o texto do campo.';
		return false;
	}

	function adicionar(): void {
		if (!alvo) {
			erro = termo.trim() ? 'Escolha uma pessoa ou área da lista.' : '';
			return;
		}
		const novo = destinatarioDoAlvo(alvo);
		if (destinatarios.some((d) => d.chave === novo.chave)) {
			erro = `${novo.nome} já está na lista.`;
			return;
		}
		destinatarios = [...destinatarios, novo];
		limparCampo();
	}

	// Enter no campo adiciona o alvo escolhido — nunca submete o modal.
	function onTecla(event: KeyboardEvent): void {
		if (event.key === 'Escape' && listaAberta) {
			// Fecha só a lista; o Esc seguinte é que fecha o modal.
			event.preventDefault();
			listaAberta = false;
			return;
		}
		if (event.key !== 'Enter') return;
		event.preventDefault();
		adicionar();
	}

	function remover(chave: string): void {
		destinatarios = destinatarios.filter((d) => d.chave !== chave);
	}

	const opcaoCls = 'flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-muted';
	const grupoCls = 'px-3 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wide text-text-muted';
</script>

<fieldset class="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
	<legend class="mb-2 p-0 text-sm font-semibold text-text-secondary">Quem enxerga</legend>
	{#each OPCOES as opcao (opcao.label)}
		{@const ativo = soEu === opcao.soEu}
		<label
			class="flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-fast has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand {ativo
				? 'border-brand bg-wash-brand'
				: 'border-border-subtle hover:bg-surface-muted'}"
		>
			<input
				type="radio"
				name="{idPrefix}-visibilidade"
				class="sr-only"
				checked={ativo}
				onchange={() => escolherVisibilidade(opcao.soEu)}
			/>
			<i
				class="fas {opcao.icone} w-5 shrink-0 text-center {ativo ? 'text-brand' : 'text-text-secondary'}"
				aria-hidden="true"
			></i>
			<span class="flex min-w-0 flex-1 flex-col">
				<span class="text-md font-semibold text-text-primary">{opcao.label}</span>
				<span class="text-xs text-text-muted">{opcao.hint}</span>
			</span>
			<span
				class="h-[18px] w-[18px] shrink-0 rounded-full bg-surface transition-[border] duration-fast {ativo
					? 'border-[5px] border-brand'
					: 'border-[1.5px] border-border-strong'}"
				aria-hidden="true"
			></span>
		</label>
	{/each}

	{#if !soEu}
		<div class="flex flex-col gap-1.5">
			<div bind:this={caixaEl} class="relative flex gap-1.5">
				<input
					id="{idPrefix}-alvo"
					type="text"
					autocomplete="off"
					role="combobox"
					aria-expanded={listaAberta && temSugestao}
					aria-controls="{idPrefix}-alvo-lista"
					aria-autocomplete="list"
					aria-label="Pessoa ou sigla da área"
					placeholder="Pessoa ou sigla da área"
					bind:value={termo}
					oninput={onDigitar}
					onfocus={() => (listaAberta = true)}
					onkeydown={onTecla}
					class="h-9 min-w-0 flex-1 rounded-md border border-border-strong bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
				<!-- Largura fixa: o SelectMenu é `w-full` e espremia o campo até sumir. -->
				<div class="w-[6.75rem] shrink-0" title={PAPEL_INFO[papel].hint}>
					<SelectMenu
						options={PAPEL_MENU}
						value={papel}
						onSelect={(v) => (papel = v === 'editor' ? 'editor' : 'viewer')}
						size="sm"
						align="right"
						ariaLabel="Papel do compartilhamento"
					/>
				</div>
				<button
					type="button"
					onclick={adicionar}
					disabled={!alvo}
					aria-label="Adicionar à lista"
					title="Adicionar"
					class="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-brand text-on-brand transition-colors duration-fast hover:bg-brand-hover disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
				>
					<i class="fas fa-plus" aria-hidden="true"></i>
				</button>

				{#if listaAberta && temSugestao}
					<ul
						id="{idPrefix}-alvo-lista"
						role="listbox"
						aria-label="Pessoas e áreas encontradas"
						class="absolute left-0 right-0 top-[calc(100%+0.25rem)] z-30 m-0 max-h-56 list-none overflow-y-auto rounded-control border border-border-subtle bg-surface-elevated p-0 pb-1 shadow-lg"
					>
						{#if pessoas.length > 0}
							<li role="presentation" class={grupoCls}>Pessoas</li>
							{#each pessoas as pessoa (pessoa.id)}
								<li role="none">
									<button
										type="button"
										role="option"
										aria-selected="false"
										onclick={() => escolherPessoa(pessoa)}
										class={opcaoCls}
									>
										<i class="fas fa-user w-4 shrink-0 text-xs text-text-muted" aria-hidden="true"></i>
										<span class="min-w-0 flex-1 truncate text-sm text-text-primary">{pessoa.name}</span>
										{#if pessoa.orgao_sigla}
											<span class="shrink-0 text-xs text-text-secondary">{pessoa.orgao_sigla}</span>
										{/if}
									</button>
								</li>
							{/each}
						{/if}
						{#if linhasOrgao.length > 0}
							<li role="presentation" class={grupoCls}>Áreas</li>
							{#each linhasOrgao as linha (linha.value)}
								<li role="none">
									<button
										type="button"
										role="option"
										aria-selected="false"
										onclick={() => escolherOrgao(linha.option)}
										class={opcaoCls}
									>
										<ColecaoIconeSvg icone="orgao" size={14} class="shrink-0 text-text-muted" />
										<span class="shrink-0 text-xs font-semibold text-text-primary">
											{#if linha.path}<span class="mr-1 font-normal text-text-muted">{linha.path} ›</span>{/if}{linha
												.option.sigla}
										</span>
										<span class="min-w-0 flex-1 truncate text-xs text-text-secondary">
											{linha.option.nome}
										</span>
									</button>
								</li>
							{/each}
						{/if}
					</ul>
				{/if}
			</div>
			{#if erro}
				<p role="alert" class="m-0 text-xs text-danger">{erro}</p>
			{/if}

			{#if destinatarios.length > 0}
				<ul class="m-0 flex list-none flex-col gap-1.5 p-0">
					{#each destinatarios as destinatario (destinatario.chave)}
						<li
							class="flex items-center gap-2 rounded-md bg-surface-muted px-2.5 py-1.5 text-sm"
							title={destinatario.detalhe}
						>
							{#if destinatario.tipo === 'pessoa'}
								<i class="fas fa-user w-4 shrink-0 text-xs text-text-secondary" aria-hidden="true"></i>
							{:else}
								<ColecaoIconeSvg icone="orgao" size={16} class="shrink-0 text-text-secondary" />
							{/if}
							<span class="min-w-0 flex-1 truncate font-semibold text-text-primary">
								{destinatario.nome}
							</span>
							<span class="shrink-0 text-xs text-text-muted">{PAPEL_INFO[destinatario.papel].label}</span>
							<button
								type="button"
								onclick={() => remover(destinatario.chave)}
								aria-label={`Remover ${destinatario.nome}`}
								class="grid h-6 w-6 shrink-0 place-items-center rounded text-text-muted transition-colors duration-fast hover:bg-wash-danger hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								<svg viewBox="0 0 20 20" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
									<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
								</svg>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</fieldset>
