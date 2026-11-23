import json
import re
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.config import (
    CHUNKS_FILE,
    EMBED_MODEL_NAME,
    PAGES_FILE,
    QDRANT_COLLECTION,
    QDRANT_DIR,
    RERANK_MODEL_NAME,
)


def tokenize(text: str) -> list[str]:
    """BM25 ke liye smart tokenizer (numbers, decimals, percentages, clause IDs preserve karta hai)."""
    return re.findall(r"[a-zA-Z0-9]+(?:[.\-][a-zA-Z0-9]+)*%?", text.lower())


class HybridRetriever:
    def __init__(self):
        print(f"Loading embedding model: {EMBED_MODEL_NAME} ...")
        self.embedder = SentenceTransformer(EMBED_MODEL_NAME)
        self.vector_size = self.embedder.get_sentence_embedding_dimension()

        print(f"Loading multilingual reranker: {RERANK_MODEL_NAME} ...")
        self.reranker = CrossEncoder(RERANK_MODEL_NAME)

        # Local Qdrant (no Docker needed!)
        self.qdrant = QdrantClient(path=str(QDRANT_DIR))

        self.chunks: list[dict] = []
        self.chunk_by_id: dict[str, dict] = {}
        self.bm25: BM25Okapi | None = None

        # Agar pehle se indexed chunks pade hain toh load kar lo
        if CHUNKS_FILE.exists():
            self._load_chunks_from_disk()

    def _load_chunks_from_disk(self):
        self.chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
        self.chunk_by_id = {c["chunk_id"]: c for c in self.chunks}
        tokenized_corpus = [tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus) if tokenized_corpus else None

    def index_documents(self, chunks: list[dict], pages: list[dict]):
        """Chunks aur pages ko disk par save karta hai aur Qdrant + BM25 rebuild karta hai."""
        CHUNKS_FILE.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
        PAGES_FILE.write_text(json.dumps(pages, indent=2), encoding="utf-8")

        # Recreate Qdrant collection cleanly
        if self.qdrant.collection_exists(QDRANT_COLLECTION):
            self.qdrant.delete_collection(QDRANT_COLLECTION)

        self.qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

        # E5 models require "passage: " prefix for documents
        passage_texts = [f"passage: {c['text']}" for c in chunks]
        embeddings = self.embedder.encode(
            passage_texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

        points = []
        for chunk, vec in zip(chunks, embeddings):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vec.tolist(),
                    payload={"chunk_id": chunk["chunk_id"]},
                )
            )

        self.qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
        self._load_chunks_from_disk()
        print(f"Indexed {len(chunks)} chunks across {len(pages)} pages into Qdrant + BM25.")

    def _vector_search(self, query: str, top_k: int = 15) -> list[str]:
        # E5 models require "query: " prefix for user questions
        q_vec = self.embedder.encode(
            f"query: {query}",
            normalize_embeddings=True,
        ).tolist()

        response = self.qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=q_vec,
            limit=top_k,
        )
        return [pt.payload["chunk_id"] for pt in response.points]

    def _bm25_search(self, query: str, top_k: int = 15) -> list[str]:
        if not self.bm25 or not self.chunks:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        # Sirf wahi return karo jinka score > 0 ho
        return [self.chunks[i]["chunk_id"] for i in ranked_indices if scores[i] > 0]

    def search(self, query: str, top_k: int = 5, candidate_k: int = 15) -> list[dict[str, Any]]:
        """
        Hybrid Search Pipeline:
        Vector Search + BM25 -> Reciprocal Rank Fusion (RRF) -> Multilingual Cross-Encoder Rerank
        """
        if not self.chunks:
            return []

        vec_ids = self._vector_search(query, top_k=candidate_k)
        bm25_ids = self._bm25_search(query, top_k=candidate_k)

        # Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[str, float] = {}
        k_const = 60
        for rank, cid in enumerate(vec_ids, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k_const + rank)
        for rank, cid in enumerate(bm25_ids, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k_const + rank)

        candidate_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True,
        )[:candidate_k]

        candidates = [self.chunk_by_id[cid] for cid in candidate_ids if cid in self.chunk_by_id]
        if not candidates:
            return []

        # Cross-Encoder Reranking
        pairs = [(query, c["text"]) for c in candidates]
        rerank_scores = self.reranker.predict(pairs)

        results = []
        for chunk, r_score in zip(candidates, rerank_scores):
            enriched = dict(chunk)
            enriched["rerank_score"] = round(float(r_score), 4)
            enriched["rrf_score"] = round(rrf_scores[chunk["chunk_id"]], 4)
            results.append(enriched)

        results.sort(key=lambda x: x["rerank_score"], reverse=True)
        return results[:top_k]

    def close(self):
        self.qdrant.close()