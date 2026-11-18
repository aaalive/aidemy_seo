#!/usr/bin/env bash
# Clean copy of the committed tree (HEAD) for sandboxed AI evaluations (Taiga).
#   scripts/export_clean.sh [out.zip]          build dist/aidemy_seo_clean.zip and audit it (no test run)
#   scripts/export_clean.sh --verify [out.zip] also install the copy in a temp venv and run verify.sh
# scripts/verify.sh itself is always in the zip.
#   scripts/export_clean.sh --check <zip|dir>  audit ANY zip or folder (e.g. one zipped by hand)
# The audit fails (exit 1) on: .git, agent/IDE files, build/cache output, .env, real channel
# handles, secrets or emails, references to removed files, a missing .gitignore, verify.sh not
# executable. Your repo is never changed.
set -euo pipefail
cd "$(dirname "$0")/.."
repo="$PWD"

audit() {   # $1 = folder holding the project files
python3 - "$1" <<'PY'
import os, re, stat, sys
root = sys.argv[1]
problems = []
AGENT = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", ".claude", ".cursor", ".cursorrules", ".windsurf",
         ".windsurfrules", ".aider.conf.yml", ".codex", ".continue", ".github", ".githooks", ".vscode", ".idea",
         "copilot-instructions.md"}
BUILD = {".git", "__pycache__", ".venv", "venv", "dist", "build", "htmlcov", "mutants", ".pytest_cache",
         ".mypy_cache", ".ruff_cache", ".coverage", ".DS_Store", ".env", "node_modules"}
SECRET = re.compile(r"AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}"
                    r"|xox[bp]-[A-Za-z0-9-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY|ya29\.[0-9A-Za-z_-]{20,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}")
OK_EMAIL = re.compile(r"@(example\.(com|org)|anthropic\.com)$|^noreply@|^user@example")
REAL_HANDLES = re.compile(r"@(sofatutor|MathebyDanielJung|Lehrerschmidt|MrWissen2go|musstewissen\w*|TheSimple\w+)\b", re.I)
REFS = re.compile(r"CLAUDE\.md|\.claude/|\.githooks|git init")
for d, dirs, files in os.walk(root):
    rel = os.path.relpath(d, root)
    for n in list(dirs) + files:
        p = os.path.normpath(os.path.join(rel, n))
        if n in AGENT:
            problems.append(f"agent/IDE file: {p}")
        if n in BUILD or n.endswith((".egg-info", ".pyc")):
            problems.append(f"build/cache/secret file: {p}")
    dirs[:] = [x for x in dirs if x not in AGENT and x not in BUILD and not x.endswith(".egg-info")]
    for n in files:
        full, p = os.path.join(d, n), os.path.normpath(os.path.join(rel, n))
        try:
            text = open(full, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET.search(text):
            problems.append(f"looks like a secret/key: {p}")
        for e in set(EMAIL.findall(text)):
            if not OK_EMAIL.search(e) and not e.startswith("@"):
                problems.append(f"email address in {p}: {e}")
        if p.startswith("examples") and REAL_HANDLES.search(text):
            problems.append(f"real channel handles in {p}")
        if REFS.search(text) and p != os.path.normpath("scripts/export_clean.sh"):
            problems.append(f"references a removed file or git init: {p}")
if not os.path.isfile(os.path.join(root, ".gitignore")):
    problems.append(".gitignore missing")
v = os.path.join(root, "scripts", "verify.sh")
if os.path.isfile(v) and not os.stat(v).st_mode & stat.S_IXUSR:
    problems.append("scripts/verify.sh is not executable (use `bash scripts/verify.sh` or chmod +x)")
if os.path.exists(os.path.join(root, "scripts", "export_clean.sh")):
    problems.append("scripts/export_clean.sh is in the upload (repo tooling, not part of the task)")
for x in sorted(set(problems)):
    print("  FAIL", x)
n = sum(len(f) for _, _, f in os.walk(root))
print(("audit: CLEAN" if not problems else f"audit: {len(set(problems))} problem(s)") + f" ({n} files)")
sys.exit(1 if problems else 0)
PY
}

unpack() {  # $1 zip or folder -> prints the project folder
  if [ -d "$1" ]; then echo "$1"; return; fi
  local t; t="$(mktemp -d)"
  python3 - "$1" "$t" <<'UNZIP'
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:   # restore file modes, like a real unzip
    for i in z.infolist():
        z.extract(i, sys.argv[2])
        mode = i.external_attr >> 16
        if mode and not i.is_dir():
            os.chmod(os.path.join(sys.argv[2], i.filename), mode & 0o777)
UNZIP
  local top; top="$(find "$t" -mindepth 1 -maxdepth 1)"
  if [ "$(echo "$top" | wc -l)" -eq 1 ] && [ -d "$top" ]; then echo "$top"; else echo "$t"; fi
}

if [ "${1:-}" = "--check" ]; then
  [ -n "${2:-}" ] || { echo "usage: scripts/export_clean.sh --check <zip|dir>" >&2; exit 2; }
  audit "$(unpack "$2")"; exit $?
fi
verify=0; [ "${1:-}" = "--verify" ] && { verify=1; shift; }
out="${1:-dist/aidemy_seo_clean.zip}"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "export: WARNING - uncommitted changes are NOT in the zip (it exports HEAD $(git rev-parse --short HEAD)):"
  git status --short --untracked-files=no | sed 's/^/  /'
fi
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
         if not re.search(r"CLAUDE\.md|\.claude/|\.githooks|\.github/workflows|git init|export_clean", l)]
readme.write_text("\n".join(lines) + "\n")
contrib = r / "CONTRIBUTING.md"
text = contrib.read_text()
text = re.sub(r"\n[^\n]*\.githooks[^\n]*", "", text)
text = re.sub(r"\nAgents: read `CLAUDE\.md` first;[^\n]*\n[^\n]*\n", "\n", text)
contrib.write_text(text)
v = r / "scripts" / "verify.sh"
v.write_text(v.read_text().replace(
    "# the Claude Code hooks (.claude/settings.json) and GitHub Actions. Green = done.", "# CI. Green = done."))
s = r / "specs" / "README.md"
s.write_text(s.read_text().replace(" (see `.claude/skills/spec-first-feature`)", ""))
PY
chmod +x "$r/scripts/verify.sh"
audit "$r" || { echo "export: refused - fix the problems above" >&2; exit 1; }
if [ "$verify" = 1 ]; then
  echo "export: installing the copy in a temp venv and running verify.sh ..."
  python3 -m venv "$tmp/venv" && "$tmp/venv/bin/pip" install -q -e "$r[dev]" >/dev/null 2>&1 \
    || { echo "export: refused - pip install -e '.[dev]' fails on the clean copy" >&2; exit 1; }
  if ! (cd "$r" && PATH="$tmp/venv/bin:$PATH" bash scripts/verify.sh >"$tmp/verify.log" 2>&1); then
    tail -20 "$tmp/verify.log" >&2; echo "export: refused - verify.sh fails on the clean copy" >&2; exit 1
  fi
  tail -1 "$tmp/verify.log"
  rm -rf "$r"/src/*.egg-info "$r/.coverage" "$r/.pytest_cache" "$r/.mypy_cache" "$r/.ruff_cache"
  find "$r" -name __pycache__ -prune -exec rm -rf {} +
  audit "$r" >/dev/null || { echo "export: verify left build output behind" >&2; exit 1; }
fi
case "$out" in /*) dest="$out" ;; *) dest="$repo/$out" ;; esac
mkdir -p "$(dirname "$dest")"; rm -f "$dest"
python3 - "$tmp" "$dest" <<'PY'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:   # keeps file modes (verify.sh stays executable)
    for d, _, files in os.walk(os.path.join(root, "aidemy_seo")):
        for f in sorted(files):
            full = os.path.join(d, f)
            z.write(full, os.path.relpath(full, root))
PY
echo "export: $out ready - upload its unzipped files with Mount files in turn 1"
