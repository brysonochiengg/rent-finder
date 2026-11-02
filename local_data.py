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


@st.cache_data(ttl=21600,show_spinner=False)
def nearby_places(lat,lon):
    q=f'''[out:json][timeout:20];(
      nwr(around:2500,{lat},{lon})["public_transport"];
      nwr(around:2500,{lat},{lon})["highway"="bus_stop"];
      nwr(around:2500,{lat},{lon})["railway"~"station|halt|tram_stop|subway_entrance"];
      nwr(around:2500,{lat},{lon})["shop"~"supermarket|grocery|convenience"];
      nwr(around:2500,{lat},{lon})["amenity"~"school|college|university|kindergarten"];
    );out center tags;'''
    errors=[]
    for endpoint in OVERPASS_SERVERS:
      for method in ('GET',):
        try:
            if method == 'GET':
                r=requests.get(endpoint,params={'data':q},headers=HEADERS,timeout=12)
            else:
                r=requests.post(endpoint,data={'data':q},headers=HEADERS,timeout=12)
            r.raise_for_status()
            payload=r.json()
            elements=payload['elements']
            result={'Transportation':[],'Grocery stores':[],'Schools and colleges':[]}
            seen=set()
            for item in elements:
                key=(item.get('type'),item.get('id'))
                if key in seen: continue
                seen.add(key)
                tags=item.get('tags') or {}
                loc=item.get('center') or item
                if loc.get('lat') is None or loc.get('lon') is None: continue
                if tags.get('shop') in ('supermarket','grocery','convenience'):
                    group='Grocery stores'
                elif tags.get('amenity') in ('school','college','university','kindergarten'):
                    group='Schools and colleges'
                elif ('public_transport' in tags or tags.get('highway')=='bus_stop' or tags.get('railway') in ('station','halt','tram_stop','subway_entrance')):
                    group='Transportation'
                else: continue
                name=tags.get('name') or tags.get('operator') or 'Unnamed mapped stop/location'
                kind=tags.get('shop') or tags.get('amenity') or tags.get('railway') or tags.get('public_transport') or 'bus stop'
                result[group].append((name,kind,_km(lat,lon,float(loc['lat']),float(loc['lon']))))
            for group in result: result[group].sort(key=lambda x:x[2])
            return result
        except Exception as exc:
            errors.append(f'{endpoint.split("/")[2]} [{method}]: {type(exc).__name__} ({str(exc)[:90]})')
    raise RuntimeError('; '.join(errors))


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
    if lat is not None:
        try: places=nearby_places(lat,lon)
        except Exception as exc: errors.append(f'Mapped places failed: {exc}')
    for group,emoji in [('Transportation','🚆'),('Grocery stores','🛒'),('Schools and colleges','🎓')]:
        st.markdown(f'#### {emoji} {group}')
        if places is None:
            st.info('Could not load mapped places right now.')
        elif not places[group]:
            st.write('No mapped locations returned within 2.5 km. This does not prove none exist.')
        else:
            st.caption(f'{len(places[group])} mapped locations; nearest 10 shown.')
            for name,kind,km in places[group][:10]:
                st.write(f'• **{name}** ({kind.replace("_"," ")}) — {km:.2f} km straight-line distance')
    st.markdown('#### 🚔 Crime statistics')
    st.write('Crime rates are published by reporting agency or municipality, not reliably by ZIP code. This app does not invent a ZIP crime rate.')
    st.link_button('Look up official local crime statistics (FBI)', 'https://cde.ucr.cjis.gov/')
    st.markdown('#### 📚 Education statistics')
    try:
        pct,source=education(str(zip_code).zfill(5))
        st.metric('Adults 25+ with bachelor’s degree or higher',f'{pct:.1f}%')
        st.caption(f'{source}; educational attainment is not a school-quality rating.')
    except Exception as exc:
        st.info('Education estimate could not be loaded.')
        errors.append(f'Education data failed: {exc}')
    with st.expander('🔧 Data source diagnostics',expanded=bool(errors)):
        if errors:
            for err in errors: st.code(err)
        else:
            st.success('Available automatic data sources responded successfully.')
        st.caption('Sources: Zippopotam / OpenStreetMap geocoding, OpenStreetMap Overpass, US Census ACS. Public APIs can be rate-limited or temporarily offline.')
