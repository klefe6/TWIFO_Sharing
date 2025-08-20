import os
import datetime

# compute today’s ISO date once:
TODAY = datetime.date.today().isoformat()  # e.g. "2025-05-21"

import urllib.parse

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
from flask import request, send_from_directory
from PyPDF2 import PdfReader  # for in-PDF keyword search (beta)

# ── new prefix map & detector ──
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "HT_":    "HighTower Research",
    "JPM_":   "JP Morgan",
    "MZ_":    "Mizuho",
    "TSL_":   "TSLombard",
    "T_":     "TWIFO",
    "WF_":    "Wells Fargo",
    "SEB_":   "SEB Commodities",
    "R_":     "Rabobank",
    "MUFG_":  "MUFG",
    "ANZ_":   "ANZ",
    "BCA_":   "BCA",
    "BNPP_":  "BNPP",
    "BNY_":   "Bank of New York Melon",
    "CACIB_": "CACIB",
    "CITI_":  "Citi",
    "HSBC_":  "HSBC",
    "ING_":   "ING",
    "MS_":    "Morgan Stanley",
    "NOM_":   "Nomura",
    "RBC_":   "RBC",
    "SG_":    "SocGen",
    "STI_":   "Stifel",
    "TME_":   "TME",
    "UBS_":   "UBS",
}

def detect_category(fname: str) -> str:
    """Return the matching category from PREFIX_MAP, or 'Others'."""
    for pfx, cat in PREFIX_MAP.items():
        if fname.startswith(pfx):
            return cat
    return "Others"


############################
# 1) CONFIGURATION
############################

APP_TITLE = "H&C Internal Research Directory"
FILES_DIR = os.path.normpath(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)

# Two user credentials
CREDENTIALS = {
    "jlu":      {"password": "jlu25%^&",    "greeting": "Hello James,"},
    "dhughes":  {"password": "RV&",  "greeting": ""},
    "iwill":    {"password": "win",  "greeting": "Hello Winner,"}
}
LOG_FILE = os.path.expanduser("~/Documents/login_log.txt")

# Corporate colors
HEADER_BG_COLOR   = "#004080"
HEADER_TEXT_COLOR = "white"
ROW_ODD_COLOR     = "#f2f2f2"
ROW_EVEN_COLOR    = "white"
APP_BG_COLOR      = "#f7f9fa"
TITLE_COLOR       = "#004080"

############################
# 2) HELPERS
############################

def get_category_options():
    # build a sorted list of all categories + "Others"
    categories = sorted(set(PREFIX_MAP.values()) | {"Others"})
    counts = {cat: 0 for cat in categories}

    # scan your FILES_DIR
    for fname in os.listdir(FILES_DIR):
        if not fname.lower().endswith(".pdf") or fname == "README.txt":
            continue
        cat = detect_category(fname)
        counts[cat] += 1

    return [
        {"label": f"{cat} ({counts[cat]})", "value": cat}
        for cat in categories
    ]

# ── 0b) Precompute sorted category options with "Others" last ──
_raw_opts = get_category_options()
_base = sorted([o for o in _raw_opts if o["value"] != "Others"],
               key=lambda o: o["label"])
_others = [o for o in _raw_opts if o["value"] == "Others"]
CATEGORY_OPTIONS = _base + _others

def pdf_contains(filepath: str, term_lower: str) -> bool:
    try:
        reader = PdfReader(filepath)
        for page in reader.pages:
            text = page.extract_text() or ""
            if term_lower in text.lower():
                return True
    except Exception:
        pass
    return False

############################
# 3) INITIALIZE APP
############################

app = dash.Dash(
    __name__,
    external_stylesheets=["https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"],
    suppress_callback_exceptions=True
)
app.title = APP_TITLE
server = app.server

############################
# 4a) FILES LAYOUT
############################
files_layout = html.Div(
    id="files-section",
    style={"backgroundColor": APP_BG_COLOR, "padding": "40px 20px", "minHeight": "100vh"},
    children=[

        # Row 1: Title + Search Bars
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "justifyContent": "center",
                "gap": "10px",
                "marginBottom": "20px",
            },
            children=[
                html.H1(
                    APP_TITLE,
                    style={
                        "width": "100%",
                        "textAlign": "center",
                        "color": TITLE_COLOR,
                        "marginBottom": "10px",
                        "fontFamily": "Arial, sans-serif",
                    },
                ),
                dcc.Input(
                    id="title-search-input",
                    type="text",
                    placeholder="Search Titles…",
                    debounce=True,
                    style={"width": "300px", "padding": "6px"},
                ),
                html.Button("×", id="clear-title-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="title-search-btn", className="btn btn-primary btn-sm"),
                dcc.Input(
                    id="content-search-input",
                    type="text",
                    placeholder="Search inside PDFs…",
                    debounce=True,
                    style={"width": "300px", "padding": "6px"},
                ),
                html.Button("×", id="clear-content-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="content-search-btn", className="btn btn-primary btn-sm"),
            ],
        ),

        # ── Row 2: Category Filter (3 cols, centered, Others last) ──
        html.Div(
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "gap": "20px",
                "marginBottom": "20px",
            },
            children=[

                # 3-column checklist
                html.Div(
                    dcc.Checklist(
                        id="box-dropdown",
                        options=CATEGORY_OPTIONS,
                        # select all by default
                        value=[opt["value"] for opt in CATEGORY_OPTIONS],
                        inputStyle={"marginRight": "6px"},
                        labelStyle={"display": "block"},
                    ),
                    style={
                        "columnCount": 3,
                        "columnGap": "1em",
                        "border": "1px solid #ccc",
                        "borderRadius": "4px",
                        "padding": "10px",
                        "maxHeight": "260px",
                        "overflowY": "auto",
                        "width": "80%",
                        "margin": "0 auto",
                    },
                ),

                # Select/Clear buttons
                html.Div(
                    [
                        html.Button(
                            "Select All", id="select-all", n_clicks=0,
                            className="btn btn-sm btn-outline-primary"
                        ),
                        html.Button(
                            "Clear All",  id="clear-all",  n_clicks=0,
                            className="btn btn-sm btn-outline-secondary"
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "gap": "8px",
                        "justifyContent": "center",
                    },
                ),

                # Progress bar
                html.Div(
                    className="progress flex-grow-1",
                    id="progress-container",
                    style={"visibility": "hidden", "height": "8px"},
                    children=[
                        html.Div(
                            className="progress-bar progress-bar-striped progress-bar-animated",
                            role="progressbar",
                            style={"width": "100%"},
                        )
                    ],
                ),
            ],
        ),


        # Row 3: DataTable
        dcc.Loading(
            id="loading-table",
            type="default",
            style={"width": "100%"},
            children=[
                    dash_table.DataTable(
                    id="files-table",
                    columns=[
                        {"id": "firm",      "name": "Firm"},
                        {"id": "frequency", "name": "Frequency"},
                        {"id": "date",      "name": "Date"},
                        {"id": "title",     "name": "Title"},
                        {"id": "view",      "name": "View",      "presentation": "markdown"},
                    ],
                    data=[],
                    filter_action="native",
                    sort_action="native",
                    page_action="native",
                    page_size=20,


                    # highlight today’s rows
                    style_data_conditional=[
                        # 1) odd/even for all the other rows
                        {"if": {"row_index": "odd"},  "backgroundColor": ROW_ODD_COLOR},
                        {"if": {"row_index": "even"}, "backgroundColor": ROW_EVEN_COLOR},

                        # 2) then your today‐rule *last*
                        {
                            "if": {"filter_query": f'{{date}} eq "{TODAY}"'},
                            "backgroundColor": "#e6f7ff",
                        },
                    ],

                    style_table={"width": "100%", "overflowX": "auto"},
                    style_cell={
                        "textAlign": "left",
                        "padding": "8px",
                        "fontFamily": "Arial, sans-serif",
                        "whiteSpace": "nowrap",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                    style_header={
                        "backgroundColor": HEADER_BG_COLOR,
                        "color": HEADER_TEXT_COLOR,
                        "fontWeight": "bold",
                    },
                )
            ],
        ),
    ],
)


############################
# 4) APP LAYOUT (with LOGIN + MAIN)
############################
app.layout = html.Div([

    # store to track login status
    dcc.Store(id='login-status', storage_type='session', data=False),
        # store to track which user is logged in
    dcc.Store(id='login-user',   storage_type='session', data=""),

    

    # dummy div for clientside scroll callback
    html.Div(id='dummy-output', style={'display': 'none'}),

    # --- LOGIN SECTION ---
    html.Div(
        id='login-section',
        style={
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'justifyContent': 'center',
            'height': '100vh'
        },
        children=[
            html.Div(
                style={
                    'backgroundColor': '#fff',
                    'padding': '40px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 5px rgba(0,0,0,0.15)',
                    'textAlign': 'center',
                    'maxWidth': '400px'
                },
                children=[
                    html.H1(APP_TITLE, style={'marginBottom': '20px', 'color': '#333'}),

                    # Disclaimer
                    html.Div(
                        style={'textAlign': 'left', 'marginBottom': '20px', 'fontSize': '14px'},
                        children=[
                            html.P(
                                "Disclaimer: This directory is for authorized Hughes & Company users only. "
                                "Articles here may not be redistributed without permission."
                            )
                            
                        ]
                    ),

                    # Username + Password
                    dcc.Input(
                        id='login-username', type='text', placeholder='Username',
                        style={
                            'marginBottom': '10px',
                            'width': '100%',
                            'padding': '8px',
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        }
                    ),
                    dcc.Input(
                        id='login-password', type='password', placeholder='Password',
                        style={
                            'marginBottom': '10px',
                            'width': '100%',
                            'padding': '8px',
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        },
                        n_submit=0
                    ),
                    html.Button(
                        'Login',
                        id='login-button',
                        style={
                            'width': '100%',
                            'padding': '10px',
                            'backgroundColor': '#007BFF',
                            'color': '#fff',
                            'border': 'none',
                            'borderRadius': '4px',
                            'fontWeight': 'bold',
                            'cursor': 'pointer'
                        }
                    ),

                    # Feedback message
                    html.Div(
                        id='login-message',
                        style={'color': 'red', 'marginTop': '10px', 'minHeight': '20px'}
                    )
                ]
            )
        ]
    ),

    # --- MAIN SECTION (hidden until login) ---
    html.Div(
        id='main-section',
        style={'display': 'none', 'opacity': '0', 'transition': 'opacity 0.8s'},
        children=[

            # Greeting + Logout
            html.Div(
                style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '20px',
                    'backgroundColor': HEADER_BG_COLOR
                },
                children=[
                    html.H3(id='greeting', style={'color': HEADER_TEXT_COLOR, 'margin': '0'}),
                    html.Button(
                        "Logout",
                        id="logout-button",
                        style={
                            'backgroundColor': '#dc3545',
                            'color': '#fff',
                            'border': 'none',
                            'padding': '8px 16px',
                            'borderRadius': '4px',
                            'cursor': 'pointer'
                        }
                    )
                ]
            ),

            # file-browser UI!
            files_layout
        ]
    )
])

# ── 4b) “Select All / Clear All” for the category dropdown ──
@app.callback(
    Output("box-dropdown", "value"),
    Input("select-all", "n_clicks"),
    Input("clear-all",  "n_clicks"),
    State("box-dropdown", "options"),
    prevent_initial_call=True,
)
def select_clear_all(n_select, n_clear, options):
    triggered = ctx.triggered_id
    all_vals = [opt["value"] for opt in options]
    if triggered == "select-all":
        return all_vals
    elif triggered == "clear-all":
        return []
    return dash.no_update



############################
# 5) SEARCH / TABLE CALLBACKS
############################

@app.callback(
    [Output("title-search-input","value"), Output("title-search-btn","n_clicks")],
    Input("clear-title-search","n_clicks"),
    State("title-search-btn","n_clicks"),
    prevent_initial_call=True,
)
def clear_title_and_search(n_clear, n_search):
    return "", (n_search or 0) + 1

@app.callback(
    [Output("content-search-input","value"), Output("content-search-btn","n_clicks")],
    Input("clear-content-search","n_clicks"),
    State("content-search-btn","n_clicks"),
    prevent_initial_call=True,
)
def clear_content_and_search(n_clear, n_search):
    return "", (n_search or 0) + 1

@app.callback(
    [
        Output("files-table", "columns"),
        Output("files-table", "data"),
        Output("progress-container", "style"),
    ],
    [
        Input("box-dropdown",         "value"),
        Input("select-all",           "n_clicks"),
        Input("clear-all",            "n_clicks"),
        Input("title-search-btn",     "n_clicks"),
        Input("title-search-input",   "n_submit"),
        Input("content-search-btn",   "n_clicks"),
        Input("content-search-input", "n_submit"),
        Input("login-user",           "data"),
    ],
    [
        State("box-dropdown",         "options"),
        State("title-search-input",   "value"),
        State("content-search-input", "value"),
    ],
    prevent_initial_call=True,
)
def update_file_table(
    sel, n_select, n_clear,
    _tbtn, _tenter,
    _cbtn, _center,
    login_user,
    options, title_value, content_value
):
    
    # path to “Small Caps” folder
    SC = r"C:\Users\H&CDanHughes\Documents\SC_files"

    # 1) Handle Select/Clear All
    triggered = ctx.triggered_id
    if triggered == "select-all":
        sel = [opt["value"] for opt in options]
    elif triggered == "clear-all":
        sel = []

    selected = set(sel or [])
    tt = (title_value or "").strip().lower()
    ct = (content_value or "").strip().lower()

    # 2) Build columns
    cols = [
        {"id": "firm",  "name": "Firm",  "type": "text"},
        {"id": "frequency", "name": "Frequency", "type": "text"},
        {"id": "date",      "name": "Date",      "type": "datetime"},
        {"id": "title",     "name": "Title",     "type": "text"},
        {"id": "view",      "name": "View",      "presentation": "markdown"},
    ]
    if login_user == "iwill":
        cols.insert(4, {"id": "subject",  "name": "Subject",  "type": "text"})
        cols.append({"id": "download","name": "Download","presentation": "markdown"})

    # 3) Scan directories
    rows = []
    scan = [(FILES_DIR, "General")]
    if login_user == "iwill":
        scan.append((SC, "Small Caps"))

    for dpath, subj in scan:
        if not os.path.isdir(dpath):
            continue

        for fname in sorted(os.listdir(dpath)):
            # only PDFs
            if not fname.lower().endswith(".pdf") or fname == "README.txt":
                continue

            # now `fname` is bound—detect its category:
            category = detect_category(fname)

            # apply multi-select filter
            if selected and "All" not in selected and category not in selected:
                continue

            # parse Title / Date / Frequency
            core, _ = os.path.splitext(fname)
            parts = core.split("_")
            if len(parts) >= 4:
                _, *tp, date_part, fcode = parts
                title_str = " ".join(tp).replace("_", " ")
            elif len(parts) == 3:
                _, title_str, date_part = parts
                title_str = title_str.replace("_", " ")
                fcode = "u"
            else:
                title_str = "_".join(parts[1:])
                date_part = ""
                fcode = "u"

            # extract date + flag if it's today
            try:
                dt = datetime.datetime.strptime(date_part, "%Y%m%d")
                date_fmt = dt.strftime("%Y-%m-%d")
                is_today = (dt.date() == datetime.date.today())
            except:
                date_fmt = "Unknown"
                is_today = False

            # map frequency
            fmap = {"y":"Yearly","q":"Quarterly","m":"Monthly","w":"Weekly","u":""}
            frequency = fmap.get(fcode.lower(), "unknown")

            # title/content search filters
            if tt and tt not in title_str.lower():
                continue
            if ct and not pdf_contains(os.path.join(dpath, fname), ct):
                continue

            # build the single row (with is_today flag)
            safe = urllib.parse.quote(fname)
            view_md = f"[View](/view?file={safe})"
            row = {
                "firm":      category,
                "frequency": frequency,
                "date":      date_fmt,
                "title":     title_str,
                "view":      view_md,
                "is_today":  is_today
            }
            if login_user == "iwill":
                row["subject"]  = subj
                row["download"] = f"[Download](/download?file={safe})"

            rows.append(row)


    # Sort rows by date (most recent first), ignoring "Unknown"
    def sort_key(r):
        try:
            return datetime.datetime.strptime(r["date"], "%Y-%m-%d")
        except:
            return datetime.datetime.min  # "Unknown" dates go last

    rows.sort(key=sort_key, reverse=True)

    # hide progress bar
    style = {"visibility": "hidden", "height": "8px"}
    return cols, rows, style


############################
# 6) LOGIN / LOGOUT CALLBACK
############################

@app.callback(
    Output('login-message','children'),
    Output('main-section','style'),
    Output('greeting','children'),
    Output('login-status','data'),
    Output('login-user','data'),         
    Input('login-button','n_clicks'),
    Input('login-password','n_submit'),
    Input('logout-button','n_clicks'),
    State('login-username','value'),
    State('login-password','value'),
    prevent_initial_call=True
)

def handle_login_logout(login_clicks, pw_enter, logout_clicks,
                        username, password):
    triggered = ctx.triggered_id

    # Logout
    if triggered == "logout-button":
        return "", {'display':'none','opacity':'0'}, "", False, ""

    # Validate
    success = username in CREDENTIALS and password == CREDENTIALS[username]['password']
    greeting = CREDENTIALS.get(username,{}).get('greeting',"") if success else ""

    # Log attempt
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = request.remote_addr
    status = "SUCCESS" if success else "FAIL"
    try:
        with open(LOG_FILE,'a') as f:
            f.write(f"{now} | IP: {ip} | user={username} | {status}\n")
    except Exception:
        pass

    if success:
        return (
            "", 
            {'display':'block','opacity':'1','transition':'opacity 0.8s'},
            greeting,
            True,
            username         # ← add this
        )
    else:
        return (
            "Invalid credentials.",
            {'display':'none','opacity':'0'},
            "",
            False,
            ""               # ← add this
        )


############################
# 7) CLIENTSIDE SCROLL
############################

app.clientside_callback(
    """
    function(loginSuccess) {
        if (loginSuccess) {
            document
              .getElementById('main-section')
              .scrollIntoView({ behavior: 'smooth' });
        }
        return '';
    }
    """,
    Output('dummy-output', 'children'),
    Input('login-status', 'data')
)


############################
# 8) FILE VIEW / DOWNLOAD
############################

@server.route("/view")
def view_file():
    f = request.args.get("file")
    if not f:
        return "No file specified.", 400

    # Check both directories
    dirs_to_check = [
        FILES_DIR,
        r"C:\Users\H&CDanHughes\Documents\SC_files"
    ]

    for directory in dirs_to_check:
        full_path = os.path.join(directory, f)
        if os.path.isfile(full_path):
            return send_from_directory(directory, f)

    return "File not found.", 404


@server.route("/download")
def download_file():
    f = request.args.get("file")
    if not f:
        return "No file specified.", 400

    # Check both directories
    dirs_to_check = [
        FILES_DIR,
        r"C:\Users\H&CDanHughes\Documents\SC_files"
    ]

    for directory in dirs_to_check:
        full_path = os.path.join(directory, f)
        if os.path.isfile(full_path):
            return send_from_directory(directory, f, as_attachment=True)

    return "File not found.", 404


############################
# 9) RUN
############################

if __name__ == "__main__":
    app.run(debug=True, port=8065)

