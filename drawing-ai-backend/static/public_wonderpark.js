const uploadForm = document.getElementById("uploadForm");
const customerNameInput = document.getElementById("customerName");
const fileInput = document.getElementById("fileInput");
const pickFileBtn = document.getElementById("pickFileBtn");
const dropzone = document.getElementById("dropzone");
const previewSection = document.getElementById("previewSection");
const previewCanvas = document.getElementById("previewCanvas");
const submitBtn = document.getElementById("submitBtn");
const warningBox = document.getElementById("warningBox");
const errorBox = document.getElementById("errorBox");
const uploadSection = document.getElementById("uploadSection");
const thankYouSection = document.getElementById("thankYouSection");
const submissionIdText = document.getElementById("submissionIdText");
const resultTitle = document.getElementById("resultTitle");
const resultInstruction = document.getElementById("resultInstruction");
const resultImageWrap = document.getElementById("resultImageWrap");
const resultImage = document.getElementById("resultImage");
const resultActions = document.getElementById("resultActions");
const approveShowcaseBtn = document.getElementById("approveShowcaseBtn");
const photoPrintBtn = document.getElementById("photoPrintBtn");
const regenerateImageBtn = document.getElementById("regenerateImageBtn");
const approveStatusText = document.getElementById("approveStatusText");
const animalUploadText = document.getElementById("animalUploadText");
const presetAnimalInput = document.getElementById("presetAnimalInput");
const paperTemplateIdInput = document.getElementById("paperTemplateIdInput");
const restartLink = document.querySelector(".restart-link");
const cameraSection = document.getElementById("cameraSection");
const cameraVideo = document.getElementById("cameraVideo");
const cameraPreviewImage = document.getElementById("cameraPreviewImage");
const cameraStatus = document.getElementById("cameraStatus");
const captureNowBtn = document.getElementById("captureNowBtn");
const rescanBtn = document.getElementById("rescanBtn");
const openGalleryBtn = document.getElementById("openGalleryBtn");
const cameraCaptureCanvas = document.getElementById("cameraCaptureCanvas");
const scanGuide = cameraSection ? cameraSection.querySelector(".scan-guide") : null;

const CAMERA_SCAN_INTERVAL_MS = 260;
const CAMERA_READY_STREAK_REQUIRED = 2;
const CAMERA_ANALYSIS_WIDTH = 320;
const CAMERA_ANALYSIS_HEIGHT = 240;
const CAMERA_MAX_CAPTURE_DIMENSION = 2048;
const CAMERA_MOTION_THRESHOLD = 12.5;
const CAMERA_READY_SCORE_THRESHOLD = 5;
const MANUAL_CAPTURE_COUNTDOWN_SECONDS = 3;
const WONDERPARK_STATUS_POLL_MS = 2200;
const WONDERPARK_QUEUE_ESTIMATE_TICK_MS = 1000;
const WONDERPARK_STATUS_ENDPOINT_HINT = "Status tracking is unavailable right now. Please ask staff to restart the backend service.";

let config = {
  enabled: true,
  maxUploadBytes: 12 * 1024 * 1024,
  minRecommendedWidth: 1200,
  minRecommendedHeight: 900,
};

let sourceFile = null;
let sourceImage = null;
let objectUrl = "";
let uploadInProgress = false;
let cameraStream = null;
let cameraScanTimer = null;
let cameraStarting = false;
let cameraReadyStreak = 0;
let cameraLastSignature = null;
let cameraAutoCaptured = false;
let galleryModeEnabled = false;
let manualCaptureCountdownTimer = null;
let manualCaptureCountdownRemaining = 0;
let latestSubmissionId = "";
let latestSubmissionStatus = "";
let statusPollTimer = null;
let approvalInProgress = false;
let regenerateInProgress = false;
let submissionStatusEndpointUnavailable = false;
let queueEstimateRemainingSeconds = null;
let queueEstimateAnchorMs = 0;
let queueEstimatePosition = 0;
let queueEstimateTicker = null;
let queueEstimateRefreshInFlight = false;

const cameraAnalysisCanvas = document.createElement("canvas");
cameraAnalysisCanvas.width = CAMERA_ANALYSIS_WIDTH;
cameraAnalysisCanvas.height = CAMERA_ANALYSIS_HEIGHT;
const cameraAnalysisContext = cameraAnalysisCanvas.getContext("2d", { willReadFrequently: true });

const ANIMAL_VALUES = new Set(["lion", "zebra", "elephant", "tiger", "unknown"]);
const pageContext = {
  presetAnimal: "unknown",
  paperTemplateId: "",
};

function normalizeAnimalValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized || !ANIMAL_VALUES.has(normalized)) {
    return "";
  }
  return normalized;
}

function readAnimalFromPath(pathname) {
  const segments = String(pathname || "")
    .split("/")
    .filter(Boolean);
  if (segments.length < 3) {
    return "";
  }
  if (segments[0] !== "public" || segments[1] !== "wonderpark") {
    return "";
  }
  return normalizeAnimalValue(segments[2]);
}

function readAnimalFromQuery(search) {
  const params = new URLSearchParams(search || "");
  return normalizeAnimalValue(params.get("animal"));
}

function readTemplateIdFromQuery(search) {
  const params = new URLSearchParams(search || "");
  const raw = params.get("paperTemplateId") || params.get("templateId") || "";
  return String(raw).trim();
}

function updateAnimalText(animal) {
  const normalized = normalizeAnimalValue(animal);
  if (!animalUploadText) {
    return;
  }
  if (normalized === "lion") {
    animalUploadText.textContent = "Upload your colored lion drawing";
    return;
  }
  if (normalized === "zebra") {
    animalUploadText.textContent = "Upload your colored zebra drawing";
    return;
  }
  if (normalized === "elephant") {
    animalUploadText.textContent = "Upload your colored elephant drawing";
    return;
  }
  if (normalized === "tiger") {
    animalUploadText.textContent = "Upload your colored tiger drawing";
    return;
  }
  animalUploadText.textContent = "Upload your colored drawing";
}

function initializeUploadContext() {
  const queryAnimal = readAnimalFromQuery(window.location.search);
  const pathAnimal = readAnimalFromPath(window.location.pathname);
  const resolvedAnimal = queryAnimal || pathAnimal || "unknown";
  const templateId = readTemplateIdFromQuery(window.location.search);

  pageContext.presetAnimal = resolvedAnimal;
  pageContext.paperTemplateId = templateId;

  if (presetAnimalInput) {
    presetAnimalInput.value = resolvedAnimal;
  }
  if (paperTemplateIdInput) {
    paperTemplateIdInput.value = templateId;
  }
  if (restartLink) {
    const restartBase = resolvedAnimal && resolvedAnimal !== "unknown"
      ? `/public/wonderpark/${resolvedAnimal}`
      : "/public/wonderpark";
    restartLink.setAttribute("href", restartBase);
  }
  updateAnimalText(resolvedAnimal);
}

function showError(message) {
  errorBox.hidden = false;
  errorBox.textContent = String(message || "Unexpected error.");
}

function clearError() {
  errorBox.hidden = true;
  errorBox.textContent = "";
}

function stopSubmissionPolling() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
  stopQueueEstimateTicker();
}

function safePositiveInt(value) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue) || numberValue <= 0) {
    return 0;
  }
  return Math.max(1, Math.round(numberValue));
}

function normalizeQueueJobId(value) {
  return String(value || "").trim();
}

function parseQueueTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return Number.MAX_SAFE_INTEGER;
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) {
    return Number.MAX_SAFE_INTEGER;
  }
  return parsed;
}

function formatQueueDuration(seconds) {
  const safe = Math.max(0, Math.round(Number(seconds) || 0));
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  if (minutes <= 0) {
    return `${remainder}s`;
  }
  return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
}

function getQueueEstimateRemainingSeconds() {
  if (queueEstimateRemainingSeconds === null) {
    return null;
  }
  const elapsedSeconds = Math.floor((Date.now() - queueEstimateAnchorMs) / 1000);
  return Math.max(0, queueEstimateRemainingSeconds - Math.max(0, elapsedSeconds));
}

function renderQueueCountdownStatus() {
  if (!approveStatusText) {
    return;
  }
  const remaining = getQueueEstimateRemainingSeconds();
  approveStatusText.hidden = false;
  if (remaining === null) {
    approveStatusText.textContent = "Generating your artwork...";
    return;
  }
  if (remaining <= 0) {
    approveStatusText.textContent = "Generating your artwork... Finalizing output.";
    return;
  }
  let statusText = `Generating your artwork... Estimated wait: ${formatQueueDuration(remaining)}`;
  if (queueEstimatePosition > 0) {
    statusText += ` (queue #${queueEstimatePosition})`;
  }
  approveStatusText.textContent = statusText;
}

function stopQueueEstimateTicker() {
  if (queueEstimateTicker) {
    clearInterval(queueEstimateTicker);
    queueEstimateTicker = null;
  }
  queueEstimateRemainingSeconds = null;
  queueEstimateAnchorMs = 0;
  queueEstimatePosition = 0;
  queueEstimateRefreshInFlight = false;
}

function setQueueEstimateCountdown(remainingSeconds, queuePosition) {
  const safeSeconds = safePositiveInt(remainingSeconds);
  if (safeSeconds <= 0) {
    return;
  }
  queueEstimateRemainingSeconds = safeSeconds;
  queueEstimateAnchorMs = Date.now();
  queueEstimatePosition = safePositiveInt(queuePosition);
  if (!queueEstimateTicker) {
    queueEstimateTicker = setInterval(() => {
      renderQueueCountdownStatus();
    }, WONDERPARK_QUEUE_ESTIMATE_TICK_MS);
  }
  renderQueueCountdownStatus();
}

function resolveSubmissionQueueJobId(submission) {
  const latestJobId = normalizeQueueJobId(submission?.latest_job_id);
  if (latestJobId) {
    return latestJobId;
  }
  return normalizeQueueJobId(submission?.queue_job_id);
}

function isSubmissionWaiting(submission) {
  const processingStatus = String(submission?.processing_status || "").toLowerCase();
  const outputUrl = String(
    submission?.generated_image_url
    || submission?.latest_output_url
    || submission?.approved_image_url
    || ""
  ).trim();
  return processingStatus !== "completed" || !outputUrl;
}

function resolveQueueEstimateSecondsForJob(job, fallbackPerJob) {
  const estimateSeconds = safePositiveInt(job?.estimatedSeconds);
  if (estimateSeconds > 0) {
    return estimateSeconds;
  }
  return safePositiveInt(fallbackPerJob);
}

function buildQueueEtaFromPayload(payload, targetJobId) {
  const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
  const currentJobId = normalizeQueueJobId(payload?.currentJob);
  const queueLength = Math.max(0, Math.round(Number(payload?.queueLength) || 0));
  const totalWaitSeconds = Math.max(0, Math.round(Number(payload?.estimatedWaitSeconds) || 0));
  const activeCount = queueLength + (currentJobId ? 1 : 0);
  const fallbackPerJob = activeCount > 0 ? Math.max(1, Math.round(totalWaitSeconds / activeCount)) : 0;

  let processingJob = null;
  const queuedJobs = [];
  for (const job of jobs) {
    if (!job || typeof job !== "object") {
      continue;
    }
    const status = String(job.status || "").toLowerCase();
    if (status === "processing") {
      if (!processingJob) {
        processingJob = job;
      }
      if (currentJobId && normalizeQueueJobId(job.jobId) === currentJobId) {
        processingJob = job;
      }
      continue;
    }
    if (status === "queued") {
      queuedJobs.push(job);
    }
  }
  queuedJobs.sort((left, right) => {
    const leftTs = parseQueueTimestamp(left?.queuedAt || left?.createdAt);
    const rightTs = parseQueueTimestamp(right?.queuedAt || right?.createdAt);
    if (leftTs !== rightTs) {
      return leftTs - rightTs;
    }
    return normalizeQueueJobId(left?.jobId).localeCompare(normalizeQueueJobId(right?.jobId));
  });

  const orderedJobs = [];
  if (processingJob) {
    orderedJobs.push(processingJob);
  }
  for (const queuedJob of queuedJobs) {
    const queuedId = normalizeQueueJobId(queuedJob?.jobId);
    const processingId = normalizeQueueJobId(processingJob?.jobId);
    if (queuedId && queuedId === processingId) {
      continue;
    }
    orderedJobs.push(queuedJob);
  }

  const targetId = normalizeQueueJobId(targetJobId);
  const targetIndex = targetId
    ? orderedJobs.findIndex((job) => normalizeQueueJobId(job?.jobId) === targetId)
    : -1;
  if (targetIndex >= 0) {
    let countdownSeconds = 0;
    for (let index = 0; index <= targetIndex; index += 1) {
      countdownSeconds += resolveQueueEstimateSecondsForJob(orderedJobs[index], fallbackPerJob);
    }
    if (countdownSeconds <= 0) {
      countdownSeconds = totalWaitSeconds;
    }
    return {
      countdownSeconds,
      queuePosition: targetIndex + 1,
    };
  }

  if (totalWaitSeconds > 0) {
    return {
      countdownSeconds: totalWaitSeconds,
      queuePosition: 0,
    };
  }
  return {
    countdownSeconds: 0,
    queuePosition: 0,
  };
}

async function refreshQueueEstimateForSubmission(submission) {
  if (!submission || queueEstimateRefreshInFlight) {
    return;
  }
  if (!isSubmissionWaiting(submission)) {
    return;
  }
  queueEstimateRefreshInFlight = true;
  try {
    const targetJobId = resolveSubmissionQueueJobId(submission);
    const response = await fetch("/api/queue/status", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json().catch(() => ({}));
    const eta = buildQueueEtaFromPayload(payload, targetJobId);
    if (eta.countdownSeconds > 0) {
      setQueueEstimateCountdown(eta.countdownSeconds, eta.queuePosition);
      return;
    }
    renderQueueCountdownStatus();
  } catch (_error) {
    renderQueueCountdownStatus();
  } finally {
    queueEstimateRefreshInFlight = false;
  }
}

function setResultReadyUi() {
  if (resultTitle) {
    resultTitle.textContent = "Your AI artwork is ready.";
  }
  if (resultInstruction) {
    resultInstruction.textContent = "Add to showcase, or regenerate if you want another result.";
  }
}

function setResultWaitingUi() {
  if (resultTitle) {
    resultTitle.textContent = "Your artwork has been submitted successfully.";
  }
  if (resultInstruction) {
    resultInstruction.textContent = "Please wait while the AI transforms your artwork.";
  }
}

function setResultErrorUi(message) {
  if (resultTitle) {
    resultTitle.textContent = "Generation failed.";
  }
  if (resultInstruction) {
    resultInstruction.textContent = String(message || "Please upload again.");
  }
}

function setResultActionsState({ showApprove = false, showRegenerate = false, showPhoto = false, photoJobId = "" } = {}) {
  const hasAction = Boolean(showApprove || showRegenerate || showPhoto);
  if (resultActions) {
    resultActions.hidden = !hasAction;
  }
  if (approveShowcaseBtn) {
    approveShowcaseBtn.hidden = !showApprove;
    approveShowcaseBtn.disabled = !showApprove || approvalInProgress || regenerateInProgress;
  }
  if (regenerateImageBtn) {
    regenerateImageBtn.hidden = !showRegenerate;
    regenerateImageBtn.disabled = !showRegenerate || regenerateInProgress || approvalInProgress;
  }
  if (photoPrintBtn) {
    const safePhotoJobId = normalizeQueueJobId(photoJobId);
    photoPrintBtn.hidden = !showPhoto || !safePhotoJobId;
    photoPrintBtn.href = safePhotoJobId ? `/photo/${encodeURIComponent(safePhotoJobId)}` : "#";
  }
}

function renderSubmissionResult(submission) {
  const processingStatus = String(submission?.processing_status || "").toLowerCase();
  const resultStatus = String(submission?.result_status || "").toLowerCase();
  const outputUrl = String(
    submission?.generated_image_url
    || submission?.latest_output_url
    || submission?.approved_image_url
    || ""
  ).trim();
  const photoJobId = resolveSubmissionQueueJobId(submission);

  latestSubmissionStatus = processingStatus;

  if (processingStatus === "failed") {
    stopQueueEstimateTicker();
    if (resultImageWrap) {
      resultImageWrap.hidden = true;
    }
    setResultActionsState({ showApprove: false, showRegenerate: true });
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = "Generation failed. Tap Regenerate Image to try again.";
    }
    setResultErrorUi(submission?.error || "Generation failed.");
    return;
  }

  if (processingStatus !== "completed" || !outputUrl) {
    if (resultImageWrap) {
      resultImageWrap.hidden = true;
    }
    setResultActionsState({ showApprove: false, showRegenerate: false });
    renderQueueCountdownStatus();
    setResultWaitingUi();
    void refreshQueueEstimateForSubmission(submission);
    return;
  }

  stopQueueEstimateTicker();
  if (resultImage) {
    resultImage.src = outputUrl;
  }
  if (resultImageWrap) {
    resultImageWrap.hidden = false;
  }
  setResultReadyUi();

  const approved = resultStatus === "approved" || Boolean(submission?.showcase_visible);
  if (approved) {
    setResultActionsState({ showApprove: false, showRegenerate: false, showPhoto: true, photoJobId });
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = "Thank you! Your artwork has been added to the showcase.";
    }
    stopSubmissionPolling();
    return;
  }

  setResultActionsState({ showApprove: true, showRegenerate: true, showPhoto: true, photoJobId });
  if (approveStatusText) {
    approveStatusText.hidden = false;
    approveStatusText.textContent = "Review your image, then Add to Showcase or Regenerate.";
  }
}

async function fetchSubmissionStatus(submissionId) {
  const encoded = encodeURIComponent(String(submissionId || "").trim());
  const response = await fetch(`/api/public/wonderpark/submissions/${encoded}?absolute=1`, {
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = String(payload?.detail || "").trim();
    if (response.status === 404 && detail.toLowerCase() === "not found") {
      const error = new Error(WONDERPARK_STATUS_ENDPOINT_HINT);
      error.code = "status-endpoint-unavailable";
      throw error;
    }
    if (response.status === 404) {
      const error = new Error("Submission not found. Please upload again.");
      error.code = "submission-not-found";
      throw error;
    }
    throw new Error(detail || "Unable to fetch submission status.");
  }
  return payload?.submission || null;
}

async function refreshSubmissionStatus() {
  if (!latestSubmissionId || submissionStatusEndpointUnavailable) {
    return;
  }
  try {
    const submission = await fetchSubmissionStatus(latestSubmissionId);
    if (!submission) {
      return;
    }
    renderSubmissionResult(submission);
  } catch (error) {
    const code = String(error?.code || "");
    if (code === "status-endpoint-unavailable" || code === "submission-not-found") {
      submissionStatusEndpointUnavailable = true;
      stopSubmissionPolling();
    }
    stopQueueEstimateTicker();
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = error?.message || "Unable to fetch latest status.";
    }
  }
}

function startSubmissionPolling(submissionId) {
  latestSubmissionId = String(submissionId || "").trim();
  submissionStatusEndpointUnavailable = false;
  stopSubmissionPolling();
  if (!latestSubmissionId) {
    return;
  }
  void refreshSubmissionStatus();
  statusPollTimer = setInterval(() => {
    void refreshSubmissionStatus();
  }, WONDERPARK_STATUS_POLL_MS);
}

async function approveCurrentSubmission() {
  if (!latestSubmissionId || approvalInProgress || regenerateInProgress) {
    return;
  }
  let approvalSucceeded = false;
  approvalInProgress = true;
  if (approveShowcaseBtn) {
    approveShowcaseBtn.disabled = true;
    approveShowcaseBtn.textContent = "Adding...";
  }
  if (regenerateImageBtn) {
    regenerateImageBtn.disabled = true;
  }
  if (approveStatusText) {
    approveStatusText.hidden = false;
    approveStatusText.textContent = "Adding your artwork to showcase...";
  }

  try {
    const encoded = encodeURIComponent(latestSubmissionId);
    const response = await fetch(`/api/public/wonderpark/submissions/${encoded}/approve?absolute=1`, {
      method: "POST",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(payload?.detail || "Unable to add artwork to showcase."));
    }
    const submission = payload?.submission || null;
    if (submission) {
      renderSubmissionResult(submission);
    }
    approvalSucceeded = true;
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = String(
        payload?.message || "Thank you! Your artwork has been added to the showcase."
      );
    }
  } catch (error) {
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = error?.message || "Unable to add to showcase.";
    }
    if (approveShowcaseBtn) {
      approveShowcaseBtn.disabled = false;
    }
    if (regenerateImageBtn) {
      regenerateImageBtn.disabled = false;
    }
  } finally {
    approvalInProgress = false;
    if (approveShowcaseBtn) {
      approveShowcaseBtn.textContent = "Add to Showcase";
    }
    if (!approvalSucceeded && latestSubmissionStatus === "completed") {
      setResultActionsState({ showApprove: true, showRegenerate: true });
    }
  }
}

async function regenerateCurrentSubmission() {
  if (!latestSubmissionId || regenerateInProgress || approvalInProgress) {
    return;
  }
  regenerateInProgress = true;
  if (regenerateImageBtn) {
    regenerateImageBtn.disabled = true;
    regenerateImageBtn.textContent = "Regenerating...";
  }
  if (approveShowcaseBtn) {
    approveShowcaseBtn.disabled = true;
  }
  if (approveStatusText) {
    approveStatusText.hidden = false;
    approveStatusText.textContent = "Submitting regeneration request...";
  }
  stopQueueEstimateTicker();

  try {
    const encoded = encodeURIComponent(latestSubmissionId);
    const response = await fetch(`/api/public/wonderpark/submissions/${encoded}/regenerate?absolute=1`, {
      method: "POST",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(payload?.detail || "Unable to regenerate artwork."));
    }
    if (payload?.ok === false) {
      throw new Error(String(payload?.message || payload?.submission?.error || "Unable to regenerate artwork."));
    }
    const submission = payload?.submission || null;
    if (submission) {
      renderSubmissionResult(submission);
    }
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = String(payload?.message || "Regenerating your artwork...");
    }
    startSubmissionPolling(latestSubmissionId);
  } catch (error) {
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = error?.message || "Unable to regenerate artwork.";
    }
  } finally {
    regenerateInProgress = false;
    if (regenerateImageBtn) {
      regenerateImageBtn.textContent = "Regenerate Image";
    }
    if (latestSubmissionStatus === "completed") {
      setResultActionsState({ showApprove: true, showRegenerate: true });
    } else if (latestSubmissionStatus === "failed") {
      setResultActionsState({ showApprove: false, showRegenerate: true });
    }
  }
}

function showWarnings(messages) {
  const rows = Array.isArray(messages) ? messages.filter(Boolean) : [];
  if (rows.length === 0) {
    warningBox.hidden = true;
    warningBox.textContent = "";
    return;
  }
  warningBox.hidden = false;
  warningBox.textContent = rows.join(" ");
}

function setCameraStatus(message, tone = "info") {
  if (!cameraStatus) {
    return;
  }
  cameraStatus.classList.remove("is-warn", "is-error");
  if (tone === "warn") {
    cameraStatus.classList.add("is-warn");
  } else if (tone === "error") {
    cameraStatus.classList.add("is-error");
  }
  cameraStatus.textContent = String(message || "");
}

function showDropzone(show) {
  if (!dropzone) {
    return;
  }
  dropzone.hidden = !show;
}

function showPreviewInCameraFrame(imageUrl) {
  if (cameraPreviewImage) {
    cameraPreviewImage.src = String(imageUrl || "");
    cameraPreviewImage.hidden = !Boolean(imageUrl);
  }
  if (cameraVideo) {
    cameraVideo.hidden = Boolean(imageUrl);
  }
  if (scanGuide) {
    scanGuide.hidden = Boolean(imageUrl);
  }
}

function resetCameraFrameToLiveView() {
  if (cameraPreviewImage) {
    cameraPreviewImage.hidden = true;
    cameraPreviewImage.src = "";
  }
  if (cameraVideo) {
    cameraVideo.hidden = false;
  }
  if (scanGuide) {
    scanGuide.hidden = false;
  }
}

function setGalleryMode(enabled) {
  galleryModeEnabled = Boolean(enabled);
  cancelManualCaptureCountdown();
  if (!galleryModeEnabled) {
    resetCameraFrameToLiveView();
  }
  showDropzone(galleryModeEnabled);
  if (openGalleryBtn) {
    openGalleryBtn.textContent = galleryModeEnabled ? "Use Camera Scan" : "Use Gallery Image";
  }
  if (captureNowBtn) {
    captureNowBtn.hidden = galleryModeEnabled;
    captureNowBtn.disabled = galleryModeEnabled || !cameraStream;
  }
}

function drawPreview() {
  if (!sourceImage || !previewCanvas) {
    return;
  }
  const context = previewCanvas.getContext("2d");
  if (!context) {
    return;
  }

  context.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
  context.fillStyle = "#eef4fb";
  context.fillRect(0, 0, previewCanvas.width, previewCanvas.height);

  const ratio = Math.min(previewCanvas.width / sourceImage.width, previewCanvas.height / sourceImage.height);
  const dw = sourceImage.width * ratio;
  const dh = sourceImage.height * ratio;
  const dx = (previewCanvas.width - dw) / 2;
  const dy = (previewCanvas.height - dh) / 2;

  context.drawImage(sourceImage, 0, 0, sourceImage.width, sourceImage.height, dx, dy, dw, dh);
  context.strokeStyle = "#1f93ff";
  context.lineWidth = 2;
  context.strokeRect(dx, dy, dw, dh);
}

function evaluateWarnings(image) {
  if (!image) {
    return [];
  }
  const warnings = [
    "Please upload a flat artwork scan or straight photo for best results.",
  ];
  if (image.width < Number(config.minRecommendedWidth || 1200) || image.height < Number(config.minRecommendedHeight || 900)) {
    warnings.push("Resolution is low; clearer scan quality gives better AI output.");
  }

  const sampleCanvas = document.createElement("canvas");
  sampleCanvas.width = 64;
  sampleCanvas.height = 64;
  const ctx = sampleCanvas.getContext("2d");
  if (ctx) {
    ctx.drawImage(image, 0, 0, 64, 64);
    const data = ctx.getImageData(0, 0, 64, 64).data;
    let sum = 0;
    let sumSq = 0;
    for (let i = 0; i < data.length; i += 4) {
      const luma = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      sum += luma;
      sumSq += luma * luma;
    }
    const count = data.length / 4;
    const mean = count > 0 ? sum / count : 0;
    const variance = count > 0 ? (sumSq / count) - (mean * mean) : 0;
    const std = Math.sqrt(Math.max(0, variance));
    if (mean < 40) {
      warnings.push("Image appears very dark. Try brighter lighting or scanner mode.");
    }
    if (std < 7 && (mean > 235 || mean < 20)) {
      warnings.push("Image looks blank or nearly blank. Please check before submit.");
    }
  }
  return warnings;
}

async function fileToImage(file) {
  if (!file) {
    throw new Error("No file selected.");
  }
  if (file.size > Number(config.maxUploadBytes || 0)) {
    throw new Error("File is too large.");
  }
  if (!/^image\/(jpeg|png|webp)$/i.test(file.type || "")) {
    throw new Error("Please upload JPG, PNG, or WEBP image.");
  }

  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = "";
  }
  objectUrl = URL.createObjectURL(file);
  const image = await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Unable to read image."));
    img.src = objectUrl;
  });
  return image;
}

function getCropRect(image) {
  return {
    sx: 0,
    sy: 0,
    sw: Math.max(12, image.width),
    sh: Math.max(12, image.height),
  };
}

async function createProcessedBlob(image) {
  const crop = getCropRect(image);
  const maxDimension = CAMERA_MAX_CAPTURE_DIMENSION;
  const scale = Math.min(1, maxDimension / Math.max(crop.sw, crop.sh));
  const width = Math.max(24, Math.round(crop.sw * scale));
  const height = Math.max(24, Math.round(crop.sh * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Unable to prepare image.");
  }
  ctx.drawImage(image, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, width, height);

  const blob = await new Promise((resolve) => {
    canvas.toBlob((output) => resolve(output), "image/png");
  });
  if (!blob) {
    throw new Error("Failed to compress image.");
  }
  return blob;
}

function stopCameraScan({ keepStatus = false } = {}) {
  cancelManualCaptureCountdown();
  if (cameraScanTimer) {
    clearInterval(cameraScanTimer);
    cameraScanTimer = null;
  }
  if (cameraStream) {
    const tracks = cameraStream.getTracks();
    tracks.forEach((track) => {
      try {
        track.stop();
      } catch (_error) {
        // Ignore.
      }
    });
    cameraStream = null;
  }
  if (cameraVideo) {
    cameraVideo.srcObject = null;
  }
  if (captureNowBtn) {
    captureNowBtn.disabled = true;
  }
  cameraReadyStreak = 0;
  cameraLastSignature = null;
  if (!keepStatus) {
    setCameraStatus("");
  }
}

function cancelManualCaptureCountdown() {
  if (manualCaptureCountdownTimer) {
    clearInterval(manualCaptureCountdownTimer);
    manualCaptureCountdownTimer = null;
  }
  manualCaptureCountdownRemaining = 0;
}

function canManualCapture() {
  return Boolean(cameraStream && cameraVideo && !galleryModeEnabled && !cameraStarting);
}

function setManualCaptureButtonEnabled(enabled) {
  if (!captureNowBtn) {
    return;
  }
  captureNowBtn.disabled = !enabled;
}

function scoreCameraFrame(imageData, previousSignature) {
  const { data, width, height } = imageData;
  let samples = 0;
  let lumaSum = 0;
  let lumaSqSum = 0;
  let whiteCount = 0;
  let colorfulCount = 0;
  let edgeCount = 0;
  let motionSum = 0;
  let motionCount = 0;
  let signatureIndex = 0;
  const signature = [];
  const step = 4;

  for (let y = 0; y < height; y += step) {
    for (let x = 0; x < width; x += step) {
      const idx = (y * width + x) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];
      const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      const rgbMax = Math.max(r, g, b);
      const rgbMin = Math.min(r, g, b);
      const sat = rgbMax - rgbMin;

      signature.push(luma);
      if (Array.isArray(previousSignature) && previousSignature.length > signatureIndex) {
        motionSum += Math.abs(luma - previousSignature[signatureIndex]);
        motionCount += 1;
      }
      signatureIndex += 1;

      samples += 1;
      lumaSum += luma;
      lumaSqSum += luma * luma;
      if (luma > 228) {
        whiteCount += 1;
      }
      if (sat > 26) {
        colorfulCount += 1;
      }

      if (x + step < width) {
        const idxRight = idx + (step * 4);
        const lumaRight = (
          0.2126 * data[idxRight]
          + 0.7152 * data[idxRight + 1]
          + 0.0722 * data[idxRight + 2]
        );
        if (Math.abs(luma - lumaRight) > 22) {
          edgeCount += 1;
        }
      }
      if (y + step < height) {
        const idxDown = idx + ((step * width) * 4);
        const lumaDown = (
          0.2126 * data[idxDown]
          + 0.7152 * data[idxDown + 1]
          + 0.0722 * data[idxDown + 2]
        );
        if (Math.abs(luma - lumaDown) > 22) {
          edgeCount += 1;
        }
      }
    }
  }

  const mean = samples > 0 ? (lumaSum / samples) : 0;
  const variance = samples > 0 ? ((lumaSqSum / samples) - (mean * mean)) : 0;
  const std = Math.sqrt(Math.max(0, variance));
  const whiteRatio = samples > 0 ? (whiteCount / samples) : 0;
  const colorRatio = samples > 0 ? (colorfulCount / samples) : 0;
  const edgeRatio = samples > 0 ? (edgeCount / (samples * 2)) : 0;
  const motion = motionCount > 0 ? (motionSum / motionCount) : 999;

  const hasPrevSignature = Array.isArray(previousSignature) && previousSignature.length > 0;
  const brightnessOk = mean > 35 && mean < 245;
  const contrastOk = std > 12 && std < 125;
  const whiteOk = whiteRatio > 0.02 && whiteRatio < 0.96;
  const colorOk = colorRatio > 0.004;
  const edgesOk = edgeRatio > 0.035;
  const motionOk = !hasPrevSignature || motion < CAMERA_MOTION_THRESHOLD;
  const nonBlankOk = whiteRatio < 0.985 && (std > 8 || edgeRatio > 0.02 || colorRatio > 0.002);
  const readinessChecks = [brightnessOk, contrastOk, whiteOk, colorOk, edgesOk, motionOk, nonBlankOk];
  const readyScore = readinessChecks.reduce((total, passed) => total + (passed ? 1 : 0), 0);

  const ready = Boolean(
    hasPrevSignature
    && nonBlankOk
    && motionOk
    && readyScore >= CAMERA_READY_SCORE_THRESHOLD
  );

  return {
    ready,
    mean,
    std,
    whiteRatio,
    colorRatio,
    edgeRatio,
    motion,
    readyScore,
    hasPrevSignature,
    signature,
  };
}

async function captureCameraFrame() {
  if (!cameraVideo || !cameraCaptureCanvas) {
    return;
  }
  const videoWidth = Math.max(320, Number(cameraVideo.videoWidth || 0));
  const videoHeight = Math.max(240, Number(cameraVideo.videoHeight || 0));
  const videoRect = cameraVideo.getBoundingClientRect();
  const guideRect = scanGuide ? scanGuide.getBoundingClientRect() : null;
  const ctx = cameraCaptureCanvas.getContext("2d");
  if (!ctx) {
    return;
  }

  let sx = 0;
  let sy = 0;
  let sw = videoWidth;
  let sh = videoHeight;

  if (guideRect && videoRect.width > 1 && videoRect.height > 1) {
    const containerWidth = videoRect.width;
    const containerHeight = videoRect.height;
    const scale = Math.max(containerWidth / videoWidth, containerHeight / videoHeight);
    const renderedWidth = videoWidth * scale;
    const renderedHeight = videoHeight * scale;
    const offsetX = (containerWidth - renderedWidth) / 2;
    const offsetY = (containerHeight - renderedHeight) / 2;

    const guideX = guideRect.left - videoRect.left;
    const guideY = guideRect.top - videoRect.top;
    const guideW = guideRect.width;
    const guideH = guideRect.height;

    sx = (guideX - offsetX) / scale;
    sy = (guideY - offsetY) / scale;
    sw = guideW / scale;
    sh = guideH / scale;

    sx = Math.max(0, Math.min(videoWidth - 8, sx));
    sy = Math.max(0, Math.min(videoHeight - 8, sy));
    sw = Math.max(8, Math.min(videoWidth - sx, sw));
    sh = Math.max(8, Math.min(videoHeight - sy, sh));
  }

  const scaleToMax = Math.min(1, CAMERA_MAX_CAPTURE_DIMENSION / Math.max(sw, sh));
  const outputWidth = Math.max(320, Math.round(sw * scaleToMax));
  const outputHeight = Math.max(240, Math.round(sh * scaleToMax));
  cameraCaptureCanvas.width = outputWidth;
  cameraCaptureCanvas.height = outputHeight;
  ctx.drawImage(cameraVideo, sx, sy, sw, sh, 0, 0, outputWidth, outputHeight);

  const blob = await new Promise((resolve) => {
    cameraCaptureCanvas.toBlob((output) => resolve(output), "image/jpeg", 0.95);
  });
  if (!blob) {
    throw new Error("Unable to capture camera frame.");
  }
  return new File([blob], `camera_scan_${Date.now()}.jpg`, { type: "image/jpeg" });
}

async function onArtworkDetected(trigger = "auto") {
  if (cameraAutoCaptured) {
    return;
  }
  cancelManualCaptureCountdown();
  cameraAutoCaptured = true;
  if (cameraScanTimer) {
    clearInterval(cameraScanTimer);
    cameraScanTimer = null;
  }

  setCameraStatus(trigger === "manual" ? "Capturing..." : "Artwork detected. Capturing...");
  try {
    const file = await captureCameraFrame();
    const previewReady = await setPreviewFromFile(file, { showPreviewPanel: false });
    if (!previewReady) {
      throw new Error("Preview failed");
    }
    stopCameraScan({ keepStatus: true });
    setCameraStatus("Captured successfully. Adjust crop if needed, then submit.");
    if (rescanBtn) {
      rescanBtn.hidden = false;
    }
  } catch (error) {
    cameraAutoCaptured = false;
    setCameraStatus("Capture failed. Please scan again or use gallery image.", "error");
    setManualCaptureButtonEnabled(canManualCapture());
    showDropzone(true);
  }
}

function startManualCaptureCountdown() {
  if (cameraAutoCaptured || manualCaptureCountdownTimer) {
    return;
  }
  if (!canManualCapture()) {
    setCameraStatus("Camera is not ready yet. Please wait a moment.", "warn");
    return;
  }

  manualCaptureCountdownRemaining = MANUAL_CAPTURE_COUNTDOWN_SECONDS;
  setManualCaptureButtonEnabled(false);
  setCameraStatus(`Snapping in ${manualCaptureCountdownRemaining}... Hold still.`);

  manualCaptureCountdownTimer = setInterval(() => {
    manualCaptureCountdownRemaining -= 1;
    if (manualCaptureCountdownRemaining > 0) {
      setCameraStatus(`Snapping in ${manualCaptureCountdownRemaining}... Hold still.`);
      return;
    }
    cancelManualCaptureCountdown();
    setCameraStatus("Capturing now...");
    void onArtworkDetected("manual");
  }, 1000);
}

function scanCameraFrame() {
  if (!cameraAnalysisContext || !cameraVideo) {
    return;
  }
  if (!cameraVideo.videoWidth || !cameraVideo.videoHeight) {
    return;
  }

  cameraAnalysisContext.drawImage(
    cameraVideo,
    0,
    0,
    CAMERA_ANALYSIS_WIDTH,
    CAMERA_ANALYSIS_HEIGHT,
  );
  const imageData = cameraAnalysisContext.getImageData(
    0,
    0,
    CAMERA_ANALYSIS_WIDTH,
    CAMERA_ANALYSIS_HEIGHT,
  );
  const score = scoreCameraFrame(imageData, cameraLastSignature);
  cameraLastSignature = score.signature;

  if (score.ready) {
    cameraReadyStreak += 1;
    if (cameraReadyStreak >= CAMERA_READY_STREAK_REQUIRED) {
      void onArtworkDetected();
      return;
    }
    setCameraStatus(
      `Artwork detected. Hold still... (${cameraReadyStreak}/${CAMERA_READY_STREAK_REQUIRED})`,
    );
    return;
  }

  cameraReadyStreak = 0;
  if (!score.hasPrevSignature) {
    setCameraStatus("Camera ready. Hold your artwork inside the frame.");
    return;
  }
  if (score.motion >= CAMERA_MOTION_THRESHOLD) {
    setCameraStatus("Hold still for auto capture...");
    return;
  }
  if (score.mean <= 35) {
    setCameraStatus("Scene looks dark. Add more light.", "warn");
    return;
  }
  if (score.mean >= 245 || score.whiteRatio >= 0.985) {
    setCameraStatus("Frame looks too bright or blank. Reposition artwork.", "warn");
    return;
  }
  setCameraStatus(`Scanning for artwork... (${score.readyScore}/${CAMERA_READY_SCORE_THRESHOLD})`);
}

async function startCameraScan() {
  if (galleryModeEnabled) {
    return;
  }
  if (!cameraSection || !cameraVideo) {
    return;
  }
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
    setCameraStatus("Camera is not supported on this browser. Use gallery upload.", "warn");
    setGalleryMode(true);
    return;
  }
  if (cameraStarting) {
    return;
  }

  cameraStarting = true;
  cameraAutoCaptured = false;
  cameraReadyStreak = 0;
  cameraLastSignature = null;
  resetCameraFrameToLiveView();
  if (rescanBtn) {
    rescanBtn.hidden = true;
  }
  if (captureNowBtn) {
    captureNowBtn.disabled = true;
  }
  setCameraStatus("Opening camera...");

  try {
    stopCameraScan({ keepStatus: true });
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    });
    cameraStream = stream;
    cameraVideo.srcObject = stream;
    await cameraVideo.play();
    if (captureNowBtn) {
      captureNowBtn.hidden = false;
      captureNowBtn.disabled = false;
    }
    setCameraStatus("Scanning for artwork...");
    if (cameraScanTimer) {
      clearInterval(cameraScanTimer);
    }
    cameraScanTimer = setInterval(scanCameraFrame, CAMERA_SCAN_INTERVAL_MS);
  } catch (_error) {
    setCameraStatus("Camera access failed. Use gallery image upload.", "error");
    setGalleryMode(true);
  } finally {
    cameraStarting = false;
  }
}

function clearPreview() {
  sourceFile = null;
  sourceImage = null;
  previewSection.hidden = true;
  submitBtn.disabled = true;
  showWarnings([]);
  resetCameraFrameToLiveView();
}

async function setPreviewFromFile(file, options = {}) {
  const showPreviewPanel = options.showPreviewPanel !== false;
  clearError();
  sourceFile = file;
  if (!sourceFile) {
    clearPreview();
    return false;
  }

  try {
    const image = await fileToImage(sourceFile);
    sourceImage = image;
    previewSection.hidden = !showPreviewPanel;
    submitBtn.disabled = false;
    if (showPreviewPanel) {
      drawPreview();
    }
    showPreviewInCameraFrame(image.src || objectUrl);
    showWarnings(evaluateWarnings(image));
    return true;
  } catch (error) {
    clearPreview();
    showError(error.message || "Unable to read image.");
    return false;
  }
}

async function loadConfig() {
  try {
    const response = await fetch("/api/public/wonderpark/config", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.enabled) {
      showError("Public upload is currently unavailable.");
      submitBtn.disabled = true;
      return false;
    }
    const sdReachable = Boolean(payload?.stableDiffusion?.reachable);
    if (!sdReachable) {
      const sdDetail = String(payload?.stableDiffusion?.error || "").trim();
      showError(sdDetail || "Generation service is offline. Please start Stable Diffusion WebUI with --api.");
      submitBtn.disabled = true;
      return false;
    }
    config = { ...config, ...payload };
    return true;
  } catch (_error) {
    showError("Unable to load upload settings.");
    return false;
  }
}

async function digestFileHash(file) {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const bytes = Array.from(new Uint8Array(hashBuffer));
  return bytes.map((row) => row.toString(16).padStart(2, "0")).join("");
}

async function blockedByLocalDuplicate(file) {
  try {
    const hash = await digestFileHash(file);
    const key = `wonderpark:last:${hash}`;
    const now = Date.now();
    const last = Number(localStorage.getItem(key) || "0");
    if (last > 0 && (now - last) < (2 * 60 * 1000)) {
      return true;
    }
    localStorage.setItem(key, String(now));
    return false;
  } catch (_error) {
    return false;
  }
}

async function submitUpload(event) {
  event.preventDefault();
  clearError();

  if (uploadInProgress) {
    return;
  }
  const customerName = String(customerNameInput.value || "").trim();
  if (!customerName) {
    showError("Please enter your name.");
    return;
  }
  if (!sourceFile || !sourceImage) {
    showError("Please scan or choose your artwork image first.");
    return;
  }

  const localDuplicate = await blockedByLocalDuplicate(sourceFile);
  if (localDuplicate) {
    showError("This image was submitted recently. Please wait before resubmitting the same file.");
    return;
  }

  uploadInProgress = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting...";

  try {
    const processedBlob = await createProcessedBlob(sourceImage);
    const formData = new FormData();
    const presetAnimal = normalizeAnimalValue(pageContext.presetAnimal) || "unknown";
    const paperTemplateId = String(pageContext.paperTemplateId || "").trim();
    formData.append("customerName", customerName);
    formData.append("presetAnimal", presetAnimal);
    if (paperTemplateId) {
      formData.append("paperTemplateId", paperTemplateId);
    }
    formData.append("image", processedBlob, "processed_artwork.png");
    formData.append("originalImage", sourceFile, sourceFile.name || "artwork_upload");

    const uploadUrl = new URL("/api/public/wonderpark/upload", window.location.origin);
    if (presetAnimal) {
      uploadUrl.searchParams.set("animal", presetAnimal);
    }

    const response = await fetch(`${uploadUrl.pathname}${uploadUrl.search}`, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.detail;
      if (typeof detail === "string") {
        throw new Error(detail);
      }
      if (detail && typeof detail === "object" && detail.message) {
        throw new Error(String(detail.message));
      }
      throw new Error("Upload failed. Please try again.");
    }

    const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
    showWarnings(warnings);
    const submissionId = String(payload?.submission?.submission_id || "").trim();
    submissionIdText.textContent = submissionId || "-";
    uploadSection.hidden = true;
    thankYouSection.hidden = false;
    if (resultImageWrap) {
      resultImageWrap.hidden = true;
    }
    if (resultActions) {
      resultActions.hidden = true;
    }
    if (approveStatusText) {
      approveStatusText.hidden = false;
      approveStatusText.textContent = "Generating your artwork...";
    }
    stopQueueEstimateTicker();
    renderQueueCountdownStatus();
    setResultWaitingUi();
    stopCameraScan({ keepStatus: true });
    startSubmissionPolling(submissionId);
  } catch (error) {
    showError(error?.message || "Upload failed.");
  } finally {
    uploadInProgress = false;
    submitBtn.disabled = !sourceFile;
    submitBtn.textContent = "Submit Artwork";
  }
}

function openGalleryFromFallback() {
  if (!fileInput) {
    return;
  }
  setGalleryMode(true);
  stopCameraScan({ keepStatus: true });
  setCameraStatus("Gallery upload mode enabled.", "warn");
  fileInput.click();
}

pickFileBtn.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
  if (file) {
    stopCameraScan({ keepStatus: true });
    setCameraStatus("Image selected. Adjust crop then submit.");
    if (rescanBtn) {
      rescanBtn.hidden = false;
    }
  }
  void setPreviewFromFile(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
  });
});

dropzone.addEventListener("drop", (event) => {
  const files = event.dataTransfer?.files;
  const file = files && files[0] ? files[0] : null;
  if (file) {
    stopCameraScan({ keepStatus: true });
    setCameraStatus("Image selected. Adjust crop then submit.");
    if (rescanBtn) {
      rescanBtn.hidden = false;
    }
    void setPreviewFromFile(file);
  }
});

if (openGalleryBtn) {
  openGalleryBtn.addEventListener("click", () => {
    if (galleryModeEnabled) {
      setGalleryMode(false);
      clearError();
      void startCameraScan();
      return;
    }
    openGalleryFromFallback();
  });
}

if (rescanBtn) {
  rescanBtn.addEventListener("click", () => {
    clearPreview();
    clearError();
    if (galleryModeEnabled) {
      setGalleryMode(false);
    }
    void startCameraScan();
  });
}

if (captureNowBtn) {
  captureNowBtn.addEventListener("click", () => {
    clearError();
    startManualCaptureCountdown();
  });
}

if (approveShowcaseBtn) {
  approveShowcaseBtn.addEventListener("click", () => {
    clearError();
    void approveCurrentSubmission();
  });
}

if (regenerateImageBtn) {
  regenerateImageBtn.addEventListener("click", () => {
    clearError();
    void regenerateCurrentSubmission();
  });
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopCameraScan({ keepStatus: true });
    return;
  }
  if (!sourceFile && !galleryModeEnabled) {
    void startCameraScan();
  }
});

window.addEventListener("pagehide", () => {
  stopSubmissionPolling();
  stopCameraScan({ keepStatus: true });
});

uploadForm.addEventListener("submit", submitUpload);

initializeUploadContext();
setGalleryMode(false);
void loadConfig().then((enabled) => {
  if (enabled) {
    return startCameraScan();
  }
  return null;
});
