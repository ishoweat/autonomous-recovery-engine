"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import type { ConnectionStatus } from "@/lib/types";

interface AppHeaderProps {
 activeIncidentId?: string;
 isStreamConnected?: boolean;
 connectionStatus?: ConnectionStatus;
}

export function AppHeader({
 activeIncidentId = "INC-8092",
 isStreamConnected = true,
 connectionStatus = "CONNECTED"
}: AppHeaderProps) {
 const pathname = usePathname();

 const navItems = [
  {
   name: "Live Recovery Pipeline",
   href: "/detect",
   isActive: pathname.startsWith("/detect"),
   isPrimary: true
  },
  {
   name: "Mission Control",
   href: "/",
   isActive: pathname === "/"
  },
  {
   name: "Analytics & ROI",
   href: "/roi",
   isActive: pathname.startsWith("/roi")
  },
  {
   name: "Learning Report",
   href: "/learning",
   isActive: pathname.startsWith("/learning")
  }
 ];


 const isOnline = isStreamConnected && connectionStatus !== "BACKEND_OFFLINE" && connectionStatus !== "DISCONNECTED";

 return (
  <header className="fixed top-0 left-0 right-0 z-50 bg-[#0F1115]/95 backdrop-blur-xl border-b border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
   <div className="h-20 w-full px-gutter-desktop flex items-center justify-between gap-space-md">
    {/* Brand / Logo */}
    <Link href="/" className="flex items-center gap-space-lg shrink-0 group">
     <div className="flex items-center gap-space-md">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-container/20 border border-primary-container/40 group-hover:border-primary-container transition-colors">
       <span className="material-symbols-outlined text-primary-container text-[22px]">
        shield
       </span>
      </div>
      <div className="flex flex-col">
       <span className="font-headline-md text-headline-md font-semibold tracking-tight text-on-surface group-hover:text-primary-fixed transition-colors">
        AUTONOMOUS RECOVERY ENGINE
       </span>
       <span className="font-label-caps text-label-caps text-primary-fixed opacity-90">
        NVIDIA NEMOTRON POWERED | MISSION CONTROL v3.4
       </span>
      </div>
     </div>
    </Link>

    {/* Center Navigation */}
    <nav className="hidden xl:flex items-center gap-space-xs">
     {navItems.map((item) => (
      <Link
       key={item.name}
       href={item.href as any}
       className={`px-space-md py-space-sm rounded-lg font-mono-code text-mono-code transition-all whitespace-nowrap ${
        item.isActive
         ? "bg-surface-container-high text-primary-fixed border border-white/[0.08] font-semibold"
         : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container"
       }`}
      >
       {item.name}
      </Link>
     ))}
    </nav>

    {/* Right Status Actions & Indicators */}
    <div className="flex items-center gap-space-md shrink-0">
     {/* SSE Stream Status */}
     <div className="hidden md:flex items-center gap-space-sm bg-surface-container-low px-space-md py-space-xs rounded-full shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]">
      <span
       className={`w-2 h-2 rounded-full ${
        isOnline
         ? "bg-primary animate-pulse"
         : connectionStatus === "RECONNECTING"
          ? "bg-tertiary animate-pulse"
          : "bg-error"
       }`}
      />
      <span className="font-label-badge text-label-badge">
       {connectionStatus === "RECOVERED" ? (
        <span className="text-primary-fixed">STREAM: RECOVERED</span>
       ) : connectionStatus === "OFFLINE" || connectionStatus === "BACKEND_OFFLINE" ? (
        <span className="text-error">STREAM: OFFLINE</span>
       ) : connectionStatus === "RECONNECTING" ? (
        <span className="text-tertiary">RECONNECTING...</span>
       ) : isOnline ? (
        <span className="text-primary-fixed">SSE STREAM: CONNECTED</span>
       ) : (
        <span className="text-error">SSE STREAM: OFFLINE</span>
       )}
      </span>
     </div>

     {/* Telemetry Live Badge */}
     <div className="hidden lg:flex items-center gap-space-xs px-space-sm py-space-2xs rounded-lg bg-surface-container border border-white/[0.08]">
      <span className="font-label-caps text-label-caps text-on-surface-variant">
       TELEMETRY LIVE
      </span>
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-secondary-fixed" />
     </div>


     {/* Incident Quick Badge / Switcher */}
     <Link
      href={`/detect?incident_id=${activeIncidentId}`}
      className="flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-surface-container hover:bg-surface-bright text-on-surface font-label-caps text-label-caps transition-colors shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
     >
      <span className="material-symbols-outlined text-[16px] text-secondary">
       sync_alt
      </span>
      <span className="hidden sm:inline cursor-pointer" title={activeIncidentId} onClick={(e) => { e.preventDefault(); navigator.clipboard.writeText(activeIncidentId); }}>{activeIncidentId}</span>
     </Link>

     {/* Operator Avatar */}
     <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 border border-white/[0.1]">
      <span className="material-symbols-outlined text-on-primary text-[18px]">
       person
      </span>
     </div>
    </div>
   </div>
  </header>
 );
}
