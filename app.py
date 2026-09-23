from io import BytesIO
import re
from datetime import date

import pandas as pd
import requests
import streamlit as st
from pypdf import PdfReader
from docx import Document
from neighborhood_report import render_neighborhood_report

# -------------------------------------------------
# Public rental data
# -------------------------------------------------

ZORI_ZIP_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Zip_zori_uc_sfrcondomfr_sm_month.csv"
)

CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
)

st.set_page_config(
    page_title="RentFinder",
    page_icon="🏠",
    layout="centered",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 950px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        .hero {
            padding: 1.8rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #111827, #1f2937);
            color: white;
            margin-bottom: 1.5rem;
        }

        .hero h1 {
            margin: 0;
            font-size: 2.5rem;
        }

        .hero p {
            margin-top: .55rem;
            margin-bottom: 0;
            color: #d1d5db;
            font-size: 1.05rem;
        }

        .rent-card, .lease-card {
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 1.4rem;
            margin-top: 1rem;
        }

        .rent-big {
            font-size: 2.8rem;
            font-weight: 800;
            margin: .15rem 0;
        }

        .muted {
            color: #6b7280;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# RENT FINDER FUNCTIONS
# =========================================================

def extract_zip(text: str):
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    return match.group(1) if match else None


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def load_zillow_rent_data():
    response = requests.get(ZORI_ZIP_URL, timeout=45)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        dtype={"RegionName": str},
        low_memory=False,
    )

    df["RegionName"] = (
        df["RegionName"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )

    return df


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def geocode_address_to_zip(address: str):
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }

    response = requests.get(
        CENSUS_GEOCODER_URL,
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    matches = response.json().get("result", {}).get("addressMatches", [])

    if not matches:
        raise LookupError(
            "I couldn't match that address. Try entering the 5-digit ZIP code directly."
        )

    match = matches[0]
    matched_address = match.get("matchedAddress", "")
    zip_code = extract_zip(matched_address)

    if not zip_code:
        geographies = match.get("geographies", {})

        for geography_group in geographies.values():
            if not isinstance(geography_group, list):
                continue

            for record in geography_group:
                for key in ("ZIP", "ZCTA5", "ZCTA5CE20", "ZCTA5CE10"):
                    value = record.get(key)
                    if value and re.fullmatch(r"\d{5}", str(value)):
                        zip_code = str(value)
                        break

                if zip_code:
                    break

            if zip_code:
                break

    if not zip_code:
        raise LookupError(
            "The address was matched, but I couldn't determine its ZIP code. "
            "Enter the ZIP code directly."
        )

    return zip_code, matched_address or address


def resolve_location(location: str):
    direct_zip = extract_zip(location)

    if direct_zip and len(location.strip()) <= 10:
        return direct_zip, f"ZIP {direct_zip}"

    if direct_zip and ("," in location or any(c.isalpha() for c in location)):
        return direct_zip, location.strip()

    return geocode_address_to_zip(location.strip())


def date_columns(df: pd.DataFrame):
    columns = []

    for col in df.columns:
        try:
            pd.to_datetime(col, format="%Y-%m-%d")
            columns.append(col)
        except (ValueError, TypeError):
            continue

    return sorted(columns)


def lookup_zip(df: pd.DataFrame, zip_code: str):
    match = df[df["RegionName"] == zip_code]

    if match.empty:
        raise LookupError(
            f"Zillow's ZIP-level rent dataset does not currently contain ZIP {zip_code}."
        )

    return match.iloc[0]


def money(value):
    if pd.isna(value):
        return "N/A"
    return f"${float(value):,.0f}"


def pct(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):+.1f}%"


# =========================================================
# LEASE UPDATER FUNCTIONS
# =========================================================

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December|Jan|Feb|Mar|Apr|"
    "Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

DATE_PATTERNS = [
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
]

DATE_RE = re.compile("|".join(f"(?:{p})" for p in DATE_PATTERNS), re.IGNORECASE)


def extract_lease_text(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    raw = uploaded_file.getvalue()

    if suffix == ".pdf":
        reader = PdfReader(BytesIO(raw))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)

    elif suffix == ".docx":
        doc = Document(BytesIO(raw))
        chunks = [p.text for p in doc.paragraphs]

        for table in doc.tables:
            for row in table.rows:
                chunks.append(" | ".join(cell.text for cell in row.cells))

        text = "\n".join(chunks)

    elif suffix == ".txt":
        text = raw.decode("utf-8", errors="replace")

    else:
        raise ValueError("Unsupported file type.")

    if not text.strip():
        raise ValueError(
            "No readable text was found. Scanned/image-only PDFs are not supported "
            "in this version."
        )

    return text


def find_dates(text):
    dates = []
    seen = set()

    for match in DATE_RE.finditer(text):
        value = match.group(0)
        key = value.lower()

        if key not in seen:
            seen.add(key)
            dates.append(value)

    return dates


def replace_dates(text, replacements):
    result = text

    # Replace longer strings first.
    for old, new in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = re.sub(
            re.escape(old),
            new,
            result,
            flags=re.IGNORECASE,
        )

    return result


def build_docx(text, source_name):
    doc = Document()
    doc.add_heading("Updated Lease Draft", level=1)

    p = doc.add_paragraph()
    p.add_run("Source file: ").bold = True
    p.add_run(source_name)

    p = doc.add_paragraph()
    p.add_run("Generated: ").bold = True
    p.add_run(date.today().strftime("%B %d, %Y"))

    warning = doc.add_paragraph()
    run = warning.add_run(
        "DRAFT FOR REVIEW — Dates were automatically updated. "
        "Review all terms before signing or relying on this document."
    )
    run.bold = True

    doc.add_paragraph("")

    for line in text.splitlines():
        doc.add_paragraph(line)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


# =========================================================
# UI: RENT FINDER
# =========================================================

def render_rent_finder():
    st.markdown(
        """
        <div class="hero">
            <h1>🏠 RentFinder</h1>
            <p>
                Find the typical asking rent for a U.S. ZIP code or street address.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("rent_search"):
        location = st.text_input(
            "Location",
            placeholder="Example: 07102 or 123 Main St, Newark, NJ",
        )

        submitted = st.form_submit_button(
            "Find rent",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    if not location.strip():
        st.error("Enter a ZIP code or full street address.")
        return

    try:
        with st.spinner("Finding rental market data..."):
            zip_code, resolved_location = resolve_location(location)
            df = load_zillow_rent_data()
            row = lookup_zip(df, zip_code)
            monthly_columns = date_columns(df)

        available = [
            col for col in monthly_columns
            if col in row.index and not pd.isna(row[col])
        ]

        if not available:
            raise LookupError(
                f"No usable rent observations were found for ZIP {zip_code}."
            )

        latest_col = available[-1]
        latest_value = float(row[latest_col])
        latest_date = pd.to_datetime(latest_col)

        previous_value = float(row[available[-2]]) if len(available) >= 2 else None

        mom_change = None
        if previous_value:
            mom_change = ((latest_value / previous_value) - 1) * 100

        target_yoy_date = latest_date - pd.DateOffset(years=1)
        dates_map = {pd.to_datetime(col): col for col in available}

        yoy_value = None

        if dates_map:
            closest = min(
                dates_map.keys(),
                key=lambda d: abs((d - target_yoy_date).days),
            )

            if abs((closest - target_yoy_date).days) <= 45:
                yoy_value = float(row[dates_map[closest]])

        yoy_change = None
        if yoy_value:
            yoy_change = ((latest_value / yoy_value) - 1) * 100

        st.success(f"Rental data found for ZIP {zip_code}")

        st.markdown(
            f"""
            <div class="rent-card">
                <div class="muted">Typical monthly asking rent</div>
                <div class="rent-big">{money(latest_value)}</div>
                <div class="muted">
                    ZIP {zip_code} • {latest_date.strftime("%B %Y")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        c1.metric("Month-over-month", pct(mom_change))
        c2.metric("Year-over-year", pct(yoy_change))

        st.caption(f"Search resolved as: {resolved_location}")

        recent = available[-24:]
        history = pd.DataFrame(
            {
                "Month": pd.to_datetime(recent),
                "Typical Asking Rent": [float(row[col]) for col in recent],
            }
        ).set_index("Month")

        st.subheader("Rent trend")
        st.line_chart(history, use_container_width=True)

    except Exception as exc:
        st.error(str(exc))


# =========================================================
# UI: LEASE UPDATER
# =========================================================

def render_lease_updater():
    st.markdown(
        """
        <div class="hero">
            <h1>📄 Lease Updater</h1>
            <p>
                Upload a lease, detect its dates, and generate an updated draft
                using today's date.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.warning(
        "This creates a new draft and does not alter the original lease. "
        "Changing lease dates can affect legal rights and obligations, so review "
        "the generated document before signing or using it."
    )

    uploaded = st.file_uploader(
        "Upload lease",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=False,
    )

    if not uploaded:
        st.info("Upload a PDF, DOCX, or TXT lease to begin.")
        return

    try:
        with st.spinner("Reading lease..."):
            text = extract_lease_text(uploaded)

        dates = find_dates(text)

        st.success(f"Loaded {uploaded.name}")

        with st.expander("Preview extracted lease text"):
            st.text_area(
                "Lease text",
                value=text,
                height=350,
                disabled=True,
                label_visibility="collapsed",
            )

        if not dates:
            st.info(
                "No standard-form dates were detected in this lease."
            )
            return

        today_default = date.today().strftime("%B %d, %Y")

        st.subheader("Dates detected")
        st.caption(
            "Choose which dates should be replaced. Each selected date defaults "
            "to today's date."
        )

        replacements = {}

        for i, old_date in enumerate(dates):
            st.markdown('<div class="lease-card">', unsafe_allow_html=True)

            col1, col2 = st.columns([1, 2])

            with col1:
                selected = st.checkbox(
                    f"Update {old_date}",
                    value=True,
                    key=f"lease_date_check_{i}",
                )

            with col2:
                new_date = st.text_input(
                    "Replacement date",
                    value=today_default,
                    key=f"lease_date_value_{i}",
                    disabled=not selected,
                )

            if selected and new_date.strip():
                replacements[old_date] = new_date.strip()

            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        if st.button(
            "Generate updated lease draft",
            type="primary",
            use_container_width=True,
        ):
            if not replacements:
                st.error("Select at least one date to update.")
                return

            updated_text = replace_dates(text, replacements)
            updated_docx = build_docx(updated_text, uploaded.name)

            st.session_state["updated_lease_text"] = updated_text
            st.session_state["updated_lease_docx"] = updated_docx
            st.session_state["updated_lease_name"] = (
                f"{Path(uploaded.name).stem}_updated_{date.today().isoformat()}.docx"
            )

        if "updated_lease_text" in st.session_state:
            st.success("Updated lease draft created.")

            st.subheader("Preview updated draft")

            st.text_area(
                "Updated lease",
                value=st.session_state["updated_lease_text"],
                height=400,
                disabled=True,
                label_visibility="collapsed",
            )

            st.download_button(
                "Download updated lease draft (.docx)",
                data=st.session_state["updated_lease_docx"],
                file_name=st.session_state["updated_lease_name"],
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                use_container_width=True,
            )

    except Exception as exc:
        st.error(str(exc))


# =========================================================
# MAIN NAVIGATION
# =========================================================

st.sidebar.title("RentFinder")

page = st.sidebar.radio(
    "Choose a tool",
    [
        "🏠 Rent Finder",
        "📄 Lease Updater",
        "📊 Neighborhood Report",
    ],
)

if page == "🏠 Rent Finder":
    render_rent_finder()
elif page == "📄 Lease Updater":
    render_lease_updater()
else:
    render_neighborhood_report(resolve_location, load_zillow_rent_data, lookup_zip, date_columns)

st.sidebar.caption(
    "Rent data: Zillow Research ZORI. "
    "Address lookup: U.S. Census Bureau."
)
