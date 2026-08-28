import { getApiBase } from "@/lib/api";

const PROBE_TIMEOUT_MS = 8000;

export type ApiPulseProbeResult = {
  ok: boolean;
  status?: string;
  service?: string;
};

export async function probeApiHealth(signal?: AbortSignal): Promise<ApiPulseProbeResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  try {
    const res = await fetch(`${getApiBase()}/api/health`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json()) as { status?: string; service?: string };
    return {
      ok: data.status === "ok",
      status: data.status,
      service: data.service,
    };
  } catch {
    return { ok: false };
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", onAbort);
  }
}

export const PULSE_INTERVAL_UNHEALTHY_MS = 5000;
export const PULSE_INTERVAL_HEALTHY_MS = 30000;
