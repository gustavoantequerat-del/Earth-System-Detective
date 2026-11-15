// app/page.tsx
// Entry point: solo monta <Dashboard/>. Todo el estado vive ahí.

"use client";

import Dashboard from "@/components/Dashboard";

export default function Page() {
  return <Dashboard />;
}