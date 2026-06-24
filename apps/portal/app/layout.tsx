import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { ThemeProvider } from "next-themes";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "ai-gw /dev",
  description: "ai-gw — AI Gateway developer portal",
};

const rybbitEnabled = process.env.NEXT_PUBLIC_RYBBIT_ENABLED === "true";
const rybbitUrl = process.env.NEXT_PUBLIC_RYBBIT_URL ?? "";
const rybbitSiteId = process.env.NEXT_PUBLIC_RYBBIT_SITE_ID ?? "";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-surface="portal"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
        {rybbitEnabled && rybbitUrl && rybbitSiteId && (
          <Script
            src={`${rybbitUrl}/api/script.js`}
            data-site-id={rybbitSiteId}
            strategy="afterInteractive"
          />
        )}
      </body>
    </html>
  );
}
