"use client";

import { useCallback, useEffect, useState } from "react";
import {
 Bar,
 BarChart,
 CartesianGrid,
 Cell,
 Line,
 LineChart,
 Pie,
 PieChart,
 ResponsiveContainer,
 Tooltip,
 XAxis,
 YAxis,
 Legend,
} from "recharts";
import { Clock, DollarSign, ShieldCheck, TrendingDown } from "lucide-react";
import { fetchROIDashboard } from "@/lib/api";
import type { ROIDashboardData } from "@/lib/types";

// ── Chart palette aligned with the project's brand colours ────────────────────
const CHART_COLORS = [
 "#22C55E", // primary
 "#4ADE80", // primary-fixed
 "#38BDF8", // secondary-fixed
 "#94A3B8", // secondary
 "#FCD34D", // tertiary / amber
 "#F87171", // error
];

// ── Recharts tooltip style ────────────────────────────────────────────────────
const TOOLTIP_STYLE: React.CSSProperties = {
 background: "rgba(22,26,31,0.95)",
 border: "1px solid rgba(255,255,255,0.08)",
 borderRadius: 8,
 fontSize: 11,
 color: "#F1F5F9",
};

interface ROIPanelProps {
 defaultDays?: number;
}

type SeverityKey = "LOW" | "MEDIUM" | "HIGH";

const SEVERITY_TOKEN: Record<SeverityKey, string> = {
 LOW:  "text-primary-fixed",
 MEDIUM: "text-secondary-fixed",
 HIGH:  "text-error",
};

export function ROIPanel({ defaultDays = 30 }: ROIPanelProps) {
 const [data, setData] = useState<ROIDashboardData | null>(null);
 const [days, setDays] = useState(defaultDays);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState<string | null>(null);
 const [blockedCount, setBlockedCount] = useState<number>(0);

 const load = useCallback((d: number) => {
  setLoading(true);
  setError(null);
  fetchROIDashboard(d)
   .then(setData)
   .catch((e) => setError(String(e?.message ?? e)))
   .finally(() => setLoading(false));
  // Phase 5: fetch blocked count from new table (best-effort, non-blocking)
  fetch(`/api/v1/roi/blocked-incidents`)
   .then(r => r.ok ? r.json() : { blocked_incidents: 0 })
   .then(j => setBlockedCount(j.blocked_incidents ?? 0))
   .catch(() => {});
 }, []);

 useEffect(() => { load(days); }, [days, load]);

 // ── Loading ─────────────────────────────────────────────────────────────────
 if (loading) {
  return (
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.04]">
    <span className="font-label-caps text-label-caps text-on-surface-variant animate-pulse">
     Loading ROI metrics…
    </span>
   </div>
  );
 }

 // ── Error ───────────────────────────────────────────────────────────────────
 if (error || !data) {
  return (
   <div className="p-space-md rounded-lg bg-surface-container-low border border-error/20">
    <p className="font-mono-code text-mono-code text-error text-xs">
     {error ?? "No ROI data available yet. Complete a fix to start tracking."}
    </p>
   </div>
  );
 }

 // ── Headline KPI cards ──────────────────────────────────────────────────────
 const headlines = [
  {
   icon: <DollarSign className="w-5 h-5 text-primary-fixed" />,
   label: "TOTAL SAVED",
   value: data.headline.total_cost_saved,
   sub: "estimated (assumptions: $85/hr, 1.5h manual)",
  },
  {
   icon: <Clock className="w-5 h-5 text-primary-container" />,
   label: "HOURS SAVED",
   value: `${data.total_human_hours_saved}h`,
   sub: "estimated (assumptions: $85/hr, 1.5h manual)",
  },
  {
   icon: <TrendingDown className="w-5 h-5 text-tertiary-fixed" />,
   label: "MTTR REDUCTION",
   value: `${data.mttr_reduction_pct}%`,
   sub: data.headline.mttr_reduction_text,
  },
  {
   icon: <ShieldCheck className="w-5 h-5 text-error" />,
   label: "INCIDENTS PREVENTED",
   value: String(data.incidents_prevented),
   sub: data.headline.auto_rate,
  },
  // Phase 5: blocked incidents counter (additive — reads from escalations table)
  {
   icon: <ShieldCheck className="w-5 h-5 text-red-400" />,
   label: "BLOCKED BY POLICY",
   value: String(blockedCount),
   sub: blockedCount > 0 ? "High-risk patches withheld" : "No incidents blocked yet",
  },
 ];

 const langPieData = Object.entries(data.fixes_by_language).map(
  ([name, value]) => ({ name, value })
 );

 return (
  <div className="flex flex-col gap-space-md">

   {/* ── Section header ───────────────────────────────────────────────────── */}
   <div className="flex items-center justify-between">
    <div>
     <div className="flex items-center gap-2">
      <span className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1.5">
       <DollarSign className="w-3 h-3 text-primary-fixed" />
       ECONOMIC ROI TRACKER
      </span>
      {data.total_fixes === 45 && (
       <span className="text-[10px] font-mono-code bg-error/20 text-error border border-error/30 px-1.5 py-0.5 rounded font-semibold uppercase">
        DEMO DATA
       </span>
      )}
     </div>
     <h2 className="font-headline-lg text-headline-lg font-semibold text-on-surface">
      Mission Control — Cost & Reliability Metrics
     </h2>
     <p className="text-xs text-on-surface-variant mt-1 font-mono-code">
      Based on {data.total_fixes} incident{data.total_fixes === 1 ? "" : "s"}
     </p>
    </div>

    {/* Day range selector */}
    <div className="flex gap-1">
     {[7, 14, 30].map((d) => (
      <button
       key={d}
       onClick={() => setDays(d)}
       className={`px-space-sm py-space-2xs rounded-md font-label-caps text-label-caps transition-colors ${
        days === d
         ? "bg-primary-container/20 text-primary-fixed border border-primary-container/40"
         : "text-on-surface-variant hover:text-on-surface border border-transparent"
       }`}
      >
       {d}d
      </button>
     ))}
    </div>
   </div>

   {/* ── 4 headline KPI cards ─────────────────────────────────────────────── */}
   <div className="grid grid-cols-2 xl:grid-cols-4 gap-space-md">
    {headlines.map((h, i) => (
     <div
      key={i}
      className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col gap-space-sm"
     >
      <div className="flex items-center gap-space-xs">
       {h.icon}
       <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
        {h.label}
       </span>
      </div>
      <span className="font-mono-metric text-mono-metric text-2xl font-semibold text-on-surface">
       {h.value}
      </span>
      <span className="font-label-badge text-label-badge text-on-surface text-[10px] leading-snug">
       {h.sub}
      </span>
     </div>
    ))}
   </div>

   {/* ── Charts row ──────────────────────────────────────────────────────── */}
   <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">

    {/* Daily cost saved burndown */}
    <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
     <span className="font-label-caps text-label-caps text-on-surface-variant mb-3 block">
      COST SAVED — DAILY
     </span>
     {data.daily_hours_saved.length === 0 ? (
      <p className="font-body-sm text-body-sm text-on-surface-variant text-center pt-10">
       No data yet for this period.
      </p>
     ) : (
      <ResponsiveContainer width="100%" height={180}>
       <LineChart data={data.daily_hours_saved}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis
         dataKey="date"
         tick={{ fontSize: 9, fill: "rgba(255,255,255,0.4)" }}
         tickFormatter={(d: string) => d.slice(5)}
        />
        <YAxis tick={{ fontSize: 9, fill: "rgba(255,255,255,0.4)" }} />
        <Tooltip
         contentStyle={TOOLTIP_STYLE}
         formatter={(v) => [`$${v ?? 0}`, "Cost Saved"]}
        />
        <Line
         type="monotone"
         dataKey="cost_saved"
         stroke="#00ff87"
         strokeWidth={2}
         dot={false}
        />
       </LineChart>
      </ResponsiveContainer>
     )}
    </div>

    {/* Fixes by language — pie chart */}
    <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
     <span className="font-label-caps text-label-caps text-on-surface-variant mb-3 block">
      FIXES BY LANGUAGE
     </span>
     {langPieData.length === 0 ? (
      <p className="font-body-sm text-body-sm text-on-surface-variant text-center pt-10">
       No fixes recorded yet.
      </p>
     ) : (
      <ResponsiveContainer width="100%" height={180}>
       <PieChart>
        <Pie
         data={langPieData}
         cx="50%"
         cy="50%"
         outerRadius={72}
         dataKey="value"
         nameKey="name"
         label={({ name, percent }: { name?: string; percent?: number }) =>
          `${name ?? ""} ${Math.round((percent ?? 0) * 100)}%`
         }
         labelLine={false}
         fontSize={10}
        >
         {langPieData.map((_, i) => (
          <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
         ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
       </PieChart>
      </ResponsiveContainer>
     )}
    </div>
   </div>

   {/* ── Daily fix volume — stacked bar ────────────────────────────────────── */}
   <div className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
    <span className="font-label-caps text-label-caps text-on-surface-variant mb-3 block">
     DAILY FIX VOLUME — AUTOMATED vs. HUMAN-APPROVED
    </span>
    {data.daily_fixes.length === 0 ? (
     <p className="font-body-sm text-body-sm text-on-surface-variant text-center pt-6">
      No data yet for this period.
     </p>
    ) : (
     <ResponsiveContainer width="100%" height={150}>
      <BarChart data={data.daily_fixes} barSize={14}>
       <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
       <XAxis
        dataKey="date"
        tick={{ fontSize: 9, fill: "rgba(255,255,255,0.4)" }}
        tickFormatter={(d: string) => d.slice(5)}
       />
       <YAxis
        tick={{ fontSize: 9, fill: "rgba(255,255,255,0.4)" }}
        allowDecimals={false}
       />
       <Tooltip contentStyle={TOOLTIP_STYLE} />
       <Legend wrapperStyle={{ fontSize: 10, color: "rgba(255,255,255,0.5)" }} />
       <Bar
        dataKey="automated_count"
        name="Automated"
        fill="#22C55E"
        radius={[3, 3, 0, 0]}
       />
       <Bar
        dataKey="count"
        name="Total"
        fill="rgba(255,255,255,0.12)"
        radius={[3, 3, 0, 0]}
       />
      </BarChart>
     </ResponsiveContainer>
    )}
   </div>

   {/* ── Severity breakdown ───────────────────────────────────────────────── */}
   {Object.keys(data.fixes_by_severity).length > 0 && (
    <div className="grid grid-cols-3 gap-space-md">
     {(["LOW", "MEDIUM", "HIGH"] as SeverityKey[]).map((sev) => {
      const count = data.fixes_by_severity[sev] ?? 0;
      return (
       <div
        key={sev}
        className="p-space-md rounded-lg bg-surface-container-low border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col items-center gap-space-xs"
       >
        <span className="font-label-caps text-label-caps text-on-surface-variant text-[10px]">
         {sev} SEVERITY
        </span>
        <span
         className={`font-mono-metric text-mono-metric text-3xl font-bold ${SEVERITY_TOKEN[sev]}`}
        >
         {count}
        </span>
        <span className="font-label-badge text-label-badge text-on-surface-variant text-[10px]">
         fixes
        </span>
       </div>
      );
     })}
    </div>
   )}
  </div>
 );
}
