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

export interface QueryResponse {
  question: string;
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
}