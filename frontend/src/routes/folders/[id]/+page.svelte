<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import type { Category, Document } from '$lib/types';
  import DocumentCard from '$lib/components/DocumentCard.svelte';
  import UncategorizedDocumentCard from '$lib/components/UncategorizedDocumentCard.svelte';

  let folder: Category | undefined;
  let categories: Category[] = [];
  let documents: Document[] = [];
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      const id = Number($page.params.id);
      const [folders, items] = await Promise.all([api.categories(), api.documents(id)]);
      categories = folders;
      folder = folders.find((item) => item.id === id);
      if (!folder) throw new Error('Folder not found.');
      documents = items;
    } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not load this folder.'; }
    finally { loading = false; }
  });

  function categorized(documentId: number) {
    documents = documents.filter((document) => document.id !== documentId);
    if (folder) folder = { ...folder, document_count: Math.max(0, folder.document_count - 1) };
  }
</script>

<svelte:head><title>{folder?.name ?? 'Folder'} · Scanny</title></svelte:head>

<a class="back-link" href="/folders"><span>←</span> Folders</a>
<div class="page-header compact">
  <div><p class="eyebrow">Folder</p><h1>{folder?.name ?? 'Loading…'}</h1>{#if folder}<p class="subtitle">{folder.document_count} {folder.document_count === 1 ? 'document' : 'documents'}</p>{/if}</div>
</div>

{#if loading}
  <div class="document-grid">{#each Array(4) as _}<div class="document-card skeleton-card"><div class="thumbnail skeleton"></div></div>{/each}</div>
{:else if error}
  <div class="error-state"><strong>Couldn’t open this folder.</strong><span>{error}</span></div>
{:else if documents.length === 0}
  <div class="empty-state small"><div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M3 7h7l2 2h9v10H3z" /></svg></div><h2>No documents in this folder</h2></div>
{:else}
  <div class="document-grid">
    {#each documents as document (document.id)}
      {#if folder?.is_system}
        <UncategorizedDocumentCard {document} {categories} oncategorized={categorized} />
      {:else}
        <DocumentCard {document} />
      {/if}
    {/each}
  </div>
{/if}
