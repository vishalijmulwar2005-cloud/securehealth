"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { MedicalRecord } from "@/lib/types";
import { Banner, Button, Card, EmptyState, ErrorState, Input, Loading, Select } from "@/components/ui";

const RECORD_TYPES = ["BLOOD_REPORT", "XRAY", "PRESCRIPTION", "SCAN", "GENERAL"];

export default function PatientRecordsPage() {
  const [records, setRecords] = useState<MedicalRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("BLOOD_REPORT");
  const [creating, setCreating] = useState(false);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setRecords(await api.get<MedicalRecord[]>("/records")); }
    catch { setError("Could not load records."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function createRecord(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true); setError(null); setOk(null);
    try {
      await api.post("/records", { title, record_type: type });
      setOk("Record created.");  // shown only after server confirmation
      setTitle("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the record.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Medical records</h1>
        <p className="text-sm text-ink-soft">Metadata, files and lifecycle for your health data.</p>
      </header>

      <Card title="New record">
        <form onSubmit={createRecord} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm font-medium text-ink-soft">Title
            <Input className="mt-1" required maxLength={255} value={title}
              onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Annual blood panel" />
          </label>
          <label className="text-sm font-medium text-ink-soft">Type
            <Select className="mt-1" value={type} onChange={(e) => setType(e.target.value)}>
              {RECORD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          </label>
          <Button type="submit" disabled={creating}>{creating ? "Creating…" : "Create"}</Button>
        </form>
        <div className="mt-3 space-y-2">
          {ok && <Banner kind="ok">{ok}</Banner>}
          {error && <ErrorState message={error} onRetry={load} />}
        </div>
      </Card>

      {!records ? <Loading /> : records.length === 0 ? (
        <EmptyState what="No records yet." next="Create a record above, then attach a report file to it." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {records.map((r) => (
            <Link key={r.id} href={`/patient/records/${r.id}`}
              className="rounded-xl border border-line bg-white p-4 shadow-card transition hover:border-teal">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-ink">{r.title}</h3>
                <span className="text-[11px] font-medium uppercase text-ink-faint">{r.record_type}</span>
              </div>
              <p className="mt-1 text-xs text-ink-faint">{r.files.length} file{r.files.length === 1 ? "" : "s"} · record #{r.id}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
