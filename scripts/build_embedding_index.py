from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI

from kaoyan_ai.config import get_settings
from kaoyan_ai.rag import LocalRetriever


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an offline RAG embedding index.")
    parser.add_argument(
        "--collection",
        choices=("question_bank", "knowledge_points"),
        required=True,
    )
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required to build the embedding index")
    retriever = LocalRetriever()
    items = retriever.load_items(args.collection)
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=max(60, settings.llm_timeout_seconds),
    )
    indexed = []
    for offset in range(0, len(items), args.batch_size):
        batch = items[offset:offset + args.batch_size]
        texts = [retriever._item_text(item)[:8000] for item in batch]
        response = client.embeddings.create(model=settings.embedding_model, input=texts)
        for item, result in zip(batch, response.data):
            indexed.append({"id": item.id, "embedding": list(result.embedding)})
        print(f"{min(offset + len(batch), len(items))}/{len(items)}")
    output = settings.rag_embedding_index_dir / f"{args.collection}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {"model": settings.embedding_model, "items": indexed},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temp.replace(output)
    print(output)


if __name__ == "__main__":
    main()
