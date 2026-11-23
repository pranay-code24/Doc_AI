import json
import re
from typing import Any

from app.config import AMENDMENT_GRAPH_FILE
from app.llm.ollama_client import call_ollama_json


METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_id": {"type": "string"},
        "effective_date": {"type": "string"},
        "amends_doc_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "clause_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_ref": {"type": "string"},
                    "subject": {"type": "string"},
                    "action": {"type": "string", "enum": ["defines", "supersedes", "retains"]},
                    "new_value_summary": {"type": "string"},
                },
                "required": ["clause_ref", "subject", "action", "new_value_summary"],
            },
        },
    },
    "required": ["doc_id", "effective_date", "amends_doc_ids", "clause_changes"],
}


METADATA_SYSTEM_PROMPT = """You are a precise legal/policy document metadata extractor.
Analyze the given document text and extract:
1. "doc_id": Official Document ID (e.g., "POL-2023-01", "CIRC-2024-07"). If none, use the filename.
2. "effective_date": ISO date "YYYY-MM-DD" when the document takes effect. If unknown, use "1900-01-01".
3. "amends_doc_ids": List of Document IDs that this document DIRECTLY amends or supersedes (e.g., ["POL-2023-01"]). Return [] if it does not formally amend another document.
4. "clause_changes": For each major numbered clause (e.g. "Clause 4.2", "Clause 5.1") mentioned in this document:
   - "clause_ref": normalized clause label like "Clause 4.2" (or topic name if no number).
   - "subject": short topic name (e.g. "Base Interest Rate", "Late Payment Penalty").
   - "action":
       * "supersedes" ONLY if this document explicitly amends/replaces/supersedes an earlier clause.
       * "retains" if this document explicitly says a prior rule remains active/unchanged.
       * "defines" if this document introduces a base rule without superseding an earlier document.
   - "new_value_summary": concise summary of the rule/number (e.g., "11.25% per annum").
"""


CLAUSE_REF_RE = re.compile(r"\bClause\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)


def extract_clause_refs(text: str) -> list[str]:
    """Text se normalized clause references (e.g., 'Clause 4.2') nikalta hai."""
    matches = CLAUSE_REF_RE.findall(text)
    seen = []
    for m in matches:
        ref = f"Clause {m}"
        if ref not in seen:
            seen.append(ref)
    return seen


def regex_header_hints(doc_name: str, full_text: str) -> dict[str, Any]:
    """Fast deterministic regex fallback for common banking/policy headers."""
    doc_id_m = re.search(r"Document\s*ID\s*:\s*([A-Z0-9\-_/]+)", full_text, re.IGNORECASE)
    date_m = re.search(r"Effective\s*Date\s*:\s*(\d{4}-\d{2}-\d{2})", full_text, re.IGNORECASE)
    amends_m = re.search(r"Amends\s*:\s*([A-Z0-9\-_/]+)", full_text, re.IGNORECASE)
    return {
        "doc_id": doc_id_m.group(1).strip() if doc_id_m else "",
        "effective_date": date_m.group(1).strip() if date_m else "",
        "amends_direct": amends_m.group(1).strip() if amends_m else "",
        "doc_name": doc_name,
    }


class AmendmentGraph:
    def __init__(self):
        self.docs: dict[str, dict[str, Any]] = {}          # doc_name -> metadata
        self.id_to_doc_name: dict[str, str] = {}           # doc_id -> doc_name
        self.clause_chains: dict[str, list[dict]] = {}     # clause_ref -> chronologically sorted steps
        self.superseded_chunks: dict[str, dict] = {}       # chunk_id -> superseded_by info
        self.load()

    def load(self):
        if AMENDMENT_GRAPH_FILE.exists():
            data = json.loads(AMENDMENT_GRAPH_FILE.read_text(encoding="utf-8"))
            self.docs = data.get("docs", {})
            self.id_to_doc_name = data.get("id_to_doc_name", {})
            self.clause_chains = data.get("clause_chains", {})
            self.superseded_chunks = data.get("superseded_chunks", {})

    def save(self):
        payload = {
            "docs": self.docs,
            "id_to_doc_name": self.id_to_doc_name,
            "clause_chains": self.clause_chains,
            "superseded_chunks": self.superseded_chunks,
        }
        AMENDMENT_GRAPH_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def build_graph(self, chunks: list[dict[str, Any]], pages: list[dict[str, Any]]):
        """
        Saare documents ka amendment graph aur clause-level A -> B -> C timeline banata hai.
        """
        # 1. Group raw text per document
        pages_by_doc: dict[str, list[dict]] = {}
        for p in pages:
            pages_by_doc.setdefault(p["doc_name"], []).append(p)

        self.docs = {}
        self.id_to_doc_name = {}

        for doc_name, doc_pages in sorted(pages_by_doc.items()):
            doc_pages.sort(key=lambda x: x["page_number"])
            # Pehle 2 pages ka text metadata extraction ke liye kaafi hota hai
            combined_text = "\n\n".join(p["raw_text"] for p in doc_pages[:2])
            hints = regex_header_hints(doc_name, combined_text)

            print(f"Extracting amendment metadata for: {doc_name} ...")
            meta = call_ollama_json(
                system_prompt=METADATA_SYSTEM_PROMPT,
                user_prompt=f"FILENAME: {doc_name}\n\nDOCUMENT TEXT:\n{combined_text}",
                json_schema=METADATA_SCHEMA,
            )

            # Regex hints se reliability boost karo
            doc_id = hints["doc_id"] or meta.get("doc_id") or doc_name
            eff_date = hints["effective_date"] or meta.get("effective_date") or "1900-01-01"

            amends_ids = list(meta.get("amends_doc_ids") or [])
            if hints["amends_direct"]:
                # Agar header me exact 'Amends: X' likha hai toh wahi direct parent hai
                amends_ids = [hints["amends_direct"]]
            # Self-reference hatao
            amends_ids = [a for a in amends_ids if a != doc_id and a != doc_name]

            self.docs[doc_name] = {
                "doc_name": doc_name,
                "doc_id": doc_id,
                "effective_date": eff_date,
                "amends_doc_ids": amends_ids,
                "clause_changes": meta.get("clause_changes", []),
            }
            self.id_to_doc_name[doc_id] = doc_name
            self.id_to_doc_name[doc_name] = doc_name

        # 2. Build document-level amendment ancestors (e.g., DocC amends DocB which amends DocA)
        def get_ancestors(doc_name: str, visited: set[str] | None = None) -> set[str]:
            visited = visited or set()
            ancestors: set[str] = set()
            meta = self.docs.get(doc_name, {})
            for parent_id in meta.get("amends_doc_ids", []):
                parent_name = self.id_to_doc_name.get(parent_id)
                if parent_name and parent_name not in visited:
                    visited.add(parent_name)
                    ancestors.add(parent_name)
                    ancestors |= get_ancestors(parent_name, visited)
            return ancestors

        doc_ancestors = {dn: get_ancestors(dn) for dn in self.docs}

        # 3. Map chunks to clauses and build chronological Clause Chains (A -> B -> C)
        # Sirf wahi documents ek chain me aate hain jo ek-dusre ke amendment lineage me hon!
        chunks_by_doc_and_clause: dict[tuple[str, str], list[dict]] = {}
        for ch in chunks:
            refs = extract_clause_refs(ch["text"])
            for ref in refs:
                chunks_by_doc_and_clause.setdefault((ch["doc_name"], ref), []).append(ch)

        self.clause_chains = {}
        self.superseded_chunks = {}

        # Collect all clause_refs mentioned across docs that participate in amendments
        all_clause_refs = sorted(
            {ref for (_, ref) in chunks_by_doc_and_clause.keys()}
        )

        for clause_ref in all_clause_refs:
            # Find docs that mention this clause_ref
            involved_docs = [
                dn for (dn, ref) in chunks_by_doc_and_clause.keys() if ref == clause_ref
            ]
            # Check if any doc in involved_docs amends another doc in involved_docs
            linked_docs = set()
            for dn in involved_docs:
                for other in involved_docs:
                    if other != dn and other in doc_ancestors.get(dn, set()):
                        linked_docs.add(dn)
                        linked_docs.add(other)

            if len(linked_docs) < 2:
                continue

            # Sort linked docs chronologically by effective_date
            ordered_docs = sorted(
                linked_docs,
                key=lambda dn: self.docs[dn]["effective_date"],
            )

            chain_steps = []
            for dn in ordered_docs:
                meta = self.docs[dn]
                doc_chunks = chunks_by_doc_and_clause[(dn, clause_ref)]
                # Choose the most descriptive chunk for this clause in this doc
                best_chunk = max(doc_chunks, key=lambda c: len(c["text"]))

                # Find matching action & summary from LLM metadata
                action = "defines"
                summary = best_chunk["text"][:140]
                subject = best_chunk.get("section_title", clause_ref)
                for cc in meta.get("clause_changes", []):
                    if cc.get("clause_ref", "").lower() == clause_ref.lower():
                        action = cc.get("action", action)
                        summary = cc.get("new_value_summary", summary)
                        subject = cc.get("subject", subject)
                        break

                # Fallback check in text for "superseded"
                if action == "defines" and meta["amends_doc_ids"]:
                    if re.search(r"\b(supersed|amend|revis|increas|chang)", best_chunk["text"], re.IGNORECASE):
                        action = "supersedes"

                chain_steps.append(
                    {
                        "clause_ref": clause_ref,
                        "subject": subject,
                        "doc_name": dn,
                        "doc_id": meta["doc_id"],
                        "effective_date": meta["effective_date"],
                        "amends_doc_ids": meta["amends_doc_ids"],
                        "action": action,
                        "summary": summary,
                        "chunk_id": best_chunk["chunk_id"],
                        "page_number": best_chunk["page_number"],
                        "quote": best_chunk["text"],
                        "status": "ACTIVE",  # Niche update hoga
                    }
                )

            # Mark earlier steps as SUPERSEDED by the latest superseding step
            # Find the last step that either defines or supersedes
            active_idx = 0
            for idx, step in enumerate(chain_steps):
                if step["action"] in ("defines", "supersedes"):
                    active_idx = idx

            active_step = chain_steps[active_idx]
            for idx, step in enumerate(chain_steps):
                if idx < active_idx:
                    step["status"] = "SUPERSEDED"
                    step["superseded_by"] = active_step["doc_id"]
                    # Mark all chunks for (doc_name, clause_ref) as superseded
                    for ch in chunks_by_doc_and_clause[(step["doc_name"], clause_ref)]:
                        self.superseded_chunks[ch["chunk_id"]] = {
                            "clause_ref": clause_ref,
                            "superseded_by_doc": active_step["doc_name"],
                            "superseded_by_doc_id": active_step["doc_id"],
                            "active_chunk_id": active_step["chunk_id"],
                        }
                else:
                    step["status"] = "ACTIVE"

            self.clause_chains[clause_ref] = chain_steps

        self.save()
        print(
            f"[OK] Amendment graph built: {len(self.docs)} docs, "
            f"{len(self.clause_chains)} amendment chains detected: {list(self.clause_chains.keys())}"
        )

    def resolve_chunks(
        self,
        retrieved_chunks: list[dict[str, Any]],
        all_chunks_by_id: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Retrieved chunks par ACTIVE vs SUPERSEDED status tag karta hai,
        relevant amendment chains collect karta hai, aur agar active latest chunk missing ho
        toh usko automatically context me inject kar deta hai.
        """
        relevant_chains: list[dict[str, Any]] = []
        seen_chain_refs: set[str] = set()
        chunk_map: dict[str, dict[str, Any]] = {}

        for ch in retrieved_chunks:
            enriched = dict(ch)
            cid = enriched["chunk_id"]
            if cid in self.superseded_chunks:
                sup_info = self.superseded_chunks[cid]
                enriched["status"] = f"SUPERSEDED (replaced by {sup_info['superseded_by_doc_id']})"
                enriched["is_active"] = False
            else:
                enriched["status"] = "ACTIVE (Currently Applicable)"
                enriched["is_active"] = True

            meta = self.docs.get(enriched["doc_name"], {})
            enriched["doc_id"] = meta.get("doc_id", enriched["doc_name"])
            enriched["effective_date"] = meta.get("effective_date", "1900-01-01")
            chunk_map[cid] = enriched

            # Check if this chunk belongs to any amendment chain
            # Sirf relevant chunks (score >= -0.5) ke liye hi amendment chain attach karo
            if enriched.get("rerank_score", 0.0) < -0.5:
                continue

            for ref in extract_clause_refs(enriched["text"]):
                if ref in self.clause_chains and ref not in seen_chain_refs:
                    seen_chain_refs.add(ref)
                    steps = self.clause_chains[ref]
                    relevant_chains.append(
                        {
                            "clause_ref": ref,
                            "subject": steps[-1]["subject"],
                            "active_doc_id": next(
                                (s["doc_id"] for s in reversed(steps) if s["status"] == "ACTIVE"),
                                steps[-1]["doc_id"],
                            ),
                            "active_summary": next(
                                (s["summary"] for s in reversed(steps) if s["status"] == "ACTIVE"),
                                steps[-1]["summary"],
                            ),
                            "steps": steps,
                        }
                    )

                    # Make sure the ACTIVE latest chunk of this chain is definitely in context!
                    for s in steps:
                        if s["status"] == "ACTIVE" and s["chunk_id"] not in chunk_map:
                            raw_active = all_chunks_by_id.get(s["chunk_id"])
                            if raw_active:
                                inj = dict(raw_active)
                                inj["status"] = "ACTIVE (Currently Applicable - Resolved from Amendment Chain)"
                                inj["is_active"] = True
                                inj["rerank_score"] = enriched.get("rerank_score", 1.0) + 0.5
                                inj["doc_id"] = s["doc_id"]
                                inj["effective_date"] = s["effective_date"]
                                chunk_map[s["chunk_id"]] = inj

        # Sort: ACTIVE chunks pehle aayein (sorted by rerank_score), phir SUPERSEDED chunks reference ke liye
        resolved_list = sorted(
            chunk_map.values(),
            key=lambda c: (1 if c["is_active"] else 0, c.get("rerank_score", 0.0)),
            reverse=True,
        )
        return resolved_list, relevant_chains

    def are_amendment_related(self, doc_a: str, doc_b: str) -> bool:
        """Check karta hai ki kya doc_a aur doc_b formal amendment relationship me hain."""
        if doc_a == doc_b:
            return False

        def is_ancestor(child: str, target: str, visited: set[str] | None = None) -> bool:
            visited = visited or set()
            for pid in self.docs.get(child, {}).get("amends_doc_ids", []):
                pname = self.id_to_doc_name.get(pid)
                if pname == target:
                    return True
                if pname and pname not in visited:
                    visited.add(pname)
                    if is_ancestor(pname, target, visited):
                        return True
            return False

        return is_ancestor(doc_a, doc_b) or is_ancestor(doc_b, doc_a)