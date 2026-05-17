const visitorNameInput = document.getElementById("visitorName");
const visitorNotesInput = document.getElementById("visitorNotes");
const drawingFileInput = document.getElementById("drawingFile");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const controlHint = document.getElementById("controlHint");
const staffLanUrl = document.getElementById("staffLanUrl");
const galleryLanUrl = document.getElementById("galleryLanUrl");

const statusText = document.getElementById("statusText");
const jobIdText = document.getElementById("jobIdText");
const visitorText = document.getElementById("visitorText");
const presetText = document.getElementById("presetText");
const promptModeText = document.getElementById("promptModeText");
const estimatedTimeText = document.getElementById("estimatedTimeText");
const elapsedTimeText = document.getElementById("elapsedTimeText");
const finalDurationText = document.getElementById("finalDurationText");

const inputPreviewLink = document.getElementById("inputPreviewLink");
const inputPreviewImage = document.getElementById("inputPreviewImage");
const outputPreviewLink = document.getElementById("outputPreviewLink");
const outputPreviewImage = document.getElementById("outputPreviewImage");

const ratingSection = document.getElementById("ratingSection");
const starGroup = document.getElementById("starGroup");
const tagGroup = document.getElementById("tagGroup");
const feedbackNoteInput = document.getElementById("feedbackNote");
const saveRatingBtn = document.getElementById("saveRatingBtn");
const ratingStatus = document.getElementById("ratingStatus");
const scoreSubjectPreserved = document.getElementById("scoreSubjectPreserved");
const scoreColorImprovement = document.getElementById("scoreColorImprovement");
const scoreBackgroundFullness = document.getElementById("scoreBackgroundFullness");
const scoreStyleQuality = document.getElementById("scoreStyleQuality");
const scoreChildFriendlyResult = document.getElementById("scoreChildFriendlyResult");
const autoReviewBox = document.getElementById("autoReviewBox");
const autoRatingText = document.getElementById("autoRatingText");
const autoConfidenceText = document.getElementById("autoConfidenceText");
const autoBadTagsText = document.getElementById("autoBadTagsText");
const autoGoodTagsText = document.getElementById("autoGoodTagsText");
const autoNotesText = document.getElementById("autoNotesText");
const applyAutoReviewBtn = document.getElementById("applyAutoReviewBtn");

const galleryControlList = document.getElementById("galleryControlList");
const refreshGalleryControlBtn = document.getElementById("refreshGalleryControlBtn");

const eventLog = document.getElementById("eventLog");
const methodTabs = Array.from(document.querySelectorAll(".method-tab"));
const methodPanels = Array.from(document.querySelectorAll(".method-panel"));
const webcamPermissionStatus = document.getElementById("webcamPermissionStatus");
const requestWebcamPermissionBtn = document.getElementById("requestWebcamPermissionBtn");

const BAD_FEEDBACK_TAG_GROUPS = [
  {
    title: "1. Identity / subject problems",
    tags: [
      { id: "wrong_subject", label: "Wrong subject" },
      { id: "same_as_input", label: "Same as input" },
      { id: "person_missing", label: "Person missing" },
      { id: "main_object_missing", label: "Main object missing" },
      { id: "wrong_composition", label: "Wrong composition" },
      { id: "over_changed", label: "Over changed" }
    ]
  },
  {
    title: "2. Quality and color problems",
    tags: [
      { id: "too_empty", label: "Too empty" },
      { id: "bad_colors", label: "Bad colors" },
      { id: "low_quality", label: "Low quality" },
      { id: "too_realistic", label: "Too realistic" },
      { id: "scary_or_creepy", label: "Scary or creepy" }
    ]
  },
  {
    title: "3. Legacy / advanced tags",
    tags: [
      { id: "wrong_generation", label: "Wrong generation (legacy)" },
      { id: "person_changed", label: "Person changed" },
      { id: "face_changed", label: "Face changed" },
      { id: "artwork_missing", label: "Artwork missing" },
      { id: "artwork_changed", label: "Artwork changed" },
      { id: "object_missing", label: "Object missing" },
      { id: "object_changed", label: "Object changed" },
      { id: "composition_wrong", label: "Composition wrong (legacy)" },
      { id: "changed_too_much", label: "Changed too much (legacy)" },
      { id: "creepy", label: "Creepy (legacy)" },
      { id: "background_wrong", label: "Background wrong" },
      { id: "too_messy", label: "Too messy" },
      { id: "style_wrong", label: "Style wrong" },
      { id: "not_lively_enough", label: "Not lively enough" },
      { id: "too_cartoon", label: "Too cartoon" }
    ]
  },
  {
    title: "4. Technical artifacts",
    tags: [
      { id: "bad_face", label: "Bad face" },
      { id: "bad_hands", label: "Bad hands" },
      { id: "blurry", label: "Blurry" },
      { id: "too_dark", label: "Too dark" },
      { id: "text_or_watermark", label: "Text or watermark" }
    ]
  }
];

const GOOD_FEEDBACK_TAGS = [
  { id: "good_preserve_shape", label: "Good preserve shape" },
  { id: "good_preserve_person", label: "Good preserve person" },
  { id: "good_preserve_artwork", label: "Good preserve artwork" },
  { id: "good_lively", label: "Good lively" },
  { id: "good_colors", label: "Good colors" },
  { id: "good_style", label: "Good style" },
  { id: "good_overall", label: "Good overall" }
];

const ALL_FEEDBACK_TAG_IDS = new Set([
  ...BAD_FEEDBACK_TAG_GROUPS.flatMap((group) => group.tags.map((tag) => tag.id)),
  ...GOOD_FEEDBACK_TAGS.map((tag) => tag.id)
]);

const DEFAULT_ESTIMATE = {
  estimatedSeconds: 60,
  minSeconds: 48,
  maxSeconds: 78,
  sampleCount: 0
};

let loading = false;
let currentMethod = "upload";
let currentJobId = null;
let selectedRating = null;
let activeEstimate = null;
let elapsedTimerId = null;
let elapsedStartMs = null;
let localInputPreviewUrl = null;
let galleryControlItems = [];
let latestQueueStatus = null;
let webcamPermissionState = "unknown";
let webcamPermissionPending = null;
let currentAutoReview = {
  autoRating: 0,
  autoBadTags: [],
  autoGoodTags: [],
  autoNotes: "",
  confidence: 0,
  metrics: {
    similarityScore: 0,
    whiteBackgroundRatio: 0,
    colorRatio: 0,
    edgeRatio: 0,
    colorGain: 0
  }
};

function appendEvent(text, isError = false) {
  const item = document.createElement("li");
  item.textContent = text;
  if (isError) {
    item.classList.add("error");
  }
  eventLog.prepend(item);
  while (eventLog.children.length > 30) {
    eventLog.removeChild(eventLog.lastChild);
  }
}

function setupLanHelper() {
  if (!staffLanUrl || !galleryLanUrl) {
    return;
  }
  const base = `${window.location.protocol}//${window.location.host}`;
  const staffUrl = `${base}/staff`;
  const galleryUrl = `${base}/gallery`;
  staffLanUrl.href = staffUrl;
  staffLanUrl.textContent = staffUrl;
  galleryLanUrl.href = galleryUrl;
  galleryLanUrl.textContent = galleryUrl;
}

function formatWaitSeconds(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return "0 sec";
  }
  return `${Math.round(numeric)} sec`;
}

function formatClock(totalSeconds) {
  const safeSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatDateTime(isoString) {
  if (!isoString) {
    return "-";
  }
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    return isoString;
  }
  return parsed.toLocaleString();
}

function formatSourceLabel(sourceValue) {
  return String(sourceValue || "").trim().toLowerCase() === "api" ? "API" : "Staff";
}

function formatEstimateRange(estimate) {
  if (!estimate) {
    return "-";
  }
  return `${estimate.minSeconds}-${estimate.maxSeconds} sec`;
}

function normalizeEstimate(rawEstimate) {
  if (!rawEstimate || typeof rawEstimate !== "object") {
    return { ...DEFAULT_ESTIMATE };
  }

  const estimatedSeconds = Math.max(1, Math.round(Number(rawEstimate.estimatedSeconds) || DEFAULT_ESTIMATE.estimatedSeconds));
  const minSeconds = Math.max(1, Math.round(Number(rawEstimate.minSeconds) || estimatedSeconds));
  const maxSeconds = Math.max(minSeconds, Math.round(Number(rawEstimate.maxSeconds) || estimatedSeconds));
  const sampleCount = Math.max(0, Math.round(Number(rawEstimate.sampleCount) || 0));

  return {
    estimatedSeconds,
    minSeconds,
    maxSeconds,
    sampleCount
  };
}

function setStatus(value) {
  const text = value || "Idle";
  statusText.textContent = text;

  const lower = text.toLowerCase();
  statusText.dataset.state = "idle";
  if (lower.includes("generat") || lower.includes("captur")) {
    statusText.dataset.state = "running";
  } else if (lower.includes("error") || lower.includes("fail")) {
    statusText.dataset.state = "error";
  } else if (lower.includes("complete")) {
    statusText.dataset.state = "complete";
  }
}

function stopElapsedTimer(finalSeconds = null) {
  if (elapsedTimerId !== null) {
    window.clearInterval(elapsedTimerId);
    elapsedTimerId = null;
  }

  if (typeof finalSeconds === "number" && Number.isFinite(finalSeconds)) {
    elapsedTimeText.textContent = formatClock(finalSeconds);
  }
}

function startElapsedTimer(startedAtIso = null) {
  stopElapsedTimer();

  let startMs = Date.now();
  if (startedAtIso) {
    const parsedStart = Date.parse(startedAtIso);
    if (!Number.isNaN(parsedStart)) {
      startMs = parsedStart;
    }
  }

  elapsedStartMs = startMs;
  elapsedTimeText.textContent = "00:00";

  elapsedTimerId = window.setInterval(() => {
    const elapsedSeconds = Math.floor((Date.now() - elapsedStartMs) / 1000);
    elapsedTimeText.textContent = formatClock(elapsedSeconds);
  }, 1000);
}

function setLoading(nextLoading) {
  loading = nextLoading;
  methodTabs.forEach((tab) => {
    tab.disabled = nextLoading;
  });
  clearBtn.disabled = nextLoading;

  const scannerMode = currentMethod === "scanner";
  generateBtn.disabled = nextLoading || scannerMode;
  drawingFileInput.disabled = nextLoading || currentMethod !== "upload";
}

function setPreview(linkEl, imageEl, sourceUrl) {
  if (!sourceUrl) {
    imageEl.removeAttribute("src");
    imageEl.hidden = true;
    linkEl.href = "#";
    linkEl.setAttribute("aria-disabled", "true");
    linkEl.classList.add("is-empty");
    linkEl.classList.remove("is-loading");
    return;
  }

  const isBlobUrl = sourceUrl.startsWith("blob:");
  const cacheBustedUrl = isBlobUrl
    ? sourceUrl
    : `${sourceUrl}${sourceUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
  imageEl.hidden = true;
  imageEl.src = cacheBustedUrl;
  linkEl.href = sourceUrl;
  linkEl.setAttribute("aria-disabled", "false");
  linkEl.classList.remove("is-empty");
}

function setPreviewLoading(linkEl, isLoading) {
  linkEl.classList.toggle("is-loading", Boolean(isLoading));
}

function resetLocalInputPreviewUrl() {
  if (localInputPreviewUrl) {
    URL.revokeObjectURL(localInputPreviewUrl);
    localInputPreviewUrl = null;
  }
}

function applyEstimate(estimate) {
  activeEstimate = normalizeEstimate(estimate);
  estimatedTimeText.textContent = formatEstimateRange(activeEstimate);
}

function applyQueueStatus(statusPayload, { silent = false } = {}) {
  if (!statusPayload || typeof statusPayload !== "object") {
    return;
  }
  latestQueueStatus = statusPayload;
  const queueLength = Number(statusPayload.queueLength || 0);
  const currentJob = statusPayload.currentJob || "-";
  const waitText = formatWaitSeconds(statusPayload.estimatedWaitSeconds || 0);

  if (!loading && !currentJobId) {
    setStatus(queueLength > 0 ? "Queued" : "Idle");
  }
  if (queueLength > 0 || currentJob !== "-") {
    estimatedTimeText.textContent = waitText;
  }
  if (!silent) {
    appendEvent(`Queue: ${queueLength} waiting, current job: ${currentJob}.`);
  }
}

async function fetchQueueStatus({ silent = false } = {}) {
  try {
    const response = await fetch("/queue/status");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to load queue status.");
    }
    applyQueueStatus(data, { silent });
  } catch (error) {
    if (!silent) {
      appendEvent(error.message || "Failed to load queue status.", true);
    }
  }
}

async function fetchGenerationEstimate() {
  try {
    const response = await fetch("/generation/estimate");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to load estimate.");
    }
    return normalizeEstimate(data);
  } catch (error) {
    appendEvent(`Using default estimate (${DEFAULT_ESTIMATE.estimatedSeconds} sec).`);
    return { ...DEFAULT_ESTIMATE };
  }
}

function renderTagCheckboxes() {
  tagGroup.innerHTML = "";

  const createTagGroup = (title, tags, variant) => {
    const group = document.createElement("section");
    group.className = "tag-category";

    const heading = document.createElement("p");
    heading.className = "tag-category-title";
    heading.textContent = title;
    group.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "tag-category-grid";

    tags.forEach((tagMeta) => {
      const label = document.createElement("label");
      label.className = `tag-item ${variant}`;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = tagMeta.id;

      const text = document.createElement("span");
      text.textContent = tagMeta.label;

      label.appendChild(checkbox);
      label.appendChild(text);
      grid.appendChild(label);
    });

    group.appendChild(grid);
    tagGroup.appendChild(group);
  };

  BAD_FEEDBACK_TAG_GROUPS.forEach((group) => {
    createTagGroup(group.title, group.tags, "bad");
  });
  createTagGroup("Good feedback tags", GOOD_FEEDBACK_TAGS, "good");
}

function setSelectedRating(ratingValue) {
  selectedRating = ratingValue;
  starGroup.querySelectorAll(".star-btn").forEach((button) => {
    const value = Number(button.dataset.star || "0");
    button.classList.toggle("active", value === ratingValue);
  });
}

function getSelectedFeedbackTags() {
  const selected = [];
  tagGroup.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    if (checkbox.checked) {
      selected.push(checkbox.value);
    }
  });
  return selected;
}

function setSelectedFeedbackTags(tags) {
  const selectedSet = new Set(Array.isArray(tags) ? tags : []);
  tagGroup.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.checked = selectedSet.has(checkbox.value);
  });
}

function getComparisonScoresFromForm() {
  const fields = [
    ["subjectPreserved", scoreSubjectPreserved],
    ["colorImprovement", scoreColorImprovement],
    ["backgroundFullness", scoreBackgroundFullness],
    ["styleQuality", scoreStyleQuality],
    ["childFriendlyResult", scoreChildFriendlyResult]
  ];
  const payload = {};
  fields.forEach(([key, element]) => {
    if (!element) {
      return;
    }
    const numeric = Number(element.value);
    if (Number.isInteger(numeric) && numeric >= 1 && numeric <= 5) {
      payload[key] = numeric;
    }
  });
  return payload;
}

function setComparisonScoresToForm(scores) {
  const safe = scores && typeof scores === "object" ? scores : {};
  const fields = [
    ["subjectPreserved", scoreSubjectPreserved],
    ["colorImprovement", scoreColorImprovement],
    ["backgroundFullness", scoreBackgroundFullness],
    ["styleQuality", scoreStyleQuality],
    ["childFriendlyResult", scoreChildFriendlyResult]
  ];
  fields.forEach(([key, element]) => {
    if (!element) {
      return;
    }
    const numeric = Number(safe[key]);
    element.value = Number.isInteger(numeric) && numeric >= 1 && numeric <= 5 ? String(numeric) : "";
  });
}

function normalizeAutoReview(rawReview) {
  const fallback = {
    autoRating: 0,
    autoBadTags: [],
    autoGoodTags: [],
    autoNotes: "",
    confidence: 0,
    metrics: {
      similarityScore: 0,
      whiteBackgroundRatio: 0,
      colorRatio: 0,
      edgeRatio: 0,
      colorGain: 0
    }
  };

  if (!rawReview || typeof rawReview !== "object") {
    return fallback;
  }

  const autoRating = Number(rawReview.autoRating);
  const badTags = Array.isArray(rawReview.autoBadTags)
    ? rawReview.autoBadTags.filter((tag) => typeof tag === "string" && ALL_FEEDBACK_TAG_IDS.has(tag))
    : [];
  const goodTags = Array.isArray(rawReview.autoGoodTags)
    ? rawReview.autoGoodTags.filter((tag) => typeof tag === "string" && ALL_FEEDBACK_TAG_IDS.has(tag))
    : [];
  const confidenceValue = Number(rawReview.confidence);
  const rawMetrics = rawReview.metrics && typeof rawReview.metrics === "object" ? rawReview.metrics : {};
  const metricNumber = (value, min = 0, max = 1) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return Math.max(min, Math.min(max, numeric));
  };

  return {
    autoRating: Number.isInteger(autoRating) && autoRating >= 1 && autoRating <= 5 ? autoRating : 0,
    autoBadTags: Array.from(new Set(badTags)),
    autoGoodTags: Array.from(new Set(goodTags)),
    autoNotes: String(rawReview.autoNotes || "").trim(),
    confidence:
      Number.isFinite(confidenceValue) && confidenceValue >= 0
        ? Math.max(0, Math.min(1, confidenceValue))
        : 0,
    metrics: {
      similarityScore: metricNumber(rawMetrics.similarityScore, 0, 1),
      whiteBackgroundRatio: metricNumber(rawMetrics.whiteBackgroundRatio, 0, 1),
      colorRatio: metricNumber(rawMetrics.colorRatio, 0, 1),
      edgeRatio: metricNumber(rawMetrics.edgeRatio, 0, 1),
      colorGain: metricNumber(rawMetrics.colorGain, -1, 1)
    }
  };
}

function renderAutoReview(rawReview) {
  currentAutoReview = normalizeAutoReview(rawReview);
  if (!autoReviewBox) {
    return;
  }

  autoRatingText.textContent = currentAutoReview.autoRating
    ? `${currentAutoReview.autoRating}/5`
    : "-";
  autoConfidenceText.textContent = `${Math.round(currentAutoReview.confidence * 100)}%`;
  autoBadTagsText.textContent = currentAutoReview.autoBadTags.length
    ? currentAutoReview.autoBadTags.join(", ")
    : "-";
  autoGoodTagsText.textContent = currentAutoReview.autoGoodTags.length
    ? currentAutoReview.autoGoodTags.join(", ")
    : "-";
  autoNotesText.textContent = currentAutoReview.autoNotes || "-";

  if (applyAutoReviewBtn) {
    applyAutoReviewBtn.disabled = currentAutoReview.autoRating <= 0;
  }
}

function applyAutoReviewToForm() {
  if (!currentAutoReview || currentAutoReview.autoRating <= 0) {
    ratingStatus.textContent = "Auto review rating is not available yet.";
    return;
  }

  setSelectedRating(currentAutoReview.autoRating);
  const mergedTags = Array.from(new Set([
    ...currentAutoReview.autoBadTags,
    ...currentAutoReview.autoGoodTags
  ]));
  setSelectedFeedbackTags(mergedTags);

  const clampScore = (value) => Math.max(1, Math.min(5, Math.round(value)));
  const metrics = currentAutoReview.metrics || {};
  const similarity = Number(metrics.similarityScore || 0);
  const whiteRatio = Number(metrics.whiteBackgroundRatio || 0);
  const colorRatio = Number(metrics.colorRatio || 0);
  const edgeRatio = Number(metrics.edgeRatio || 0);
  const colorGain = Number(metrics.colorGain || 0);
  const hasCreepy = currentAutoReview.autoBadTags.includes("scary_or_creepy") || currentAutoReview.autoBadTags.includes("creepy");

  setComparisonScoresToForm({
    subjectPreserved: clampScore(1 + similarity * 4),
    colorImprovement: clampScore(3 + colorGain * 6),
    backgroundFullness: clampScore(5 - whiteRatio * 4),
    styleQuality: clampScore(1 + (edgeRatio * 2.4 + colorRatio * 1.8)),
    childFriendlyResult: hasCreepy ? 2 : clampScore(3 + (0.5 - whiteRatio) * 2)
  });

  const notePrefix = "AUTO REVIEW:";
  const autoNoteLine = currentAutoReview.autoNotes
    ? `${notePrefix} ${currentAutoReview.autoNotes}`
    : `${notePrefix} autoRating=${currentAutoReview.autoRating}/5 confidence=${Math.round(currentAutoReview.confidence * 100)}%`;

  const currentNote = String(feedbackNoteInput.value || "").trim();
  if (!currentNote.includes(notePrefix)) {
    feedbackNoteInput.value = currentNote ? `${currentNote}\n${autoNoteLine}` : autoNoteLine;
  }
  ratingStatus.textContent = "Auto review applied. You can edit before saving.";
}

function setWebcamPermissionState(state, message) {
  webcamPermissionState = state;
  if (webcamPermissionStatus) {
    webcamPermissionStatus.textContent = message;
  }
  if (requestWebcamPermissionBtn) {
    requestWebcamPermissionBtn.disabled = state === "checking";
  }
}

function canRequestBrowserCameraPermission() {
  return Boolean(
    window.navigator &&
      window.navigator.mediaDevices &&
      typeof window.navigator.mediaDevices.getUserMedia === "function"
  );
}

function stopMediaStream(stream) {
  if (!stream || typeof stream.getTracks !== "function") {
    return;
  }
  stream.getTracks().forEach((track) => {
    try {
      track.stop();
    } catch (error) {
      // Ignore track stop errors.
    }
  });
}

function buildCameraPermissionErrorMessage(error) {
  const errorName = String((error && error.name) || "").trim();
  if (errorName === "NotAllowedError" || errorName === "PermissionDeniedError") {
    return "Camera permission denied. Allow camera access in browser settings.";
  }
  if (errorName === "NotFoundError" || errorName === "DevicesNotFoundError") {
    return "No camera device found on this browser device.";
  }
  if (errorName === "NotReadableError" || errorName === "TrackStartError") {
    return "Camera is busy or unavailable. Close other camera apps and try again.";
  }
  if (errorName === "SecurityError") {
    return "Camera access is blocked by browser security policy.";
  }
  if (!window.isSecureContext) {
    return "Camera permission requires HTTPS or localhost.";
  }
  return "Unable to request camera permission from browser.";
}

async function requestWebcamPermission({ silent = false } = {}) {
  if (!canRequestBrowserCameraPermission()) {
    setWebcamPermissionState(
      "unsupported",
      "Camera permission API not supported in this browser."
    );
    if (!silent) {
      appendEvent("Browser does not support camera permission request.", true);
    }
    return false;
  }

  if (webcamPermissionPending) {
    return webcamPermissionPending;
  }

  setWebcamPermissionState("checking", "Requesting camera permission...");
  webcamPermissionPending = window.navigator.mediaDevices
    .getUserMedia({ video: true })
    .then((stream) => {
      stopMediaStream(stream);
      setWebcamPermissionState("granted", "Camera permission granted.");
      if (!silent) {
        appendEvent("Camera permission granted.");
      }
      return true;
    })
    .catch((error) => {
      const message = buildCameraPermissionErrorMessage(error);
      setWebcamPermissionState("denied", message);
      if (!silent) {
        appendEvent(message, true);
      }
      return false;
    })
    .finally(() => {
      webcamPermissionPending = null;
    });

  return webcamPermissionPending;
}

function updateControlText() {
  if (currentMethod === "upload") {
    generateBtn.textContent = "Generate Artwork";
    controlHint.textContent = "Upload a drawing file and generate from upload.";
  } else if (currentMethod === "webcam") {
    generateBtn.textContent = "Capture + Generate";
    controlHint.textContent = "Capture from webcam and generate in one run.";
  } else {
    generateBtn.textContent = "Scanner Auto Mode";
    controlHint.textContent = "Scanner auto import runs in the background. Watch live events for completed jobs.";
  }
}

function setActiveMethod(methodName) {
  currentMethod = methodName;

  methodTabs.forEach((tab) => {
    const isActive = tab.dataset.method === methodName;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  methodPanels.forEach((panel) => {
    const isActive = panel.dataset.panel === methodName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });

  updateControlText();
  setLoading(loading);
  if (methodName === "webcam") {
    requestWebcamPermission({ silent: false });
  }
}

function resetStatusCards() {
  setStatus("Idle");
  jobIdText.textContent = "-";
  visitorText.textContent = "-";
  presetText.textContent = "-";
  promptModeText.textContent = "-";
  estimatedTimeText.textContent = activeEstimate ? formatEstimateRange(activeEstimate) : "-";
  elapsedTimeText.textContent = "00:00";
  finalDurationText.textContent = "-";
}

function updateStatusFromResult(result, source = "response") {
  const settings = result.generationSettings || {};
  const jobId = result.jobId || "-";

  setStatus(result.status || "Completed");
  jobIdText.textContent = jobId;
  visitorText.textContent = result.visitorName || "-";
  presetText.textContent = result.preset || "-";
  promptModeText.textContent = result.promptMode || result.promptType || "-";

  if (result.estimate && typeof result.estimate === "object") {
    applyEstimate(result.estimate);
  } else if (Number.isFinite(Number(result.estimatedSeconds))) {
    const estimateValue = Math.max(1, Math.round(Number(result.estimatedSeconds)));
    applyEstimate({
      estimatedSeconds: estimateValue,
      minSeconds: estimateValue,
      maxSeconds: estimateValue,
      sampleCount: 0
    });
  }

  currentJobId = result.jobId || currentJobId;

  if (result.inputUrl) {
    setPreview(inputPreviewLink, inputPreviewImage, result.inputUrl);
  }
  if (result.outputUrl) {
    setPreview(outputPreviewLink, outputPreviewImage, result.outputUrl);
    setPreviewLoading(outputPreviewLink, false);
    ratingSection.hidden = false;
  }

  const durationSeconds = Number(result.durationSeconds);
  if (Number.isFinite(durationSeconds) && durationSeconds > 0) {
    stopElapsedTimer(durationSeconds);
    finalDurationText.textContent = formatClock(durationSeconds);
  } else if (source === "error") {
    stopElapsedTimer();
    finalDurationText.textContent = "-";
  }

  const rawStaffRating = result.staffRating ?? result.rating;
  const existingRating = Number(rawStaffRating);
  if (Number.isInteger(existingRating) && existingRating >= 1 && existingRating <= 5) {
    setSelectedRating(existingRating);
  } else {
    setSelectedRating(null);
  }

  const autoReviewFromResult =
    result.autoReview && typeof result.autoReview === "object"
      ? result.autoReview
      : {
          autoRating: Number(result.autoRating) || 0,
          autoBadTags: [],
          autoGoodTags: [],
          autoNotes: "",
          confidence: 0,
          metrics: {
            similarityScore: 0,
            whiteBackgroundRatio: 0,
            colorRatio: 0,
            edgeRatio: 0,
            colorGain: 0
          }
        };
  renderAutoReview(autoReviewFromResult);

  setSelectedFeedbackTags(result.feedbackTags || []);
  setComparisonScoresToForm(result.comparisonScores || {});
  feedbackNoteInput.value = result.feedbackNote || "";

  ratingStatus.textContent = result.ratedAt
    ? `Rating saved at ${new Date(result.ratedAt).toLocaleString()}`
    : "No rating saved yet.";

  if (settings.controlWeight !== undefined || settings.denoisingStrength !== undefined) {
    appendEvent(
      `Completed ${jobId} with preset ${result.preset || "-"} (weight ${settings.controlWeight ?? "-"}, denoise ${settings.denoisingStrength ?? "-"}).`
    );
  }
}

function clearDashboard() {
  if (loading) {
    return;
  }

  resetLocalInputPreviewUrl();
  if (drawingFileInput) {
    drawingFileInput.value = "";
  }

  currentJobId = null;
  selectedRating = null;

  setSelectedRating(null);
  setSelectedFeedbackTags([]);
  setComparisonScoresToForm({});
  renderAutoReview(null);
  feedbackNoteInput.value = "";
  ratingStatus.textContent = "No rating saved yet.";
  ratingSection.hidden = true;

  stopElapsedTimer();
  resetStatusCards();

  setPreview(inputPreviewLink, inputPreviewImage, null);
  setPreview(outputPreviewLink, outputPreviewImage, null);
  setPreviewLoading(outputPreviewLink, false);

  appendEvent("Staff panel reset.");
}

async function submitGeneration() {
  if (loading) {
    return;
  }

  if (currentMethod === "scanner") {
    appendEvent("Scanner mode is automatic. Drop files in scanner_inputs/.", true);
    return;
  }

  const visitorName = visitorNameInput.value.trim() || "Guest";
  const visitorNotes = visitorNotesInput.value.trim();

  if (currentMethod === "upload") {
    const selectedFile = drawingFileInput.files[0];
    if (!selectedFile) {
      appendEvent("Select an image file before generating.", true);
      return;
    }

    resetLocalInputPreviewUrl();
    localInputPreviewUrl = URL.createObjectURL(selectedFile);
    setPreview(inputPreviewLink, inputPreviewImage, localInputPreviewUrl);
  }
  if (currentMethod === "webcam") {
    const hasPermission = await requestWebcamPermission({ silent: false });
    if (!hasPermission) {
      setStatus("Camera permission required");
      return;
    }
  }

  const estimate = await fetchGenerationEstimate();
  applyEstimate(estimate);

  setStatus("Generating");
  jobIdText.textContent = "pending";
  visitorText.textContent = visitorName;
  presetText.textContent = "-";
  promptModeText.textContent = "-";
  finalDurationText.textContent = "-";
  ratingSection.hidden = true;

  setPreviewLoading(outputPreviewLink, true);
  stopElapsedTimer();
  elapsedTimeText.textContent = "00:00";
  setLoading(true);

  if (visitorNotes) {
    appendEvent(`Note for ${visitorName}: ${visitorNotes}`);
  }

  try {
    const formData = new FormData();
    formData.append("visitorName", visitorName);

    let endpoint = "/generate";
    if (currentMethod === "upload") {
      formData.append("file", drawingFileInput.files[0]);
    } else {
      endpoint = "/capture";
    }

    const response = await fetch(endpoint, {
      method: "POST",
      body: formData
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Generation failed.");
    }

    if (payload.status === "queued" && payload.job) {
      currentJobId = payload.job.jobId || currentJobId;
      setStatus("Queued");
      jobIdText.textContent = payload.job.jobId || "pending";
      visitorText.textContent = payload.job.visitorName || visitorName;
      presetText.textContent = "-";
      promptModeText.textContent = "-";
      finalDurationText.textContent = "-";
      setPreviewLoading(outputPreviewLink, false);
      applyQueueStatus(payload, { silent: true });
      appendEvent(`Queued job ${payload.job.jobId}.`);
    } else {
      updateStatusFromResult({ status: "Completed", ...payload }, "response");
    }
  } catch (error) {
    setStatus("Error");
    stopElapsedTimer();
    setPreviewLoading(outputPreviewLink, false);
    finalDurationText.textContent = "-";
    appendEvent(error.message || "Unexpected generation error.", true);
  } finally {
    setLoading(false);
  }
}

async function saveRating() {
  if (!currentJobId) {
    appendEvent("Generate an artwork before saving rating.", true);
    return;
  }

  if (!selectedRating) {
    appendEvent("Select a rating from 1 to 5 stars.", true);
    return;
  }

  const payload = {
    rating: selectedRating,
    feedbackTags: getSelectedFeedbackTags(),
    feedbackNote: feedbackNoteInput.value.trim(),
    comparisonScores: getComparisonScoresFromForm()
  };

  saveRatingBtn.disabled = true;
  ratingStatus.textContent = "Saving rating...";

  try {
    const response = await fetch(`/gallery/rate/${encodeURIComponent(currentJobId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to save rating.");
    }

    updateStatusFromResult(data, "rating");
    mergeGalleryControlItem(data);
    appendEvent(`Saved rating ${data.rating} for ${data.jobId}.`);
  } catch (error) {
    ratingStatus.textContent = error.message || "Failed to save rating.";
    appendEvent(error.message || "Failed to save rating.", true);
  } finally {
    saveRatingBtn.disabled = false;
  }
}

function sortGalleryControlItems(items) {
  return items.slice().sort((a, b) => {
    const aTime = Date.parse(a.createdAt || "") || 0;
    const bTime = Date.parse(b.createdAt || "") || 0;
    return bTime - aTime;
  });
}

function mergeGalleryControlItem(updatedItem) {
  if (!updatedItem || !updatedItem.jobId) {
    return;
  }

  const index = galleryControlItems.findIndex((item) => item.jobId === updatedItem.jobId);
  if (index >= 0) {
    galleryControlItems[index] = { ...galleryControlItems[index], ...updatedItem };
  } else {
    galleryControlItems.push(updatedItem);
  }

  galleryControlItems = sortGalleryControlItems(galleryControlItems);

  if (currentJobId && currentJobId === updatedItem.jobId) {
    visitorText.textContent = updatedItem.visitorName || visitorText.textContent;
  }

  renderGalleryControlList();
}

function removeGalleryControlItem(jobId) {
  if (!jobId) {
    return;
  }
  galleryControlItems = galleryControlItems.filter((item) => item.jobId !== jobId);

  if (currentJobId && currentJobId === jobId) {
    currentJobId = null;
    ratingSection.hidden = true;
    ratingStatus.textContent = "No rating saved yet.";
  }

  renderGalleryControlList();
}

function setGalleryControlButtonsDisabled(buttons, disabled) {
  buttons.forEach((button) => {
    button.disabled = disabled;
  });
}

async function renameGalleryItem(jobId, visitorName, statusEl, buttons) {
  const cleanName = visitorName.trim() || "Guest";
  statusEl.textContent = "Saving name...";
  setGalleryControlButtonsDisabled(buttons, true);

  try {
    const response = await fetch(`/gallery/item/${encodeURIComponent(jobId)}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visitorName: cleanName })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to rename item.");
    }

    mergeGalleryControlItem(data);
    statusEl.textContent = "Name updated.";
    appendEvent(`Renamed ${jobId} to ${data.visitorName || "Guest"}.`);
  } catch (error) {
    statusEl.textContent = error.message || "Failed to rename item.";
    appendEvent(statusEl.textContent, true);
  } finally {
    setGalleryControlButtonsDisabled(buttons, false);
  }
}

async function setGalleryItemVisibility(jobId, hiddenValue, statusEl, buttons) {
  statusEl.textContent = hiddenValue ? "Hiding item..." : "Showing item...";
  setGalleryControlButtonsDisabled(buttons, true);

  try {
    const response = await fetch(`/gallery/item/${encodeURIComponent(jobId)}/visibility`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hidden: hiddenValue })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to update visibility.");
    }

    mergeGalleryControlItem(data);
    statusEl.textContent = hiddenValue ? "Hidden from public gallery." : "Visible on public gallery.";
    appendEvent(`${hiddenValue ? "Hid" : "Unhid"} gallery item ${jobId}.`);
  } catch (error) {
    statusEl.textContent = error.message || "Failed to update visibility.";
    appendEvent(statusEl.textContent, true);
  } finally {
    setGalleryControlButtonsDisabled(buttons, false);
  }
}

async function deleteGalleryItem(jobId, statusEl, buttons) {
  statusEl.textContent = "Deleting item...";
  setGalleryControlButtonsDisabled(buttons, true);

  try {
    const response = await fetch(`/gallery/item/${encodeURIComponent(jobId)}`, {
      method: "DELETE"
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to delete item.");
    }

    removeGalleryControlItem(jobId);
    appendEvent(`Deleted gallery item ${jobId}.`);
  } catch (error) {
    statusEl.textContent = error.message || "Failed to delete item.";
    appendEvent(statusEl.textContent, true);
    setGalleryControlButtonsDisabled(buttons, false);
  }
}

function createGalleryControlCard(item) {
  const wrapper = document.createElement("article");
  wrapper.className = "gallery-control-item";
  wrapper.dataset.jobId = item.jobId || "";
  if (item.hidden) {
    wrapper.classList.add("is-hidden");
  }

  const top = document.createElement("div");
  top.className = "gallery-control-top";

  const thumb = document.createElement("img");
  thumb.className = "gallery-control-thumb";
  thumb.alt = `Generated output for ${item.visitorName || "Guest"}`;
  if (item.outputUrl) {
    thumb.src = `${item.outputUrl}${item.outputUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
  }
  top.appendChild(thumb);

  const meta = document.createElement("div");
  meta.className = "gallery-control-meta";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = item.visitorName || "Guest";
  nameInput.placeholder = "Visitor name";
  meta.appendChild(nameInput);

  const jobLine = document.createElement("div");
  jobLine.className = "gallery-control-job";
  const visibilityText = item.hidden ? "Hidden" : "Visible";
  jobLine.textContent = `Job ${item.jobId || "-"} | ${formatDateTime(item.createdAt)} | ${visibilityText}`;
  meta.appendChild(jobLine);

  const sourceLine = document.createElement("div");
  sourceLine.className = "gallery-control-source";
  sourceLine.textContent = `Source: ${formatSourceLabel(item.source)}`;
  meta.appendChild(sourceLine);

  const actionRow = document.createElement("div");
  actionRow.className = "gallery-control-actions";

  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "small-action-btn";
  renameBtn.textContent = "Save Name";

  const visibilityBtn = document.createElement("button");
  visibilityBtn.type = "button";
  visibilityBtn.className = "small-action-btn";
  visibilityBtn.textContent = item.hidden ? "Unhide" : "Hide";

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "small-action-btn danger";
  deleteBtn.textContent = "Delete";

  const previewWrap = document.createElement("div");
  previewWrap.className = "gallery-control-preview-wrap";

  const previewBtn = document.createElement("button");
  previewBtn.type = "button";
  previewBtn.className = "small-action-btn gallery-control-preview-btn";
  previewBtn.textContent = "Before/After";
  previewWrap.appendChild(previewBtn);

  const previewPanel = document.createElement("div");
  previewPanel.className = "gallery-control-preview-popover";
  previewPanel.hidden = true;

  const previewGrid = document.createElement("div");
  previewGrid.className = "gallery-control-preview-grid";

  const beforeBox = document.createElement("div");
  beforeBox.className = "gallery-control-preview-box";
  const beforeLabel = document.createElement("p");
  beforeLabel.className = "gallery-control-preview-label";
  beforeLabel.textContent = "Before";
  beforeBox.appendChild(beforeLabel);
  if (item.inputUrl) {
    const beforeImg = document.createElement("img");
    beforeImg.src = `${item.inputUrl}${item.inputUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
    beforeImg.alt = `Before image for ${item.visitorName || "Guest"}`;
    beforeBox.appendChild(beforeImg);
  } else {
    const beforeEmpty = document.createElement("p");
    beforeEmpty.className = "gallery-control-preview-empty";
    beforeEmpty.textContent = "Before image not available";
    beforeBox.appendChild(beforeEmpty);
  }
  previewGrid.appendChild(beforeBox);

  const afterBox = document.createElement("div");
  afterBox.className = "gallery-control-preview-box";
  const afterLabel = document.createElement("p");
  afterLabel.className = "gallery-control-preview-label";
  afterLabel.textContent = "After";
  afterBox.appendChild(afterLabel);
  if (item.outputUrl) {
    const afterImg = document.createElement("img");
    afterImg.src = `${item.outputUrl}${item.outputUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
    afterImg.alt = `After image for ${item.visitorName || "Guest"}`;
    afterBox.appendChild(afterImg);
  } else {
    const afterEmpty = document.createElement("p");
    afterEmpty.className = "gallery-control-preview-empty";
    afterEmpty.textContent = "After image not available";
    afterBox.appendChild(afterEmpty);
  }
  previewGrid.appendChild(afterBox);

  previewPanel.appendChild(previewGrid);
  previewWrap.appendChild(previewPanel);

  actionRow.appendChild(renameBtn);
  actionRow.appendChild(visibilityBtn);
  actionRow.appendChild(deleteBtn);
  actionRow.appendChild(previewWrap);
  meta.appendChild(actionRow);

  const status = document.createElement("p");
  status.className = "gallery-control-status";
  status.textContent = "";
  meta.appendChild(status);

  top.appendChild(meta);
  wrapper.appendChild(top);

  const actionButtons = [renameBtn, visibilityBtn, deleteBtn];

  renameBtn.addEventListener("click", async () => {
    await renameGalleryItem(item.jobId, nameInput.value, status, actionButtons);
  });

  visibilityBtn.addEventListener("click", async () => {
    const nextHidden = !Boolean(item.hidden);
    await setGalleryItemVisibility(item.jobId, nextHidden, status, actionButtons);
  });

  deleteBtn.addEventListener("click", async () => {
    const confirmDelete = window.confirm(`Delete gallery item ${item.jobId}? This also removes image files.`);
    if (!confirmDelete) {
      return;
    }
    await deleteGalleryItem(item.jobId, status, actionButtons);
  });

  let hidePreviewTimer = null;
  const showPreview = () => {
    if (hidePreviewTimer) {
      window.clearTimeout(hidePreviewTimer);
      hidePreviewTimer = null;
    }
    previewPanel.hidden = false;
  };

  const hidePreview = () => {
    hidePreviewTimer = window.setTimeout(() => {
      previewPanel.hidden = true;
    }, 90);
  };

  previewWrap.addEventListener("mouseenter", showPreview);
  previewWrap.addEventListener("mouseleave", hidePreview);
  previewBtn.addEventListener("focus", showPreview);
  previewBtn.addEventListener("blur", hidePreview);

  return wrapper;
}

function renderGalleryControlList() {
  if (!galleryControlList) {
    return;
  }

  galleryControlList.innerHTML = "";

  if (!Array.isArray(galleryControlItems) || galleryControlItems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "panel-hint";
    empty.textContent = "No gallery items yet.";
    galleryControlList.appendChild(empty);
    return;
  }

  galleryControlItems.forEach((item) => {
    galleryControlList.appendChild(createGalleryControlCard(item));
  });
}

async function loadGalleryControlItems({ silent = false } = {}) {
  if (!refreshGalleryControlBtn) {
    return;
  }

  refreshGalleryControlBtn.disabled = true;
  try {
    const response = await fetch("/gallery/items?includeHidden=true");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to load gallery items.");
    }

    const items = Array.isArray(data.items) ? data.items : [];
    galleryControlItems = sortGalleryControlItems(items);
    renderGalleryControlList();

    if (!silent) {
      appendEvent(`Loaded ${galleryControlItems.length} gallery item(s) for staff control.`);
    }
  } catch (error) {
    if (!silent) {
      appendEvent(error.message || "Failed to load gallery control list.", true);
    }
  } finally {
    refreshGalleryControlBtn.disabled = false;
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

  socket.onopen = () => {
    appendEvent("Live updates connected.");
    fetchQueueStatus({ silent: true });
  };

  socket.onclose = () => {
    appendEvent("Live updates disconnected. Reconnecting...", true);
    window.setTimeout(connectWebSocket, 3000);
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "generation_complete") {
        updateStatusFromResult({ status: "Completed", ...payload }, "ws");
        mergeGalleryControlItem(payload);
      } else if (payload.type === "generation_error") {
        setStatus("Error");
        jobIdText.textContent = payload.jobId || "-";
        stopElapsedTimer();
        setPreviewLoading(outputPreviewLink, false);
        appendEvent(`Error on ${payload.jobId || "unknown"}: ${payload.error || "Unknown error"}`, true);
      } else if (payload.type === "queue_updated") {
        applyQueueStatus(payload, { silent: true });
      } else if (payload.type === "job_started" && payload.job) {
        const startedJob = payload.job;
        if (currentJobId && startedJob.jobId === currentJobId) {
          setStatus("Processing");
          jobIdText.textContent = startedJob.jobId || "-";
          visitorText.textContent = startedJob.visitorName || visitorText.textContent;
          startElapsedTimer(startedJob.startedAt || null);
        }
        appendEvent(`Job started: ${startedJob.jobId}.`);
      } else if (payload.type === "job_failed" && payload.job) {
        const failedJob = payload.job;
        if (currentJobId && failedJob.jobId === currentJobId) {
          setStatus("Error");
          stopElapsedTimer();
          setPreviewLoading(outputPreviewLink, false);
        }
        appendEvent(`Job failed: ${failedJob.jobId} (${failedJob.error || "Unknown error"})`, true);
      } else if (payload.type === "job_cancelled" && payload.job) {
        const cancelledJob = payload.job;
        if (currentJobId && cancelledJob.jobId === currentJobId) {
          setStatus("Cancelled");
          stopElapsedTimer();
          setPreviewLoading(outputPreviewLink, false);
          finalDurationText.textContent = "-";
        }
        appendEvent(`Job cancelled: ${cancelledJob.jobId}.`, true);
      } else if (payload.type === "job_completed" && payload.job) {
        appendEvent(`Job completed: ${payload.job.jobId}.`);
      } else if (payload.type === "gallery_item_updated" && payload.item) {
        mergeGalleryControlItem(payload.item);
      } else if (payload.type === "gallery_item_deleted" && payload.jobId) {
        removeGalleryControlItem(payload.jobId);
      }
    } catch (error) {
      appendEvent("Malformed live event payload.", true);
    }
  };
}

function wirePreviewLinkSafety(linkEl) {
  linkEl.addEventListener("click", (event) => {
    if (linkEl.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
    }
  });
}

methodTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (loading) {
      return;
    }
    setActiveMethod(tab.dataset.method || "upload");
  });
});

if (drawingFileInput) {
  drawingFileInput.addEventListener("change", () => {
    const selectedFile = drawingFileInput.files[0];
    if (!selectedFile) {
      resetLocalInputPreviewUrl();
      setPreview(inputPreviewLink, inputPreviewImage, null);
      return;
    }

    resetLocalInputPreviewUrl();
    localInputPreviewUrl = URL.createObjectURL(selectedFile);
    setPreview(inputPreviewLink, inputPreviewImage, localInputPreviewUrl);
  });
}

[inputPreviewImage, outputPreviewImage].forEach((imageEl) => {
  imageEl.hidden = true;
  imageEl.addEventListener("load", () => {
    imageEl.hidden = false;
  });
  imageEl.addEventListener("error", () => {
    imageEl.hidden = true;
    if (imageEl === inputPreviewImage) {
      inputPreviewLink.classList.add("is-empty");
    } else {
      outputPreviewLink.classList.add("is-empty");
      outputPreviewLink.classList.remove("is-loading");
    }
  });
});

starGroup.querySelectorAll(".star-btn").forEach((button) => {
  button.addEventListener("click", () => {
    setSelectedRating(Number(button.dataset.star || "0"));
  });
});

if (refreshGalleryControlBtn) {
  refreshGalleryControlBtn.addEventListener("click", () => {
    loadGalleryControlItems();
  });
}

if (requestWebcamPermissionBtn) {
  requestWebcamPermissionBtn.addEventListener("click", () => {
    requestWebcamPermission({ silent: false });
  });
}

if (applyAutoReviewBtn) {
  applyAutoReviewBtn.addEventListener("click", () => {
    applyAutoReviewToForm();
  });
}

generateBtn.addEventListener("click", submitGeneration);
clearBtn.addEventListener("click", clearDashboard);
saveRatingBtn.addEventListener("click", saveRating);

renderTagCheckboxes();
setupLanHelper();
setActiveMethod("upload");
setStatus("Idle");
ratingSection.hidden = true;
renderAutoReview(null);
setPreview(inputPreviewLink, inputPreviewImage, null);
setPreview(outputPreviewLink, outputPreviewImage, null);
wirePreviewLinkSafety(inputPreviewLink);
wirePreviewLinkSafety(outputPreviewLink);
setWebcamPermissionState("unknown", "Camera permission: not requested.");

fetchGenerationEstimate().then((estimate) => {
  applyEstimate(estimate);
  appendEvent(`Loaded estimate from ${estimate.sampleCount} completed job(s).`);
});

loadGalleryControlItems({ silent: true });
fetchQueueStatus({ silent: true });
connectWebSocket();
