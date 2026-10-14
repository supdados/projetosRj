import { describe, it, expect } from 'vitest';
import { pinSelectedProjects } from './pinnedPickerSelection';

interface FakeProject {
	id: number;
	status: string;
}

const vigente: FakeProject = { id: 1, status: 'Vigente' };
const outroVigente: FakeProject = { id: 2, status: 'Vigente' };
const finalizado: FakeProject = { id: 3, status: 'Finalizado' };
const suspenso: FakeProject = { id: 4, status: 'Suspenso' };

const known = new Map([vigente, outroVigente, finalizado, suspenso].map((p) => [p.id, p]));

describe('pinSelectedProjects', () => {
	it('mantém o resultado intacto quando a seleção já está nele', () => {
		expect(pinSelectedProjects([vigente, outroVigente], [2], known)).toEqual([
			vigente,
			outroVigente
		]);
	});

	it('fixa no topo o selecionado que o filtro escondeu, na ordem da seleção', () => {
		expect(pinSelectedProjects([vigente], [4, 3], known)).toEqual([suspenso, finalizado, vigente]);
	});

	it('ignora selecionado que nunca apareceu numa busca (sem dados para exibir)', () => {
		expect(pinSelectedProjects([vigente], [99], known)).toEqual([vigente]);
	});

	it('não duplica selecionado presente no resultado', () => {
		expect(pinSelectedProjects([finalizado], [3], known)).toEqual([finalizado]);
	});
});
