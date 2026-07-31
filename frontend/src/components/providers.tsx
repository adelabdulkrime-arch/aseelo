"use client";

import type { ReactNode } from "react";

import { OfflineBanner, UpdateBanner } from "@/components/pwa-banners";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { PwaProvider } from "@/lib/pwa";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <PwaProvider>
        <AuthProvider>
          <OfflineBanner />
          {children}
          <UpdateBanner />
        </AuthProvider>
      </PwaProvider>
    </I18nProvider>
  );
}
