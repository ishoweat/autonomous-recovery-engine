"use client";

import React from "react";
import type { ExplainableRisk, RiskDecision } from "@/lib/types";

interface KpiMetricsGridProps {
 status: string;
 currentNode: string;
 risk?: ExplainableRisk | null;
 retryCount: number;
 prUrl?: string;
 branchName?: string;
}

export const KpiMetricsGrid = React.memo(function KpiMetricsGrid({
 status = "INVESTIGATING",
 currentNode = "triage-orchestrator-04",
 risk,
 retryCount = 0,
 prUrl = "",
 branchName = "fix/inc-8092-auth"
}: KpiMetricsGridProps) {
 const riskScore = typeof risk?.score === "number" && Number.isFinite(risk.score) ? risk.score : 0.0;
 const riskDecision: RiskDecision | string = risk?.decision ?? "BLOCK";

 return (
  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-space-md">
   {/* KPI 1: Incident Status */}
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col justify-between relative overflow-hidden">
    <div className="flex items-center justify-between">
     <span className="font-label-caps text-label-caps text-on-surface-variant">
      INCIDENT STATUS
     </span>
     <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-primary-fixed">
      <span className="material-symbols-outlined text-[18px]">
       emergency_home
      </span>
     </div>
    </div>
    <div className="my-space-sm">
     <div className="flex items-center gap-space-sm">
      <span className="font-headline-lg text-headline-lg font-semibold text-primary tracking-tight">
       {status}
      </span>
     </div>
     <div className="font-mono-code text-mono-code text-on-surface-variant text-xs mt-1 truncate">
      Current node:{" "}
      <span className="text-secondary-fixed">{currentNode}</span>
     </div>
    </div>
    {/* Pulse Telemetry Sparkline SVG */}
    <div className="w-full h-8 pt-1">
     <svg
      className="w-full h-full text-primary-fixed-dim"
      fill="none"
      viewBox="0 0 240 32"
     >
      <path
       d="M0,16 L40,16 L55,4 L65,28 L75,10 L85,20 L95,16 L140,16 L150,2 L162,30 L172,12 L182,18 L190,16 L240,16"
       stroke="currentColor"
       strokeLinejoin="round"
       strokeWidth="2"
      />
      <path
       d="M0,16 L40,16 L55,4 L65,28 L75,10 L85,20 L95,16 L140,16 L150,2 L162,30 L172,12 L182,18 L190,16 L240,16 L240,32 L0,32 Z"
       fill="currentColor"
       fillOpacity="0.08"
      />
     </svg>
    </div>
   </div>

   {/* KPI 2: Aggregate Risk Score */}
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col justify-between relative overflow-hidden">
    <div className="flex items-center justify-between">
     <span className="font-label-caps text-label-caps text-on-surface-variant">
      AGGREGATE RISK SCORE
     </span>
     <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-primary-fixed">
      <span className="material-symbols-outlined text-[18px]">
       verified_user
      </span>
     </div>
    </div>
    <div className="my-space-sm flex items-baseline justify-between">
     <div className="flex items-baseline gap-1">
      <span className="font-mono-metric text-mono-metric text-primary-container">
       {riskScore.toFixed(2)}
      </span>
      <span className="font-mono-code text-mono-code text-on-surface-variant text-sm">
       / 1.00
      </span>
     </div>
     <span
      className={`px-space-xs py-space-2xs rounded font-label-badge text-label-badge ${
       riskDecision === "ALLOW"
        ? "bg-primary-container/20 text-primary-fixed border border-primary-container/30"
        : riskDecision === "APPROVE"
         ? "bg-tertiary-container/20 text-tertiary-fixed border border-tertiary-fixed/30"
         : "bg-error-container/30 text-error border border-error/30"
      }`}
     >
      {riskDecision === "ALLOW"
       ? "ALLOW GATE"
       : riskDecision === "APPROVE"
        ? "APPROVE GATE"
        : "BLOCK GATE"}
     </span>
    </div>
    {/* Risk Threshold Progress Bar */}
    <div className="flex flex-col gap-1">
     <div className="w-full bg-surface-container-highest h-2 rounded-full overflow-hidden flex">
      <div
       className="bg-primary-container h-full w-[30%]"
       title="ALLOW < 0.30"
      />
      <div
       className="bg-secondary h-full w-[40%]"
       title="APPROVE 0.30 - 0.70"
      />
      <div className="bg-error h-full w-[30%]" title="BLOCK > 0.70" />
     </div>
     <div className="flex justify-between font-label-badge text-label-badge text-on-surface-variant text-[9px]">
      <span>ALLOW: 0.00</span>
      <span>APPROVE: 0.30</span>
      <span>BLOCK: 0.70</span>
     </div>
    </div>
   </div>

   {/* KPI 3: Recovery Retries */}
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col justify-between relative overflow-hidden">
    <div className="flex items-center justify-between">
     <span className="font-label-caps text-label-caps text-on-surface-variant">
      RECOVERY RETRIES
     </span>
     <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-secondary">
      <span className="material-symbols-outlined text-[18px]">
       autorenew
      </span>
     </div>
    </div>
    <div className="my-space-sm flex items-center justify-between">
     <div>
      <span className="font-mono-metric text-mono-metric text-on-surface">
       {retryCount}
      </span>
      <p className="font-mono-code text-mono-code text-on-surface-variant text-xs mt-1">
       Maximum allowed: 3
      </p>
     </div>
     {/* Gauge Mini Chart */}
     <div className="relative w-12 h-12 flex items-center justify-center">
      <svg className="w-12 h-12 -rotate-90" viewBox="0 0 36 36">
       <path
        className="text-surface-container-highest"
        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none"
        stroke="currentColor"
        strokeWidth="3.5"
       />
       <path
        className="text-primary-container"
        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none"
        stroke="currentColor"
        strokeDasharray={`${(retryCount / 3) * 100}, 100`}
        strokeLinecap="round"
        strokeWidth="3.5"
       />
      </svg>
      <span className="absolute font-label-badge text-label-badge text-primary-fixed">
       {retryCount}/3
      </span>
     </div>
    </div>
    <div className="pt-space-xs border-t border-surface-container-highest flex items-center justify-between font-label-badge text-label-badge text-primary-fixed">
     <span>{retryCount === 0 ? "CLEAN STATE" : `RETRY ${retryCount}`}</span>
     <span className="material-symbols-outlined text-[14px]">
      check_circle
     </span>
    </div>
   </div>

   {/* KPI 4: Pull Request Target */}
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col justify-between relative overflow-hidden">
    <div className="flex items-center justify-between">
     <span className="font-label-caps text-label-caps text-on-surface-variant">
      PULL REQUEST STATUS
     </span>
     <div className="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-primary-fixed">
      <span className="material-symbols-outlined text-[18px]">
       fork_right
      </span>
     </div>
    </div>
    <div className="my-space-sm">
     <span className="font-headline-lg text-headline-lg font-semibold text-on-surface">
      {prUrl ? "OPEN" : "PENDING"}
     </span>
     <p className="font-mono-code text-mono-code text-on-surface-variant text-xs mt-1 truncate">
      {prUrl ? "PR Created on GitHub" : "Awaiting verification run"}
     </p>
    </div>
    <div className="pt-space-xs border-t border-surface-container-highest flex items-center justify-between font-label-badge text-label-badge text-on-surface-variant">
     <span className="truncate max-w-[140px]">BRANCH: {branchName}</span>
     <span className="text-secondary-fixed">
      {prUrl ? "DISPATCHED" : "STAGED"}
     </span>
    </div>
   </div>
  </div>
 );
});
