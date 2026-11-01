import type { ErrorEvent, EventHint } from "@sentry/react";

type Configuration = {
  enabled?: string;
  dsn?: string;
  environment?: string;
  release?: string;
};

const environments = new Set(["development", "test", "preview", "staging", "production"]);
const errorTypes = new Set(["Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError", "URIError", "EvalError"]);

function codeFile(value: string): string | undefined {
  const filename = value.replace(/^https?:\/\/[^/]+/, "")
    .replace(/^.*\/\.next\/server\//, "/_next/server/")
    .replace(/^app:\/\/\//, "/").split(/[?#]/)[0];
  return !filename.includes("..") && /^\/(?:_next\/(?:static|server)\/[A-Za-z0-9_./-]+\.js|_expo\/static\/js\/(?:web|android|ios)\/[A-Za-z0-9_.-]+\.(?:js|hbc)|assets\/[A-Za-z0-9_./-]+\.js|index(?:\.android)?\.bundle)$/.test(filename) ? filename : undefined;
}

function validDsn(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname.endsWith(".ingest.de.sentry.io") &&
      /^[a-f0-9]{32}$/.test(url.username) && /^\/[0-9]+$/.test(url.pathname) &&
      !url.password && !url.search && !url.hash && (!url.port || url.port === "443");
  } catch {
    return false;
  }
}

/** Reconstruct technical metadata; never copy error messages or request context. */
export function monitoringOptions(component: string, config: Configuration) {
  if (config.enabled !== "true" || !config.dsn || !validDsn(config.dsn)) return undefined;
  const environment = environments.has(config.environment ?? "") ? config.environment : "unknown";
  const release = /^[a-f0-9]{7,40}$/.test(config.release ?? "") ? config.release : undefined;
  return {
    dsn: config.dsn,
    environment,
    release,
    defaultIntegrations: false as const,
    sendClientReports: false,
    maxBreadcrumbs: 0,
    tracesSampleRate: 0,
    traceLifecycle: "static" as const,
    profilesSampleRate: 0,
    tracePropagationTargets: [] as string[],
    dataCollection: {
      userInfo: false, cookies: false, httpHeaders: false, httpBodies: [],
      urlQueryParams: false, stackFrameVariables: false, frameContextLines: 0,
      genAI: { inputs: false, outputs: false }, databaseQueryData: false, queues: false,
    },
    beforeSendLog: () => null,
    beforeSendMetric: () => null,
    beforeSendTransaction: () => null,
    beforeSend(event: ErrorEvent, hint: EventHint): ErrorEvent | null {
      hint.attachments = [];
      if (!(hint.originalException instanceof Error)) return null;
      if (["AbortError", "CanceledError", "CancellationError"].includes(hint.originalException.name)) return null;
      const exception = event.exception?.values?.[0];
      if (!exception) return null;
      const type = errorTypes.has(exception.type ?? "") ? exception.type : "ApplicationError";
      const frames = (exception.stacktrace?.frames ?? []).flatMap((frame) => {
        const filename = codeFile(frame.filename ?? "");
        if (!filename) return [];
        return [{
          filename,
          ...(Number.isSafeInteger(frame.lineno) && (frame.lineno ?? 0) > 0 ? { lineno: frame.lineno } : {}),
          ...(Number.isSafeInteger(frame.colno) && (frame.colno ?? -1) >= 0 ? { colno: frame.colno } : {}),
        }];
      }).slice(-50);
      const images = (event.debug_meta?.images ?? []).flatMap((image) => {
        const filename = codeFile(image.code_file ?? "");
        return image.type === "sourcemap" && filename && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(image.debug_id ?? "")
          ? [{ type: "sourcemap" as const, code_file: filename, debug_id: image.debug_id }] : [];
      });
      return {
        ...(event.event_id && /^[a-f0-9]{32}$/.test(event.event_id) ? { event_id: event.event_id } : {}),
        type: undefined, platform: "javascript", level: "error", environment, ...(release ? { release } : {}),
        tags: { component },
        ...(images.length ? { debug_meta: { images } } : {}),
        exception: { values: [{ type, value: "Application error; private details removed", stacktrace: { frames } }] },
      };
    },
  };
}
