import streamlit as st
import pandas as pd
from rapidfuzz import process

st.title("Karnataka School Management Finder")

# Load dataset
file_path = "karnataka_schools.xlsx"
df = pd.read_excel(file_path)

st.write("Search schools by name or location in Karnataka")

search_query = st.text_input("Enter School Name / Location:")

if search_query:
    column_to_search = "SCHOOL NAME"

    matches = process.extract(
        search_query,
        df[column_to_search].astype(str),
        limit=10,
        score_cutoff=60
    )

    if matches:
        matched_df = pd.DataFrame([df.iloc[m[2]] for m in matches])
        st.success(f"✅ Found {len(matched_df)} matching schools:")
        st.dataframe(matched_df)
    else:
        st.warning("❌ No matching schools found. Try different keywords!")

