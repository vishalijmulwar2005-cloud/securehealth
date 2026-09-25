"use client";
import { AppShell } from "@/components/shell";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui";

/** Profile/Security (UI/UX §25): identity/session/security context without
 * revealing secrets. Backend remains authoritative for all security state. */
export default function ProfilePage() {
  return (
    <AppShell requireRole="PATIENT">
      <Profile />
    </AppShell>
  );
}

function Profile() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Profile & security</h1>
        <p className="text-sm text-ink-soft">
          Identity and session context. Security state is server-authoritative.
        </p>
      </header>

      <Card title="Identity">
        <dl className="space-y-2 text-sm">
          <Row k="Full name" v={user.full_name} />
          <Row k="Email" v={user.email} />
          <Row k="Role" v={user.role} />
          <Row k="Account status" v={user.status} />
          {user.pseudo_id && <Row k="Pseudonymous ID" v={user.pseudo_id} />}
        </dl>
        <p className="mt-3 text-[11px] text-ink-faint">
          Your pseudonymous ID is derived with HMAC-SHA-256 under a server-side secret — it
          never exposes your identity and plain hashes are never used as security identities.
        </p>
      </Card>

      <Card title="Session security">
        <dl className="space-y-2 text-sm">
          <Row k="Transport" v="Bearer access token (30-minute target) with one-shot refresh rotation" />
          <Row k="Logout" v="Revokes the refresh session server-side and clears protected client state" />
          <Row k="Authorization" v="Role and account state are re-validated from the database on every request" />
        </dl>
        <p className="mt-3 text-[11px] text-ink-faint">
          Production browser deployment targets secure httpOnly cookie transport with CSRF
          protection (tracked in the build status board).
        </p>
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-2">
      <dt className="text-ink-soft">{k}</dt>
      <dd className="font-medium text-ink">{v}</dd>
    </div>
  );
}
