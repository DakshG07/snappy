<script lang="ts">
  import '../styles.css';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import { authReady, currentUser, loadCurrentUser, logout as endSession } from '$lib/auth';
  import UploadButton from '$lib/components/UploadButton.svelte';

  let { children } = $props();
  let unsureId = $state<number | null>(null);
  let unsureCount = $state(0);
  let loggingOut = $state(false);
  let authRoute = $derived($page.url.pathname === '/login' || $page.url.pathname === '/register');

  async function refreshUnsureCount() {
    try {
      const categories = await api.categories();
      const unsure = categories.find((category) => category.is_system);
      unsureId = unsure?.id ?? null;
      unsureCount = unsure?.document_count ?? 0;
    } catch {
      // Navigation should remain usable if the status count cannot refresh.
    }
  }

  onMount(() => {
    let interval: number | undefined;
    let disposed = false;
    const refresh = () => void refreshUnsureCount();
    void (async () => {
      const user = await loadCurrentUser();
      if (disposed) return;
      if (!user && !authRoute) {
        await goto('/login');
      } else if (user && authRoute) {
        await goto('/');
      }
      if (user) {
        await refreshUnsureCount();
        interval = window.setInterval(refresh, 10000);
      }
    })();
    const unauthorized = () => {
      currentUser.set(null);
      authReady.set(true);
      void goto('/login');
    };
    window.addEventListener('scanny:categories-changed', refresh);
    window.addEventListener('scanny:unauthorized', unauthorized);
    return () => {
      disposed = true;
      if (interval !== undefined) window.clearInterval(interval);
      window.removeEventListener('scanny:categories-changed', refresh);
      window.removeEventListener('scanny:unauthorized', unauthorized);
    };
  });

  async function signOut() {
    loggingOut = true;
    try {
      await endSession();
      await goto('/login');
    } finally {
      loggingOut = false;
    }
  }
</script>

<svelte:head><title>Scanny</title><meta name="description" content="Your school papers, quietly organized." /></svelte:head>

{#if authRoute}
  <main class="auth-main">{@render children()}</main>
{:else if !$authReady}
  <div class="auth-loading"><span class="spinner dark"></span><span>Opening Scanny…</span></div>
{:else if $currentUser}
  <div class="app-shell">
    <aside class="sidebar no-print">
      <a class="brand" href="/" aria-label="Scanny home">
        <span class="brand-mark"><span></span></span>
        <span>Scanny</span>
      </a>
      <nav aria-label="Main navigation">
        <a class:active={$page.url.pathname === '/'} href="/">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4zM8 9h8M8 13h8M8 17h5" /></svg>
          Recent
        </a>
        <a class:active={$page.url.pathname.startsWith('/folders')} href="/folders">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v10H3z" /></svg>
          Folders
        </a>
      </nav>
      <button class="mobile-logout" type="button" title={`Signed in as ${$currentUser.email}. Log out`} aria-label={`Log out ${$currentUser.email}`} disabled={loggingOut} onclick={signOut}>
        <span>{$currentUser.email.slice(0, 1).toUpperCase()}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" /></svg>
      </button>
      <div class="sidebar-upload"><UploadButton /></div>
      <div class="sidebar-footer">
        {#if unsureCount > 0 && unsureId !== null}
          <a class="uncategorized-notice" href={`/folders/${unsureId}`}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5L20 19.5H4zM12 9v5M12 17h.01" /></svg>
            <span><strong>{unsureCount} {unsureCount === 1 ? 'document' : 'documents'}</strong> couldn’t be categorized</span>
            <span aria-hidden="true">→</span>
          </a>
        {/if}
        <div class="sidebar-user">
          <div><span class="user-avatar">{$currentUser.email.slice(0, 1).toUpperCase()}</span><span title={$currentUser.email}>{$currentUser.email}</span></div>
          <button type="button" disabled={loggingOut} onclick={signOut}>{loggingOut ? 'Signing out…' : 'Logout'}</button>
        </div>
        <p class="local-note"><span></span> Local workspace</p>
      </div>
    </aside>
    <main class="main-content">{@render children()}</main>
  </div>
{/if}
