import React, { useState } from 'react';
import { ShieldAlert, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import type { RecoveryState } from '@/lib/types';

interface ApprovalPanelProps {
  state: Partial<RecoveryState>;
  onApprove: () => void;
  onReject: () => void;
  isLoading: boolean;
  error?: string | null;
}

export function ApprovalPanel({ state, onApprove, onReject, isLoading, error }: ApprovalPanelProps) {
  const risk = (state.explainable_risk as any) || {};
  const score = risk.score ?? 0;
  const breakdown = risk.breakdown || [];
  
  // Convert breakdown array if it is an array
  const factors = Array.isArray(breakdown) ? breakdown : [];

  return (
    <div className="rounded-xl border border-warning/30 bg-warning/5 overflow-hidden mt-4">
      <div className="border-b border-warning/20 bg-warning/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-warning" />
          <h2 className="text-sm font-semibold text-warning uppercase tracking-wider">
            Operator Approval Required
          </h2>
        </div>
        <div className="text-xs font-mono bg-warning/20 text-warning-container px-2 py-1 rounded">
          Risk Score: {Number(score).toFixed(2)}
        </div>
      </div>
      
      <div className="p-6 space-y-6">
        {factors.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Risk Factors
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {factors.map((f: any) => (
                <div key={f.factor || f.name} className="bg-surface-container-low border border-white/[0.04] p-3 rounded-lg">
                  <div className="text-[10px] text-slate-500 uppercase">{f.factor || f.name}</div>
                  <div className="mt-1 text-sm font-mono text-white">
                    {f.value !== undefined ? Number(f.value).toFixed(2) : 'N/A'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {state.current_patch_diff && (
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Proposed Patch Diff
            </h3>
            <div className="bg-[#0A0D12] border border-white/[0.08] p-3 rounded-lg overflow-x-auto max-h-48 text-xs font-mono">
              {state.current_patch_diff.split('\n').map((line, idx) => (
                <div key={idx} className={
                  line.startsWith('+') ? 'text-emerald-400 bg-emerald-950/20' : 
                  line.startsWith('-') ? 'text-red-400 bg-red-950/20' : 
                  'text-slate-400'
                }>
                  {line}
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-red-400 bg-red-950/30 border border-red-500/20 rounded-lg p-3">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3 justify-end pt-4 border-t border-white/[0.04]">
          <button
            onClick={onReject}
            disabled={isLoading}
            aria-label="Reject Fix"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-red-500/30 text-red-400 hover:bg-red-500/10 disabled:opacity-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
            Reject Fix
          </button>
          
          <button
            onClick={onApprove}
            disabled={isLoading}
            aria-label="Approve and Proceed"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Approve & Proceed
          </button>
        </div>
      </div>
    </div>
  );
}
