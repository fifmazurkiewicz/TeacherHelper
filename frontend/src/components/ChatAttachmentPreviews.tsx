import { useCallback, useEffect, useId, useState } from "react";
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

type PreviewRowProps = {
  a: ChatPreviewAttachment;
  kind: "image" | "audio";
  parentOpen: boolean;
};

/**
 * Pobiera blob dopiero, gdy rodzic `<details>` jest otwarty; URL utrzymuje do odmontowania wiersza.
 */
function PreviewRow({ a, kind, parentOpen }: PreviewRowProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "error">("idle");

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
    return (
      <div className="min-w-0 max-w-md">
        <p className="mb-1 truncate text-xs text-ink-500 dark:text-paper-400" title={a.name}>
          {a.name}
        </p>
        <audio
          className="h-8 w-full max-w-md"
          src={url}
          controls
          preload="metadata"
        >
          {a.name}
        </audio>
      </div>
    );
  }

  if (kind === "image" && url) {
    return (
      <div className="min-w-0 max-w-sm">
        <p className="mb-1 truncate text-xs text-ink-500 dark:text-paper-400" title={a.name}>
          {a.name}
        </p>
        <img
          src={url}
          alt={a.name}
          className="max-h-64 max-w-full rounded-lg border border-ink-800/15 object-contain dark:border-paper-100/15"
        />
      </div>
    );
  }

  return null;
}

type Props = {
  attachments: ChatPreviewAttachment[];
};

/**
 * Sekcja <details> (domyślnie zwinięta): podgląd audio (wav, mp3, …) i obrazów (jpg, png, …).
 * Pliki wciąż można pobrać osobnymi przyciskami w wątku.
 */
export function ChatAttachmentPreviews({ attachments }: Props) {
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
          <PreviewRow key={a.id} a={a} kind={kind} parentOpen={open} />
        ))}
      </div>
    </details>
  );
}
