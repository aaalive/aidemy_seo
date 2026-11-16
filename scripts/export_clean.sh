#!/usr/bin/env bash
# Build a clean copy of the committed tree (HEAD) for sandboxed AI evaluations:
# no .git, no agent/workflow files, no real channel handles. Your repo is not changed.
# Usage: scripts/export_clean.sh [out.zip]   (default: dist/aidemy_seo_clean.zip)
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-dist/aidemy_seo_clean.zip}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
git archive --format=tar --prefix=aidemy_seo/ HEAD | tar -x -C "$tmp"
r="$tmp/aidemy_seo"
rm -rf "$r/.claude" "$r/CLAUDE.md" "$r/.github" "$r/.githooks" "$r/scripts/export_clean.sh"
cat > "$r/examples/channels_de_school.txt" <<'TXT'
# Channels to compare with (one handle, channel id or URL per line).
# Placeholders - replace with real channels before running `aidemy-seo channels`.
@example_channel_one
@example_channel_two
@example_channel_three
TXT
python3 - "$r" <<'PY'
import re, sys, pathlib
r = pathlib.Path(sys.argv[1])
readme = r / "README.md"
lines = [l for l in readme.read_text().splitlines()
         if not re.search(r"CLAUDE\.md|\.claude/|\.githooks|\.github/workflows|git init", l)]
readme.write_text("\n".join(lines) + "\n")
contrib = r / "CONTRIBUTING.md"
text = contrib.read_text()
text = re.sub(r"\n[^\n]*\.githooks[^\n]*", "", text)
text = re.sub(r"\nAgents: read `CLAUDE\.md` first;[^\n]*\n[^\n]*\n", "\n", text)
contrib.write_text(text)
v = r / "scripts" / "verify.sh"
v.write_text(v.read_text().replace(
    "# the Claude Code hooks (.claude/settings.json) and GitHub Actions. Green = done.",
    "# CI. Green = done."))
s = r / "specs" / "README.md"
s.write_text(s.read_text().replace(
    " (see `.claude/skills/spec-first-feature`)", ""))
PY
left="$(grep -rIlE 'CLAUDE\.md|\.claude/|\.githooks|git init' "$r" || true)"
[ -z "$left" ] || { echo "export: still references removed files: $left" >&2; exit 1; }
# Upload hygiene (2026-11-16: a task was rejected for __pycache__, *.egg-info and dist/ in the
# upload). git archive only exports tracked files, so none should be here - this proves it.
bad="$(cd "$tmp" && find aidemy_seo \( -name __pycache__ -o -name '*.egg-info' -o -name '*.pyc' -o -name .git \
      -o -name .venv -o -name venv -o -name dist -o -name build -o -name .coverage -o -name htmlcov \
      -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name mutants -o -name .DS_Store \
      -o -name .env \) -print)"
[ -z "$bad" ] || { echo "export: build/cache output in the export: $bad" >&2; exit 1; }
[ -f "$r/.gitignore" ] || { echo "export: .gitignore missing" >&2; exit 1; }
mkdir -p "$(dirname "$out")"; rm -f "$out"
python3 - "$tmp" "$PWD/$out" <<'PY'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:   # keeps file modes (verify.sh stays executable)
    for d, _, files in os.walk(os.path.join(root, "aidemy_seo")):
        for f in sorted(files):
            full = os.path.join(d, f)
            info = zipfile.ZipInfo.from_file(full, os.path.relpath(full, root))
            with open(full, "rb") as fh:
                z.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
PY
echo "export: $out ($(cd "$tmp" && find aidemy_seo -type f | wc -l) files)"
