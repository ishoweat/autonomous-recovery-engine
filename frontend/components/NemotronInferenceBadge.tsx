"use client";

import React from "react";
import { Cpu, AlertTriangle, Clock } from "lucide-react";
import { ModelInferenceTelemetry } from "@/lib/api";

interface NemotronInferenceBadgeProps {
  inference?: ModelInferenceTelemetry | null;
  defaultModel?: string;
  isStreaming?: boolean;
}

export const NemotronInferenceBadge: React.FC<NemotronInferenceBadgeProps> = ({
  inference,
  defaultModel = "nvidia/Nemotron-3_5-Lightning",
  isStreaming = false,
}) => {
  const provider = inference?.provider || "Nebius Token Factory";
  const model = inference?.model || defaultModel;
  const isError = inference?.success === false || inference?.inference_status === "ERROR";
  const hasInference = Boolean(inference && inference.success && inference.inference_status !== "ERROR");
  
  const statusLabel = isError ? "ERROR" : isStreaming ? "INFERRING..." : hasInference ? "VERIFIED INFERENCE" : "IDLE";
  const latency = inference?.latency !== undefined ? `${inference.latency.toFixed(2)}s` : isStreaming ? "Computing..." : "—";
  const inferenceStatus = isError ? "FAILED" : isStreaming ? "IN_PROGRESS" : hasInference ? (inference?.inference_status || "RECEIVED") : "READY";

  return (
    <div
      className={`inline-flex flex-wrap items-center gap-2.5 px-3 py-1.5 rounded-lg font-mono text-[11px] border transition-all ${
        isError
          ? "bg-red-950/40 border-red-800/60 text-red-300"
          : hasInference
          ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.12)]"
          : isStreaming
          ? "bg-amber-950/40 border-amber-500/40 text-amber-300"
          : "bg-surface-container-high/80 border-white/[0.08] text-slate-300"
      }`}
    >
      {/* NEMOTRON Brand */}
      <div className="flex items-center gap-1.5 font-bold tracking-wider text-emerald-400">
        <Cpu className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
        <span className="uppercase font-semibold">NEMOTRON</span>
      </div>

      <span className="text-white/20">|</span>

      {/* Provider */}
      <div className="flex items-center gap-1">
        <span className="text-slate-400">Provider:</span>
        <span className="text-slate-100 font-medium">{provider}</span>
      </div>

      <span className="text-white/20">|</span>

      {/* Model */}
      <div className="flex items-center gap-1">
        <span className="text-slate-400">Model:</span>
        <span className="text-emerald-300 font-semibold">{model}</span>
      </div>

      <span className="text-white/20">|</span>

      {/* Status */}
      <div className="flex items-center gap-1">
        <span className="text-slate-400">Status:</span>
        <span
          className={`font-bold flex items-center gap-1 ${
            isError ? "text-red-400" : hasInference ? "text-emerald-400" : isStreaming ? "text-amber-400" : "text-slate-400"
          }`}
        >
          {isError ? (
            <AlertTriangle className="h-3 w-3 shrink-0" />
          ) : hasInference ? (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
          ) : isStreaming ? (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
          ) : null}
          {statusLabel}
        </span>
      </div>

      <span className="text-white/20">|</span>

      {/* Latency */}
      <div className="flex items-center gap-1">
        <Clock className="h-3 w-3 text-slate-400 shrink-0" />
        <span className="text-slate-400">Latency:</span>
        <span className="text-amber-300 font-medium">{latency}</span>
      </div>

      <span className="text-white/20">|</span>

      {/* Inference */}
      <div className="flex items-center gap-1">
        <span className="text-slate-400">Inference:</span>
        <span
          className={`font-semibold uppercase ${
            isError
              ? "text-red-400"
              : hasInference
              ? "text-emerald-300 font-bold"
              : isStreaming
              ? "text-amber-300 font-bold"
              : "text-slate-400"
          }`}
        >
          {inferenceStatus}
        </span>
      </div>

      {/* Request ID if present */}
      {inference?.request_id ? (
        <>
          <span className="text-white/20">|</span>
          <span className="text-slate-400 text-[10px]" title={`Request ID: ${inference.request_id}`}>
            id: {inference.request_id.slice(-8)}
          </span>
        </>
      ) : null}

      {/* Token count tag if present */}
      {inference?.token_usage?.total_tokens ? (
        <>
          <span className="text-white/20">|</span>
          <span className="text-slate-400 text-[10px]">
            {inference.token_usage.total_tokens.toLocaleString()} tokens
          </span>
        </>
      ) : null}
    </div>
  );
};
