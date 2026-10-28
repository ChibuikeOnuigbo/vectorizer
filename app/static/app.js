/* Vectorizer — simplified landing, icons only nav, two methods model and classic best tier, choice modal, custom sliders, pro viewer with floating tools, compare dotted line */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    landing: $("landing"),
    upload: $("upload"),
    result: $("result"),
    advanced: $("advanced"),

    startBtn: $("startBtn"),
    navHome: $("navHome"),
    navUpload: $("navUpload"),
    navSimple: $("navSimple"),
    navAdvanced: $("navAdvanced"),

    backBtn: $("backBtn"),

    dropzone: $("dropzone"),
    convertBtn: $("convertBtn"),
    modelToggle: $("modelToggle"),
    fileInput: $("fileInput"),
    methodModel: $("methodModel"),
    modelOptions: $("modelOptions"),
    mColors: $("mColors"),
    mColorsVal: $("mColorsVal"),
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
    inspectColors: $("inspectColors"),
    inspectPaths: $("inspectPaths"),
    inspectKb: $("inspectKb"),
    inspectTime: $("inspectTime"),
    inspectTrans: $("inspectTrans"),
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
    viewFloatZoomOut: $("viewFloatZoomOut"),
    viewFloatZoomIn: $("viewFloatZoomIn"),
    viewFloatDrag: $("viewFloatDrag"),
    viewFloatFit: $("viewFloatFit"),
    viewHint: $("viewHint"),
    compareOverlay: $("compareOverlay"),
    compareStage: $("compareStage"),
    compareSrc: $("compareSrc"),
    compareVec: $("compareVec"),
    compareSlider: $("compareSlider"),
    compareDivider: $("compareDivider"),
    compareHandle: $("compareHandle"),
    compareCloseBtn: $("compareCloseBtn"),
    toast: $("toast"),
    brandHome: $("brandHome"),
    // (deleted) manual training panel elements — none exist in index.html
  };

  const ACCEPTED = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
  const MAX_BYTES = 20 * 1024 * 1024;
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
    viewZoom: 100,
    viewPanX: 0,
    viewPanY: 0,
    viewIsDragging: false,
    viewDragStartX: 0,
    viewDragStartY: 0,
    viewPanStartX: 0,
    viewPanStartY: 0,
    viewDragMode: false,
    method: "model",
    mTouched: { colors: false },
  };

  let toastTimer = null;
  window.__vz = { view: "landing", model: { status: "idle", lastParams: null, lastError: null } };


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
      // Never overwrite a stored project with an empty one; init paths call
      // saveProject() before any vector exists, which used to
      // clobber the user's saved work on every page load (R2 persistence bug
      // found by qa/qa_regressions.mjs). Without a vector we only persist
      // the current view name.
      if (!state.svgText) {
        localStorage.setItem("vz_view", window.__vz.view);
        return;
      }
      const data = {
        fileName: state.fileName,
        svgText: state.svgText,
        meta: state.meta,
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
      setMethod("model");
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
        toast("Project restored", "ok");
        return true;
      }
    } catch {}
    return false;
  }

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
  function refreshIcons() {
    try {
      if (window.lucide && typeof window.lucide.createIcons === "function") window.lucide.createIcons();
      if (typeof window.initLucide === "function") window.initLucide();
    } catch {}
  }
  function setView(name) {
    if (els.landing) els.landing.hidden = name !== "landing";
    if (els.upload) els.upload.hidden = name !== "upload";
    if (els.result) els.result.hidden = name !== "result";
    if (els.advanced) els.advanced.hidden = name !== "advanced";

    window.__vz.view = name;
    localStorage.setItem("vz_view", name);
    window.scrollTo({ top: 0 });

    saveProject();
    // Lucide + Tailwind + shadcn + Icon8 + FontAwesome all use SVG, refresh after view change
    setTimeout(refreshIcons, 50);
  }
  function showResult(meta, modelUsed) {
    state.meta = meta;
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
    setView("result");
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
    const cs = document.getElementById("compareSlider");
    if (cs) {
      const min = parseFloat(cs.min) || 0;
      const max = parseFloat(cs.max) || 100;
      const val = parseFloat(cs.value) || 50;
      const pct = ((val - min) / (max - min)) * 100;
      cs.style.setProperty("--fill", pct + "%");
    }
  }

  function appendSliders(fd) {
    if (state.mTouched.colors) {
      const v = parseInt(els.mColors?.value || "0", 10);
      if (v > 0) fd.append("colors", String(Math.min(128, 2 ** (v + 1))));
    }

  }

  async function convert(file) {
    if (state.busy) return;
    const err = validFile(file);
    if (err) { toast(err, "error"); return; }
    setLoading(true);
    try {
      state.sourceFile = file;
      if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
      state.sourceUrl = URL.createObjectURL(file);
      if (els.resultOriginal) els.resultOriginal.src = state.sourceUrl;
      if (els.advResultOriginal) els.advResultOriginal.src = state.sourceUrl;
      if (els.srcMeta) els.srcMeta.textContent = `${file.name} ${ (file.size/1024).toFixed(1)} KB`;

      const fd = new FormData();
      fd.append("file", file);
      appendSliders(fd);
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      state.svgText = data.svg;
      state.fileName = (file.name || "image").replace(/\.[^.]+$/, "") + ".svg";
      if (els.resultSvg) els.resultSvg.src = makeBlobUrl();
      if (els.advResultSvg) els.advResultSvg.src = makeBlobUrl();
      showResult(data.meta, true);
      toast("Vector ready", "ok");
    } catch (e) {
      toast(e.message || "Conversion failed Try another image", "error");
    } finally {
      setLoading(false);
    }
  }

  // 2026-10-05 simplification: the manual training panel + its JS were
  // deleted from the product UI (the verdict flywheel lives in the
  // self-contained test-report.html; the /api/manual/* endpoints remain
  // for that page only).

  function applyViewTransform() {
    if (!els.viewStageInner) return;
    const scale = state.viewZoom / 100;
    els.viewStageInner.style.transform = `translate(${state.viewPanX}px, ${state.viewPanY}px) scale(${scale})`;
    if (els.viewZoomLevel) els.viewZoomLevel.textContent = Math.round(state.viewZoom) + "%";
    if (els.viewStage) {
      if (state.viewZoom > 100 || state.viewDragMode) els.viewStage.classList.add("drag-mode");
      else els.viewStage.classList.remove("drag-mode");
    }
  }
  function setViewZoom(delta, anchor) {
    const oldZoom = state.viewZoom;
    let newZoom = oldZoom + delta;
    newZoom = Math.max(25, Math.min(800, newZoom));
    if (anchor && els.viewStage) {
      const rect = els.viewStage.getBoundingClientRect();
      const cx = rect.width / 2, cy = rect.height / 2;
      const ax = anchor.x - rect.left - cx;
      const ay = anchor.y - rect.top - cy;
      const scaleRatio = newZoom / oldZoom;
      state.viewPanX = anchor.panX + (ax - ax * scaleRatio) + (state.viewPanX - anchor.panX) * scaleRatio;
      state.viewPanY = anchor.panY + (ay - ay * scaleRatio) + (state.viewPanY - anchor.panY) * scaleRatio;
    }
    state.viewZoom = newZoom;
    applyViewTransform();
  }
  function setViewZoomAbsolute(zoom, center) {
    state.viewZoom = Math.max(25, Math.min(800, zoom));
    if (center) { state.viewPanX = 0; state.viewPanY = 0; }
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
    if (els.viewFloatDrag) els.viewFloatDrag.classList.remove("active");
    applyViewTransform();
    document.body.style.overflow = "hidden";
    setTimeout(refreshIcons, 50);
  }
  function closeView() {
    if (els.viewOverlay) els.viewOverlay.hidden = true;
    state.viewOpen = false;
    state.viewIsDragging = false;
    if (els.viewStage) els.viewStage.classList.remove("dragging");
    document.body.style.overflow = "";
  }
  function openCompare() {
    if (!state.sourceUrl || !state.svgUrl) { toast("Need source and vector to compare", "error"); return; }
    if (els.compareSrc) els.compareSrc.src = state.sourceUrl;
    if (els.compareVec) els.compareVec.src = state.svgUrl;
    if (els.compareOverlay) els.compareOverlay.hidden = false;
    state.compareOpen = true;
    updateCompare(50);
    setTimeout(refreshIcons, 50);
  }
  function closeCompare() {
    if (els.compareOverlay) els.compareOverlay.hidden = true;
    state.compareOpen = false;
  }
  function updateCompare(val) {
    const v = Math.max(0, Math.min(100, val));
    const vec = document.querySelector(".compare-vector");
    if (vec) vec.style.clipPath = `inset(0 0 0 ${v}%)`;
    if (els.compareDivider) els.compareDivider.style.left = v + "%";
    if (els.compareHandle) els.compareHandle.style.left = v + "%";
    const cs = els.compareSlider;
    if (cs) {
      if (Math.abs(parseFloat(cs.value) - v) > 0.01) cs.value = String(v);
      const min = parseFloat(cs.min) || 0;
      const max = parseFloat(cs.max) || 100;
      const pct = ((v - min) / (max - min)) * 100;
      cs.style.setProperty("--fill", pct + "%");
    }
  }

  // No native image dragging anywhere: users kept pulling imgs out of their
  // containers (dropzone, viewer, compare). Block it globally, including
  // images added later (this fires for every drag attempt on any <img>).
  document.addEventListener("dragstart", (e) => {
    if (e.target && e.target.tagName === "IMG") e.preventDefault();
  }, true);

  // Compare: the dotted line + handle are directly draggable (pointer drag
  // on the stage snaps the divider to the pointer and keeps it following).
  function compareDragStart(e) {
    if (!state.compareOpen) return;
    e.preventDefault();
    state._cmpDragging = true;
    try { els.compareStage.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }
    compareDragMove(e);
  }
  function compareDragMove(e) {
    if (!state._cmpDragging || !els.compareStage) return;
    const r = els.compareStage.getBoundingClientRect();
    if (!r.width) return;
    const v = ((e.clientX - r.left) / r.width) * 100;
    updateCompare(v);
  }
  function compareDragEnd(e) {
    if (!state._cmpDragging) return;
    state._cmpDragging = false;
    try { els.compareStage.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
  }

  if (els.startBtn) els.startBtn.addEventListener("click", () => setView("upload"));
  if (els.navHome) els.navHome.addEventListener("click", () => setView("landing"));
  if (els.navUpload) els.navUpload.addEventListener("click", () => setView("upload"));
  if (els.navSimple) els.navSimple.addEventListener("click", () => {
    if (state.svgText) setView("result");
    else setView("landing");
  });
  if (els.navAdvanced) els.navAdvanced.addEventListener("click", () => {
    if (state.svgText) setView("advanced");
    else setView("upload");
  });

  if (els.backBtn) els.backBtn.addEventListener("click", () => setView("landing"));

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

  if (els.resultSvgBox) els.resultSvgBox.addEventListener("click", (e) => { e.stopPropagation(); openView(); });
  if (els.advResultSvgBox) els.advResultSvgBox.addEventListener("click", (e) => { e.stopPropagation(); openView(); });
  if (els.viewBtn) els.viewBtn.addEventListener("click", openView);
  if (els.advViewBtn) els.advViewBtn.addEventListener("click", openView);
  if (els.viewCloseBtn) els.viewCloseBtn.addEventListener("click", closeView);
  if (els.viewCloseBtn2) els.viewCloseBtn2.addEventListener("click", closeView);
  if (els.viewDownloadBtn) els.viewDownloadBtn.addEventListener("click", download);
  if (els.viewZoomOutBtn) els.viewZoomOutBtn.addEventListener("click", () => setViewZoom(-25));
  if (els.viewZoomInBtn) els.viewZoomInBtn.addEventListener("click", () => setViewZoom(25));
  if (els.viewFitBtn) els.viewFitBtn.addEventListener("click", fitView);
  if (els.viewActualBtn) els.viewActualBtn.addEventListener("click", () => setViewZoomAbsolute(100, true));
  if (els.viewFloatZoomOut) els.viewFloatZoomOut.addEventListener("click", () => setViewZoom(-25));
  if (els.viewFloatZoomIn) els.viewFloatZoomIn.addEventListener("click", () => setViewZoom(25));
  if (els.viewFloatFit) els.viewFloatFit.addEventListener("click", fitView);
  const toggleDrag = () => {
    state.viewDragMode = !state.viewDragMode;
    if (els.viewDragBtn) els.viewDragBtn.classList.toggle("active", state.viewDragMode);
    if (els.viewFloatDrag) els.viewFloatDrag.classList.toggle("active", state.viewDragMode);
    if (els.viewStage) els.viewStage.classList.toggle("drag-mode", state.viewDragMode || state.viewZoom > 100);
  };
  if (els.viewDragBtn) els.viewDragBtn.addEventListener("click", toggleDrag);
  if (els.viewFloatDrag) els.viewFloatDrag.addEventListener("click", toggleDrag);

  if (els.viewStage) {
    els.viewStage.addEventListener("wheel", (e) => {
      if (!state.viewOpen) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -25 : 25;
      setViewZoom(delta, { x: e.clientX, y: e.clientY, panX: state.viewPanX, panY: state.viewPanY });
    }, { passive: false });
    els.viewStage.addEventListener("mousedown", (e) => {
      if (!state.viewOpen) return;
      if (e.button !== 0) return;
      if (state.viewZoom <= 100 && !state.viewDragMode) return;
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
  }

  if (els.compareBtn) els.compareBtn.addEventListener("click", openCompare);
  if (els.advCompareBtn) els.advCompareBtn.addEventListener("click", openCompare);
  if (els.compareCloseBtn) els.compareCloseBtn.addEventListener("click", closeCompare);
  if (els.compareOverlay) {
    if (els.compareStage) {
      els.compareStage.addEventListener("pointerdown", compareDragStart);
      els.compareStage.addEventListener("pointermove", compareDragMove);
      els.compareStage.addEventListener("pointerup", compareDragEnd);
      els.compareStage.addEventListener("pointercancel", compareDragEnd);
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.compareOpen) closeCompare();
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

  // one smart mode; tuning numerics are server-locked
  function setMethod(method) {
    state.method = "model";
    saveProject();
  }
  if (els.methodModel) els.methodModel.addEventListener("click", () => setMethod("model"));

  // model mode sliders: Colors / Detail level / Corner smoothness
  const COLORS_STEPS = ["Auto", "4", "8", "16", "32", "64", "128"];
  if (els.mColors) {
    els.mColors.addEventListener("input", () => {
      state.mTouched.colors = parseInt(els.mColors.value, 10) > 0;
      if (els.mColorsVal) els.mColorsVal.textContent = COLORS_STEPS[parseInt(els.mColors.value, 10)] || "Auto";
      updateSliderFill(els.mColors);
      saveProject();
    });
  }
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
    if (f) convert(f);
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
    if (state.viewOpen) {
      if (e.key === "+" || e.key === "=") { e.preventDefault(); setViewZoom(25); }
      if (e.key === "-" || e.key === "_") { e.preventDefault(); setViewZoom(-25); }
      if (e.key === "0") { e.preventDefault(); fitView(); }
      if (e.key === "1") { e.preventDefault(); setViewZoomAbsolute(100, true); }
    }
  });

  (async () => {
    initSlidersFill();
    const restored = await loadProject();
    if (!restored) {
      const v = localStorage.getItem("vz_view");
      if (v && ["landing", "upload", "result", "advanced"].includes(v)) setView(v);
      else setView("landing");
    }
    applyZoom();
  })();
})();
