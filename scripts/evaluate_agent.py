from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaoyan_ai.evaluation import load_traces, trace_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize persisted Agent run traces.")
    parser.add_argument(
        "--trace-dir",
        type=Path,
        default=Path("data/agent_runs"),
    )
    args = parser.parse_args()
    paths = sorted(args.trace_dir.glob("*.jsonl"))
    print(json.dumps(trace_metrics(load_traces(paths)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
