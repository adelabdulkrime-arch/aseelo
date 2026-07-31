"use client";

/** Progressive-web-app state: installability, offline status, worker updates. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** Chromium-only event; it is not in lib.dom yet. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "aseelo.installDismissed";

interface PwaValue {
  /** True when the browser offered a native install prompt we can replay. */
  canInstall: boolean;
  /** iOS never fires beforeinstallprompt, so it needs manual instructions. */
  isIos: boolean;
  isStandalone: boolean;
  installDismissed: boolean;
  offline: boolean;
  updateReady: boolean;
  promptInstall: () => Promise<void>;
  dismissInstall: () => void;
  applyUpdate: () => void;
}

const PwaContext = createContext<PwaValue | null>(null);

function detectStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari predates display-mode and exposes this instead.
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

export function PwaProvider({ children }: { children: ReactNode }) {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isIos, setIsIos] = useState(false);
  const [installDismissed, setInstallDismissed] = useState(true);
  const [offline, setOffline] = useState(false);
  const [updateReady, setUpdateReady] = useState(false);
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);

  // ---- environment ----
  useEffect(() => {
    setIsStandalone(detectStandalone());
    setIsIos(/iphone|ipad|ipod/i.test(window.navigator.userAgent));
    setInstallDismissed(window.localStorage.getItem(DISMISS_KEY) === "1");
    setOffline(!window.navigator.onLine);
  }, []);

  // ---- install prompt ----
  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      // Suppress the browser's own mini-infobar so we can place the CTA ourselves.
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setDeferred(null);
      setIsStandalone(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  // ---- connectivity ----
  useEffect(() => {
    const goOnline = () => setOffline(false);
    const goOffline = () => setOffline(true);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  // ---- service worker registration + update detection ----
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    let reloading = false;
    const onControllerChange = () => {
      // Fires after the new worker takes over; reload once to run the new build.
      if (reloading) return;
      reloading = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);

    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        const promote = (worker: ServiceWorker | null) => {
          if (!worker) return;
          // Only an update if something is already controlling the page;
          // otherwise this is just the first install.
          if (worker.state === "installed" && navigator.serviceWorker.controller) {
            setWaiting(worker);
            setUpdateReady(true);
          }
        };
        promote(registration.waiting);
        registration.addEventListener("updatefound", () => {
          const installing = registration.installing;
          installing?.addEventListener("statechange", () => promote(installing));
        });
      })
      .catch(() => {
        // An unavailable service worker must never break the app.
      });

    return () => {
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    };
  }, []);

  const promptInstall = useCallback(async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    // A prompt can only be replayed once.
    setDeferred(null);
  }, [deferred]);

  const dismissInstall = useCallback(() => {
    setInstallDismissed(true);
    window.localStorage.setItem(DISMISS_KEY, "1");
  }, []);

  const applyUpdate = useCallback(() => {
    if (!waiting) return window.location.reload();
    waiting.postMessage({ type: "SKIP_WAITING" });
    setUpdateReady(false);
  }, [waiting]);

  const value = useMemo<PwaValue>(
    () => ({
      canInstall: deferred !== null,
      isIos,
      isStandalone,
      installDismissed,
      offline,
      updateReady,
      promptInstall,
      dismissInstall,
      applyUpdate,
    }),
    [
      deferred,
      isIos,
      isStandalone,
      installDismissed,
      offline,
      updateReady,
      promptInstall,
      dismissInstall,
      applyUpdate,
    ],
  );

  return <PwaContext.Provider value={value}>{children}</PwaContext.Provider>;
}

export function usePwa(): PwaValue {
  const context = useContext(PwaContext);
  if (!context) throw new Error("usePwa must be used inside <PwaProvider>");
  return context;
}
