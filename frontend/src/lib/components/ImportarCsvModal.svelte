<script lang="ts">
	/**
	 * Modal de importação de projetos via CSV (Admin) em quatro estados — modo,
	 * arquivo, revisão e conclusão. A análise (`POST /api/projetos/importar-csv/analise`)
	 * roda ao receber o arquivo; o envio reusa o MESMO `File` com `mapeamento` e `modo`.
	 */
	import { tick, untrack } from 'svelte';
	import { fade, fly, slide, type FlyParams } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { ApiClientError } from '$lib/api/client';
	import { analisarImportacaoCsv, importProjectsCsv } from '$lib/api/projects';
	import { confirmAction } from '$lib/stores/confirm';
	import { animateHeight } from '$lib/utils/animateHeight';
	import { delayedPending, type DelayedPending } from '$lib/utils/delayedPending';
	import { countMapped, hasField, hasTitulo, type ImportFieldMapping } from '$lib/utils/importMappingState';
	import type { AnaliseImportacao, ImportModo, ImportProjectsResultV2 } from '$lib/types/importExport';
	import type { ProjectsListOptions } from '$lib/types/projects';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import OrgaoTreeSelect from '$lib/components/OrgaoTreeSelect.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import ImportCsvMapping from '$lib/components/ImportCsvMapping.svelte';
	import ImportCsvModoStep from '$lib/components/ImportCsvModoStep.svelte';
	import ImportCsvSucesso from '$lib/components/ImportCsvSucesso.svelte';

	type EstadoImportacao = 'modo' | 'arquivo' | 'revisao' | 'sucesso';

	interface Props {
		open: boolean;
		options: ProjectsListOptions | null;
		onClose: () => void;
		onImported: (count: number) => void;
	}

	let { open, options, onClose, onImported }: Props = $props();
	const STATUS_OPTIONS = ['Vigente', 'Suspenso', 'Finalizado'];
	const STATUS_DOT: Record<string, string> = {
		Vigente: 'var(--ds-color-fill-success)',
		Suspenso: 'var(--ds-color-fill-warning)',
		Finalizado: 'var(--ds-color-status-finalizada)'
	};
	const CLASSE_ESTADO = 'flex flex-col gap-3 focus:outline-none [grid-area:1/1]';
	const CLASSE_LINK =
		'shrink-0 rounded-sm text-xs text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
	const CLASSE_LABEL = 'text-sm font-semibold text-text-secondary';
	const CLASSE_CAMADA = 'pointer-events-none transition-opacity duration-fast [grid-area:1/1]';
	const CLASSE_PRIMARIO =
		'inline-flex h-9 items-center justify-center rounded-md bg-brand text-sm font-semibold text-on-brand shadow-sm transition-ui hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand active:scale-[0.98] active:[transition-duration:90ms] disabled:cursor-not-allowed';

	let estado = $state<EstadoImportacao>('modo');
	let modo = $state<ImportModo>('simples');
	let file = $state<File | null>(null);
	let analise = $state<AnaliseImportacao | null>(null);
	let mapping = $state<ImportFieldMapping>({});
	let mappingExpandido = $state<boolean>(false);
	let maisOpcoesAberto = $state<boolean>(false);
	let orgaoId = $state<string>('');
	let status = $state<string>('Vigente');
	let deliveryType = $state<string>('');
	let specialProject = $state<string>('');
	let analisando = $state<boolean>(false);
	let importando = $state<boolean>(false);
	let analiseErro = $state<string>('');
	let importErro = $state<string>('');
	let resultado = $state<ImportProjectsResultV2 | null>(null);
	let anuncioSucesso = $state<string>('');
	let profundidadeDrag = $state<number>(0);
	// Só depois da abertura o fly de troca de estado deve tocar — no mount ele brigaria com a entrada do painel.
	let jaAbriu = $state<boolean>(false);
	// Invalida continuações de análise/import antigas (arquivo trocado, modal fechado).
	let sessaoFluxo = 0;
	const ORDEM_ESTADOS: Record<EstadoImportacao, number> = { modo: 0, arquivo: 1, revisao: 2, sucesso: 3 };
	// Voltar (trocar arquivo) entra de cima; avançar entra de baixo.
	let sentido: 1 | -1 = 1;

	let corpoEl = $state<HTMLDivElement | null>(null);
	let modoEl = $state<HTMLDivElement | null>(null);
	let arquivoEl = $state<HTMLDivElement | null>(null);
	let revisaoEl = $state<HTMLFormElement | null>(null);
	let sucessoEl = $state<HTMLDivElement | null>(null);
	let sucessoComp = $state<{ focusConcluir: () => void } | null>(null);
	let fileInputEl = $state<HTMLInputElement | null>(null);
	const analisePendente = delayedPending({ showAfterMs: 150, minVisibleMs: 350 });
	const importPendente = delayedPending({ showAfterMs: 150, minVisibleMs: 350 });
	const orgaoOptions = $derived(options?.orgaos_options ?? []);
	// Adapta a lista plana ao shape numérico do OrgaoTreeSelect.
	const orgaoTreeOptions = $derived<OrgaoSelectOption[]>(
		orgaoOptions.map((o) => ({ ...o, value: Number(o.value) }))
	);
	const statusMenuOptions = $derived<SelectMenuOption[]>(
		STATUS_OPTIONS.map((opt) => ({ value: opt, label: opt, dot: STATUS_DOT[opt] }))
	);
	const deliveryMenuOptions = $derived<SelectMenuOption[]>(
		(options?.delivery_types_options ?? []).map((opt) => ({ value: opt, label: opt }))
	);
	const specialMenuOptions = $derived<SelectMenuOption[]>(
		(options?.special_projects_options ?? []).map((opt) => ({ value: opt, label: opt }))
	);

	const dragAtivo = $derived(profundidadeDrag > 0);
	const modoComEtapas = $derived(modo === 'com_etapas');
	const rotuloModo = $derived(modoComEtapas ? 'Projetos com etapas' : 'Somente projetos');
	const tituloMapeado = $derived(hasTitulo(mapping));
	const colunasMapeadas = $derived(countMapped(mapping));
	const obrigatoriosMapeados = $derived(
		tituloMapeado &&
			(!modoComEtapas || (hasField(mapping, 'ref_projeto') && hasField(mapping, 'etapa')))
	);
	const tabelaVisivel = $derived(mappingExpandido || !obrigatoriosMapeados);
	const motivoBloqueio = $derived.by<string>(() => {
		if (!tituloMapeado) return 'Mapeie a coluna do título.';
		if (modoComEtapas && !hasField(mapping, 'ref_projeto')) return 'Mapeie a coluna Ref do projeto.';
		if (modoComEtapas && !hasField(mapping, 'etapa')) return 'Mapeie a coluna Etapa.';
		if (orgaoId.trim().length === 0) return 'Escolha a área de destino.';
		return '';
	});
	const podeImportar = $derived(motivoBloqueio === '');
	const rotuloImportar = $derived(
		modoComEtapas ? 'Importar' : `Importar ${analise?.total_linhas ?? 0} projetos`
	);
	const rotuloSucesso = $derived(
		resultado === null
			? ''
			: modoComEtapas
				? `${resultado.imported_count} projetos e ${resultado.etapas_criadas} etapas importados`
				: `${resultado.imported_count} projetos importados`
	);
	// No com etapas, linha sem título é erro 422 — só sobram linhas em branco.
	const descricaoIgnoradas = $derived(
		modoComEtapas ? 'linha(s) em branco ignorada(s).' : 'linha(s) ignorada(s) por não ter título.'
	);
	const dropzoneEstadoClasse = $derived(
		dragAtivo
			? 'border-brand bg-wash-brand'
			: analisando
				? 'border-border-subtle bg-surface'
				: 'border-border-subtle bg-surface hover:border-border-strong hover:bg-surface-muted'
	);
	const dropzoneClasse = $derived(`grid min-h-[200px] w-full rounded-lg border border-dashed transition-ui focus:outline-none focus-visible:ring-2 focus-visible:ring-brand ${dropzoneEstadoClasse}`);
	const camada = (extra: string, visivel: boolean): string =>
		`${CLASSE_CAMADA} ${extra} ${visivel ? 'opacity-100' : 'opacity-0'}`;
	const spanBotao = (visivel: boolean): string =>
		`inline-flex items-center justify-center gap-2 transition-opacity duration-fast [grid-area:1/1] ${visivel ? 'opacity-100' : 'opacity-0'}`;
	const voar = (): FlyParams => ({ y: 8 * sentido, duration: prefersReducedMotion.current ? 0 : 200, easing: cubicOut, delay: prefersReducedMotion.current ? 0 : 60 });
	const entrar = (): FlyParams => (jaAbriu ? voar() : { duration: 0 });
	const sumir = () => ({ duration: prefersReducedMotion.current ? 0 : 120 });
	const deslizar = () => ({ duration: prefersReducedMotion.current ? 0 : 240, easing: cubicOut });

	// Reseta o formulário sempre que o modal abre; ao fechar, mata timers.
	// untrack: resetarFormulario lê `orgaoOptions` — sem ele uma revalidação de
	// `options` com o modal aberto apagaria arquivo, análise e mapeamento.
	$effect(() => {
		if (open) {
			untrack(() => resetarFormulario());
			void tick().then(() => (jaAbriu = true));
			return;
		}
		jaAbriu = false;
		sessaoFluxo += 1;
		analisePendente.reset();
		importPendente.reset();
	});

	// Idempotente: `options` costuma chegar depois da abertura, e o órgão único precisa entrar quando chegar.
	$effect(() => {
		if (open && orgaoId === '' && orgaoOptions.length === 1) orgaoId = orgaoOptions[0].value;
	});

	// A região live é persistente e o texto entra num flush POSTERIOR — nó criado já com conteúdo não é anunciado.
	$effect(() => {
		if (estado !== 'sucesso' || resultado === null) {
			anuncioSucesso = '';
			return;
		}
		const partes = [`${rotuloSucesso}.`];
		if (resultado.ignored_count > 0) {
			partes.push(`${resultado.ignored_count} ${descricaoIgnoradas}`);
		}
		if (resultado.adjusted_count > 0) {
			partes.push(`Valores não reconhecidos em ${resultado.adjusted_count} linha(s) receberam os padrões escolhidos.`);
		}
		const texto = partes.join(' ');
		void tick().then(() => (anuncioSucesso = texto));
	});

	// Drag na janela toda; dragenter/dragleave disparam nos filhos, o contador de profundidade (>0 = ativo) mata o flicker.
	// O preventDefault vale com o modal aberto em QUALQUER estado: soltar um arquivo sem ele faz o navegador abrir o CSV e derrubar a SPA.
	$effect(() => {
		if (!open) return;
		const aoDrag = (evento: DragEvent): void => {
			if (!evento.dataTransfer?.types.includes('Files')) return;
			if (evento.type === 'dragleave') {
				profundidadeDrag = Math.max(0, profundidadeDrag - 1);
				return;
			}
			evento.preventDefault();
			const aceitaArquivo = estado === 'arquivo' && !analisando;
			if (evento.type === 'dragenter' && aceitaArquivo) profundidadeDrag += 1;
			if (evento.type !== 'drop') return;
			profundidadeDrag = 0;
			if (!aceitaArquivo) return;
			const solto = evento.dataTransfer.files?.[0];
			if (solto) void receberArquivo(solto);
		};
		const eventos = ['dragenter', 'dragleave', 'dragover', 'drop'] as const;
		for (const nome of eventos) window.addEventListener(nome, aoDrag);
		return () => {
			profundidadeDrag = 0;
			for (const nome of eventos) window.removeEventListener(nome, aoDrag);
		};
	});

	function resetarFormulario(): void {
		sessaoFluxo += 1;
		estado = 'modo';
		modo = 'simples';
		file = null;
		analise = null;
		resultado = null;
		mapping = {};
		mappingExpandido = maisOpcoesAberto = analisando = importando = false;
		analiseErro = importErro = deliveryType = specialProject = '';
		status = 'Vigente';
		orgaoId = orgaoOptions.length === 1 ? orgaoOptions[0].value : '';
		profundidadeDrag = 0;
		analisePendente.reset();
		importPendente.reset();
	}

	/** Espera o indicador cumprir os 350ms mínimos antes de trocar de tela. */
	function aguardarPendenteSumir(pendente: DelayedPending): Promise<void> {
		return new Promise((resolve) => {
			let liberar: () => void = () => {};
			liberar = pendente.subscribe((visivel) => {
				if (visivel) return;
				queueMicrotask(() => liberar());
				resolve();
			});
		});
	}

	// Foca o container que entra ANTES da saída terminar e anima a altura MEDIDA.
	async function trocarEstado(novo: EstadoImportacao): Promise<void> {
		const alturaAntes = corpoEl?.offsetHeight ?? 0;
		sentido = ORDEM_ESTADOS[novo] >= ORDEM_ESTADOS[estado] ? 1 : -1;
		estado = novo;
		await tick();
		const entrada =
			novo === 'modo' ? modoEl : novo === 'arquivo' ? arquivoEl : novo === 'revisao' ? revisaoEl : sucessoEl;
		if (novo === 'sucesso') sucessoComp?.focusConcluir();
		else entrada?.focus({ preventScroll: true });
		if (entrada) animarCorpo(alturaAntes, entrada.offsetHeight);
	}

	// Overflow escondido só durante a animação — no repouso decaparia o painel absoluto do OrgaoTreeSelect.
	function animarCorpo(de: number, para: number): void {
		if (!corpoEl) return;
		const animacao = animateHeight(corpoEl, de, para);
		if (animacao === null) return;
		corpoEl.style.overflow = 'hidden';
		const liberar = (): void => void corpoEl?.style.removeProperty('overflow');
		animacao.addEventListener('finish', liberar);
		animacao.addEventListener('cancel', liberar);
	}

	function aoEscolherArquivo(event: Event): void {
		const input = event.currentTarget as HTMLInputElement;
		const escolhido = input.files?.[0] ?? null;
		input.value = '';
		if (escolhido) void receberArquivo(escolhido);
	}

	async function receberArquivo(novo: File): Promise<void> {
		if (analisando || estado !== 'arquivo') return;
		const sessao = ++sessaoFluxo;
		file = novo;
		analiseErro = '';
		analisando = true;
		analisePendente.start();
		const dados = new FormData();
		dados.append('arquivo', novo);
		try {
			const recebida = await analisarImportacaoCsv(dados, modo);
			await concluirAnalise(sessao, () => {
				prepararRevisao(recebida);
				void trocarEstado('revisao');
			});
		} catch (err) {
			await concluirAnalise(sessao, () => {
				file = null;
				if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
				analiseErro = err instanceof Error ? err.message : 'Falha ao ler o arquivo CSV.';
			});
		}
	}

	async function concluirAnalise(sessao: number, aplicar: () => void): Promise<void> {
		analisePendente.stop();
		await aguardarPendenteSumir(analisePendente);
		if (sessao !== sessaoFluxo || !open) return;
		analisando = false;
		aplicar();
	}

	function prepararRevisao(recebida: AnaliseImportacao): void {
		analise = recebida;
		const inicial: ImportFieldMapping = {};
		for (const coluna of recebida.colunas) inicial[coluna.indice] = coluna.campo;
		mapping = inicial;
		mappingExpandido =
			!hasTitulo(inicial) ||
			(modo === 'com_etapas' && !(hasField(inicial, 'ref_projeto') && hasField(inicial, 'etapa')));
		maisOpcoesAberto = false;
		importErro = '';
	}

	function trocarArquivo(): void {
		sessaoFluxo += 1;
		file = null;
		analise = null;
		mapping = {};
		analiseErro = importErro = '';
		void trocarEstado('arquivo');
	}

	// Trocar o modo invalida a análise — o catálogo de campos é por modo.
	function voltarAoModo(): void {
		sessaoFluxo += 1;
		file = null;
		analise = null;
		mapping = {};
		analiseErro = importErro = '';
		void trocarEstado('modo');
	}

	function montarFormularioDeImportacao(arquivo: File): FormData {
		const dados = new FormData();
		dados.append('arquivo', arquivo);
		dados.append('orgao_id', orgaoId);
		dados.append('status', status);
		if (deliveryType) dados.append('delivery_type', deliveryType);
		if (specialProject) dados.append('special_project', specialProject);
		// Só as colunas não-ignoradas: `{"0":"titulo","3":"descricao"}`.
		const envio = Object.entries(mapping).filter(([, campo]) => campo !== null);
		dados.append('mapeamento', JSON.stringify(Object.fromEntries(envio)));
		return dados;
	}

	async function importar(): Promise<void> {
		if (importando || !podeImportar || file === null || analise === null) return;
		const sessao = sessaoFluxo;
		importando = true;
		importErro = '';
		importPendente.start();
		try {
			const recebido = await importProjectsCsv(montarFormularioDeImportacao(file), modo);
			await concluirImport(sessao, () => {
				resultado = recebido;
				void trocarEstado('sucesso');
			});
		} catch (err) {
			await concluirImport(sessao, () => {
				if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
				importErro = err instanceof Error ? err.message : 'Falha ao importar o CSV.';
			});
		}
	}

	async function concluirImport(sessao: number, aplicar: () => void): Promise<void> {
		importPendente.stop();
		await aguardarPendenteSumir(importPendente);
		if (sessao !== sessaoFluxo || !open) return;
		importando = false;
		aplicar();
	}

	function onSubmitRevisao(event: SubmitEvent): void {
		event.preventDefault();
		void importar();
	}

	/** Enter com o foco no próprio container da revisão também importa. */
	function onRevisaoKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Enter' || event.target !== event.currentTarget) return;
		event.preventDefault();
		void importar();
	}

	function concluir(): void {
		if (!open) return;
		if (resultado !== null) onImported(resultado.imported_count);
	}

	// Esc/backdrop: sem arquivo fecha direto; com arquivo confirma o descarte; na conclusão avisa a lista via onImported.
	async function requestClose(): Promise<void> {
		if (!open || importando) return;
		if (estado === 'sucesso') return concluir();
		if (file === null) return onClose();
		const aceitou = await confirmAction({
			title: 'Descartar a importação?',
			description: `O arquivo "${file.name}" e os atributos escolhidos serão descartados.`,
			tone: 'warning',
			icon: 'draft',
			confirmLabel: 'Descartar importação',
			cancelLabel: 'Continuar editando'
		});
		if (aceitou) onClose();
	}

	const fechar = (): void => void requestClose();
</script>

<Modal {open} labelId="importar-projetos-title" maxWidth="max-w-xl" onBackdrop={fechar}>
		<div class="flex flex-col gap-4">
			<h2 id="importar-projetos-title" class="font-heading text-xl font-bold text-text-primary">Importar projetos</h2>
			<div bind:this={corpoEl} class="grid items-start">
				{#if estado === 'modo'}
					<div bind:this={modoEl} tabindex="-1" class={CLASSE_ESTADO} in:fly={entrar()} out:fade={sumir()}>
						<ImportCsvModoStep {modo} classeLink={CLASSE_LINK} onSelect={(novo) => (modo = novo)} />
						<div class="flex justify-end gap-2">
							<Button variant="secondary" onclick={fechar}>Cancelar</Button>
							<button type="button" onclick={() => void trocarEstado('arquivo')} class="px-6 {CLASSE_PRIMARIO}">Continuar</button>
						</div>
					</div>
				{:else if estado === 'arquivo'}
					<div bind:this={arquivoEl} tabindex="-1" class={CLASSE_ESTADO} in:fly={entrar()} out:fade={sumir()}>
						<div class="flex items-center justify-between gap-3">
							<span class="min-w-0 truncate text-sm text-text-secondary">Formato: <span class="font-medium text-text-primary">{rotuloModo}</span></span>
							<button type="button" onclick={voltarAoModo} disabled={analisando} class="{CLASSE_LINK} disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:no-underline">alterar</button>
						</div>
						{#if analiseErro}
							<div transition:slide={deslizar()}>
								<StateBanner tone="danger" title="Não foi possível ler o arquivo." description={analiseErro} />
							</div>
						{/if}
						<button type="button" onclick={() => !analisando && fileInputEl?.click()} aria-label="Escolher arquivo CSV" aria-busy={analisando} class={dropzoneClasse}>
							<span class={camada('flex flex-col items-center justify-center gap-1', !dragAtivo && !analisando)} aria-hidden={dragAtivo || analisando}>
								<span class="text-md font-medium text-text-primary">Solte o arquivo CSV aqui</span>
								<span class="text-sm text-text-muted">ou clique para escolher</span>
							</span>
							<span class={camada('flex items-center justify-center text-md font-medium text-text-primary', dragAtivo)} aria-hidden="true">Pode soltar</span>
							<span class={camada('flex flex-col items-center justify-center gap-2', analisando)} aria-hidden={!analisando}>
								<span class="flex max-w-[20rem] flex-col gap-1">
									<span class="truncate text-sm font-medium text-text-primary">{file?.name}</span>
									<span class="skeleton-shimmer h-0.5 w-full rounded-full transition-opacity duration-fast {$analisePendente ? 'opacity-100' : 'opacity-0'}"></span>
								</span>
								<span class="text-xs text-text-muted transition-opacity duration-fast {$analisePendente ? 'opacity-100' : 'opacity-0'}">Lendo o arquivo…</span>
							</span>
						</button>
						<span class="sr-only" aria-live="polite">{$analisePendente ? 'Lendo o arquivo…' : ''}</span>
						<input bind:this={fileInputEl} type="file" accept=".csv,text/csv" class="hidden" onchange={aoEscolherArquivo} />
					</div>
				{:else if estado === 'revisao'}
					<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
					<form bind:this={revisaoEl} tabindex="-1" class={CLASSE_ESTADO} onsubmit={onSubmitRevisao} onkeydown={onRevisaoKeydown} in:fly={entrar()} out:fade={sumir()}>
						{#if file !== null && analise !== null}
							<div class="flex items-center justify-between gap-3">
								<span class="min-w-0 truncate text-sm text-text-secondary">
									<span class="font-medium text-text-primary">{file.name}</span> · {analise.total_linhas} linhas
								</span>
								<button type="button" onclick={trocarArquivo} disabled={importando} class="{CLASSE_LINK} disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:no-underline">trocar</button>
							</div>
							{#if tituloMapeado}
								<div class="flex items-center justify-between gap-3">
									<span class="text-sm text-text-secondary">{colunasMapeadas} de {analise.colunas.length} colunas reconhecidas</span>
									<button type="button" onclick={() => (mappingExpandido = !mappingExpandido)} aria-expanded={tabelaVisivel} class={CLASSE_LINK}>Revisar colunas</button>
								</div>
							{:else}
								<p class="text-sm text-attention">Nenhuma coluna foi reconhecida como Título — escolha abaixo.</p>
							{/if}
							{#if tabelaVisivel}
								<div transition:slide={deslizar()}>
									<ImportCsvMapping colunas={analise.colunas} campos={analise.campos} {mapping} disabled={importando} onChange={(proximo) => (mapping = proximo)} />
								</div>
							{/if}
							<div class="flex flex-col gap-1 text-sm">
								<label for="importar-projetos-orgao" class={CLASSE_LABEL}>Área de destino</label>
								<OrgaoTreeSelect id="importar-projetos-orgao" options={orgaoTreeOptions} value={orgaoId ? Number(orgaoId) : null} onSelect={(v) => (orgaoId = v == null ? '' : String(v))} placeholder="Selecione a área…" ariaLabel="Área de destino (obrigatório)" />
							</div>
							<div class="flex flex-col gap-2">
								<button type="button" onclick={() => (maisOpcoesAberto = !maisOpcoesAberto)} aria-expanded={maisOpcoesAberto} class="flex items-center gap-1.5 self-start rounded-sm text-sm font-semibold text-text-secondary transition-colors duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand">
									Mais opções
									<i class="fas fa-chevron-down text-2xs text-text-muted transition-transform duration-fast" style:transform={maisOpcoesAberto ? 'rotate(180deg)' : 'none'} aria-hidden="true"></i>
								</button>
								{#if maisOpcoesAberto}
									<div transition:slide={deslizar()} class="flex flex-col gap-2">
										<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
											<div class="flex flex-col gap-1 text-sm">
												<label for="importar-projetos-status" class={CLASSE_LABEL}>Status padrão</label>
												<SelectMenu id="importar-projetos-status" options={statusMenuOptions} value={status} onSelect={(v) => (status = v ?? status)} ariaLabel="Status padrão" />
											</div>
											<div class="flex flex-col gap-1 text-sm">
												<label for="importar-projetos-delivery" class={CLASSE_LABEL}>Tipo de entrega</label>
												<SelectMenu id="importar-projetos-delivery" options={deliveryMenuOptions} value={deliveryType || null} onSelect={(v) => (deliveryType = v ?? '')} allowAll allLabel="—" ariaLabel="Tipo de entrega" />
											</div>
											<div class="flex flex-col gap-1 text-sm">
												<label for="importar-projetos-special" class={CLASSE_LABEL}>Projeto especial</label>
												<SelectMenu id="importar-projetos-special" options={specialMenuOptions} value={specialProject || null} onSelect={(v) => (specialProject = v ?? '')} allowAll allLabel="—" ariaLabel="Projeto especial" />
											</div>
										</div>
										<p class="text-xs text-text-muted">Aplicados apenas às linhas em que o CSV não informar o valor.</p>
									</div>
								{/if}
							</div>
							{#if importErro}
								<div transition:slide={deslizar()}>
									<StateBanner tone="danger" title="Não foi possível importar." description={importErro} />
								</div>
							{/if}
							<div class="grid min-h-[1rem]" aria-live="polite">
								{#if motivoBloqueio}
									<span class="text-xs text-text-muted [grid-area:1/1]">{motivoBloqueio}</span>
								{/if}
							</div>
							<div class="flex justify-end gap-2">
								<Button variant="secondary" onclick={fechar} disabled={importando}>Cancelar</Button>
								<button type="submit" disabled={!podeImportar} aria-disabled={importando} aria-busy={importando} class="min-w-[13rem] px-4 {CLASSE_PRIMARIO}">
									<span class="sr-only" aria-live="polite">{$importPendente ? 'Importando…' : rotuloImportar}</span>
									<span class="grid" aria-hidden="true">
										<span class={spanBotao(!$importPendente)}>{rotuloImportar}</span>
										<span class={spanBotao($importPendente)}>
											<i class="fas fa-spinner {$importPendente ? 'fa-spin' : ''}" style="--fa-animation-duration: 0.8s"></i>
											Importando…
										</span>
									</span>
								</button>
							</div>
						{/if}
					</form>
				{:else}
					<div bind:this={sucessoEl} tabindex="-1" class="flex flex-col items-center gap-3 py-6 text-center focus:outline-none [grid-area:1/1]" in:fly={entrar()} out:fade={sumir()}>
						{#if resultado !== null}
							<ImportCsvSucesso bind:this={sucessoComp} {resultado} rotulo={rotuloSucesso} {descricaoIgnoradas} classePrimario={CLASSE_PRIMARIO} onConcluir={concluir} />
						{/if}
					</div>
				{/if}
			</div>
			<p class="sr-only" role="status">{anuncioSucesso}</p>
		</div>
</Modal>
