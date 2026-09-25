"use client";
/** ConsoleLayout adopted from the verified console: fixed white header with
 * role chip, fixed left sidebar (active = white card + teal text), content
 * column. Backend remains the security boundary. */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth, roleHome } from "@/lib/auth";
import { Button, Loading } from "./ui";
import type { Role } from "@/lib/types";

const NAV: Record<string, { href: string; label: string }[]> = {
  PATIENT: [
    { href: "/patient", label: "Dashboard" },
    { href: "/patient/records", label: "Records" },
    { href: "/patient/privacy", label: "Privacy Center" },
    { href: "/patient/notifications", label: "Notifications" },
    { href: "/patient/history", label: "Access History" },
    { href: "/patient/profile", label: "Profile" },
  ],
  DOCTOR: [
    { href: "/doctor", label: "Dashboard" },
    { href: "/doctor/prescriptions", label: "Prescriptions" },
  ],
  SYSTEM_ADMIN: [
    { href: "/admin", label: "Overview" },
    { href: "/admin/hospitals", label: "Hospitals" },
    { href: "/fl", label: "Federated Training" },
    { href: "/ledger", label: "Ledger" },
    { href: "/admin/audit", label: "Audit Trail" },
  ],
  HOSPITAL_ADMIN: [
    { href: "/admin", label: "Overview" },
    { href: "/admin/hospitals", label: "Hospitals" },
    { href: "/fl", label: "Federated Training" },
    { href: "/ledger", label: "Ledger" },
    { href: "/admin/audit", label: "Audit Trail" },
  ],
  REGULATOR: [{ href: "/regulator", label: "Verification Console" }],
};

const ROLE_BLURB: Record<string, string> = {
  PATIENT: "Controls their own consent and records",
  DOCTOR: "Requests access, treats within authorized scope",
  SYSTEM_ADMIN: "Runs the platform, manages accounts and nodes",
  HOSPITAL_ADMIN: "Runs training, manages consortium nodes",
  REGULATOR: "Checks the ledger and audit trail",
};

export function AppShell({ children, requireRole }: {
  children: React.ReactNode; requireRole: Role | Role[];
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const roles = Array.isArray(requireRole) ? requireRole : [requireRole];

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center">
        <Loading label="Checking your session..." />
      </main>
    );
  }

  if (!user) {
    return (
      <main className="grid min-h-screen place-items-center px-4">
        <div className="w-full max-w-md rounded-lg border border-line bg-white p-8 text-center">
          <h1 className="text-lg font-semibold text-ink">Sign in required</h1>
          <p className="mt-2 text-sm text-ink-soft">
            You need an authenticated session to open this area.
          </p>
          <Button className="mt-5 w-full" onClick={() => router.push("/login")}>Go to sign in</Button>
        </div>
      </main>
    );
  }

  if (!roles.includes(user.role)) {
    return (
      <main className="grid min-h-screen place-items-center px-4">
        <div className="w-full max-w-md rounded-lg border border-amber/30 bg-amber-wash p-8 text-center">
          <h1 className="text-lg font-semibold text-amber-deep">Not available for your role</h1>
          <p className="mt-2 text-sm text-ink-soft">
            This area is limited to {roles.join(" / ").replace(/_/g, " ")} accounts. Your role: {user.role}.
          </p>
          <Button className="mt-5" tone="outline" onClick={() => router.push(roleHome[user.role] ?? "/")}>
            Go to your dashboard
          </Button>
        </div>
      </main>
    );
  }

  const nav = NAV[user.role] ?? [];
  return (
    <div className="min-h-screen">
      <header className="fixed top-0 inset-x-0 z-40 bg-white border-b border-line">
        <div className="h-[57px] flex items-center justify-between px-4 gap-3">
          <div className="flex items-center gap-3">
            <button onClick={() => router.push(roleHome[user.role] ?? "/")}
              className="font-extrabold tracking-tight text-ink">
              SecureHealth <span className="text-ink-faint font-semibold hidden sm:inline">- Care Console</span>
            </button>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden md:block text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-faint">
              {ROLE_BLURB[user.role]}
            </span>
            <span className="rounded-full bg-teal-wash text-teal-deep px-3 py-1 text-xs font-semibold">
              {user.role.replace("_", " ")}
            </span>
            <Button tone="ghost" onClick={async () => { await logout(); router.push("/login"); }}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <aside className="hidden lg:block fixed top-[57px] bottom-0 left-0 w-[240px] bg-paper border-r border-line overflow-y-auto">
        <nav className="p-3 space-y-1">
          {nav.map((n) => {
            const active = pathname === n.href;
            return (
              <Link key={n.href} href={n.href}
                className={`flex items-center rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
                  active ? "bg-white text-teal-deep border border-teal/30 shadow-sm" : "text-ink-soft hover:bg-white hover:text-ink"}`}>
                {n.label}
              </Link>
            );
          })}
          <div className="pt-3 mt-3 border-t border-line px-3">
            <div className="text-[11px] text-ink-faint leading-relaxed">
              Server-backed JWT identity. All patient data is synthetic.
            </div>
          </div>
        </nav>
      </aside>

      <main className="lg:ml-[240px] pt-[57px] min-h-screen">
        <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
        <footer className="border-t border-line px-6 py-5 text-xs text-ink-faint">
          SecureHealth - privacy-preserving healthcare platform - synthetic demo data only
        </footer>
      </main>
    </div>
  );
}
