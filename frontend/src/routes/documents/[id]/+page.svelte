<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import ScanAdjuster from '$lib/components/ScanAdjuster.svelte';
  import type { Category, Document, ScanCorners, ScanMode } from '$lib/types';

  let document: Document | null = null;
  let categories: Category[] = [];
  let loading = true;
  let error = '';
  let editingTitle = false;
  let titleDraft = '';
  let saving = false;
  let deleting = false;
  let adjusting = false;
  let mounted = true;

  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
  const confidence = (value: number | null) => value == null ? 'Unavailable' : value.toFixed(2);
  const analysisMetadata = (item: Document) => {
    const value = item.scan_debug?.document_analysis;
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
  };
  const semanticMetadata = (item: Document) => {
    const value = item.scan_debug?.semantic_search;
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
  };
  const detectorMethod = (item: Document) =>
    String(item.scan_debug?.selected_method ?? item.scan_debug?.detection_method ?? 'Unavailable');
  const isProcessing = (item: Document | null) =>
    item?.processing_status === 'uploaded' || item?.processing_status === 'processing';
  const delay = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function pollUntilFinished(id: number) {
    while (mounted && isProcessing(document)) {
      await delay(1200);
      if (!mounted) return;
      try {
        const updated = await api.document(id);
        document = updated;
        if (!editingTitle) titleDraft = updated.title;
      } catch (cause) {
        error = cause instanceof Error ? cause.message : 'Could not refresh document status.';
        return;
      }
    }
  }

  onMount(() => {
    const id = Number($page.params.id);
    void (async () => {
      try {
        [document, categories] = await Promise.all([api.document(id), api.categories()]);
        titleDraft = document.title;
      } catch (cause) {
        error = cause instanceof Error ? cause.message : 'Could not load document.';
      } finally {
        loading = false;
      }
      if (isProcessing(document)) await pollUntilFinished(id);
    })();
    return () => { mounted = false; };
  });

  async function saveTitle() {
    if (!document || !titleDraft.trim()) return;
    saving = true;
    try { document = await api.updateDocument(document.id, { title: titleDraft }); editingTitle = false; }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Could not save title.'; }
    finally { saving = false; }
  }

  async function moveFolder(event: Event) {
    if (!document) return;
    saving = true;
    try {
      document = await api.updateDocument(document.id, { category_id: Number((event.currentTarget as HTMLSelectElement).value) });
      window.dispatchEvent(new CustomEvent('scanny:categories-changed'));
    }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Could not move document.'; }
    finally { saving = false; }
  }

  async function saveAdjustment(corners: ScanCorners, scanMode: ScanMode) {
    if (!document) return;
    const documentId = document.id;
    saving = true;
    error = '';
    try {
      document = await api.adjustDocument(documentId, corners, scanMode);
      adjusting = false;
      saving = false;
      if (isProcessing(document)) await pollUntilFinished(documentId);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not save the adjusted scan.';
    } finally {
      saving = false;
    }
  }

  async function deleteDocument() {
    if (!document || !window.confirm(`Delete “${document.title}”? This cannot be undone.`)) return;
    deleting = true;
    error = '';
    try {
      await api.deleteDocument(document.id);
      await goto('/');
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not delete the document.';
      deleting = false;
    }
  }
</script>

<svelte:head><title>{document?.title ?? 'Document'} · Scanny</title></svelte:head>

{#if loading}
  <div class="viewer-loading"><div class="spinner dark"></div><span>Loading scan…</span></div>
{:else if error && !document}
  <div class="error-state"><strong>Couldn’t open this document.</strong><span>{error}</span><a class="button secondary" href="/">Back to Recent</a></div>
{:else if document}
  <div class="document-detail">
    <a class="back-link no-print" href="/"><span>←</span> Recent</a>
    <header class="detail-header no-print">
      <div class="detail-heading">
        {#if editingTitle}
          <form class="title-form" on:submit|preventDefault={saveTitle}>
            <input bind:value={titleDraft} maxlength="200" aria-label="Document title" />
            <button class="button primary" disabled={saving}>Save</button>
            <button class="button quiet" type="button" on:click={() => { editingTitle = false; titleDraft = document?.title ?? ''; }}>Cancel</button>
          </form>
        {:else}
          <div class="editable-title"><h1>{document.title}</h1><button class="icon-button" disabled={isProcessing(document)} aria-label="Edit title" title="Edit title" on:click={() => (editingTitle = true)}><svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16z" /></svg></button></div>
        {/if}
        <div class="detail-meta">
          <select aria-label="Move to folder" value={document.category_id} disabled={saving || isProcessing(document)} on:change={moveFolder}>
            {#each categories as category}<option value={category.id}>{category.name}</option>{/each}
          </select>
          <span>·</span><time datetime={document.created_at}>{formatDate(document.created_at)}</time>
          {#if document.processing_status === 'needs_review'}<span>·</span><span class="status-review">Needs review</span>{/if}
          {#if isProcessing(document)}<span>·</span><span class="status-processing">Processing</span>{/if}
        </div>
      </div>
      <div class="detail-actions">
        {#if !adjusting}<button class="button danger" disabled={isProcessing(document) || deleting} on:click={deleteDocument}><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" /></svg>{deleting ? 'Deleting…' : 'Delete'}</button>{/if}
        {#if !adjusting}<button class="button secondary" disabled={isProcessing(document)} on:click={() => { error = ''; adjusting = true; }}><svg viewBox="0 0 24 24"><path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M8 8h8v8H8z" /></svg>Adjust</button>{/if}
        <button class="button secondary print-button" disabled={isProcessing(document) || adjusting} on:click={() => window.print()}><svg viewBox="0 0 24 24"><path d="M7 9V4h10v5M7 17H5a2 2 0 01-2-2v-4a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2h-2M7 14h10v7H7z" /></svg>Print</button>
      </div>
    </header>
    {#if error}<div class="alert no-print">{error}<button on:click={() => (error = '')}>×</button></div>{/if}

    {#if document.processing_status === 'needs_review' && !adjusting}
      <section class="review-category-prompt no-print">
        <div class="review-prompt-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5L20 19.5H4zM12 9v5M12 17h.01" /></svg></div>
        <div class="review-prompt-copy">
          <h2>What category is this?</h2>
          <p>The scan needs review. File it now so it doesn’t stay in Needs Review.</p>
        </div>
        <select aria-label="Choose document category" value={document.category_id} disabled={saving} on:change={moveFolder}>
          {#each categories as category}<option value={category.id}>{category.is_system ? 'Choose a category…' : category.name}</option>{/each}
        </select>
        <button class="button secondary" on:click={() => (adjusting = true)}>Adjust scan</button>
      </section>
    {/if}

    {#if adjusting}
      <ScanAdjuster
        originalUrl={document.original_image_url}
        initialCorners={document.detected_corners}
        initialMode={document.scan_mode}
        {saving}
        oncancel={() => { adjusting = false; error = ''; }}
        onsave={saveAdjustment}
      />
    {:else}
      <div class:has-processing={isProcessing(document)} class="scan-stage">
        <img class:processing-preview={isProcessing(document)} class="scan-image" src={document.scanned_image_url} alt={document.title} />
        {#if isProcessing(document)}
          <div class="processing-overlay" aria-live="polite">
            <span class="spinner dark" aria-hidden="true"></span>
            <strong>Processing document…</strong>
            <span>You can keep browsing while Scanny finishes.</span>
          </div>
        {/if}
      </div>
    {/if}

    {#if !isProcessing(document) && !adjusting}
      {@const analysis = analysisMetadata(document)}
      {@const semantic = semanticMetadata(document)}
      <details class="debug-panel no-print">
        <summary><span>Diagnostics</span><span class="chevron">⌄</span></summary>
        <div class="debug-content">
          <section class="debug-block full">
            <h2>Markdown transcription</h2>
            <pre>{document.ocr_text || document.ocr_error || 'No transcription is available.'}</pre>
          </section>
          <section class="debug-block">
            <h2>Gemini metadata</h2>
            <dl>
              <div><dt>Returned title</dt><dd>{String(analysis.model_title ?? document.title)}</dd></div>
              <div><dt>Returned category</dt><dd>{String(analysis.model_category ?? document.category.name)}</dd></div>
              <div><dt>Validated category</dt><dd>{document.category.name}</dd></div>
              <div><dt>Category confidence</dt><dd>{confidence(document.classification_confidence)}</dd></div>
              <div><dt>Provider</dt><dd>{String(analysis.provider ?? 'Unavailable')}</dd></div>
            </dl>
            {#if document.classification_error}<p class="debug-note">{document.classification_error}</p>{/if}
          </section>
          <section class="debug-block">
            <h2>Processing</h2>
            <dl>
              <div><dt>Status</dt><dd>{document.processing_status}</dd></div>
              <div><dt>Scan mode</dt><dd>{document.scan_mode === 'black_and_white' ? 'B&W' : 'Color'}</dd></div>
              <div><dt>Scan confidence</dt><dd>{confidence(document.scan_confidence)}</dd></div>
              <div><dt>Detector</dt><dd>{detectorMethod(document)}</dd></div>
              <div><dt>Search embedding</dt><dd>{String(semantic.embedding ?? analysis.embedding ?? 'Unavailable')}</dd></div>
              <div><dt>Embedding model</dt><dd>{String(semantic.model ?? analysis.embedding_model ?? 'Unavailable')}</dd></div>
            </dl>
          </section>
          <section class="debug-block image-comparison full">
            <h2>Images</h2>
            <div>
              <a href={document.original_image_url} target="_blank" rel="noreferrer"><img src={document.original_image_url} alt="Original capture" /><span>Original image ↗</span></a>
              <a href={document.scanned_image_url} target="_blank" rel="noreferrer"><img src={document.scanned_image_url} alt="Processed scan" /><span>Processed scan ↗</span></a>
            </div>
          </section>
        </div>
      </details>
    {/if}
  </div>
{/if}
