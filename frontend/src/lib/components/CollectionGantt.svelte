<script lang="ts">
	/**
	 * Gantt do cronograma da coleção (tela 3c, seção "Cronograma das etapas").
	 *
	 * Três escalas ancoradas no hoje, trocadas pelo segmented control do header:
	 * Mês (mês corrente, colunas semanais 01/08/15/22/29), Semestre (default,
	 * mês −2..+4, gridlines mensais) e Ano (mês −5..+6 — ancorado no hoje, e não
	 * no ano civil, para a linha HOJE ficar perto do centro em qualquer data).
	 * Cada projeto é uma linha; as barras são as etapas datadas
	 * (`CronogramaEtapa`), posicionadas por fração mês+dia para casarem com as
	 * gridlines mesmo com meses de 28–31 dias. O estado da barra (`barra`) já
	 * chega decidido do backend — aqui só se pinta. Etapas fora da janela são
	 * clampadas na borda (ou omitidas se inteiramente fora); barra mínima de 6px
	 * garante etapas pontuais visíveis. Etapas que se sobrepõem no tempo são
	 * empilhadas em sub-lanes (greedy por ordem de início) e a altura da linha
	 * cresce com o nº de lanes. Cada barra é focável e mostra tooltip com nome,
	 * período e status no hover/focus.
	 */
	import { base } from '$app/paths';
	import FilterChipGroup from '$lib/components/FilterChipGroup.svelte';
	import type { BarraEtapa, CronogramaEtapa, CronogramaProjeto } from '$lib/types/collections';
	import { formatIsoDatePartsBR } from '$lib/utils/dateFormat';

	const { projetos }: { projetos: CronogramaProjeto[] } = $props();

	type EscalaGantt = 'mes' | 'semestre' | 'ano';

	const ESCALAS: { id: EscalaGantt; label: string }[] = [
		{ id: 'mes', label: 'Mês' },
		{ id: 'semestre', label: 'Semestre' },
		{ id: 'ano', label: 'Ano' }
	];

	const MESES_ANTES: Record<EscalaGantt, number> = { mes: 0, semestre: 2, ano: 5 };
	const TOTAL_MESES: Record<EscalaGantt, number> = { mes: 1, semestre: 7, ano: 12 };

	let escala = $state<EscalaGantt>('semestre');

	const hoje = new Date();
	const diasNoMesAtual = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0).getDate();

	const totalMeses = $derived(TOTAL_MESES[escala]);
	const inicioJanela = $derived(
		new Date(hoje.getFullYear(), hoje.getMonth() - MESES_ANTES[escala], 1)
	);

	const MES_CURTO = [
		'Jan',
		'Fev',
		'Mar',
		'Abr',
		'Mai',
		'Jun',
		'Jul',
		'Ago',
		'Set',
		'Out',
		'Nov',
		'Dez'
	];

	interface ColunaGantt {
		rotulo: string;
		widthPct: number;
	}

	function colunasMensais(): ColunaGantt[] {
		return Array.from({ length: totalMeses }, (_, i) => {
			const mes = new Date(inicioJanela.getFullYear(), inicioJanela.getMonth() + i, 1);
			const nome = MES_CURTO[mes.getMonth()];
			// Janeiro carrega o ano curto para desambiguar janelas que viram o ano.
			const rotulo = mes.getMonth() === 0 ? `${nome}/${String(mes.getFullYear()).slice(2)}` : nome;
			return { rotulo, widthPct: 100 / totalMeses };
		});
	}

	function colunasSemanais(): ColunaGantt[] {
		const mm = String(hoje.getMonth() + 1).padStart(2, '0');
		return [1, 8, 15, 22, 29]
			.filter((dia) => dia <= diasNoMesAtual)
			.map((dia) => ({
				rotulo: `${String(dia).padStart(2, '0')}/${mm}`,
				widthPct: ((Math.min(dia + 6, diasNoMesAtual) - dia + 1) / diasNoMesAtual) * 100
			}));
	}

	const colunas = $derived(escala === 'mes' ? colunasSemanais() : colunasMensais());

	// Gridline no início de cada coluna; 0% coincide com a borda esquerda da área.
	const gridlinePcts = $derived.by(() => {
		const pcts: number[] = [];
		let acumulado = 0;
		for (const coluna of colunas) {
			pcts.push(acumulado);
			acumulado += coluna.widthPct;
		}
		return pcts;
	});

	const BARRA_CLASS: Record<BarraEtapa, string> = {
		concluida: 'bg-success-600 dark:bg-success-400',
		execucao: 'bg-brand',
		vencida: 'bg-fill-danger',
		prevista: 'bg-progress-track'
	};

	const BARRA_LABEL: Record<BarraEtapa, string> = {
		concluida: 'Concluída',
		execucao: 'Em execução',
		vencida: 'Vencida',
		prevista: 'Prevista'
	};

	const LEGENDA: BarraEtapa[] = ['concluida', 'execucao', 'vencida', 'prevista'];

	/** % da janela para um ISO YYYY-MM-DD; `new Date(iso)` interpretaria UTC e deslocaria o dia. */
	function pctNaJanela(iso: string, fimDoDia = false): number {
		const [ano, mes, dia] = iso.split('-').map(Number);
		const meses = (ano - inicioJanela.getFullYear()) * 12 + (mes - 1 - inicioJanela.getMonth());
		const diasNoMes = new Date(ano, mes, 0).getDate();
		return ((meses + (dia - (fimDoDia ? 0 : 1)) / diasNoMes) / totalMeses) * 100;
	}

	const hojePct = $derived(
		((MESES_ANTES[escala] + (hoje.getDate() - 1) / diasNoMesAtual) / totalMeses) * 100
	);
	const hojeLeft = $derived(`calc(280px + (100% - 280px) * ${(hojePct / 100).toFixed(4)})`);

	function periodoEtapa(etapa: CronogramaEtapa): string {
		if (etapa.data_inicio && etapa.data_fim) {
			return `${formatIsoDatePartsBR(etapa.data_inicio)}–${formatIsoDatePartsBR(etapa.data_fim)}`;
		}
		return formatIsoDatePartsBR(etapa.data_fim ?? etapa.data_inicio);
	}

	interface BarraRender {
		key: number;
		leftPct: number;
		widthPct: number;
		lane: number;
		barra: BarraEtapa;
		nome: string;
		periodo: string;
		aria: string;
	}

	interface LinhaRender {
		barras: BarraRender[];
		lanes: number;
	}

	function barraDaEtapa(etapa: CronogramaEtapa): BarraRender | null {
		const inicioIso = etapa.data_inicio ?? etapa.data_fim;
		const fimIso = etapa.data_fim ?? etapa.data_inicio;
		if (!inicioIso || !fimIso) return null;
		const left = pctNaJanela(inicioIso);
		const right = pctNaJanela(fimIso, true);
		if (right < left) return null; // data_fim < data_inicio — etapa inconsistente, não desenha
		// right === 0 / left === 100 encostam na fronteira sem tocar a janela: inteiramente fora.
		if (right <= 0 || left >= 100) return null;
		const leftClamped = Math.max(0, left);
		const periodo = periodoEtapa(etapa);
		return {
			key: etapa.id,
			leftPct: leftClamped,
			widthPct: Math.max(Math.min(100, right) - leftClamped, 0),
			lane: 0,
			barra: etapa.barra,
			nome: etapa.nome,
			periodo,
			aria: `${etapa.nome} — ${periodo} (${BARRA_LABEL[etapa.barra]})`
		};
	}

	let areaBarrasWidth = $state(0);
	// Mínimo de 6px do render convertido em %, para alocar lanes no mesmo espaço visual das barras.
	const minPct = $derived(areaBarrasWidth > 0 ? 600 / areaBarrasWidth : 0);

	/** Greedy por ordem de início: cada barra cai na primeira lane livre no seu trecho visível. */
	function alocarLanes(barras: BarraRender[]): LinhaRender {
		const ordenadas = [...barras].sort((a, b) => a.leftPct - b.leftPct || b.widthPct - a.widthPct);
		const fimPorLane: number[] = [];
		for (const barra of ordenadas) {
			const leftVisual = Math.min(barra.leftPct, 100 - minPct);
			let lane = fimPorLane.findIndex((fim) => fim <= leftVisual);
			if (lane === -1) lane = fimPorLane.length;
			barra.lane = lane;
			fimPorLane[lane] = leftVisual + Math.max(barra.widthPct, minPct);
		}
		return { barras: ordenadas, lanes: Math.max(fimPorLane.length, 1) };
	}

	function linhaDoProjeto(projeto: CronogramaProjeto): LinhaRender {
		const barras = projeto.etapas
			.map(barraDaEtapa)
			.filter((barra): barra is BarraRender => barra !== null);
		return alocarLanes(barras);
	}

	// 1 lane = linha de 52px (visual original: barra de 14px com 19px de folga).
	const PASSO_LANE = 20;

	function alturaLinha(lanes: number): number {
		return PASSO_LANE * lanes + 32;
	}

	function topoBarra(lane: number): number {
		return 19 + lane * PASSO_LANE;
	}

	function resumoLinha(projeto: CronogramaProjeto): string {
		const datadas =
			projeto.etapas.length === 1 ? '1 etapa datada' : `${projeto.etapas.length} etapas datadas`;
		const semData = projeto.sem_data > 0 ? `, ${projeto.sem_data} sem data` : '';
		return `${projeto.nome}: ${datadas}${semData}`;
	}
</script>

<div class="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-4">
	<h2 class="m-0 text-base font-bold text-text-primary">Cronograma das etapas</h2>
	<FilterChipGroup
		label="Escala do cronograma"
		options={ESCALAS}
		value={escala}
		onchange={(id) => (escala = id as EscalaGantt)}
	/>
	<span class="ml-auto flex flex-wrap items-center gap-3 text-xs text-text-muted">
		{#each LEGENDA as barra (barra)}
			<span class="flex items-center gap-1.5">
				<span class="h-2 w-3.5 rounded {BARRA_CLASS[barra]}" aria-hidden="true"></span>
				{BARRA_LABEL[barra]}
			</span>
		{/each}
	</span>
</div>

{#if projetos.length === 0}
	<p class="m-0 px-5 py-6 text-center text-sm text-text-muted">
		Nenhum projeto na coleção para montar o cronograma.
	</p>
{:else}
	<div class="px-5 pb-5 pt-3">
		<div class="grid grid-cols-[280px_1fr] pb-7 text-xs font-medium text-text-secondary">
			<div>Projeto</div>
			<div class="flex text-center" bind:clientWidth={areaBarrasWidth}>
				{#each colunas as coluna, i (i)}
					<span class="truncate" style:width={`${coluna.widthPct.toFixed(3)}%`}>
						{coluna.rotulo}
					</span>
				{/each}
			</div>
		</div>
		<div class="relative border-t border-border-subtle">
			{#each gridlinePcts as pct, i (i)}
				<div
					class="absolute bottom-0 top-0 w-px bg-border-subtle"
					style:left={`calc(280px + (100% - 280px) * ${(pct / 100).toFixed(4)})`}
					aria-hidden="true"
				></div>
			{/each}
			<div
				class="absolute bottom-0 top-0 z-[2] w-0.5 rounded-full bg-brand"
				style:left={hojeLeft}
				aria-hidden="true"
			></div>
			<div
				class="absolute -top-6 z-[3] inline-flex h-5 -translate-x-1/2 items-center rounded-sm bg-brand px-2 text-2xs font-semibold text-on-brand"
				style:left={hojeLeft}
			>
				HOJE
			</div>
			{#each projetos as projeto (projeto.id)}
				{@const linha = linhaDoProjeto(projeto)}
				<div
					class="grid grid-cols-[280px_1fr] items-center border-b border-border-subtle last:border-b-0"
					style:height={`${alturaLinha(linha.lanes)}px`}
				>
					<div class="min-w-0 pr-4">
						<a
							href={`${base}/projetos/${projeto.id}`}
							class="block truncate text-sm font-medium text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							{projeto.nome}
						</a>
						<div class="truncate text-xs text-text-muted">
							<span class="font-mono">{projeto.id}</span>
							{#if projeto.orgao_sigla}
								<span> · {projeto.orgao_sigla}</span>
							{/if}
							{#if projeto.sem_data > 0}
								<span> · +{projeto.sem_data} sem data</span>
							{/if}
						</div>
					</div>
					<div class="relative h-full" role="group" aria-label={resumoLinha(projeto)}>
						{#each linha.barras as barra (barra.key)}
							<button
								type="button"
								class="group absolute h-3.5 cursor-default rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 {BARRA_CLASS[
									barra.barra
								]}"
								style:top={`${topoBarra(barra.lane)}px`}
								style:left={`min(${barra.leftPct.toFixed(3)}%, calc(100% - 6px))`}
								style:width={`max(${barra.widthPct.toFixed(3)}%, 6px)`}
								aria-label={barra.aria}
							>
								<span
									class="pointer-events-none invisible absolute bottom-full left-1/2 z-20 mb-1.5 flex w-max max-w-[280px] -translate-x-1/2 flex-col items-start gap-0.5 rounded-md border border-border-subtle bg-surface-elevated px-2.5 py-1.5 text-left opacity-0 shadow-popover transition-opacity duration-fast group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100"
								>
									<span class="text-xs font-semibold text-text-primary">{barra.nome}</span>
									<span class="whitespace-nowrap font-mono text-2xs text-text-secondary">
										{barra.periodo}
									</span>
									<span class="text-2xs text-text-muted">{BARRA_LABEL[barra.barra]}</span>
								</span>
							</button>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}
