import { useCallback, useEffect, useState } from "react";
import {
  api,
  createTopic,
  deleteTopic,
  downloadFileBlob,
  getTopic,
  listTopics,
  searchTopicRag,
  uploadFile,
  type ApiFile,
  type ApiTopic,
  type TopicSearchHit,
} from "@/lib/api";

export default function TopicStudioPage() {
  const [topics, setTopics] = useState<ApiTopic[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [files, setFiles] = useState<ApiFile[]>([]);
  const [ragQuery, setRagQuery] = useState("");
  const [ragHits, setRagHits] = useState<TopicSearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topicDetail, setTopicDetail] = useState<ApiTopic | null>(null);

  const selected = topics.find((t) => t.id === selectedId) ?? null;
  const displayTopic = topicDetail ?? selected;

  const refreshTopics = useCallback(async () => {
    const list = await listTopics();
    setTopics(list);
  }, []);

  const refreshFiles = useCallback(async (topicId: string) => {
    const q = `?topic_id=${encodeURIComponent(topicId)}`;
    const list = await api<ApiFile[]>(`/v1/files${q}`);
    setFiles(list);
  }, []);

  useEffect(() => {
    refreshTopics().catch(() => setError("Nie udało się wczytać tematów"));
  }, [refreshTopics]);

  useEffect(() => {
    if (!selectedId) {
      setFiles([]);
      setRagHits(null);
      setTopicDetail(null);
      return;
    }
    refreshFiles(selectedId).catch(() => setError("Nie udało się wczytać plików tematu"));
    setTopicDetail(null);
    getTopic(selectedId)
      .then(setTopicDetail)
      .catch(() => setError("Nie udało się wczytać szczegółów tematu (GET /v1/topics/{id})"));
  }, [selectedId, refreshFiles]);

  async function onCreateTopic(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const t = await createTopic({
        name: newName.trim(),
        description: newDesc.trim() || null,
      });
      setNewName("");
      setNewDesc("");
      await refreshTopics();
      setSelectedId(t.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd tworzenia tematu");
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteTopic(id: string) {
    if (!window.confirm("Usunąć ten temat? (Wymagane: brak przypisanych plików.)")) return;
    setError(null);
    try {
      await deleteTopic(id);
      if (selectedId === id) setSelectedId(null);
      await refreshTopics();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się usunąć tematu");
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !selectedId) return;
    setError(null);
    setBusy(true);
    try {
      await uploadFile(f, { topicId: selectedId });
      await refreshFiles(selectedId);
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

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = ragQuery.trim();
    if (!q || !selectedId) return;
    setError(null);
    setBusy(true);
    setRagHits(null);
    try {
      const hits = await searchTopicRag(selectedId, q);
      setRagHits(hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wyszukiwanie nie powiodło się");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-ink-900 dark:text-paper-100">Omówienie tematu</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
          Zbierz materiały w jednym temacie i przeszukuj je semantycznie (fragmenty z indeksu). To osobna ścieżka od
          Asystenta z narzędziami.
        </p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,280px)_1fr]">
        <div className="space-y-4">
          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-3 font-semibold text-ink-900 dark:text-paper-100">Nowy temat</h2>
            <form onSubmit={onCreateTopic} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-sm">
                Nazwa
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Opis (opcjonalnie)
                <input
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dim disabled:opacity-50"
              >
                Utwórz
              </button>
            </form>
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-3 font-semibold text-ink-900 dark:text-paper-100">Twoje tematy</h2>
            <ul className="space-y-1">
              {topics.map((t) => (
                <li key={t.id}>
                  <div className="flex items-start gap-2 rounded-lg border border-transparent px-2 py-1.5 hover:border-ink-800/10 dark:hover:border-paper-100/10">
                    <button
                      type="button"
                      onClick={() => setSelectedId(t.id)}
                      className={`min-w-0 flex-1 text-left text-sm font-medium ${
                        selectedId === t.id ? "text-accent" : "text-ink-800 dark:text-paper-200"
                      }`}
                    >
                      {t.name}
                    </button>
                    <button
                      type="button"
                      title="Usuń temat"
                      onClick={() => void onDeleteTopic(t.id)}
                      className="shrink-0 text-xs text-red-600 hover:underline dark:text-red-400"
                    >
                      Usuń
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            {topics.length === 0 && (
              <p className="text-sm text-ink-500 dark:text-paper-500">Brak tematów — utwórz pierwszy powyżej.</p>
            )}
          </section>
        </div>

        <div className="space-y-6">
          {!selected && (
            <p className="rounded-xl border border-dashed border-ink-800/25 bg-paper-50 px-4 py-8 text-center text-sm text-ink-600 dark:border-paper-100/15 dark:bg-ink-900/50 dark:text-paper-400">
              Wybierz temat z listy lub utwórz nowy, aby dodawać pliki i wyszukiwać w materiałach.
            </p>
          )}

          {selected && displayTopic && (
            <>
              <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
                <h2 className="text-lg font-semibold text-ink-900 dark:text-paper-100">{displayTopic.name}</h2>
                {displayTopic.description && (
                  <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">{displayTopic.description}</p>
                )}
                <p className="mt-2 font-mono text-xs text-ink-500 dark:text-paper-500">
                  id: {displayTopic.id} · utworzono: {displayTopic.created_at}
                </p>
              </section>

              <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
                <h3 className="mb-3 font-semibold text-ink-900 dark:text-paper-100">Pliki w temacie</h3>
                <label className="inline-flex cursor-pointer items-center rounded-md border border-dashed border-accent/40 bg-accent-muted/30 px-4 py-2 text-sm font-medium text-accent-dim hover:bg-accent-muted/50 dark:border-accent/30 dark:bg-teal-950/40 dark:text-teal-200">
                  {busy ? "Przetwarzanie…" : "Dodaj plik do tematu"}
                  <input type="file" className="hidden" onChange={(e) => void onUpload(e)} disabled={busy} />
                </label>
                <ul className="mt-4 divide-y divide-ink-800/10 dark:divide-paper-100/10">
                  {files.map((f) => (
                    <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                      <span className="font-medium text-ink-900 dark:text-paper-100">{f.name}</span>
                      <button
                        type="button"
                        onClick={() => void onDownload(f.id)}
                        className="text-accent hover:underline"
                      >
                        Pobierz
                      </button>
                    </li>
                  ))}
                </ul>
                {files.length === 0 && (
                  <p className="mt-2 text-sm text-ink-500 dark:text-paper-500">
                    Brak plików — dodaj je przyciskiem powyżej.
                  </p>
                )}
              </section>

              <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
                <h3 className="mb-2 font-semibold text-ink-900 dark:text-paper-100">Szukaj w treści (semantycznie)</h3>
                <p className="mb-3 text-xs text-ink-500 dark:text-paper-500">
                  Zapytanie trafia do indeksu fragmentów przypisanych do tego tematu.
                </p>
                <form onSubmit={runSearch} className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
                    Pytanie
                    <input
                      value={ragQuery}
                      onChange={(e) => setRagQuery(e.target.value)}
                      placeholder="np. Jakie są główne pojęcia w materiale?"
                      className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={busy || !ragQuery.trim()}
                    className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dim disabled:opacity-50"
                  >
                    Szukaj
                  </button>
                </form>

                {ragHits && ragHits.length === 0 && (
                  <p className="mt-4 text-sm text-ink-500 dark:text-paper-500">Brak trafień — spróbuj innego sformułowania.</p>
                )}
                {ragHits && ragHits.length > 0 && (
                  <ul className="mt-4 space-y-3">
                    {ragHits.map((h, i) => (
                      <li
                        key={`${h.file_id}-${h.chunk_index}-${i}`}
                        className="rounded-lg border border-ink-800/10 bg-paper-50 p-3 text-sm dark:border-paper-100/10 dark:bg-ink-950"
                      >
                        <p className="text-xs text-ink-500 dark:text-paper-500">
                          {h.file_name} · fragment {h.chunk_index} · dopasowanie {(h.score * 100).toFixed(1)}%
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-ink-800 dark:text-paper-200">{h.text}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
