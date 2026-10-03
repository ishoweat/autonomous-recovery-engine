import re

with open("frontend/app/detect/page.tsx", "r") as f:
    content = f.read()

# 1. Add state
content = re.sub(
    r"const \[repairResult, setRepairResult\] = useState<any>\(null\);",
    r"const [repairResult, setRepairResult] = useState<any>(null);\n const [streamedReasoning, setStreamedReasoning] = useState<string>(\"\");",
    content,
    count=1
)

# 2. Clear state on Analyze
content = re.sub(
    r"setRepairResult\(null\);",
    r"setRepairResult(null);\n  setStreamedReasoning(\"\");",
    content,
    count=1
)

# 3. Add to ALL_EVENTS
content = re.sub(
    r"\"approval_rejected\",",
    r"\"approval_rejected\",\n    \"llm_token_chunk\",",
    content,
    count=1
)

# 4. Handle event
handle_code = """
     } else if (eventType === "llm_token_chunk") {
      if (d.chunk || payload.metadata?.chunk) {
       setStreamedReasoning((prev) => prev + (d.chunk || payload.metadata?.chunk));
      }
     } else if (eventType === "risk_evaluated") {
"""
content = content.replace("     } else if (eventType === \"risk_evaluated\") {", handle_code)

# 5. Render in Nemotron panel (replace the "Thinking..." block)
render_code = """
         ) : analyzing || streamedReasoning ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-[#0F1115] to-[#161A1F]">
           <div className="relative">
            <div className="relative flex h-14 w-14 items-center justify-center rounded-full border border-blue-500/30 bg-blue-500/10">
             <Bot className="h-7 w-7 text-blue-400 animate-pulse" />
            </div>
           </div>
           <div className="text-center w-full max-w-2xl px-6">
            <p className="font-mono text-xs font-semibold text-blue-300">
             NVIDIA Nemotron Reasoning
            </p>
            {streamedReasoning ? (
             <div className="mt-4 text-left bg-black/40 p-4 rounded-lg border border-white/10 h-[200px] overflow-y-auto font-mono text-[11px] text-slate-300 whitespace-pre-wrap">
              {streamedReasoning}
             </div>
            ) : (
             <>
              <p className="mt-1.5 font-mono text-[11px] text-slate-400 max-w-[280px] leading-relaxed mx-auto">
               {analyzeStep || "Running agentic remediation pipeline..."}
              </p>
              <div className="flex gap-1.5 justify-center mt-4">
               {[0, 1, 2, 3, 4].map((i) => (
                <div
                 key={i}
                 className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce"
                 style={{ animationDelay: `${i * 0.12}s` }}
                />
               ))}
              </div>
             </>
            )}
           </div>
          </div>
         ) : repairResult && editorMode === "diff" ? (
"""
content = re.sub(
    r"\) : analyzing \? \(\n\s*<div className=\"h-full flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-\[#0F1115\] to-\[#161A1F\]\">.*?\) : repairResult && editorMode === \"diff\" \? \(",
    render_code.strip(),
    content,
    flags=re.DOTALL
)

with open("frontend/app/detect/page.tsx", "w") as f:
    f.write(content)
