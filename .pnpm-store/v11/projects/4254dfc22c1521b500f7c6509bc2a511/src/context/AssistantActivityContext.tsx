import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { PendingProjectAction } from "@/lib/api";

/** Odpowiedź POST /v1/chat — spójna z backendem i AssistantPage. */
export type AssistantChatResponse = {
  reply: string;
  conversation_id: string;
  created_file_ids: string[];
  run_modules: string[];
  created_files?: { id: string; name: string; mime_type: string }[];
  needs_clarification: boolean;
  clarification_question: string | null;
  linked_project_id: string | null;
  pending_project_creation?: PendingProjectAction | null;
  pending_project_deletion?: PendingProjectAction | null;
};

export type AssistantChatPending = {
  label: string;
  conversationId: string | null;
  userPreview: string;
};

type AssistantActivityValue = {
  pending: AssistantChatPending | null;
  beginAssistantRequest: (p: AssistantChatPending) => void;
  endAssistantRequest: () => void;
  /** Przerywa fetch czatu (AbortSignal); bezpieczne wywołać z banera lub z widoku asystenta. */
  abortAssistantRequest: () => void;
  /** Sygnał bieżącego POST /v1/chat — wywołać zaraz po beginAssistantRequest w tym samym ticku. */
  getAssistantAbortSignal: () => AbortSignal;
};

const AssistantActivityContext = createContext<AssistantActivityValue | null>(null);

export function AssistantActivityProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<AssistantChatPending | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);

  const beginAssistantRequest = useCallback((p: AssistantChatPending) => {
    chatAbortRef.current?.abort();
    chatAbortRef.current = new AbortController();
    setPending(p);
  }, []);

  const endAssistantRequest = useCallback(() => {
    chatAbortRef.current = null;
    setPending(null);
  }, []);

  const abortAssistantRequest = useCallback(() => {
    chatAbortRef.current?.abort();
  }, []);

  const getAssistantAbortSignal = useCallback(() => {
    const c = chatAbortRef.current;
    if (!c) {
      throw new Error("Brak aktywnego żądania asystenta (AbortController).");
    }
    return c.signal;
  }, []);

  const value = useMemo(
    () => ({
      pending,
      beginAssistantRequest,
      endAssistantRequest,
      abortAssistantRequest,
      getAssistantAbortSignal,
    }),
    [pending, beginAssistantRequest, endAssistantRequest, abortAssistantRequest, getAssistantAbortSignal],
  );

  return (
    <AssistantActivityContext.Provider value={value}>{children}</AssistantActivityContext.Provider>
  );
}

export function useAssistantActivity(): AssistantActivityValue {
  const ctx = useContext(AssistantActivityContext);
  if (!ctx) {
    throw new Error("useAssistantActivity musi być wewnątrz AssistantActivityProvider");
  }
  return ctx;
}
