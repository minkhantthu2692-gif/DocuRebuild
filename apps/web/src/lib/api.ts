import type {
  AiProbeRequest,
  AiProbeResponse,
  AiProvidersResponse,
  AiRegionProposalsRequest,
  AiRegionProposalsResponse,
  AiSettings,
  AiSuggestionCreate,
  AiSuggestionDecisionInput,
  AiSuggestionDecisionResponse,
  AiSuggestionsResponse,
  AiUsageResponse,
  AppCapabilities,
  AppMeta,
  AppSettings,
  AppearanceSettings,
  BackupSelection,
  BackupSettings,
  DocumentRecord,
  DocumentRevision,
  DocumentRevisionSummary,
  EditorSettings,
  ElementSummary,
  ExportSettings,
  HealthStatus,
  HistoryEvent,
  ImportJob,
  JSONContent,
  LanguageCode,
  OcrCapabilities,
  PageEdits,
  OcrRun,
  PageRestoreResult,
  PageSummary,
  ProjectBackupSummary,
  ProjectDetail,
  ProjectSummary,
  RegionProposals,
} from "@docurebuild/shared-types";

import { filenameFromDisposition } from "@/lib/download";

const API_BASE = "/api";

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
  ai?: Partial<AiSettings>;
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
  listProjectHistory: (projectId: string, limit = 100) =>
    request<HistoryEvent[]>(`/projects/${projectId}/history?limit=${limit}`),

  getDocument: (projectId: string) =>
    request<DocumentRecord>(`/projects/${projectId}/document`),
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
  startOcr: (projectId: string, pageId: string, languages: string[]) =>
    request<OcrRun>(`/projects/${projectId}/pages/${pageId}/ocr`, {
      method: "POST",
      body: JSON.stringify({ languages }),
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
  createAiRegionProposals: (
    projectId: string,
    pageId: string,
    payload: AiRegionProposalsRequest = {},
  ) =>
    request<AiRegionProposalsResponse>(
      `/projects/${projectId}/pages/${pageId}/ai-region-proposals`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listAiProviders: () => request<AiProvidersResponse>("/ai/providers"),
  getAiUsage: () => request<AiUsageResponse>("/ai/usage"),
  probeAiProvider: (payload: AiProbeRequest) =>
    request<AiProbeResponse>("/ai/probe", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
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
