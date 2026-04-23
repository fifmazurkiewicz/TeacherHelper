import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  createConversation,
  createProjectConfirmed,
  deleteConversation,
  deleteProjectConfirmed,
  downloadFileBlob,
  ensureConversationFolder,
  listConversationMessages,
  listConversations,
  patchConversation,
  setToken,
  transcribeVoice,
  uploadUserFile,
  type ApiChatMessage,
  type ApiConversation,
  type PendingProjectAction,
} from "@/lib/api";
import {
  useAssistantActivity,
  type AssistantChatResponse,
} from "@/context/AssistantActivityContext";
import { ThemeToggle } from "@/components/ThemeToggle";

type ChatAttachment = { id: string; name: string; mime_type: string };

function coerceMessageExtra(raw: unknown): Record<string, unknown> | undefined {
  if (raw == null) return undefined;
  if (typeof raw === "object" && !Array.isArray(raw)) return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      const p = JSON.parse(raw) as unknown;
      if (p && typeof p === "object" && !Array.isArray(p)) return p as Record<string, unknown>;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

/** Skróty plików zapisanych w turze — z ``extra`` wiadomości z API (odporna na kształt pól). */
function attachmentsFromMessageExtra(
  extra: Record<string, unknown> | null | undefined,
): ChatAttachment[] | undefined {
  if (!extra) return undefined;
  const raw = extra["created_files"];
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const out: ChatAttachment[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const id = o["id"] != null ? String(o["id"]) : "";
    const name = typeof o["name"] === "string" ? o["name"] : "";
    const mime_type = typeof o["mime_type"] === "string" ? o["mime_type"] : "";
    if (!id || !name) continue;
    out.push({ id, name, mime_type });
  }
  return out.length ? out : undefined;
}

function normalizeResponseAttachments(
  files: AssistantChatResponse["created_files"],
): ChatAttachment[] | undefined {
  if (!files?.length) return undefined;
  const out: ChatAttachment[] = [];
  for (const f of files) {
    const id = f.id != null ? String(f.id) : "";
    const name = f.name ?? "";
    if (!id || !name) continue;
    out.push({ id, name, mime_type: f.mime_type ?? "" });
  }
  return out.length ? out : undefined;
}

/** Gdy z GET /messages brak ``created_files``, a POST /v1/chat je zwrócił — dociągnij przyciski „Pobierz”. */
function mergeLastAssistantAttachments(
  messages: ChatMessage[],
  attachments: ChatAttachment[] | undefined,
): ChatMessage[] {
  if (!attachments?.length) return messages;
  let lastAi = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      lastAi = i;
      break;
    }
  }
  if (lastAi < 0) return messages;
  const existing = messages[lastAi].attachments;
  if (existing && existing.length > 0) return messages;
  return messages.map((m, i) => (i === lastAi ? { ...m, attachments } : m));
}

type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  text: string;
  attachments?: ChatAttachment[];
};

/** Zapobiega utracie treści z pola „Napisz wiadomość…” przy nawigacji (np. Asystent → Materiały). */
const ASSISTANT_UI_STORAGE_KEY = "teacher-helper:assistant-ui";

/** Po kliknięciu „Potwierdź utworzenie projektu” — bez tego orchestrator nie dostaje drugiej tury i nie generuje plików. */
const MSG_AFTER_PROJECT_CREATE_CONFIRM =
  "Potwierdzam utworzenie folderu. Katalog jest już powiązany z tą rozmową — kontynuuj i wygeneruj oraz zapisz w bibliotece wszystkie uzgodnione materiały (bez ponownego pytania o folder).";

const SIDEBAR_WIDTH_STORAGE_KEY = "teacher-helper:assistant-sidebar-w";
const SIDEBAR_WIDTH_DEFAULT = 260;
const SIDEBAR_WIDTH_MIN = 168;
const SIDEBAR_WIDTH_MAX = 520;

function readInitialSidebarWidth(): number {
  if (typeof sessionStorage === "undefined") return SIDEBAR_WIDTH_DEFAULT;
  try {
    const v = sessionStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    const n = v ? parseInt(v, 10) : NaN;
    if (Number.isFinite(n) && n >= SIDEBAR_WIDTH_MIN && n <= SIDEBAR_WIDTH_MAX) return n;
  } catch {
    /* ignore */
  }
  return SIDEBAR_WIDTH_DEFAULT;
}

const CHAT_ATTACH_MAX = 10;
const CHAT_UPLOAD_MAX_BYTES = 50 * 1024 * 1024;

const CHAT_FILE_INPUT_ACCEPT =
  ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

type PersistedAssistantUi = {
  draft: string;
  conversationId: string | null;
  attached: ChatAttachment[];
};

function validateChatUploadFile(file: File): string | null {
  const n = file.name.toLowerCase();
  const mime = (file.type || "").toLowerCase();
  const okExt = n.endsWith(".pdf") || n.endsWith(".docx") || n.endsWith(".txt");
  const okMime =
    mime === "application/pdf" ||
    mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    mime === "text/plain";
  if (!okExt && !okMime) {
    return "Dozwolone typy: PDF, DOCX, TXT.";
  }
  if (file.size > CHAT_UPLOAD_MAX_BYTES) {
    return "Maks. rozmiar pliku: 50 MB.";
  }
  return null;
}

function preferredRecordingMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  for (const t of candidates) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

function extensionForAudioBlob(blob: Blob): string {
  const t = (blob.type || "").toLowerCase();
  if (t.includes("webm")) return "webm";
  if (t.includes("mp4") || t.includes("m4a")) return "m4a";
  if (t.includes("ogg")) return "ogg";
  return "webm";
}

function mapStoredMessages(rows: ApiChatMessage[]): ChatMessage[] {
  return rows
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      text: m.content,
      attachments: attachmentsFromMessageExtra(coerceMessageExtra(m.extra)),
    }));
}

/** Krótki opis tego, co prawdopodobnie robi backend — użytkownik widzi to podczas oczekiwania. */
function assistantBusyLabel(userText: string): string {
  const t = userText.toLowerCase();
  if (
    /piosenk|muzyk|nut|suno|chór|refren|melod/.test(t) ||
    (t.includes("piosen") && !t.includes("scenariusz"))
  ) {
    return "Tworzę materiał muzyczny…";
  }
  if (/scenariusz|przedstaw|dramat|teatr|widowisk|dialog/.test(t)) {
    return "Przygotowuję scenariusz…";
  }
  if (/grafik|plakat|ilustracj|obraz|rysun|dall|poster/.test(t)) {
    return "Generuję grafikę…";
  }
  if (/wideo|film|storyboard|kadr/.test(t)) {
    return "Przygotowuję materiał wideo…";
  }
  if (/wiersz|poezj|haiku|rym/.test(t)) {
    return "Piszę wiersz…";
  }
  if (/prezentac|slajd|ppt|powerpoint/.test(t)) {
    return "Tworzę plan prezentacji…";
  }
  if (/pdf|docx|eksport|eksportuj|pobierz plik/.test(t)) {
    return "Przygotowuję eksport pliku…";
  }
  if (/projekt|folder|paczk|zestaw materiał/.test(t)) {
    return "Przygotowuję propozycję projektu lub materiały…";
  }
  if (/bibliotek|szukaj|znajdź|fragment|w plikach|z moich plik/.test(t)) {
    return "Szukam w Twoich materiałach…";
  }
  if (/wyjaśnij|co to|jak to|dlaczego|podaj|wymień|napisz krótko/.test(t) && t.length < 120) {
    return "Formułuję odpowiedź…";
  }
  return "Asystent przetwarza prośbę…";
}

function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Ładowanie"
      className={`inline-block size-4 shrink-0 animate-spin rounded-full border-2 border-accent/30 border-t-accent ${className ?? ""}`}
    />
  );
}

function IconPlusChat({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

function IconMic({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3z" />
      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
    </svg>
  );
}

function IconArrowUp({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 4l-8 8h5v8h6v-8h5l-8-8z" />
    </svg>
  );
}

function normalizePersistedAttachments(raw: unknown): ChatAttachment[] {
  if (!Array.isArray(raw)) return [];
  const out: ChatAttachment[] = [];
  for (const x of raw) {
    if (typeof x === "string" && x) {
      out.push({ id: x, name: "Załącznik", mime_type: "" });
      continue;
    }
    if (x && typeof x === "object" && "id" in x && typeof (x as ChatAttachment).id === "string") {
      const o = x as ChatAttachment;
      out.push({
        id: o.id,
        name: typeof o.name === "string" ? o.name : "Plik",
        mime_type: typeof o.mime_type === "string" ? o.mime_type : "",
      });
    }
  }
  return out;
}

export default function AssistantPage() {
  const navigate = useNavigate();
  const mountedRef = useRef(true);
  const {
    pending: chatPending,
    beginAssistantRequest,
    endAssistantRequest,
    abortAssistantRequest,
    getAssistantAbortSignal,
  } = useAssistantActivity();
  const allowPersistUi = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordChunksRef = useRef<BlobPart[]>([]);
  const recordedMimeRef = useRef<string>("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [conversations, setConversations] = useState<ApiConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatAttachments, setChatAttachments] = useState<ChatAttachment[]>([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [pendingProjectCreate, setPendingProjectCreate] = useState<PendingProjectAction | null>(null);
  const [pendingProjectDelete, setPendingProjectDelete] = useState<PendingProjectAction | null>(null);
  const [projectConfirmBusy, setProjectConfirmBusy] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(readInitialSidebarWidth);
  const sidebarResizeRef = useRef<{
    pointerId: number;
    startX: number;
    startW: number;
  } | null>(null);
  const sidebarWidthCommitRef = useRef(sidebarWidth);

  const loadConversations = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
  }, []);

  const stopMediaTracks = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      stopMediaTracks();
    };
  }, [stopMediaTracks]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    sidebarWidthCommitRef.current = sidebarWidth;
  }, [sidebarWidth]);

  useEffect(() => {
    api<{ role: string }>("/v1/auth/me")
      .then((m: { role: string }) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  useEffect(() => {
    loadConversations().catch(() => setError("Nie udało się wczytać rozmów"));
  }, [loadConversations]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = sessionStorage.getItem(ASSISTANT_UI_STORAGE_KEY);
        if (!raw) return;
        const p = JSON.parse(raw) as Partial<PersistedAssistantUi> & { attached?: unknown };
        if (typeof p.draft === "string") setMessage(p.draft);
        if (p.attached !== undefined) setChatAttachments(normalizePersistedAttachments(p.attached));
        if (p.conversationId && typeof p.conversationId === "string") {
          setError(null);
          setLoadingThread(true);
          setConversationId(p.conversationId);
          try {
            const rows = await listConversationMessages(p.conversationId);
            if (!cancelled) setMessages(mapStoredMessages(rows));
          } catch {
            if (!cancelled) {
              setError("Nie udało się wczytać wiadomości");
              setMessages([]);
            }
          } finally {
            if (!cancelled) setLoadingThread(false);
          }
        }
      } catch {
        /* ignore invalid JSON */
      } finally {
        allowPersistUi.current = true;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!allowPersistUi.current) return;
    try {
      const payload: PersistedAssistantUi = {
        draft: message,
        conversationId,
        attached: chatAttachments,
      };
      sessionStorage.setItem(ASSISTANT_UI_STORAGE_KEY, JSON.stringify(payload));
    } catch {
      /* quota / private mode */
    }
  }, [message, conversationId, chatAttachments]);

  async function openConversation(id: string) {
    setError(null);
    setChatAttachments([]);
    setLoadingThread(true);
    setConversationId(id);
    try {
      const rows = await listConversationMessages(id);
      setMessages(mapStoredMessages(rows));
    } catch {
      setError("Nie udało się wczytać wiadomości");
      setMessages([]);
    } finally {
      setLoadingThread(false);
    }
  }

  async function startNewChat() {
    setError(null);
    setRenamingId(null);
    setLoadingThread(true);
    try {
      const c = await createConversation({});
      setConversationId(c.id);
      setMessages([]);
      setChatAttachments([]);
      await loadConversations();
    } catch {
      setError("Nie udało się utworzyć rozmowy (POST /v1/conversations)");
      setConversationId(null);
      setMessages([]);
      setChatAttachments([]);
    } finally {
      setLoadingThread(false);
    }
  }

  async function saveRename() {
    const t = renameDraft.trim();
    if (!renamingId || t.length < 1) {
      setError("Tytuł musi mieć co najmniej 1 znak.");
      return;
    }
    setError(null);
    try {
      await patchConversation(renamingId, { title: t });
      setRenamingId(null);
      await loadConversations();
    } catch {
      setError("Nie udało się zapisać tytułu");
    }
  }

  async function removeConversation(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!window.confirm("Usunąć tę rozmowę?")) return;
    try {
      await deleteConversation(id);
      if (conversationId === id) {
        setConversationId(null);
        setMessages([]);
        setChatAttachments([]);
        setRenamingId(null);
      }
      await loadConversations();
    } catch {
      setError("Nie udało się usunąć rozmowy");
    }
  }

  async function downloadFromChat(fileId: string) {
    setError(null);
    setDownloadingId(fileId);
    try {
      const { blob, filename } = await downloadFileBlob(fileId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się pobrać pliku");
    } finally {
      setDownloadingId(null);
    }
  }

  async function postChatTurn(args: {
    outgoing: string;
    userBubbleText: string;
    priorMessages: ChatMessage[];
    attachmentsSnapshot: ChatAttachment[];
    /** Przy błędzie przywróć pole wiadomości i załączniki (tylko zwykłe wysyłanie z kompozytora). */
    onErrorRestore?: { messageDraft: string; attachments: ChatAttachment[] };
  }) {
    setError(null);
    setPendingProjectCreate(null);
    setPendingProjectDelete(null);
    const busy = assistantBusyLabel(args.outgoing);
    setBusyLabel(busy);
    setLoading(true);
    beginAssistantRequest({
      label: busy,
      userPreview: args.userBubbleText,
      conversationId,
    });
    const signal = getAssistantAbortSignal();
    setMessages((m) => [
      ...m,
      {
        role: "user",
        text: args.userBubbleText,
        attachments: args.attachmentsSnapshot.length ? args.attachmentsSnapshot : undefined,
      },
    ]);
    try {
      const historyPayload = args.priorMessages.map((m) => ({
        role: m.role,
        content: m.text,
      }));
      const body: {
        message: string;
        conversation_id?: string;
        attached_file_ids?: string[];
        history?: { role: string; content: string }[];
      } = { message: args.outgoing, history: historyPayload };
      if (conversationId) body.conversation_id = conversationId;
      const ids = args.attachmentsSnapshot.map((a) => a.id);
      if (ids.length) body.attached_file_ids = ids;
      const res = await api<AssistantChatResponse>("/v1/chat", {
        method: "POST",
        json: body,
        signal,
      });
      try {
        const raw = sessionStorage.getItem(ASSISTANT_UI_STORAGE_KEY);
        if (raw) {
          const p = JSON.parse(raw) as PersistedAssistantUi;
          p.conversationId = res.conversation_id;
          sessionStorage.setItem(ASSISTANT_UI_STORAGE_KEY, JSON.stringify(p));
        } else {
          sessionStorage.setItem(
            ASSISTANT_UI_STORAGE_KEY,
            JSON.stringify({
              draft: "",
              conversationId: res.conversation_id,
              attached: [],
            } satisfies PersistedAssistantUi),
          );
        }
      } catch {
        /* quota / private mode */
      }
      if (!mountedRef.current) return;
      setConversationId(res.conversation_id);
      try {
        const rows = await listConversationMessages(res.conversation_id, { signal });
        if (!mountedRef.current) return;
        let mapped = mapStoredMessages(rows);
        mapped = mergeLastAssistantAttachments(mapped, normalizeResponseAttachments(res.created_files));
        setMessages(mapped);
      } catch {
        const attachments =
          res.created_files && res.created_files.length > 0 ? res.created_files : undefined;
        setMessages((m) => [...m, { role: "assistant", text: res.reply, attachments }]);
      }
      if (res.pending_project_creation) setPendingProjectCreate(res.pending_project_creation);
      if (res.pending_project_deletion) setPendingProjectDelete(res.pending_project_deletion);
      setChatAttachments([]);
      await loadConversations();
    } catch (e) {
      const aborted =
        (e instanceof DOMException && e.name === "AbortError") ||
        (e instanceof Error && e.name === "AbortError");
      if (aborted) {
        if (mountedRef.current) {
          setError(null);
          setMessages((m) => m.slice(0, -1));
          if (args.onErrorRestore) {
            setMessage(args.onErrorRestore.messageDraft);
            setChatAttachments(args.onErrorRestore.attachments);
          }
        }
      } else if (mountedRef.current) {
        setError(e instanceof Error ? e.message : "Błąd czatu");
        setMessages((m) => m.slice(0, -1));
        if (args.onErrorRestore) {
          setMessage(args.onErrorRestore.messageDraft);
          setChatAttachments(args.onErrorRestore.attachments);
        }
      }
    } finally {
      endAssistantRequest();
      if (mountedRef.current) {
        setLoading(false);
        setBusyLabel(null);
      }
    }
  }

  async function send() {
    const trimmed = message.trim();
    const outgoing =
      trimmed || (chatAttachments.length ? "Uwzględnij załączone pliki w odpowiedzi." : "");
    if (!outgoing || loading || loadingThread || uploadBusy || voiceRecording || voiceBusy || chatPending != null)
      return;
    if (!trimmed && !chatAttachments.length) return;

    const snapshot = [...chatAttachments];
    const userBubbleText = trimmed || "Załączone pliki — proszę o uwzględnienie.";
    const prior = messages;
    setMessage("");
    await postChatTurn({
      outgoing,
      userBubbleText,
      priorMessages: prior,
      attachmentsSnapshot: snapshot,
      onErrorRestore: { messageDraft: trimmed, attachments: snapshot },
    });
  }

  async function addChatFilesFromList(list: FileList | null) {
    if (!list?.length) return;
    if (!conversationId) {
      setError("Utwórz lub wybierz rozmowę, zanim dodasz pliki.");
      return;
    }
    setError(null);
    setUploadBusy(true);
    let count = chatAttachments.length;
    try {
      let projectId: string;
      try {
        const conv = await ensureConversationFolder(conversationId);
        if (!conv.project_id) {
          setError("Nie udało się powiązać katalogu z rozmową.");
          return;
        }
        projectId = conv.project_id;
        setConversations((prev) => prev.map((x) => (x.id === conv.id ? { ...x, ...conv } : x)));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Nie udało się utworzyć katalogu dla tej rozmowy");
        return;
      }
      for (const file of [...list]) {
        const verr = validateChatUploadFile(file);
        if (verr) {
          setError(verr);
          continue;
        }
        if (count >= CHAT_ATTACH_MAX) {
          setError(`Możesz dołączyć maks. ${CHAT_ATTACH_MAX} plików naraz.`);
          break;
        }
        try {
          const row = await uploadUserFile(file, projectId);
          setChatAttachments((prev) => [...prev, { id: row.id, name: row.name, mime_type: row.mime_type }]);
          count += 1;
        } catch (e) {
          setError(e instanceof Error ? e.message : "Nie udało się przesłać pliku");
        }
      }
    } finally {
      setUploadBusy(false);
    }
  }

  async function toggleVoiceInput() {
    if (voiceBusy || loading || loadingThread || uploadBusy || chatPending != null || !conversationId) return;
    if (voiceRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Ta przeglądarka nie obsługuje nagrywania z mikrofonu.");
      return;
    }
    setError(null);
    recordChunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const mime = preferredRecordingMime();
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      recordedMimeRef.current = mr.mimeType || mime || "audio/webm";
      mr.ondataavailable = (ev) => {
        if (ev.data.size > 0) recordChunksRef.current.push(ev.data);
      };
      mr.onstop = async () => {
        stopMediaTracks();
        setVoiceRecording(false);
        mediaRecorderRef.current = null;
        const blob = new Blob(recordChunksRef.current, { type: recordedMimeRef.current || "audio/webm" });
        recordChunksRef.current = [];
        if (blob.size < 200) {
          setError("Nagranie jest za krótkie.");
          return;
        }
        setVoiceBusy(true);
        try {
          const name = `recording.${extensionForAudioBlob(blob)}`;
          const { text } = await transcribeVoice(blob, name);
          setMessage((prev) => {
            const p = prev.trim();
            const next = p ? `${p} ${text}` : text;
            return next.trim();
          });
          requestAnimationFrame(() => {
            const el = composerTextareaRef.current;
            if (el) {
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            }
          });
        } catch (e) {
          setError(e instanceof Error ? e.message : "Nie udało się przetworzyć nagrania");
        } finally {
          setVoiceBusy(false);
        }
      };
      mr.start();
      setVoiceRecording(true);
    } catch {
      setError("Brak dostępu do mikrofonu — sprawdź uprawnienia w przeglądarce.");
      stopMediaTracks();
    }
  }

  function removeChatAttachment(id: string) {
    setChatAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function logout() {
    setToken(null);
    navigate("/login");
  }

  function onSidebarResizePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    e.preventDefault();
    sidebarResizeRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startW: sidebarWidth,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onSidebarResizePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = sidebarResizeRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    const dx = e.clientX - d.startX;
    const next = Math.min(
      SIDEBAR_WIDTH_MAX,
      Math.max(SIDEBAR_WIDTH_MIN, d.startW + dx),
    );
    setSidebarWidth(next);
    sidebarWidthCommitRef.current = next;
  }

  function endSidebarResize(e: React.PointerEvent<HTMLDivElement>) {
    const d = sidebarResizeRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    sidebarResizeRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
    try {
      sessionStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidthCommitRef.current));
    } catch {
      /* quota / private mode */
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-ink-800/15 px-3 dark:border-paper-100/10">
        <span className="font-semibold text-accent">Teacher Helper</span>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Link
            to="/materials"
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Materiały
          </Link>
          <Link
            to="/profile"
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Profil
          </Link>
          {isAdmin && (
            <>
              <Link
                to="/admin/monitoring"
                className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
              >
                Monitoring
              </Link>
              <Link
                to="/admin/users"
                className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
              >
                Użytkownicy
              </Link>
            </>
          )}
          <ThemeToggle className="rounded-md px-2 py-1 text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800" />
          <button
            type="button"
            onClick={logout}
            className="rounded-md px-2 py-1 text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Wyloguj
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          className="flex min-w-0 shrink-0 flex-col border-r border-ink-800/15 bg-white dark:border-paper-100/10 dark:bg-ink-900"
          style={{ width: sidebarWidth }}
        >
          <div className="p-2">
            <button
              type="button"
              onClick={() => void startNewChat()}
              disabled={loadingThread || loading || chatPending != null}
              className="w-full rounded-lg border border-ink-800/20 bg-paper-50 py-2 text-sm font-medium text-ink-900 hover:bg-paper-100 disabled:opacity-50 dark:border-paper-100/20 dark:bg-ink-950 dark:text-paper-100 dark:hover:bg-ink-800"
            >
              Nowy czat
            </button>
          </div>
          <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1 pb-2">
            {conversations.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-0.5 rounded-lg ${
                  conversationId === c.id ? "bg-accent/15" : "hover:bg-paper-100 dark:hover:bg-ink-800"
                }`}
              >
                {renamingId === c.id ? (
                  <div className="flex min-w-0 flex-1 flex-col gap-1 px-1 py-1">
                    <input
                      value={renameDraft}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      className="w-full rounded border border-ink-800/20 bg-white px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      autoFocus
                    />
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => void saveRename()}
                        className="rounded bg-accent px-2 py-0.5 text-xs text-white"
                      >
                        OK
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenamingId(null)}
                        className="rounded border border-ink-800/20 px-2 py-0.5 text-xs dark:border-paper-100/20"
                      >
                        Anuluj
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => void openConversation(c.id)}
                      disabled={loading || chatPending != null}
                      className="min-w-0 flex-1 truncate px-2 py-2 text-left text-sm text-ink-800 disabled:opacity-45 dark:text-paper-200"
                      title={c.title}
                    >
                      {c.title}
                    </button>
                    <button
                      type="button"
                      title="Zmień tytuł"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingId(c.id);
                        setRenameDraft(c.title);
                      }}
                      className="shrink-0 rounded p-1 text-ink-400 opacity-0 hover:bg-paper-100 hover:text-accent group-hover:opacity-100 dark:text-paper-500 dark:hover:bg-ink-800"
                    >
                      Edytuj
                    </button>
                    <button
                      type="button"
                      title="Usuń"
                      onClick={(e) => void removeConversation(c.id, e)}
                      className="shrink-0 rounded p-1 text-ink-400 opacity-0 hover:bg-red-500/10 hover:text-red-600 group-hover:opacity-100 dark:text-paper-500 dark:hover:text-red-400"
                    >
                      ×
                    </button>
                  </>
                )}
              </div>
            ))}
          </nav>
        </aside>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={Math.round(sidebarWidth)}
          aria-valuemin={SIDEBAR_WIDTH_MIN}
          aria-valuemax={SIDEBAR_WIDTH_MAX}
          aria-label="Szerokość panelu czatów — przeciągnij"
          className="group relative w-2 shrink-0 cursor-col-resize select-none touch-none"
          onPointerDown={onSidebarResizePointerDown}
          onPointerMove={onSidebarResizePointerMove}
          onPointerUp={endSidebarResize}
          onPointerCancel={endSidebarResize}
        >
          <div className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ink-800/20 transition-colors group-hover:bg-accent/60 group-active:bg-accent dark:bg-paper-100/12" />
        </div>

        <section className="flex min-w-0 flex-1 flex-col bg-paper-50 dark:bg-ink-950">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {loadingThread && (
              <p className="text-sm text-ink-500">Wczytywanie rozmowy…</p>
            )}
            {!loadingThread && messages.length === 0 && (
              <p className="text-sm text-ink-500">
                Zacznij rozmowę. Mogę oprzeć się na Twoich materiałach w bibliotece oraz na plikach PDF, DOCX lub TXT,
                które dołączysz poniżej.
              </p>
            )}
            {!loadingThread &&
              messages.map((msg, i) => (
                <div
                  key={msg.id ?? `local-${i}`}
                  className={`rounded-xl px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "ml-8 bg-accent/12 text-ink-900 dark:text-paper-100"
                      : "mr-8 border border-ink-800/10 bg-white text-ink-900 dark:border-paper-100/10 dark:bg-ink-900 dark:text-paper-100"
                  }`}
                >
                  <span className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-paper-500">
                    {msg.role === "user" ? "Ty" : "Asystent"}
                  </span>
                  <pre className="mt-1 whitespace-pre-wrap font-sans">{msg.text}</pre>
                  {msg.role === "user" && msg.attachments && msg.attachments.length > 0 && (
                    <ul className="mt-2 list-inside list-disc text-xs text-ink-600 dark:text-paper-400">
                      {msg.attachments.map((a) => (
                        <li key={a.id}>{a.name}</li>
                      ))}
                    </ul>
                  )}
                  {msg.role === "assistant" && msg.attachments && msg.attachments.length > 0 && (
                    <div className="mt-3 border-t border-ink-800/10 pt-3 dark:border-paper-100/10">
                      <p className="mb-2 text-xs font-medium text-ink-600 dark:text-paper-400">Pobierz plik</p>
                      <div className="flex flex-wrap gap-2">
                        {msg.attachments.map((a) => {
                          const audio = (a.mime_type || "").startsWith("audio/");
                          const label = audio ? "Pobierz MP3 / audio" : "Pobierz";
                          return (
                            <button
                              key={a.id}
                              type="button"
                              disabled={downloadingId === a.id}
                              onClick={() => void downloadFromChat(a.id)}
                              className="rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/15 disabled:opacity-50 dark:text-accent-muted"
                              title={a.name}
                            >
                              {downloadingId === a.id ? "…" : `${label}: ${a.name.length > 36 ? `${a.name.slice(0, 34)}…` : a.name}`}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            {!loadingThread && (loading || chatPending != null) && (
              <div
                className="mr-8 flex gap-3 rounded-xl border border-accent/25 bg-accent/5 px-3 py-3 text-sm text-ink-800 dark:border-accent/30 dark:bg-accent/10 dark:text-paper-100"
                aria-live="polite"
              >
                <Spinner className="mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <span className="text-xs font-semibold uppercase tracking-wide text-accent dark:text-accent">
                    Asystent
                  </span>
                  <p className="mt-1 font-medium leading-snug">
                    {chatPending?.label ?? busyLabel ?? "Asystent przetwarza prośbę…"}
                  </p>
                  <p className="mt-1 text-xs text-ink-500 dark:text-paper-400">
                    {chatPending && !loading
                      ? "Nadal czekamy na odpowiedź z serwera — możesz zostać tutaj lub wrócić za chwilę; w „Materiały” też widać pasek postępu."
                      : "To może potrwać ok. minuty przy generowaniu materiałów."}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => abortAssistantRequest()}
                  className="shrink-0 self-start rounded-lg border border-ink-800/20 bg-white px-2.5 py-1.5 text-xs font-medium text-ink-800 hover:bg-paper-100 dark:border-paper-100/20 dark:bg-ink-900 dark:text-paper-100 dark:hover:bg-ink-800"
                >
                  Przerwij
                </button>
              </div>
            )}
          </div>

          {(pendingProjectCreate || pendingProjectDelete) && (
            <div className="shrink-0 space-y-2 border-t border-ink-800/10 px-4 py-3 dark:border-paper-100/10">
              {pendingProjectCreate && (
                <div
                  className="rounded-xl border border-accent/30 bg-accent/5 px-3 py-3 text-sm text-ink-800 dark:border-accent/40 dark:bg-accent/10 dark:text-paper-100"
                  role="status"
                >
                  <p className="font-medium text-accent dark:text-accent-muted">{pendingProjectCreate.summary}</p>
                  {pendingProjectCreate.description ? (
                    <p className="mt-1 text-xs text-ink-600 dark:text-paper-400">{pendingProjectCreate.description}</p>
                  ) : null}
                  <p className="mt-1 text-xs text-ink-500 dark:text-paper-500">
                    Token ważny ok. {Math.round(pendingProjectCreate.expires_in_seconds / 60)} min — potwierdź tutaj lub
                    w „Moje materiały”.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={projectConfirmBusy || loading || chatPending != null || loadingThread}
                      onClick={() => {
                        void (async () => {
                          setError(null);
                          setProjectConfirmBusy(true);
                          try {
                            const prior = messagesRef.current;
                            const proj = await createProjectConfirmed(
                              pendingProjectCreate.confirmation_token,
                            );
                            setPendingProjectCreate(null);
                            if (conversationId) {
                              const conv = await patchConversation(conversationId, {
                                project_id: proj.id,
                              });
                              setConversations((prev) =>
                                prev.map((x) => (x.id === conv.id ? { ...x, ...conv } : x)),
                              );
                              await postChatTurn({
                                outgoing: MSG_AFTER_PROJECT_CREATE_CONFIRM,
                                userBubbleText: MSG_AFTER_PROJECT_CREATE_CONFIRM,
                                priorMessages: prior,
                                attachmentsSnapshot: [],
                              });
                            }
                          } catch (e) {
                            setError(e instanceof Error ? e.message : "Nie udało się utworzyć projektu");
                          } finally {
                            setProjectConfirmBusy(false);
                          }
                        })();
                      }}
                      className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-dim disabled:opacity-50"
                    >
                      {projectConfirmBusy ? "…" : "Potwierdź utworzenie projektu"}
                    </button>
                    <button
                      type="button"
                      disabled={projectConfirmBusy}
                      onClick={() => setPendingProjectCreate(null)}
                      className="rounded-lg border border-ink-800/25 px-3 py-1.5 text-xs dark:border-paper-100/20"
                    >
                      Odrzuć
                    </button>
                  </div>
                </div>
              )}
              {pendingProjectDelete && pendingProjectDelete.project_id && (
                <div
                  className="rounded-xl border border-red-500/30 bg-red-500/5 px-3 py-3 text-sm text-ink-800 dark:text-paper-100"
                  role="status"
                >
                  <p className="font-medium text-red-700 dark:text-red-400">{pendingProjectDelete.summary}</p>
                  <p className="mt-1 text-xs text-ink-500 dark:text-paper-500">
                    Token ważny ok. {Math.round(pendingProjectDelete.expires_in_seconds / 60)} min.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={projectConfirmBusy}
                      onClick={() => {
                        void (async () => {
                          setError(null);
                          setProjectConfirmBusy(true);
                          try {
                            await deleteProjectConfirmed(
                              pendingProjectDelete.project_id as string,
                              pendingProjectDelete.confirmation_token,
                            );
                            setPendingProjectDelete(null);
                          } catch (e) {
                            setError(e instanceof Error ? e.message : "Nie udało się usunąć projektu");
                          } finally {
                            setProjectConfirmBusy(false);
                          }
                        })();
                      }}
                      className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      {projectConfirmBusy ? "…" : "Potwierdź usunięcie projektu"}
                    </button>
                    <button
                      type="button"
                      disabled={projectConfirmBusy}
                      onClick={() => setPendingProjectDelete(null)}
                      className="rounded-lg border border-ink-800/25 px-3 py-1.5 text-xs dark:border-paper-100/20"
                    >
                      Anuluj
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {error && (
            <p className="shrink-0 px-4 text-sm text-red-600 dark:text-red-400">{error}</p>
          )}

          <div className="shrink-0 border-t border-ink-800/10 bg-paper-50/90 px-3 pb-3 pt-2 dark:border-paper-100/10 dark:bg-ink-950/90">
            <input
              ref={fileInputRef}
              type="file"
              accept={CHAT_FILE_INPUT_ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => {
                void addChatFilesFromList(e.target.files);
                e.target.value = "";
              }}
            />
            <div className="mx-auto mb-2 max-w-3xl space-y-2">
              {chatAttachments.length > 0 && (
                <ul className="flex flex-wrap gap-2 text-xs">
                  {chatAttachments.map((a) => (
                    <li
                      key={a.id}
                      className="flex max-w-full items-center gap-1 rounded-full border border-ink-800/20 bg-white px-2 py-1 dark:border-paper-100/15 dark:bg-ink-900"
                    >
                      <span className="truncate" title={a.name}>
                        {a.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeChatAttachment(a.id)}
                        disabled={loading || chatPending != null || uploadBusy || voiceRecording || voiceBusy}
                        className="shrink-0 rounded px-1 text-ink-500 hover:bg-red-500/10 hover:text-red-600 disabled:opacity-40 dark:text-paper-400"
                        aria-label={`Usuń ${a.name}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="mx-auto max-w-3xl">
              <div className="flex min-h-[52px] items-end gap-0.5 rounded-[28px] border border-ink-800/15 bg-white px-1.5 py-1.5 shadow-sm dark:border-paper-100/12 dark:bg-ink-900">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={
                    loadingThread || loading || chatPending != null || uploadBusy || !conversationId || voiceRecording || voiceBusy
                  }
                  title={`Załącz plik PDF, DOCX lub TXT (do ${CHAT_ATTACH_MAX}, max 50 MB — folder tej rozmowy w Materiałach).`}
                  aria-label="Załącz plik"
                  className="flex size-9 shrink-0 items-center justify-center rounded-full text-ink-700 hover:bg-paper-100 disabled:opacity-40 dark:text-paper-200 dark:hover:bg-ink-800"
                >
                  {uploadBusy ? <Spinner className="size-[18px]" /> : <IconPlusChat className="size-5" />}
                </button>
                <textarea
                  ref={composerTextareaRef}
                  value={message}
                  onChange={(e) => {
                    setMessage(e.target.value);
                    const el = e.target;
                    el.style.height = "auto";
                    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  rows={1}
                  placeholder="Wiadomość…"
                  disabled={loadingThread || loading || chatPending != null || uploadBusy || voiceRecording || voiceBusy}
                  className="min-h-[40px] max-h-[200px] w-0 min-w-0 flex-1 resize-none border-0 bg-transparent px-1 py-2 text-sm text-ink-900 outline-none ring-0 placeholder:text-ink-400 focus:ring-0 dark:text-paper-100 dark:placeholder:text-paper-500"
                />
                <button
                  type="button"
                  onClick={() => void toggleVoiceInput()}
                  disabled={loadingThread || loading || chatPending != null || uploadBusy || !conversationId || voiceBusy}
                  title={
                    voiceRecording
                      ? "Kliknij, by zakończyć nagranie i przetworzyć mowę (xAI / Grok STT)"
                      : "Mów do mikrofonu — kliknij, by zacząć; kliknij ponownie, by wysłać nagranie do transkrypcji"
                  }
                  aria-label={voiceRecording ? "Zatrzymaj nagrywanie" : "Nagraj wiadomość głosową"}
                  className={`flex size-9 shrink-0 items-center justify-center rounded-full disabled:opacity-40 ${
                    voiceRecording
                      ? "bg-red-500/20 text-red-600 dark:bg-red-500/25 dark:text-red-400"
                      : "text-ink-700 hover:bg-paper-100 dark:text-paper-200 dark:hover:bg-ink-800"
                  }`}
                >
                  {voiceBusy ? <Spinner className="size-[18px]" /> : <IconMic className="size-5" />}
                </button>
                <button
                  type="button"
                  onClick={() => void send()}
                  disabled={
                    loading ||
                    chatPending != null ||
                    loadingThread ||
                    uploadBusy ||
                    voiceRecording ||
                    voiceBusy ||
                    (!message.trim() && chatAttachments.length === 0)
                  }
                  title="Wyślij"
                  aria-label="Wyślij wiadomość"
                  className={`mb-0.5 flex size-9 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-35 ${
                    message.trim() || chatAttachments.length > 0
                      ? "bg-accent text-white hover:bg-accent-dim"
                      : "bg-ink-200 text-ink-500 dark:bg-ink-700 dark:text-paper-400"
                  }`}
                >
                  {loading || chatPending != null ? (
                    <Spinner className="size-[18px] border-2 border-white/40 border-t-white" />
                  ) : (
                    <IconArrowUp className="size-5" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
