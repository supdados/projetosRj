import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

import { createFlashStore, flashDurationMs } from './flash';

/** Mensagem exata do 422 que originou o bug (10 palavras → 7000 ms em `warning`). */
const MSG_BUG = 'Finalize as 1 tarefa(s) pendente(s) desta etapa antes de concluí-la.';

function palavras(n: number): string {
	return Array.from({ length: n }, (_, i) => `p${i}`).join(' ');
}

beforeEach(() => {
	vi.useFakeTimers();
	vi.setSystemTime(0);
});

afterEach(() => {
	vi.useRealTimers();
});

describe('flash store — inserção e auto-dismiss', () => {
	it('show insere um toast com count 1 e a categoria informada (info é o default)', () => {
		const flash = createFlashStore();
		flash.show('Salvo.');
		flash.show('Falhou.', 'danger');

		const items = get(flash);
		expect(items).toHaveLength(2);
		expect(items[0]).toMatchObject({ message: 'Salvo.', category: 'info', count: 1 });
		expect(items[1]).toMatchObject({ message: 'Falhou.', category: 'danger', count: 1 });
	});

	it('cada instância numera os ids do zero (sem contador compartilhado)', () => {
		const primeira = createFlashStore();
		const segunda = createFlashStore();

		expect(primeira.show('Salvo.', 'success')).toBe(segunda.show('Salvo.', 'success'));
	});

	it('auto-dismiss remove exatamente no flashDurationMs calculado', () => {
		const flash = createFlashStore();
		flash.show('Salvo.', 'success');
		const duracao = flashDurationMs('Salvo.', 'success');

		vi.advanceTimersByTime(duracao - 1);
		expect(get(flash)).toHaveLength(1);

		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});
});

describe('flash store — duração', () => {
	it('mensagem curta em success → 4000', () => {
		expect(flashDurationMs('Salvo.', 'success')).toBe(4000);
	});

	it('mensagem de 10 palavras em warning → 7000', () => {
		expect(flashDurationMs(MSG_BUG, 'warning')).toBe(7000);
		expect(MSG_BUG.trim().split(/\s+/)).toHaveLength(10);
	});

	it('mensagem de 30 palavras satura em 10000', () => {
		expect(flashDurationMs(palavras(30), 'success')).toBe(10000);
	});

	it('options.durationMs é clampado em 10000', () => {
		const flash = createFlashStore();
		flash.show('Salvo.', 'success', { durationMs: 30000 });

		vi.advanceTimersByTime(9999);
		expect(get(flash)).toHaveLength(1);

		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});
});

describe('flash store — deduplicação', () => {
	it('repetições idênticas viram contador, sem reescrever a message', () => {
		const flash = createFlashStore();
		flash.show(MSG_BUG, 'warning');
		flash.show(MSG_BUG, 'warning');

		expect(get(flash)).toHaveLength(1);
		expect(get(flash)[0].count).toBe(2);

		for (let i = 3; i <= 9; i += 1) flash.show(MSG_BUG, 'warning');

		expect(get(flash)).toHaveLength(1);
		expect(get(flash)[0].count).toBe(9);
		expect(get(flash)[0].message).toBe(MSG_BUG);
	});

	it('repetição reinicia o timer do toast vivo', () => {
		const flash = createFlashStore();
		const duracao = flashDurationMs('Salvo.', 'success');
		flash.show('Salvo.', 'success');

		vi.advanceTimersByTime(duracao * 0.9);
		flash.show('Salvo.', 'success');
		vi.advanceTimersByTime(duracao * 0.9);

		expect(get(flash)).toHaveLength(1);
	});

	it('teto de vida: repetição a cada 500 ms não passa de 10 000 ms', () => {
		const flash = createFlashStore();
		const id = flash.show(MSG_BUG, 'warning');

		for (let t = 500; t <= 9500; t += 500) {
			vi.advanceTimersByTime(500);
			flash.show(MSG_BUG, 'warning');
		}
		expect(get(flash).some((item) => item.id === id)).toBe(true);

		vi.advanceTimersByTime(500);
		flash.show(MSG_BUG, 'warning');
		expect(get(flash).some((item) => item.id === id)).toBe(false);
	});

	it('mensagens ou categorias diferentes não deduplicam', () => {
		const flash = createFlashStore();
		flash.show('Primeira.', 'info');
		flash.show('Segunda.', 'info');
		expect(get(flash)).toHaveLength(2);

		const outro = createFlashStore();
		outro.show('Mesma.', 'info');
		outro.show('Mesma.', 'warning');
		expect(get(outro)).toHaveLength(2);
	});

	it('options.key agrupa textos diferentes e preserva o texto do primeiro', () => {
		const flash = createFlashStore();
		flash.show('Finalize as 1 tarefa(s).', 'warning', { key: 'etapa-tarefas-pendentes' });
		flash.show('Finalize as 2 tarefa(s).', 'warning', { key: 'etapa-tarefas-pendentes' });

		expect(get(flash)).toHaveLength(1);
		expect(get(flash)[0].count).toBe(2);
		expect(get(flash)[0].message).toBe('Finalize as 1 tarefa(s).');
	});

	it('cauda de 1 s suprime a repetição; depois dela nasce toast novo com count 1', () => {
		const flash = createFlashStore();
		const id = flash.show('Salvo.', 'success');
		flash.dismiss(id);

		vi.advanceTimersByTime(999);
		expect(flash.show('Salvo.', 'success')).toBe(-1);
		expect(get(flash)).toHaveLength(0);

		vi.advanceTimersByTime(2);
		const novo = flash.show('Salvo.', 'success');
		expect(novo).not.toBe(-1);
		expect(get(flash)).toHaveLength(1);
		expect(get(flash)[0].count).toBe(1);
	});
});

describe('flash store — teto e evicção', () => {
	it('4 toasts distintos deixam 3 na pilha, descartando o mais antigo', () => {
		const flash = createFlashStore();
		for (let i = 1; i <= 4; i += 1) flash.show(`Aviso ${i}`, 'info');

		const mensagens = get(flash).map((item) => item.message);
		expect(mensagens).toHaveLength(3);
		expect(mensagens).not.toContain('Aviso 1');
		expect(mensagens).toContain('Aviso 4');
	});

	it('evicção por severidade: info despeja o success, não os danger', () => {
		const flash = createFlashStore();
		for (let i = 1; i <= 2; i += 1) flash.show(`Erro ${i}`, 'danger');
		flash.show('Salvo.', 'success');
		flash.show('Informação.', 'info');

		const items = get(flash);
		expect(items).toHaveLength(3);
		expect(items.map((item) => item.message)).not.toContain('Salvo.');
		expect(items.filter((item) => item.category === 'danger')).toHaveLength(2);
		expect(items.map((item) => item.message)).toContain('Informação.');
	});

	it('fallback FIFO: pilha só de danger aceita o success despejando o mais antigo', () => {
		const flash = createFlashStore();
		for (let i = 1; i <= 3; i += 1) flash.show(`Erro ${i}`, 'danger');
		flash.show('Salvo.', 'success');

		const mensagens = get(flash).map((item) => item.message);
		expect(mensagens).toHaveLength(3);
		expect(mensagens).not.toContain('Erro 1');
		expect(mensagens).toContain('Salvo.');
	});
});

describe('flash store — dismiss, pausa e clear', () => {
	it('dismiss remove só o alvo e não afeta o timer dos outros', () => {
		const flash = createFlashStore();
		const primeiro = flash.show('Primeira.', 'info');
		flash.show('Segunda.', 'info');
		flash.dismiss(primeiro);

		expect(get(flash)).toHaveLength(1);
		expect(get(flash)[0].message).toBe('Segunda.');

		const duracao = flashDurationMs('Segunda.', 'info');
		vi.advanceTimersByTime(duracao - 1);
		expect(get(flash)).toHaveLength(1);
		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});

	it('pause congela o auto-dismiss e resume usa o tempo restante', () => {
		const flash = createFlashStore();
		const duracao = flashDurationMs('Salvo.', 'success');
		const id = flash.show('Salvo.', 'success');

		vi.advanceTimersByTime(1000);
		flash.pause(id);
		vi.advanceTimersByTime(duracao * 3);
		expect(get(flash)).toHaveLength(1);

		flash.resume(id);
		vi.advanceTimersByTime(duracao - 1000 - 1);
		expect(get(flash)).toHaveLength(1);
		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});

	it('pausas aninhadas: sair do foco com o ponteiro parado não retoma o relógio', () => {
		const flash = createFlashStore();
		const duracao = flashDurationMs('Salvo.', 'success');
		const id = flash.show('Salvo.', 'success');

		flash.pause(id); // ponteiro entra no toast
		flash.pause(id); // foco entra no botão de fechar
		flash.resume(id); // foco sai (Tab), ponteiro continua sobre o toast
		vi.advanceTimersByTime(duracao * 3);
		expect(get(flash)).toHaveLength(1);

		flash.resume(id); // ponteiro sai — só agora o relógio volta a correr
		vi.advanceTimersByTime(duracao - 1);
		expect(get(flash)).toHaveLength(1);
		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});

	it('resume sem pause correspondente não derruba o toast nem o relógio', () => {
		const flash = createFlashStore();
		const duracao = flashDurationMs('Salvo.', 'success');
		const id = flash.show('Salvo.', 'success');

		flash.resume(id);
		vi.advanceTimersByTime(duracao - 1);
		expect(get(flash)).toHaveLength(1);
		vi.advanceTimersByTime(1);
		expect(get(flash)).toHaveLength(0);
	});

	it('clear esvazia a pilha e nenhum timer pendente reintroduz item', () => {
		const flash = createFlashStore();
		flash.show('Primeira.', 'info');
		flash.show('Segunda.', 'danger');
		flash.clear();

		expect(get(flash)).toHaveLength(0);
		vi.advanceTimersByTime(20000);
		expect(get(flash)).toHaveLength(0);
	});
});

describe('flash store — cenário do bug (cliques repetidos no concluir etapa)', () => {
	it('9 respostas 422 idênticas geram 1 toast com count 9 e message intacta', () => {
		const flash = createFlashStore();
		for (let i = 0; i < 9; i += 1) {
			flash.show(MSG_BUG, 'warning');
			vi.advanceTimersByTime(50);
		}

		const items = get(flash);
		expect(items).toHaveLength(1);
		expect(items[0].count).toBe(9);
		expect(items[0].message).toBe(MSG_BUG);
	});
});
