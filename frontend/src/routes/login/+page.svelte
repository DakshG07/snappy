<script lang="ts">
  import { goto } from '$app/navigation';
  import { login } from '$lib/auth';

  let email = '';
  let password = '';
  let error = '';
  let submitting = false;

  async function submit() {
    error = '';
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      error = 'Enter a valid email address.';
      return;
    }
    if (password.length < 8) {
      error = 'Password must be at least 8 characters.';
      return;
    }
    submitting = true;
    try {
      await login(email, password);
      await goto('/');
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not sign in.';
    } finally {
      submitting = false;
    }
  }
</script>

<svelte:head><title>Sign In · Scanny</title></svelte:head>

<div class="auth-page">
  <section class="auth-card">
    <div class="auth-brand"><span class="brand-mark"><span></span></span><span>Scanny</span></div>
    <div class="auth-heading"><h1>Sign in</h1><p>Open your document library.</p></div>
    <form on:submit|preventDefault={submit}>
      <label for="email">Email</label>
      <input id="email" type="email" bind:value={email} autocomplete="email" required />
      <label for="password">Password</label>
      <input id="password" type="password" bind:value={password} autocomplete="current-password" minlength="8" required />
      {#if error}<p class="auth-error" role="alert">{error}</p>{/if}
      <button class="button primary auth-submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign In'}</button>
    </form>
    <p class="auth-switch">New to Scanny? <a href="/register">Create an account</a></p>
  </section>
</div>
