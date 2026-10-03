"use client";

import React from "react";
import {
 Brain,
 CheckCircle2,
 ChevronRight,
 GitPullRequest,
 ShieldCheck,
 Sparkles,
 Terminal,
} from "lucide-react";

interface WhatHappensNextPanelProps {
 isApproved: boolean;
 incidentId?: string;
 prUrl?: string;
}

export function WhatHappensNextPanel({
 isApproved,
 incidentId,
 prUrl,
}: WhatHappensNextPanelProps) {
 const steps = [
  {
   step: "01",
   title: "Docker Sandbox Verification",
   desc: "Executes isolated pytest suite with new regression test to confirm zero side-effects.",
   icon: Terminal,
   status: isApproved ? "completed" : "ready",
  },
  {
   step: "02",
   title: "Git Commit & Branch Push",
   desc: "Creates dedicated `fix/inc-remediation` branch with clear semantic commit history.",
   icon: ShieldCheck,
   status: isApproved ? "completed" : "ready",
  },
  {
   step: "03",
   title: "GitHub Pull Request Dispatched",
   desc: "Opens automated PR containing Nemotron RCA, patch diff, and risk breakdown.",
   icon: GitPullRequest,
   status: isApproved ? "active" : "pending",
   link: prUrl,
  },
  {
   step: "04",
   title: "Knowledge Base Memory Indexing",
   desc: "Saves root cause pattern and validated fix diff for future sub-second incident recall.",
   icon: Brain,
   status: isApproved ? "completed" : "pending",
  },
 ];

 return (
  <div className="p-space-md rounded-lg bg-surface-container-low shadow-[0_1px_3px_rgba(0,0,0,0.4)] flex flex-col gap-space-sm border border-white/[0.08]">
   <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-xs">
    <div className="flex items-center gap-2">
     <div className="p-1 rounded bg-primary-container/20 text-primary-fixed">
      <Sparkles className="w-4 h-4" />
     </div>
     <div>
      <span className="font-label-caps text-label-caps text-primary-fixed block">
       POST-APPROVAL LIFECYCLE
      </span>
      <span className="font-headline-md text-headline-md font-semibold text-on-surface">
       What Happens Next
      </span>
     </div>
    </div>
    <span
     className={`font-label-badge text-label-badge px-2 py-0.5 rounded border ${
      isApproved
       ? "bg-primary-container/20 text-primary-fixed border-primary-container/40"
       : "bg-surface-container text-on-surface-variant border-white/[0.06]"
     }`}
    >
     {isApproved ? "EXECUTION IN PROGRESS" : "AWAITING AUTHORIZATION"}
    </span>
   </div>

   <p className="font-body-sm text-body-sm text-on-surface-variant">
    {isApproved
     ? "Human approval granted. The engine is safely executing the following autonomous remediation pipeline:"
     : "Upon human approval, the engine will execute the following safe end-to-end recovery sequence:"}
   </p>

   <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
    {steps.map((item) => {
     const Icon = item.icon;
     const isDone = item.status === "completed";
     const isActive = item.status === "active";

     return (
      <div
       key={item.step}
       className={`p-3 rounded-lg border transition-all flex flex-col justify-between ${
        isDone
         ? "bg-surface-container-lowest/80 border-primary-container/30"
         : isActive
          ? "bg-surface-container-lowest border-secondary/40"
          : "bg-surface-container-lowest/40 border-white/[0.04]"
       }`}
      >
       <div className="flex items-start gap-2.5">
        <div
         className={`p-2 rounded-lg shrink-0 mt-0.5 ${
          isDone
           ? "bg-primary-container/20 text-primary-fixed"
           : isActive
            ? "bg-secondary/20 text-secondary-fixed animate-pulse"
            : "bg-surface-container text-on-surface-variant"
         }`}
        >
         <Icon className="w-4 h-4" />
        </div>
        <div className="flex flex-col">
         <div className="flex items-center gap-1.5">
          <span className="font-mono-code text-[11px] font-semibold text-on-surface-variant">
           {item.step}
          </span>
          <span className="font-headline-md text-xs font-semibold text-on-surface">
           {item.title}
          </span>
         </div>
         <p className="font-body-sm text-[11px] text-on-surface-variant mt-1 leading-normal">
          {item.desc}
         </p>
        </div>
       </div>

       {item.link ? (
        <a
         href={item.link}
         target="_blank"
         rel="noopener noreferrer"
         className="mt-2 flex items-center justify-between text-[11px] font-mono-code text-primary-fixed bg-primary-container/10 px-2 py-1 rounded hover:bg-primary-container/20 transition-colors"
        >
         <span>View Pull Request #{item.link.split("/").pop() || "PR"}</span>
         <ChevronRight className="w-3 h-3" />
        </a>
       ) : null}
      </div>
     );
    })}
   </div>
  </div>
 );
}
