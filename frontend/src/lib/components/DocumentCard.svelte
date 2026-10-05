<script lang="ts">
  import type { Document } from '$lib/types';
  export let document: Document;

  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(
      new Date(value)
    );
</script>

<a class="document-card" href={`/documents/${document.id}`}>
  <div class="thumbnail">
    <img src={document.scanned_image_url} alt="Preview of {document.title}" loading="lazy" />
    {#if document.processing_status === 'needs_review'}
      <span class="review-chip">Needs review</span>
    {:else if document.processing_status === 'uploaded' || document.processing_status === 'processing'}
      <span class="processing-chip"><span class="spinner dark" aria-hidden="true"></span>Processing</span>
    {/if}
  </div>
  <div class="card-body">
    <h2>{document.title}</h2>
    <div class="card-meta">
      <span class="category-badge">{document.category.name}</span>
      <time datetime={document.created_at}>{formatDate(document.created_at)}</time>
    </div>
  </div>
</a>
