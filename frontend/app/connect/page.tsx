"use client";

import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { GitHubSessionWidget } from "@/components/GitHubSessionWidget";
import { API_BASE_URL } from "@/lib/api";
import { Loader2, CheckCircle2, ShieldAlert, Terminal, AlertTriangle, GitBranch, Github, Info } from "lucide-react";

const ANALYSIS_STEPS = [
 "FETCHING FILE STRUCTURE",
 "ANALYZING SOURCE CODE",
 "ANALYZING DEPENDENCIES",
 "ANALYZING TESTS",
 "ANALYZING CI/CD",
 "BUILDING CODEBASE CONTEXT",
 "READY FOR DETECTION"
];

export default function ConnectPage() {
 const router = useRouter();
 const [repoUrl, setRepoUrl] = useState("");
 const [loading, setLoading] = useState(false);
 const [error, setError] = useState<string | null>(null);
 const [infoNotice, setInfoNotice] = useState<string | null>(null);
 
 // Incident detected state
 const [repoDetails, setRepoDetails] = useState<any>(null);

 // Animation state
 const [analyzing, setAnalyzing] = useState(false);
 const [currentStep, setCurrentStep] = useState(0);

 useEffect(() => {
  if (analyzing && currentStep < ANALYSIS_STEPS.length) {
   const timer = setTimeout(() => {
    setCurrentStep((prev) => prev + 1);
   }, 800); // 800ms per step
   return () => clearTimeout(timer);
  }
 }, [analyzing, currentStep]);

 const autoValidateRepo = async (url: string) => {
  setRepoUrl(url);
  if (!url.trim()) return;
  setLoading(true);
  setError(null);
  setRepoDetails(null);
  try {
   const valRes = await fetch(`${API_BASE_URL}/api/v1/github/validate-repo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ repository_url: url })
   });
   if (valRes.ok) {
    const data = await valRes.json();
    setRepoDetails(data);
    if (typeof window !== "undefined") {
     localStorage.setItem("connected_repo", JSON.stringify({
      owner: data.owner || "",
      repo: data.repo || "",
      full_name: data.full_name || (data.owner && data.repo ? `${data.owner}/${data.repo}` : ""),
      default_branch: data.default_branch || "main",
      repository_url: url
     }));
    }
   }
  } catch (_e) {}
  setLoading(false);
 };

 async function handleValidateRepo(e: React.FormEvent) {
  e.preventDefault();
  setLoading(true);
  setError(null);
  setRepoDetails(null);

  try {
   const valRes = await fetch(`${API_BASE_URL}/api/v1/github/validate-repo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ repository_url: repoUrl })
   });
   
   if (!valRes.ok) {
    let errorDetail = "Failed to validate repository.";
    try {
     const errorJson = await valRes.json();
     if (errorJson.detail) errorDetail = errorJson.detail;
    } catch {
     const text = await valRes.text();
     if (text) errorDetail = text;
    }
    throw new Error(errorDetail);
   }
   const data = await valRes.json();

   setRepoDetails(data);
   if (typeof window !== "undefined") {
    localStorage.setItem("connected_repo", JSON.stringify({
     owner: data.owner || "",
     repo: data.repo || "",
     full_name: data.full_name || (data.owner && data.repo ? `${data.owner}/${data.repo}` : ""),
     default_branch: data.default_branch || "main",
     repository_url: repoUrl
    }));
   }
   
   // Automatically continue to investigate
   handleInvestigate(true, data);
  } catch (err: any) {
   let msg = err.message || "Failed to validate repository.";
   try {
    const parsed = JSON.parse(msg);
    if (parsed.detail) msg = parsed.detail;
   } catch {}
   setError(msg);
  } finally {
   setLoading(false);
  }
 }

 async function handleInvestigate(allowManual: boolean | React.MouseEvent = false, scannedData?: any) {
  const isManual = typeof allowManual === "boolean" ? allowManual : false;
  setAnalyzing(true);
  setCurrentStep(0);
  setError(null);
  setInfoNotice(null);

  const activeRepoDetails = scannedData || repoDetails;
  
  if (typeof window !== "undefined" && activeRepoDetails) {
   localStorage.setItem("connected_repo", JSON.stringify({
    owner: activeRepoDetails.owner || "",
    repo: activeRepoDetails.repo || "",
    full_name: activeRepoDetails.full_name || (activeRepoDetails.owner && activeRepoDetails.repo ? `${activeRepoDetails.owner}/${activeRepoDetails.repo}` : ""),
    default_branch: activeRepoDetails.default_branch || "main",
    repository_url: repoUrl
   }));
  }

  try {
   const ingestRes = await fetch(`${API_BASE_URL}/api/v1/incident/ingest-repo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
     repository_url: repoUrl,
     owner: activeRepoDetails?.owner || "",
     repo: activeRepoDetails?.repo || "",
     default_branch: activeRepoDetails?.default_branch || "main",
     allow_manual: isManual
    })
   });
   
   if (!ingestRes.ok) {
    const textData = await ingestRes.text();
    let msg = textData || "Failed to analyze repository";
    try {
     const parsed = JSON.parse(textData);
     if (parsed.detail) msg = parsed.detail;
    } catch {}

    if (msg.includes("No recent failing CI workflows found")) {
     setInfoNotice(msg);
     setAnalyzing(false);
     return;
    }

    throw new Error(msg);
   }
   
   const data = await ingestRes.json();
   router.push(`/detect?incident_id=${data.incident_id}&repoUrl=${encodeURIComponent(repoUrl)}`);

  } catch (err: any) {
   let msg = err.message || "Failed to analyze repository.";
   try {
    const parsed = JSON.parse(msg);
    if (parsed.detail) msg = parsed.detail;
   } catch {}
   setError(msg);
   setAnalyzing(false);
  }
 }

 return (
  <AppShell isStreamConnected={false}>
   <div className="flex flex-col items-center justify-center flex-1 px-gutter-desktop py-space-xl overflow-y-auto">
    <div className={`w-full ${repoDetails ? 'max-w-4xl' : 'max-w-2xl'} transition-all bg-surface-container-low border border-white/[0.06] rounded-xl p-space-xl`}>
     
     {!analyzing ? (
      <>
       <GitHubSessionWidget
        className="mb-space-lg"
        currentRepoUrl={repoUrl}
        onSelectRepo={(url) => autoValidateRepo(url)}
       />

       {!repoDetails && <h1 className="text-headline-md font-semibold mb-space-md text-on-surface">Target GitHub Repository</h1>}
       
       <form onSubmit={handleValidateRepo} className="flex gap-space-sm mb-space-lg">
        <input 
         type="text" 
         placeholder="https://github.com/username/repository" 
         value={repoUrl}
         onChange={(e) => setRepoUrl(e.target.value)}
         className="flex-1 bg-surface-container border border-white/[0.1] rounded-lg px-space-md py-space-sm text-on-surface focus:outline-none focus:border-primary-container font-mono-code"
         required
        />
        <button 
         type="submit"
         disabled={loading || !repoUrl}
         className="bg-primary text-white px-space-md py-space-sm rounded-md font-semibold disabled:opacity-50 flex items-center gap-2 transition-all hover:bg-primary/90 "
        >
         {loading && !repoDetails ? (
          <><Loader2 className="w-4 h-4 animate-spin" /> SCANNING...</>
         ) : (
          "SCAN REPOSITORY"
         )}
        </button>
       </form>

       {error && (
        <div className="bg-error/10 border border-error/30 text-error p-space-md rounded-lg mb-space-md font-mono-code text-sm flex flex-col items-start gap-3">
         <div className="flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 shrink-0" />
          <div>
           <strong>GitHub Connection Error</strong><br/>
           {error}
          </div>
         </div>
         {error.includes("Not authenticated") && (
          <button
           onClick={() => window.location.href = `${API_BASE_URL}/auth/github/login`}
           className="mt-2 bg-primary-container text-on-primary-container px-space-md py-space-sm rounded-lg font-semibold flex items-center gap-2 hover:bg-primary-fixed transition-colors"
          >
           Authenticate with GitHub
          </button>
         )}
        </div>
       )}

       {infoNotice && (
        <div className="bg-primary/10 border border-primary/30 text-on-surface p-space-md rounded-lg mb-space-md font-mono-code text-sm flex flex-col items-start gap-3">
         <div className="flex items-start gap-3 text-primary-fixed">
          <Info className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
           <strong className="text-on-surface">CI Workflow Status</strong><br/>
           <span className="text-on-surface/90">{infoNotice}</span>
          </div>
         </div>
         <button
          onClick={() => handleInvestigate(true)}
          className="mt-2 bg-primary text-white px-space-md py-space-sm rounded-lg font-semibold flex items-center gap-2 hover:bg-primary/90 transition-colors shadow-sm"
         >
          TRIGGER MANUAL INCIDENT INVESTIGATION →
         </button>
        </div>
       )}

       {/* DETECTION DASHBOARD INCIDENT CARD */}
       {repoDetails && (
        <div className="mt-space-xl animate-fade-in">
         <div className="flex items-center gap-2 mb-space-sm text-primary-fixed">
          <CheckCircle2 className="w-5 h-5" />
          <h2 className="text-title-lg font-semibold">Repository Validated</h2>
         </div>
         
         <div className="border border-white/[0.08] bg-surface-container rounded-xl overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
          <div className="bg-primary/10 border-b border-white/[0.05] p-space-md flex flex-col gap-2">
           <div className="flex items-center gap-2 text-on-surface">
            <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
            <span className="font-mono-code font-semibold">Repository: {repoDetails.full_name}</span>
           </div>
           <div className="flex items-center gap-2 text-on-surface">
            <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
            <span className="font-mono-code">Default branch: {repoDetails.default_branch}</span>
           </div>
           <div className="flex items-center gap-2 text-on-surface">
            <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
            <span className="font-mono-code">Visibility: {repoDetails.visibility}</span>
           </div>
           <div className="flex items-center gap-2 text-on-surface">
            <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
            <span className="font-mono-code">Read access: {repoDetails.permissions?.contents_read ? "yes" : "no"}</span>
           </div>
           <div className="flex items-center gap-2 text-on-surface">
            <CheckCircle2 className="w-4 h-4 text-primary-fixed" />
            <span className="font-mono-code">Write/PR access: {repoDetails.permissions?.contents_write && repoDetails.permissions?.pull_requests ? "yes" : "no"}</span>
           </div>
          </div>
          
          <div className="p-space-md border-t border-white/[0.05] bg-surface-container-low flex justify-end">
           <button 
            onClick={() => handleInvestigate(false)}
            className="bg-primary text-white px-space-lg py-space-sm rounded-md font-semibold shadow-[0_1px_3px_rgba(0,0,0,0.4)] hover:bg-primary/90 transition-colors flex items-center gap-2"
           >
            INVESTIGATE INCIDENT →
           </button>
          </div>
         </div>
        </div>
       )}
      </>
     ) : (
      <div className="flex flex-col items-center py-space-xl">
       <div className="w-16 h-16 rounded-full bg-primary-container/20 flex items-center justify-center mb-space-lg border border-primary/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
        <Terminal className="w-8 h-8 text-primary-fixed" />
       </div>
       
       <h2 className="text-headline-sm font-semibold text-primary-fixed mb-space-xl flex items-center gap-2">
        REPOSITORY CONNECTED <CheckCircle2 className="w-6 h-6" />
       </h2>

       <div className="w-full max-w-sm flex flex-col gap-space-md font-mono-code text-sm">
        {ANALYSIS_STEPS.map((step, idx) => {
         const isPast = idx < currentStep;
         const isCurrent = idx === currentStep;
         
         if (!isPast && !isCurrent) return null;

         return (
          <div key={step} className="flex items-center gap-3">
           {isPast ? (
            <CheckCircle2 className="w-5 h-5 text-primary-fixed shrink-0" />
           ) : (
            <Loader2 className="w-5 h-5 text-primary-container animate-spin shrink-0" />
           )}
           <span className={isPast ? "text-on-surface" : "text-primary-container animate-pulse"}>
            {step}
           </span>
          </div>
         );
        })}
       </div>
      </div>
     )}

    </div>
   </div>
  </AppShell>
 );
}
