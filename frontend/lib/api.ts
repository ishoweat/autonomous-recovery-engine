import type {
  RecoveryState,
  RiskDecision
} from "@/lib/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

export interface ApprovalResponse {
  incident_id: string;
  approved: boolean;
  action: string;
  message: string;
}

async function parseResponse<T>(
  response: Response
): Promise<T> {
  const text = await response.text();

  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = {
        detail: text
      };
    }
  }

  if (!response.ok) {
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload
        ? String(
            (payload as { detail: unknown }).detail
          )
        : `Request failed with HTTP ${response.status}`;

    throw new Error(message);
  }

  return payload as T;
}

export async function getIncident(
  incidentId: string
): Promise<RecoveryState> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/incident/${encodeURIComponent(
      incidentId
    )}`,
    {
      method: "GET",
      cache: "no-store",
      credentials: "include"
    }
  );

  return parseResponse<RecoveryState>(response);
}

export async function approveIncident(
  incidentId: string,
  approved: boolean
): Promise<ApprovalResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/incident/${encodeURIComponent(
      incidentId
    )}/approve`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "include",
      body: JSON.stringify({
        approved,
        operator: "mission-control-operator",
        reviewer: "mission-control-operator",
        reason: approved
          ? "Approved by Mission Control operator"
          : "Rejected by Mission Control operator"
      })
    }
  );

  return parseResponse<ApprovalResponse>(response);
}

export function incidentStreamUrl(
  incidentId: string
): string {
  return `${API_BASE_URL}/api/v1/incident/${encodeURIComponent(
    incidentId
  )}/stream`;
}

export async function submitGithubWebhook(
  payload?: unknown
): Promise<{ incident_id: string }> {
  const demoPayload = payload ?? {
    action: "completed",
    workflow_run: {
      id: 987654321,
      name: "pytest",
      conclusion: "failure",
      head_branch: "main",
      head_sha: "0123456789abcdef",
      repository: {
        full_name: "demo/autonomous-recovery-engine"
      }
    },
    repository: {
      full_name: "demo/autonomous-recovery-engine"
    },
    sender: {
      login: "github-actions"
    }
  };

  const response = await fetch(
    `${API_BASE_URL}/webhook/github`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "workflow_run"
      },
      credentials: "include",
      body: JSON.stringify(demoPayload)
    }
  );

  return parseResponse<{ incident_id: string }>(
    response
  );
}

export interface CodeRepairRequest {
  code: string;
  file_path?: string;
  language?: string;
  error_message?: string;
}

export interface CodeRepairResponse {
  incident_id: string;
  original_code: string;
  corrected_code: string;
  patch_diff: string;
  explanation: string;
  risk_score: number;
  risk_decision: string;
  test_results: {
    stdout: string;
    stderr: string;
    exit_code: number;
    tests_passed?: boolean;
  };
  status: string;
}

export async function repairCode(
  incidentId: string,
  request: CodeRepairRequest
): Promise<CodeRepairResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/incident/${encodeURIComponent(
      incidentId
    )}/repair`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "include",
      body: JSON.stringify(request)
    }
  );

  return parseResponse<CodeRepairResponse>(response);
}

export function isRiskDecision(
  value: string
): value is RiskDecision {
  return (
    value === "ALLOW" ||
    value === "APPROVE" ||
    value === "BLOCK"
  );
}

export interface RepoTreeNode {
  name: string;
  path: string;
  type: "tree" | "blob";
  size?: number;
  has_error?: boolean;
  error_badge?: "error" | null;
  error_context?: string | null;
  children?: RepoTreeNode[];
}

export interface RepoTreeItem {
  path: string;
  type: "tree" | "blob";
  size?: number;
  has_error?: boolean;
  error_badge?: "error" | null;
  error_context?: string | null;
}

export interface RepoTreeResponse {
  owner: string;
  repo: string;
  full_name: string;
  default_branch: string;
  commit_sha?: string;
  tree: RepoTreeItem[] | RepoTreeNode[];
  nested_tree?: RepoTreeNode[];
  flat_tree?: RepoTreeItem[];
  total_files: number;
  is_mock: boolean;
}

export interface FileContentResponse {
  file_path: string;
  content: string;
  language: string;
  size: number;
}

export interface CreatePrRequest {
  repo?: string;
  baseBranch?: string;
  filePath?: string;
  fixedContent?: string;
  commitMessage?: string;
  prTitle?: string;
  prBody?: string;

  incident_id?: string;
  repository_url?: string;
  file_path?: string;
  corrected_code?: string;
  patch_diff?: string;
  branch_name?: string;
  pr_title?: string;
  pr_body?: string;
  commit_message?: string;
  auto_merge?: boolean;
  autoMerge?: boolean;
}

export interface CreatePrResponse {
  incident_id?: string;
  pr_url: string;
  pr_number: number;
  prUrl?: string;
  prNumber?: number;
  branch_name: string;
  branchName?: string;
  commit_sha: string;
  commitSha?: string;
  merged?: boolean;
  merge_sha?: string;
  merge_mode?: string;
  mergeMode?: string;
  is_mock: boolean;
  message: string;
}

export async function fetchRepoTree(
  repositoryUrl: string,
  branch: string = "main"
): Promise<RepoTreeResponse> {
  const url = `${API_BASE_URL}/api/github/tree?repo=${encodeURIComponent(
    repositoryUrl
  )}&branch=${encodeURIComponent(branch)}`;
  const response = await fetch(url, {
    method: "GET",
    credentials: "include"
  });

  return parseResponse<RepoTreeResponse>(response);
}

export async function fetchFileContent(
  repositoryUrl: string,
  filePath: string,
  branch: string = "main"
): Promise<FileContentResponse> {
  const url = `${API_BASE_URL}/api/github/file-content?repo=${encodeURIComponent(
    repositoryUrl
  )}&path=${encodeURIComponent(filePath)}&branch=${encodeURIComponent(branch)}`;
  const response = await fetch(url, {
    method: "GET",
    credentials: "include"
  });

  return parseResponse<FileContentResponse>(response);
}

export async function createGitHubPr(
  request: CreatePrRequest
): Promise<CreatePrResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (typeof window !== "undefined") {
    const sessionId = localStorage.getItem("session_id");
    if (sessionId) {
      headers["X-Session-ID"] = sessionId;
      headers["Authorization"] = `Bearer ${sessionId}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/github/create-pr`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(request)
    });
  } catch (err: any) {
    const isNetworkError =
      err instanceof TypeError &&
      (err.message === "Failed to fetch" || err.message.includes("NetworkError"));
    if (isNetworkError) {
      throw new Error(
        `Unable to reach backend server at ${API_BASE_URL}. Please ensure the backend is running.`
      );
    }
    throw err;
  }

  return parseResponse<CreatePrResponse>(response);
}

export interface PrStatusResponse {
  status: "queued" | "in_progress" | "completed" | string;
  conclusion: "success" | "failure" | string;
  testsPassed: boolean;
  tests_passed?: boolean;
  message: string;
  sha?: string;
  prNumber?: number;
}

export async function fetchPrStatus(
  repo: string,
  prNumber: number,
  sha: string
): Promise<PrStatusResponse> {
  const url = `${API_BASE_URL}/api/github/pr-status?repo=${encodeURIComponent(
    repo
  )}&prNumber=${prNumber}&sha=${encodeURIComponent(sha)}`;
  const response = await fetch(url, {
    method: "GET",
    credentials: "include"
  });

  return parseResponse<PrStatusResponse>(response);
}

export interface MergePrResponse {
  merged: boolean;
  message: string;
  sha?: string;
}

export async function mergeGitHubPr(
  repo: string,
  prNumber: number,
  commitMessage?: string,
  incidentId?: string
): Promise<MergePrResponse> {
  const response = await fetch(`${API_BASE_URL}/api/github/merge-pr`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify({ repo, prNumber, commitMessage, incident_id: incidentId, incidentId })
  });

  return parseResponse<MergePrResponse>(response);
}

export interface PostMergeVerifyResponse {
  tests_passed: boolean;
  exit_code: number;
  message: string;
  error?: string;
  merged_sha?: string;
}

export async function verifyPostMerge(
  repo: string,
  prNumber: number,
  incidentId?: string,
  commitSha?: string
): Promise<PostMergeVerifyResponse> {
  const response = await fetch(`${API_BASE_URL}/api/github/post-merge-verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify({
      repo,
      pr_number: prNumber,
      incident_id: incidentId,
      commit_sha: commitSha
    })
  });

  return parseResponse<PostMergeVerifyResponse>(response);
}

export interface ExplainFailureResponse {
  incident_id: string;
  error_type: string;
  simple_explanation: string;
  analogy: string;
  key_takeaway: string;
  affected_file?: string;
}

export async function explainIncidentFailure(
  incidentId: string,
  request?: { error_message?: string; affected_file?: string; code_context?: string }
): Promise<ExplainFailureResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/incident/${encodeURIComponent(incidentId)}/explain-failure`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "include",
      body: JSON.stringify(request ?? {})
    }
  );

  return parseResponse<ExplainFailureResponse>(response);
}

export async function fetchWeeklyLearningReport(): Promise<import("./types").WeeklyLearningReport> {
  const response = await fetch(`${API_BASE_URL}/api/v1/learning/report`, {
    method: "GET",
    cache: "no-store",
    credentials: "include"
  });

  return parseResponse<import("./types").WeeklyLearningReport>(response);
}

// ── ARE v2 API functions ──────────────────────────────────────────────────────

import type {
  AdversarialReport,
  PolyglotFixResult,
  ROIDashboardData,
} from "@/lib/types";

export async function runAdversarialCheck(
  patchCode: string,
  patchDiff: string = ""
): Promise<AdversarialReport> {
  const response = await fetch(`${API_BASE_URL}/api/v2/adversarial/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      patch_code: patchCode,
      patch_diff: patchDiff,
      mock_mode: false,
    }),
  });
  return parseResponse<AdversarialReport>(response);
}

export async function runPolyglotFix(
  failedTestLog: string,
  sourceFiles: Record<string, string>
): Promise<PolyglotFixResult> {
  const response = await fetch(`${API_BASE_URL}/api/v2/polyglot/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      failed_test_log: failedTestLog,
      source_files: sourceFiles,
      mock_mode: false,
    }),
  });
  return parseResponse<PolyglotFixResult>(response);
}

export async function fetchROIDashboard(
  days: number = 30
): Promise<ROIDashboardData> {
  const response = await fetch(
    `${API_BASE_URL}/api/v2/roi/dashboard?days=${days}`,
    { method: "GET", cache: "no-store", credentials: "include" }
  );
  return parseResponse<ROIDashboardData>(response);
}

export async function fetchROIWeeklyReport(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/v2/roi/weekly-report`, {
    method: "GET",
    cache: "no-store",
    credentials: "include"
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

// ── Phase 4: Remediate endpoint ───────────────────────────────────────────────

export interface RiskBreakdownScore {
  label: string;
  score: number;     // 0–1 contribution
  weight: number;
  explanation: string;
}

export interface RemediateRiskAssessment {
  overall: number;
  decision: "ALLOW" | "APPROVE" | "BLOCK";
  breakdown: RiskBreakdownScore[];
}

export interface ModelInferenceTelemetry {
  provider: string;
  model: string;
  request_started?: string;
  response_received?: string;
  success: boolean;
  latency: number;
  request_id?: string;
  token_usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  } | null;
  inference_status?: "RECEIVED" | "PENDING" | "ERROR" | "LIVE";
  error?: string;
}

export interface TavilySource {
  id: number;
  url: string;
  domain: string;
  title: string;
  snippet: string;
  score?: number;
  support?: string;
  extracted?: string;
}

export interface TavilyEvidencePayload {
  queries: string[];
  sources: TavilySource[];
  extracted_text?: string;
  confidence: "high" | "medium" | "low" | "none";
  loop_trail?: string[];
  trail_string?: string;
  why_fix?: string;
}

export interface RemediateResponse {
  incidentId: string;
  filePath?: string;
  fixedCode: string;
  diff: string;
  explanation: string;
  rootCause?: string;
  affectedLineNumber?: number;
  defectStatus?: "CONFIRMED" | "SUSPECTED";
  defectCategory?: string;
  verificationStatus?: "VERIFIED" | "PARTIALLY_VERIFIED" | "PARTIALLY VERIFIED" | "FAILED" | "UNVERIFIED";
  generatedTestCode?: string;
  riskAssessment: RemediateRiskAssessment;
  testResults: {
    stdout: string;
    stderr: string;
    exit_code: number;
    tests_passed: boolean;
    runtime?: number;
    stage?: string;
    violations?: string[];
    verification_status?: string;
    test_executed?: boolean;
    after_test?: { passed?: boolean; exit_code?: number; status?: string; summary?: string };
    before_test?: { passed?: boolean; exit_code?: number; status?: string; summary?: string };
  };
  inference?: ModelInferenceTelemetry;
  tavilyEvidence?: TavilyEvidencePayload;
}


export interface RemediateRequest {
  repoUrl: string;
  filePath: string;
  fileContent: string;
  stackTrace?: string;
  errorMessage?: string;
}

export async function remediateCode(
  request: RemediateRequest
): Promise<RemediateResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (typeof window !== "undefined") {
    const sessionId = localStorage.getItem("session_id");
    if (sessionId) {
      headers["X-Session-ID"] = sessionId;
      headers["Authorization"] = `Bearer ${sessionId}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/remediate`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify({
        repoUrl: request.repoUrl || "",
        filePath: request.filePath || "calculator.py",
        fileContent: request.fileContent || "",
        stackTrace: request.stackTrace || "",
        errorMessage: request.errorMessage || "",
      }),
    });
  } catch (err: any) {
    const isNetworkError =
      err instanceof TypeError &&
      (err.message === "Failed to fetch" || err.message.includes("NetworkError"));
    if (isNetworkError) {
      throw new Error(
        `Unable to reach backend server at ${API_BASE_URL}. Please ensure the backend server is running on port 8000.`
      );
    }
    throw err;
  }

  return parseResponse<RemediateResponse>(response);
}
