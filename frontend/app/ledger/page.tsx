"use client";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell";
import { ApiError, api } from "@/lib/api";
import { Banner, Button, Card, EmptyState, ErrorState, Loading, StatusBadge } from "@/components/ui";

interface Block {
  index: number; timestamp: string; type: string; data: Record<string, unknown>;
  previous_hash: string; nonce: number; hash: string;
}
interface BlocksResponse { total: number; types: Record<string, number>; blocks: Block[] }
interface Verify { valid: boolean; broken_index: number; count: number }

export default function LedgerPage() {
  return (
    <AppShell requireRole={["SYSTEM_ADMIN", "HOSPITAL_ADMIN", "PATIENT", "DOCTOR"]}>
      <LedgerExplorer />
    </AppShell>
  );
}

function LedgerExplorer() {
  const [data, setData] = useState<BlocksResponse | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const b = await api.get<BlocksResponse>(`/ledger/blocks${filter ? `?type=${filter}` : ""}`);
      setData(b);
    } catch {
      setError("Could not load the ledger.");
    }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const me = await api.get<{ role: string }>("/auth/me");
        setIsAdmin(me.role === "SYSTEM_ADMIN");
        setVerify(await api.get<Verify>("/ledger/verify"));
      } catch { /* read-only fallback */ }
    })();
  }, []);

  async function runVerify() {
    setError(null); setOk(null);
    try { setVerify(await api.get<Verify>("/ledger/verify")); setOk(null); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Verification failed."); }
  }

  async function tamper(index: number) {
    setError(null); setOk(null);
    try {
      const r = await api.post<{ validation: Verify }>(`/ledger/tamper/${index}`, {});
      setVerify(r.validation);
      setOk(`Block ${index} edited without re-mining — validation fails at exactly that block.`);
      await load();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Tamper demo failed."); }
  }

  async function restore(index: number) {
    setError(null); setOk(null);
    try {
      const r = await api.post<{ restore_block: number; validation: Verify }>(`/ledger/restore/${index}`, {});
      setVerify(r.validation);
      setOk(`Blocks re-mined from #${index}; RESTORE block #${r.restore_block} appended. Chain whole again.`);
      await load();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Restore failed."); }
  }

  if (error && !data) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <Loading />;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-ink">Ledger explorer</h1>
        <p className="text-sm text-ink-soft">
          Every consent change, access decision and training round is a block — SHA-256 proof-of-work,
          difficulty 3, metadata only. Never medical values.
        </p>
      </header>

      <div className="space-y-2">
        {ok && <Banner kind="ok">{ok}</Banner>}
        {error && <ErrorState message={error} onRetry={load} />}
      </div>

      <Card title="Chain integrity" action={<Button kind="secondary" onClick={runVerify}>Verify every block</Button>}>
        {verify ? (
          verify.valid ? (
            <p className="text-sm text-teal-deep">✓ All {verify.count} blocks verified — every stored hash matches its contents and links to the previous block.</p>
          ) : (
            <p className="text-sm text-alarm">✕ Chain broken at block #{verify.broken_index} — stored hash does not match the block contents.</p>
          )
        ) : <Loading />}
      </Card>

      <div className="flex flex-wrap gap-2">
        <FilterChip label="All" active={filter === null} onClick={() => setFilter(null)} />
        {Object.entries(data.types).map(([t, n]) => (
          <FilterChip key={t} label={`${t} (${n})`} active={filter === t} onClick={() => setFilter(t)} />
        ))}
      </div>

      {data.blocks.length === 0 ? (
        <EmptyState what="No blocks of this type yet." />
      ) : (
        <div className="space-y-2">
          {data.blocks.map((b) => (
            <div key={b.index} className="rounded-xl border border-line bg-white shadow-card">
              <button className="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left"
                onClick={() => setOpen(open === b.index ? null : b.index)}>
                <span className="text-sm font-semibold text-ink">#{b.index}</span>
                <StatusBadge status={b.type === "GENESIS" ? "ACTIVE" : b.data?._tampered ? "FAILED" : "COMPLETED"} />
                <span className="text-xs font-medium text-ink-soft">{b.type}</span>
                <span className="font-mono text-[10px] text-ink-faint">{b.hash.slice(0, 20)}…</span>
                <span className="text-[11px] text-ink-faint">{b.timestamp.slice(0, 19).replace("T", " ")}</span>
              </button>
              {open === b.index && (
                <div className="border-t border-line px-4 py-3 text-xs">
                  <pre className="overflow-x-auto rounded-lg bg-paper p-3 text-[11px] text-ink">
                    {JSON.stringify(b.data, null, 2)}
                  </pre>
                  <p className="mt-2 font-mono text-[10px] text-ink-faint">
                    nonce {b.nonce} · previous {b.previous_hash.slice(0, 24)}…
                  </p>
                  {isAdmin && (
                    <div className="mt-3 flex gap-2">
                      <Button kind="secondary" onClick={() => tamper(b.index)}>Tamper demo (edit without re-mining)</Button>
                      <Button kind="ghost" onClick={() => restore(b.index)}>Restore from here</Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
        active ? "border-teal bg-teal text-white" : "border-line bg-white text-ink-soft hover:border-teal"}`}>
      {label}
    </button>
  );
}
