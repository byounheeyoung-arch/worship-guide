"""Scriptable diagnostics and coherent checkpoints; never generates app ZIPs."""

import argparse, json, importlib.util, shutil, sys
from dataclasses import asdict
from pathlib import Path
from .db import WGDB
from .paths import default_db_path
from .pipeline import import_document
from .master_import import import_master_snapshot
from .pdf_export import export_collection_pdf


def main():
    parser = argparse.ArgumentParser(prog="wg")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    job = sub.add_parser("import")
    job.add_argument("source", type=Path)
    job.add_argument("--start", type=int, default=1)
    job.add_argument("--end", type=int, default=20)
    job.add_argument("--engine", choices=["easyocr", "tesseract"], default="easyocr")
    master = sub.add_parser("import-master")
    master.add_argument("snapshot", type=Path)
    export = sub.add_parser("export")
    export.add_argument("collection_id", type=int)
    export.add_argument("output", type=Path)
    export.add_argument("--mode", choices=["simple", "guide"], default="simple")
    acceptance = sub.add_parser("verify-20")
    acceptance.add_argument("source_id", type=int)
    args = parser.parse_args()
    with WGDB(args.db) as db:
        if args.command == "doctor":
            result = {
                "python": sys.version.split()[0],
                "database": str(db.path),
                "integrity": db.conn.execute("PRAGMA integrity_check").fetchone()[0],
                "schema": db.conn.execute("PRAGMA user_version").fetchone()[0],
                "songs": len(db.list_songs()),
                "scores": db.conn.execute(
                    "SELECT COUNT(*) FROM score_variants"
                ).fetchone()[0],
                "pending_review": len(db.review_queue()),
                "easyocr_installed": bool(importlib.util.find_spec("easyocr")),
                "tesseract": shutil.which("tesseract"),
            }
        elif args.command == "import":
            result = asdict(
                import_document(
                    db,
                    args.source,
                    start_page=args.start,
                    end_page=args.end,
                    engine=args.engine,
                    progress=lambda p: print(json.dumps(p), flush=True),
                )
            )
        elif args.command == "import-master":
            result = import_master_snapshot(db, args.snapshot)
        elif args.command == "verify-20":
            from .acceptance import verify_twenty

            result = verify_twenty(db, args.source_id)
        else:
            collection = db.get_collection(args.collection_id)
            if not collection:
                raise ValueError("악보집을 찾을 수 없습니다.")
            pages, warnings = export_collection_pdf(
                db.get_collection_items(args.collection_id),
                args.output,
                db_dir=db.path.parent,
                mode=args.mode,
                title=collection["name"],
                description=collection["description"],
            )
            result = {"pages": pages, "warnings": warnings, "output": str(args.output)}
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
