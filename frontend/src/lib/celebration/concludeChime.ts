/**
 * Chime de conclusão de projeto — porte FIEL de
 * `static/js/pages/projects/detail/08-project-status.js`
 * (`getConcludeAudioContext` / `primeConcludeAudioContext` /
 * `playConcludeSuccessChime`).
 *
 * Som SINTETIZADO via Web Audio API (NÃO é um asset .mp3): arpejo ascendente de
 * 3 notas (G3 196Hz, B3 246.94Hz, E4 329.63Hz) em sine+triangle, com sparkle de
 * harmônicos na última nota, sub-bass 110->65Hz, lowpass 2200Hz e highshelf
 * 2800Hz. As frequências e o agendamento são COPIADOS 1:1 do legado.
 *
 * O `AudioContext` precisa ser "armado" por um gesto do usuário (clique/pointer)
 * para tocar sem bloqueio de autoplay — daí `primeConcludeAudioContext`, que o
 * componente chama no `pointerdown`/click do botão "Concluir".
 */

type WindowWithWebkitAudio = Window &
	typeof globalThis & { webkitAudioContext?: typeof AudioContext };

let concludeAudioContext: AudioContext | null = null;

function getConcludeAudioContext(): AudioContext | null {
	if (concludeAudioContext) return concludeAudioContext;
	if (typeof window === 'undefined') return null;
	const win = window as WindowWithWebkitAudio;
	const AudioContextClass = win.AudioContext || win.webkitAudioContext;
	if (!AudioContextClass) return null;
	concludeAudioContext = new AudioContextClass();
	return concludeAudioContext;
}

/**
 * "Arma" o AudioContext a partir de um gesto do usuário (resume se suspenso),
 * para que `playConcludeSuccessChime` toque sem bloqueio de autoplay.
 */
export async function primeConcludeAudioContext(): Promise<void> {
	try {
		const context = getConcludeAudioContext();
		if (!context) return;
		if (context.state === 'suspended') await context.resume();
	} catch (error) {
		console.warn('Não foi possível preparar o áudio de conclusão.', error);
	}
}

/** Toca o chime de sucesso da conclusão (porte 1:1 do legado). */
export function playConcludeSuccessChime(): void {
	const context = getConcludeAudioContext();
	if (!context) return;
	if (context.state === 'suspended') context.resume().catch(() => {});

	try {
		const now = context.currentTime + 0.012;

		const masterGain = context.createGain();
		masterGain.gain.setValueAtTime(0.75, now);

		const toneFilter = context.createBiquadFilter();
		toneFilter.type = 'lowpass';
		toneFilter.frequency.setValueAtTime(2200, now);
		toneFilter.Q.value = 0.7;

		masterGain.connect(toneFilter);
		toneFilter.connect(context.destination);

		const sparkleGain = context.createGain();
		sparkleGain.gain.setValueAtTime(0.18, now);

		const sparkleHP = context.createBiquadFilter();
		sparkleHP.type = 'highpass';
		sparkleHP.frequency.setValueAtTime(1400, now);

		const sparkleShelf = context.createBiquadFilter();
		sparkleShelf.type = 'highshelf';
		sparkleShelf.frequency.setValueAtTime(2800, now);
		sparkleShelf.gain.setValueAtTime(3.5, now);

		sparkleGain.connect(sparkleHP);
		sparkleHP.connect(sparkleShelf);
		sparkleShelf.connect(context.destination);

		const playNote = (
			freq: number,
			start: number,
			duration: number,
			gain: number,
			opts: { sparkle?: boolean } = {}
		): void => {
			const startAt = now + start;
			const endAt = startAt + duration;

			const oscBody = context.createOscillator();
			const oscTexture = context.createOscillator();
			const gainBody = context.createGain();
			const gainTexture = context.createGain();

			oscBody.type = 'sine';
			oscBody.frequency.setValueAtTime(freq, startAt);
			oscTexture.type = 'triangle';
			oscTexture.frequency.setValueAtTime(freq * 2, startAt);

			gainBody.gain.setValueAtTime(0.0001, startAt);
			gainBody.gain.exponentialRampToValueAtTime(gain, startAt + 0.01);
			gainBody.gain.exponentialRampToValueAtTime(gain * 0.55, startAt + duration * 0.55);
			gainBody.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.03);

			gainTexture.gain.setValueAtTime(0.0001, startAt);
			gainTexture.gain.exponentialRampToValueAtTime(gain * 0.28, startAt + 0.008);
			gainTexture.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.02);

			oscBody.connect(gainBody);
			oscTexture.connect(gainTexture);
			gainBody.connect(masterGain);
			gainTexture.connect(masterGain);

			if (opts.sparkle) {
				const sparkleStart = startAt + duration * 0.55;
				const sparkleEnd = endAt + 0.08;

				const sp1 = context.createOscillator();
				const sp2 = context.createOscillator();
				const spGain = context.createGain();

				sp1.type = 'sine';
				sp2.type = 'triangle';

				sp1.frequency.setValueAtTime(freq * 2, sparkleStart);
				sp2.frequency.setValueAtTime(freq * 3, sparkleStart);

				spGain.gain.setValueAtTime(0.0001, sparkleStart);
				spGain.gain.exponentialRampToValueAtTime(gain * 0.075, sparkleStart + 0.012);
				spGain.gain.exponentialRampToValueAtTime(0.0001, sparkleEnd);

				sp1.connect(spGain);
				sp2.connect(spGain);
				spGain.connect(sparkleGain);

				sp1.start(sparkleStart);
				sp2.start(sparkleStart);
				sp1.stop(sparkleEnd + 0.02);
				sp2.stop(sparkleEnd + 0.02);
			}

			oscBody.start(startAt);
			oscTexture.start(startAt);
			oscBody.stop(endAt + 0.06);
			oscTexture.stop(endAt + 0.06);
		};

		[
			{ freq: 196.0, start: 0.0, duration: 0.18, gain: 0.095, sparkle: false },
			{ freq: 246.94, start: 0.14, duration: 0.2, gain: 0.088, sparkle: false },
			{ freq: 329.63, start: 0.28, duration: 0.22, gain: 0.082, sparkle: true }
		].forEach((note) =>
			playNote(note.freq, note.start, note.duration, note.gain, { sparkle: note.sparkle })
		);

		const subOsc = context.createOscillator();
		const subGain = context.createGain();
		subOsc.type = 'sine';
		subOsc.frequency.setValueAtTime(110, now);
		subOsc.frequency.exponentialRampToValueAtTime(65, now + 0.11);

		subGain.gain.setValueAtTime(0.0001, now);
		subGain.gain.exponentialRampToValueAtTime(0.04, now + 0.01);
		subGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);

		subOsc.connect(subGain);
		subGain.connect(masterGain);
		subOsc.start(now);
		subOsc.stop(now + 0.13);

		setTimeout(() => {
			masterGain.disconnect();
			toneFilter.disconnect();
			sparkleGain.disconnect();
			sparkleHP.disconnect();
			sparkleShelf.disconnect();
		}, 1100);
	} catch (error) {
		console.error('Sound error:', error);
	}
}
