"use client";

import { AppShell } from "@/components/AppShell";
import { ROIPanel } from "@/components/ROIPanel";

export default function ROIPage() {
 return (
  <AppShell isStreamConnected={true}>
   <div className="w-full px-gutter-desktop py-space-lg flex flex-col gap-space-lg max-w-[1720px] mx-auto">
    <ROIPanel defaultDays={30} />
   </div>
  </AppShell>
 );
}
