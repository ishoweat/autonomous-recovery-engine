import { ShieldCheck, GitPullRequest, Search, FileText } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

interface RecoveryCompletePanelProps {
  repository: string;
  incidentId: string;
  rootCause: string;
  riskAssessment: string;
  prNumber?: string;
  prUrl?: string;
  branchName?: string;
  forkRepo?: string;
  commitSha?: string;
}

export function RecoveryCompletePanel({
  repository,
  incidentId,
  rootCause,
  riskAssessment,
  prNumber = "47",
  prUrl,
  branchName,
  forkRepo,
  commitSha,
}: RecoveryCompletePanelProps) {
  const shortCommit = commitSha ? commitSha.slice(0, 7) : undefined;

  return (
    <div className="bg-surface-container border border-primary-container/30 rounded-xl overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.4)]">
      {/* Header */}
      <div className="bg-primary-container/10 border-b border-primary-container/30 px-space-lg py-space-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-primary-fixed" />
          <h2 className="text-title-md font-semibold text-primary-fixed tracking-wide">RECOVERY COMPLETE</h2>
        </div>
        {forkRepo ? (
          <span className="bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs px-2.5 py-1 rounded-full font-mono">
            FORK RECOVERY PATH
          </span>
        ) : (
          <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs px-2.5 py-1 rounded-full font-mono">
            DIRECT PUSH PATH
          </span>
        )}
      </div>

      <div className="p-space-lg flex flex-col gap-space-lg">
        {/* Recovery Pipeline Flow: ORIGINAL REPO -> FORK -> VERIFIED COMMIT -> PR URL */}
        <div className="bg-surface-container-lowest border border-white/[0.08] p-3.5 rounded-lg flex flex-wrap items-center gap-2 text-xs font-mono">
          <div className="flex flex-col">
            <span className="text-on-surface-variant text-[10px] uppercase tracking-wider">Original Repo</span>
            <span className="text-on-surface font-semibold">{repository}</span>
          </div>
          <span className="text-on-surface-variant font-bold px-1">→</span>
          {forkRepo ? (
            <>
              <div className="flex flex-col">
                <span className="text-amber-400/80 text-[10px] uppercase tracking-wider">Fork Repo</span>
                <span className="text-amber-300 font-semibold">{forkRepo}</span>
              </div>
              <span className="text-on-surface-variant font-bold px-1">→</span>
            </>
          ) : null}
          <div className="flex flex-col">
            <span className="text-on-surface-variant text-[10px] uppercase tracking-wider">Verified Commit</span>
            <span className="text-emerald-400 font-semibold">{shortCommit || "verified"}</span>
          </div>
          <span className="text-on-surface-variant font-bold px-1">→</span>
          <div className="flex flex-col">
            <span className="text-on-surface-variant text-[10px] uppercase tracking-wider">PR Link</span>
            {prUrl ? (
              <a href={prUrl} target="_blank" rel="noopener noreferrer" className="text-primary-fixed hover:underline font-semibold flex items-center gap-1">
                <GitPullRequest className="w-3 h-3" /> #{prNumber || "PR"}
              </a>
            ) : (
              <span className="text-on-surface-variant">None</span>
            )}
          </div>
        </div>

        {/* Core Info */}
        <div className="grid grid-cols-2 gap-space-md">
          <div className="bg-surface-container-low p-space-md rounded-lg border border-white/[0.05]">
            <p className="text-xs text-on-surface-variant mb-1">Repository</p>
            <p className="font-mono-code text-sm text-on-surface truncate">{repository}</p>
          </div>
          <div className="bg-surface-container-low p-space-md rounded-lg border border-white/[0.05]">
            <p className="text-xs text-on-surface-variant mb-1">Incident</p>
            <p className="font-mono-code text-sm text-on-surface truncate">{incidentId}</p>
          </div>
        </div>

    {/* RCA */}
    <div>
     <h3 className="text-sm font-semibold text-on-surface mb-2">ROOT CAUSE</h3>
     <div className="bg-surface-container-lowest border border-white/[0.05] rounded-lg p-space-md font-mono-code text-sm text-on-surface-variant">
      {rootCause}
     </div>
    </div>

    {/* Verification & Risk */}
    <div className="grid grid-cols-3 gap-space-md">
     <div className="flex flex-col gap-1">
      <span className="text-xs text-on-surface-variant">Verified Patch</span>
      <span className="flex items-center gap-1 text-sm font-semibold text-primary-fixed">
       <ShieldCheck className="w-4 h-4" /> ✓
      </span>
     </div>
     <div className="flex flex-col gap-1">
      <span className="text-xs text-on-surface-variant">Risk Assessment</span>
      <span className={`text-sm font-bold ${riskAssessment === 'HIGH' ? 'text-error' : 'text-primary-fixed'}`}>
       {riskAssessment}
      </span>
     </div>
     <div className="flex flex-col gap-1">
      <span className="text-xs text-on-surface-variant">Human Approval</span>
      <span className="flex items-center gap-1 text-sm font-semibold text-primary-fixed">
       <ShieldCheck className="w-4 h-4" /> ✓
      </span>
     </div>
    </div>

    {/* PR Info */}
    <div className="bg-surface-container-low p-space-md rounded-lg border border-primary-container/20 flex flex-col gap-4">
     <div>
      <p className="text-xs text-on-surface-variant mb-1">Recovery Branch</p>
      <p className="font-mono-code text-sm text-on-surface">{branchName || `ai-recovery/${incidentId}`}</p>
     </div>
     <div>
      <p className="text-xs text-on-surface-variant mb-1">Pull Request</p>
      <a href={prUrl || "#"} target="_blank" rel="noopener noreferrer" className="font-mono-code text-sm text-primary-fixed hover:underline flex items-center gap-2">
       <GitPullRequest className="w-4 h-4" /> #{prNumber}
      </a>
     </div>
     <div>
      <p className="text-xs text-on-surface-variant mb-1">Status</p>
      <p className="font-mono-code text-sm text-warning font-semibold">AWAITING HUMAN MERGE</p>
     </div>
    </div>
   </div>

   {/* Action Footer */}
   <div className="bg-surface-container-low border-t border-white/[0.05] p-space-md flex items-center justify-end gap-space-md">
    <button className="px-space-md py-space-sm text-on-surface-variant hover:text-on-surface transition-colors text-sm font-semibold tracking-wide flex items-center gap-2 border border-white/[0.1] rounded-md">
     <FileText className="w-4 h-4" /> VIEW AUDIT TRAIL
    </button>
    {prUrl && (
     <a 
      href={prUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="bg-primary text-white px-space-lg py-space-sm rounded-lg font-semibold tracking-wide hover:bg-primary/90 transition-colors flex items-center gap-2"
      onClick={() => {
        // Trigger a fake webhook to simulate PR merge for the demo
        fetch(`${API_BASE_URL}/api/v1/webhooks/github`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-GitHub-Event': 'pull_request',
            'X-Recovery-Mock': 'true'
          },
          body: JSON.stringify({
            action: 'closed',
            pull_request: {
              merged: true,
              merge_commit_sha: commitSha || "fake_merge_sha",
              head: { ref: branchName || `recovery/fix-${incidentId}` }
            },
            repository: { clone_url: "" }
          })
        }).catch(console.error);
      }}
     >
      <GitPullRequest className="w-4 h-4" /> OPEN GITHUB PR
     </a>
    )}
   </div>
  </div>
 );
}
