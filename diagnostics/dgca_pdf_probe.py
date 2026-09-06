"""Minimal diagnostics-only PDF text probe without external dependencies."""

import re
import sys
import zlib
from pathlib import Path


def extract_strings(path: Path) -> str:
    data = path.read_bytes()
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        stream = match.group(1)
        candidates = [stream]
        if stream.startswith(b"\r\n"):
            candidates.append(stream[2:])
        if stream.startswith(b"\n"):
            candidates.append(stream[1:])
        for candidate in candidates:
            try:
                decoded = zlib.decompress(candidate)
            except Exception:
                continue
            chunks.extend(
                value.decode("latin1", "ignore")
                for value in re.findall(rb"\((?:\\.|[^\\()])*\)", decoded)
            )
    return " ".join(chunks)


def main() -> None:
    terms = [
        "fare",
        "tariff",
        "revenue",
        "passenger",
        "city",
        "market",
        "load factor",
        "available seat",
        "distance",
        "kilometre",
        "capacity",
    ]
    for arg in sys.argv[1:]:
        path = Path(arg)
        text = extract_strings(path)
        print(f"FILE {path}")
        print(f"EXTRACTED_CHARS {len(text)}")
        lower = text.lower()
        for term in terms:
            idx = lower.find(term)
            if idx == -1:
                print(f"TERM {term}: NOT_FOUND")
            else:
                snippet = text[max(0, idx - 220) : idx + 520]
                print(f"TERM {term}: {snippet}")
        print("---")


if __name__ == "__main__":
    main()
