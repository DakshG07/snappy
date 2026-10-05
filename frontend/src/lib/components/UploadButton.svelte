<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';

  let input: HTMLInputElement;
  let uploading = false;
  let error = '';

  async function selectImage(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    uploading = true;
    error = '';
    try {
      const document = await api.upload(file);
      await goto(`/documents/${document.id}`);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Upload failed.';
    } finally {
      uploading = false;
      input.value = '';
    }
  }
</script>

<div class="upload-wrap">
  <input bind:this={input} class="visually-hidden" type="file" accept="image/jpeg,image/png" on:change={selectImage} />
  <button class="button primary" disabled={uploading} on:click={() => input.click()}>
    {#if uploading}
      <span class="spinner" aria-hidden="true"></span>
      Uploading…
    {:else}
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v5h14v-5" /></svg>
      Upload image
    {/if}
  </button>
  {#if error}<div class="upload-error" role="alert">{error}</div>{/if}
</div>
