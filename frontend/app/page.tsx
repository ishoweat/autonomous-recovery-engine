"use client";

import { API_BASE_URL } from "@/lib/api";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import {
 ArrowRight,
 Bot,
 GitBranch,
 Loader2,
 Radar,
 ShieldAlert,
 ShieldCheck,
 Terminal,
 Zap,
 X,
 Sparkles,
 AlertTriangle
} from "lucide-react";
import { submitGithubWebhook } from "@/lib/api";
import { AppShell } from "@/components/AppShell";

export default function HomePage() {
 const router = useRouter();
 const [showModal, setShowModal] = useState(false);
 const [authStatus, setAuthStatus] = useState<"idle" | "checking" | "missing">("idle");
 const [flags, setFlags] = useState<{enable_webhook_ingress?: boolean, enable_demo_scenarios?: boolean, enable_benchmark_view?: boolean}>({});
 const [benchmarkData, setBenchmarkData] = useState<any>(null);

 useEffect(() => {
  fetch(`${API_BASE_URL}/api/flags`)
   .then(res => res.json())
   .then(data => {
    setFlags(data);
    if (data.enable_benchmark_view) {
     fetch(`${API_BASE_URL}/api/benchmark/results`)
      .then(r => r.json())
      .then(d => setBenchmarkData(d))
      .catch(console.error);
    }
   })
   .catch(err => console.error(err));
 }, []);

 async function handleConnectGithub() {
  setAuthStatus("checking");
  try {
   const res = await fetch(`${API_BASE_URL}/auth/github/status`);
   const data = await res.json();
   if (data.configured) {
    window.location.href = `${API_BASE_URL}/auth/github/login`;
   } else {
    setAuthStatus("missing");
   }
  } catch (err) {
   setAuthStatus("missing");
  }
 }

 return (
  <AppShell isStreamConnected={true}>
   <div className="flex flex-col items-center justify-center flex-1 px-gutter-desktop py-space-xl">
    <div className="w-full max-w-5xl">
     {/* Hero Header */}
     <div className="mb-space-lg text-center">
      <div className="mx-auto mb-space-md flex h-14 w-14 items-center justify-center rounded-xl border border-primary/40 bg-primary-container/15 shadow-[0_0_20px_rgba(34,197,94,0.15)]">
       <span className="material-symbols-outlined text-primary-fixed text-[30px]">
        shield
       </span>
      </div>

      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-container/10 border border-primary-container/30 mb-space-xs">
       <span className="w-2 h-2 rounded-full bg-primary-fixed animate-ping" />
       <span className="font-mono-code text-[11px] font-bold tracking-wider text-primary-fixed uppercase">
        NVIDIA NEMOTRON RECOVERY ENGINE • {flags.enable_webhook_ingress ? "WAITING FOR CI FAILURE..." : "LIVE RECOVERY MODE"}
       </span>
      </div>

      <h1 className="mt-space-xs font-display-hero text-headline-xl md:text-display-hero font-semibold tracking-tight text-on-surface">
       Autonomous Recovery Engine
      </h1>

      <p className="mx-auto mt-space-sm max-w-2xl font-body-lg text-body-lg text-on-surface-variant leading-relaxed">
       Stateful AI incident remediation: real CI failure ingestion, Nemotron root cause reasoning, isolated sandbox validation, explainable risk governance, and external GitHub PR generation.
      </p>
     </div>

     {/* ── 30–60 Second Evaluator Story Narrative Stepper ────── */}
     <div className="mb-space-xl rounded-xl border border-white/[0.1] bg-[#0C0F14]/90 p-space-md shadow-2xl backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-space-xs mb-space-sm">
       <div className="flex items-center gap-2">
        <span className="flex h-2 w-2 rounded-full bg-primary-fixed animate-pulse" />
        <span className="font-mono-code text-[11px] font-bold tracking-widest text-primary-fixed uppercase">
         Primary 30–60s Evaluator Story
        </span>
       </div>
       <span className="font-mono-code text-[10px] text-on-surface-variant">
        Zero Mock Fallbacks • Authentic Execution Chain
       </span>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-1.5 text-center">
       {[
        { step: "1", title: "GitHub Failure", sub: "Actions CI run" },
        { step: "2", title: "Webhook", sub: "Event ingestion" },
        { step: "3", title: "Exact Error", sub: "File & traceback" },
        { step: "4", title: "Nemotron", sub: "LLM reasoning" },
        { step: "5", title: "Root Cause", sub: "Diagnosis found" },
        { step: "6", title: "Real Patch", sub: "Unified diff" },
        { step: "7", title: "Sandbox", sub: "Pytest verify" },
        { step: "8", title: "Risk Gate", sub: "Human approval" },
        { step: "9", title: "GitHub PR", sub: "Branch & commit" },
       ].map((item) => (
        <div
         key={item.step}
         className="flex flex-col items-center rounded-lg border border-white/[0.06] bg-surface-container-low/70 p-2 hover:border-primary/40 hover:bg-surface-container transition-all"
        >
         <div className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-container text-primary-fixed text-[11px] font-mono-code font-bold mb-1">
          {item.step}
         </div>
         <span className="font-headline-md text-[11px] font-semibold text-on-surface leading-tight">
          {item.title}
         </span>
         <span className="font-mono-code text-[9px] text-on-surface-variant mt-0.5 truncate w-full">
          {item.sub}
         </span>
        </div>
       ))}
      </div>
     </div>

     {/* ── Primary Action Callouts ────────────────────────────── */}
     <div className="flex flex-col items-center justify-center gap-space-md sm:flex-row mb-space-xl">
      <Link
       href="/detect"
       className="group flex items-center gap-space-sm rounded-lg bg-primary text-black hover:bg-primary-fixed px-space-xl py-space-md font-mono-code text-sm font-bold shadow-[0_0_24px_rgba(34,197,94,0.35)] hover:shadow-[0_0_32px_rgba(34,197,94,0.5)] transition-all active:scale-[0.98]"
      >
       <Zap className="h-4 w-4 text-black fill-black" />
       Launch Live Recovery Pipeline
       <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
      </Link>

      <Link
       href="/connect"
       className="flex items-center gap-space-xs rounded-lg bg-surface-container hover:bg-surface-bright text-on-surface px-space-lg py-space-md font-mono-code text-xs font-semibold transition-colors border border-white/[0.1]"
      >
       <GitBranch className="h-4 w-4 text-secondary-fixed" />
       Connect GitHub Repository
      </Link>

     </div>

     {/* ── Demo Scenarios Panel ───────────────────────────── */}
      {flags.enable_demo_scenarios && (
       <div className="mb-space-xl rounded-xl border border-white/[0.1] bg-surface-container-low/70 p-space-md shadow-lg">
        <h3 className="font-headline-md text-headline-sm font-semibold text-on-surface mb-space-sm flex items-center gap-2">
         <Sparkles className="w-5 h-5 text-primary-fixed" />
         Demo Scenarios
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-sm">
         {[
          {
           title: "Low Risk Calculator",
           desc: "One-line fix for ZeroDivisionError in uncritical file.",
           outcome: "ALLOW",
           color: "text-primary-fixed",
           bg: "bg-primary-container/20 border-primary-container/40",
           url: "/detect?repoUrl=demo/low_risk_calculator"
          },
          {
           title: "Medium Risk Data Pipeline",
           desc: "Multi-line fix skipping last batch record in business logic.",
           outcome: "APPROVE",
           color: "text-secondary-fixed",
           bg: "bg-secondary/20 border-secondary/40",
           url: "/detect?repoUrl=demo/medium_risk_data_pipeline"
          },
          {
           title: "High Risk Auth & Payments",
           desc: "Sensitive validation logic change in auth/payments.py.",
           outcome: "BLOCK",
           color: "text-error",
           bg: "bg-error/20 border-error/40",
           url: "/detect?repoUrl=demo/high_risk_auth_payments"
          }
         ].map(scenario => (
          <Link
           key={scenario.title}
           href={scenario.url as any}
           className="p-space-sm rounded-lg border border-white/[0.05] bg-surface-container hover:border-white/[0.15] transition-colors flex flex-col gap-2"
          >
           <span className="font-headline-sm text-sm font-semibold text-on-surface">{scenario.title}</span>
           <span className="font-body-sm text-xs text-on-surface-variant flex-1">{scenario.desc}</span>
           <div className={`mt-auto self-start px-2 py-0.5 rounded font-mono-code text-[10px] font-bold border ${scenario.bg} ${scenario.color}`}>
            EXPECTED: {scenario.outcome}
           </div>
          </Link>
         ))}
        </div>
       </div>
      )}

      {/* ── Benchmark Panel ───────────────────────────── */}
      {flags.enable_benchmark_view && (
       <div className="mb-space-xl rounded-xl border border-white/[0.1] bg-surface-container-low/70 p-space-md shadow-lg">
        <h3 className="font-headline-md text-headline-sm font-semibold text-on-surface mb-space-sm flex items-center gap-2">
         <Radar className="w-5 h-5 text-secondary-fixed" />
         Autonomous Benchmark Results
        </h3>
        
        {!benchmarkData || !benchmarkData.exists ? (
         <div className="p-space-md rounded-lg bg-surface-container border border-white/5 font-mono-code text-sm text-on-surface-variant flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Run `python benchmark/run_benchmark.py` in your terminal to generate results.
         </div>
        ) : (
         <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
           <div className="p-4 rounded-lg bg-surface-container border border-white/5">
            <div className="text-xs text-on-surface-variant font-label-caps mb-1">Total Cases</div>
            <div className="text-2xl text-on-surface font-mono-metric font-bold">{benchmarkData.results.length}</div>
           </div>
           <div className="p-4 rounded-lg bg-surface-container border border-white/5">
            <div className="text-xs text-on-surface-variant font-label-caps mb-1">Fix Rate</div>
            <div className="text-2xl text-primary-fixed font-mono-metric font-bold">
             {Math.round((benchmarkData.results.filter((r:any) => r.fixed).length / benchmarkData.results.length) * 100)}%
            </div>
           </div>
           <div className="p-4 rounded-lg bg-surface-container border border-white/5">
            <div className="text-xs text-on-surface-variant font-label-caps mb-1">Avg Time</div>
            <div className="text-2xl text-secondary-fixed font-mono-metric font-bold">
             {Math.round(benchmarkData.results.reduce((a:number, b:any) => a + (b.total_time||0), 0) / benchmarkData.results.length * 10) / 10}s
            </div>
           </div>
           <div className="p-4 rounded-lg bg-surface-container border border-white/5">
            <div className="text-xs text-on-surface-variant font-label-caps mb-1">Total Tokens</div>
            <div className="text-2xl text-on-surface font-mono-metric font-bold">
             {benchmarkData.results.reduce((a:number, b:any) => a + (b.tokens||0), 0)}
            </div>
           </div>
          </div>
          
          <div className="overflow-x-auto rounded-lg border border-white/5">
           <table className="w-full text-sm text-left">
            <thead className="bg-surface-container text-xs font-label-caps text-on-surface-variant border-b border-white/5">
             <tr>
              <th className="px-4 py-3">Case</th>
              <th className="px-4 py-3">Fixed</th>
              <th className="px-4 py-3">Decision</th>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Retries</th>
             </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-surface-container-low/50">
             {benchmarkData.results.map((r:any, i:number) => (
              <tr key={i} className="hover:bg-surface-container/50 transition-colors">
               <td className="px-4 py-3 font-mono-code text-on-surface">{r.case}</td>
               <td className="px-4 py-3">{r.fixed ? "✅" : "❌"}</td>
               <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                 r.decision === 'ALLOW' ? 'bg-primary-container/20 text-primary-fixed' : 
                 r.decision === 'APPROVE' ? 'bg-secondary/20 text-secondary-fixed' : 
                 r.decision === 'BLOCK' ? 'bg-error/20 text-error' : 'bg-surface/50 text-on-surface'
                }`}>{r.decision}</span>
               </td>
               <td className="px-4 py-3 text-on-surface-variant font-mono-metric">{r.total_time}s</td>
               <td className="px-4 py-3 text-on-surface-variant font-mono-metric">{r.retries}</td>
              </tr>
             ))}
            </tbody>
           </table>
          </div>
         </div>
        )}
       </div>
      )}

      {/* ── 4 Architectural Pillars ─────────────────────────────── */}
     <div className="grid gap-space-md grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
      {[
       {
        icon: Radar,
        label: "Detect & Ingest",
        detail: "Webhook parses failing commit SHA, branch & exact stack trace from GitHub Actions.",
        href: "/detect",
        badge: "Real Ingest"
       },
       {
        icon: Bot,
        label: "Nemotron Reasoning",
        detail: "Diagnoses root cause with concise AI evidence, line-specific context & repair diff.",
        href: "/detect",
        badge: "Nebius / NVIDIA"
       },
       {
        icon: Terminal,
        label: "Sandbox Verification",
        detail: "Executes test runner in an isolated container to verify exit code 0 before PR creation.",
        href: "/detect",
        badge: "Isolated Docker"
       },
       {
        icon: GitBranch,
        label: "PR Dispatch",
        detail: "Creates real recovery branch, commits tested patch, and opens external GitHub PR.",
        href: "/detect",
        badge: "PyGithub Live"
       }
      ].map((item) => {
       const Icon = item.icon;

       return (
        <Link
         key={item.label}
         href={(item.href || "/detect") as any}
         className="p-space-md rounded-lg transition-all duration-200 group relative block border border-white/[0.08] bg-surface-container-low hover:border-primary/50 hover:bg-surface-container shadow-[0_1px_3px_rgba(0,0,0,0.4)]"
        >
         {item.badge ? (
          <span className="absolute top-space-sm right-space-sm rounded bg-primary-container/15 px-space-xs py-space-2xs font-label-badge text-[10px] text-primary-fixed border border-primary-container/30">
           {item.badge}
          </span>
         ) : null}

         <div className="p-space-xs rounded-lg w-fit bg-surface-container text-on-surface-variant group-hover:text-primary-fixed">
          <Icon className="h-5 w-5" />
         </div>

         <p className="mt-space-md font-headline-md text-headline-md font-semibold text-on-surface flex items-center justify-between">
          <span>{item.label}</span>
          <ArrowRight className="h-3.5 w-3.5 text-on-surface-variant opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1 group-hover:translate-x-0" />
         </p>

         <p className="mt-space-2xs font-body-sm text-body-sm text-on-surface-variant group-hover:text-on-surface leading-relaxed">
          {item.detail}
         </p>
        </Link>
       );
      })}
     </div>

    </div>
   </div>

   {showModal && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0F1115]/80 backdrop-blur-sm">
     <div className="w-full max-w-md bg-surface-container-low border border-white/[0.08] rounded-xl p-space-xl shadow-[0_20px_25px_-5px_rgba(0,0,0,0.5)]">
      
      {authStatus === "missing" ? (
       <div className="flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-full bg-error/10 flex items-center justify-center mb-space-md border border-error/30 text-error">
         <ShieldAlert className="w-6 h-6" />
        </div>
        <h3 className="text-headline-sm font-semibold text-on-surface mb-space-sm">
         GitHub integration is not configured yet
        </h3>
        <p className="text-body-sm text-on-surface-variant mb-space-lg">
         Please set <code>GITHUB_CLIENT_ID</code> and <code>GITHUB_CLIENT_SECRET</code> in the backend environment variables to enable OAuth authentication.
        </p>
        <div className="flex gap-space-sm w-full">
         <button
          onClick={() => {
           setAuthStatus("idle");
           setShowModal(false);
          }}
          className="flex-1 py-space-sm rounded-lg border border-white/[0.1] text-on-surface hover:bg-surface-container transition-colors font-semibold"
         >
          CANCEL
         </button>
         <button
          onClick={handleConnectGithub}
          className="flex-1 py-space-sm rounded-md bg-primary-container text-on-primary-container hover:bg-primary-fixed transition-colors font-semibold"
         >
          TRY AGAIN
         </button>
        </div>
       </div>
      ) : (
       <div className="flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center mb-space-md border border-white/[0.1] text-on-surface">
         <Bot className="w-6 h-6" />
        </div>
        <h3 className="text-headline-sm font-semibold text-on-surface mb-space-sm">
         Connect GitHub Repository
        </h3>
        <p className="text-body-sm text-on-surface-variant mb-space-xl">
         Connect a repository so Autonomous Recovery Engine can inspect its code, detect failures, identify root causes, and prepare verified fixes.
        </p>
        
        <div className="flex flex-col gap-space-sm w-full">
         <button
          onClick={handleConnectGithub}
          disabled={authStatus === "checking"}
          className="w-full flex items-center justify-center gap-2 py-space-md rounded-md bg-primary text-white font-semibold hover:bg-primary/90 disabled:opacity-50"
         >
          {authStatus === "checking" ? (
           <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
           "Continue with GitHub"
          )}
         </button>
         
         <Link
          href="/detect"
          onClick={() => setShowModal(false)}
          className="w-full py-space-sm rounded-lg border border-white/[0.1] text-on-surface hover:bg-surface-container transition-colors font-semibold mt-space-xs block"
         >
          Enter Repository URL
         </Link>
         <button
          onClick={() => setShowModal(false)}
          className="absolute top-space-md right-space-md text-on-surface-variant hover:text-on-surface"
         >
          <X className="w-5 h-5" />
         </button>
        </div>
       </div>
      )}
     </div>
    </div>
   )}
  </AppShell>
 );
}
