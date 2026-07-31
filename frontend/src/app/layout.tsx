import type { Metadata, Viewport } from "next";
import Script from "next/script";

import { Providers } from "@/components/providers";

import "./globals.css";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "ASEELO";

export const metadata: Metadata = {
  title: { default: `${APP_NAME} Video`, template: `%s · ${APP_NAME}` },
  description: "From Idea to Content — branded 9:16 Reels and Shorts in minutes.",
  manifest: "/manifest.webmanifest",
  applicationName: APP_NAME,
  appleWebApp: { capable: true, title: APP_NAME, statusBarStyle: "black-translucent" },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#0F172A",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // lang/dir are the Arabic default; I18nProvider updates them on the client
  // once a stored locale preference is read.
  return (
    <html lang="ar" dir="rtl">
      <head>
        {/* Must run before hydration: it carries the API origin for this
            deployment, which is decided at run time rather than build time. */}
        <Script src="/runtime-config.js" strategy="beforeInteractive" />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
