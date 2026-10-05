<script lang="ts">
  import type { ScanCorners, ScanMode } from '$lib/types';

  export let originalUrl: string;
  export let initialCorners: ScanCorners | null;
  export let initialMode: ScanMode;
  export let saving = false;
  export let oncancel: () => void;
  export let onsave: (corners: ScanCorners, mode: ScanMode) => void;

  type CornerName = keyof ScanCorners;
  const cornerNames: CornerName[] = ['top_left', 'top_right', 'bottom_right', 'bottom_left'];
  const cornerLabels: Record<CornerName, string> = {
    top_left: '1',
    top_right: '2',
    bottom_right: '3',
    bottom_left: '4'
  };

  let width = 0;
  let height = 0;
  let initialized = false;
  let activeCorner: CornerName | null = null;
  let overlay: SVGSVGElement;
  let mode: ScanMode = initialMode;
  let corners: ScanCorners = {
    top_left: [0, 0],
    top_right: [0, 0],
    bottom_right: [0, 0],
    bottom_left: [0, 0]
  };

  function clampPoint(point: [number, number]): [number, number] {
    return [Math.max(0, Math.min(width, point[0])), Math.max(0, Math.min(height, point[1]))];
  }

  function imageLoaded(event: Event) {
    const image = event.currentTarget as HTMLImageElement;
    width = image.naturalWidth;
    height = image.naturalHeight;
    if (initialized) return;
    const insetX = width * 0.06;
    const insetY = height * 0.06;
    const defaults: ScanCorners = {
      top_left: [insetX, insetY],
      top_right: [width - insetX, insetY],
      bottom_right: [width - insetX, height - insetY],
      bottom_left: [insetX, height - insetY]
    };
    const source = initialCorners ?? defaults;
    corners = {
      top_left: clampPoint(source.top_left),
      top_right: clampPoint(source.top_right),
      bottom_right: clampPoint(source.bottom_right),
      bottom_left: clampPoint(source.bottom_left)
    };
    initialized = true;
  }

  function updateFromPointer(event: PointerEvent) {
    if (!activeCorner || !overlay) return;
    const bounds = overlay.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const y = ((event.clientY - bounds.top) / bounds.height) * height;
    corners = { ...corners, [activeCorner]: clampPoint([x, y]) };
  }

  function beginDrag(event: PointerEvent, corner: CornerName) {
    event.preventDefault();
    activeCorner = corner;
    overlay.setPointerCapture(event.pointerId);
    updateFromPointer(event);
  }

  function endDrag(event: PointerEvent) {
    if (overlay.hasPointerCapture(event.pointerId)) overlay.releasePointerCapture(event.pointerId);
    activeCorner = null;
  }

  function moveWithKeyboard(event: KeyboardEvent, corner: CornerName) {
    const movements: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1]
    };
    const movement = movements[event.key];
    if (!movement) return;
    event.preventDefault();
    const step = event.shiftKey ? 10 : 1;
    corners = {
      ...corners,
      [corner]: clampPoint([
        corners[corner][0] + movement[0] * step,
        corners[corner][1] + movement[1] * step
      ])
    };
  }

  $: polygonPoints = cornerNames.map((name) => corners[name].join(',')).join(' ');
  $: handleRadius = Math.max(18, Math.min(width, height) * 0.018);
  $: lineWidth = Math.max(5, Math.min(width, height) * 0.004);
</script>

<section class="adjust-shell no-print" aria-label="Adjust scan corners">
  <div class="adjust-toolbar">
    <div>
      <h2>Adjust scan</h2>
      <p>Drag each numbered handle to a corner of the document.</p>
    </div>
    <fieldset class="scan-mode" disabled={saving}>
      <legend>Output</legend>
      <label class:active={mode === 'color'}><input type="radio" bind:group={mode} value="color" />Color</label>
      <label class:active={mode === 'black_and_white'}><input type="radio" bind:group={mode} value="black_and_white" />B&amp;W</label>
    </fieldset>
    <div class="adjust-actions">
      <button class="button quiet" type="button" disabled={saving} on:click={oncancel}>Cancel</button>
      <button class="button primary" type="button" disabled={saving || !initialized} on:click={() => onsave(corners, mode)}>
        {#if saving}<span class="spinner" aria-hidden="true"></span>Saving…{:else}Save scan{/if}
      </button>
    </div>
  </div>

  <div class="adjust-stage">
    <div class="adjust-canvas">
      <img
        class:preview-bw={mode === 'black_and_white'}
        src={originalUrl}
        alt="Original document capture"
        on:load={imageLoaded}
      />
      {#if width && height}
        <svg
          bind:this={overlay}
          class="corner-overlay"
          class:dragging={activeCorner !== null}
          role="group"
          aria-label="Document corner controls"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          on:pointermove={updateFromPointer}
          on:pointerup={endDrag}
          on:pointercancel={endDrag}
          on:pointerleave={(event) => activeCorner && endDrag(event)}
        >
          <polygon points={polygonPoints} style={`stroke-width:${lineWidth}`} />
          {#each cornerNames as corner}
            <g
              class="corner-handle"
              class:active={activeCorner === corner}
              role="button"
              tabindex="0"
              aria-label={`Corner ${cornerLabels[corner]}`}
              on:pointerdown={(event) => beginDrag(event, corner)}
              on:keydown={(event) => moveWithKeyboard(event, corner)}
            >
              <circle cx={corners[corner][0]} cy={corners[corner][1]} r={handleRadius} style={`stroke-width:${lineWidth}`} />
              <text x={corners[corner][0]} y={corners[corner][1]} dy="0.35em" style={`font-size:${handleRadius * 1.05}px`}>{cornerLabels[corner]}</text>
            </g>
          {/each}
        </svg>
      {/if}
    </div>
  </div>
  <p class="adjust-hint">B&amp;W is previewed approximately here; the server generates the final high-contrast version when you save.</p>
</section>
