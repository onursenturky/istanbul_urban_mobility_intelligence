"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { O3BrandMark } from "@/components/O3BrandMark";

const NAV_ITEMS = [
  { href: "/overview", label: "Overview" },
  { href: "/typology", label: "Urban Typology" },
  { href: "/fifteen-minute", label: "15-Minute Istanbul" },
  { href: "/cycling-gain", label: "Cycling Gain" },
  { href: "/transit", label: "Transit Connection" },
  { href: "/gaps", label: "Accessibility Gaps" },
  { href: "/ebike", label: "E-bike" },
  { href: "/methods", label: "Data & Methods" },
];

/**
 * Persistent compact desktop sidebar for EXPLORATION mode (Phase 13.1 desktop-first
 * correction). Deliberately narrow (see w-56 below) so the map keeps ~75-80% of the
 * viewport width -- this is a navigation rail, not a mobile-style stacked menu.
 */
export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const links = (
    <ul className="flex flex-col gap-0.5">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={`block px-3 py-2 rounded-lg text-sm transition-colors ${
                active ? "bg-o3-accent font-medium" : "text-o3-text-secondary hover:text-o3-text-primary hover:bg-o3-card"
              }`}
              style={active ? { color: "#113306" } : undefined}
              aria-current={active ? "page" : undefined}
            >
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  return (
    <>
      {/* Desktop: persistent narrow rail */}
      <aside className="hidden md:flex md:flex-col md:w-56 md:shrink-0 h-full border-r border-o3-card bg-o3-bg-primary px-3 py-4 gap-6 overflow-y-auto o3-scrollbar">
        <Link href="/" className="px-1">
          <O3BrandMark />
        </Link>
        <nav aria-label="Analysis modules">{links}</nav>
        <div className="mt-auto px-1 pt-4 border-t border-o3-card">
          <p className="text-o3-text-secondary text-[11px] leading-snug">An O3 Sustainability spatial intelligence project.</p>
        </div>
      </aside>

      {/* Mobile: compact top bar + collapsible menu (existing mobile pattern, unchanged) */}
      <div className="md:hidden flex items-center justify-between h-14 px-4 border-b border-o3-card bg-o3-bg-primary shrink-0">
        <Link href="/" className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-o3-accent" aria-hidden />
          <span className="font-semibold text-o3-text-primary text-sm">Istanbul / Urban Mobility Intelligence</span>
        </Link>
        <button
          className="text-o3-text-primary p-2 rounded-md hover:bg-o3-card"
          onClick={() => setMobileOpen((v) => !v)}
          aria-expanded={mobileOpen}
          aria-label="Toggle navigation menu"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {mobileOpen && (
        <div className="md:hidden border-b border-o3-card bg-o3-bg-primary px-4 py-3">
          {links}
        </div>
      )}
    </>
  );
}
