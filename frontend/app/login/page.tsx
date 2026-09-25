"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useAuth, roleHome } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, ErrorState, Input } from "@/components/ui";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.push(roleHome[user.role] ?? "/");
  }, [user, loading, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const me = await login(email, password);
      router.push(roleHome[me.role] ?? "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed; try again");
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm rounded-xl border border-line bg-white p-6 shadow-card">
        <div className="mb-4 flex items-center gap-2">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-md bg-teal font-bold text-white">+</span>
          <h1 className="text-lg font-bold text-ink">Sign in to SecureHealth</h1>
        </div>
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-sm font-medium text-ink-soft">
            Email
            <Input className="mt-1" type="email" required autoComplete="email"
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-ink-soft">
            Password
            <span className="relative mt-1 block">
              <Input type={show ? "text" : "password"} required autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} className="pr-14" />
              <button type="button" onClick={() => setShow(!show)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-medium text-teal-deep">
                {show ? "Hide" : "Show"}
              </button>
            </span>
          </label>
          {error && <ErrorState message={error} />}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Verifying…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-ink-soft">
          No account? <a href="/register" className="font-medium text-teal-deep underline">Create one</a>
        </p>
        <p className="mt-3 text-center text-[11px] text-ink-faint">
          Sessions are verified server-side; demo identities are synthetic only.
        </p>
      </div>
    </main>
  );
}
