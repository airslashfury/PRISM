import type { Metadata, Viewport } from "next";

import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "PRISM — Infrastructure Intelligence",
  description:
    "Puerto Rico Infrastructure Simulation Model — resilience, economy, optimization, and rail corridors as one interconnected system.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        {/* Fonts load progressively; the system stack is the graceful fallback. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-background font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
