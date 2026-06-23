import streamlit as st
import pandas as pd
from datetime import date
import io
import base64
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image as RLImage
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL = "https://urgotpfzfuydxaklopnp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVyZ290cGZ6ZnV5ZHhha2xvcG5wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyMzI4MDUsImV4cCI6MjA5NzgwODgwNX0.ovytSOtNYvhYHUA1rrXCti4XCzatIXtawYwljgq9iRE"

@st.cache_resource
def get_sb() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

sb = get_sb()

# ── Helpers ───────────────────────────────────────────────
def next_account_number():
    r = sb.table("clients").select("account_number").order("id", desc=True).limit(1).execute()
    if not r.data:
        return "ACC-1001"
    try:
        return f"ACC-{int(r.data[0]['account_number'].split('-')[1]) + 1}"
    except:
        return "ACC-1001"

def next_invoice_number():
    r = sb.table("invoices").select("invoice_number").order("id", desc=True).limit(1).execute()
    if not r.data:
        return "INV-0001"
    try:
        return f"INV-{int(r.data[0]['invoice_number'].split('-')[1]) + 1:04d}"
    except:
        return "INV-0001"

def get_setting(key, default=""):
    r = sb.table("settings").select("value").eq("key", key).execute()
    return r.data[0]["value"] if r.data else default

def set_setting(key, value):
    sb.table("settings").upsert({"key": key, "value": value}).execute()


# ── Validation ────────────────────────────────────────────
import re

def validate_email(email):
    if not email:
        return True
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))

def validate_phone(phone):
    if not phone:
        return True
    digits = re.sub(r"[\s\(\)\-\+\.]", "", phone)
    return digits.isdigit() and 7 <= len(digits) <= 15

def validate_required(value, label, errors):
    if not str(value).strip():
        errors.append(f"⚠️ **{label}** is required.")

def show_errors(errors):
    if errors:
        st.warning("\n\n".join(errors))
        return True
    return False

# ── PDF ───────────────────────────────────────────────────
def generate_invoice_pdf(client, trips_data, invoice_number, invoice_date, grand_total,
                          logo_bytes=None, company_info=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)

    GOLD  = colors.HexColor("#B8860B")
    DARK  = colors.HexColor("#1a1a2e")
    LGRAY = colors.HexColor("#f7f7f7")
    WHITE = colors.white

    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    co = company_info or {}
    co_name    = co.get("name",    "EXECUTIVE LIMO")
    co_tagline = co.get("tagline", "Premium Chauffeur Services")
    co_address = co.get("address", "123 Luxury Drive, Beverly Hills, CA 90210")
    co_phone   = co.get("phone",   "(310) 555-0100")
    co_email   = co.get("email",   "billing@executivelimo.com")

    story = []

    # ── Header ──
    if logo_bytes:
        logo_img = RLImage(io.BytesIO(logo_bytes), width=1.4*inch, height=1.0*inch)
        logo_img.hAlign = 'LEFT'
        logo_cell = logo_img
    else:
        logo_cell = Paragraph(f"<b>{co_name}</b>",
                              S('lt', fontSize=20, textColor=DARK, fontName='Helvetica-Bold'))

    company_cell = [
        Paragraph(f"<b>{co_name}</b>",
                  S('cn', fontSize=15, textColor=DARK, fontName='Helvetica-Bold', spaceAfter=2)),
        Paragraph(co_tagline,
                  S('ct', fontSize=8, textColor=colors.HexColor("#666"), fontName='Helvetica', spaceAfter=2)),
        Paragraph(co_address,
                  S('ca', fontSize=8, textColor=colors.HexColor("#444"), fontName='Helvetica', spaceAfter=1)),
        Paragraph(f"Tel: {co_phone}   Email: {co_email}",
                  S('cp', fontSize=8, textColor=colors.HexColor("#444"), fontName='Helvetica')),
    ]

    inv_cell = [
        Paragraph("INVOICE",
                  S('ih', fontSize=22, textColor=GOLD, fontName='Helvetica-Bold', alignment=TA_RIGHT, spaceAfter=4)),
        Paragraph(f"<b>Invoice #:</b> {invoice_number}",
                  S('i1', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"<b>Date:</b> {invoice_date}",
                  S('i2', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"<b>Account:</b> {client.get('account_number','')}",
                  S('i3', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT)),
    ]

    hdr = Table([[logo_cell, company_cell, inv_cell]],
                colWidths=[1.5*inch, 3.3*inch, 2.6*inch])
    hdr.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING',  (1,0), (1,0),   10),
        ('RIGHTPADDING', (2,0), (2,0),   0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=10))

    # ── Bill To ──
    lbl  = S('lbl', fontSize=7,  textColor=colors.HexColor("#999"), fontName='Helvetica-Bold', spaceAfter=3)
    bval = S('bv',  fontSize=11, textColor=DARK, fontName='Helvetica-Bold', spaceAfter=2)
    val  = S('v',   fontSize=9,  textColor=DARK, fontName='Helvetica', spaceAfter=1)

    bill = [Paragraph("BILL TO", lbl),
            Paragraph(client.get('client_name',''), bval)]
    for field in ['company_name','phone','email','address']:
        if client.get(field):
            bill.append(Paragraph(client[field], val))

    bt = Table([[bill, ""]], colWidths=[3.8*inch, 3.6*inch])
    bt.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,0), LGRAY),
        ('TOPPADDING',    (0,0), (0,0), 8),
        ('BOTTOMPADDING', (0,0), (0,0), 10),
        ('LEFTPADDING',   (0,0), (0,0), 10),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(bt)
    story.append(Spacer(1, 12))

    # ── Trip Table ──
    headers   = ['Date','Conf #','Passenger','Service Type','Vehicle',
                 'Base Rate','Gratuity','Fuel Charge','Misc','Total']
    col_widths = [0.7*inch, 0.7*inch, 1.0*inch, 1.05*inch, 0.7*inch,
                  0.65*inch, 0.65*inch, 0.7*inch, 0.5*inch, 0.65*inch]

    hs = S('th',  fontSize=7.5, textColor=WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)
    cs = S('td',  fontSize=8,   textColor=DARK,  fontName='Helvetica',      alignment=TA_CENTER)
    ns = S('num', fontSize=8,   textColor=DARK,  fontName='Helvetica',      alignment=TA_RIGHT)
    gs = S('gt',  fontSize=9,   textColor=WHITE, fontName='Helvetica-Bold', alignment=TA_RIGHT)

    rows = [[Paragraph(h, hs) for h in headers]]
    for t in trips_data:
        rows.append([
            Paragraph(str(t.get('pickup_date','')),         cs),
            Paragraph(str(t.get('confirmation_number','')), cs),
            Paragraph(str(t.get('passenger_name','')),      cs),
            Paragraph(str(t.get('service_type','')),        cs),
            Paragraph(str(t.get('vehicle_type','')),        cs),
            Paragraph(f"${t.get('base_rate',0):.2f}",       ns),
            Paragraph(f"${t.get('gratuity',0):.2f}",        ns),
            Paragraph(f"${t.get('fuel_charge',0):.2f}",     ns),
            Paragraph(f"${t.get('misc_charge',0):.2f}",     ns),
            Paragraph(f"${t.get('trip_total',0):.2f}",      ns),
        ])

    rows.append([
        Paragraph("", gs), Paragraph("", gs), Paragraph("", gs), Paragraph("", gs),
        Paragraph("GRAND TOTAL", gs),
        Paragraph("", gs), Paragraph("", gs), Paragraph("", gs), Paragraph("", gs),
        Paragraph(f"${grand_total:.2f}", gs),
    ])

    n = len(rows)
    tt = Table(rows, colWidths=col_widths, repeatRows=1)
    tt.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),  (-1,0),  DARK),
        ('TOPPADDING',    (0,0),  (-1,0),  6),
        ('BOTTOMPADDING', (0,0),  (-1,0),  6),
        ('ROWBACKGROUNDS',(0,1),  (-1,n-2),[WHITE, LGRAY]),
        ('TOPPADDING',    (0,1),  (-1,-2), 5),
        ('BOTTOMPADDING', (0,1),  (-1,-2), 5),
        ('LEFTPADDING',   (0,0),  (-1,-1), 4),
        ('RIGHTPADDING',  (0,0),  (-1,-1), 4),
        ('LINEBELOW',     (0,0),  (-1,-2), 0.3, colors.HexColor("#dddddd")),
        ('BACKGROUND',    (0,-1), (-1,-1), DARK),
        ('TOPPADDING',    (0,-1), (-1,-1), 7),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 7),
        ('LINEABOVE',     (0,-1), (-1,-1), 2, GOLD),
        ('SPAN',          (4,-1), (8,-1)),
        ('ALIGN',         (4,-1), (8,-1),  'RIGHT'),
    ]))
    story.append(tt)
    story.append(Spacer(1, 20))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#cccccc"), spaceAfter=6))
    story.append(Paragraph(
        "Thank you for choosing us. Payment is due within 30 days. "
        "Please reference your invoice number on all payments.",
        S('ft', fontSize=8, textColor=colors.HexColor("#888"),
          fontName='Helvetica', alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# ── Page config ───────────────────────────────────────────
st.set_page_config(page_title="Limo CRM", page_icon="🚗", layout="wide")
st.markdown("""
<style>
/* ── Global ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0f0f0f !important;
    color: #f0f0f0;
}
[data-testid="stMain"] { background-color: #0f0f0f !important; }
[data-testid="block-container"] { padding-top: 1.5rem !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #1a1a1a !important;
    border-right: 1px solid #2a2a2a;
}
[data-testid="stSidebar"] * { color: #f0f0f0 !important; }
[data-testid="stSidebar"] .stRadio > label { display: none; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap: 4px; display: flex; flex-direction: column; }
[data-testid="stSidebar"] .stRadio label {
    display: flex !important; align-items: center;
    padding: 10px 16px; border-radius: 10px;
    cursor: pointer; font-size: 0.95rem;
    transition: background 0.2s;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #2a2a2a !important; }
[data-testid="stSidebar"] .stRadio input:checked + div { color: #e8b84b !important; }

/* ── Quick Stat cards ── */
.qs-card {
    background: #1c1c1c;
    border-radius: 16px;
    padding: 20px 18px;
    display: flex; flex-direction: column;
    border: 1px solid #2a2a2a;
    position: relative; overflow: hidden;
    min-height: 110px;
}
.qs-card.urgent { border-color: #e8b84b; }
.qs-label { font-size: 0.78rem; color: #888; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; margin-bottom: 10px; }
.qs-value { font-size: 2.2rem; font-weight: 800; color: #ffffff; line-height: 1; }
.qs-sub   { font-size: 0.78rem; color: #666; margin-top: 6px; }
.qs-icon  { position: absolute; right: 16px; top: 50%; transform: translateY(-50%); font-size: 2rem; opacity: 0.18; }
.qs-card.urgent .qs-label { color: #e8b84b; }
.qs-card.urgent .qs-value { color: #e8b84b; }

/* ── Section title ── */
.section-title {
    font-size: 1.15rem; font-weight: 700;
    color: #ffffff; margin: 28px 0 14px 0;
    letter-spacing: 0.01em;
}

/* ── Trip cards ── */
.trip-card {
    background: #1c1c1c;
    border-radius: 16px;
    padding: 18px;
    border: 1px solid #2a2a2a;
    margin-bottom: 12px;
    position: relative;
}
.trip-card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.badge {
    background: #e8b84b; color: #000;
    font-size: 0.7rem; font-weight: 800;
    padding: 4px 10px; border-radius: 20px;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.badge.red { background: #ff4444; color: #fff; }
.pickup-time { font-size: 0.8rem; color: #aaa; }
.pickup-time span { font-weight: 700; color: #fff; font-size: 1rem; }
.trip-tag {
    display: inline-flex; align-items: center; gap: 5px;
    background: #2a2a2a; border-radius: 8px;
    padding: 4px 10px; font-size: 0.75rem; color: #ccc;
    margin-bottom: 8px;
}
.trip-field-label { font-size: 0.68rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
.trip-field-value { font-size: 0.95rem; font-weight: 700; color: #fff; }

/* ── Ongoing trip row ── */
.ongoing-row {
    background: #1c1c1c; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 8px;
    display: flex; align-items: center; justify-content: space-between;
    border: 1px solid #2a2a2a;
}
.ongoing-info { display: flex; align-items: center; gap: 12px; }
.ongoing-dot { width: 36px; height: 36px; background: #2a2a2a; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }
.ongoing-main { font-size: 0.9rem; font-weight: 700; color: #fff; }
.ongoing-sub  { font-size: 0.75rem; color: #666; }
.en-route-badge {
    background: #1a1a1a; border: 1px solid #e8b84b;
    color: #e8b84b; font-size: 0.7rem; font-weight: 700;
    padding: 5px 12px; border-radius: 8px; letter-spacing: 0.06em;
}

/* ── Greeting ── */
.greeting-bar {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 24px;
}
.greeting-text { font-size: 1.4rem; font-weight: 800; color: #fff; }
.greeting-sub  { font-size: 0.85rem; color: #666; margin-top: 2px; }

/* ── Buttons ── */
.stButton>button {
    background: #e8b84b; color: #000;
    border-radius: 10px; border: none;
    font-weight: 700; padding: 10px 20px;
}
.stButton>button:hover { background: #f5c842; color: #000; }

/* ── Inputs ── */
.stTextInput input, .stTextArea textarea, .stSelectbox div {
    background: #1c1c1c !important;
    border: 1px solid #2a2a2a !important;
    color: #fff !important; border-radius: 10px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #e8b84b !important;
    box-shadow: 0 0 0 2px rgba(232,184,75,0.15) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: #1c1c1c; border-radius: 10px; padding: 4px; }
.stTabs [data-baseweb="tab"] { color: #888; border-radius: 8px; }
.stTabs [aria-selected="true"] { background: #e8b84b !important; color: #000 !important; font-weight: 700; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { background: #1c1c1c; border-radius: 12px; }

/* ── Expander ── */
.streamlit-expanderHeader { background: #1c1c1c !important; border-radius: 10px; color: #fff !important; }
details { background: #1c1c1c; border-radius: 10px; border: 1px solid #2a2a2a !important; }

/* ── Hide Streamlit default elements ── */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 8px 10px 8px;">
        <div style="font-size:1.3rem; font-weight:800; color:#e8b84b; margin-bottom:4px;">🚗 Limo CRM</div>
        <div style="font-size:0.75rem; color:#555;">Management System</div>
    </div>
    <hr style="border-color:#2a2a2a; margin: 8px 0 16px 0;">
    """, unsafe_allow_html=True)
    page = st.radio("Menu", [
        "📊 Dashboard", "👥 Clients", "🗺️ Trips", "📄 Invoices", "⚙️ Settings"
    ])

page_name = page.split(" ", 1)[1]

# ══════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════
if page_name == "Dashboard":

    # ── Data ──
    n_clients  = len(sb.table("clients").select("id").execute().data)
    n_trips    = len(sb.table("trips").select("id").execute().data)
    n_invoices = len(sb.table("invoices").select("id").execute().data)
    inv_data   = sb.table("invoices").select("grand_total").execute().data
    revenue    = sum(r["grand_total"] or 0 for r in inv_data)
    recent_trips = sb.table("trips").select("*, clients(client_name, account_number)").order("id", desc=True).limit(5).execute().data
    recent_invoices = sb.table("invoices").select("*, clients(client_name)").order("id", desc=True).limit(5).execute().data

    # ── Greeting ──
    st.markdown("""
    <div class="greeting-bar">
        <div>
            <div class="greeting-text">👋 Welcome back!</div>
            <div class="greeting-sub">Here's what's happening today</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick Stats ──
    st.markdown('<div class="section-title">Quick Stats</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""
    <div class="qs-card">
        <div class="qs-label">Total Clients</div>
        <div class="qs-value">{n_clients}</div>
        <div class="qs-sub">Registered accounts</div>
        <div class="qs-icon">👥</div>
    </div>""", unsafe_allow_html=True)
    c2.markdown(f"""
    <div class="qs-card">
        <div class="qs-label">Total Trips</div>
        <div class="qs-value">{n_trips}</div>
        <div class="qs-sub">All time trips logged</div>
        <div class="qs-icon">🗺️</div>
    </div>""", unsafe_allow_html=True)
    c3.markdown(f"""
    <div class="qs-card">
        <div class="qs-label">Total Invoices</div>
        <div class="qs-value">{n_invoices}</div>
        <div class="qs-sub">Generated invoices</div>
        <div class="qs-icon">📄</div>
    </div>""", unsafe_allow_html=True)
    c4.markdown(f"""
    <div class="qs-card urgent">
        <div class="qs-label">Total Revenue</div>
        <div class="qs-value">${revenue:,.0f}</div>
        <div class="qs-sub">From all invoices</div>
        <div class="qs-icon">💰</div>
    </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Recent Trips ──
    col_left, col_right = st.columns([1.1, 0.9])

    with col_left:
        st.markdown('<div class="section-title">Recent Trips</div>', unsafe_allow_html=True)
        if not recent_trips:
            st.markdown('<div class="trip-card"><div style="color:#555;text-align:center;padding:20px;">No trips yet</div></div>', unsafe_allow_html=True)
        for t in recent_trips:
            cl = t.get("clients") or {}
            svc_icon = "✈️" if "Airport" in (t.get("service_type") or "") else "🚗"
            st.markdown(f"""
            <div class="trip-card">
                <div class="trip-card-top">
                    <span class="badge">{"Airport" if "Airport" in (t.get("service_type") or "") else t.get("service_type","Trip")}</span>
                    <div class="pickup-time">📅 <span>{t.get("pickup_date","")}</span></div>
                </div>
                <div class="trip-tag">{svc_icon} {t.get("pickup_location","—")}</div>
                <div style="display:flex; gap:32px; margin-top:10px;">
                    <div>
                        <div class="trip-field-label">Passenger</div>
                        <div class="trip-field-value">{t.get("passenger_name","—")}</div>
                    </div>
                    <div>
                        <div class="trip-field-label">Vehicle</div>
                        <div class="trip-field-value">{t.get("vehicle_type","—")}</div>
                    </div>
                    <div>
                        <div class="trip-field-label">Total</div>
                        <div class="trip-field-value" style="color:#e8b84b;">${t.get("trip_total",0):.2f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Recent Invoices ──
    with col_right:
        st.markdown('<div class="section-title">Recent Invoices</div>', unsafe_allow_html=True)
        if not recent_invoices:
            st.markdown('<div class="ongoing-row"><span style="color:#555;">No invoices yet</span></div>', unsafe_allow_html=True)
        for inv in recent_invoices:
            cl = inv.get("clients") or {}
            st.markdown(f"""
            <div class="ongoing-row">
                <div class="ongoing-info">
                    <div class="ongoing-dot">📄</div>
                    <div>
                        <div class="ongoing-main">{cl.get("client_name","—")}</div>
                        <div class="ongoing-sub">{inv.get("invoice_number","")} &nbsp;·&nbsp; {inv.get("invoice_date","")}</div>
                    </div>
                </div>
                <div class="en-route-badge">${inv.get("grand_total",0):,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════
# CLIENTS
# ══════════════════════════════════════════
elif page_name == "Clients":
    st.title("👥 Client Management")
    tab1, tab2, tab3 = st.tabs(["➕ Add Client", "🔍 Search / Edit", "📋 All Clients"])

    with tab1:
        st.subheader("Add New Client")
        acc = next_account_number()
        st.info(f"Account Number will be: **{acc}**")
        with st.form("add_client"):
            c1,c2  = st.columns(2)
            name    = c1.text_input("Client Name *",     placeholder="e.g. John Smith")
            company = c2.text_input("Company Name",      placeholder="e.g. ABC Corp")
            phone   = c1.text_input("Phone",             placeholder="e.g. +1 310 555 0100")
            email   = c2.text_input("Email",             placeholder="e.g. john@email.com")
            address = st.text_input("Billing Address *", placeholder="e.g. 123 Main St, Los Angeles, CA")
            notes   = st.text_area("Notes", height=80)
            if st.form_submit_button("✅ Save Client", use_container_width=True):
                errors = []
                validate_required(name,    "Client Name",     errors)
                validate_required(address, "Billing Address", errors)
                if phone and not validate_phone(phone):
                    errors.append("⚠️ **Phone** format is invalid. Use digits only, e.g. +1 310 555 0100")
                if email and not validate_email(email):
                    errors.append("⚠️ **Email** format is invalid. Use format: name@example.com")
                if not show_errors(errors):
                    sb.table("clients").insert({
                        "account_number": acc, "client_name": name.strip(),
                        "company_name": company.strip(), "phone": phone.strip(),
                        "email": email.strip(), "address": address.strip(), "notes": notes.strip()
                    }).execute()
                    st.success(f"✅ Client **{name}** added with account **{acc}**!")
                    st.rerun()

    with tab2:
        search = st.text_input("Search by name, company, or account number")
        if search:
            data = sb.table("clients").select("*").or_(
                f"client_name.ilike.%{search}%,company_name.ilike.%{search}%,account_number.ilike.%{search}%"
            ).execute().data
        else:
            data = sb.table("clients").select("*").order("id", desc=True).limit(20).execute().data

        for row in data:
            with st.expander(f"**{row['account_number']}** — {row['client_name']} | {row.get('company_name','')}"):
                with st.form(f"edit_{row['id']}"):
                    c1,c2   = st.columns(2)
                    name    = c1.text_input("Client Name",  row['client_name'])
                    company = c2.text_input("Company",      row.get('company_name','') or '')
                    phone   = c1.text_input("Phone",        row.get('phone','') or '')
                    email   = c2.text_input("Email",        row.get('email','') or '')
                    address = st.text_input("Address",      row.get('address','') or '')
                    notes   = st.text_area("Notes",         row.get('notes','') or '', height=70)
                    ca, cb  = st.columns(2)
                    if ca.form_submit_button("💾 Update"):
                        errors = []
                        validate_required(name,    "Client Name",     errors)
                        validate_required(address, "Billing Address", errors)
                        validate_required(phone,   "Phone",           errors)
                        validate_required(email,   "Email",           errors)
                        if phone and not validate_phone(phone):
                            errors.append("⚠️ **Phone** format is invalid. Use digits only, e.g. +1 310 555 0100")
                        if email and not validate_email(email):
                            errors.append("⚠️ **Email** format is invalid. Use format: name@example.com")
                        if not show_errors(errors):
                            sb.table("clients").update({
                                "client_name": name.strip(), "company_name": company.strip(),
                                "phone": phone.strip(), "email": email.strip(),
                                "address": address.strip(), "notes": notes.strip()
                            }).eq("id", row['id']).execute()
                            st.success("✅ Updated!"); st.rerun()
                    if cb.form_submit_button("🗑️ Delete"):
                        sb.table("clients").delete().eq("id", row['id']).execute()
                        st.warning("Deleted."); st.rerun()

    with tab3:
        data = sb.table("clients").select("account_number,client_name,company_name,phone,email").order("id", desc=True).execute().data
        if data:
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        else:
            st.info("No clients yet.")

# ══════════════════════════════════════════
# TRIPS
# ══════════════════════════════════════════
elif page_name == "Trips":
    st.title("🗺️ Trip Management")
    tab1, tab2 = st.tabs(["➕ Add Trip", "📋 View Trips"])

    with tab1:
        clients = sb.table("clients").select("id,account_number,client_name").order("client_name").execute().data
        if not clients:
            st.warning("No clients yet. Please add a client first.")
        else:
            opts = {f"{c['account_number']} — {c['client_name']}": c['id'] for c in clients}
            sel  = st.selectbox("Select Client *", list(opts.keys()))
            cid  = opts[sel]

            with st.form("add_trip"):
                st.subheader("Trip Details")
                c1,c2      = st.columns(2)
                conf_num   = c1.text_input("Confirmation Number")
                passenger  = c2.text_input("Passenger Name")
                svc_type   = c1.selectbox("Service Type", ["Airport Transfer","Point-to-Point","As Directed","Other"])
                veh_type   = c2.text_input("Vehicle Type", placeholder="e.g. Sedan, SUV, Stretch Limo")
                pickup_dt  = c1.date_input("Pickup Date", value=date.today())
                pickup_tm  = c2.time_input("Pickup Time")
                pickup_loc = c1.text_input("Pickup Location")
                dropoff    = c2.text_input("Drop-off Location")
                stops      = st.text_input("Stops (optional)")
                driver     = st.text_input("Driver Name")

                st.subheader("Charges")
                c1,c2,c3,c4 = st.columns(4)
                base  = c1.number_input("Base Rate ($)",   min_value=0.0, step=0.01)
                grat  = c2.number_input("Gratuity ($)",    min_value=0.0, step=0.01)
                fuel  = c3.number_input("Fuel Charge ($)", min_value=0.0, step=0.01)
                misc  = c4.number_input("Misc ($)",        min_value=0.0, step=0.01)
                total = base + grat + fuel + misc
                st.metric("Trip Total", f"${total:.2f}")

                submitted = st.form_submit_button("✅ Save Trip", use_container_width=True)
                if submitted:
                    errors = []
                    validate_required(passenger,  "Passenger Name",   errors)
                    validate_required(pickup_loc, "Pickup Location",  errors)
                    validate_required(dropoff,    "Drop-off Location",errors)
                    validate_required(veh_type,   "Vehicle Type",     errors)
                    if base == 0:
                        errors.append("⚠️ **Base Rate** must be greater than $0.00")
                    if show_errors(errors):
                        pass
                    else:
                        now      = time.time()
                        trip_sig = f"{cid}|{conf_num}|{passenger}|{pickup_dt}|{base}|{grat}|{fuel}|{misc}"
                        already  = (st.session_state.get("last_trip_sig") == trip_sig and
                                    now - st.session_state.get("last_trip_save", 0) < 5)
                        if already:
                            st.warning("⚠️ This trip was already saved. Change the details to add another.")
                        else:
                            st.session_state["last_trip_save"] = now
                            st.session_state["last_trip_sig"]  = trip_sig
                            sb.table("trips").insert({
                                "client_id": cid,
                                "confirmation_number": conf_num,
                                "passenger_name": passenger,
                                "service_type": svc_type,
                                "vehicle_type": veh_type,
                                "pickup_date": str(pickup_dt),
                                "pickup_time": str(pickup_tm),
                                "pickup_location": pickup_loc,
                                "dropoff_location": dropoff,
                                "stops": stops,
                                "driver_name": driver,
                                "base_rate": base, "gratuity": grat,
                                "fuel_charge": fuel, "misc_charge": misc,
                                "trip_total": total
                            }).execute()
                            st.success(f"✅ Trip saved! Total: **${total:.2f}**")
                            st.rerun()

    with tab2:
        clients = sb.table("clients").select("id,account_number,client_name").order("client_name").execute().data
        if clients:
            opts = {"— All Clients —": None} | {f"{c['account_number']} — {c['client_name']}": c['id'] for c in clients}
            sel  = st.selectbox("Filter by Client", list(opts.keys()))
            cid  = opts[sel]

            if cid:
                trips = sb.table("trips").select("*, clients(account_number,client_name)").eq("client_id", cid).order("pickup_date", desc=True).execute().data
            else:
                trips = sb.table("trips").select("*, clients(account_number,client_name)").order("pickup_date", desc=True).limit(50).execute().data

            if not trips:
                st.info("No trips found.")
            else:
                for t in trips:
                    cl = t.get("clients") or {}
                    with st.expander(f"📅 {t['pickup_date']} — {t['passenger_name']} | {t['service_type']} | ${t['trip_total']:.2f}"):
                        c1,c2,c3 = st.columns(3)
                        c1.write(f"**Account:** {cl.get('account_number','')}")
                        c2.write(f"**Client:** {cl.get('client_name','')}")
                        c3.write(f"**Conf #:** {t.get('confirmation_number','')}")
                        c1.write(f"**Pickup:** {t.get('pickup_location','')}")
                        c2.write(f"**Drop-off:** {t.get('dropoff_location','')}")
                        c3.write(f"**Total:** ${t['trip_total']:.2f}")
                        if st.button("🗑️ Delete Trip", key=f"dt_{t['id']}"):
                            sb.table("trips").delete().eq("id", t['id']).execute()
                            st.rerun()

# ══════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════
elif page_name == "Invoices":
    st.title("📄 Invoice Management")
    tab1, tab2 = st.tabs(["🧾 Generate Invoice", "📚 Invoice History"])

    # Load logo & company info from Supabase settings
    logo_bytes = None
    logo_b64   = get_setting("logo_b64")
    if logo_b64:
        try:
            logo_bytes = base64.b64decode(logo_b64)
        except:
            pass

    company_info = {
        "name":    get_setting("co_name",    "EXECUTIVE LIMO"),
        "tagline": get_setting("co_tagline", "Premium Chauffeur Services"),
        "address": get_setting("co_address", "123 Luxury Drive, Beverly Hills, CA 90210"),
        "phone":   get_setting("co_phone",   "(310) 555-0100"),
        "email":   get_setting("co_email",   "billing@executivelimo.com"),
    }

    with tab1:
        clients = sb.table("clients").select("*").order("client_name").execute().data
        if not clients:
            st.warning("No clients yet.")
        else:
            opts      = {f"{c['account_number']} — {c['client_name']}": c for c in clients}
            selected  = st.selectbox("Select Client", list(opts.keys()))
            client    = opts[selected]

            trips = sb.table("trips").select("*").eq("client_id", client['id']).order("pickup_date").execute().data
            if not trips:
                st.warning("This client has no trips. Add trips first.")
            else:
                st.subheader("Select Trips to Include")
                labels  = [f"{t['pickup_date']} — {t['passenger_name']} — ${t['trip_total']:.2f}" for t in trips]
                chosen  = st.multiselect("Trips", labels, default=labels)
                sel_idx = [labels.index(l) for l in chosen]
                sel_trips = [trips[i] for i in sel_idx]

                if sel_trips:
                    grand_total = sum(t['trip_total'] for t in sel_trips)
                    st.metric("Grand Total", f"${grand_total:.2f}")
                    inv_date = st.date_input("Invoice Date", value=date.today())

                    if st.button("🖨️ Generate & Save Invoice", use_container_width=True, type="primary"):
                        inv_num   = next_invoice_number()
                        pdf_bytes = generate_invoice_pdf(
                            client, sel_trips, inv_num, str(inv_date),
                            grand_total, logo_bytes=logo_bytes, company_info=company_info
                        )
                        pdf_b64 = base64.b64encode(pdf_bytes).decode()
                        sb.table("invoices").insert({
                            "invoice_number": inv_num,
                            "client_id":      client['id'],
                            "invoice_date":   str(inv_date),
                            "grand_total":    grand_total,
                            "pdf_data":       pdf_b64
                        }).execute()
                        st.success(f"Invoice **{inv_num}** generated!")
                        st.download_button("⬇️ Download PDF", data=pdf_bytes,
                                           file_name=f"{inv_num}.pdf", mime="application/pdf")

    with tab2:
        search = st.text_input("Search by invoice #, client name, or account")
        inv_data = sb.table("invoices").select("*, clients(account_number,client_name)").order("id", desc=True).execute().data

        if search:
            s = search.lower()
            inv_data = [r for r in inv_data if
                        s in (r.get("invoice_number") or "").lower() or
                        s in (r.get("clients", {}) or {}).get("client_name","").lower() or
                        s in (r.get("clients", {}) or {}).get("account_number","").lower()]

        if not inv_data:
            st.info("No invoices yet.")
        else:
            for row in inv_data:
                cl = row.get("clients") or {}
                with st.expander(f"**{row['invoice_number']}** — {cl.get('client_name','')} — {row['invoice_date']} — ${row['grand_total']:.2f}"):
                    st.write(f"**Account:** {cl.get('account_number','')}")
                    ca, cb = st.columns(2)
                    if row.get("pdf_data"):
                        try:
                            pdf_bytes = base64.b64decode(row["pdf_data"])
                            ca.download_button("⬇️ Download PDF", data=pdf_bytes,
                                               file_name=f"{row['invoice_number']}.pdf",
                                               mime="application/pdf", key=f"dl_{row['id']}")
                        except:
                            ca.warning("PDF unavailable")
                    if cb.button("🗑️ Delete", key=f"di_{row['id']}"):
                        sb.table("invoices").delete().eq("id", row['id']).execute()
                        st.rerun()

# ══════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════
elif page_name == "Settings":
    st.title("⚙️ Company Settings")
    st.info("These details appear on every invoice you generate.")

    # Logo
    st.subheader("🖼️ Company Logo")
    current_logo = get_setting("logo_b64")
    if current_logo:
        try:
            st.image(base64.b64decode(current_logo), width=200)
            st.caption("Current logo")
        except:
            pass

    uploaded = st.file_uploader("Upload your logo (PNG or JPG)", type=["png","jpg","jpeg"])
    if uploaded:
        set_setting("logo_b64", base64.b64encode(uploaded.read()).decode())
        st.success("✅ Logo saved!"); st.rerun()

    if current_logo:
        if st.button("🗑️ Remove Logo"):
            set_setting("logo_b64", ""); st.rerun()

    st.markdown("---")
    st.subheader("🏢 Company Information")
    with st.form("company_settings"):
        co_name    = st.text_input("Company Name",  get_setting("co_name",    "EXECUTIVE LIMO"))
        co_tagline = st.text_input("Tagline",       get_setting("co_tagline", "Premium Chauffeur Services"))
        co_address = st.text_input("Address",       get_setting("co_address", "123 Luxury Drive, Beverly Hills, CA 90210"))
        c1,c2      = st.columns(2)
        co_phone   = c1.text_input("Phone",         get_setting("co_phone",   "(310) 555-0100"))
        co_email   = c2.text_input("Email",         get_setting("co_email",   "billing@executivelimo.com"))
        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            set_setting("co_name",    co_name)
            set_setting("co_tagline", co_tagline)
            set_setting("co_address", co_address)
            set_setting("co_phone",   co_phone)
            set_setting("co_email",   co_email)
            st.success("✅ Settings saved! All future invoices will use this info.")
