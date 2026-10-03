"use client";

import { useState } from "react";
import { Globe } from "lucide-react";
import type { PolyglotAudiences } from "@/lib/types";

const LANG_TOKENS: Record<string, string> = {
 python:   "bg-primary-container/20 text-primary-fixed border-primary-container/40",
 go:     "bg-tertiary-container/20 text-tertiary-fixed border-tertiary-fixed/30",
 rust:    "bg-secondary/20 text-secondary-fixed border-secondary/40",
 javascript: "bg-secondary-container/20 text-secondary-fixed border-secondary/30",
 typescript: "bg-primary-container/15 text-primary-container border-primary-container/30",
 java:    "bg-error/20 text-error border-error/40",
};

interface PolyglotBadgeProps {
 language: string;
 semanticIssue: string;
 audiences?: PolyglotAudiences;
 confidence: number;
}

type AudienceTab = "devops" | "product" | "researcher";

export function PolyglotBadge({
 language,
 semanticIssue,
 audiences,
 confidence,
}: PolyglotBadgeProps) {
 const [tab, setTab] = useState<AudienceTab>("devops");

 if (!language) return null;

 const langClass = LANG_TOKENS[language.toLowerCase()] ??
  "bg-surface-container text-on-surface-variant border-white/[0.06]";

 const tabClass = (t: AudienceTab) =>
  `px-space-sm py-space-2xs rounded-md font-label-caps text-label-caps transition-colors cursor-pointer ${
   tab === t
    ? "bg-primary-container/20 text-primary-fixed border border-primary-container/40"
    : "text-on-surface-variant hover:text-on-surface"
  }`;

 return (
  <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col gap-space-md">

   {/* ── Header ─────────────────────────────────────────────────────────── */}
   <div className="flex items-center justify-between">
    <div className="flex flex-col">
     <span className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1.5">
      <Globe className="w-3 h-3 text-primary-container" />
      POLYGLOT FIX ENGINE
     </span>
     <span className="font-headline-md text-headline-md font-semibold text-on-surface">
      Language-Aware Repair
     </span>
    </div>

    <div className="flex items-center gap-space-xs">
     {/* Language badge */}
     <span
      className={`px-space-xs py-space-2xs rounded font-label-badge text-label-badge border ${langClass}`}
     >
      {language.toUpperCase()}
     </span>
     {/* Confidence badge */}
     <span className="px-space-xs py-space-2xs rounded font-label-badge text-label-badge bg-surface-container text-on-surface-variant border border-white/[0.06]">
      {Math.round(confidence * 100)}%
     </span>
    </div>
   </div>

   {/* ── Semantic root cause ─────────────────────────────────────────────── */}
   <div className="p-space-sm rounded-lg bg-surface-container border border-white/[0.08]">
    <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px] block mb-1">
     SEMANTIC ROOT CAUSE
    </span>
    <p className="font-mono-code text-mono-code text-secondary-fixed text-xs leading-relaxed">
     {semanticIssue}
    </p>
   </div>

   {/* ── Multi-audience explainer ────────────────────────────────────────── */}
   {audiences && (
    <div className="flex flex-col gap-space-sm">
     <div className="flex gap-1">
      {(["devops", "product", "researcher"] as AudienceTab[]).map((t) => (
       <button key={t} className={tabClass(t)} onClick={() => setTab(t)}>
        {t.charAt(0).toUpperCase() + t.slice(1)}
       </button>
      ))}
     </div>

     <div className="p-space-sm rounded-lg bg-surface-container shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] min-h-[52px]">
      <p className="font-body-sm text-body-sm text-on-surface leading-relaxed">
       {audiences[tab]}
      </p>
     </div>
    </div>
   )}
  </div>
 );
}
