const messageBox = document.getElementById("messageBox");
const jobIdBadge = document.getElementById("jobIdBadge");
const sourceImage = document.getElementById("sourceImage");
const sourceEmpty = document.getElementById("sourceEmpty");
const visitorNameText = document.getElementById("visitorNameText");
const photoPrintImage = document.getElementById("photoPrintImage");
const photoEmpty = document.getElementById("photoEmpty");
const createPhotoBtn = document.getElementById("createPhotoBtn");
const downloadPhotoLink = document.getElementById("downloadPhotoLink");
const recreatePhotoBtn = document.getElementById("recreatePhotoBtn");

let currentJob = null;
let currentPhoto = null;
let actionInProgress = false;

function readJobId() {
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  if (pathParts[0] === "photo" && pathParts[1]) {
    return decodeURIComponent(pathParts[1]);
  }
  const params = new URLSearchParams(window.location.search);
  return String(params.get("jobId") || "").trim();
}

function showMessage(message, tone = "error") {
  if (!messageBox) {
    return;
  }
  messageBox.hidden = !message;
  messageBox.textContent = String(message || "");
  messageBox.classList.toggle("is-info", tone === "info");
}

function withCache(url) {
  const raw = String(url || "").trim();
  if (!raw) {
    return "";
  }
  const separator = raw.includes("?") ? "&" : "?";
  return `${raw}${separator}v=${Date.now()}`;
}

function sanitizeFilenamePart(value) {
  const cleaned = String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return cleaned || "Wonderpark-Guest";
}

function updateButtons() {
  const hasPhoto = Boolean(currentPhoto?.photoPrintUrl || currentJob?.photoPrintUrl);
  if (createPhotoBtn) {
    createPhotoBtn.hidden = hasPhoto;
    createPhotoBtn.disabled = actionInProgress;
  }
  if (recreatePhotoBtn) {
    recreatePhotoBtn.disabled = actionInProgress || !currentJob;
  }
  if (downloadPhotoLink) {
    downloadPhotoLink.classList.toggle("is-disabled", !hasPhoto || actionInProgress);
  }
}

function renderJob(job) {
  currentJob = job || null;
  const jobId = String(job?.jobId || readJobId() || "").trim();
  const visitorName = String(job?.visitorName || "Wonderpark Guest").trim() || "Wonderpark Guest";

  if (jobIdBadge) {
    jobIdBadge.textContent = jobId || "-";
  }
  if (visitorNameText) {
    visitorNameText.textContent = visitorName;
  }
  if (sourceImage && sourceEmpty) {
    const outputUrl = String(job?.outputUrl || "").trim();
    if (outputUrl) {
      sourceImage.src = withCache(outputUrl);
      sourceImage.hidden = false;
      sourceEmpty.hidden = true;
    } else {
      sourceImage.hidden = true;
      sourceEmpty.hidden = false;
      sourceEmpty.textContent = "Generated output image not found.";
    }
  }
}

function renderPhoto(photo) {
  currentPhoto = photo || null;
  const photoUrl = String(photo?.photoPrintUrl || currentJob?.photoPrintUrl || "").trim();
  const jobId = String(currentJob?.jobId || readJobId() || "").trim();
  const visitorName = String(currentJob?.visitorName || "Wonderpark Guest").trim() || "Wonderpark Guest";

  if (photoUrl) {
    photoPrintImage.src = withCache(photoUrl);
    photoPrintImage.hidden = false;
    photoEmpty.hidden = true;
    downloadPhotoLink.href = photoUrl;
    downloadPhotoLink.download = `AI-Genius-Wonderpark-${sanitizeFilenamePart(visitorName)}-${sanitizeFilenamePart(jobId)}.png`;
  } else {
    photoPrintImage.hidden = true;
    photoEmpty.hidden = false;
    photoEmpty.textContent = "Create the 4x6 photo to preview it here.";
    downloadPhotoLink.href = "#";
    downloadPhotoLink.removeAttribute("download");
  }
  updateButtons();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(payload?.detail || payload?.message || "Request failed."));
  }
  return payload;
}

async function loadPage() {
  const jobId = readJobId();
  if (!jobId) {
    showMessage("Job not found");
    if (sourceEmpty) {
      sourceEmpty.textContent = "Job not found.";
    }
    updateButtons();
    return;
  }

  try {
    showMessage("Loading photo print details...", "info");
    const job = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderJob(job);
    const photo = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/photo`);
    renderPhoto(photo);
    showMessage("");
  } catch (error) {
    showMessage(error?.message || "Unable to load job.");
    updateButtons();
  }
}

async function createOrRecreatePhoto() {
  const jobId = String(currentJob?.jobId || readJobId() || "").trim();
  if (!jobId || actionInProgress) {
    return;
  }

  actionInProgress = true;
  updateButtons();
  if (createPhotoBtn) {
    createPhotoBtn.textContent = "Creating...";
  }
  if (recreatePhotoBtn) {
    recreatePhotoBtn.textContent = "Recreating...";
  }

  try {
    showMessage("Creating 4x6 photo print...", "info");
    const photo = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/create-photo`, {
      method: "POST",
    });
    renderPhoto(photo);
    showMessage("");
  } catch (error) {
    showMessage(error?.message || "Unable to create photo print.");
  } finally {
    actionInProgress = false;
    if (createPhotoBtn) {
      createPhotoBtn.textContent = "Create 4x6 Photo";
    }
    if (recreatePhotoBtn) {
      recreatePhotoBtn.textContent = "Recreate Photo";
    }
    updateButtons();
  }
}

if (createPhotoBtn) {
  createPhotoBtn.addEventListener("click", () => {
    void createOrRecreatePhoto();
  });
}

if (recreatePhotoBtn) {
  recreatePhotoBtn.addEventListener("click", () => {
    void createOrRecreatePhoto();
  });
}

void loadPage();
