# Voter Deletion List Search — multi-constituency

A free, mobile-friendly app where each constituency gets its own page (its
own URL) with a search form, plus a Home page that links out to all of
them. Currently loaded with two example constituencies: **175-Bommanahalli**
and **161-C.V. RamannNagar**.

## How it works

- `build_database.py` — run **once locally** (and again whenever you add
  new PDFs). Parses every PDF under `pdfs/` into a single SQLite file
  (`data.db`) with proper columns and search indexes.
- `streamlit_app.py` — the app itself. Reads the list of constituencies
  straight out of `data.db` and **automatically builds one page per
  constituency** (with its own URL, e.g. `.../175-bommanahalli`) plus a
  Home page linking to each. You never hand-write or maintain page files —
  add a new constituency's PDFs, rebuild `data.db`, redeploy, and its page
  just appears.

Splitting it this way means the deployed app never has to parse PDFs live —
it just queries an indexed database, which is fast even on free hosting.

## 1. Organize your PDFs by constituency

```
pdfs/
├── 175-Bommanahalli/
│   ├── part_279.pdf
│   ├── part_280.pdf
│   └── ...
└── 161-CV-RamanNagar/
    ├── part_1.pdf
    └── ...
```

The folder names are just for **your own organization** — the actual
Constituency and Booth values shown in the app always come from each PDF's
own header line ("AC: ...; Part: ..."), not the folder name. So folders can
be named however's convenient for you.

## 2. Set up locally

```bash
git clone <your-repo-url>
cd <your-repo>
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Build the database:

```bash
python build_database.py --pdf-dir pdfs --db-path data.db
```

This prints a per-file record count (with the Constituency/Booth it
detected) and finishes with a total.

**If a PDF's header can't be parsed** (the "AC: ...; Part: ..." line at the
top of page 1 isn't found), that PDF is skipped entirely — no partial or
guessed data gets written. A `failed_pdfs.txt` file is created listing which
PDFs failed and why, so you can check them and, if needed, add those
records manually.

Test locally:

```bash
streamlit run streamlit_app.py 
OR
python -m streamlit run streamlit_app.py

```

Open the URL it prints, confirm the Home page lists both constituencies,
click into one, and try a search (e.g. "mohan").

## 3. Push to GitHub

Create a **public** GitHub repo (required for Streamlit Community Cloud's
free tier) and push:

```bash
git init
git add streamlit_app.py build_database.py requirements.txt data.db pdfs README.md
git commit -m "Multi-constituency voter search app"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Committing the raw `pdfs/` folder is optional (only `data.db` is actually
used at runtime) — keeping them in the repo just makes it easy to rebuild
`data.db` from scratch later or on another machine.

**Important:** if `data.db` ever exceeds ~90-100MB (unlikely for a handful
of constituencies), you'll need [Git LFS](https://git-lfs.com/).

## 4. Deploy on Streamlit Community Cloud (free)

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in
   with GitHub (no credit card required).
2. Click **"New app"**.
3. Select your repository, branch (`main`), and main file path
   (`streamlit_app.py`).
4. Click **"Deploy"**.

You get a public URL like `https://<your-app-name>.streamlit.app`. Each
constituency automatically gets its own path under that same URL, e.g.:

```
https://<your-app-name>.streamlit.app/                    → Home (links to all)
https://<your-app-name>.streamlit.app/175-bommanahalli    → Bommanahalli search
https://<your-app-name>.streamlit.app/161-c-v-ramannnagar → C.V. RamannNagar search
```

Streamlit Community Cloud's free tier allows **unlimited public apps**, so
this single-app/multi-page approach uses just one of them — no need to
deploy a separate app per constituency.

### Notes on the free tier

- The app "sleeps" after a period of inactivity and wakes up on the next
  visit (takes a few seconds) — normal for the free tier.
- Free tier apps get ~1GB RAM. Since the app queries an indexed SQLite file
  rather than loading everything into memory, this is comfortable even for
  a few hundred thousand records across many constituencies.

## 5. Adding a new constituency later

```bash
# add the new constituency's PDFs under pdfs/<any-folder-name>/
python build_database.py --pdf-dir pdfs --db-path data.db
git add data.db pdfs
git commit -m "Add <constituency> data"
git push
```

Streamlit Cloud redeploys automatically on push, and the new constituency's
page appears on the Home page and in the sidebar — no code changes needed.

## Disclaimer shown to users

This tool reflects only the PDFs that have been loaded into it and may not
be fully current. Always confirm voter status on the official ECI /
Karnataka CEO website before taking any action. This disclaimer is already
shown in the app's footer.
