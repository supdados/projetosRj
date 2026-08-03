/**
 * Testes do espelho cliente da politica de concessao de administrador.
 * As regras replicam `services/admin_grant_policy.py` (fonte da verdade).
 */
import { describe, it, expect } from 'vitest';
import {
	canDeleteUser,
	canGrantAdmin,
	canManageUser,
	MSG_SO_SUPER_ADMIN_ALTERA_PERFIL,
	MSG_SO_SUPER_ADMIN_GERE_ADMIN,
	type GrantTarget,
	type GrantViewer
} from './adminGrant';

const superAdmin: GrantViewer = { id: 1, is_super_admin: true };
const adminComum: GrantViewer = { id: 2, is_super_admin: false };
const usuarioComum: GrantViewer = { id: 3 };

const alvoSuper: GrantTarget = { id: 1, is_admin: true, is_super_admin: true };
const alvoAdmin: GrantTarget = { id: 2, is_admin: true, is_super_admin: false };
const alvoOutroAdmin: GrantTarget = { id: 4, is_admin: true, is_super_admin: false };
const alvoComum: GrantTarget = { id: 3, is_admin: false, is_super_admin: false };

describe('canGrantAdmin', () => {
	it('libera apenas o administrador principal', () => {
		expect(canGrantAdmin(superAdmin)).toBe(true);
		expect(canGrantAdmin(adminComum)).toBe(false);
		expect(canGrantAdmin(usuarioComum)).toBe(false);
	});

	it('nega quando a sessao ainda nao carregou (fail-closed)', () => {
		expect(canGrantAdmin(null)).toBe(false);
		expect(canGrantAdmin(undefined)).toBe(false);
	});

	it('nega quando o backend nao envia is_super_admin', () => {
		expect(canGrantAdmin({ id: 9 })).toBe(false);
	});
});

describe('canManageUser', () => {
	it('super admin gerencia qualquer alvo', () => {
		expect(canManageUser(superAdmin, alvoAdmin)).toBe(true);
		expect(canManageUser(superAdmin, alvoComum)).toBe(true);
		expect(canManageUser(superAdmin, alvoSuper)).toBe(true);
	});

	it('admin comum gerencia nao-admins e a si mesmo', () => {
		expect(canManageUser(adminComum, alvoComum)).toBe(true);
		expect(canManageUser(adminComum, alvoAdmin)).toBe(true);
	});

	it('admin comum nao gerencia outro admin nem o principal', () => {
		expect(canManageUser(adminComum, alvoOutroAdmin)).toBe(false);
		expect(canManageUser(adminComum, alvoSuper)).toBe(false);
	});

	it('nega sem viewer', () => {
		expect(canManageUser(null, alvoComum)).toBe(false);
	});
});

describe('canDeleteUser', () => {
	it('nunca exclui o administrador principal', () => {
		expect(canDeleteUser(superAdmin, alvoSuper)).toBe(false);
		expect(canDeleteUser(adminComum, alvoSuper)).toBe(false);
	});

	it('nunca exclui a propria conta', () => {
		expect(canDeleteUser(adminComum, alvoAdmin)).toBe(false);
	});

	it('super admin exclui admin comum', () => {
		expect(canDeleteUser(superAdmin, alvoOutroAdmin)).toBe(true);
	});

	it('admin comum exclui nao-admin, mas nao outro admin', () => {
		expect(canDeleteUser(adminComum, alvoComum)).toBe(true);
		expect(canDeleteUser(adminComum, alvoOutroAdmin)).toBe(false);
	});
});

describe('mensagens', () => {
	it('sao textos PT nao vazios', () => {
		expect(MSG_SO_SUPER_ADMIN_ALTERA_PERFIL).toContain('administrador principal');
		expect(MSG_SO_SUPER_ADMIN_GERE_ADMIN).toContain('administrador principal');
	});
});
