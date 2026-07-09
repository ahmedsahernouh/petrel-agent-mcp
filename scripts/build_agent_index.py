#!/usr/bin/env python3
"""Build a local agent retrieval index from the Petrel knowledge vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_ROOT = PROJECT_ROOT / "vault" / "Petrel Knowledge Wiki"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "agent-index"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z0-9_]+):\s*(.*)$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def parse_block(lines: list[str]) -> Any:
    meaningful = [line for line in lines if line.strip()]
    if not meaningful:
        return []

    if all(line.strip().startswith("- ") for line in meaningful):
        return [parse_scalar(line.strip()[2:].strip()) for line in meaningful]

    result: dict[str, Any] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def commit_current() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        result[current_key] = parse_block(current_lines)
        current_key = None
        current_lines = []

    for line in meaningful:
        stripped = line.strip()
        match = FRONTMATTER_KEY_RE.match(stripped)
        if match:
            commit_current()
            key, rest = match.group(1), match.group(2)
            if rest.strip():
                result[key] = parse_scalar(rest)
            else:
                current_key = key
                current_lines = []
            continue
        if current_key is not None:
            current_lines.append(stripped)

    commit_current()
    if result:
        return result
    return "\n".join(line.rstrip() for line in lines).strip()


def parse_frontmatter(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def commit_current() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        data[current_key] = parse_block(current_lines)
        current_key = None
        current_lines = []

    for line in text.splitlines():
        if not line.strip() or line.lstrip() != line:
            if current_key is not None:
                current_lines.append(line)
            continue

        match = FRONTMATTER_KEY_RE.match(line)
        if not match:
            if current_key is not None:
                current_lines.append(line)
            continue

        commit_current()
        key, rest = match.group(1), match.group(2)
        if rest.strip():
            data[key] = parse_scalar(rest)
        else:
            current_key = key
            current_lines = []

    commit_current()
    return data


def split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    lines = markdown.splitlines()
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                frontmatter = "\n".join(lines[1:idx])
                body = "\n".join(lines[idx + 1 :])
                return parse_frontmatter(frontmatter), body
    return {}, markdown


def as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(value_to_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(value_to_text(item) for item in value)
    return str(value)


def markdown_to_text(markdown: str) -> str:
    text = markdown
    text = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r"\1 \2", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1 \2", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("`", " ")
    text = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[>#*_~|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_heading(raw: str) -> str:
    return markdown_to_text(raw).strip()


def iter_sections(body: str, default_title: str) -> list[tuple[list[str], str]]:
    sections: list[tuple[list[str], str]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        cleaned = markdown_to_text("\n".join(current_lines))
        if cleaned:
            sections.append((heading_stack[:] or [default_title], cleaned))
        current_lines = []

    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            heading = clean_heading(match.group(2))
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(heading)
            continue
        current_lines.append(line)

    flush()
    return sections


def split_long_text(text: str, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks: list[str] = []
    start = 0
    overlap = min(overlap_words, max_words // 3)
    while start < len(words):
        end = min(len(words), start + max_words)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(0, end - overlap)
    return chunks


def vault_link(rel_vault_path: str) -> str:
    return "/" + quote(rel_vault_path.replace("\\", "/"), safe="/#")


def collection_for_path(rel_vault_path: str) -> str:
    if rel_vault_path in {"index.md", "log.md"}:
        return "okf_navigation"
    top = rel_vault_path.split("/", 1)[0]
    if top.startswith("01 Sources"):
        return "source"
    if top.startswith("15 Topic Maps"):
        return "topic_map"
    if top.startswith("10 Manual Sections"):
        return "manual_section"
    if top.startswith("20 Workflows"):
        return "workflow"
    if top.startswith("30 Skills"):
        return "skill"
    if top.startswith("40 Tools"):
        return "tool"
    if top.startswith("50 Concepts"):
        return "concept"
    if top.startswith("60 Figures Tables"):
        return "figure_table"
    if top.startswith("70 Example Data"):
        return "example_data"
    if top.startswith("80 Courses"):
        return "course"
    if top.startswith("90 Indexes"):
        return "index"
    return "other"


def is_reviewed(review_status: str, confidence: str) -> bool:
    status = review_status.lower()
    conf = confidence.lower()
    positive = ("reviewed", "validated", "curated", "accepted")
    negative = ("needs", "draft", "raw", "unreviewed")
    return any(word in status or word in conf for word in positive) and not any(
        word in status or word in conf for word in negative
    )


def retrieval_profile(meta: dict[str, Any], rel_vault_path: str) -> tuple[str, int]:
    collection = collection_for_path(rel_vault_path)
    review_status = str(meta.get("review_status", "unknown"))
    confidence = str(meta.get("confidence", "unknown"))
    reviewed = is_reviewed(review_status, confidence)

    if collection in {"workflow", "skill"}:
        if reviewed:
            return "tier_1_reviewed_workflow_skill", 100
        return "tier_2_draft_workflow_skill", 84
    if collection == "topic_map":
        if reviewed:
            return "tier_2_reviewed_topic_map", 88
        return "tier_2_draft_topic_map", 80
    if collection == "manual_section":
        if reviewed:
            return "tier_2_reviewed_manual_section", 92
        return "tier_3_draft_manual_section", 72
    if collection in {"tool", "concept"}:
        if reviewed:
            return "tier_3_reviewed_tool_concept", 82
        return "tier_3_draft_tool_concept", 70
    if collection == "figure_table":
        return "tier_4_figure_table", 60
    if collection == "course":
        return "tier_4_course_map", 55
    if collection == "index":
        return "tier_4_index", 48
    if collection == "okf_navigation":
        return "tier_4_okf_navigation", 58
    if collection == "source":
        if str(meta.get("confidence", "")).lower() == "local_install_help_metadata":
            return "tier_5_installed_help_metadata", 52
        return "tier_5_raw_source", 45
    if collection == "example_data":
        return "tier_6_example_data", 35
    return "tier_5_other", 40


def detect_operation_signals(body: str) -> dict[str, Any]:
    lower = body.lower()
    headings = []
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            headings.append(clean_heading(match.group(2)).lower())

    def has_heading(*needles: str) -> bool:
        return any(any(needle in heading for needle in needles) for heading in headings)

    signals = {
        "has_inputs": has_heading("input", "required input"),
        "has_outputs": has_heading("output"),
        "has_preconditions": has_heading("precondition"),
        "has_steps": has_heading("steps", "execution phase", "workflow sequence"),
        "has_validation": has_heading("validation", "validation checks", "validation gates"),
        "has_failure_modes": has_heading("failure", "common failures"),
        "has_recovery": has_heading("recovery", "troubleshooting"),
        "has_mcp_tool_draft": "mcp tool draft" in lower or "tool_name:" in lower or "tool_family:" in lower,
        "has_source_evidence": has_heading("source evidence", "source evidence and gaps"),
    }
    signals["operation_readiness_score"] = sum(1 for value in signals.values() if value is True)
    return signals


def extract_source_locations(source_refs: Any) -> list[str]:
    locations: list[str] = []
    for ref in as_list(source_refs):
        match = re.search(r"\(([^)]+)\)", ref)
        target = match.group(1) if match else ref
        locations.append(target)
    return locations


def index_note(
    note_path: Path,
    vault_root: Path,
    max_words: int,
    overlap_words: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    markdown = note_path.read_text(encoding="utf-8", errors="replace")
    meta, body = split_frontmatter(markdown)
    rel_vault_path = note_path.relative_to(vault_root).as_posix()
    project_path = note_path.relative_to(PROJECT_ROOT).as_posix()
    title = str(meta.get("title") or note_path.stem)
    description = str(meta.get("description") or "")
    doc_id = stable_hash(rel_vault_path, 12)
    body_hash = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
    source_refs = as_list(meta.get("source_refs"))
    source_locations = extract_source_locations(source_refs)
    retrieval_tier, retrieval_priority = retrieval_profile(meta, rel_vault_path)
    collection = collection_for_path(rel_vault_path)
    operation_signals = detect_operation_signals(body)
    version_scope = meta.get("version_scope", {})

    sections = iter_sections(body, title)
    chunks: list[dict[str, Any]] = []
    chunk_ordinal = 0
    for heading_path, section_text in sections:
        for section_part_ordinal, chunk_text in enumerate(split_long_text(section_text, max_words, overlap_words), start=1):
            chunk_ordinal += 1
            chunk_id = stable_hash(
                f"{rel_vault_path}|{' > '.join(heading_path)}|{section_part_ordinal}|{chunk_text[:200]}",
                16,
            )
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "chunk_ordinal": chunk_ordinal,
                    "section_part_ordinal": section_part_ordinal,
                    "title": title,
                    "type": meta.get("type", ""),
                    "description": description,
                    "collection": collection,
                    "vault_path": rel_vault_path,
                    "project_path": project_path,
                    "vault_link": vault_link(rel_vault_path),
                    "heading_path": heading_path,
                    "heading": heading_path[-1] if heading_path else title,
                    "chunk_text": chunk_text,
                    "chunk_word_count": len(chunk_text.split()),
                    "tags": as_list(meta.get("tags")),
                    "domain": as_list(meta.get("domain")),
                    "tools": as_list(meta.get("tools")),
                    "category": meta.get("category", ""),
                    "source_id": meta.get("source_id", ""),
                    "source_kind": meta.get("source_kind", meta.get("source_type", "")),
                    "source_path": meta.get("source_path", ""),
                    "source_hash": meta.get("source_sha256", meta.get("source_hash", "")),
                    "resource": meta.get("resource", ""),
                    "source_refs": source_refs,
                    "source_locations": source_locations,
                    "source_page_or_section": source_locations,
                    "version_scope": version_scope,
                    "review_status": meta.get("review_status", "unknown"),
                    "confidence": meta.get("confidence", "unknown"),
                    "retrieval_tier": retrieval_tier,
                    "retrieval_priority": retrieval_priority,
                    "is_curated": collection in {"topic_map", "workflow", "skill", "manual_section", "tool", "concept"},
                    "operation_signals": operation_signals,
                    "operation_readiness_score": operation_signals["operation_readiness_score"],
                    "installed_product": meta.get("installed_product", ""),
                    "installed_version": meta.get("installed_version", ""),
                    "timestamp": meta.get("timestamp", ""),
                }
            )

    document = {
        "doc_id": doc_id,
        "title": title,
        "type": meta.get("type", ""),
        "description": description,
        "collection": collection,
        "vault_path": rel_vault_path,
        "project_path": project_path,
        "vault_link": vault_link(rel_vault_path),
        "body_sha256": body_hash,
        "heading_count": sum(1 for line in body.splitlines() if HEADING_RE.match(line)),
        "chunk_count": len(chunks),
        "word_count": len(markdown_to_text(body).split()),
        "tags": as_list(meta.get("tags")),
        "domain": as_list(meta.get("domain")),
        "tools": as_list(meta.get("tools")),
        "category": meta.get("category", ""),
        "source_id": meta.get("source_id", ""),
        "source_kind": meta.get("source_kind", meta.get("source_type", "")),
        "source_path": meta.get("source_path", ""),
        "source_hash": meta.get("source_sha256", meta.get("source_hash", "")),
        "resource": meta.get("resource", ""),
        "source_refs": source_refs,
        "source_locations": source_locations,
        "version_scope": version_scope,
        "review_status": meta.get("review_status", "unknown"),
        "confidence": meta.get("confidence", "unknown"),
        "retrieval_tier": retrieval_tier,
        "retrieval_priority": retrieval_priority,
        "is_curated": collection in {"topic_map", "workflow", "skill", "manual_section", "tool", "concept"},
        "operation_signals": operation_signals,
        "operation_readiness_score": operation_signals["operation_readiness_score"],
        "installed_product": meta.get("installed_product", ""),
        "installed_version": meta.get("installed_version", ""),
        "timestamp": meta.get("timestamp", ""),
    }
    return document, chunks


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=False) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_terms(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    token_re = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-+.]*")
    doc_freq: Counter[str] = Counter()
    term_freq: Counter[str] = Counter()
    for chunk in chunks:
        text = " ".join(
            [
                str(chunk.get("title", "")),
                str(chunk.get("description", "")),
                " ".join(as_list(chunk.get("heading_path"))),
                " ".join(as_list(chunk.get("tags"))),
                " ".join(as_list(chunk.get("domain"))),
                " ".join(as_list(chunk.get("tools"))),
                str(chunk.get("category", "")),
                str(chunk.get("chunk_text", "")),
            ]
        ).lower()
        tokens = [token.strip("._-+") for token in token_re.findall(text)]
        tokens = [token for token in tokens if token]
        term_freq.update(tokens)
        doc_freq.update(set(tokens))
    return {
        "chunk_count": len(chunks),
        "top_terms": [{"term": term, "frequency": count} for term, count in term_freq.most_common(250)],
        "top_document_terms": [{"term": term, "document_frequency": count} for term, count in doc_freq.most_common(250)],
    }


def table_from_counter(counter: Counter[str], left_header: str, right_header: str) -> list[str]:
    lines = [f"| {left_header} | {right_header} |", "| --- | ---: |"]
    for key, count in counter.most_common():
        lines.append(f"| `{key}` | {count} |")
    return lines


def write_summary(path: Path, documents: list[dict[str, Any]], chunks: list[dict[str, Any]], generated_at: str) -> None:
    doc_tiers = Counter(str(doc["retrieval_tier"]) for doc in documents)
    chunk_tiers = Counter(str(chunk["retrieval_tier"]) for chunk in chunks)
    doc_types = Counter(str(doc.get("type", "unknown")) for doc in documents)
    review_statuses = Counter(str(doc.get("review_status", "unknown")) for doc in documents)
    confidences = Counter(str(doc.get("confidence", "unknown")) for doc in documents)
    operation_docs = sorted(
        [doc for doc in documents if int(doc.get("operation_readiness_score", 0)) > 0],
        key=lambda row: (int(row.get("operation_readiness_score", 0)), int(row.get("retrieval_priority", 0))),
        reverse=True,
    )[:20]

    lines: list[str] = [
        "# Petrel Agent Index Summary",
        "",
        f"- Generated: `{generated_at}`",
        f"- Vault root: `{DEFAULT_VAULT_ROOT}`",
        f"- Documents indexed: `{len(documents)}`",
        f"- Chunks indexed: `{len(chunks)}`",
        "",
        "## Retrieval Tiers",
        "",
        "| Tier | Documents | Chunks |",
        "| --- | ---: | ---: |",
    ]
    for tier in sorted(set(doc_tiers) | set(chunk_tiers)):
        lines.append(f"| `{tier}` | {doc_tiers.get(tier, 0)} | {chunk_tiers.get(tier, 0)} |")

    lines.extend(["", "## Note Types", ""])
    lines.extend(table_from_counter(doc_types, "Type", "Documents"))
    lines.extend(["", "## Review Status", ""])
    lines.extend(table_from_counter(review_statuses, "Review status", "Documents"))
    lines.extend(["", "## Confidence", ""])
    lines.extend(table_from_counter(confidences, "Confidence", "Documents"))
    lines.extend(["", "## Highest Operation Readiness", ""])
    lines.extend(["| Score | Priority | Title | Path |", "| ---: | ---: | --- | --- |"])
    for doc in operation_docs:
        lines.append(
            f"| {doc.get('operation_readiness_score', 0)} | {doc.get('retrieval_priority', 0)} | "
            f"{doc.get('title', '')} | `{doc.get('vault_path', '')}` |"
        )

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `petrel_knowledge_documents.jsonl`: one row per vault note.",
            "- `petrel_knowledge_chunks.jsonl`: retrieval chunks with source, version, review, confidence, and tier metadata.",
            "- `petrel_knowledge_terms.json`: lightweight term-frequency report for debugging lexical retrieval.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def should_skip(path: Path, vault_root: Path) -> bool:
    rel_parts = path.relative_to(vault_root).parts
    return any(part in {"_templates", ".obsidian"} for part in rel_parts)


def build_index(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    vault_root = Path(args.vault_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for note_path in sorted(vault_root.rglob("*.md")):
        if should_skip(note_path, vault_root):
            continue
        document, note_chunks = index_note(note_path, vault_root, args.max_words, args.overlap_words)
        if document["chunk_count"] == 0:
            continue
        documents.append(document)
        chunks.extend(note_chunks)

    generated_at = utc_now()
    manifest = {
        "generated_at": generated_at,
        "project_root": str(PROJECT_ROOT),
        "vault_root": str(vault_root),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "chunk_max_words": args.max_words,
        "chunk_overlap_words": args.overlap_words,
        "schema": "petrel-agent-index-v1",
        "files": {
            "documents": "petrel_knowledge_documents.jsonl",
            "chunks": "petrel_knowledge_chunks.jsonl",
            "terms": "petrel_knowledge_terms.json",
            "summary": "petrel_knowledge_summary.md",
        },
    }

    write_jsonl(output_dir / "petrel_knowledge_documents.jsonl", documents)
    write_jsonl(output_dir / "petrel_knowledge_chunks.jsonl", chunks)
    write_json(output_dir / "petrel_knowledge_terms.json", build_terms(chunks))
    write_json(output_dir / "petrel_knowledge_manifest.json", manifest)
    write_summary(output_dir / "petrel_knowledge_summary.md", documents, chunks, generated_at)
    return documents, chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", default=str(DEFAULT_VAULT_ROOT), help="Vault root containing Petrel Markdown notes.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated agent index files.")
    parser.add_argument("--max-words", type=int, default=420, help="Maximum words per retrieval chunk.")
    parser.add_argument("--overlap-words", type=int, default=60, help="Word overlap for long split chunks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    documents, chunks = build_index(args)
    print(f"Indexed documents: {len(documents)}")
    print(f"Indexed chunks: {len(chunks)}")
    print(f"Output: {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
