import { describe, it, expect } from 'vitest';
import { projectStatusDotClass } from './projectLabels';

describe('projectStatusDotClass', () => {
	it('segue a família da pílula de status', () => {
		expect(projectStatusDotClass('Vigente')).toBe('bg-primary-600');
		expect(projectStatusDotClass('Finalizado')).toBe('bg-success-600');
		expect(projectStatusDotClass('Suspenso')).toBe('bg-warning-600');
		expect(projectStatusDotClass('Cancelado')).toBe('bg-danger-600');
	});

	it('ignora caixa/espaços e cai no neutro para status desconhecido ou vazio', () => {
		expect(projectStatusDotClass('  suspenso ')).toBe('bg-warning-600');
		expect(projectStatusDotClass('Outro')).toBe('bg-neutral-600');
		expect(projectStatusDotClass(null)).toBe('bg-neutral-600');
	});
});
