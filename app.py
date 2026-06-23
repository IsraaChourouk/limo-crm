import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image as RLImage
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io

# ── DB ────────────────────────────────────────────────────
DB_PATH = "limo_crm.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_number TEXT UNIQUE,
        client_name TEXT,
        company_name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        notes TEXT
    );
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        confirmation_number TEXT,
        passenger_name TEXT,
        service_type TEXT,
        vehicle_type TEXT,
        pickup_date TEXT,
        pickup_time TEXT,
        pickup_location TEXT,
        dropoff_location TEXT,
        stops TEXT,
        driver_name TEXT,
        base_rate REAL DEFAULT 0,
        gratuity REAL DEFAULT 0,
        fuel_charge REAL DEFAULT 0,
        misc_charge REAL DEFAULT 0,
        trip_total REAL DEFAULT 0,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    );
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT,
        client_id INTEGER,
        invoice_date TEXT,
        grand_total REAL,
        pdf_data BLOB,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES(?,?)", (key, value))
    conn.commit()
    conn.close()

def next_account_number():
    conn = get_conn()
    row = conn.execute("SELECT account_number FROM clients ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return "ACC-1001"
    try:
        return f"ACC-{int(row[0].split('-')[1])+1}"
    except:
        return "ACC-1001"

def next_invoice_number():
    conn = get_conn()
    row = conn.execute("SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return "INV-0001"
    try:
        return f"INV-{int(row[0].split('-')[1])+1:04d}"
    except:
        return "INV-0001"

# ── PDF ───────────────────────────────────────────────────
def generate_invoice_pdf(client, trips_data, invoice_number, invoice_date, grand_total, logo_bytes=None, company_info=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch
    )

    GOLD  = colors.HexColor("#B8860B")
    DARK  = colors.HexColor("#1a1a2e")
    LGRAY = colors.HexColor("#f7f7f7")
    WHITE = colors.white

    def style(name, **kw):
        return ParagraphStyle(name, **kw)

    co = company_info or {}
    co_name    = co.get("name",    "EXECUTIVE LIMO")
    co_tagline = co.get("tagline", "Premium Chauffeur Services")
    co_address = co.get("address", "123 Luxury Drive, Beverly Hills, CA 90210")
    co_phone   = co.get("phone",   "(310) 555-0100")
    co_email   = co.get("email",   "billing@executivelimo.com")

    story = []

    # ── HEADER ──
    # Logo cell
    if logo_bytes:
        logo_buf = io.BytesIO(logo_bytes)
        logo_img = RLImage(logo_buf, width=1.4*inch, height=1.0*inch)
        logo_img.hAlign = 'LEFT'
        logo_cell = logo_img
    else:
        logo_cell = Paragraph(
            f"<b>{co_name}</b>",
            style('logotext', fontSize=20, textColor=DARK, fontName='Helvetica-Bold')
        )

    # Company info cell
    company_cell = [
        Paragraph(f"<b>{co_name}</b>",
                  style('cn', fontSize=15, textColor=DARK, fontName='Helvetica-Bold', spaceAfter=2)),
        Paragraph(co_tagline,
                  style('ct', fontSize=8, textColor=colors.HexColor("#666"), fontName='Helvetica', spaceAfter=2)),
        Paragraph(co_address,
                  style('ca', fontSize=8, textColor=colors.HexColor("#444"), fontName='Helvetica', spaceAfter=1)),
        Paragraph(f"Tel: {co_phone}   Email: {co_email}",
                  style('cp', fontSize=8, textColor=colors.HexColor("#444"), fontName='Helvetica')),
    ]

    # Invoice meta cell (right)
    inv_cell = [
        Paragraph("INVOICE",
                  style('inv', fontSize=22, textColor=GOLD, fontName='Helvetica-Bold', alignment=TA_RIGHT, spaceAfter=4)),
        Paragraph(f"<b>Invoice #:</b> {invoice_number}",
                  style('im', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"<b>Date:</b> {invoice_date}",
                  style('id2', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT, spaceAfter=2)),
        Paragraph(f"<b>Account:</b> {client['account_number']}",
                  style('ia', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT)),
    ]

    header_tbl = Table(
        [[logo_cell, company_cell, inv_cell]],
        colWidths=[1.5*inch, 3.3*inch, 2.6*inch]
    )
    header_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('ALIGN',        (2,0), (2,0),   'RIGHT'),
        ('LEFTPADDING',  (1,0), (1,0),   10),
        ('RIGHTPADDING', (2,0), (2,0),   0),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=10))

    # ── BILL TO ──
    lbl = style('lbl', fontSize=7, textColor=colors.HexColor("#999"), fontName='Helvetica-Bold', spaceAfter=3)
    val = style('val', fontSize=9, textColor=DARK, fontName='Helvetica', spaceAfter=1)
    bold_val = style('bval', fontSize=11, textColor=DARK, fontName='Helvetica-Bold', spaceAfter=2)

    bill_items = [Paragraph("BILL TO", lbl)]
    bill_items.append(Paragraph(client.get('client_name',''), bold_val))
    if client.get('company_name'):
        bill_items.append(Paragraph(client['company_name'], val))
    if client.get('phone'):
        bill_items.append(Paragraph(client['phone'], val))
    if client.get('email'):
        bill_items.append(Paragraph(client['email'], val))
    if client.get('address'):
        bill_items.append(Paragraph(client['address'], val))

    bill_tbl = Table([[bill_items, ""]], colWidths=[3.8*inch, 3.6*inch])
    bill_tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (0,0), LGRAY),
        ('TOPPADDING',   (0,0), (0,0), 8),
        ('BOTTOMPADDING',(0,0), (0,0), 10),
        ('LEFTPADDING',  (0,0), (0,0), 10),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
        ('ROUNDEDCORNERS', (0,0), (0,0), [4,4,4,4]),
    ]))
    story.append(bill_tbl)
    story.append(Spacer(1, 12))

    # ── TRIP TABLE ──
    # Columns: Date | Conf# | CLIENT INFO (Passenger/Service/Vehicle) | Base Rate | Gratuity | Fuel | Misc | Total
    # We'll split into readable columns as per your spec
    headers = ['Date', 'Conf #', 'Passenger', 'Service Type', 'Vehicle',
               'Base Rate', 'Gratuity', 'Fuel Charge', 'Misc', 'Total']
    col_w   = [0.7*inch, 0.7*inch, 1.0*inch, 1.05*inch, 0.7*inch,
               0.65*inch, 0.65*inch, 0.7*inch, 0.5*inch, 0.65*inch]

    hdr_style = style('th', fontSize=7.5, textColor=WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)
    cell_style = style('td', fontSize=8, textColor=DARK, fontName='Helvetica', alignment=TA_CENTER)
    num_style  = style('num', fontSize=8, textColor=DARK, fontName='Helvetica', alignment=TA_RIGHT)

    rows = [[Paragraph(h, hdr_style) for h in headers]]
    for t in trips_data:
        rows.append([
            Paragraph(str(t.get('pickup_date','')), cell_style),
            Paragraph(str(t.get('confirmation_number','')), cell_style),
            Paragraph(str(t.get('passenger_name','')), cell_style),
            Paragraph(str(t.get('service_type','')), cell_style),
            Paragraph(str(t.get('vehicle_type','')), cell_style),
            Paragraph(f"${t.get('base_rate',0):.2f}", num_style),
            Paragraph(f"${t.get('gratuity',0):.2f}", num_style),
            Paragraph(f"${t.get('fuel_charge',0):.2f}", num_style),
            Paragraph(f"${t.get('misc_charge',0):.2f}", num_style),
            Paragraph(f"${t.get('trip_total',0):.2f}", num_style),
        ])

    # Grand total row
    gt_style = style('gt', fontSize=9, textColor=WHITE, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    rows.append([
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph("GRAND TOTAL", gt_style),
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph("", gt_style),
        Paragraph(f"${grand_total:.2f}", gt_style),
    ])

    trip_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    n = len(rows)
    trip_tbl.setStyle(TableStyle([
        # Header
        ('BACKGROUND',   (0,0),  (-1,0),  DARK),
        ('TOPPADDING',   (0,0),  (-1,0),  6),
        ('BOTTOMPADDING',(0,0),  (-1,0),  6),
        # Data rows alternating
        ('ROWBACKGROUNDS',(0,1), (-1,n-2), [WHITE, LGRAY]),
        ('TOPPADDING',   (0,1),  (-1,-2), 5),
        ('BOTTOMPADDING',(0,1),  (-1,-2), 5),
        ('LEFTPADDING',  (0,0),  (-1,-1), 4),
        ('RIGHTPADDING', (0,0),  (-1,-1), 4),
        # Grid on data rows
        ('LINEBELOW',    (0,0),  (-1,-2), 0.3, colors.HexColor("#dddddd")),
        # Grand total row
        ('BACKGROUND',   (0,-1), (-1,-1), DARK),
        ('TOPPADDING',   (0,-1), (-1,-1), 7),
        ('BOTTOMPADDING',(0,-1), (-1,-1), 7),
        ('LINEABOVE',    (0,-1), (-1,-1), 2, GOLD),
        # Span grand total label across cols 4-8
        ('SPAN',         (4,-1), (8,-1)),
        ('ALIGN',        (4,-1), (8,-1), 'RIGHT'),
    ]))
    story.append(trip_tbl)
    story.append(Spacer(1, 20))

    # ── FOOTER ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=6))
    story.append(Paragraph(
        "Thank you for choosing us. Payment is due within 30 days. "
        "Please reference your invoice number on all payments.",
        style('foot', fontSize=8, textColor=colors.HexColor("#888"), fontName='Helvetica', alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# ── APP ───────────────────────────────────────────────────
init_db()
st.set_page_config(page_title="Limo CRM", page_icon="🚗", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #1a1a2e; }
[data-testid="stSidebar"] * { color: #f0f0f0 !important; }
.metric-card {
    background: linear-gradient(135deg,#1a1a2e,#16213e);
    border-radius:12px; padding:20px; color:white;
    border-left:4px solid #B8860B; margin-bottom:8px;
}
.metric-value { font-size:2rem; font-weight:bold; color:#B8860B; }
.metric-label { font-size:0.85rem; color:#aaa; margin-top:4px; }
.stButton>button { background:#1a1a2e; color:white; border-radius:8px; border:1px solid #B8860B; }
.stButton>button:hover { background:#B8860B; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🚗 Limo CRM")
    st.markdown("---")
    page = st.radio("Navigation", [
        "📊 Dashboard", "👥 Clients", "🗺️ Trips", "📄 Invoices", "⚙️ Settings"
    ])

page_name = page.split(" ", 1)[1]

# ══════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════
if page_name == "Dashboard":
    st.title("📊 Dashboard")
    conn = get_conn()
    n_clients  = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    n_trips    = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    n_invoices = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    revenue    = conn.execute("SELECT COALESCE(SUM(grand_total),0) FROM invoices").fetchone()[0]
    conn.close()

    c1,c2,c3,c4 = st.columns(4)
    def metric(col, label, value):
        col.markdown(f'<div class="metric-card"><div class="metric-value">{value}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

    metric(c1,"Total Clients", n_clients)
    metric(c2,"Total Trips", n_trips)
    metric(c3,"Total Invoices", n_invoices)
    metric(c4,"Total Revenue", f"${revenue:,.2f}")

    st.markdown("---")
    conn = get_conn()
    recent = pd.read_sql("""
        SELECT i.invoice_number, c.client_name, i.invoice_date, i.grand_total
        FROM invoices i JOIN clients c ON i.client_id=c.id
        ORDER BY i.id DESC LIMIT 5
    """, conn)
    conn.close()
    if not recent.empty:
        st.subheader("Recent Invoices")
        st.dataframe(recent, use_container_width=True, hide_index=True)

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
            c1,c2 = st.columns(2)
            name    = c1.text_input("Client Name *")
            company = c2.text_input("Company Name")
            phone   = c1.text_input("Phone")
            email   = c2.text_input("Email")
            address = st.text_input("Billing Address")
            notes   = st.text_area("Notes", height=80)
            if st.form_submit_button("✅ Save Client", use_container_width=True):
                if not name:
                    st.error("Client name is required.")
                else:
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO clients (account_number,client_name,company_name,phone,email,address,notes) VALUES(?,?,?,?,?,?,?)",
                        (acc,name,company,phone,email,address,notes)
                    )
                    conn.commit(); conn.close()
                    st.success(f"Client **{name}** added with account **{acc}**!")
                    st.rerun()

    with tab2:
        search = st.text_input("Search by name, company, or account number")
        conn = get_conn()
        if search:
            df = pd.read_sql(
                "SELECT * FROM clients WHERE client_name LIKE ? OR company_name LIKE ? OR account_number LIKE ?",
                conn, params=(f"%{search}%",)*3)
        else:
            df = pd.read_sql("SELECT * FROM clients ORDER BY id DESC LIMIT 20", conn)
        conn.close()

        for _, row in df.iterrows():
            with st.expander(f"**{row['account_number']}** — {row['client_name']} | {row.get('company_name','')}"):
                with st.form(f"edit_{row['id']}"):
                    c1,c2 = st.columns(2)
                    name    = c1.text_input("Client Name", row['client_name'])
                    company = c2.text_input("Company", row.get('company_name','') or '')
                    phone   = c1.text_input("Phone", row.get('phone','') or '')
                    email   = c2.text_input("Email", row.get('email','') or '')
                    address = st.text_input("Address", row.get('address','') or '')
                    notes   = st.text_area("Notes", row.get('notes','') or '', height=70)
                    ca, cb  = st.columns(2)
                    if ca.form_submit_button("💾 Update"):
                        conn = get_conn()
                        conn.execute(
                            "UPDATE clients SET client_name=?,company_name=?,phone=?,email=?,address=?,notes=? WHERE id=?",
                            (name,company,phone,email,address,notes,row['id'])
                        )
                        conn.commit(); conn.close()
                        st.success("Updated!"); st.rerun()
                    if cb.form_submit_button("🗑️ Delete"):
                        conn = get_conn()
                        conn.execute("DELETE FROM clients WHERE id=?", (row['id'],))
                        conn.commit(); conn.close()
                        st.warning("Deleted."); st.rerun()

    with tab3:
        conn = get_conn()
        all_c = pd.read_sql("SELECT account_number,client_name,company_name,phone,email FROM clients ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(all_c, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════
# TRIPS
# ══════════════════════════════════════════
elif page_name == "Trips":
    st.title("🗺️ Trip Management")
    tab1, tab2 = st.tabs(["➕ Add Trip", "📋 View Trips"])

    with tab1:
        conn = get_conn()
        clients = pd.read_sql("SELECT id,account_number,client_name FROM clients ORDER BY client_name", conn)
        conn.close()
        if clients.empty:
            st.warning("No clients yet. Please add a client first.")
        else:
            opts = {f"{r['account_number']} — {r['client_name']}": r['id'] for _,r in clients.iterrows()}
            sel  = st.selectbox("Select Client *", list(opts.keys()))
            cid  = opts[sel]

            with st.form("add_trip"):
                st.subheader("Trip Details")
                c1,c2 = st.columns(2)
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
                    # Guard against double-click: check if identical trip already saved in last 5 seconds
                    import time
                    now = time.time()
                    last_key = "last_trip_save"
                    last_sig_key = "last_trip_sig"
                    trip_sig = f"{cid}|{conf_num}|{passenger}|{pickup_dt}|{pickup_tm}|{base}|{grat}|{fuel}|{misc}"

                    already_saved = (
                        st.session_state.get(last_sig_key) == trip_sig and
                        now - st.session_state.get(last_key, 0) < 5
                    )

                    if already_saved:
                        st.warning("⚠️ This trip was already saved. If you want to add another trip, please change the details.")
                    else:
                        st.session_state[last_key] = now
                        st.session_state[last_sig_key] = trip_sig
                        conn = get_conn()
                        conn.execute("""
                            INSERT INTO trips
                            (client_id,confirmation_number,passenger_name,service_type,vehicle_type,
                             pickup_date,pickup_time,pickup_location,dropoff_location,stops,driver_name,
                             base_rate,gratuity,fuel_charge,misc_charge,trip_total)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (cid,conf_num,passenger,svc_type,veh_type,
                              str(pickup_dt),str(pickup_tm),pickup_loc,dropoff,stops,driver,
                              base,grat,fuel,misc,total))
                        conn.commit(); conn.close()
                        st.success(f"✅ Trip saved! Total: **${total:.2f}**")
                        st.rerun()

    with tab2:
        conn = get_conn()
        clients = pd.read_sql("SELECT id,account_number,client_name FROM clients ORDER BY client_name", conn)
        conn.close()
        if not clients.empty:
            opts = {"— All Clients —": None} | {f"{r['account_number']} — {r['client_name']}": r['id'] for _,r in clients.iterrows()}
            sel  = st.selectbox("Filter by Client", list(opts.keys()))
            cid  = opts[sel]
            conn = get_conn()
            q = """SELECT t.id,c.account_number,c.client_name,t.confirmation_number,
                          t.passenger_name,t.service_type,t.pickup_date,
                          t.pickup_location,t.dropoff_location,t.trip_total
                   FROM trips t JOIN clients c ON t.client_id=c.id """
            trips_df = pd.read_sql(q + ("WHERE t.client_id=? ORDER BY t.pickup_date DESC" if cid else "ORDER BY t.pickup_date DESC LIMIT 50"),
                                   conn, params=(cid,) if cid else ())
            conn.close()
            if trips_df.empty:
                st.info("No trips found.")
            else:
                for _, row in trips_df.iterrows():
                    with st.expander(f"📅 {row['pickup_date']} — {row['passenger_name']} | {row['service_type']} | ${row['trip_total']:.2f}"):
                        c1,c2,c3 = st.columns(3)
                        c1.write(f"**Account:** {row['account_number']}")
                        c2.write(f"**Client:** {row['client_name']}")
                        c3.write(f"**Conf #:** {row.get('confirmation_number','')}")
                        c1.write(f"**Pickup:** {row['pickup_location']}")
                        c2.write(f"**Drop-off:** {row['dropoff_location']}")
                        c3.write(f"**Total:** ${row['trip_total']:.2f}")
                        if st.button("🗑️ Delete Trip", key=f"dt_{row['id']}"):
                            conn = get_conn()
                            conn.execute("DELETE FROM trips WHERE id=?", (row['id'],))
                            conn.commit(); conn.close(); st.rerun()

# ══════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════
elif page_name == "Invoices":
    st.title("📄 Invoice Management")
    tab1, tab2 = st.tabs(["🧾 Generate Invoice", "📚 Invoice History"])

    # Load saved logo & company info
    logo_bytes = None
    logo_b64 = get_setting("logo_b64")
    if logo_b64:
        import base64
        try:
            logo_bytes = base64.b64decode(logo_b64)
        except:
            logo_bytes = None

    company_info = {
        "name":    get_setting("co_name",    "EXECUTIVE LIMO"),
        "tagline": get_setting("co_tagline", "Premium Chauffeur Services"),
        "address": get_setting("co_address", "123 Luxury Drive, Beverly Hills, CA 90210"),
        "phone":   get_setting("co_phone",   "(310) 555-0100"),
        "email":   get_setting("co_email",   "billing@executivelimo.com"),
    }

    with tab1:
        conn = get_conn()
        clients = pd.read_sql("SELECT * FROM clients ORDER BY client_name", conn)
        conn.close()
        if clients.empty:
            st.warning("No clients yet.")
        else:
            opts = {f"{r['account_number']} — {r['client_name']}": r['id'] for _,r in clients.iterrows()}
            selected = st.selectbox("Select Client", list(opts.keys()))
            client_id = opts[selected]

            conn = get_conn()
            row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            cols = [d[0] for d in conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).description]
            client_dict = dict(zip(cols, row))
            trips_df = pd.read_sql("SELECT * FROM trips WHERE client_id=? ORDER BY pickup_date", conn, params=(client_id,))
            conn.close()

            if trips_df.empty:
                st.warning("This client has no trips. Add trips first.")
            else:
                st.subheader("Select Trips to Include")
                labels = [f"{r['pickup_date']} — {r['passenger_name']} — ${r['trip_total']:.2f}" for _,r in trips_df.iterrows()]
                chosen = st.multiselect("Trips", labels, default=labels)
                idxs   = [labels.index(t) for t in chosen]
                sel_df = trips_df.iloc[idxs]

                if not sel_df.empty:
                    grand_total = sel_df['trip_total'].sum()
                    st.metric("Grand Total", f"${grand_total:.2f}")
                    inv_date = st.date_input("Invoice Date", value=date.today())

                    if st.button("🖨️ Generate & Save Invoice", use_container_width=True, type="primary"):
                        inv_num   = next_invoice_number()
                        pdf_bytes = generate_invoice_pdf(
                            client_dict, sel_df.to_dict('records'),
                            inv_num, str(inv_date), grand_total,
                            logo_bytes=logo_bytes, company_info=company_info
                        )
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO invoices (invoice_number,client_id,invoice_date,grand_total,pdf_data) VALUES(?,?,?,?,?)",
                            (inv_num, client_id, str(inv_date), grand_total, pdf_bytes)
                        )
                        conn.commit(); conn.close()
                        st.success(f"Invoice **{inv_num}** generated!")
                        st.download_button("⬇️ Download PDF", data=pdf_bytes,
                                           file_name=f"{inv_num}.pdf", mime="application/pdf")

    with tab2:
        search = st.text_input("Search by invoice #, client, or account")
        conn = get_conn()
        base_q = """SELECT i.id,i.invoice_number,c.account_number,c.client_name,i.invoice_date,i.grand_total
                    FROM invoices i JOIN clients c ON i.client_id=c.id """
        inv_df = pd.read_sql(
            base_q + ("WHERE i.invoice_number LIKE ? OR c.client_name LIKE ? OR c.account_number LIKE ? ORDER BY i.id DESC" if search
                      else "ORDER BY i.id DESC"),
            conn, params=(f"%{search}%",)*3 if search else ()
        )
        conn.close()
        if inv_df.empty:
            st.info("No invoices yet.")
        else:
            for _, row in inv_df.iterrows():
                with st.expander(f"**{row['invoice_number']}** — {row['client_name']} — {row['invoice_date']} — ${row['grand_total']:.2f}"):
                    st.write(f"**Account:** {row['account_number']}")
                    ca, cb = st.columns(2)
                    conn = get_conn()
                    pdf_row = conn.execute("SELECT pdf_data FROM invoices WHERE id=?", (row['id'],)).fetchone()
                    conn.close()
                    if pdf_row and pdf_row[0]:
                        ca.download_button("⬇️ Download PDF", data=bytes(pdf_row[0]),
                                           file_name=f"{row['invoice_number']}.pdf",
                                           mime="application/pdf", key=f"dl_{row['id']}")
                    if cb.button("🗑️ Delete", key=f"di_{row['id']}"):
                        conn = get_conn()
                        conn.execute("DELETE FROM invoices WHERE id=?", (row['id'],))
                        conn.commit(); conn.close(); st.rerun()

# ══════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════
elif page_name == "Settings":
    st.title("⚙️ Company Settings")
    st.info("These details appear on every invoice you generate.")

    import base64

    # Logo upload
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
        logo_b64 = base64.b64encode(uploaded.read()).decode()
        set_setting("logo_b64", logo_b64)
        st.success("✅ Logo saved!")
        st.rerun()

    if current_logo:
        if st.button("🗑️ Remove Logo"):
            set_setting("logo_b64", "")
            st.rerun()

    st.markdown("---")
    st.subheader("🏢 Company Information")

    with st.form("company_settings"):
        co_name    = st.text_input("Company Name",   get_setting("co_name",    "EXECUTIVE LIMO"))
        co_tagline = st.text_input("Tagline",        get_setting("co_tagline", "Premium Chauffeur Services"))
        co_address = st.text_input("Address",        get_setting("co_address", "123 Luxury Drive, Beverly Hills, CA 90210"))
        c1, c2 = st.columns(2)
        co_phone   = c1.text_input("Phone",          get_setting("co_phone",   "(310) 555-0100"))
        co_email   = c2.text_input("Email",          get_setting("co_email",   "billing@executivelimo.com"))

        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            set_setting("co_name",    co_name)
            set_setting("co_tagline", co_tagline)
            set_setting("co_address", co_address)
            set_setting("co_phone",   co_phone)
            set_setting("co_email",   co_email)
            st.success("✅ Settings saved! All future invoices will use this info.")
