export interface DocumentInfo {
  doc_name: string;
  pages: number;
  doc_id: string;
  effective_date: string;
  amends_doc_ids: string[];
}

export interface CitationHighlight {
  doc_name: string;
  page_number: number;
  verbatim_quote: string;
  bboxes: number[][];
  page_width: number;
  page_height: number;
  label?: string;
  color?: "yellow" | "red";
}

export interface VerifiedClaim extends CitationHighlight {
  sentence: string;
  english_claim?: string;
  quote_match_score: number;
  nli_scores: {
    entailment: number;
    neutral: number;
    contradiction: number;
  };
}

export interface BlockedClaim {
  sentence: string;
  doc_name: string;
  page_number: number;
  verbatim_quote: string;
  block_reason: string;
}

export interface AmendmentStep {
  clause_ref: string;
  subject: string;
  doc_name: string;
  doc_id: string;
  effective_date: string;
  action: string;
  summary: string;
  page_number: number;
  status: "ACTIVE" | "SUPERSEDED";
  superseded_by?: string;
}

export interface AmendmentChain {
  clause_ref: string;
  subject: string;
  active_doc_id: string;
  active_summary: string;
  steps: AmendmentStep[];
}

export interface ContradictionItem {
  subject: string;
  conflict_type: string;
  explanation: string;
  nli_contradiction_score: number;
  source_a: CitationHighlight;
  source_b: CitationHighlight;
}

export interface CalculationResult {
  operation: string;
  formula: string;
  inputs: Record<string, string>;
  steps: string[];
  result: string;
  numeric_result: number;
  citation: CitationHighlight;
}

export interface GuardrailCheck {
  name: string;
  status: string;
  detail: string;
}

export interface QueryResponse {
  question: string;
  language?: string;
  abstained: boolean;
  answer: string;
  faithfulness: {
    score_percent: number;
    verified_sentences: number;
    total_draft_sentences: number;
    displayed_backed_percent: number;
  };
  verified_claims: VerifiedClaim[];
  blocked_claims: BlockedClaim[];
  missing_info: string;
  amendment_chains: AmendmentChain[];
  contradictions: ContradictionItem[];
  calculation: CalculationResult | null;
  guardrails?: {
    status: string;
    block_type: string | null;
    warnings: string[];
    checks: GuardrailCheck[];
  };
  telemetry?: {
    provider: string;
    model: string;
    cache_hit: boolean;
    timing_ms: Record<string, number>;
  };
}

export interface BenchmarkCaseRow {
  id: string;
  category: string;
  question: string;
  passed: boolean;
  abstained: boolean;
  faithfulness_percent: number;
  latency_ms: number;
  guardrail_status: string;
  answer_preview: string;
  notes: string;
}

export interface BenchmarkReport {
  has_report: boolean;
  generated_at?: string;
  provider?: string;
  model?: string;
  summary?: {
    overall_accuracy_percent: number;
    tests_passed: number;
    total_tests: number;
    avg_faithfulness_percent: number;
    hallucination_leak_rate_percent: number;
    abstention_accuracy_percent: number;
    guardrail_block_rate_percent: number;
    avg_latency_ms: number;
    avg_full_pipeline_latency_ms: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
  };
  cases?: BenchmarkCaseRow[];
}