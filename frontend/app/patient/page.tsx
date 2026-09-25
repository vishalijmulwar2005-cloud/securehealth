"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AccessEvent, ConsentBundle, MedicalRecord, Notification } from "@/lib/types";
import { Card, EmptyState, ErrorState, Loading, StatusBadge } from "@/components/ui";

export default function PatientDashboard() {
  const [records, setRecords] = useState<MedicalRecord[] | null>(null);
  const [consents, setConsents] = useState<ConsentBundle | null>(null);
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [history, setHistory] = useState<AccessEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [r, c, n, h] = await Promise.all([
        api.get<MedicalRecord[]>("/records"),
        api.get<ConsentBundle>("/consents"),
        api.get<Notification[]>("/notifications"),
        api.get<AccessEvent[]>("/access-history"),
      ]);
      setRecords(r); setConsents(c); setNotifications(n); setHistory(h);
    } catch {
      setError("Could not load your dashboard data.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!records || !consents || !notifications || !history) return <Loading />;

  const unread = notifications.filter((n) => !n.read).length;
  const activePerms = consents.permissions.filter((p) => p.status === "ACTIVE");
  const pendingReqs = consents.requests.filter((r) => r.status === "PENDING");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Your health dashboard</h1>
        <p className="text-sm text-ink-soft">What changed, and who can access your data.</p>
      </header>

      <div className="grid gap-4 sm:grid-cols-4">
        {[
          { label: "Records", value: records.length, href: "/patient/records" },
          { label: "Active permissions", value: activePerms.length, href: "/patient/privacy" },
          { label: "Pending requests", value: pendingReqs.length, href: "/patient/privacy" },
          { label: "Unread alerts", value: unread, href: "/patient/notifications" },
        ].map((k) => (
          <Link key={k.label} href={k.href}
            className="rounded-xl border border-line bg-white p-4 shadow-card transition hover:border-teal">
            <p className="text-2xl font-bold text-teal-deep">{k.value}</p>
            <p className="mt-1 text-xs font-medium uppercase tracking-wide text-ink-faint">{k.label}</p>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Recent reports" action={<Link className="text-xs font-medium text-teal-deep underline" href="/patient/records">Open records</Link>}>
          {records.length === 0 ? (
            <EmptyState what="No reports yet." next="Upload your first report from Records." />
          ) : (
            <ul className="divide-y divide-line">
              {records.slice(0, 5).map((r) => (
                <li key={r.id} className="flex items-center justify-between py-2">
                  <Link href={`/patient/records/${r.id}`} className="text-sm font-medium text-ink hover:text-teal-deep">
                    {r.title}
                  </Link>
                  <span className="text-xs text-ink-faint">{r.record_type}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Permissions" action={<Link className="text-xs font-medium text-teal-deep underline" href="/patient/privacy">Privacy Center</Link>}>
          {consents.permissions.length === 0 ? (
            <EmptyState what="No permissions yet." next="Doctor requests will appear here for approval." />
          ) : (
            <ul className="space-y-2">
              {consents.permissions.slice(0, 5).map((p) => (
                <li key={p.id} className="flex items-center justify-between text-sm">
                  <span className="text-ink-soft">Recipient #{p.recipient_user_id} · {p.permission_type}</span>
                  <StatusBadge status={p.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent activity">
          {history.length === 0 ? (
            <EmptyState what="No recorded activity yet." />
          ) : (
            <ul className="divide-y divide-line">
              {history.slice(0, 5).map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-ink-soft">{a.action} · {a.resource_type ?? "—"} #{a.resource_id ?? "—"}</span>
                  <StatusBadge status={a.outcome === "GRANTED" ? "ACTIVE" : "REJECTED"} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Latest notifications" action={<Link className="text-xs font-medium text-teal-deep underline" href="/patient/notifications">View all</Link>}>
          {notifications.length === 0 ? (
            <EmptyState what="No notifications." next="Requests and processing events appear here." />
          ) : (
            <ul className="divide-y divide-line">
              {notifications.slice(0, 5).map((n) => (
                <li key={n.id} className="py-2">
                  <p className={`text-sm ${n.read ? "text-ink-soft" : "font-semibold text-ink"}`}>{n.title}</p>
                  <p className="text-xs text-ink-faint">{n.created_at.slice(0, 16).replace("T", " ")}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
