"use client";
import { AppShell } from "@/components/shell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AppShell requireRole="SYSTEM_ADMIN">{children}</AppShell>;
}
