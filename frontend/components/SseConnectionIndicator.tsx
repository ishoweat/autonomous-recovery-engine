import { Radio } from "lucide-react";

interface SseConnectionIndicatorProps {
 connected: boolean;
 error: string | null;
}

export function SseConnectionIndicator({
 connected,
 error
}: SseConnectionIndicatorProps) {
 return (
  <div className="flex items-center gap-2">
   <Radio
    className={[
     "h-3.5 w-3.5",
     connected
      ? "animate-pulse text-emerald-400"
      : "text-red-400"
    ].join(" ")}
   />

   <span className="font-mono text-[10px] text-slate-500">
    {connected
     ? "stream connected"
     : error ?? "stream disconnected"}
   </span>
  </div>
 );
}
