import { Sidebar } from "@/components/Sidebar";

// EXPLORATION mode shell (Phase 13.1 desktop-first correction).
//
// Deliberately built as ONE fixed `h-screen` root with a `flex-1` chain all the way down to
// the map, instead of the previous nested-flex-with-viewport-relative-height-and-min-height-
// floor approach. That earlier approach was diagnosed (via live DOM measurement, see
// components/MapView.tsx comments and qa/phase13_1_map_rendering_qa.json) as a real,
// reproducible cause of the map container's *own* layout intermittently collapsing back to a
// live height of 0 after its first correct paint -- because it depended on THREE separate,
// independently-recalculated sizing mechanisms (a `vh` unit, a `min-height` floor, and an
// `absolute inset-0` percentage-height chain) staying in agreement, which they did not always
// do across route transitions and font-swap reflows.
//
// A single `h-screen` (a hard, viewport-derived, always-definite value) with `flex-1` at each
// level below it removes that ambiguity: every intermediate box has an unambiguous, CSS-
// -algorithm-guaranteed height, computed exactly once per layout pass, with no unit mixing.
export default function ExplorationLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen flex flex-col md:flex-row overflow-hidden bg-o3-bg-deep">
      <Sidebar />
      <main className="flex-1 min-w-0 min-h-0 relative overflow-hidden">{children}</main>
    </div>
  );
}
