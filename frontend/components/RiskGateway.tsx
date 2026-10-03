"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
 AlertTriangle,
 CheckCircle2,
 Lock,
 LockOpen,
 Shield,
 ShieldAlert,
 ShieldCheck,
 Sparkles,
} from "lucide-react";
import type { ExplainableRisk, RiskDecision } from "@/lib/types";
import { WhatHappensNextPanel } from "@/components/WhatHappensNextPanel";
import { approveIncident } from "@/lib/api";

interface RiskGatewayProps {
 risk?: ExplainableRisk | null;
 incidentId?: string;
 onAuthorize?: () => void;
 humanApproved?: boolean;
 prUrl?: string;
 repositoryUrl?: string;
 repositoryOwner?: string;
 repositoryName?: string;
 repositoryFullName?: string;
 defaultBranch?: string;
}

export function RiskGateway({
 risk,
 incidentId,
 onAuthorize,
 humanApproved = false,
 prUrl = "",
 repositoryUrl = "",
 repositoryOwner = "",
 repositoryName = "",
 repositoryFullName = "",
 defaultBranch = "",
}: RiskGatewayProps) {
 const router = useRouter();
 const [authorized, setAuthorized] = useState(humanApproved);
 const [isAuthorizing, setIsAuthorizing] = useState(false);
 const [noRepoError, setNoRepoError] = useState<string | null>(null);

 React.useEffect(() => {
  if (humanApproved) {
   setAuthorized(true);
  }
 }, [humanApproved]);

 const hasEvaluated = Boolean(risk && typeof risk.score === "number" && Number.isFinite(risk.score));
 const score = hasEvaluated ? risk!.score : 0.0;
 const rawDecision = risk?.decision;
 const decision: "ALLOW" | "APPROVE" | "BLOCK" | "PENDING" = hasEvaluated
  ? (rawDecision as "ALLOW" | "APPROVE" | "BLOCK") ?? (score > 0.7 ? "BLOCK" : score >= 0.3 ? "APPROVE" : "ALLOW")
  : "PENDING";

 const handleAuthorize = async () => {
  setIsAuthorizing(true);
  setNoRepoError(null);
  setAuthorized(true);
  if (onAuthorize) {
   onAuthorize();
  }

  try {
   if (incidentId) {
    await approveIncident(incidentId, true);
   }

   // If incidentId is provided, we are in the Incident Monitor view.
   // Seamlessly stay on current page while SSE pipeline handles recovery!
   if (incidentId) {
    setIsAuthorizing(false);
    return;
   }

   // Read stored repository context from props or localStorage for standalone wizard
   let storedRepo: any = null;
   if (typeof window !== "undefined") {
    try {
     const raw = localStorage.getItem("connected_repo");
     if (raw) storedRepo = JSON.parse(raw);
    } catch {}
   }

   const targetRepoUrl =
    repositoryUrl ||
    storedRepo?.repository_url ||
    (repositoryFullName || storedRepo?.full_name ? `https://github.com/${repositoryFullName || storedRepo?.full_name}` : "");
   
   const owner = repositoryOwner || storedRepo?.owner || (repositoryFullName.includes("/") ? repositoryFullName.split("/")[0] : "");
   const repo = repositoryName || storedRepo?.repo || (repositoryFullName.includes("/") ? repositoryFullName.split("/")[1] : "");
   const branch = defaultBranch || storedRepo?.default_branch || "main";
   const fullName = repositoryFullName || storedRepo?.full_name || (owner && repo ? `${owner}/${repo}` : "");

   if (!targetRepoUrl && !fullName && (!storedRepo || !storedRepo.full_name)) {
    setNoRepoError("No repository connected. Return to Mission Control to connect a repository.");
    setIsAuthorizing(false);
    return;
   }

   // Navigate to Detection Workspace passing repo context via search parameters
   const searchParams = new URLSearchParams();
   if (targetRepoUrl) searchParams.set("repoUrl", targetRepoUrl);
   if (owner) searchParams.set("owner", owner);
   if (repo) searchParams.set("repo", repo);
   if (branch) searchParams.set("branch", branch);

   router.push(`/detect?${searchParams.toString()}`);
  } catch (err: any) {
   setNoRepoError(err?.message || "Failed to authorize recovery with backend. Please retry.");
  } finally {
   setIsAuthorizing(false);
  }
 };

 // Derive breakdown from real backend risk breakdown or structural dimensions
 const breakdownFactors = risk?.breakdown && risk.breakdown.length > 0
  ? risk.breakdown.map((b) => {
    const isCoverage = b.factor.toLowerCase().includes("coverage") || b.factor.toLowerCase().includes("safety");
    let color = b.contribution > 0.2 ? "bg-error" : b.contribution > 0.1 ? "bg-secondary" : "bg-primary-container";
    let textColor = b.contribution > 0.2 ? "text-error" : b.contribution > 0.1 ? "text-secondary-fixed" : "text-primary-fixed";
    if (isCoverage) {
      color = b.contribution > 0.8 ? "bg-primary-container" : b.contribution > 0.5 ? "bg-secondary" : "bg-error";
      textColor = b.contribution > 0.8 ? "text-primary-fixed" : b.contribution > 0.5 ? "text-secondary-fixed" : "text-error";
    }
    return {
    name: b.factor,
    score: b.contribution,
    max: b.weight || 0.4,
    status: b.explanation || "Evaluated",
    color,
    textColor,
   }})
  : [
    {
     name: "File Criticality",
     score: risk ? risk.score * 0.4 : 0.0,
     max: 0.4,
     status: risk ? "Evaluated" : "Pending Analysis",
     color: "bg-secondary",
     textColor: "text-secondary-fixed",
    },
    {
     name: "Patch Size",
     score: risk ? risk.score * 0.2 : 0.0,
     max: 0.3,
     status: risk ? "Evaluated" : "Pending Analysis",
     color: "bg-primary-container",
     textColor: "text-primary-fixed",
    },
    {
     name: "Test Coverage",
     score: risk ? 0.0 : 0.0,
     max: 0.3,
     status: risk ? "Verified" : "Pending Sandbox",
     color: "bg-primary-container",
     textColor: "text-primary-fixed",
    },
    {
     name: "Change Surface",
     score: risk ? risk.score * 0.4 : 0.0,
     max: 0.3,
     status: risk ? "Evaluated" : "Pending Analysis",
     color: "bg-secondary",
     textColor: "text-secondary-fixed",
    },
   ];

 return (
  <div className="flex flex-col gap-space-md">
   {/* Visual Risk Card */}
   <div className="p-space-md rounded-lg bg-surface-container-low shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col gap-space-md relative overflow-hidden border border-white/[0.08]">
    {/* Header */}
    <div className="flex items-center justify-between">
     <div className="flex flex-col">
      <span className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1.5">
       <Shield className="w-3 h-3 text-secondary-fixed" />
       VISUAL RISK GATEWAY
      </span>
      <span className="font-headline-md text-headline-md font-semibold text-on-surface">
       Pre-Execution Risk Assessment
      </span>
     </div>
     <div className="w-9 h-9 rounded-lg bg-surface-container flex items-center justify-center text-primary-fixed border border-white/[0.06]">
      {authorized ? (
       <ShieldCheck className="w-5 h-5 text-primary-fixed" />
      ) : decision === "BLOCK" ? (
       <ShieldAlert className="w-5 h-5 text-error" />
      ) : (
       <Shield className="w-5 h-5 text-secondary-fixed" />
      )}
     </div>
    </div>

    {/* Aggregate Risk Score Card */}
    <div className="flex items-center justify-between p-space-md rounded-lg bg-surface-container-lowest shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
     <div className="flex flex-col">
      <span className="font-label-caps text-label-caps text-on-surface-variant">
       AGGREGATE RISK SCORE
      </span>
      <div className="flex items-baseline gap-1 mt-1">
       <span className="font-mono-metric text-mono-metric text-2xl font-semibold text-primary-container">
        {hasEvaluated ? score.toFixed(2) : "0.00"}
       </span>
       <span className="font-mono-code text-mono-code text-on-surface-variant text-sm">
        / 1.00 {hasEvaluated ? "" : "(Pending)"}
       </span>
      </div>
     </div>
     <div
      className={`flex items-center gap-space-xs px-space-md py-space-xs rounded-lg font-label-caps text-label-caps border font-bold ${
       decision === "ALLOW"
        ? "bg-primary-container/20 text-primary-fixed border-primary-container/40"
        : decision === "APPROVE"
         ? "bg-secondary/20 text-secondary-fixed border-secondary/40"
         : decision === "BLOCK"
          ? "bg-error/20 text-error border-error/40"
          : "bg-surface-container/60 text-on-surface-variant border-white/10"
      }`}
     >
      {decision === "ALLOW" ? (
       <CheckCircle2 className="w-4 h-4" />
      ) : decision === "APPROVE" ? (
       <ShieldCheck className="w-4 h-4" />
      ) : decision === "BLOCK" ? (
       <AlertTriangle className="w-4 h-4" />
      ) : (
       <Shield className="w-4 h-4" />
      )}
      <span>{decision === "APPROVE" ? "APPROVAL REQUIRED" : decision === "PENDING" ? "PENDING ANALYSIS" : decision}</span>
     </div>
    </div>

     {/* 4 Scoring Breakdown Bars */}
    <div className="flex flex-col gap-3">
     <span className="font-label-caps text-label-caps text-on-surface-variant flex items-center justify-between">
      <span>RISK FACTOR BREAKDOWN (4 DIMENSIONS)</span>
      <span className="text-[10px] text-primary-fixed">LIVE POLICY GATE</span>
     </span>

     {breakdownFactors.map((factor) => {
      const pct = Math.min(100, Math.round((factor.score / factor.max) * 100));

      return (
       <div key={factor.name} className="flex flex-col gap-1">
        <div className="flex justify-between font-mono-code text-xs">
         <span className="text-on-surface">{factor.name}</span>
         <span className={factor.textColor}>
          {factor.score.toFixed(2)} ({factor.status})
         </span>
        </div>
        <div className="w-full bg-surface-container-highest h-2 rounded-full overflow-hidden" title={factor.status}>
         <div
          className={`${factor.color} h-full transition-all duration-500`}
          style={{ width: `${Math.max(4, pct)}%` }}
         />
        </div>
       </div>
      );
     })}
    </div>

    {/* Human Checkpoint Status Banner */}
    <div
     className={`p-space-md rounded-lg flex items-start gap-space-sm border ${
      authorized
       ? "bg-primary-container/10 border-primary-container/30"
       : "bg-surface-container border-secondary/30"
     }`}
    >
     <div className="mt-0.5">
      {authorized ? (
       <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
      ) : (
       <Lock className="w-4 h-4 text-secondary-fixed" />
      )}
     </div>
     <div className="flex flex-col">
      <span
       className={`font-label-caps text-label-caps font-semibold ${
        authorized ? "text-primary-fixed" : "text-secondary-fixed"
       }`}
      >
       {authorized ? "HUMAN AUTHORIZATION GRANTED" : "HUMAN APPROVAL GATEWAY"}
      </span>
      <p className="font-body-sm text-xs text-on-surface-variant mt-0.5 leading-relaxed">
       {authorized
        ? "SRE Operator verified and authorized production branch merge. Automated GitHub PR ready."
        : "Risk policy gateway requires explicit human operator sign-off before committing to the repository."}
      </p>
     </div>
    </div>

    {/* Authorize Button */}
    <button
     onClick={handleAuthorize}
     disabled={authorized || isAuthorizing || decision === "BLOCK" || decision === "PENDING"}
     className={`w-full py-space-sm rounded-lg font-label-caps text-label-caps font-bold transition-all flex items-center justify-center gap-space-xs ${
      authorized
       ? "bg-secondary-fixed/20 text-secondary-fixed border border-secondary-fixed/40 cursor-default"
       : decision === "BLOCK"
        ? "bg-error/20 text-error border border-error/40 cursor-not-allowed"
        : decision === "PENDING"
         ? "bg-surface-container text-on-surface-variant/60 border border-white/10 cursor-not-allowed"
         : "bg-primary hover:bg-primary/90 text-white active:scale-[0.98]"
     }`}
    >
     {isAuthorizing ? (
      <span>AUTHORIZING...</span>
     ) : authorized ? (
      <>
       <LockOpen className="w-4 h-4 text-secondary-fixed" />
       <span>GATE UNLOCKED • DISPATCHING PR</span>
      </>
     ) : decision === "BLOCK" ? (
      <>
       <AlertTriangle className="w-4 h-4 text-error" />
       <span>EXECUTION BLOCKED BY POLICY</span>
      </>
     ) : decision === "PENDING" ? (
      <>
       <Shield className="w-4 h-4 text-on-surface-variant/60" />
       <span>AWAITING RISK ASSESSMENT</span>
      </>
     ) : (
      <>
       <ShieldCheck className="w-4 h-4" />
       <span>APPROVE & DISPATCH PR</span>
      </>
     )}
    </button>

    {noRepoError && (
     <div className="bg-error/10 border border-error/30 text-error p-space-sm rounded-lg font-mono-code text-xs flex items-center gap-2 mt-2">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>{noRepoError}</span>
     </div>
    )}
   </div>

   {/* "What Happens Next" Panel */}
   <WhatHappensNextPanel
    isApproved={authorized}
    incidentId={incidentId}
    prUrl={prUrl}
   />
  </div>
 );
}
