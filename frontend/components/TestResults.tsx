"use client";

import {
 CheckCircle2,
 CircleX,
 Clock3,
 Terminal
} from "lucide-react";

import type {
 TestResults as TestResultState
} from "@/lib/types";

interface TestResultsProps {
 results: TestResultState | undefined;
}

export function TestResults({
 results
}: TestResultsProps) {
 if (!results) {
  return (
   <div className="panel p-5">
    <p className="eyebrow">
     Sandbox verification
    </p>

    <p className="mt-3 text-xs text-slate-600">
     Awaiting sandbox execution.
    </p>
   </div>
  );
 }

 const passed =
  results.tests_passed === true ||
  results.exit_code === 0;

 return (
  <div className="panel overflow-hidden">
   <div className="panel-header flex items-center justify-between">
    <div className="flex items-center gap-2">
     <Terminal className="h-4 w-4 text-slate-500" />

     <div>
      <p className="eyebrow">
       Sandbox verification
      </p>

      <h2 className="mt-1 text-sm font-medium text-white">
       Test execution
      </h2>
     </div>
    </div>

    {passed ? (
     <CheckCircle2 className="h-4 w-4 text-emerald-400" />
    ) : (
     <CircleX className="h-4 w-4 text-red-400" />
    )}
   </div>

   <div className="grid gap-px bg-white/[0.08] sm:grid-cols-3">
    <div className="bg-[#161A1F] p-4">
     <p className="eyebrow">exit code</p>

     <p
      className={[
       "mt-2 font-mono text-xl",
       passed
        ? "text-primary-fixed"
        : "text-error"
      ].join(" ")}
     >
      {results.exit_code}
     </p>
    </div>

    <div className="bg-[#161A1F] p-4">
     <p className="eyebrow">status</p>

     <p className="mt-2 font-mono text-xs text-slate-300">
      {passed ? "PASSED" : "FAILED"}
     </p>
    </div>

    <div className="bg-[#161A1F] p-4">
     <p className="eyebrow">timeout</p>

     <div className="mt-2 flex items-center gap-1.5">
      <Clock3 className="h-3.5 w-3.5 text-slate-600" />

      <span className="font-mono text-xs text-slate-300">
       {results.timed_out
        ? "YES"
        : "NO"}
      </span>
     </div>
    </div>
   </div>

   <div className="grid border-t border-white/[0.06] md:grid-cols-2">
    <div className="border-b border-white/[0.06] md:border-b-0 md:border-r">
     <div className="px-4 py-3">
      <p className="font-mono text-[9px] text-slate-600">
       stdout
      </p>
     </div>

     <pre className="terminal h-[180px] overflow-auto whitespace-pre-wrap p-4 font-mono text-[10px] leading-relaxed text-slate-500">
      {results.stdout || "(empty)"}
     </pre>
    </div>

    <div>
     <div className="px-4 py-3">
      <p className="font-mono text-[9px] text-slate-600">
       stderr
      </p>
     </div>

     <pre className="terminal h-[180px] overflow-auto whitespace-pre-wrap p-4 font-mono text-[10px] leading-relaxed text-slate-500">
      {results.stderr || "(empty)"}
     </pre>
    </div>
   </div>
  </div>
 );
}
