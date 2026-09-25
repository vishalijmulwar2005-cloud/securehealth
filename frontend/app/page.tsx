"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth, roleHome } from "@/lib/auth";
import { Button, Loading } from "@/components/ui";

/** Pure-CSS 3D scene: tilted core + orbiting hospital nodes + data planes.
 * No WebGL dependency; respects prefers-reduced-motion (globals.css). */
function HeroScene() {
  return (
    <div className="scene relative mx-auto h-80 w-full max-w-md select-none" aria-hidden>
      <div className="scene-3d relative h-full w-full">
        {/* floating data planes */}
        <div className="animate-float-slow absolute left-1/2 top-1/2 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-3xl border border-teal/25 bg-teal/5 shadow-[0_20px_60px_rgba(14,124,123,.18)]"
          style={{ transform: "translateZ(-60px)" }} />
        <div className="animate-float absolute left-1/2 top-1/2 h-52 w-52 -translate-x-1/2 -translate-y-1/2 rounded-3xl border border-teal/40 bg-gradient-to-br from-teal/15 to-teal-wash/40 shadow-[0_24px_70px_rgba(14,124,123,.25)]"
          style={{ transform: "translateZ(20px)" }} />
        {/* secure core */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <div className="grid h-24 w-24 place-items-center rounded-2xl bg-gradient-to-br from-teal-deep to-teal text-2xl font-bold text-white shadow-[0_18px_50px_rgba(10,94,93,.45)]">
            <span className="animate-float">+</span>
          </div>
          <p className="mt-2 text-center text-[10px] font-semibold uppercase tracking-widest text-teal-deep">Secure Core</p>
        </div>
        {/* orbiting hospital nodes */}
        <div className="absolute left-1/2 top-1/2 h-0 w-0 animate-orbit">
          <span className="absolute -left-2 -top-2 grid h-4 w-4 place-items-center rounded-full bg-ink text-[8px] font-bold text-white">H1</span>
        </div>
        <div className="absolute left-1/2 top-1/2 h-0 w-0 animate-orbit" style={{ animationDuration: "24s", animationDirection: "reverse" }}>
          <span className="absolute -left-2 -top-2 grid h-4 w-4 place-items-center rounded-full bg-amber text-[8px] font-bold text-white">H2</span>
        </div>
        <div className="absolute left-1/2 top-1/2 h-0 w-0 animate-spin-slow">
          <span className="absolute -left-1.5 top-1/2 h-3 w-3 rounded-full bg-teal shadow-[0_0_12px_rgba(14,124,123,.9)]" />
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.push(roleHome[user.role] ?? "/");
  }, [user, loading, router]);

  if (loading) return <main className="mx-auto max-w-3xl px-4 py-24"><Loading /></main>;

  return (
    <main className="texture-grid min-h-screen">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 sm:px-10">
        <span className="flex items-center gap-2.5">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-teal text-sm font-bold text-white shadow-lg shadow-teal/30">+</span>
          <span className="text-sm font-bold tracking-tight text-ink">SecureHealth</span>
        </span>
        <span className="flex items-center gap-2">
          <Link href="/login"><Button kind="ghost">Sign in</Button></Link>
          <Link href="/register"><Button>Get Started</Button></Link>
        </span>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-teal/10 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -left-32 top-40 h-80 w-80 rounded-full bg-amber/10 blur-3xl" />
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-16 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal">
              Privacy-preserving healthcare intelligence
            </p>
            <h1 className="mt-4 text-4xl font-bold leading-tight text-ink sm:text-5xl">
              Your records.<br />Your consent.<br />
              <span className="bg-gradient-to-r from-teal to-teal-deep bg-clip-text text-transparent">Verifiable by design.</span>
            </h1>
            <p className="mt-5 max-w-lg text-ink-soft">
              Patient-controlled permissions, AI-assisted report understanding, federated
              learning that never moves raw records, and a tamper-evident PoW audit ledger —
              one coherent platform.
            </p>
            <div className="mt-8 flex gap-3">
              <Button onClick={() => router.push("/register")}>Get Started</Button>
              <Link href="#architecture"><Button kind="secondary">Explore the Platform</Button></Link>
            </div>
          </div>
          <HeroScene />
        </div>
      </section>

      {/* Architecture flow — 3D-tilted cards */}
      <section id="architecture" className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-bold text-ink">How the secure network works</h2>
        <p className="mx-auto mt-2 max-w-xl text-center text-sm text-ink-soft">
          Every step is server-authorized, audited, and truthful — success is shown only after the backend confirms it.
        </p>
        <div className="scene mt-12 grid gap-6 md:grid-cols-4">
          {[
            { t: "Patient Data", d: "Encrypted at rest outside public web roots; retrieved only after authorization.", icon: "🗂" },
            { t: "Secure Core", d: "Identity, roles, ownership and consent checked server-side on every action.", icon: "🛡" },
            { t: "Hospital · AI · Ledger", d: "AI assists, never diagnoses; the ledger stores fingerprints only.", icon: "⛓" },
            { t: "Global Model", d: "Federated learning aggregates model updates — records moved: 0.", icon: "🌐" },
          ].map((s, i) => (
            <div key={s.t}
              className="rounded-2xl border border-line bg-white p-5 shadow-card transition hover:-translate-y-1 hover:shadow-xl"
              style={{ transform: `rotateX(6deg) rotateY(${(i - 1.5) * 4}deg)` }}>
              <span aria-hidden className="text-2xl">{s.icon}</span>
              <h3 className="mt-2 font-semibold text-ink">{s.t}</h3>
              <p className="mt-1 text-sm text-ink-soft">{s.d}</p>
            </div>
          ))}
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-3">
          {[
            { t: "Patient control", d: "Grant, review and revoke access with visible scope and duration.", i: "🔑" },
            { t: "Truthful states", d: "Nothing reports success before the server confirms it.", i: "✓" },
            { t: "Auditable by design", d: "Access and denials are recorded and reviewable.", i: "📎" },
          ].map((c) => (
            <div key={c.t} className="rounded-xl border border-line bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lg">
              <span aria-hidden className="text-xl">{c.i}</span>
              <h3 className="mt-1 font-semibold text-ink">{c.t}</h3>
              <p className="mt-1 text-sm text-ink-soft">{c.d}</p>
            </div>
          ))}
        </div>

        <div className="mt-14 rounded-2xl border border-teal/20 bg-gradient-to-r from-teal-wash to-white p-8 text-center shadow-card">
          <p className="text-sm font-medium text-teal-deep">
            Ready? Create an account or sign in to your role dashboard.
          </p>
          <div className="mt-4 flex justify-center gap-3">
            <Button onClick={() => router.push("/register")}>Create account</Button>
            <Link href="/login"><Button kind="secondary">Sign in</Button></Link>
          </div>
        </div>
      </section>
    </main>
  );
}
