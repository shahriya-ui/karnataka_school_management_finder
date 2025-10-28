# app.py
import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import html

# ---------- CONFIG ----------
DATAFILE = "karnataka_schools.xlsx"   # put file in repo root for Streamlit Cloud
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
        .verify-btn {
            background-color:#0A3D62;
            color:white;
            padding:8px 12px;
            border-radius:6px;
            text-decoration:none;
            display:inline-block;
            margin-top:6px;
        }
        .small { font-size:13px; color:#444; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="header">Karnataka School Finder</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Select a district, type a school name (typos allowed). Shows up to 5 accurate matches.</div>', unsafe_allow_html=True)

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
    for c in ['school_name','village','district','block','state_mgmt','school_category','school_type','school_status','udise_code']:
        if c in df_local.columns:
            df_local[c] = df_local[c].astype(str).str.strip()
        else:
            # ensure column exists to avoid KeyErrors later
            df_local[c] = df_local.get(c, "")
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
                df[c] = df.get(c, "")
        df['school_name_lower'] = df['school_name'].str.lower()
        df['village_lower'] = df['village'].str.lower()

# ---------- UI controls ----------
# District dropdown (All + sorted list)
districts = sorted(df['district'].dropna().unique().tolist())
districts_display = ["All Districts"] + districts
selected_district = st.selectbox("Select District:", districts_display, index=0)

# School name input
school_query = st.text_input("School name (type partial name; typos allowed):")

st.write("---")

# ---------- Helper: fuzzy search inside a df subset ----------
def fuzzy_search_in_df(name_query, df_subset, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS):
    if name_query is None or name_query.strip() == "":
        return pd.DataFrame()
    # build choices
    choices = df_subset['school_name'].dropna().tolist()
    # get matches with scores
    matches = process.extract(name_query, choices, scorer=fuzz.WRatio, limit=200)
    # filter by threshold
    good = [m for m in matches if m[1] >= threshold]
    # sort by score desc and keep up to max_results distinct names
    good_sorted = sorted(good, key=lambda x: x[1], reverse=True)[:max_results]
    if not good_sorted:
        return pd.DataFrame()
    matched_names = [m[0] for m in good_sorted]
    # preserve score mapping so we can show confidence
    score_map = {m[0]: m[1] for m in good_sorted}
    result_rows = df_subset[df_subset['school_name'].isin(matched_names)].copy()
    # attach match_score (use score_map by name)
    result_rows['match_score'] = result_rows['school_name'].map(score_map).fillna(0).astype(int)
    # order by match_score desc
    result_rows = result_rows.sort_values(by='match_score', ascending=False)
    # deduplicate by school_name keeping highest score row (if duplicates exist)
    result_rows = result_rows.drop_duplicates(subset=['school_name'], keep='first')
    return result_rows

# ---------- Perform search ----------
results = pd.DataFrame()
if school_query and df.shape[0] > 0:
    # filter by district if specified
    if selected_district != "All Districts":
        subset = df[df['district'].astype(str).str.strip().str.lower() == selected_district.strip().lower()]
    else:
        subset = df.copy()
    if subset.empty:
        st.info("No schools found in selected district. Try 'All Districts' or different district.")
    else:
        # First try quick exact/partial case-insensitive contains (fast)
        q = school_query.strip().lower()
        partials = subset[subset['school_name_lower'].str.contains(q, na=False)]
        if not partials.empty:
            # compute fuzzy scores for these and pick top matches
            results = fuzzy_search_in_df(school_query, partials, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS)
        else:
            # no direct partials → run fuzzy on entire subset
            results = fuzzy_search_in_df(school_query, subset, threshold=SCORE_THRESHOLD, max_results=MAX_RESULTS)

# ---------- Display results ----------
if results.empty:
    if school_query:
        st.warning("No strong matches found (≥ 75%). Try adding more of the name or change district.")
    else:
        st.info("Select a district and type a school name to start searching.")
else:
    st.success(f"Showing {min(len(results), MAX_RESULTS)} best match(es) (confidence % shown).")
    # build display rows with minimal official fields
    display_cols = ['school_name','udise_code','district','block','village','match_score']
    display_df = results[display_cols].copy()
    display_df = display_df.rename(columns={
        'school_name': 'School Name',
        'udise_code': 'UDISE',
        'district': 'District',
        'block': 'Block',
        'village': 'Village',
        'match_score': 'Confidence (%)'
    })
    # Round/format confidence
    display_df['Confidence (%)'] = display_df['Confidence (%)'].astype(int)
    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)

    # Show details card for selected school (optional)
    # Let user pick one to view full small card
    labels = display_df['School Name'].tolist()
    sel = st.selectbox("Select a school to view details:", ["-- pick --"] + labels)
    if sel != "-- pick --":
        chosen = results[results['school_name'] == sel].iloc[0]
        # Build simple official card
        def s(x): return html.escape(str(x)) if pd.notna(x) else "-"
        st.markdown(f"""
            <div class="card">
                <div style="font-size:18px; font-weight:700; color:#0A3D62">{s(chosen['school_name'])}</div><br/>
                <div><span class="label">UDISE:</span> {s(chosen['udise_code'])}</div>
                <div><span class="label">District:</span> {s(chosen['district'])}</div>
                <div><span class="label">Block:</span> {s(chosen['block'])}</div>
                <div><span class="label">Village:</span> {s(chosen['village'])}</div>
                <a class="verify-btn" href="https://udiseplus.gov.in/school/SchoolDirectory?udisecode={html.escape(str(chosen['udise_code']))}" target="_blank">Verify on UDISE+</a>
            </div>
        """, unsafe_allow_html=True)
