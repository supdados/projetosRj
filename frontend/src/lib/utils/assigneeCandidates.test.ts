import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TaskAssignee } from '$lib/types/tasks';
import {
	assigneeCandidatesEpoch,
	invalidateAssigneeCandidates,
	loadAssigneeCandidates
} from './assigneeCandidates';

const convidado = { id: 7, name: 'Convidado VPD' } as TaskAssignee;

beforeEach(() => invalidateAssigneeCandidates());

describe('cache de candidatos do AssigneePicker', () => {
	it('reaproveita a mesma requisição para a mesma chave', async () => {
		const fetcher = vi.fn().mockResolvedValue([convidado]);
		await loadAssigneeCandidates('p3', fetcher);
		await loadAssigneeCandidates('p3', fetcher);
		expect(fetcher).toHaveBeenCalledTimes(1);
	});

	it('busca de novo depois de invalidar e avança a geração', async () => {
		const fetcher = vi.fn().mockResolvedValue([]);
		await loadAssigneeCandidates('t12', fetcher);
		const before = assigneeCandidatesEpoch();
		invalidateAssigneeCandidates();
		fetcher.mockResolvedValue([convidado]);
		expect(await loadAssigneeCandidates('t12', fetcher)).toEqual([convidado]);
		expect(fetcher).toHaveBeenCalledTimes(2);
		expect(assigneeCandidatesEpoch()).toBe(before + 1);
	});

	it('descarta a chave quando a requisição falha, permitindo nova tentativa', async () => {
		const fetcher = vi.fn().mockRejectedValueOnce(new Error('rede')).mockResolvedValue([convidado]);
		await expect(loadAssigneeCandidates('p4', fetcher)).rejects.toThrow('rede');
		expect(await loadAssigneeCandidates('p4', fetcher)).toEqual([convidado]);
		expect(fetcher).toHaveBeenCalledTimes(2);
	});
});
