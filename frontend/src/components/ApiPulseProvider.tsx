import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  PULSE_INTERVAL_HEALTHY_MS,
  PULSE_INTERVAL_UNHEALTHY_MS,
  probeApiHealth,
} from "@/lib/api/pulse";

type ApiPulseValue = {
  isHealthy: boolean;
  isWaking: boolean;
  status: string | null;
  checkNow: () => Promise<boolean>;
};

const ApiPulseContext = createContext<ApiPulseValue | null>(null);

export function ApiPulseProvider({ children }: { children: ReactNode }) {
  const [isHealthy, setIsHealthy] = useState(true);
  const [isWaking, setIsWaking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const probingRef = useRef(false);

  const applyProbe = useCallback((ok: boolean, nextStatus?: string | null) => {
    setIsHealthy(ok);
    setStatus(nextStatus ?? (ok ? "ok" : null));
    setIsWaking(!ok);
  }, []);

  const checkNow = useCallback(async () => {
    if (probingRef.current) return false;
    probingRef.current = true;
    setIsWaking(true);
    try {
      const result = await probeApiHealth();
      applyProbe(result.ok, result.status ?? null);
      return result.ok;
    } finally {
      probingRef.current = false;
    }
  }, [applyProbe]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function tick() {
      if (cancelled) return;
      if (probingRef.current) {
        timer = window.setTimeout(tick, PULSE_INTERVAL_UNHEALTHY_MS);
        return;
      }
      probingRef.current = true;
      setIsWaking((prev) => prev || !isHealthy);
      try {
        const result = await probeApiHealth();
        if (cancelled) return;
        applyProbe(result.ok, result.status ?? null);
        timer = window.setTimeout(tick, result.ok ? PULSE_INTERVAL_HEALTHY_MS : PULSE_INTERVAL_UNHEALTHY_MS);
      } finally {
        probingRef.current = false;
      }
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [applyProbe]);

  const value = useMemo(
    () => ({ isHealthy, isWaking, status, checkNow }),
    [isHealthy, isWaking, status, checkNow],
  );

  return <ApiPulseContext.Provider value={value}>{children}</ApiPulseContext.Provider>;
}

export function useApiPulse(): ApiPulseValue {
  const ctx = useContext(ApiPulseContext);
  if (!ctx) {
    throw new Error("useApiPulse musi być wewnątrz ApiPulseProvider");
  }
  return ctx;
}
