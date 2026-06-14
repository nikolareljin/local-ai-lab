#!/usr/bin/env bash
# Reorder lessons by renaming their NN- directory prefix — the number lives only
# in the directory name, so this is all it takes.
#
# Usage:
#   tools/renumber-lessons.sh swap <A> <B>     # swap two lessons' numbers
#   tools/renumber-lessons.sh move <FROM> <TO> # move a lesson to a free number
#
# Uses `git mv` so the change is tracked, then refreshes lessons/CURRICULUM.md.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

# Echo the lesson dir for a number, or nothing. Avoids `ls | head`, which fails
# under `set -euo pipefail` when no directory matches.
dir_for() {
  local n d; n="$(printf '%02d' "$1")"
  for d in "lessons/${n}-"*/; do
    [[ -d "$d" ]] && { printf '%s\n' "${d%/}"; return 0; }
  done
  return 0
}
slug_of() { local d="$1"; d="${d#lessons/}"; echo "${d#*-}"; }

case "${1:-}" in
  swap)
    [[ $# -eq 3 ]] || { echo "usage: $0 swap <A> <B>" >&2; exit 1; }
    a="$(dir_for "$2")"; b="$(dir_for "$3")"
    [[ -n "$a" && -n "$b" ]] || { echo "both lessons must exist (got '$a' '$b')" >&2; exit 1; }
    na="$(printf '%02d' "$2")"; nb="$(printf '%02d' "$3")"
    # PID-scoped temp name so an interrupted earlier run can't collide with us.
    tmp="lessons/__tmp_renumber.$$"
    [[ -e "$tmp" ]] && { echo "temp dir $tmp already exists; aborting" >&2; exit 1; }
    git mv "$a" "$tmp"
    git mv "$b" "lessons/${na}-$(slug_of "$b")"
    git mv "$tmp" "lessons/${nb}-$(slug_of "$a")"
    echo "Swapped lessons $2 and $3."
    ;;
  move)
    [[ $# -eq 3 ]] || { echo "usage: $0 move <FROM> <TO>" >&2; exit 1; }
    a="$(dir_for "$2")"; [[ -n "$a" ]] || { echo "lesson $2 not found" >&2; exit 1; }
    [[ -z "$(dir_for "$3")" ]] || { echo "lesson $3 already exists" >&2; exit 1; }
    git mv "$a" "lessons/$(printf '%02d' "$3")-$(slug_of "$a")"
    echo "Moved lesson $2 to $3."
    ;;
  *)
    echo "usage: $0 swap <A> <B> | move <FROM> <TO>" >&2; exit 1 ;;
esac

bash "$root/tools/sync-curriculum.sh" || true
echo "Note: review cross-lesson links/nav after reordering."
