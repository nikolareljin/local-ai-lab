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
import home_automation  # noqa: E402
import invoice_extract  # noqa: E402
import pdf_index  # noqa: E402
import requests  # noqa: E402
import tool_loop  # noqa: E402
from recipe_kit import call  # noqa: E402

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
