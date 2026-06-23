import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io

# ── DB setup ──────────────────────────────────────────────
DB_PATH = "limo_crm.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
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
    """)
    conn.commit()
    conn.close()

def next_account_number():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT account_number FROM clients ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return "ACC-1001"
    try:
        num = int(row[0].split("-")[1]) + 1
    except Exception:
        num = 1001
    return f"ACC-{num}"

def next_invoice_number():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return "INV-0001"
    try:
        num = int(row[0].split("-")[1]) + 1
    except Exception:
        num = 1
    return f"INV-{num:04d}"

# ── PDF Generation ────────────────────────────────────────
def generate_invoice_pdf(client, trips_data, invoice_number, invoice_date, grand_total):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.5*inch, rightMargin=0.5*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()

    gold = colors.HexColor("#B8860B")
    dark = colors.HexColor("#1a1a2e")
    light_gray = colors.HexColor("#f5f5f5")

    title_style = ParagraphStyle('title', fontSize=22, textColor=dark,
                                  spaceAfter=2, fontName='Helvetica-Bold', alignment=TA_LEFT)
    sub_style   = ParagraphStyle('sub', fontSize=9, textColor=colors.HexColor("#555555"),
                                  spaceAfter=2, fontName='Helvetica')
    label_style = ParagraphStyle('label', fontSize=8, textColor=colors.HexColor("#888888"),
                                  fontName='Helvetica-Bold')
    value_style = ParagraphStyle('value', fontSize=9, textColor=dark, fontName='Helvetica')
    inv_style   = ParagraphStyle('inv', fontSize=9, textColor=dark, fontName='Helvetica', alignment=TA_RIGHT)

    # Header row: company left, invoice info right
    company_block = [
        Paragraph("✦ EXECUTIVE LIMO", title_style),
        Paragraph("Premium Chauffeur Services", sub_style),
        Paragraph("123 Luxury Drive, Beverly Hills, CA 90210", sub_style),
        Paragraph("📞 (310) 555-0100  ✉ billing@executivelimo.com", sub_style),
    ]
    invoice_block = [
        Paragraph(f"<b>INVOICE</b>", ParagraphStyle('h', fontSize=18, textColor=gold,
                   fontName='Helvetica-Bold', alignment=TA_RIGHT)),
        Paragraph(f"Invoice #: {invoice_number}", inv_style),
        Paragraph(f"Date: {invoice_date}", inv_style),
        Paragraph(f"Account: {client['account_number']}", inv_style),
    ]

    header_data = [[company_block, invoice_block]]
    header_table = Table(header_data, colWidths=[3.8*inch, 3.2*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=gold, spaceAfter=12))

    # Bill To
    bill_data = [[
        [Paragraph("BILL TO", label_style),
         Paragraph(f"<b>{client['client_name']}</b>", ParagraphStyle('cn', fontSize=11, fontName='Helvetica-Bold', textColor=dark)),
         Paragraph(client.get('company_name','') or '', value_style),
         Paragraph(client.get('phone','') or '', value_style),
         Paragraph(client.get('email','') or '', value_style),
         Paragraph(client.get('address','') or '', value_style)],
        ""
    ]]
    bill_table = Table(bill_data, colWidths=[4.5*inch, 2.5*inch])
    bill_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), light_gray),
        ('ROWPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 14))

    # Trip table header
    col_headers = ['Date', 'Conf #', 'Passenger', 'Service', 'Vehicle',
                   'Base Rate', 'Gratuity', 'Fuel', 'Misc', 'Total']
    col_widths = [0.65*inch, 0.75*inch, 1.0*inch, 0.85*inch, 0.75*inch,
                  0.65*inch, 0.65*inch, 0.55*inch, 0.55*inch, 0.65*inch]

    table_data = [col_headers]
    for t in trips_data:
        table_data.append([
            t.get('pickup_date',''),
            t.get('confirmation_number',''),
            t.get('passenger_name',''),
            t.get('service_type',''),
            t.get('vehicle_type',''),
            f"${t.get('base_rate',0):.2f}",
            f"${t.get('gratuity',0):.2f}",
            f"${t.get('fuel_charge',0):.2f}",
            f"${t.get('misc_charge',0):.2f}",
            f"${t.get('trip_total',0):.2f}",
        ])

    # Grand total row
    table_data.append(['', '', '', '', 'GRAND TOTAL', '', '', '', '',
                        f"${grand_total:.2f}"])

    trip_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    trip_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), dark),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (5,1), (-1,-1), 'RIGHT'),
        ('FONTSIZE', (0,1), (-1,-2), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, light_gray]),
        ('GRID', (0,0), (-1,-2), 0.3, colors.HexColor("#dddddd")),
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, gold),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#1a1a2e")),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.white),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,-1), (-1,-1), 9),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(trip_table)
    story.append(Spacer(1, 20))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 8))
    footer = Paragraph(
        "Thank you for choosing Executive Limo. Payment is due within 30 days. "
        "Please reference your invoice number on all payments.",
        ParagraphStyle('foot', fontSize=8, textColor=colors.HexColor("#666666"),
                        fontName='Helvetica', alignment=TA_CENTER)
    )
    story.append(footer)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# ── Streamlit UI ──────────────────────────────────────────
init_db()
st.set_page_config(page_title="Executive Limo CRM", page_icon="🚗", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #1a1a2e; }
[data-testid="stSidebar"] * { color: #f0f0f0 !important; }
[data-testid="stSidebar"] .stRadio label { color: #f0f0f0 !important; }
.metric-card {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-radius: 12px; padding: 20px; color: white;
    border-left: 4px solid #B8860B;
}
.metric-value { font-size: 2rem; font-weight: bold; color: #B8860B; }
.metric-label { font-size: 0.85rem; color: #aaaaaa; margin-top: 4px; }
h1, h2, h3 { color: #1a1a2e; }
.stButton > button {
    background: #1a1a2e; color: white; border-radius: 8px;
    border: 1px solid #B8860B;
}
.stButton > button:hover { background: #B8860B; color: white; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🚗 Executive Limo")
    st.markdown("---")
    page = st.radio("Navigation", [
        "📊 Dashboard",
        "👥 Clients",
        "🗺️ Trips",
        "📄 Invoices",
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

    c1, c2, c3, c4 = st.columns(4)
    def metric(col, label, value):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    metric(c1, "Total Clients",   n_clients)
    metric(c2, "Total Trips",     n_trips)
    metric(c3, "Total Invoices",  n_invoices)
    metric(c4, "Total Revenue",   f"${revenue:,.2f}")

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
            c1, c2 = st.columns(2)
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
                        (acc, name, company, phone, email, address, notes)
                    )
                    conn.commit(); conn.close()
                    st.success(f"Client **{name}** added with account **{acc}**!")
                    st.rerun()

    with tab2:
        st.subheader("Search & Edit Clients")
        search = st.text_input("Search by name, company, or account number")
        conn = get_conn()
        if search:
            df = pd.read_sql(
                "SELECT * FROM clients WHERE client_name LIKE ? OR company_name LIKE ? OR account_number LIKE ?",
                conn, params=(f"%{search}%",)*3
            )
        else:
            df = pd.read_sql("SELECT * FROM clients ORDER BY id DESC LIMIT 20", conn)
        conn.close()

        for _, row in df.iterrows():
            with st.expander(f"**{row['account_number']}** — {row['client_name']} | {row.get('company_name','')}"):
                with st.form(f"edit_{row['id']}"):
                    c1, c2 = st.columns(2)
                    name    = c1.text_input("Client Name", row['client_name'])
                    company = c2.text_input("Company", row.get('company_name','') or '')
                    phone   = c1.text_input("Phone", row.get('phone','') or '')
                    email   = c2.text_input("Email", row.get('email','') or '')
                    address = st.text_input("Address", row.get('address','') or '')
                    notes   = st.text_area("Notes", row.get('notes','') or '', height=70)
                    col_a, col_b = st.columns(2)
                    if col_a.form_submit_button("💾 Update"):
                        conn = get_conn()
                        conn.execute(
                            "UPDATE clients SET client_name=?,company_name=?,phone=?,email=?,address=?,notes=? WHERE id=?",
                            (name, company, phone, email, address, notes, row['id'])
                        )
                        conn.commit(); conn.close()
                        st.success("Updated!"); st.rerun()
                    if col_b.form_submit_button("🗑️ Delete", type="secondary"):
                        conn = get_conn()
                        conn.execute("DELETE FROM clients WHERE id=?", (row['id'],))
                        conn.commit(); conn.close()
                        st.warning("Deleted."); st.rerun()

    with tab3:
        conn = get_conn()
        all_clients = pd.read_sql("SELECT account_number,client_name,company_name,phone,email FROM clients ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(all_clients, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════
# TRIPS
# ══════════════════════════════════════════
elif page_name == "Trips":
    st.title("🗺️ Trip Management")
    tab1, tab2 = st.tabs(["➕ Add Trip", "📋 View Trips"])

    with tab1:
        conn = get_conn()
        clients = pd.read_sql("SELECT id, account_number, client_name FROM clients ORDER BY client_name", conn)
        conn.close()

        if clients.empty:
            st.warning("No clients yet. Please add a client first.")
        else:
            client_options = {f"{r['account_number']} — {r['client_name']}": r['id'] for _, r in clients.iterrows()}
            selected = st.selectbox("Select Client *", list(client_options.keys()))
            client_id = client_options[selected]

            with st.form("add_trip"):
                st.subheader("Trip Details")
                c1, c2 = st.columns(2)
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
                c1, c2, c3, c4 = st.columns(4)
                base   = c1.number_input("Base Rate ($)", min_value=0.0, step=0.01)
                grat   = c2.number_input("Gratuity ($)",  min_value=0.0, step=0.01)
                fuel   = c3.number_input("Fuel Charge ($)", min_value=0.0, step=0.01)
                misc   = c4.number_input("Misc Charge ($)", min_value=0.0, step=0.01)
                total  = base + grat + fuel + misc
                st.metric("Trip Total", f"${total:.2f}")

                if st.form_submit_button("✅ Save Trip", use_container_width=True):
                    conn = get_conn()
                    conn.execute("""
                        INSERT INTO trips
                        (client_id,confirmation_number,passenger_name,service_type,vehicle_type,
                         pickup_date,pickup_time,pickup_location,dropoff_location,stops,driver_name,
                         base_rate,gratuity,fuel_charge,misc_charge,trip_total)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (client_id, conf_num, passenger, svc_type, veh_type,
                          str(pickup_dt), str(pickup_tm), pickup_loc, dropoff, stops, driver,
                          base, grat, fuel, misc, total))
                    conn.commit(); conn.close()
                    st.success(f"Trip saved! Total: **${total:.2f}**")
                    st.rerun()

    with tab2:
        conn = get_conn()
        clients = pd.read_sql("SELECT id, account_number, client_name FROM clients ORDER BY client_name", conn)
        conn.close()

        if not clients.empty:
            client_opts = {"— All Clients —": None} | {f"{r['account_number']} — {r['client_name']}": r['id'] for _, r in clients.iterrows()}
            sel = st.selectbox("Filter by Client", list(client_opts.keys()))
            cid = client_opts[sel]

            conn = get_conn()
            if cid:
                trips_df = pd.read_sql("""
                    SELECT t.id, c.account_number, c.client_name, t.confirmation_number,
                           t.passenger_name, t.service_type, t.pickup_date, t.pickup_location,
                           t.dropoff_location, t.trip_total
                    FROM trips t JOIN clients c ON t.client_id=c.id
                    WHERE t.client_id=? ORDER BY t.pickup_date DESC
                """, conn, params=(cid,))
            else:
                trips_df = pd.read_sql("""
                    SELECT t.id, c.account_number, c.client_name, t.confirmation_number,
                           t.passenger_name, t.service_type, t.pickup_date, t.pickup_location,
                           t.dropoff_location, t.trip_total
                    FROM trips t JOIN clients c ON t.client_id=c.id
                    ORDER BY t.pickup_date DESC LIMIT 50
                """, conn)
            conn.close()

            if trips_df.empty:
                st.info("No trips found.")
            else:
                for _, row in trips_df.iterrows():
                    with st.expander(f"📅 {row['pickup_date']} — {row['passenger_name']} | {row['service_type']} | ${row['trip_total']:.2f}"):
                        col1, col2, col3 = st.columns(3)
                        col1.write(f"**Account:** {row['account_number']}")
                        col2.write(f"**Client:** {row['client_name']}")
                        col3.write(f"**Conf #:** {row.get('confirmation_number','')}")
                        col1.write(f"**Pickup:** {row['pickup_location']}")
                        col2.write(f"**Drop-off:** {row['dropoff_location']}")
                        col3.write(f"**Total:** ${row['trip_total']:.2f}")
                        if st.button("🗑️ Delete Trip", key=f"del_trip_{row['id']}"):
                            conn = get_conn()
                            conn.execute("DELETE FROM trips WHERE id=?", (row['id'],))
                            conn.commit(); conn.close()
                            st.rerun()

# ══════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════
elif page_name == "Invoices":
    st.title("📄 Invoice Management")
    tab1, tab2 = st.tabs(["🧾 Generate Invoice", "📚 Invoice History"])

    with tab1:
        conn = get_conn()
        clients = pd.read_sql("SELECT * FROM clients ORDER BY client_name", conn)
        conn.close()

        if clients.empty:
            st.warning("No clients yet.")
        else:
            client_opts = {f"{r['account_number']} — {r['client_name']}": r['id'] for _, r in clients.iterrows()}
            selected = st.selectbox("Select Client", list(client_opts.keys()))
            client_id = client_opts[selected]

            conn = get_conn()
            client_row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            client_keys = [d[0] for d in conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).description]
            client_dict = dict(zip(client_keys, client_row))

            trips_df = pd.read_sql("""
                SELECT * FROM trips WHERE client_id=? ORDER BY pickup_date
            """, conn, params=(client_id,))
            conn.close()

            if trips_df.empty:
                st.warning("This client has no trips. Add trips first.")
            else:
                st.subheader("Select Trips to Include")
                trip_labels = [
                    f"{r['pickup_date']} — {r['passenger_name']} — ${r['trip_total']:.2f}"
                    for _, r in trips_df.iterrows()
                ]
                selected_trips = st.multiselect("Trips", trip_labels, default=trip_labels)
                selected_idx = [trip_labels.index(t) for t in selected_trips]
                selected_trips_df = trips_df.iloc[selected_idx]

                if not selected_trips_df.empty:
                    grand_total = selected_trips_df['trip_total'].sum()
                    st.metric("Grand Total", f"${grand_total:.2f}")

                    inv_date = st.date_input("Invoice Date", value=date.today())

                    if st.button("🖨️ Generate & Save Invoice", use_container_width=True, type="primary"):
                        inv_num = next_invoice_number()
                        trips_list = selected_trips_df.to_dict('records')
                        pdf_bytes = generate_invoice_pdf(
                            client_dict, trips_list, inv_num, str(inv_date), grand_total
                        )
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO invoices (invoice_number,client_id,invoice_date,grand_total,pdf_data) VALUES(?,?,?,?,?)",
                            (inv_num, client_id, str(inv_date), grand_total, pdf_bytes)
                        )
                        conn.commit(); conn.close()
                        st.success(f"Invoice **{inv_num}** generated!")
                        st.download_button(
                            "⬇️ Download PDF", data=pdf_bytes,
                            file_name=f"{inv_num}.pdf", mime="application/pdf"
                        )

    with tab2:
        st.subheader("Invoice History")
        search = st.text_input("Search by invoice #, client name, or account")
        conn = get_conn()
        if search:
            inv_df = pd.read_sql("""
                SELECT i.id, i.invoice_number, c.account_number, c.client_name,
                       i.invoice_date, i.grand_total
                FROM invoices i JOIN clients c ON i.client_id=c.id
                WHERE i.invoice_number LIKE ? OR c.client_name LIKE ? OR c.account_number LIKE ?
                ORDER BY i.id DESC
            """, conn, params=(f"%{search}%",)*3)
        else:
            inv_df = pd.read_sql("""
                SELECT i.id, i.invoice_number, c.account_number, c.client_name,
                       i.invoice_date, i.grand_total
                FROM invoices i JOIN clients c ON i.client_id=c.id
                ORDER BY i.id DESC
            """, conn)
        conn.close()

        if inv_df.empty:
            st.info("No invoices yet.")
        else:
            for _, row in inv_df.iterrows():
                with st.expander(f"**{row['invoice_number']}** — {row['client_name']} — {row['invoice_date']} — ${row['grand_total']:.2f}"):
                    st.write(f"**Account:** {row['account_number']}")
                    col_a, col_b = st.columns(2)
                    # Download
                    conn = get_conn()
                    pdf_row = conn.execute("SELECT pdf_data FROM invoices WHERE id=?", (row['id'],)).fetchone()
                    conn.close()
                    if pdf_row and pdf_row[0]:
                        col_a.download_button(
                            "⬇️ Download PDF", data=bytes(pdf_row[0]),
                            file_name=f"{row['invoice_number']}.pdf",
                            mime="application/pdf", key=f"dl_{row['id']}"
                        )
                    if col_b.button("🗑️ Delete Invoice", key=f"del_inv_{row['id']}"):
                        conn = get_conn()
                        conn.execute("DELETE FROM invoices WHERE id=?", (row['id'],))
                        conn.commit(); conn.close()
                        st.rerun()
