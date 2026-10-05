<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Category } from '$lib/types';

  let categories: Category[] = [];
  let loading = true;
  let error = '';
  let showCreate = false;
  let folderName = '';
  let saving = false;
  let editingId: number | null = null;
  let editingName = '';
  $: visibleCategories = categories.filter((category) => !category.is_system || category.document_count > 0);

  async function load() {
    try { categories = await api.categories(); error = ''; }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Could not load folders.'; }
    finally { loading = false; }
  }

  onMount(load);

  async function createFolder() {
    if (!folderName.trim()) return;
    saving = true;
    try {
      await api.createCategory(folderName);
      folderName = '';
      showCreate = false;
      await load();
    } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not create folder.'; }
    finally { saving = false; }
  }

  async function renameFolder(category: Category) {
    if (!editingName.trim()) return;
    try { await api.updateCategory(category.id, editingName); editingId = null; await load(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Could not rename folder.'; }
  }

  async function deleteFolder(category: Category) {
    if (!confirm(`Delete the empty “${category.name}” folder?`)) return;
    try { await api.deleteCategory(category.id); await load(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Could not delete folder.'; }
  }
</script>

<svelte:head><title>Folders · Scanny</title></svelte:head>

<div class="page-header">
  <div><p class="eyebrow">Organization</p><h1>Folders</h1></div>
  <button class="button primary" on:click={() => (showCreate = true)}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>Create folder
  </button>
</div>

{#if showCreate}
  <form class="inline-form" on:submit|preventDefault={createFolder}>
    <label for="new-folder">Folder name</label>
    <input id="new-folder" bind:value={folderName} maxlength="80" placeholder="e.g. Physics" />
    <button class="button primary" disabled={saving || !folderName.trim()}>{saving ? 'Creating…' : 'Create'}</button>
    <button class="button quiet" type="button" on:click={() => (showCreate = false)}>Cancel</button>
  </form>
{/if}

{#if error}<div class="alert" role="alert">{error}<button aria-label="Dismiss" on:click={() => (error = '')}>×</button></div>{/if}

{#if loading}
  <div class="folder-grid">{#each Array(4) as _}<div class="folder-card skeleton-card"><div class="skeleton folder-icon"></div><div class="skeleton line wide"></div><div class="skeleton line"></div></div>{/each}</div>
{:else if visibleCategories.length === 0}
  <div class="empty-state small">
    <div class="empty-icon">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v10H3z" /></svg>
    </div>
    <h2>No folders yet</h2>
    <p>Create a folder to start organizing your scans.</p>
  </div>
{:else}
  <div class="folder-grid">
    {#each visibleCategories as category (category.id)}
      <article class:system-review={category.is_system} class="folder-card">
        {#if editingId === category.id}
          <div class="folder-link">
            <div class:review={category.is_system} class="folder-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v10H3z" /></svg>
            </div>
            <form on:submit|preventDefault={() => renameFolder(category)}>
              <input bind:value={editingName} maxlength="80" aria-label="Folder name" />
              <button class="icon-button" title="Save" aria-label="Save">✓</button>
            </form>
            <p>{category.document_count} {category.document_count === 1 ? 'document' : 'documents'}</p>
          </div>
        {:else}
          <a class="folder-link" href={`/folders/${category.id}`} aria-label={`Open ${category.name}`}>
          <div class:review={category.is_system} class="folder-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v10H3z" /></svg>
          </div>
            <h2>{category.name}</h2>
            <p>{category.document_count} {category.document_count === 1 ? 'document' : 'documents'}</p>
          </a>
        {/if}
        {#if !category.is_system}
          <div class="folder-actions">
            <button class="icon-button" title="Rename" aria-label={`Rename ${category.name}`} on:click={() => { editingId = category.id; editingName = category.name; }}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" /></svg>
            </button>
            <button class="icon-button danger" disabled={category.document_count > 0} title={category.document_count ? 'Move documents before deleting' : 'Delete'} aria-label={`Delete ${category.name}`} on:click={() => deleteFolder(category)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V4h6v3M8 10v8m4-8v8m4-8v8M7 7l1 14h8l1-14" /></svg>
            </button>
          </div>
        {/if}
      </article>
    {/each}
  </div>
{/if}
