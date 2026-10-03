"use client";

import React from "react";
import type { TelemetryEvent } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

interface TelemetryConsoleProps {
 events?: TelemetryEvent[];
}

export const TelemetryConsole = React.memo(function TelemetryConsole({ events = [] }: TelemetryConsoleProps) {
  const sandboxFailed = events.some((e) => e.event_type === "test_failed" || (e.node === "SANDBOX" && e.status === "failed"));
  const sandboxCompleted = events.some((e) => e.event_type === "sandbox_completed" || e.event_type === "patch_validated" || (e.node === "SANDBOX" && e.status === "completed"));
  const sandboxStarted = events.some((e) => e.event_type === "sandbox_started" || (e.node === "SANDBOX" && e.status === "started"));

  const runtimeStatus = sandboxFailed
    ? "SANDBOX: FAILED"
    : sandboxCompleted
    ? "SANDBOX: VERIFIED"
    : sandboxStarted
    ? "SANDBOX: RUNNING"
    : "RUNTIME: READY";

  return (
    <div className="rounded-lg bg-surface-container-lowest p-space-md border border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
      <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-xs mb-space-sm">
        <div className="flex items-center gap-space-xs">
          <span className="w-2.5 h-2.5 rounded-full bg-error/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-tertiary-fixed-dim/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-primary-container/70" />
          <span className="font-label-caps text-label-caps text-on-surface-variant ml-space-xs">
            ISOLATED WORKSPACE SANDBOX [PYTEST -Q]
          </span>
        </div>
        <span
          className={`font-label-badge text-label-badge font-semibold ${
            sandboxFailed
              ? "text-error"
              : sandboxCompleted
              ? "text-primary-fixed"
              : "text-secondary-fixed"
          }`}
        >
          {runtimeStatus}
        </span>
      </div>

      <div className="font-mono-code text-mono-code text-xs text-on-surface-variant flex flex-col gap-1 max-h-48 overflow-y-auto">
        {events.length === 0 ? (
          <p className="text-on-surface-variant/60 italic py-2">
            Waiting for live execution telemetry...
          </p>
        ) : (
          events.map((event, idx) => (
            <p key={event.id ?? `${event.timestamp}-${idx}`}>
              <span className="text-primary-fixed">
                [{formatTimestamp(event.timestamp)}]
              </span>{" "}
              <span className="text-secondary-fixed">[{event.node}]:</span>{" "}
              <span
                className={
                  event.status === "failed"
                    ? "text-error"
                    : event.status === "completed"
                    ? "text-primary-fixed"
                    : "text-on-surface-variant"
                }
              >
                {event.message}
              </span>
            </p>
          ))
        )}
      </div>
    </div>
  );
});
