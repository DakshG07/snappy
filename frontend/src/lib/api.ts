import type { Category, Document, ScanCorners, ScanMode, SearchResponse, User } from './types';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...options, credentials: 'include' });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    if (response.status === 401 && !path.startsWith('/api/auth/') && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('scanny:unauthorized'));
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  me: () => request<User>('/api/auth/me'),
  register: (email: string, password: string) =>
    request<User>('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    }),
  login: (email: string, password: string) =>
    request<User>('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  documents: (categoryId?: number) =>
    request<Document[]>(`/api/documents${categoryId ? `?category_id=${categoryId}` : ''}`),
  document: (id: number) => request<Document>(`/api/documents/${id}`),
  search: (query: string, signal?: AbortSignal) =>
    request<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`, { signal }),
  upload: (file: File) => {
    const form = new FormData();
    form.append('image', file);
    return request<Document>('/api/documents', { method: 'POST', body: form });
  },
  updateDocument: (id: number, values: { title?: string; category_id?: number }) =>
    request<Document>(`/api/documents/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values)
    }),
  adjustDocument: (id: number, corners: ScanCorners, scanMode: ScanMode) =>
    request<Document>(`/api/documents/${id}/adjust`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners, scan_mode: scanMode })
    }),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
  categories: () => request<Category[]>('/api/categories'),
  createCategory: (name: string) =>
    request<Category>('/api/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    }),
  updateCategory: (id: number, name: string) =>
    request<Category>(`/api/categories/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    }),
  deleteCategory: (id: number) => request<void>(`/api/categories/${id}`, { method: 'DELETE' })
};
