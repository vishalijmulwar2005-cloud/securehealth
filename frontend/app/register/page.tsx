"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAuth, roleHome } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, ErrorState, Input, Select } from "@/components/ui";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({
    email: "", password: "", full_name: "", role: "PATIENT" as "PATIENT" | "DOCTOR",
    specialty: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const me = await register({
        email: form.email, password: form.password, full_name: form.full_name,
        role: form.role, specialty: form.specialty || undefined,
      });
      router.push(roleHome[me.role] ?? "/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.fields?.length
          ? `${err.message}: ${err.fields.map((f) => `${f.field} ${f.issue}`).join("; ")}`
          : err.message);
      } else {
        setError("Registration failed; try again");
      }
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-sm rounded-xl border border-line bg-white p-6 shadow-card">
        <h1 className="text-lg font-bold text-ink">Create your account</h1>
        <p className="mt-1 text-xs text-ink-faint">Patient and doctor accounts register here; administrative roles are provisioned by the platform.</p>
        <form onSubmit={onSubmit} className="mt-4 space-y-3">
          <label className="block text-sm font-medium text-ink-soft">Full name
            <Input className="mt-1" required value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-ink-soft">Email
            <Input className="mt-1" type="email" required value={form.email}
              onChange={(e) => set("email", e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-ink-soft">Password
            <Input className="mt-1" type="password" required minLength={8}
              value={form.password} onChange={(e) => set("password", e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-ink-soft">I am a
            <Select className="mt-1" value={form.role}
              onChange={(e) => set("role", e.target.value as "PATIENT" | "DOCTOR")}>
              <option value="PATIENT">Patient</option>
              <option value="DOCTOR">Doctor</option>
            </Select>
          </label>
          {form.role === "DOCTOR" && (
            <label className="block text-sm font-medium text-ink-soft">Specialty
              <Input className="mt-1" value={form.specialty}
                onChange={(e) => set("specialty", e.target.value)} />
            </label>
          )}
          {error && <ErrorState message={error} />}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating…" : "Create account"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-ink-soft">
          Have an account? <a href="/login" className="font-medium text-teal-deep underline">Sign in</a>
        </p>
      </div>
    </main>
  );
}
