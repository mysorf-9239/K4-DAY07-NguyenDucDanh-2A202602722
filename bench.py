from __future__ import annotations

import argparse
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from src import (
    ChunkingStrategyComparator,
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    GeminiEmbedder,
    LocalEmbedder,
    OpenAIEmbedder,
    RecursiveChunker,
    SentenceChunker,
    _mock_embed,
)

DATA_DIR = Path("data/library-policy")
TOP_K = 3
CHUNK_SIZE = 700

# CP5: each member changes ONLY this line so the rest of the harness stays identical.
# Me uses heading-aware chunking to satisfy the L3A heading/section requirement.
STRATEGY = "heading_aware"

BASELINE_DOCS = (
    "course-reserves-student.md",
    "equipment-loans.md",
    "interlibrary-consortium-loans.md",
)


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    query: str
    gold_answer: str
    gold_doc_ids: tuple[str, ...]
    metadata_filter: dict[str, str] | None = None


BENCHMARKS = (
    BenchmarkCase(
        id="Q1",
        query="How long can I borrow books?",
        gold_answer=(
            "For an undergraduate student, the number of books is unlimited "
            "and the loan period is 6 weeks."
        ),
        gold_doc_ids=("borrowing-books-undergraduate",),
        metadata_filter={"audience": "student"},
    ),
    BenchmarkCase(
        id="Q2",
        query="How many reserve items may a student borrow at one time?",
        gold_answer="Students may borrow up to three reserve items at one time.",
        gold_doc_ids=("course-reserves-student",),
    ),
    BenchmarkCase(
        id="Q3",
        query=(
            "How do I request library equipment, and how far in advance "
            "must I reserve it?"
        ),
        gold_answer=(
            'From the equipment page, click "Reserve this item", log into the '
            "library account, and make the request. Reservations must be made "
            "at least 1 day in advance."
        ),
        gold_doc_ids=("equipment-loans",),
    ),
    BenchmarkCase(
        id="Q4",
        query="How long do Interlibrary Loan requests usually take to arrive?",
        gold_answer="Average delivery times for Interlibrary Loans are 7-14 business days.",
        gold_doc_ids=("interlibrary-consortium-loans",),
    ),
    BenchmarkCase(
        id="Q5",
        query=(
            "Where is food allowed in Lauinger Library, and what kinds of food "
            "are prohibited?"
        ),
        gold_answer=(
            "Food is allowed only on the second floor of Lauinger Library. "
            "Examples of prohibited food include pizza, hamburgers, fries, "
            "ice cream, hot subs, and other smelly, greasy, or messy foods."
        ),
        gold_doc_ids=("library-use-policy",),
    ),
)


class HeadingAwareChunker:
    """Chunk Markdown by heading hierarchy, with recursive fallback for long sections.

    Each emitted chunk keeps its heading path. If a section is longer than
    chunk_size, RecursiveChunker splits only the body and the heading path is
    prepended to every child chunk so later pieces do not lose section context.
    """

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def __init__(self, chunk_size: int = CHUNK_SIZE) -> None:
        self.chunk_size = max(100, chunk_size)

    def chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        chunks: list[str] = []
        heading_stack: list[tuple[int, str]] = []
        body_lines: list[str] = []

        def emit_section() -> None:
            nonlocal body_lines

            body = "\n".join(body_lines).strip()
            body_lines = []

            if not body:
                return

            prefix = "\n".join(heading for _, heading in heading_stack).strip()

            if prefix:
                full_section = f"{prefix}\n\n{body}"
            else:
                full_section = body

            if len(full_section) <= self.chunk_size:
                chunks.append(full_section)
                return

            # Keep enough room to prepend the complete heading path to every
            # recursively split child.
            prefix_cost = len(prefix) + 2 if prefix else 0
            body_budget = max(100, self.chunk_size - prefix_cost)

            pieces = RecursiveChunker(chunk_size=body_budget).chunk(body)

            for piece in pieces:
                if prefix:
                    chunks.append(f"{prefix}\n\n{piece}".strip())
                else:
                    chunks.append(piece.strip())

        for raw_line in text.splitlines():
            match = self.HEADING_RE.match(raw_line.strip())

            if match:
                # Flush content belonging to the previous heading path.
                emit_section()

                level = len(match.group(1))
                heading = raw_line.strip()

                # Keep only parent headings, then add the new current heading.
                heading_stack = [
                    (existing_level, existing_heading)
                    for existing_level, existing_heading in heading_stack
                    if existing_level < level
                ]
                heading_stack.append((level, heading))
            else:
                body_lines.append(raw_line)

        emit_section()

        # Heading-only documents are rare, but return something useful rather
        # than silently dropping all content.
        if not chunks and heading_stack:
            chunks.append("\n".join(h for _, h in heading_stack))

        return [chunk for chunk in chunks if chunk.strip()]


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Parse the simple YAML frontmatter used by this lab without PyYAML."""
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"{path} does not start with YAML frontmatter")

    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError(f"{path} has malformed YAML frontmatter")

    frontmatter_text = parts[1]
    body = parts[2].strip()

    metadata: dict[str, str] = {}

    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    # The filename stem is the canonical original-document id in the lab.
    metadata["doc_id"] = path.stem

    return metadata, body


def make_chunker(strategy: str):
    """Return the selected strategy while keeping the benchmark harness fixed."""
    if strategy == "fixed_size":
        return FixedSizeChunker(chunk_size=CHUNK_SIZE, overlap=100)
    if strategy == "by_sentences":
        return SentenceChunker(max_sentences_per_chunk=5)
    if strategy == "recursive":
        return RecursiveChunker(chunk_size=CHUNK_SIZE)
    if strategy == "heading_aware":
        return HeadingAwareChunker(chunk_size=CHUNK_SIZE)

    raise ValueError(f"Unknown strategy: {strategy}")


class NormalizedEmbedder:
    """Normalize any backend so EmbeddingStore dot product equals cosine."""

    def __init__(self, base: Callable[[str], list[float]], backend_name: str) -> None:
        self.base = base
        self._backend_name = backend_name

    def __call__(self, text: str) -> list[float]:
        vector = [float(value) for value in self.base(text)]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def make_embedder() -> NormalizedEmbedder:
    """Select the embedding backend from EMBEDDING_PROVIDER."""
    load_dotenv(override=False)
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()

    try:
        if provider == "local":
            base = LocalEmbedder()
            name = getattr(base, "_backend_name", "local")
        elif provider == "openai":
            base = OpenAIEmbedder()
            name = getattr(base, "_backend_name", "openai")
        elif provider == "gemini":
            base = GeminiEmbedder()
            name = getattr(base, "_backend_name", "gemini")
        elif provider == "mock":
            base = _mock_embed
            name = "mock embeddings fallback"
        else:
            raise ValueError(f"Unsupported EMBEDDING_PROVIDER={provider!r}")
    except Exception as exc:
        print(
            f"[warning] Could not initialize {provider!r} embedder: "
            f"{exc}. Falling back to mock embeddings."
        )
        base = _mock_embed
        name = "mock embeddings fallback"

    return NormalizedEmbedder(base=base, backend_name=name)


def load_chunk_documents(chunker) -> tuple[list[Document], dict[str, int]]:
    """Parse, chunk, and spread frontmatter metadata onto every chunk."""
    docs: list[Document] = []
    per_doc_counts: dict[str, int] = {}

    paths = sorted(DATA_DIR.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No Markdown documents found under {DATA_DIR}")

    for path in paths:
        metadata, body = parse_frontmatter(path)
        chunks = chunker.chunk(body)
        per_doc_counts[path.stem] = len(chunks)

        for index, chunk in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                "doc_id": path.stem,
                "chunk_index": index,
                "chunk_strategy": STRATEGY,
            }

            docs.append(
                Document(
                    id=f"{path.stem}#{index}",
                    content=chunk,
                    metadata=chunk_metadata,
                )
            )

    return docs, per_doc_counts


def compact(text: str, limit: int = 190) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def run_baseline() -> None:
    """Run the three built-in chunkers on three representative clean bodies."""
    comparator = ChunkingStrategyComparator()

    print("=== BASELINE CHUNKING ANALYSIS ===")
    print("Frontmatter is excluded from all measurements.\n")

    for filename in BASELINE_DOCS:
        path = DATA_DIR / filename
        _, body = parse_frontmatter(path)
        result = comparator.compare(body, chunk_size=CHUNK_SIZE)

        print(f"Document: {path.stem}")
        for strategy_name in ("fixed_size", "by_sentences", "recursive"):
            stats = result[strategy_name]
            print(
                f"  {strategy_name:13} "
                f"count={stats['count']:>3} "
                f"avg_length={stats['avg_length']:.1f}"
            )
        print()


def run_benchmark() -> None:
    chunker = make_chunker(STRATEGY)
    embedder = make_embedder()
    docs, per_doc_counts = load_chunk_documents(chunker)

    store = EmbeddingStore(
        collection_name=f"library_policy_{STRATEGY}",
        embedding_fn=embedder,
    )
    store.add_documents(docs)

    print("=== CP5 RETRIEVAL BENCHMARK ===")
    print(f"Data directory     : {DATA_DIR}")
    print(f"Strategy           : {STRATEGY}")
    print(f"Embedding backend  : {embedder._backend_name}")
    print(f"Documents          : {len(per_doc_counts)}")
    print(f"Chunks loaded      : {store.get_collection_size()}")
    print("Chunks per document:")
    for doc_id, count in per_doc_counts.items():
        print(f"  - {doc_id}: {count}")

    if embedder._backend_name == "mock embeddings fallback":
        print(
            "\n[warning] Mock embeddings do not represent semantic similarity. "
            "They are acceptable for CP5 pipeline validation, but switch to a "
            "real backend before judging retrieval quality in CP6."
        )

    for case in BENCHMARKS:
        print("\n" + "=" * 88)
        print(f"{case.id}: {case.query}")
        print(f"Metadata filter: {case.metadata_filter}")
        print(f"Gold document(s): {', '.join(case.gold_doc_ids)}")
        print(f"Gold answer: {case.gold_answer}")

        results = store.search_with_filter(
            case.query,
            top_k=TOP_K,
            metadata_filter=case.metadata_filter,
        )

        if not results:
            print("  NO RESULTS")
            continue

        gold_doc_hit = False

        for rank, result in enumerate(results, start=1):
            metadata = result["metadata"]
            doc_id = metadata.get("doc_id", "unknown")
            chunk_index = metadata.get("chunk_index", "?")

            if doc_id in case.gold_doc_ids:
                gold_doc_hit = True

            print(
                f"  {rank}. score={result['score']:.4f} "
                f"doc_id={doc_id} chunk={chunk_index} "
                f"audience={metadata.get('audience')}"
            )
            print(f"     {compact(result['content'])}")

        print(
            "Gold-document present in top-3: "
            + ("YES" if gold_doc_hit else "NO")
            + "  (navigation aid only; CP6 relevance must be judged from chunk content)"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run built-in chunking baseline on three representative documents.",
    )
    args = parser.parse_args()

    if args.baseline:
        run_baseline()
    else:
        run_benchmark()


if __name__ == "__main__":
    main()
