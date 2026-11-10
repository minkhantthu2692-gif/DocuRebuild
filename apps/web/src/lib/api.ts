import type {
  AppCapabilities,
  AppMeta,
  AppSettings,
  AppearanceSettings,
  DocumentRecord,
  EditorSettings,
  ElementSummary,
  HealthStatus,
  ImportJob,
  JSONContent,
  LanguageCode,
  OcrCapabilities,
  PageEdits,
  OcrRun,
  PageSummary,
  ProjectDetail,
  ProjectSummary,
} from "@docurebuild/shared-types";

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
    throw new ApiError(code, message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface SettingsPatch {
  language?: LanguageCode;
  appearance?: Partial<AppearanceSettings>;
  editor?: Partial<EditorSettings>;
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

  getDocument: (projectId: string) =>
    request<DocumentRecord>(`/projects/${projectId}/document`),
  saveDocument: (projectId: string, content: JSONContent, plainText: string) =>
    request<DocumentRecord>(`/projects/${projectId}/document`, {
      method: "PUT",
      body: JSON.stringify({ content, plain_text: plainText }),
    }),

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
  deleteElement: (projectId: string, elementId: string) =>
    request<{ ok: boolean }>(`/projects/${projectId}/elements/${elementId}`, {
      method: "DELETE",
    }),

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
  ocr: false,
  ai: false,
  export: false,
};
