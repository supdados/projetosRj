<script lang="ts">
	/**
	 * Micro-interacao do KPI "Em atraso" (vermelho): ampulheta de VIDRO transparente
	 * (imagem webp) com areia desenhada num <canvas> ATRAS.
	 *
	 * REPOUSO: areia preenche o bulbo SUPERIOR (clip CURVO seguindo a parede do bulbo).
	 * Nenhum rAF => 0 CPU.
	 *
	 * HOVER (proprio OU ancestral `.group`) por 15s CONTINUOS (gate anti-agressivo;
	 * sair zera a contagem): uma RACHADURA e desenhada no ponto de vazamento (canvas)
	 * e a areia VAZA do GARGALO (meio do item) num fluxo UNIFORME (pouca
	 * aleatoriedade = parabola previsivel), cai ate o CHAO DO CARD (medido em runtime)
	 * e e ABSORVIDA por um MONTE desenhado (forma limpa que cresce) — previsivel, sem
	 * pilha de pixels espalhada. Permanece ate o mouse sair (entao escoa).
	 *
	 * O nivel do bulbo segue a fracao ja despejada (emitido/TOTAL) => esvazia junto.
	 * Canvas 2D + rAF (0KB). Decorativo (`aria-hidden`). reduced-motion: so a imagem.
	 */
	import { onMount } from 'svelte';

	interface Props {
		/** Largura da AMPULHETA em px. */
		size?: number;
		image?: string;
	}

	let { size = 36, image = '/static/img/dashboard/hourglass-normal.webp' }: Props = $props();

	const RATIO = 320 / 209;
	const HW = $derived(size);
	const HH = $derived(size * RATIO);

	let CW = $state(0);
	let CH = $state(0);

	// --- Tuning ---
	const GRAVITY = 0.055;
	const EMIT_PER_FRAME = 3;
	const TOTAL = 460; // orcamento de graos; o bulbo esvazia ao despejar todos
	const NOMINAL_VX = 0.95; // velocidade horizontal "media" (fluxo uniforme)
	const SANDS = ['#e3c07d', '#d4ad6a'];
	const MAX_HALFW = $derived(size * 0.684); // meia-largura final do monte (-28%)
	const MAX_PEAKH = $derived(size * 0.446); // altura final do monte (-28%)

	let canvas: HTMLCanvasElement;
	let root: HTMLElement;

	let reduced = false;
	let crackAlpha = 0; // fade da rachadura desenhada (0 repouso -> 1 hover)

	/**
	 * Maquina de estados finita (statechart minimo) — UNICA fonte da verdade.
	 * O `loop` so LE `phase`; enter/leave so REESCREVEM `phase` (start/stop). E o
	 * que mata o flicker/oscilacao em hover/leave RAPIDOS e repetidos:
	 *   idle     -> repouso, sem rAF (0 CPU), vidro intacto
	 *   entering -> vazando (emite graos, rachadura sobe, monte cresce)
	 *   active   -> tudo despejado e assentado; frame final congelado (rAF parado)
	 *   leaving  -> sem hover: pilha some (fade) + rachadura some; ao zerar -> idle
	 * `hovering` deriva de phase (entering|active). Re-entrar durante `leaving`
	 * SO re-mira para entering: a pilha que AINDA existe e reaproveitada
	 * (pileAlpha volta a subir) — nada e resetado no meio => sem salto/flicker.
	 */
	type Phase = 'idle' | 'entering' | 'active' | 'leaving';
	let phase: Phase = 'idle';
	const isHovering = () => phase === 'entering' || phase === 'active';

	// `raf` guarda o id do rAF agendado (nunca 0 quando vivo) p/ cancelamento
	// deterministico. Toda mutacao passa por requestLoop()/cancelLoop() => UM
	// unico loop vivo, sem rAF concorrente/preso. Ver rAF lifecycle (MDN).
	let raf = 0;
	let emitted = 0; // graos despejados (dirige o nivel do bulbo)
	let landed = 0; // graos absorvidos pelo monte (dirige o tamanho do monte)
	let fill = 0;
	let pileAlpha = 1;
	let landX = 0; // x onde o fluxo aterrissa (centro do monte), medido no start

	interface Grain {
		x: number;
		y: number;
		vx: number;
		vy: number;
		s: number;
		c: string;
	}
	let grains: Grain[] = [];

	function rand(a: number, b: number): number {
		return a + Math.random() * (b - a);
	}

	// Bulbo SUPERIOR com paredes concavas (curvas).
	function upperBulbPath(ctx: CanvasRenderingContext2D, hw: number, hh: number) {
		const cx = hw / 2;
		const topY = hh * 0.085;
		const topHalf = hw * 0.4;
		const neckY = hh * 0.47;
		const neckHalf = hw * 0.055;
		ctx.beginPath();
		ctx.moveTo(cx - topHalf, topY);
		ctx.lineTo(cx + topHalf, topY);
		ctx.quadraticCurveTo(cx + topHalf * 0.5, hh * 0.32, cx + neckHalf, neckY);
		ctx.lineTo(cx - neckHalf, neckY);
		ctx.quadraticCurveTo(cx - topHalf * 0.5, hh * 0.32, cx - topHalf, topY);
		ctx.closePath();
	}

	// Ponto de vazamento: perto do GARGALO (meio do item) — faz sentido vazar tanto.
	function leakPoint(hw: number, hh: number) {
		return { x: hw * 0.55, y: hh * 0.52 };
	}

	function spawnGrain(hw: number, hh: number): Grain {
		const p = leakPoint(hw, hh);
		// Pouca aleatoriedade => fluxo uniforme/previsivel (mesma parabola).
		return {
			x: p.x + rand(-0.5, 0.5),
			y: p.y + rand(-0.5, 0.5),
			vx: NOMINAL_VX + rand(-0.06, 0.06),
			vy: rand(-0.03, 0.06),
			s: 1,
			c: Math.random() < 0.5 ? SANDS[0] : SANDS[1]
		};
	}

	function drawBulbSand(ctx: CanvasRenderingContext2D, hw: number, hh: number, f: number) {
		ctx.save();
		upperBulbPath(ctx, hw, hh);
		ctx.clip();
		const top = hh * 0.085 + hh * 0.39 * f;
		ctx.fillStyle = SANDS[0];
		ctx.fillRect(0, top, hw, hh);
		ctx.restore();
	}

	// Perfil de altura do monte (triangular) p/ COLISAO — cresce com `progress`.
	function moundHeightAt(x: number, progress: number): number {
		if (progress <= 0) return 0;
		const halfW = MAX_HALFW * Math.sqrt(progress);
		const peakH = MAX_PEAKH * Math.sqrt(progress);
		const d = Math.abs(x - landX);
		if (d >= halfW) return 0;
		return peakH * (1 - d / halfW);
	}

	// Desenha o MONTE como forma limpa (curva), tamanho ~ raiz da fracao absorvida.
	function drawMound(ctx: CanvasRenderingContext2D, fy: number, progress: number) {
		if (progress <= 0) return;
		const halfW = MAX_HALFW * Math.sqrt(progress);
		const peakH = MAX_PEAKH * Math.sqrt(progress);
		ctx.beginPath();
		ctx.moveTo(landX - halfW, fy);
		ctx.quadraticCurveTo(landX - halfW * 0.42, fy - peakH * 0.96, landX, fy - peakH);
		ctx.quadraticCurveTo(landX + halfW * 0.42, fy - peakH * 0.96, landX + halfW, fy);
		ctx.closePath();
		ctx.fillStyle = SANDS[1];
		ctx.fill();
	}

	// Rachadura desenhada (starburst de fissuras) no ponto de vazamento.
	function drawCrack(ctx: CanvasRenderingContext2D, hw: number, hh: number, alpha: number) {
		if (alpha <= 0.01) return;
		const p = leakPoint(hw, hh);
		// Raios da fissura, relativos ao tamanho (deterministico, sem ruido por frame).
		const rays = [
			[[0, 0], [hw * 0.13, -hh * 0.05], [hw * 0.24, -hh * 0.03]],
			[[0, 0], [hw * 0.15, hh * 0.02], [hw * 0.27, hh * 0.06]],
			[[0, 0], [-hw * 0.04, -hh * 0.08], [hw * 0.01, -hh * 0.15]],
			[[0, 0], [hw * 0.05, hh * 0.07], [hw * 0.02, hh * 0.14]],
			[[0, 0], [-hw * 0.11, hh * 0.0], [-hw * 0.21, hh * 0.02]]
		];
		ctx.save();
		ctx.lineCap = 'round';
		ctx.lineJoin = 'round';
		for (const ray of rays) {
			// halo claro (vidro estilhacado) + linha fina escura por cima.
			ctx.globalAlpha = alpha * 0.5;
			ctx.strokeStyle = 'rgba(255,255,255,0.9)';
			ctx.lineWidth = 1.4;
			ctx.beginPath();
			ctx.moveTo(p.x + ray[0][0], p.y + ray[0][1]);
			for (let i = 1; i < ray.length; i++) ctx.lineTo(p.x + ray[i][0], p.y + ray[i][1]);
			ctx.stroke();
			ctx.globalAlpha = alpha * 0.8;
			ctx.strokeStyle = 'rgba(90,110,130,0.9)';
			ctx.lineWidth = 0.7;
			ctx.stroke();
		}
		ctx.restore();
	}

	function renderStatic() {
		const ctx = canvas?.getContext('2d');
		if (!ctx) return;
		ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
		ctx.globalAlpha = 1;
		drawBulbSand(ctx, HW, HH, 0);
	}

	// --- Ciclo de vida do rAF (UM unico loop garantido) ---------------------
	// Agenda o loop SOMENTE se nenhum estiver vivo. `raf` guarda o id retornado
	// (nunca 0 quando agendado), permitindo cancelamento deterministico.
	// Idempotente: chamar varias vezes nao duplica o loop (anti rAF-fantasma).
	function requestLoop() {
		if (raf) return;
		raf = requestAnimationFrame(loop);
	}

	// Cancela o loop em qualquer caminho de parada (cleanup, aba oculta).
	function cancelLoop() {
		if (!raf) return;
		cancelAnimationFrame(raf);
		raf = 0;
	}

	// Volta ao repouso de forma atomica: congela, limpa estado e desenha o estatico.
	function resetToIdle() {
		cancelLoop();
		phase = 'idle';
		grains = [];
		emitted = 0;
		landed = 0;
		pileAlpha = 1;
		fill = 0;
		crackAlpha = 0;
		renderStatic();
	}

	function loop() {
		// O id atual ja consumiu sua chamada; zere ANTES de decidir reagendar, p/
		// requestLoop() voltar a poder agendar (mantem o invariante "raf!=0 = vivo").
		raf = 0;

		// Aba oculta: o navegador pausa o rAF. Deixamos congelado; `visibilitychange`
		// religa via requestLoop() ao voltar (sem perder a pose nem duplicar loop).
		if (document.hidden) return;
		const ctx = canvas?.getContext('2d');
		if (!ctx) return;

		const w = canvas.clientWidth;
		const h = canvas.clientHeight;
		const fy = h - 0.5;
		ctx.clearRect(0, 0, w, h);

		const hovering = isHovering();
		// Fade da pilha so quando NAO ha hover (leaving). Re-entrou no fade: recupera.
		if (!hovering) pileAlpha = Math.max(0, pileAlpha - 0.03);
		else pileAlpha = Math.min(1, pileAlpha + 0.06);
		// Rachadura aparece/some suavemente (lerp) conforme o hover.
		crackAlpha += ((hovering ? 1 : 0) - crackAlpha) * 0.18;

		// Emite o fluxo (orcamento). O bulbo segue a fracao emitida.
		if (hovering && emitted < TOTAL) {
			for (let i = 0; i < EMIT_PER_FRAME && emitted < TOTAL; i++) {
				grains.push(spawnGrain(HW, HH));
				emitted++;
			}
		}
		fill = Math.min(1, emitted / TOTAL);
		const progress = Math.min(1, landed / TOTAL);

		ctx.globalAlpha = pileAlpha;
		drawBulbSand(ctx, HW, HH, fill);
		drawMound(ctx, fy, progress); // monte cresce conforme a areia chega

		// Grãos caindo: parabola uniforme; ao tocar o monte/chao sao ABSORVIDOS.
		ctx.globalAlpha = pileAlpha;
		const survivors: Grain[] = [];
		for (const p of grains) {
			p.vy += GRAVITY;
			p.x += p.vx;
			p.y += p.vy;
			const surf = fy - moundHeightAt(p.x, progress);
			if (p.y + p.s >= surf && p.vy > 0) {
				landed++; // vira "monte"; nao desenhamos o grao individual
				continue;
			}
			if (p.x > w + 4 || p.y > h + 4) continue;
			ctx.fillStyle = p.c;
			ctx.fillRect(p.x, p.y, p.s, p.s);
			survivors.push(p);
		}
		grains = survivors;
		ctx.globalAlpha = 1;

		// Rachadura no vidro, no ponto de vazamento (por cima da areia do canvas).
		drawCrack(ctx, HW, HH, crackAlpha);

		// --- Transicoes da FSM (decididas SO a partir de phase + progresso) ---
		// `raf` ja foi zerado no topo do frame, entao requestLoop() pode reagendar.
		if (hovering) {
			// entering -> active quando tudo foi despejado, assentou e a rachadura
			// terminou de aparecer: congela no frame final (sem reagendar => 0 CPU).
			if (phase === 'entering' && emitted >= TOTAL && grains.length === 0 && crackAlpha > 0.98) {
				phase = 'active';
				return; // congelado; o proximo stop() religa o loop p/ escoar
			}
			if (phase === 'active') return; // ja congelado; nada a fazer
			requestLoop(); // entering ainda em andamento
			return;
		}

		// leaving: continua ate a pilha sumir E os graos/monte/rachadura residuais.
		if (pileAlpha > 0 && (grains.length > 0 || landed > 0 || crackAlpha > 0.01)) {
			requestLoop();
			return;
		}
		resetToIdle(); // escoou por completo: volta atomicamente ao repouso e PARA
	}

	// start/stop sao IDEMPOTENTES: so movem a `phase` e (re)agendam o loop; nunca
	// resetam progresso. Re-disparos (mouseenter no root E no `.group` quase
	// juntos, ou hover/leave rapidos) viram no-ops ou simples re-mira => sem
	// "restart"/flicker e sem rAF duplicado (requestLoop guarda contra isso).
	function start() {
		if (reduced) return; // sem canvas/animacao; so o vidro intacto
		if (isHovering()) return; // ja entering|active: nada a (re)iniciar
		// Vindo de idle (estado ja zerado por resetToIdle) OU de leaving (pilha/graos
		// parciais): em ambos so passamos a `entering`. Em leaving, o loop reaproveita
		// o estado atual e `pileAlpha` volta a subir => retomada suave (latest wins).
		phase = 'entering';
		requestLoop();
	}

	function stop() {
		if (reduced || phase === 'idle' || phase === 'leaving') return; // ja saindo/parado
		phase = 'leaving';
		requestLoop(); // sai do frame congelado (active) p/ escoar (no-op se ja roda)
	}

	function sizeCanvasToCard() {
		const card = root.closest('.group') as HTMLElement | null;
		const rr = root.getBoundingClientRect();
		if (card) {
			const cr = card.getBoundingClientRect();
			CH = Math.max(HH * 1.4, cr.bottom - rr.top - 8);
			CW = Math.max(HW * 2.4, Math.min(size * 5, cr.right - rr.left - 8));
		} else {
			CH = HH * 2.2;
			CW = HW * 4;
		}
		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		canvas.width = Math.round(CW * dpr);
		canvas.height = Math.round(CH * dpr);
		const ctx = canvas.getContext('2d')!;
		ctx.setTransform(1, 0, 0, 1, 0, 0);
		ctx.scale(dpr, dpr);

		// Aterrissagem do fluxo (com chao vazio): onde a parabola atinge fy.
		const p = leakPoint(HW, HH);
		const fy = CH - 0.5;
		const t = Math.sqrt((2 * (fy - p.y)) / GRAVITY);
		landX = Math.max(MAX_HALFW, Math.min(CW - MAX_HALFW, p.x + NOMINAL_VX * t));
	}

	onMount(() => {
		const mq = matchMedia('(prefers-reduced-motion: reduce)');
		reduced = mq.matches;
		const onMq = (e: MediaQueryListEvent) => (reduced = e.matches);
		mq.addEventListener('change', onMq);

		sizeCanvasToCard();
		renderStatic();

		// Anti hover-thrash: escutamos UM unico alvo estavel. Se existe o cartao
		// `.group` (KPI), o root vive DENTRO dele; escutar os dois faria o root emitir
		// enter/leave extras quando o cursor cruza a borda do root SEM sair do cartao
		// -> stop()/start() em pingue-pongue. Um so alvo elimina essa borda interna.
		const group = root.closest('.group') as HTMLElement | null;
		const hoverTarget: HTMLElement = group ?? root;

		// DELAY DE ENTRADA (15s): a animacao e intensa demais p/ disparar a cada hover,
		// entao so jorra apos 15s de hover CONTINUO. `enterTimer` agenda o start(); sair
		// zera a contagem (via leave). A grace de 90ms na saida (abaixo) absorve flicks
		// transitorios -> um micro-leave NAO reseta os 15s.
		const ENTER_DELAY_MS = 15000;
		let enterTimer = 0;
		const clearEnterTimer = () => {
			if (enterTimer) {
				clearTimeout(enterTimer);
				enterTimer = 0;
			}
		};

		// Hover-intent na SAIDA: uma `mouseleave` transitoria (cursor rocando a borda,
		// jitter de layout, ou leave->enter rapido) NAO deve agir de imediato. Um
		// pequeno atraso cancelavel absorve o ruido; reentrar antes do prazo cancela a
		// saida e mantem o estado/contagem. Ref: hover-intent (cssscript.com/sv-hover-intent).
		const LEAVE_DELAY_MS = 90;
		let leaveTimer = 0;
		const clearLeaveTimer = () => {
			if (leaveTimer) {
				clearTimeout(leaveTimer);
				leaveTimer = 0;
			}
		};
		const enter = () => {
			clearLeaveTimer(); // reentrou: cancela qualquer drenagem/saida pendente
			// Animacao JA tocou e esta drenando (leaving): voltar rapido RETOMA na hora
			// (sem exigir novos 15s) — start() reaproveita a pose e a pilha volta a subir.
			if (phase === 'leaving') {
				start();
				return;
			}
			if (phase !== 'idle') return; // entering/active: ja rodando, nada a fazer
			if (enterTimer) return; // ja contando os 15s
			enterTimer = window.setTimeout(() => {
				enterTimer = 0;
				start(); // 15s continuos -> dispara o jorro
			}, ENTER_DELAY_MS);
		};
		const leave = () => {
			clearLeaveTimer();
			leaveTimer = window.setTimeout(() => {
				leaveTimer = 0;
				clearEnterTimer(); // saiu de fato: zera a contagem dos 15s
				stop(); // se estava jorrando, drena; se idle, no-op
			}, LEAVE_DELAY_MS);
		};
		hoverTarget.addEventListener('mouseenter', enter);
		hoverTarget.addEventListener('mouseleave', leave);
		hoverTarget.addEventListener('focusin', enter);
		hoverTarget.addEventListener('focusout', leave);
		// Resize com debounce: ResizeObserver/resize podem disparar em rajada (layout
		// reflow do card). So re-medimos em repouso (idle) e apos a rajada assentar,
		// evitando recalcular landX/CH no meio de um fluxo (que causaria salto).
		let resizeTimer = 0;
		const onResize = () => {
			if (resizeTimer) clearTimeout(resizeTimer);
			resizeTimer = window.setTimeout(() => {
				resizeTimer = 0;
				if (phase === 'idle') {
					sizeCanvasToCard();
					renderStatic();
				}
			}, 120);
		};
		window.addEventListener('resize', onResize);

		// Aba oculta pausa o rAF (navegador) e o loop() retorna cedo zerando `raf`.
		// Ao reexibir, religamos SE ainda ha trabalho (hover ativo ou drenagem em
		// curso). Sem isto, o loop ficaria preso parado apos voltar de outra aba.
		const onVisibility = () => {
			if (document.hidden) {
				clearEnterTimer(); // aba oculta NAO conta os 15s (senao dispara ao voltar)
				cancelLoop(); // libera o id; loop() tambem zera, mas cancelamos ja
				return;
			}
			if (phase !== 'idle') requestLoop();
		};
		document.addEventListener('visibilitychange', onVisibility);

		// Perder o FOCO da janela (cmd-tab / clicar em outro app) sem o cursor sair do
		// elemento NAO dispara mouseleave -> o timer dos 15s continuaria e a animacao
		// comecaria ao voltar. Cancelamos a contagem no blur; so re-hover reinicia.
		const onBlur = () => clearEnterTimer();
		window.addEventListener('blur', onBlur);

		return () => {
			mq.removeEventListener('change', onMq);
			hoverTarget.removeEventListener('mouseenter', enter);
			hoverTarget.removeEventListener('mouseleave', leave);
			hoverTarget.removeEventListener('focusin', enter);
			hoverTarget.removeEventListener('focusout', leave);
			clearEnterTimer();
			clearLeaveTimer();
			if (resizeTimer) clearTimeout(resizeTimer);
			window.removeEventListener('resize', onResize);
			document.removeEventListener('visibilitychange', onVisibility);
			window.removeEventListener('blur', onBlur);
			cancelLoop(); // unico caminho de cancelamento no unmount (sem leak)
		};
	});
</script>

<span
	class="ah-root"
	bind:this={root}
	style="--ah-hw: {HW}px; --ah-hh: {HH}px; --ah-cw: {CW}px; --ah-ch: {CH}px;"
	aria-hidden="true"
>
	<canvas bind:this={canvas} class="ah-sand"></canvas>
	<img class="ah-glass" src={image} alt="" />
</span>

<style>
	.ah-root {
		display: inline-flex;
		position: relative;
		z-index: 1;
		width: var(--ah-hw);
		height: var(--ah-hh);
		flex-shrink: 0;
	}
	.ah-sand {
		position: absolute;
		top: 0;
		left: 0;
		width: var(--ah-cw);
		height: var(--ah-ch);
		z-index: 0;
		pointer-events: none;
	}
	.ah-glass {
		position: absolute;
		top: 0;
		left: 0;
		width: var(--ah-hw);
		height: var(--ah-hh);
		z-index: 1;
		pointer-events: none;
		object-fit: contain;
	}

	@media (prefers-reduced-motion: reduce) {
		.ah-sand {
			display: none;
		}
	}
</style>
