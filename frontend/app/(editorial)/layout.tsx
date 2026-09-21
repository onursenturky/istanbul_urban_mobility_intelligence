import { AppShell } from "@/components/AppShell";

// EDITORIAL mode: landing + overview. Scrolling page, top navigation, room for large
// storytelling typography and highlight panels. See app/(exploration)/layout.tsx for the
// structurally different map-first shell used by every analytical page.
export default function EditorialLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
