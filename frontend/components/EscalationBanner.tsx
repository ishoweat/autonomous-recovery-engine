import React, { useEffect, useState } from 'react';
import { ShieldX, AlertTriangle, ExternalLink, RotateCcw, Loader2, ChevronDown, ChevronUp } from 'lucide-react';

interface RiskFactor {
  factor?: string;
  name?: string;
  contribution?: number;
  value?: number;
  explanation?: string;
}

interface EscalationBannerProps {
  riskScore: number;
  topFactors?: RiskFactor[];
  issueUrl?: string | null;
  incidentId: string;
  failureReason?: string;
  onReset: () => void;
}

export function EscalationBanner({
  riskScore,
  topFactors = [],
  issueUrl,
  incidentId,
  failureReason = 'BLOCKED_BY_POLICY',
  onReset,
}: EscalationBannerProps) {
  const [expanded, setExpanded] = useState(false);
  const [pct] = useState(() => Math.round(riskScore * 100));

  const topTwo = topFactors.slice(0, 2);

  return (
    <div
      id={`escalation-banner-${incidentId}`}
      role="alert"
      className="rounded-xl border border-red-500/40 bg-gradient-to-br from-red-950/60 to-red-900/20 shadow-xl shadow-red-500/10 overflow-hidden mt-4"
    >
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-red-500/20 bg-red-950/40">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-red-500/20 border border-red-500/30 shrink-0">
            <ShieldX className="h-5 w-5 text-red-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-red-300 uppercase tracking-wider">
              Patch Blocked by Policy
            </h2>
            <p className="text-[11px] text-red-400/70 font-mono mt-0.5">
              {failureReason} · Incident {incidentId}
            </p>
          </div>
        </div>

        {/* Risk score badge */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-2xl font-mono font-bold text-red-400">
            {pct}%
          </span>
          <span className="text-[10px] font-mono text-red-500 uppercase">Risk Score</span>
        </div>
      </div>

      {/* ── Risk bar ──────────────────────────────────────────────── */}
      <div className="px-5 pt-3 pb-2">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-mono text-[10px] text-red-400/60 uppercase tracking-wider">Policy Threshold</span>
          <span className="font-mono text-[10px] text-red-400">Score {riskScore.toFixed(3)} / limit 0.700</span>
        </div>
        <div className="h-2.5 w-full rounded-full bg-red-950/40 border border-red-900/40 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-red-600 to-red-400 transition-all duration-1000"
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>

      {/* ── Top risk factors ──────────────────────────────────────── */}
      {topTwo.length > 0 && (
        <div className="px-5 pt-2 pb-3">
          <span className="text-[10px] font-mono text-red-400/60 uppercase tracking-wider block mb-2">
            Top Risk Drivers
          </span>
          <div className="grid grid-cols-2 gap-2">
            {topTwo.map((f, i) => (
              <div
                key={i}
                className="rounded-lg bg-red-950/30 border border-red-800/30 px-3 py-2"
              >
                <div className="text-[10px] text-red-400/70 font-mono uppercase">{f.factor || f.name || '?'}</div>
                <div className="text-sm font-mono font-semibold text-red-300 mt-0.5">
                  {Number(f.contribution ?? f.value ?? 0).toFixed(3)}
                </div>
                {f.explanation && (
                  <div className="text-[10px] text-red-500/60 mt-1 leading-relaxed line-clamp-2">
                    {f.explanation}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Expandable details ────────────────────────────────────── */}
      {topFactors.length > 2 && (
        <div className="px-5 pb-2">
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            className="flex items-center gap-1.5 text-[10px] font-mono text-red-400/60 hover:text-red-300 transition"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? 'Hide' : 'Show'} all {topFactors.length} factors
          </button>
          {expanded && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              {topFactors.slice(2).map((f, i) => (
                <div
                  key={i}
                  className="rounded-lg bg-red-950/20 border border-red-900/20 px-3 py-2"
                >
                  <div className="text-[10px] text-red-400/60 font-mono uppercase">{f.factor || f.name || '?'}</div>
                  <div className="text-sm font-mono text-red-400/80 mt-0.5">
                    {Number(f.contribution ?? f.value ?? 0).toFixed(3)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Footer actions ────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-red-500/20 bg-red-950/20">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
          <span className="text-[11px] text-red-400/80 leading-relaxed">
            Automated patch withheld. A human engineer must review and apply the fix manually.
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {issueUrl && (
            <a
              href={issueUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-900/30 px-3 py-1.5 text-[10px] font-mono text-red-300 hover:bg-red-900/60 transition"
            >
              <ExternalLink className="h-3 w-3" />
              View Issue
            </a>
          )}

          <button
            type="button"
            onClick={onReset}
            className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 font-mono text-[10px] text-slate-400 hover:text-white hover:bg-white/[0.06] transition"
          >
            <RotateCcw className="h-3 w-3" />
            Reset Investigation
          </button>
        </div>
      </div>
    </div>
  );
}
