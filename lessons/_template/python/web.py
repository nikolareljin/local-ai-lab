"""Lesson web GUI stub — the shared, L1-style "experiment locally" interface.

Copy this into a new lesson and fill in the three things a lesson actually owns:
its tunable PARAMS, a few EXAMPLES, and a `search(query, values)` that runs the
lesson's own compute and returns rankings + a "why" breakdown. Everything else
(the dark page, the live sliders, the wiring) comes from tools/lesson_web.py, so
every lesson's GUI looks and behaves the same — like Lesson 1's.

Launch it with:  ./run -l N web        (or make it the default: defaultAction:"web")
"""

import sys
from pathlib import Path

# Reach the shared scaffold under tools/ (this file runs with cwd = the lesson dir,
# so resolve the repo root from the file path, not the working directory).
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from lesson_web import serve  # noqa: E402  (sys.path set up above)

# Tunable knobs shown as live controls. kind="range" → slider (min/max/step),
# kind="toggle" → checkbox. `default` should match the lesson's own constants so
# the GUI opens on the exact behaviour your demo/test pin.
PARAMS = [
    {"name": "example_knob", "label": "Example knob", "kind": "range",
     "min": 0, "max": 10, "step": 1, "default": 5},
]

# One-click example queries (label shown on the chip, query typed into the box).
EXAMPLES = [
    {"label": "An example query", "query": "replace me"},
]


def search(query, values):
    """Run the lesson's compute for `query` with the tuned `values`, and return:
        {"arms":   [{"label": str, "ranking": [str, ...]}, ...],
         "blocks": [ ...breakdown blocks... ]}   # see tools/lesson_web.py for block kinds
    """
    if not query:
        return {"arms": [], "blocks": [{"kind": "note", "text": "Type a query above."}]}
    # TODO: call your lesson's functions here using values["example_knob"], etc.
    return {
        "arms": [{"label": "Results", "ranking": [f"you searched for: {query}"]}],
        "blocks": [{"kind": "note", "text": "Replace search() with your lesson's compute."}],
    }


def main():
    serve(
        title="Lesson N · TITLE",
        subtitle="One line on what the user is experimenting with.",
        hint="A short tip on what to try.",
        params=PARAMS,
        examples=EXAMPLES,
        search=search,
    )


if __name__ == "__main__":
    main()
