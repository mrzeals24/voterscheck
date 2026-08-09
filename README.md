# Voter Deletion List Search — one database per constituency

Each constituency gets its **own** SQLite file (e.g. `data_175.db`,
`data_161.db`) instead of one shared database, plus its own page in the
app. A single manifest file (`constituencies.txt`) controls both which
constituencies the app shows and which zips get extracted locally.

## Why split per constituency

- **Smaller, targeted Git/LFS pushes.** Adding a new constituency only
  creates a new file — existing constituencies' `.db` files, and their
  Git/LFS history, are untouched. Previously, adding *any* constituency
  meant re-uploading one giant combined file every time.
- **Comment a line out to hide a constituency** from the Home page without
  losing its mapping or deleting its data.

## Files

- `constituencies.txt` — the manifest. One line per constituency, pipe
  (`|`) separated. Comment a line with a leading `#` to hide it from the
  Streamlit app AND skip it during PDF extraction.
- `extract_pdfs.py` — reads the manifest, extracts every constituency's
  zip whose `extract_needed` column is `True`.
- `build_database.py` — parses PDFs and writes one `.db` file per
  constituency it finds.
- `streamlit_app.py` — the app. Reads the manifest to decide which pages
  to build; each page opens only its own constituency's `.db` file.

## Manifest format

```
# constituency|db_filename|zip_path|dest_path|extract_needed|enabled
175-Bommanahalli|data_175.db|pdfs\AC175.zip|pdfs\175-Bommanahalli|False|True
161-C.V. RamannNagar|data_161.db|pdfs\AC161.zip|pdfs\161-CV-RamanNagar|False|True
```

- `constituency` must exactly match the text `build_database.py` prints
  after parsing that constituency's PDFs (copy it from there, don't retype
  it, to avoid a mismatch).
- `db_filename` is what the deployed Streamlit app actually reads.
- `zip_path` / `dest_path` are used only by `extract_pdfs.py` (ignored by
  the deployed app) and can be **relative to your project folder** — e.g.
  `pdfs\AC175.zip` resolves against wherever `extract_pdfs.py` itself
  lives, so nothing machine-specific needs to go in this file.
- `extract_needed` — True/False, controls `extract_pdfs.py` only.
- `enabled` — True/False, controls the Streamlit app only. Set to `False`
  while you're still testing a new constituency locally (extraction and
  `build_database.py` still work normally), then flip to `True` once
  you're happy with the data and ready to make it public.

Two independent ways to hide a constituency:
- **Comment the whole line** with a leading `#` — skipped everywhere (app
  and extraction both ignore it).
- **Set `enabled` to `False`** — stays out of the public app only; you can
  keep extracting/rebuilding it locally while testing.

## Workflow for adding a new constituency

```powershell
# 1. In constituencies.txt: add a new line (or uncomment an existing one),
#    with extract_needed set to True for this constituency.

# 2. Extract its PDFs from the zip
python extract_pdfs.py

# 3. Build just that constituency's .db file (safe to point at the whole
#    pdfs/ folder — build_database.py groups by constituency automatically
#    and only rewrites the file(s) for constituencies it actually finds
#    PDFs for in this run)
python build_database.py --pdf-dir pdfs\<new-constituency-folder> --db-dir .
python build_database.py --pdf-dir pdfs\175-Bommanahalli --db-dir .

# 4. Console output will print the exact manifest line for this
#    constituency — confirm it matches what's already in constituencies.txt
#    (or copy it in if this is a brand new constituency).

# 5. Commit and push
git add constituencies.txt data_<ac_number>.db
git commit -m "Add <constituency> data"
git push origin main

# 6. On share.streamlit.io: Reboot app (see note below on why)
```

## Testing a new constituency before making it public

```powershell
# In constituencies.txt: add the new line with extract_needed=True and
# enabled=False (so it's invisible on the live Home page for now)

python extract_pdfs.py
python build_database.py --pdf-dir pdfs\<new-constituency-folder> --db-dir .
streamlit run streamlit_app.py   # confirm it's NOT on the Home page,
                                  # but you can still verify data_<ac>.db
                                  # locally (e.g. sqlite3 spot-checks)

# Happy with it? Flip enabled to True in constituencies.txt, then:
git add constituencies.txt data_<ac_number>.db
git commit -m "Enable <constituency>"
git push origin main
```

## Hiding a constituency without deleting it

Just add a `#` at the start of its line in `constituencies.txt`, commit,
push. Its `.db` file stays in the repo untouched — uncomment the line
later to bring it back instantly, no rebuild needed.

## Setup (first time)

```bash
git clone <your-repo-url>
cd <your-repo>
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Test locally:
```bash
streamlit run streamlit_app.py
```

## Deploying free on Streamlit Community Cloud

1. Push your repo to a **public** GitHub repo (`data_*.db` files go through
   Git LFS if any exceed 100MB — see `.gitattributes`).
2. [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub →
   "New app" → select your repo → main file `streamlit_app.py` → Deploy.
3. After pushing updates, Streamlit usually auto-redeploys within a minute
   or two. If changes don't seem to show up (more likely after an LFS
   history rewrite or manifest change), manually **Reboot app**: open your
   app → "Manage app" (bottom-right) → ⋮ menu → "Reboot app".

Streamlit Community Cloud's free tier allows unlimited public apps, so this
single-app/multi-page approach uses just one of them.

## Disclaimer shown to users

Every constituency page shows: this tool only reflects data present in the
loaded PDFs and may not be fully current — always verify voter status on
the official Karnataka CEO site
([ceo.karnataka.gov.in/asddo.html](https://ceo.karnataka.gov.in/asddo.html))
before taking any action.

M K PRASHANTH · EPIC: WZU3136868

Relative: M K KHADRIGA (Father) · Age: 47

Reason for removal: Untraceable/Absent

161-C.V. RamannNagar · Booth 94-Govt. Lower Primary Sc
