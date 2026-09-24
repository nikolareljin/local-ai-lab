"""Lesson 9 - offline tests for the four recipes in `python/recipes/`.

No model and no network: every recipe runs against its scripted stand-in, and
the network functions are replaced with ones that fail the test if called.
Each recipe gets two kinds of test: its `main()` end to end, and its tool
functions called directly, including the inputs the guards exist to refuse.
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
for path in (HERE, HERE / "recipes"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import doc_automation  # noqa: E402
import doc_summary  # noqa: E402
import doc_summary_graph  # noqa: E402
import home_automation  # noqa: E402
import invoice_extract  # noqa: E402
import pdf_index  # noqa: E402
import requests  # noqa: E402
import tool_loop  # noqa: E402
from recipe_kit import ScriptedModel, call  # noqa: E402

from localrag.extract import extract_pages  # noqa: E402

BAD = "inv-1002-harbor-lane.md"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a recipe test tried to use the network")

    monkeypatch.setattr(requests, "post", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.delenv("HASS_URL", raising=False)
    monkeypatch.delenv("HASS_TOKEN", raising=False)


def after(marker: str, text: str):
    return json.loads(text.split(marker, 1)[1])


def run_one(toolset, tool, user_text="", confirm=None, /, **args):
    return tool_loop.execute(toolset, call(tool, **args), user_text, guarded=True,
                             confirm=confirm)


# --- invoice_extract -------------------------------------------------------------------


def test_invoice_main_flags_the_bad_invoice(capsys):
    assert invoice_extract.main([]) == 0
    ledger = {r["document"]: r for r in after("ledger:", capsys.readouterr().out)}
    assert ledger[BAD]["status"] == "needs_review"
    assert (ledger[BAD]["total"], ledger[BAD]["lines_sum"]) == (1240.0, 1204.0)
    assert [r["status"] for d, r in ledger.items() if d != BAD] == ["clean", "clean"]


def good_args(desk, document):
    text = desk.read_document(document)
    return invoice_extract._parse(document, text)


def test_record_invoice_rejects_a_bad_total_once_then_files_for_review():
    desk = invoice_extract.InvoiceDesk()
    args = good_args(desk, BAD)
    first = desk.record_invoice(**args)
    assert "does not match the sum of lines 1,204.00" in first and BAD not in desk.records
    second = desk.record_invoice(**args, note="checked")
    assert "needs_review" in second and desk.records[BAD]["status"] == "needs_review"


def test_record_invoice_refuses_a_total_the_document_does_not_print():
    # "Fixing" the total to the sum would make the ledger clean and the invoice wrong.
    desk = invoice_extract.InvoiceDesk()
    result = desk.record_invoice(**{**good_args(desk, BAD), "total": 1204.0})
    assert "1,204.00 does not appear" in result and not desk.records


@pytest.mark.parametrize("date", ["09/03/2026", "2026-02-30", "2026-3-9"])
def test_record_invoice_refuses_bad_dates(date):
    desk = invoice_extract.InvoiceDesk()
    args = {**good_args(desk, "inv-1001-bluefin.md"), "invoice_date": date}
    assert desk.record_invoice(**args).startswith("error: invoice_date")


def test_record_invoice_clean_and_no_double_entry():
    desk = invoice_extract.InvoiceDesk()
    args = good_args(desk, "inv-1003-quillstone.md")
    assert desk.record_invoice(**args) == "Recorded inv-1003-quillstone.md as clean."
    assert "already recorded" in desk.record_invoice(**args)


def test_read_document_stays_in_the_inbox():
    desk = invoice_extract.InvoiceDesk()
    with pytest.raises(ValueError):
        desk.read_document("../../../../.env")
    assert run_one(desk, "read_document", name="../tasks.json")["status"] == "invalid args"


def test_record_invoice_schema_refuses_unknown_currency():
    desk = invoice_extract.InvoiceDesk()
    args = {**good_args(desk, "inv-1001-bluefin.md"), "currency": "JPY"}
    assert run_one(desk, "record_invoice", **args)["status"] == "invalid args"


# --- home_automation ------------------------------------------------------------------


def test_home_main_offline_declines_the_unlock(capsys):
    assert home_automation.main([]) == 0
    out = capsys.readouterr().out
    state = after("final state:", out)
    assert state["front_door"] == "locked" and state["thermostat_c"] == 21.0
    assert state["lights"]["kitchen"] == {"on": True, "brightness": 30}
    assert "not requested" in out and "declined" in out and "invalid args" in out


def test_home_main_yes_unlocks_only_when_asked(capsys):
    assert home_automation.main(["--yes"]) == 0
    out = capsys.readouterr().out
    assert after("final state:", out)["front_door"] == "unlocked"
    assert "not requested" in out  # the cozy run's unlock is still refused


def test_thermostat_out_of_range_is_rejected_and_state_unchanged():
    house = home_automation.House()
    before = json.dumps(house.state, sort_keys=True)
    assert run_one(house, "set_thermostat", celsius=35)["status"] == "invalid args"
    assert json.dumps(house.state, sort_keys=True) == before


@pytest.mark.parametrize("text,confirm,status", [
    ("Make the kitchen cozy.", lambda n, a: True, "not requested"),
    ("Do not unlock the door.", lambda n, a: True, "not requested"),
    ("Unlock the front door.", None, "declined"),
    ("Unlock the front door.", lambda n, a: False, "declined"),
    ("Unlock the front door.", lambda n, a: True, "ok"),
])
def test_unlock_needs_intent_and_confirmation(text, confirm, status):
    house = home_automation.House()
    assert run_one(house, "unlock_door", text, confirm)["status"] == status
    assert house.state["front_door"] == ("unlocked" if status == "ok" else "locked")


def test_set_light_off_zeroes_brightness():
    house = home_automation.House()
    house.set_light("office", True, 70)
    assert house.set_light("office", False) == "office light off."
    assert house.state["lights"]["office"] == {"on": False, "brightness": 0}


def test_home_assistant_request_shape_without_network():
    sent = []

    class Resp:
        status_code = 200

    def fake_post(url, **kw):
        sent.append((url, kw))
        return Resp()

    house = home_automation.House(hass=home_automation.HomeAssistant(
        "http://homeassistant.local:8123/", "test-token", post=fake_post))
    assert "HTTP 200" in house.set_light("kitchen", True, 30)
    house.set_light("kitchen", False)
    (url_on, kw_on), (url_off, kw_off) = sent
    assert url_on == "http://homeassistant.local:8123/api/services/light/turn_on"
    assert kw_on["json"] == {"entity_id": "light.kitchen", "brightness_pct": 30}
    assert kw_on["headers"] == {"Authorization": "Bearer test-token"}
    assert url_off.endswith("/light/turn_off") and kw_off["json"] == {"entity_id": "light.kitchen"}


def test_hass_flag_without_env_refuses(capsys):
    assert home_automation.HomeAssistant.from_env() is None
    assert home_automation.main(["--hass"]) == 2


# --- doc_automation -------------------------------------------------------------------


@pytest.fixture()
def desk(tmp_path):
    d = doc_automation.DraftDesk(out_dir=tmp_path)
    d.search_docs("what the warranty covers status ring")
    d.search_docs("how to make a warranty claim")
    return d


FIELDS = {"serial": "AX1-1", "purchase_date": "2025-11-02",
          "fault": "Ring dark, covered [warranty.md:1]", "evidence": "Export [warranty.md:1]"}


def test_doc_main_rejects_uncited_then_saves(capsys):
    assert doc_automation.main([]) == 0
    out = capsys.readouterr().out
    assert "field 'fault' has no [file:page] citation" in out
    assert "Saved rma_request-draft.md." in out and "{fault}" not in out


def test_fill_template_saves_a_fully_cited_letter(desk, tmp_path):
    assert desk.fill_template("rma_request.md", FIELDS) == "Saved rma_request-draft.md."
    text = (tmp_path / "rma_request-draft.md").read_text()
    assert "AX1-1" in text and "[warranty.md:1]" in text
    assert "{" not in text and "needs-source" not in text


@pytest.mark.parametrize("change,error", [
    ({"fault": "Ring dark."}, "has no [file:page] citation"),
    ({"evidence": "Export [made_up.md:9]"}, "which no search returned"),
    ({"serial": ""}, "must be non-empty text"),
])
def test_fill_template_refusals(desk, tmp_path, change, error):
    assert error in desk.fill_template("rma_request.md", {**FIELDS, **change})
    assert not list(tmp_path.glob("*-draft.md"))


def test_fill_template_missing_field_and_schema_enum(desk):
    fields = {k: v for k, v in FIELDS.items() if k != "evidence"}
    assert "missing fields ['evidence']" in desk.fill_template("rma_request.md", fields)
    bad = run_one(desk, "fill_template", template="../secret.md", fields=FIELDS)
    assert bad["status"] == "invalid args"
    assert desk.fill_template("../tasks.json", FIELDS).startswith("error: no template")


def test_uncited_search_cannot_be_cited(tmp_path):
    fresh = doc_automation.DraftDesk(out_dir=tmp_path)  # searched nothing yet
    assert "which no search returned" in fresh.fill_template("rma_request.md", FIELDS)


# --- pdf_index ------------------------------------------------------------------------


def test_pdf_main_answers_with_a_real_page(capsys):
    assert pdf_index.main([]) == 0
    out = capsys.readouterr().out
    assert "outside the allowed folder" in out and "[LESSON1.pdf:11]" in out
    pages = {p["page_number"]: p["text"] for p in
             extract_pages(pdf_index.PDF_ROOT / "LESSON1.pdf")}
    assert "MCP servers" in pages[11]


@pytest.fixture()
def jail(tmp_path):
    """root/ with one real PDF, plus a folder and a file symlinked out of it."""
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "sub").mkdir(parents=True)
    outside.mkdir()
    shutil.copy(pdf_index.PDF_ROOT / "LESSON10.pdf", root / "sub" / "LESSON10.pdf")
    shutil.copy(pdf_index.PDF_ROOT / "LESSON9.pdf", outside / "secret.pdf")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    (root / "sub" / "secret.pdf").symlink_to(outside / "secret.pdf")
    return pdf_index.PdfIndex(root=root), outside


@pytest.mark.parametrize("path", ["../../", "..", "sub/../../outside", "escape", "/etc"])
def test_index_folder_refuses_paths_outside_root(jail, path):
    index, _ = jail
    assert "outside the allowed folder" in index.index_folder(path)
    assert index.retriever is None


def test_index_folder_refuses_absolute_path_outside_root(jail):
    index, outside = jail
    assert "outside the allowed folder" in index.index_folder(str(outside))


def test_index_folder_skips_files_symlinked_out(jail):
    index, _ = jail
    assert index.index_folder(".").startswith("Indexed 1 PDF(s)")
    assert "secret.pdf" not in index.list_documents()
    assert index.index_folder(str(index.root / "sub")).startswith("Indexed 1 PDF(s)")


def test_pdf_tools_before_and_after_indexing():
    index = pdf_index.PdfIndex(limit=1)
    assert index.search_docs("anything").startswith("error: nothing is indexed")
    assert index.index_folder("missing").startswith("error: 'missing' is not a folder")
    assert index.index_folder(".").startswith("Indexed 1 PDF(s)")
    assert index.list_documents() == "CHEATSHEET.pdf (6 pages)"
    hits = index.search_docs("MCP tool design", 2).split("\n\n")
    pages = {p["page_number"]: p["text"] for p in
             extract_pages(pdf_index.PDF_ROOT / "CHEATSHEET.pdf")}
    for hit in hits:
        m = pdf_index._HIT.match(hit)
        page = int(m.group(1).split(":")[1].rstrip("]"))
        assert m.group(1).startswith("[CHEATSHEET.pdf:") and page in pages
        assert " ".join(m.group(2).split())[:40] in " ".join(pages[page].split())


# --- doc_summary ----------------------------------------------------------------------

WARRANTY_QUOTE = "Two years from the date of purchase against manufacturing defects."


def summary_args(**change):
    args = {"document": "warranty.md", "summary": "Two-year cover.", "audience": "customer",
            "key_points": [{"point": "Cover", "quote": WARRANTY_QUOTE}], "action_items": []}
    return {**args, **change}


def test_summary_quote_must_be_verbatim_whitespace_aside():
    desk = doc_summary.SummaryDesk()
    desk.read_document("warranty.md")
    spaced = {"point": "Cover", "quote": "Two years  from the date\nof purchase against"}
    assert desk.record_summary(**summary_args(key_points=[spaced])).startswith("Recorded")
    reworded = {"point": "Cover", "quote": "Two years from purchase against manufacturing defects."}
    result = desk.record_summary(**summary_args(key_points=[reworded]))
    assert "key point 'Cover' does not appear word for word" in result
    short = {"point": "Cover", "quote": "Two years"}
    assert "too short" in desk.record_summary(**summary_args(key_points=[short]))


def test_summary_refuses_an_unread_document():
    desk = doc_summary.SummaryDesk()
    assert "has not been read" in desk.record_summary(**summary_args())
    assert not desk.records


def test_summary_limits_and_enums():
    desk = doc_summary.SummaryDesk()
    desk.read_document("warranty.md")
    six = [{"point": str(i), "quote": WARRANTY_QUOTE} for i in range(6)]
    assert "1-5 key points, got 6" in desk.record_summary(**summary_args(key_points=six))
    assert "1-5 key points, got 0" in desk.record_summary(**summary_args(key_points=[]))
    many = ["x"] * 6
    assert "at most 5 action items" in desk.record_summary(**summary_args(action_items=many))
    for bad in (summary_args(audience="board"), summary_args(document="secret.md"),
                summary_args(summary="x" * 401)):
        assert run_one(desk, "record_summary", **bad)["status"] == "invalid args"
    with pytest.raises(ValueError):
        desk.read_document("../../../.env")


def test_doc_summary_main_records_both_and_no_refund(capsys):
    assert doc_summary.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("tool error") == 2  # each paraphrased first try was refused
    assert "== warranty.md  (for customer)" in out and "== ticket_9001.md  (for support)" in out
    assert "tries to instruct the assistant" in out


def test_doc_summary_json_parses_and_ticket_has_no_refund(capsys):
    assert doc_summary.main(["--json"]) == 0
    records = {r["document"]: r for r in json.loads(capsys.readouterr().out)}
    assert set(records) == {"warranty.md", "ticket_9001.md"}
    ticket = records["ticket_9001.md"]
    assert not any("refund" in a.lower() for a in ticket["action_items"])
    assert any("instruct" in kp["point"] for kp in ticket["key_points"])


def test_doc_summary_ticket_read_is_flagged():
    desk = doc_summary.SummaryDesk()
    step = run_one(desk, "read_document", name="ticket_9001.md")
    assert step["flags"] and step["result"].startswith("[WARNING")


# --- doc_summary_graph ----------------------------------------------------------------


@pytest.fixture()
def graph_parts(tmp_path):
    pytest.importorskip("langgraph")
    from langgraph.checkpoint.memory import MemorySaver

    def build(behaviour="first-try-fails"):
        desk = doc_summary.SummaryDesk()
        return doc_summary_graph.build_graph(desk, doc_summary_graph.standin(behaviour),
                                             tmp_path, checkpointer=MemorySaver())
    return build, tmp_path


def test_graph_happy_path_saves(graph_parts):
    build, out = graph_parts
    state = doc_summary_graph.run(build("good"), "warranty.md", ["approve"])
    assert state["status"] == "saved" and state["attempts"] == 1
    saved = json.loads((out / "warranty-summary.json").read_text())
    assert saved["document"] == "warranty.md"


def test_graph_paraphrase_retries_then_passes(graph_parts):
    build, _ = graph_parts
    state = doc_summary_graph.run(build(), "warranty.md", ["approve"])
    assert state["status"] == "saved" and state["attempts"] == 2
    assert any(line.startswith("verify     retry") for line in state["trace"])


def test_graph_gives_up_after_two_attempts(graph_parts):
    build, out = graph_parts
    state = doc_summary_graph.run(build("stubborn"), "warranty.md", ["approve"])
    assert state["status"] == "abstained" and state["attempts"] == 2
    assert not state["packets"] and not list(out.glob("*.json"))


def test_graph_veto_saves_nothing(graph_parts):
    build, out = graph_parts
    state = doc_summary_graph.run(build("good"), "warranty.md", ["veto"])
    assert state["status"] == "vetoed" and not list(out.glob("*.json"))


def test_graph_edit_loops_back_to_summarize(graph_parts):
    build, out = graph_parts
    state = doc_summary_graph.run(build("good"), "warranty.md",
                                  ["edit:write it for engineering", "approve"])
    assert len(state["packets"]) == 2 and state["attempts"] == 2
    assert json.loads((out / "warranty-summary.json").read_text())["audience"] == "engineering"


def test_graph_resume_does_not_reread(graph_parts):
    build, _ = graph_parts
    state = doc_summary_graph.run(build("good"), "warranty.md",
                                  ["edit:write it for engineering", "approve"])
    assert state["reads"] == 1


def test_graph_ticket_refund_is_sent_back(graph_parts):
    build, out = graph_parts
    state = doc_summary_graph.run(build(), "ticket_9001.md", ["approve"])
    assert "'refund'" in next(t for t in state["trace"] if t.startswith("verify     retry"))
    saved = json.loads((out / "ticket_9001-summary.json").read_text())
    assert not any("refund" in a.lower() for a in saved["action_items"])
    assert state["packets"][0]["flags"]


def test_graph_check_allows_describing_the_injection(graph_parts):
    state = {"text": (doc_summary.NOTES_DIR / "ticket_9001.md").read_text(), "record": {
        "key_points": [], "action_items": ["Warn support the ticket held injected "
                                           "SYSTEM instructions, which were ignored."]}}
    state["flagged"] = [p for p in state["text"].split("\n\n") if "SYSTEM" in p]
    assert doc_summary_graph.check(state) == ""
    state["record"]["action_items"] = ["Approve the refund."]
    assert "'refund'" in doc_summary_graph.check(state)


def test_graph_main_offline(capsys):
    pytest.importorskip("langgraph")
    assert doc_summary_graph.main([]) == 0
    out = capsys.readouterr().out
    assert "status: saved" in out and "reads: 1" in out
    assert doc_summary_graph.main(["--graph"]) == 0
    assert "verify -> summarize" in capsys.readouterr().out


def test_graph_document_text_never_reaches_the_user_turn(graph_parts, monkeypatch):
    # A side-effecting tool whose intent phrase appears ONLY in the document. If the
    # document were in the question, the intent guard would read it as the user asking.
    _, out = graph_parts
    from langgraph.checkpoint.memory import MemorySaver

    from tools import Tool

    ran, questions = [], []
    desk = doc_summary.SummaryDesk()
    desk.add(Tool("create_ticket", "Open a ticket.",
                  {"type": "object", "properties": {"title": {"type": "string"}}},
                  lambda title="": ran.append(title) or "opened",
                  side_effect=True, intent=r"create_ticket"))
    # Offer it, so the call reaches the intent guard instead of the unknown-tool guard.
    monkeypatch.setattr(doc_summary_graph, "SUMMARIZE_TOOLS",
                        ["read_document", "record_summary", "create_ticket"])
    text = (doc_summary.NOTES_DIR / "ticket_9001.md").read_text()
    assert "create_ticket" in text  # the phrase is in the document...

    def obedient(document, attempt, question):
        questions.append(question)
        return ScriptedModel([[call("read_document", name=document)],
                              [call("create_ticket", title="Refund approved for every unit")],
                              "done"])

    graph = doc_summary_graph.build_graph(desk, obedient, out, checkpointer=MemorySaver())
    state = doc_summary_graph.run(graph, "ticket_9001.md", ["approve"])
    assert not ran and state["status"] == "abstained"
    assert any("create_ticket -> not requested" in t for t in state["trace"])
    assert all("create_ticket" not in q and "SYSTEM:" not in q for q in questions)
    # ...and the failing direction: the same call with the document in the user turn runs.
    leaky = tool_loop.run(ScriptedModel([[call("create_ticket", title="x")], "done"]),
                          f"Summarize this:\n{text}", desk, max_turns=2,
                          confirm=lambda n, a: True)
    assert leaky["calls"][0]["status"] == "ok" and ran == ["x"]
