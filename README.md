# RentFinder + Lease Updater + Neighborhood Report

This version has three tools:

1. **Rent Finder** — ZIP/address → Zillow Research ZORI rent trend.
2. **Lease Updater** — upload a PDF/DOCX/TXT lease and generate a present-date draft for review.
3. **Neighborhood Report** — generates a downloadable Word report covering rent, housing-size proxy, transportation, crime context, education, nearby apartment buildings and public neighborhood/building photos.

## Run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Neighborhood Report data sources

- Zillow Research ZORI — typical asking-rent trend
- Census Reporter / American Community Survey — median gross rent, household income, median rooms, commute modes, educational attainment
- OpenStreetMap / Overpass — nearby transit, schools, colleges and apartment-building features
- OpenCrime — city-level data processed from FBI Crime Data Explorer
- Wikimedia Commons — nearby public building/neighborhood imagery

## Important limitations

Free public area-level datasets do **not** reliably provide exact square footage for individual active rental units or actual photos of current listings. This version therefore labels median room count as a housing-size proxy and labels Wikimedia photos as neighborhood/building context.

For exact unit square footage and active listing photos, add a property-listing data provider later.


## Smart Lease Updater update
- Detects more real-world date formats, including `1 day of July 2020`.
- Shows surrounding context and classifies likely lease dates vs personal/DOB dates.
- Personal/DOB dates are not preselected.
- For DOCX files, edits a copy of the original document instead of rebuilding the lease from plain text.
- Searches normal paragraphs, tables, headers, and footers.
- Keeps the original upload unchanged and generates a separate draft for review.


## New: Moving Decision Assistant
A fourth sidebar tool lets you assess a ZIP or compare two ZIPs using optional proposed rent, income, monthly expenses and one-time moving costs. It shows evidence-based pros and cons, mapped transit/schools when available, and a downloadable DOCX report.

### Update your deployed Streamlit app
Upload `app.py` and `moving_assistant.py` to the root of your existing GitHub repository. Keep `neighborhood_report.py` and `requirements.txt` in the same directory. Commit changes; Streamlit Cloud normally redeploys automatically.

This report does not currently include reliable property-level square footage/photos, healthcare quality, crime-based safety ratings or environmental risk scores. Verify those separately.


## Automatic analysis directly under the RentFinder chart
The Rent Finder tab now automatically displays **Location pros & cons** immediately after the rent trend chart, using the same searched ZIP/address. There is no second location input or button. Data are from Zillow rent trends, ACS/Census Reporter and OpenStreetMap, with transparent limitations and graceful fallback if external data are unavailable.

To update GitHub, replace `app.py` and `moving_assistant.py` with the files in this archive. Leave the other existing files in place.


## Rent Finder local area data
Immediately below the rent chart, the same searched ZIP automatically shows mapped transportation, grocery stores, educational facilities, city crime data when verified and available, and ZIP educational attainment. Upload/replace `app.py` and add `local_data.py`; retain the other Python files.

## Fix for unavailable location data
`local_data.py` now uses a fallback ZIP geocoder, two OpenStreetMap Overpass endpoints, and a direct US Census ACS fallback. Each section handles errors independently and displays diagnostic messages. Crime data links to official FBI reporting rather than guessing a ZIP crime rate.

Replace `local_data.py` in GitHub and commit. If the deployed app is still showing the older output, also replace `app.py` from this ZIP.
\n\n### Overpass connectivity update\nTries GET and POST across four public Overpass instances. If all are blocked, expand Data source diagnostics and share the exact errors. This update does not guarantee public API availability.\n

Moving Decision Assistant has been removed from navigation and source code.


## Current full-repository release (November 2026)

Sidebar: Rent Finder, Lease Updater, Neighborhood Report. There is **no Moving Decision Assistant**.

Rent Finder shows nearby mapped transportation, grocery stores, and schools, plus available Census educational attainment, directly below the rent chart. Official FBI Crime Data Explorer is linked because a verified ZIP-level crime rate is not available from the current sources.

**Important:** External public map servers can fail or rate-limit requests. Expand **Data source diagnostics** to see the error. This release does not guarantee successful live data retrieval. The location reference is the ZIP-area centroid, not the exact apartment.

### Replace the existing GitHub repository contents

1. On the main branch, remove old application files including `moving_assistant.py`. Do not delete the repository.
2. Upload the five files in this ZIP to the repository root, not a subfolder.
3. Commit, then check the Streamlit Cloud app points to this repository, `main`, and `app.py`. Reboot and hard-refresh if necessary.
4. Try ZIP 07102. If a category is unavailable, copy its diagnostic message.


## Google Places API (New) setup

1. In Google Cloud Console, enable billing and **Places API (New)**. Create an API key restricted to Places API (New).
2. In Streamlit Community Cloud, open your app → Settings → Secrets, and add:

```toml
GOOGLE_PLACES_API_KEY = "PASTE_YOUR_KEY_HERE"
```

3. For local development, create `.streamlit/secrets.toml` with the same contents. Never commit this file or your real API key to GitHub.
4. Restart or redeploy your app. Test ZIP 07102 and open Data source diagnostics if an API request fails.

Nearby place lists now use Google Places (New) and show names, addresses, and straight-line distances. The separate Neighborhood Report tab still uses its original OSM integration; the inline neighborhood section under the Rent Finder chart is the part switched to Google Places. Crime statistics are not provided by Places API. Google Places may charge for API calls; set billing alerts and usage quotas.
