import pytest
from worship_guide.db import WGDB
from worship_guide.pipeline import register_source
from worship_guide.acceptance import verify_twenty
from test_pipeline import make_pdf, reviewed


def test_bulk_gate_is_created_only_after_real_reopen_and_pdf_order_checks(tmp_path):
    source = make_pdf(tmp_path / "twenty.pdf")
    with WGDB(tmp_path / "data/db") as db:
        sid = register_source(db, source)
        with pytest.raises(ValueError, match="승인한 20페이지"):
            verify_twenty(db, sid)
        assert (
            db.conn.execute("SELECT count(*) FROM acceptance_runs").fetchone()[0] == 0
        )
        reviewed(db, source)
        before = [
            dict(r) for r in db.conn.execute("SELECT * FROM score_variants ORDER BY id")
        ]
        evidence = verify_twenty(db, sid)
        assert evidence["passed"] and evidence["simple_pdf_render_order_match"]
        assert evidence["guide_toc_render_order_match"] and evidence["korean_text"]
        assert [
            dict(r) for r in db.conn.execute("SELECT * FROM score_variants ORDER BY id")
        ] == before
        assert len(db.list_collections()) == 0  # QA collection stays in the copy
        assert (
            db.conn.execute("SELECT count(*) FROM acceptance_runs").fetchone()[0] == 1
        )
