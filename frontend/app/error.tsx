"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="min-h-screen flex items-center" style={{ background: "#113306" }}>
      <section className="max-w-2xl mx-auto px-6 py-24 flex flex-col gap-6 text-center items-center">
        <p className="text-o3-text-secondary text-sm tracking-widest uppercase">Error</p>
        <h1 className="text-o3-text-primary font-semibold text-3xl md:text-4xl leading-tight">Something went wrong.</h1>
        <p className="text-o3-text-secondary text-base max-w-lg">
          This page couldn&apos;t load. No analytical data was affected -- try again, or head back to the homepage.
        </p>
        <div className="flex gap-3 mt-2">
          <button
            onClick={reset}
            className="rounded-full bg-o3-accent px-6 py-3 font-medium text-sm hover:brightness-105 transition"
            style={{ color: "#113306" }}
          >
            Try again
          </button>
          <a
            href="/"
            className="rounded-full border border-o3-card-strong px-6 py-3 font-medium text-sm text-o3-text-primary hover:bg-o3-card transition"
          >
            Back to homepage
          </a>
        </div>
      </section>
    </div>
  );
}
