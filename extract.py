"""
extract_pdfs.py

Reads constituencies.txt and extracts PDFs (from each constituency's zip)
for every row where extract_needed is True. Same manifest file drives both
this script and the Streamlit app — see constituencies.txt for the column
format.

zip_path and dest_path in the manifest can be RELATIVE (e.g.
"pdfs\\AC 175 Bommanahalli-...zip") — they're resolved relative to this
script's own folder (your project root), so you never need to write a full
machine-specific path. Absolute paths still work too, if you ever need one.

Usage:
    python extract_pdfs.py
"""

import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
MANIFEST_PATH = PROJECT_ROOT / "constituencies.txt"


def resolve_path(raw_path: str) -> Path:
    """Relative paths are resolved against the project root (this script's
    folder). Absolute paths are used as-is.
    """
    p = Path(raw_path)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_manifest(path: Path) -> list[dict]:
    entries = []
    if not path.exists():
        print(f"Manifest not found at {path}")
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            print(f"Skipping malformed manifest line: {raw_line}")
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


def extract_and_truncate_pdfs(zip_path: Path, dest_path: Path) -> None:
    if not zip_path.exists():
        print(f"  Error: Could not find the source archive at {zip_path}")
        return

    extended_dest_path = "\\\\?\\" + os.path.abspath(dest_path)
    print(f"  Extracting and truncating files to: {dest_path}")
    os.makedirs(extended_dest_path, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                # Skip directory structures inside the zip, we will flatten
                # or handle files directly.
                if member.endswith("/"):
                    continue

                # Get just the file name out of any nested zip folders.
                original_filename = os.path.basename(member)
                if not original_filename:
                    continue

                # Separate name and extension.
                name_part, ext_part = os.path.splitext(original_filename)

                # Truncate to 50 characters if it's too long.
                if len(name_part) > 50:
                    name_part = name_part[:50].strip()

                # Form the new file name.
                new_filename = f"{name_part}{ext_part}"
                target_path = os.path.join(extended_dest_path, new_filename)

                # Handle potential duplicate names caused by truncation.
                counter = 1
                while os.path.exists(target_path):
                    target_path = os.path.join(
                        extended_dest_path, f"{name_part}_{counter}{ext_part}"
                    )
                    counter += 1

                # Extract and write the file.
                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())

                print(f"    Extracted: {os.path.basename(target_path)}")

        print("  SUCCESS: All PDFs extracted and truncated successfully!")

    except Exception as e:
        print(f"  An error occurred during extraction: {e}")


def main() -> None:
    entries = load_manifest(MANIFEST_PATH)
    to_process = [e for e in entries if e["extract_needed"]]

    if not to_process:
        print(
            "No constituencies flagged with extract_needed=True in "
            "constituencies.txt. Set a row's extract_needed column to True "
            "and rerun."
        )
        return

    for entry in to_process:
        status = "enabled" if entry["enabled"] else "NOT yet enabled (test-only)"
        print(f"=== {entry['constituency']} ({status}) ===")
        zip_path = resolve_path(entry["zip_path"])
        dest_path = resolve_path(entry["dest_path"])
        extract_and_truncate_pdfs(zip_path, dest_path)
        print()


if __name__ == "__main__":
    main()