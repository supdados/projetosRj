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

	// Reproduz .account-input / .account-label do original (20-glass-forms-and-admin.css):
	// input com borda sutil, raio md, foco com ring da marca; label em caixa alta.
	const inputClass =
		'rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const labelClass = 'text-xs font-semibold uppercase tracking-wide text-text-muted';
	const sectionTitleClass =
		'font-heading text-md font-semibold text-text-primary';
	const cardClass =
		'flex flex-col gap-4 rounded-lg border border-border-subtle bg-surface p-5 shadow-sm';
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
					bind:value={sigla}
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
					<select id="orgao-pai" required bind:value={paiId} class={inputClass}>
						<option value="">Selecione…</option>
						{#each candidatosPai as pai (pai.id)}
							<option value={String(pai.id)}>{pai.sigla} — {pai.nome}</option>
						{/each}
					</select>
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
