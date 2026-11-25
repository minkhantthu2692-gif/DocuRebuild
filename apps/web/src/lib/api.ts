import type {
  AiConnectionCreate,
  AiConnectionDetail,
  AiConnectionPatch,
  AiConnectionTestRequest,
  AiConnectionTestResponse,
  AiConnectionsResponse,
  AiEquationRequest,
  AiEquationResponse,
  AiKey,
  AiKeyCreate,
  AiKeyPatch,
  AiManualModelCreate,
  AiModel,
  AiModelFavoriteInput,
  AiOverview,
  AiPreferences,
  AiPreferencesPatch,
  AiProvidersResponse,
  AiRegionProposalsRequest,
  AiRegionProposalsResponse,
  AiRouteTask,
  AiRouteUpdate,
  AiRoutesResponse,
  AiSuggestionBulkInput,
  AiSuggestionBulkResponse,
  AiSuggestionCreate,
  AiSuggestionDecisionInput,
  AiSuggestionDecisionResponse,
  AiSuggestionsResponse,
  AiTableRequest,
  AiTableResponse,
  AiTasksResponse,
  AiUsageHistoryResponse,
  AiUsageOutcome,
  AiUsageResponse,
  AiUsageTask,
  AppCapabilities,
  AppMeta,
  AppSettings,
  AppearanceSettings,
  BackupSelection,
  BackupSettings,
  DocumentLayout,
  DocumentLayoutInput,
  DocumentRecord,
  DocumentRestoreResult,
  DocumentRevision,
  DocumentRevisionSummary,
  EditorSettings,
  ElementAssetRepairResult,
  ElementSummary,
  ElementTableRequest,
  ElementTableResponse,
  ExportSettings,
  FactoryResetResult,
  FontFaceSummary,
  FontsResponse,
  HealthStatus,
  HistoryEvent,
  ImportJob,
  JSONContent,
  LanguageCode,
  OcrCapabilities,
  PageAssetRepairResult,
  PageEdits,
  OcrRun,
  PageRestoreResult,
  PageSummary,
  PageTableProposals,
  ProjectBackupSummary,
  ProjectBulkDeleteResult,
  ProjectDetail,
  ProjectSummary,
  RegionProposals,
  TableProposal,
} from "@docurebuild/shared-types";

import { filenameFromDisposition } from "@/lib/download";

const API_BASE = "/api";

/**
 * The desktop shell opens the client from the local API origin and injects a
 * per-launch token through its preload bridge. In browser development mode the
 * bridge is absent and the request stays a same-origin call with no token.
 */
function desktopAuthHeaders(): Record<string, string> {
  const token = window.docurebuild?.apiToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let code = "request_failed";
  let message = `Request failed with status ${response.status}.`;
  try {
    const body = await response.json();
    if (body?.detail?.code) {
      code = body.detail.code;
      message = body.detail.message ?? message;
    }
  } catch {
    /* Non-JSON error response. */
  }
  return new ApiError(code, message, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...desktopAuthHeaders(),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("network_unreachable", "The local backend is not reachable.", 0);
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function download(
  path: string,
  init?: RequestInit,
  fallbackName = "project-backup.zip",
): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(typeof init?.body === "string" ? { "Content-Type": "application/json" } : {}),
        ...desktopAuthHeaders(),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("network_unreachable", "The local backend is not reachable.", 0);
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")) ?? fallbackName,
  };
}

export interface SettingsPatch {
  language?: LanguageCode;
  appearance?: Partial<AppearanceSettings>;
  editor?: Partial<EditorSettings>;
  export?: Partial<ExportSettings>;
  backups?: Partial<BackupSettings>;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string;
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  meta: () => request<AppMeta>("/meta"),

  getSettings: () => request<AppSettings>("/settings"),
  updateSettings: (patch: SettingsPatch) =>
    request<AppSettings>("/settings", { method: "PATCH", body: JSON.stringify(patch) }),

  listFonts: (refresh = false) =>
    request<FontsResponse>(`/fonts${refresh ? "?refresh=true" : ""}`),
  importFont: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<FontFaceSummary>("/fonts/import", { method: "POST", body: form });
  },
  deleteFont: (fontId: string) =>
    request<void>(`/fonts/${encodeURIComponent(fontId)}`, { method: "DELETE" }),
  // Font files are fetched with the desktop bearer token and registered through
  // the FontFace API. A plain CSS URL would not be authenticated.
  getFontFile: async (fontId: string): Promise<ArrayBuffer> => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/fonts/${encodeURIComponent(fontId)}/file`, {
        headers: desktopAuthHeaders(),
      });
    } catch {
      throw new ApiError("network_unreachable", "The local backend is not reachable.", 0);
    }
    if (!response.ok) {
      throw await errorFromResponse(response);
    }
    return response.arrayBuffer();
  },

  listProjects: () => request<ProjectSummary[]>("/projects"),
  getProject: (projectId: string) => request<ProjectDetail>(`/projects/${projectId}`),
  createProject: (payload: ProjectCreatePayload) =>
    request<ProjectDetail>("/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (projectId: string, payload: { name?: string; description?: string }) =>
    request<ProjectDetail>(`/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  openProject: (projectId: string) =>
    request<ProjectDetail>(`/projects/${projectId}/open`, { method: "POST" }),
  deleteProject: (projectId: string) =>
    request<{ ok: boolean; trash_path: string }>(`/projects/${projectId}`, { method: "DELETE" }),
  bulkDeleteProjects: (projectIds: string[]) =>
    request<ProjectBulkDeleteResult>("/projects/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ project_ids: projectIds }),
    }),
  resetAllData: (confirmation: string) =>
    request<FactoryResetResult>("/system/reset", {
      method: "POST",
      body: JSON.stringify({ confirm: confirmation }),
    }),
  // A password is sent in the request body, never in the URL, and is used only
  // for this download. Without one the archive stays a plain .zip.
  downloadProjectBackup: (projectId: string, password?: string) =>
    password
      ? download(
          `/projects/${projectId}/backup`,
          { method: "POST", body: JSON.stringify({ password }) },
          "project-backup.drbz",
        )
      : download(`/projects/${projectId}/backup`),
  listProjectBackups: (projectId: string) =>
    request<ProjectBackupSummary[]>(`/projects/${projectId}/backups`),
  createProjectBackupCopy: (projectId: string) =>
    request<ProjectBackupSummary>(`/projects/${projectId}/backups`, { method: "POST" }),
  downloadProjectBackupCopy: (projectId: string, filename: string) =>
    download(`/projects/${projectId}/backups/${encodeURIComponent(filename)}`),
  deleteProjectBackupCopy: (projectId: string, filename: string) =>
    request<{ ok: boolean; filename: string }>(
      `/projects/${projectId}/backups/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),
  restoreProjectBackupCopy: (projectId: string, filename: string) =>
    request<ProjectDetail>(
      `/projects/${projectId}/backups/${encodeURIComponent(filename)}/restore`,
      { method: "POST" },
    ),
  restoreProjectBackup: (file: File, password?: string) => {
    const form = new FormData();
    form.append("file", file);
    // Only sent when the user typed one; the backend ignores it for a plain zip.
    if (password) form.append("password", password);
    return request<ProjectDetail>("/projects/restore", { method: "POST", body: form });
  },
  inspectUploadedBackup: (projectId: string, file: File, password?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (password) form.append("password", password);
    return request<BackupSelection>(`/projects/${projectId}/backup/selection`, {
      method: "POST",
      body: form,
    });
  },
  inspectStoredBackup: (projectId: string, filename: string) =>
    request<BackupSelection>(
      `/projects/${projectId}/backups/${encodeURIComponent(filename)}/selection`,
      { method: "POST" },
    ),
  restoreSelectedPages: (projectId: string, token: string, pageIds: string[]) =>
    request<PageRestoreResult>(
      `/projects/${projectId}/backup/selection/${encodeURIComponent(token)}/pages`,
      { method: "POST", body: JSON.stringify({ page_ids: pageIds }) },
    ),
  restoreBackupDocument: (
    projectId: string,
    token: string,
    revisionId: string | null,
  ) =>
    request<DocumentRestoreResult>(
      `/projects/${projectId}/backup/selection/${encodeURIComponent(token)}/document`,
      { method: "POST", body: JSON.stringify({ revision_id: revisionId }) },
    ),
  repairBackupPageAssets: (projectId: string, token: string, pageId: string) =>
    request<PageAssetRepairResult>(
      `/projects/${projectId}/backup/selection/${encodeURIComponent(token)}/page-assets`,
      { method: "POST", body: JSON.stringify({ page_id: pageId }) },
    ),
  repairBackupElementAsset: (
    projectId: string,
    token: string,
    elementId: string,
  ) =>
    request<ElementAssetRepairResult>(
      `/projects/${projectId}/backup/selection/${encodeURIComponent(token)}/element-assets`,
      { method: "POST", body: JSON.stringify({ element_id: elementId }) },
    ),
  listProjectHistory: (projectId: string, limit = 100) =>
    request<HistoryEvent[]>(`/projects/${projectId}/history?limit=${limit}`),

  getDocument: (projectId: string) =>
    request<DocumentRecord>(`/projects/${projectId}/document`),
  getDocumentLayout: (projectId: string) =>
    request<DocumentLayout>(`/projects/${projectId}/document/layout`),
  saveDocumentLayout: (projectId: string, layout: DocumentLayoutInput) =>
    request<DocumentLayout>(`/projects/${projectId}/document/layout`, {
      method: "PUT",
      body: JSON.stringify(layout),
    }),
  downloadDocument: (
    projectId: string,
    format: "markdown" | "txt" | "docx" | "pdf",
  ) =>
    download(
      `/projects/${projectId}/document/export?format=${format}`,
      undefined,
      `document.${format}`,
    ),
  saveDocument: (projectId: string, content: JSONContent, plainText: string) =>
    request<DocumentRecord>(`/projects/${projectId}/document`, {
      method: "PUT",
      body: JSON.stringify({ content, plain_text: plainText }),
    }),

  listDocumentRevisions: (projectId: string, limit = 200) =>
    request<DocumentRevisionSummary[]>(
      `/projects/${projectId}/document/revisions?limit=${limit}`,
    ),
  createDocumentRevision: (projectId: string) =>
    request<DocumentRevisionSummary>(`/projects/${projectId}/document/revisions`, {
      method: "POST",
    }),
  getDocumentRevision: (projectId: string, revisionId: string) =>
    request<DocumentRevision>(
      `/projects/${projectId}/document/revisions/${revisionId}`,
    ),
  restoreDocumentRevision: (projectId: string, revisionId: string) =>
    request<DocumentRecord>(
      `/projects/${projectId}/document/revisions/${revisionId}/restore`,
      { method: "POST" },
    ),

  listPages: (projectId: string) => request<PageSummary[]>(`/projects/${projectId}/pages`),
  startImport: (projectId: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return request<ImportJob>(`/projects/${projectId}/imports`, {
      method: "POST",
      body: form,
    });
  },
  getImportJob: (projectId: string, jobId: string) =>
    request<ImportJob>(`/projects/${projectId}/imports/${jobId}`),
  listImportJobs: (projectId: string, limit = 10) =>
    request<ImportJob[]>(`/projects/${projectId}/imports?limit=${limit}`),
  cancelImportJob: (projectId: string, jobId: string) =>
    request<ImportJob>(`/projects/${projectId}/imports/${jobId}/cancel`, {
      method: "POST",
    }),
  rotatePage: (projectId: string, pageId: string, degrees: number) =>
    request<PageSummary>(`/projects/${projectId}/pages/${pageId}/rotate`, {
      method: "POST",
      body: JSON.stringify({ degrees }),
    }),
  deletePage: (projectId: string, pageId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/pages/${pageId}`, { method: "DELETE" }),
  reorderPages: (projectId: string, pageIds: string[]) =>
    request<PageSummary[]>(`/projects/${projectId}/pages/order`, {
      method: "PUT",
      body: JSON.stringify({ page_ids: pageIds }),
    }),

  updatePageEdits: (projectId: string, pageId: string, edits: PageEdits) =>
    request<PageSummary>(`/projects/${projectId}/pages/${pageId}/edits`, {
      method: "PATCH",
      body: JSON.stringify({ edits }),
    }),
  resetPageEdits: (projectId: string, pageId: string) =>
    request<PageSummary>(`/projects/${projectId}/pages/${pageId}/edits/reset`, {
      method: "POST",
    }),
  pageBasePreview: (projectId: string, pageId: string) =>
    `${API_BASE}/projects/${projectId}/pages/${pageId}/edits/base`,
  estimatePageSkew: (projectId: string, pageId: string) =>
    request<{ angle: number }>(`/projects/${projectId}/pages/${pageId}/deskew-estimate`),

  getOcrCapabilities: (refresh = false) =>
    request<OcrCapabilities>(`/ocr/capabilities${refresh ? "?refresh=true" : ""}`),
  getLatestOcr: (projectId: string, pageId: string) =>
    request<OcrRun | null>(`/projects/${projectId}/pages/${pageId}/ocr`),
  startOcr: (
    projectId: string,
    pageId: string,
    languages: string[],
    pageSegmentationMode?: number,
  ) =>
    request<OcrRun>(`/projects/${projectId}/pages/${pageId}/ocr`, {
      method: "POST",
      body: JSON.stringify({
        languages,
        page_segmentation_mode: pageSegmentationMode ?? null,
      }),
    }),
  getOcrRun: (projectId: string, runId: string) =>
    request<OcrRun>(`/projects/${projectId}/ocr/runs/${runId}`),
  updateOcrBlock: (
    projectId: string,
    pageId: string,
    blockId: string,
    patch: { text?: string; verified?: boolean },
  ) =>
    request<OcrRun>(
      `/projects/${projectId}/pages/${pageId}/ocr/blocks/${blockId}`,
      {
        method: "PATCH",
        body: JSON.stringify(patch),
      },
    ),

  listElements: (projectId: string, pageId: string) =>
    request<ElementSummary[]>(`/projects/${projectId}/pages/${pageId}/elements`),
  createElement: (
    projectId: string,
    pageId: string,
    payload: {
      kind: ElementSummary["kind"];
      x: number;
      y: number;
      width: number;
      height: number;
      caption: string;
    },
  ) =>
    request<ElementSummary>(`/projects/${projectId}/pages/${pageId}/elements`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateElement: (
    projectId: string,
    elementId: string,
    patch: { caption?: string; verified?: boolean },
  ) =>
    request<ElementSummary>(`/projects/${projectId}/elements/${elementId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  extractElementText: (projectId: string, elementId: string, languages: string[]) =>
    request<ElementSummary>(`/projects/${projectId}/elements/${elementId}/text`, {
      method: "POST",
      body: JSON.stringify({ languages }),
    }),
  updateElementText: (projectId: string, elementId: string, text: string) =>
    request<ElementSummary>(`/projects/${projectId}/elements/${elementId}/text`, {
      method: "PATCH",
      body: JSON.stringify({ text }),
    }),
  deleteElement: (projectId: string, elementId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/elements/${elementId}`, {
      method: "DELETE",
    }),
  getRegionProposals: (projectId: string, pageId: string) =>
    request<RegionProposals>(`/projects/${projectId}/pages/${pageId}/region-proposals`),
  getTableProposal: (projectId: string, pageId: string, blockId: string) =>
    request<TableProposal>(
      `/projects/${projectId}/pages/${pageId}/ocr/blocks/${blockId}/table-proposal`,
    ),
  getPageTableProposals: (projectId: string, pageId: string) =>
    request<PageTableProposals>(`/projects/${projectId}/pages/${pageId}/table-proposals`),
  createAiRegionProposals: (
    projectId: string,
    pageId: string,
    payload: AiRegionProposalsRequest = {},
  ) =>
    request<AiRegionProposalsResponse>(
      `/projects/${projectId}/pages/${pageId}/ai-region-proposals`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  createAiEquationProposal: (
    projectId: string,
    elementId: string,
    payload: AiEquationRequest = {},
  ) =>
    request<AiEquationResponse>(
      `/projects/${projectId}/elements/${elementId}/ai-equation`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  createAiTableProposal: (
    projectId: string,
    elementId: string,
    payload: AiTableRequest = {},
  ) =>
    request<AiTableResponse>(
      `/projects/${projectId}/elements/${elementId}/ai-table`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  createElementTableProposal: (
    projectId: string,
    elementId: string,
    payload: ElementTableRequest = {},
  ) =>
    request<ElementTableResponse>(
      `/projects/${projectId}/elements/${elementId}/table-proposal`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listAiProviders: () => request<AiProvidersResponse>("/ai/providers"),
  listAiConnections: () => request<AiConnectionsResponse>("/ai/connections"),
  getAiConnection: (connectionId: string) =>
    request<AiConnectionDetail>(`/ai/connections/${connectionId}`),
  createAiConnection: (payload: AiConnectionCreate) =>
    request<AiConnectionDetail>("/ai/connections", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAiConnection: (connectionId: string, payload: AiConnectionPatch) =>
    request<AiConnectionDetail>(`/ai/connections/${connectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteAiConnection: (connectionId: string) =>
    request<void>(`/ai/connections/${connectionId}`, { method: "DELETE" }),
  testAiConnection: (
    connectionId: string,
    payload: AiConnectionTestRequest = {},
  ) =>
    request<AiConnectionTestResponse>(`/ai/connections/${connectionId}/test`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  addAiKey: (connectionId: string, payload: AiKeyCreate) =>
    request<AiKey>(`/ai/connections/${connectionId}/keys`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAiKey: (connectionId: string, keyId: string, payload: AiKeyPatch) =>
    request<AiKey>(`/ai/connections/${connectionId}/keys/${keyId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteAiKey: (connectionId: string, keyId: string) =>
    request<void>(`/ai/connections/${connectionId}/keys/${keyId}`, {
      method: "DELETE",
    }),
  listAiModels: (
    connectionId: string | null,
    params: {
      query?: string;
      capability?: "text" | "vision";
      favoritesOnly?: boolean;
      availableOnly?: boolean;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (params.query) query.set("query", params.query);
    if (params.capability) query.set("capability", params.capability);
    if (params.favoritesOnly) query.set("favorites_only", "true");
    if (params.availableOnly) query.set("available_only", "true");
    const suffix = query.size > 0 ? `?${query.toString()}` : "";
    return request<AiModel[]>(
      connectionId
        ? `/ai/connections/${connectionId}/models${suffix}`
        : `/ai/models${suffix}`,
    );
  },
  addAiModel: (connectionId: string, payload: AiManualModelCreate) =>
    request<AiModel>(`/ai/connections/${connectionId}/models`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  favoriteAiModel: (connectionId: string, payload: AiModelFavoriteInput) =>
    request<AiModel>(`/ai/connections/${connectionId}/models/favorite`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  clearRecentAiModels: () =>
    request<void>("/ai/models/clear-recent", { method: "POST" }),
  listAiRoutes: () => request<AiRoutesResponse>("/ai/routes"),
  updateAiRoute: (task: AiRouteTask, payload: AiRouteUpdate) =>
    request<unknown>(`/ai/routes/${task}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getAiTasks: () => request<AiTasksResponse>("/ai/tasks"),
  getAiPreferences: () => request<AiPreferences>("/ai/preferences"),
  updateAiPreferences: (payload: AiPreferencesPatch) =>
    request<AiPreferences>("/ai/preferences", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  getAiOverview: () => request<AiOverview>("/ai/overview"),
  getAiMigration: () =>
    request<{ needed: boolean; migrated: boolean; completed_at: string | null; detail: string | null }>(
      "/ai/migration",
    ),
  getAiUsage: () => request<AiUsageResponse>("/ai/usage"),
  getAiUsageHistory: (
    params: {
      limit?: number;
      offset?: number;
      outcome?: AiUsageOutcome;
      task?: AiUsageTask;
      connectionId?: string;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    if (params.outcome) query.set("outcome", params.outcome);
    if (params.task) query.set("task", params.task);
    if (params.connectionId) query.set("connection_id", params.connectionId);
    const suffix = query.size > 0 ? `?${query.toString()}` : "";
    return request<AiUsageHistoryResponse>(`/ai/usage/history${suffix}`);
  },
  clearAiUsage: () => request<void>("/ai/usage", { method: "DELETE" }),
  createAiCleanupSuggestion: (
    projectId: string,
    pageId: string,
    blockId: string,
    payload: AiSuggestionCreate,
  ) =>
    request<AiSuggestionDecisionResponse>(
      `/projects/${projectId}/pages/${pageId}/ocr/blocks/${blockId}/ai-suggestions`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  listAiSuggestions: (
    projectId: string,
    pageId: string,
    status?: "pending" | "accepted" | "rejected",
  ) =>
    request<AiSuggestionsResponse>(
      `/projects/${projectId}/pages/${pageId}/ai-suggestions${
        status ? `?status=${encodeURIComponent(status)}` : ""
      }`,
    ),
  listProjectAiSuggestions: (
    projectId: string,
    status?: "pending" | "accepted" | "rejected",
    limit = 200,
  ) =>
    request<AiSuggestionsResponse>(
      `/projects/${projectId}/ai-suggestions?limit=${limit}${
        status ? `&status=${encodeURIComponent(status)}` : ""
      }`,
    ),
  decideAiSuggestion: (
    projectId: string,
    suggestionId: string,
    payload: AiSuggestionDecisionInput,
  ) =>
    request<AiSuggestionDecisionResponse>(
      `/projects/${projectId}/ai-suggestions/${suggestionId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  decideAiSuggestionsBulk: (projectId: string, payload: AiSuggestionBulkInput) =>
    request<AiSuggestionBulkResponse>(
      `/projects/${projectId}/ai-suggestions/bulk`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  assetUrl: (projectId: string, assetId: string | null, version?: string) => {
    if (!assetId) return null;
    const suffix = version ? `?v=${encodeURIComponent(version)}` : "";
    return `${API_BASE}/projects/${projectId}/assets/${assetId}/file${suffix}`;
  },
};

export const DEFAULT_CAPABILITIES: AppCapabilities = {
  import_images: false,
  import_pdf: false,
  image_transform: false,
  element_extraction: false,
  region_proposals: false,
  ocr: false,
  ai: true,
  export: false,
  backup: false,
};
