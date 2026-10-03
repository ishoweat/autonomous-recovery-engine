export function AppFooter() {
 return (
  <footer className="w-full bg-surface-container-lowest py-space-lg border-t border-white/[0.08] mt-auto">
   <div className="w-full px-gutter-desktop flex flex-col md:flex-row items-center justify-between gap-space-md">
    <div className="flex items-center gap-space-md">
     <span className="font-label-badge text-label-badge text-on-surface-variant">
      Autonomous Recovery Engine SRE Node #412
     </span>
     <span className="font-label-badge text-label-badge text-secondary-fixed">
      CLUSTER: US-EAST-DGX-01
     </span>
    </div>
    <div className="font-label-badge text-label-badge text-on-surface-variant">
     © 2025 Autonomous Recovery Systems. Hardened Kernel Ops.
    </div>
   </div>
  </footer>
 );
}
