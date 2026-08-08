"""
streamlit_app.py — entry point.

Uses Streamlit's dynamic multipage navigation (st.Page / st.navigation) to
build one page per constituency found in data.db, plus a Home hub page that
links to each. No page files to hand-maintain: add a new constituency's
PDFs, rerun build_database.py, restart the app, and its page appears
automatically — both in the sidebar nav and as a link on the Home page.
"""

import re
import sqlite3
from functools import partial
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "data.db"
ALL_BOOTHS = "All booths in this constituency"

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


@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@st.cache_data
def get_constituencies():
    if not DB_PATH.exists():
        return []
    conn = get_connection()
    cur = conn.execute("SELECT DISTINCT constituency FROM electors ORDER BY constituency")
    return [row[0] for row in cur.fetchall()]


@st.cache_data
def get_booths(constituency: str):
    conn = get_connection()
    cur = conn.execute(
        "SELECT DISTINCT booth FROM electors WHERE constituency = ? ORDER BY booth",
        (constituency,),
    )
    return [row[0] for row in cur.fetchall()]


def search(constituency: str, booth: str, name: str, epic: str):
    conn = get_connection()
    query = (
        "SELECT constituency, booth, part_name, epic_number, elector_name, "
        "relative_details, age, reason FROM electors WHERE constituency = ?"
    )
    params = [constituency]
    if booth and booth != ALL_BOOTHS:
        query += " AND booth = ?"
        params.append(booth)
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
            "No data loaded yet. Run `python build_database.py --pdf-dir pdfs` "
            "locally, commit the resulting data.db, and redeploy."
        )
        return
    for constituency, page in constituency_pages.items():
        st.page_link(page, label=constituency, icon="📍", use_container_width=True)


def render_constituency_page(constituency: str, home_page):
    st.page_link(home_page, label="⬅ All constituencies", icon="🏠")
    st.title(f"🔍 {constituency}")
    st.caption(
        "Search this constituency's voter roll deletion list to check if a "
        "name was flagged for removal (e.g. untraceable, permanently "
        "shifted, deceased, or already enrolled elsewhere)."
    )

    booth_options = [ALL_BOOTHS] + get_booths(constituency)

    with st.form(f"search_form_{slugify(constituency)}"):
        booth_choice = st.selectbox(
            "Booth (optional — search across all booths if left as-is)",
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
            cols, rows = search(constituency, booth_choice, name_input, epic_input)
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
    constituencies = get_constituencies()

    # constituency_pages is populated below, but home_page_fn is defined now
    # and closes over it by reference — by the time a user actually opens
    # the Home page, the dict has already been filled in, so this works
    # without needing the two pages to reference each other up front.
    constituency_pages = {}

    def home_page_fn():
        render_home(constituency_pages)

    home = st.Page(home_page_fn, title="Home", icon="🏠", url_path="", default=True)

    for c in constituencies:
        constituency_pages[c] = st.Page(
            partial(render_constituency_page, c, home),
            title=c,
            icon="📍",
            url_path=slugify(c),
        )

    pages = [home] + list(constituency_pages.values())
    nav = st.navigation(pages)
    nav.run()


if __name__ == "__main__":
    main()
