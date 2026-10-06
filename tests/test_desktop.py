"""Exercise real Tk widgets and background pipeline; run under a display/Xvfb."""

import os, time
from types import SimpleNamespace
import pytest
from worship_guide.app import WorshipGuide
from worship_guide.db import WGDB
from worship_guide.pipeline import import_document
from test_pipeline import make_pdf, FixtureOCR

needs_display = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="Desktop test needs a display (CI runs Xvfb)"
)


@needs_display
def test_import_worker_review_preview_keyboard_and_editor_share_one_db(
    tmp_path, monkeypatch
):
    source = make_pdf(tmp_path / "input.pdf", 3)
    path = tmp_path / "data/db"
    app = WorshipGuide(path)
    messages = []
    monkeypatch.setattr(
        "worship_guide.review_center.messagebox.showerror",
        lambda *a, **k: messages.append(a),
    )
    monkeypatch.setattr(
        "worship_guide.app.import_document",
        lambda db, path, **kwargs: import_document(
            db, path, **{**kwargs, "backend": FixtureOCR(), "dpi": 72}
        ),
    )
    try:
        app.update()
        app.pdf.set(str(source))
        app.end.set("3")
        app.engine.set("fixture")
        app.start_analysis()
        deadline = time.monotonic() + 15
        while app.worker_thread.is_alive() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        app.poll()
        app.update()
        assert not app.worker_thread.is_alive()
        assert str(app.run_btn["state"]) == "normal"
        review = app.open_review()
        app.update()
        assert len(review.rows) == 3 and review.photo is not None
        assert review.key_var.get() == "" and "E" in review.key_hint.get()
        assert review.navigate(SimpleNamespace(widget=review.title_entry), 1) is None
        assert review.index == 0
        review.title_var.set("예수 닮기를")
        review.key_var.set("Bb")
        review.approve()
        app.update()
        assert not messages
        assert len(review.rows) == 2 and review.key_var.get() == ""
        editor = app.open_editor()
        app.update()
        assert len(editor.tree.get_children()) == 1
        row = app.db.list_songs()[0]
        assert row["available_keys"] == "Bb"
        editor.tree.selection_set(str(row["id"]))
        editor.on_select()
        app.update()
        assert len(editor.score_tree.get_children()) == 1
        editor.on_close()
        review.close()
        reopened = app.open_review()
        app.update()
        assert len(reopened.rows) == 2
        reopened.close()
    finally:
        app.close()
        app.poll()


def test_all_normal_module_imports_are_valid():
    import importlib, pkgutil, worship_guide

    for module in pkgutil.iter_modules(worship_guide.__path__):
        if module.name != "__main__":
            importlib.import_module("worship_guide." + module.name)
