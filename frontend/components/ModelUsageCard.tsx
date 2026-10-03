import React, { useMemo } from "react";
import { Server, Zap, Cpu, CircleDollarSign } from "lucide-react";

interface ModelUsageEvent {
  step: string;
  model: string;
  latency: number;
  tokens: number | null;
  est_cost: number | null;
  timestamp: string;
}

interface ModelUsageCardProps {
  events: any[];
}

export function ModelUsageCard({ events }: ModelUsageCardProps) {
  const usageEvents = useMemo(() => {
    const list: ModelUsageEvent[] = [];
    events.forEach((ev) => {
      const meta = ev.metadata?.inference;
      if (meta && meta.success) {
        let step = ev.event_type;
        if (ev.event_type === "triage_completed") step = "Triage";
        else if (ev.event_type === "root_cause_identified") step = "Root Cause";
        else if (ev.event_type === "patch_generated") step = "Patch Gen";
        
        list.push({
          step,
          model: meta.model || "Unknown",
          latency: meta.latency || 0,
          tokens: meta.token_usage?.total_tokens || null,
          est_cost: meta.est_cost || null,
          timestamp: ev.timestamp,
        });
      }
    });
    return list.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }, [events]);

  if (usageEvents.length === 0) return null;

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-4 pb-2 border-b border-white/[0.06]">
        <Server className="h-4 w-4 text-purple-400" />
        <span className="font-mono text-xs font-semibold text-purple-300">
          Model Inference Telemetry
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[11px] font-mono text-slate-300">
          <thead className="text-slate-500 border-b border-white/[0.04]">
            <tr>
              <th className="pb-2 font-medium">Step</th>
              <th className="pb-2 font-medium">Model ID</th>
              <th className="pb-2 font-medium">Latency</th>
              <th className="pb-2 font-medium">Tokens</th>
              <th className="pb-2 font-medium">Est. Cost</th>
            </tr>
          </thead>
          <tbody>
            {usageEvents.map((u, i) => (
              <tr key={i} className="border-b border-white/[0.02] last:border-0 hover:bg-white/[0.01]">
                <td className="py-2.5 text-purple-300">{u.step}</td>
                <td className="py-2.5">{u.model}</td>
                <td className="py-2.5">{u.latency.toFixed(2)}s</td>
                <td className="py-2.5">{u.tokens ? u.tokens.toLocaleString() : "-"}</td>
                <td className="py-2.5">{u.est_cost !== null ? `$${u.est_cost.toFixed(6)}` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
