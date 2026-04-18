import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  createProjectConfirmed,
  deleteFileConfirmed,
  deleteProjectConfirmed,
  downloadFileBlob,
  exportFile,
  fileDeleteImpact,
  getProject,
  importKieMusicByTask,
  prepareFileDelete,
  prepareFileReindex,
  prepareProjectCreate,
  prepareProjectDelete,
  projectDeleteImpact,
  reindexFileConfirmed,
  uploadFile,
  type FileDeleteImpact,
  type ProjectDeleteImpact,
  type ProjectResponse,
} from "@/lib/api";
import type { ApiFile } from "@/lib/api";

type Project = { id: string; name: string; description: string | null; created_at: string };

type PendingConfirm = {
  kind: "project_delete" | "project_create" | "file_delete" | "file_reindex";
  id: string;
  label: string;
  summary: string;
  token: string;
  impactNote?: string;
};

type ResourceInfo =
  | { kind: "project"; project: ProjectResponse; impact: ProjectDeleteImpact }
  | { kind: "file"; impact: FileDeleteImpact };

const uploadCategories = [
  { value: "", label: "Inne" },
  { value: "scenario", label: "Scenariusz" },
  { value: "graphic", label: "Grafika" },
  { value: "video", label: "Wideo" },
  { value: "music", label: "Muzyka" },
  { value: "poetry", label: "Poezja" },
  { value: "presentation", label: "Prezentacja" },
];

const CATEGORY_LABELS: Record<string, string> = {
  "": "Inne",
  scenario: "Scenariusz",
  graphic: "Grafika",
  video: "Wideo",
  music: "Muzyka",
  poetry: "Poezja",
  presentation: "Prezentacja",
  other: "Inne",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(name: string): string {
  const x = name.toLowerCase();
  const ext = x.includes(".") ? x.slice(x.lastIndexOf(".")) : "";
  if ([".mp3", ".wav", ".ogg"].includes(ext)) return String.fromCodePoint(0x1f3b5);
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(ext)) return String.fromCodePoint(0x1f5bc, 0xfe0f);
  if (ext === ".pdf") return String.fromCodePoint(0x1f4c4);
  if ([".doc", ".docx"].includes(ext)) return String.fromCodePoint(0x1f4dd);
  if ([".ppt", ".pptx"].includes(ext)) return String.fromCodePoint(0x1f4e0);
  if ([".mp4", ".webm", ".mov"].includes(ext)) return String.fromCodePoint(0x1f3ac);
  if (ext === ".json") return "{}";
  return String.fromCodePoint(0x1f4c1);
}

function formatFileDate(iso: string | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "";
  }
}

type ExportFormat = "pdf" | "docx" | "txt";

/** Jak w backendzie ``extract_plain_text`` — bez tekstu nie ma eksportu do PDF/DOCX/TXT. */
function supportsTextExport(f: ApiFile): boolean {
  const m = (f.mime_type ?? "").toLowerCase().split(";")[0].trim();
  const n = f.name.toLowerCase();
  if (m === "text/plain" || m === "application/json" || m === "text/markdown") return true;
  if (m === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") return true;
  if (n.endsWith(".txt") || n.endsWith(".md") || n.endsWith(".json") || n.endsWith(".docx")) return true;
  return false;
}

/** Formaty sensowne dla typu pliku (bez zbędnego „eksportu” do tego samego formatu). */
function exportFormatsForFile(f: ApiFile): ExportFormat[] {
  if (!supportsTextExport(f)) return [];
  const m = (f.mime_type ?? "").toLowerCase().split(";")[0].trim();
  const n = f.name.toLowerCase();
  const txtLike =
    m === "text/plain" ||
    m === "text/markdown" ||
    n.endsWith(".txt") ||
    n.endsWith(".md");
  const docx =
    m === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || n.endsWith(".docx");
  const json = m === "application/json" || n.endsWith(".json");

  if (txtLike) return ["pdf", "docx"];
  if (docx) return ["pdf", "txt"];
  if (json) return ["pdf", "docx", "txt"];
  return ["pdf", "docx", "txt"];
}

const cardBase =
  "rounded-2xl border border-ink-800/12 bg-white shadow-sm dark:border-paper-100/10 dark:bg-ink-900";
const inputBase =
  "rounded-xl border border-ink-800/20 bg-paper-50 px-3 py-2.5 text-sm outline-none ring-accent/0 transition focus:ring-2 focus:ring-accent/30 dark:border-paper-100/20 dark:bg-ink-950";

export default function MaterialsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [showNewProject, setShowNewProject] = useState(false);
  const [projectId, setProjectId] = useState<string>("");
  const [files, setFiles] = useState<ApiFile[]>([]);
  const [uploadCategory, setUploadCategory] = useState("");
  const [listFilterCategory, setListFilterCategory] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [resourceInfo, setResourceInfo] = useState<ResourceInfo | null>(null);
  const [kieOpen, setKieOpen] = useState(false);
  const [kieTaskId, setKieTaskId] = useState("");
  const [kieTargetProject, setKieTargetProject] = useState("");

  const refreshProjects = useCallback(async () => {
    const list = await api<Project[]>("/v1/projects");
    setProjects(list);
  }, []);

  const refreshFiles = useCallback(async () => {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    const list = await api<ApiFile[]>(`/v1/files${q}`);
    setFiles(list);
  }, [projectId]);

  useEffect(() => {
    refreshProjects().catch(() => setError("Nie udało się wczytać projektów"));
  }, [refreshProjects]);

  useEffect(() => {
    refreshFiles().catch(() => setError("Nie udało się wczytać plików"));
  }, [refreshFiles]);

  const filteredFiles = useMemo(() => {
    let list = files;
    const q = searchQuery.trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (listFilterCategory) list = list.filter((f) => f.category === listFilterCategory);
    return list;
  }, [files, searchQuery, listFilterCategory]);

  const activeProject = projectId ? projects.find((p) => p.id === projectId) : null;

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const prep = await prepareProjectCreate({
        name: newName.trim(),
        description: newDesc.trim() || null,
      });
      setPending({
        kind: "project_create",
        id: "",
        label: newName.trim(),
        summary: prep.summary,
        token: prep.confirmation_token,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setError(null);
    setBusy(true);
    try {
      await uploadFile(f, {
        projectId: projectId || undefined,
        category: uploadCategory || undefined,
      });
      await refreshFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload nie powiódł się");
    } finally {
      setBusy(false);
    }
  }

  async function onDownload(id: string) {
    setError(null);
    try {
      const { blob, filename } = await downloadFileBlob(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pobieranie nie powiodło się");
    }
  }

  async function startDeleteProject(id: string) {
    setError(null);
    setBusy(true);
    try {
      const p = projects.find((x) => x.id === id);
      const [prep, impact] = await Promise.all([prepareProjectDelete(id), projectDeleteImpact(id)]);
      setPending({
        kind: "project_delete",
        id,
        label: p?.name ?? id,
        summary: prep.summary,
        token: prep.confirmation_token,
        impactNote: `${impact.message} Powiązanych plików w projekcie: ${impact.files_attached_count}.`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się przygotować usunięcia");
    } finally {
      setBusy(false);
    }
  }

  async function openProjectInfo(id: string) {
    setError(null);
    setBusy(true);
    try {
      const [project, impact] = await Promise.all([getProject(id), projectDeleteImpact(id)]);
      setResourceInfo({ kind: "project", project, impact });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się wczytać projektu");
    } finally {
      setBusy(false);
    }
  }

  async function openFileInfo(id: string) {
    setError(null);
    try {
      const impact = await fileDeleteImpact(id);
      setResourceInfo({ kind: "file", impact });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się wczytać metadanych pliku");
    }
  }

  async function startDeleteFile(id: string, name: string) {
    setError(null);
    setBusy(true);
    try {
      const [prep, impact] = await Promise.all([prepareFileDelete(id), fileDeleteImpact(id)]);
      setPending({
        kind: "file_delete",
        id,
        label: name,
        summary: prep.summary,
        token: prep.confirmation_token,
        impactNote: `${impact.message} Fragmentów w indeksie: ${impact.indexed_chunks}.`,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się przygotować usunięcia pliku");
    } finally {
      setBusy(false);
    }
  }

  async function onExport(id: string, format: "pdf" | "docx" | "txt") {
    setError(null);
    try {
      const { blob, filename } = await exportFile(id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eksport nie powiódł się");
    }
  }

  async function startReindexFile(id: string, name: string) {
    setError(null);
    setBusy(true);
    try {
      const prep = await prepareFileReindex(id);
      setPending({
        kind: "file_reindex",
        id,
        label: name,
        summary: prep.summary,
        token: prep.confirmation_token,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się przygotować reindeksacji");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPending() {
    if (!pending) return;
    setError(null);
    setBusy(true);
    try {
      if (pending.kind === "project_create") {
        await createProjectConfirmed(pending.token);
        setNewName("");
        setNewDesc("");
        setShowNewProject(false);
        await refreshProjects();
      } else if (pending.kind === "project_delete") {
        await deleteProjectConfirmed(pending.id, pending.token);
        if (projectId === pending.id) setProjectId("");
        await refreshProjects();
        await refreshFiles();
      } else if (pending.kind === "file_delete") {
        await deleteFileConfirmed(pending.id, pending.token);
        await refreshFiles();
      } else {
        await reindexFileConfirmed(pending.id, pending.token);
        await refreshFiles();
      }
      setPending(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operacja nie powiodła się");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 pb-16 pt-2">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-ink-900 dark:text-paper-50 sm:text-3xl">
          Moje materiały
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-ink-600 dark:text-paper-400">
          Tutaj są pliki z asystenta i Twoje uploady. Ułóż je w{" "}
          <strong className="font-medium text-ink-800 dark:text-paper-200">projekty</strong>, żeby uporządkować pliki
          — albo przeglądaj wszystko naraz. Usuwanie i reindeksacja wymagają krótkiego potwierdzenia w oknie dialogowym.
        </p>
      </header>

      {error && (
        <div
          className="flex items-start justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="shrink-0 rounded-lg px-2 py-0.5 text-xs font-medium text-red-700 hover:bg-red-100 dark:text-red-300 dark:hover:bg-red-900/40"
          >
            Zamknij
          </button>
        </div>
      )}

      {kieOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]">
          <div className={`w-full max-w-md ${cardBase} p-6 shadow-xl`}>
            <h3 className="text-lg font-semibold text-ink-900 dark:text-paper-50">Pobierz utwór z KIE</h3>
            <p className="mt-2 text-xs leading-relaxed text-ink-500 dark:text-paper-500">
              Wklej <strong>taskId</strong> z pliku .txt po generacji w czacie. W konfiguracji serwera potrzebny jest m.in.{" "}
              <code className="rounded-md bg-paper-200/80 px-1.5 py-0.5 font-mono text-[0.7rem] dark:bg-ink-800">
                KIE_MUSIC_POLL_TIMEOUT_SECONDS &gt; 0
              </code>
              .
            </p>
            <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
              Task ID
              <input
                value={kieTaskId}
                onChange={(e) => setKieTaskId(e.target.value)}
                placeholder="np. a73adec4d76825c0…"
                className={`${inputBase} font-mono text-xs`}
                autoFocus
              />
            </label>
            <label className="mt-4 flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
              Zapisz w projekcie
              <select
                value={kieTargetProject}
                onChange={(e) => setKieTargetProject(e.target.value)}
                className={inputBase}
              >
                <option value="">Bez projektu (tylko biblioteka)</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setKieOpen(false)}
                className="rounded-xl border border-ink-800/20 px-4 py-2.5 text-sm font-medium dark:border-paper-100/20"
              >
                Anuluj
              </button>
              <button
                type="button"
                disabled={busy || !kieTaskId.trim()}
                onClick={() => {
                  void (async () => {
                    setError(null);
                    setBusy(true);
                    try {
                      await importKieMusicByTask({
                        task_id: kieTaskId.trim(),
                        project_id: kieTargetProject.trim() || null,
                      });
                      setKieOpen(false);
                      await refreshFiles();
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Import KIE nie powiódł się");
                    } finally {
                      setBusy(false);
                    }
                  })();
                }}
                className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-accent-dim disabled:opacity-50"
              >
                {busy ? "Pobieranie…" : "Pobierz MP3"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-12 lg:gap-8">
        {/* Lewa kolumna: projekty + upload */}
        <div className="space-y-4 lg:col-span-5">
          <section className={`${cardBase} p-5`}>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500 dark:text-paper-500">
              Projekt / folder
            </h2>
            <p className="mt-1 text-xs text-ink-500 dark:text-paper-500">
              Wybierz, które pliki widzisz na liście obok. „Wszystkie” — cała biblioteka.
            </p>

            <div className="mt-4 space-y-2">
              <button
                type="button"
                onClick={() => setProjectId("")}
                className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left text-sm font-medium transition ${
                  !projectId
                    ? "border-accent/50 bg-accent/10 text-accent dark:text-accent-muted"
                    : "border-ink-800/12 hover:border-ink-800/25 dark:border-paper-100/10 dark:hover:border-paper-100/20"
                }`}
              >
                <span>Wszystkie materiały</span>
                <span className="text-xs font-normal text-ink-500 dark:text-paper-500">{files.length} w widoku</span>
              </button>

              <ul className="max-h-[min(40vh,22rem)] space-y-2 overflow-y-auto pr-1">
                {projects.map((p) => {
                  const sel = projectId === p.id;
                  return (
                    <li
                      key={p.id}
                      className={`rounded-xl border transition ${
                        sel
                          ? "border-accent/50 bg-accent/5 ring-1 ring-accent/20"
                          : "border-ink-800/10 dark:border-paper-100/10"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 px-3 py-2.5">
                        <button
                          type="button"
                          onClick={() => setProjectId(sel ? "" : p.id)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <span className={`block truncate text-sm font-medium ${sel ? "text-accent dark:text-accent-muted" : ""}`}>
                            {p.name}
                          </span>
                          {p.description && (
                            <span className="mt-0.5 line-clamp-2 text-xs text-ink-500 dark:text-paper-500">{p.description}</span>
                          )}
                        </button>
                        <div className="flex shrink-0 flex-col gap-1">
                          <button
                            type="button"
                            onClick={() => void openProjectInfo(p.id)}
                            disabled={busy}
                            className="rounded-lg px-2 py-1 text-[0.65rem] font-medium text-ink-600 hover:bg-paper-100 dark:text-paper-400 dark:hover:bg-ink-800"
                          >
                            Info
                          </button>
                          <button
                            type="button"
                            onClick={() => void startDeleteProject(p.id)}
                            disabled={busy}
                            className="rounded-lg px-2 py-1 text-[0.65rem] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                          >
                            Usuń
                          </button>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>

              {projects.length === 0 && (
                <p className="rounded-xl border border-dashed border-ink-800/20 px-4 py-6 text-center text-sm text-ink-500 dark:border-paper-100/15 dark:text-paper-500">
                  Nie masz jeszcze projektów. Utwórz pierwszy poniżej — to tylko etykieta grupująca pliki.
                </p>
              )}

              <div className="border-t border-ink-800/10 pt-4 dark:border-paper-100/10">
                <button
                  type="button"
                  onClick={() => setShowNewProject((v) => !v)}
                  className="flex w-full items-center justify-between rounded-xl border border-ink-800/15 px-4 py-3 text-left text-sm font-medium hover:bg-paper-50 dark:border-paper-100/15 dark:hover:bg-ink-800/50"
                >
                  <span>Nowy projekt</span>
                  <span className="text-ink-400">{showNewProject ? "−" : "+"}</span>
                </button>
                {showNewProject && (
                  <form onSubmit={createProject} className="mt-3 space-y-3">
                    <label className="flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
                      Nazwa
                      <input
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="np. Jasełka 2025"
                        className={inputBase}
                      />
                    </label>
                    <label className="flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
                      Opis (opcjonalnie)
                      <input
                        value={newDesc}
                        onChange={(e) => setNewDesc(e.target.value)}
                        className={inputBase}
                      />
                    </label>
                    <button
                      type="submit"
                      disabled={busy}
                      className="w-full rounded-xl bg-accent py-2.5 text-sm font-semibold text-white hover:bg-accent-dim disabled:opacity-50"
                    >
                      Przygotuj utworzenie
                    </button>
                  </form>
                )}
              </div>
            </div>
          </section>

          <section className={`${cardBase} p-5`}>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500 dark:text-paper-500">
              Dodaj plik
            </h2>
            <p className="mt-1 text-xs text-ink-500 dark:text-paper-500">
              Plik trafi do {activeProject ? `projektu „${activeProject.name}”` : "biblioteki (bez projektu)"}.
            </p>
            <div className="mt-4 space-y-3">
              <label className="flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
                Kategoria w bibliotece
                <select
                  value={uploadCategory}
                  onChange={(e) => setUploadCategory(e.target.value)}
                  className={inputBase}
                >
                  {uploadCategories.map((c) => (
                    <option key={c.value || "other"} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label
                className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-ink-800/20 bg-paper-50/50 px-4 py-8 text-center transition hover:border-accent/40 hover:bg-accent/5 dark:border-paper-100/15 dark:bg-ink-950/50`}
              >
                <span className="text-2xl" aria-hidden>
                  {String.fromCodePoint(0x1f4e4)}
                </span>
                <span className="mt-2 text-sm font-medium text-ink-800 dark:text-paper-200">
                  {busy ? "Przetwarzanie…" : "Wybierz plik z dysku"}
                </span>
                <span className="mt-1 text-xs text-ink-500">Maks. 50 MB</span>
                <input type="file" className="hidden" onChange={(e) => void onUpload(e)} disabled={busy} />
              </label>
            </div>

            <details className="mt-4 rounded-xl border border-ink-800/10 px-3 py-2 text-xs dark:border-paper-100/10">
              <summary className="cursor-pointer font-medium text-ink-700 dark:text-paper-300">Import audio z KIE (Suno)</summary>
              <p className="mt-2 leading-relaxed text-ink-500 dark:text-paper-500">
                Jeśli masz <strong>taskId</strong> z raportu po generacji w czacie, możesz dociągnąć MP3 bez webhooka.
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setKieTaskId("");
                  setKieTargetProject(projectId || "");
                  setKieOpen(true);
                }}
                className="mt-2 w-full rounded-lg border border-accent/35 bg-accent/10 py-2 text-xs font-semibold text-accent hover:bg-accent/15 disabled:opacity-50 dark:text-accent-muted"
              >
                Otwórz formularz importu
              </button>
            </details>
          </section>
        </div>

        {/* Prawa kolumna: lista plików */}
        <div className="lg:col-span-7">
          <section className={`${cardBase} min-h-[12rem] p-5`}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink-900 dark:text-paper-50">Twoje pliki</h2>
                <p className="mt-0.5 text-xs text-ink-500 dark:text-paper-500">
                  {activeProject ? `Projekt: ${activeProject.name}` : "Wszystkie projekty"} · {filteredFiles.length}{" "}
                  {filteredFiles.length === 1 ? "plik" : "plików"}
                  {listFilterCategory || searchQuery ? " (po filtrze)" : ""}
                </p>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[200px]">
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Szukaj po nazwie…"
                  className={inputBase}
                  aria-label="Szukaj plików"
                />
                <select
                  value={listFilterCategory}
                  onChange={(e) => setListFilterCategory(e.target.value)}
                  className={inputBase}
                  aria-label="Filtruj po kategorii"
                >
                  <option value="">Wszystkie kategorie</option>
                  {uploadCategories
                    .filter((c) => c.value)
                    .map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            {filteredFiles.length === 0 ? (
              <div className="mt-10 rounded-2xl border border-dashed border-ink-800/15 bg-paper-50/30 px-6 py-12 text-center dark:border-paper-100/10 dark:bg-ink-950/30">
                <p className="text-sm font-medium text-ink-700 dark:text-paper-300">
                  {files.length === 0 ? "Brak plików w tym widoku" : "Nic nie pasuje do wyszukiwania ani filtra"}
                </p>
                <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-ink-500 dark:text-paper-500">
                  {files.length === 0
                    ? "Wygeneruj materiał w Asystencie albo prześlij plik — pojawi się tutaj."
                    : "Zmień filtr lub wyczyść pole szukania."}
                </p>
                {(searchQuery || listFilterCategory) && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery("");
                      setListFilterCategory("");
                    }}
                    className="mt-4 text-xs font-semibold text-accent hover:underline"
                  >
                    Wyczyść filtry
                  </button>
                )}
              </div>
            ) : (
              <ul className="mt-6 space-y-3">
                {filteredFiles.map((f) => {
                  const cat = CATEGORY_LABELS[f.category] ?? f.category;
                  const created = formatFileDate((f as ApiFile & { created_at?: string }).created_at);
                  return (
                    <li
                      key={f.id}
                      className="flex flex-col gap-4 rounded-2xl border border-ink-800/10 bg-paper-50/40 p-4 dark:border-paper-100/10 dark:bg-ink-950/40 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex min-w-0 flex-1 items-start gap-3">
                        <div
                          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/15 text-lg"
                          aria-hidden
                        >
                          {fileIcon(f.name)}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink-900 dark:text-paper-50">{f.name}</p>
                          <p className="mt-0.5 text-xs text-ink-500 dark:text-paper-500">
                            <span className="rounded-md bg-ink-800/5 px-1.5 py-0.5 dark:bg-paper-100/10">{cat}</span>
                            <span className="mx-1.5">·</span>
                            {formatBytes(f.size_bytes)}
                            {created && (
                              <>
                                <span className="mx-1.5">·</span>
                                {created}
                              </>
                            )}
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col gap-2 sm:items-end">
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => void onDownload(f.id)}
                            className="rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-accent-dim"
                          >
                            Pobierz
                          </button>
                          {exportFormatsForFile(f).map((fmt) => (
                            <button
                              key={fmt}
                              type="button"
                              onClick={() => void onExport(f.id, fmt)}
                              className="rounded-xl border border-ink-800/15 px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-700 hover:bg-white dark:border-paper-100/15 dark:text-paper-300 dark:hover:bg-ink-900"
                            >
                              {fmt}
                            </button>
                          ))}
                        </div>
                        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem] font-medium">
                          <button
                            type="button"
                            onClick={() => void openFileInfo(f.id)}
                            className="text-ink-600 hover:text-accent dark:text-paper-400"
                          >
                            Szczegóły / skutek usunięcia
                          </button>
                          <button
                            type="button"
                            onClick={() => void startReindexFile(f.id, f.name)}
                            disabled={busy}
                            className="text-ink-600 hover:text-accent disabled:opacity-50 dark:text-paper-400"
                          >
                            Reindeksuj
                          </button>
                          <button
                            type="button"
                            onClick={() => void startDeleteFile(f.id, f.name)}
                            disabled={busy}
                            className="text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
                          >
                            Usuń
                          </button>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>

      {resourceInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]">
          <div className={`max-h-[90vh] w-full max-w-lg overflow-y-auto ${cardBase} p-6 shadow-xl`}>
            <h3 className="text-lg font-semibold text-ink-900 dark:text-paper-50">
              {resourceInfo.kind === "project" ? "Szczegóły projektu" : "Szczegóły pliku"}
            </h3>
            {resourceInfo.kind === "project" && (
              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Nazwa</dt>
                  <dd className="mt-0.5 font-medium">{resourceInfo.project.name}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Opis</dt>
                  <dd className="mt-0.5">{resourceInfo.project.description ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Utworzono</dt>
                  <dd className="mt-0.5 font-mono text-xs">{resourceInfo.project.created_at}</dd>
                </div>
                <div className="border-t border-ink-800/10 pt-3 dark:border-paper-100/10">
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Skutek usunięcia</dt>
                  <dd className="mt-1 text-ink-700 dark:text-paper-300">{resourceInfo.impact.message}</dd>
                  <dd className="mt-2 text-xs">
                    Plików w projekcie: <strong>{resourceInfo.impact.files_attached_count}</strong>
                  </dd>
                </div>
              </dl>
            )}
            {resourceInfo.kind === "file" && (
              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Nazwa</dt>
                  <dd className="mt-0.5 font-medium">{resourceInfo.impact.name}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Rozmiar</dt>
                  <dd className="mt-0.5">{formatBytes(resourceInfo.impact.size_bytes)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Fragmentów w indeksie</dt>
                  <dd className="mt-0.5">{resourceInfo.impact.indexed_chunks}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-ink-500 dark:text-paper-500">Komunikat</dt>
                  <dd className="mt-1 text-ink-700 dark:text-paper-300">{resourceInfo.impact.message}</dd>
                </div>
              </dl>
            )}
            <div className="mt-8 flex justify-end">
              <button
                type="button"
                onClick={() => setResourceInfo(null)}
                className="rounded-xl border border-ink-800/20 px-4 py-2.5 text-sm font-medium dark:border-paper-100/20"
              >
                Zamknij
              </button>
            </div>
          </div>
        </div>
      )}

      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]">
          <div className={`max-h-[90vh] w-full max-w-md overflow-y-auto ${cardBase} p-6 shadow-xl`}>
            <h3 className="text-lg font-semibold text-ink-900 dark:text-paper-50">
              {pending.kind === "project_create" && "Potwierdź utworzenie projektu"}
              {pending.kind === "project_delete" && "Potwierdź usunięcie projektu"}
              {pending.kind === "file_delete" && "Potwierdź usunięcie pliku"}
              {pending.kind === "file_reindex" && "Potwierdź modyfikację indeksu"}
            </h3>
            <p className="mt-3 text-sm text-ink-700 dark:text-paper-300">
              <strong>{pending.label}</strong>
            </p>
            <p className="mt-3 text-sm leading-relaxed text-ink-600 dark:text-paper-400">{pending.summary}</p>
            {pending.impactNote && pending.kind !== "project_create" && (
              <p className="mt-4 rounded-xl border border-ink-800/12 bg-paper-50 px-3 py-2 text-xs leading-relaxed text-ink-700 dark:border-paper-100/10 dark:bg-ink-950 dark:text-paper-300">
                <strong className="text-ink-800 dark:text-paper-200">API:</strong> {pending.impactNote}
              </p>
            )}
            {pending.kind !== "project_create" && (
              <p className="mt-4 text-xs leading-relaxed text-ink-500 dark:text-paper-500">
                Tej operacji nie można cofnąć z poziomu aplikacji.
              </p>
            )}
            <div className="mt-8 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setPending(null)}
                className="rounded-xl border border-ink-800/20 px-4 py-2.5 text-sm font-medium dark:border-paper-100/20"
              >
                Anuluj
              </button>
              <button
                type="button"
                onClick={() => void confirmPending()}
                disabled={busy}
                className={
                  pending.kind === "project_create"
                    ? "rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-accent-dim disabled:opacity-50"
                    : "rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
                }
              >
                {busy ? "…" : "Potwierdzam"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
