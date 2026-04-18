import { Navigate, Outlet, useLocation } from "react-router-dom";
import { getToken } from "@/lib/api";
import { Nav } from "./Nav";

export function ProtectedLayout() {
  const { pathname } = useLocation();
  const chatLayout = pathname === "/assistant";

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  if (chatLayout) {
    return (
      <div className="flex h-screen flex-col overflow-hidden bg-paper-50 dark:bg-ink-950">
        <Outlet />
      </div>
    );
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </>
  );
}
