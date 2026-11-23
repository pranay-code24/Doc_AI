"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Calculator,
  CheckCircle2,
  Cpu,
  FileUp,
  GitBranch,
  Globe,
  Loader2,
  MessageSquareText,
  Mic,
  MicOff,
  Play,
  RotateCcw,
  Send,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Volume2,
  Zap,
} from "lucide-react";
import PdfHighlightViewer from "@/components/PdfHighlightViewer";
import { getTranslations } from "@/lib/translations";
import {
  BenchmarkReport,
  CitationHighlight,
  DocumentInfo,
  QueryResponse,
} from "@/types/docai";

const API_BASE = "http://localhost:8000";

const LANGUAGE_OPTIONS = [
  { code: "hi", label: "हिन्दी (Hindi)", speech: "hi-IN" },
  { code: "en", label: "English", speech: "en-IN" },
  { code: "mr", label: "मराठी (Marathi)", speech: "mr-IN" },
  { code: "bn", label: "বাংলা (Bengali)", speech: "bn-IN" },
  { code: "ta", label: "தமிழ் (Tamil)", speech: "ta-IN" },
  { code: "te", label: "తెలుగు (Telugu)", speech: "te-IN" },
  { code: "gu", label: "ગુજરાતી (Gujarati)", speech: "gu-IN" },
  { code: "kn", label: "ಕನ್ನಡ (Kannada)", speech: "kn-IN" },
  { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)", speech: "pa-IN" },
  { code: "auto", label: "Auto Detect", speech: "en-IN" },
];

const QUICK_PROMPT_QUERIES = [
  "What is the currently applicable interest rate for a Retail Personal Loan?",
  "What is the maximum repayment tenure and minimum applicant age?",
  "If my overdue EMI is INR 20,000 for 2 months past the grace period, what is the total late payment penalty?",
  "Calculate the monthly EMI for a Retail Personal Loan of INR 5,00,000 for 24 months at the current interest rate.",
  "What is the loan policy for NRI applicants or cryptocurrency collateral?",
  "2+2",
];

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<"qa" | "metrics">("qa");
  const [viewMode, setViewMode] = useState<"simple" | "audit">("simple");
  const [language, setLanguage] = useState<string>("en");
  const [provider, setProvider] = useState<"groq" | "ollama">("groq");
  const [groqAvailable, setGroqAvailable] = useState<boolean>(false);

  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [activeHighlight, setActiveHighlight] =
    useState<CitationHighlight | null>(null);

  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [listening, setListening] = useState(false);
  const [history, setHistory] = useState<QueryResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [runningBench, setRunningBench] = useState(false);

  const t = getTranslations(language);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`);
      if (!res.ok) throw new Error("Backend offline");
      const data = await res.json();
      setDocuments(data.documents || []);
      setGroqAvailable(Boolean(data.groq_configured));
      if (data.default_provider === "ollama" && !data.groq_configured) {
        setProvider("ollama");
      }
      if (data.documents?.length > 0 && !selectedDoc) {
        setSelectedDoc(data.documents[0].doc_name);
        setPageNumber(1);
      }
    } catch {
      setError(
        "Backend server (http://localhost:8000) is not running. Start uvicorn first."
      );
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/metrics`);
      if (res.ok) {
        setBenchmark(await res.json());
      }
    } catch {
      // ignore initial error
    }
  };

  useEffect(() => {
    fetchDocuments();
    fetchMetrics();
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

  const speakText = (text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const langCfg =
      LANGUAGE_OPTIONS.find((l) => l.code === language) || LANGUAGE_OPTIONS[1];
    utter.lang = langCfg.speech;
    utter.rate = 0.95;
    window.speechSynthesis.speak(utter);
  };

  const toggleVoiceInput = () => {
    if (typeof window === "undefined") return;
    const SR =
      (window as unknown as Record<string, unknown>).SpeechRecognition ||
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
    if (!SR) {
      setError("Voice input is supported in Chrome / Edge / Safari browsers.");
      return;
    }
    if (listening) {
      setListening(false);
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const recognition = new (SR as any)();
    const langCfg =
      LANGUAGE_OPTIONS.find((l) => l.code === language) || LANGUAGE_OPTIONS[1];
    recognition.lang = langCfg.speech;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    setListening(true);
    recognition.onresult = (event: {
      results: ArrayLike<ArrayLike<{ transcript: string }>>;
    }) => {
      const transcript = event.results[0][0].transcript;
      setQuestion(transcript);
      setListening(false);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognition.start();
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
        body: JSON.stringify({
          question: q,
          language,
          provider,
          use_cache: true,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Query failed");
      }
      const data: QueryResponse = await res.json();
      setHistory((prev) => [data, ...prev]);

      if (data.contradictions.length > 0) {
        jumpToHighlight(
          data.contradictions[0].source_a,
          `Conflict Side A (${data.contradictions[0].subject})`,
          "red"
        );
      } else if (data.verified_claims.length > 0) {
        jumpToHighlight(data.verified_claims[0], "Verified Proof", "yellow");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleRunBenchmark = async () => {
    setRunningBench(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/metrics/run?provider=${encodeURIComponent(provider)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error("Benchmark failed");
      setBenchmark(await res.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Benchmark failed");
    } finally {
      setRunningBench(false);
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
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Upload failed");
      }
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
    <div className="h-screen flex flex-col bg-slate-50 text-slate-900 overflow-hidden">
      {/* CLEAN HIGH-CONTRAST HEADER */}
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-slate-200 bg-white shadow-xs shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-emerald-600 text-white shadow-xs">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-extrabold tracking-tight text-slate-900">
              {t.appTitle}
            </h1>
            <p className="text-xs text-slate-500">{t.appSubtitle}</p>
          </div>
        </div>

        {/* Navigation + Mode + Language Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={() => setActiveTab("qa")}
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition ${
                activeTab === "qa"
                  ? "bg-white text-blue-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <MessageSquareText className="w-3.5 h-3.5" />
              {t.tabAsk}
            </button>
            <button
              onClick={() => setActiveTab("metrics")}
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition ${
                activeTab === "metrics"
                  ? "bg-white text-blue-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <BarChart3 className="w-3.5 h-3.5" />
              {t.tabMetrics}
            </button>
          </div>

          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={() => setViewMode("simple")}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                viewMode === "simple"
                  ? "bg-emerald-600 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.simpleMode}
            </button>
            <button
              onClick={() => setViewMode("audit")}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                viewMode === "audit"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.auditMode}
            </button>
          </div>

          <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-lg px-2.5 py-1">
            <Globe className="w-3.5 h-3.5 text-blue-700" />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-transparent text-xs font-semibold text-blue-900 focus:outline-none cursor-pointer"
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          {viewMode === "audit" && (
            <button
              onClick={() =>
                setProvider((p) =>
                  p === "groq" ? "ollama" : groqAvailable ? "groq" : "ollama"
                )
              }
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition ${
                provider === "groq" && groqAvailable
                  ? "bg-amber-50 border-amber-300 text-amber-900"
                  : "bg-slate-100 border-slate-300 text-slate-700"
              }`}
              title="Toggle Fast Open-Source Inference (Groq Free) vs Offline Local Ollama"
            >
              {provider === "groq" && groqAvailable ? (
                <>
                  <Zap className="w-3.5 h-3.5 text-amber-600" />
                  Fast Open-Source (~2s)
                </>
              ) : (
                <>
                  <Cpu className="w-3.5 h-3.5" />
                  Offline Local (Ollama)
                </>
              )}
            </button>
          )}

          <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition shadow-xs">
            {uploading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FileUp className="w-3.5 h-3.5" />
            )}
            {t.uploadPdfs}
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
            className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 transition"
            title="Reset 4 Demo Banking PDFs"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* TAB 1: LIVE Q&A + PDF VIEWER */}
      {activeTab === "qa" ? (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
          {/* LEFT PANE */}
          <div className="lg:col-span-7 flex flex-col min-h-0 overflow-hidden bg-slate-50">
            {/* Indexed Documents Bar */}
            <div className="px-5 py-2.5 border-b border-slate-200 bg-white flex items-center gap-2 overflow-x-auto shrink-0">
              <span className="text-xs font-bold text-slate-500 shrink-0">
                {t.yourPdfs} ({documents.length}):
              </span>
              {documents.map((doc) => (
                <div
                  key={doc.doc_name}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border shrink-0 transition ${
                    selectedDoc === doc.doc_name
                      ? "bg-blue-50 border-blue-400 text-blue-800"
                      : "bg-slate-50 border-slate-200 text-slate-700 hover:border-slate-400"
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
                  <button
                    onClick={() => handleDeleteDoc(doc.doc_name)}
                    className="text-slate-400 hover:text-red-600"
                    title="Delete PDF"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>

            {/* Citizen-Friendly Input + Voice Mic + Quick Buttons */}
            <div className="p-4 border-b border-slate-200 bg-white shrink-0 space-y-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAsk();
                }}
                className="flex gap-2"
              >
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  className={`px-3.5 py-2.5 rounded-xl border font-semibold text-sm inline-flex items-center gap-1.5 transition shrink-0 ${
                    listening
                      ? "bg-red-600 border-red-600 text-white animate-pulse"
                      : "bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-700"
                  }`}
                  title="Voice Input"
                >
                  {listening ? (
                    <MicOff className="w-4 h-4" />
                  ) : (
                    <Mic className="w-4 h-4 text-blue-600" />
                  )}
                  <span className="hidden sm:inline">
                    {listening ? t.listening : t.speak}
                  </span>
                </button>

                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={t.inputPlaceholder}
                  className="flex-1 bg-slate-50 border-2 border-slate-200 rounded-xl px-4 py-2.5 text-base text-slate-900 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white"
                  disabled={loading}
                />

                <button
                  type="submit"
                  disabled={loading || !question.trim()}
                  className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-sm font-bold inline-flex items-center gap-2 transition shadow-xs shrink-0"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {t.askBtn}
                </button>
              </form>

              {/* Easy 1-Click Localized Starter Questions */}
              <div className="flex flex-wrap gap-2">
                {QUICK_PROMPT_QUERIES.map((qText, i) => (
                  <button
                    key={i}
                    onClick={() => handleAsk(qText)}
                    disabled={loading}
                    className="text-xs font-semibold px-3 py-1.5 rounded-full bg-slate-100 hover:bg-blue-50 hover:text-blue-800 hover:border-blue-300 border border-slate-200 text-slate-700 transition inline-flex items-center gap-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                    {t.quickLabels[i]}
                  </button>
                ))}
              </div>

              {error && (
                <div className="text-xs font-medium text-red-800 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {error}
                </div>
              )}
            </div>

            {/* Results Feed */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {loading && (
                <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5 flex items-center gap-3 text-sm font-semibold text-blue-900">
                  <Loader2 className="w-5 h-5 text-blue-600 animate-spin shrink-0" />
                  {t.loadingMsg}
                </div>
              )}

              {history.length === 0 && !loading && (
                <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white p-10 text-center space-y-3">
                  <ShieldCheck className="w-12 h-12 mx-auto text-emerald-600" />
                  <h2 className="text-lg font-bold text-slate-900">
                    {t.welcomeTitle}
                  </h2>
                  <p className="text-sm text-slate-600 max-w-lg mx-auto">
                    {t.welcomeDesc}
                  </p>
                  <div className="flex flex-wrap justify-center gap-3 pt-2 text-xs font-semibold">
                    <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                      {t.legendGreen}
                    </span>
                    <span className="px-3 py-1 rounded-full bg-red-50 text-red-800 border border-red-200">
                      {t.legendRed}
                    </span>
                    <span className="px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                      {t.legendYellow}
                    </span>
                  </div>
                </div>
              )}

              {history.map((item, idx) => {
                const isConflict = item.contradictions.length > 0;
                const statusTheme = isConflict
                  ? {
                      border: "border-red-300",
                      headerBg: "bg-red-50",
                      badgeBg: "bg-red-600 text-white",
                      badgeText: t.badgeConflict,
                    }
                  : item.abstained
                  ? {
                      border: "border-amber-300",
                      headerBg: "bg-amber-50",
                      badgeBg: "bg-amber-500 text-white",
                      badgeText: t.badgeAbstained,
                    }
                  : {
                      border: "border-emerald-300",
                      headerBg: "bg-emerald-50",
                      badgeBg: "bg-emerald-600 text-white",
                      badgeText: `${t.badgeVerified} (${item.faithfulness.score_percent}%)`,
                    };

                return (
                  <div
                    key={idx}
                    className={`rounded-2xl border-2 ${statusTheme.border} bg-white overflow-hidden shadow-xs`}
                  >
                    <div
                      className={`px-4 py-3 ${statusTheme.headerBg} border-b border-slate-200 flex flex-wrap items-center justify-between gap-2`}
                    >
                      <p className="text-sm font-bold text-slate-900">
                        Q: {item.question}
                      </p>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => speakText(item.answer)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-white hover:bg-blue-50 text-blue-700 border border-blue-200 transition"
                          title="Listen"
                        >
                          <Volume2 className="w-3.5 h-3.5" />
                          {t.listenBtn}
                        </button>

                        <span
                          className={`inline-flex items-center gap-1 text-xs font-bold px-3 py-1 rounded-full ${statusTheme.badgeBg}`}
                        >
                          {item.abstained ? (
                            <ShieldAlert className="w-3.5 h-3.5" />
                          ) : (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          )}
                          {statusTheme.badgeText}
                        </span>
                      </div>
                    </div>

                    <div className="p-4 space-y-4">
                      {item.guardrails?.warnings?.map((w, wIdx) => (
                        <div
                          key={wIdx}
                          className="text-xs font-semibold text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-center gap-2"
                        >
                          <Shield className="w-4 h-4 text-amber-600 shrink-0" />
                          {w}
                        </div>
                      ))}

                      <div className="text-base leading-relaxed font-medium text-slate-900 bg-slate-50 rounded-xl p-4 border border-slate-200">
                        {item.answer}
                      </div>

                      {item.contradictions.length > 0 && (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-red-700">
                            <AlertTriangle className="w-4 h-4" />
                            {t.conflictHeader} ({item.contradictions.length})
                          </div>
                          {item.contradictions.map((c, cIdx) => (
                            <div
                              key={cIdx}
                              className="rounded-xl border border-red-200 bg-red-50/70 p-3.5 space-y-3"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-sm font-bold text-red-900">
                                  {c.subject}
                                </span>
                                <span className="text-[11px] font-bold uppercase px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">
                                  {c.conflict_type}
                                </span>
                              </div>
                              <p className="text-xs text-red-900/90">
                                {c.explanation}
                              </p>

                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {[
                                  { title: "Document A", src: c.source_a },
                                  { title: "Document B", src: c.source_b },
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
                                    className="text-left rounded-lg border border-red-200 bg-white hover:border-red-500 p-3 transition space-y-1.5 shadow-2xs"
                                  >
                                    <div className="flex items-center justify-between text-xs font-bold text-red-700">
                                      <span>{title}</span>
                                      <span>
                                        {src.doc_name} (p.{src.page_number})
                                      </span>
                                    </div>
                                    <p className="text-xs italic text-slate-700">
                                      &ldquo;{src.verbatim_quote}&rdquo;
                                    </p>
                                    <span className="text-xs font-semibold text-blue-600 underline">
                                      {t.highlightRed}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {item.calculation && (
                        <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-xs font-extrabold uppercase text-indigo-800">
                              <Calculator className="w-4 h-4" />
                              {t.calcHeader} — {item.calculation.operation}
                            </div>
                            <span className="text-base font-extrabold text-emerald-800 bg-emerald-100 px-3 py-1 rounded-lg border border-emerald-300">
                              {item.calculation.result}
                            </span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                            {Object.entries(item.calculation.inputs).map(
                              ([k, v]) => (
                                <div
                                  key={k}
                                  className="bg-white rounded-lg p-2.5 border border-indigo-100"
                                >
                                  <div className="text-[11px] font-semibold text-slate-500">
                                    {k}
                                  </div>
                                  <div className="text-xs font-bold text-slate-900">
                                    {v}
                                  </div>
                                </div>
                              )
                            )}
                          </div>

                          <div className="space-y-1 bg-white rounded-lg p-3 border border-indigo-100">
                            {item.calculation.steps.map((st, sIdx) => (
                              <div
                                key={sIdx}
                                className="text-xs font-mono text-slate-800"
                              >
                                {st}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {item.amendment_chains.length > 0 && (
                        <div className="space-y-2.5">
                          <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-blue-700">
                            <GitBranch className="w-4 h-4" />
                            {t.amendmentHeader}
                          </div>
                          {item.amendment_chains.map((chain, chIdx) => (
                            <div
                              key={chIdx}
                              className="rounded-xl border border-blue-200 bg-blue-50/40 p-3.5 space-y-2"
                            >
                              <div className="text-xs font-bold text-blue-900">
                                {chain.clause_ref} ({chain.subject}) —{" "}
                                <span className="text-emerald-700">
                                  {chain.active_doc_id}
                                </span>
                              </div>
                              <div className="space-y-2 border-l-2 border-blue-300 pl-3 ml-1">
                                {chain.steps.map((step, sIdx) => {
                                  const isActive = step.status === "ACTIVE";
                                  return (
                                    <div
                                      key={sIdx}
                                      className={`rounded-lg p-2.5 text-xs border ${
                                        isActive
                                          ? "bg-emerald-50 border-emerald-300"
                                          : "bg-white border-slate-200 opacity-75"
                                      }`}
                                    >
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <button
                                          onClick={() => {
                                            setSelectedDoc(step.doc_name);
                                            setPageNumber(step.page_number);
                                          }}
                                          className="font-bold text-slate-900 hover:text-blue-700 hover:underline"
                                        >
                                          [{step.effective_date}] {step.doc_id}{" "}
                                          ({step.doc_name})
                                        </button>
                                        <span
                                          className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                                            isActive
                                              ? "bg-emerald-600 text-white"
                                              : "bg-slate-200 text-slate-600"
                                          }`}
                                        >
                                          {isActive ? t.activeToday : t.oldRule}
                                        </span>
                                      </div>
                                      <p
                                        className={`mt-1 text-slate-700 ${
                                          !isActive ? "line-through" : "font-medium"
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

                      {item.verified_claims.length > 0 && (
                        <div className="space-y-2">
                          <div className="text-xs font-extrabold uppercase tracking-wider text-emerald-700">
                            {t.proofHeader}
                          </div>
                          {item.verified_claims.map((cl, clIdx) => (
                            <button
                              key={clIdx}
                              onClick={() =>
                                jumpToHighlight(
                                  cl,
                                  `Proof #${clIdx + 1} (${cl.doc_name}, Page ${
                                    cl.page_number
                                  })`,
                                  "yellow"
                                )
                              }
                              className="w-full text-left rounded-xl border border-emerald-200 bg-emerald-50/40 hover:border-amber-500 hover:bg-amber-50/40 p-3 transition space-y-1"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                                <span className="font-bold text-slate-900">
                                  📄 {cl.doc_name} • Page {cl.page_number}
                                </span>
                                {viewMode === "audit" ? (
                                  <span className="text-[11px] font-semibold text-emerald-700 tabular-nums">
                                    Quote: {cl.quote_match_score}% • NLI
                                    Entail:{" "}
                                    {(cl.nli_scores.entailment * 100).toFixed(
                                      1
                                    )}
                                    %
                                  </span>
                                ) : (
                                  <span className="text-xs font-semibold text-blue-600 underline">
                                    {t.viewOnPdf}
                                  </span>
                                )}
                              </div>
                              <p className="text-xs italic text-slate-700">
                                &ldquo;{cl.verbatim_quote}&rdquo;
                              </p>
                            </button>
                          ))}
                        </div>
                      )}

                      {viewMode === "audit" && (
                        <div className="rounded-xl border border-slate-300 bg-slate-100/80 p-3.5 space-y-3">
                          {item.guardrails && (
                            <div className="space-y-1.5">
                              <div className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wider text-slate-700">
                                <Shield className="w-3.5 h-3.5 text-blue-600" />
                                Active Guardrails Audit ({item.guardrails.status})
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                {item.guardrails.checks.map((chk, gIdx) => (
                                  <div
                                    key={gIdx}
                                    className="bg-white rounded-lg px-2.5 py-1.5 border border-slate-200 flex items-center justify-between gap-2 text-[11px]"
                                  >
                                    <span className="font-semibold text-slate-800 truncate">
                                      {chk.name}
                                    </span>
                                    <span
                                      className={`font-bold px-1.5 py-0.5 rounded shrink-0 ${
                                        chk.status === "BLOCKED" ||
                                        chk.status === "CONFLICT_FLAGGED"
                                          ? "bg-red-100 text-red-700"
                                          : chk.status === "REDACTED" ||
                                            chk.status === "ABSTAINED"
                                          ? "bg-amber-100 text-amber-800"
                                          : "bg-emerald-100 text-emerald-700"
                                      }`}
                                    >
                                      {chk.status}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {item.telemetry && (
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-700 pt-1 border-t border-slate-200">
                              <span className="font-bold text-slate-900">
                                ⚡ Total:{" "}
                                {(
                                  (item.telemetry.timing_ms.total || 0) / 1000
                                ).toFixed(2)}
                                s
                              </span>
                              <span>
                                ({item.telemetry.provider.toUpperCase()} /{" "}
                                {item.telemetry.model}
                                {item.telemetry.cache_hit ? " • CACHE HIT" : ""})
                              </span>
                              {Object.entries(item.telemetry.timing_ms)
                                .filter(([k]) => k !== "total")
                                .map(([k, ms]) => (
                                  <span
                                    key={k}
                                    className="px-2 py-0.5 bg-white rounded border border-slate-200 font-mono"
                                  >
                                    {k}: {ms}ms
                                  </span>
                                ))}
                            </div>
                          )}

                          {item.blocked_claims.length > 0 && (
                            <div className="pt-1 border-t border-slate-200 space-y-1">
                              <div className="text-[11px] font-bold uppercase text-red-700">
                                Blocked Claims ({item.blocked_claims.length})
                              </div>
                              {item.blocked_claims.map((b, bIdx) => (
                                <div
                                  key={bIdx}
                                  className="text-xs text-slate-700"
                                >
                                  •{" "}
                                  <span className="line-through">
                                    {b.sentence}
                                  </span>{" "}
                                  —{" "}
                                  <span className="font-semibold text-red-700">
                                    {b.block_reason}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT PANE: PDF VIEWER */}
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
      ) : (
        /* TAB 2: LIVE EVALUATION METRICS & PROOF DASHBOARD */
        <div className="flex-1 overflow-y-auto p-6 max-w-6xl mx-auto w-full space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
            <div>
              <h2 className="text-xl font-extrabold text-slate-900">
                {t.metricsTitle}
              </h2>
              <p className="text-sm text-slate-600">{t.metricsSub}</p>
              {benchmark?.has_report && (
                <p className="text-xs text-slate-500 mt-1">
                  Last run: {benchmark.generated_at} • Provider:{" "}
                  <strong>
                    {benchmark.provider?.toUpperCase()} ({benchmark.model})
                  </strong>
                </p>
              )}
            </div>

            <button
              onClick={handleRunBenchmark}
              disabled={runningBench}
              className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-bold inline-flex items-center gap-2 shadow-xs transition"
            >
              {runningBench ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {runningBench ? t.runningBenchBtn : t.runBenchBtn}
            </button>
          </div>

          {benchmark?.has_report && benchmark.summary ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {[
                  {
                    label: "Benchmark Accuracy",
                    val: `${benchmark.summary.overall_accuracy_percent}%`,
                    sub: `${benchmark.summary.tests_passed}/${benchmark.summary.total_tests} passed`,
                    color: "text-emerald-700 bg-emerald-50 border-emerald-200",
                  },
                  {
                    label: "Avg Faithfulness",
                    val: `${benchmark.summary.avg_faithfulness_percent}%`,
                    sub: "Verbatim + NLI",
                    color: "text-blue-700 bg-blue-50 border-blue-200",
                  },
                  {
                    label: "Hallucination Leak",
                    val: `${benchmark.summary.hallucination_leak_rate_percent}%`,
                    sub: "Displayed guesses",
                    color: "text-emerald-700 bg-emerald-50 border-emerald-200",
                  },
                  {
                    label: "Abstention Accuracy",
                    val: `${benchmark.summary.abstention_accuracy_percent}%`,
                    sub: "Missing & Conflicts",
                    color: "text-indigo-700 bg-indigo-50 border-indigo-200",
                  },
                  {
                    label: "Guardrail Block Rate",
                    val: `${benchmark.summary.guardrail_block_rate_percent}%`,
                    sub: "2+2 & Injection",
                    color: "text-purple-700 bg-purple-50 border-purple-200",
                  },
                  {
                    label: "Median Latency (p50)",
                    val: `${(benchmark.summary.p50_latency_ms / 1000).toFixed(
                      2
                    )}s`,
                    sub: `Avg: ${(
                      benchmark.summary.avg_full_pipeline_latency_ms / 1000
                    ).toFixed(2)}s`,
                    color: "text-amber-800 bg-amber-50 border-amber-200",
                  },
                ].map((kpi) => (
                  <div
                    key={kpi.label}
                    className={`rounded-2xl border p-4 ${kpi.color}`}
                  >
                    <div className="text-xs font-bold opacity-80">
                      {kpi.label}
                    </div>
                    <div className="text-2xl font-extrabold mt-1 tabular-nums">
                      {kpi.val}
                    </div>
                    <div className="text-[11px] opacity-75 mt-0.5">
                      {kpi.sub}
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
                <div className="px-5 py-3 border-b border-slate-200 font-bold text-sm text-slate-800">
                  Case-by-Case Verification &amp; Latency Matrix
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                      <tr>
                        <th className="px-4 py-3">ID</th>
                        <th className="px-4 py-3">Category</th>
                        <th className="px-4 py-3">Test Query</th>
                        <th className="px-4 py-3">Result</th>
                        <th className="px-4 py-3">Faithfulness</th>
                        <th className="px-4 py-3">Latency</th>
                        <th className="px-4 py-3">Guardrail</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {benchmark.cases?.map((row) => (
                        <tr key={row.id} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-bold">{row.id}</td>
                          <td className="px-4 py-3 font-semibold text-slate-800">
                            {row.category}
                          </td>
                          <td className="px-4 py-3 text-slate-600 max-w-xs truncate">
                            {row.question}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`px-2 py-0.5 rounded-full font-bold ${
                                row.passed
                                  ? "bg-emerald-100 text-emerald-800"
                                  : "bg-red-100 text-red-800"
                              }`}
                            >
                              {row.passed ? "PASS" : "FAIL"}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono">
                            {row.abstained
                              ? "Abstained"
                              : `${row.faithfulness_percent}%`}
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold">
                            {row.latency_ms < 100
                              ? `${row.latency_ms} ms`
                              : `${(row.latency_ms / 1000).toFixed(2)} s`}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {row.guardrail_status}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-slate-500">
              Click <strong>&ldquo;{t.runBenchBtn}&rdquo;</strong> above to
              execute all 9 verification tests and generate real-time proof.
            </div>
          )}
        </div>
      )}
    </div>
  );
}