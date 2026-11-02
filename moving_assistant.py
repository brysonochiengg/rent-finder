
from io import BytesIO
from datetime import date
import streamlit as st
import pandas as pd
from docx import Document
from neighborhood_report import census_profile, geocode_zip, nearby_osm

def currency(v):
    return "Not available" if v is None else f"${v:,.0f}"

def evaluate(zipcode, proposed, income, other):
    result = {"ZIP":zipcode, "Market rent":None, "Transit features":None, "Schools":None}
    try:
        profile = census_profile(zipcode)
        result["Median gross rent"] = profile.get("median_gross_rent")
        result["Education attainment"] = profile.get("bachelors_plus_pct")
    except Exception:
        result["Median gross rent"] = None
        result["Education attainment"] = None
    try:
        point = geocode_zip(zipcode)
        if point.get("lat") and point.get("lon"):
            places = nearby_osm(point["lat"],point["lon"],2000)
            if isinstance(places,dict):
                result["Transit features"] = len(places.get("transit",[]))
                result["Schools"] = len(places.get("schools",[]))
    except Exception:
        pass
    pros, cons, notes = [], [], []
    if proposed and income:
        ratio = proposed / income * 100
        (pros if ratio <= 30 else cons).append(f"Rent is {ratio:.1f}% of entered monthly income.")
    else:
        notes.append("Enter rent and income for an affordability assessment.")
    if result["Median gross rent"] and proposed:
        diff = 100 * (proposed/result["Median gross rent"] - 1)
        (pros if diff < -5 else cons if diff > 10 else notes).append(
            f"Proposed rent is {abs(diff):.1f}% {'below' if diff < 0 else 'above'} ZIP median gross rent. "
            "Gross rent includes some utilities; verify comparability."
        )
    if result["Transit features"] is not None:
        notes.append(f"{result['Transit features']} mapped transit features within 2 km; not a commute-time estimate.")
    if result["Schools"] is not None:
        notes.append(f"{result['Schools']} mapped schools/colleges within 2 km; not school ratings.")
    remaining = income-proposed-other if income else None
    return result,pros,cons,notes,remaining

def report_docx(results, priorities):
    doc=Document()
    doc.add_heading("RentFinder — Moving Decision Report",0)
    doc.add_paragraph(f"Generated {date.today().isoformat()}. Planning draft; verify data before deciding.")
    for name,entry in results.items():
        data, pros, cons, notes, remaining = entry
        doc.add_heading(name,1)
        for key,value in data.items():
            doc.add_paragraph(f"{key}: {value if value is not None else 'Unavailable'}")
        doc.add_paragraph(f"Income remaining after entered expenses: {currency(remaining)}")
        for title,items in [("Potential pros",pros),("Potential cons",cons),("Additional context",notes)]:
            doc.add_heading(title,2)
            for item in items or ["No supported findings available."]:
                doc.add_paragraph(item,style="List Bullet")
    doc.add_heading("Personal priorities",1)
    for key,value in priorities.items(): doc.add_paragraph(f"{key}: {value}%")
    doc.add_paragraph("Area data are not property-specific. Missing information is not a negative score. "
        "Check actual apartment size, condition, utilities, commute, school assignment, flood exposure, "
        "current crime reporting, and lease terms independently.")
    buf=BytesIO(); doc.save(buf); return buf.getvalue()

def render_moving_assistant(resolver, load_zillow_rent_data, lookup_zip, date_columns):
    st.title("⚖️ Moving Decision Assistant")
    st.write("Compare the pros and cons of a proposed move using available public neighborhood data and your budget.")
    st.info("The assessment is evidence-based. Missing information is identified, not guessed.")
    with st.form("moving_decision"):
        compare=st.checkbox("Compare two locations")
        zip_a=st.text_input("Location A: five-digit ZIP code",max_chars=5)
        zip_b=st.text_input("Location B: five-digit ZIP code",max_chars=5,disabled=not compare)
        income=st.number_input("Monthly household income ($)",min_value=0.0,value=0.0,step=100.0)
        rent_a=st.number_input("Proposed monthly rent A ($)",min_value=0.0,value=0.0,step=50.0)
        rent_b=st.number_input("Proposed monthly rent B ($)",min_value=0.0,value=0.0,step=50.0,disabled=not compare)
        other=st.number_input("Other monthly expenses ($)",min_value=0.0,value=0.0,step=50.0)
        moving=st.number_input("One-time moving expenses ($)",min_value=0.0,value=0.0,step=100.0)
        st.caption("Priorities appear in the report; no unsupported numerical neighborhood score is invented.")
        priorities={}
        defaults={"Affordability":30,"Transportation":20,"Education":10,"Healthcare":10,"Environment":10,"Lifestyle":20}
        for key,default in defaults.items():
            priorities[key]=st.slider(key,0,100,default,key="move_"+key)
        submit=st.form_submit_button("Generate moving report",type="primary")
    if not submit: return
    if sum(priorities.values())!=100:
        st.error("Your priorities must total 100%."); return
    inputs=[("Location A",zip_a,rent_a)]
    if compare: inputs.append(("Location B",zip_b,rent_b))
    if any(len(z)!=5 or not z.isdigit() for _,z,_ in inputs):
        st.error("Enter a valid five-digit ZIP for each location."); return
    results={}
    for name,zipcode,rent in inputs:
        with st.spinner(f"Analyzing {zipcode}..."):
            results[name]=evaluate(zipcode,rent,income,other)
        data,pros,cons,notes,remaining=results[name]
        st.subheader(f"{name} — {zipcode}")
        a,b,c=st.columns(3)
        a.metric("Proposed rent",currency(rent if rent else None))
        b.metric("ZIP median gross rent",currency(data.get("Median gross rent")))
        c.metric("Remaining monthly income",currency(remaining))
        st.markdown("**Potential advantages**")
        for x in pros: st.success(x)
        if not pros: st.caption("No clear advantages supported by available inputs.")
        st.markdown("**Potential drawbacks**")
        for x in cons: st.warning(x)
        if not cons: st.caption("No clear drawbacks supported by available inputs.")
        with st.expander("Context and missing data"):
            for x in notes: st.write("• "+x)
            st.write("Still verify apartment square footage, photos, actual commute, nearby healthcare, "
                     "current crime statistics, flood exposure and local amenities.")
    if compare:
        st.subheader("Side-by-side")
        st.dataframe(pd.DataFrame([{"Metric":"Proposed rent","A":currency(rent_a),"B":currency(rent_b)},
            {"Metric":"ZIP median gross rent","A":currency(results["Location A"][0].get("Median gross rent")),
             "B":currency(results["Location B"][0].get("Median gross rent"))}]),hide_index=True)
    st.write(f"Estimated one-time moving expenses: {currency(moving)}")
    st.download_button("Download moving report (.docx)",report_docx(results,priorities),
        file_name=f"moving_report_{date.today().isoformat()}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
