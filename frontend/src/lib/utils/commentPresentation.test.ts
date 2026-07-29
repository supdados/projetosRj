/**
 * Testes do render de menções: `segmentsFromMentions` confia nos intervalos que
 * o servidor resolveu (`services/comment_mentions`) e só precisa ser robusto a
 * dado inconsistente — nunca voltar a adivinhar onde o nome termina.
 */
import { describe, it, expect } from 'vitest';
import { segmentsFromMentions, splitMentions } from './commentPresentation';

const trechos = (text: string, mentions: { start: number; length: number }[]) =>
	segmentsFromMentions(text, mentions).map((s) => [s.text, s.isMention]);

describe('segmentsFromMentions', () => {
	it('destaca o nome composto inteiro', () => {
		const texto = '@Ana Luiza Ribeiro faca X coisas';
		expect(trechos(texto, [{ start: 0, length: 18 }])).toEqual([
			['@Ana Luiza Ribeiro', true],
			[' faca X coisas', false]
		]);
	});

	it('mantém o texto intacto quando não há menção', () => {
		expect(trechos('sem ninguem marcado', [])).toEqual([['sem ninguem marcado', false]]);
	});

	it('usa unidades UTF-16, então emoji antes da menção não desloca o realce', () => {
		const texto = '😀 @Ana oi';
		// start=3 => 2 unidades do emoji + 1 do espaço (o que o backend grava).
		expect(trechos(texto, [{ start: 3, length: 4 }])).toEqual([
			['😀 ', false],
			['@Ana', true],
			[' oi', false]
		]);
	});

	it('ordena intervalos fora de ordem', () => {
		const texto = '@Ana e @Bia';
		expect(
			trechos(texto, [
				{ start: 7, length: 4 },
				{ start: 0, length: 4 }
			])
		).toEqual([
			['@Ana', true],
			[' e ', false],
			['@Bia', true]
		]);
	});

	it('descarta intervalo sobreposto, inválido ou além do fim do texto', () => {
		const texto = '@Ana oi';
		const sobreposto = trechos(texto, [
			{ start: 0, length: 4 },
			{ start: 2, length: 3 }
		]);
		expect(sobreposto).toEqual([
			['@Ana', true],
			[' oi', false]
		]);
		expect(trechos(texto, [{ start: -1, length: 4 }])).toEqual([[texto, false]]);
		expect(trechos(texto, [{ start: 0, length: 999 }])).toEqual([[texto, false]]);
		expect(trechos(texto, [{ start: 0, length: 0 }])).toEqual([[texto, false]]);
	});
});

describe('splitMentions (legado, só para comentários sem `mentions`)', () => {
	it('sem a lista de nomes, casa apenas uma palavra — o bug que motivou a mudança', () => {
		const segmentos = splitMentions('@Ana Luiza Ribeiro faca X coisas');
		expect(segmentos[0]).toEqual({ text: '@Ana', isMention: true });
	});

	it('com a lista de nomes, prefere o mais longo', () => {
		const segmentos = splitMentions('@Ana Luiza Ribeiro faca X', ['Ana', 'Ana Luiza Ribeiro']);
		expect(segmentos[0]).toEqual({ text: '@Ana Luiza Ribeiro', isMention: true });
	});
});
