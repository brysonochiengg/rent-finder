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
