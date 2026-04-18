import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  createConversation,
  createProjectConfirmed,
  deleteConversation,
  deleteProjectConfirmed,
  downloadFileBlob,
  listConversationMessages,
  listConversations,
  patchConversation,
  setToken,
  type ApiChatMessage,
  type ApiConversation,
  type ApiFile,
  type PendingProjectAction,
} from "@/lib/api";

type ChatAttachment = { id: string; name: string; mime_type: string };

type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  text: string;
  attachments?: ChatAttachment[];
};

type ChatResponse = {
  reply: string;
  conversation_id: string;
  created_file_ids: string[];
  run_modules: string[];
  created_files?: ChatAttachment[];
  needs_clarification: boolean;
  clarification_question: string | null;
  linked_project_id: string | null;
  pending_project_creation?: PendingProjectAction | null;
  pending_project_deletion?: PendingProjectAction | null;
};

function mapStoredMessages(rows: ApiChatMessage[]): ChatMessage[] {
  return rows
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => {
      const extra = (m as ApiChatMessage & { extra?: { created_files?: ChatAttachment[] } | null }).extra;
      return {
        id: (m as ApiChatMessage & { id?: string }).id,
        role: m.role as "user" | "assistant",
        text: m.content,
        attachments: extra?.created_files,
      };
    });
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

export default function AssistantPage() {
  const navigate = useNavigate();
  const [isAdmin, setIsAdmin] = useState(false);
  const [conversations, setConversations] = useState<ApiConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [files, setFiles] = useState<ApiFile[]>([]);
  const [attached, setAttached] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [pendingProjectCreate, setPendingProjectCreate] = useState<PendingProjectAction | null>(null);
  const [pendingProjectDelete, setPendingProjectDelete] = useState<PendingProjectAction | null>(null);
  const [projectConfirmBusy, setProjectConfirmBusy] = useState(false);

  const loadConversations = useCallback(async () => {
    const list = await listConversations();
    setConversations(list);
  }, []);

  const loadFiles = useCallback(async () => {
    const list = await api<ApiFile[]>("/v1/files");
    setFiles(list);
  }, []);

  useEffect(() => {
    api<{ role: string }>("/v1/auth/me")
      .then((m) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  useEffect(() => {
    loadConversations().catch(() => setError("Nie udało się wczytać rozmów"));
  }, [loadConversations]);

  useEffect(() => {
    loadFiles().catch(() => setError("Nie udało się wczytać plików"));
  }, [loadFiles]);

  async function openConversation(id: string) {
    setError(null);
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
      setAttached(new Set());
      await loadConversations();
    } catch {
      setError("Nie udało się utworzyć rozmowy (POST /v1/conversations)");
      setConversationId(null);
      setMessages([]);
      setAttached(new Set());
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
      await patchConversation(renamingId, t);
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
        setAttached(new Set());
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

  async function send() {
    const text = message.trim();
    if (!text || loading) return;
    setError(null);
    setPendingProjectCreate(null);
    setPendingProjectDelete(null);
    setBusyLabel(assistantBusyLabel(text));
    setLoading(true);
    setMessage("");
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.text,
      }));
      const body: {
        message: string;
        conversation_id?: string;
        attached_file_ids?: string[];
        history?: { role: string; content: string }[];
      } = { message: text, history: historyPayload };
      if (conversationId) body.conversation_id = conversationId;
      const ids = [...attached];
      if (ids.length) body.attached_file_ids = ids;
      const res = await api<ChatResponse>("/v1/chat", { method: "POST", json: body });
      let out = res.reply;
      if (res.needs_clarification && res.clarification_question) {
        out += `\n\n(${res.clarification_question})`;
      }
      const attachments =
        res.created_files && res.created_files.length > 0 ? res.created_files : undefined;
      setMessages((m) => [...m, { role: "assistant", text: out, attachments }]);
      setConversationId(res.conversation_id);
      if (res.pending_project_creation) setPendingProjectCreate(res.pending_project_creation);
      if (res.pending_project_deletion) setPendingProjectDelete(res.pending_project_deletion);
      await loadConversations();
      if (res.created_file_ids.length) await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd czatu");
      setMessages((m) => m.slice(0, -1));
      setMessage(text);
    } finally {
      setLoading(false);
      setBusyLabel(null);
    }
  }

  function toggleAttach(id: string) {
    setAttached((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function logout() {
    setToken(null);
    navigate("/login");
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-ink-800/15 px-3 dark:border-paper-100/10">
        <span className="font-semibold text-accent">Teacher Helper</span>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Link
            to="/topics"
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Omówienie tematu
          </Link>
          <Link
            to="/materials"
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Materiały
          </Link>
          <Link
            to="/intent"
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Analiza intencji
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
        <aside className="flex w-[260px] shrink-0 flex-col border-r border-ink-800/15 bg-white dark:border-paper-100/10 dark:bg-ink-900">
          <div className="p-2">
            <button
              type="button"
              onClick={() => void startNewChat()}
              disabled={loadingThread}
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
                      className="min-w-0 flex-1 truncate px-2 py-2 text-left text-sm text-ink-800 dark:text-paper-200"
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

        <section className="flex min-w-0 flex-1 flex-col bg-paper-50 dark:bg-ink-950">
          <div className="border-b border-ink-800/10 px-4 py-2 dark:border-paper-100/10">
            <button
              type="button"
              onClick={() => setFilesOpen((o) => !o)}
              className="text-sm font-medium text-ink-700 dark:text-paper-300"
            >
              {filesOpen ? "▼" : "▶"} Pliki z biblioteki (kontekst)
            </button>
            {filesOpen && (
              <div className="mt-2 max-h-36 overflow-y-auto text-sm">
                {files.length === 0 ? (
                  <p className="text-ink-500">Brak plików — dodaj w „Moje materiały”.</p>
                ) : (
                  <ul className="space-y-1">
                    {files.map((f) => (
                      <li key={f.id} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={attached.has(f.id)}
                          onChange={() => toggleAttach(f.id)}
                          id={`f-${f.id}`}
                        />
                        <label htmlFor={`f-${f.id}`} className="cursor-pointer truncate">
                          {f.name}{" "}
                          <span className="text-ink-500">({f.category})</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {loadingThread && (
              <p className="text-sm text-ink-500">Wczytywanie rozmowy…</p>
            )}
            {!loadingThread && messages.length === 0 && (
              <p className="text-sm text-ink-500">
                Zacznij rozmowę — materiały mogę zapisać w projekcie, gdy poprosisz o „folder” lub eksport PDF.
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
                  {msg.role === "assistant" && msg.attachments && msg.attachments.length > 0 && (
                    <div className="mt-3 border-t border-ink-800/10 pt-3 dark:border-paper-100/10">
                      <p className="mb-2 text-xs font-medium text-ink-600 dark:text-paper-400">Pobierz plik</p>
                      <div className="flex flex-wrap gap-2">
                        {msg.attachments.map((a) => {
                          const audio = a.mime_type.startsWith("audio/");
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
            {!loadingThread && loading && busyLabel && (
              <div
                className="mr-8 flex gap-3 rounded-xl border border-accent/25 bg-accent/5 px-3 py-3 text-sm text-ink-800 dark:border-accent/30 dark:bg-accent/10 dark:text-paper-100"
                aria-live="polite"
              >
                <Spinner className="mt-0.5" />
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-accent dark:text-accent">
                    Asystent
                  </span>
                  <p className="mt-1 font-medium leading-snug">{busyLabel}</p>
                  <p className="mt-1 text-xs text-ink-500 dark:text-paper-400">
                    To może potrwać ok. minuty przy generowaniu materiałów.
                  </p>
                </div>
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
                      disabled={projectConfirmBusy}
                      onClick={() => {
                        void (async () => {
                          setError(null);
                          setProjectConfirmBusy(true);
                          try {
                            await createProjectConfirmed(pendingProjectCreate.confirmation_token);
                            setPendingProjectCreate(null);
                            await loadFiles();
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
                            await loadFiles();
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

          <div className="shrink-0 border-t border-ink-800/10 p-3 dark:border-paper-100/10">
            <div className="mx-auto flex max-w-3xl gap-2">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={2}
                placeholder="Napisz wiadomość…"
                disabled={loadingThread || loading}
                className="flex-1 resize-none rounded-xl border border-ink-800/20 bg-white px-3 py-2 text-sm dark:border-paper-100/20 dark:bg-ink-900"
              />
              <button
                type="button"
                onClick={() => void send()}
                disabled={loading || loadingThread}
                className="flex min-w-[7.5rem] shrink-0 items-center justify-center gap-2 self-end rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dim disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <Spinner className="size-3.5 border-2 border-white/40 border-t-white" />
                    <span>Pracuję…</span>
                  </>
                ) : (
                  "Wyślij"
                )}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
