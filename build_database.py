"""
build_database.py

Parses voter-deletion-list PDFs (Karnataka CEO format) and writes ONE SQLite
file PER CONSTITUENCY (e.g. data_175.db, data_161.db) instead of one shared
database. This means adding a new constituency only touches its own file —
existing constituencies' files, and their Git/LFS history, are untouched.

Usage:
    python build_database.py --pdf-dir ./pdfs --db-dir .

PDFs can be anywhere under --pdf-dir (organize into per-constituency
subfolders for your own convenience — folder names don't matter, the actual
Constituency/Booth values always come from each PDF's own header text).

After a successful run, this prints the exact line to add/verify in
constituencies.txt for each constituency it found, so the Streamlit app
knows to load it.

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

BOOTH_LABEL_MAX_LEN = 25

# Matches the "AC: 175-Bommanahalli; Part: 279-MITRA ACADEMY SCHOOL ..." line
# that appears near the top of every page, giving us AC + part metadata.
# No DOTALL: '.' stops at end-of-line, so we only capture that one line.
HEADER_RE = re.compile(
    r"AC:\s*(\d+)-([^;]+);\s*Part:\s*(\d+)-(.+)",
    re.IGNORECASE,
)


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


def build_database(pdf_dir: Path, db_dir: Path) -> None:
    pdf_files = sorted(pdf_dir.rglob("*.pdf"))  # rglob: works whether PDFs
    # sit directly in pdf_dir or are organized into per-constituency
    # subfolders (e.g. pdfs/175-Bommanahalli/*.pdf, pdfs/161-CV-RamanNagar/*.pdf).
    # Subfolder names are just for your own organization — the actual
    # Constituency/Booth values always come from each PDF's own header text.
    if not pdf_files:
        print(f"No PDFs found in {pdf_dir} (searched recursively)")
        return

    db_dir.mkdir(parents=True, exist_ok=True)

    # Group parsed records by AC number, so each constituency ends up in its
    # own file regardless of how its PDFs are organized on disk.
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
            print(f"    {constituency}|{db_filename}")

    print(f"\nSucceeded: {len(pdf_files) - len(failed)} / {len(pdf_files)} PDFs")

    if failed:
        report_path = pdf_dir.parent / "failed_pdfs.txt"
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=Path, default=Path("pdfs"))
    parser.add_argument(
        "--db-dir", type=Path, default=Path("."),
        help="Folder to write per-constituency .db files into (default: current folder)"
    )
    args = parser.parse_args()
    build_database(args.pdf_dir, args.db_dir)