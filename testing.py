import streamlit as st
import pandas as pd
from datetime import date

# Set up page title with some style
st.markdown("""
<style>
    .main-title {
        color: #007bff;
        font-size: 36px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .subtitle {
        color: #007bff;
        font-size: 24px;
        margin-bottom: 10px;
    }
    .export-btn {
        background-color: #007bff !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        font-size: 16px !important;
        margin-top: 20px !important;
    }
    .file-table th {
        background-color: #f0f8ff !important;
        color: #007bff !important;
        font-weight: bold !important;
    }
    .file-table td {
        background-color: #f8f9fa !important;
        border-bottom: 1px solid #dee2e6 !important;
    }
</style>
""", unsafe_allow_html=True)

# Main Title
st.markdown('<div class="main-title">Dropbox Filtering System</div>', unsafe_allow_html=True)

# Access Token Input
access_token = st.text_input("Enter your Dropbox ACCESS TOKEN", type="password", placeholder="Paste your ACCESS TOKEN here")

# Date range input with blue borders
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", date.today())
with col2:
    end_date = st.date_input("End Date", date.today())

# Mock data for preview
mock_data = [
    {"day_folder": "May 15", "provider": "Goldman", "orig_name": "Market Trends Analysis.pdf", "suggested_name": "GM_Market Trends Analysis_20250515_m.pdf", "high_quality": True, "delete": False},
    {"day_folder": "May 15", "provider": "JP Morgan", "orig_name": "Global Strategy Update.pdf", "suggested_name": "JPM_Global Strategy Update_20250515_w.pdf", "high_quality": True, "delete": False},
    {"day_folder": "May 15", "provider": "Other", "orig_name": "Daily Sales Report.pdf", "suggested_name": "", "high_quality": False, "delete": False},
    {"day_folder": "May 16", "provider": "Barclays", "orig_name": "Weekly Market Summary.pdf", "suggested_name": "BA_Weekly Market Summary_20250516_w.pdf", "high_quality": True, "delete": False},
    {"day_folder": "May 16", "provider": "Other", "orig_name": "Random Note.pdf", "suggested_name": "", "high_quality": False, "delete": False},
]

df = pd.DataFrame(mock_data)

# Show editable table
st.markdown('<div class="subtitle">File Preview</div>', unsafe_allow_html=True)
styled_df = df[["day_folder", "provider", "orig_name", "suggested_name", "high_quality", "delete"]]

# Use Streamlit's built-in data editor
edited_df = st.data_editor(
    styled_df,
    num_rows="dynamic",
    use_container_width=True
)

# Export button with better styling
if st.button("Export Results", key="export", help="Save the changes you made to file names and selections"):
    if access_token.strip() == "":
        st.error("Please enter your ACCESS TOKEN before exporting.")
    else:
        st.success("Export completed (mock).")


#cd TWIFO_Sharing
#streamlit run testing.py