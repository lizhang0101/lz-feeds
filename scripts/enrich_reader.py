#!/usr/bin/env python3
"""Add AI-generated summaries to the reader page JSON.

Reads ``_data/latest_entries.json``, sends each entry's snippet to Gemini,
and writes ``ai_summary`` back to the same file in place.

Usage:
    python enrich_reader.py [--reader PATH] [--model MODEL]

Defaults:
    --reader  ../_data/latest_entries.json  (relative to this script)
    --model   gemini-2.5-flash

Environment:
    GEMINI_API_KEY — Google Gemini API key (required)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types


READER_SYSTEM_PROMPT = """\
You are summarizing RSS article excerpts for a personal reading page. For each entry, write a 1-2 sentence summary in Chinese that captures the main point concisely. Be specific — mention key facts, names, or findings.

Return a JSON array. Each object must have:
  "link": copy from input exactly
  "ai_summary": 1-2 sentences in Chinese\
"""


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Error: set GEMINI_API_KEY")
    return key


def enrich_reader(client: "genai.Client", reader_path: Path, model: str) -> None:
    """Generate AI summaries for reader entries and write them back."""
    with open(reader_path, encoding="utf-8") as f:
        data = json.load(f)

    to_summarize = []
    for src in data.get("sources", []):
        for entry in src.get("entries", []):
            if entry.get("snippet") and not entry.get("ai_summary"):
                to_summarize.append(
                    {
                        "link": entry["link"],
                        "title": entry.get("title", ""),
                        "snippet": entry["snippet"],
                    }
                )

    if not to_summarize:
        print("No entries with snippets to summarize")
        return

    print(f"Summarizing {len(to_summarize)} reader entries with {model}...")
    response = client.models.generate_content(
        model=model,
        contents=(
            f"Summarize these {len(to_summarize)} entries:\n\n"
            f"{json.dumps(to_summarize, ensure_ascii=False)}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=READER_SYSTEM_PROMPT,
            max_output_tokens=16384,
            response_mime_type="application/json",
        ),
    )

    try:
        results = json.loads(response.text)
        if isinstance(results, dict):
            results = list(results.values())
        summaries = {
            item["link"]: item.get("ai_summary", "")
            for item in results
            if "link" in item
        }
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"Warning: JSON parse error: {exc}", file=sys.stderr)
        return

    updated = 0
    for src in data["sources"]:
        for entry in src["entries"]:
            if entry["link"] in summaries:
                entry["ai_summary"] = summaries[entry["link"]]
                updated += 1

    with open(reader_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Updated {updated} entries with AI summaries → {reader_path}")


def main() -> None:
    default_reader = Path(__file__).resolve().parent.parent / "_data" / "latest_entries.json"
    parser = argparse.ArgumentParser(
        description="Add AI summaries to the reader JSON"
    )
    parser.add_argument(
        "--reader",
        type=Path,
        default=default_reader,
        help=f"Path to reader JSON (default: {default_reader})",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model ID (default: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    if not args.reader.exists():
        sys.exit(f"Error: {args.reader} not found")

    client = genai.Client(api_key=get_api_key())
    enrich_reader(client, args.reader, args.model)


if __name__ == "__main__":
    main()
