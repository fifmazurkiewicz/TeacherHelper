import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ImageLightbox } from "@/components/ChatAttachmentPreviews";
import {
  api,
  createProjectConfirmed,
  deleteFileConfirmed,
  deleteProjectConfirmed,
  downloadFileBlob,
  downloadProjectArchive,
  exportFile,
  fileDeleteImpact,
  getProject,
  moveFilesToProject,
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

/** Widok „pliki bez przypisanego katalogu” — nie jest to UUID projektu. */
const LOOSE_FOLDER_ID = "__bez_projektu__";

type Project = { id: string; name: string; description: string | null; created_at: string };

type PendingConfirm =
  | {
      kind: "project_delete" | "project_create" | "file_delete" | "file_reindex";
      id: string;
      label: string;
      summary: string;
      token: string;
      impactNote?: string;
    }
  | {
      kind: "files_delete_bulk";
      label: string;
      summary: string;
      impactNote?: string;
      items: { id: string; label: string; token: string }[];
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

/** Odmiana:1 plik, 2–4 pliki (22 pliki), 5–21 plików, 12–14 plików. */
function plikiLabel(n: number): string {
  if (n === 1) return "plik";
  const mod100 = n % 100;
  if (mod100 >= 12 && mod100 <= 14) return "plików";
  const mod10 = n % 10;
  if (mod10 >= 2 && mod10 <= 4) return "pliki";
  return "plików";
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

function isRasterImageFile(f: ApiFile): boolean {
  const m = (f.mime_type ?? "").toLowerCase();
  if (m.startsWith("image/") && !m.includes("svg")) return true;
  const x = f.name.toLowerCase();
  const ext = x.includes(".") ? x.slice(x.lastIndexOf(".")) : "";
  return [".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(ext);
}

function isAudioFile(f: ApiFile): boolean {
  const m = (f.mime_type ?? "").toLowerCase().split(";")[0].trim();
  if (m.startsWith("audio/")) return true;
  if (m === "application/octet-stream" || m === "binary/octet-stream") {
    return /\.(mp3|wav|ogg|m4a|aac|flac|opus|weba)$/i.test(f.name);
  }
  const x = f.name.toLowerCase();
  const ext = x.includes(".") ? x.slice(x.lastIndexOf(".")) : "";
  return [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus", ".weba"].includes(ext);
}

function IconPlay({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M8 5v14l11-7L8 5z" />
    </svg>
  );
}

function IconPause({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
    </svg>
  );
}

const audioListBtnClass =
  "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border-0 bg-accent/15 text-accent transition hover:bg-accent/25 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:ring-offset-2 focus:ring-offset-paper-50 dark:text-accent-muted dark:focus:ring-offset-ink-900 disabled:cursor-wait disabled:opacity-70";

type FileListFileThumbProps = {
  f: ApiFile;
  materialsAudio: { fileId: string; url: string } | null;
  materialsAudioPlaying: boolean;
  materialsAudioLoadingId: string | null;
  onMaterialsAudioClick: (f: ApiFile) => void;
};

function FileListFileThumb({
  f,
  materialsAudio,
  materialsAudioPlaying,
  materialsAudioLoadingId,
  onMaterialsAudioClick,
}: FileListFileThumbProps) {
  if (isRasterImageFile(f)) return <FileListRasterThumb f={f} />;
  if (isAudioFile(f)) {
    const active = materialsAudio?.fileId === f.id;
    const playing = active && materialsAudioPlaying;
    const loading = materialsAudioLoadingId === f.id;
    return (
      <button
        type="button"
        className={audioListBtnClass}
        onClick={() => onMaterialsAudioClick(f)}
        disabled={loading}
        aria-label={
          loading
            ? "Wczytywanie pliku…"
            : playing
              ? "Wstrzymaj odsłuch"
              : active
                ? "Wznów odsłuch"
                : "Odsłuchaj w przeglądarce"
        }
      >
        {loading ? (
          <span
            className="size-5 shrink-0 animate-spin rounded-full border-2 border-accent/30 border-t-accent"
            aria-hidden
          />
        ) : playing ? (
          <IconPause className="size-5" />
        ) : (
          <IconPlay className="ml-0.5 size-5" />
        )}
      </button>
    );
  }
  return (
    <div
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/15 text-lg"
      aria-hidden
    >
      {fileIcon(f.name)}
    </div>
  );
}

function FileListRasterThumb({ f }: { f: ApiFile }) {
  const [shouldLoad, setShouldLoad] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [useFallback, setUseFallback] = useState(false);
  const [lightbox, setLightbox] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const urlForCleanup = useRef<string | null>(null);

  const want = isRasterImageFile(f);

  useEffect(() => {
    if (!want) return;
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setShouldLoad(true);
            io.disconnect();
            break;
          }
        }
      },
      { root: null, rootMargin: "160px 0px", threshold: 0.01 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [want, f.id]);

  useEffect(() => {
    if (!want || !shouldLoad) return;
    if (useFallback) return;
    const ac = new AbortController();
    (async () => {
      try {
        const { blob } = await downloadFileBlob(f.id, { signal: ac.signal });
        if (ac.signal.aborted) return;
        const t = (blob.type || "").toLowerCase();
        if (!t.startsWith("image/") || t.includes("svg")) {
          setUseFallback(true);
          return;
        }
        const u = URL.createObjectURL(blob);
        urlForCleanup.current = u;
        setSrc(u);
      } catch {
        if (!ac.signal.aborted) setUseFallback(true);
      }
    })();
    return () => {
      ac.abort();
      if (urlForCleanup.current) {
        URL.revokeObjectURL(urlForCleanup.current);
        urlForCleanup.current = null;
      }
    };
  }, [want, shouldLoad, f.id, useFallback]);

  if (!want) {
    return (
      <div
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/15 text-lg"
        aria-hidden
      >
        {fileIcon(f.name)}
      </div>
    );
  }

  const loading = shouldLoad && !src && !useFallback;

  return (
    <div
      ref={ref}
      className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-accent/15 text-lg"
      aria-hidden
    >
      {useFallback && fileIcon(f.name)}
      {loading && (
        <span className="block size-8 rounded-md bg-ink-800/10 animate-pulse dark:bg-paper-100/10" />
      )}
      {src && !useFallback && (
        <>
          <button
            type="button"
            className="group relative h-full w-full min-h-0 cursor-zoom-in overflow-hidden rounded-xl border-0 p-0 text-left focus:outline-none focus:ring-2 focus:ring-accent/50 focus:ring-offset-2 focus:ring-offset-paper-50 dark:focus:ring-offset-ink-900"
            onClick={() => setLightbox(true)}
            title="Powiększ"
            aria-label={`Powiększ obraz: ${f.name}`}
          >
            <img
              src={src}
              alt=""
              className="h-full w-full object-cover transition group-hover:opacity-90"
              onError={() => {
                if (urlForCleanup.current) {
                  URL.revokeObjectURL(urlForCleanup.current);
                  urlForCleanup.current = null;
                }
                setSrc(null);
                setUseFallback(true);
              }}
            />
          </button>
          {lightbox && (
            <ImageLightbox url={src} name={f.name} onClose={() => setLightbox(false)} />
          )}
        </>
      )}
      {!shouldLoad && !useFallback && !src && fileIcon(f.name)}
    </div>
  );
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
  const [folderZipBusy, setFolderZipBusy] = useState(false);
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [resourceInfo, setResourceInfo] = useState<ResourceInfo | null>(null);
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(() => new Set());
  const [bulkMoveTarget, setBulkMoveTarget] = useState("");
  const selectAllFilteredRef = useRef<HTMLInputElement>(null);

  const [materialsAudio, setMaterialsAudio] = useState<{
    fileId: string;
    url: string;
  } | null>(null);
  const [materialsAudioPlaying, setMaterialsAudioPlaying] = useState(false);
  const [materialsAudioLoadingId, setMaterialsAudioLoadingId] = useState<string | null>(null);
  const materialsAudioRef = useRef<HTMLAudioElement | null>(null);
  const materialsAudioCleanupRef = useRef<{ fileId: string; url: string } | null>(null);
  materialsAudioCleanupRef.current = materialsAudio;

  const refreshProjects = useCallback(async () => {
    const list = await api<Project[]>("/v1/projects");
    setProjects(list);
  }, []);

  const refreshFiles = useCallback(async () => {
    const list = await api<ApiFile[]>(`/v1/files`);
    setFiles(list);
  }, []);

  useEffect(() => {
    refreshProjects().catch((err) =>
      setError(err instanceof Error ? err.message : "Nie udało się wczytać projektów"),
    );
  }, [refreshProjects]);

  useEffect(() => {
    refreshFiles().catch((err) =>
      setError(err instanceof Error ? err.message : "Nie udało się wczytać plików"),
    );
  }, [refreshFiles]);

  useEffect(() => {
    setSelectedFileIds(new Set());
    setShowUploadPanel(false);
    setBulkMoveTarget("");
  }, [projectId]);

  useEffect(() => {
    setSelectedFileIds((prev) => {
      const next = new Set([...prev].filter((id) => files.some((f) => f.id === id)));
      if (next.size === prev.size && [...prev].every((id) => next.has(id))) return prev;
      return next;
    });
  }, [files]);

  useEffect(() => {
    return () => {
      const x = materialsAudioCleanupRef.current;
      if (x?.url) URL.revokeObjectURL(x.url);
    };
  }, []);

  useEffect(() => {
    setMaterialsAudio((prev) => {
      if (!prev) return null;
      if (files.some((x) => x.id === prev.fileId)) return prev;
      URL.revokeObjectURL(prev.url);
      return null;
    });
  }, [files]);

  const filesInFolder = useMemo(() => {
    if (!projectId) return [];
    if (projectId === LOOSE_FOLDER_ID) return files.filter((f) => !f.project_id);
    return files.filter((f) => f.project_id === projectId);
  }, [files, projectId]);

  const filteredFiles = useMemo(() => {
    let list = filesInFolder;
    const q = searchQuery.trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (listFilterCategory) list = list.filter((f) => f.category === listFilterCategory);
    return list;
  }, [filesInFolder, searchQuery, listFilterCategory]);

  const filteredProjects = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => p.name.toLowerCase().includes(q));
  }, [projects, searchQuery]);

  const looseCount = useMemo(() => files.filter((f) => !f.project_id).length, [files]);

  const activeProject =
    projectId && projectId !== LOOSE_FOLDER_ID ? projects.find((p) => p.id === projectId) ?? null : null;
  const folderTitle =
    projectId === LOOSE_FOLDER_ID ? "Inne pliki" : activeProject?.name ?? "Katalog";

  const selectedIdsInFiles = useMemo(
    () => [...selectedFileIds].filter((id) => files.some((f) => f.id === id)),
    [selectedFileIds, files],
  );

  const filteredIds = useMemo(() => filteredFiles.map((f) => f.id), [filteredFiles]);
  const selectedInFilteredCount = useMemo(
    () => filteredIds.filter((id) => selectedFileIds.has(id)).length,
    [filteredIds, selectedFileIds],
  );
  const allFilteredSelected =
    filteredFiles.length > 0 && selectedInFilteredCount === filteredFiles.length;
  const someFilteredSelected =
    selectedInFilteredCount > 0 && selectedInFilteredCount < filteredFiles.length;

  useEffect(() => {
    const el = selectAllFilteredRef.current;
    if (el) el.indeterminate = someFilteredSelected;
  }, [someFilteredSelected]);

  function toggleSelectAllFiltered(checked: boolean) {
    setSelectedFileIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        filteredIds.forEach((id) => next.add(id));
      } else {
        filteredIds.forEach((id) => next.delete(id));
      }
      return next;
    });
  }

  function toggleFileSelected(fileId: string, checked: boolean) {
    setSelectedFileIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(fileId);
      else next.delete(fileId);
      return next;
    });
  }

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
        projectId: projectId && projectId !== LOOSE_FOLDER_ID ? projectId : undefined,
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

  const onMaterialsAudioClick = useCallback(
    async (f: ApiFile) => {
      if (materialsAudio?.fileId === f.id) {
        const el = materialsAudioRef.current;
        if (el) {
          if (el.paused) void el.play().catch(() => {});
          else el.pause();
        }
        return;
      }
      if (materialsAudio?.url) URL.revokeObjectURL(materialsAudio.url);
      setMaterialsAudioLoadingId(f.id);
      setError(null);
      try {
        const { blob } = await downloadFileBlob(f.id);
        const url = URL.createObjectURL(blob);
        setMaterialsAudio({ fileId: f.id, url });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Nie udało się wczytać pliku");
        setMaterialsAudio(null);
      } finally {
        setMaterialsAudioLoadingId((id) => (id === f.id ? null : id));
      }
    },
    [materialsAudio],
  );

  useEffect(() => {
    const el = materialsAudioRef.current;
    if (!materialsAudio) {
      if (el) {
        el.pause();
        el.removeAttribute("src");
      }
      return;
    }
    if (!el) return;
    el.src = materialsAudio.url;
    void el.load();
    const p = el.play();
    if (p !== undefined) {
      p.catch(() => {
        setError("Nie udało się uruchomić odtwarzania w tej przeglądarce.");
      });
    }
  }, [materialsAudio]);

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

  async function onBulkMoveFiles() {
    const ids = selectedIdsInFiles;
    if (ids.length === 0 || !bulkMoveTarget || !projectId) return;
    if (bulkMoveTarget === projectId) {
      setError("Wybierz inny katalog niż bieżący.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const targetProjectId = bulkMoveTarget === LOOSE_FOLDER_ID ? null : bulkMoveTarget;
      await moveFilesToProject(ids, targetProjectId);
      setSelectedFileIds(new Set());
      setBulkMoveTarget("");
      await refreshFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się przenieść plików");
    } finally {
      setBusy(false);
    }
  }

  async function startBulkDeleteFiles() {
    const ids = selectedIdsInFiles;
    if (ids.length === 0) return;
    setError(null);
    setBusy(true);
    try {
      const prepared = await Promise.all(
        ids.map(async (id) => {
          const f = files.find((x) => x.id === id);
          const [prep, impact] = await Promise.all([prepareFileDelete(id), fileDeleteImpact(id)]);
          return {
            id,
            label: f?.name ?? id,
            token: prep.confirmation_token,
            chunks: impact.indexed_chunks,
          };
        }),
      );
      const totalChunks = prepared.reduce((a, x) => a + x.chunks, 0);
      const n = prepared.length;
      const namesPreview = prepared
        .slice(0, 8)
        .map((x) => x.label)
        .join(", ");
      const more = n > 8 ? ` (+${n - 8} więcej)` : "";
      const bulkImpactNote = `Łącznie ${totalChunks} fragmentów w indeksie. Wybrane: ${namesPreview}${more}`;
      setPending({
        kind: "files_delete_bulk",
        label: `${n} ${plikiLabel(n)}`,
        summary: `Trwale usunąć ${n} ${plikiLabel(n)} z biblioteki i indeksu?`,
        impactNote: bulkImpactNote,
        items: prepared.map(({ id, label, token }) => ({ id, label, token })),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się przygotować zbiorczego usunięcia");
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
      } else if (pending.kind === "files_delete_bulk") {
        for (const it of pending.items) {
          await deleteFileConfirmed(it.id, it.token);
        }
        setSelectedFileIds(new Set());
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
    <div className="mx-auto max-w-6xl space-y-8 px-4 pb-16 pt-2">
      <audio
        ref={materialsAudioRef}
        className="hidden"
        preload="auto"
        onPlay={() => setMaterialsAudioPlaying(true)}
        onPause={() => setMaterialsAudioPlaying(false)}
        onEnded={() => setMaterialsAudioPlaying(false)}
        playsInline
      />
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-ink-900 dark:text-paper-50 sm:text-3xl">
          Moje materiały
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-ink-600 dark:text-paper-400">
          <strong className="font-medium text-ink-800 dark:text-paper-200">Katalog</strong> to folder na materiały (np.
          przedstawienie o Kopciuszku). W Asystencie wybierz ten sam katalog — pliki z czatu trafią tutaj. Usunięcie
          katalogu usuwa też jego pliki. Pojedyncze pliki i reindeksacja wymagają krótkiego potwierdzenia.
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

      {!projectId ? (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold text-ink-900 dark:text-paper-50">Twoje pliki</h2>
              <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
                Kliknij folder. W Asystencie wybierz ten sam katalog — materiały z czatu zapiszą się tutaj.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowNewProject((v) => !v)}
              className="shrink-0 rounded-xl border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent hover:bg-accent/15 dark:text-accent-muted"
            >
              {showNewProject ? "Zwiń formularz" : "+ Nowy katalog"}
            </button>
          </div>

          {showNewProject && (
            <form
              onSubmit={createProject}
              className="mt-4 space-y-3 rounded-xl border border-ink-800/10 bg-paper-50/40 p-4 dark:border-paper-100/10 dark:bg-ink-950/40"
            >
              <label className="flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
                Nazwa katalogu
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="np. Przedstawienie o Kopciuszku"
                  className={inputBase}
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium text-ink-800 dark:text-paper-200">
                Opis (opcjonalnie)
                <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} className={inputBase} />
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

          <div className="mt-6 max-w-md">
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Szukaj katalogu po nazwie…"
              className={inputBase}
              aria-label="Szukaj katalogów"
            />
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            <button
              type="button"
              onClick={() => setProjectId(LOOSE_FOLDER_ID)}
              className="flex flex-col items-center rounded-2xl border border-ink-800/12 bg-paper-50/40 p-4 text-center transition hover:border-accent/40 hover:bg-accent/5 dark:border-paper-100/10 dark:bg-ink-950/40"
            >
              <span className="text-4xl leading-none" aria-hidden>
                {String.fromCodePoint(0x1f4c1)}
              </span>
              <span className="mt-2 text-sm font-semibold text-ink-900 dark:text-paper-50">Inne pliki</span>
              <span className="mt-1 text-xs text-ink-500 dark:text-paper-500">
                {looseCount} {plikiLabel(looseCount)}
              </span>
            </button>
            {filteredProjects.map((p) => {
              const cnt = files.filter((f) => f.project_id === p.id).length;
              return (
                <div
                  key={p.id}
                  className="group relative flex flex-col rounded-2xl border border-ink-800/12 bg-paper-50/40 dark:border-paper-100/10 dark:bg-ink-950/40"
                >
                  <button
                    type="button"
                    onClick={() => setProjectId(p.id)}
                    className="flex flex-1 flex-col items-center p-4 text-center transition hover:bg-accent/5"
                  >
                    <span className="text-4xl leading-none" aria-hidden>
                      {String.fromCodePoint(0x1f4c2)}
                    </span>
                    <span className="mt-2 line-clamp-2 min-h-10 text-sm font-semibold text-ink-900 dark:text-paper-50">
                      {p.name}
                    </span>
                    <span className="mt-1 text-xs text-ink-500 dark:text-paper-500">
                      {cnt} {plikiLabel(cnt)}
                    </span>
                  </button>
                  <div className="absolute right-1 top-1 flex gap-0.5 rounded-md bg-white/90 p-0.5 opacity-0 shadow-sm transition group-hover:opacity-100 dark:bg-ink-900/90">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void openProjectInfo(p.id);
                      }}
                      disabled={busy}
                      className="rounded px-1.5 py-0.5 text-[0.65rem] font-medium text-ink-600 hover:bg-paper-100 dark:text-paper-400 dark:hover:bg-ink-800"
                    >
                      Info
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void startDeleteProject(p.id);
                      }}
                      disabled={busy}
                      className="rounded px-1.5 py-0.5 text-[0.65rem] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                    >
                      Usuń
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {projects.length > 0 && filteredProjects.length === 0 && (
            <p className="mt-6 text-center text-sm text-ink-500 dark:text-paper-500">
              Brak katalogów pasujących do wyszukiwania.
            </p>
          )}
          {projects.length === 0 && (
            <p className="mt-6 rounded-xl border border-dashed border-ink-800/20 px-4 py-8 text-center text-sm text-ink-500 dark:border-paper-100/15 dark:text-paper-500">
              Nie masz jeszcze własnych katalogów — dodaj pierwszy przyciskiem „+ Nowy katalog” albo korzystaj z folderu{" "}
              <strong className="font-medium text-ink-700 dark:text-paper-300">Inne pliki</strong>.
            </p>
          )}
        </div>
      ) : (
        <section className={`${cardBase} overflow-hidden`}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-ink-800/10 px-4 py-3 dark:border-paper-100/10">
            <button
              type="button"
              onClick={() => setProjectId("")}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
            >
              ← Twoje pliki
            </button>
            <span className="text-ink-300 dark:text-paper-600">/</span>
            <h2 className="text-base font-semibold text-ink-900 dark:text-paper-50">{folderTitle}</h2>
            {activeProject?.description && (
              <p className="w-full text-xs text-ink-500 sm:ml-auto sm:w-auto dark:text-paper-500">
                {activeProject.description}
              </p>
            )}
          </div>
          <div className="space-y-6 p-5">
            <div>
              <button
                type="button"
                onClick={() => setShowUploadPanel((v) => !v)}
                className="rounded-xl border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent hover:bg-accent/15 dark:text-accent-muted"
                aria-expanded={showUploadPanel}
              >
                {showUploadPanel ? "Zwiń dodawanie pliku" : "Dodaj plik"}
              </button>
              <div
                className={`grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none ${
                  showUploadPanel ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                }`}
              >
                <div className="overflow-hidden">
                  <div className="mt-4 rounded-xl border border-ink-800/10 bg-paper-50/30 p-4 dark:border-paper-100/10 dark:bg-ink-950/30">
                    <h3 className="text-sm font-semibold text-ink-800 dark:text-paper-200">
                      Przesyłanie pliku
                    </h3>
                    <p className="mt-1 text-xs text-ink-500 dark:text-paper-500">
                      {projectId === LOOSE_FOLDER_ID
                        ? "Plik trafi do biblioteki bez przypisanego katalogu."
                        : `Plik trafi do katalogu „${folderTitle}”.`}
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
                        <input
                          type="file"
                          className="hidden"
                          onChange={(e) => void onUpload(e)}
                          disabled={busy}
                        />
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <section className={`${cardBase} min-h-[12rem] p-5`}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-ink-900 dark:text-paper-50">Twoje pliki</h2>
                <p className="mt-0.5 text-xs text-ink-500 dark:text-paper-500">
                  {folderTitle} · {filteredFiles.length}{" "}
                  {filteredFiles.length === 1 ? "plik" : "plików"}
                  {listFilterCategory || searchQuery ? " (po filtrze)" : ""}
                </p>
                {projectId !== LOOSE_FOLDER_ID && filesInFolder.length > 0 ? (
                  <button
                    type="button"
                    disabled={folderZipBusy || busy}
                    onClick={() => {
                      void (async () => {
                        if (!projectId || projectId === LOOSE_FOLDER_ID) return;
                        setError(null);
                        setFolderZipBusy(true);
                        try {
                          const { blob, filename } = await downloadProjectArchive(projectId);
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url;
                          a.download = filename;
                          a.click();
                          URL.revokeObjectURL(url);
                        } catch (e) {
                          setError(
                            e instanceof Error
                              ? e.message
                              : "Nie udało się pobrać archiwum katalogu",
                          );
                        } finally {
                          setFolderZipBusy(false);
                        }
                      })();
                    }}
                    className="mt-3 w-full rounded-lg border border-ink-800/20 bg-paper-50 px-3 py-2 text-left text-xs font-semibold text-ink-800 hover:bg-paper-100 disabled:opacity-50 dark:border-paper-100/20 dark:bg-ink-950 dark:text-paper-200 dark:hover:bg-ink-800 sm:w-auto"
                  >
                    {folderZipBusy ? "Pakowanie archiwum…" : "Pobierz cały katalog (ZIP)"}
                  </button>
                ) : null}
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
                  {filesInFolder.length === 0
                    ? "Brak plików w tym katalogu"
                    : "Nic nie pasuje do wyszukiwania ani filtra"}
                </p>
                <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-ink-500 dark:text-paper-500">
                  {filesInFolder.length === 0
                    ? "Wygeneruj materiał w Asystencie (z wybranym katalogiem) albo prześlij plik powyżej."
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
              <>
                <div className="mt-4 flex flex-col gap-3 rounded-xl border border-ink-800/10 bg-paper-50/50 px-3 py-3 dark:border-paper-100/10 dark:bg-ink-950/50 sm:flex-row sm:items-center sm:justify-between">
                  <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-800 dark:text-paper-200">
                    <input
                      ref={selectAllFilteredRef}
                      type="checkbox"
                      checked={allFilteredSelected}
                      onChange={(e) => toggleSelectAllFiltered(e.target.checked)}
                      disabled={busy}
                      className="size-4 rounded border-ink-800/30 text-accent focus:ring-accent/40 dark:border-paper-100/30"
                      aria-label="Zaznacz wszystkie widoczne pliki"
                    />
                    <span>
                      Zaznacz widoczne ({selectedInFilteredCount}/{filteredFiles.length})
                    </span>
                  </label>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    {selectedIdsInFiles.length > 0 && (
                      <span className="text-xs text-ink-500 dark:text-paper-500">
                        Zaznaczono: {selectedIdsInFiles.length} {plikiLabel(selectedIdsInFiles.length)}
                      </span>
                    )}
                    <label className="flex items-center gap-2 text-xs text-ink-600 dark:text-paper-400">
                      <span className="sr-only sm:not-sr-only sm:inline">Do katalogu</span>
                      <select
                        value={bulkMoveTarget}
                        onChange={(e) => setBulkMoveTarget(e.target.value)}
                        disabled={busy || selectedIdsInFiles.length === 0}
                        className={`${inputBase} max-w-[200px] py-2 text-xs`}
                        aria-label="Katalog docelowy dla przeniesienia"
                      >
                        <option value="">Przenieś do…</option>
                        {projectId !== LOOSE_FOLDER_ID && (
                          <option value={LOOSE_FOLDER_ID}>Inne pliki</option>
                        )}
                        {projects
                          .filter((p) => p.id !== projectId)
                          .map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      disabled={
                        busy ||
                        selectedIdsInFiles.length === 0 ||
                        !bulkMoveTarget ||
                        bulkMoveTarget === projectId
                      }
                      onClick={() => void onBulkMoveFiles()}
                      className="rounded-xl border border-accent/50 bg-accent/10 px-4 py-2 text-xs font-semibold text-accent hover:bg-accent/15 disabled:opacity-50 dark:text-accent-muted"
                    >
                      Przenieś
                    </button>
                    <button
                      type="button"
                      disabled={busy || selectedIdsInFiles.length === 0}
                      onClick={() => void startBulkDeleteFiles()}
                      className="rounded-xl bg-red-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
                    >
                      Usuń zaznaczone
                    </button>
                  </div>
                </div>
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
                        <input
                          type="checkbox"
                          checked={selectedFileIds.has(f.id)}
                          onChange={(e) => toggleFileSelected(f.id, e.target.checked)}
                          disabled={busy}
                          className="mt-3 size-4 shrink-0 rounded border-ink-800/30 text-accent focus:ring-accent/40 dark:border-paper-100/30"
                          aria-label={`Zaznacz plik ${f.name}`}
                        />
                        <FileListFileThumb
                          f={f}
                          materialsAudio={materialsAudio}
                          materialsAudioPlaying={materialsAudioPlaying}
                          materialsAudioLoadingId={materialsAudioLoadingId}
                          onMaterialsAudioClick={onMaterialsAudioClick}
                        />
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
              </>
            )}
          </section>
        </div>
      </section>
      )}

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
              {pending.kind === "files_delete_bulk" && "Potwierdź usunięcie plików"}
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
