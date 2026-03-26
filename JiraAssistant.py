import os
import re
import requests
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import quote

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jira Assistant",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS (light + dark adaptive) ──────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

/* ── Shared / structural ── */
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
#MainMenu, footer { visibility: hidden; }

.stButton button {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    border-radius: 6px;
}
.stAlert {
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
}
[data-testid="stMetric"] {
    border-radius: 6px;
    padding: 12px 16px;
    border-width: 1px;
    border-style: solid;
}
[data-testid="stMetricLabel"] {
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: .07em;
}
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
}
[data-testid="stDataFrame"] {
    border-radius: 6px;
    overflow: hidden;
    border-width: 1px;
    border-style: solid;
}
h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }
.stTextInput input,
.stSelectbox select,
[data-testid="stTextArea"] textarea {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    border-radius: 6px;
}
[data-testid="stSidebar"] .stRadio label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
}

/* ── LIGHT MODE ── */
@media (prefers-color-scheme: light) {
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #f8fafc;
        color: #1e293b;
    }
    [data-testid="stSidebar"] {
        background-color: #f1f5f9;
        border-right: 1px solid #cbd5e1;
    }
    [data-testid="stSidebar"] .stRadio label { color: #475569; }
    [data-testid="stMetric"] {
        background: #ffffff;
        border-color: #e2e8f0;
    }
    [data-testid="stMetricLabel"] { color: #64748b !important; }
    [data-testid="stMetricValue"] { color: #1e293b !important; }
    [data-testid="stDataFrame"]   { border-color: #e2e8f0; }
    h1  { color: #0f766e !important; }
    h2, h3 { color: #1e293b !important; }
    .stTextInput input,
    .stSelectbox select,
    [data-testid="stTextArea"] textarea {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        color: #1e293b;
    }
}

/* ── DARK MODE ── */
@media (prefers-color-scheme: dark) {
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0d0f12;
        color: #e2e8f0;
    }
    [data-testid="stSidebar"] {
        background-color: #13161b;
        border-right: 1px solid #232830;
    }
    [data-testid="stSidebar"] .stRadio label { color: #94a3b8; }
    [data-testid="stMetric"] {
        background: #1a1f27;
        border-color: #232830;
    }
    [data-testid="stMetricLabel"] { color: #4f6070 !important; }
    [data-testid="stMetricValue"] { color: #e2e8f0 !important; }
    [data-testid="stDataFrame"]   { border-color: #232830; }
    h1  { color: #4af0b0 !important; }
    h2, h3 { color: #e2e8f0 !important; }
    .stTextInput input,
    .stSelectbox select,
    [data-testid="stTextArea"] textarea {
        background-color: #1a1f27;
        border: 1px solid #2e3540;
        color: #e2e8f0;
    }
}
</style>
""", unsafe_allow_html=True)

# ─── Configuration ────────────────────────────────────────────────────────────
load_dotenv()

# ─── Session state defaults ──────────────────────────────────────────────────
def init_state():
    defaults = {
        "jira_url":          os.getenv("JIRA_URL", ""),
        "jira_token":        os.getenv("JIRA_API_TOKEN", ""),
        "default_project":   os.getenv("JIRA_DEFAULT_PROJECT", ""),
        "fix_version_changes": [{"original": "", "new": ""}],
        "projects_cache":    None,
        "query_history":     [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ─── Jira API helpers ────────────────────────────────────────────────────────
def headers():
    return {
        "Authorization": f"Bearer {st.session_state.jira_token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

def jira_get(path: str, params: dict = None) -> dict:
    url = st.session_state.jira_url.rstrip("/") + path
    resp = requests.get(url, headers=headers(), params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()

def jira_search(jql: str, fields: str, max_results: int = 200, expand: str = None) -> list:
    params = {"jql": jql, "maxResults": max_results, "fields": fields}
    if expand:
        params["expand"] = expand
    data = jira_get("/rest/api/2/search", params=params)
    return data.get("issues", [])

def extract_field(field):
    """Safely extract value from Jira custom field (dict, list, or scalar)."""
    if field is None:
        return "Not set"
    if isinstance(field, dict):
        return field.get("value") or field.get("name") or "Not set"
    if isinstance(field, list):
        if not field:
            return "Not set"
        first = field[0]
        return first.get("value") or first.get("name") if isinstance(first, dict) else str(first)
    return str(field)

def issue_url(key: str) -> str:
    base = st.session_state.jira_url.rstrip("/")
    return f"{base}/browse/{key}"

def clickable_key(key: str) -> str:
    return f"[{key}]({issue_url(key)})"

# ─── Project loader ───────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_projects(jira_url: str, jira_token: str) -> list:
    try:
        resp = requests.get(
            jira_url.rstrip("/") + "/rest/api/2/project",
            headers={"Authorization": f"Bearer {jira_token}", "Accept": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        projects = [
            {"key": p["key"], "name": p["name"]}
            for p in resp.json()
            if not p.get("archived", False)
        ]
        return sorted(projects, key=lambda x: x["key"])
    except Exception:
        return []

# ─── Status badge helper ──────────────────────────────────────────────────────
STATUS_EMOJI = {
    "to do": "⬜", "open": "⬜", "backlog": "⬜",
    "in progress": "🔵", "active": "🔵",
    "done": "✅", "closed": "✅", "resolved": "✅",
    "in review": "🟡", "testing": "🟡", "qa": "🟡",
    "blocked": "🔴", "feature ready": "🟣",
}

def status_icon(status: str) -> str:
    if not status:
        return "—"
    key = status.lower()
    for k, icon in STATUS_EMOJI.items():
        if k in key:
            return f"{icon} {status}"
    return status

PRIORITY_ICON = {
    "highest": "🔴", "blocker": "🔴",
    "high": "🟠", "medium": "🟡",
    "low": "🔵", "lowest": "⚪",
}

def priority_icon(priority: str) -> str:
    if not priority:
        return "—"
    return PRIORITY_ICON.get(priority.lower(), "⚪") + " " + priority

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔷 Jira Assistant")
    st.caption("👨‍💻 Created by Karan Kakade")
    st.divider()

    page = st.radio(
        "Navigate",
        options=[
            "⚙️  Settings",
            "◈  Ask Anything",
            "📋  Missing Fields",
            "🔍  Story Alignment",
            "⚠️  Full Hygiene Report",
            "🔄  Fix Version Changes",
            "🏃  Current Sprint",
            "👥  Team Workload",
            "👤  My Issues",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    if st.session_state.jira_url and st.session_state.jira_token:
        st.success(f"Connected to\n`{st.session_state.jira_url}`", icon="🟢")
    else:
        st.warning("Not configured — go to Settings", icon="🔴")

    # Query history in sidebar
    if st.session_state.query_history:
        st.divider()
        st.caption("RECENT QUERIES")
        for q in st.session_state.query_history[-6:][::-1]:
            st.caption(f"• {q[:45]}{'…' if len(q)>45 else ''}")


# ═════════════════════════════════════════════════════════════════════════════
#  SETTINGS PAGE
# ═════════════════════════════════════════════════════════════════════════════
def page_settings():
    st.title("⚙️ Connection Settings")
    st.caption("👨‍💻 Created by Karan Kakade")
    st.caption("Credentials are stored in your session only — never persisted to disk unless you use a .env file.")
    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input(
            "Jira Base URL",
            value=st.session_state.jira_url,
            placeholder="https://jira.yourcompany.com",
            help="No trailing slash. Jira Server / Data Center.",
        )
        token = st.text_input(
            "Personal Access Token",
            value=st.session_state.jira_token,
            type="password",
            help="Profile → Personal Access Tokens (Jira Server 8.14+). Used as Bearer token.",
        )
        default_project = st.text_input(
            "Default Project Key (optional)",
            value=st.session_state.default_project,
            placeholder="e.g. PROJ",
            help="Pre-selected in all dropdowns.",
        ).upper().strip()

        col_save, col_test, _ = st.columns([1, 1, 2])
        with col_save:
            if st.button("💾 Save Settings", type="primary"):
                st.session_state.jira_url = url.strip().rstrip("/")
                st.session_state.jira_token = token.strip()
                st.session_state.default_project = default_project
                st.session_state.projects_cache = None
                load_projects.clear()
                st.success("Settings saved!")

        with col_test:
            if st.button("🔌 Test Connection"):
                if not url or not token:
                    st.error("Fill in URL and token first.")
                else:
                    try:
                        resp = requests.get(
                            url.rstrip("/") + "/rest/api/2/myself",
                            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                            timeout=15,
                        )
                        resp.raise_for_status()
                        d = resp.json()
                        st.success(f"✅ Connected as **{d.get('displayName', d.get('name', 'Unknown'))}**")
                    except Exception as e:
                        st.error(f"❌ {e}")

    with col2:
        st.info(
            "**How to get a PAT:**\n\n"
            "1. Log into Jira\n"
            "2. Click your avatar → Profile\n"
            "3. Personal Access Tokens → Create token\n"
            "4. Copy and paste here\n\n"
            "Requires Jira Server 8.14+",
            icon="ℹ️",
        )

    st.divider()
    st.caption("You can also set these via a `.env` file: `JIRA_URL`, `JIRA_API_TOKEN`, `JIRA_DEFAULT_PROJECT`")


# ═════════════════════════════════════════════════════════════════════════════
#  SHARED: project selector widget
# ═════════════════════════════════════════════════════════════════════════════
def project_selector(key_suffix: str = "") -> str:
    """Renders a project selectbox and returns the selected project key."""
    projects = load_projects(st.session_state.jira_url, st.session_state.jira_token)
    if not projects:
        st.warning("No projects loaded. Check Settings & connection.")
        return ""
    options = [f"{p['key']} — {p['name']}" for p in projects]
    default_idx = 0
    if st.session_state.default_project:
        for i, o in enumerate(options):
            if o.startswith(st.session_state.default_project + " "):
                default_idx = i
                break
    selected = st.selectbox("Project", options, index=default_idx, key=f"proj_{key_suffix}")
    return selected.split(" — ")[0] if selected else ""


def require_config() -> bool:
    if not st.session_state.jira_url or not st.session_state.jira_token:
        st.error("Please configure your Jira URL and token in ⚙️ Settings first.")
        return False
    return True


# ═════════════════════════════════════════════════════════════════════════════
#  NATURAL LANGUAGE QUERY PAGE
# ═════════════════════════════════════════════════════════════════════════════
def parse_intent(query: str) -> str:
    q = query.lower()
    if re.search(r"hygiene|no stor|no link", q):            return "epic_hygiene"
    if re.search(r"missing.*(fix|priority)|fix.*empty", q): return "missing_fields"
    if re.search(r"workload|who has|team.*load", q):        return "team_workload"
    if re.search(r"sprint", q):                             return "sprint_issues"
    if re.search(r"block", q):                              return "blocked_issues"
    if re.search(r"my (open|issue|ticket)|assigned.*me", q):return "my_issues"
    if re.search(r"epic", q):                               return "epics"
    return "general_search"

def page_ask():
    st.title("◈ Ask Anything")
    st.caption("Natural language queries — powered by Jira REST API")

    if not require_config():
        return

    # Suggestion chips rendered as buttons in a horizontal row
    st.markdown("**Quick queries:**")
    chips = [
        "Active epics missing fix version",
        "Epics with no linked stories",
        "My open issues",
        "Current sprint progress",
        "Team workload summary",
    ]
    cols = st.columns(len(chips))
    for col, chip in zip(cols, chips):
        with col:
            if st.button(chip, key=f"chip_{chip}", use_container_width=True):
                st.session_state["nl_query_prefill"] = chip

    query = st.text_area(
        "Your question",
        value=st.session_state.pop("nl_query_prefill", ""),
        placeholder="e.g. Show epics in progress with no linked stories, team workload, sprint status…",
        height=80,
        label_visibility="collapsed",
    )

    run = st.button("Run Query ↵", type="primary")

    if run and query.strip():
        q = query.strip()
        # Update history
        hist = st.session_state.query_history
        if q not in hist:
            hist.append(q)
        if len(hist) > 20:
            st.session_state.query_history = hist[-20:]

        intent = parse_intent(q)
        proj = st.session_state.default_project

        with st.spinner("Querying Jira…"):
            try:
                if intent == "epic_hygiene":
                    run_epic_hygiene_query(proj)
                elif intent == "missing_fields":
                    run_missing_fields(proj)
                elif intent == "team_workload":
                    run_team_workload(proj)
                elif intent == "sprint_issues":
                    run_sprint_issues(proj)
                elif intent == "blocked_issues":
                    run_blocked_issues(proj)
                elif intent == "my_issues":
                    run_my_issues(proj)
                elif intent == "epics":
                    run_epics_list(proj, q)
                else:
                    run_general_search(proj, q)
            except Exception as e:
                st.error(f"Jira error: {e}")


# ─── Intent runners (used by both Ask page and dedicated pages) ───────────────

def run_epic_hygiene_query(proj: str):
    jql = "issuetype = Epic AND statusCategory != Done"
    if proj:
        jql += f" AND project = {proj}"
    epics = jira_search(jql, "summary,status", max_results=50)

    orphan_rows, stalled_rows = [], []
    prog = st.progress(0, text="Checking epics…")
    for i, epic in enumerate(epics):
        prog.progress((i + 1) / max(len(epics), 1), text=f"Checking {epic['key']}…")
        cat = epic["fields"]["status"].get("statusCategory", {}).get("key", "")
        stories = jira_search(
            f'"Epic Link" = {epic["key"]} OR parent = {epic["key"]}',
            "summary,status", max_results=50,
        )
        in_prog = [s for s in stories if s["fields"]["status"].get("statusCategory", {}).get("key") == "indeterminate"]
        if cat == "indeterminate" and not stories:
            orphan_rows.append({
                "Epic Key":  clickable_key(epic["key"]),
                "Summary":   epic["fields"]["summary"],
                "Status":    status_icon(epic["fields"]["status"]["name"]),
                "Issue":     "⚠️ No stories linked",
            })
        status_name = epic["fields"]["status"]["name"].lower()
        if in_prog and (cat == "new" or "backlog" in status_name or "to do" in status_name):
            for s in in_prog:
                stalled_rows.append({
                    "Epic":         clickable_key(epic["key"]),
                    "Epic Status":  status_icon(epic["fields"]["status"]["name"]),
                    "Story":        clickable_key(s["key"]),
                    "Story Summary": s["fields"]["summary"],
                    "Story Status": status_icon(s["fields"]["status"]["name"]),
                })
    prog.empty()

    if orphan_rows:
        st.subheader("🔴 In-Progress Epics — No Stories")
        st.dataframe(pd.DataFrame(orphan_rows), use_container_width=True, hide_index=True)
    if stalled_rows:
        st.subheader("🟡 Stories Active, Epic Not Started")
        st.dataframe(pd.DataFrame(stalled_rows), use_container_width=True, hide_index=True)
    if not orphan_rows and not stalled_rows:
        st.success("✅ No epic hygiene issues found.")


def run_missing_fields(proj: str):
    if not proj:
        st.warning("Set a Default Project Key in Settings to use this query.")
        return
    jql = (f'project = {proj} AND issuetype = Epic '
           f'AND (fixVersion is EMPTY OR priority is EMPTY) '
           f'AND status in ("Open","In Progress","Feature Ready")')
    issues = jira_search(jql, "summary,status,priority,fixVersions")
    rows = []
    for i in issues:
        f = i["fields"]
        missing = []
        if not f.get("fixVersions"):
            missing.append("Fix Version")
        if not f.get("priority"):
            missing.append("Priority")
        rows.append({
            "Epic Key": clickable_key(i["key"]),
            "Summary":  f["summary"],
            "Status":   status_icon(f["status"]["name"]),
            "Missing":  ", ".join(missing),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.success("✅ No epics with missing fields found.")


def run_team_workload(proj: str):
    jql = "issuetype != Epic AND statusCategory != Done AND assignee is not EMPTY"
    if proj:
        jql += f" AND project = {proj}"
    issues = jira_search(jql, "assignee,status", max_results=500)
    counts: dict = {}
    for i in issues:
        name = (i["fields"].get("assignee") or {}).get("displayName", "Unassigned")
        cat  = i["fields"]["status"].get("statusCategory", {}).get("key", "")
        if name not in counts:
            counts[name] = {"Total": 0, "In Progress": 0, "To Do": 0, "In Review": 0}
        counts[name]["Total"] += 1
        if cat == "indeterminate":  counts[name]["In Progress"] += 1
        elif cat == "new":          counts[name]["To Do"] += 1
        else:                       counts[name]["In Review"] += 1

    if not counts:
        st.info("No open issues found."); return

    total = sum(v["Total"] for v in counts.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Open Issues",  total)
    m2.metric("Assignees",    len(counts))
    m3.metric("Avg / Person", f"{total/len(counts):.1f}")

    df = pd.DataFrame([{"Assignee": k, **v} for k, v in counts.items()])
    df = df.sort_values("Total", ascending=False).reset_index(drop=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

def run_sprint_issues(proj: str):
    jql = "sprint in openSprints()"
    if proj:
        jql += f" AND project = {proj}"
    issues = jira_search(jql + " ORDER BY status ASC", "summary,status,priority,assignee,issuetype")
    if not issues:
        st.info("No issues found in current sprint."); return

    done = sum(1 for i in issues if i["fields"]["status"].get("statusCategory", {}).get("key") == "done")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total",     len(issues))
    m2.metric("Done",      done)
    m3.metric("Remaining", len(issues) - done)
    m4.metric("Complete",  f"{round(done/len(issues)*100)}%")

    # Group issues by assignee
    by_assignee = {}
    for i in issues:
        assignee = (i["fields"].get("assignee") or {}).get("displayName", "Unassigned")
        if assignee not in by_assignee:
            by_assignee[assignee] = []
        by_assignee[assignee].append({
            "Key":      clickable_key(i["key"]),
            "Type":     i["fields"].get("issuetype", {}).get("name", "—"),
            "Summary":  i["fields"]["summary"],
            "Status":   status_icon(i["fields"]["status"]["name"]),
            "Priority": priority_icon((i["fields"].get("priority") or {}).get("name", "")),
        })

    # Display a table for each assignee
    st.divider()
    for assignee in sorted(by_assignee.keys()):
        issues_list = by_assignee[assignee]
        assignee_done = sum(1 for row in issues_list if "✅" in row["Status"])
    
        with st.expander(f"👤 {assignee}  —  {len(issues_list)} issue(s)  •  {assignee_done} done", expanded=True):
            df = pd.DataFrame(issues_list)
            st.dataframe(df, use_container_width=True, hide_index=True)

def run_blocked_issues(proj: str):
    jql = 'statusCategory != Done AND (labels = blocked OR priority = Blocker)'
    if proj:
        jql += f" AND project = {proj}"
    issues = jira_search(jql, "summary,status,priority,assignee")
    if not issues:
        st.success("✅ No blocked issues found."); return
    rows = [{
        "Key":      clickable_key(i["key"]),
        "Summary":  i["fields"]["summary"],
        "Status":   status_icon(i["fields"]["status"]["name"]),
        "Priority": priority_icon((i["fields"].get("priority") or {}).get("name", "")),
        "Assignee": (i["fields"].get("assignee") or {}).get("displayName", "Unassigned"),
    } for i in issues]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def run_my_issues(proj: str):
    jql = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
    if proj:
        jql = f"assignee = currentUser() AND project = {proj} AND statusCategory != Done ORDER BY updated DESC"
    issues = jira_search(jql, "summary,status,priority,project,updated")
    if not issues:
        st.success("✅ No open issues assigned to you."); return
    rows = [{
        "Key":     clickable_key(i["key"]),
        "Project": i["fields"].get("project", {}).get("key", "—"),
        "Summary": i["fields"]["summary"],
        "Status":  status_icon(i["fields"]["status"]["name"]),
        "Priority":priority_icon((i["fields"].get("priority") or {}).get("name", "")),
        "Updated": i["fields"].get("updated", "")[:10],
    } for i in issues]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def run_epics_list(proj: str, query: str = ""):
    jql = "issuetype = Epic AND statusCategory != Done"
    if proj:
        jql += f" AND project = {proj}"
    issues = jira_search(jql, "summary,status,priority,assignee,fixVersions")
    if not issues:
        st.info("No active epics found."); return
    rows = [{
        "Key":         clickable_key(i["key"]),
        "Summary":     i["fields"]["summary"],
        "Status":      status_icon(i["fields"]["status"]["name"]),
        "Fix Version": ", ".join(v["name"] for v in i["fields"].get("fixVersions", [])) or "—",
        "Priority":    priority_icon((i["fields"].get("priority") or {}).get("name", "")),
        "Assignee":    (i["fields"].get("assignee") or {}).get("displayName", "Unassigned"),
    } for i in issues]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def run_general_search(proj: str, query: str):
    clean = query.replace('"', "")
    jql = f'text ~ "{clean}"'
    if proj:
        jql += f" AND project = {proj}"
    jql += " ORDER BY updated DESC"
    issues = jira_search(jql, "summary,status,priority,assignee,issuetype")
    st.caption(f"JQL: `{jql}`")
    if not issues:
        st.info("No results found."); return
    rows = [{
        "Key":      clickable_key(i["key"]),
        "Type":     i["fields"].get("issuetype", {}).get("name", "—"),
        "Summary":  i["fields"]["summary"],
        "Status":   status_icon(i["fields"]["status"]["name"]),
        "Priority": priority_icon((i["fields"].get("priority") or {}).get("name", "")),
        "Assignee": (i["fields"].get("assignee") or {}).get("displayName", "Unassigned"),
    } for i in issues]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 1: MISSING FIELDS PAGE
# ═════════════════════════════════════════════════════════════════════════════
def page_missing_fields():
    st.title("📋 Ongoing Epics With Missing Fields")
    st.caption("Finds active epics where Fix Version or Priority is empty.")
    if not require_config(): return

    proj = project_selector("missing")
    if st.button("Run Check", type="primary") and proj:
        with st.spinner("Checking for missing fields…"):
            try:
                run_missing_fields(proj)
            except Exception as e:
                st.error(f"Error: {e}")


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 2: STORY ALIGNMENT PAGE
# ═════════════════════════════════════════════════════════════════════════════
def page_story_alignment():
    st.title("🔍 Epic-Story Alignment Issues")
    st.caption(
        "Checks epics against their stories for status mismatches. "
        "Includes custom fields: Deliverable Type (`customfield_11007`), "
        "Epic Status (`customfield_10001`), Functional Work Type (`customfield_18801`)."
    )
    if not require_config(): return

    col1, col2 = st.columns([2, 1])
    with col1:
        proj = project_selector("align")
    with col2:
        fix_version = st.text_input("Fix Version", placeholder="e.g. R2025a", key="align_fv")

    if st.button("Run Alignment Check", type="primary"):
        if not proj:
            st.warning("Select a project first."); return
        if not fix_version:
            st.warning("Enter a Fix Version to scope the check."); return

        with st.spinner("Fetching epics and stories…"):
            try:
                _run_alignment(proj, fix_version)
            except Exception as e:
                st.error(f"Error: {e}")


def _run_alignment(proj: str, fix_version: str):
    # Step A: Epics with custom fields
    epic_jql = (
        f'project = {proj} AND issuetype = Epic AND fixVersion = "{fix_version}" '
        f'AND status in ("To Do","In Progress","Feature Ready","Done")'
    )
    epic_issues = jira_search(
        epic_jql,
        "summary,status,assignee,customfield_10001,customfield_11007",
        max_results=100,
    )
    if not epic_issues:
        st.info(f"No epics found for fix version '{fix_version}' in {proj}."); return

    # Build epic map
    epic_map = {}
    for iss in epic_issues:
        f = iss["fields"]
        epic_status   = extract_field(f.get("customfield_10001")) or f["status"]["name"]
        deliverable   = extract_field(f.get("customfield_11007"))
        epic_map[iss["key"]] = {
            "summary":       f["summary"],
            "epic_status":   epic_status,
            "deliverable":   deliverable,
            "assignee":      (f.get("assignee") or {}).get("displayName", "Unassigned"),
            "stories":       [],
        }

    # Step B: Stories via issueFunction, fallback to Epic Link
    story_issues = []
    try:
        story_jql = (
            f'issuetype in (Bug, Story) AND project = {proj} '
            f'AND issueFunction in issuesInEpics("Project = {proj} AND issueType = Epic AND fixVersion = {fix_version}")'
        )
        story_issues = jira_search(
            story_jql,
            "summary,status,issuetype,customfield_10000,customfield_18801",
            max_results=1000,
        )
    except Exception:
        epic_keys = ",".join(f'"{k}"' for k in epic_map)
        fallback_jql = f'"Epic Link" in ({epic_keys}) AND project = {proj}'
        story_issues = jira_search(
            fallback_jql,
            "summary,status,issuetype,customfield_10000,customfield_18801",
            max_results=1000,
        )

    for iss in story_issues:
        f = iss["fields"]
        link = f.get("customfield_10000")
        if link and link in epic_map:
            epic_map[link]["stories"].append({
                "key":                  iss["key"],
                "summary":              f.get("summary", ""),
                "type":                 f.get("issuetype", {}).get("name", "—"),
                "status":               f.get("status", {}).get("name", "Unknown"),
                "functional_work_type": extract_field(f.get("customfield_18801")),
            })

    # ── Epic Overview grouped by assignee ──
    st.subheader(f"Epic Overview — {fix_version}")

    # Group epics by assignee
    by_assignee = {}
    for k, v in epic_map.items():
        assignee = v["assignee"]
        if assignee not in by_assignee:
            by_assignee[assignee] = []
        by_assignee[assignee].append({
            "Epic Key":         clickable_key(k),
            "Summary":          v["summary"],
            "Epic Status":      status_icon(v["epic_status"]),
            "Deliverable Type": v["deliverable"],
            "# Stories":        len(v["stories"]),
        })

    # Display a table per assignee
    for assignee in sorted(by_assignee.keys()):
        epics_list = by_assignee[assignee]
        with st.expander(f"👤 {assignee}  —  {len(epics_list)} epic(s)", expanded=True):
            df = pd.DataFrame(epics_list)
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Detect alignment issues ──
    alignment_issues = []
    for epic_key, info in epic_map.items():
        active = [s for s in info["stories"] if s["status"] in ("To Do", "In Progress")]
        if info["epic_status"] == "Done" and active:
            for s in active:
                alignment_issues.append({
                    "Epic":         clickable_key(epic_key),
                    "Epic Status":  status_icon(info["epic_status"]),
                    "Story":        clickable_key(s["key"]),
                    "Story Summary": s["summary"],
                    "Func. Work Type": s["functional_work_type"],
                    "Story Status": status_icon(s["status"]),
                    "Warning":      "Epic Done but story still active",
                })
        if info["epic_status"] == "In Progress" and not info["stories"]:
            alignment_issues.append({
                "Epic":         clickable_key(epic_key),
                "Epic Status":  status_icon(info["epic_status"]),
                "Story":        "—",
                "Story Summary": "—",
                "Func. Work Type": "—",
                "Story Status": "—",
                "Warning":      "Epic In Progress but no stories linked",
            })

    st.divider()
    st.subheader("⚠️ Alignment Issues")
    if alignment_issues:
        st.dataframe(pd.DataFrame(alignment_issues), use_container_width=True, hide_index=True)
    else:
        st.success("✅ No epic-story alignment issues found.")


# ═════════════════════════════════════════════════════════════════════════════
#  FULL HYGIENE REPORT
# ═════════════════════════════════════════════════════════════════════════════
def page_full_hygiene():
    st.title("⚠️ Full Epic Hygiene Report")
    st.caption("Runs Section 1 (Missing Fields) + Section 2 (Story Alignment) together.")
    if not require_config(): return

    col1, col2 = st.columns([2, 1])
    with col1:
        proj = project_selector("full")
    with col2:
        fix_version = st.text_input("Fix Version (for Section 2)", placeholder="e.g. R2025a", key="full_fv")

    if st.button("Run Full Report", type="primary"):
        if not proj:
            st.warning("Select a project first."); return

        with st.spinner("Running Section 1 — Missing Fields…"):
            try:
                st.subheader("📋 Section 1 — Ongoing Epics With Missing Fields")
                run_missing_fields(proj)
            except Exception as e:
                st.error(f"Section 1 error: {e}")

        st.divider()

        if fix_version:
            with st.spinner("Running Section 2 — Story Alignment…"):
                try:
                    st.subheader("🔍 Section 2 — Epic-Story Alignment")
                    _run_alignment(proj, fix_version)
                except Exception as e:
                    st.error(f"Section 2 error: {e}")
        else:
            st.info("💡 Enter a Fix Version above to also run the Story Alignment check (Section 2).")


# ═════════════════════════════════════════════════════════════════════════════
#  SECTION 3: FIX VERSION CHANGES PAGE
# ═════════════════════════════════════════════════════════════════════════════
def page_fix_version_changes():
    st.title("🔄 Fix Version Changes Tracker")
    st.caption(
        "Finds epics where the fix version was changed between two values, "
        "based on the issue changelog. Results are grouped by assignee.\n\n"
        "💡 Use `EMPTY` (case-insensitive) to match issues with no fix version set."
    )
    if not require_config(): return

    proj = project_selector("fv")

    # Dynamic From→To pairs
    st.markdown("**Fix Version Change Pairs**")
    if "fix_version_changes" not in st.session_state:
        st.session_state.fix_version_changes = [{"original": "", "new": ""}]

    for idx, change in enumerate(st.session_state.fix_version_changes):
        c1, c2, c3 = st.columns([5, 5, 1])
        with c1:
            orig = st.text_input(
                f"From #{idx+1}", value=change["original"],
                key=f"fv_orig_{idx}", placeholder="e.g. R2024a or EMPTY",
            )
            st.session_state.fix_version_changes[idx]["original"] = orig
        with c2:
            new_v = st.text_input(
                f"To #{idx+1}", value=change["new"],
                key=f"fv_new_{idx}", placeholder="e.g. R2025a or EMPTY",
            )
            st.session_state.fix_version_changes[idx]["new"] = new_v
        with c3:
            st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
            if idx > 0 and st.button("✕", key=f"fv_rm_{idx}"):
                st.session_state.fix_version_changes.pop(idx)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    col_add, col_run, _ = st.columns([1, 1, 4])
    with col_add:
        if st.button("➕ Add pair"):
            st.session_state.fix_version_changes.append({"original": "", "new": ""})
            st.rerun()
    with col_run:
        search = st.button("Search Changes", type="primary")

    if search:
        if not proj:
            st.warning("Select a project first."); return
        valid = [c for c in st.session_state.fix_version_changes if c["original"].strip() and c["new"].strip()]
        if not valid:
            st.warning("Enter at least one From → To pair."); return

        with st.spinner("Scanning changelogs…"):
            try:
                results = _find_fv_changes(proj, valid)
            except Exception as e:
                st.error(f"Error: {e}"); return

        if not results:
            st.info("No epics found with the specified fix version changes."); return

        total = sum(len(v) for v in results.values())
        st.success(f"Found {total} epic(s) across {len(results)} assignee(s).")

        for assignee, epics in sorted(results.items()):
            with st.expander(f"👤 {assignee}  —  {len(epics)} epic(s)", expanded=True):
                df = pd.DataFrame(epics)
                st.dataframe(df, use_container_width=True, hide_index=True)


def _find_fv_changes(proj: str, pairs: list) -> dict:
    conditions = []
    for p in pairs:
        orig = "EMPTY" if p["original"].upper() == "EMPTY" else f'"{p["original"]}"'
        new  = "EMPTY" if p["new"].upper()      == "EMPTY" else f'"{p["new"]}"'
        conditions.append(f"fixVersion changed from {orig} to {new}")

    jql = f'project = {proj} AND issuetype = Epic AND ({" OR ".join(conditions)})'
    issues = jira_search(jql, "summary,assignee,fixVersions", max_results=1000, expand="changelog")

    by_assignee: dict = {}
    for iss in issues:
        f        = iss["fields"]
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        current_fv = ", ".join(v["name"] for v in f.get("fixVersions", [])) or "EMPTY"

        # Parse changelog for original fix version
        original_fv = "Unknown"
        for history in reversed(iss.get("changelog", {}).get("histories", [])):
            if original_fv != "Unknown":
                break
            for item in history.get("items", []):
                if item.get("field") != "Fix Version":
                    continue
                from_str = item.get("fromString")
                to_str   = item.get("toString")
                for pair in pairs:
                    from_empty = pair["original"].upper() == "EMPTY"
                    to_empty   = pair["new"].upper()      == "EMPTY"
                    from_match = (from_str is None or from_str == "") if from_empty else (from_str and pair["original"] in from_str)
                    to_match   = (to_str   is None or to_str   == "") if to_empty   else (to_str   and pair["new"]      in to_str)
                    if from_match and to_match:
                        original_fv = from_str or "EMPTY"
                        break
                if original_fv != "Unknown":
                    break

        by_assignee.setdefault(assignee, []).append({
            "Epic Key":            clickable_key(iss["key"]),
            "Summary":             f.get("summary", ""),
            "Original Fix Version": original_fv,
            "New Fix Version":     current_fv,
        })

    return by_assignee


# ═════════════════════════════════════════════════════════════════════════════
#  QUICK PAGES (Sprint / Workload / Blocked / My Issues)
# ═════════════════════════════════════════════════════════════════════════════
def page_sprint():
    st.title("🏃 Current Sprint Issues")
    if not require_config(): return
    proj = project_selector("sprint")
    if st.button("Load Sprint", type="primary") and proj:
        with st.spinner("Fetching sprint issues…"):
            try:
                run_sprint_issues(proj)
            except Exception as e:
                st.error(f"Error: {e}")

def page_workload():
    st.title("👥 Team Workload")
    if not require_config(): return
    proj = project_selector("workload")
    if st.button("Load Workload", type="primary") and proj:
        with st.spinner("Fetching team workload…"):
            try:
                run_team_workload(proj)
            except Exception as e:
                st.error(f"Error: {e}")

def page_blocked():
    st.title("🚧 Blocked Issues")
    if not require_config(): return
    proj = project_selector("blocked")
    if st.button("Find Blocked Issues", type="primary") and proj:
        with st.spinner("Fetching blocked issues…"):
            try:
                run_blocked_issues(proj)
            except Exception as e:
                st.error(f"Error: {e}")

def page_my_issues():
    st.title("👤 My Open Issues")
    if not require_config(): return
    proj = project_selector("me")
    if st.button("Load My Issues", type="primary"):
        with st.spinner("Fetching your issues…"):
            try:
                run_my_issues(proj)
            except Exception as e:
                st.error(f"Error: {e}")


# ═════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═════════════════════════════════════════════════════════════════════════════
PAGES = {
    "⚙️  Settings":            page_settings,
    "◈  Ask Anything":         page_ask,
    "📋  Missing Fields":      page_missing_fields,
    "🔍  Story Alignment":     page_story_alignment,
    "⚠️  Full Hygiene Report": page_full_hygiene,
    "🔄  Fix Version Changes": page_fix_version_changes,
    "🏃  Current Sprint":      page_sprint,
    "👥  Team Workload":       page_workload,
    "👤  My Issues":           page_my_issues,
}

PAGES[page]()