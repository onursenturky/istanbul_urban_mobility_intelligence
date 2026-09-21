import type { Metadata, Viewport } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-outfit",
  display: "swap",
});

const SITE_DESCRIPTION =
  "A network-based spatial intelligence framework for understanding urban accessibility and active-mobility opportunities across Istanbul. An O3 Sustainability spatial intelligence project.";

// No tracking scripts, no analytics IDs, no marketing SDKs anywhere in this metadata or the
// app -- Phase 14 Section 37 constraint. metadataBase intentionally omitted (no production
// domain assigned yet, see docs/deployment_options.md); Next resolves the file-convention
// opengraph-image/icon routes to request-relative URLs without it.
export const metadata: Metadata = {
  title: "Istanbul Urban Mobility Intelligence | O3 Sustainability",
  description: SITE_DESCRIPTION,
  openGraph: {
    title: "Istanbul Urban Mobility Intelligence | O3 Sustainability",
    description: SITE_DESCRIPTION,
    siteName: "Istanbul Urban Mobility Intelligence",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Istanbul Urban Mobility Intelligence | O3 Sustainability",
    description: SITE_DESCRIPTION,
  },
};

export const viewport: Viewport = {
  themeColor: "#113306",
};

// Root layout only sets up fonts/global CSS. Page chrome is intentionally NOT shared here --
// EDITORIAL mode (landing/overview) and EXPLORATION mode (the map-driven pages) use two
// structurally different shells (see app/(editorial)/layout.tsx and app/(exploration)/layout.tsx),
// per the Phase 13.1 desktop-first correction: an exploration page's chrome (persistent compact
// sidebar, map filling the remaining viewport) is not just a themed variant of the editorial
// top-nav/scrolling-page chrome, it is a different composition entirely.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={outfit.variable}>
      <body>{children}</body>
    </html>
  );
}
