import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Gateway — Admin",
  description: "SimCorp AI Gateway admin portal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" data-surface="admin">
      <body>{children}</body>
    </html>
  );
}
