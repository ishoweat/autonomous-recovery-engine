/**
 * Exact mirror of backend/orchestration/state.py::RecoveryState.
 *
 * Keep these names synchronized with the Python TypedDict.
 */
export interface RecoveryState {
  incident_id: string;
  repository_owner?: string;
  repository_name?: string;
  repository_full_name?: string;
  repository_url?: string;
  repository?: string;
  default_branch?: string;
  source_branch?: string;
  github_payload: Record<string, unknown>;
  is_mock_mode: boolean;
  triage_context: string;
  root_cause_analysis: Record<string, unknown>;
  explainable_risk: ExplainableRiskPayload;
  action_decision: "ALLOW" | "APPROVE" | "BLOCK";
  human_approved: boolean;
  current_patch_diff: string;
  test_results: TestResults;
  retry_count: number;
  pr_url: string;
  runtime_model?: string;
}

export interface TestResults {
  stdout: string;
  stderr: string;
  exit_code: number;
}

export interface ExplainableRiskPayload {
  score: number;
  breakdown: RiskBreakdownItem[];
  decision: "ALLOW" | "APPROVE" | "BLOCK";
}

export interface RiskBreakdownItem {
  factor: string;
  value: number;
  weight: number;
  contribution: number;
  explanation: string;
}

export type AgentNodeStatus =
  | "started"
  | "running"
  | "completed"
  | "failed"
  | "waiting"
  | "escalated";

export type IncidentEventType =
  | "incident_created"
  | "node_started"
  | "node_completed"
  | "node_failed"
  | "reasoning"
  | "risk_evaluated"
  | "state_mutation"
  | "sandbox_started"
  | "sandbox_completed"
  | "approval_required"
  | "approval_received"
  | "retry"
  | "pr_created"
  | "escalated"
  | "incident_resolved"
  | "heartbeat"
  | "error";

export interface AgentNodeStatusPayload {
  node: string;
  status: AgentNodeStatus;
  message?: string;
  reasoning?: string;
  retryCount?: number;
  timestamp: string;
}

export interface IncidentEvent {
  event_id: string;
  incident_id: string;
  event_type: IncidentEventType | string;
  node_name?: string | null;
  message: string;
  reasoning?: string | null;
  metadata?: Record<string, unknown>;
  timestamp: string;
  risk_score?: number | null;
  retry_count?: number | null;
  state_key?: keyof RecoveryState | null;
  state_value?: unknown;
  node_status?: AgentNodeStatus | null;
}

export interface PatchApprovalRequest {
  approved: boolean;
  operator?: string;
  reason?: string;
  expected_patch_hash?: string;
}

export interface PatchApprovalResponse {
  incident_id: string;
  approved: boolean;
  resumed: boolean;
  idempotent: boolean;
  next_node: string;
  message: string;
}

export interface WebhookAcceptedResponse {
  accepted: boolean;
  incident_id: string;
  repository: string;
  branch: string;
  is_mock_mode: boolean;
  message: string;
}

export interface IncidentSnapshot {
  incident_id: string;
  state: RecoveryState;
  status: string;
  updated_at?: string;
}

export interface SSEConnectionState {
  connected: boolean;
  lastEventId?: string;
  reconnectAttempts: number;
}
