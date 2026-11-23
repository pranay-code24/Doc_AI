"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Calculator,
  CheckCircle2,
  FileUp,
  GitBranch,
  Loader2,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import PdfHighlightViewer from "@/components/PdfHighlightViewer";
import {
  CitationHighlight,
  DocumentInfo,
  QueryResponse,
} from "@/types/docai";

const API_BASE = "http://localhost:8000";

const DEMO_QUESTIONS = [
  {
    tag: "Amendment Chain",
    q: "What is the currently applicable interest rate for a Retail Personal Loan?",
  },
  {
    tag: "Contradiction",
    q: "What is the maximum repayment tenure and minimum applicant age?",
  },
  {
    tag: "Penalty Calc",
    q: "If my overdue EMI is INR 20,000 for 2 months past the grace period, what is the total late payment penalty?",
  },
  {
    tag: "EMI Calc",
    q: "Calculate the monthly EMI for a Retail Personal Loan of INR 5,00,000 for 24 months at the current interest rate.",
  },
  {
    tag: "Zero-Guessing",
    q: "What is the loan policy for NRI applicants or cryptocurrency collateral?",
  },
  {
    tag: "Hindi Q&A",
    q: "Personal loan ke liye minimum monthly income kitni honi chahiye?",
  },
];

export default function HomePage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [activeHighlight, setActiveHighlight] =
    useState<CitationHighlight | null>(null);

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [history, setHistory] = useState<QueryResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`);
      if (!res.ok) throw new Error("Backend not reachable");
      const data = await res.json();
      setDocuments(data.documents || []);
      if (data.documents?.length > 0 && !selectedDoc) {
        setSelectedDoc(data.documents[0].doc_name);
        setPageNumber(1);
      }
    } catch {
      setError(
        "FastAPI backend (http://localhost:8000) se connect nahi ho paya. Make sure uvicorn chal raha hai."
      );
    }
  };

  useEffect(() => {
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const jumpToHighlight = (
    highlight: CitationHighlight,
    label?: string,
    color: "yellow" | "red" = "yellow"
  ) => {
    setSelectedDoc(highlight.doc_name);
    setPageNumber(highlight.page_number);
    setActiveHighlight({ ...highlight, label, color });
  };

  const handleAsk = async (customQuestion?: string) => {
    const q = (customQuestion ?? question).trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    if (!customQuestion) setQuestion("");

    try {
      const res = await fetch(`${API_BASE}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Query failed");
      }
      const data: QueryResponse = await res.json();
      setHistory((prev) => [data, ...prev]);

      // Automatically jump PDF viewer to first verified citation or contradiction
      if (data.contradictions.length > 0) {
        jumpToHighlight(
          data.contradictions[0].source_a,
          `Conflict Side A (${data.contradictions[0].subject})`,
          "red"
        );
      } else if (data.verified_claims.length > 0) {
        jumpToHighlight(
          data.verified_claims[0],
          "Verified Evidence",
          "yellow"
        );
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setError(null);
    const formData = new FormData();
    Array.from(files).forEach((f) => formData.append("files", f));

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      await fetchDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDeleteDoc = async (docName: string) => {
    setUploading(true);
    try {
      await fetch(
        `${API_BASE}/api/documents/${encodeURIComponent(docName)}`,
        { method: "DELETE" }
      );
      if (selectedDoc === docName) {
        setSelectedDoc(null);
        setActiveHighlight(null);
      }
      await fetchDocuments();
    } finally {
      setUploading(false);
    }
  };

  const handleResetSamples = async () => {
    setUploading(true);
    setError(null);
    try {
      await fetch(`${API_BASE}/api/reset-samples`, { method: "POST" });
      await fetchDocuments();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-slate-100 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-slate-950 shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/15 border border-emerald-500/30">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white">
              Zero-Guessing &amp; Contradiction-Checking Document AI
            </h1>
            <p className="text-xs text-slate-400">
              100% Local Open-Source Pipeline • Qwen2.5 + Multilingual E5 +
              mDeBERTa-v3 NLI + Qdrant
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-sky-600 hover:bg-sky-500 text-white transition">
            {uploading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FileUp className="w-3.5 h-3.5" />
            )}
            Upload PDFs
            <input
              type="file"
              accept="application/pdf"
              multiple
              onChange={handleFileUpload}
              className="hidden"
              disabled={uploading}
            />
          </label>
          <button
            onClick={handleResetSamples}
            disabled={uploading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition"
            title="Restore 4 banking sample PDFs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset Demo PDFs
          </button>
        </div>
      </header>

      {/* Main Split-Screen Body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
        {/* LEFT PANE: Documents + Q&A + Verification Cards */}
        <div className="lg:col-span-7 flex flex-col min-h-0 overflow-hidden">
          {/* Indexed Documents Strip */}
          <div className="px-5 py-2.5 border-b border-slate-800/80 bg-slate-900/50 flex items-center gap-2 overflow-x-auto shrink-0">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold shrink-0">
              Indexed ({documents.length}):
            </span>
            {documents.map((doc) => (
              <div
                key={doc.doc_name}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border shrink-0 transition ${
                  selectedDoc === doc.doc_name
                    ? "bg-sky-500/20 border-sky-500/50 text-sky-200"
                    : "bg-slate-800/80 border-slate-700 text-slate-300 hover:border-slate-500"
                }`}
              >
                <button
                  onClick={() => {
                    setSelectedDoc(doc.doc_name);
                    setPageNumber(1);
                  }}
                  className="truncate max-w-[175px]"
                >
                  {doc.doc_name}
                </button>
                <span className="text-[10px] text-slate-400">
                  ({doc.doc_id})
                </span>
                <button
                  onClick={() => handleDeleteDoc(doc.doc_name)}
                  className="text-slate-500 hover:text-red-400 ml-0.5"
                  title="Remove PDF"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>

          {/* Query Box + 1-Click Demo Chips */}
          <div className="p-4 border-b border-slate-800 bg-slate-900/30 shrink-0 space-y-2.5">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAsk();
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask across all PDFs (English or Hindi)... e.g., What is the current interest rate?"
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2 transition"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Verify &amp; Answer
              </button>
            </form>

            {/* Quick Demo Prompts */}
            <div className="flex flex-wrap gap-1.5">
              {DEMO_QUESTIONS.map((item) => (
                <button
                  key={item.tag}
                  onClick={() => handleAsk(item.q)}
                  disabled={loading}
                  className="text-[11px] px-2.5 py-1 rounded-md bg-slate-800/90 hover:bg-slate-700 border border-slate-700/80 text-slate-300 transition inline-flex items-center gap-1"
                >
                  <Sparkles className="w-3 h-3 text-amber-400" />
                  {item.tag}
                </button>
              ))}
            </div>

            {error && (
              <div className="text-xs text-red-300 bg-red-950/60 border border-red-800 rounded-md px-3 py-2">
                {error}
              </div>
            )}
          </div>

          {/* Results Feed */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {loading && (
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 flex items-center gap-3 text-sm text-slate-300">
                <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" />
                Running Hybrid Retrieval → Amendment Graph → Contradiction
                Audit → Quote &amp; NLI Verification...
              </div>
            )}

            {history.length === 0 && !loading && (
              <div className="text-center py-16 text-slate-400 space-y-2">
                <ShieldCheck className="w-10 h-10 mx-auto text-slate-600" />
                <p className="text-sm font-medium text-slate-300">
                  Ask a question or click any Demo chip above to test the
                  pipeline.
                </p>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  Every answer sentence is checked against verbatim PDF quotes
                  and mDeBERTa-v3 NLI entailment before being shown.
                </p>
              </div>
            )}

            {history.map((item, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-slate-800 bg-slate-900/70 overflow-hidden shadow-lg"
              >
                {/* Question Header + Faithfulness Score Badge */}
                <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-white">
                    Q: {item.question}
                  </p>

                  <div className="flex items-center gap-2">
                    {item.abstained ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">
                        <ShieldAlert className="w-3.5 h-3.5" />
                        Safe Abstention (No Guessing)
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Faithfulness: {item.faithfulness.score_percent}% (
                        {item.faithfulness.verified_sentences}/
                        {item.faithfulness.total_draft_sentences})
                      </span>
                    )}
                  </div>
                </div>

                <div className="p-4 space-y-4">
                  {/* Verified Answer Box */}
                  <div
                    className={`rounded-lg p-3.5 text-sm leading-relaxed border ${
                      item.abstained
                        ? "bg-amber-950/30 border-amber-800/60 text-amber-100"
                        : "bg-slate-950/60 border-slate-800 text-slate-100"
                    }`}
                  >
                    {item.answer}
                  </div>

                  {/* SIDE-BY-SIDE CONTRADICTION ALERTS */}
                  {item.contradictions.length > 0 && (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-400">
                        <AlertTriangle className="w-4 h-4" />
                        Contradiction Alert ({item.contradictions.length}{" "}
                        detected)
                      </div>
                      {item.contradictions.map((c, cIdx) => (
                        <div
                          key={cIdx}
                          className="rounded-lg border border-red-800/70 bg-red-950/25 p-3.5 space-y-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-semibold text-red-200">
                              Conflict: {c.subject}
                            </span>
                            <span className="text-[11px] uppercase px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/40">
                              {c.conflict_type}
                            </span>
                          </div>
                          <p className="text-xs text-red-200/80">
                            {c.explanation}
                          </p>

                          {/* Side-by-Side Quotes */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {[
                              { title: "Side A", src: c.source_a },
                              { title: "Side B", src: c.source_b },
                            ].map(({ title, src }) => (
                              <button
                                key={title}
                                onClick={() =>
                                  jumpToHighlight(
                                    src,
                                    `${title}: ${c.subject}`,
                                    "red"
                                  )
                                }
                                className="text-left rounded-md border border-red-800/60 bg-slate-950/80 hover:border-red-400 p-3 transition space-y-1.5"
                              >
                                <div className="flex items-center justify-between text-[11px] font-semibold text-red-300">
                                  <span>{title}</span>
                                  <span>
                                    {src.doc_name} • p.{src.page_number}
                                  </span>
                                </div>
                                <p className="text-xs italic text-slate-200">
                                  &ldquo;{src.verbatim_quote}&rdquo;
                                </p>
                                <span className="text-[10px] text-sky-400 underline">
                                  Click to highlight on PDF →
                                </span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* CALCULATION WORKING CARD (BONUS) */}
                  {item.calculation && (
                    <div className="rounded-lg border border-indigo-700/60 bg-indigo-950/30 p-3.5 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-300">
                          <Calculator className="w-4 h-4" />
                          Deterministic Calculation Working —{" "}
                          {item.calculation.operation}
                        </div>
                        <span className="text-sm font-bold text-emerald-300 bg-emerald-950/70 px-2.5 py-0.5 rounded border border-emerald-700/60">
                          {item.calculation.result}
                        </span>
                      </div>

                      <div className="text-xs font-mono bg-slate-950/80 px-3 py-2 rounded border border-slate-800 text-indigo-200">
                        {item.calculation.formula}
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        {Object.entries(item.calculation.inputs).map(
                          ([k, v]) => (
                            <div
                              key={k}
                              className="bg-slate-950/60 rounded p-2 border border-slate-800"
                            >
                              <div className="text-[10px] text-slate-400">
                                {k}
                              </div>
                              <div className="text-xs font-medium text-slate-100">
                                {v}
                              </div>
                            </div>
                          )
                        )}
                      </div>

                      <div className="space-y-1 text-xs text-slate-200 pt-1">
                        {item.calculation.steps.map((st, sIdx) => (
                          <div key={sIdx} className="font-mono text-[11px]">
                            {st}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* AMENDMENT CHAIN TIMELINE (A -> B -> C) */}
                  {item.amendment_chains.length > 0 && (
                    <div className="space-y-2.5">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-sky-400">
                        <GitBranch className="w-4 h-4" />
                        Amendment Chain Resolution
                      </div>
                      {item.amendment_chains.map((chain, chIdx) => (
                        <div
                          key={chIdx}
                          className="rounded-lg border border-sky-900/70 bg-slate-950/60 p-3.5 space-y-2.5"
                        >
                          <div className="text-xs font-semibold text-sky-200">
                            {chain.clause_ref} ({chain.subject}) — Active
                            Version:{" "}
                            <span className="text-emerald-300">
                              {chain.active_doc_id}
                            </span>
                          </div>
                          <div className="space-y-2 border-l-2 border-slate-700 pl-3 ml-1">
                            {chain.steps.map((step, sIdx) => {
                              const isActive = step.status === "ACTIVE";
                              return (
                                <div
                                  key={sIdx}
                                  className={`rounded-md p-2.5 text-xs border ${
                                    isActive
                                      ? "bg-emerald-950/35 border-emerald-700/60"
                                      : "bg-slate-900/70 border-slate-800 opacity-75"
                                  }`}
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <button
                                      onClick={() => {
                                        setSelectedDoc(step.doc_name);
                                        setPageNumber(step.page_number);
                                      }}
                                      className="font-semibold text-white hover:text-sky-300 underline-offset-2 hover:underline"
                                    >
                                      [{step.effective_date}] {step.doc_id} (
                                      {step.doc_name})
                                    </button>
                                    <span
                                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                        isActive
                                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                          : "bg-slate-700 text-slate-300"
                                      }`}
                                    >
                                      {isActive
                                        ? "ACTIVE TODAY"
                                        : `SUPERSEDED BY ${step.superseded_by}`}
                                    </span>
                                  </div>
                                  <p
                                    className={`mt-1 text-slate-300 ${
                                      !isActive ? "line-through opacity-75" : ""
                                    }`}
                                  >
                                    {step.summary}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* VERIFIED EXACT CITATIONS */}
                  {item.verified_claims.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                        Verified Exact Citations (Click to Highlight on PDF)
                      </div>
                      <div className="space-y-2">
                        {item.verified_claims.map((cl, clIdx) => (
                          <button
                            key={clIdx}
                            onClick={() =>
                              jumpToHighlight(
                                cl,
                                `Citation #${clIdx + 1} (${cl.doc_name}, p.${
                                  cl.page_number
                                })`,
                                "yellow"
                              )
                            }
                            className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/70 hover:border-amber-500/70 p-3 transition space-y-1.5"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                              <span className="font-semibold text-amber-300">
                                [{clIdx + 1}] {cl.doc_name} • Page{" "}
                                {cl.page_number}
                              </span>
                              <span className="text-[11px] text-emerald-400 tabular-nums">
                                Quote Match: {cl.quote_match_score}% • NLI
                                Entail:{" "}
                                {(cl.nli_scores.entailment * 100).toFixed(1)}%
                              </span>
                            </div>
                            <p className="text-xs italic text-slate-300">
                              &ldquo;{cl.verbatim_quote}&rdquo;
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* BLOCKED CLAIMS (IF ANY) */}
                  {item.blocked_claims.length > 0 && (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-1.5">
                      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Blocked Unverified Claims ({item.blocked_claims.length})
                      </div>
                      {item.blocked_claims.map((b, bIdx) => (
                        <div key={bIdx} className="text-xs text-slate-400">
                          • <span className="line-through">{b.sentence}</span> —{" "}
                          <span className="text-amber-400">
                            {b.block_reason}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT PANE: Rendered PDF Viewer with Yellow Passage Highlight */}
        <div className="lg:col-span-5 h-full min-h-[450px] overflow-hidden">
          <PdfHighlightViewer
            documents={documents}
            selectedDoc={selectedDoc}
            pageNumber={pageNumber}
            activeHighlight={activeHighlight}
            onSelectDoc={(doc, page = 1) => {
              setSelectedDoc(doc);
              setPageNumber(page);
            }}
            onPageChange={setPageNumber}
          />
        </div>
      </div>
    </div>
  );
}