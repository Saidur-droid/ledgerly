"""Fail CI when Ask Ledgerly bypasses its validated response boundary."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).parents[2]
FRONTEND = ROOT / "frontend" / "src"
FORBIDDEN = {
    r"\bString\s*\(\s*response\s*\)": "implicit String(response)",
    r"`[^`]*\$\{\s*response\s*\}[^`]*`": "response template interpolation",
    r"\bresponse\.answer\b": "legacy unvalidated answer access",
    r"\bChatResponseContent\b": "legacy ad-hoc response renderer",
    r'role:\s*"assistant";\s*content:\s*unknown': "unknown assistant JSX content",
}


def main() -> int:
    failures: list[str] = []
    files = sorted(FRONTEND.rglob("*.ts")) + sorted(FRONTEND.rglob("*.tsx"))
    for path in files:
        content = path.read_text(encoding="utf-8")
        for pattern, description in FORBIDDEN.items():
            if re.search(pattern, content, re.DOTALL):
                failures.append(f"{path.relative_to(ROOT)}: {description}")

    api = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")
    required_api_patterns = {
        "request<unknown>(\"/api/v1/chat\"": "chat response must enter as unknown",
        "parseAskLedgerlyResponse(payload)": "chat payload must be runtime validated",
    }
    for pattern, description in required_api_patterns.items():
        if pattern not in api:
            failures.append(f"frontend/src/lib/api.ts: missing {description}")

    renderer = (FRONTEND / "components" / "chat-response.tsx").read_text(
        encoding="utf-8"
    )
    for required in (
        "AskLedgerlyResponseRenderer",
        "assertNever",
        "switch (response.type)",
        "switch (section.type)",
    ):
        if required not in renderer:
            failures.append(f"frontend/src/components/chat-response.tsx: missing {required}")

    if failures:
        print("Unsafe Ask Ledgerly response patterns found:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Ask Ledgerly contract boundary static check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
