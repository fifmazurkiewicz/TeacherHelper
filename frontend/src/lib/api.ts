const TOKEN_KEY = "th_access_token";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, "") ?? "/th-api";

function buildUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token == null || token === "") localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

export function getAdminKeyHeaders(): Record<string, string> {
  const k = (import.meta.env.VITE_ADMIN_API_KEY as string | undefined)?.trim();
  if (!k) return {};
  return { "X-Admin-Key": k };
}

type ApiInit = {
  method?: string;
  headers?: Record<string, string>;
  json?: unknown;
  signal?: AbortSignal;
};

async function errorText(res: Response): Promise<string> {
  const t = await res.text();
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && d !== null) {
      const o = d as { message?: unknown; code?: string };
      if (typeof o.message === "string") return o.message;
    }
  } catch {
    /* ignore */
  }
  return t || res.statusText || `HTTP ${res.status}`;
}

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  return fetch(buildUrl(path), { ...init, headers });
}

export async function api<T>(path: string, init?: ApiInit): Promise<T> {
  const headers: Record<string, string> = { ...init?.headers };
  let body: BodyInit | undefined;
  if (init?.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const res = await authFetch(path, {
    method: init?.method ?? "GET",
    headers,
    body,
    signal: init?.signal,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw new Error(await errorText(res));
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// --- typy odpowiedzi (zgodne z backendem) ---

export type AdminStats = {
  users: number;
  files: number;
  ai_read_audits: number;
};

export async function adminStats(): Promise<AdminStats> {
  return api<AdminStats>("/v1/admin/stats", { headers: getAdminKeyHeaders() });
}

export type PendingProjectAction = {
  confirmation_token: string;
  expires_in_seconds: number;
  summary: string;
  name: string | null;
  description: string | null;
  project_id: string | null;
  project_name: string | null;
};

export type ApiConversation = {
  id: string;
  title: string;
  project_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiChatMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
  extra: Record<string, unknown> | null;
};

export type ProjectResponse = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
};

export type ApiFile = {
  id: string;
  name: string;
  category: string;
  mime_type: string;
  version: number;
  size_bytes: number;
  project_id: string | null;
  topic_id: string | null;
  created_at: string;
};

export type ProjectDeleteImpact = {
  resource: string;
  project_id: string;
  name: string;
  files_attached_count: number;
  message: string;
};

export type FileDeleteImpact = {
  resource: string;
  file_id: string;
  name: string;
  size_bytes: number;
  indexed_chunks: number;
  message: string;
};

type PrepareResult = {
  confirmation_token: string;
  expires_in_seconds: number;
  header_name: string;
  summary: string;
};

function parseContentDispositionFilename(cd: string | null): string | null {
  if (!cd) return null;
  const mStar = /filename\*\s*=\s*[^']*''([^;]+)/i.exec(cd);
  if (mStar) {
    try {
      return decodeURIComponent(mStar[1].trim().replace(/^"|"$/g, ""));
    } catch {
      return mStar[1].trim();
    }
  }
  const m = /filename\s*=\s*("?)([^";\n]+)\1/i.exec(cd);
  return m ? m[2].trim() : null;
}

async function blobResult(res: Response): Promise<{ blob: Blob; filename: string }> {
  if (!res.ok) throw new Error(await errorText(res));
  const name = parseContentDispositionFilename(res.headers.get("Content-Disposition")) ?? "download";
  return { blob: await res.blob(), filename: name };
}

export async function downloadFileBlob(fileId: string, opts?: { signal?: AbortSignal }): Promise<{
  blob: Blob;
  filename: string;
}> {
  const res = await authFetch(`/v1/files/${encodeURIComponent(fileId)}/download`, {
    method: "GET",
    signal: opts?.signal,
  });
  return blobResult(res);
}

export async function downloadProjectArchive(projectId: string): Promise<{ blob: Blob; filename: string }> {
  const res = await authFetch(`/v1/projects/${encodeURIComponent(projectId)}/download-archive`, { method: "GET" });
  return blobResult(res);
}

export async function exportFile(
  fileId: string,
  format: "pdf" | "docx" | "txt",
): Promise<{ blob: Blob; filename: string }> {
  const res = await authFetch(
    `/v1/files/${encodeURIComponent(fileId)}/export?${new URLSearchParams({ target_format: format })}`,
    { method: "POST" },
  );
  return blobResult(res);
}

export async function listConversations(): Promise<ApiConversation[]> {
  return api<ApiConversation[]>("/v1/conversations");
}

export async function createConversation(body: { title?: string | null }): Promise<ApiConversation> {
  return api<ApiConversation>("/v1/conversations", { method: "POST", json: body ?? {} });
}

export async function deleteConversation(id: string): Promise<void> {
  await api<undefined>(`/v1/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function patchConversation(
  id: string,
  body: { title?: string; project_id?: string | null },
): Promise<ApiConversation> {
  return api<ApiConversation>(`/v1/conversations/${encodeURIComponent(id)}`, { method: "PATCH", json: body });
}

export async function listConversationMessages(
  conversationId: string,
  opts?: { signal?: AbortSignal },
): Promise<ApiChatMessage[]> {
  return api<ApiChatMessage[]>(`/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
    signal: opts?.signal,
  });
}

export async function ensureConversationFolder(conversationId: string): Promise<ApiConversation> {
  return api<ApiConversation>(`/v1/conversations/${encodeURIComponent(conversationId)}/ensure-folder`, {
    method: "POST",
  });
}

export async function getProject(projectId: string): Promise<ProjectResponse> {
  return api<ProjectResponse>(`/v1/projects/${encodeURIComponent(projectId)}`);
}

export async function projectDeleteImpact(projectId: string): Promise<ProjectDeleteImpact> {
  return api<ProjectDeleteImpact>(`/v1/projects/${encodeURIComponent(projectId)}/delete-impact`);
}

export async function prepareProjectDelete(projectId: string): Promise<PrepareResult> {
  return api<PrepareResult>(`/v1/projects/${encodeURIComponent(projectId)}/prepare-delete`, { method: "POST" });
}

export async function prepareProjectCreate(body: { name: string; description: string | null }): Promise<PrepareResult> {
  return api<PrepareResult>("/v1/projects/prepare-create", { method: "POST", json: body });
}

export async function createProjectConfirmed(confirmationToken: string): Promise<ProjectResponse> {
  return api<ProjectResponse>("/v1/projects", {
    method: "POST",
    headers: { "X-Resource-Confirmation": confirmationToken },
  });
}

export async function deleteProjectConfirmed(projectId: string, confirmationToken: string): Promise<void> {
  await api<undefined>(`/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
    headers: { "X-Resource-Confirmation": confirmationToken },
  });
}

export async function fileDeleteImpact(fileId: string): Promise<FileDeleteImpact> {
  return api<FileDeleteImpact>(`/v1/files/${encodeURIComponent(fileId)}/delete-impact`);
}

export async function prepareFileDelete(fileId: string): Promise<PrepareResult> {
  return api<PrepareResult>(`/v1/files/${encodeURIComponent(fileId)}/prepare-delete`, { method: "POST" });
}

export async function prepareFileReindex(fileId: string): Promise<PrepareResult> {
  return api<PrepareResult>(`/v1/files/${encodeURIComponent(fileId)}/prepare-reindex`, { method: "POST" });
}

export async function deleteFileConfirmed(fileId: string, confirmationToken: string): Promise<void> {
  await api<undefined>(`/v1/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    headers: { "X-Resource-Confirmation": confirmationToken },
  });
}

export async function reindexFileConfirmed(fileId: string, confirmationToken: string): Promise<ApiFile> {
  return api<ApiFile>(`/v1/files/${encodeURIComponent(fileId)}/reindex`, {
    method: "POST",
    headers: { "X-Resource-Confirmation": confirmationToken },
  });
}

export async function moveFilesToProject(fileIds: string[], projectId: string | null): Promise<ApiFile[]> {
  return api<ApiFile[]>("/v1/files/move", {
    method: "POST",
    json: { file_ids: fileIds, project_id: projectId },
  });
}

export async function uploadFile(
  file: File,
  opts: { projectId?: string; category?: string; topicId?: string },
): Promise<ApiFile> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts.projectId) fd.append("project_id", opts.projectId);
  if (opts.topicId) fd.append("topic_id", opts.topicId);
  if (opts.category) fd.append("category", opts.category);
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const res = await fetch(buildUrl("/v1/files"), { method: "POST", headers, body: fd });
  if (!res.ok) throw new Error(await errorText(res));
  return (await res.json()) as ApiFile;
}

export function uploadUserFile(file: File, projectId: string): Promise<ApiFile> {
  return uploadFile(file, { projectId });
}

export async function transcribeVoice(blob: Blob, filename: string): Promise<{ text: string }> {
  const fd = new FormData();
  fd.append("file", blob, filename);
  const headers: Record<string, string> = {};
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const res = await fetch(buildUrl("/v1/voice/transcribe"), { method: "POST", headers, body: fd });
  if (!res.ok) throw new Error(await errorText(res));
  return (await res.json()) as { text: string };
}
