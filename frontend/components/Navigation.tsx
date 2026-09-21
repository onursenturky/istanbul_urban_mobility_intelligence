"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

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

export function Navigation() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="border-b border-o3-card bg-o3-bg-primary/95 backdrop-blur sticky top-0 z-40">
      <div className="mx-auto max-w-[1600px] px-4 md:px-6 flex items-center justify-between h-14">
        <Link href="/" className="flex items-center gap-2 shrink-0" aria-label="Istanbul Urban Mobility Intelligence, home">
          <span className="w-2.5 h-2.5 rounded-full bg-o3-accent" aria-hidden />
          <span className="font-semibold text-o3-text-primary text-sm tracking-tight">
            Istanbul <span className="text-o3-text-secondary font-normal">/ Urban Mobility Intelligence</span>
          </span>
        </Link>

        <ul className="hidden lg:flex items-center gap-1 text-sm">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`px-3 py-1.5 rounded-full transition-colors ${
                    active
                      ? "bg-o3-accent text-o3-highlight-text font-medium"
                      : "text-o3-text-secondary hover:text-o3-text-primary hover:bg-o3-card"
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

        <button
          className="lg:hidden text-o3-text-primary p-2 rounded-md hover:bg-o3-card"
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
        <ul className="lg:hidden flex flex-col gap-1 px-4 pb-4 text-sm">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`block px-3 py-2 rounded-md ${
                    active ? "bg-o3-accent font-medium" : "text-o3-text-secondary hover:bg-o3-card"
                  }`}
                  style={active ? { color: "#113306" } : undefined}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
