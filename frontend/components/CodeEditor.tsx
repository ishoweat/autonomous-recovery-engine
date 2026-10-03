"use client";

import { useCallback, useRef, useState, useEffect } from "react";
import Editor, { DiffEditor } from "@monaco-editor/react";
import {
 Brain,
 Check,
 Code2,
 FileCode,
 FlaskConical,
 GitCompare,
 Lightbulb,
 Loader2,
 Play,
 RotateCcw,
 Sparkles,
 Zap,
} from "lucide-react";
import { repairCode, type CodeRepairResponse } from "@/lib/api";
import { ExplainFailureModal } from "@/components/ExplainFailureModal";

interface CodeEditorProps {
 incidentId: string;
 onRepairComplete?: (result: CodeRepairResponse) => void;
 filePath?: string;
 initialExplanation?: string;
 initialGeneratedTest?: string;
 autoStartRepair?: boolean;
}

const DEFAULT_BROKEN_CODE = `def authenticate(payload: dict) -> dict:
  """
  Authenticate user request against repository registry.
  """
  user_id = payload["user_id"]
  return lookup_user(user_id)
`;

const DEFAULT_REPAIRED_CODE = `def authenticate(payload: dict) -> dict:
  """
  Authenticate user request against repository registry.
  """
  user_id = payload.get("user_id")
  if not user_id:
    raise ValueError("user_id is required")
  return lookup_user(user_id)
`;

const DEFAULT_GENERATED_TEST = `import pytest
from backend.api.auth import authenticate

def test_missing_user_id_payload_raises_value_error():
  """
  Regression Test: Verifies that missing user_id raises controlled ValueError
  instead of an unhandled KeyError crashing the worker.
  """
  with pytest.raises(ValueError, match="user_id is required"):
    authenticate({})
`;

export function CodeEditor({
 incidentId,
 onRepairComplete,
 filePath = "backend/api/auth.py",
 initialExplanation,
 initialGeneratedTest,
 autoStartRepair,
}: CodeEditorProps) {
 const [activeTab, setActiveTab] = useState<"side-by-side" | "unified" | "generated-test">("side-by-side");
 const [isFixing, setIsFixing] = useState(false);
 const [fixSuccess, setFixSuccess] = useState(false);
 const [originalCode, setOriginalCode] = useState(DEFAULT_BROKEN_CODE);
 const [modifiedCode, setModifiedCode] = useState(DEFAULT_REPAIRED_CODE);
 const [patchDiff, setPatchDiff] = useState<string | null>(null);
 const [explanation, setExplanation] = useState<string>(
  initialExplanation ||
   "Why I fixed it this way: The fix safely accesses user_id via payload.get() and raises a controlled ValueError when missing, preventing the unhandled KeyError while preserving valid authentication flows."
 );
 const [generatedTest, setGeneratedTest] = useState<string>(
  initialGeneratedTest || DEFAULT_GENERATED_TEST
 );
 const repairLockRef = useRef(false);

 const handleFixCode = useCallback(async () => {
  if (repairLockRef.current) return;
  repairLockRef.current = true;
  setIsFixing(true);

  try {
   const result = await repairCode(incidentId, {
    code: originalCode,
    file_path: filePath,
    language: "python",
    error_message: "KeyError: 'user_id'",
   });

   if (result.corrected_code) {
    setModifiedCode(result.corrected_code);
   }
   if (result.patch_diff) {
    setPatchDiff(result.patch_diff);
   }
   if (result.explanation) {
    setExplanation(`Why I fixed it this way: ${result.explanation}`);
   }
   setFixSuccess(true);
   setActiveTab("side-by-side");

   if (onRepairComplete) {
    onRepairComplete(result);
   }
  } catch (err: any) {
   setFixSuccess(false);
   setExplanation(`Repair failed: ${err?.message || "Internal inference failure"}`);
  } finally {
   setIsFixing(false);
   repairLockRef.current = false;
  }
 }, [incidentId, filePath, originalCode, onRepairComplete]);

 useEffect(() => {
  if (autoStartRepair && !isFixing && !fixSuccess && !repairLockRef.current) {
   handleFixCode();
  }
 }, [autoStartRepair, isFixing, fixSuccess, handleFixCode]);

 return (
  <div className="rounded-lg bg-surface-container-lowest shadow-[0_1px_3px_rgba(0,0,0,0.4)] overflow-hidden border border-white/[0.08] flex flex-col">
   {/* Code Editor Header & Tab Switcher */}
   <div className="flex flex-wrap items-center justify-between gap-space-sm px-space-md py-space-sm bg-surface-container-low border-b border-surface-container-highest">
    <div className="flex items-center gap-space-sm">
     <div className="p-1 rounded bg-secondary/15 text-secondary-fixed">
      <Code2 className="w-4 h-4" />
     </div>
     <span className="font-label-caps text-label-caps text-on-surface font-semibold">
      NEURAL PATCH WORKSPACE
     </span>
     <span className="font-mono-code text-mono-code text-xs text-on-surface-variant hidden sm:inline">
      | {filePath}
     </span>
    </div>

    {/* Action Buttons */}
    <div className="flex items-center gap-space-xs">
     <ExplainFailureModal
      incidentId={incidentId}
      filePath={filePath}
      errorMessage="KeyError: 'user_id'"
     />

     <button
      onClick={handleFixCode}
      disabled={isFixing}
      className={`flex items-center gap-space-xs px-space-md py-space-xs rounded-lg font-label-caps text-label-caps transition-all border ${
       fixSuccess
        ? "bg-primary text-surface-container-lowest font-bold border-primary "
        : "bg-primary-container/20 hover:bg-primary-container hover:text-surface-container-lowest text-primary-fixed border-primary/30"
      }`}
     >
      {isFixing ? (
       <Loader2 className="w-4 h-4 animate-spin" />
      ) : fixSuccess ? (
       <Check className="w-4 h-4" />
      ) : (
       <Sparkles className="w-4 h-4" />
      )}
      <span>
       {isFixing
        ? "GENERATING PATCH..."
        : fixSuccess
         ? "PATCH GENERATED"
         : "GENERATE REPAIR"}
      </span>
     </button>
    </div>
   </div>

   {/* View Tabs */}
   <div className="flex items-center justify-between px-space-md py-2 bg-surface-container-low/50 border-b border-surface-container-highest/60">
    <div className="flex items-center gap-1.5">
     <button
      onClick={() => setActiveTab("side-by-side")}
      className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-mono-code transition-all ${
       activeTab === "side-by-side"
        ? "bg-primary-container/20 text-primary-fixed font-bold border border-primary-container/40"
        : "text-on-surface-variant hover:text-white hover:bg-white/[0.04]"
      }`}
     >
      <GitCompare className="w-3.5 h-3.5" />
      <span>Side-by-Side Diff</span>
     </button>

     <button
      onClick={() => setActiveTab("unified")}
      className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-mono-code transition-all ${
       activeTab === "unified"
        ? "bg-primary-container/20 text-primary-fixed font-bold border border-primary-container/40"
        : "text-on-surface-variant hover:text-white hover:bg-white/[0.04]"
      }`}
     >
      <FileCode className="w-3.5 h-3.5" />
      <span>Unified Diff</span>
     </button>

     <button
      onClick={() => setActiveTab("generated-test")}
      className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-mono-code transition-all ${
       activeTab === "generated-test"
        ? "bg-secondary/20 text-secondary-fixed font-bold border border-secondary/40"
        : "text-on-surface-variant hover:text-white hover:bg-white/[0.04]"
      }`}
     >
      <FlaskConical className="w-3.5 h-3.5" />
      <span>Auto-Generated Pytest</span>
     </button>
    </div>

    <span className="text-[11px] font-mono-code text-on-surface-variant hidden md:inline">
     {activeTab === "side-by-side"
      ? "Original (Left) vs AI Patch (Right)"
      : activeTab === "unified"
       ? "Standard Unified Git Diff"
       : "Pytest Test Reproducing Bug"}
    </span>
   </div>

   {/* "Why I Fixed It This Way" Explanation Banner */}
   {explanation && (
    <div className="px-space-md py-2.5 bg-primary-container/10 border-b border-primary-container/20 flex items-start gap-2.5">
     <Brain className="w-4 h-4 text-primary-fixed shrink-0 mt-0.5" />
     <div className="flex flex-col">
      <span className="text-[11px] font-mono-code text-primary-fixed font-semibold">
       NEMOTRON REASONING EXPLANATION
      </span>
      <p className="text-xs text-white/90 font-body-sm leading-relaxed mt-0.5">
       {explanation}
      </p>
     </div>
    </div>
   )}

   {/* Monaco Diff / Editor Views */}
   <div className="h-[340px] bg-[#0F1115] relative">
    {activeTab === "side-by-side" && (
     <DiffEditor
      height="100%"
      original={originalCode}
      modified={modifiedCode}
      language="python"
      theme="vs-dark"
      options={{
       readOnly: false,
       renderSideBySide: true,
       minimap: { enabled: false },
       fontSize: 12,
       lineNumbers: "on",
       scrollBeyondLastLine: false,
       automaticLayout: true,
       renderOverviewRuler: false,
       padding: { top: 12, bottom: 12 },
      }}
     />
    )}

    {activeTab === "unified" && (
     <Editor
      height="100%"
      language="diff"
      theme="vs-dark"
      value={
       patchDiff ||
       `--- a/${filePath}\n+++ b/${filePath}\n@@ -1,6 +1,11 @@\n def authenticate(payload):\n-  user_id = payload["user_id"]\n+  user_id = payload.get("user_id")\n+  if not user_id:\n+    raise ValueError("user_id is required")\n   return lookup_user(user_id)\n`
      }
      options={{
       readOnly: true,
       minimap: { enabled: false },
       fontSize: 12,
       lineNumbers: "on",
       scrollBeyondLastLine: false,
       automaticLayout: true,
       padding: { top: 12, bottom: 12 },
      }}
     />
    )}

    {activeTab === "generated-test" && (
     <Editor
      height="100%"
      language="python"
      theme="vs-dark"
      value={generatedTest}
      options={{
       readOnly: true,
       minimap: { enabled: false },
       fontSize: 12,
       lineNumbers: "on",
       scrollBeyondLastLine: false,
       automaticLayout: true,
       padding: { top: 12, bottom: 12 },
      }}
     />
    )}
   </div>

   {/* Code Editor Bottom Bar */}
   <div className="px-space-md py-space-sm bg-surface-container-low flex flex-wrap items-center justify-between gap-space-sm border-t border-surface-container-highest">
    <div className="flex items-center gap-space-sm text-xs font-mono-code text-on-surface-variant">
     <span>
      Target: <span className="text-on-surface">{filePath}</span>
     </span>
     <span>•</span>
     <span>
      Regression Test:{" "}
      <span className="text-primary-fixed font-semibold">1 Auto-Generated</span>
     </span>
    </div>
    <div className="flex items-center gap-2">
     <span className="text-[10px] font-mono-code text-primary-fixed bg-primary-container/10 px-2 py-0.5 rounded border border-primary-container/20">
      POLICY GATE: HUMAN APPROVAL REQUIRED
     </span>
    </div>
   </div>
  </div>
 );
}
