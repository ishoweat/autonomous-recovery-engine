import React from 'react';
import { ExternalLink } from "lucide-react";

interface TriggerBadgeProps {
  trigger?: string | null;
  deliveryId?: string | null;
  workflowUrl?: string | null;
}

export function TriggerBadge({ trigger, deliveryId, workflowUrl }: TriggerBadgeProps) {
  const isWebhook = trigger?.toLowerCase() === 'webhook';
  const label = isWebhook ? 'Webhook' : 'Manual';
  
  return (
    <div className="flex items-center gap-2">
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${
        isWebhook 
          ? 'bg-purple-50 text-purple-700 border-purple-200' 
          : 'bg-blue-50 text-blue-700 border-blue-200'
      }`}>
        <span className="mr-1 opacity-75">Trigger:</span>
        <span className="font-semibold">{label}</span>
      </span>
      
      {isWebhook && deliveryId && (
        <span className="text-[10px] font-mono text-on-surface-variant border border-white/[0.1] bg-surface-container-low px-2 py-0.5 rounded-md">
          ID: {deliveryId.slice(0, 8)}...
        </span>
      )}
      
      {isWebhook && workflowUrl && (
        <a 
          href={workflowUrl} 
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[10px] text-primary-fixed hover:underline"
        >
          <ExternalLink className="w-3 h-3" />
          View Run
        </a>
      )}
    </div>
  );
}
