"use client";

import React from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Highlighter,
} from "lucide-react";
import { CitationHighlight, DocumentInfo } from "@/types/docai";

const API_BASE = "http://localhost:8000";

interface PdfHighlightViewerProps {
  documents: DocumentInfo[];
  selectedDoc: string | null;
  pageNumber: number;
  activeHighlight: CitationHighlight | null;
  onSelectDoc: (docName: string, page?: number) => void;
  onPageChange: (page: number) => void;
}

export default function PdfHighlightViewer({
  documents,
  selectedDoc,
  pageNumber,
  activeHighlight,
  onSelectDoc,
  onPageChange,
}: PdfHighlightViewerProps) {
  const docMeta = documents.find((d) => d.doc_name === selectedDoc);
  const totalPages = docMeta?.pages ?? 1;

  const showHighlights =
    activeHighlight &&
    activeHighlight.doc_name === selectedDoc &&
    activeHighlight.page_number === pageNumber &&
    activeHighlight.bboxes.length > 0 &&
    activeHighlight.page_width > 0 &&
    activeHighlight.page_height > 0;

  return (
    <div className="flex h-full flex-col bg-slate-100 text-slate-800 border-l border-slate-200">
      {/* Top Bar */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-4 h-4 text-blue-600 shrink-0" />
          <select
            value={selectedDoc ?? ""}
            onChange={(e) => onSelectDoc(e.target.value, 1)}
            className="bg-slate-50 text-slate-900 text-xs font-semibold rounded-lg px-2.5 py-1.5 border border-slate-300 focus:outline-none focus:border-blue-500 max-w-[240px] truncate"
          >
            {documents.map((d) => (
              <option key={d.doc_name} value={d.doc_name}>
                {d.doc_name} ({d.pages}p)
              </option>
            ))}
          </select>
        </div>

        {selectedDoc && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-slate-100 rounded-lg px-1.5 py-1 border border-slate-300">
              <button
                onClick={() => onPageChange(Math.max(1, pageNumber - 1))}
                disabled={pageNumber <= 1}
                className="p-0.5 hover:bg-slate-200 rounded disabled:opacity-30"
                title="Previous page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs font-semibold px-1.5 tabular-nums">
                Page {pageNumber} / {totalPages}
              </span>
              <button
                onClick={() => onPageChange(Math.min(totalPages, pageNumber + 1))}
                disabled={pageNumber >= totalPages}
                className="p-0.5 hover:bg-slate-200 rounded disabled:opacity-30"
                title="Next page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <a
              href={`${API_BASE}/api/pdf-raw/${encodeURIComponent(selectedDoc)}`}
              target="_blank"
              rel="noreferrer"
              className="p-1.5 bg-white hover:bg-slate-100 rounded-lg border border-slate-300 text-slate-700"
              title="Open original PDF"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        )}
      </div>

      {/* Active Highlight Banner */}
      {showHighlights && activeHighlight && (
        <div
          className={`px-4 py-2.5 text-xs flex items-start gap-2 border-b ${
            activeHighlight.color === "red"
              ? "bg-red-50 border-red-200 text-red-900"
              : "bg-amber-50 border-amber-200 text-amber-900"
          }`}
        >
          <Highlighter className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="font-bold">
              {activeHighlight.label || "Original Proof Highlighted"}:
            </span>{" "}
            <span className="italic line-clamp-2">
              &ldquo;{activeHighlight.verbatim_quote}&rdquo;
            </span>
          </div>
        </div>
      )}

      {/* Rendered PDF Page Canvas + Exact Highlight Overlays */}
      <div className="flex-1 overflow-auto p-4 flex justify-center items-start bg-slate-100">
        {selectedDoc ? (
          <div className="relative inline-block shadow-lg rounded-lg overflow-hidden border border-slate-300 bg-white max-w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE}/api/pdf-page/${encodeURIComponent(
                selectedDoc
              )}/${pageNumber}`}
              alt={`${selectedDoc} page ${pageNumber}`}
              className="block w-full h-auto max-w-[600px] select-none"
            />

            {showHighlights &&
              activeHighlight.bboxes.map((box, idx) => {
                const [x0, y0, x1, y1] = box;
                const leftPct = (x0 / activeHighlight.page_width) * 100;
                const topPct = (y0 / activeHighlight.page_height) * 100;
                const widthPct = ((x1 - x0) / activeHighlight.page_width) * 100;
                const heightPct =
                  ((y1 - y0) / activeHighlight.page_height) * 100;

                const isRed = activeHighlight.color === "red";
                return (
                  <div
                    key={idx}
                    style={{
                      left: `${Math.max(0, leftPct - 0.5)}%`,
                      top: `${Math.max(0, topPct - 0.4)}%`,
                      width: `${Math.min(100, widthPct + 1.0)}%`,
                      height: `${Math.min(100, heightPct + 0.8)}%`,
                    }}
                    className={`absolute pointer-events-none rounded-sm transition-all duration-300 ${
                      isRed
                        ? "bg-red-400/35 border-2 border-red-600 shadow-sm"
                        : "bg-yellow-300/45 border-2 border-amber-500 shadow-sm"
                    }`}
                  />
                );
              })}
          </div>
        ) : (
          <div className="text-slate-500 text-sm mt-20 text-center">
            Select or upload a PDF document to view pages and highlighted proof.
          </div>
        )}
      </div>
    </div>
  );
}