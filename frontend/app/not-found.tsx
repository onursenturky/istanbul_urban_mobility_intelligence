import Link from "next/link";

export default function NotFound() {
  return (
    <div className="relative min-h-screen overflow-hidden flex items-center" style={{ background: "#113306" }}>
      <div className="absolute inset-0 -z-10 opacity-[0.12]" aria-hidden>
        <svg width="100%" height="100%" preserveAspectRatio="none">
          <defs>
            <pattern id="grid-404" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#B2F093" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid-404)" />
        </svg>
      </div>

      <section className="max-w-2xl mx-auto px-6 py-24 flex flex-col gap-6 text-center items-center">
        <p className="text-o3-text-secondary text-sm tracking-widest uppercase">404</p>
        <h1 className="text-o3-text-primary font-semibold text-4xl md:text-5xl leading-tight">This route is off the map.</h1>
        <p className="text-o3-text-secondary text-base md:text-lg max-w-lg">
          Return to Istanbul Urban Mobility Intelligence to keep exploring.
        </p>
        <Link
          href="/"
          className="rounded-full bg-o3-accent px-6 py-3 font-medium text-sm hover:brightness-105 transition mt-2"
          style={{ color: "#113306" }}
        >
          Back to the homepage
        </Link>
      </section>
    </div>
  );
}
