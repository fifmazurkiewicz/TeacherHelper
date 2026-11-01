import * as Sentry from "@sentry/react";
import { monitoringOptions } from "./monitoring-options";

export function initMonitoring(): boolean {
  const options = monitoringOptions("teacherhelper-web", {
    enabled: import.meta.env.VITE_SENTRY_ENABLED,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT,
    release: import.meta.env.VITE_SENTRY_RELEASE,
  });
  if (!options) return false;
  try {
    Sentry.init({ ...options, integrations: [Sentry.globalHandlersIntegration(), Sentry.browserApiErrorsIntegration(), Sentry.dedupeIntegration()] });
    return true;
  } catch { return false; }
}
