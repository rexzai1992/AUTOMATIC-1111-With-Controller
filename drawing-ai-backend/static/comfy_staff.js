(function () {
  const state = {
    currentJobId: "",
    currentJobStatus: "idle",
    currentBeforeUrl: "",
    galleryItems: [],
    presets: [],
    presetCategories: [],
    ws: null,
    wsRetryHandle: null
  };

  const el = {
    generateForm: document.getElementById("generateForm"),
    generateBtn: document.getElementById("generateBtn"),
    refreshStatusBtn: document.getElementById("refreshStatusBtn"),
    refreshGalleryBtn: document.getElementById("refreshGalleryBtn"),
    clearComfyBtn: document.getElementById("clearComfyBtn"),
    imageFile: document.getElementById("imageFile"),
    stylePreset: document.getElementById("stylePreset"),
    presetCategoryFilter: document.getElementById("presetCategoryFilter"),
    prompt: document.getElementById("prompt"),
    negativePrompt: document.getElementById("negativePrompt"),
    steps: document.getElementById("steps"),
    cfg: document.getElementById("cfg"),
    denoise: document.getElementById("denoise"),
    seed: document.getElementById("seed"),
    megapixels: document.getElementById("megapixels"),
    beforeImage: document.getElementById("beforeImage"),
    afterImage: document.getElementById("afterImage"),
    beforeHint: document.getElementById("beforeHint"),
    afterHint: document.getElementById("afterHint"),
    engineBadge: document.getElementById("engineBadge"),
    backendBadge: document.getElementById("backendBadge"),
    workflowBadge: document.getElementById("workflowBadge"),
    wsBadge: document.getElementById("wsBadge"),
    jobIdValue: document.getElementById("jobIdValue"),
    jobStatusValue: document.getElementById("jobStatusValue"),
    queueRunningValue: document.getElementById("queueRunningValue"),
    queuePendingValue: document.getElementById("queuePendingValue"),
    queueTotalValue: document.getElementById("queueTotalValue"),
    etaPerImageValue: document.getElementById("etaPerImageValue"),
    etaWaitValue: document.getElementById("etaWaitValue"),
    selectedPresetValue: document.getElementById("selectedPresetValue"),
    selectedPresetCategoryValue: document.getElementById("selectedPresetCategoryValue"),
    errorValue: document.getElementById("errorValue"),
    eventsLog: document.getElementById("eventsLog"),
    galleryList: document.getElementById("galleryList"),
    galleryCountLabel: document.getElementById("galleryCountLabel")
  };

  function fmtSeconds(value) {
    const sec = Number(value);
    if (!Number.isFinite(sec) || sec < 0) {
      return "-";
    }
    if (sec < 60) {
      return `${Math.round(sec)}s`;
    }
    const min = Math.floor(sec / 60);
    const rem = Math.round(sec % 60);
    return `${min}m ${rem}s`;
  }

  function fmtTime(value) {
    if (!value) {
      return "-";
    }
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) {
      return String(value);
    }
    return dt.toLocaleString();
  }

  function setWsBadge(connected) {
    if (!el.wsBadge) {
      return;
    }
    if (connected) {
      el.wsBadge.textContent = "ws: connected";
      el.wsBadge.classList.remove("warn");
      el.wsBadge.classList.add("ok");
    } else {
      el.wsBadge.textContent = "ws: reconnecting";
      el.wsBadge.classList.remove("ok");
      el.wsBadge.classList.add("warn");
    }
  }

  function appendEvent(message, level) {
    if (!el.eventsLog) {
      return;
    }
    const row = document.createElement("div");
    if (level === "error") {
      row.className = "event-error";
    } else if (level === "warn") {
      row.className = "event-warn";
    }
    const now = new Date().toLocaleTimeString();
    row.textContent = `[${now}] ${message}`;
    el.eventsLog.appendChild(row);
    while (el.eventsLog.children.length > 180) {
      el.eventsLog.removeChild(el.eventsLog.firstChild);
    }
    el.eventsLog.scrollTop = el.eventsLog.scrollHeight;
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    let payload = null;
    try {
      payload = await res.json();
    } catch (err) {
      payload = null;
    }
    if (!res.ok) {
      const detail = payload && payload.detail ? payload.detail : `Request failed: ${res.status}`;
      throw new Error(detail);
    }
    return payload || {};
  }

  function getJobEngine(job) {
    const settings = job && typeof job.generationSettings === "object" ? job.generationSettings : {};
    const engine = String((job && job.generationEngine) || settings.generationEngine || "").toLowerCase();
    return engine;
  }

  function isComfyJob(job) {
    return getJobEngine(job) === "comfyui";
  }

  function updateBeforePreview(file) {
    if (!file) {
      return;
    }
    if (state.currentBeforeUrl) {
      URL.revokeObjectURL(state.currentBeforeUrl);
      state.currentBeforeUrl = "";
    }
    const objectUrl = URL.createObjectURL(file);
    state.currentBeforeUrl = objectUrl;
    if (el.beforeImage) {
      el.beforeImage.src = objectUrl;
      el.beforeImage.style.display = "block";
    }
    if (el.beforeHint) {
      el.beforeHint.textContent = file.name || "Uploaded image";
    }
    if (el.afterImage) {
      el.afterImage.removeAttribute("src");
      el.afterImage.style.display = "none";
    }
    if (el.afterHint) {
      el.afterHint.textContent = "Waiting for generation output";
    }
  }

  function setCurrentJob(jobId, status) {
    state.currentJobId = String(jobId || "");
    state.currentJobStatus = String(status || "idle");
    if (el.jobIdValue) {
      el.jobIdValue.textContent = state.currentJobId || "-";
    }
    if (el.jobStatusValue) {
      el.jobStatusValue.textContent = state.currentJobStatus;
    }
  }

  function setStatusError(message) {
    if (el.errorValue) {
      el.errorValue.textContent = message || "-";
    }
  }

  function setSelectedPresetMeta(presetName, presetCategory) {
    if (el.selectedPresetValue) {
      el.selectedPresetValue.textContent = presetName || "-";
    }
    if (el.selectedPresetCategoryValue) {
      el.selectedPresetCategoryValue.textContent = presetCategory || "-";
    }
  }

  function getPresetMetaFromPayload(payload) {
    const settings = payload && typeof payload.generationSettings === "object" ? payload.generationSettings : {};
    const backendMeta = payload && typeof payload.backendMetadata === "object"
      ? payload.backendMetadata
      : (settings && typeof settings.backendMetadata === "object" ? settings.backendMetadata : {});
    const stylePresetName = String(
      backendMeta.style_preset_name
      || settings.stylePresetName
      || settings.style_preset_name
      || ""
    );
    const styleCategory = String(
      backendMeta.style_category
      || settings.styleCategory
      || settings.style_category
      || ""
    );
    return {
      stylePresetName,
      styleCategory
    };
  }

  function updateQueueEstimate(estimate) {
    const data = estimate || {};
    if (el.queueRunningValue) {
      el.queueRunningValue.textContent = String(data.queueRunning ?? "-");
    }
    if (el.queuePendingValue) {
      el.queuePendingValue.textContent = String(data.queuePending ?? "-");
    }
    if (el.queueTotalValue) {
      el.queueTotalValue.textContent = String(data.queueTotal ?? "-");
    }
    if (el.etaPerImageValue) {
      el.etaPerImageValue.textContent = fmtSeconds(data.estimatedSecondsPerImage);
    }
    if (el.etaWaitValue) {
      const source = data.queueSource ? ` (${data.queueSource})` : "";
      el.etaWaitValue.textContent = `${fmtSeconds(data.estimatedWaitSeconds)}${source}`;
    }
  }

  function applyDefaultInputs(defaults) {
    if (!defaults || typeof defaults !== "object") {
      return;
    }
    if (el.steps && !el.steps.value && defaults.steps !== undefined && defaults.steps !== null) {
      el.steps.value = String(defaults.steps);
    }
    if (el.cfg && !el.cfg.value && defaults.cfg !== undefined && defaults.cfg !== null) {
      el.cfg.value = String(defaults.cfg);
    }
    if (el.denoise && !el.denoise.value && defaults.denoise !== undefined && defaults.denoise !== null) {
      el.denoise.value = String(defaults.denoise);
    }
    if (el.seed && !el.seed.value && defaults.seed !== undefined && defaults.seed !== null) {
      el.seed.value = String(defaults.seed);
    }
    if (el.megapixels && !el.megapixels.value && defaults.megapixels !== undefined && defaults.megapixels !== null) {
      el.megapixels.value = String(defaults.megapixels);
    }
  }

  function populatePresetCategoryFilter(categories) {
    if (!el.presetCategoryFilter) {
      return;
    }
    const previous = String(el.presetCategoryFilter.value || "");
    el.presetCategoryFilter.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "All Categories";
    el.presetCategoryFilter.appendChild(allOption);
    categories.forEach((category) => {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      el.presetCategoryFilter.appendChild(option);
    });
    if (previous && categories.includes(previous)) {
      el.presetCategoryFilter.value = previous;
    }
  }

  function getFilteredPresets() {
    const selectedCategory = String(el.presetCategoryFilter && el.presetCategoryFilter.value ? el.presetCategoryFilter.value : "").trim().toLowerCase();
    if (!selectedCategory) {
      return state.presets.slice();
    }
    return state.presets.filter((preset) => {
      const category = String(preset.category || "").trim().toLowerCase();
      return category === selectedCategory;
    });
  }

  function populateStylePresetSelect(presets) {
    if (!el.stylePreset) {
      return;
    }
    const previous = String(el.stylePreset.value || "random");
    el.stylePreset.innerHTML = "";

    const randomOption = document.createElement("option");
    randomOption.value = "random";
    randomOption.textContent = "Random Style";
    el.stylePreset.appendChild(randomOption);

    presets.forEach((preset) => {
      const option = document.createElement("option");
      option.value = String(preset.id || "");
      option.textContent = `${preset.name || preset.id} (${preset.category || "uncategorized"})`;
      el.stylePreset.appendChild(option);
    });

    const values = new Set(Array.from(el.stylePreset.options).map((option) => option.value));
    el.stylePreset.value = values.has(previous) ? previous : "random";
  }

  function applyPresetFilter() {
    const filtered = getFilteredPresets();
    populateStylePresetSelect(filtered);
  }

  async function loadComfyPresets() {
    try {
      const payload = await fetchJson("/comfy/presets");
      const presets = Array.isArray(payload.presets) ? payload.presets : [];
      state.presets = presets;

      const categories = Array.from(new Set(
        presets
          .map((preset) => String((preset && preset.category) || "").trim())
          .filter((value) => value)
      )).sort();
      state.presetCategories = categories;
      populatePresetCategoryFilter(categories);
      applyPresetFilter();

      appendEvent(`Loaded ${presets.length} style presets.`, "info");
    } catch (err) {
      appendEvent(`Failed to load style presets: ${err.message || err}`, "error");
    }
  }

  async function loadComfyStatus() {
    try {
      const payload = await fetchJson("/api/comfy/staff/status");
      const backend = payload.backend || {};
      const estimate = payload.estimate || {};
      const configuredEngine = String(payload.configuredEngine || "stable_diffusion");

      if (el.engineBadge) {
        el.engineBadge.textContent = `configured engine: ${configuredEngine}`;
      }

      if (el.backendBadge) {
        const reachable = Boolean(backend.reachable);
        el.backendBadge.textContent = reachable ? "backend: reachable" : "backend: offline";
        el.backendBadge.classList.toggle("ok", reachable);
        el.backendBadge.classList.toggle("warn", !reachable);
      }

      if (el.workflowBadge) {
        const wf = backend.workflowPath || "workflow: unknown";
        el.workflowBadge.textContent = `workflow: ${wf}`;
      }

      applyDefaultInputs(payload.defaults || {});
      updateQueueEstimate(estimate);
      const presetsError = payload.presetsError || "";
      setStatusError(backend.error || estimate.queueError || presetsError || "-");
    } catch (err) {
      setStatusError(String(err && err.message ? err.message : err));
      appendEvent(`Status refresh failed: ${err.message || err}`, "error");
    }
  }

  function buildWsUrl() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.host}/ws`;
  }

  function scheduleWsReconnect() {
    if (state.wsRetryHandle) {
      window.clearTimeout(state.wsRetryHandle);
    }
    state.wsRetryHandle = window.setTimeout(connectWebSocket, 1500);
  }

  function handleGenerationComplete(payload) {
    const jobId = String(payload.jobId || "");
    if (!jobId) {
      return;
    }
    const presetMeta = getPresetMetaFromPayload(payload);
    if (presetMeta.stylePresetName || presetMeta.styleCategory) {
      setSelectedPresetMeta(presetMeta.stylePresetName, presetMeta.styleCategory);
    }
    if (state.currentJobId && state.currentJobId === jobId) {
      setCurrentJob(jobId, "completed");
      const outputUrl = payload.outputUrl ? `${payload.outputUrl}?t=${Date.now()}` : "";
      if (outputUrl && el.afterImage) {
        el.afterImage.src = outputUrl;
        el.afterImage.style.display = "block";
      }
      if (el.afterHint) {
        el.afterHint.textContent = outputUrl ? "Generated result ready" : "Output URL missing";
      }
      if (presetMeta.stylePresetName) {
        appendEvent(`Job ${jobId} completed with preset ${presetMeta.stylePresetName}.`, "info");
      } else {
        appendEvent(`Job ${jobId} completed.`, "info");
      }
    }
    loadComfyGallery();
  }

  function handleJobEvent(type, job) {
    if (!job || typeof job !== "object") {
      return;
    }
    if (!isComfyJob(job)) {
      return;
    }
    const jobId = String(job.jobId || "");
    if (state.currentJobId && jobId === state.currentJobId) {
      const status = String(job.status || "").toLowerCase() || type.replace("job_", "");
      setCurrentJob(jobId, status);
      if (type === "job_failed") {
        setStatusError(job.error || "Generation failed");
      }
    }
  }

  function handleSocketPayload(payload) {
    if (!payload || typeof payload !== "object") {
      return;
    }
    const type = String(payload.type || "");
    if (!type) {
      return;
    }

    if (type === "queue_updated") {
      appendEvent(`Queue updated (local): length=${payload.queueLength ?? "?"}`, "info");
      loadComfyStatus();
      return;
    }

    if (type === "generation_complete") {
      handleGenerationComplete(payload);
      return;
    }

    if (type === "generation_error") {
      if (state.currentJobId && String(payload.jobId || "") === state.currentJobId) {
        setCurrentJob(state.currentJobId, "failed");
      }
      setStatusError(payload.error || "Generation error");
      appendEvent(`Generation error for ${payload.jobId || "-"}: ${payload.error || "unknown"}`, "error");
      return;
    }

    if (type === "job_started" || type === "job_completed" || type === "job_failed" || type === "job_cancelled") {
      handleJobEvent(type, payload.job || {});
      const jobId = payload.job && payload.job.jobId ? payload.job.jobId : "-";
      appendEvent(`${type} (${jobId})`, type === "job_failed" ? "error" : "info");
      if (type === "job_completed" || type === "job_failed" || type === "job_cancelled") {
        loadComfyGallery();
      }
      loadComfyStatus();
      return;
    }

    if (type === "gallery_item_updated" || type === "gallery_item_deleted") {
      loadComfyGallery();
      return;
    }
  }

  function connectWebSocket() {
    try {
      if (state.ws) {
        state.ws.close();
        state.ws = null;
      }
      const ws = new WebSocket(buildWsUrl());
      state.ws = ws;

      ws.addEventListener("open", () => {
        setWsBadge(true);
        appendEvent("Live events connected.", "info");
      });

      ws.addEventListener("message", (evt) => {
        try {
          const payload = JSON.parse(evt.data);
          handleSocketPayload(payload);
        } catch (err) {
          appendEvent(`WS parse error: ${err.message || err}`, "warn");
        }
      });

      ws.addEventListener("close", () => {
        setWsBadge(false);
        appendEvent("Live events disconnected. Reconnecting...", "warn");
        scheduleWsReconnect();
      });

      ws.addEventListener("error", () => {
        setWsBadge(false);
      });
    } catch (err) {
      setWsBadge(false);
      appendEvent(`WebSocket failed: ${err.message || err}`, "error");
      scheduleWsReconnect();
    }
  }

  function createGalleryEmpty(text) {
    const box = document.createElement("div");
    box.className = "muted";
    box.textContent = text;
    return box;
  }

  async function renameGalleryItem(jobId, visitorName) {
    await fetchJson(`/gallery/item/${encodeURIComponent(jobId)}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visitorName })
    });
  }

  async function toggleGalleryHidden(jobId, hidden) {
    await fetchJson(`/gallery/item/${encodeURIComponent(jobId)}/visibility`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hidden: Boolean(hidden) })
    });
  }

  async function deleteGalleryItem(jobId) {
    await fetchJson(`/gallery/item/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  }

  function renderGallery(items) {
    if (!el.galleryList) {
      return;
    }
    el.galleryList.innerHTML = "";
    if (!items.length) {
      el.galleryList.appendChild(createGalleryEmpty("No ComfyUI gallery items yet."));
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "gallery-row";

      const thumbs = document.createElement("div");
      thumbs.className = "thumbs";
      const before = document.createElement("img");
      before.loading = "lazy";
      before.decoding = "async";
      before.alt = "Before";
      before.src = item.inputUrl || "";
      const after = document.createElement("img");
      after.loading = "lazy";
      after.decoding = "async";
      after.alt = "After";
      after.src = item.outputUrl || "";
      thumbs.appendChild(before);
      thumbs.appendChild(after);
      row.appendChild(thumbs);

      const body = document.createElement("div");
      const top = document.createElement("div");
      top.className = "row-top";
      const title = document.createElement("strong");
      title.textContent = item.jobId || "unknown-job";
      top.appendChild(title);

      const right = document.createElement("div");
      const hiddenPill = document.createElement("span");
      hiddenPill.className = "pill";
      hiddenPill.textContent = item.hidden ? "hidden" : "visible";
      right.appendChild(hiddenPill);
      const timePill = document.createElement("span");
      timePill.className = "pill";
      timePill.textContent = fmtTime(item.createdAt);
      right.appendChild(timePill);
      top.appendChild(right);
      body.appendChild(top);

      const nameLabel = document.createElement("label");
      nameLabel.textContent = "Visitor name";
      body.appendChild(nameLabel);

      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.value = item.visitorName || "Guest";
      body.appendChild(nameInput);

      const promptLine = document.createElement("p");
      promptLine.className = "muted";
      promptLine.style.marginTop = "8px";
      const promptUsed = item.promptUsed || item.prompt || "";
      promptLine.textContent = promptUsed ? `Prompt: ${promptUsed.slice(0, 180)}` : "Prompt: (workflow default)";
      body.appendChild(promptLine);

      const presetMeta = getPresetMetaFromPayload(item);
      const presetLine = document.createElement("p");
      presetLine.className = "muted";
      presetLine.textContent = presetMeta.stylePresetName
        ? `Preset: ${presetMeta.stylePresetName}${presetMeta.styleCategory ? ` (${presetMeta.styleCategory})` : ""}`
        : "Preset: random or not recorded";
      body.appendChild(presetLine);

      const actions = document.createElement("div");
      actions.className = "row-actions";
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "secondary";
      saveBtn.textContent = "Save Name";
      saveBtn.addEventListener("click", async () => {
        try {
          await renameGalleryItem(item.jobId, nameInput.value || "Guest");
          appendEvent(`Renamed ${item.jobId}.`, "info");
          await loadComfyGallery();
        } catch (err) {
          appendEvent(`Rename failed ${item.jobId}: ${err.message || err}`, "error");
        }
      });
      actions.appendChild(saveBtn);

      const hideBtn = document.createElement("button");
      hideBtn.type = "button";
      hideBtn.className = "secondary";
      hideBtn.textContent = item.hidden ? "Unhide" : "Hide";
      hideBtn.addEventListener("click", async () => {
        try {
          await toggleGalleryHidden(item.jobId, !item.hidden);
          appendEvent(`${item.hidden ? "Unhid" : "Hid"} ${item.jobId}.`, "info");
          await loadComfyGallery();
        } catch (err) {
          appendEvent(`Visibility update failed ${item.jobId}: ${err.message || err}`, "error");
        }
      });
      actions.appendChild(hideBtn);

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "danger";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", async () => {
        const confirmed = window.confirm(`Delete gallery item ${item.jobId}?`);
        if (!confirmed) {
          return;
        }
        try {
          await deleteGalleryItem(item.jobId);
          appendEvent(`Deleted ${item.jobId}.`, "warn");
          await loadComfyGallery();
        } catch (err) {
          appendEvent(`Delete failed ${item.jobId}: ${err.message || err}`, "error");
        }
      });
      actions.appendChild(deleteBtn);

      body.appendChild(actions);
      row.appendChild(body);
      el.galleryList.appendChild(row);
    });
  }

  async function loadComfyGallery() {
    try {
      const payload = await fetchJson("/gallery/items?includeHidden=true");
      const items = Array.isArray(payload.items) ? payload.items : [];
      const comfyItems = items.filter((item) => item && typeof item === "object" && isComfyJob(item));
      comfyItems.sort((a, b) => {
        const da = new Date(a.createdAt || 0).getTime();
        const db = new Date(b.createdAt || 0).getTime();
        return db - da;
      });
      state.galleryItems = comfyItems;
      if (el.galleryCountLabel) {
        el.galleryCountLabel.textContent = `items: ${comfyItems.length}`;
      }
      renderGallery(comfyItems.slice(0, 60));
    } catch (err) {
      appendEvent(`Failed to load gallery: ${err.message || err}`, "error");
      if (el.galleryList) {
        el.galleryList.innerHTML = "";
        el.galleryList.appendChild(createGalleryEmpty("Failed to load gallery."));
      }
    }
  }

  async function clearComfyGalleryItems() {
    const list = Array.isArray(state.galleryItems) ? state.galleryItems : [];
    if (!list.length) {
      appendEvent("No Comfy items to clear.", "warn");
      return;
    }
    const confirmed = window.confirm(`Delete ${list.length} Comfy gallery item(s)?`);
    if (!confirmed) {
      return;
    }
    let deletedCount = 0;
    for (const item of list) {
      try {
        await deleteGalleryItem(item.jobId);
        deletedCount += 1;
      } catch (err) {
        appendEvent(`Failed deleting ${item.jobId}: ${err.message || err}`, "error");
      }
    }
    appendEvent(`Cleared ${deletedCount}/${list.length} Comfy gallery item(s).`, "warn");
    await loadComfyGallery();
  }

  async function submitGenerateForm(event) {
    event.preventDefault();
    const file = el.imageFile && el.imageFile.files ? el.imageFile.files[0] : null;
    if (!file) {
      appendEvent("Select an input image first.", "warn");
      return;
    }

    updateBeforePreview(file);
    setCurrentJob("", "queueing");
    setStatusError("-");
    appendEvent("Queueing ComfyUI generation request...", "info");

    const formData = new FormData(el.generateForm);
    if (!formData.get("visitorName")) {
      formData.set("visitorName", "Staff");
    }
    const selectedStylePreset = String(el.stylePreset && el.stylePreset.value ? el.stylePreset.value : "random");
    formData.set("stylePreset", selectedStylePreset || "random");
    const selectedCategory = String(el.presetCategoryFilter && el.presetCategoryFilter.value ? el.presetCategoryFilter.value : "").trim();
    if (selectedCategory) {
      formData.set("styleCategory", selectedCategory);
    }
    if (selectedStylePreset && selectedStylePreset !== "random") {
      const selectedPreset = state.presets.find((preset) => String(preset.id || "") === selectedStylePreset);
      setSelectedPresetMeta(
        selectedPreset ? String(selectedPreset.name || selectedStylePreset) : selectedStylePreset,
        selectedPreset ? String(selectedPreset.category || "-") : (selectedCategory || "-")
      );
    } else {
      setSelectedPresetMeta("Random Style", selectedCategory || "-");
    }

    if (el.generateBtn) {
      el.generateBtn.disabled = true;
      el.generateBtn.textContent = "Queueing...";
    }

    try {
      const payload = await fetchJson("/api/comfy/staff/generate", {
        method: "POST",
        body: formData
      });
      const job = payload.job || {};
      const jobId = String(job.jobId || "");
      setCurrentJob(jobId, "queued");
      appendEvent(`Queued job ${jobId || "-"} with style preset ${selectedStylePreset}.`, "info");
      if (selectedStylePreset === "random") {
        setSelectedPresetMeta("Random Style", selectedCategory || "-");
      }
      updateQueueEstimate({
        queueRunning: payload.queueRunning ?? "-",
        queuePending: payload.queueLength ?? "-",
        queueTotal: payload.queueLength ?? "-",
        estimatedSecondsPerImage: payload.job ? payload.job.estimatedSeconds : null,
        estimatedWaitSeconds: payload.estimatedWaitSeconds
      });
      if (el.afterHint) {
        el.afterHint.textContent = "Job queued. Waiting for output...";
      }
      loadComfyStatus();
    } catch (err) {
      setCurrentJob("", "failed");
      setStatusError(err.message || String(err));
      appendEvent(`Generate request failed: ${err.message || err}`, "error");
    } finally {
      if (el.generateBtn) {
        el.generateBtn.disabled = false;
        el.generateBtn.textContent = "Queue Comfy Generation";
      }
    }
  }

  function bindEvents() {
    if (el.generateForm) {
      el.generateForm.addEventListener("submit", submitGenerateForm);
    }
    if (el.presetCategoryFilter) {
      el.presetCategoryFilter.addEventListener("change", () => {
        applyPresetFilter();
      });
    }
    if (el.stylePreset) {
      el.stylePreset.addEventListener("change", () => {
        const value = String(el.stylePreset.value || "random");
        if (value === "random") {
          setSelectedPresetMeta("Random Style", String(el.presetCategoryFilter && el.presetCategoryFilter.value ? el.presetCategoryFilter.value : "-"));
          return;
        }
        const selectedPreset = state.presets.find((preset) => String(preset.id || "") === value);
        setSelectedPresetMeta(
          selectedPreset ? String(selectedPreset.name || value) : value,
          selectedPreset ? String(selectedPreset.category || "-") : "-"
        );
      });
    }
    if (el.refreshStatusBtn) {
      el.refreshStatusBtn.addEventListener("click", () => {
        loadComfyStatus();
      });
    }
    if (el.refreshGalleryBtn) {
      el.refreshGalleryBtn.addEventListener("click", () => {
        loadComfyGallery();
      });
    }
    if (el.clearComfyBtn) {
      el.clearComfyBtn.addEventListener("click", () => {
        clearComfyGalleryItems();
      });
    }
    if (el.imageFile) {
      el.imageFile.addEventListener("change", () => {
        const file = el.imageFile.files && el.imageFile.files[0] ? el.imageFile.files[0] : null;
        if (file) {
          updateBeforePreview(file);
        }
      });
    }
  }

  async function init() {
    bindEvents();
    setWsBadge(false);
    setSelectedPresetMeta("Random Style", "-");
    connectWebSocket();
    await loadComfyPresets();
    await loadComfyStatus();
    await loadComfyGallery();
    window.setInterval(() => {
      loadComfyStatus();
    }, 5000);
  }

  init();
})();
