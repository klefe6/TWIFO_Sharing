import streamlit as st
import subprocess


#remember for this file, we need to run streamlit and not python
#cd TWIFO_Sharing
#streamlit run import_dropbox.py

# ——— PAGE CONFIG (FIRST STREAMLIT CALL) ———
st.set_page_config(page_title="Dropbox Filter", layout="wide")

# ——— IMPORTS ———
import pandas as pd
import re
import datetime
from datetime import timedelta
import os
import dropbox
from dropbox.files import FolderMetadata, FileMetadata
from dropbox.exceptions import ApiError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# ——— CONFIG ———
# ——— DYNAMIC DROPBOX FOLDER SELECTION ———
root_options = st.sidebar.multiselect(
    "Dropbox root(s)",
    options=["Current", "Archives"],
    default=["Current"],
    help="Choose Current, Archive, or both"
)
year = st.sidebar.number_input(
    "Year",
    min_value=2000,
    max_value=2100,
    value=datetime.date.today().year,
    help="Select the year to scan"
)
months = [datetime.date(1900, i, 1).strftime("%B") for i in range(1, 13)]
month = st.sidebar.selectbox(
    "Month",
    options=months,
    index=datetime.date.today().month - 1,
    help="Select the month to scan"
)

# three‐letter Dropbox folder name
month_abbrev = month[:3]  # e.g. "June" → "Jun"

DEFAULT_KEEP = [
    "Annual","Weekly","Monthly","Quarterly",
    "Commodity","Commodities","Gold","Bitcoin","SOFR","Interest Rates", "CTAs", "CFTC", "CME", "BNY"
]
DEFAULT_SKIP = [
    "Earnings",          "Earnings_",          "Earnings-",
    "Daily",             "Daily_",             "Daily-",
    "Morning",           "Morning_",           "Morning-",
    "Equity",            "Equity_",            "Equity-",
    "Stocks",            "Stocks_",            "Stocks-",
    "Briefing",          "Briefing_",          "Briefing-",
    "Brief",             "Brief_",             "Brief-",
    "brief",             "brief_",             "brief-",
    "Intell",            "Intell_",            "Intell-",
    "Commentary",        "Commentary_",        "Commentary-",
    "Oil Data",          "Oil Data_",          "Oil Data-",
    "Regional",          "Regional_",          "Regional-",
    "Australia",         "Australia_",         "Australia-",
    "New Zealand",       "New Zealand_",       "New Zealand-",
    "UK",                "UK_",                "UK-",
    "Germany",           "Germany_",           "Germany-",
    "France",            "France_",            "France-",
    "Italy",             "Italy_",             "Italy-",
    "Spain",             "Spain_",             "Spain-",
    "China Property",    "China Property_",    "China Property-",
    "Americas Business", "Americas Business_", "Americas Business-",
    "Biotech",           "Biotech_",           "Biotech-",
    "Switzerland",       "Switzerland_",       "Switzerland-",
    "Sweden",            "Sweden_",            "Sweden-",
    "Norway",            "Norway_",            "Norway-",
    "Denmark",           "Denmark_",           "Denmark-",
    "Netherlands",       "Netherlands_",       "Netherlands-",
    "Belgium",           "Belgium_",           "Belgium-",
    "Japan",             "Japan_",             "Japan-",
    "Taiwan",            "Taiwan_",            "Taiwan-",
    "India",             "India_",             "India-",
    "Brazil",            "Brazil_",            "Brazil-",
    "Mexico",            "Mexico_",            "Mexico-",
    "Russia",            "Russia_",            "Russia-",
    "Turkey",            "Turkey_",            "Turkey-",
    "South Africa",      "South Africa_",      "South Africa-",
    "Indonesia",         "Indonesia_",         "Indonesia-",
    "Malaysia",          "Malaysia_",          "Malaysia-",
    "Hong Kong",         "Hong Kong_",         "Hong Kong-",
    "Singapore",         "Singapore_",         "Singapore-",
    "Philippines",       "Philippines_",       "Philippines-",
    "Vietnam",           "Vietnam_",           "Vietnam-",
    "Thailand",          "Thailand_",          "Thailand-",
]

# ——— INITIALIZE SESSION-STATE FOR TEXT AREAS ———
if "keep_text" not in st.session_state:
    st.session_state.keep_text = "\n".join(DEFAULT_KEEP)
if "skip_text" not in st.session_state:
    st.session_state.skip_text = "\n".join(DEFAULT_SKIP)

# ——— SIDEBAR: PATTERN EDITOR ———
st.sidebar.header("🔧 Keyword Settings")
st.sidebar.write(
    "Enter one keyword per line. Words in the **KEEP** list will be included, while words in the **SKIP** list will be excluded. "
    "Changes will automatically take effect when you click the **Scan Dropbox** button."
)

keep_text = st.sidebar.text_area(
    "KEEP (one per line)",
    key="keep_text",
    height=200
)
skip_text = st.sidebar.text_area(
    "SKIP (one per line)",
    key="skip_text",
    height=200
)

# ——— BUILD REGEX FROM TEXT AREAS ———
keep_list = [p.strip() for p in keep_text.splitlines() if p.strip()]
skip_list = [p.strip() for p in skip_text.splitlines() if p.strip()]

KEEP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, keep_list)) + r")(?=\W|$)")
SKIP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, skip_list)) + r")\b")

# ——— CATEGORY PREFIXES ———
CATEGORY_PREFIXES = {
    "BOA":   ["BofA"],
    "BA":    ["Barclays","BARC"],
    "BR":    ["BlackRock","BLK"],
    "DB":    ["Deutsche Bank","DB","DBK"],
    "GM":    ["Goldman","Goldman Sachs","GS"],
    "HT":    ["HighTower Research"],
    "JPM":   ["JP Morgan","JPM","JPMorgan"],
    "MZ":    ["Mizuho"],
    "TSL":   ["TSLombard","TS Lombard"],
    "T":     ["TWIFO"],
    "WF":    ["Wells Fargo","WFC"],
    "SEB":   ["SEB Commodities","SEB"],
    "R":     ["Rabobank"],
    "MUFG":  ["MUFG","Macro2Markets","Mitsubishi UFJ"],
    "ANZ":   ["ANZ","Australia & New Zealand Banking Group"],
    "BCA":   ["BCA"],
    "BNPP":  ["BNPP","BNP Paribas"],
    "BNY":   ["BNY","BNY Mellon"],
    "CACIB": ["CACIB","Crédit Agricole CIB"],
    "CITI":  ["Citi","Citigroup","C"],
    "HSBC":  ["HSBC"],
    "ING":   ["ING","ING Group"],
    "MS":    ["Morgan Stanley","MS"],
    "NOM":   ["Nomura"],
    "RBC":   ["RBC","Royal Bank of Canada"],
    "SG":    ["SocGen","Société Générale"],
    "STI":   ["Stifel"],
    "TME":   ["TME"],
    "UBS":   ["UBS"],
    "O":     ["Other","Others","OTHERS"]
}

# ——— FREQUENCY CODES ———
FREQ_KEYS = {
    "y": re.compile(r"(?i)\bAnnual\b"),
    "q": re.compile(r"(?i)\bQuarterly\b"),
    "m": re.compile(r"(?i)\bMonthly\b"),
    "w": re.compile(r"(?i)\bWeekly\b"),
}

# ——— SCANNER FUNCTION ———
def scan_dropbox(dbx, base: str, dates):
    rows = []
    # month_name is e.g. "May" from "/Current/2025/May"
    month_name = base.rsplit("/", 1)[-1]


    for d in dates:
        day_folder  = f"{month_abbrev} {d.day}"
        folder_path = f"{base}/{day_folder}"
        # ── DEBUG ──
        st.write(f"🔎 attempting to list folder: '{folder_path}'")
        try:
            res = dbx.files_list_folder(folder_path)
        except ApiError as e:
            # show the exact error for this path
            st.write(f"⚠️ skip {folder_path}: {e}")
            continue

        for entry in res.entries:
            if not isinstance(entry, FolderMetadata):
                continue

            # provider code
            prefix = "O"
            is_gm = False
            name_l = entry.name.lower().strip()
            for code, syns in CATEGORY_PREFIXES.items():
                if any(name_l.startswith(s.lower()) for s in syns):
                    prefix = code
                    is_gm = (code == "GM")
                    break

            # list top‐level files
            try:
                children = dbx.files_list_folder(entry.path_lower).entries
            except ApiError:
                continue

            # if Goldman, also grab anything under its "S&T" subfolder
            if is_gm:
                try:
                    nested = dbx.files_list_folder(entry.path_lower + "/s&t").entries
                    children.extend(nested)
                except ApiError:
                    pass  # no S&T or unreadable, skip

            # now process every FileMetadata in children
            for f in children:
                if not isinstance(f, FileMetadata):
                    continue

                raw_name  = f.name                 # exact filename
                path_lower = f.path_lower          # full lowercase path e.g. "/current/2025/may/May 20/Goldman/s&t/…pdf"
                orig = re.sub(r"^(BofA|MUFG|ING)[\s_-]+", "", raw_name)

                if is_gm and re.search(r"(?i)monthly[\s_]+stats", orig):
                    continue
                if SKIP_PAT.search(orig):
                    continue
                if not KEEP_PAT.search(orig):
                    continue

                # frequency code
                freq = "u"
                for k, p in FREQ_KEYS.items():
                    if p.search(orig):
                        freq = k
                        break

                # build suggested name (use a different variable!)
                file_base = orig.rsplit(".", 1)[0]
                # new: removes ANY of “BNY-”, “BNY_” or “BNY ” (and repeated prefixes)
                file_base = re.sub(
                    rf"^(?:{re.escape(prefix)}[-_\s]+)+",
                    "",
                    file_base,
                    flags=re.IGNORECASE
                )
                file_base = re.sub(r"\b\d*2025\d*\b", "", file_base)
                file_base = file_base.replace("_", " ").strip()
                file_base = re.sub(r"\s{2,}", " ", file_base)
                date_str   = d.strftime("%Y%m%d")
                suggested  = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"
            
                rows.append({
                    "day_folder":     day_folder,
                    "provider":       entry.name,
                    "raw_name":       raw_name,
                    "path_lower":     path_lower,    # <-- new!
                    "orig_name":      orig,
                    "suggested_name": suggested,
                    "delete":         False
                })

    return pd.DataFrame(rows)


# ——— UI HEADER ———
st.markdown("<h1 style='color:#007bff'>Dropbox Filtering System</h1>", unsafe_allow_html=True)

# 1) ACCESS TOKEN
token = st.text_input(
    "Dropbox ACCESS TOKEN",
    type="password",
    key="token"
)

# ── Generate API Token button ──    ### ← insert here, after the ACCESS TOKEN field
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center">
      <a href="https://www.dropbox.com/developers/apps/info/7qkbdoq6f8bb60z"
         target="_blank" style="text-decoration:none">
        <button style="padding:8px 16px; font-size:16px;">Generate API Token</button>
      </a>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown("<br>", unsafe_allow_html=True)

# 2) DATE SELECTION
st.subheader("📅 Date Selection")
mode = st.radio("Mode", ["Date Range", "Days Back"], key="mode")
if mode == "Date Range":
    start_date = st.date_input("Start Date", datetime.date.today(), key="start")
    end_date   = st.date_input("End Date",   datetime.date.today(), key="end")
else:
    end_date   = st.date_input("End Date", datetime.date.today(), key="end_back")
    back       = st.number_input("Days Back", 1, 90, 3, key="back")
    start_date = end_date - timedelta(days=back)

# 3) SCAN BUTTON
if st.button("Scan Dropbox", key="scan"):
    if not token:
        st.error("Please enter your ACCESS TOKEN.")
    else:
        try:
            dbx = dropbox.Dropbox(token.strip())

            # 1) build once, outside any loop
            dropbox_bases = [f"/{root}/{year}/{month}" for root in root_options]
            st.write("🔍 scanning these Dropbox bases:", dropbox_bases)

            # 2) scan each base
            with st.spinner("Scanning…"):
                dates = pd.date_range(start=start_date, end=end_date)
                dfs = []
                for base in dropbox_bases:
                    # base must be a string like "/Current/2025/May"
                    dfs.append(scan_dropbox(dbx, base, dates))

                df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

            # 3) show results
            if df.empty:
                st.warning("No matching files found.")
            else:
                st.success(f"Found {len(df)} target files.")
                st.session_state.df = df

        except Exception as e:
            st.error(f"Error: {e}")

# 4) RESULTS GRID & DOWNLOAD
if "df" in st.session_state and not st.session_state.df.empty:
    st.subheader("📁 High-Quality Target Files")
    df = st.session_state.df.copy()

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("suggested_name", editable=True)
    gb.configure_selection("multiple", use_checkbox=True, suppressRowClickSelection=True)
    gb.configure_pagination(paginationAutoPageSize=True)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    opts = gb.build()

    resp = AgGrid(
        df,
        gridOptions=opts,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        height=500,
        theme="streamlit"
    )

    st.session_state.df = pd.DataFrame(resp["data"])

    # DELETE:
    sel_df = pd.DataFrame(resp["selected_rows"])
    if st.button("Delete selected rows", key="delete"):
        to_remove = set(zip(sel_df["orig_name"], sel_df["provider"]))
        df_full = st.session_state.df
        mask = [
            (r.orig_name, r.provider) not in to_remove
            for r in df_full.itertuples()
        ]
        st.session_state.df = df_full[mask].reset_index(drop=True)
        st.success(f"Deleted {len(to_remove)} rows.")

    # download all
    export_dir = os.path.expanduser(
        r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
    )
    os.makedirs(export_dir, exist_ok=True)
    if st.button("Download all remaining rows", key="download"):
        dbx = dropbox.Dropbox(token.strip())
        for _, row in st.session_state.df.iterrows():
            src = row["path_lower"]   # ← use the exact Dropbox path you stored
            st.write("→ downloading from:", src)
            dst = os.path.join(export_dir, row["suggested_name"])
            try:
                dbx.files_download_to_file(dst, src)
            except ApiError as e:
                st.error(f"Failed to download {src}: {e}")
        st.success("Download pass complete.")

          # ── NEW: Run twifo.py directly ──
    # ── Run run_twifo.bat to update website ──   ### ← replace your current Update-Website block with this
    if st.button("Update Website", key="update"):
        try:
            bat_path = r"C:\Program Files\Coding Projects\TWIFO_Sharing\reboot_twifo.bat"
            result = subprocess.run(
                [bat_path],
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            st.success("✅ Website update script ran successfully!")
            if result.stdout:
                st.text(result.stdout)
            if result.stderr:
                st.warning(result.stderr)
        except subprocess.CalledProcessError as e:
            st.error(f"❌ Error running update script:\n{e.stderr or e}")
   
#remember for this file, we need to run streamlit and not python
#cd TWIFO_Sharing
#streamlit run import_dropbox.py


