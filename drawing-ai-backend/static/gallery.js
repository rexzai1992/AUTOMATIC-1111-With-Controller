const galleryGrid = document.getElementById("galleryGrid");
const wsStatusBadge = document.getElementById("wsStatusBadge");
const GALLERY_MAX_ITEMS = 60;
let lastGalleryLoadMs = 0;

const BAD_FEEDBACK_TAG_GROUPS = [
  {
    title: "Quick bad tags",
    tags: [
      { id: "wrong_subject", label: "Wrong subject" },
      { id: "same_as_input", label: "Same as input" },
      { id: "person_missing", label: "Person missing" },
      { id: "person_unrecognizable", label: "Person unrecognizable" },
      { id: "face_identity_changed", label: "Face identity changed" },
      { id: "gender_changed", label: "Gender changed" },
      { id: "clothing_changed", label: "Clothing changed" },
      { id: "shirt_changed", label: "Shirt changed" },
      { id: "outfit_changed", label: "Outfit changed" },
      { id: "main_object_missing", label: "Main object missing" },
      { id: "creation_unrecognizable", label: "Creation unrecognizable" },
      { id: "wrong_composition", label: "Wrong composition" },
      { id: "too_empty", label: "Too empty" },
      { id: "bad_colors", label: "Bad colors" },
      { id: "low_quality", label: "Low quality" },
      { id: "over_changed", label: "Over changed" },
      { id: "too_realistic", label: "Too realistic" },
      { id: "scary_or_creepy", label: "Scary or creepy" }
    ]
  },
  {
    title: "Legacy / detailed tags",
    tags: [
      { id: "wrong_generation", label: "Wrong generation (legacy)" },
      { id: "person_changed", label: "Person changed" },
      { id: "face_changed", label: "Face changed" },
      { id: "artwork_missing", label: "Artwork missing" },
      { id: "artwork_changed", label: "Artwork changed" },
      { id: "object_missing", label: "Object missing" },
      { id: "object_changed", label: "Object changed" },
      { id: "background_wrong", label: "Background wrong" },
      { id: "background_not_changed", label: "Background not changed" },
      { id: "background_too_plain", label: "Background too plain" },
      { id: "composition_wrong", label: "Composition wrong (legacy)" },
      { id: "too_much_change", label: "Too much change" }
    ]
  },
  {
    title: "Style and artifact tags",
    tags: [
      { id: "style_wrong", label: "Style wrong" },
      { id: "style_too_weak", label: "Style too weak" },
      { id: "not_lively_enough", label: "Not lively enough" },
      { id: "changed_too_much", label: "Changed too much (legacy)" },
      { id: "too_cartoon", label: "Too cartoon" }
    ]
  },
  {
    title: "Quality problems",
    tags: [
      { id: "too_messy", label: "Too messy" },
      { id: "bad_face", label: "Bad face" },
      { id: "bad_hands", label: "Bad hands" },
      { id: "blurry", label: "Blurry" },
      { id: "creepy", label: "Creepy (legacy)" },
      { id: "text_or_watermark", label: "Text or watermark" }
    ]
  },
  {
    title: "Color / lighting problems",
    tags: [
      { id: "bad_colors", label: "Bad colors" },
      { id: "too_dark", label: "Too dark" }
    ]
  }
];

const GOOD_FEEDBACK_TAGS = [
  { id: "good_preserve_shape", label: "Good preserve shape" },
  { id: "good_preserve_person", label: "Good preserve person" },
  { id: "good_preserve_artwork", label: "Good preserve artwork" },
  { id: "good_preserve_identity", label: "Good preserve identity" },
  { id: "good_preserve_clothing", label: "Good preserve clothing" },
  { id: "good_preserve_creation", label: "Good preserve creation" },
  { id: "good_background_change", label: "Good background change" },
  { id: "good_style_change", label: "Good style change" },
  { id: "style_good_identity_good", label: "Style + identity good" },
  { id: "good_lively", label: "Good lively" },
  { id: "good_colors", label: "Good colors" },
  { id: "good_style", label: "Good style" },
  { id: "good_overall", label: "Good overall" }
];

function formatTime(isoString) {
  if (!isoString) {
    return "-";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
}

function renderEmptyState() {
  galleryGrid.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = "Waiting for the first generated artwork...";
  galleryGrid.appendChild(empty);
}

function setWsStatus(connected) {
  if (!wsStatusBadge) {
    return;
  }
  if (connected) {
    wsStatusBadge.textContent = "Connected";
    wsStatusBadge.classList.remove("reconnecting");
    wsStatusBadge.classList.add("connected");
  } else {
    wsStatusBadge.textContent = "Reconnecting";
    wsStatusBadge.classList.remove("connected");
    wsStatusBadge.classList.add("reconnecting");
  }
}

function createTagCheckboxes(container, selectedTags) {
  const selected = new Set(Array.isArray(selectedTags) ? selectedTags : []);
  container.innerHTML = "";

  const createGroup = (title, tags, variant) => {
    const section = document.createElement("section");
    section.className = "mini-tag-category";

    const heading = document.createElement("p");
    heading.className = "mini-tag-category-title";
    heading.textContent = title;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "mini-tags-grid";

    tags.forEach((tagMeta) => {
      const label = document.createElement("label");
      label.className = `mini-tag ${variant}`;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = tagMeta.id;
      checkbox.checked = selected.has(tagMeta.id);

      const text = document.createElement("span");
      text.textContent = tagMeta.label;

      label.appendChild(checkbox);
      label.appendChild(text);
      grid.appendChild(label);
    });

    section.appendChild(grid);
    container.appendChild(section);
  };

  BAD_FEEDBACK_TAG_GROUPS.forEach((group) => {
    createGroup(group.title, group.tags, "bad");
  });
  createGroup("Good feedback tags", GOOD_FEEDBACK_TAGS, "good");
}

function getSelectedTags(container) {
  const tags = [];
  container.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    if (checkbox.checked) {
      tags.push(checkbox.value);
    }
  });
  return tags;
}

function createCard(item) {
  const card = document.createElement("article");
  card.className = "gallery-card";
  card.dataset.jobId = item.jobId || "";
  const cacheKey = encodeURIComponent(String(item.updatedAt || item.completedAt || item.createdAt || ""));

  const image = document.createElement("img");
  image.loading = "lazy";
  image.decoding = "async";
  image.src = cacheKey ? `${item.outputUrl}?v=${cacheKey}` : `${item.outputUrl}`;
  image.alt = `Generated drawing by ${item.visitorName || "Guest"}`;
  card.appendChild(image);

  const meta = document.createElement("div");
  meta.className = "meta";

  const visitor = document.createElement("p");
  visitor.className = "visitor";
  visitor.textContent = item.visitorName || "Guest";
  meta.appendChild(visitor);

  const time = document.createElement("p");
  time.className = "time";
  time.textContent = formatTime(item.createdAt);
  meta.appendChild(time);

  const ratingLine = document.createElement("p");
  ratingLine.className = "rating-line";
  const displayRating = Number(item.staffRating ?? item.rating ?? item.autoRating ?? 0);
  ratingLine.textContent = Number.isInteger(displayRating) && displayRating >= 1 && displayRating <= 5
    ? `Auto rating: ${displayRating}/5`
    : "Auto rating: unavailable";
  meta.appendChild(ratingLine);

  const actionsRow = document.createElement("div");
  actionsRow.className = "card-actions";
  const rateButton = document.createElement("button");
  rateButton.type = "button";
  rateButton.className = "rate-btn";
  rateButton.textContent = "Rate";
  rateButton.hidden = true;
  actionsRow.appendChild(rateButton);

  const previewWrap = document.createElement("div");
  previewWrap.className = "before-after-wrap";

  const previewButton = document.createElement("button");
  previewButton.type = "button";
  previewButton.className = "before-after-btn";
  previewButton.textContent = "Before/After";
  previewWrap.appendChild(previewButton);

  const previewPanel = document.createElement("div");
  previewPanel.className = "before-after-popover";
  previewPanel.hidden = true;

  const previewGrid = document.createElement("div");
  previewGrid.className = "before-after-grid";
  let previewImagesLoaded = false;

  const beforeCard = document.createElement("div");
  beforeCard.className = "before-after-card";
  const beforeLabel = document.createElement("p");
  beforeLabel.className = "before-after-label";
  beforeLabel.textContent = "Before";
  beforeCard.appendChild(beforeLabel);
  const beforeSlot = document.createElement("div");
  beforeSlot.className = "before-after-slot";
  beforeCard.appendChild(beforeSlot);
  previewGrid.appendChild(beforeCard);

  const afterCard = document.createElement("div");
  afterCard.className = "before-after-card";
  const afterLabel = document.createElement("p");
  afterLabel.className = "before-after-label";
  afterLabel.textContent = "After";
  afterCard.appendChild(afterLabel);
  const afterSlot = document.createElement("div");
  afterSlot.className = "before-after-slot";
  afterCard.appendChild(afterSlot);
  previewGrid.appendChild(afterCard);

  previewPanel.appendChild(previewGrid);
  previewWrap.appendChild(previewPanel);
  actionsRow.appendChild(previewWrap);

  const photoButton = document.createElement("button");
  photoButton.type = "button";
  photoButton.className = "photo-print-btn";
  photoButton.textContent = "Print 4x6";
  actionsRow.appendChild(photoButton);

  meta.appendChild(actionsRow);

  let hidePreviewTimer = null;
  const loadPreviewImages = () => {
    if (previewImagesLoaded) {
      return;
    }
    previewImagesLoaded = true;
    if (item.inputUrl) {
      const beforeImage = document.createElement("img");
      beforeImage.loading = "lazy";
      beforeImage.decoding = "async";
      beforeImage.src = cacheKey ? `${item.inputUrl}?v=${cacheKey}` : `${item.inputUrl}`;
      beforeImage.alt = `Before drawing by ${item.visitorName || "Guest"}`;
      beforeSlot.replaceChildren(beforeImage);
    } else {
      const beforeEmpty = document.createElement("p");
      beforeEmpty.className = "before-after-empty";
      beforeEmpty.textContent = "Before image not available";
      beforeSlot.replaceChildren(beforeEmpty);
    }

    if (item.outputUrl) {
      const afterImage = document.createElement("img");
      afterImage.loading = "lazy";
      afterImage.decoding = "async";
      afterImage.src = cacheKey ? `${item.outputUrl}?v=${cacheKey}` : `${item.outputUrl}`;
      afterImage.alt = `Generated artwork by ${item.visitorName || "Guest"}`;
      afterSlot.replaceChildren(afterImage);
    } else {
      const afterEmpty = document.createElement("p");
      afterEmpty.className = "before-after-empty";
      afterEmpty.textContent = "After image not available";
      afterSlot.replaceChildren(afterEmpty);
    }
  };

  const showPreview = () => {
    if (hidePreviewTimer) {
      clearTimeout(hidePreviewTimer);
      hidePreviewTimer = null;
    }
    loadPreviewImages();
    previewPanel.hidden = false;
    previewWrap.classList.add("is-open");
  };

  const hidePreview = () => {
    hidePreviewTimer = setTimeout(() => {
      previewPanel.hidden = true;
      previewWrap.classList.remove("is-open");
    }, 90);
  };

  previewWrap.addEventListener("mouseenter", showPreview);
  previewWrap.addEventListener("mouseleave", hidePreview);
  previewButton.addEventListener("focus", showPreview);
  previewButton.addEventListener("blur", hidePreview);
  photoButton.addEventListener("click", async () => {
    const jobId = String(item.jobId || "").trim();
    if (!jobId) {
      window.alert("Job not found");
      return;
    }

    const printWindow = window.open("", "_blank");
    photoButton.disabled = true;
    photoButton.textContent = "Creating...";
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/create-photo`, {
        method: "POST"
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.detail || payload.message || "Unable to create 4x6 photo."));
      }

      const photoUrl = String(payload.photoPrintUrl || "").trim();
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
      photoButton.disabled = false;
      photoButton.textContent = "Print 4x6";
    }
  });
  card.appendChild(meta);
  return card;
}

function upsertItem(item, options = {}) {
  const preservePosition = Boolean(options.preservePosition);

  if (item.hidden) {
    const toRemove = galleryGrid.querySelector(`[data-job-id="${item.jobId}"]`);
    if (toRemove) {
      toRemove.remove();
    }
    if (!galleryGrid.querySelector(".gallery-card")) {
      renderEmptyState();
    }
    return;
  }

  const existing = galleryGrid.querySelector(`[data-job-id="${item.jobId}"]`);
  const emptyState = galleryGrid.querySelector(".empty-state");
  if (emptyState) {
    emptyState.remove();
  }

  const card = createCard(item);

  if (existing && preservePosition) {
    const parent = existing.parentElement || galleryGrid;
    const next = existing.nextSibling;
    existing.remove();
    if (next) {
      parent.insertBefore(card, next);
    } else {
      parent.appendChild(card);
    }
    return;
  }

  if (existing) {
    existing.remove();
  }
  galleryGrid.prepend(card);
  const cards = galleryGrid.querySelectorAll(".gallery-card");
  if (cards.length > GALLERY_MAX_ITEMS) {
    cards[cards.length - 1].remove();
  }
}

async function loadGallery() {
  lastGalleryLoadMs = Date.now();
  try {
    const response = await fetch(`/api/gallery?limit=${GALLERY_MAX_ITEMS}`);
    const data = await response.json();
    const items = Array.isArray(data.items) ? data.items : [];
    if (items.length === 0) {
      renderEmptyState();
      return;
    }
    galleryGrid.innerHTML = "";
    items.forEach((item) => {
      galleryGrid.appendChild(createCard(item));
    });
  } catch (error) {
    renderEmptyState();
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  ws.onopen = async () => {
    setWsStatus(true);
    if (Date.now() - lastGalleryLoadMs > 5000) {
      await loadGallery();
    }
  };

  ws.onclose = () => {
    setWsStatus(false);
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => {
    setWsStatus(false);
  };

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "generation_complete") {
        upsertItem(payload);
      } else if (payload.type === "gallery_item_updated" && payload.item) {
        upsertItem(payload.item, { preservePosition: true });
      } else if (payload.type === "gallery_item_deleted" && payload.jobId) {
        const existing = galleryGrid.querySelector(`[data-job-id="${payload.jobId}"]`);
        if (existing) {
          existing.remove();
        }
        if (!galleryGrid.querySelector(".gallery-card")) {
          renderEmptyState();
        }
      }
    } catch (error) {
      // Ignore malformed payload.
    }
  };
}

setWsStatus(false);
loadGallery();
connectWebSocket();
