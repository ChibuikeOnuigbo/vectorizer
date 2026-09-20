/* Vectorizer frontend — one click to convert, view, download.
   "Smart model" (default on) runs an ONNX parameter predictor in the
   browser; the server vectorizes with the model's chosen settings. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    landing: $("landing"),
    upload: $("upload"),
    result: $("result"),
    manual: $("manual"),
    debug: $("debug"),
    startBtn: $("startBtn"),
    manualBtn: $("manualBtn"),
    debugBtn: $("debugBtn"),
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
    downloadBtn: $("downloadBtn"),
    viewBtn: $("viewBtn"),
    newBtn: $("newBtn"),
    dropOverlay: $("dropOverlay"),
    viewOverlay: $("viewOverlay"),
    viewStage: $("viewStage"),
    viewTitle: $("viewTitle"),
    viewDownloadBtn: $("viewDownloadBtn"),
    viewCloseBtn: $("viewCloseBtn"),
    toast: $("toast"),
    brandHome: $("brandHome"),
    // manual training
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
    // debug vet
    debugLimit: $("debugLimit"),
    debugVetBtn: $("debugVetBtn"),
    debugStatus: $("debugStatus"),
    debugResults: $("debugResults"),
  };

  const ACCEPTED = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
  const MAX_BYTES = 20 * 1024 * 1024;
  const MODEL_F = 1047;
  const state = {
    svgText: null, svgUrl: null, fileName: "vector.svg",
    busy: false, viewOpen: false,
  };
  let toastTimer = null;

  // debug/QA hook
  window.__vz = { view: "landing", model: { status: "idle", lastParams: null, lastError: null } };

  /* ---------- helpers ---------- */

  function toast(msg, kind) {
    els.toast.textContent = msg;
    els.toast.className = `toast ${kind || ""}`;
    els.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.hidden = true; }, 4200);
  }

  function validFile(file) {
    if (!file) return "No file found.";
    const name = (file.name || "image").toLowerCase();
    if (!ACCEPTED.some((e) => name.endsWith(e)))
      return `Unsupported file type: ${name}. Use PNG, JPG, WebP, GIF or BMP.`;
    if (file.size > MAX_BYTES) return "File too large (max 20 MB).";
    return null;
  }

  function setLoading(on) {
    state.busy = on;
    els.convertBtn.disabled = on;
    els.dropzone.style.pointerEvents = on ? "none" : "";
    const label = els.convertBtn.querySelector(".btn-label");
    label.textContent = on ? "Converting" : "Convert";
    els.convertBtn.classList.toggle("loading", on);
  }

  function setView(name) {
    els.landing.hidden = name !== "landing";
    els.upload.hidden = name !== "upload";
    els.result.hidden = name !== "result";
    if (els.manual) els.manual.hidden = name !== "manual";
    if (els.debug) els.debug.hidden = name !== "debug";
    window.__vz.view = name;
    window.scrollTo({ top: 0 });
    if (name === "manual") refreshManualStatus();
    if (name === "debug") els.debugStatus.textContent = "Click Vet to run strict grading...";
  }

  function showResult(meta, modelUsed) {
    setView("result");
    const parts = [`${meta.colors} colors`, `${meta.paths} paths`, `${meta.kb} KB`];
    if (meta.transparent_bg) parts.push("transparent background");
    if (modelUsed) parts.push("smart model");
    parts.push(`${meta.seconds}s`);
    els.resultMeta.textContent = parts.join("  \u00B7  ");
  }

  function makeBlobUrl() {
    if (state.svgUrl) URL.revokeObjectURL(state.svgUrl);
    const blob = new Blob([state.svgText], { type: "image/svg+xml" });
    state.svgUrl = URL.createObjectURL(blob);
    return state.svgUrl;
  }

  function download() {
    const a = document.createElement("a");
    a.href = makeBlobUrl();
    a.download = state.fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  /* ---------- smart model (ONNX in the browser) ---------- */

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

  /* Must stay in lockstep with model/features.py (FEATURE_DIM=1047). */
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
    const px = (x, y) => ((y * N) + x) * 4;
    let cr = 0, cg = 0, cb = 0, n = 0, content = 0;
    const sr = new Array(N * N), sg = new Array(N * N), sb = new Array(N * N);
    for (let i = 0; i < N * N; i++) {
      sr[i] = d[i * 4] / 255; sg[i] = d[i * 4 + 1] / 255; sb[i] = d[i * 4 + 2] / 255;
    }
    for (let i = 0; i < N * N; i++) {
      if (d[i * 4 + 3] > 127.5) {
        cr += sr[i]; cg += sg[i]; cb += sb[i];
        n++; content++;
      }
    }
    const base = 1024;
    out[base + 0] = n ? cr / n : 0;
    out[base + 1] = n ? cg / n : 0;
    out[base + 2] = n ? cb / n : 0;
    // std over ALL pixels (population)
    const meanR = cr / (n || 1), meanG = cg / (n || 1), meanB = cb / (n || 1);
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

    // hue/sat over content (matches _rgb_to_hsv in features.py)
    const hueBin = new Array(12).fill(0);
    let satSum = 0;
    for (let i = 0; i < N * N; i++) {
      if (d[i * 4 + 3] <= 127.5) continue;
      const r = sr[i], g = sg[i], b = sb[i];
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), dd = mx - mn;
      let h = 0;
      if (dd > 0) {
        if (mx === r) h = ((g - b) / dd) % 6;
        else if (mx === g) h = (b - r) / dd + 2;
        else h = (r - g) / dd + 4;
        h = (h / 6) % 1;
        let bin = Math.floor(h * 12);
        if (bin >= 12) bin = 11;
        hueBin[bin]++;
      }
      satSum += mx > 0 ? dd / Math.max(mx, 1e-9) : 0;
    }
    for (let k = 0; k < 12; k++) out[base + 7 + k] = n && hueBin[k] / n >= 0.02 ? 1 : 0;
    out[base + 19] = n ? satSum / n : 0;

    // alpha edge density (wrap-around, like np.roll)
    const a = new Array(N * N);
    for (let i = 0; i < N * N; i++) a[i] = d[i * 4 + 3] / 255;
    let edge = 0;
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const i = y * N + x;
      const xr = (x + 1) % N, dr = (y + 1) % N;
      edge += Math.abs(a[y * N + xr] - a[i]) + Math.abs(a[dr * N + x] - a[i]);
    }
    out[base + 20] = Math.min(1, edge / (N * N));

    // distinct 4-bit colors (a4 = floor(alpha01) -> 0 or 1, matches python)
    const keys = new Set();
    for (let i = 0; i < N * N; i++) {
      const r4 = Math.floor(sr[i] * 15) & 15;
      const g4 = Math.floor(sg[i] * 15) & 15;
      const b4 = Math.floor(sb[i] * 15) & 15;
      const a4 = Math.floor(d[i * 4 + 3] / 255) & 15;
      keys.add(((r4 << 12) | (g4 << 8) | (b4 << 4) | a4));
    }
    out[base + 21] = Math.min(1, keys.size / 256);

    // luma gradient over content
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
          modelUsed = true;
        } catch (me) {
          window.__vz.model.status = "error";
          window.__vz.model.lastError = String(me && me.message || me);
          toast("Smart model unavailable \u2014 using standard settings", "error");
        }
      }
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      state.svgText = data.svg;
      state.fileName = (file.name || "image").replace(/\.[^.]+$/, "") + ".svg";
      els.resultOriginal.src = URL.createObjectURL(file);
      els.resultSvg.src = makeBlobUrl();
      showResult(data.meta, modelUsed);
      toast("Vector ready", "ok");
    } catch (e) {
      toast(e.message || "Conversion failed. Try another image.", "error");
    } finally {
      setLoading(false);
    }
  }

  /* ---------- manual training & debug vet (very strict) ---------- */

  async function refreshManualStatus() {
    if (!els.manualStatus) return;
    try {
      const res = await fetch("/api/manual/status");
      const data = await res.json();
      els.manualStatus.innerHTML = `
        <strong>Collected:</strong> ${data.total_images} images (Section 1) · ${data.total_results} results (Section 2) · ONNX ${(data.onnx_size/1024/1024).toFixed(2)} MB · Model ${data.model_exists ? "exists" : "missing"}<br>
        <small>${data.note || ""}</small><br>
        <small>Images sample: ${(data.images_sample||[]).slice(0,5).join(", ")}</small><br>
        <small>Results sample: ${(data.results_sample||[]).slice(0,5).join(", ")}</small>
      `;
      if (els.manualLog && data.last_training) {
        els.manualLog.innerHTML = "<h4>Last training (continuous):</h4><pre>" + JSON.stringify(data.last_training, null, 2) + "</pre>";
      }
    } catch (e) {
      els.manualStatus.textContent = "Failed to load status: " + e.message;
    }
  }

  async function uploadManual(files, endpoint, listEl) {
    if (!files || files.length === 0) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    try {
      toast(`Uploading ${files.length} files...`, "ok");
      const res = await fetch(endpoint, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.status);
      toast(`Saved ${data.saved} files — total images ${data.total_images}, results ${data.total_results}`, "ok");
      if (listEl) {
        listEl.innerHTML = data.files.map(n => `<div>${n}</div>`).join("");
      }
      refreshManualStatus();
    } catch (e) {
      toast("Upload failed: " + e.message, "error");
    }
  }

  async function triggerManualTrain() {
    try {
      toast("Starting training in background...", "ok");
      const res = await fetch("/api/manual/train", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.status);
      toast(data.msg, "ok");
      if (els.manualLog) els.manualLog.innerHTML += "<p>Training started — check status in 30s, ONNX will update, model improves...</p>";
    } catch (e) {
      toast("Train failed: " + e.message, "error");
    }
  }

  async function vetModelStrict() {
    if (!els.debugStatus || !els.debugResults) return;
    const limit = parseInt(els.debugLimit?.value || "20", 10) || 20;
    els.debugStatus.textContent = `Vetting model very strictly (limit ${limit}) — scanning result and grading strictly...`;
    els.debugResults.innerHTML = "<p>Running strict scan...</p>";
    try {
      const res = await fetch(`/api/debug/vet?limit=${limit}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      els.debugStatus.innerHTML = `
        <strong>Strict Vet Result:</strong> ${data.pass} PASS / ${data.fail} FAIL / ${data.total} total — pass_rate ${(data.pass_rate*100).toFixed(1)}% — avg_score ${data.avg_score}<br>
        <small>Thresholds: ${data.thresholds.clean} | ${data.thresholds.blurred}</small><br>
        <small>Model: ${data.model.arch}, ONNX ${(data.model.onnx_size/1024/1024).toFixed(2)} MB</small>
      `;
      const rows = data.results.map(r => {
        if (r.error) return `<div class="debug-row fail">${r.name}: ERROR ${r.error}</div>`;
        const cls = r.grade === "PASS" ? "pass" : "fail";
        return `<div class="debug-row ${cls}">
          <strong>${r.name}</strong> — ${r.grade} — score ${r.score} cov ${r.coverage} prec ${r.precision} color_err ${r.color_err} paths ${r.paths} ${r.is_clean ? "clean" : "blurred"}<br>
          <small>strict: score_ok=${r.strict.score_ok} coverage_ok=${r.strict.coverage_ok} precision_ok=${r.strict.precision_ok} color_ok=${r.strict.color_ok} paths_ok=${r.strict.paths_ok} | params ${JSON.stringify(r.params)}</small>
        </div>`;
      }).join("");
      els.debugResults.innerHTML = rows;
      toast(`Vet done: ${data.pass} PASS / ${data.fail} FAIL`, data.fail > 0 ? "error" : "ok");
    } catch (e) {
      els.debugStatus.textContent = "Vet failed: " + e.message;
      toast("Vet failed: " + e.message, "error");
    }
  }

  /* ---------- wiring ---------- */

  els.startBtn.addEventListener("click", () => setView("upload"));
  if (els.manualBtn) els.manualBtn.addEventListener("click", () => setView("manual"));
  if (els.debugBtn) els.debugBtn.addEventListener("click", () => setView("debug"));
  els.backBtn.addEventListener("click", () => setView("landing"));
  if (els.manualBackBtn) els.manualBackBtn.addEventListener("click", () => setView("landing"));
  if (els.debugBackBtn) els.debugBackBtn.addEventListener("click", () => setView("landing"));
  els.newBtn.addEventListener("click", () => setView("upload"));
  els.brandHome.addEventListener("click", (e) => {
    if (window.__vz.view === "landing") return;
    e.preventDefault();
    setView("landing");
  });

  const openPicker = () => els.fileInput.click();
  els.convertBtn.addEventListener("click", openPicker);
  els.dropzone.addEventListener("click", openPicker);
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPicker(); }
  });
  els.fileInput.addEventListener("change", () => {
    const f = els.fileInput.files && els.fileInput.files[0];
    if (f) convert(f);
    els.fileInput.value = "";
  });
  els.downloadBtn.addEventListener("click", download);

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

  // debug vet wiring
  if (els.debugVetBtn) els.debugVetBtn.addEventListener("click", vetModelStrict);

  /* ---------- fullscreen view ---------- */

  function openView() {
    if (!state.svgText) return;
    const img = document.createElement("img");
    img.src = makeBlobUrl();
    img.alt = "Vectorized SVG, fullscreen";
    while (els.viewStage.firstChild) els.viewStage.removeChild(els.viewStage.firstChild);
    els.viewStage.appendChild(img);
    els.viewTitle.textContent = state.fileName;
    els.viewOverlay.hidden = false;
    state.viewOpen = true;
  }
  function closeView() {
    els.viewOverlay.hidden = true;
    state.viewOpen = false;
  }
  els.viewBtn.addEventListener("click", openView);
  els.viewCloseBtn.addEventListener("click", closeView);
  els.viewDownloadBtn.addEventListener("click", download);
  els.viewOverlay.addEventListener("click", (e) => {
    if (e.target === els.viewStage) closeView();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.viewOpen) closeView();
  });

  /* ---------- drag & drop + paste ---------- */

  let dragDepth = 0;
  window.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragDepth += 1;
    document.body.classList.add("dragging");
    els.dropOverlay.hidden = false;
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      els.dropOverlay.hidden = true;
      document.body.classList.remove("dragging");
    }
  });
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    els.dropOverlay.hidden = true;
    document.body.classList.remove("dragging");
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    convert(f);
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
})();
