#!/usr/bin/env python3
"""Rebuild investigation visualization from saved data.

Usage:
    python3 tools/build-investigation.py investigations/isabel-dos-santos/raw-data.json
    python3 tools/build-investigation.py data.json --portable
    python3 tools/build-investigation.py data.json --slug my-investigation
    python3 tools/build-investigation.py data.json --no-open
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sift.visualizer import generate_visualization


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild investigation visualization from saved JSON data",
    )
    parser.add_argument(
        "data_file", type=Path,
        help="JSON file with investigation data (raw-data.json or full investigation dict)",
    )
    parser.add_argument(
        "--portable", action="store_true",
        help="Produce a single self-contained HTML file",
    )
    parser.add_argument(
        "--slug", type=str, default=None,
        help="Investigation slug for output directory name",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't open browser after generating",
    )
    args = parser.parse_args()

    if not args.data_file.exists():
        print(f"Error: {args.data_file} not found", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.data_file.read_text(encoding="utf-8"))

    # If data is the raw graph payload (has "metadata" key), wrap it for
    # generate_visualization which expects the pre-graph-build format.
    # If it already has "metadata.query", it's the built graph — pass as-is
    # but set the query for slug generation.
    if "metadata" in data and "nodes" in data:
        # Already-built graph data — wrap minimally so generate_visualization
        # can skip _build_graph and just re-serialize.
        # Actually, generate_visualization always calls _build_graph on the
        # input, so we need to pass raw investigation data.
        # If only raw-data.json is available (the built graph), we can
        # bypass generate_visualization and write files directly.
        from sift.visualizer import _write_split, _write_portable, _slugify

        slug = args.slug or _slugify(data.get("metadata", {}).get("query", "investigation"))
        graph_json = json.dumps(data, ensure_ascii=False)

        if args.portable:
            path = _write_portable(graph_json, slug, None, not args.no_open)
        else:
            path = _write_split(graph_json, slug, None, not args.no_open)
    else:
        # Raw investigation data — full pipeline
        path = generate_visualization(
            data,
            open_browser=not args.no_open,
            portable=args.portable,
            slug=args.slug,
        )

    print(f"Wrote: {path}")


if __name__ == "__main__":
    main()
