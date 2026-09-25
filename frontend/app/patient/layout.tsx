"use client";
import { AppShell } from "@/components/shell";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return <AppShell requireRole="PATIENT">{children}</AppShell>;
}
