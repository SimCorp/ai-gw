import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Portal — SimCorp",
  description: "AI Gateway developer portal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body data-surface="portal">{children}</body>
    </html>
  );
}
