import { useCallback, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { downloadFileBlob } from "@/lib/api";

export type ChatPreviewAttachment = { id: string; name: string; mime_type: string };

function imageKind(mime: string, name: string): boolean {
  const m = mime.toLowerCase();
  if (m.startsWith("image/")) return true;
  const n = name.toLowerCase();
  return [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].some((e) => n.endsWith(e));
}

function audioKind(mime: string, name: string): boolean {
  const m = mime.toLowerCase();
  if (m.startsWith("audio/")) return true;
  return /\.(wav|mp3|m4a|ogg|flac|aac|opus|webm)$/i.test(name);
}

function previewKind(a: ChatPreviewAttachment): "image" | "audio" | null {
  if (imageKind(a.mime_type, a.name)) return "image";
  if (audioKind(a.mime_type, a.name)) return "audio";
  return null;
}

export function hasPreviewableAttachments(attachments: ChatPreviewAttachment[] | undefined): boolean {
  if (!attachments?.length) return false;
  return attachments.some((a) => previewKind(a) != null);
}

/** Etykieta formatu do chipa (MP3, WAV, …). */
function audioFormatLabel(name: string, mime: string): string {
  const n = name.toLowerCase();
  const m = mime.toLowerCase();
  if (n.endsWith(".mp3") || m.includes("mpeg")) return "MP3";
  if (n.endsWith(".wav") || m.includes("wav")) return "WAV";
  if (n.endsWith(".m4a") || m.includes("mp4") || m.includes("aac")) return "M4A";
  if (n.endsWith(".ogg") || m.includes("ogg")) return "OGG";
  if (n.endsWith(".flac") || m.includes("flac")) return "FLAC";
  if (n.endsWith(".opus") || m.includes("opus")) return "OPUS";
  if (m.startsWith("audio/")) return m.split("/")[1]?.slice(0, 6).toUpperCase() || "AUDIO";
  return "AUDIO";
}

function IconZoom({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="2" />
      <path
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M15 15l5 5"
      />
    </svg>
  );
}

function IconDownload({ className }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3v9m0 0l-4-4m4 4l4-4M5 20h14"
      />
    </svg>
  );
}

type ImageLightboxProps = {
  url: string;
  name: string;
  onClose: () => void;
};

function ImageLightbox({ url, name, onClose }: ImageLightboxProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Powiększony podgląd: ${name}`}
      onClick={onClose}
    >
      <button
        type="button"
        className="absolute right-4 top-4 rounded-lg border border-white/30 bg-black/50 px-3 py-1.5 text-sm text-white hover:bg-black/70"
        onClick={onClose}
      >
        Zamknij
      </button>
      <img
        src={url}
        alt={name}
        className="max-h-[min(90vh,900px)] max-w-full object-contain shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>,
    document.body,
  );
}

type PreviewRowProps = {
  a: ChatPreviewAttachment;
  kind: "image" | "audio";
  parentOpen: boolean;
  onDownloadFile?: (fileId: string) => void | Promise<void>;
  downloadingId: string | null;
};

/**
 * Pobiera blob dopiero, gdy rodzic `<details>` jest otwarty; URL utrzymuje do odmontowania wiersza.
 */
function PreviewRow({ a, kind, parentOpen, onDownloadFile, downloadingId }: PreviewRowProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "error">("idle");
  const [lightbox, setLightbox] = useState(false);

  useEffect(() => {
    if (!parentOpen) return;
    if (url) return;
    let cancelled = false;
    setPhase("loading");
    (async () => {
      try {
        const { blob } = await downloadFileBlob(a.id);
        if (cancelled) return;
        const u = URL.createObjectURL(blob);
        setUrl(u);
        setPhase("idle");
      } catch {
        if (!cancelled) setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [parentOpen, a.id, url]);

  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );

  const confirmAndDownload = useCallback(() => {
    if (!onDownloadFile) return;
    if (!window.confirm(`Pobrać plik „${a.name}”?`)) return;
    void onDownloadFile(a.id);
  }, [a.id, a.name, onDownloadFile]);

  const downloadDirect = useCallback(() => {
    if (!onDownloadFile) return;
    void onDownloadFile(a.id);
  }, [a.id, onDownloadFile]);

  if (phase === "error") {
    return (
      <div className="text-xs text-ink-500 dark:text-paper-500">
        Nie udało się załadować podglądu: {a.name}
      </div>
    );
  }

  if (parentOpen && (phase === "loading" || !url)) {
    return (
      <div className="text-xs text-ink-500 dark:text-paper-500">Ładowanie podglądu… {a.name}</div>
    );
  }

  if (kind === "audio" && url) {
    const busy = downloadingId === a.id;
    const fmt = audioFormatLabel(a.name, a.mime_type);
    return (
      <div className="min-w-0 max-w-lg rounded-lg border border-ink-800/12 bg-white/60 p-2.5 dark:border-paper-100/12 dark:bg-ink-900/50">
        <div className="mb-2 flex min-w-0 items-start justify-between gap-2">
          <p className="min-w-0 flex-1 truncate text-xs font-medium text-ink-800 dark:text-paper-100" title={a.name}>
            {a.name}
          </p>
          <span className="shrink-0 rounded-md bg-ink-800/8 px-1.5 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide text-ink-500 dark:bg-paper-100/10 dark:text-paper-400">
            {fmt}
          </span>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-3">
          <audio
            className="h-9 min-h-[2.25rem] w-full min-w-0 flex-1 [color-scheme:light] sm:max-w-md dark:[color-scheme:dark]"
            src={url}
            controls
            controlsList="nodownload"
            preload="metadata"
          >
            {a.name}
          </audio>
          {onDownloadFile && (
            <button
              type="button"
              disabled={busy}
              onClick={downloadDirect}
              title={`Zapisz „${a.name}” na dysku`}
              className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border border-accent/45 bg-accent/12 px-3 py-2 text-xs font-semibold text-accent shadow-sm transition-colors hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50 dark:text-accent-muted"
            >
              {busy ? (
                "Pobieranie…"
              ) : (
                <>
                  <IconDownload className="h-4 w-4 shrink-0" />
                  Pobierz utwór
                </>
              )}
            </button>
          )}
        </div>
        {onDownloadFile && (
          <p className="mt-1.5 text-[0.65rem] leading-snug text-ink-500 dark:text-paper-500">
            Najpierw odsłuch w przeglądarce, albo zapisz plik — ten sam co w „Moje materiały”.
          </p>
        )}
      </div>
    );
  }

  if (kind === "image" && url) {
    return (
      <div className="min-w-0 max-w-sm">
        <p className="mb-1 truncate text-xs text-ink-500 dark:text-paper-400" title={a.name}>
          {a.name}
        </p>
        <div className="group relative inline-block max-w-full">
          <img
            src={url}
            alt={a.name}
            className="max-h-64 max-w-full rounded-lg border border-ink-800/15 object-contain dark:border-paper-100/15"
          />
          {onDownloadFile && (
            <div
              className="absolute right-1.5 top-1.5 flex gap-1 opacity-100 transition-opacity md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-ink-900/75 text-paper-50 shadow-md backdrop-blur-sm hover:bg-ink-900/90 dark:bg-black/60 dark:hover:bg-black/80"
                title="Powiększ podgląd"
                aria-label="Powiększ obraz"
                onClick={() => setLightbox(true)}
              >
                <IconZoom className="h-[18px] w-[18px]" />
              </button>
              <button
                type="button"
                disabled={downloadingId === a.id}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-ink-900/75 text-paper-50 shadow-md backdrop-blur-sm hover:bg-ink-900/90 disabled:opacity-50 dark:bg-black/60 dark:hover:bg-black/80"
                title="Pobierz plik"
                aria-label="Pobierz obraz"
                onClick={confirmAndDownload}
              >
                {downloadingId === a.id ? (
                  <span className="text-xs">…</span>
                ) : (
                  <IconDownload className="h-[18px] w-[18px]" />
                )}
              </button>
            </div>
          )}
        </div>
        {lightbox && <ImageLightbox url={url} name={a.name} onClose={() => setLightbox(false)} />}
      </div>
    );
  }

  return null;
}

type Props = {
  attachments: ChatPreviewAttachment[];
  /** Po potwierdzeniu (audio / ikona przy obrazie) — pobranie z biblioteki */
  onDownloadFile?: (fileId: string) => void | Promise<void>;
  /** Wyłącza interakcje podczas trwającego pobierania */
  downloadingId?: string | null;
};

/**
 * Sekcja <details> (domyślnie zwinięta): podgląd audio (wav, mp3, …) i obrazów (jpg, png, …).
 * Audio: karta z odtwarzaczem i wyraźnym przyciskiem **Pobierz utwór** (jeden klik, bez pytania). Obraz: ikony lupy i pobrania.
 */
export function ChatAttachmentPreviews({ attachments, onDownloadFile, downloadingId = null }: Props) {
  const idBase = useId();
  const rows = attachments
    .map((a) => {
      const k = previewKind(a);
      if (!k) return null;
      return { a, kind: k as "image" | "audio" };
    })
    .filter((x): x is { a: ChatPreviewAttachment; kind: "image" | "audio" } => x != null);

  const [open, setOpen] = useState(false);

  const onToggle = useCallback((e: React.SyntheticEvent<HTMLDetailsElement>) => {
    setOpen(e.currentTarget.open);
  }, []);

  if (rows.length === 0) return null;

  return (
    <details
      className="mt-2 rounded-lg border border-ink-800/10 bg-ink-800/[0.03] p-0 dark:border-paper-100/10 dark:bg-paper-100/[0.04]"
      onToggle={onToggle}
    >
      <summary className="cursor-pointer list-none select-none rounded-lg px-2.5 py-2 text-xs font-medium text-ink-600 [list-style:none] hover:bg-ink-800/5 sm:px-3 dark:text-paper-400 dark:hover:bg-paper-100/5 [&::-webkit-details-marker]:hidden">
        <span
          className={`mr-1.5 inline-block text-accent transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▸
        </span>
        Podgląd: audio / obraz ({rows.length}
        {rows.length === 1 ? " plik" : " pliki"}) — kliknij, aby otworzyć
        <span className="sr-only" id={idBase}>
          Sekcja z odtwarzaczem audio i miniaturkami obrazów; można ją zwinąć, by nie zaśmiecać widoku
        </span>
      </summary>
      <div
        className="space-y-4 border-t border-ink-800/10 px-2.5 pb-3 pt-2 sm:px-3 dark:border-paper-100/10"
        role="region"
        aria-describedby={idBase}
      >
        {rows.map(({ a, kind }) => (
          <PreviewRow
            key={a.id}
            a={a}
            kind={kind}
            parentOpen={open}
            onDownloadFile={onDownloadFile}
            downloadingId={downloadingId}
          />
        ))}
      </div>
    </details>
  );
}
