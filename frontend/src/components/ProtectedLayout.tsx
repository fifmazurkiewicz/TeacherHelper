import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { getToken } from "@/lib/api";
import { AssistantActivityProvider } from "@/context/AssistantActivityContext";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";
import { useChatShell } from "@/hooks/useChatShell";
import { AssistantBackgroundChatBanner } from "./AssistantBackgroundChatBanner";
import { Nav } from "./Nav";

type AuthState = "loading" | "authenticated" | "unauthenticated";

export function ProtectedLayout() {
  const { pathname } = useLocation();
  const chatLayout = pathname === "/assistant";
  useChatShell(chatLayout);
  const [authState, setAuthState] = useState<AuthState>("loading");

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

  if (authState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper-50 text-sm text-ink-600 dark:bg-ink-950 dark:text-paper-400">
        Ładowanie sesji…
      </div>
    );
  }

  if (authState === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return (
    <AssistantActivityProvider>
      {chatLayout ? (
        <div className="chat-app-shell flex min-h-0 flex-col overflow-hidden bg-paper-50 dark:bg-ink-950">
          <Outlet />
        </div>
      ) : (
        <>
          <AssistantBackgroundChatBanner />
          <Nav />
          <main className="mx-auto max-w-5xl px-3 py-6 sm:px-4 sm:py-8">
            <Outlet />
          </main>
        </>
      )}
    </AssistantActivityProvider>
  );
}
