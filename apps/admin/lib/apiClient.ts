import { getAdminToken, clearAdminToken } from './adminAuth';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAdminToken();
  const headers: HeadersInit = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(init?.headers ?? {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearAdminToken();
    if (typeof window !== 'undefined') window.location.href = '/login';
    throw new Error(`${path} 401`);
  }
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

export { BASE };
