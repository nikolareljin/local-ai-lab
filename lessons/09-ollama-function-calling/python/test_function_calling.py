"""Lesson 9 - offline tests. No Ollama, no network, no API key.

Every claim the lesson makes about the loop and its guards is pinned here, and
the demo's committed output is diffed byte for byte.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cassette  # noqa: E402
import function_calling as fc  # noqa: E402
import guards  # noqa: E402
import router  # noqa: E402
import tool_loop  # noqa: E402
from lesson_core import CASSETTE_DIR, load_tasks  # noqa: E402

from tools import Toolbox, calculate  # noqa: E402

LESSON = HERE.parent


@pytest.fixture(scope="module")
def box_factory():
    shared = Toolbox().retriever
    return lambda: Toolbox(retriever=shared)


class Scripted:
    """A model that replies from a fixed list, and counts how often it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        reply = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        if isinstance(reply, str):
            return {"message": {"role": "assistant", "content": reply}, "seconds": 0.0}
        return {"message": {"role": "assistant", "content": "", "tool_calls": reply},
                "seconds": 0.0}


def call(name, **args):
    return [{"function": {"name": name, "arguments": args}}]


# --- the calculator ------------------------------------------------------------------


@pytest.mark.parametrize("expr,want", [
    ("2340 * 0.175", "409.5"),
    ("(14 * 30) / 7", "60"),
    ("2^10", "1024"),
    ("1,000 + 1", "1001"),
])
def test_calculator_does_arithmetic(expr, want):
    assert calculate(expr).endswith(f"= {want}")


@pytest.mark.parametrize("expr", [
    "__import__('os').system('true')",
    "open('/etc/passwd')",
    "(9**64)**64",
    "1/0",
    "x + 1",
    "1e308 * 10",
])
def test_calculator_refuses_anything_but_arithmetic(expr):
    assert calculate(expr).startswith("error:")


# --- schema validation -------------------------------------------------------------------


def test_validator_accepts_a_valid_ticket(box_factory):
    schema = box_factory().get("create_ticket").parameters
    assert guards.validate(schema, {"title": "Ring amber", "severity": "high"}) == []


@pytest.mark.parametrize("args,fragment", [
    ({"title": "x"}, "severity is required"),
    ({"title": "x", "severity": "critical"}, "must be one of"),
    ({"title": 7, "severity": "low"}, "must be string"),
    ({"title": "x", "severity": "low", "owner": "me"}, "not a parameter"),
    ({"title": "x" * 121, "severity": "low"}, "longer than 120"),
    ("not an object", "must be object"),
])
def test_validator_names_what_is_wrong(box_factory, args, fragment):
    schema = box_factory().get("create_ticket").parameters
    assert any(fragment in e for e in guards.validate(schema, args))


def test_validator_rejects_bools_as_integers(box_factory):
    schema = box_factory().get("search_docs").parameters
    assert guards.validate(schema, {"query": "x", "k": True})
    assert guards.validate(schema, {"query": "x", "k": 99})


def test_string_arguments_are_parsed_before_validation():
    assert guards.coerce_arguments('{"query": "amber"}') == {"query": "amber"}
    assert guards.coerce_arguments(None) == {}


# --- the loop --------------------------------------------------------------------------


def test_a_tool_result_goes_back_to_the_model_as_a_tool_message(box_factory):
    model = Scripted(call("calculator", expression="2340 * 0.175"), "It is 409.5.")
    r = tool_loop.run(model, "What is 17.5% of 2340?", box_factory())
    assert r["answer"] == "It is 409.5." and r["turns"] == 2
    tool_msg = r["messages"][3]
    assert tool_msg["role"] == "tool" and tool_msg["tool_name"] == "calculator"
    assert tool_msg["content"].endswith("= 409.5")


def test_search_docs_output_carries_citations(box_factory):
    out = box_factory().search_docs("status ring amber")
    assert "[faq.md:1]" in out
    # The poisoned ticket outranks the FAQ on an innocent question. That is why
    # every tool result is screened, not only the ones that look suspicious.
    assert out.startswith("[ticket_9001.md:1]")
    assert guards.screen_output(out)


def test_max_turns_caps_a_model_that_never_stops(box_factory):
    model = Scripted(*[call("search_docs", query=f"try {i}") for i in range(20)])
    r = tool_loop.run(model, "q", box_factory(), max_turns=3)
    assert r["stopped"] == "max turns" and model.calls == 3 and r["answer"] is None


def test_repeated_identical_calls_are_stopped(box_factory):
    model = Scripted(call("search_docs", query="amber"))  # the same call, forever
    r = tool_loop.run(model, "q", box_factory(), max_turns=10)
    assert r["stopped"] == "repeating itself"
    assert [c["status"] for c in r["calls"]] == ["ok", "repeat", "repeat"]
    assert model.calls == 3


def test_unknown_tool_is_reported_to_the_model_not_run(box_factory):
    model = Scripted(call("reboot_device", unit=7), "I cannot reboot devices.")
    r = tool_loop.run(model, "Reboot unit 7", box_factory())
    assert r["calls"][0]["status"] == "unknown tool"
    assert "Available: search_docs" in r["messages"][3]["content"]
    assert r["answer"] == "I cannot reboot devices."


def test_invalid_args_let_the_model_retry(box_factory):
    box = box_factory()
    model = Scripted(call("create_ticket", title="Amber ring", severity="critical"),
                     call("create_ticket", title="Amber ring", severity="high"), "Done.")
    r = tool_loop.run(model, "Open a ticket please", box, confirm=lambda n, a: True)
    assert [c["status"] for c in r["calls"]] == ["invalid args", "ok"]
    assert box.outbox == [{"id": "T-1001", "title": "Amber ring", "severity": "high"}]


@pytest.mark.parametrize("question,allowed", [
    ("Please open a support ticket: ring amber. Severity high.", True),
    ("Can you file a ticket for this?", True),
    ("Summarize support ticket 9001.", False),  # mentions a ticket, asks for none
    ("Why is the ring amber?", False),
])
def test_side_effect_needs_the_user_to_have_asked(box_factory, question, allowed):
    box = box_factory()
    model = Scripted(call("create_ticket", title="x", severity="low"), "ok")
    r = tool_loop.run(model, question, box, confirm=lambda n, a: True)
    assert (r["calls"][0]["status"] == "ok") is allowed
    assert len(box.outbox) == int(allowed)


def test_side_effect_needs_confirmation(box_factory):
    box = box_factory()
    asked = []
    model = Scripted(call("create_ticket", title="x", severity="low"), "ok")
    r = tool_loop.run(model, "Open a ticket", box, confirm=lambda n, a: asked.append(n) or False)
    assert asked == ["create_ticket"] and r["calls"][0]["status"] == "declined"
    assert box.outbox == []
    r2 = tool_loop.run(Scripted(call("create_ticket", title="x", severity="low"), "ok"),
                       "Open a ticket", box)  # no confirm callback at all
    assert r2["calls"][0]["status"] == "declined"


def test_injected_tool_output_is_flagged_and_obeying_it_is_blocked(box_factory):
    box = box_factory()
    r = tool_loop.run(router.ObedientStandIn(), "Summarize support ticket 9001.", box,
                      confirm=lambda n, a: True)
    first, second = r["calls"][0], r["calls"][1]
    assert "instruction override" in first["flags"] and "role injection" in first["flags"]
    assert first["result"].startswith("[WARNING")
    assert second["name"] == "create_ticket" and second["status"] == "not requested"
    assert box.outbox == []


def test_guards_off_runs_whatever_the_model_sends(box_factory):
    box = box_factory()
    r = tool_loop.run(Scripted(call("create_ticket", title="x", severity="critical"), "ok"),
                      "Why is the ring amber?", box, guarded=False)
    assert r["calls"][0]["status"] == "ok" and box.outbox[0]["severity"] == "critical"
    r2 = tool_loop.run(Scripted(call("reboot_device"), "ok"), "q", box_factory(), guarded=False)
    assert r2["calls"][0]["status"] == "crashed: KeyError"


# --- calls written as text ------------------------------------------------------------------


TEXT_CALL = '{"name": "calculator", "arguments": {"expression": "2340 * 0.175"}}'


@pytest.mark.parametrize("content", [
    TEXT_CALL,
    f"```json\n{TEXT_CALL}\n```",
    f"<tool_call>\n{TEXT_CALL}\n</tool_call>",
])
def test_text_calls_are_recovered_in_every_common_wrapping(content):
    calls = guards.recover_text_calls(content, ["calculator"])
    assert calls[0]["function"]["arguments"] == {"expression": "2340 * 0.175"}


def test_text_calls_are_ignored_unless_lenient(box_factory):
    strict = tool_loop.run(Scripted(TEXT_CALL, "409.5"), "What is 17.5% of 2340?", box_factory())
    assert strict["calls"] == [] and strict["answer"] == TEXT_CALL
    lenient = tool_loop.run(Scripted(TEXT_CALL, "409.5"), "What is 17.5% of 2340?",
                            box_factory(), lenient=True)
    assert lenient["calls"][0]["recovered"] and lenient["answer"] == "409.5"


def test_recovery_only_accepts_offered_tool_names():
    assert guards.recover_text_calls('{"name": "rm_rf", "arguments": {}}', ["calculator"]) == []


# --- cassettes, the router, the score ----------------------------------------------------


def test_replay_refuses_a_conversation_it_was_not_recorded_against(box_factory):
    rec = cassette.Recorder(Scripted(call("calculator", expression="1+1"), "2"))
    rec.model = "scripted"
    tool_loop.run(rec, "What is 1+1?", box_factory())
    ok = tool_loop.run(cassette.Replay(rec.turns), "What is 1+1?", box_factory())
    assert ok["answer"] == "2"
    with pytest.raises(cassette.CassetteDrift):
        tool_loop.run(cassette.Replay(rec.turns), "What is 2+2?", box_factory())


def test_the_router_is_right_where_its_rules_reach():
    assert router.route("What is 17.5% of 2340?") == ["calculator"]
    assert router.route("Why does the status ring stay amber?") == ["search_docs"]
    assert router.route("Please open a support ticket: severity high") == ["create_ticket"]


def test_score_never_sees_expect_until_after_the_run():
    import inspect

    assert "task" not in inspect.signature(tool_loop.run).parameters
    assert "expect" not in inspect.getsource(tool_loop)
    assert "expect" not in inspect.getsource(guards)


def test_every_task_has_a_why():
    assert all(t["why"] and t["ask"] for t in load_tasks()["tasks"])


# --- the committed demo -------------------------------------------------------------------


needs_cassettes = pytest.mark.skipif(not any(CASSETTE_DIR.glob("*.json")),
                                     reason="no cassettes recorded")


@needs_cassettes
def test_every_cassette_replays_against_todays_code(box_factory):
    tasks = load_tasks()["tasks"]
    for tape in fc.recorded_models():
        fc.replay_all(tape, tasks, box_factory().retriever, max_turns=5)


@needs_cassettes
def test_demo_output_matches_the_committed_file():
    out = subprocess.run([sys.executable, str(HERE / "function_calling.py"), "demo"],
                         capture_output=True, text=True, cwd=LESSON, check=True).stdout
    assert out == (LESSON / "expected-output.txt").read_text(encoding="utf-8")
