"""Reliable, independently loaded local facts under RentFinder chart."""
import math
import requests
import streamlit as st

HEADERS = {'User-Agent': 'RentFinder/2.1 (public neighborhood research app)'}
OVERPASS_SERVERS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://overpass.nchc.org.tw/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]


def _get(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=18, **kwargs)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400, show_spinner=False)
def zip_location(zip_code):
    """Try US ZIP directory first, then OpenStreetMap geocoding."""
    errors=[]
    try:
        obj=_get(f'https://api.zippopotam.us/us/{zip_code}')
        place=obj['places'][0]
        return float(place['latitude']), float(place['longitude']), place['place name'], place['state abbreviation']
    except Exception as exc:
        errors.append(f'ZIP lookup: {type(exc).__name__}')
    try:
        data=_get('https://nominatim.openstreetmap.org/search',params={
            'postalcode':zip_code,'country':'United States','format':'jsonv2','limit':1})
        if data:
            return float(data[0]['lat']),float(data[0]['lon']),None,None
    except Exception as exc:
        errors.append(f'Backup geocoder: {type(exc).__name__}')
    raise RuntimeError('; '.join(errors) or 'No coordinates found for ZIP')


def _km(lat,lon,lat2,lon2):
    a=math.sin(math.radians(lat2-lat)/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon)/2)**2
    return 12742*math.asin(min(1,math.sqrt(a)))


# Google Places API (New): requests are server-side and the key is never displayed.
GOOGLE_PLACES_ENDPOINT = 'https://places.googleapis.com/v1/places:searchNearby'
CATEGORY_TYPES = {
    'Transportation': ['transit_station', 'train_station', 'subway_station', 'bus_station', 'bus_stop'],
    'Grocery stores': ['supermarket', 'grocery_store'],
    'Schools and colleges': ['school', 'primary_school', 'secondary_school', 'university'],
}


def _places_key():
    try:
        return str(st.secrets.get('GOOGLE_PLACES_API_KEY', '')).strip()
    except Exception:
        return ''


@st.cache_data(ttl=3600, show_spinner=False)
def nearby_category(lat, lon, group, api_key, radius_m=2500):
    body = {
        'includedTypes': CATEGORY_TYPES[group],
        'maxResultCount': 20,
        'rankPreference': 'DISTANCE',
        'locationRestriction': {'circle': {
            'center': {'latitude': float(lat), 'longitude': float(lon)},
            'radius': float(radius_m),
        }},
    }
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': 'places.id,places.displayName,places.formattedAddress,places.location,places.primaryType',
    }
    try:
        response = requests.post(GOOGLE_PLACES_ENDPOINT, json=body, headers=headers, timeout=(8, 25))
    except requests.RequestException as exc:
        raise RuntimeError(f'Google Places network error: {type(exc).__name__}: {exc}') from exc
    if not response.ok:
        try:
            message = response.json().get('error', {}).get('message', '')
        except ValueError:
            message = response.text[:160]
        raise RuntimeError(f'Google Places HTTP {response.status_code}: {message[:220]}')
    try:
        places = response.json().get('places', [])
    except ValueError as exc:
        raise RuntimeError('Google Places returned invalid JSON') from exc
    output = []
    seen = set()
    for place in places:
        place_id = place.get('id')
        if place_id in seen:
            continue
        seen.add(place_id)
        location = place.get('location') or {}
        if 'latitude' not in location or 'longitude' not in location:
            continue
        name = (place.get('displayName') or {}).get('text', '')
        if not name:
            continue
        distance = _km(lat, lon, float(location['latitude']), float(location['longitude']))
        output.append((name, (place.get('primaryType') or 'place').replace('_', ' '), distance, place.get('formattedAddress', '')))
    output.sort(key=lambda row: row[2])
    return output


def nearby_places(lat, lon, api_key):
    results, failures = {}, []
    for group in CATEGORY_TYPES:
        try:
            results[group] = nearby_category(lat, lon, group, api_key)
        except Exception as exc:
            results[group] = None
            failures.append(f'{group}: {exc}')
    return results, failures


@st.cache_data(ttl=86400,show_spinner=False)
def education(zip_code):
    """ACS education by ZIP tabulation area; public Census API fallback to Census Reporter."""
    errors=[]
    try:
        from neighborhood_report import census_profile
        value=census_profile(zip_code).get('bachelors_plus_pct')
        if value is not None: return float(value),'Census Reporter / ACS'
    except Exception as exc:
        errors.append(f'Census Reporter: {type(exc).__name__}')
    for year in (2024,2023,2022):
        try:
            data=_get(f'https://api.census.gov/data/{year}/acs/acs5',params={
                'get':'NAME,B15003_001E,B15003_022E,B15003_023E,B15003_024E,B15003_025E',
                'for':f'zip code tabulation area:{zip_code}'})
            row=dict(zip(data[0],data[1]))
            total=int(row['B15003_001E'])
            if total <= 0: continue
            grads=sum(max(0,int(row[f'B15003_0{i}E'])) for i in (22,23,24,25))
            return grads/total*100,f'US Census ACS 5-year {year}'
        except Exception as exc:
            errors.append(f'ACS {year}: {type(exc).__name__}')
    raise RuntimeError('; '.join(errors))


def render_inline_location_analysis(zip_code,resolved_location,typical_rent,yoy_change,observation_month):
    st.divider()
    st.subheader('📍 Nearby transportation, groceries, crime & education')
    st.caption(f'For {resolved_location} (ZIP {zip_code}). Nearby distances are from the ZIP-area reference point, not a specific apartment.')
    errors=[]
    lat=lon=city=state=None
    try:
        lat,lon,city,state=zip_location(str(zip_code).zfill(5))
        st.caption(f'Location reference: {city or "ZIP area"}{", " + state if state else ""}. Search radius: 2.5 km.')
    except Exception as exc:
        errors.append(f'Location lookup failed: {exc}')
    places=None
    api_key = _places_key()
    if not api_key:
        errors.append('Missing GOOGLE_PLACES_API_KEY in Streamlit Secrets. Add it before searching for nearby places.')
    elif lat is not None:
        places, place_errors = nearby_places(lat, lon, api_key)
        errors.extend(place_errors)
    for group,emoji in [('Transportation','🚆'),('Grocery stores','🛒'),('Schools and colleges','🎓')]:
        st.markdown(f'#### {emoji} {group}')
        if places is None or places[group] is None:
            st.warning(f'Could not retrieve {group.lower()} from the map providers. Open diagnostics below for details.')
        elif not places[group]:
            st.write('No mapped locations returned within 2.5 km. This does not prove none exist.')
        else:
            st.caption(f'{len(places[group])} mapped locations; nearest 10 shown.')
            for name, kind, km, address in places[group][:10]:
                st.write(f'• **{name}** ({kind}) — {km:.2f} km straight-line distance')
                if address:
                    st.caption(address)
    st.markdown('#### 🚔 Crime statistics')
    st.write('Crime rates are published by reporting agency or municipality, not reliably by ZIP code. This app does not invent a ZIP crime rate.')
    st.link_button('Look up official local crime statistics (FBI)', 'https://cde.ucr.cjis.gov/')
    with st.expander('🔧 Data source diagnostics',expanded=bool(errors)):
        if errors:
            for err in errors: st.code(err)
        else:
            st.success('Available automatic data sources responded successfully.')
        st.caption('Sources: Zippopotam / OpenStreetMap backup geocoding, Google Places API (New), US Census ACS. Google Places usage may incur charges; results are limited to 20 per category.')
