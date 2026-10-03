import type { ReactNode } from "react";

interface StatCardProps {
 label: string;
 value: string;
 detail?: string;
 icon?: ReactNode;
}

export function StatCard({
 label,
 value,
 detail,
 icon
}: StatCardProps) {
 return (
  <div className="panel p-4">
   <div className="flex items-start justify-between">
    <div>
     <p className="eyebrow">{label}</p>

     <p className="mt-2 text-2xl font-semibold tracking-tight text-white">
      {value}
     </p>

     {detail ? (
      <p className="mt-1 text-xs text-slate-500">
       {detail}
      </p>
     ) : null}
    </div>

    {icon ? (
     <div className="rounded-lg border border-white/[0.06] bg-white/[0.025] p-2 text-slate-400">
      {icon}
     </div>
    ) : null}
   </div>
  </div>
 );
}
