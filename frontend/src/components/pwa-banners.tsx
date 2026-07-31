"use client";

import { useI18n } from "@/lib/i18n";
import { usePwa } from "@/lib/pwa";

/** Sits above the mobile bottom nav so it never covers navigation. */
const STACK = "fixed inset-x-0 bottom-[68px] z-30 mx-auto max-w-md px-4 md:bottom-4";

export function OfflineBanner() {
  const { t } = useI18n();
  const { offline } = usePwa();
  if (!offline) return null;

  return (
    <div className="sticky top-0 z-40 bg-amber-500 px-4 py-2 text-center text-sm font-semibold text-ink" role="status">
      {t("offlineBanner")}
    </div>
  );
}

export function UpdateBanner() {
  const { t } = useI18n();
  const { updateReady, applyUpdate } = usePwa();
  if (!updateReady) return null;

  return (
    <div className={STACK} role="status">
      <div className="flex items-center gap-3 rounded-xl bg-ink px-4 py-3 text-white shadow-lg">
        <span className="flex-1 text-sm font-medium">{t("updateAvailable")}</span>
        <button type="button" onClick={applyUpdate} className="btn bg-accent px-3 py-1.5 text-ink">
          {t("updateNow")}
        </button>
      </div>
    </div>
  );
}

export function InstallBanner() {
  const { t } = useI18n();
  const { canInstall, isIos, isStandalone, installDismissed, promptInstall, dismissInstall } =
    usePwa();

  // Nothing to offer once installed, dismissed, or when the platform can't install.
  if (isStandalone || installDismissed) return null;
  if (!canInstall && !isIos) return null;

  return (
    <div className={STACK}>
      <div className="animate-fade-in rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
        <div className="flex items-start gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- static icon in /public */}
          <img src="/icons/icon-192.png" alt="" className="h-10 w-10 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">{t("installTitle")}</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              {isIos && !canInstall ? t("installIosBody") : t("installBody")}
            </p>
          </div>
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={dismissInstall} className="btn-secondary px-3 py-1.5 text-xs">
            {t("dismiss")}
          </button>
          {canInstall && (
            <button
              type="button"
              onClick={() => void promptInstall()}
              className="btn-primary px-3 py-1.5 text-xs"
            >
              {t("install")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
