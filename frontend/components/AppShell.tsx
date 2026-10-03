"use client";

import React from "react";
import { AppHeader } from "./AppHeader";
import { AppFooter } from "./AppFooter";

import type { ConnectionStatus } from "@/lib/types";

interface AppShellProps {
 children: React.ReactNode;
 activeIncidentId?: string;
 isStreamConnected?: boolean;
 connectionStatus?: ConnectionStatus;
}

export function AppShell({
 children,
 activeIncidentId,
 isStreamConnected,
 connectionStatus
}: AppShellProps) {
 return (
  <div className="bg-surface-container-lowest font-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container min-h-screen flex flex-col">
   <AppHeader
    activeIncidentId={activeIncidentId}
    isStreamConnected={isStreamConnected}
    connectionStatus={connectionStatus}
   />
   <main className="w-full pt-20 bg-surface-container-lowest min-h-screen flex-1 flex flex-col">
    {children}
   </main>
   <AppFooter />
  </div>
 );
}
