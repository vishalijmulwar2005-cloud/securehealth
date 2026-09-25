"use client";
import { AppShell } from "@/components/shell";

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
  return <AppShell requireRole="DOCTOR">{children}</AppShell>;
}
