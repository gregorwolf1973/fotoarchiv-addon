<script>
  import { onMount, untrack } from 'svelte';
  import {
    clampView, fovLimits, lens, MODEL_IDS, MODEL_INDEX, MODELS, paniniEdge, paniniStrength, PRESETS, sanitize, SHADER, startView,
    STRETCH_MAX, TILT_MAX, VERTEX,
  } from '../lib/weitwinkel.js';
  import Icon from './Icon.svelte';

  // Weitwinkel- und Fischaugenfotos entzerrt ansehen: Ziehen schwenkt, Mausrad bzw. zwei Finger
  // zoomen, Pfeiltasten schwenken, +/- zoomt, 0 setzt zurück. Die Kamera (Vorgabe oder Linse,
  // Bildwinkel, Streckung, Neigung) stellt man unten ein; sie wird je Foto im Browser gemerkt.
  let { src, assetId, name = 'foto', onclose } = $props();

  const KEY = 'fotoarchiv.weitwinkel';
  const KEEP = 50; // so viele Fotos merkt sich der Browser, ältere fallen heraus
  const MAX_PIXELS = 16e6; // größere Fotos verkleinern, sonst scheitern Handys am Speicher
  let canvas = $state();
  let width = $state(0);
  let height = $state(0);
  let error = $state('');
  let loaded = $state(false);
  let photo = $state({ width: 0, height: 0 });
  // svelte-ignore state_referenced_locally
  let settings = $state(readSettings(assetId));
  let view = $state({ fov: 140, yaw: 0, pitch: 0 });
  let gl = null;
  let program = null;
  let uniforms = {};
  let fine = $state(false); // Feineinstellung aufgeklappt

  const cam = $derived(photo.width ? lens(settings, photo.width, photo.height) : null);
  const limits = $derived(fovLimits(settings.model));

  function readAll() {
    try {
      const all = JSON.parse(localStorage.getItem(KEY) ?? '{}');
      return all && typeof all === 'object' && Array.isArray(all.order) ? all : { order: [], photos: {} };
    } catch {
      return { order: [], photos: {} };
    }
  }
  function readSettings(id) {
    const all = readAll();
    return sanitize(all.photos?.[id] ?? all.last);
  }
  function storeSettings() {
    try {
      const all = readAll();
      const key = String(assetId);
      all.photos ??= {};
      all.photos[key] = all.last = { ...settings };
      all.order = [...all.order.filter((k) => k !== key), key];
      for (const old of all.order.splice(0, Math.max(0, all.order.length - KEEP))) delete all.photos[old];
      localStorage.setItem(KEY, JSON.stringify(all));
    } catch {
      /* ohne Speicher geht es auch */
    }
  }

  /** Einstellung ändern; jede Hand-Änderung macht aus der Vorgabe „eigene Einstellung“. */
  function change(patch) {
    settings = sanitize({ ...settings, preset: 'custom', ...patch });
    storeSettings();
  }
  function choosePreset(id) {
    if (PRESETS[id]) {
      settings = sanitize({ preset: id, ...PRESETS[id] });
      storeSettings();
    } else {
      change({});
    }
  }
  const reset = () => cam && (view = startView(cam));

  // Neue Kamera-Einstellung: Ansicht in die neuen Grenzen bringen, beim ersten Mal ganz zeigen
  let started = false;
  $effect(() => {
    if (!cam) return;
    if (!started) {
      started = true;
      view = startView(cam);
    } else {
      view = clampView(untrack(() => view), cam);
    }
  });

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }

  /** Foto als Textur laden; zu große Bilder vorher verkleinern (über ein Canvas, das die EXIF-Drehung beachtet). */
  function upload(img) {
    const max = Math.min(8192, gl.getParameter(gl.MAX_TEXTURE_SIZE) || 4096);
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    const scale = Math.min(1, max / Math.max(w, h), Math.sqrt(MAX_PIXELS / (w * h)));
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * scale);
    c.height = Math.round(img.naturalHeight * scale);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
    photo = { width: c.width, height: c.height };
  }

  onMount(() => {
    gl = canvas.getContext('webgl', { antialias: false });
    // Handy: nach App-Wechsel kann der Browser die Grafik verwerfen; dann bleibt das Bild sonst schwarz
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      loaded = false;
      error = 'Der Browser hat die Grafik zurückgesetzt – bitte die Ansicht schließen und neu öffnen.';
    });
    if (!gl) {
      error = 'Dieser Browser kann kein WebGL – die entzerrte Ansicht geht hier nicht.';
      return;
    }
    try {
      program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, SHADER));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    } catch (e) {
      error = `Die Ansicht ließ sich nicht starten: ${e.message}`;
      return;
    }
    gl.useProgram(program);
    for (const n of ['img', 'size', 'aspect', 'edge', 'd', 'f', 'model', 'stretch', 'yaw', 'pitch', 'tilt'])
      uniforms[n] = gl.getUniformLocation(program, n);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(program, 'pos');
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

    const img = new Image();
    img.onload = () => {
      upload(img);
      loaded = true;
    };
    img.onerror = () => (error = 'Das Foto ließ sich nicht laden.');
    img.src = src;
    return () => {
      img.onload = img.onerror = null; // nach dem Schließen nicht mehr hochladen
      img.src = '';
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
  });

  function draw() {
    if (!gl || !loaded || !cam || !width || !height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(width * dpr);
    const h = Math.round(height * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    const d = paniniStrength(view.fov);
    gl.uniform1i(uniforms.img, 0);
    gl.uniform2f(uniforms.size, photo.width, photo.height);
    gl.uniform1f(uniforms.aspect, h / w);
    gl.uniform1f(uniforms.edge, paniniEdge(view.fov, d));
    gl.uniform1f(uniforms.d, d);
    gl.uniform1f(uniforms.f, cam.f);
    gl.uniform1i(uniforms.model, MODEL_INDEX[settings.model]);
    gl.uniform1f(uniforms.stretch, cam.stretch);
    gl.uniform1f(uniforms.yaw, view.yaw);
    gl.uniform1f(uniforms.pitch, view.pitch);
    gl.uniform1f(uniforms.tilt, cam.tilt);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  // Neu zeichnen, sobald sich Ansicht, Einstellung oder Größe ändern (höchstens einmal je Bild)
  let frame = 0;
  $effect(() => {
    [view, settings, width, height, loaded, cam];
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  });

  /** Gezeigten Ausschnitt als JPEG speichern. */
  function save() {
    draw(); // direkt vor dem Auslesen zeichnen, sonst ist der Puffer schon geleert
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${name.replace(/\.[^.]+$/, '')}_entzerrt.jpg`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      },
      'image/jpeg',
      0.92,
    );
  }

  // ── Bedienung ──────────────────────────────────────────────────
  const radPerPixel = () => ((view.fov * Math.PI) / 180 / Math.max(1, width)) * 0.9;
  function pan(dx, dy) {
    if (cam) view = clampView({ ...view, yaw: view.yaw - dx * radPerPixel(), pitch: view.pitch + dy * radPerPixel() }, cam);
  }
  function zoom(factor) {
    if (cam) view = clampView({ ...view, fov: view.fov * factor }, cam);
  }

  const pointers = new Map();
  let pinch = null;
  function pointerdown(e) {
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {
      /* Zeiger schon wieder weg */
    }
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { dist: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, fov: view.fov };
    }
  }
  function pointermove(e) {
    const last = pointers.get(e.pointerId);
    if (!last) return;
    pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a[0] - b[0], a[1] - b[1]) || 1;
      if (cam) view = clampView({ ...view, fov: (pinch.fov * pinch.dist) / dist }, cam);
    } else if (pointers.size === 1) {
      pan(e.clientX - last[0], e.clientY - last[1]);
    }
  }
  function pointerup(e) {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
  }
  function wheel(e) {
    e.preventDefault();
    const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY; // Firefox liefert Zeilen
    zoom(Math.exp(delta * 0.0015));
  }
  $effect(() => {
    if (!canvas) return;
    canvas.addEventListener('wheel', wheel, { passive: false });
    return () => canvas.removeEventListener('wheel', wheel);
  });

  function keydown(e) {
    if (e.target.closest?.('input, select, textarea')) {
      if (e.key === 'Escape') onclose();
      return;
    }
    const step = 40;
    if (e.key === 'Escape' || e.key === 'w') onclose();
    else if (e.key === 'ArrowLeft') pan(step, 0);
    else if (e.key === 'ArrowRight') pan(-step, 0);
    else if (e.key === 'ArrowUp') pan(0, step);
    else if (e.key === 'ArrowDown') pan(0, -step);
    else if (e.key === '+' || e.key === '=') zoom(1 / 1.2);
    else if (e.key === '-') zoom(1.2);
    else if (e.key === '0') reset();
    else return;
    e.preventDefault();
    e.stopImmediatePropagation();
  }

  let closeButton = $state();
  $effect(() => closeButton?.focus());
</script>

<svelte:window onkeydown={keydown} />

<div class="weitwinkel" role="dialog" aria-modal="true" aria-label="Weitwinkel entzerrt" bind:clientWidth={width} bind:clientHeight={height}>
  <canvas
    bind:this={canvas}
    onpointerdown={pointerdown}
    onpointermove={pointermove}
    onpointerup={pointerup}
    onpointercancel={pointerup}
    ondblclick={reset}
    aria-label="Entzerrtes Foto: ziehen zum Schwenken, Mausrad zum Zoomen"
  ></canvas>

  {#if error}
    <p class="message">{error}</p>
  {:else if !loaded}
    <p class="message">Foto wird geladen …</p>
  {/if}

  <div class="bar top">
    <button class="round" bind:this={closeButton} onclick={onclose} title="Zurück zum Foto (Esc)"><Icon name="close" /></button>
    <span class="title">Weitwinkel entzerrt</span>
    <span class="spacer"></span>
    <button class="round" onclick={reset} disabled={!loaded} title="Ganze Ansicht (0, Doppelklick)"><Icon name="restore" /></button>
    <button class="round" onclick={save} disabled={!loaded} title="Ausschnitt als Bild speichern"><Icon name="download" /></button>
  </div>

  <div class="bar bottom">
    <label>
      Kamera
      <select value={settings.preset} onchange={(e) => choosePreset(e.currentTarget.value)}>
        {#each Object.entries(PRESETS) as [id, p] (id)}<option value={id}>{p.label}</option>{/each}
        <option value="custom">Eigene Einstellung</option>
      </select>
    </label>
    <button class="link" onclick={() => (fine = !fine)} aria-expanded={fine}>{fine ? 'Weniger' : 'Feineinstellung'}</button>
    {#if fine}
      <div class="fine">
        <label>
          Linse
          <select value={settings.model} onchange={(e) => change({ model: e.currentTarget.value })}>
            {#each MODEL_IDS as id (id)}<option value={id}>{MODELS[id].label}</option>{/each}
          </select>
        </label>
        <label class="slider" title="Bildwinkel von links nach rechts">
          Bildwinkel
          <input type="range" min={limits.min} max={limits.max} step="1" value={settings.fov}
            oninput={(e) => change({ fov: +e.currentTarget.value })} />
          <output>{settings.fov}°</output>
        </label>
        <label class="slider" title="Action-Kameras stauchen die Bildmitte und dehnen die Seiten (z. B. GoPro SuperView)">
          Seitenstreckung
          <input type="range" min="0" max={STRETCH_MAX} step="0.01" value={settings.stretch}
            oninput={(e) => change({ stretch: +e.currentTarget.value })} />
          <output>{Math.round(settings.stretch * 100)} %</output>
        </label>
        <label class="slider" title="Wie stark die Kamera nach unten (positiv) oder oben geneigt war">
          Neigung
          <input type="range" min={-TILT_MAX} max={TILT_MAX} step="1" value={settings.tilt}
            oninput={(e) => change({ tilt: +e.currentTarget.value })} />
          <output>{settings.tilt}°</output>
        </label>
        <span class="hint">Erst den Bildwinkel einstellen, bis Linien in der Mitte gerade sind, dann die Seitenstreckung für die Ränder, zuletzt die Neigung, bis Senkrechte senkrecht stehen.</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .weitwinkel {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: #000;
    color: #fff;
  }
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    touch-action: none;
    cursor: grab;
  }
  canvas:active {
    cursor: grabbing;
  }
  .message {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    margin: 0;
    padding: 12px 16px;
    max-width: calc(100% - 32px);
    border-radius: 8px;
    background: rgb(0 0 0 / 0.75);
    text-align: center;
  }
  .bar {
    position: absolute;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 16px;
    padding: 12px calc(12px + env(safe-area-inset-right, 0px)) 12px calc(12px + env(safe-area-inset-left, 0px));
  }
  .top {
    top: 0;
    gap: 4px;
    padding-top: calc(12px + env(safe-area-inset-top, 0px));
    background: linear-gradient(rgb(0 0 0 / 0.6), transparent);
  }
  .bottom {
    bottom: 0;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    background: linear-gradient(transparent, rgb(0 0 0 / 0.7));
    font-size: 0.9rem;
  }
  .title {
    margin-left: 4px;
    font-weight: 500;
  }
  .spacer {
    flex: 1;
  }
  label {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .slider input {
    width: min(200px, 34vw);
  }
  .fine {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 16px;
    width: 100%;
  }
  .link {
    min-height: 0;
    padding: 4px 8px;
    border: 0;
    background: transparent;
    color: #fff;
    text-decoration: underline;
    cursor: pointer;
  }
  output {
    min-width: 3.2em;
    font-variant-numeric: tabular-nums;
  }
  select {
    max-width: 60vw;
  }
  .hint {
    color: rgb(255 255 255 / 0.75);
    font-size: 0.8rem;
  }
  .round {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: #fff;
    cursor: pointer;
  }
  .round:hover:not(:disabled) {
    background: rgb(255 255 255 / 0.18);
  }
  .round:disabled {
    opacity: 0.4;
  }
  @media (max-width: 599px) {
    .hint {
      display: none;
    }
    .round {
      width: 40px;
      height: 40px;
    }
  }
</style>
