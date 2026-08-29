import { useEffect } from "react";

/**
 * Mobile chat shell: mirrors visualViewport height into --vvh and locks document scroll.
 * Fixes iOS Safari 100vh / keyboard clipping so the composer stays in the visible band.
 */
export function useChatShell(active: boolean) {
  useEffect(() => {
    if (!active || typeof window === "undefined") return;

    const root = document.documentElement;
    const body = document.body;
    root.classList.add("chat-shell-active");
    body.classList.add("overflow-hidden");

    const vv = window.visualViewport;

    function updateViewport() {
      if (vv) {
        root.style.setProperty("--vvh", `${vv.height}px`);
        root.style.setProperty(
          "--vvs-bottom",
          vv.height < 500 ? "0px" : "env(safe-area-inset-bottom, 0px)",
        );
      } else {
        root.style.setProperty("--vvh", "100dvh");
        root.style.setProperty("--vvs-bottom", "env(safe-area-inset-bottom, 0px)");
      }
    }

    updateViewport();
    vv?.addEventListener("resize", updateViewport);
    vv?.addEventListener("scroll", updateViewport);
    window.addEventListener("resize", updateViewport);

    return () => {
      vv?.removeEventListener("resize", updateViewport);
      vv?.removeEventListener("scroll", updateViewport);
      window.removeEventListener("resize", updateViewport);
      root.classList.remove("chat-shell-active");
      body.classList.remove("overflow-hidden");
      root.style.removeProperty("--vvh");
      root.style.removeProperty("--vvs-bottom");
    };
  }, [active]);
}
