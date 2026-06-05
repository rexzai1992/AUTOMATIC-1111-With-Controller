const searchInput = document.getElementById("searchInput");
const statusSelect = document.getElementById("statusSelect");
const refreshBtn = document.getElementById("refreshBtn");
const errorText = document.getElementById("errorText");
const summaryBox = document.getElementById("summaryBox");
const listContainer = document.getElementById("listContainer");

const params = new URLSearchParams(window.location.search);
const apiKey = String(params.get("apiKey") || "").trim();

let loading = false;

function setError(message) {
  const text = String(message || "").trim();
  if (!text) {
    errorText.hidden = true;
    errorText.textContent = "";
    return;
  }
  errorText.hidden = false;
  errorText.textContent = text;
}

function statusClass(status) {
  const normalized = String(status || "").trim().toLowerCase();
  return `status-${normalized}`;
}

function withApiKey(url) {
  const next = new URL(url, window.location.origin);
  if (apiKey) {
    next.searchParams.set("apiKey", apiKey);
  }
  return next.toString();
}

function renderSummary(payload) {
  const counts = payload?.statusCounts || {};
  const queue = payload?.queueMonitoring || {};
  const cards = [
    ["pending", Number(counts.pending || 0)],
    ["queued", Number(counts.queued || 0)],
    ["processing", Number(counts.processing || 0)],
    ["completed", Number(counts.completed || 0)],
    ["failed", Number(counts.failed || 0)],
    ["global queue", Number(queue.globalQueueLength || 0)],
    ["wonderpark queue", Number(queue.wonderparkQueueLength || 0)],
  ];

  summaryBox.innerHTML = `<div class="summary-grid">${cards
    .map(([label, value]) => `<article class="summary-card"><span>${label}</span><strong>${value}</strong></article>`)
    .join("")}</div>`;
}

function renderList(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (items.length === 0) {
    listContainer.innerHTML = "<p>No submissions found.</p>";
    return;
  }

  const rows = items.map((row) => {
    const id = String(row.submission_id || "");
    const status = String(row.processing_status || "pending");
    const name = String(row.customer_name || "-");
    const created = String(row.created_at || "-");
    const uploaded = String(row.uploaded_image_url || "");
    const thumb = String(row.thumbnail_url || uploaded || "");
    const generated = String(row.generated_image_url || "");
    const originalFilename = String(row.original_filename || "artwork.png");
    const retryCount = Number(row.retry_count || 0);
    const error = String(row.error || "");

    const previewHref = thumb ? thumb : uploaded;
    const generatedLink = generated ? `<a href="${generated}" target="_blank" rel="noopener noreferrer">Generated</a>` : "-";
    const downloadUrl = withApiKey(`/api/admin/wonderpark/submissions/${encodeURIComponent(id)}/download`);

    return `
      <tr>
        <td>
          <div><strong>${id}</strong></div>
          <div>${created}</div>
        </td>
        <td>${name}</td>
        <td><span class="status-pill ${statusClass(status)}">${status}</span></td>
        <td>
          ${previewHref ? `<a href="${previewHref}" target="_blank" rel="noopener noreferrer"><img src="${previewHref}" alt="uploaded artwork"></a>` : "-"}
        </td>
        <td>${generatedLink}</td>
        <td>
          <div>${originalFilename}</div>
          <div>retry=${retryCount}</div>
          ${error ? `<div class="error">${error}</div>` : ""}
        </td>
        <td>
          <div class="row-actions">
            ${previewHref ? `<a href="${previewHref}" target="_blank" rel="noopener noreferrer">Preview</a>` : ""}
            <a href="${downloadUrl}" target="_blank" rel="noopener noreferrer">Download</a>
            <button type="button" data-action="retry" data-id="${id}">Retry</button>
            <button type="button" class="action-danger" data-action="delete" data-id="${id}">Delete</button>
          </div>
        </td>
      </tr>`;
  }).join("");

  listContainer.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Submission</th>
          <th>Name</th>
          <th>Status</th>
          <th>Uploaded Artwork</th>
          <th>Generated</th>
          <th>Info</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function loadSubmissions() {
  if (loading) {
    return;
  }
  loading = true;
  setError("");

  try {
    const query = new URLSearchParams();
    const search = String(searchInput.value || "").trim();
    const status = String(statusSelect.value || "").trim();
    if (search) {
      query.set("search", search);
    }
    if (status) {
      query.set("status", status);
    }
    query.set("limit", "200");
    if (apiKey) {
      query.set("apiKey", apiKey);
    }

    const response = await fetch(`/api/admin/wonderpark/submissions?${query.toString()}`, {
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail || "Failed to load submissions.");
    }

    renderSummary(payload);
    renderList(payload);
  } catch (error) {
    setError(error?.message || "Failed to load submissions.");
  } finally {
    loading = false;
  }
}

async function retrySubmission(submissionId) {
  const url = withApiKey(`/api/admin/wonderpark/submissions/${encodeURIComponent(submissionId)}/retry`);
  const response = await fetch(url, { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.detail || "Retry failed.");
  }
}

async function deleteSubmission(submissionId) {
  const url = withApiKey(`/api/admin/wonderpark/submissions/${encodeURIComponent(submissionId)}`);
  const response = await fetch(url, { method: "DELETE" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.detail || "Delete failed.");
  }
}

listContainer.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const action = target.getAttribute("data-action");
  const id = target.getAttribute("data-id");
  if (!action || !id) {
    return;
  }

  try {
    setError("");
    if (action === "retry") {
      target.setAttribute("disabled", "disabled");
      await retrySubmission(id);
      await loadSubmissions();
      return;
    }
    if (action === "delete") {
      const confirmed = window.confirm(`Delete submission ${id}? This removes stored upload files.`);
      if (!confirmed) {
        return;
      }
      target.setAttribute("disabled", "disabled");
      await deleteSubmission(id);
      await loadSubmissions();
    }
  } catch (error) {
    setError(error?.message || "Action failed.");
  } finally {
    target.removeAttribute("disabled");
  }
});

refreshBtn.addEventListener("click", loadSubmissions);
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadSubmissions();
  }
});
statusSelect.addEventListener("change", loadSubmissions);

loadSubmissions();
