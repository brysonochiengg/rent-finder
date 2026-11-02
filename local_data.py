
"""Location facts directly below RentFinder's rent chart."""
import math
import requests
import streamlit as st
from neighborhood_report import geocode_zip, census_profile, find_crime, USER_AGENT

OVERPASS = "https://overpass-api.de/api/interpreter"

def distance_km(lat1,lon1,lat2,lon2):
    p1,p2=math.radians(lat1),math.radians(lat2)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371*2*math.asin(min(1,math.sqrt(a)))

@st.cache_data(ttl=21600,show_spinner=False)
def get_local_places(lat,lon):
    """One combined request for transport, groceries and educational sites."""
    q=f"""[out:json][timeout:35];(
      nwr(around:2000,{lat},{lon})["public_transport"];
      nwr(around:2000,{lat},{lon})["highway"="bus_stop"];
      nwr(around:2000,{lat},{lon})["railway"~"station|halt|tram_stop|subway_entrance"];
      nwr(around:2000,{lat},{lon})["shop"~"supermarket|grocery|convenience"];
      nwr(around:2000,{lat},{lon})["amenity"~"school|college|university|kindergarten"];
    );out center tags;"""
    response=requests.post(OVERPASS,data={"data":q},headers={"User-Agent":USER_AGENT},timeout=48)
    response.raise_for_status()
    found={"Transportation":[],"Grocery stores":[],"Education":[]}
    seen=set()
    for el in response.json().get("elements",[]):
        identity=(el.get("type"),el.get("id"))
        if identity in seen: continue
        seen.add(identity)
        tags=el.get("tags",{})
        coords=el.get("center",el)
        if coords.get("lat") is None or coords.get("lon") is None: continue
        category=None
        if tags.get("shop") in ("supermarket","grocery","convenience"):
            category="Grocery stores"
        elif tags.get("amenity") in ("school","college","university","kindergarten"):
            category="Education"
        elif "public_transport" in tags or tags.get("highway")=="bus_stop" or tags.get("railway") in ("station","halt","tram_stop","subway_entrance"):
            category="Transportation"
        if not category: continue
        km=distance_km(float(lat),float(lon),float(coords["lat"]),float(coords["lon"]))
        found[category].append({"name":tags.get("name") or tags.get("operator") or "Unnamed mapped location",
                                "type":tags.get("shop") or tags.get("amenity") or tags.get("railway") or tags.get("public_transport") or "bus stop",
                                "distance":km})
    for key in found:
        found[key].sort(key=lambda item:item["distance"])
    return found

@st.cache_data(ttl=86400,show_spinner=False)
def place_city_state(lat,lon):
    r=requests.get("https://nominatim.openstreetmap.org/reverse",
        params={"lat":lat,"lon":lon,"format":"jsonv2","addressdetails":1},
        headers={"User-Agent":USER_AGENT},timeout=20)
    r.raise_for_status()
    a=r.json().get("address",{})
    return (a.get("city") or a.get("town") or a.get("village") or a.get("municipality"),
            a.get("state_code") or a.get("state"))

def render_inline_location_analysis(zip_code,resolved_location,typical_rent,yoy_change,observation_month):
    st.divider()
    st.subheader("📍 Local area information")
    st.caption(f"Results for {resolved_location} · ZIP {zip_code}. Locations are measured from the ZIP-code center, not the exact property.")
    try:
        geo=geocode_zip(str(zip_code))
        lat,lon=geo.get("lat"),geo.get("lon")
    except Exception:
        lat=lon=None
    places={}
    if lat is not None and lon is not None:
        try:
            with st.spinner("Finding nearby transportation, stores and schools..."):
                places=get_local_places(float(lat),float(lon))
        except Exception:
            st.info("Mapped nearby locations are temporarily unavailable. Please try again later.")
    else:
        st.info("A map position was not available for this ZIP code.")

    for title,icon in (("Transportation","🚆"),("Grocery stores","🛒"),("Education","🎓")):
        st.markdown(f"#### {icon} {title}")
        items=places.get(title)
        if items is None:
            st.write("Data unavailable.")
        elif not items:
            st.write("No locations returned within 2 km; this does not mean none exist.")
        else:
            st.caption(f"{len(items)} mapped location(s) within 2 km. Showing the nearest 8.")
            for item in items[:8]:
                st.write(f"• **{item['name']}** ({item['type'].replace('_',' ')}) — {item['distance']:.2f} km straight-line distance")

    st.markdown("#### 🚔 Reported crime")
    st.caption("Crime figures are reported by law-enforcement jurisdiction, not by ZIP code or individual street.")
    record=None
    if lat is not None and lon is not None:
        try:
            city,state=place_city_state(float(lat),float(lon))
            if city and state:
                # The legacy city index may use abbreviations; do not infer a match.
                record=find_crime(city,state)
        except Exception:
            pass
    if record:
        fields=[("Violent crime",record.get("violentCrimeRate")),
                ("Property crime",record.get("propertyCrimeRate"))]
        year=record.get("year") or record.get("dataYear")
        if year: st.caption(f"City-level reporting year: {year}")
        for name,value in fields:
            if value is not None:
                st.write(f"• {name}: **{value}** reported offenses per 100,000 people")
        if all(v is None for _,v in fields):
            st.write("No comparable rate fields were available.")
    else:
        st.write("A verified matching city-level crime rate is unavailable from the configured dataset.")
    st.markdown("**Official source for agency-level crime statistics:**")
    st.link_button("View FBI Crime Data Explorer","https://cde.ucr.cjis.gov/")

    st.markdown("#### 📚 Education statistics")
    try:
        census=census_profile(str(zip_code))
        value=census.get("bachelors_plus_pct")
        if value is not None:
            st.metric("Residents age 25+ with bachelor's degree or higher",f"{value:.1f}%")
            st.caption("American Community Survey ZIP-level educational attainment; not a school-quality measure.")
        else:
            st.write("Educational attainment estimate unavailable.")
    except Exception:
        st.write("Census educational attainment estimate unavailable.")
    st.caption("Sources: OpenStreetMap/Overpass (mapped nearby places), Census Reporter/ACS (educational attainment), "
               "configured city crime index where available, and FBI Crime Data Explorer. "
               "Mapped places and official crime reporting may be incomplete or delayed.")
