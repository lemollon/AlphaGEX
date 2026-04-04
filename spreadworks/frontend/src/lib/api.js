/**
 * Centralized API URL configuration.
 *
 * In dev mode (npm run dev), Vite proxies /api/* to localhost:8000,
 * so the empty-string default works.
 *
 * In production, VITE_API_URL must be set at build time
 * (e.g. https://spreadworks-backend.onrender.com).
 */
export const API_URL = import.meta.env.VITE_API_URL || '';
