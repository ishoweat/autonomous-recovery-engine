"use client";

import React from "react";
import type { RecoveryNode, RecoveryState, TelemetryEvent } from "@/lib/types";

interface WorkflowPipelineProps {
 currentNode?: RecoveryNode | string;
 isCompleted?: boolean;
 state?: RecoveryState | null;
 events?: TelemetryEvent[];
}

export const WorkflowPipeline = React.memo(function WorkflowPipeline({
 currentNode = "TRIAGE",
 isCompleted = false,
 state,
 events = []
}: WorkflowPipelineProps) {
  // Internal node for UI timing control
  const [displayNode, setDisplayNode] = React.useState<string>(currentNode);

  // Apply delays based on stage transitions
  React.useEffect(() => {
    const prev = displayNode.toUpperCase();
    const next = String(currentNode).toUpperCase();
    if (prev === next) return;
    let delay = 0;
    // Detect -> Reason (1s)
    if (prev === "START" || prev === "TRIAGE") {
      delay = 1000;
    } else if (prev === "ROOT_CAUSE" || prev === "REPAIR") {
      // Reason -> Verify (2s)
      delay = 2000;
    } else if (prev === "SANDBOX" || prev === "FAILURE_ANALYZER") {
      // Verify -> Recover (2s)
      delay = 2000;
    } else if (prev === "COMPLETE" || prev === "RECOVERY_COMPLETE") {
      // Recover -> Live Recovery page (2s)
      delay = 2000;
    }
    const timer = setTimeout(() => setDisplayNode(currentNode), delay);
    return () => clearTimeout(timer);
  }, [currentNode]);
   const normalizedNode = String(displayNode).toUpperCase();

 // Determine stage active/completed states
 const isDetectActive =
  normalizedNode === "START" ||
  normalizedNode === "TRIAGE";
 const isDetectDone =
  normalizedNode !== "START" && normalizedNode !== "TRIAGE";

 const isReasonActive =
  normalizedNode === "ROOT_CAUSE" ||
  normalizedNode === "REPAIR";
 const isReasonDone =
  isDetectDone &&
  normalizedNode !== "ROOT_CAUSE" &&
  normalizedNode !== "REPAIR";

 const isVerifyActive =
  normalizedNode === "SANDBOX" ||
  normalizedNode === "FAILURE_ANALYZER";
 const isVerifyDone =
  isReasonDone &&
  normalizedNode !== "SANDBOX" &&
  normalizedNode !== "FAILURE_ANALYZER";

 const isRecoverActive =
  normalizedNode === "RISK_GATEWAY" ||
  normalizedNode === "POLICY_RISK_GATEWAY" ||
  normalizedNode === "DECISION_ROUTER" ||
  normalizedNode === "HUMAN_APPROVAL" ||
  normalizedNode === "HUMAN_APPROVAL_NODE" ||
  normalizedNode === "APPROVAL" ||
  normalizedNode === "RECOVERY_COMPLETE" ||
  normalizedNode === "RECOVERY_COMPLETE_NODE" ||
  normalizedNode === "GITHUB" ||
  normalizedNode === "COMPLETE" ||
  Boolean(state?.pr_url) ||
  isCompleted;

 // Extract live metrics from state & events
 const triageEvent = events.find((e) => e.stage === "triage" || e.node === "TRIAGE");
 const reasonEvent = events.find((e) => e.stage === "root_cause" || e.node === "ROOT_CAUSE");
 const testResults = state?.test_results;
 const prUrl = state?.pr_url;
 const confidence = state?.root_cause_analysis?.confidence;

 return (
  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-space-md">
   {/* Stage 1: Detect */}
   <div
    className={`relative p-space-md rounded-lg flex flex-col justify-between overflow-hidden transition-all border ${
     isDetectActive
      ? "bg-surface-container-high border-primary/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]"
      : "bg-surface-container-low border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] hover:bg-surface-container"
    }`}
   >
    {isDetectActive && (
     <div className="absolute top-0 left-0 right-0 h-1 bg-primary" />
    )}
    <div className="flex items-start justify-between">
     <div
      className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
       isDetectActive
        ? "bg-surface-container-lowest text-primary border-primary/30"
        : "bg-surface-container text-on-surface-variant border-white/[0.08]"
      }`}
     >
      <span className="material-symbols-outlined text-[22px]">radar</span>
     </div>
     <span
      className={`px-space-xs py-space-2xs rounded font-label-badge text-label-badge tracking-wide flex items-center gap-1 border ${
       isDetectActive
        ? "bg-primary-container/20 text-primary-fixed border-primary/30"
        : "bg-surface-container-highest text-on-surface-variant border-white/[0.08]"
      }`}
     >
      {isDetectActive && (
       <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
      )}
      {isDetectActive ? "ACTIVE STAGE" : isDetectDone ? "COMPLETED" : "STANDBY"}
     </span>
    </div>
    <div className="mt-space-md">
     <div className="flex items-center justify-between">
      <span className="font-headline-md text-headline-md font-semibold text-primary">
       01. Detect
      </span>
      <span className="font-label-caps text-label-caps text-primary-fixed">
       {isDetectDone ? "COMPLETED" : isDetectActive ? "INGESTING" : "STANDBY"}
      </span>
     </div>
     <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
      {state?.triage_context
       ? `Ingested failure: ${state.triage_context.slice(0, 75)}...`
       : "Ingest telemetry & explore GitHub repos. Live failure context parsing."}
     </p>
    </div>
    <div className="mt-space-md pt-space-xs flex items-center justify-between font-mono-code text-mono-code text-xs text-on-surface-variant/80 border-t border-surface-container-highest">
     <span>{triageEvent ? "Stream: Active" : "Telemetry: Live"}</span>
     <span className="text-primary-fixed font-semibold">
      {isDetectDone ? "Parsed" : isDetectActive ? "Analyzing" : "Standby"}
     </span>
    </div>
   </div>

   {/* Stage 2: Reason */}
   <div
    className={`relative p-space-md rounded-lg flex flex-col justify-between overflow-hidden transition-all border ${
     isReasonActive
      ? "bg-surface-container-high border-secondary/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]"
      : "bg-surface-container-low border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] hover:bg-surface-container"
    }`}
   >
    {isReasonActive && (
     <div className="absolute top-0 left-0 right-0 h-1 bg-secondary-fixed" />
    )}
    <div className="flex items-start justify-between">
     <div
      className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
       isReasonActive
        ? "bg-surface-container-lowest text-secondary-fixed border-secondary/30"
        : "bg-surface-container text-secondary border-white/[0.08]"
      }`}
     >
      <span className="material-symbols-outlined text-[22px]">psychology</span>
     </div>
     <span
      className={`px-space-xs py-space-2xs rounded font-label-badge text-label-badge tracking-wide border ${
       isReasonActive
        ? "bg-secondary/20 text-secondary-fixed border-secondary/30"
        : "bg-surface-container-highest text-on-surface-variant border-white/[0.08]"
      }`}
     >
      {isReasonActive ? "PROCESSING" : isReasonDone ? "COMPLETED" : "STANDBY"}
     </span>
    </div>
    <div className="mt-space-md">
     <div className="flex items-center justify-between">
      <span className="font-headline-md text-headline-md font-semibold text-on-surface">
       02. Reason
      </span>
      <span className="font-label-caps text-label-caps text-secondary-fixed">
       {state?.runtime_model ? state.runtime_model.split("/").pop()?.toUpperCase() : "NEMOTRON"}
      </span>
     </div>
     <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
      {state?.root_cause_analysis?.summary
       ? `Root cause: ${state.root_cause_analysis.summary.slice(0, 75)}...`
       : "LangGraph Nemotron AI root cause diagnosis & patch generation."}
     </p>
    </div>
    <div className="mt-space-md pt-space-xs flex items-center justify-between font-mono-code text-mono-code text-xs text-on-surface-variant/80 border-t border-surface-container-highest">
     <span>{confidence ? `Confidence: ${(confidence * 100).toFixed(0)}%` : "Model: Nemotron"}</span>
     <span className="text-secondary-fixed font-semibold">
      {state?.current_patch_diff ? "Patch Generated" : isReasonActive ? "Drafting" : "Standby"}
     </span>
    </div>
   </div>

   {/* Stage 3: Verify */}
   <div
    className={`relative p-space-md rounded-lg flex flex-col justify-between overflow-hidden transition-all border ${
     isVerifyActive
      ? "bg-surface-container-high border-tertiary/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]"
      : "bg-surface-container-low border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] hover:bg-surface-container"
    }`}
   >
    {isVerifyActive && (
     <div className="absolute top-0 left-0 right-0 h-1 bg-tertiary" />
    )}
    <div className="flex items-start justify-between">
     <div
      className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
       isVerifyActive
        ? "bg-surface-container-lowest text-tertiary border-tertiary/30"
        : "bg-surface-container text-tertiary-fixed-dim border-white/[0.08]"
      }`}
     >
      <span className="material-symbols-outlined text-[22px]">terminal</span>
     </div>
     <span className="px-space-xs py-space-2xs rounded font-label-badge text-label-badge bg-surface-container-highest text-on-surface-variant tracking-wide border border-white/[0.08]">
      {isVerifyActive ? "TESTING" : isVerifyDone ? "VERIFIED" : "STANDBY"}
     </span>
    </div>
    <div className="mt-space-md">
     <div className="flex items-center justify-between">
      <span className="font-headline-md text-headline-md font-semibold text-on-surface">
       03. Verify
      </span>
      <span className="font-label-caps text-label-caps text-on-surface-variant">
       SANDBOX
      </span>
     </div>
     <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
      {testResults
       ? (testResults.exit_code === 0 ? "Pytest regression tests passed with zero failures in isolated sandbox." : `Sandbox execution finished with exit code ${testResults.exit_code}.`)
       : "Isolated Docker container tests & adversarial resilience validation."}
     </p>
    </div>
    <div className="mt-space-md pt-space-xs flex items-center justify-between font-mono-code text-mono-code text-xs text-on-surface-variant/80 border-t border-surface-container-highest">
     <span>Sandbox: {testResults ? (testResults.exit_code === 0 ? "Exit 0 (Success)" : `Exit ${testResults.exit_code}`) : (isVerifyActive ? "Executing" : "Standby")}</span>
     <span className={testResults?.exit_code === 0 ? "text-primary-fixed font-semibold" : "text-on-surface-variant"}>
      {testResults?.exit_code === 0 ? "Verified" : isVerifyActive ? "Running" : "Standby"}
     </span>
    </div>
   </div>

   {/* Stage 4: Recover */}
   <div
    className={`relative p-space-md rounded-lg flex flex-col justify-between overflow-hidden transition-all border ${
     isRecoverActive
      ? "bg-surface-container-high border-primary/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]"
      : "bg-surface-container-low border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.4)] hover:bg-surface-container"
    }`}
   >
    {isRecoverActive && (
     <div className="absolute top-0 left-0 right-0 h-1 bg-primary" />
    )}
    <div className="flex items-start justify-between">
     <div className="w-10 h-10 rounded-lg bg-surface-container flex items-center justify-center text-on-surface-variant border border-white/[0.08]">
      <span className="material-symbols-outlined text-[22px]">merge</span>
     </div>
     <span
      className={`px-space-xs py-space-2xs rounded font-label-badge text-label-badge tracking-wide border ${
       prUrl
        ? "bg-primary-container/20 text-primary-fixed border-primary/30"
        : isRecoverActive
        ? "bg-primary-container/20 text-primary-fixed border-primary/30"
        : "bg-surface-container-highest text-on-surface-variant border-white/[0.08]"
      }`}
     >
      {prUrl ? "COMPLETED" : state?.human_approved ? "APPROVED" : isRecoverActive ? "AWAITING APPROVAL" : "GATED"}
     </span>
    </div>
    <div className="mt-space-md">
     <div className="flex items-center justify-between">
      <span className="font-headline-md text-headline-md font-semibold text-on-surface">
       04. Recover
      </span>
      <span className="font-label-caps text-label-caps text-on-surface-variant">
       PR &amp; ROLLOUT
      </span>
     </div>
     <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
      {prUrl
       ? `Pull request opened & verified: ${prUrl}`
       : "Commit verified fix, assemble cryptographic audit trail, and dispatch GitHub PR."}
     </p>
    </div>
    <div className="mt-space-md pt-space-xs flex items-center justify-between font-mono-code text-mono-code text-xs text-on-surface-variant/80 border-t border-surface-container-highest">
     <span>Policy: {state?.action_decision || "Risk Evaluated"}</span>
     <span className={prUrl ? "text-primary-fixed font-semibold" : "text-on-surface-variant"}>
      {prUrl ? (state?.pr_number ? `PR #${state.pr_number} (COMPLETED)` : "COMPLETED") : "Pending"}
     </span>
    </div>
   </div>
  </div>
 );
});
