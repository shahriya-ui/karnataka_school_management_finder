# app.py
import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import html

# ---------- CONFIG ----------
DATAFILE = "karnataka_schools.xlsx"   # put file in repo root for Streamlit Cloud / Colab
SCORE_THRESHOLD = 75                  # high tolerance (less results, more accurate)
MAX_RESULTS = 5
# ----------------------------

st.set_page_config(page_title="Karnataka School Finder", layout="wide")

# ---------- Blue official CSS ----------
st.markdown(
    """
    <style>
        .stApp { background-color: #ffffff; }
        .header { font-size:28px; font-weight:700; color:#0A3D62; margin-bottom:6px; }
        .sub { color:#0A3D62; margin-bottom: 14px; }
        .card {
            background: #ffffff;
            padding: 14px;
            border-radius:10px;
            margin-bottom: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            border-left: 6px solid #0A3D62;
        }
        .label { color:#0A3D62; font-weight:600; }
        .small { font-size:13px; color:#444; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="header">Karnataka School Finder</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Select a district, type a school name (typos allowed). Click a school to view details.</div>', unsafe_allow_html=True)

# ---------- Load data ----------
@st.cache_data
def load_data(path=DATAFILE):
    try:
        df_local = pd.read_excel(path)
    except Exception:
        return pd.DataFrame()
    # drop unnamed index cols
    df_local = df_local.loc[:, ~df_local.columns.str.contains('^Unnamed')]
    # normalize column names & whitespace
    df_local.columns = df_local.columns.str.strip()
    # ensure expected columns exist
    for c in ['school_name','village','district','block','state_mgmt','school_category','school_type','school_status','udise_code']:
        if c in df_local.columns:
            df_local[c] = df_local[c].astype(str).str.strip()
        else:
            df_local[c] = ""
    # lowercase helper columns for matching
    df_local['school_name_lower'] = df_local['school_name'].str.lower()
    df_local['village_lower'] = df_local['village'].str.lower()
    return df_local

df = load_data()

# If dataset not found in repo root, show uploader
if df.empty:
    st.warning("Dataset not found in app root. Please upload `karnataka_schools.xlsx` (Excel file).")
    uploaded = st.file_uploader("Upload Karnataka Excel file", type=["xlsx"])
    if uploaded:
        df = pd.read_excel(uploaded)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df.columns = df.columns.str.strip()
        for c in ['school_name','village','district','block','state_mgmt','school_category','school_type','school_status','udise_code']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
            else:
                df[c] = ""
        df['school_name_lower'] = df['school_name'].str.lower()
        df['village_lower'] = df['village'].str.lower()

# ---------- Management mapping (clean labels) ----------
def map_management(raw):
    if not raw or str(raw).strip() == "":
        return "Not available"
    r = str(raw).strip().lower()
    # common patterns -> normalized label
    if "department of education" in r or "dept of education" in r or "education" in r and "private" not in r:
        return "Government"
    if "private" in r and "aided" in r:
        return "Private Aided"
    if "private" in r or "unaided" in r or "unaided" in r:
        return "Private Unaided"
    if "aided" in r and "private" not in r:
        return "Government Aided"
    if "central" in r or "kvs" in r or "navodaya" in r or "central government" in r:
        return "Central Government"
    if "local" in r or "panchayat" in r or "municipal" in r or "local body" in r:
        return "Local Body"
    # fallback: capitalize words
    return str(raw).strip().title()

# ---------- UI controls ----------
districts = sorted(df['district'].dropna().unique().tolist())
districts_display = ["All Districts"] + districts
selected_district = st.selectbox("Select District:", districts_display, index=0)

school_query = st.text_input("School name (type partial name; typos allowed):")

st.write("---")

# ---------- Helper: fuzzy search inside a df subset ----------
def fuzzy_search_in_df(name_query, df_subset, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS):
    if name_query is None or name_query.strip() == "":
        return pd.DataFrame()
    choices = df_subset['school_name'].dropna().tolist()
    matches = process.extract(name_query, choices, scorer=fuzz.WRatio, limit=200)
    good = [m for m in matches if m[1] >= threshold]
    good_sorted = sorted(good, key=lambda x: x[1], reverse=True)[:max_results]
    if not good_sorted:
        return pd.DataFrame()
    matched_names = [m[0] for m in good_sorted]
    score_map = {m[0]: m[1] for m in good_sorted}
    result_rows = df_subset[df_subset['school_name'].isin(matched_names)].copy()
    result_rows['match_score'] = result_rows['school_name'].map(score_map).fillna(0).astype(int)
    result_rows = result_rows.sort_values(by='match_score', ascending=False)
    result_rows = result_rows.drop_duplicates(subset=['school_name'], keep='first')
    return result_rows

# ---------- Perform search ----------
results = pd.DataFrame()
if school_query and df.shape[0] > 0:
    if selected_district != "All Districts":
        subset = df[df['district'].astype(str).str.strip().str.lower() == selected_district.strip().lower()]
    else:
        subset = df.copy()
    if subset.empty:
        st.info("No schools found in selected district. Try 'All Districts' or different district.")
    else:
        q = school_query.strip().lower()
        partials = subset[subset['school_name_lower'].str.contains(q, na=False)]
        if not partials.empty:
            results = fuzzy_search_in_df(school_query, partials, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS)
        else:
            results = fuzzy_search_in_df(school_query, subset, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS)

# ---------- Display results as clickable expanders ----------
if results.empty:
    if school_query:
        st.warning(f"No strong matches found (≥ {SCORE_THRESHOLD}%). Try adding more of the name or change district.")
    else:
        st.info("Select a district and type a school name to start searching.")
else:
    st.success(f"Showing {min(len(results), MAX_RESULTS)} best match(es) (confidence % shown).")
    # for readability: loop through rows and build expanders
    for _, row in results.iterrows():
        name = row['school_name']
        score = int(row.get('match_score', 0))
        village = row.get('village', "")
        block = row.get('block', "")
        district = row.get('district', "")
        udise = row.get('udise_code', "")
        management_raw = row.get('state_mgmt', "")
        management = map_management(management_raw)
        status = row.get('school_status', "")
        header = f"{name}  —  {village if village else block if block else district}  ({score}%)"
        with st.expander(header):
            # show minimal official fields in two columns
            col1, col2 = st.columns([2,1])
            with col1:
                st.markdown(f"**School Name:** {html.escape(str(name))}")
                st.markdown(f"**District:** {html.escape(str(district))}")
                st.markdown(f"**Block:** {html.escape(str(block))}")
                st.markdown(f"**Village:** {html.escape(str(village))}")
            with col2:
                st.markdown(f"**Management:** {html.escape(str(management))}")
                st.markdown(f"**Status:** {html.escape(str(status))}")
                st.markdown(f"**UDISE:** {html.escape(str(udise))}")
            # small note
            st.markdown('<div class="small">If details look incorrect, try selecting a different district or refine the school name.</div>', unsafe_allow_html=True)
