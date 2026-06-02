// SPA pura (CSR): sem SSR, sem prerender. O Flask serve o index via Jinja (CSP nonce).
// CSRF e responsabilidade do backend Flask (cookie de sessao + X-CSRFToken); o
// checkOrigin do Kit fica desligado em svelte.config.js.
export const ssr = false;
export const prerender = false;
