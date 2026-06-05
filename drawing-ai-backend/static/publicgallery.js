const PUBLIC_GALLERY_POLL_MS = 15000;

const FINAL_STATUSES = new Set(["generated", "shown", "completed", "complete"]);
const ACTIVE_STATUSES = new Set(["pending", "queued", "processing", "generating", "active"]);
const BLOCKED_STATUSES = new Set(["failed", "hidden", "cancelled", "error"]);

const grid = document.getElementById("publicGalleryGrid");
const emptyState = document.getElementById("publicGalleryEmpty");
const modal = document.getElementById("previewModal");
const previewImage = document.getElementById("previewImage");
const previewTitle = document.getElementById("previewTitle");
const previewMeta = document.getElementById("previewMeta");

const state = {
  items: [],
  itemMap: new Map(),
  ws: null,
  reconnectTimer: null,
  pollTimer: null,
};

function safeText(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function safeUrl(...values) {
  for (const value of values) {
    const text = safeText(value);
    if (!text) {
      continue;
    }
    if (text.startsWith("/") || /^https?:\/\//i.test(text)) {
      return text;
    }
  }
  return "";
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toLocaleDateString();
}

function toTimeMs(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 0;
  }
  return parsed.getTime();
}

function normalizedStatus(raw) {
  if (raw && raw.hidden === true) {
    return "hidden";
  }
  const status = safeText(raw?.status).toLowerCase();
  if (status.includes("fail")) {
    return "failed";
  }
  if (status.includes("cancel")) {
    return "cancelled";
  }
  if (status.includes("hidden")) {
    return "hidden";
  }
  if (status.includes("queue")) {
    return "queued";
  }
  if (status.includes("process")) {
    return "processing";
  }
  if (status.includes("generat") && !status.includes("generated")) {
    return "generating";
  }
  if (FINAL_STATUSES.has(status)) {
    return status;
  }
  if (ACTIVE_STATUSES.has(status)) {
    return status;
  }
  if (safeText(raw?.generationError) || safeText(raw?.error)) {
    return "failed";
  }
  if (safeUrl(raw?.generatedImageUrl, raw?.outputUrl)) {
    return "completed";
  }
  return status || "unknown";
}

function normalizeRecord(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }

  const id = safeText(raw.jobId || raw.id || raw.submissionId || raw.submission_id);
  if (!id) {
    return null;
  }

  const status = normalizedStatus(raw);
  if (BLOCKED_STATUSES.has(status)) {
    return null;
  }
  if (ACTIVE_STATUSES.has(status)) {
    return null;
  }

  const generatedImageUrl = safeUrl(
    raw.generatedImageUrl,
    raw.generated_image_url,
    raw.outputUrl,
  );

  const fallbackImageUrl = safeUrl(
    raw.imageUrl,
    raw.image_url,
  );

  let imageUrl = generatedImageUrl;
  if (!imageUrl) {
    const completedLike = FINAL_STATUSES.has(status) || status === "completed" || status === "shown" || status === "unknown";
    if (completedLike) {
      imageUrl = fallbackImageUrl;
    }
  }

  if (!imageUrl) {
    return null;
  }

  const name = safeText(
    raw.visitorName
      || raw.studentName
      || raw.customerName
      || raw.customer_name
      || raw.name,
    "Customer",
  );

  const createdAt = safeText(
    raw.createdAt
      || raw.created_at
      || raw.completedAt
      || raw.completed_at
      || raw.updatedAt,
  );

  return {
    id,
    name,
    createdAt,
    timeMs: toTimeMs(createdAt),
    dateLabel: formatDate(createdAt),
    imageUrl,
  };
}

function compareByTimeDesc(a, b) {
  return (b.timeMs || 0) - (a.timeMs || 0);
}

function renderGallery() {
  const items = [...state.items].sort(compareByTimeDesc);
  state.items = items;

  if (items.length === 0) {
    grid.replaceChildren();
    emptyState.hidden = false;
    return;
  }

  emptyState.hidden = true;
  const fragment = document.createDocumentFragment();

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "public-gallery-card";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "public-gallery-btn";
    button.dataset.id = item.id;

    const image = document.createElement("img");
    image.className = "public-gallery-image";
    image.loading = "lazy";
    image.decoding = "async";
    image.src = item.imageUrl;
    image.alt = `Generated Drawing by ${item.name}`;

    const meta = document.createElement("div");
    meta.className = "public-gallery-meta";

    const name = document.createElement("p");
    name.className = "public-gallery-name";
    name.textContent = item.name;

    const date = document.createElement("p");
    date.className = "public-gallery-date";
    date.textContent = item.dateLabel ? `Created ${item.dateLabel}` : "Created recently";

    meta.appendChild(name);
    meta.appendChild(date);

    button.appendChild(image);
    button.appendChild(meta);
    card.appendChild(button);

    const printButton = document.createElement("button");
    printButton.type = "button";
    printButton.className = "public-gallery-print-btn";
    printButton.dataset.id = item.id;
    printButton.textContent = "Print 4x6";
    card.appendChild(printButton);
    fragment.appendChild(card);
  });

  grid.replaceChildren(fragment);
}

function openPreview(itemId) {
  const item = state.itemMap.get(itemId);
  if (!item) {
    return;
  }
  previewImage.src = item.imageUrl;
  previewImage.alt = `Generated Drawing by ${item.name}`;
  previewTitle.textContent = "Generated Drawing";
  previewMeta.textContent = item.dateLabel
    ? `${item.name} · ${item.dateLabel}`
    : item.name;
  modal.hidden = false;
}

function closePreview() {
  modal.hidden = true;
}

async function createPhotoPrint(itemId, trigger) {
  const jobId = safeText(itemId);
  if (!jobId) {
    window.alert("Job not found");
    return;
  }

  const printWindow = window.open("", "_blank");
  if (trigger) {
    trigger.disabled = true;
    trigger.textContent = "Creating...";
  }

  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/create-photo`, {
      method: "POST",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(payload.detail || payload.message || "Unable to create 4x6 photo."));
    }
    const photoUrl = safeUrl(payload.photoPrintUrl);
    if (!photoUrl) {
      throw new Error("Photo print URL missing.");
    }
    const cacheBustUrl = `${photoUrl}${photoUrl.includes("?") ? "&" : "?"}v=${Date.now()}`;
    if (printWindow) {
      printWindow.location.href = cacheBustUrl;
    } else {
      window.open(cacheBustUrl, "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    if (printWindow) {
      printWindow.close();
    }
    window.alert(error?.message || "Unable to create 4x6 photo.");
  } finally {
    if (trigger) {
      trigger.disabled = false;
      trigger.textContent = "Print 4x6";
    }
  }
}

function applyRecords(rawItems) {
  const nextMap = new Map();

  (Array.isArray(rawItems) ? rawItems : []).forEach((raw) => {
    const item = normalizeRecord(raw);
    if (!item) {
      return;
    }
    nextMap.set(item.id, item);
  });

  const nextItems = Array.from(nextMap.values()).sort(compareByTimeDesc);
  state.itemMap = nextMap;
  state.items = nextItems;
  renderGallery();
}

async function fetchGallery() {
  const response = await fetch(`/api/gallery?limit=260&offset=0`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Gallery request failed (${response.status})`);
  }
  const payload = await response.json();
  return Array.isArray(payload.items) ? payload.items : [];
}

async function refreshGallery() {
  const items = await fetchGallery();
  applyRecords(items);
}

function upsertFromRealtime(raw) {
  const item = normalizeRecord(raw);
  const id = safeText(raw?.jobId || raw?.id);

  if (!item) {
    if (id && state.itemMap.has(id)) {
      state.itemMap.delete(id);
      state.items = Array.from(state.itemMap.values()).sort(compareByTimeDesc);
      renderGallery();
    }
    return;
  }

  state.itemMap.set(item.id, item);
  state.items = Array.from(state.itemMap.values()).sort(compareByTimeDesc);
  renderGallery();
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  state.ws = ws;

  ws.onclose = () => {
    state.ws = null;
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
    }
    state.reconnectTimer = setTimeout(connectWebSocket, 3000);
  };

  ws.onmessage = (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    if (!payload || typeof payload !== "object") {
      return;
    }

    if (payload.type === "generation_complete") {
      upsertFromRealtime(payload);
      return;
    }

    if (payload.type === "gallery_item_updated" && payload.item) {
      upsertFromRealtime(payload.item);
      return;
    }

    if (payload.type === "gallery_item_deleted" && payload.jobId) {
      const jobId = safeText(payload.jobId);
      if (jobId && state.itemMap.has(jobId)) {
        state.itemMap.delete(jobId);
        state.items = Array.from(state.itemMap.values()).sort(compareByTimeDesc);
        renderGallery();
      }
    }
  };
}

function setupInteractions() {
  grid.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const printButton = target.closest(".public-gallery-print-btn");
    if (printButton) {
      event.preventDefault();
      event.stopPropagation();
      void createPhotoPrint(printButton.dataset.id, printButton);
      return;
    }

    const button = target.closest(".public-gallery-btn");
    if (!button) {
      return;
    }
    const itemId = safeText(button.dataset.id);
    if (!itemId) {
      return;
    }
    openPreview(itemId);
  });

  modal.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.dataset.closeModal === "true") {
      closePreview();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      closePreview();
    }
  });
}

async function initializePublicGallery() {
  setupInteractions();
  await refreshGallery();
  connectWebSocket();
  state.pollTimer = setInterval(() => {
    refreshGallery().catch(() => {
      // Ignore transient network errors.
    });
  }, PUBLIC_GALLERY_POLL_MS);
}

initializePublicGallery().catch(() => {
  applyRecords([]);
});
