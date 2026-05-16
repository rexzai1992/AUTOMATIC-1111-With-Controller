const galleryGrid = document.getElementById("galleryGrid");

const FEEDBACK_TAGS = [
  "too_close_to_drawing",
  "changed_too_much",
  "not_lively_enough",
  "too_realistic",
  "too_cartoon",
  "bad_face",
  "bad_hands",
  "bad_colors",
  "too_dark",
  "too_empty",
  "good_preserve_shape",
  "good_lively",
  "good_colors",
  "good_overall"
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

function createTagCheckboxes(container, selectedTags) {
  const selected = new Set(Array.isArray(selectedTags) ? selectedTags : []);
  container.innerHTML = "";
  FEEDBACK_TAGS.forEach((tag) => {
    const label = document.createElement("label");
    label.className = "mini-tag";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = tag;
    checkbox.checked = selected.has(tag);

    const text = document.createElement("span");
    text.textContent = tag;

    label.appendChild(checkbox);
    label.appendChild(text);
    container.appendChild(label);
  });
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

  const image = document.createElement("img");
  image.src = `${item.outputUrl}?t=${Date.now()}`;
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
  ratingLine.textContent = item.rating ? `Rating: ${item.rating}/5` : "Rating: not rated";
  meta.appendChild(ratingLine);

  const actionsRow = document.createElement("div");
  actionsRow.className = "card-actions";
  const rateButton = document.createElement("button");
  rateButton.type = "button";
  rateButton.className = "rate-btn";
  rateButton.textContent = "Rate";
  actionsRow.appendChild(rateButton);
  meta.appendChild(actionsRow);

  const panel = document.createElement("div");
  panel.className = "mini-rating-panel";
  panel.hidden = true;

  const ratingLabel = document.createElement("label");
  ratingLabel.textContent = "Rating";
  const ratingSelect = document.createElement("select");
  ratingSelect.innerHTML = `
    <option value="">Select</option>
    <option value="1">1</option>
    <option value="2">2</option>
    <option value="3">3</option>
    <option value="4">4</option>
    <option value="5">5</option>
  `;
  if (item.rating) {
    ratingSelect.value = String(item.rating);
  }
  panel.appendChild(ratingLabel);
  panel.appendChild(ratingSelect);

  const tagsContainer = document.createElement("div");
  tagsContainer.className = "mini-tags-grid";
  createTagCheckboxes(tagsContainer, item.feedbackTags || []);
  panel.appendChild(tagsContainer);

  const noteInput = document.createElement("textarea");
  noteInput.rows = 2;
  noteInput.placeholder = "Optional feedback note";
  noteInput.value = item.feedbackNote || "";
  panel.appendChild(noteInput);

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "save-mini-rating-btn";
  saveBtn.textContent = "Save";
  panel.appendChild(saveBtn);

  const panelStatus = document.createElement("p");
  panelStatus.className = "mini-panel-status";
  panelStatus.textContent = item.ratedAt ? `Saved ${formatTime(item.ratedAt)}` : "";
  panel.appendChild(panelStatus);

  rateButton.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
  });

  saveBtn.addEventListener("click", async () => {
    const numericRating = Number(ratingSelect.value);
    if (!Number.isInteger(numericRating) || numericRating < 1 || numericRating > 5) {
      panelStatus.textContent = "Choose rating 1-5.";
      return;
    }

    saveBtn.disabled = true;
    panelStatus.textContent = "Saving...";
    try {
      const response = await fetch(`/gallery/rate/${item.jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating: numericRating,
          feedbackTags: getSelectedTags(tagsContainer),
          feedbackNote: noteInput.value.trim()
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to save rating.");
      }
      item.rating = data.rating;
      item.feedbackTags = data.feedbackTags;
      item.feedbackNote = data.feedbackNote;
      item.ratedAt = data.ratedAt;
      ratingLine.textContent = `Rating: ${data.rating}/5`;
      panelStatus.textContent = `Saved ${formatTime(data.ratedAt)}`;
    } catch (error) {
      panelStatus.textContent = error.message;
    } finally {
      saveBtn.disabled = false;
    }
  });

  meta.appendChild(panel);
  card.appendChild(meta);
  return card;
}

function upsertItem(item) {
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
  if (existing) {
    existing.remove();
  }

  const card = createCard(item);
  const emptyState = galleryGrid.querySelector(".empty-state");
  if (emptyState) {
    emptyState.remove();
  }
  galleryGrid.prepend(card);
}

async function loadGallery() {
  try {
    const response = await fetch("/gallery/items");
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

  ws.onclose = () => setTimeout(connectWebSocket, 1500);
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "generation_complete") {
        upsertItem(payload);
      } else if (payload.type === "gallery_item_updated" && payload.item) {
        upsertItem(payload.item);
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

loadGallery();
connectWebSocket();
