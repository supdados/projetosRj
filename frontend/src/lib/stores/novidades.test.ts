import { get } from 'svelte/store';
import { describe, expect, it } from 'vitest';
import type { NovidadeResumo } from '$lib/types/novidades';
import { createNovidadesStore } from './novidades';

const COLECOES: NovidadeResumo = {
	slug: 'colecoes-2026-11',
	titulo: 'Coleções',
	publicada_em: '2026-11-05T00:00:00Z',
	vista: false
};

class ServidorFalso {
	marcadas: [string, boolean][] = [];
	falhaAoBuscar = false;
	falhaAoMarcar = false;

	buscar = async (): Promise<NovidadeResumo[]> => {
		if (this.falhaAoBuscar) throw new Error('offline');
		return [COLECOES];
	};

	marcar = async (slug: string, concluida: boolean): Promise<void> => {
		if (this.falhaAoMarcar) throw new Error('offline');
		this.marcadas.push([slug, concluida]);
	};
}

describe('store de novidades', () => {
	it('fechar marca como vista na hora e avisa o servidor', async () => {
		const servidor = new ServidorFalso();
		const store = createNovidadesStore(servidor.buscar, servidor.marcar);
		await store.carregar();
		store.abrir(COLECOES.slug);

		await store.fechar(true);

		expect(get(store).aberta).toBeNull();
		expect(get(store).itens[0].vista).toBe(true);
		expect(servidor.marcadas).toEqual([[COLECOES.slug, true]]);
	});

	it('prévia do admin não conta como vista', async () => {
		const servidor = new ServidorFalso();
		const store = createNovidadesStore(servidor.buscar, servidor.marcar);
		await store.carregar();
		store.abrir(COLECOES.slug, true);

		await store.fechar(false);

		expect(get(store).itens[0].vista).toBe(false);
		expect(servidor.marcadas).toEqual([]);
	});

	it('falha de rede não vira erro: lista vazia ao carregar e fechamento segue', async () => {
		const servidor = new ServidorFalso();
		servidor.falhaAoBuscar = true;
		servidor.falhaAoMarcar = true;
		const store = createNovidadesStore(servidor.buscar, servidor.marcar);

		expect(await store.carregar()).toEqual([]);
		store.abrir(COLECOES.slug);
		await expect(store.fechar(false)).resolves.toBeUndefined();
		expect(get(store).aberta).toBeNull();
	});
});
