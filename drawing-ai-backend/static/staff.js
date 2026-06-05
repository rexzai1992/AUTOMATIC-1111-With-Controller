const visitorNameInput = document.getElementById("visitorName");
const visitorNotesInput = document.getElementById("visitorNotes");
const drawingFileInput = document.getElementById("drawingFile");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const controlHint = document.getElementById("controlHint");
const generationModeSelect = document.getElementById("generationModeSelect");
const styleSelectWrap = document.getElementById("styleSelectWrap");
const styleIdSelect = document.getElementById("styleIdSelect");
const modePresetInfoBox = document.getElementById("modePresetInfoBox");
const modePresetInfoText = document.getElementById("modePresetInfoText");
const modeControlNetInfoText = document.getElementById("modeControlNetInfoText");
const modeModelNameText = document.getElementById("modeModelNameText");
const modeGenerationSettingsText = document.getElementById("modeGenerationSettingsText");
const modeWarningText = document.getElementById("modeWarningText");
const aiArtVentureEnabledToggle = document.getElementById("aiArtVentureEnabledToggle");
const aiArtVenturePanel = document.getElementById("aiArtVenturePanel");
const randomStyleEnabledToggle = document.getElementById("randomStyleEnabledToggle");
const randomThemeEnabledToggle = document.getElementById("randomThemeEnabledToggle");
const aiArtVentureStyleSelect = document.getElementById("aiArtVentureStyleSelect");
const aiArtVentureThemeSelect = document.getElementById("aiArtVentureThemeSelect");
const aiArtVentureCustomTheme = document.getElementById("aiArtVentureCustomTheme");
const resetCustomThemeBtn = document.getElementById("resetCustomThemeBtn");
const currentSelectedStyleName = document.getElementById("currentSelectedStyleName");
const currentSelectedThemeName = document.getElementById("currentSelectedThemeName");
const selectedThemePromptText = document.getElementById("selectedThemePromptText");
const lastGeneratedStyleName = document.getElementById("lastGeneratedStyleName");
const lastGeneratedThemeName = document.getElementById("lastGeneratedThemeName");
const aiArtVenturePromptPreview = document.getElementById("aiArtVenturePromptPreview");
const randomStyleNote = document.getElementById("randomStyleNote");
const randomThemeNote = document.getElementById("randomThemeNote");
const customThemeNote = document.getElementById("customThemeNote");
const staffLanUrl = document.getElementById("staffLanUrl");
const galleryLanUrl = document.getElementById("galleryLanUrl");
const comfyStaffLanUrl = document.getElementById("comfyStaffLanUrl");
const showcaseLanUrl = document.getElementById("showcaseLanUrl");
const wonderparkLanUrl = document.getElementById("wonderparkLanUrl");
const publicGalleryLanUrl = document.getElementById("publicGalleryLanUrl");

const statusText = document.getElementById("statusText");
const jobIdText = document.getElementById("jobIdText");
const visitorText = document.getElementById("visitorText");
const presetText = document.getElementById("presetText");
const promptModeText = document.getElementById("promptModeText");
const estimatedTimeText = document.getElementById("estimatedTimeText");
const elapsedTimeText = document.getElementById("elapsedTimeText");
const finalDurationText = document.getElementById("finalDurationText");
const generationEngineText = document.getElementById("generationEngineText");
const generationWorkflowText = document.getElementById("generationWorkflowText");

const inputPreviewLink = document.getElementById("inputPreviewLink");
const inputPreviewImage = document.getElementById("inputPreviewImage");
const outputPreviewLink = document.getElementById("outputPreviewLink");
const outputPreviewImage = document.getElementById("outputPreviewImage");
const photoPrintLink = document.getElementById("photoPrintLink");

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
const comparisonReviewBox = document.querySelector(".comparison-review-box");
const autoReviewBox = document.getElementById("autoReviewBox");
const autoRatingText = document.getElementById("autoRatingText");
const autoConfidenceText = document.getElementById("autoConfidenceText");
const autoBadTagsText = document.getElementById("autoBadTagsText");
const autoGoodTagsText = document.getElementById("autoGoodTagsText");
const autoNotesText = document.getElementById("autoNotesText");
const applyAutoReviewBtn = document.getElementById("applyAutoReviewBtn");
const AUTO_RATING_ONLY = true;

const galleryControlList = document.getElementById("galleryControlList");
const refreshGalleryControlBtn = document.getElementById("refreshGalleryControlBtn");
const clearGalleryControlBtn = document.getElementById("clearGalleryControlBtn");

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
      { id: "person_unrecognizable", label: "Person unrecognizable" },
      { id: "face_identity_changed", label: "Face identity changed" },
      { id: "gender_changed", label: "Gender changed" },
      { id: "clothing_changed", label: "Clothing changed" },
      { id: "shirt_changed", label: "Shirt changed" },
      { id: "outfit_changed", label: "Outfit changed" },
      { id: "main_object_missing", label: "Main object missing" },
      { id: "creation_unrecognizable", label: "Creation unrecognizable" },
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
      { id: "too_much_change", label: "Too much change" },
      { id: "creepy", label: "Creepy (legacy)" },
      { id: "background_wrong", label: "Background wrong" },
      { id: "background_not_changed", label: "Background not changed" },
      { id: "background_too_plain", label: "Background too plain" },
      { id: "too_messy", label: "Too messy" },
      { id: "style_wrong", label: "Style wrong" },
      { id: "style_too_weak", label: "Style too weak" },
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
const JOB_STATUS_POLL_INTERVAL_MS = 3000;
const BACKEND_STATUS_POLL_INTERVAL_MS = 20000;

const GENERATION_MODE_IDS = {
  DRAWING_TO_ARTWORK: "drawing_to_artwork",
  PERSON_HOLDING_ARTWORK: "person_holding_artwork",
  AI_ART_VENTURE: "ai_art_venture"
};

const AI_ART_VENTURE_THEMES = Array.isArray(window.AI_ART_VENTURE_THEME_PRESETS)
  ? window.AI_ART_VENTURE_THEME_PRESETS
  : [];
const AI_ART_VENTURE_FUN_STYLES = Array.isArray(window.AI_ART_VENTURE_STYLE_PRESETS)
  ? window.AI_ART_VENTURE_STYLE_PRESETS
  : [];
const AI_ART_VENTURE_DEFAULT_UI_SETTINGS = {
  enabled: false,
  randomStyleEnabled: true,
  randomThemeEnabled: false,
  selectedStyleId: "pixar_3d",
  selectedThemeId: "underwater-world",
  customTheme: "",
  ...(window.AI_ART_VENTURE_DEFAULTS && typeof window.AI_ART_VENTURE_DEFAULTS === "object"
    ? window.AI_ART_VENTURE_DEFAULTS
    : {})
};
const AI_ART_VENTURE_NEGATIVE_APPEND = String(
  window.AI_ART_VENTURE_NEGATIVE_APPEND
  || "white background, plain background, empty background, transparent background, studio background, blank wall"
);
const AI_ART_VENTURE_STORAGE_KEYS = {
  randomStyleEnabled: "staff.aiArtVentureRandomStyleEnabled",
  randomThemeEnabled: "staff.aiArtVentureRandomThemeEnabled",
  selectedStyleId: "staff.aiArtVentureSelectedStyleId",
  selectedThemeId: "staff.aiArtVentureSelectedThemeId",
  customTheme: "staff.aiArtVentureCustomTheme"
};

const AI_ART_VENTURE_FALLBACK_STYLES = [
  { id: "pixar_3d", label: "Pixar 3D", styleRiskLevel: "experimental", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.68, cfgScale: 7.5 } },
  { id: "disney_3d", label: "Disney 3D", styleRiskLevel: "experimental", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.68, cfgScale: 7.5 } },
  { id: "anime_movie", label: "Anime Movie", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.41, softEdgeWeight: 0.80, controlWeight: 0.80, ipAdapterWeight: 0.66, cfgScale: 7.4 } },
  { id: "watercolor", label: "Watercolor", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.42, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.64, cfgScale: 7.5 } },
  { id: "oil_painting", label: "Oil Painting", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.5, steps: 34 } },
  { id: "renaissance", label: "Renaissance", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.5, steps: 34 } },
  { id: "da_vinci", label: "Da Vinci", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.4, steps: 34 } },
  { id: "comic_book", label: "Comic Book", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.39, softEdgeWeight: 0.82, controlWeight: 0.82, ipAdapterWeight: 0.64, cfgScale: 7.3 } },
  { id: "manga", label: "Manga", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.39, softEdgeWeight: 0.82, controlWeight: 0.82, ipAdapterWeight: 0.65, cfgScale: 7.2 } },
  { id: "doodle", label: "Doodle", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.36, softEdgeWeight: 0.84, controlWeight: 0.84, ipAdapterWeight: 0.62, cfgScale: 6.8 } },
  { id: "lego_3d", label: "LEGO 3D", styleRiskLevel: "experimental", overrides: { denoisingStrength: 0.45, softEdgeWeight: 0.74, controlWeight: 0.74, ipAdapterWeight: 0.70, cfgScale: 7.4 } },
  { id: "clay_toy", label: "Clay Toy", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.42, softEdgeWeight: 0.80, controlWeight: 0.80, ipAdapterWeight: 0.65, cfgScale: 7.5 } },
  { id: "plush_toy", label: "Plush Toy", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.42, softEdgeWeight: 0.80, controlWeight: 0.80, ipAdapterWeight: 0.66, cfgScale: 7.3 } },
  { id: "fantasy_epic", label: "Fantasy Epic", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.43, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.5 } },
  { id: "cyberpunk", label: "Cyberpunk", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.42, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.5 } },
  { id: "steampunk", label: "Steampunk", styleRiskLevel: "balanced", overrides: { denoisingStrength: 0.42, softEdgeWeight: 0.78, controlWeight: 0.78, ipAdapterWeight: 0.66, cfgScale: 7.4 } },
  { id: "minecraft", label: "Minecraft", styleRiskLevel: "experimental", overrides: { denoisingStrength: 0.46, softEdgeWeight: 0.74, controlWeight: 0.74, ipAdapterWeight: 0.70, cfgScale: 7.4 } },
  { id: "low_poly", label: "Low Poly", styleRiskLevel: "experimental", overrides: { denoisingStrength: 0.45, softEdgeWeight: 0.74, controlWeight: 0.74, ipAdapterWeight: 0.70, cfgScale: 7.3 } },
  { id: "storybook", label: "Storybook", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.40, softEdgeWeight: 0.80, controlWeight: 0.80, ipAdapterWeight: 0.64, cfgScale: 7.4 } },
  { id: "paper_cut", label: "Paper Cut", styleRiskLevel: "safe", overrides: { denoisingStrength: 0.40, softEdgeWeight: 0.82, controlWeight: 0.82, ipAdapterWeight: 0.64, cfgScale: 7.3 } }
];

const MODE_SETTINGS_FALLBACK = {
  generationModes: [
    { id: GENERATION_MODE_IDS.DRAWING_TO_ARTWORK, label: "Drawing to Artwork", supportsStyles: true, defaultStyleId: "auto" },
    { id: GENERATION_MODE_IDS.PERSON_HOLDING_ARTWORK, label: "Person Holding Artwork", supportsStyles: true, defaultStyleId: "auto" },
    { id: GENERATION_MODE_IDS.AI_ART_VENTURE, label: "AI Art Venture", supportsStyles: true, defaultStyleId: "pixar_3d" }
  ],
  defaultGenerationMode: GENERATION_MODE_IDS.DRAWING_TO_ARTWORK,
  defaultStyleId: "auto",
  standardStyles: [
    { id: "auto", label: "Auto" },
    { id: "storybook", label: "Storybook" },
    { id: "storybook_plus", label: "Storybook Plus" },
    { id: "watercolor", label: "Watercolor" },
    { id: "cartoon", label: "Cartoon" },
    { id: "anime", label: "Anime" },
    { id: "pixel", label: "Pixel" }
  ],
  aiArtVenture: {
    modeId: GENERATION_MODE_IDS.AI_ART_VENTURE,
    modeLabel: "AI Art Venture",
    defaultStyleId: "pixar_3d",
    baseSettings: {
      checkpoint: "DreamShaper_8_pruned.safetensors [879db523c3]",
      controlNetModel: "control_v11p_sd15_softedge",
      controlNetModule: "softedge_teed",
      controlMode: "Balanced",
      resizeMode: "Crop and Resize",
      pixelPerfect: true,
      guidanceStart: 0.0,
      guidanceEnd: 1.0,
      controlWeight: 0.78,
      softEdgeWeight: 0.78,
      denoisingStrength: 0.40,
      cfgScale: 7.4,
      steps: 32,
      samplerName: "DPM++ 2M Karras",
      width: 768,
      height: 768,
      useIpAdapter: true,
      ipAdapterModule: "ip-adapter_face_id_plus",
      ipAdapterModel: "ip-adapter-faceid-plusv2_sd15",
      ipAdapterWeight: 0.62,
      identitySafetyMode: true,
      experimentalMode: false
    },
    styles: AI_ART_VENTURE_FALLBACK_STYLES
  }
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
let modeSettings = JSON.parse(JSON.stringify(MODE_SETTINGS_FALLBACK));
let jobStatusPollTimerId = null;
let backendStatusPollTimerId = null;
let lastNonAiGenerationMode = GENERATION_MODE_IDS.DRAWING_TO_ARTWORK;
let aiArtVentureUiState = {
  enabled: Boolean(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.enabled),
  randomStyleEnabled: Boolean(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.randomStyleEnabled),
  randomThemeEnabled: Boolean(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.randomThemeEnabled),
  selectedStyleId: String(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedStyleId || "pixar_3d"),
  selectedThemeId: String(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedThemeId || "underwater-world"),
  customTheme: String(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.customTheme || ""),
  lastGeneratedStyleName: "-",
  lastGeneratedThemeName: "-",
  lastGeneratedPrompt: "-",
  lastGeneratedBackendStyleId: ""
};
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
  const routeMap = [
    [staffLanUrl, `${base}/staff`],
    [galleryLanUrl, `${base}/gallery`],
    [comfyStaffLanUrl, `${base}/comfy/staff`],
    [showcaseLanUrl, `${base}/showcase`],
    [wonderparkLanUrl, `${base}/public/wonderpark`],
    [publicGalleryLanUrl, `${base}/publicgallery`]
  ];
  for (const [node, url] of routeMap) {
    if (!node) {
      continue;
    }
    node.href = url;
    node.textContent = url;
  }
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

function setPhotoPrintLink(jobId, visible = true) {
  if (!photoPrintLink) {
    return;
  }
  const safeJobId = String(jobId || "").trim();
  photoPrintLink.hidden = !visible || !safeJobId;
  photoPrintLink.href = safeJobId ? `/photo/${encodeURIComponent(safeJobId)}` : "#";
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

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function pickRandom(items) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }
  return items[Math.floor(Math.random() * items.length)] || null;
}

function parseStoredBool(value, fallback) {
  if (typeof value !== "string") {
    return Boolean(fallback);
  }
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return Boolean(fallback);
}

function readLocalStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function writeLocalStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    // Ignore storage quota/security errors for staff UX resilience.
  }
}

function getAiArtVentureThemeById(themeId) {
  const normalized = String(themeId || "").trim().toLowerCase();
  return AI_ART_VENTURE_THEMES.find((theme) => String(theme?.id || "").trim().toLowerCase() === normalized) || null;
}

function normalizeAiStyleRisk(value) {
  const risk = String(value || "").trim().toLowerCase();
  if (risk === "safe" || risk === "balanced" || risk === "experimental") {
    return risk;
  }
  return "balanced";
}

function getAiArtVentureStylePresets() {
  const backendStyles = Array.isArray(modeSettings?.aiArtVenture?.styles) ? modeSettings.aiArtVenture.styles : [];
  if (backendStyles.length > 0) {
    const staticById = new Map(
      AI_ART_VENTURE_FUN_STYLES.map((style) => [String(style?.id || "").trim().toLowerCase(), style])
    );
    return backendStyles
      .filter((style) => style && typeof style === "object")
      .map((style) => {
        const id = String(style.id || "").trim();
        const key = id.toLowerCase();
        const staticStyle = staticById.get(key);
        return {
          id,
          name: String(style.label || staticStyle?.name || id || "Style"),
          label: String(style.label || staticStyle?.label || id || "Style"),
          backendStyleId: String(style.id || staticStyle?.backendStyleId || id),
          styleRiskLevel: normalizeAiStyleRisk(style.styleRiskLevel || staticStyle?.styleRiskLevel || "balanced"),
          prompt: String(style.stylePrompt || staticStyle?.prompt || ""),
        };
      });
  }
  return AI_ART_VENTURE_FUN_STYLES.map((style) => ({
    ...style,
    id: String(style?.id || ""),
    backendStyleId: String(style?.backendStyleId || style?.id || ""),
    styleRiskLevel: normalizeAiStyleRisk(style?.styleRiskLevel || "balanced"),
    name: String(style?.name || style?.label || style?.id || "Style"),
  }));
}

function getAiArtVentureFunStyleById(styleId) {
  const normalized = String(styleId || "").trim().toLowerCase();
  return getAiArtVentureStylePresets().find((style) => String(style?.id || "").trim().toLowerCase() === normalized) || null;
}

function normalizeAiArtVentureUiState() {
  const stylePresets = getAiArtVentureStylePresets();
  const configuredDefaultStyleId = String(
    modeSettings?.aiArtVenture?.defaultStyleId
    || AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedStyleId
    || "pixar_3d"
  );
  const fallbackStyle = getAiArtVentureFunStyleById(configuredDefaultStyleId)
    || stylePresets[0]
    || { id: "pixar_3d", backendStyleId: "pixar_3d", name: "Pixar 3D", styleRiskLevel: "experimental" };
  const fallbackTheme = getAiArtVentureThemeById(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedThemeId)
    || AI_ART_VENTURE_THEMES[0]
    || { id: "underwater-world" };

  const selectedStyle = getAiArtVentureFunStyleById(aiArtVentureUiState.selectedStyleId) || fallbackStyle;
  const selectedTheme = getAiArtVentureThemeById(aiArtVentureUiState.selectedThemeId) || fallbackTheme;

  aiArtVentureUiState.enabled = Boolean(aiArtVentureUiState.enabled);
  aiArtVentureUiState.randomStyleEnabled = Boolean(aiArtVentureUiState.randomStyleEnabled);
  aiArtVentureUiState.randomThemeEnabled = Boolean(aiArtVentureUiState.randomThemeEnabled);
  aiArtVentureUiState.selectedStyleId = String(selectedStyle.id || fallbackStyle.id || "pixar_3d");
  aiArtVentureUiState.selectedThemeId = String(selectedTheme.id || fallbackTheme.id || "underwater-world");
  aiArtVentureUiState.customTheme = String(aiArtVentureUiState.customTheme || "").trim();
  aiArtVentureUiState.lastGeneratedStyleName = String(aiArtVentureUiState.lastGeneratedStyleName || "-");
  aiArtVentureUiState.lastGeneratedThemeName = String(aiArtVentureUiState.lastGeneratedThemeName || "-");
  aiArtVentureUiState.lastGeneratedPrompt = String(aiArtVentureUiState.lastGeneratedPrompt || "-");
  aiArtVentureUiState.lastGeneratedBackendStyleId = String(aiArtVentureUiState.lastGeneratedBackendStyleId || "");
}

function loadAiArtVentureUiStateFromLocalStorage() {
  // Keep AI mode opt-in per session so stale localStorage cannot silently
  // force normal generations into AI Art Venture mode.
  aiArtVentureUiState.enabled = Boolean(AI_ART_VENTURE_DEFAULT_UI_SETTINGS.enabled);
  aiArtVentureUiState.randomStyleEnabled = parseStoredBool(
    readLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.randomStyleEnabled),
    AI_ART_VENTURE_DEFAULT_UI_SETTINGS.randomStyleEnabled
  );
  aiArtVentureUiState.randomThemeEnabled = parseStoredBool(
    readLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.randomThemeEnabled),
    AI_ART_VENTURE_DEFAULT_UI_SETTINGS.randomThemeEnabled
  );
  aiArtVentureUiState.selectedStyleId = String(
    readLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.selectedStyleId)
    || AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedStyleId
    || "pixar_3d"
  );
  aiArtVentureUiState.selectedThemeId = String(
    readLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.selectedThemeId)
    || AI_ART_VENTURE_DEFAULT_UI_SETTINGS.selectedThemeId
    || "underwater-world"
  );
  aiArtVentureUiState.customTheme = String(
    readLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.customTheme)
    || AI_ART_VENTURE_DEFAULT_UI_SETTINGS.customTheme
    || ""
  );
  normalizeAiArtVentureUiState();
}

function saveAiArtVentureUiStateToLocalStorage() {
  writeLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.randomStyleEnabled, String(Boolean(aiArtVentureUiState.randomStyleEnabled)));
  writeLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.randomThemeEnabled, String(Boolean(aiArtVentureUiState.randomThemeEnabled)));
  writeLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.selectedStyleId, String(aiArtVentureUiState.selectedStyleId || "pixar_3d"));
  writeLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.selectedThemeId, String(aiArtVentureUiState.selectedThemeId || "underwater-world"));
  writeLocalStorage(AI_ART_VENTURE_STORAGE_KEYS.customTheme, String(aiArtVentureUiState.customTheme || ""));
}

function buildRiskBadgeText(riskLevel) {
  const risk = normalizeAiStyleRisk(riskLevel);
  if (risk === "safe") {
    return "Safe";
  }
  if (risk === "experimental") {
    return "Experimental";
  }
  return "Balanced";
}

function appendAiStyleOptions(targetSelect, styles) {
  if (!targetSelect) {
    return;
  }
  targetSelect.innerHTML = "";
  const grouped = {
    safe: [],
    balanced: [],
    experimental: [],
  };
  styles.forEach((style) => {
    const risk = normalizeAiStyleRisk(style?.styleRiskLevel);
    grouped[risk].push(style);
  });
  ["safe", "balanced", "experimental"].forEach((riskKey) => {
    const rows = grouped[riskKey];
    if (!rows.length) {
      return;
    }
    const optGroup = document.createElement("optgroup");
    optGroup.label = buildRiskBadgeText(riskKey);
    rows.forEach((style) => {
      const option = document.createElement("option");
      option.value = String(style.id || "");
      option.textContent = `${String(style.name || style.label || style.id || "Style")} [${buildRiskBadgeText(riskKey)}]`;
      optGroup.appendChild(option);
    });
    targetSelect.appendChild(optGroup);
  });
}

function rebuildAiArtVenturePresetControls() {
  const stylePresets = getAiArtVentureStylePresets();
  if (aiArtVentureStyleSelect) {
    appendAiStyleOptions(aiArtVentureStyleSelect, stylePresets);
  }

  if (aiArtVentureThemeSelect) {
    aiArtVentureThemeSelect.innerHTML = "";
    AI_ART_VENTURE_THEMES.forEach((theme) => {
      const option = document.createElement("option");
      option.value = String(theme.id || "");
      option.textContent = String(theme.name || theme.id || "Theme");
      aiArtVentureThemeSelect.appendChild(option);
    });
  }
}

function composeAiArtVentureFinalPrompt(stylePrompt, themePrompt) {
  return [
    `Transform the uploaded image into ${stylePrompt}.`,
    "",
    "Keep the person identity, gender, face shape, hairstyle, skin tone, shirt color, outfit, body pose, and handmade creation recognizable and consistent with the original image.",
    "",
    `Replace the plain white background with ${themePrompt}.`,
    "",
    "The background must be visible, detailed, colorful, and match the selected style. Do not leave the background white, empty, plain, transparent, or studio-like.",
    "",
    "The person should still be holding their creation clearly in the foreground.",
    "The handmade creation must remain clearly visible and recognizable.",
    "Do not change the person's gender.",
    "Do not change the outfit into a suit, dress, costume, uniform, or different clothing.",
    "Do not replace the creation/object with a different object.",
    "Do not crop out the creation.",
    "Do not hide the hands."
  ].join("\n").trim();
}

function appendNegativePrompt(basePrompt, appendPrompt) {
  const base = String(basePrompt || "").trim();
  const append = String(appendPrompt || "").trim();
  if (!append) {
    return base;
  }
  if (!base) {
    return append;
  }
  if (base.toLowerCase().includes(append.toLowerCase())) {
    return base;
  }
  return `${base}, ${append}`;
}

function resolveAiArtVentureGenerationChoice() {
  normalizeAiArtVentureUiState();
  const stylePresets = getAiArtVentureStylePresets();
  const selectedStyle = getAiArtVentureFunStyleById(aiArtVentureUiState.selectedStyleId)
    || stylePresets[0]
    || null;
  const selectedTheme = getAiArtVentureThemeById(aiArtVentureUiState.selectedThemeId)
    || AI_ART_VENTURE_THEMES[0]
    || null;

  let finalStyle = selectedStyle;
  if (aiArtVentureUiState.randomStyleEnabled) {
    finalStyle = pickRandom(stylePresets) || selectedStyle;
  }

  const customThemeText = String(aiArtVentureUiState.customTheme || "").trim();
  let finalTheme = selectedTheme;
  if (aiArtVentureUiState.randomThemeEnabled && !customThemeText) {
    finalTheme = pickRandom(AI_ART_VENTURE_THEMES) || selectedTheme;
  }

  const finalThemeName = customThemeText ? "Custom Theme" : String(finalTheme?.name || selectedTheme?.name || "Theme");
  const finalThemePrompt = customThemeText
    ? customThemeText
    : String(finalTheme?.prompt || selectedTheme?.prompt || "a colorful imaginative environment");
  const finalThemeId = customThemeText ? "custom-theme" : String(finalTheme?.id || selectedTheme?.id || "");
  const finalStyleName = String(finalStyle?.name || selectedStyle?.name || "Style");
  const finalStyleId = String(finalStyle?.id || selectedStyle?.id || "pixar_3d");
  const backendStyleId = String(finalStyle?.backendStyleId || finalStyle?.id || "pixar_3d");
  const finalPrompt = composeAiArtVentureFinalPrompt(String(finalStyle?.prompt || ""), finalThemePrompt);
  const backendNegativeBase = String(modeSettings?.aiArtVenture?.negativePrompt || "");
  const negativePrompt = appendNegativePrompt(backendNegativeBase, AI_ART_VENTURE_NEGATIVE_APPEND);

  return {
    finalStyleId,
    finalStyleName,
    backendStyleId,
    finalThemeId,
    finalThemeName,
    finalThemePrompt,
    finalPrompt,
    negativePrompt
  };
}

function applyAiArtVentureUiStateToControls() {
  normalizeAiArtVentureUiState();
  if (aiArtVentureEnabledToggle) {
    aiArtVentureEnabledToggle.checked = Boolean(aiArtVentureUiState.enabled);
  }
  if (randomStyleEnabledToggle) {
    randomStyleEnabledToggle.checked = Boolean(aiArtVentureUiState.randomStyleEnabled);
  }
  if (randomThemeEnabledToggle) {
    randomThemeEnabledToggle.checked = Boolean(aiArtVentureUiState.randomThemeEnabled);
  }
  if (aiArtVentureStyleSelect) {
    aiArtVentureStyleSelect.value = aiArtVentureUiState.selectedStyleId;
  }
  if (aiArtVentureThemeSelect) {
    aiArtVentureThemeSelect.value = aiArtVentureUiState.selectedThemeId;
  }
  if (aiArtVentureCustomTheme) {
    aiArtVentureCustomTheme.value = aiArtVentureUiState.customTheme;
  }

  const selectedStyle = getAiArtVentureFunStyleById(aiArtVentureUiState.selectedStyleId);
  const selectedTheme = getAiArtVentureThemeById(aiArtVentureUiState.selectedThemeId);
  if (currentSelectedStyleName) {
    const selectedRisk = buildRiskBadgeText(selectedStyle?.styleRiskLevel || "balanced");
    currentSelectedStyleName.textContent = selectedStyle
      ? `${String(selectedStyle?.name || selectedStyle?.label || selectedStyle?.id || "Style")} [${selectedRisk}]`
      : "-";
  }
  if (currentSelectedThemeName) {
    currentSelectedThemeName.textContent = String(selectedTheme?.name || "-");
  }
  if (selectedThemePromptText) {
    selectedThemePromptText.textContent = String(selectedTheme?.prompt || "-");
  }
  if (lastGeneratedStyleName) {
    lastGeneratedStyleName.textContent = aiArtVentureUiState.lastGeneratedStyleName;
  }
  if (lastGeneratedThemeName) {
    lastGeneratedThemeName.textContent = aiArtVentureUiState.lastGeneratedThemeName;
  }
  if (aiArtVenturePromptPreview) {
    aiArtVenturePromptPreview.textContent = aiArtVentureUiState.lastGeneratedPrompt;
  }
  if (randomStyleNote) {
    randomStyleNote.hidden = !aiArtVentureUiState.randomStyleEnabled;
  }
  if (randomThemeNote) {
    randomThemeNote.hidden = !aiArtVentureUiState.randomThemeEnabled;
  }
  if (customThemeNote) {
    customThemeNote.hidden = !Boolean(String(aiArtVentureUiState.customTheme || "").trim());
  }
}

function isAiArtVentureEnabledFromToggle() {
  return Boolean(aiArtVentureEnabledToggle?.checked);
}

function syncModeFromAiArtVentureToggle() {
  if (!generationModeSelect) {
    return;
  }

  const aiEnabled = isAiArtVentureEnabledFromToggle();
  const currentMode = String(generationModeSelect.value || "");
  if (!isAiArtVentureMode(currentMode)) {
    lastNonAiGenerationMode = currentMode || lastNonAiGenerationMode;
  }

  if (aiEnabled) {
    generationModeSelect.value = GENERATION_MODE_IDS.AI_ART_VENTURE;
    if (!loading) {
      generationModeSelect.disabled = true;
    }
  } else {
    if (!loading) {
      generationModeSelect.disabled = false;
    }
    if (isAiArtVentureMode(generationModeSelect.value)) {
      const availableModes = Array.from(generationModeSelect.options).map((option) => option.value);
      const fallbackMode = availableModes.includes(lastNonAiGenerationMode)
        ? lastNonAiGenerationMode
        : (availableModes.includes(modeSettings.defaultGenerationMode)
          ? modeSettings.defaultGenerationMode
          : GENERATION_MODE_IDS.DRAWING_TO_ARTWORK);
      generationModeSelect.value = String(fallbackMode || GENERATION_MODE_IDS.DRAWING_TO_ARTWORK);
    }
  }

  if (aiArtVenturePanel) {
    aiArtVenturePanel.hidden = !aiEnabled;
  }
}

function initializeAiArtVenturePanel() {
  rebuildAiArtVenturePresetControls();
  loadAiArtVentureUiStateFromLocalStorage();
  applyAiArtVentureUiStateToControls();
  syncModeFromAiArtVentureToggle();
}

function isAiArtVentureMode(modeId) {
  return String(modeId || "").trim().toLowerCase() === GENERATION_MODE_IDS.AI_ART_VENTURE;
}

function getGenerationModeValue() {
  if (!generationModeSelect) {
    return String(modeSettings.defaultGenerationMode || GENERATION_MODE_IDS.DRAWING_TO_ARTWORK);
  }
  return String(generationModeSelect.value || modeSettings.defaultGenerationMode || GENERATION_MODE_IDS.DRAWING_TO_ARTWORK);
}

function getStyleValueForMode(modeId) {
  const mode = String(modeId || "");
  if (isAiArtVentureMode(mode) && isAiArtVentureEnabledFromToggle()) {
    const selectedStyle = getAiArtVentureFunStyleById(aiArtVentureUiState.selectedStyleId);
    if (selectedStyle?.backendStyleId || selectedStyle?.id) {
      return String(selectedStyle.backendStyleId || selectedStyle.id);
    }
  }
  if (!styleIdSelect) {
    return isAiArtVentureMode(mode)
      ? String(modeSettings?.aiArtVenture?.defaultStyleId || "pixar_3d")
      : "auto";
  }
  if (styleIdSelect.value) {
    return String(styleIdSelect.value);
  }
  return isAiArtVentureMode(mode)
    ? String(modeSettings?.aiArtVenture?.defaultStyleId || "pixar_3d")
    : "auto";
}

function getAiArtStyle(styleId) {
  const styles = Array.isArray(modeSettings?.aiArtVenture?.styles) ? modeSettings.aiArtVenture.styles : [];
  const normalized = String(styleId || "").trim().toLowerCase();
  const byId = styles.find((style) => String(style?.id || "").trim().toLowerCase() === normalized);
  if (byId) {
    return byId;
  }
  const defaultId = String(modeSettings?.aiArtVenture?.defaultStyleId || "pixar_3d").trim().toLowerCase();
  return styles.find((style) => String(style?.id || "").trim().toLowerCase() === defaultId) || styles[0] || null;
}

function renderModePresetInfo() {
  if (!modePresetInfoBox || !modePresetInfoText || !modeControlNetInfoText || !modeModelNameText || !modeGenerationSettingsText || !modeWarningText) {
    return;
  }

  const mode = getGenerationModeValue();
  if (!isAiArtVentureMode(mode)) {
    modePresetInfoBox.hidden = true;
    if (styleSelectWrap) {
      styleSelectWrap.hidden = true;
    }
    return;
  }

  const aiConfig = modeSettings?.aiArtVenture || {};
  const base = aiConfig.baseSettings && typeof aiConfig.baseSettings === "object" ? aiConfig.baseSettings : {};
  const backendStyleId = getStyleValueForMode(mode);
  const style = getAiArtStyle(backendStyleId) || {};
  const overrides = style.overrides && typeof style.overrides === "object" ? style.overrides : {};
  const effective = { ...base, ...overrides };
  const styleRiskLevel = normalizeAiStyleRisk(style.styleRiskLevel || "balanced");
  const uiStyle = getAiArtVentureFunStyleById(aiArtVentureUiState.selectedStyleId);
  const softEdgeWeight = effective.softEdgeWeight ?? effective.controlWeight ?? 0.78;
  const ipAdapterWeight = effective.ipAdapterWeight ?? 0.62;
  const ipStatus = aiConfig.ipAdapterStatus && typeof aiConfig.ipAdapterStatus === "object"
    ? aiConfig.ipAdapterStatus
    : {};
  const ipAdapterEnabled = Boolean(
    ipStatus.enabled ?? effective.ipAdapterFaceIdEnabled ?? effective.ipAdapterDetected ?? false
  );
  const ipAdapterModule = String(
    ipStatus.module
    || effective.ipAdapterModule
    || "ip-adapter_face_id_plus"
  );
  const ipAdapterModel = String(
    ipStatus.model
    || effective.ipAdapterModel
    || "ip-adapter-faceid-plusv2_sd15"
  );
  const ipAdapterWarning = String(ipStatus.warning || effective.ipAdapterWarning || "").trim();
  const styleLabel = isAiArtVentureEnabledFromToggle()
    ? String(uiStyle?.name || style.label || style.id || "Style")
    : String(style.label || style.id || "Style");

  if (styleSelectWrap) {
    styleSelectWrap.hidden = Boolean(isAiArtVentureEnabledFromToggle());
  }
  modePresetInfoBox.hidden = false;
  modePresetInfoText.textContent =
    `${styleLabel} | risk=${styleRiskLevel} | image-to-image stylization with recognizable subject/object transfer`;
  modeControlNetInfoText.textContent =
    `Unit1 SoftEdge: module=${effective.controlNetModule ?? "softedge_teed"}, `
    + `model=${effective.controlNetModel ?? "control_v11p_sd15_softedge"}, `
    + `weight=${softEdgeWeight}, mode=${effective.controlMode ?? "Balanced"} | `
    + `Unit2 FaceID: module=${ipAdapterModule}, model=${ipAdapterModel}, `
    + `enabled=${ipAdapterEnabled ? "yes" : "no"}, weight=${ipAdapterWeight}`;
  modeModelNameText.textContent = String(effective.checkpoint || "DreamShaper_8_pruned.safetensors [879db523c3]");
  modeGenerationSettingsText.textContent =
    `softEdgeWeight=${softEdgeWeight}, ipAdapterWeight=${ipAdapterWeight}, `
    + `denoisingStrength=${effective.denoisingStrength ?? 0.40}, cfgScale=${effective.cfgScale ?? 7.4}, `
    + `steps=${effective.steps ?? 32}, sampler=${effective.samplerName ?? "DPM++ 2M Karras"}, `
    + `size=${effective.width ?? 768}x${effective.height ?? 768}, `
    + `faceId=${ipAdapterEnabled ? "enabled" : "disabled"}`;

  const warnings = [];
  if (styleRiskLevel === "experimental") {
    warnings.push("Experimental style may change face/person more.");
  }
  if (!ipAdapterEnabled && ipAdapterWarning) {
    warnings.push(ipAdapterWarning);
  }
  modeWarningText.textContent = warnings.length > 0 ? warnings.join(" ") : "None";
}

function rebuildStyleOptionsForMode(modeId, preferredStyleId = "") {
  if (!styleIdSelect) {
    return;
  }

  const mode = String(modeId || "");
  const isAiMode = isAiArtVentureMode(mode);
  const styles = isAiMode
    ? (Array.isArray(modeSettings?.aiArtVenture?.styles) ? modeSettings.aiArtVenture.styles : [])
    : (Array.isArray(modeSettings?.standardStyles) ? modeSettings.standardStyles : []);

  styleIdSelect.innerHTML = "";
  if (isAiMode) {
    appendAiStyleOptions(
      styleIdSelect,
      styles.map((style) => ({
        ...style,
        name: String(style?.label || style?.id || "Style"),
      }))
    );
  } else {
    styles.forEach((style) => {
      if (!style || typeof style !== "object") {
        return;
      }
      const option = document.createElement("option");
      option.value = String(style.id || "");
      option.textContent = String(style.label || style.id || "Style");
      styleIdSelect.appendChild(option);
    });
  }

  const normalizedPreferred = String(preferredStyleId || "").trim().toLowerCase();
  let targetValue = "";
  if (normalizedPreferred) {
    const preferred = styles.find((row) => String(row?.id || "").trim().toLowerCase() === normalizedPreferred);
    if (preferred) {
      targetValue = String(preferred.id || "");
    }
  }

  if (!targetValue) {
    if (isAiMode) {
      targetValue = String(modeSettings?.aiArtVenture?.defaultStyleId || "pixar_3d");
    } else {
      targetValue = "auto";
    }
  }
  styleIdSelect.value = targetValue;
}

function applyGenerationModeUiState(preferredStyleId = "") {
  syncModeFromAiArtVentureToggle();
  const mode = getGenerationModeValue();
  const effectivePreferredStyleId = preferredStyleId
    || (isAiArtVentureMode(mode) ? getStyleValueForMode(mode) : "");
  rebuildStyleOptionsForMode(mode, effectivePreferredStyleId);
  rebuildAiArtVenturePresetControls();
  applyAiArtVentureUiStateToControls();
  renderModePresetInfo();
}

function normalizeModeSettingsPayload(rawPayload) {
  if (!rawPayload || typeof rawPayload !== "object") {
    return cloneJson(MODE_SETTINGS_FALLBACK);
  }

  const fallback = cloneJson(MODE_SETTINGS_FALLBACK);
  const payload = cloneJson(rawPayload);
  const result = { ...fallback, ...payload };
  if (!Array.isArray(result.generationModes) || result.generationModes.length === 0) {
    result.generationModes = fallback.generationModes;
  }
  if (!Array.isArray(result.standardStyles) || result.standardStyles.length === 0) {
    result.standardStyles = fallback.standardStyles;
  }
  if (!result.aiArtVenture || typeof result.aiArtVenture !== "object") {
    result.aiArtVenture = fallback.aiArtVenture;
  } else {
    result.aiArtVenture = {
      ...fallback.aiArtVenture,
      ...result.aiArtVenture,
      baseSettings: {
        ...fallback.aiArtVenture.baseSettings,
        ...(result.aiArtVenture.baseSettings && typeof result.aiArtVenture.baseSettings === "object"
          ? result.aiArtVenture.baseSettings
          : {})
      },
      styles: Array.isArray(result.aiArtVenture.styles) && result.aiArtVenture.styles.length > 0
        ? result.aiArtVenture.styles
        : fallback.aiArtVenture.styles
    };
  }
  return result;
}

async function loadGenerationModeSettings() {
  try {
    const response = await fetch("/settings/presets");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to load generation settings.");
    }
    modeSettings = normalizeModeSettingsPayload(payload);
  } catch (_error) {
    modeSettings = cloneJson(MODE_SETTINGS_FALLBACK);
  }

  if (!generationModeSelect) {
    return;
  }

  const selectedModeBefore = generationModeSelect.value || modeSettings.defaultGenerationMode || GENERATION_MODE_IDS.DRAWING_TO_ARTWORK;
  generationModeSelect.innerHTML = "";
  (modeSettings.generationModes || []).forEach((mode) => {
    if (!mode || typeof mode !== "object") {
      return;
    }
    const option = document.createElement("option");
    option.value = String(mode.id || "");
    option.textContent = String(mode.label || mode.id || "Mode");
    generationModeSelect.appendChild(option);
  });

  const availableModeValues = Array.from(generationModeSelect.options).map((option) => option.value);
  const fallbackMode = String(modeSettings.defaultGenerationMode || GENERATION_MODE_IDS.DRAWING_TO_ARTWORK);
  generationModeSelect.value = availableModeValues.includes(selectedModeBefore)
    ? selectedModeBefore
    : (availableModeValues.includes(fallbackMode) ? fallbackMode : availableModeValues[0]);
  if (!isAiArtVentureMode(generationModeSelect.value)) {
    lastNonAiGenerationMode = String(generationModeSelect.value || lastNonAiGenerationMode);
  }

  applyGenerationModeUiState();
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
  if (generationModeSelect) {
    generationModeSelect.disabled = nextLoading || isAiArtVentureEnabledFromToggle();
  }
  if (styleIdSelect) {
    styleIdSelect.disabled = nextLoading;
  }
  if (aiArtVentureEnabledToggle) {
    aiArtVentureEnabledToggle.disabled = nextLoading;
  }
  if (randomStyleEnabledToggle) {
    randomStyleEnabledToggle.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }
  if (randomThemeEnabledToggle) {
    randomThemeEnabledToggle.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }
  if (aiArtVentureStyleSelect) {
    aiArtVentureStyleSelect.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }
  if (aiArtVentureThemeSelect) {
    aiArtVentureThemeSelect.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }
  if (aiArtVentureCustomTheme) {
    aiArtVentureCustomTheme.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }
  if (resetCustomThemeBtn) {
    resetCustomThemeBtn.disabled = nextLoading || !isAiArtVentureEnabledFromToggle();
  }

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

function isTerminalJobStatus(statusValue) {
  const normalized = String(statusValue || "").trim().toLowerCase();
  return normalized === "completed" || normalized === "failed" || normalized === "cancelled";
}

function stopJobStatusPolling() {
  if (jobStatusPollTimerId) {
    window.clearInterval(jobStatusPollTimerId);
    jobStatusPollTimerId = null;
  }
}

function startJobStatusPolling() {
  if (!currentJobId || jobStatusPollTimerId) {
    return;
  }
  jobStatusPollTimerId = window.setInterval(() => {
    void fetchCurrentJobStatus({ silent: true });
  }, JOB_STATUS_POLL_INTERVAL_MS);
}

async function fetchCurrentJobStatus({ silent = false } = {}) {
  if (!currentJobId) {
    return;
  }
  const targetJobId = String(currentJobId);
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(targetJobId)}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Failed to load job ${targetJobId}.`);
    }

    const status = String(data.status || "").trim().toLowerCase();
    if (isTerminalJobStatus(status)) {
      const normalizedStatus = status === "completed"
        ? "Completed"
        : status === "failed"
          ? "Failed"
          : "Cancelled";
      updateStatusFromResult({ ...data, status: normalizedStatus }, "poll");
      stopJobStatusPolling();
      return;
    }

    if (status === "processing") {
      setStatus("Processing");
      if (data.startedAt) {
        startElapsedTimer(data.startedAt);
      }
      return;
    }

    if (status === "queued") {
      setStatus("Queued");
    }
  } catch (error) {
    if (!silent) {
      appendEvent(error.message || "Failed to poll current job status.", true);
    }
  }
}

function formatGenerationEngineLabel(engineValue) {
  const normalized = String(engineValue || "").trim().toLowerCase();
  if (normalized === "comfyui") {
    return "ComfyUI";
  }
  if (normalized === "stable_diffusion") {
    return "Stable Diffusion";
  }
  return "Unknown";
}

function setGenerationBackendStatusDisplay(healthPayload = null) {
  if (!generationEngineText || !generationWorkflowText) {
    return;
  }

  const payload = healthPayload && typeof healthPayload === "object" ? healthPayload : {};
  const backendPayload = payload.generationBackend && typeof payload.generationBackend === "object"
    ? payload.generationBackend
    : {};
  const rawEngine = String(payload.generationEngine || backendPayload.mode || "").trim().toLowerCase();
  const normalizedEngine = rawEngine === "comfyui" || rawEngine === "stable_diffusion"
    ? rawEngine
    : "unknown";

  generationEngineText.dataset.engine = normalizedEngine;
  generationEngineText.textContent = formatGenerationEngineLabel(rawEngine);

  const workflowPath = String(
    backendPayload.workflowPath
    || backendPayload.workflow_path
    || ""
  ).trim();
  if (normalizedEngine === "comfyui") {
    generationWorkflowText.textContent = workflowPath
      ? `Workflow: ${workflowPath}`
      : "Workflow: (not reported)";
    return;
  }
  if (normalizedEngine === "stable_diffusion") {
    generationWorkflowText.textContent = "Workflow: n/a";
    return;
  }
  generationWorkflowText.textContent = "Workflow: unavailable";
}

async function fetchGenerationBackendStatus({ silent = true } = {}) {
  try {
    const response = await fetch("/health");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to load backend health.");
    }
    setGenerationBackendStatusDisplay(data);
  } catch (error) {
    setGenerationBackendStatusDisplay(null);
    if (!silent) {
      appendEvent(error.message || "Failed to load backend health.", true);
    }
  }
}

function startBackendStatusPolling() {
  if (backendStatusPollTimerId) {
    window.clearInterval(backendStatusPollTimerId);
  }
  backendStatusPollTimerId = window.setInterval(() => {
    void fetchGenerationBackendStatus({ silent: true });
  }, BACKEND_STATUS_POLL_INTERVAL_MS);
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

function applyAutoRatingOnlyUi() {
  if (!AUTO_RATING_ONLY) {
    return;
  }
  if (applyAutoReviewBtn) {
    applyAutoReviewBtn.hidden = true;
  }
  if (starGroup) {
    starGroup.hidden = true;
  }
  if (tagGroup) {
    tagGroup.hidden = true;
  }
  if (comparisonReviewBox) {
    comparisonReviewBox.hidden = true;
  }
  const feedbackNoteLabel = document.querySelector('label[for="feedbackNote"]');
  if (feedbackNoteLabel) {
    feedbackNoteLabel.hidden = true;
  }
  if (feedbackNoteInput) {
    feedbackNoteInput.hidden = true;
  }
  if (saveRatingBtn) {
    saveRatingBtn.hidden = true;
    saveRatingBtn.disabled = true;
  }
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
  const resultMode = String(result.generationMode || getGenerationModeValue() || modeSettings.defaultGenerationMode);
  const resultStyle = String(result.styleId || getStyleValueForMode(resultMode));
  const normalizedStatus = String(result.status || "").trim().toLowerCase();
  if (isAiArtVentureMode(resultMode)) {
    aiArtVentureUiState.lastGeneratedStyleName = String(
      result.finalStyleName
      || result.styleLabel
      || aiArtVentureUiState.lastGeneratedStyleName
      || "-"
    );
    aiArtVentureUiState.lastGeneratedThemeName = String(
      result.finalThemeName
      || aiArtVentureUiState.lastGeneratedThemeName
      || "-"
    );
    aiArtVentureUiState.lastGeneratedPrompt = String(
      result.finalPrompt
      || settings.finalPrompt
      || aiArtVentureUiState.lastGeneratedPrompt
      || "-"
    );
    aiArtVentureUiState.lastGeneratedBackendStyleId = String(result.styleId || aiArtVentureUiState.lastGeneratedBackendStyleId || "");
    applyAiArtVentureUiStateToControls();
  }

  setStatus(result.status || "Completed");
  jobIdText.textContent = jobId;
  visitorText.textContent = result.visitorName || "-";
  presetText.textContent = result.preset || "-";
  promptModeText.textContent = result.promptMode || result.promptType || "-";

  if (generationModeSelect) {
    const modeValues = Array.from(generationModeSelect.options).map((option) => option.value);
    if (modeValues.includes(resultMode)) {
      generationModeSelect.value = resultMode;
      applyGenerationModeUiState(resultStyle);
    }
  }

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
  if (isTerminalJobStatus(normalizedStatus)) {
    stopJobStatusPolling();
  }

  if (result.inputUrl) {
    setPreview(inputPreviewLink, inputPreviewImage, result.inputUrl);
  }
  if (result.outputUrl) {
    setPreview(outputPreviewLink, outputPreviewImage, result.outputUrl);
    setPreviewLoading(outputPreviewLink, false);
    setPhotoPrintLink(result.jobId || currentJobId, true);
    ratingSection.hidden = false;
  } else if (normalizedStatus === "queued" || normalizedStatus === "processing") {
    setPhotoPrintLink("", false);
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

  const displayRating = Number(result.staffRating ?? result.rating ?? result.autoRating ?? currentAutoReview.autoRating ?? 0);
  if (Number.isInteger(displayRating) && displayRating >= 1 && displayRating <= 5) {
    const ratedAtText = result.ratedAt ? new Date(result.ratedAt).toLocaleString() : "just now";
    ratingStatus.textContent = `Auto rating: ${displayRating}/5 (${ratedAtText})`;
  } else {
    ratingStatus.textContent = "Auto rating not available yet.";
  }

  if (settings.controlWeight !== undefined || settings.denoisingStrength !== undefined) {
    appendEvent(
      `Completed ${jobId} with preset ${result.preset || "-"} mode=${resultMode} style=${resultStyle} `
      + `(weight ${settings.controlWeight ?? "-"}, denoise ${settings.denoisingStrength ?? "-"}).`
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
  stopJobStatusPolling();
  selectedRating = null;

  setSelectedRating(null);
  setSelectedFeedbackTags([]);
  setComparisonScoresToForm({});
  renderAutoReview(null);
  feedbackNoteInput.value = "";
  ratingStatus.textContent = "Auto rating not available yet.";
  ratingSection.hidden = true;

  stopElapsedTimer();
  resetStatusCards();

  setPreview(inputPreviewLink, inputPreviewImage, null);
  setPreview(outputPreviewLink, outputPreviewImage, null);
  setPreviewLoading(outputPreviewLink, false);
  setPhotoPrintLink("", false);

  appendEvent("Staff panel reset.");
}

async function submitGeneration() {
  if (loading) {
    return;
  }

  if (currentMethod === "scanner") {
    setStatus("Scanner auto mode");
    controlHint.textContent = "Scanner mode is automatic. Drop files in scanner_inputs/ and watch Live Events.";
    appendEvent("Scanner mode is automatic. Drop files in scanner_inputs/.", true);
    return;
  }

  const visitorName = visitorNameInput.value.trim() || "Guest";
  const visitorNotes = visitorNotesInput.value.trim();

  if (currentMethod === "upload") {
    const selectedFile = drawingFileInput.files[0];
    if (!selectedFile) {
      setStatus("Select drawing file");
      controlHint.textContent = "Please choose an image file first, then click Generate Artwork.";
      drawingFileInput.focus();
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
    let selectedMode = getGenerationModeValue();
    const aiArtVentureEnabled = isAiArtVentureEnabledFromToggle() && isAiArtVentureMode(selectedMode);
    let selectedStyle = getStyleValueForMode(selectedMode);
    let aiFinalChoice = null;
    if (aiArtVentureEnabled) {
      selectedMode = GENERATION_MODE_IDS.AI_ART_VENTURE;
      aiFinalChoice = resolveAiArtVentureGenerationChoice();
      selectedStyle = String(aiFinalChoice.backendStyleId || selectedStyle || "pixar_3d");
      aiArtVentureUiState.lastGeneratedStyleName = String(aiFinalChoice.finalStyleName || "-");
      aiArtVentureUiState.lastGeneratedThemeName = String(aiFinalChoice.finalThemeName || "-");
      aiArtVentureUiState.lastGeneratedPrompt = String(aiFinalChoice.finalPrompt || "-");
      aiArtVentureUiState.lastGeneratedBackendStyleId = selectedStyle;
      applyAiArtVentureUiStateToControls();
    }
    formData.append("visitorName", visitorName);
    formData.append("generationMode", selectedMode);
    formData.append("styleId", selectedStyle);
    formData.append("mode", aiArtVentureEnabled ? "ai-art-venture" : "normal");
    formData.append("aiArtVentureEnabled", String(aiArtVentureEnabled));
    if (aiArtVentureEnabled && aiFinalChoice) {
      formData.append("randomStyleEnabled", String(aiArtVentureUiState.randomStyleEnabled));
      formData.append("randomThemeEnabled", String(aiArtVentureUiState.randomThemeEnabled));
      formData.append("selectedStyleId", String(aiArtVentureUiState.selectedStyleId || ""));
      formData.append("selectedThemeId", String(aiArtVentureUiState.selectedThemeId || ""));
      formData.append("customTheme", String(aiArtVentureUiState.customTheme || ""));
      formData.append("finalStyleId", String(aiFinalChoice.finalStyleId || ""));
      formData.append("finalStyleName", String(aiFinalChoice.finalStyleName || ""));
      formData.append("finalThemeId", String(aiFinalChoice.finalThemeId || ""));
      formData.append("finalThemeName", String(aiFinalChoice.finalThemeName || ""));
    }

    let endpoint = "/generate";
    if (currentMethod === "upload") {
      formData.append("file", drawingFileInput.files[0]);
    } else {
      endpoint = "/capture";
    }

    if (aiArtVentureEnabled && aiFinalChoice) {
      appendEvent(
        `Submitting AI Art Venture style=${aiFinalChoice.finalStyleName} theme=${aiFinalChoice.finalThemeName} for ${visitorName}.`
      );
    }
    appendEvent(`Submitting ${selectedMode} / ${selectedStyle} for ${visitorName}.`);

    const response = await fetch(endpoint, {
      method: "POST",
      body: formData
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Generation failed.");
    }

    if (payload.status === "queued" && payload.job) {
      const queuedMode = String(payload.job.generationMode || selectedMode);
      const queuedStyle = String(payload.job.styleId || selectedStyle);
      currentJobId = payload.job.jobId || currentJobId;
      startJobStatusPolling();
      void fetchCurrentJobStatus({ silent: true });
      setStatus("Queued");
      jobIdText.textContent = payload.job.jobId || "pending";
      visitorText.textContent = payload.job.visitorName || visitorName;
      presetText.textContent = "-";
      promptModeText.textContent = "-";
      finalDurationText.textContent = "-";
      if (generationModeSelect) {
        const modeValues = Array.from(generationModeSelect.options).map((option) => option.value);
        if (modeValues.includes(queuedMode)) {
          generationModeSelect.value = queuedMode;
          applyGenerationModeUiState(queuedStyle);
        }
      }
      setPreviewLoading(outputPreviewLink, false);
      applyQueueStatus(payload, { silent: true });
      appendEvent(`Queued job ${payload.job.jobId} (${queuedMode} / ${queuedStyle}).`);
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
  if (AUTO_RATING_ONLY) {
    appendEvent("Manual rating is disabled. Ratings are automatic.");
    return;
  }

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
    ratingStatus.textContent = "Auto rating not available yet.";
  }

  renderGalleryControlList();
}

function setGalleryControlButtonsDisabled(buttons, disabled) {
  buttons.forEach((button) => {
    button.disabled = disabled;
  });
}

function setGalleryControlHeaderButtonsDisabled(disabled) {
  [refreshGalleryControlBtn, clearGalleryControlBtn].forEach((button) => {
    if (button) {
      button.disabled = disabled;
    }
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

  setGalleryControlHeaderButtonsDisabled(true);
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
    setGalleryControlHeaderButtonsDisabled(false);
  }
}

async function clearAllGalleryPhotos() {
  if (!clearGalleryControlBtn) {
    return;
  }

  const itemCount = Array.isArray(galleryControlItems) ? galleryControlItems.length : 0;
  const confirmText =
    itemCount > 0
      ? `Clear ${itemCount} gallery photo(s)? This permanently deletes gallery images.`
      : "Clear all gallery photos? This permanently deletes gallery images.";

  if (!window.confirm(confirmText)) {
    return;
  }

  setGalleryControlHeaderButtonsDisabled(true);
  try {
    const response = await fetch("/gallery/clear", { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to clear gallery photos.");
    }

    const deletedJobIds = Array.isArray(data.deletedJobIds) ? data.deletedJobIds : [];
    if (deletedJobIds.length > 0) {
      deletedJobIds.forEach((jobId) => {
        removeGalleryControlItem(String(jobId || ""));
      });
    } else {
      galleryControlItems = [];
      renderGalleryControlList();
    }

    const deletedCount = Number(data.deletedCount || deletedJobIds.length || 0);
    appendEvent(`Cleared ${deletedCount} gallery photo(s).`);
    await loadGalleryControlItems({ silent: true });
  } catch (error) {
    appendEvent(error.message || "Failed to clear gallery photos.", true);
  } finally {
    setGalleryControlHeaderButtonsDisabled(false);
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

  socket.onopen = () => {
    appendEvent("Live updates connected.");
    fetchQueueStatus({ silent: true });
    void fetchGenerationBackendStatus({ silent: true });
    if (currentJobId) {
      startJobStatusPolling();
      void fetchCurrentJobStatus({ silent: true });
    }
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
        stopJobStatusPolling();
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
          startJobStatusPolling();
          setStatus("Processing");
          jobIdText.textContent = startedJob.jobId || "-";
          visitorText.textContent = startedJob.visitorName || visitorText.textContent;
          startElapsedTimer(startedJob.startedAt || null);
        }
        appendEvent(`Job started: ${startedJob.jobId}.`);
      } else if (payload.type === "job_failed" && payload.job) {
        const failedJob = payload.job;
        if (currentJobId && failedJob.jobId === currentJobId) {
          stopJobStatusPolling();
          setStatus("Error");
          stopElapsedTimer();
          setPreviewLoading(outputPreviewLink, false);
        }
        appendEvent(`Job failed: ${failedJob.jobId} (${failedJob.error || "Unknown error"})`, true);
      } else if (payload.type === "job_cancelled" && payload.job) {
        const cancelledJob = payload.job;
        if (currentJobId && cancelledJob.jobId === currentJobId) {
          stopJobStatusPolling();
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

if (clearGalleryControlBtn) {
  clearGalleryControlBtn.addEventListener("click", () => {
    clearAllGalleryPhotos();
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

if (generationModeSelect) {
  generationModeSelect.addEventListener("change", () => {
    const selectedMode = String(generationModeSelect.value || "");
    if (isAiArtVentureMode(selectedMode)) {
      aiArtVentureUiState.enabled = true;
    } else {
      aiArtVentureUiState.enabled = false;
      lastNonAiGenerationMode = selectedMode || lastNonAiGenerationMode;
    }
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
    applyGenerationModeUiState();
  });
}

if (styleIdSelect) {
  styleIdSelect.addEventListener("change", () => {
    renderModePresetInfo();
  });
}

if (aiArtVentureEnabledToggle) {
  aiArtVentureEnabledToggle.addEventListener("change", () => {
    aiArtVentureUiState.enabled = Boolean(aiArtVentureEnabledToggle.checked);
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
    applyGenerationModeUiState();
    setLoading(loading);
  });
}

if (randomStyleEnabledToggle) {
  randomStyleEnabledToggle.addEventListener("change", () => {
    aiArtVentureUiState.randomStyleEnabled = Boolean(randomStyleEnabledToggle.checked);
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
    renderModePresetInfo();
  });
}

if (randomThemeEnabledToggle) {
  randomThemeEnabledToggle.addEventListener("change", () => {
    aiArtVentureUiState.randomThemeEnabled = Boolean(randomThemeEnabledToggle.checked);
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
  });
}

if (aiArtVentureStyleSelect) {
  aiArtVentureStyleSelect.addEventListener("change", () => {
    aiArtVentureUiState.selectedStyleId = String(aiArtVentureStyleSelect.value || aiArtVentureUiState.selectedStyleId);
    normalizeAiArtVentureUiState();
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
    renderModePresetInfo();
  });
}

if (aiArtVentureThemeSelect) {
  aiArtVentureThemeSelect.addEventListener("change", () => {
    aiArtVentureUiState.selectedThemeId = String(aiArtVentureThemeSelect.value || aiArtVentureUiState.selectedThemeId);
    normalizeAiArtVentureUiState();
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
  });
}

if (aiArtVentureCustomTheme) {
  aiArtVentureCustomTheme.addEventListener("input", () => {
    aiArtVentureUiState.customTheme = String(aiArtVentureCustomTheme.value || "");
    normalizeAiArtVentureUiState();
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
  });
}

if (resetCustomThemeBtn) {
  resetCustomThemeBtn.addEventListener("click", () => {
    aiArtVentureUiState.customTheme = "";
    saveAiArtVentureUiStateToLocalStorage();
    applyAiArtVentureUiStateToControls();
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
applyAutoRatingOnlyUi();
renderAutoReview(null);
setPreview(inputPreviewLink, inputPreviewImage, null);
setPreview(outputPreviewLink, outputPreviewImage, null);
wirePreviewLinkSafety(inputPreviewLink);
wirePreviewLinkSafety(outputPreviewLink);
setGenerationBackendStatusDisplay(null);
setWebcamPermissionState("unknown", "Camera permission: not requested.");
initializeAiArtVenturePanel();
loadGenerationModeSettings().then(() => {
  applyGenerationModeUiState();
  setLoading(loading);
});

fetchGenerationEstimate().then((estimate) => {
  applyEstimate(estimate);
  appendEvent(`Loaded estimate from ${estimate.sampleCount} completed job(s).`);
});

loadGalleryControlItems({ silent: true });
fetchQueueStatus({ silent: true });
void fetchGenerationBackendStatus({ silent: true });
startBackendStatusPolling();
connectWebSocket();
