"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { Button, Card, EmptyState, ErrorState, Loading } from "@/components/ui";

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setItems(await api.get<Notification[]>("/notifications")); }
    catch { setError("Could not load notifications."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function markRead(id: number) {
    try { await api.post(`/notifications/${id}/read`); await load(); }
    catch { setError("Could not update the notification."); }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Notifications</h1>
        <p className="text-sm text-ink-soft">
          Generated from confirmed server events — never optimistic UI state.
        </p>
      </header>
      {error && <ErrorState message={error} onRetry={load} />}
      {!items ? <Loading /> : items.length === 0 ? (
        <EmptyState what="No notifications yet."
          next="Access requests, permission changes, processing and security events appear here." />
      ) : (
        <Card title={`${items.filter((n) => !n.read).length} unread`}>
          <ul className="divide-y divide-line">
            {items.map((n) => (
              <li key={n.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <p className={`text-sm ${n.read ? "text-ink-soft" : "font-semibold text-ink"}`}>
                    {n.read ? "○" : "●"} {n.title}
                  </p>
                  {n.message && <p className="text-xs text-ink-faint">{n.message}</p>}
                  <p className="text-[11px] text-ink-faint">{n.created_at.slice(0, 16).replace("T", " ")}</p>
                </div>
                {!n.read && (
                  <Button kind="ghost" onClick={() => markRead(n.id)}>Mark read</Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
