import { describe, it, expect } from 'vitest';
import { resolveFocusEtapaId } from './focusEtapa';

describe('resolveFocusEtapaId', () => {
	it('devolve o id quando é inteiro positivo e existe entre as etapas', () => {
		expect(resolveFocusEtapaId('?focus_etapa=12', [10, 12, 13])).toBe(12);
	});

	it('ignora quando o param está ausente', () => {
		expect(resolveFocusEtapaId('?historico=1', [10, 12])).toBeNull();
		expect(resolveFocusEtapaId('', [10, 12])).toBeNull();
	});

	it('ignora quando a etapa não existe no projeto', () => {
		expect(resolveFocusEtapaId('?focus_etapa=99', [10, 12])).toBeNull();
	});

	it('ignora valores não numéricos, zero e negativos', () => {
		expect(resolveFocusEtapaId('?focus_etapa=abc', [10])).toBeNull();
		expect(resolveFocusEtapaId('?focus_etapa=0', [0, 10])).toBeNull();
		expect(resolveFocusEtapaId('?focus_etapa=-5', [-5, 10])).toBeNull();
		expect(resolveFocusEtapaId('?focus_etapa=1.5', [1, 2])).toBeNull();
	});

	it('preserva outros params na leitura (só olha focus_etapa)', () => {
		expect(resolveFocusEtapaId('?historico=1&focus_etapa=13', [13])).toBe(13);
	});
});
