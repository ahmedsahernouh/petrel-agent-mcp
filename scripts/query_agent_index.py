#!/usr/bin/env python3
"""Query and smoke-test the local Petrel agent retrieval index."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = PROJECT_ROOT / "agent-index" / "petrel_knowledge_chunks.jsonl"
DEFAULT_RESULTS_JSON = PROJECT_ROOT / "agent-index" / "retrieval_smoke_results.json"
DEFAULT_RESULTS_MD = PROJECT_ROOT / "agent-index" / "retrieval_smoke_results.md"

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-+.]*")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "petrel",
    "the",
    "this",
    "to",
    "with",
}
PRACTICE_QUERY_TERMS = {"practice", "example", "fixture", "dataset", "course", "demo", "sample", "training"}
INSTALLED_HELP_QUERY_TERMS = {"2018", "help", "helpcenter", "installed", "command", "batch", "syntax", "editor"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text.lower()):
        token = raw.strip("._-+")
        if not token or token in STOPWORDS:
            continue
        tokens.append(token)
        compact = token.replace("-", "").replace("_", "")
        if compact and compact != token and compact not in STOPWORDS:
            tokens.append(compact)
    return tokens


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(value_to_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(value_to_text(item) for item in value)
    return str(value)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {exc}") from exc
    return rows


def weighted_chunk_text(chunk: dict[str, Any]) -> str:
    title = value_to_text(chunk.get("title", ""))
    description = value_to_text(chunk.get("description", ""))
    heading = value_to_text(chunk.get("heading_path", ""))
    tags = value_to_text(chunk.get("tags", ""))
    domain = value_to_text(chunk.get("domain", ""))
    tools = value_to_text(chunk.get("tools", ""))
    category = value_to_text(chunk.get("category", ""))
    source_id = value_to_text(chunk.get("source_id", ""))
    source_path = value_to_text(chunk.get("source_path", ""))
    chunk_text = value_to_text(chunk.get("chunk_text", ""))
    return " ".join(
        [
            " ".join([title] * 6),
            " ".join([description] * 3),
            " ".join([heading] * 4),
            " ".join([tags, domain, tools, category] * 3),
            source_id,
            source_path,
            chunk_text,
        ]
    )


class SearchIndex:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            raise ValueError("The agent index has no chunks.")
        self.chunks = chunks
        self.term_freqs: list[Counter[str]] = []
        self.lengths: list[int] = []
        self.doc_freq: Counter[str] = Counter()
        for chunk in chunks:
            tokens = tokenize(weighted_chunk_text(chunk))
            tf = Counter(tokens)
            self.term_freqs.append(tf)
            self.lengths.append(sum(tf.values()))
            self.doc_freq.update(tf.keys())
        self.avg_len = sum(self.lengths) / max(1, len(self.lengths))

    def bm25(self, index: int, query_terms: Counter[str]) -> float:
        tf = self.term_freqs[index]
        doc_len = self.lengths[index] or 1
        score = 0.0
        k1 = 1.45
        b = 0.72
        total_docs = len(self.chunks)
        for term, query_count in query_terms.items():
            freq = tf.get(term, 0)
            if freq == 0:
                continue
            df = self.doc_freq.get(term, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / self.avg_len)
            score += idf * ((freq * (k1 + 1)) / denom) * min(query_count, 3)
        return score

    def score_metadata(self, chunk: dict[str, Any], query: str, query_tokens: list[str]) -> float:
        normalized_query = normalize_text(query)
        title = normalize_text(value_to_text(chunk.get("title", "")))
        heading = normalize_text(value_to_text(chunk.get("heading_path", "")))
        tags = normalize_text(value_to_text(chunk.get("tags", "")))
        tier = str(chunk.get("retrieval_tier", ""))
        collection = str(chunk.get("collection", ""))
        confidence = str(chunk.get("confidence", ""))
        priority = float(chunk.get("retrieval_priority", 40) or 40)
        token_set = set(query_tokens)

        score = priority / 24.0
        if collection in {"workflow", "skill"}:
            score += 2.5
        elif collection in {"tool", "concept"}:
            score += 1.5
        if normalized_query and normalized_query in title:
            score += 8.0
        title_tokens = set(tokenize(title))
        if title_tokens and title_tokens.issubset(token_set):
            score += 6.0
        if normalized_query and normalized_query in heading:
            score += 4.0

        important = [token for token in query_tokens if token not in {"data", "workflow", "tool"}]
        if important:
            title_hits = sum(1 for token in set(important) if token in title)
            heading_hits = sum(1 for token in set(important) if token in heading)
            tag_hits = sum(1 for token in set(important) if token in tags)
            score += title_hits * 1.2 + heading_hits * 0.8 + tag_hits * 0.6

        score += float(chunk.get("operation_readiness_score", 0) or 0) * 0.12

        if collection == "example_data" and not (token_set & PRACTICE_QUERY_TERMS):
            score -= 3.0
        if tier.startswith("tier_5") and collection == "source":
            score -= 1.25
        if confidence == "local_install_help_metadata" and token_set & INSTALLED_HELP_QUERY_TERMS:
            score += 1.25
        return score

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        query_terms = Counter(query_tokens)
        scored: list[dict[str, Any]] = []
        for idx, chunk in enumerate(self.chunks):
            lexical = self.bm25(idx, query_terms)
            if lexical <= 0:
                continue
            metadata = self.score_metadata(chunk, query, query_tokens)
            score = lexical + metadata
            result = dict(chunk)
            result["_score"] = round(score, 4)
            result["_lexical_score"] = round(lexical, 4)
            result["_metadata_score"] = round(metadata, 4)
            result["_snippet"] = make_snippet(value_to_text(chunk.get("chunk_text", "")), query_tokens)
            scored.append(result)
        scored.sort(
            key=lambda row: (
                float(row["_score"]),
                int(row.get("retrieval_priority", 0) or 0),
                int(row.get("operation_readiness_score", 0) or 0),
            ),
            reverse=True,
        )
        return scored[:top_k]


def make_snippet(text: str, query_tokens: list[str], width: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    lower = compact.lower()
    positions = [lower.find(token) for token in query_tokens if lower.find(token) >= 0]
    if positions:
        start = max(0, min(positions) - 80)
    else:
        start = 0
    end = min(len(compact), start + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(compact) else ""
    return prefix + compact[start:end] + suffix


def print_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No matching chunks.")
        return
    for rank, result in enumerate(results, start=1):
        heading_path = result.get("heading_path", "")
        if isinstance(heading_path, list):
            heading = " > ".join(str(item) for item in heading_path)
        else:
            heading = value_to_text(heading_path)
        print(f"{rank}. score={result['_score']} tier={result.get('retrieval_tier')} title={result.get('title')}")
        print(f"   heading: {heading}")
        print(f"   review={result.get('review_status')} confidence={result.get('confidence')}")
        print(f"   path: {result.get('vault_path')}")
        print(f"   snippet: {result.get('_snippet')}")


def hit_haystack(hit: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                value_to_text(hit.get("title", "")),
                value_to_text(hit.get("heading_path", "")),
                value_to_text(hit.get("vault_path", "")),
                value_to_text(hit.get("source_id", "")),
                value_to_text(hit.get("source_path", "")),
                value_to_text(hit.get("chunk_text", "")),
            ]
        )
    )


def evaluate_case(search_index: SearchIndex, case: dict[str, Any], top_k: int) -> dict[str, Any]:
    query = str(case["query"])
    expected_any = [normalize_text(str(item)) for item in case.get("expected_any", [])]
    expected_title_any = [normalize_text(str(item)) for item in case.get("expected_title_any", [])]
    expected_path_any = [normalize_text(str(item)) for item in case.get("expected_path_any", [])]
    required_terms = [normalize_text(str(item)) for item in case.get("required_terms", [])]
    results = search_index.search(query, top_k)
    pass_rank: int | None = None
    matched = ""

    for rank, hit in enumerate(results, start=1):
        haystack = hit_haystack(hit)
        title = normalize_text(value_to_text(hit.get("title", "")))
        path = normalize_text(value_to_text(hit.get("vault_path", "")))
        if expected_any and not any(expected in haystack for expected in expected_any):
            continue
        if expected_title_any and not any(expected in title for expected in expected_title_any):
            continue
        if expected_path_any and not any(expected in path for expected in expected_path_any):
            continue
        if required_terms and not all(term in haystack for term in required_terms):
            continue
        pass_rank = rank
        matched = str(hit.get("title", ""))
        break

    has_expectation = bool(expected_any or expected_title_any or expected_path_any or required_terms)
    passed = pass_rank is not None if has_expectation else bool(results)
    return {
        "query": query,
        "passed": passed,
        "pass_rank": pass_rank,
        "matched": matched,
        "expected_any": case.get("expected_any", []),
        "expected_title_any": case.get("expected_title_any", []),
        "expected_path_any": case.get("expected_path_any", []),
        "required_terms": case.get("required_terms", []),
        "top_results": [
            {
                "rank": idx,
                "score": hit.get("_score"),
                "title": hit.get("title"),
                "heading_path": hit.get("heading_path"),
                "vault_path": hit.get("vault_path"),
                "retrieval_tier": hit.get("retrieval_tier"),
                "review_status": hit.get("review_status"),
                "confidence": hit.get("confidence"),
            }
            for idx, hit in enumerate(results, start=1)
        ],
    }


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path)


def write_eval_outputs(results: list[dict[str, Any]], args: argparse.Namespace) -> None:
    generated_at = utc_now()
    payload = {
        "generated_at": generated_at,
        "index": str(Path(args.index).resolve()),
        "eval_file": str(Path(args.eval).resolve()) if args.eval else "",
        "top_k": args.top_k,
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["passed"]),
        "failed_count": sum(1 for result in results if not result["passed"]),
        "results": results,
    }
    results_json = Path(args.results_json or DEFAULT_RESULTS_JSON)
    results_md = Path(args.results_md or DEFAULT_RESULTS_MD)
    results_json.parent.mkdir(parents=True, exist_ok=True)
    results_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Petrel Retrieval Smoke Results",
        "",
        f"- Generated: `{generated_at}`",
        f"- Index: `{payload['index']}`",
        f"- Eval file: `{payload['eval_file']}`",
        f"- Top K: `{args.top_k}`",
        f"- Passed: `{payload['passed_count']}`",
        f"- Failed: `{payload['failed_count']}`",
        "",
        "| Status | Rank | Query | Matched |",
        "| --- | ---: | --- | --- |",
    ]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        rank = result["pass_rank"] if result["pass_rank"] is not None else ""
        matched = result["matched"] or ""
        lines.append(f"| {status} | {rank} | {result['query']} | {matched} |")
    results_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval(search_index: SearchIndex, args: argparse.Namespace) -> int:
    cases = load_eval_cases(Path(args.eval))
    results = [evaluate_case(search_index, case, args.top_k) for case in cases]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        rank = result["pass_rank"] if result["pass_rank"] is not None else "-"
        matched = result["matched"] or "(no expected hit)"
        print(f"[{status}] rank={rank} query={result['query']} -> {matched}")
    write_eval_outputs(results, args)
    failed = sum(1 for result in results if not result["passed"])
    print(f"Smoke tests: {len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to petrel_knowledge_chunks.jsonl.")
    parser.add_argument("--query", help="Query string to run against the index.")
    parser.add_argument("--eval", help="JSONL file of retrieval smoke-test cases.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of chunks to return or evaluate.")
    parser.add_argument("--results-json", help="Where to write evaluation JSON.")
    parser.add_argument("--results-md", help="Where to write evaluation Markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.query and not args.eval:
        print("Specify --query or --eval.", file=sys.stderr)
        return 2

    chunks = load_jsonl(Path(args.index))
    search_index = SearchIndex(chunks)

    exit_code = 0
    if args.query:
        print_results(search_index.search(args.query, args.top_k))
    if args.eval:
        exit_code = run_eval(search_index, args)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
