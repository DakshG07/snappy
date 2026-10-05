<script lang="ts">
  import { api } from '$lib/api';
  import type { Category, Document } from '$lib/types';

  export let document: Document;
  export let categories: Category[];
  export let oncategorized: (documentId: number) => void;

  let categoryId = '';
  let saving = false;
  let error = '';
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(
      new Date(value)
    );
  const isProcessing = (item: Document) =>
    item.processing_status === 'uploaded' || item.processing_status === 'processing';
  $: availableCategories = categories.filter((category) => !category.is_system);

  async function categorize() {
    const selected = Number(categoryId);
    if (!selected) return;
    saving = true;
    error = '';
    try {
      await api.updateDocument(document.id, { category_id: selected });
      window.dispatchEvent(new CustomEvent('scanny:categories-changed'));
      oncategorized(document.id);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not categorize this document.';
    } finally {
      saving = false;
    }
  }
</script>

<article class="document-card unsure-document-card">
  <a class="card-preview-link" href={`/documents/${document.id}`} aria-label={`Open ${document.title}`}>
    <div class="thumbnail">
      <img src={document.scanned_image_url} alt="Preview of {document.title}" loading="lazy" />
      {#if document.processing_status === 'needs_review'}
        <span class="review-chip">Needs review</span>
      {:else if isProcessing(document)}
        <span class="processing-chip"><span class="spinner dark" aria-hidden="true"></span>Processing</span>
      {/if}
    </div>
    <div class="card-body unsure-card-heading">
      <h2>{document.title}</h2>
      <time datetime={document.created_at}>{formatDate(document.created_at)}</time>
    </div>
  </a>
  <form class="quick-categorize" on:submit|preventDefault={categorize}>
    <label for={`category-${document.id}`}>What category is this?</label>
    <div>
      <select id={`category-${document.id}`} bind:value={categoryId} disabled={saving || isProcessing(document)}>
        <option value="" disabled>Choose a folder…</option>
        {#each availableCategories as category}<option value={category.id}>{category.name}</option>{/each}
      </select>
      <button class="button primary" disabled={saving || !categoryId || isProcessing(document)}>
        {saving ? 'Saving…' : 'Categorize'}
      </button>
    </div>
    {#if availableCategories.length === 0}<a class="create-folder-link" href="/folders">Create a folder first →</a>{/if}
    {#if error}<p class="inline-error">{error}</p>{/if}
  </form>
</article>
