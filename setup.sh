#!/usr/bin/env bash
# local-ai-lab - get the course onto this machine and ready to run. Linux and macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.sh | bash
#
# or, to read it first (recommended for any script from the internet):
#
#   curl -fsSLO https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.sh
#   less setup.sh && bash setup.sh
#
# What it does, in order:
#   1. checks the tools the course needs and says how to get the missing ones
#   2. clones the repository (skipped when run inside a clone)
#   3. creates the Python virtualenv and installs requirements.txt into it
#   4. pulls the local model the lessons use, if Ollama is installed
#   5. prints what is ready and what to run next
#
# What it never does: run sudo on its own, or pipe another installer from the internet
# into a shell. With --with-system-packages it asks your package manager (apt, dnf,
# pacman, brew) for git and Python, and nothing else.
#
# Options (after `bash -s --` when piping):
#   --dir PATH                where to clone (default: ./local-ai-lab)
#   --ref TAG                 check out a release tag instead of main
#   --with-system-packages    install git and Python with the system package manager
#   --models none|small|all   Ollama models to pull: small = qwen3:1.7b (default), all adds qwen3.5:4b
#   --dry-run                 print what would be done, do nothing
#   -h, --help                this text
set -euo pipefail

REPO_URL="${LOCAL_AI_LAB_REPO:-https://github.com/nikolareljin/local-ai-lab.git}"
DIR="local-ai-lab"
REF=""
SYSTEM_PACKAGES=0
MODELS="small"
DRY_RUN=0
SMALL_MODEL="qwen3:1.7b"   # the simulated Jev and the LLM arm of Lesson 10; tools in Lesson 9
BIG_MODEL="qwen3.5:4b"     # optional: the better, slower simulated Jev

say()  { printf '%s\n' "$*"; }
info() { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] %s\n' "$*" >&2; }
die()  { warn "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# Run a command, or only print it under --dry-run.
run()  { if [[ $DRY_RUN -eq 1 ]]; then say "  would run: $*"; else "$@"; fi; }

# A heredoc, not "read my own comments": when piped from curl there is no file to read.
usage() {
  cat <<'USAGE'
local-ai-lab setup - clone the course and get it ready to run (Linux, macOS).

  curl -fsSL https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.sh | bash
  curl -fsSL https://raw.githubusercontent.com/nikolareljin/local-ai-lab/main/setup.sh | bash -s -- --models all

Options:
  --dir PATH                where to clone (default: ./local-ai-lab)
  --ref TAG                 check out a release tag instead of main
  --with-system-packages    install git and Python with the system package manager
  --models none|small|all   Ollama models to pull: small = qwen3:1.7b (default), all adds qwen3.5:4b
  --dry-run                 print what would be done, do nothing
  -h, --help                this text

It never runs sudo unless you pass --with-system-packages, and never pipes another
installer from the internet into a shell.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)    [[ $# -ge 2 ]] || die "--dir needs a path"; DIR="$2"; shift 2 ;;
    --ref)    [[ $# -ge 2 ]] || die "--ref needs a tag"; REF="$2"; shift 2 ;;
    --models) [[ $# -ge 2 ]] || die "--models needs none, small or all"; MODELS="$2"; shift 2 ;;
    --with-system-packages) SYSTEM_PACKAGES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done
case "$MODELS" in none|small|all) ;; *) die "--models must be none, small or all" ;; esac

# --------------------------------------------------------------------------- 1. tools
# Python 3.10+ that can also build a virtualenv. Debian and Ubuntu ship python3 without
# the venv module (it is the python3-venv package), and step 3 would fail halfway.
python_ok() {
  local py
  for py in python3 python; do
    if have "$py" && "$py" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$py"; return 0
    fi
  done
  return 1
}

install_system_packages() {
  # Only the distribution's own, signed packages - and only git and Python.
  if have apt-get; then   run sudo apt-get update && run sudo apt-get install -y git python3 python3-venv python3-pip
  elif have dnf; then     run sudo dnf install -y git python3 python3-pip
  elif have pacman; then  run sudo pacman -S --needed --noconfirm git python python-pip
  elif have brew; then    run brew install git python
  else die "no supported package manager found (apt, dnf, pacman, brew); install git and Python 3.10+ by hand"
  fi
}

PYTHON=""
if ! have git || ! python_ok; then
  if [[ $SYSTEM_PACKAGES -eq 1 ]]; then
    info "installing git and Python with the system package manager"
    install_system_packages
    [[ $DRY_RUN -eq 1 ]] || { have git && python_ok; } || die "git or Python 3.10+ is still missing after the install"
  else
    have git  || warn "git is missing."
    python_ok || warn "Python 3.10 or newer, with its venv module, is missing."
    warn "Install them, or run again with --with-system-packages:"
    warn "  Debian/Ubuntu: sudo apt-get install -y git python3 python3-venv python3-pip"
    warn "  Fedora:        sudo dnf install -y git python3 python3-pip"
    warn "  Arch:          sudo pacman -S --needed git python python-pip"
    warn "  macOS:         brew install git python"
    warn "On Ubuntu or Debian, distrodeck (https://github.com/nikolareljin/distrodeck) or NikOS"
    warn "(https://github.com/nikolareljin/nikos) set up a whole local-AI workstation in one go."
    [[ $DRY_RUN -eq 1 ]] || exit 1
  fi
fi
[[ -n "$PYTHON" ]] || PYTHON="python3"

# --------------------------------------------------------------------------- 2. the repository
if git rev-parse --show-toplevel >/dev/null 2>&1 && [[ -f "$(git rev-parse --show-toplevel)/run" ]] \
   && [[ -d "$(git rev-parse --show-toplevel)/lessons" ]]; then
  ROOT="$(git rev-parse --show-toplevel)"
  info "using the clone at $ROOT"
elif [[ -d "$DIR/.git" ]]; then
  ROOT="$(cd "$DIR" && pwd)"
  info "using the existing clone at $ROOT"
else
  info "cloning $REPO_URL into $DIR"
  run git clone --recurse-submodules "$REPO_URL" "$DIR"
  ROOT="$(cd "$DIR" 2>/dev/null && pwd || printf '%s' "$DIR")"
fi
if [[ -n "$REF" ]]; then
  info "checking out $REF"
  run git -C "$ROOT" checkout --quiet "$REF"
fi
# The run script reads helper functions from a submodule; make sure it is there.
run git -C "$ROOT" submodule update --init --recursive --quiet

# --------------------------------------------------------------------------- 3. Python environment
if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  info "creating the virtualenv at $ROOT/venv"
  run "$PYTHON" -m venv "$ROOT/venv"
fi
info "installing the course's Python packages into the virtualenv"
run "$ROOT/venv/bin/python" -m pip install --quiet --upgrade pip
run "$ROOT/venv/bin/python" -m pip install --quiet -r "$ROOT/requirements.txt"

# --------------------------------------------------------------------------- 4. local models
# Why a model at all: Lesson 10's "simulated Jev" and its LLM arm are a small local model
# answering through Ollama, and Lesson 9's tool calls use the same one. The demos replay
# recordings and need no model; the live commands do.
OLLAMA_NOTE=""
if [[ "$MODELS" == "none" ]]; then
  OLLAMA_NOTE="skipped (--models none)"
elif ! have ollama; then
  OLLAMA_NOTE="Ollama is not installed: get it from https://ollama.com/download, then: ollama pull $SMALL_MODEL"
else
  info "pulling $SMALL_MODEL (1.4 GB) for the live lessons"
  if run ollama pull "$SMALL_MODEL"; then OLLAMA_NOTE="$SMALL_MODEL ready"; else
    OLLAMA_NOTE="could not pull $SMALL_MODEL - is Ollama running? start it, then: ollama pull $SMALL_MODEL"
  fi
  if [[ "$MODELS" == "all" ]]; then
    info "pulling $BIG_MODEL (3.4 GB)"
    run ollama pull "$BIG_MODEL" || warn "could not pull $BIG_MODEL"
  fi
fi

# --------------------------------------------------------------------------- 5. summary
row() { printf '  %-4s%-26s%s\n' "$1" "$2" "$3"; }
say
if [[ $DRY_RUN -eq 1 ]]; then
  say "Dry run: nothing was changed. A real run would leave:"
else
  say "local-ai-lab is set up in $ROOT"
fi
say
row yes "repository"  "$ROOT"
row yes "Python packages" "in $ROOT/venv"
if [[ "$OLLAMA_NOTE" == *ready ]]; then row yes "local model" "$OLLAMA_NOTE"; else row "--" "local model" "$OLLAMA_NOTE"; fi
if have node;   then row yes "Node.js (--lang node)" "found";   else row "--" "Node.js (--lang node)" "optional: https://nodejs.org (22 or newer)"; fi
if have dotnet; then row yes ".NET 8 (--lang csharp)" "found"; else row "--" ".NET 8 (--lang csharp)" "optional: https://dotnet.microsoft.com/download"; fi
if [[ -n "${TYPESAFE_API_KEY:-}" ]]; then row yes "TypeSafe key (Lesson 10)" "set"; else
  row "--" "TypeSafe key (Lesson 10)" "optional, for one real Jev call: https://console.typesafe.ai/keys"; fi
say
say "Next:"
say "  cd $ROOT"
say "  ./run -l 1            # Lesson 1: the RAG web UI"
say "  ./run -l 10 check     # Lesson 10: is this machine ready for the live parts?"
say "  ./run -l 10 demo      # Lesson 10: the recorded scorecard, no model needed"
