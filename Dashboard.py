"""
IntelliWatch — Stable Analytics Dashboard
Runs on: http://127.0.0.1:8050
"""

import os
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dash import Dash, html, dcc, Input, Output
import dash_bootstrap_components as dbc

# -------------------------------------------------
# Paths
# -------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ATTENDANCE_CSV = os.path.join(BASE_DIR, "Attendance.csv")
FLAGGED_CSV    = os.path.join(BASE_DIR, "dangerous_persons.csv")
DETECTIONS_CSV = os.path.join(BASE_DIR, "dangerous_detections.csv")

# -------------------------------------------------
# Colors
# -------------------------------------------------

BG         = "#0A0E17"
CARD       = "#0F1520"
BORDER     = "#1E3A5F"
ACCENT     = "#00C853"
ACCENT_DIM = "#00A36C"
DANGER     = "#FF3B3B"
WARN       = "#FF9500"
TEXT       = "#C8D8E8"
MUTED      = "#3A6A8A"

# -------------------------------------------------
# Safe CSV loader
# -------------------------------------------------

def safe_read_csv(path, columns):
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame(columns=columns)
        df.columns = df.columns.str.strip()
        return df
    except Exception:
        return pd.DataFrame(columns=columns)

# -------------------------------------------------
# Data loaders
# -------------------------------------------------

def load_attendance():
    df = safe_read_csv(ATTENDANCE_CSV, ["Name", "Time"])
    if df.empty:
        return df
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"]).copy()
    df["Date"] = df["Time"].dt.date
    df["Hour"] = df["Time"].dt.hour
    return df


def load_flagged():
    return safe_read_csv(FLAGGED_CSV, ["Name", "Reason", "Level", "Date"])


def load_detections():
    df = safe_read_csv(
        DETECTIONS_CSV,
        ["Name", "Reason", "Level", "Confidence", "DateTime", "Action"]
    )
    if df.empty:
        return df
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    return df

# -------------------------------------------------
# Empty chart helper
# -------------------------------------------------

def empty_chart(text="No Data Available"):
    fig = go.Figure()
    fig.add_annotation(
        text=text, x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color=TEXT, family="Consolas, monospace"),
        xref="paper", yref="paper",
    )
    fig.update_layout(
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=260,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig

# -------------------------------------------------
# Common chart theme
# -------------------------------------------------

PLOT_THEME = dict(
    paper_bgcolor=CARD,
    plot_bgcolor=CARD,
    font=dict(color=TEXT, family="Consolas, monospace", size=12),
    margin=dict(l=48, r=20, t=36, b=36),
)

# Axis style applied separately via update_xaxes/update_yaxes
_AXIS_STYLE = dict(gridcolor=BORDER, linecolor=BORDER, tickfont=dict(color=MUTED))

# -------------------------------------------------
# Dash App
# -------------------------------------------------

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="IntelliWatch — Analytics",
)

# -------------------------------------------------
# Layout
# -------------------------------------------------

_CARD_STYLE = {
    "background": CARD,
    "border": f"1px solid {BORDER}",
    "borderRadius": "6px",
    "padding": "14px",
    "marginBottom": "4px",
}

_CARD_DANGER_STYLE = {**_CARD_STYLE, "border": f"1px solid {DANGER}"}

_HDR_STYLE = {
    "color": MUTED,
    "fontSize": "11px",
    "letterSpacing": "3px",
    "fontFamily": "Consolas, monospace",
    "marginBottom": "8px",
    "textTransform": "uppercase",
}

app.layout = html.Div(
    style={"background": BG, "minHeight": "100vh", "padding": "0"},
    children=[

        # ── Header bar ───────────────────────────────────────────────────────
        html.Div(style={
            "background": "#060A10",
            "borderBottom": f"1px solid {BORDER}",
            "padding": "0 28px",
            "height": "52px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
        }, children=[
            html.Div([
                html.Span("IntelliWatch", style={
                    "color": ACCENT, "fontWeight": "bold",
                    "fontSize": "16px", "letterSpacing": "2px",
                    "fontFamily": "Consolas, monospace",
                }),
                html.Span("  ·  ANALYTICS DASHBOARD", style={
                    "color": MUTED, "fontSize": "12px", "letterSpacing": "3px",
                    "fontFamily": "Consolas, monospace",
                }),
            ]),
            html.Div([
                html.Span(id="live-clock", style={
                    "color": MUTED, "fontSize": "12px",
                    "letterSpacing": "2px", "fontFamily": "Consolas, monospace",
                }),
                dcc.Interval(id="clock-interval", interval=1000),
            ]),
        ]),

        # ── Toolbar ───────────────────────────────────────────────────────────
        html.Div(style={
            "padding": "10px 28px",
            "display": "flex",
            "alignItems": "center",
            "gap": "14px",
            "borderBottom": f"1px solid #0A0E17",
        }, children=[
            dbc.Button("⟳  REFRESH", id="refresh-btn", style={
                "background": "transparent",
                "border": f"1px solid {BORDER}",
                "color": MUTED,
                "fontFamily": "Consolas, monospace",
                "fontSize": "12px",
                "letterSpacing": "2px",
                "padding": "5px 16px",
            }),
            dcc.Interval(id="auto-refresh", interval=30_000),
            html.Span("AUTO-REFRESH EVERY 30s", style={
                "color": MUTED, "fontSize": "11px",
                "letterSpacing": "2px", "fontFamily": "Consolas, monospace",
            }),
        ]),

        # ── Main content ──────────────────────────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "20px 24px"}, children=[

            # KPI cards
            dbc.Row(id="kpi-row", className="g-3 mb-3"),

            # Row 1 : Daily + Hourly
            dbc.Row(className="g-3 mb-3", children=[
                dbc.Col(html.Div(style=_CARD_STYLE, children=[
                    html.P("◈  DAILY ATTENDANCE TREND", style=_HDR_STYLE),
                    dcc.Graph(id="daily-chart",
                              figure=empty_chart("Loading..."),
                              config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]), md=8),
                dbc.Col(html.Div(style=_CARD_STYLE, children=[
                    html.P("◈  ATTENDANCE BY HOUR", style=_HDR_STYLE),
                    dcc.Graph(id="hour-chart",
                              figure=empty_chart("Loading..."),
                              config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]), md=4),
            ]),

            # Row 2 : Top profiles + Threat + Detection history
            dbc.Row(className="g-3 mb-3", children=[
                dbc.Col(html.Div(style=_CARD_STYLE, children=[
                    html.P("◈  TOP PROFILES BY ATTENDANCE", style=_HDR_STYLE),
                    dcc.Graph(id="top-profiles-chart",
                              figure=empty_chart("Loading..."),
                              config={"displayModeBar": False},
                              style={"height": "280px"}),
                ]), md=6),
                dbc.Col(html.Div(style=_CARD_DANGER_STYLE, children=[
                    html.P("⚑  THREAT LEVEL DISTRIBUTION", style={**_HDR_STYLE, "color": DANGER}),
                    dcc.Graph(id="threat-chart",
                              figure=empty_chart("Loading..."),
                              config={"displayModeBar": False},
                              style={"height": "280px"}),
                ]), md=3),
                dbc.Col(html.Div(style=_CARD_DANGER_STYLE, children=[
                    html.P("⚑  DETECTION HISTORY", style={**_HDR_STYLE, "color": DANGER}),
                    dcc.Graph(id="detection-chart",
                              figure=empty_chart("Loading..."),
                              config={"displayModeBar": False},
                              style={"height": "280px"}),
                ]), md=3),
            ]),

            # Row 3 : Tables
            dbc.Row(className="g-3 mb-3", children=[
                dbc.Col(html.Div(style=_CARD_STYLE, children=[
                    html.P("≡  TODAY'S ATTENDANCE", style=_HDR_STYLE),
                    html.Div(id="today-table"),
                ]), md=7),
                dbc.Col(html.Div(style=_CARD_DANGER_STYLE, children=[
                    html.P("⚑  SECURITY WATCHLIST", style={**_HDR_STYLE, "color": DANGER}),
                    html.Div(id="flagged-table"),
                ]), md=5),
            ]),

            # Row 4 : Detections log
            dbc.Row(className="g-3 mb-3", children=[
                dbc.Col(html.Div(style=_CARD_DANGER_STYLE, children=[
                    html.P("⚑  RECENT THREAT DETECTIONS", style={**_HDR_STYLE, "color": DANGER}),
                    html.Div(id="detections-table"),
                ]), md=12),
            ]),

        ]),
    ]
)

# -------------------------------------------------
# Callbacks
# -------------------------------------------------

@app.callback(
    Output("live-clock", "children"),
    Input("clock-interval", "n_intervals"),
)
def update_clock(_):
    return datetime.now().strftime("%Y-%m-%d  %H:%M:%S")


@app.callback(
    Output("kpi-row",            "children"),
    Output("daily-chart",        "figure"),
    Output("hour-chart",         "figure"),
    Output("top-profiles-chart", "figure"),
    Output("threat-chart",       "figure"),
    Output("detection-chart",    "figure"),
    Output("today-table",        "children"),
    Output("flagged-table",      "children"),
    Output("detections-table",   "children"),
    Input("refresh-btn",         "n_clicks"),
    Input("auto-refresh",        "n_intervals"),
    prevent_initial_call=False,
)
def update_all(_clicks, _intervals):
    try:
        return _build_dashboard()
    except Exception as exc:
        import traceback; traceback.print_exc()
        err = empty_chart(f"Error: {exc}")
        err_p = html.P(str(exc), style={"color": DANGER, "padding": "12px",
                                        "fontFamily": "Consolas", "fontSize": "12px"})
        return ([], err, err, err, err, err, err_p, err_p, err_p)


def _build_dashboard():
    from dash import dash_table

    df         = load_attendance()
    dff        = load_flagged()
    dfd        = load_detections()
    today      = datetime.now().date()

    # ── KPI cards ────────────────────────────────────────────────────────────
    total    = len(df)
    today_n  = len(df[df["Date"] == today]) if not df.empty else 0
    unique   = df["Name"].nunique() if not df.empty else 0
    flagged  = len(dff)

    def _kpi(label, value, color=ACCENT):
        return dbc.Col(html.Div(style={
            "background": CARD,
            "border": f"1px solid {BORDER}",
            "borderLeft": f"3px solid {color}",
            "borderRadius": "6px",
            "padding": "16px 20px",
        }, children=[
            html.Div(str(value), style={
                "fontSize": "36px", "fontWeight": "bold",
                "color": color, "fontFamily": "Consolas, monospace",
            }),
            html.Div(label.upper(), style={
                "fontSize": "11px", "color": MUTED,
                "letterSpacing": "2px", "fontFamily": "Consolas, monospace",
            }),
        ]), md=3)

    kpi_row = [
        _kpi("Total Records",    total,   ACCENT),
        _kpi("Present Today",    today_n, ACCENT),
        _kpi("Unique Profiles",  unique,  ACCENT),
        _kpi("Flagged Persons",  flagged, DANGER),
    ]

    # ── Daily attendance bar ─────────────────────────────────────────────────
    if not df.empty:
        daily = df.groupby("Date").size().reset_index(name="Count")
        daily["Date"] = daily["Date"].astype(str)
        fig_daily = px.bar(daily, x="Date", y="Count",
                           color_discrete_sequence=[ACCENT])
        fig_daily.update_traces(marker_line_width=0, opacity=0.85)
        fig_daily.update_layout(**PLOT_THEME, height=260, showlegend=False)
        fig_daily.update_xaxes(**_AXIS_STYLE, title_text="")
        fig_daily.update_yaxes(**_AXIS_STYLE, title_text="ENTRIES")
        fig_daily.update_xaxes(**_AXIS_STYLE, title_text="")
        fig_daily.update_yaxes(**_AXIS_STYLE, title_text="ENTRIES")
    else:
        fig_daily = empty_chart("No attendance data yet")

    # ── Hourly bar ───────────────────────────────────────────────────────────
    if not df.empty:
        hourly = df.groupby("Hour").size().reset_index(name="Count")
        all_hours = pd.DataFrame({"Hour": range(24)})
        hourly = all_hours.merge(hourly, on="Hour", how="left").fillna(0)
        hourly["Count"] = hourly["Count"].astype(int)
        fig_hour = px.bar(hourly, x="Hour", y="Count",
                          color_discrete_sequence=[ACCENT_DIM])
        fig_hour.update_traces(marker_line_width=0, opacity=0.85)
        fig_hour.update_layout(**PLOT_THEME, height=260, showlegend=False)
        fig_hour.update_xaxes(**_AXIS_STYLE, title_text="HOUR",
                              tickmode="linear", dtick=4)
        fig_hour.update_yaxes(**_AXIS_STYLE, title_text="")
    else:
        fig_hour = empty_chart("No data")

    # ── Top profiles ─────────────────────────────────────────────────────────
    if not df.empty:
        top = df["Name"].value_counts().head(12).reset_index()
        top.columns = ["Profile", "Count"]
        fig_top = px.bar(top, x="Count", y="Profile", orientation="h",
                         color_discrete_sequence=[ACCENT])
        fig_top.update_traces(marker_line_width=0, opacity=0.85)
        fig_top.update_layout(**PLOT_THEME, height=280, showlegend=False)
        fig_top.update_xaxes(**_AXIS_STYLE, title_text="TOTAL APPEARANCES")
        fig_top.update_yaxes(autorange="reversed", gridcolor=BORDER,
                             linecolor=BORDER, tickfont=dict(color=TEXT, size=11),
                             title_text="")
    else:
        fig_top = empty_chart("No data")

    # ── Threat level donut ───────────────────────────────────────────────────
    if not dff.empty and "Level" in dff.columns:
        tc = dff["Level"].value_counts().reset_index()
        tc.columns = ["Level", "Count"]
        col_map = {"High": DANGER, "Medium": WARN, "Low": "#FFD60A"}
        fig_threat = px.pie(tc, names="Level", values="Count",
                            color="Level", color_discrete_map=col_map, hole=0.55)
        fig_threat.update_layout(**PLOT_THEME, height=280, showlegend=True,
                                 legend=dict(font=dict(color=TEXT, size=11)))
        fig_threat.update_traces(textfont_color="#000", textfont_size=11)
    else:
        fig_threat = empty_chart("No flagged persons")

    # ── Detection history line ────────────────────────────────────────────────
    if not dfd.empty and "DateTime" in dfd.columns:
        dfd_v = dfd.dropna(subset=["DateTime"]).copy()
        dfd_v["Date"] = dfd_v["DateTime"].dt.date
        det = dfd_v.groupby("Date").size().reset_index(name="Detections")
        det["Date"] = det["Date"].astype(str)
        fig_det = px.line(det, x="Date", y="Detections",
                          color_discrete_sequence=[DANGER], markers=True)
        fig_det.update_traces(line_width=2, marker_size=5)
        fig_det.update_layout(**PLOT_THEME, height=280, showlegend=False)
        fig_det.update_xaxes(**_AXIS_STYLE, title_text="")
        fig_det.update_yaxes(**_AXIS_STYLE, title_text="DETECTIONS")
    else:
        fig_det = empty_chart("No detection history")

    # ── Today table ──────────────────────────────────────────────────────────
    _tbl_style = dict(
        style_table={"overflowX": "auto"},
        style_cell={
            "backgroundColor": CARD, "color": TEXT,
            "fontFamily": "Consolas, monospace", "fontSize": "12px",
            "border": f"1px solid {BORDER}", "padding": "8px 12px",
        },
        style_header={
            "backgroundColor": "#060A10", "color": MUTED,
            "fontFamily": "Consolas, monospace", "fontSize": "11px",
            "letterSpacing": "2px", "border": f"1px solid {BORDER}",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": BG}
        ],
    )

    today_df = (df[df["Date"] == today][["Name", "Time"]].copy()
                if not df.empty else pd.DataFrame())
    if not today_df.empty:
        today_df["Time"] = today_df["Time"].dt.strftime("%H:%M:%S")
        today_df = today_df.sort_values("Time", ascending=False)
        today_table = dash_table.DataTable(
            data=today_df.to_dict("records"),
            columns=[{"name": c.upper(), "id": c} for c in today_df.columns],
            page_size=15, **_tbl_style,
        )
    else:
        today_table = html.P("No attendance recorded today.",
                             style={"color": MUTED, "padding": "12px",
                                    "fontFamily": "Consolas", "fontSize": "12px"})

    # ── Flagged table ────────────────────────────────────────────────────────
    if not dff.empty:
        show = [c for c in ["Name", "Level", "Reason", "Date"] if c in dff.columns]
        tbl_f = {**_tbl_style}
        tbl_f["style_data_conditional"] = [
            {"if": {"row_index": "odd"}, "backgroundColor": BG},
            {"if": {"filter_query": '{Level} = "High"'},
             "color": DANGER, "fontWeight": "bold"},
            {"if": {"filter_query": '{Level} = "Medium"'}, "color": WARN},
            {"if": {"filter_query": '{Level} = "Low"'},  "color": "#FFD60A"},
        ]
        flagged_table = dash_table.DataTable(
            data=dff[show].to_dict("records"),
            columns=[{"name": c.upper(), "id": c} for c in show],
            page_size=10, **tbl_f,
        )
    else:
        flagged_table = html.P("No flagged persons on watchlist.",
                               style={"color": MUTED, "padding": "12px",
                                      "fontFamily": "Consolas", "fontSize": "12px"})

    # ── Detections table ─────────────────────────────────────────────────────
    if not dfd.empty:
        show_d = [c for c in ["Name", "Level", "Reason", "Confidence",
                               "DateTime", "Action"] if c in dfd.columns]
        dfd_s = dfd[show_d].copy().sort_values("DateTime", ascending=False).head(50)
        if "Confidence" in dfd_s.columns:
            dfd_s["Confidence"] = dfd_s["Confidence"].apply(
                lambda v: f"{float(v):.1%}" if pd.notnull(v) else "—"
            )

        if "DateTime" in dfd_s.columns:
            dfd_s["DateTime"] = dfd_s["DateTime"].apply(
                lambda v: v.strftime("%Y-%m-%d  %H:%M:%S") if pd.notnull(v) else "—"
            )
        tbl_d = {**_tbl_style}
        tbl_d["style_data_conditional"] = [
            {"if": {"row_index": "odd"}, "backgroundColor": BG},
            {"if": {"filter_query": '{Level} = "High"'},
             "color": DANGER, "fontWeight": "bold"},
            {"if": {"filter_query": '{Level} = "Medium"'}, "color": WARN},
        ]
        detections_table = dash_table.DataTable(
            data=dfd_s.to_dict("records"),
            columns=[{"name": c.upper(), "id": c} for c in show_d],
            page_size=10, **tbl_d,
        )
    else:
        detections_table = html.P("No threat detections logged.",
                                  style={"color": MUTED, "padding": "12px",
                                         "fontFamily": "Consolas", "fontSize": "12px"})

    return (kpi_row, fig_daily, fig_hour, fig_top, fig_threat,
            fig_det, today_table, flagged_table, detections_table)


# -------------------------------------------------
# Run
# -------------------------------------------------

if __name__ == "__main__":
    print("  IntelliWatch Analytics Dashboard")
    print("  Running at http://127.0.0.1:8050")
    app.run(debug=False, port=8050, use_reloader=False)