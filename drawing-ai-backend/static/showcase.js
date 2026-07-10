const SHOWCASE_POLL_MS = 10000;
const BASE_ROAMING_ITEMS = 7;
const RESIZE_DEBOUNCE_MS = 180;
const ARRIVE_STAGE_MS = 2200;
const REVEAL_HOLD_MS = 3600;
const TRANSFORM_STAGE_MAX_MS = 120000;
const GUIDE_ASSET_VERSION = "20260522i";
const BACKGROUND_ROTATE_MS = 10 * 60 * 1000;
const BACKGROUND_IMAGE_SET = [
  "/static/assets/craftpix_underwater/bg1.png",
  "/static/assets/craftpix_underwater/bg2.png",
  "/static/assets/craftpix_underwater/bg3.png",
  "/static/assets/craftpix_underwater/bg4.png",
];
const ROAM_MIN_SPEED = 18;
const ROAM_MAX_SPEED = 44;
const ROAM_EDGE_MARGIN = 10;
const ROAM_COLLISION_PADDING = 18;
const ROAM_DIRECTION_CHANGE_MIN_MS = 1800;
const ROAM_DIRECTION_CHANGE_MAX_MS = 4600;
const MODE_RATIO_DUAL = 2.0;
const MODE_RATIO_TRIPLE = 3.2;
const MODE_RATIO_ULTRAWIDE = 4.3;
const MUSIC_PROMPT_STORAGE_KEY = "showcaseMusicPromptSeen";

const ACTIVE_STATUSES = new Set(["pending", "queued", "processing", "generating", "active"]);
const FINAL_STATUSES = new Set(["generated", "shown", "completed", "complete"]);
const BLOCKED_STATUSES = new Set(["failed", "hidden", "cancelled", "error"]);

const SLOT_MAP = {
  single: [
    { x: 12, y: 22 },
    { x: 85, y: 24 },
    { x: 18, y: 70 },
    { x: 82, y: 72 },
    { x: 28, y: 16 },
    { x: 72, y: 16 },
    { x: 50, y: 84 },
  ],
  dual: [
    { x: 6, y: 22 },
    { x: 15, y: 68 },
    { x: 28, y: 30 },
    { x: 38, y: 80 },
    { x: 48, y: 14 },
    { x: 8, y: 46 },
    { x: 58, y: 84 },
    { x: 64, y: 54 },
    { x: 70, y: 28 },
    { x: 82, y: 70 },
    { x: 93, y: 24 },
    { x: 92, y: 62 },
    { x: 78, y: 16 },
  ],
  triple: [
    { x: 4, y: 24 },
    { x: 12, y: 72 },
    { x: 20, y: 34 },
    { x: 30, y: 16 },
    { x: 39, y: 80 },
    { x: 48, y: 28 },
    { x: 52, y: 86 },
    { x: 61, y: 18 },
    { x: 70, y: 74 },
    { x: 80, y: 34 },
    { x: 88, y: 68 },
    { x: 96, y: 26 },
    { x: 8, y: 50 },
    { x: 36, y: 52 },
    { x: 66, y: 46 },
    { x: 92, y: 54 },
  ],
  ultrawide: [
    { x: 3, y: 22 },
    { x: 7, y: 74 },
    { x: 12, y: 36 },
    { x: 16, y: 18 },
    { x: 21, y: 80 },
    { x: 26, y: 26 },
    { x: 31, y: 68 },
    { x: 36, y: 14 },
    { x: 41, y: 82 },
    { x: 46, y: 32 },
    { x: 52, y: 76 },
    { x: 57, y: 20 },
    { x: 62, y: 62 },
    { x: 68, y: 16 },
    { x: 73, y: 78 },
    { x: 79, y: 30 },
    { x: 84, y: 70 },
    { x: 89, y: 24 },
    { x: 94, y: 58 },
    { x: 98, y: 38 },
  ],
};

const GUIDE_VARIANTS = [
  { key: "fish_blue", imageUrl: `/static/assets/showcase_guides_svg/fish_blue.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_blue_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_blue_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_blue_skeleton", imageUrl: `/static/assets/showcase_guides_svg/fish_blue_skeleton.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_blue_skeleton_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_blue_skeleton_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_brown", imageUrl: `/static/assets/showcase_guides_svg/fish_brown.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_brown_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_brown_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_green", imageUrl: `/static/assets/showcase_guides_svg/fish_green.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_green_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_green_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_green_skeleton", imageUrl: `/static/assets/showcase_guides_svg/fish_green_skeleton.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_green_skeleton_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_green_skeleton_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey", imageUrl: `/static/assets/showcase_guides_svg/fish_grey.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey_long_a", imageUrl: `/static/assets/showcase_guides_svg/fish_grey_long_a.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey_long_a_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_grey_long_a_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey_long_b", imageUrl: `/static/assets/showcase_guides_svg/fish_grey_long_b.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey_long_b_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_grey_long_b_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_grey_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_grey_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_orange", imageUrl: `/static/assets/showcase_guides_svg/fish_orange.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_orange_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_orange_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_orange_skeleton", imageUrl: `/static/assets/showcase_guides_svg/fish_orange_skeleton.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_orange_skeleton_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_orange_skeleton_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_pink", imageUrl: `/static/assets/showcase_guides_svg/fish_pink.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_pink_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_pink_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_pink_skeleton", imageUrl: `/static/assets/showcase_guides_svg/fish_pink_skeleton.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_pink_skeleton_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_pink_skeleton_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_red", imageUrl: `/static/assets/showcase_guides_svg/fish_red.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_red_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_red_outline.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_red_skeleton", imageUrl: `/static/assets/showcase_guides_svg/fish_red_skeleton.svg?v=${GUIDE_ASSET_VERSION}` },
  { key: "fish_red_skeleton_outline", imageUrl: `/static/assets/showcase_guides_svg/fish_red_skeleton_outline.svg?v=${GUIDE_ASSET_VERSION}` },
];

const shell = document.getElementById("showcaseShell");
const stageMessage = document.getElementById("stageMessage");
const wsStatusBadge = document.getElementById("wsStatusBadge");
const craftpixBgA = document.getElementById("craftpixBgA");
const craftpixBgB = document.getElementById("craftpixBgB");
const bubbleLayer = document.getElementById("bubbleLayer");
const bgFishLayer = document.getElementById("bgFishLayer");
const centerPresentation = document.getElementById("centerPresentation");
const centerCard = document.getElementById("centerCard");
const centerOriginalImage = document.getElementById("centerOriginalImage");
const centerGeneratedImage = document.getElementById("centerGeneratedImage");
const centerLabel = document.getElementById("centerLabel");
const centerName = document.getElementById("centerName");
const centerStatus = document.getElementById("centerStatus");
const fishCourier = document.getElementById("fishCourier");
const roamingLayer = document.getElementById("roamingLayer");
const showcaseMusic = document.getElementById("showcaseMusic");
const showcaseSoundButton = document.getElementById("showcaseSoundButton");

const state = {
  displayMode: "single",
  presenting: null,
  presentationQueue: [],
  queuedPresentationIds: new Set(),
  roamingItems: [],
  seenCompletedIds: new Set(),
  presentedIds: new Set(),
  resizeTimer: null,
  pollTimer: null,
  reconnectTimer: null,
  ws: null,
  decorationKey: "",
  presentationTimers: [],
  backgroundTimer: null,
  backgroundIndex: 0,
  backgroundFrontLayer: "a",
  roamMotionById: {},
  roamRaf: 0,
  roamLastTs: 0,
  musicStarted: false,
  musicPromptSeen: false,
};

function readStorageFlag(key) {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeStorageFlag(key) {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // Ignore storage failures in restricted browser modes.
  }
}

function setSoundButtonVisible(visible) {
  if (!showcaseSoundButton) {
    return;
  }
  const shouldShow = visible && !state.musicPromptSeen;
  showcaseSoundButton.classList.toggle("is-hidden", !shouldShow);
  if (shouldShow) {
    state.musicPromptSeen = true;
    writeStorageFlag(MUSIC_PROMPT_STORAGE_KEY);
  }
}

async function startShowcaseMusic() {
  if (!showcaseMusic || state.musicStarted) {
    return;
  }

  try {
    showcaseMusic.volume = 0.6;
    await showcaseMusic.play();
    state.musicStarted = true;
    state.musicPromptSeen = true;
    writeStorageFlag(MUSIC_PROMPT_STORAGE_KEY);
    setSoundButtonVisible(false);
  } catch {
    setSoundButtonVisible(true);
  }
}

function initializeShowcaseMusic() {
  if (!showcaseMusic) {
    return;
  }

  state.musicPromptSeen = readStorageFlag(MUSIC_PROMPT_STORAGE_KEY);

  showcaseMusic.addEventListener("playing", () => {
    state.musicStarted = true;
    state.musicPromptSeen = true;
    writeStorageFlag(MUSIC_PROMPT_STORAGE_KEY);
    setSoundButtonVisible(false);
  });

  if (showcaseSoundButton) {
    showcaseSoundButton.addEventListener("click", startShowcaseMusic);
  }

  window.addEventListener("pointerdown", startShowcaseMusic, { once: true, passive: true });
  window.addEventListener("keydown", startShowcaseMusic, { once: true });
  startShowcaseMusic();
}

function createGuideBadge(guide, direction, seed) {
  const badge = document.createElement("span");
  badge.className = `roaming-guide guide-${guide.key}`;
  badge.setAttribute("aria-hidden", "true");
  badge.style.setProperty("--guide-delay", `${-(seed % 9)}s`);
  badge.style.setProperty("--guide-direction", direction > 0 ? "1" : "-1");

  const image = document.createElement("img");
  image.className = "guide-image";
  image.loading = "lazy";
  image.decoding = "async";
  image.src = guide.imageUrl || GUIDE_VARIANTS[0].imageUrl;
  image.alt = `${guide.key} guide`;
  badge.appendChild(image);
  return badge;
}

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

function hashString(value) {
  const input = String(value ?? "");
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
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
  if (safeUrl(raw?.imageUrl, raw?.image_url) && safeText(raw?.status)) {
    return status || "completed";
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
  const hidden = Boolean(raw.hidden) || status === "hidden";
  const source = safeText(raw.source || "public").toLowerCase();
  if (source !== "public_wonderpark") {
    return null;
  }
  if (hidden || BLOCKED_STATUSES.has(status)) {
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
    raw.uploadedImageUrl,
    raw.uploaded_image_url,
  );

  let finalImageUrl = generatedImageUrl;
  if (!finalImageUrl && (FINAL_STATUSES.has(status) || status === "completed")) {
    finalImageUrl = fallbackImageUrl;
  }

  const originalImageUrl = safeUrl(
    raw.originalImageUrl,
    raw.original_image_url,
    raw.inputUrl,
    raw.originalUrl,
    fallbackImageUrl,
    finalImageUrl,
  );

  if (!originalImageUrl && !finalImageUrl) {
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
      || raw.startedAt
      || raw.queuedAt
      || raw.updatedAt,
  );

  const completedByStatus = FINAL_STATUSES.has(status) || status === "completed";
  const isCompleted = Boolean(finalImageUrl) && (completedByStatus || status === "unknown");
  if (isCompleted && raw.showcaseVisible !== true) {
    return null;
  }
  let isActive = ACTIVE_STATUSES.has(status) || (!isCompleted && Boolean(originalImageUrl));
  // Public Wonderpark should only appear after a real generated image is ready.
  if (source === "public_wonderpark" && !isCompleted) {
    isActive = false;
  }

  return {
    id,
    status,
    hidden,
    name,
    createdAt,
    dateLabel: formatDate(createdAt),
    timeMs: toTimeMs(createdAt),
    originalImageUrl,
    finalImageUrl,
    fallbackImageUrl,
    isCompleted,
    isActive,
    source,
  };
}

function setWsStatus(connected) {
  if (!wsStatusBadge) {
    return;
  }
  wsStatusBadge.textContent = connected ? "Connected" : "Reconnecting";
  wsStatusBadge.classList.toggle("connected", connected);
  wsStatusBadge.classList.toggle("reconnecting", !connected);
}

function getViewportSize() {
  const visualViewport = window.visualViewport;
  const width = Math.max(
    1,
    Math.round(
      visualViewport?.width
        || window.innerWidth
        || document.documentElement.clientWidth
        || 1,
    ),
  );
  const height = Math.max(
    1,
    Math.round(
      visualViewport?.height
        || window.innerHeight
        || document.documentElement.clientHeight
        || 1,
    ),
  );
  return {
    width,
    height,
    ratio: width / Math.max(1, height),
  };
}

function syncViewportSize() {
  if (!shell) {
    return;
  }
  const viewport = getViewportSize();
  shell.style.setProperty("--viewport-width-px", `${viewport.width}px`);
  shell.style.setProperty("--viewport-height-px", `${viewport.height}px`);
}

function getDisplayMode() {
  const viewport = getViewportSize();
  if (viewport.ratio >= MODE_RATIO_ULTRAWIDE || viewport.width >= 5000) {
    return "ultrawide";
  }
  if (viewport.ratio >= MODE_RATIO_TRIPLE || viewport.width >= 3400) {
    return "triple";
  }
  if (viewport.ratio >= MODE_RATIO_DUAL || viewport.width >= 2200) {
    return "dual";
  }
  return "single";
}

function getRoamingItemLimit(mode = state.displayMode) {
  const viewport = getViewportSize();
  const widthDriven = Math.max(1, Math.floor(viewport.width / 470));

  if (mode === "ultrawide") {
    return clamp(widthDriven + 3, 12, 20);
  }
  if (mode === "triple") {
    return clamp(widthDriven + 2, 10, 16);
  }
  if (mode === "dual") {
    return clamp(widthDriven + 1, 8, 13);
  }
  return clamp(widthDriven, 6, BASE_ROAMING_ITEMS);
}

function seededShuffle(input, seed) {
  const list = [...input];
  let current = Math.max(1, seed % 2147483647);
  for (let i = list.length - 1; i > 0; i -= 1) {
    current = (current * 48271) % 2147483647;
    const j = current % (i + 1);
    const tmp = list[i];
    list[i] = list[j];
    list[j] = tmp;
  }
  return list;
}

function setBackgroundLayerImage(layer, url) {
  if (!layer || !url) {
    return;
  }
  layer.style.backgroundImage = `url("${url}")`;
}

function rotateCraftpixBackground() {
  if (!craftpixBgA || !craftpixBgB || BACKGROUND_IMAGE_SET.length === 0) {
    return;
  }

  state.backgroundIndex = (state.backgroundIndex + 1) % BACKGROUND_IMAGE_SET.length;
  const nextUrl = BACKGROUND_IMAGE_SET[state.backgroundIndex];

  const front = state.backgroundFrontLayer === "a" ? craftpixBgA : craftpixBgB;
  const back = state.backgroundFrontLayer === "a" ? craftpixBgB : craftpixBgA;

  setBackgroundLayerImage(back, nextUrl);
  back.classList.add("is-active");
  front.classList.remove("is-active");
  state.backgroundFrontLayer = state.backgroundFrontLayer === "a" ? "b" : "a";
}

function initializeCraftpixBackgrounds() {
  if (!craftpixBgA || !craftpixBgB || BACKGROUND_IMAGE_SET.length === 0) {
    return;
  }

  const daySeed = hashString(new Date().toISOString().slice(0, 10));
  state.backgroundIndex = daySeed % BACKGROUND_IMAGE_SET.length;
  const firstUrl = BACKGROUND_IMAGE_SET[state.backgroundIndex];
  const secondUrl = BACKGROUND_IMAGE_SET[(state.backgroundIndex + 1) % BACKGROUND_IMAGE_SET.length];

  setBackgroundLayerImage(craftpixBgA, firstUrl);
  setBackgroundLayerImage(craftpixBgB, secondUrl);
  craftpixBgA.classList.add("is-active");
  craftpixBgB.classList.remove("is-active");
  state.backgroundFrontLayer = "a";

  if (state.backgroundTimer) {
    clearInterval(state.backgroundTimer);
  }
  state.backgroundTimer = setInterval(rotateCraftpixBackground, BACKGROUND_ROTATE_MS);
}

function ensureBackdropDecorations(mode) {
  const key = `${mode}:no-bubbles-no-bg-fish`;
  if (state.decorationKey === key) {
    return;
  }
  state.decorationKey = key;

  if (bubbleLayer) {
    bubbleLayer.replaceChildren();
  }
  if (bgFishLayer) {
    bgFishLayer.replaceChildren();
  }
}

function applyDisplayMode(mode) {
  if (!mode) {
    return;
  }
  state.displayMode = mode;
  syncViewportSize();
  shell.setAttribute("data-display-mode", mode);
  const roamingLimit = getRoamingItemLimit(mode);
  if (state.roamingItems.length > roamingLimit) {
    state.roamingItems = state.roamingItems.slice(0, roamingLimit);
  }
  ensureBackdropDecorations(mode);
  renderRoamingItems();
}

function setCenterImage(imageEl, url, altText) {
  if (!imageEl) {
    return;
  }
  if (!url) {
    imageEl.removeAttribute("src");
    imageEl.alt = altText;
    return;
  }
  if (imageEl.src !== url) {
    imageEl.src = url;
  }
  imageEl.alt = altText;
}

function clearPresentationTimers() {
  while (state.presentationTimers.length > 0) {
    const timer = state.presentationTimers.pop();
    clearTimeout(timer);
  }
}

function schedulePresentationTimer(callback, waitMs) {
  const timer = setTimeout(callback, waitMs);
  state.presentationTimers.push(timer);
}

function updateStageMessage() {
  if (!stageMessage) {
    return;
  }
  if (!state.presenting) {
    stageMessage.textContent = "Waiting for the next drawing...";
    return;
  }
  if (state.presenting.stage === "revealed") {
    stageMessage.textContent = "New drawing is ready!";
    return;
  }
  stageMessage.textContent = "Transforming drawing...";
}

function renderCenterCard() {
  if (!state.presenting) {
    centerPresentation.classList.add("is-hidden");
    centerPresentation.classList.remove("is-visible");
    centerCard.className = "center-card stage-arrive";
    centerName.textContent = "Customer";
    centerStatus.textContent = "Transforming drawing...";
    centerLabel.textContent = "Customer Drawing";
    updateStageMessage();
    return;
  }

  centerPresentation.classList.remove("is-hidden");
  centerPresentation.classList.add("is-visible");

  const stage = state.presenting.stage || "arrive";
  if (stage === "roam_out") {
    centerCard.className = "center-card stage-roam-out";
  } else if (stage === "revealed") {
    centerCard.className = "center-card stage-revealed";
  } else if (stage === "transforming") {
    centerCard.className = "center-card stage-transforming";
  } else {
    centerCard.className = "center-card stage-arrive";
  }

  centerName.textContent = state.presenting.name || "Customer";

  const showGenerated = stage === "revealed" && safeText(state.presenting.finalImageUrl);
  centerLabel.textContent = showGenerated ? "Generated Drawing" : "Customer Drawing";
  centerStatus.textContent = showGenerated ? "New drawing is ready!" : "Transforming drawing...";

  const originalUrl = safeUrl(state.presenting.originalImageUrl, state.presenting.finalImageUrl);
  const generatedUrl = safeUrl(state.presenting.finalImageUrl, state.presenting.originalImageUrl);

  setCenterImage(centerOriginalImage, originalUrl, "Customer Drawing");
  setCenterImage(centerGeneratedImage, generatedUrl, "Generated Drawing");

  updateStageMessage();
}

function removeRoamingItemById(itemId) {
  if (!itemId) {
    return;
  }
  state.roamingItems = state.roamingItems.filter((entry) => entry.id !== itemId);
  renderRoamingItems();
}

function upsertRoamingItem(item) {
  if (!item || !item.id) {
    return;
  }
  const imageUrl = safeUrl(item.finalImageUrl, item.originalImageUrl);
  if (!imageUrl) {
    return;
  }

  const normalized = {
    id: item.id,
    name: item.name || "Customer",
    createdAt: item.createdAt || "",
    timeMs: Number(item.timeMs || 0),
    finalImageUrl: imageUrl,
    originalImageUrl: safeUrl(item.originalImageUrl, imageUrl),
  };

  const existingIndex = state.roamingItems.findIndex((entry) => entry.id === normalized.id);
  if (existingIndex >= 0) {
    state.roamingItems[existingIndex] = normalized;
  } else {
    state.roamingItems.unshift(normalized);
  }

  state.roamingItems.sort((a, b) => (b.timeMs || 0) - (a.timeMs || 0));
  state.roamingItems = state.roamingItems.slice(0, getRoamingItemLimit());
  renderRoamingItems();
}

function getSlotsForCurrentMode() {
  const mode = state.displayMode || "single";
  const baseSlots = SLOT_MAP[mode] || SLOT_MAP.single;
  if (!state.presenting) {
    return baseSlots;
  }
  const roamingLimit = getRoamingItemLimit(mode);
  const safeSlots = baseSlots.filter((slot) => Math.abs(slot.x - 50) > 14 || Math.abs(slot.y - 50) > 20);
  return safeSlots.length >= roamingLimit ? safeSlots : baseSlots;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function randomFromSeed(seed, min, max) {
  const normalized = (Math.abs(seed) % 10000) / 10000;
  return min + (max - min) * normalized;
}

function normalizeRoamSpeed(motion) {
  const speed = Math.hypot(motion.vx, motion.vy);
  if (speed <= 0.001) {
    motion.vx = ROAM_MIN_SPEED;
    motion.vy = 0;
    return;
  }
  if (speed < ROAM_MIN_SPEED) {
    const factor = ROAM_MIN_SPEED / speed;
    motion.vx *= factor;
    motion.vy *= factor;
    return;
  }
  if (speed > ROAM_MAX_SPEED * 1.35) {
    const factor = (ROAM_MAX_SPEED * 1.35) / speed;
    motion.vx *= factor;
    motion.vy *= factor;
  }
}

function stopRoamAnimator() {
  if (state.roamRaf) {
    cancelAnimationFrame(state.roamRaf);
  }
  state.roamRaf = 0;
  state.roamLastTs = 0;
}

function syncRoamingMotion(renderEntries) {
  if (!roamingLayer) {
    return;
  }

  const layerRect = roamingLayer.getBoundingClientRect();
  const layerWidth = Math.max(320, layerRect.width || window.innerWidth || 1);
  const layerHeight = Math.max(240, layerRect.height || window.innerHeight || 1);
  const now = performance.now();
  const nextMotionById = {};

  renderEntries.forEach((entry) => {
    const { item, card, slot, seed } = entry;
    const existing = state.roamMotionById[item.id];
    const cardWidth = Math.max(96, card.offsetWidth || 160);
    const cardHeight = Math.max(96, card.offsetHeight || 160);
    const minX = ROAM_EDGE_MARGIN;
    const maxX = Math.max(minX, layerWidth - cardWidth - ROAM_EDGE_MARGIN);
    const minY = ROAM_EDGE_MARGIN;
    const maxY = Math.max(minY, layerHeight - cardHeight - ROAM_EDGE_MARGIN);
    const initialScale = Number.parseFloat(card.style.getPropertyValue("--scale")) || 0.9;
    const guideEl = card.querySelector(".roaming-guide");

    if (existing) {
      const preserved = {
        ...existing,
        card,
        guideEl,
        w: cardWidth,
        h: cardHeight,
        scale: initialScale || existing.scale || 0.9,
      };
      preserved.x = clamp(preserved.x, minX, maxX);
      preserved.y = clamp(preserved.y, minY, maxY);
      normalizeRoamSpeed(preserved);
      nextMotionById[item.id] = preserved;
      return;
    }

    const spawnX = clamp((slot.x / 100) * layerWidth - (cardWidth / 2), minX, maxX);
    const spawnY = clamp((slot.y / 100) * layerHeight - (cardHeight / 2), minY, maxY);
    const baseSpeed = randomFromSeed(seed * 13, ROAM_MIN_SPEED, ROAM_MAX_SPEED);
    const angle = ((Math.abs(seed) % 360) * Math.PI) / 180;
    let vx = Math.cos(angle) * baseSpeed;
    let vy = Math.sin(angle) * baseSpeed;
    if (Math.abs(vx) < 8) {
      vx = vx < 0 ? -8 : 8;
    }
    if (Math.abs(vy) < 5) {
      vy = vy < 0 ? -5 : 5;
    }

    nextMotionById[item.id] = {
      id: item.id,
      card,
      guideEl,
      x: spawnX,
      y: spawnY,
      vx,
      vy,
      w: cardWidth,
      h: cardHeight,
      scale: initialScale,
      tiltBase: randomFromSeed(seed * 17, -1.8, 1.8),
      bobPhase: randomFromSeed(seed * 19, 0, Math.PI * 2),
      nextTurnAt: now + randomFromSeed(seed * 23, ROAM_DIRECTION_CHANGE_MIN_MS, ROAM_DIRECTION_CHANGE_MAX_MS),
      guideDir: vx >= 0 ? "1" : "-1",
    };
  });

  state.roamMotionById = nextMotionById;

  if (Object.keys(state.roamMotionById).length === 0) {
    stopRoamAnimator();
    return;
  }

  if (!state.roamRaf) {
    state.roamLastTs = 0;
    state.roamRaf = requestAnimationFrame(stepRoamMotion);
  }
}

function stepRoamMotion(timestamp) {
  const motions = Object.values(state.roamMotionById);
  if (!roamingLayer || motions.length === 0) {
    stopRoamAnimator();
    return;
  }

  if (!state.roamLastTs) {
    state.roamLastTs = timestamp;
  }
  const dt = Math.min(0.05, Math.max(0.001, (timestamp - state.roamLastTs) / 1000));
  state.roamLastTs = timestamp;

  const layerRect = roamingLayer.getBoundingClientRect();
  const layerWidth = Math.max(320, layerRect.width || window.innerWidth || 1);
  const layerHeight = Math.max(240, layerRect.height || window.innerHeight || 1);

  motions.forEach((motion, index) => {
    if (!motion.card || !motion.card.isConnected) {
      return;
    }

    if (timestamp >= motion.nextTurnAt) {
      const turnSeed = hashString(`${motion.id}:${Math.floor(timestamp / 250)}:${index}`);
      const turnDeg = randomFromSeed(turnSeed, -42, 42);
      const turn = (turnDeg * Math.PI) / 180;
      const cos = Math.cos(turn);
      const sin = Math.sin(turn);
      const nextVx = motion.vx * cos - motion.vy * sin;
      const nextVy = motion.vx * sin + motion.vy * cos;
      const desired = randomFromSeed(turnSeed * 3, ROAM_MIN_SPEED, ROAM_MAX_SPEED);
      const currentSpeed = Math.max(0.001, Math.hypot(nextVx, nextVy));
      motion.vx = (nextVx / currentSpeed) * desired;
      motion.vy = (nextVy / currentSpeed) * desired;
      motion.nextTurnAt = timestamp + randomFromSeed(turnSeed * 5, ROAM_DIRECTION_CHANGE_MIN_MS, ROAM_DIRECTION_CHANGE_MAX_MS);
    }

    motion.x += motion.vx * dt;
    motion.y += motion.vy * dt;

    const minX = ROAM_EDGE_MARGIN;
    const maxX = Math.max(minX, layerWidth - motion.w - ROAM_EDGE_MARGIN);
    const minY = ROAM_EDGE_MARGIN;
    const maxY = Math.max(minY, layerHeight - motion.h - ROAM_EDGE_MARGIN);

    if (motion.x <= minX) {
      motion.x = minX;
      motion.vx = Math.abs(motion.vx);
    } else if (motion.x >= maxX) {
      motion.x = maxX;
      motion.vx = -Math.abs(motion.vx);
    }

    if (motion.y <= minY) {
      motion.y = minY;
      motion.vy = Math.abs(motion.vy);
    } else if (motion.y >= maxY) {
      motion.y = maxY;
      motion.vy = -Math.abs(motion.vy);
    }

    normalizeRoamSpeed(motion);
  });

  for (let i = 0; i < motions.length; i += 1) {
    const a = motions[i];
    if (!a.card || !a.card.isConnected) {
      continue;
    }
    for (let j = i + 1; j < motions.length; j += 1) {
      const b = motions[j];
      if (!b.card || !b.card.isConnected) {
        continue;
      }

      const ax = a.x + (a.w / 2);
      const ay = a.y + (a.h / 2);
      const bx = b.x + (b.w / 2);
      const by = b.y + (b.h / 2);
      const dx = bx - ax;
      const dy = by - ay;
      const minX = ((a.w + b.w) / 2) + ROAM_COLLISION_PADDING;
      const minY = ((a.h + b.h) / 2) + ROAM_COLLISION_PADDING;
      const overlapX = minX - Math.abs(dx);
      const overlapY = minY - Math.abs(dy);

      if (overlapX <= 0 || overlapY <= 0) {
        continue;
      }

      let nx = dx;
      let ny = dy;
      const dist = Math.hypot(nx, ny);
      if (dist < 0.001) {
        nx = (i % 2 === 0) ? 1 : -1;
        ny = 0;
      } else {
        nx /= dist;
        ny /= dist;
      }

      const push = (Math.min(overlapX, overlapY) * 0.55) + 0.6;
      a.x -= nx * push;
      a.y -= ny * push;
      b.x += nx * push;
      b.y += ny * push;

      const impulse = 22;
      a.vx -= nx * impulse;
      a.vy -= ny * impulse;
      b.vx += nx * impulse;
      b.vy += ny * impulse;
      normalizeRoamSpeed(a);
      normalizeRoamSpeed(b);
    }
  }

  motions.forEach((motion) => {
    if (!motion.card || !motion.card.isConnected) {
      return;
    }

    const minX = ROAM_EDGE_MARGIN;
    const maxX = Math.max(minX, layerWidth - motion.w - ROAM_EDGE_MARGIN);
    const minY = ROAM_EDGE_MARGIN;
    const maxY = Math.max(minY, layerHeight - motion.h - ROAM_EDGE_MARGIN);
    motion.x = clamp(motion.x, minX, maxX);
    motion.y = clamp(motion.y, minY, maxY);

    const bob = Math.sin((timestamp / 760) + motion.bobPhase) * 2.8;
    motion.card.style.transform = `translate3d(${motion.x.toFixed(2)}px, ${(motion.y + bob).toFixed(2)}px, 0) scale(${motion.scale.toFixed(3)})`;

    const tilt = clamp(((motion.vx / ROAM_MAX_SPEED) * 5) + motion.tiltBase, -10, 10);
    motion.card.style.setProperty("--tilt", `${tilt.toFixed(2)}deg`);

    const dir = motion.vx >= 0 ? "1" : "-1";
    if (motion.guideEl && motion.guideDir !== dir) {
      motion.guideEl.style.setProperty("--guide-direction", dir);
      motion.guideDir = dir;
    }
  });

  state.roamRaf = requestAnimationFrame(stepRoamMotion);
}

function renderRoamingItems() {
  const items = state.roamingItems.slice(0, getRoamingItemLimit());
  if (items.length === 0) {
    if (roamingLayer) {
      roamingLayer.replaceChildren();
    }
    state.roamMotionById = {};
    stopRoamAnimator();
    return;
  }

  const slotSeed = hashString(items.map((entry) => entry.id).join("|"));
  const orderedSlots = seededShuffle(getSlotsForCurrentMode(), slotSeed);

  const fragment = document.createDocumentFragment();
  const shellStyle = window.getComputedStyle(shell);
  const scaleBase = Number.parseFloat(shellStyle.getPropertyValue("--roam-scale-base")) || 0.88;

  const renderEntries = [];

  items.forEach((item, index) => {
    const slot = orderedSlots[index % orderedSlots.length] || { x: 50, y: 80 };
    const seed = hashString(`${item.id}:${index}`);
    const guide = GUIDE_VARIANTS[(seed + index) % GUIDE_VARIANTS.length];
    const direction = seed % 2 === 0 ? 1 : -1;

    const card = document.createElement("article");
    card.className = "roaming-card";
    card.dataset.direction = direction > 0 ? "right" : "left";
    card.dataset.guide = guide.key;

    const scale = scaleBase + ((seed % 20) - 10) / 100;

    card.style.setProperty("--roam-opacity", "1");
    card.style.setProperty("--blur", "0px");
    card.style.setProperty("--scale", `${Math.max(0.72, scale).toFixed(3)}`);
    card.style.setProperty("--tilt", `${((seed % 12) - 6) / 4}deg`);
    card.style.transform = `translate3d(0, 0, 0) scale(${Math.max(0.72, scale).toFixed(3)})`;

    const figure = document.createElement("figure");

    const image = document.createElement("img");
    image.loading = "lazy";
    image.decoding = "async";
    image.src = item.finalImageUrl;
    image.alt = `Generated Drawing by ${item.name}`;

    const guideBadge = createGuideBadge(guide, direction, seed);
    const media = document.createElement("div");
    media.className = "roaming-media";

    const caption = document.createElement("figcaption");
    caption.textContent = item.name || "Customer";

    media.appendChild(image);
    media.appendChild(guideBadge);
    figure.appendChild(media);
    figure.appendChild(caption);
    card.appendChild(figure);
    fragment.appendChild(card);
    renderEntries.push({ item, card, slot, seed });
  });

  roamingLayer.replaceChildren(fragment);
  syncRoamingMotion(renderEntries);
}

function finishPresentation(presentationId) {
  if (!state.presenting || state.presenting.id !== presentationId) {
    return;
  }

  const completedItem = { ...state.presenting };
  state.presenting.stage = "roam_out";
  renderCenterCard();

  clearPresentationTimers();
  schedulePresentationTimer(() => {
    if (!state.presenting || state.presenting.id !== presentationId) {
      return;
    }
    const finalImage = safeUrl(completedItem.finalImageUrl, completedItem.originalImageUrl);
    if (finalImage) {
      upsertRoamingItem({
        ...completedItem,
        finalImageUrl: finalImage,
      });
    }
    state.presenting = null;
    renderCenterCard();
    processPresentationQueue();
  }, 680);
}

function revealCurrentPresentation() {
  if (!state.presenting) {
    return;
  }
  const finalImage = safeUrl(state.presenting.finalImageUrl);
  if (!finalImage) {
    return;
  }

  state.presenting.finalImageUrl = finalImage;
  state.presenting.stage = "revealed";
  renderCenterCard();

  clearPresentationTimers();
  schedulePresentationTimer(() => {
    finishPresentation(state.presenting?.id);
  }, REVEAL_HOLD_MS);
}

function setTransformingStage(presentationId) {
  if (!state.presenting || state.presenting.id !== presentationId) {
    return;
  }
  state.presenting.stage = "transforming";
  renderCenterCard();

  clearPresentationTimers();
  schedulePresentationTimer(() => {
    finishPresentation(presentationId);
  }, TRANSFORM_STAGE_MAX_MS);
}

function animateFishCourier(direction) {
  if (!fishCourier) {
    return;
  }
  fishCourier.dataset.direction = direction === "right" ? "right" : "left";
  fishCourier.classList.remove("swim");
  // Restart CSS animation.
  void fishCourier.offsetWidth;
  fishCourier.classList.add("swim");
}

function startPresentation(entry) {
  if (!entry || !entry.id) {
    return;
  }

  clearPresentationTimers();
  const direction = hashString(entry.id) % 2 === 0 ? "left" : "right";

  state.presenting = {
    ...entry,
    stage: "arrive",
    direction,
    startedAt: Date.now(),
  };

  state.presentedIds.add(entry.id);
  renderCenterCard();
  animateFishCourier(direction);

  schedulePresentationTimer(() => {
    if (!state.presenting || state.presenting.id !== entry.id) {
      return;
    }
    if (safeUrl(state.presenting.finalImageUrl)) {
      revealCurrentPresentation();
      return;
    }
    setTransformingStage(entry.id);
  }, ARRIVE_STAGE_MS);
}

function processPresentationQueue() {
  if (state.presenting || state.presentationQueue.length === 0) {
    return;
  }
  const next = state.presentationQueue.shift();
  state.queuedPresentationIds.delete(next.id);
  startPresentation(next);
}

function enqueuePresentation(item) {
  if (!item || !item.id) {
    return;
  }

  if (state.presenting && state.presenting.id === item.id) {
    if (safeUrl(item.finalImageUrl)) {
      state.presenting.finalImageUrl = safeUrl(item.finalImageUrl);
      revealCurrentPresentation();
    }
    return;
  }

  if (state.queuedPresentationIds.has(item.id)) {
    const existing = state.presentationQueue.find((entry) => entry.id === item.id);
    if (existing && safeUrl(item.finalImageUrl)) {
      existing.finalImageUrl = safeUrl(item.finalImageUrl);
    }
    return;
  }

  state.presentationQueue.push({ ...item });
  state.queuedPresentationIds.add(item.id);
  processPresentationQueue();
}

function applyCompletedItem(item) {
  if (!item || !item.id || !item.isCompleted) {
    return;
  }

  state.seenCompletedIds.add(item.id);

  if (state.presenting && state.presenting.id === item.id) {
    state.presenting.finalImageUrl = safeUrl(item.finalImageUrl, state.presenting.finalImageUrl);
    revealCurrentPresentation();
    return;
  }

  if (!state.presentedIds.has(item.id)) {
    enqueuePresentation(item);
    return;
  }

  upsertRoamingItem(item);
}

function handleQueueSnapshot(rawJobs) {
  const jobs = Array.isArray(rawJobs) ? rawJobs : [];
  const normalized = jobs
    .map((job) => normalizeRecord(job))
    .filter((job) => job && job.isActive);

  if (normalized.length === 0) {
    return;
  }

  normalized.sort((a, b) => {
    const rankA = a.status === "processing" ? 0 : 1;
    const rankB = b.status === "processing" ? 0 : 1;
    if (rankA !== rankB) {
      return rankA - rankB;
    }
    return (a.timeMs || 0) - (b.timeMs || 0);
  });

  const candidate = normalized[0];
  if (!candidate) {
    return;
  }

  if (state.presenting && state.presenting.id === candidate.id) {
    return;
  }

  if (state.presentedIds.has(candidate.id)) {
    return;
  }

  enqueuePresentation(candidate);
}

function syncGalleryItems(rawItems, isInitial = false) {
  const normalized = (Array.isArray(rawItems) ? rawItems : [])
    .map((item) => normalizeRecord(item))
    .filter((item) => Boolean(item));

  const completed = normalized
    .filter((item) => item.isCompleted)
    .sort((a, b) => (b.timeMs || 0) - (a.timeMs || 0));

  if (isInitial) {
    completed.forEach((item) => {
      state.seenCompletedIds.add(item.id);
      state.presentedIds.add(item.id);
    });
    state.roamingItems = completed.slice(0, getRoamingItemLimit()).map((item) => ({
      id: item.id,
      name: item.name,
      createdAt: item.createdAt,
      timeMs: item.timeMs,
      finalImageUrl: safeUrl(item.finalImageUrl, item.originalImageUrl),
      originalImageUrl: safeUrl(item.originalImageUrl, item.finalImageUrl),
    }));
    renderRoamingItems();
    return;
  }

  completed.forEach((item) => {
    if (!state.seenCompletedIds.has(item.id)) {
      applyCompletedItem(item);
      return;
    }
    if (state.presentedIds.has(item.id)) {
      upsertRoamingItem(item);
    }
  });
}

async function fetchGallerySnapshot() {
  const response = await fetch(`/api/gallery?limit=140&offset=0&source=public_wonderpark&showcaseOnly=true`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Gallery request failed (${response.status})`);
  }
  const payload = await response.json();
  return Array.isArray(payload.items) ? payload.items : [];
}

async function fetchQueueSnapshot() {
  const response = await fetch(`/api/queue/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Queue request failed (${response.status})`);
  }
  const payload = await response.json();
  return Array.isArray(payload.jobs) ? payload.jobs : [];
}

async function refreshSnapshots(options = {}) {
  const initial = Boolean(options.initial);
  const [galleryResult, queueResult] = await Promise.allSettled([
    fetchGallerySnapshot(),
    fetchQueueSnapshot(),
  ]);

  if (galleryResult.status === "fulfilled") {
    syncGalleryItems(galleryResult.value, initial);
  }

  if (queueResult.status === "fulfilled") {
    handleQueueSnapshot(queueResult.value);
  }
}

function handleIncomingItem(rawItem) {
  const item = normalizeRecord(rawItem);
  if (!item) {
    if (rawItem && rawItem.jobId) {
      removeRoamingItemById(String(rawItem.jobId));
      if (state.presenting && state.presenting.id === String(rawItem.jobId)) {
        clearPresentationTimers();
        state.presenting = null;
        renderCenterCard();
        processPresentationQueue();
      }
    }
    return;
  }

  if (item.isCompleted) {
    applyCompletedItem(item);
    return;
  }

  if (item.isActive && !state.presentedIds.has(item.id)) {
    enqueuePresentation(item);
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  state.ws = ws;

  ws.onopen = () => {
    setWsStatus(true);
  };

  ws.onclose = () => {
    setWsStatus(false);
    state.ws = null;
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
    }
    state.reconnectTimer = setTimeout(connectWebSocket, 2800);
  };

  ws.onerror = () => {
    setWsStatus(false);
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
      handleIncomingItem(payload);
      return;
    }

    if (payload.type === "gallery_item_updated" && payload.item) {
      handleIncomingItem(payload.item);
      return;
    }

    if (payload.type === "gallery_item_deleted" && payload.jobId) {
      removeRoamingItemById(String(payload.jobId));
      if (state.presenting && state.presenting.id === String(payload.jobId)) {
        clearPresentationTimers();
        state.presenting = null;
        renderCenterCard();
        processPresentationQueue();
      }
      return;
    }

    if (payload.type === "queue_updated") {
      handleQueueSnapshot(payload.jobs);
      return;
    }

    if (payload.type === "generation_error" && payload.jobId) {
      if (state.presenting && state.presenting.id === String(payload.jobId)) {
        clearPresentationTimers();
        state.presenting = null;
        renderCenterCard();
        processPresentationQueue();
      }
    }
  };
}

function onResize() {
  syncViewportSize();
  if (state.resizeTimer) {
    clearTimeout(state.resizeTimer);
  }
  state.resizeTimer = setTimeout(() => {
    applyDisplayMode(getDisplayMode());
  }, RESIZE_DEBOUNCE_MS);
}

async function initializeShowcase() {
  syncViewportSize();
  applyDisplayMode(getDisplayMode());
  initializeCraftpixBackgrounds();
  initializeShowcaseMusic();
  setWsStatus(false);
  renderCenterCard();

  await refreshSnapshots({ initial: true });

  connectWebSocket();
  window.addEventListener("resize", onResize, { passive: true });
  window.addEventListener("orientationchange", onResize, { passive: true });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", onResize, { passive: true });
    window.visualViewport.addEventListener("scroll", onResize, { passive: true });
  }

  state.pollTimer = setInterval(() => {
    refreshSnapshots().catch(() => {
      // Ignore transient polling errors.
    });
  }, SHOWCASE_POLL_MS);
}

initializeShowcase().catch(() => {
  renderCenterCard();
});
