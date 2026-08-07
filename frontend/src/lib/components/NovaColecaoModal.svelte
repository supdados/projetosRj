<script lang="ts">
	/**
	 * Modal "Nova coleção" em 2 passos (design 3b): Identidade (nome, descrição,
	 * ícone, cor) → Projetos (card-resumo editável + ColecaoProjectPicker).
	 * A criação é ATÔMICA: "Criar coleção" faz um único POST /api/colecoes com
	 * `project_ids`. Máquina de fases no molde de CriarProjetoModal: trocar de
	 * passo desmonta o dono do foco, então cada transição re-foca um alvo
	 * visível via tick(); chrome (backdrop/Esc/focus-trap) é o Modal base.
	 */
	import { tick } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import { criarColecao } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import type {
		ColecaoResumo,
		CollectionColorId,
		CollectionIconId
	} from '$lib/types/collections';

	interface Props {
		/** Modal aberto? (controlado pela página). */
		open: boolean;
		/** Fecha o modal sem criar (✕, Esc, backdrop, Cancelar). */
		onClose: () => void;
		/** Coleção criada com sucesso; o modal fecha sozinho em seguida. */
		onCreated: (colecao: ColecaoResumo) => void;
	}

	let { open, onClose, onCreated }: Props = $props();

	const DESCRICAO_MAX = 200;

	type Fase = 'identidade' | 'projetos';
	const PASSOS: { id: Fase; label: string }[] = [
		{ id: 'identidade', label: 'Identidade' },
		{ id: 'projetos', label: 'Projetos' }
	];

	const ICONE_OPTIONS: { id: CollectionIconId; label: string }[] = [
		{ id: 'camadas', label: 'Camadas' },
		{ id: 'servidores', label: 'Servidores' },
		{ id: 'pessoas', label: 'Pessoas' },
		{ id: 'documento', label: 'Documento' },
		{ id: 'estrela', label: 'Estrela' },
		{ id: 'rede', label: 'Rede' },
		{ id: 'capacitacao', label: 'Capacitação' },
		{ id: 'calendario', label: 'Calendário' }
	];

	// Mapas ESTÁTICOS por família: classe montada em runtime não compila.
	const COR_OPTIONS: {
		id: CollectionColorId;
		label: string;
		wash: string;
		dot: string;
		ativo: string;
	}[] = [
		{ id: 'primary', label: 'Azul', wash: 'bg-wash-brand', dot: 'bg-primary-600', ativo: 'border-primary-600' },
		{ id: 'success', label: 'Verde', wash: 'bg-wash-success', dot: 'bg-success-600', ativo: 'border-success-600' },
		{ id: 'warning', label: 'Âmbar', wash: 'bg-wash-warning', dot: 'bg-warning-600', ativo: 'border-warning-600' },
		{ id: 'attention', label: 'Laranja', wash: 'bg-wash-attention', dot: 'bg-attention-600', ativo: 'border-attention-600' },
		{ id: 'danger', label: 'Vermelho', wash: 'bg-wash-danger', dot: 'bg-danger-600', ativo: 'border-danger-600' },
		{ id: 'neutral', label: 'Cinza', wash: 'bg-wash-neutral', dot: 'bg-neutral-600', ativo: 'border-neutral-600' }
	];

	const ICONE_ATIVO_CLASS: Record<CollectionColorId, string> = {
		primary: 'border-primary-600 bg-wash-brand text-brand',
		success: 'border-success-600 bg-wash-success text-success',
		warning: 'border-warning-600 bg-wash-warning text-warning',
		attention: 'border-attention-600 bg-wash-attention text-attention',
		danger: 'border-danger-600 bg-wash-danger text-danger',
		neutral: 'border-neutral-600 bg-wash-neutral text-text-secondary'
	};

	let fase = $state<Fase>('identidade');
	let nome = $state('');
	let descricao = $state('');
	let icone = $state<CollectionIconId>('camadas');
	let cor = $state<CollectionColorId>('primary');
	let selecionados = $state<number[]>([]);
	let triedNext = $state(false);
	let submitting = $state(false);
	let erro = $state<string | null>(null);

	let nomeInputEl = $state<HTMLInputElement | null>(null);
	let passo2HeadingEl = $state<HTMLHeadingElement | null>(null);

	const nomeInvalido = $derived(triedNext && !nome.trim());

	let prevOpen = false;
	$effect(() => {
		if (open && !prevOpen) {
			resetar();
			focusAfterTick(() => nomeInputEl);
		}
		prevOpen = open;
	});

	function resetar(): void {
		fase = 'identidade';
		nome = '';
		descricao = '';
		icone = 'camadas';
		cor = 'primary';
		selecionados = [];
		triedNext = false;
		submitting = false;
		erro = null;
	}

	// offsetParent null = display:none; focar alvo invisível derrubaria o trap.
	function focusAfterTick(getEl: () => HTMLElement | null): void {
		void tick().then(() => {
			const el = getEl();
			if (el && el.offsetParent !== null) el.focus();
		});
	}

	function irParaProjetos(): void {
		triedNext = true;
		if (!nome.trim()) {
			nomeInputEl?.focus();
			return;
		}
		fase = 'projetos';
		focusAfterTick(() => passo2HeadingEl);
	}

	function voltarParaIdentidade(): void {
		erro = null;
		fase = 'identidade';
		focusAfterTick(() => nomeInputEl);
	}

	function requestClose(): void {
		if (submitting) return;
		onClose();
	}

	async function criar(): Promise<void> {
		if (submitting) return;
		submitting = true;
		erro = null;
		try {
			const colecao = await criarColecao({
				nome: nome.trim(),
				descricao: descricao.trim() || null,
				icone,
				cor,
				project_ids: selecionados.length > 0 ? selecionados : undefined
			});
			onCreated(colecao);
			onClose();
		} catch (err) {
			erro =
				err instanceof ApiClientError ? err.message : 'Não foi possível criar a coleção.';
		} finally {
			submitting = false;
		}
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
	const fieldCls =
		'h-[var(--control-h-md)] w-full rounded-control border bg-surface px-3.5 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:outline-none';
</script>

{#if open}
	<Modal labelId="nova-colecao-title" maxWidth="max-w-[540px]" onBackdrop={requestClose}>
		<div class="flex max-h-[80vh] flex-col gap-4">
			<div class="flex items-center gap-3">
				<h2 id="nova-colecao-title" class="font-heading text-xl font-bold text-text-primary">
					{fase === 'identidade' ? 'Nova coleção' : 'Adicionar projetos'}
				</h2>
				<span class="text-2xs font-medium uppercase tracking-caps text-text-muted">
					Passo {fase === 'identidade' ? 1 : 2} de 2
				</span>
				<button
					type="button"
					onclick={requestClose}
					disabled={submitting}
					aria-label="Fechar"
					class="ml-auto grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg
						viewBox="0 0 20 20"
						class="h-4 w-4"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						aria-hidden="true"
					>
						<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
					</svg>
				</button>
			</div>

			<ol class="flex items-center gap-3" aria-label="Passos do cadastro">
				{#each PASSOS as passo, i (passo.id)}
					{@const ativo = fase === passo.id}
					{#if i > 0}
						<li role="presentation" class="h-px flex-1 bg-border-subtle"></li>
					{/if}
					<li
						aria-current={ativo ? 'step' : undefined}
						class="flex items-center gap-2 text-xs {ativo
							? 'font-medium text-brand'
							: 'text-text-muted'}"
					>
						<span
							class="grid h-[22px] w-[22px] place-items-center rounded-sm text-2xs font-semibold {ativo
								? 'bg-brand text-on-brand'
								: 'border border-border-subtle'}"
						>
							{i + 1}
						</span>
						{passo.label}
					</li>
				{/each}
			</ol>

			{#if fase === 'identidade'}
				<form
					class="flex min-h-0 flex-1 flex-col gap-4"
					onsubmit={(e) => {
						e.preventDefault();
						irParaProjetos();
					}}
				>
					<div class="thin-scroll flex min-h-0 flex-col gap-4 overflow-y-auto">
						<div class="flex items-end gap-3">
							<ColecaoIconTile {icone} {cor} size={52} />
							<div class="flex min-w-0 flex-1 flex-col gap-1.5">
								<label for="nc-nome" class={labelCls}>Nome da coleção</label>
								<input
									id="nc-nome"
									bind:this={nomeInputEl}
									bind:value={nome}
									type="text"
									aria-invalid={nomeInvalido}
									placeholder="Ex.: Modernização Digital 2026"
									class="{fieldCls} {nomeInvalido
										? 'border-danger'
										: 'border-border-strong focus:border-brand'}"
								/>
							</div>
						</div>
						{#if nomeInvalido}
							<p class="text-xs text-danger">Informe o nome da coleção.</p>
						{/if}

						<div class="flex flex-col gap-1.5">
							<label for="nc-descricao" class={labelCls}>Descrição (opcional)</label>
							<input
								id="nc-descricao"
								bind:value={descricao}
								type="text"
								maxlength={DESCRICAO_MAX}
								placeholder="Para que serve esta coleção"
								class="{fieldCls} border-border-strong focus:border-brand"
							/>
						</div>

						<div class="flex flex-col gap-2">
							<span id="nc-icone-label" class={labelCls}>Ícone</span>
							<div role="group" aria-labelledby="nc-icone-label" class="grid grid-cols-8 gap-2">
								{#each ICONE_OPTIONS as opcao (opcao.id)}
									{@const ativo = icone === opcao.id}
									<button
										type="button"
										aria-pressed={ativo}
										aria-label={opcao.label}
										onclick={() => (icone = opcao.id)}
										class="grid aspect-square place-items-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativo
											? ICONE_ATIVO_CLASS[cor]
											: 'border-border-subtle text-text-secondary hover:bg-surface-muted'}"
									>
										<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
											{#each COLLECTION_ICONS[opcao.id] as p (p.d)}
												<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
											{/each}
										</svg>
									</button>
								{/each}
							</div>
						</div>

						<div class="flex flex-col gap-2">
							<span id="nc-cor-label" class={labelCls}>Cor</span>
							<div role="group" aria-labelledby="nc-cor-label" class="flex gap-2">
								{#each COR_OPTIONS as opcao (opcao.id)}
									{@const ativo = cor === opcao.id}
									<button
										type="button"
										aria-pressed={ativo}
										aria-label={opcao.label}
										onclick={() => (cor = opcao.id)}
										class="grid h-8 w-8 place-items-center rounded-md border-2 transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 {opcao.wash} {ativo
											? opcao.ativo
											: 'border-transparent hover:border-border-subtle'}"
									>
										<span class="h-3.5 w-3.5 rounded-full {opcao.dot}" aria-hidden="true"></span>
									</button>
								{/each}
							</div>
						</div>
					</div>

					<footer class="flex justify-end gap-2 border-t border-border-hairline pt-4">
						<Button variant="secondary" onclick={requestClose}>Cancelar</Button>
						<Button type="submit">Próximo</Button>
					</footer>
				</form>
			{:else}
				<div class="flex min-h-0 flex-1 flex-col gap-4">
					<div class="thin-scroll flex min-h-0 flex-col gap-4 overflow-y-auto">
						<div
							class="flex items-center gap-3 rounded-control border border-border-subtle bg-surface-muted p-3"
						>
							<ColecaoIconTile {icone} {cor} size={40} />
							<div class="min-w-0 flex-1">
								<h3
									bind:this={passo2HeadingEl}
									tabindex="-1"
									class="truncate text-sm font-semibold text-text-primary focus:outline-none"
								>
									{nome.trim()}
								</h3>
								<p class="truncate text-xs text-text-muted">
									{descricao.trim() || 'Sem descrição'}
								</p>
							</div>
							<Button variant="secondary" size="sm" onclick={voltarParaIdentidade}>Editar</Button>
						</div>

						<div class="flex flex-col gap-1.5">
							<span class={labelCls}>Projetos da sua área</span>
							<ColecaoProjectPicker
								{selecionados}
								onchange={(ids) => (selecionados = ids)}
							/>
						</div>

						{#if erro}
							<StateBanner tone="danger" title={erro} />
						{/if}
					</div>

					<footer class="flex justify-end gap-2 border-t border-border-hairline pt-4">
						<Button variant="secondary" onclick={voltarParaIdentidade} disabled={submitting}>
							Voltar
						</Button>
						<Button onclick={() => void criar()} disabled={submitting}>
							{submitting ? 'Criando…' : 'Criar coleção'}
						</Button>
					</footer>
				</div>
			{/if}
		</div>
	</Modal>
{/if}
