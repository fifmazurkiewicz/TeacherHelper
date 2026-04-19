import { Navigate, Outlet, useLocation } from "react-router-dom";
import { getToken } from "@/lib/api";
import { AssistantActivityProvider } from "@/context/AssistantActivityContext";
import { AssistantBackgroundChatBanner } from "./AssistantBackgroundChatBanner";
import { Nav } from "./Nav";

export function ProtectedLayout() {
  const { pathname } = useLocation();
  const chatLayout = pathname === "/assistant";

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AssistantActivityProvider>
      {chatLayout ? (
        <div className="flex h-screen flex-col overflow-hidden bg-paper-50 dark:bg-ink-950">
          <Outlet />
        </div>
      ) : (
        <>
          <AssistantBackgroundChatBanner />
          <Nav />
          <main className="mx-auto max-w-5xl px-4 py-8">
            <Outlet />
          </main>
        </>
      )}
    </AssistantActivityProvider>
  );
}
