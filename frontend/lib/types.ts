export type RiskDecision =
  | "ALLOW"
  | "APPROVE"
  | "BLOCK";

export type RecoveryNode =
  | "START"
  | "TRIAGE"
  | "ROOT_CAUSE"
  | "RISK_GATEWAY"
  | "REPAIR"
  | "SANDBOX"
  | "FAILURE_ANALYZER"
  | "GITHUB"
  | "ESCALATION"
  | "COMPLETE"
  | "UNKNOWN";

export interface RiskBreakdownItem {
  factor: string;
  value: number;
  weight: number;
  contribution: number;
  explanation: string;
}

export interface ExplainableRisk {
  score: number;
  breakdown: RiskBreakdownItem[];
  decision: RiskDecision;
}

export interface TestRunResult {
  exit_code: number;
  passed: boolean;
  status: string;
  summary?: string;
  stdout?: string;
  stderr?: string;
}

export interface TestResults {
  stdout: string;
  stderr: string;
  exit_code: number;
  tests_passed?: boolean;
  timed_out?: boolean;
  patch_applied?: boolean;
  runtime?: number;
  before_test?: TestRunResult;
  after_test?: TestRunResult;
}

export interface RootCauseAnalysis {
  summary?: string;
  affected_file?: string;
  file?: string;
  line_number?: number;
  line?: number;
  error_type?: string;
  error_message?: string;
  root_cause?: string;
  cause?: string;
  evidence?: string[];
  confidence?: number;
  proposed_fix?: string;
  [key: string]: unknown;
}

export interface GithubPayload {
  repository?: {
    full_name?: string;
    name?: string;
    default_branch?: string;
  };
  ref?: string;
  sender?: {
    login?: string;
  };
  head_commit?: {
    id?: string;
    message?: string;
  };
  workflow_run?: {
    id?: number;
    name?: string;
    head_branch?: string;
    head_sha?: string;
    conclusion?: string;
    status?: string;
    [key: string]: unknown;
  };
  fork_repo?: string;
  [key: string]: unknown;
}

export interface RecoveryState {
  incident_id: string;
  repository?: string;
  repository_owner?: string;
  repository_name?: string;
  repository_full_name?: string;
  repository_url?: string;
  default_branch?: string;
  source_branch?: string;
  branch?: string;
  branch_name?: string;
  commit_sha?: string;
  fork_repo?: string;
  github_payload: GithubPayload;
  is_mock_mode: boolean;
  triage_context: string;
  root_cause_analysis: RootCauseAnalysis;
  explainable_risk: ExplainableRisk;
  action_decision: RiskDecision | string;
  human_approved: boolean;
  current_patch_diff: string;
  test_results: TestResults;
  retry_count: number;
  pr_url: string;
  pr_number?: number;
  patch_explanation?: string;
  generated_test_code?: string;
  similar_past_cases?: Array<Record<string, unknown>>;
  learning_confidence_boost?: number;
  is_shadow_mode?: boolean;
  runtime_model?: string;
  // ARE Option 1 — Adversarial Resilience Layer
  adversarial_report?: AdversarialReport;
  // ARE Option 2 — Polyglot Fix Engine
  polyglot_language?: string;
  polyglot_audiences?: PolyglotAudiences;
}

export interface ExplainFailureResponse {
  incident_id: string;
  error_type: string;
  simple_explanation: string;
  analogy: string;
  key_takeaway: string;
  affected_file?: string;
}

export interface RootCauseFrequency {
  root_cause: string;
  error_type: string;
  count: number;
  percentage: number;
}


export interface LearnedPatternItem {
  id: string;
  incident_id?: string;
  repository: string;
  error_type: string;
  root_cause_summary: string;
  patch_pattern: string;
  confidence: number;
  file_path?: string;
  pattern_metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface WeeklyLearningReport {
  incidents_fixed: number;
  average_resolution_time_seconds: number;
  most_common_root_causes: Array<{
    root_cause: string;
    error_type: string;
    count: number;
    percentage: number;
  }>;
  estimated_time_saved_minutes: number;
  total_learned_patterns: number;
  shadow_mode_active: boolean;
  report_period: string;
  patterns: LearnedPatternItem[];
}

export interface TelemetryEvent {
  id?: string;
  event_id?: string;
  event_type?: string;
  timestamp?: string;
  incident_id: string;
  node: RecoveryNode;
  stage?: string;
  status: "started" | "completed" | "failed" | "waiting" | string;
  message: string;
  reasoning?: string;
  state?: Partial<RecoveryState>;
  metadata?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

export type ConnectionStatus =
  | "CONNECTED"
  | "RECONNECTING"
  | "OFFLINE"
  | "RECOVERED"
  | "DISCONNECTED"
  | "RECONNECTED"
  | "BACKEND_OFFLINE";

export interface IncidentStreamState {
  state: RecoveryState | null;
  events: TelemetryEvent[];
  connected: boolean;
  connectionStatus: ConnectionStatus;
  completed: boolean;
  error: string | null;
}

// ── ARE Option 1: Adversarial Resilience Layer ───────────────────────────────

export interface CveHit {
  pkg: string;
  version: string;
  cve_id: string;
  severity: string;
  summary: string;
}

export interface MutationDetail {
  mutation: string;
  status: "killed" | "survived";
}

export interface AdversarialRaw {
  mutation: {
    mutation_score: number;
    killed: number;
    survived: number;
    details: MutationDetail[];
    pass: boolean;
  };
  cve: {
    deps_scanned: [string, string][];
    cve_hits: CveHit[];
    critical_count: number;
    pass: boolean;
  };
  behavioral: {
    behavioral_flags: string[];
    risk_level: string;
    confidence: number;
    reasoning: string;
    pass: boolean;
  };
}

export interface AdversarialReport {
  mutation_score: number;
  cve_hits: CveHit[];
  behavioral_flags: string[];
  overall_safe: boolean;
  confidence: number;
  summary: string;
  raw: AdversarialRaw;
}

// ── ARE Option 2: Polyglot Fix Engine ────────────────────────────────────────

export interface PolyglotAudiences {
  devops: string;
  product: string;
  researcher: string;
}

export interface PolyglotFixResult {
  language: string;
  semantic_issue: string;
  fixed_code: string;
  new_test: string;
  explanation: string;
  confidence: number;
  audiences: PolyglotAudiences;
}

// ── ARE Option 5: ROI Dashboard ───────────────────────────────────────────────

export interface DailyHoursSaved {
  date: string;
  hours_saved: number;
  cost_saved: number;
}

export interface DailyFixes {
  date: string;
  count: number;
  automated_count: number;
}

export interface ROIDashboardData {
  total_fixes: number;
  total_human_hours_saved: number;
  total_cost_saved_usd: number;
  incidents_prevented: number;
  automated_fix_rate_pct: number;
  avg_mttr_before_min: number;
  avg_mttr_after_min: number;
  mttr_reduction_pct: number;
  test_pass_rate_improvement_pct: number;
  daily_hours_saved: DailyHoursSaved[];
  daily_fixes: DailyFixes[];
  fixes_by_language: Record<string, number>;
  fixes_by_severity: Record<string, number>;
  fixes_by_repo: Record<string, number>;
  headline: {
    total_cost_saved: string;
    hours_saved_text: string;
    mttr_reduction_text: string;
    incidents_prevented: string;
    auto_rate: string;
    monthly_cost_saved: string;
  };
}
