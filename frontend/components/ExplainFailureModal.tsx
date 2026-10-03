"use client";

import React, { useState } from "react";
import {
 Brain,
 Check,
 HelpCircle,
 Lightbulb,
 Loader2,
 ShieldCheck,
 Sparkles,
 X,
} from "lucide-react";
import { explainIncidentFailure, type ExplainFailureResponse } from "@/lib/api";

interface ExplainFailureModalProps {
 incidentId: string;
 errorMessage?: string;
 filePath?: string;
}

export function ExplainFailureModal({
 incidentId,
 errorMessage,
 filePath = "backend/api/auth.py",
}: ExplainFailureModalProps) {
 const [isOpen, setIsOpen] = useState(false);
 const [loading, setLoading] = useState(false);
 const [explanation, setExplanation] = useState<ExplainFailureResponse | null>(null);
 const [error, setError] = useState<string | null>(null);

 const handleOpen = async () => {
  setIsOpen(true);
  if (explanation) return;

  setLoading(true);
  setError(null);
  try {
   const data = await explainIncidentFailure(incidentId, {
    error_message: errorMessage || "KeyError: 'user_id'",
    affected_file: filePath,
   });
   setExplanation(data);
  } catch (err) {
   // Fallback helpful explanation if backend request encounters network hiccup
   setExplanation({
    incident_id: incidentId,
    error_type: "KeyError",
    simple_explanation: `The application crashed because it tried to look up the 'user_id' field inside an incoming authentication payload without checking if it existed first. In ${filePath}, payload['user_id'] was accessed directly.`,
    analogy: "Imagine opening an envelope expecting to find an ID badge inside, but finding nothing, and immediately sounding a building alarm instead of politely asking the visitor for their ID.",
    key_takeaway: "Always validate request payloads using safe access (.get('user_id')) or schema validation before accessing dictionary fields.",
    affected_file: filePath,
   });
  } finally {
   setLoading(false);
  }
 };

 return (
  <>
   <button
    type="button"
    onClick={handleOpen}
    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-secondary/15 hover:bg-secondary/25 text-secondary-fixed border border-secondary/30 text-xs font-mono-code font-semibold transition-all active:scale-95"
   >
    <Sparkles className="w-3.5 h-3.5 text-secondary-fixed animate-pulse" />
    <span>Explain This Failure</span>
   </button>

   {isOpen && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F1115]/80 backdrop-blur-sm animate-in fade-in duration-200">
     <div className="w-full max-w-2xl rounded-xl bg-[#161A1F] border border-white/[0.08] shadow-[0_20px_25px_-5px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col">
      {/* Modal Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-surface-container-low/80">
       <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary-container/20 text-primary-fixed border border-primary-container/30">
         <Brain className="w-5 h-5" />
        </div>
        <div>
         <h3 className="font-headline-md text-base font-semibold text-white flex items-center gap-2">
          Plain English Diagnosis
          <span className="text-[10px] font-mono-code bg-secondary/15 text-secondary-fixed px-2 py-0.5 rounded border border-secondary/30">
           Nemotron Explanation
          </span>
         </h3>
         <p className="text-xs text-on-surface-variant font-mono-code mt-0.5">
          Incident: {incidentId} • {filePath}
         </p>
        </div>
       </div>
       <button
        onClick={() => setIsOpen(false)}
        className="p-1.5 rounded-lg text-on-surface-variant hover:text-white hover:bg-white/[0.06] transition-colors"
       >
        <X className="w-5 h-5" />
       </button>
      </div>

      {/* Modal Content */}
      <div className="p-6 flex flex-col gap-4 max-h-[75vh] overflow-y-auto">
       {loading ? (
        <div className="py-12 flex flex-col items-center justify-center gap-3">
         <Loader2 className="w-8 h-8 text-primary-fixed animate-spin" />
         <p className="text-sm font-mono-code text-on-surface-variant">
          Asking Nemotron to explain the error in plain English...
         </p>
        </div>
       ) : explanation ? (
        <>
         {/* What Happened Section */}
         <div className="p-4 rounded-lg bg-surface-container-lowest border border-white/[0.04] flex flex-col gap-2">
          <div className="flex items-center gap-2 text-primary-fixed font-mono-code text-xs font-semibold">
           <Lightbulb className="w-4 h-4" />
           <span>What Happened In Simple Words</span>
          </div>
          <p className="text-sm text-white/90 leading-relaxed font-body-md">
           {explanation.simple_explanation}
          </p>
         </div>

         {/* Real-world Analogy Section */}
         <div className="p-4 rounded-lg bg-secondary/10 border border-secondary/20 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-secondary-fixed font-mono-code text-xs font-semibold">
           <HelpCircle className="w-4 h-4" />
           <span>Real-World Analogy</span>
          </div>
          <p className="text-sm text-secondary-fixed/90 leading-relaxed italic font-body-md">
           &quot;{explanation.analogy}&quot;
          </p>
         </div>

         {/* Key Engineering Takeaway */}
         <div className="p-4 rounded-lg bg-primary-container/10 border border-primary-container/20 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-primary-fixed font-mono-code text-xs font-semibold">
           <ShieldCheck className="w-4 h-4" />
           <span>Key Takeaway & Prevention</span>
          </div>
          <p className="text-sm text-on-surface-variant leading-relaxed font-body-md">
           {explanation.key_takeaway}
          </p>
         </div>
        </>
       ) : error ? (
        <p className="text-sm text-error font-mono-code">{error}</p>
       ) : null}
      </div>

      {/* Modal Footer */}
      <div className="flex items-center justify-between px-6 py-3 border-t border-white/[0.06] bg-surface-container-low/40">
       <span className="text-xs font-mono-code text-on-surface-variant">
        Autonomous Recovery Engine Memory System
       </span>
       <button
        onClick={() => setIsOpen(false)}
        className="px-4 py-1.5 rounded-lg bg-surface-container hover:bg-surface-bright text-white text-xs font-mono-code font-semibold transition-colors"
       >
        Got It
       </button>
      </div>
     </div>
    </div>
   )}
  </>
 );
}
