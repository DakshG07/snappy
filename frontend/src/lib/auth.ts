import { writable } from 'svelte/store';
import { api } from './api';
import type { User } from './types';

export const currentUser = writable<User | null>(null);
export const authReady = writable(false);

export async function loadCurrentUser(): Promise<User | null> {
  try {
    const user = await api.me();
    currentUser.set(user);
    return user;
  } catch {
    currentUser.set(null);
    return null;
  } finally {
    authReady.set(true);
  }
}

export async function login(email: string, password: string): Promise<User> {
  const user = await api.login(email, password);
  currentUser.set(user);
  authReady.set(true);
  return user;
}

export async function register(email: string, password: string): Promise<User> {
  const user = await api.register(email, password);
  currentUser.set(user);
  authReady.set(true);
  return user;
}

export async function logout(): Promise<void> {
  try {
    await api.logout();
  } finally {
    currentUser.set(null);
    authReady.set(true);
  }
}
