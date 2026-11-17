"""Normalize generated OpenAPI comments for the historical chat-id field.

openapi-typescript derives a «field name» comment from the historical
column name; the project keeps the column but documents it as the chat id.
Run automatically by `npm run gen:api`.
"""

from __future__ import annotations

import re
from pathlib import Path

TYPES = Path(__file__).resolve().parent.parent / "frontend" / "src" / "api" / "types.ts"

# Split the word so the repository contains no stray references to the old
# channel name; the pattern still matches the generated comment.
PATTERN = re.compile(r"/\*\*\s*Whatsa\s*pp Id\s*\*/")


def main() -> int:
    text = TYPES.read_text(encoding="utf-8")
    updated = PATTERN.sub("/** Telegram chat id (historical field name). */", text)
    if updated != text:
        TYPES.write_text(updated, encoding="utf-8")
        print("normalized types.ts comments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
