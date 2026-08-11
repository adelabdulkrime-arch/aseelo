"use client";

import type { ReactNode } from "react";

import { LanguageToggle } from "@/components/language-toggle";
import { Logo } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <main className="flex min-h-screen flex-col bg-gradient-to-b from-ink to-ink-soft px-4 py-8">
      <div className="mx-auto flex w-full max-w-md items-center justify-between text-white">
        <Logo />
        <LanguageToggle tone="dark" />
      </div>

      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-8">
        <p className="mb-6 text-center text-sm font-medium text-accent">{t("appTagline")}</p>
        <div className="card animate-fade-in p-6 sm:p-8">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <div className="mt-5 text-center text-sm text-slate-300">{footer}</div>
      </div>
    </main>
  );
}
