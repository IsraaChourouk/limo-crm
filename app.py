import streamlit as st
import pandas as pd
from datetime import date
import io
from supabase import create_client

# ─────────────────────────────
# SUPABASE
# ─────────────────────────────
SUPABASE_URL = "https://urgotpfzfuydxaklopnp.supabase.co"
SUPABASE_KEY = "YOUR_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def get_clients():
    return supabase.table("clients").select("*").execute().data

def get_trips():
    return supabase.table("trips").select("*").execute().data

def get_invoices():
    return supabase.table("invoices").select("*").execute().data


def get_setting(key, default=""):
    res = supabase.table("settings").select("value").eq("key", key).execute().data
    return res[0]["value"] if res else default


def set_setting(key, value):
    supabase.table("settings").upsert({"key": key, "value": value}).execute()

# ─────────────────────────────
# PAGE SETUP
# ─────────────────────────────
st.set_page_config(page_title="Limo CRM", layout="wide")

page = st.sidebar.radio("Navigation",
    ["📊 Dashboard", "👥 Clients", "🗺️ Trips", "📄 Invoices", "⚙️ Settings"]
)

page_name = page.split(" ", 1)[1]

# ─────────────────────────────
# DASHBOARD
# ─────────────────────────────
if page_name == "Dashboard":
    st.title("📊 Dashboard")

    clients = get_clients()
    trips = get_trips()
    invoices = get_invoices()

    n_clients = len(clients)
    n_trips = len(trips)
    n_invoices = len(invoices)
    revenue = sum(i.get("grand_total", 0) for i in invoices)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clients", n_clients)
    c2.metric("Trips", n_trips)
    c3.metric("Invoices", n_invoices)
    c4.metric("Revenue", f"${revenue:.2f}")

    st.subheader("Recent Invoices")
    recent = sorted(invoices, key=lambda x: x["id"], reverse=True)[:5]
    st.dataframe(pd.DataFrame(recent), use_container_width=True)

# ─────────────────────────────
# CLIENTS
# ─────────────────────────────
elif page_name == "Clients":
    st.title("👥 Clients")

    clients = get_clients()
    df = pd.DataFrame(clients)

    search = st.text_input("Search clients")

    if search:
        df = df[
            df["client_name"].str.contains(search, case=False, na=False)
            | df["account_number"].str.contains(search, case=False, na=False)
            | df["company_name"].fillna("").str.contains(search, case=False)
        ]

    st.dataframe(df, use_container_width=True)

# ─────────────────────────────
# TRIPS
# ─────────────────────────────
elif page_name == "Trips":
    st.title("🗺️ Trips")

    clients = pd.DataFrame(get_clients())
    trips = pd.DataFrame(get_trips())

    if clients.empty:
        st.warning("No clients")
    else:
        st.dataframe(trips, use_container_width=True)

# ─────────────────────────────
# INVOICES
# ─────────────────────────────
elif page_name == "Invoices":
    st.title("📄 Invoices")

    invoices = pd.DataFrame(get_invoices())

    if invoices.empty:
        st.info("No invoices yet")
    else:
        st.dataframe(invoices, use_container_width=True)

# ─────────────────────────────
# SETTINGS
# ─────────────────────────────
elif page_name == "Settings":
    st.title("⚙️ Settings")

    name = st.text_input("Company Name", get_setting("co_name", "EXECUTIVE LIMO"))

    if st.button("Save"):
        set_setting("co_name", name)
        st.success("Saved")
