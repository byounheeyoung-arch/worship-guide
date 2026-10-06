"""Compatibility alias; no second editor or database schema."""

from .editor import Editor

DBEditorV2 = Editor


def open_editor(master=None, db_path=None):
    return Editor(master, db_path=db_path)
