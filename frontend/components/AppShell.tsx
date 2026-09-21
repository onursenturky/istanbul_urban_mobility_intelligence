import { Navigation } from "@/components/Navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-o3-bg-deep">
      <Navigation />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-o3-card px-4 md:px-6 py-6 text-xs text-o3-text-secondary flex flex-col md:flex-row items-start md:items-center justify-between gap-2 max-w-[1600px] mx-auto w-full">
        <span>Istanbul Urban Mobility Intelligence &mdash; an O3 Sustainability spatial intelligence project.</span>
        <span>Modeled network accessibility. Not observed travel behavior. See Data &amp; Methods.</span>
      </footer>
    </div>
  );
}
