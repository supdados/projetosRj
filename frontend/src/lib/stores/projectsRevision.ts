/**
 * Sinal global de revisão da lista de projetos: quem importa projetos fora da
 * tela de Projetos chama `bumpProjectsRevision()`; a tela recarrega ao ver o
 * número mudar.
 */
import { writable } from 'svelte/store';

export const projectsRevision = writable<number>(0);

export function bumpProjectsRevision(): void {
	projectsRevision.update((n) => n + 1);
}
