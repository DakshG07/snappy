<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Document } from '$lib/types';
  import DocumentCard from '$lib/components/DocumentCard.svelte';
  import UploadButton from '$lib/components/UploadButton.svelte';

  let documents: Document[] = [];
  let loading = true;
  let error = '';
  let searchQuery = '';
  let searchResults: Document[] = [];
  let searchLoading = false;
  let searchError = '';
  let searchController: AbortController | undefined;
  let searchSequence = 0;
  let submittedQuery = '';
  $: searching = submittedQuery.length >= 2;
  const isProcessing = (document: Document) =>
    document.processing_status === 'uploaded' || document.processing_status === 'processing';
  const delay = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function clearSearch() {
    searchQuery = '';
    searchResults = [];
    searchError = '';
    searchLoading = false;
    submittedQuery = '';
    searchController?.abort();
  }

  async function submitSearch() {
    searchController?.abort();
    const query = searchQuery.trim();
    if (query.length < 2) return;
    submittedQuery = query;
    searchLoading = true;
    searchError = '';
    const sequence = ++searchSequence;
    const controller = new AbortController();
    searchController = controller;
    try {
      const response = await api.search(query, controller.signal);
      if (sequence === searchSequence) searchResults = response.results.map((result) => result.document);
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (sequence === searchSequence) {
        searchResults = [];
        searchError = cause instanceof Error ? cause.message : 'Search is temporarily unavailable.';
      }
    } finally {
      if (sequence === searchSequence) searchLoading = false;
    }
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && searchQuery) {
      event.preventDefault();
      clearSearch();
    }
  }

  function handleSearchInput() {
    if (!searchQuery.trim()) clearSearch();
  }

  onMount(() => {
    let mounted = true;
    void (async () => {
      try {
        documents = await api.documents();
        loading = false;
        while (mounted && documents.some(isProcessing)) {
          await delay(1500);
          if (mounted) documents = await api.documents();
        }
      } catch (cause) {
        error = cause instanceof Error ? cause.message : 'Could not load documents.';
      } finally {
        loading = false;
      }
    })();
    return () => { mounted = false; };
  });

  onDestroy(() => {
    searchController?.abort();
  });
</script>

<div class="page-header">
  <div><p class="eyebrow">Library</p><h1>Recent Documents</h1></div>
  <div class="mobile-upload no-print"><UploadButton /></div>
</div>

<form class="search-form no-print" on:submit|preventDefault={submitSearch}>
  <div class="search-field" class:active={searching}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>
    <label class="visually-hidden" for="document-search">Search your documents</label>
    <input
      id="document-search"
      type="search"
      placeholder="Search your documents"
      autocomplete="off"
      bind:value={searchQuery}
      on:input={handleSearchInput}
      on:keydown={handleSearchKeydown}
    />
    {#if searchLoading}<span class="spinner dark search-spinner" aria-label="Searching"></span>{/if}
    {#if searchQuery}
      <button type="button" class="search-clear" aria-label="Clear search" on:click={clearSearch}>×</button>
    {/if}
  </div>
  <button class="button primary search-submit" type="submit" disabled={searchQuery.trim().length < 2 || searchLoading}>
    Search
  </button>
</form>

{#if searching}
  <div class="search-heading"><p class="eyebrow">Search Results</p></div>
  {#if searchError}
    <div class="error-state search-state"><strong>Search is temporarily unavailable.</strong><span>{searchError}</span></div>
  {:else if searchLoading && searchResults.length === 0}
    <div class="search-loading"><span class="spinner dark" aria-hidden="true"></span><span>Searching…</span></div>
  {:else if searchResults.length === 0}
    <div class="empty-state search-state"><h2>No relevant documents found.</h2><p>Try using different words.</p></div>
  {:else}
    <div class="document-grid">
      {#each searchResults as document (document.id)}<DocumentCard {document} />{/each}
    </div>
  {/if}
{:else if loading}
  <div class="document-grid" aria-label="Loading documents">
    {#each Array(6) as _}<div class="document-card skeleton-card"><div class="thumbnail skeleton"></div><div class="card-body"><div class="skeleton line wide"></div><div class="skeleton line"></div></div></div>{/each}
  </div>
{:else if error}
  <div class="error-state"><strong>Couldn’t load your documents.</strong><span>{error}</span><button class="button secondary" on:click={() => location.reload()}>Try again</button></div>
{:else if documents.length === 0}
  <div class="empty-state">
    <div class="empty-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6zM15 3v5h4M9 13h7M9 17h5" /></svg></div>
    <h2>No documents yet</h2>
    <p>Upload an image to add your first scan.</p>
    <UploadButton />
  </div>
{:else}
  <div class="document-grid">
    {#each documents as document (document.id)}<DocumentCard {document} />{/each}
  </div>
{/if}
