/* Vectorizer — complete UI redesign, Simple Studio + Advanced Studio, persistence, custom sliders, pro fullscreen viewer with drag + zoom */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    landing: $("landing"),
    upload: $("upload"),
    result: $("result"),
    advanced: $("advanced"),
    manual: $("manual"),
    debug: $("debug"),
    startBtn: $("startBtn"),
    landingAdvancedBtn: $("landingAdvancedBtn"),
    manualBtn: $("navManual"),
    debugBtn: $("navDebug"),
    navSimple: $("navSimple"),
    navAdvanced: $("navAdvanced"),
    navManual: $("navManual"),
    navDebug: $("navDebug"),
    backBtn: $("backBtn"),
    manualBackBtn: $("manualBackBtn"),
    debugBackBtn: $("debugBackBtn"),
    dropzone: $("dropzone"),
    convertBtn: $("convertBtn"),
    modelToggle: $("modelToggle"),
    fileInput: $("fileInput"),
    resultOriginal: $("resultOriginal"),
    resultSvg: $("resultSvg"),
    resultMeta: $("resultMeta"),
    srcMeta: $("srcMeta"),
    srcPreviewBox: $("srcPreviewBox"),
    resultSvgBox: $("resultSvgBox"),
    downloadBtn: $("downloadBtn"),
    viewBtn: $("viewBtn"),
    newBtn: $("newBtn"),
    openAdvancedBtn: $("openAdvancedBtn"),
    zoomOutBtn: $("zoomOutBtn"),
    zoomInBtn: $("zoomInBtn"),
    zoomFitBtn: $("zoomFitBtn"),
    zoomResetBtn: $("zoomResetBtn"),
    zoomLevel: $("zoomLevel"),
    srcFitBtn: $("srcFitBtn"),
    compareBtn: $("compareBtn"),
    bgToggleBtn: $("bgToggleBtn"),
    // advanced
    advBackSimpleBtn: $("advBackSimpleBtn"),
    advNewBtn: $("advNewBtn"),
    advResultOriginal: $("advResultOriginal"),
    advResultSvg: $("advResultSvg"),
    advResultMeta: $("advResultMeta"),
    advSrcPreviewBox: $("advSrcPreviewBox"),
    advResultSvgBox: $("advResultSvgBox"),
    advDownloadBtn: $("advDownloadBtn"),
    advViewBtn: $("advViewBtn"),
    advCompareBtn: $("advCompareBtn"),
    advZoomOutBtn: $("advZoomOutBtn"),
    advZoomInBtn: $("advZoomInBtn"),
    advZoomFitBtn: $("advZoomFitBtn"),
    advZoomResetBtn: $("advZoomResetBtn"),
    advZoomLevel: $("advZoomLevel"),
    advSrcFitBtn: $("advSrcFitBtn"),
    advProfile: $("advProfile"),
    advCp: $("advCp"),
    advLd: $("advLd"),
    advFs: $("advFs"),
    advMi: $("advMi"),
    advCpVal: $("advCpVal"),
    advLdVal: $("advLdVal"),
    advFsVal: $("advFsVal"),
    advMiVal: $("advMiVal"),
    advReconvertBtn: $("advReconvertBtn"),
    inspectColors: $("inspectColors"),
    inspectPaths: $("inspectPaths"),
    inspectKb: $("inspectKb"),
    inspectTime: $("inspectTime"),
    inspectTrans: $("inspectTrans"),
    sidebarDebugBtn: $("sidebarDebugBtn"),
    sidebarManualBtn: $("sidebarManualBtn"),
    // overlays
    dropOverlay: $("dropOverlay"),
    viewOverlay: $("viewOverlay"),
    viewStage: $("viewStage"),
    viewStageInner: $("viewStageInner"),
    viewTitle: $("viewTitle"),
    viewDownloadBtn: $("viewDownloadBtn"),
    viewCloseBtn: $("viewCloseBtn"),
    viewCloseBtn2: $("viewCloseBtn2"),
    viewZoomOutBtn: $("viewZoomOutBtn"),
    viewZoomInBtn: $("viewZoomInBtn"),
    viewZoomLevel: $("viewZoomLevel"),
    viewFitBtn: $("viewFitBtn"),
    viewActualBtn: $("viewActualBtn"),
    viewDragBtn: $("viewDragBtn"),
    viewHint: $("viewHint"),
    compareOverlay: $("compareOverlay"),
    compareStage: $("compareStage"),
    compareSrc: $("compareSrc"),
    compareVec: $("compareVec"),
    compareSlider: $("compareSlider"),
    compareCloseBtn: $("compareCloseBtn"),
    toast: $("toast"),
    brandHome: $("brandHome"),
    // manual
    manualStatus: $("manualStatus"),
    manualDropzone1: $("manualDropzone1"),
    manualFileInput1: $("manualFileInput1"),
    manualList1: $("manualList1"),
    manualDropzone2: $("manualDropzone2"),
    manualFileInput2: $("manualFileInput2"),
    manualList2: $("manualList2"),
    manualTrainBtn: $("manualTrainBtn"),
    manualRefreshBtn: $("manualRefreshBtn"),
    manualLog: $("manualLog"),
    // debug
    debugLimit: $("debugLimit"),
    debugVetBtn: $("debugVetBtn"),
    debugStatus: $("debugStatus"),
    debugResults: $("debugResults"),
  };

  const ACCEPTED = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
  const MAX_BYTES = 20 * 1024 * 1024;
  const MODEL_F = 1047;
  const DB_NAME = "vectorizer_project";
  const DB_VERSION = 1;
  const STORE = "project";

  const state = {
    svgText: null,
    svgUrl: null,
    fileName: "vector.svg",
    busy: false,
    viewOpen: false,
    compareOpen: false,
    zoom: 100,
    advZoom: 100,
    bgChecker: true,
    sourceFile: null,
    sourceUrl: null,
    meta: null,
    profile: "flat",
    color_precision: 6,
    layer_difference: 16,
    filter_speckle: 4,
    max_iterations: 18,
    // fullscreen viewer
    viewZoom: 100,
    viewPanX: 0,
    viewPanY: 0,
    viewIsDragging: false,
    viewDragStartX: 0,
    viewDragStartY: 0,
    viewPanStartX: 0,
    viewPanStartY: 0,
    viewDragMode: false,
  };

  let toastTimer = null;
  window.__vz = { view: "landing", model: { status: "idle", lastParams: null, lastError: null } };

  /* ---------- IndexedDB persistence ---------- */
  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function idbSet(key, value) {
    try {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    } catch {}
  }
  async function idbGet(key) {
    try {
      const db = await openDB();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    } catch { return null; }
  }
  async function saveProject() {
    try {
      const data = {
        fileName: state.fileName,
        svgText: state.svgText,
        meta: state.meta,
        profile: state.profile,
        color_precision: state.color_precision,
        layer_difference: state.layer_difference,
        filter_speckle: state.filter_speckle,
        max_iterations: state.max_iterations,
        zoom: state.zoom,
        advZoom: state.advZoom,
        view: window.__vz.view,
        timestamp: Date.now(),
      };
      await idbSet("project", data);
      if (state.sourceFile) await idbSet("source_blob", state.sourceFile);
      localStorage.setItem("vz_view", window.__vz.view);
    } catch {}
  }
  async function loadProject() {
    try {
      const proj = await idbGet("project");
      const blob = await idbGet("source_blob");
      if (!proj || !proj.svgText) return false;
      state.fileName = proj.fileName || "vector.svg";
      state.svgText = proj.svgText;
      state.meta = proj.meta || null;
      state.profile = proj.profile || "flat";
      state.color_precision = proj.color_precision || 6;
      state.layer_difference = proj.layer_difference || 16;
      state.filter_speckle = proj.filter_speckle || 4;
      state.max_iterations = proj.max_iterations || 18;
      state.zoom = proj.zoom || 100;
      state.advZoom = proj.advZoom || 100;
      if (blob) {
        state.sourceFile = blob;
        if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
        state.sourceUrl = URL.createObjectURL(blob);
        if (els.resultOriginal) els.resultOriginal.src = state.sourceUrl;
        if (els.advResultOriginal) els.advResultOriginal.src = state.sourceUrl;
      }
      if (state.svgText) {
        if (state.svgUrl) URL.revokeObjectURL(state.svgUrl);
        const b = new Blob([state.svgText], { type: "image/svg+xml" });
        state.svgUrl = URL.createObjectURL(b);
        if (els.resultSvg) els.resultSvg.src = state.svgUrl;
        if (els.advResultSvg) els.advResultSvg.src = state.svgUrl;
        if (els.resultMeta && state.meta) {
          const m = state.meta;
          const parts = [`${m.colors} colors`, `${m.paths} paths`, `${m.kb} KB`, `${m.seconds}s`];
          if (m.transparent_bg) parts.push("transparent background");
          els.resultMeta.textContent = parts.join("  ·  ");
          if (els.advResultMeta) els.advResultMeta.textContent = parts.join("  ·  ");
        }
        if (state.meta) {
          if (els.inspectColors) els.inspectColors.textContent = state.meta.colors;
          if (els.inspectPaths) els.inspectPaths.textContent = state.meta.paths;
          if (els.inspectKb) els.inspectKb.textContent = state.meta.kb + " KB";
          if (els.inspectTime) els.inspectTime.textContent = state.meta.seconds + "s";
          if (els.inspectTrans) els.inspectTrans.textContent = state.meta.transparent_bg ? "yes" : "no";
        }
        const savedView = proj.view || localStorage.getItem("vz_view") || "result";
        if (savedView === "advanced") setView("advanced");
        else setView("result");
        applyZoom();
        initSlidersFill();
        toast("Project restored from previous session", "ok");
        return true;
      }
    } catch {}
    return false;
  }

  /* ---------- helpers ---------- */
  function toast(msg, kind) {
    if (!els.toast) return;
    els.toast.textContent = msg;
    els.toast.className = `toast ${kind || ""}`;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 4200);
  }
  function validFile(file) {
    if (!file) return "No file found";
    const name = (file.name || "image").toLowerCase();
    if (!ACCEPTED.some((e) => name.endsWith(e))) return `Unsupported file type ${name} Use PNG JPG WebP GIF BMP`;
    if (file.size > MAX_BYTES) return "File too large max 20 MB";
    return null;
  }
  function setLoading(on) {
    state.busy = on;
    if (els.convertBtn) els.convertBtn.disabled = on;
    if (els.dropzone) els.dropzone.style.pointerEvents = on ? "none" : "";
    const label = els.convertBtn?.querySelector(".btn-label");
    if (label) label.textContent = on ? "Converting" : "Convert";
    els.convertBtn?.classList.toggle("loading", on);
  }
  function setView(name) {
    if (els.landing) els.landing.hidden = name !== "landing";
    if (els.upload) els.upload.hidden = name !== "upload";
    if (els.result) els.result.hidden = name !== "result";
    if (els.advanced) els.advanced.hidden = name !== "advanced";
    if (els.manual) els.manual.hidden = name !== "manual";
    if (els.debug) els.debug.hidden = name !== "debug";
    window.__vz.view = name;
    localStorage.setItem("vz_view", name);
    window.scrollTo({ top: 0 });
    if (name === "manual") refreshManualStatus();
    if (name === "debug" && els.debugStatus) els.debugStatus.textContent = "Click Vet to run strict grading";
    saveProject();
  }
  function showResult(meta, modelUsed) {
    state.meta = meta;
    setView("result");
    const parts = [`${meta.colors} colors`, `${meta.paths} paths`, `${meta.kb} KB`];
    if (meta.transparent_bg) parts.push("transparent background");
    if (modelUsed) parts.push("smart model");
    parts.push(`${meta.seconds}s`);
    if (els.resultMeta) els.resultMeta.textContent = parts.join("  ·  ");
    if (els.advResultMeta) els.advResultMeta.textContent = parts.join("  ·  ");
    if (els.srcMeta) els.srcMeta.textContent = `${meta.width} x ${meta.height}`;
    if (els.inspectColors) els.inspectColors.textContent = meta.colors;
    if (els.inspectPaths) els.inspectPaths.textContent = meta.paths;
    if (els.inspectKb) els.inspectKb.textContent = meta.kb + " KB";
    if (els.inspectTime) els.inspectTime.textContent = meta.seconds + "s";
    if (els.inspectTrans) els.inspectTrans.textContent = meta.transparent_bg ? "yes" : "no";
    applyZoom();
    saveProject();
  }
  function makeBlobUrl() {
    if (state.svgUrl) URL.revokeObjectURL(state.svgUrl);
    const blob = new Blob([state.svgText], { type: "image/svg+xml" });
    state.svgUrl = URL.createObjectURL(blob);
    if (els.resultSvg) els.resultSvg.src = state.svgUrl;
    if (els.advResultSvg) els.advResultSvg.src = state.svgUrl;
    return state.svgUrl;
  }
  function download() {
    if (!state.svgText) return;
    const a = document.createElement("a");
    a.href = makeBlobUrl();
    a.download = state.fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  function applyZoom() {
    const z = state.zoom / 100;
    if (els.resultSvg) els.resultSvg.style.transform = `scale(${z})`;
    if (els.resultOriginal) els.resultOriginal.style.transform = `scale(${z})`;
    if (els.zoomLevel) els.zoomLevel.textContent = state.zoom + "%";
    const az = state.advZoom / 100;
    if (els.advResultSvg) els.advResultSvg.style.transform = `scale(${az})`;
    if (els.advResultOriginal) els.advResultOriginal.style.transform = `scale(${az})`;
    if (els.advZoomLevel) els.advZoomLevel.textContent = state.advZoom + "%";
    saveProject();
  }
  function setZoom(delta, isAdv) {
    if (isAdv) state.advZoom = Math.max(25, Math.min(400, state.advZoom + delta));
    else state.zoom = Math.max(25, Math.min(400, state.zoom + delta));
    applyZoom();
  }
  function fitZoom(isAdv) {
    if (isAdv) state.advZoom = 100;
    else state.zoom = 100;
    applyZoom();
  }

  /* ---------- custom slider fill ---------- */
  function updateSliderFill(input) {
    if (!input || !input.classList.contains("slider")) return;
    const min = parseFloat(input.min) || 0;
    const max = parseFloat(input.max) || 100;
    const val = parseFloat(input.value) || 0;
    const pct = ((val - min) / (max - min)) * 100;
    input.style.setProperty("--fill", pct + "%");
  }
  function initSlidersFill() {
    document.querySelectorAll("input.slider").forEach(updateSliderFill);
  }

  /* ---------- smart model (ONNX in browser) ---------- */
  let ortPromise = null;
  function loadOrt() {
    if (window.ort) return Promise.resolve(window.ort);
    if (!ortPromise) {
      ortPromise = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "/static/model/ort.js";
        s.onload = () => {
          try {
            window.ort.env.wasm.wasmPaths = "/static/model/";
            window.ort.env.wasm.numThreads = 1;
            resolve(window.ort);
          } catch (e) { reject(e); }
        };
        s.onerror = () => reject(new Error("model runtime failed to load"));
        document.head.appendChild(s);
      });
      ortPromise.catch(() => { ortPromise = null; });
    }
    return ortPromise;
  }
  let sessionPromise = null;
  function getSession(ort) {
    if (!sessionPromise) {
      sessionPromise = ort.InferenceSession.create("/static/model/params.onnx")
        .catch((e) => { sessionPromise = null; throw e; });
    }
    return sessionPromise;
  }
  async function computeFeatures(file) {
    const bmp = await createImageBitmap(file);
    const c = document.createElement("canvas");
    c.width = 16; c.height = 16;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, 16, 16);
    const d = ctx.getImageData(0, 0, 16, 16).data;
    bmp.close && bmp.close();
    const out = new Float32Array(MODEL_F);
    const N = 16;
    for (let i = 0; i < N * N; i++) {
      out[i * 4] = d[i * 4] / 255;
      out[i * 4 + 1] = d[i * 4 + 1] / 255;
      out[i * 4 + 2] = d[i * 4 + 2] / 255;
      out[i * 4 + 3] = d[i * 4 + 3] / 255;
    }
    const sr = new Array(N * N), sg = new Array(N * N), sb = new Array(N * N);
    for (let i = 0; i < N * N; i++) {
      sr[i] = d[i * 4] / 255; sg[i] = d[i * 4 + 1] / 255; sb[i] = d[i * 4 + 2] / 255;
    }
    let cr = 0, cg = 0, cb = 0, n = 0, content = 0;
    for (let i = 0; i < N * N; i++) {
      if (d[i * 4 + 3] > 127.5) { cr += sr[i]; cg += sg[i]; cb += sb[i]; n++; content++; }
    }
    const base = 1024;
    out[base + 0] = n ? cr / n : 0;
    out[base + 1] = n ? cg / n : 0;
    out[base + 2] = n ? cb / n : 0;
    const allMeanR = sr.reduce((a, b) => a + b, 0) / (N * N);
    const allMeanG = sg.reduce((a, b) => a + b, 0) / (N * N);
    const allMeanB = sb.reduce((a, b) => a + b, 0) / (N * N);
    const allVarR = sr.reduce((a, b) => a + (b - allMeanR) ** 2, 0) / (N * N);
    const allVarG = sg.reduce((a, b) => a + (b - allMeanG) ** 2, 0) / (N * N);
    const allVarB = sb.reduce((a, b) => a + (b - allMeanB) ** 2, 0) / (N * N);
    out[base + 3] = Math.sqrt(allVarR);
    out[base + 4] = Math.sqrt(allVarG);
    out[base + 5] = Math.sqrt(allVarB);
    out[base + 6] = content / (N * N);
    const hueBin = new Array(12).fill(0);
    let satSum = 0;
    for (let i = 0; i < N * N; i++) {
      if (d[i * 4 + 3] <= 127.5) continue;
      const r = sr[i], g = sg[i], b = sb[i];
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), dd = mx - mn;
      if (dd > 0) {
        let h = 0;
        if (mx === r) h = ((g - b) / dd) % 6;
        else if (mx === g) h = (b - r) / dd + 2;
        else h = (r - g) / dd + 4;
        h = (h / 6) % 1;
        let bin = Math.floor(h * 12); if (bin >= 12) bin = 11;
        hueBin[bin]++;
      }
      const mx2 = Math.max(r, g, b), mn2 = Math.min(r, g, b), dd2 = mx2 - mn2;
      satSum += mx2 > 0 ? dd2 / Math.max(mx2, 1e-9) : 0;
    }
    for (let k = 0; k < 12; k++) out[base + 7 + k] = n && hueBin[k] / n >= 0.02 ? 1 : 0;
    out[base + 19] = n ? satSum / n : 0;
    const a = new Array(N * N);
    for (let i = 0; i < N * N; i++) a[i] = d[i * 4 + 3] / 255;
    let edge = 0;
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const i = y * N + x;
      const xr = (x + 1) % N, dr = (y + 1) % N;
      edge += Math.abs(a[y * N + xr] - a[i]) + Math.abs(a[dr * N + x] - a[i]);
    }
    out[base + 20] = Math.min(1, edge / (N * N));
    const keys = new Set();
    for (let i = 0; i < N * N; i++) {
      const r4 = Math.floor(sr[i] * 15) & 15;
      const g4 = Math.floor(sg[i] * 15) & 15;
      const b4 = Math.floor(sb[i] * 15) & 15;
      const a4 = Math.floor(d[i * 4 + 3] / 255) & 15;
      keys.add(((r4 << 12) | (g4 << 8) | (b4 << 4) | a4));
    }
    out[base + 21] = Math.min(1, keys.size / 256);
    const luma = new Array(N * N);
    for (let i = 0; i < N * N; i++) luma[i] = (sr[i] + sg[i] + sb[i]) / 3;
    let gSum = 0, gN = 0;
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const i = y * N + x;
      if (d[i * 4 + 3] <= 127.5) continue;
      const gx = Math.abs(luma[y * N + ((x + 1) % N)] - luma[i]);
      const gy = Math.abs(luma[((y + 1) % N) * N + x] - luma[i]);
      gSum += Math.max(gx, gy); gN++;
    }
    out[base + 22] = gN ? Math.min(1, gSum / gN / 1.5) : 0;
    return out;
  }
  function paramsFromY(y) {
    const c = (v) => Math.max(0, Math.min(1, v));
    const y0 = c(y[0]), y1 = c(y[1]), y2 = c(y[2]), y3 = c(y[3]), y4 = c(y[4]);
    return {
      profile: y0 > 0.5 ? "flat" : "photo",
      color_precision: Math.max(1, Math.min(8, Math.round(1 + y1 * 7))),
      layer_difference: Math.max(6, Math.min(40, Math.round(6 + y2 * 34))),
      filter_speckle: Math.max(1, Math.min(8, 2 ** Math.round(y3 * 3))),
      max_iterations: Math.max(8, Math.min(48, Math.round(8 + y4 * 40))),
    };
  }
  async function modelParamsFor(file) {
    const ort = await loadOrt();
    const session = await getSession(ort);
    const feat = await computeFeatures(file);
    const out = await session.run({ x: new ort.Tensor("float32", feat, [1, MODEL_F]) });
    const y = Array.from(out[session.outputNames[0]].data);
    return paramsFromY(y);
  }
  function withTimeout(promise, ms) {
    return Promise.race([
      promise,
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms)),
    ]);
  }

  /* ---------- convert flow ---------- */
  async function convert(file) {
    if (state.busy) return;
    const err = validFile(file);
    if (err) { toast(err, "error"); return; }
    setLoading(true);
    let modelUsed = false;
    try {
      state.sourceFile = file;
      if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
      state.sourceUrl = URL.createObjectURL(file);
      if (els.resultOriginal) els.resultOriginal.src = state.sourceUrl;
      if (els.advResultOriginal) els.advResultOriginal.src = state.sourceUrl;
      if (els.srcMeta) els.srcMeta.textContent = `${file.name} — ${(file.size/1024).toFixed(1)} KB`;

      const fd = new FormData();
      fd.append("file", file);
      if (els.modelToggle.checked) {
        try {
          const p = await withTimeout(modelParamsFor(file), 8000);
          fd.append("use_model", "1");
          fd.append("profile", p.profile);
          fd.append("color_precision", String(p.color_precision));
          fd.append("layer_difference", String(p.layer_difference));
          fd.append("filter_speckle", String(p.filter_speckle));
          fd.append("max_iterations", String(p.max_iterations));
          window.__vz.model.status = "ready";
          window.__vz.model.lastParams = p;
          state.profile = p.profile;
          state.color_precision = p.color_precision;
          state.layer_difference = p.layer_difference;
          state.filter_speckle = p.filter_speckle;
          state.max_iterations = p.max_iterations;
          if (els.advProfile) els.advProfile.value = p.profile;
          if (els.advCp) els.advCp.value = p.color_precision;
          if (els.advLd) els.advLd.value = p.layer_difference;
          if (els.advFs) els.advFs.value = Math.log2(p.filter_speckle);
          if (els.advMi) els.advMi.value = p.max_iterations;
          if (els.advCpVal) els.advCpVal.textContent = p.color_precision;
          if (els.advLdVal) els.advLdVal.textContent = p.layer_difference;
          if (els.advFsVal) els.advFsVal.textContent = p.filter_speckle;
          if (els.advMiVal) els.advMiVal.textContent = p.max_iterations;
          initSlidersFill();
          modelUsed = true;
        } catch (me) {
          window.__vz.model.status = "error";
          window.__vz.model.lastError = String(me && me.message || me);
          toast("Smart model unavailable using standard settings", "error");
        }
      }
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      state.svgText = data.svg;
      state.fileName = (file.name || "image").replace(/\.[^.]+$/, "") + ".svg";
      if (els.resultSvg) els.resultSvg.src = makeBlobUrl();
      if (els.advResultSvg) els.advResultSvg.src = makeBlobUrl();
      showResult(data.meta, modelUsed);
      toast("Vector ready", "ok");
    } catch (e) {
      toast(e.message || "Conversion failed Try another image", "error");
    } finally {
      setLoading(false);
    }
  }

  async function reconvertWithAdvanced() {
    if (!state.sourceFile) { toast("No source image to reconvert", "error"); return; }
    if (state.busy) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", state.sourceFile);
      fd.append("use_model", "1");
      fd.append("profile", els.advProfile?.value || state.profile);
      fd.append("color_precision", String(els.advCp?.value || state.color_precision));
      fd.append("layer_difference", String(els.advLd?.value || state.layer_difference));
      const fsExp = parseInt(els.advFs?.value || "2", 10);
      const fsVal = Math.pow(2, fsExp);
      fd.append("filter_speckle", String(fsVal));
      fd.append("max_iterations", String(els.advMi?.value || state.max_iterations));
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      state.svgText = data.svg;
      state.fileName = (state.sourceFile.name || "image").replace(/\.[^.]+$/, "") + ".svg";
      makeBlobUrl();
      showResult(data.meta, true);
      toast("Reconverted with advanced settings", "ok");
    } catch (e) {
      toast(e.message || "Reconvert failed", "error");
    } finally {
      setLoading(false);
    }
  }

  /* ---------- manual training & debug vet ---------- */
  async function refreshManualStatus() {
    if (!els.manualStatus) return;
    try {
      const res = await fetch("/api/manual/status");
      const data = await res.json();
      els.manualStatus.innerHTML = `
        <strong>Collected:</strong> ${data.total_images} images Section 1 · ${data.total_results} results Section 2 · ONNX ${(data.onnx_size/1024/1024).toFixed(2)} MB · Model ${data.model_exists ? "exists" : "missing"}<br>
        <small>${data.note || ""}</small><br>
        <small>Images sample: ${(data.images_sample||[]).slice(0,5).join(", ")}</small><br>
        <small>Results sample: ${(data.results_sample||[]).slice(0,5).join(", ")}</small>
      `;
      if (els.manualLog && data.last_training) {
        els.manualLog.innerHTML = "<h4>Last training continuous</h4><pre>" + JSON.stringify(data.last_training, null, 2) + "</pre>";
      }
    } catch (e) {
      els.manualStatus.textContent = "Failed to load status " + e.message;
    }
  }
  async function uploadManual(files, endpoint, listEl) {
    if (!files || files.length === 0) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    try {
      toast(`Uploading ${files.length} files`, "ok");
      const res = await fetch(endpoint, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.status);
      toast(`Saved ${data.saved} files total images ${data.total_images} results ${data.total_results}`, "ok");
      if (listEl) listEl.innerHTML = data.files.map(n => `<div>${n}</div>`).join("");
      refreshManualStatus();
    } catch (e) {
      toast("Upload failed " + e.message, "error");
    }
  }
  async function triggerManualTrain() {
    try {
      toast("Starting training in background", "ok");
      const res = await fetch("/api/manual/train", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.status);
      toast(data.msg, "ok");
      if (els.manualLog) els.manualLog.innerHTML += "<p>Training started check status in 30s ONNX will update model improves</p>";
    } catch (e) {
      toast("Train failed " + e.message, "error");
    }
  }
  async function vetModelStrict() {
    if (!els.debugStatus || !els.debugResults) return;
    const limit = parseInt(els.debugLimit?.value || "20", 10) || 20;
    els.debugStatus.textContent = `Vetting model very strictly limit ${limit} scanning result and grading strictly`;
    els.debugResults.innerHTML = "<p>Running strict scan</p>";
    try {
      const res = await fetch(`/api/debug/vet?limit=${limit}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      els.debugStatus.innerHTML = `
        <strong>Strict Vet Result:</strong> ${data.pass} PASS ${data.fail} FAIL ${data.total} total pass rate ${(data.pass_rate*100).toFixed(1)}% avg score ${data.avg_score}<br>
        <small>Thresholds ${data.thresholds.clean} | ${data.thresholds.blurred}</small><br>
        <small>Model ${data.model.arch} ONNX ${(data.model.onnx_size/1024/1024).toFixed(2)} MB</small>
      `;
      const rows = data.results.map(r => {
        if (r.error) return `<div class="debug-row fail">${r.name} ERROR ${r.error}</div>`;
        const cls = r.grade === "PASS" ? "pass" : "fail";
        return `<div class="debug-row ${cls}">
          <strong>${r.name}</strong> ${r.grade} score ${r.score} cov ${r.coverage} prec ${r.precision} color err ${r.color_err} paths ${r.paths} ${r.is_clean ? "clean" : "blurred"}<br>
          <small>strict score ok ${r.strict.score_ok} coverage ok ${r.strict.coverage_ok} precision ok ${r.strict.precision_ok} color ok ${r.strict.color_ok} paths ok ${r.strict.paths_ok} params ${JSON.stringify(r.params)}</small>
        </div>`;
      }).join("");
      els.debugResults.innerHTML = rows;
      toast(`Vet done ${data.pass} PASS ${data.fail} FAIL`, data.fail > 0 ? "error" : "ok");
    } catch (e) {
      els.debugStatus.textContent = "Vet failed " + e.message;
      toast("Vet failed " + e.message, "error");
    }
  }

  /* ---------- fullscreen view — pro viewer with zoom, drag, no accidental close ---------- */
  function applyViewTransform() {
    if (!els.viewStageInner) return;
    const scale = state.viewZoom / 100;
    els.viewStageInner.style.transform = `translate(${state.viewPanX}px, ${state.viewPanY}px) scale(${scale})`;
    if (els.viewZoomLevel) els.viewZoomLevel.textContent = Math.round(state.viewZoom) + "%";
    // update cursor hint
    if (els.viewStage) {
      if (state.viewZoom > 100 || state.viewDragMode) {
        els.viewStage.classList.add("drag-mode");
      } else {
        els.viewStage.classList.remove("drag-mode");
      }
    }
  }
  function setViewZoom(delta, anchor) {
    const oldZoom = state.viewZoom;
    let newZoom = oldZoom + delta;
    newZoom = Math.max(25, Math.min(800, newZoom));
    // if anchor provided, adjust pan to keep anchor stable
    if (anchor && els.viewStage) {
      const rect = els.viewStage.getBoundingClientRect();
      const cx = rect.width / 2, cy = rect.height / 2;
      const ax = anchor.x - rect.left - cx;
      const ay = anchor.y - rect.top - cy;
      const scaleRatio = newZoom / oldZoom;
      // pan adjustment: keep point under cursor stable
      state.viewPanX = anchor.panX + (ax - ax * scaleRatio) + (state.viewPanX - anchor.panX) * scaleRatio;
      state.viewPanY = anchor.panY + (ay - ay * scaleRatio) + (state.viewPanY - anchor.panY) * scaleRatio;
    }
    state.viewZoom = newZoom;
    applyViewTransform();
  }
  function setViewZoomAbsolute(zoom, center) {
    state.viewZoom = Math.max(25, Math.min(800, zoom));
    if (center) {
      state.viewPanX = 0;
      state.viewPanY = 0;
    }
    applyViewTransform();
  }
  function fitView() {
    state.viewZoom = 100;
    state.viewPanX = 0;
    state.viewPanY = 0;
    applyViewTransform();
  }

  function openView() {
    if (!state.svgText) return;
    // ensure inner container exists
    if (!els.viewStageInner) {
      els.viewStageInner = document.createElement("div");
      els.viewStageInner.id = "viewStageInner";
      els.viewStageInner.className = "view-stage-inner";
      els.viewStage.appendChild(els.viewStageInner);
    }
    const img = document.createElement("img");
    img.src = makeBlobUrl();
    img.alt = "Vectorized SVG fullscreen";
    img.draggable = false;
    while (els.viewStageInner.firstChild) els.viewStageInner.removeChild(els.viewStageInner.firstChild);
    els.viewStageInner.appendChild(img);
    if (els.viewTitle) els.viewTitle.textContent = state.fileName;
    if (els.viewOverlay) els.viewOverlay.hidden = false;
    state.viewOpen = true;
    state.viewZoom = 100;
    state.viewPanX = 0;
    state.viewPanY = 0;
    state.viewDragMode = false;
    if (els.viewDragBtn) els.viewDragBtn.classList.remove("active");
    applyViewTransform();
    document.body.style.overflow = "hidden";
  }
  function closeView() {
    if (els.viewOverlay) els.viewOverlay.hidden = true;
    state.viewOpen = false;
    state.viewIsDragging = false;
    if (els.viewStage) {
      els.viewStage.classList.remove("dragging");
    }
    document.body.style.overflow = "";
  }
  function openCompare() {
    if (!state.sourceUrl || !state.svgUrl) { toast("Need source and vector to compare", "error"); return; }
    if (els.compareSrc) els.compareSrc.src = state.sourceUrl;
    if (els.compareVec) els.compareVec.src = state.svgUrl;
    if (els.compareOverlay) els.compareOverlay.hidden = false;
    state.compareOpen = true;
    updateCompare(50);
  }
  function closeCompare() {
    if (els.compareOverlay) els.compareOverlay.hidden = true;
    state.compareOpen = false;
  }
  function updateCompare(val) {
    const v = Math.max(0, Math.min(100, val));
    const vec = document.querySelector(".compare-vector");
    if (vec) vec.style.clipPath = `inset(0 0 0 ${v}%)`;
  }

  /* ---------- wiring ---------- */
  if (els.startBtn) els.startBtn.addEventListener("click", () => setView("upload"));
  if (els.landingAdvancedBtn) els.landingAdvancedBtn.addEventListener("click", () => {
    if (state.svgText) setView("advanced");
    else setView("upload");
  });
  if (els.manualBtn) els.manualBtn.addEventListener("click", () => setView("manual"));
  if (els.debugBtn) els.debugBtn.addEventListener("click", () => setView("debug"));
  if (els.navSimple) els.navSimple.addEventListener("click", () => {
    if (state.svgText) setView("result");
    else setView("landing");
  });
  if (els.navAdvanced) els.navAdvanced.addEventListener("click", () => {
    if (state.svgText) setView("advanced");
    else setView("upload");
  });
  if (els.navManual) els.navManual.addEventListener("click", () => setView("manual"));
  if (els.navDebug) els.navDebug.addEventListener("click", () => setView("debug"));
  if (els.backBtn) els.backBtn.addEventListener("click", () => setView("landing"));
  if (els.manualBackBtn) els.manualBackBtn.addEventListener("click", () => setView("landing"));
  if (els.debugBackBtn) els.debugBackBtn.addEventListener("click", () => setView("landing"));
  if (els.newBtn) els.newBtn.addEventListener("click", () => setView("upload"));
  if (els.advNewBtn) els.advNewBtn.addEventListener("click", () => setView("upload"));
  if (els.openAdvancedBtn) els.openAdvancedBtn.addEventListener("click", () => setView("advanced"));
  if (els.advBackSimpleBtn) els.advBackSimpleBtn.addEventListener("click", () => setView("result"));
  if (els.brandHome) els.brandHome.addEventListener("click", (e) => {
    e.preventDefault();
    setView("landing");
  });

  const openPicker = () => { if (els.fileInput) els.fileInput.click(); };
  if (els.convertBtn) els.convertBtn.addEventListener("click", openPicker);
  if (els.dropzone) {
    els.dropzone.addEventListener("click", openPicker);
    els.dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPicker(); }
    });
  }
  if (els.fileInput) {
    els.fileInput.addEventListener("change", () => {
      const f = els.fileInput.files && els.fileInput.files[0];
      if (f) convert(f);
      els.fileInput.value = "";
    });
  }
  if (els.downloadBtn) els.downloadBtn.addEventListener("click", download);
  if (els.advDownloadBtn) els.advDownloadBtn.addEventListener("click", download);

  // zoom controls — simple studio
  if (els.zoomOutBtn) els.zoomOutBtn.addEventListener("click", () => setZoom(-25, false));
  if (els.zoomInBtn) els.zoomInBtn.addEventListener("click", () => setZoom(25, false));
  if (els.zoomFitBtn) els.zoomFitBtn.addEventListener("click", () => fitZoom(false));
  if (els.zoomResetBtn) els.zoomResetBtn.addEventListener("click", () => fitZoom(false));
  if (els.srcFitBtn) els.srcFitBtn.addEventListener("click", () => fitZoom(false));
  if (els.advZoomOutBtn) els.advZoomOutBtn.addEventListener("click", () => setZoom(-25, true));
  if (els.advZoomInBtn) els.advZoomInBtn.addEventListener("click", () => setZoom(25, true));
  if (els.advZoomFitBtn) els.advZoomFitBtn.addEventListener("click", () => fitZoom(true));
  if (els.advZoomResetBtn) els.advZoomResetBtn.addEventListener("click", () => fitZoom(true));
  if (els.advSrcFitBtn) els.advSrcFitBtn.addEventListener("click", () => fitZoom(true));

  // inspection — clicking result opens fullscreen view, NOT upload
  if (els.resultSvgBox) {
    els.resultSvgBox.addEventListener("click", (e) => {
      e.stopPropagation();
      openView();
    });
  }
  if (els.advResultSvgBox) {
    els.advResultSvgBox.addEventListener("click", (e) => {
      e.stopPropagation();
      openView();
    });
  }
  if (els.viewBtn) els.viewBtn.addEventListener("click", openView);
  if (els.advViewBtn) els.advViewBtn.addEventListener("click", openView);

  // fullscreen viewer controls — pro tools
  if (els.viewCloseBtn) els.viewCloseBtn.addEventListener("click", closeView);
  if (els.viewCloseBtn2) els.viewCloseBtn2.addEventListener("click", closeView);
  if (els.viewDownloadBtn) els.viewDownloadBtn.addEventListener("click", download);
  if (els.viewZoomOutBtn) els.viewZoomOutBtn.addEventListener("click", () => setViewZoom(-25));
  if (els.viewZoomInBtn) els.viewZoomInBtn.addEventListener("click", () => setViewZoom(25));
  if (els.viewFitBtn) els.viewFitBtn.addEventListener("click", fitView);
  if (els.viewActualBtn) els.viewActualBtn.addEventListener("click", () => setViewZoomAbsolute(100, true));
  if (els.viewDragBtn) {
    els.viewDragBtn.addEventListener("click", () => {
      state.viewDragMode = !state.viewDragMode;
      els.viewDragBtn.classList.toggle("active", state.viewDragMode);
      if (els.viewStage) els.viewStage.classList.toggle("drag-mode", state.viewDragMode || state.viewZoom > 100);
    });
  }

  // view stage pan & zoom interactions — fix: clicking canvas does NOT force exit
  if (els.viewStage) {
    // wheel zoom
    els.viewStage.addEventListener("wheel", (e) => {
      if (!state.viewOpen) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -25 : 25;
      setViewZoom(delta, { x: e.clientX, y: e.clientY, panX: state.viewPanX, panY: state.viewPanY });
    }, { passive: false });

    // mouse drag pan
    els.viewStage.addEventListener("mousedown", (e) => {
      if (!state.viewOpen) return;
      // only left button, and only if zoomed or drag mode active
      if (e.button !== 0) return;
      if (state.viewZoom <= 100 && !state.viewDragMode) return;
      // prevent closing, start drag
      e.preventDefault();
      state.viewIsDragging = true;
      state.viewDragStartX = e.clientX;
      state.viewDragStartY = e.clientY;
      state.viewPanStartX = state.viewPanX;
      state.viewPanStartY = state.viewPanY;
      els.viewStage.classList.add("dragging");
      if (els.viewStageInner) els.viewStageInner.classList.add("dragging");
    });
    window.addEventListener("mousemove", (e) => {
      if (!state.viewIsDragging) return;
      const dx = e.clientX - state.viewDragStartX;
      const dy = e.clientY - state.viewDragStartY;
      state.viewPanX = state.viewPanStartX + dx;
      state.viewPanY = state.viewPanStartY + dy;
      applyViewTransform();
    });
    window.addEventListener("mouseup", () => {
      if (!state.viewIsDragging) return;
      state.viewIsDragging = false;
      if (els.viewStage) els.viewStage.classList.remove("dragging");
      if (els.viewStageInner) els.viewStageInner.classList.remove("dragging");
    });

    // touch pan & pinch zoom
    let lastTouchDist = null;
    let lastTouchCenter = null;
    els.viewStage.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        if (state.viewZoom <= 100 && !state.viewDragMode) return;
        state.viewIsDragging = true;
        state.viewDragStartX = e.touches[0].clientX;
        state.viewDragStartY = e.touches[0].clientY;
        state.viewPanStartX = state.viewPanX;
        state.viewPanStartY = state.viewPanY;
      } else if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        lastTouchDist = Math.hypot(dx, dy);
        lastTouchCenter = {
          x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
          y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
          panX: state.viewPanX,
          panY: state.viewPanY,
        };
      }
    }, { passive: false });
    els.viewStage.addEventListener("touchmove", (e) => {
      if (e.touches.length === 1 && state.viewIsDragging) {
        e.preventDefault();
        const dx = e.touches[0].clientX - state.viewDragStartX;
        const dy = e.touches[0].clientY - state.viewDragStartY;
        state.viewPanX = state.viewPanStartX + dx;
        state.viewPanY = state.viewPanStartY + dy;
        applyViewTransform();
      } else if (e.touches.length === 2 && lastTouchDist !== null) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        const delta = (dist - lastTouchDist) * 0.5;
        if (Math.abs(delta) > 2) {
          setViewZoom(delta, lastTouchCenter);
          lastTouchDist = dist;
        }
      }
    }, { passive: false });
    els.viewStage.addEventListener("touchend", () => {
      state.viewIsDragging = false;
      lastTouchDist = null;
      lastTouchCenter = null;
      if (els.viewStage) els.viewStage.classList.remove("dragging");
      if (els.viewStageInner) els.viewStageInner.classList.remove("dragging");
    });

    // IMPORTANT FIX: clicking canvas does NOT force exit from zoom
    // Only clicking the overlay background outside stage (not image) would close, but we disable that to prevent accidental exit
    // So we do NOT close on viewStage click anymore — only X buttons and Esc close
    // If user explicitly wants to close by clicking background, they can click the dark area outside inner? We keep it disabled to fix bug
  }

  // compare
  if (els.compareBtn) els.compareBtn.addEventListener("click", openCompare);
  if (els.advCompareBtn) els.advCompareBtn.addEventListener("click", openCompare);
  if (els.compareCloseBtn) els.compareCloseBtn.addEventListener("click", closeCompare);
  if (els.compareOverlay) {
    els.compareOverlay.addEventListener("click", (e) => {
      if (e.target === els.compareStage || e.target === els.compareOverlay) closeCompare();
    });
  }
  if (els.compareSlider) {
    els.compareSlider.addEventListener("input", (e) => updateCompare(e.target.value));
  }
  if (els.bgToggleBtn) {
    els.bgToggleBtn.addEventListener("click", () => {
      state.bgChecker = !state.bgChecker;
      if (els.resultSvgBox) els.resultSvgBox.classList.toggle("checker", state.bgChecker);
      if (els.advResultSvgBox) els.advResultSvgBox.classList.toggle("checker", state.bgChecker);
      saveProject();
    });
  }

  // advanced params — custom sliders
  function bindRange(input, valEl, key) {
    if (!input || !valEl) return;
    const update = () => {
      updateSliderFill(input);
      let displayVal = input.value;
      if (key === "filter_speckle") {
        const exp = parseInt(input.value, 10);
        const v = Math.pow(2, exp);
        displayVal = v;
        valEl.textContent = v;
        state[key] = v;
      } else {
        valEl.textContent = input.value;
        state[key] = input.type === "range" ? parseInt(input.value, 10) : input.value;
        if (key === "profile") state[key] = input.value;
      }
      saveProject();
    };
    input.addEventListener("input", update);
    // init
    update();
  }
  bindRange(els.advCp, els.advCpVal, "color_precision");
  bindRange(els.advLd, els.advLdVal, "layer_difference");
  bindRange(els.advFs, els.advFsVal, "filter_speckle");
  bindRange(els.advMi, els.advMiVal, "max_iterations");
  if (els.advProfile) {
    els.advProfile.addEventListener("change", () => { state.profile = els.advProfile.value; saveProject(); });
  }
  if (els.advReconvertBtn) els.advReconvertBtn.addEventListener("click", reconvertWithAdvanced);

  // sidebar collapsible
  document.querySelectorAll("[data-toggle]").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-toggle");
      const body = document.getElementById(id + "Body");
      if (!body) return;
      const isHidden = body.hidden;
      body.hidden = !isHidden;
      btn.parentElement.classList.toggle("collapsed", !isHidden);
    });
  });
  if (els.sidebarDebugBtn) els.sidebarDebugBtn.addEventListener("click", () => setView("debug"));
  if (els.sidebarManualBtn) els.sidebarManualBtn.addEventListener("click", () => setView("manual"));

  // manual training wiring
  if (els.manualDropzone1 && els.manualFileInput1) {
    els.manualDropzone1.addEventListener("click", () => els.manualFileInput1.click());
    els.manualDropzone1.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.manualFileInput1.click(); } });
    els.manualFileInput1.addEventListener("change", () => {
      uploadManual(els.manualFileInput1.files, "/api/manual/images", els.manualList1);
      els.manualFileInput1.value = "";
    });
  }
  if (els.manualDropzone2 && els.manualFileInput2) {
    els.manualDropzone2.addEventListener("click", () => els.manualFileInput2.click());
    els.manualDropzone2.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.manualFileInput2.click(); } });
    els.manualFileInput2.addEventListener("change", () => {
      uploadManual(els.manualFileInput2.files, "/api/manual/results", els.manualList2);
      els.manualFileInput2.value = "";
    });
  }
  if (els.manualTrainBtn) els.manualTrainBtn.addEventListener("click", triggerManualTrain);
  if (els.manualRefreshBtn) els.manualRefreshBtn.addEventListener("click", refreshManualStatus);
  if (els.debugVetBtn) els.debugVetBtn.addEventListener("click", vetModelStrict);

  /* ---------- drag and drop ---------- */
  let dragDepth = 0;
  let dragHasFiles = false;
  function isFileDrag(e) {
    if (!e.dataTransfer) return false;
    const types = e.dataTransfer.types;
    return types && (types.contains ? types.contains("Files") : types.includes && types.includes("Files"));
  }
  window.addEventListener("dragenter", (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragHasFiles = true;
    dragDepth += 1;
    if (els.dropOverlay) els.dropOverlay.hidden = false;
    document.body.classList.add("dragging");
  });
  window.addEventListener("dragover", (e) => {
    if (!dragHasFiles) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", (e) => {
    if (!dragHasFiles) return;
    if (e.target === document.documentElement || e.target === document.body) dragDepth = 0;
    else dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      if (els.dropOverlay) els.dropOverlay.hidden = true;
      document.body.classList.remove("dragging");
      dragHasFiles = false;
    }
  });
  window.addEventListener("drop", (e) => {
    if (!dragHasFiles) return;
    e.preventDefault();
    dragDepth = 0;
    dragHasFiles = false;
    if (els.dropOverlay) els.dropOverlay.hidden = true;
    document.body.classList.remove("dragging");
    const files = e.dataTransfer && e.dataTransfer.files;
    const f = files && files[0];
    if (f) {
      if (window.__vz.view === "result" || window.__vz.view === "advanced") convert(f);
      else if (window.__vz.view === "upload" || window.__vz.view === "landing") convert(f);
      else if (window.__vz.view === "manual") uploadManual(files, "/api/manual/images", els.manualList1);
      else convert(f);
    }
  });
  window.addEventListener("paste", (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (const it of items) {
      if (it.type && it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) {
          if (!f.name) f.name = "pasted-image.png";
          convert(f);
        }
        break;
      }
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (state.viewOpen) closeView();
      if (state.compareOpen) closeCompare();
      if (els.dropOverlay && !els.dropOverlay.hidden) {
        els.dropOverlay.hidden = true;
        document.body.classList.remove("dragging");
        dragDepth = 0;
        dragHasFiles = false;
      }
    }
    // viewer shortcuts
    if (state.viewOpen) {
      if (e.key === "+" || e.key === "=") { e.preventDefault(); setViewZoom(25); }
      if (e.key === "-" || e.key === "_") { e.preventDefault(); setViewZoom(-25); }
      if (e.key === "0") { e.preventDefault(); fitView(); }
      if (e.key === "1") { e.preventDefault(); setViewZoomAbsolute(100, true); }
    }
  });

  // init
  (async () => {
    initSlidersFill();
    const restored = await loadProject();
    if (!restored) {
      const v = localStorage.getItem("vz_view");
      if (v && ["landing", "upload", "result", "advanced", "manual", "debug"].includes(v)) setView(v);
      else setView("landing");
    }
    applyZoom();
  })();
})();
