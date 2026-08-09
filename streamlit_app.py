"""
streamlit_app.py — entry point.

Reads constituencies.txt (a static, hand-editable manifest) to decide which
constituencies to show. Each line with enabled=True (and not commented out
with a leading #) maps a constituency to its OWN SQLite file (e.g.
data_175.db), and gets its own page — built dynamically via Streamlit's
multipage navigation (st.Page/st.navigation) — plus a link from the Home
page.

Two independent ways to hide a constituency from this app:
  - Set its "enabled" column to False (keeps the line active for
    extract_pdfs.py — useful while you're still testing new data locally
    before making it public).
  - Comment the whole line out with a leading # (skips it everywhere,
    including extraction).
"""

import re
import sqlite3
from functools import partial
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent
MANIFEST_PATH = APP_DIR / "constituencies.txt"

st.set_page_config(
    page_title="Voter Deletion List Search",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Mobile-friendly tweaks: comfortable tap targets, no wasted side padding,
# readable font sizes (16px prevents iOS auto-zoom on input tap).
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; padding-left: 1rem; padding-right: 1rem; max-width: 640px; }
    input[type="text"] { font-size: 16px !important; }
    div.stButton > button, div.stFormSubmitButton > button { font-size: 16px !important; padding: 0.6rem 1rem; }
    div[data-testid="stPageLink"] a { font-size: 16px !important; padding: 0.5rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_manifest(path: Path) -> list[dict]:
    """Parse constituencies.txt. Only non-blank, non-'#'-commented lines
    with enabled=True are returned (i.e. only the constituencies that
    should actually be shown right now). Tolerates extra/missing columns
    (zip_path/dest_path/extract_needed are used only by extract_pdfs.py) —
    this app only needs constituency, db_filename, and enabled.
    """
    entries = []
    if not path.exists():
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue  # malformed line — silently skip rather than crash the app
        constituency, db_filename = parts[0], parts[1]
        # 6th column (enabled) is optional for backward compatibility —
        # older manifest lines without it default to enabled.
        enabled = True
        if len(parts) >= 6:
            enabled = parts[5].strip().lower() == "true"
        if not enabled:
            continue
        entries.append({"constituency": constituency, "db_filename": db_filename})
    return entries


@st.cache_resource
def get_connection(db_path_str: str):
    # Cached per db_path_str, so each constituency's file gets its own
    # connection without any cross-constituency mixing.
    return sqlite3.connect(db_path_str, check_same_thread=False)


@st.cache_data
def get_db_constituency(db_path_str: str) -> str:
    conn = get_connection(db_path_str)
    cur = conn.execute("SELECT DISTINCT constituency FROM electors ORDER BY constituency")
    row = cur.fetchone()
    return row[0] if row else ""


@st.cache_data
def get_booths(db_path_str: str, constituency: str):
    conn = get_connection(db_path_str)
    cur = conn.execute(
        "SELECT DISTINCT booth FROM electors WHERE constituency = ? ORDER BY booth",
        (constituency,),
    )
    return [row[0] for row in cur.fetchall()]


def search(db_path_str: str, constituency: str, booths: list, name: str, epic: str):
    conn = get_connection(db_path_str)
    query = (
        "SELECT constituency, booth, part_name, epic_number, elector_name, "
        "relative_details, age, reason FROM electors WHERE constituency = ?"
    )
    params = [constituency]
    if booths:
        placeholders = ", ".join("?" for _ in booths)
        query += f" AND booth IN ({placeholders})"
        params.extend(booths)
    if name:
        # LOWER() on both sides makes this fully case-insensitive regardless
        # of whether the source PDF stored the name in caps or mixed case.
        query += " AND LOWER(elector_name) LIKE LOWER(?)"
        params.append(f"%{name.strip()}%")
    if epic:
        query += " AND LOWER(epic_number) LIKE LOWER(?)"
        params.append(f"%{epic.strip()}%")
    query += " LIMIT 200"
    cur = conn.execute(query, params)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def render_home(constituency_pages: dict):
    st.title("🔍 Voter Deletion List Search")
    st.caption(
        "Pick your constituency below to search its voter roll deletion "
        "list by name or EPIC number."
    )
    if not constituency_pages:
        st.warning(
            "No constituencies are active in constituencies.txt (or the "
            "file is missing). Add/uncomment a line there, run "
            "build_database.py, and redeploy."
        )
        return
    for constituency, page in constituency_pages.items():
        st.page_link(page, label=constituency, icon="📍", use_container_width=True)


def render_constituency_page(constituency: str, db_filename: str, home_page):
    st.page_link(home_page, label="⬅ All constituencies", icon="🏠")
    st.title(f"🔍 {constituency}")

    db_path = APP_DIR / db_filename
    if not db_path.exists():
        st.error(
            f"{db_filename} not found. Run "
            f"`python build_database.py --pdf-dir pdfs --db-dir .` locally "
            f"for this constituency, commit {db_filename}, and redeploy."
        )
        return

    db_path_str = str(db_path)
    db_constituency = get_db_constituency(db_path_str) or constituency
    st.caption(
        "Search this constituency's voter roll deletion list to check if a "
        "name was flagged for removal (e.g. untraceable, permanently "
        "shifted, deceased, or already enrolled elsewhere)."
    )

    booth_options = get_booths(db_path_str, db_constituency)

    with st.form(f"search_form_{slugify(constituency)}"):
        booth_choices = st.multiselect(
            "Booth (optional — check one or more; leave empty to search all booths)",
            booth_options,
        )
        name_input = st.text_input(
            "Name (any case, partial match ok)", placeholder="e.g. mohan or MOHAN"
        )
        epic_input = st.text_input("EPIC number", placeholder="e.g. UHN4783239")
        submitted = st.form_submit_button("Search", use_container_width=True)

    if submitted:
        if not name_input and not epic_input:
            st.warning("Enter a name or EPIC number to search.")
        else:
            cols, rows = search(db_path_str, db_constituency, booth_choices, name_input, epic_input)
            if not rows:
                st.info("No matching records found in the deletion list.")
            else:
                st.success(f"Found {len(rows)} matching record(s).")
                for r in rows:
                    data = dict(zip(cols, r))
                    with st.container(border=True):
                        st.markdown(f"**{data['elector_name']}**  ·  EPIC: `{data['epic_number']}`")
                        st.write(f"Relative: {data['relative_details']}  ·  Age: {data['age']}")
                        st.write(f"Reason for removal: **{data['reason']}**")
                        st.caption(f"{data['constituency']}  ·  Booth {data['booth']}")
                if len(rows) == 200:
                    st.caption("Showing first 200 results — refine your search for more precise results.")

    st.divider()
    st.caption(
        "This tool only reflects data present in the uploaded PDFs and may not "
        "be fully up to date. Always verify your voter status on the official "
        "ECI / Karnataka CEO website before taking action: "
        "[ceo.karnataka.gov.in/asddo.html](https://ceo.karnataka.gov.in/asddo.html)"
    )


def main():
    manifest_entries = load_manifest(MANIFEST_PATH)

    # constituency_pages is populated below, but home_page_fn is defined now
    # and closes over it by reference — by the time a user actually opens
    # the Home page, the dict has already been filled in, so this works
    # without needing the two pages to reference each other up front.
    constituency_pages = {}

    def home_page_fn():
        render_home(constituency_pages)

    home = st.Page(home_page_fn, title="Home", icon="🏠", url_path="", default=True)

    for entry in manifest_entries:
        constituency = entry["constituency"]
        db_filename = entry["db_filename"]
        constituency_pages[constituency] = st.Page(
            partial(render_constituency_page, constituency, db_filename, home),
            title=constituency,
            icon="📍",
            url_path=slugify(constituency),
        )

    pages = [home] + list(constituency_pages.values())
    nav = st.navigation(pages)
    nav.run()


if __name__ == "__main__":
    main()