<script lang="ts">
	/**
	 * Campos compartilhados do formulário de órgão (criar/editar). Espelha
	 * `templates/admin/orgao_form.html`: nome, sigla, tipo, pai, código externo,
	 * vigência (início/fim), ordem e ativo. Os valores são vinculados via
	 * `bind:` ao componente pai (que faz a chamada à API), respeitando o payload
	 * aceito por `normalize_orgao_form` (campos como string/checkbox).
	 *
	 * Em modo raiz (`isRoot`), o pai é fixo em "— raiz da hierarquia —" (sem
	 * seletor) e os tipos oferecidos são apenas os `permite_raiz`; fora da raiz,
	 * o seletor de pai é obrigatório e os tipos raiz ficam de fora. A validação
	 * de hierarquia final é do backend.
	 */
	import type { CandidatoPai, OrgaoTipo } from '$lib/types/adminOrgaos';

	interface Props {
		tipos: OrgaoTipo[];
		candidatosPai: CandidatoPai[];
		isRoot: boolean;
		nome: string;
		sigla: string;
		tipoId: string;
		paiId: string;
		ordem: string;
		ativo: boolean;
		codigoExterno: string;
		dataInicio: string;
		dataFim: string;
	}

	let {
		tipos,
		candidatosPai,
		isRoot,
		nome = $bindable(),
		sigla = $bindable(),
		tipoId = $bindable(),
		paiId = $bindable(),
		ordem = $bindable(),
		ativo = $bindable(),
		codigoExterno = $bindable(),
		dataInicio = $bindable(),
		dataFim = $bindable()
	}: Props = $props();

	/**
	 * Tipos oferecidos no seletor: ativos e coerentes com o modo (raiz exige
	 * `permite_raiz`; subunidade exclui os tipos raiz). A regra hierárquica
	 * pai↔filho completa é validada no backend.
	 */
	const tipoOptions = $derived(
		tipos.filter((t) => t.ativo && (isRoot ? t.permite_raiz : !t.permite_raiz))
	);

	/**
	 * Combobox de pai com busca (espelha o `#paiCombo` do orgao_form.html). O
	 * filtro por RANK de tipo (só pais com nível superior ao tipo escolhido) não
	 * é possível no cliente porque `candidatos_pai` não traz o nível de cada pai
	 * (ver needs_backend); aqui implementamos a busca textual + navegação por
	 * teclado, que é a interação visível do original.
	 */
	let comboOpen = $state(false);
	let comboText = $state('');
	let activeIndex = $state(-1);

	// Sincroniza o rótulo exibido quando uma seleção válida existe (carga/edição).
	// Não limpa o texto quando paiId fica vazio durante a digitação — só reflete
	// uma seleção concreta, evitando apagar o que o usuário acabou de digitar.
	$effect(() => {
		const sel = candidatosPai.find((p) => String(p.id) === paiId);
		if (sel) comboText = `${sel.sigla} — ${sel.nome}`;
	});

	const comboFiltered = $derived.by(() => {
		const q = comboText.trim().toLowerCase();
		const sel = candidatosPai.find((p) => String(p.id) === paiId);
		const matchesSelected = sel && `${sel.sigla} — ${sel.nome}`.toLowerCase() === q;
		if (!q || matchesSelected) return candidatosPai;
		return candidatosPai.filter((p) =>
			`${p.sigla} — ${p.nome}`.toLowerCase().includes(q)
		);
	});

	function selectPai(id: number, label: string): void {
		paiId = String(id);
		comboText = label;
		comboOpen = false;
		activeIndex = -1;
	}

	function onComboInput(event: Event): void {
		comboText = (event.currentTarget as HTMLInputElement).value;
		// Ao digitar, invalida a seleção até confirmar uma opção (espelha v4.5).
		const sel = candidatosPai.find((p) => String(p.id) === paiId);
		if (!sel || `${sel.sigla} — ${sel.nome}` !== comboText) paiId = '';
		comboOpen = true;
		activeIndex = -1;
	}

	function onComboKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			comboOpen = false;
			return;
		}
		const list = comboFiltered;
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			if (!list.length) return;
			event.preventDefault();
			comboOpen = true;
			if (event.key === 'ArrowDown') {
				activeIndex = activeIndex < 0 ? 0 : Math.min(activeIndex + 1, list.length - 1);
			} else {
				activeIndex = activeIndex < 0 ? list.length - 1 : Math.max(activeIndex - 1, 0);
			}
		} else if (event.key === 'Enter') {
			const opt = list[activeIndex];
			if (opt) {
				event.preventDefault();
				selectPai(opt.id, `${opt.sigla} — ${opt.nome}`);
			}
		}
	}

	function uppercaseSigla(event: Event): void {
		// v4.5 força caixa alta no VALOR (não só visual): sigla.value.toUpperCase().
		sigla = (event.currentTarget as HTMLInputElement).value.toUpperCase();
	}

	// Reproduz .account-input / .account-label do original (20-glass-forms-and-admin.css):
	// input com borda sutil, raio md, foco com ring da marca; label em caixa alta.
	const inputClass =
		'rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const labelClass = 'text-xs font-semibold uppercase tracking-wide text-text-muted';
	const sectionTitleClass =
		'font-heading text-sm font-semibold text-text-primary';
	const cardClass =
		'flex flex-col gap-4 rounded-lg border border-border-subtle bg-surface p-5';
</script>

<div class="flex flex-col gap-5">
	<!-- Identificação -->
	<section class={cardClass}>
		<h2 class={sectionTitleClass}>Identificação</h2>
		<div class="grid grid-cols-1 gap-5 sm:grid-cols-4">
			<div class="flex flex-col gap-1 sm:col-span-3">
				<label for="orgao-nome" class={labelClass}
					>Nome completo <span class="text-danger">*</span></label
				>
				<input
					id="orgao-nome"
					type="text"
					required
					maxlength="255"
					bind:value={nome}
					class={inputClass}
				/>
			</div>
			<div class="flex flex-col gap-1">
				<label for="orgao-sigla" class={labelClass}>Sigla <span class="text-danger">*</span></label>
				<input
					id="orgao-sigla"
					type="text"
					required
					maxlength="50"
					value={sigla}
					oninput={uppercaseSigla}
					class="{inputClass} font-mono uppercase tracking-wide"
				/>
			</div>
		</div>
	</section>

	<!-- Posição na hierarquia -->
	<section class={cardClass}>
		<h2 class={sectionTitleClass}>Posição na hierarquia</h2>
		<div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
			<div class="flex flex-col gap-1">
				<label for="orgao-tipo" class={labelClass}>Tipo <span class="text-danger">*</span></label>
				<select id="orgao-tipo" required bind:value={tipoId} class={inputClass}>
					<option value="">— selecione —</option>
					{#each tipoOptions as tipo (tipo.id)}
						<option value={String(tipo.id)}>{tipo.nome}</option>
					{/each}
				</select>
			</div>

			<div class="flex flex-col gap-1">
				<span class={labelClass}
					>Órgão pai {#if !isRoot}<span class="text-danger">*</span>{/if}</span
				>
				{#if isRoot}
					<input
						type="text"
						value="— raiz da hierarquia —"
						disabled
						class="{inputClass} opacity-70"
					/>
				{:else}
					<!-- Combobox de pai com busca (espelha #paiCombo do orgao_form.html). -->
					<div class="pai-combo">
						<input
							id="orgao-pai"
							type="text"
							placeholder="Digite para buscar um órgão pai..."
							autocomplete="off"
							role="combobox"
							aria-expanded={comboOpen}
							aria-controls="pai-combo-list"
							aria-autocomplete="list"
							required={paiId === ''}
							value={comboText}
							oninput={onComboInput}
							onfocus={() => (comboOpen = true)}
							onkeydown={onComboKeydown}
							onblur={() => setTimeout(() => (comboOpen = false), 120)}
							class={inputClass}
						/>
						<!-- Hidden mantém o id selecionado para o submit (string). -->
						<input type="hidden" value={paiId} />
						{#if comboOpen}
							<ul id="pai-combo-list" role="listbox" class="pai-combo-dropdown">
								{#each comboFiltered as pai, i (pai.id)}
									<li role="option" aria-selected={String(pai.id) === paiId}>
										<button
											type="button"
											class="pai-combo-option"
											class:active={i === activeIndex}
											onmousedown={(e) => {
												e.preventDefault();
												selectPai(pai.id, `${pai.sigla} — ${pai.nome}`);
											}}
										>
											{pai.sigla} — {pai.nome}
										</button>
									</li>
								{/each}
								{#if comboFiltered.length === 0}
									<li class="pai-combo-empty" role="presentation">
										Nenhum órgão pai encontrado
									</li>
								{/if}
							</ul>
						{/if}
					</div>
					<p class="text-xs text-text-muted">
						Apenas pais com hierarquia superior ao tipo escolhido são válidos (validado ao
						salvar).
					</p>
				{/if}
			</div>
		</div>
	</section>

	<!-- Referência SIORG e vigência -->
	<section class={cardClass}>
		<h2 class={sectionTitleClass}>Referência SIORG e vigência</h2>
		<div class="grid grid-cols-1 gap-5 sm:grid-cols-3">
			<div class="flex flex-col gap-1">
				<label for="orgao-codigo" class={labelClass}>Código externo</label>
				<input
					id="orgao-codigo"
					type="text"
					placeholder="SIORG ou outro código"
					bind:value={codigoExterno}
					class={inputClass}
				/>
			</div>
			<div class="flex flex-col gap-1">
				<label for="orgao-inicio" class={labelClass}>Início de vigência</label>
				<input id="orgao-inicio" type="date" bind:value={dataInicio} class={inputClass} />
			</div>
			<div class="flex flex-col gap-1">
				<label for="orgao-fim" class={labelClass}>Fim de vigência</label>
				<input id="orgao-fim" type="date" bind:value={dataFim} class={inputClass} />
			</div>
		</div>
	</section>

	<!-- Ordenação e status -->
	<section class={cardClass}>
		<h2 class={sectionTitleClass}>Ordenação e status</h2>
		<div class="grid grid-cols-1 items-end gap-5 sm:grid-cols-3">
			<div class="flex flex-col gap-1">
				<label for="orgao-ordem" class={labelClass}>Ordem entre irmãos</label>
				<input id="orgao-ordem" type="number" min="0" bind:value={ordem} class={inputClass} />
			</div>
			<div class="flex items-center gap-2">
				<input
					id="orgao-ativo"
					type="checkbox"
					bind:checked={ativo}
					class="h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-primary-500"
				/>
				<label for="orgao-ativo" class="text-sm text-text-primary">Órgão ativo</label>
			</div>
		</div>
	</section>
</div>

<style>
	/* Combobox de pai (espelha o <style> inline de orgao_form.html). Tokens
	   semânticos para dark mode. */
	.pai-combo {
		position: relative;
	}
	.pai-combo-dropdown {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		max-height: 280px;
		overflow-y: auto;
		list-style: none;
		margin: 0;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 10px;
		box-shadow: var(--ds-shadow-lg);
		z-index: 50;
		padding: 4px;
	}
	.pai-combo-option {
		display: block;
		width: 100%;
		text-align: left;
		padding: 8px 10px;
		border: 0;
		background: transparent;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.9rem;
		color: var(--color-text-primary);
		line-height: 1.3;
	}
	.pai-combo-option:hover,
	.pai-combo-option.active {
		background: var(--color-surface-muted);
	}
	.pai-combo-empty {
		padding: 10px;
		color: var(--color-text-muted);
		font-size: 0.85rem;
		text-align: center;
	}
</style>
