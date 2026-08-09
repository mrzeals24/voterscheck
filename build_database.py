"""
build_database.py

Parses voter-deletion-list PDFs (Karnataka CEO format) and writes ONE SQLite
file PER CONSTITUENCY (e.g. data_175.db, data_161.db) instead of one shared
database. This means adding a new constituency only touches its own file —
existing constituencies' files, and their Git/LFS history, are untouched.

Two ways to run it:

  1. Manifest-driven (default, no --pdf-dir given): reads constituencies.txt
     and, for every row with extract_needed=True, EXTRACTS (if its dest_path
     folder doesn't already exist) then BUILDS (if its .db file doesn't
     already exist) — one command does both steps:

         python build_database.py

     Already-done work is skipped automatically, so it's safe to just rerun
     this after adding a new row to constituencies.txt. To force a redo for
     a specific constituency (e.g. you added more PDFs), delete its
     dest_path folder and/or its .db file first, then rerun.

  2. Manual (--pdf-dir given): scans that folder recursively for PDFs from
     ANY constituency and auto-discovers/writes whichever ones it finds.
     Useful the first time you're processing a constituency that isn't in
     constituencies.txt yet:

         python build_database.py --pdf-dir "pdfs\\some-folder"

PDFs can be anywhere under the given/resolved folder (organize into
per-constituency subfolders for your own convenience — folder names don't
matter, the actual Constituency/Booth values always come from each PDF's
own header text).

After a successful run, this prints the exact manifest line for each
constituency it wrote, so you can add/verify it in constituencies.txt.

If a PDF's "AC: ...; Part: ..." header line can't be found/parsed on page 1,
that PDF is SKIPPED entirely (no partial/garbage rows) and listed in
failed_pdfs.txt so you can check it and, if needed, provide the AC/Part
values manually.
"""

import argparse
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import pdfplumber

PROJECT_ROOT = Path(__file__).parent
MANIFEST_PATH = PROJECT_ROOT / "constituencies.txt"
BOOTH_LABEL_MAX_LEN = 25

# Matches the "AC: 175-Bommanahalli; Part: 279-MITRA ACADEMY SCHOOL ..." line
# that appears near the top of every page, giving us AC + part metadata.
# No DOTALL: '.' stops at end-of-line, so we only capture that one line.
HEADER_RE = re.compile(
    r"AC:\s*(\d+)-([^;]+);\s*Part:\s*(\d+)-(.+)",
    re.IGNORECASE,
)


def resolve_path(raw_path: str) -> Path:
    """Relative paths (e.g. 'pdfs\\175-Bommanahalli') are resolved against
    the project root (this script's folder). Absolute paths are used as-is.
    """
    p = Path(raw_path)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_manifest(path: Path) -> list[dict]:
    """Same manifest format/columns as extract_pdfs.py uses."""
    entries = []
    if not path.exists():
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        constituency, db_filename, zip_path, dest_path, extract_needed = parts[:5]
        enabled = parts[5].strip().lower() == "true" if len(parts) >= 6 else True
        entries.append(
            {
                "constituency": constituency,
                "db_filename": db_filename,
                "zip_path": zip_path,
                "dest_path": dest_path,
                "extract_needed": extract_needed.strip().lower() == "true",
                "enabled": enabled,
            }
        )
    return entries


def extract_pdf_metadata(pdf: pdfplumber.PDF) -> dict:
    """Pull AC number/name and Part number/name from the first page's text.

    Raises ValueError if the header line can't be found or parsed, so the
    caller can skip this PDF instead of silently writing blank/garbage
    Constituency/Booth values.
    """
    text = pdf.pages[0].extract_text() or ""
    match = HEADER_RE.search(text)
    if not match:
        raise ValueError(
            "Could not find/parse 'AC: <num>-<name>; Part: <num>-<name>' "
            "header line on page 1"
        )
    ac_number, ac_name, part_number, part_name = (g.strip() for g in match.groups())
    if not ac_number or not ac_name or not part_number or not part_name:
        raise ValueError("AC/Part header line matched but a field was empty")

    constituency = f"{ac_number}-{ac_name}"
    booth_full = f"{part_number}-{part_name}"
    booth = (
        booth_full
        if len(booth_full) <= BOOTH_LABEL_MAX_LEN
        else booth_full[:BOOTH_LABEL_MAX_LEN] + "…"
    )

    return {
        "ac_number": ac_number,
        "ac_name": ac_name,
        "part_number": part_number,
        "part_name": part_name,
        "constituency": constituency,
        "booth": booth,
    }


def parse_pdf(path: Path) -> list[dict]:
    """Extract all elector rows from a single PDF using its native tables."""
    records = []
    with pdfplumber.open(path) as pdf:
        meta = extract_pdf_metadata(pdf)  # raises ValueError if header not found
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or not row[0]:
                        continue
                    s_no = row[0].strip()
                    if not s_no.isdigit():
                        continue  # skips repeated header rows
                    clean = [c.replace("\n", " ").strip() if c else "" for c in row]
                    if len(clean) < 7:
                        continue
                    records.append(
                        {
                            **meta,
                            "s_no": clean[0],
                            "serial_no": clean[1],
                            "epic_number": clean[2],
                            "elector_name": clean[3],
                            "relative_details": clean[4],
                            "age": clean[5].strip("()"),
                            "reason": clean[6],
                            "source_file": path.name,
                        }
                    )
    if not records:
        raise ValueError("Header parsed OK but no elector table rows were found")
    return records


def write_constituency_db(db_path: Path, records: list[dict]) -> None:
    """(Re)write a single constituency's own SQLite file from its records."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS electors")
    cur.execute(
        """
        CREATE TABLE electors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constituency TEXT,
            booth TEXT,
            ac_number TEXT,
            ac_name TEXT,
            part_number TEXT,
            part_name TEXT,
            s_no TEXT,
            serial_no TEXT,
            epic_number TEXT,
            elector_name TEXT,
            relative_details TEXT,
            age TEXT,
            reason TEXT,
            source_file TEXT
        )
        """
    )
    for r in records:
        cur.execute(
            """
            INSERT INTO electors (
                constituency, booth, ac_number, ac_name, part_number, part_name,
                s_no, serial_no, epic_number, elector_name,
                relative_details, age, reason, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["constituency"], r["booth"], r["ac_number"], r["ac_name"],
                r["part_number"], r["part_name"],
                r["s_no"], r["serial_no"], r["epic_number"], r["elector_name"],
                r["relative_details"], r["age"], r["reason"], r["source_file"],
            ),
        )
    cur.execute("CREATE INDEX idx_epic ON electors(epic_number)")
    cur.execute("CREATE INDEX idx_name ON electors(elector_name)")
    cur.execute("CREATE INDEX idx_constituency ON electors(constituency)")
    cur.execute("CREATE INDEX idx_booth ON electors(booth)")
    conn.commit()
    conn.close()


def parse_pdf_folder(pdf_dir: Path, label: str) -> tuple[list[dict], list[tuple]]:
    """Parse every PDF under pdf_dir. Returns (records, failed)."""
    pdf_files = sorted(pdf_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"  No PDFs found in {pdf_dir} (searched recursively)")
        return [], []
    records = []
    failed = []
    for i, path in enumerate(pdf_files, start=1):
        try:
            file_records = parse_pdf(path)
        except Exception as e:
            print(f"  [{i}/{len(pdf_files)}] FAILED: {path.name} — {e}")
            failed.append((path.name, str(e)))
            continue
        records.extend(file_records)
        print(
            f"  [{i}/{len(pdf_files)}] {path.name}: {len(file_records)} records "
            f"({file_records[0]['constituency']} / {file_records[0]['booth']})"
        )
    return records, failed


def write_failed_report(failed: list[tuple]) -> None:
    if not failed:
        return
    report_path = PROJECT_ROOT / "failed_pdfs.txt"
    with open(report_path, "w") as f:
        f.write("These PDFs could not be parsed automatically.\n")
        f.write("Check each one, then either fix/re-source the PDF or\n")
        f.write("add its records manually.\n\n")
        for name, reason in failed:
            f.write(f"{name}\n  reason: {reason}\n\n")
    print(f"\n[WARNING] {len(failed)} PDF(s) FAILED and were skipped entirely.")
    print(f"   See {report_path} for details — provide inputs for these manually.")
    for name, reason in failed:
        print(f"   - {name}: {reason}")


def build_from_manifest(db_dir: Path) -> None:
    """Default mode: for every constituency flagged extract_needed=True in
    constituencies.txt —

      1. Extract, but ONLY if its dest_path folder doesn't already exist
         (skips redundant re-extraction of a zip you've already unpacked).
      2. Build/write its .db file, but ONLY if that .db file doesn't
         already exist (skips redundant reparsing of PDFs already loaded).

    This makes it safe to just run `python build_database.py` repeatedly
    as you add constituencies — already-done work is skipped automatically.
    To force a redo for a specific constituency (e.g. you added more PDFs
    to its folder), delete its dest_path folder and/or its .db file first,
    then rerun.
    """
    import extract  # same folder — reuses its extraction logic as-is

    entries = load_manifest(MANIFEST_PATH)
    to_process = [e for e in entries if e["extract_needed"]]

    if not to_process:
        print(
            f"No constituencies flagged with extract_needed=True in "
            f"{MANIFEST_PATH}.\n"
            f"Set a row's extract_needed column to True, or pass "
            f"--pdf-dir explicitly to scan a folder directly."
        )
        return

    db_dir.mkdir(parents=True, exist_ok=True)
    all_failed = []
    written = 0

    for entry in to_process:
        pdf_dir = resolve_path(entry["dest_path"])
        db_path = db_dir / entry["db_filename"]
        print(f"=== {entry['constituency']} ===")

        if pdf_dir.exists():
            print(f"  Skipping extraction — {pdf_dir} already exists")
        else:
            zip_path = resolve_path(entry["zip_path"])
            print(f"  Extracting {zip_path} -> {pdf_dir}")
            extract.extract_and_truncate_pdfs(zip_path, pdf_dir)

        if db_path.exists():
            print(f"  Skipping build — {db_path} already exists\n")
            continue

        records, failed = parse_pdf_folder(pdf_dir, entry["constituency"])
        all_failed.extend(failed)

        if not records:
            print("  Nothing written for this constituency.\n")
            continue

        actual_constituency = records[0]["constituency"]
        if actual_constituency != entry["constituency"]:
            print(
                f"  [WARNING] constituencies.txt says '{entry['constituency']}' "
                f"but the PDFs parsed as '{actual_constituency}' — check for "
                f"a typo in the manifest."
            )

        write_constituency_db(db_path, records)
        written += 1
        print(f"  Wrote {len(records)} records to {db_path}\n")

    print(f"Wrote {written}/{len(to_process)} constituency database file(s).")
    write_failed_report(all_failed)


def build_from_folder(pdf_dir: Path, db_dir: Path) -> None:
    """Manual mode (--pdf-dir given): scan a folder for PDFs from any
    constituency, auto-discover which constituencies are present, and
    write each one's .db file. Useful for a constituency not yet in
    constituencies.txt.
    """
    pdf_files = sorted(pdf_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {pdf_dir} (searched recursively)")
        return

    db_dir.mkdir(parents=True, exist_ok=True)

    records_by_ac = defaultdict(list)
    failed = []
    for i, path in enumerate(pdf_files, start=1):
        try:
            records = parse_pdf(path)
        except Exception as e:
            print(f"[{i}/{len(pdf_files)}] FAILED: {path.name} — {e}")
            failed.append((path.name, str(e)))
            continue
        ac_number = records[0]["ac_number"]
        records_by_ac[ac_number].extend(records)
        print(
            f"[{i}/{len(pdf_files)}] {path.name}: {len(records)} records "
            f"({records[0]['constituency']} / {records[0]['booth']})"
        )

    if not records_by_ac:
        print("\nNo constituencies produced any records — nothing written.")
    else:
        print(f"\nWriting {len(records_by_ac)} per-constituency database file(s)...")
        print("\nAdd/verify these lines in constituencies.txt "
              "(uncomment or add if missing):\n")
        for ac_number, records in records_by_ac.items():
            constituency = records[0]["constituency"]
            db_filename = f"data_{ac_number}.db"
            db_path = db_dir / db_filename
            write_constituency_db(db_path, records)
            print(f"  [{constituency}] -> {db_path}  ({len(records)} records)")
            print(f"    {constituency}|{db_filename}|<zip_path>|<dest_path>|False|True")

    print(f"\nSucceeded: {len(pdf_files) - len(failed)} / {len(pdf_files)} PDFs")
    write_failed_report(failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf-dir", type=Path, default=None,
        help="Scan this folder directly instead of reading constituencies.txt "
             "(useful for a constituency not yet in the manifest)."
    )
    parser.add_argument(
        "--db-dir", type=Path, default=Path("."),
        help="Folder to write per-constituency .db files into (default: current folder)"
    )
    args = parser.parse_args()

    if args.pdf_dir is not None:
        build_from_folder(args.pdf_dir, args.db_dir)
    else:
        build_from_manifest(args.db_dir)