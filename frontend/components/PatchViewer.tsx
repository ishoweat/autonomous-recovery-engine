"use client";

import Editor from "@monaco-editor/react";
import {
 Code2,
 Play,
 Loader2
} from "lucide-react";

interface PatchViewerProps {
 diff: string;
 onChange?: (value: string | undefined) => void;
 onSubmit?: () => void;
 submitting?: boolean;
}

export function PatchViewer({
 diff,
 onChange,
 onSubmit,
 submitting = false
}: PatchViewerProps) {
 return (
  <div className="panel overflow-hidden">
   <div className="panel-header flex flex-wrap items-center justify-between gap-3">
    <div className="flex items-center gap-2">
     <Code2 className="h-4 w-4 text-emerald-400" />

     <div>
      <p className="eyebrow text-emerald-400">
       Interactive remediation patch
      </p>

      <h2 className="mt-1 text-sm font-medium text-white">
       Editable patch editor
      </h2>
     </div>
    </div>

    <div className="flex items-center gap-3">
     <span className="rounded bg-emerald-400/10 px-2 py-1 font-mono text-[9px] text-emerald-400 border border-emerald-400/20">
      editable
     </span>

     {onSubmit ? (
      <button
       type="button"
       disabled={submitting}
       onClick={onSubmit}
       className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/10 px-3.5 py-1.5 font-mono text-[10px] font-semibold text-primary-fixed transition hover:bg-primary/20 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 shadow-sm"
      >
       {submitting ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
       ) : (
        <Play className="h-3.5 w-3.5 fill-current" />
       )}
       <span>Submit Patch & Run Sandbox</span>
      </button>
     ) : null}
    </div>
   </div>

   <div className="h-[430px]">
    <Editor
     height="100%"
     language="diff"
     theme="vs-dark"
     value={
      diff ||
      "# Type or paste your remediation diff here...\n"
     }
     onChange={onChange}
     options={{
      readOnly: false,
      minimap: {
       enabled: false
      },
      lineNumbers: "on",
      folding: false,
      wordWrap: "on",
      fontSize: 11,
      padding: {
       top: 14,
       bottom: 14
      },
      scrollBeyondLastLine: false,
      renderWhitespace: "selection",
      automaticLayout: true
     }}
    />
   </div>
  </div>
 );
}
