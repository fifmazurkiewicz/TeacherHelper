import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ACCOUNT_PENDING_EVENT, api, getToken, type AuthMe } from "@/lib/api";
import { AssistantActivityProvider } from "@/context/AssistantActivityContext";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";
import { useChatShell } from "@/hooks/useChatShell";
import PendingApprovalPage from "@/pages/PendingApprovalPage";
import { AssistantBackgroundChatBanner } from "./AssistantBackgroundChatBanner";
import { Nav } from "./Nav";

type AuthState = "loading" | "authenticated" | "unauthenticated";

export function ProtectedLayout() {
  const { pathname } = useLocation();
  const chatLayout = pathname === "/assistant";
  const adminLayout = pathname.startsWith("/admin");
  useChatShell(chatLayout);
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [approval, setApproval] = useState<"unknown" | "pending" | "approved">("unknown");
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const refreshMe = useCallback(async (manual = false) => {
    if (manual) setChecking(true);
    try {
      const me = await api<AuthMe>("/v1/auth/me");
      setApproval(me.is_approved ? "approved" : "pending");
      setApprovalError(null);
    } catch {
      setApproval((prev) => (prev === "approved" ? "approved" : "pending"));
      setApprovalError("Nie udało się sprawdzić statusu konta. Spróbuj ponownie.");
    } finally {
      if (manual) setChecking(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function checkLegacyAuth() {
      if (cancelled) return;
      setAuthState(getToken() ? "authenticated" : "unauthenticated");
    }

    if (isSupabaseConfigured && supabase) {
      void supabase.auth.getSession().then(({ data }) => {
        if (cancelled) return;
        setAuthState(data.session ? "authenticated" : "unauthenticated");
      });

      const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
        if (cancelled) return;
        setAuthState(session ? "authenticated" : "unauthenticated");
      });

      return () => {
        cancelled = true;
        subscription.subscription.unsubscribe();
      };
    }

    void checkLegacyAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (authState !== "authenticated") {
      setApproval("unknown");
      setApprovalError(null);
      return;
    }
    void refreshMe(false);
    const poll = window.setInterval(() => {
      void refreshMe(false);
    }, 15_000);
    const onPending = () => setApproval("pending");
    window.addEventListener(ACCOUNT_PENDING_EVENT, onPending);
    return () => {
      window.clearInterval(poll);
      window.removeEventListener(ACCOUNT_PENDING_EVENT, onPending);
    };
  }, [authState, refreshMe]);

  if (authState === "loading" || (authState === "authenticated" && approval === "unknown")) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper-50 text-sm text-ink-600 dark:bg-ink-950 dark:text-paper-400">
        Ładowanie sesji…
      </div>
    );
  }

  if (authState === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  if (approval === "pending") {
    return <PendingApprovalPage checking={checking} error={approvalError} onCheckStatus={() => void refreshMe(true)} />;
  }

  return (
    <AssistantActivityProvider>
      {chatLayout ? (
        <div className="chat-app-shell flex min-h-0 flex-col overflow-hidden bg-paper-50 dark:bg-ink-950">
          <Nav />
          <div className="flex min-h-0 flex-1 flex-col">
            <Outlet />
          </div>
        </div>
      ) : (
        <>
          <AssistantBackgroundChatBanner />
          <Nav />
          <main
            className={`mx-auto w-full px-3 py-6 sm:px-4 sm:py-8 ${
              adminLayout ? "max-w-7xl" : "max-w-5xl"
            }`}
          >
            <Outlet />
          </main>
        </>
      )}
    </AssistantActivityProvider>
  );
}
