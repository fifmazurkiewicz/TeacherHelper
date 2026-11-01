import { ErrorBoundary } from "@sentry/react";
import { initMonitoring } from "./lib/monitoring";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ApiPulseBanner } from "./components/ApiPulseBanner";
import { ApiPulseProvider } from "./components/ApiPulseProvider";
import { initThemeFromStorage } from "./lib/theme";
import App from "./App";
import "./globals.css";

initMonitoring();

initThemeFromStorage();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ApiPulseProvider>
      <ApiPulseBanner />
      <BrowserRouter>
        <ErrorBoundary fallback={<p role="alert">Wystąpił błąd aplikacji. Odśwież stronę.</p>}><App /></ErrorBoundary>
      </BrowserRouter>
    </ApiPulseProvider>
  </StrictMode>,
);
