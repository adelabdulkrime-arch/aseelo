"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LanguageToggle } from "@/components/language-toggle";
import { InstallBanner } from "@/components/pwa-banners";
import { LoadingState, Logo } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useI18n, type StringKey } from "@/lib/i18n";

const NAV: { href: string; key: StringKey; icon: string }[] = [
  { href: "/dashboard", key: "dashboard", icon: "▦" },
  { href: "/videos", key: "videos", icon: "🎬" },
  { href: "/videos/new", key: "createVideo", icon: "＋" },
  { href: "/brand", key: "brand", icon: "◈" },
  { href: "/settings", key: "settings", icon: "⚙" },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Only reached when no session could be established at all (guests
    // disabled, or rate limited) - there is no login page to fall back to.
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="grid min-h-screen place-items-center">
        <LoadingState />
      </main>
    );
  }

  const isActive = (href: string) =>
    href === "/videos" ? pathname === "/videos" : pathname.startsWith(href);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <Link href="/dashboard" aria-label="ASEELO">
            <Logo />
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(item.href) ? "page" : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive(item.href)
                    ? "bg-brand/10 text-brand"
                    : "text-ink-muted hover:bg-slate-100 hover:text-ink"
                }`}
              >
                {t(item.key)}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <LanguageToggle />
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-ink-soft transition hover:bg-slate-50"
            >
              {t("startOver")}
            </button>
          </div>
        </div>
      </header>

      {/* Bottom bar keeps the app thumb-reachable on phones (mobile-first). */}
      <nav
        className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 backdrop-blur md:hidden"
        aria-label="Main"
      >
        <div className="mx-auto flex max-w-5xl">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href) ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition ${
                isActive(item.href) ? "text-brand" : "text-ink-muted"
              }`}
            >
              <span aria-hidden="true" className="text-base leading-none">
                {item.icon}
              </span>
              {t(item.key)}
            </Link>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-4 pb-24 pt-6 md:pb-10">{children}</main>

      <InstallBanner />
    </div>
  );
}
