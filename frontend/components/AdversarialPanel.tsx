"use client";

import { useEffect, useState } from "react";
import {
 AlertTriangle,
 Bug,
 ShieldAlert,
 ShieldCheck,
 Zap,
} from "lucide-react";
import { runAdversarialCheck } from "@/lib/api";
import type { AdversarialReport } from "@/lib/types";

interface AdversarialPanelProps {
 /** Raw patch code / diff to validate. When falsy the panel stays hidden. */
 patchCode: string;
 patchDiff?: string;
 /**
  */
}

export function AdversarialPanel({
 patchCode,
 patchDiff = "",
}: AdversarialPanelProps) {
 const [report, setReport] = useState<AdversarialReport | null>(null);
 const [loading, setLoading] = useState(false);
 const [error, setError] = useState<string | null>(null);

 useEffect(() => {
  if (!patchCode.trim()) return;
  let cancelled = false;

  setLoading(true);
  setError(null);

  runAdversarialCheck(patchCode, patchDiff)
   .then((r) => { if (!cancelled) setReport(r); })
   .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
   .finally(() => { if (!cancelled) setLoading(false); });

  return () => { cancelled = true; };
 }, [patchCode, patchDiff]);

 if (!patchCode.trim()) return null;

 // ── Loading skeleton ────────────────────────────────────────────────────────
 if (loading) {
  return (
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
    <div className="flex items-center gap-space-sm">
     <span className="w-3 h-3 rounded-full bg-secondary-fixed animate-pulse" />
     <span className="font-label-caps text-label-caps text-on-surface-variant animate-pulse">
      Running adversarial checks…
     </span>
    </div>
   </div>
  );
 }

 // ── Error state ─────────────────────────────────────────────────────────────
 if (error) {
  return (
   <div className="p-space-md rounded-lg bg-surface-container-low border border-error/20">
    <p className="font-mono-code text-mono-code text-error text-xs">{error}</p>
   </div>
  );
 }

 if (!report) return null;

 const safe = report.overall_safe;
 const mutPct = Math.round(report.mutation_score * 100);
 const confPct = Math.round(report.confidence * 100);

 return (
  <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col gap-space-md">

   {/* ── Header ─────────────────────────────────────────────────────────── */}
   <div className="flex items-center justify-between">
    <div className="flex flex-col">
     <span className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1.5">
      {safe
       ? <ShieldCheck className="w-3 h-3 text-primary-fixed" />
       : <ShieldAlert className="w-3 h-3 text-error" />}
      ADVERSARIAL RESILIENCE
     </span>
     <span className="font-headline-md text-headline-md font-semibold text-on-surface">
      Patch Security Analysis
     </span>
    </div>

    <div
     className={`flex items-center gap-space-xs px-space-md py-space-xs rounded-lg font-label-caps text-label-caps border font-bold ${
      safe
       ? "bg-primary-container/20 text-primary-fixed border-primary-container/40"
       : "bg-error/20 text-error border-error/40"
     }`}
    >
     {safe ? <ShieldCheck className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
     <span>{safe ? "SAFE" : "UNSAFE"} · {confPct}%</span>
    </div>
   </div>

   {/* ── 3 metric cards ─────────────────────────────────────────────────── */}
   <div className="grid grid-cols-3 gap-space-sm">

    {/* Mutation Score */}
    <div className="flex flex-col items-center gap-1 p-space-sm rounded-lg bg-surface-container border border-white/[0.08]">
     <Bug className="w-4 h-4 text-tertiary-fixed" />
     <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
      Mutation
     </span>
     <span
      className={`font-mono-metric text-mono-metric text-xl font-bold ${
       mutPct >= 60 ? "text-primary-fixed" : "text-error"
      }`}
     >
      {mutPct}%
     </span>
     <span className="font-label-badge text-label-badge text-on-surface-variant text-[10px] text-center">
      {report.raw?.mutation?.killed ?? 0}k&nbsp;/&nbsp;
      {report.raw?.mutation?.survived ?? 0}s
     </span>
    </div>

    {/* CVE Hits */}
    <div className="flex flex-col items-center gap-1 p-space-sm rounded-lg bg-surface-container border border-white/[0.08]">
     <AlertTriangle className="w-4 h-4 text-secondary-fixed" />
     <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
      CVE Hits
     </span>
     <span
      className={`font-mono-metric text-mono-metric text-xl font-bold ${
       report.cve_hits.length === 0 ? "text-primary-fixed" : "text-error"
      }`}
     >
      {report.cve_hits.length}
     </span>
     <span className="font-label-badge text-label-badge text-on-surface-variant text-[10px]">
      {report.raw?.cve?.deps_scanned?.length ?? 0} deps
     </span>
    </div>

    {/* Behavioral */}
    <div className="flex flex-col items-center gap-1 p-space-sm rounded-lg bg-surface-container border border-white/[0.08]">
     <Zap className="w-4 h-4 text-primary-container" />
     <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
      Behavioral
     </span>
     <span
      className={`font-mono-metric text-mono-metric text-xl font-bold ${
       report.behavioral_flags.length === 0 ? "text-primary-fixed" : "text-secondary-fixed"
      }`}
     >
      {report.behavioral_flags.length === 0 ? "✓" : report.behavioral_flags.length}
     </span>
     <span className="font-label-badge text-label-badge text-on-surface-variant text-[10px] truncate text-center max-w-full px-1">
      {report.behavioral_flags[0] ?? "clean"}
     </span>
    </div>
   </div>

   {/* ── CVE detail list ─────────────────────────────────────────────────── */}
   {report.cve_hits.length > 0 && (
    <div className="flex flex-col gap-1">
     <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
      CVE DETAILS
     </span>
     {report.cve_hits.map((h, i) => (
      <div
       key={i}
       className="flex items-center gap-space-sm font-mono-code text-mono-code text-xs p-space-sm rounded-lg bg-error-container/20 border border-error/30"
      >
       <span className="text-error font-semibold shrink-0">{h.cve_id}</span>
       <span className="text-on-surface-variant truncate">
        {h.pkg}@{h.version}
       </span>
       <span className="ml-auto shrink-0 px-space-xs py-space-2xs rounded font-label-badge text-label-badge bg-error/20 text-error border border-error/30">
        {h.severity}
       </span>
      </div>
     ))}
    </div>
   )}

   {/* ── Summary line ────────────────────────────────────────────────────── */}
   <p className="font-mono-code text-mono-code text-on-surface-variant text-xs border-t border-surface-container-highest pt-space-sm leading-relaxed">
    {report.summary}
   </p>
  </div>
 );
}
