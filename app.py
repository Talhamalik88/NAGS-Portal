from flask import Flask, render_template, request, redirect, session, send_file, jsonify, flash, send_from_directory
from flask_mail import Mail, Message
import sqlite3, os, random, string, base64
from datetime import datetime
from io import BytesIO
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
from flask import url_for, redirect, send_from_directory
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import os
import sqlite3
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
import os
import sqlite3


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'talhamalik88@gmail.com'
app.config['MAIL_PASSWORD'] = ''
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)

# Upload folders
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploaded_docs')
UPLOAD_USER_DOCS = os.path.join(os.getcwd(), 'user_docs')
SIGNATURE_FOLDER = os.path.join(os.getcwd(), 'signatures')
for folder in [UPLOAD_FOLDER, UPLOAD_USER_DOCS, SIGNATURE_FOLDER]:
    os.makedirs(folder, exist_ok=True)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        if username.lower() == "talha" and password == "NAGS":
            session['user'] = {'name': 'Talha', 'role': 'Admin'}
            return redirect("/admin-dashboard")

        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(username)=? AND password=?", (username.lower(), password))
        user = cursor.fetchone()

        if user:
            session['user'] = {'name': user['name'], 'role': user['role']}
            session['doc_expiry_count'] = 0

            cursor.execute("SELECT * FROM user_documents WHERE user_id = ?", (user['id'],))
            docs = cursor.fetchall()
            today = datetime.now().date()
            expiring_soon = 0

            for doc in docs:
                if doc['expiry_date']:
                    try:
                        exp_date = datetime.strptime(doc['expiry_date'], "%Y-%m-%d").date()
                        days_left = (exp_date - today).days
                        if days_left in [30, 7]:
                            msg = Message(
                                subject=f"Document Expiry Alert – {doc['doc_name']}",
                                sender='talhamalik88@gmail.com',
                                recipients=[user['username']]
                            )
                            msg.body = f"Dear {user['name']},\n\nYour document \"{doc['doc_name']}\" is expiring in {days_left} day(s).\n\n- NAGS Maintenance"
                            mail.send(msg)
                        if days_left <= 30:
                            expiring_soon += 1
                    except:
                        pass

            session['doc_expiry_count'] = expiring_soon
            return redirect("/user-dashboard")

        return "Invalid username or password."

    return render_template("login.html", datetime=datetime)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")
# ----------------- ADMIN DASHBOARD -----------------
@app.route("/admin-dashboard", methods=["GET", "POST"])
def admin_dashboard():
    user = session.get("user")
    if not user or user.get("role") != "Admin":
        return redirect("/login")

    tab = request.args.get("tab", "add")

    # Handle form submission for Add Document
    if request.method == "POST" and tab == "add":
        file = request.files.get('document')
        subject = request.form.get('subject', '').strip()
        source = request.form.get('source', '').strip()
        send_to_engineers = 'send_to_engineers' in request.form
        send_to_technicians = 'send_to_technicians' in request.form

        if not file:
            flash("No file uploaded.")
            return redirect("/admin-dashboard?tab=add")

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        if not subject:
            subject = filename

        upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uploaded_by = "Admin"

        # Prepare assigned_roles value
        assigned_roles = []
        if 'send_to_engineers' in request.form:
            assigned_roles.append('Engineer')
        if 'send_to_technicians' in request.form:
            assigned_roles.append('Technician')
        assigned_roles_str = ','.join(assigned_roles)

        conn = sqlite3.connect("nags.db")
        cursor = conn.cursor()

        # Insert document with assigned_roles
        cursor.execute('''
            INSERT INTO documents (filename, subject, source, upload_time, uploaded_by, assigned_roles)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (filename, subject, source, upload_time, uploaded_by, assigned_roles_str))

        document_id = cursor.lastrowid

        cursor.execute("SELECT id, role FROM users")
        users = cursor.fetchall()

        for user in users:
            user_id, role = user
            if (send_to_engineers and role == "Engineer") or (send_to_technicians and role == "Technician"):
                cursor.execute('''
                    INSERT INTO document_recipients (document_id, user_id)
                    VALUES (?, ?)
                ''', (document_id, user_id))

        conn.commit()
        conn.close()
        flash("Document uploaded and distributed successfully.")
        return redirect("/admin-dashboard?tab=add")

    # Handle tab loading logic
    if tab == "add":
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, subject, source, upload_time, assigned_roles FROM documents ORDER BY upload_time DESC")

        existing_documents = cursor.fetchall()
        conn.close()
        print("DEBUG: Documents fetched =", len(existing_documents))
        tab_template = "tab_add_document.html"
        extra_context = {"existing_documents": existing_documents}

    elif tab == "report":
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT source FROM documents")
        sources = [row["source"] for row in cursor.fetchall()]
        cursor.execute("SELECT id, subject, source FROM documents")
        documents = cursor.fetchall()
        grouped_docs = {}
        for doc in documents:
            grouped_docs.setdefault(doc['source'], []).append({
                'id': doc['id'],
                'subject': doc['subject']
            })
        conn.close()
        tab_template = "tab_generate_report.html"
        extra_context = {
            "sources": sources,
            "grouped_documents": grouped_docs
        }

    elif tab == "maintenance":
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM maintenance_files ORDER BY upload_time DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        maintenance_file = row["filename"] if row else None

        tab_template = "tab_maintenance_data.html"
        extra_context = {"maintenance_file": maintenance_file}


    elif tab == "engineers":
        tab_template = "tab_engineers_dashboard.html"
        extra_context = {}

    elif tab == "profiles":
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        conn.close()
        tab_template = "tab_manage_profiles.html"
        extra_context = {"users": users}

    print("DEBUG: Tab =", tab)

    return render_template(
        "admin_dashboard.html",
        active_tab=tab,
        tab_template=tab_template,
        **extra_context
    )

# ----------------- ADMIN MANAGE PROFILES -----------------

# Route to Create New User
@app.route("/admin-create-user", methods=["POST"])
def admin_create_user():
    name = request.form.get("name")
    payroll_number = request.form.get("payroll_number")
    email = request.form.get("email").lower().strip()
    phone = request.form.get("phone")
    password = request.form.get("password")
    role = request.form.get("role")

    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if Payroll Number or Email already exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE payroll_number = ?", (payroll_number,))
    payroll_exists = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE LOWER(username) = ?", (email,))
    email_exists = cursor.fetchone()[0]

    if payroll_exists > 0 or email_exists > 0:
        conn.close()
        flash("Error: A user with this Payroll Number or Email already exists. Please use unique values.", "error")
        return redirect("/admin-dashboard?tab=profiles")

    # If unique, insert new user
    cursor.execute('''
        INSERT INTO users (name, payroll_number, username, phone_number, password, role)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, payroll_number, email, phone, password, role))
    conn.commit()

    # Fetch newly created user ID
    cursor.execute("SELECT id FROM users WHERE username = ?", (email,))
    user_row = cursor.fetchone()
    if user_row:
        new_user_id = user_row["id"]

        # Assign previous documents based on role
        if role in ["Engineer", "Technician"]:
            cursor.execute("SELECT id FROM documents")
            all_documents = cursor.fetchall()

            for doc in all_documents:
                document_id = doc["id"]
                cursor.execute('''
                    INSERT INTO document_recipients (document_id, user_id)
                    VALUES (?, ?)
                ''', (document_id, new_user_id))
            conn.commit()

    conn.close()

    flash("Profile created successfully.", "success")
    return redirect("/admin-dashboard?tab=profiles")


# Route to Edit Existing User
@app.route("/admin-edit-user/<int:user_id>", methods=["POST"])
def admin_edit_user(user_id):
    name = request.form.get("name")
    payroll_number = request.form.get("payroll_number")
    email = request.form.get("email")
    phone = request.form.get("phone")
    password = request.form.get("password")
    role = request.form.get("role")

    conn = sqlite3.connect('nags.db')
    cursor = conn.cursor()

    if password:
        cursor.execute('''
            UPDATE users
            SET name=?, payroll_number=?, username=?, phone_number=?, password=?, role=?
            WHERE id=?
        ''', (name, payroll_number, email, phone, password, role, user_id))
    else:
        cursor.execute('''
            UPDATE users
            SET name=?, payroll_number=?, username=?, phone_number=?, role=?
            WHERE id=?
        ''', (name, payroll_number, email, phone, role, user_id))
    conn.commit()
    conn.close()

    return redirect("/admin-dashboard?tab=profiles")


# Route to Delete User
@app.route("/admin-delete-user/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    conn = sqlite3.connect('nags.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    return redirect("/admin-dashboard?tab=profiles")
# ----------------- SIGN UP (NEW USER REGISTRATION) -----------------

# Temporary storage for OTPs (simple memory store for now)
pending_users = {}

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        payroll = request.form.get("payroll")
        email = request.form.get("email")
        phone = request.form.get("phone")
        role = request.form.get("role")

        if not email.endswith("@nags-ksa.com"):
            flash("Please use your official NAGS email address (@nags-ksa.com).")
            return redirect("/signup")

        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if payroll number or email already exists
        cursor.execute("SELECT * FROM users WHERE payroll_number = ? OR username = ?", (payroll, email))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            flash("This email or payroll number is already registered. Please login or recover your password.")
            return redirect("/signup")

        otp = ''.join(random.choices(string.digits, k=6))
        pending_users[email] = {
            "name": name,
            "payroll_number": payroll,
            "email": email,
            "phone_number": phone,
            "role": role,
            "otp": otp
        }

        msg = Message(
            subject="NAGS Portal - OTP Verification",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f"""Dear {name},

Your OTP code for registration is: {otp}

Please enter this code on the verification page to complete your registration.

Best Regards,
NAGS Maintenance Portal
"""
        mail.send(msg)

        session["pending_email"] = email
        flash("OTP sent to your registered email. Please check your inbox to verify.")
        conn.close()
        return redirect("/verify-otp")

    return render_template("signup.html")

# ----------------- VERIFY OTP -----------------
@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("pending_email")
    if not email or email not in pending_users:
        flash("No signup process found. Please start again.")
        return redirect("/signup")

    if request.method == "POST":
        user_otp = request.form.get("otp")
        if user_otp == pending_users[email]["otp"]:
            flash("OTP verified. Please set your password.")
            return redirect("/set-password")
        else:
            flash("Incorrect OTP. Please try again.")
            return redirect("/verify-otp")

    return render_template("verify_otp.html")


# ----------------- SET PASSWORD -----------------
@app.route("/set-password", methods=["GET", "POST"])
def set_password():
    email = session.get("pending_email")
    if not email or email not in pending_users:
        flash("No signup session found. Please start again.")
        return redirect("/signup")

    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect("/set-password")

        user_data = pending_users[email]
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO users (name, username, payroll_number, phone_number, password, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_data["name"],
            user_data["email"],
            user_data["payroll_number"],
            user_data["phone_number"],
            password,
            user_data["role"]  # No hardcoding anymore
        ))
        conn.commit()

        # Assign documents based on role
        cursor.execute("SELECT id FROM users WHERE username = ?", (email,))
        user_row = cursor.fetchone()
        if user_row:
            new_user_id = user_row["id"]

            if user_data["role"] in ["Engineer", "Technician"]:
                cursor.execute("SELECT id FROM documents")
                all_documents = cursor.fetchall()

                for doc in all_documents:
                    document_id = doc["id"]
                    cursor.execute('''
                        INSERT INTO document_recipients (document_id, user_id)
                        VALUES (?, ?)
                    ''', (document_id, new_user_id))
                conn.commit()

        pending_users.pop(email, None)
        session.pop("pending_email", None)

        flash("Profile created successfully! You can now log in.")
        conn.close()
        return redirect("/login")

    return render_template("set_password.html")
@app.route("/get-sign-status/<int:document_id>")
def get_sign_status(document_id):
    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT upload_time FROM documents WHERE id = ?", (document_id,))
    doc = cursor.fetchone()
    if not doc:
        return jsonify([])

    upload_time = datetime.strptime(doc['upload_time'], "%Y-%m-%d %H:%M:%S")
    today = datetime.now()

    cursor.execute('''
        SELECT u.name, u.payroll_number, dr.is_signed, dr.signed_time
        FROM document_recipients dr
        JOIN users u ON dr.user_id = u.id
        WHERE dr.document_id = ?
    ''', (document_id,))
    users = cursor.fetchall()
    conn.close()

    result = []
    for idx, row in enumerate(users, start=1):
        if row['is_signed']:
            status = "Read and Signed"
        else:
            days_pending = (today - upload_time).days
            status = f"Not Signed ({str(days_pending).zfill(2)} days)"

        result.append({
            "sno": idx,
            "name": row["name"],
            "payroll_number": row["payroll_number"],
            "status": status,
            "is_signed": bool(row["is_signed"])
        })

    return jsonify(result)
@app.route("/generate-report", methods=["POST"])
def generate_report():
    document_id = request.form.get("document_id")

    # Fetch data from DB
    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.name, u.payroll_number, dr.signature_path, dr.signed_time
        FROM document_recipients dr
        JOIN users u ON dr.user_id = u.id
        WHERE dr.document_id = ? AND dr.is_signed = 1
    ''', (document_id,))
    rows = cursor.fetchall()

    cursor.execute('SELECT source, subject, upload_time FROM documents WHERE id = ?', (document_id,))
    doc_info = cursor.fetchone()
    conn.close()

    source = doc_info['source'] if doc_info else 'N/A'
    subject = doc_info['subject'] if doc_info else 'N/A'
    upload_time = doc_info['upload_time'][:10] if doc_info else 'N/A'

    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, PageBreak
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas
    from io import BytesIO
    import os

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    styleN = styles["Normal"]
    styleH = ParagraphStyle('centered_heading', parent=styles['Heading2'], alignment=1)
    total_width = 530
    col_widths = [40, 150, 100, 120, 120]
    max_rows_per_page = 17

    # Header builder function
    def build_header_section():
        logo_path = os.path.join('static', 'logo.jpg')
        logo = Image(logo_path, width=120, height=60) if os.path.exists(logo_path) else Paragraph("NAGS", styleN)
        header = Table([
            [logo],
            [Paragraph("<hr width='100%'/>", styleN)],
            [Paragraph("<b>Read and Sign Record – Maintenance Staff</b>", styleH)]
        ], colWidths=[total_width])
        header.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 2), (-1, 2), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))

        subject_table = Table([
            [Paragraph("<b>Subject or Title of Document:</b>", styleN)],
            [Paragraph(subject, styleN)]
        ], colWidths=[total_width])
        subject_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))

        info_table = Table([
            [Paragraph("<b>Customer Operator:</b>", styleN), Paragraph("<b>Distributed Date:</b>", styleN)],
            [Paragraph(source, styleN), Paragraph(upload_time, styleN)]
        ], colWidths=[total_width / 2] * 2)
        info_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER')
        ]))

        col_headers = [[
            Paragraph("<b>S.No</b>", styleN),
            Paragraph("<b>Employee Name</b>", styleN),
            Paragraph("<b>Staff No.</b>", styleN),
            Paragraph("<b>Signature</b>", styleN),
            Paragraph("<b>Date & Time</b>", styleN)
        ]]
        col_table = Table(col_headers, colWidths=col_widths)
        col_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER')
        ]))
        return [header, subject_table, info_table, col_table]

    for i in range(0, len(rows), max_rows_per_page):
        if i > 0:
            elements.append(PageBreak())

        elements.extend(build_header_section())

        page_data = []
        for j, row in enumerate(rows[i:i + max_rows_per_page], start=i + 1):
            sig_path = os.path.join("signatures", row["signature_path"])
            sig_img = Image(sig_path, width=80, height=20) if os.path.exists(sig_path) else Paragraph("—", styleN)
            date_part, time_part = row["signed_time"].split()
            date_time = Paragraph(f"{date_part}<br/>{time_part}", styleN)
            page_data.append([
                Paragraph(str(j), styleN),
                Paragraph(row["name"], styleN),
                Paragraph(row["payroll_number"], styleN),
                sig_img,
                date_time
            ])

        table = Table(page_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER')
        ]))
        elements.append(table)

    def add_footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(40, 25, "NAGS/QA10/Rev.0 June 2012")
        canvas.drawRightString(550, 25, f"Page {doc.page}")

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    filename = f"R&S Report ({subject} - {source}).pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route("/user-dashboard", methods=["GET", "POST"])
def user_dashboard():
    user = session.get("user")
    if not user or user.get("role") not in ["Engineer", "Technician"]:
        return redirect("/login")

    # Handle the active tab from the query string
    tab = request.args.get("tab", "readsign")  # Default to 'readsign' if no tab is provided
    tab_template = "tab_read_sign.html"
    extra_context = {}

    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch user ID
    cursor.execute("SELECT id, username FROM users WHERE name=?", (user['name'],))
    row = cursor.fetchone()
    if row:
        user_id = row['id']
        user_email = row['username']
    else:
        user_id = None
        user_email = None

    documents = []

    if user_id:
        if tab == "readsign":
            cursor.execute('''
                SELECT dr.id AS recipient_id, d.filename, d.subject, d.source, dr.is_signed
                FROM document_recipients dr
                JOIN documents d ON dr.document_id = d.id
                WHERE dr.user_id = ?
                ORDER BY dr.is_signed ASC, d.upload_time DESC
            ''', (user_id,))
            documents = cursor.fetchall()

            unread_count = sum(1 for doc in documents if not doc["is_signed"])
            session['unread_count'] = unread_count

            tab_template = "tab_read_sign.html"
            extra_context = {"documents": documents}

        elif tab == "mydocs":
            # Handle upload document form submission
            if request.method == "POST":
                doc_name = request.form.get("doc_name")
                expiry_date = request.form.get("expiry_date")  # Can be None
                file = request.files.get("file")

                if not doc_name or not file:
                    flash("Document name and file are required.", "error")
                else:
                    filename = secure_filename(file.filename)
                    save_path = os.path.join(UPLOAD_USER_DOCS, filename)
                    file.save(save_path)

                    cursor.execute('''
                        INSERT INTO user_documents (user_id, doc_name, expiry_date, file_path, upload_time)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        user_id,
                        doc_name,
                        expiry_date if expiry_date else None,
                        filename,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    conn.commit()
                    flash("Document uploaded successfully.", "success")

            # After possible upload, fetch documents
            cursor.execute("SELECT * FROM user_documents WHERE user_id=?", (user_id,))
            documents = cursor.fetchall()

            # Calculate expiring soon
            today = datetime.now().date()
            expiring_count = 0
            for doc in documents:
                if doc["expiry_date"]:
                    try:
                        if isinstance(doc["expiry_date"], str):
                            try:
                                exp_date = datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date()
                            except ValueError:
                                exp_date = datetime.strptime(doc["expiry_date"], "%d-%b-%Y").date()
                        else:
                            exp_date = doc["expiry_date"].date()
                        if (exp_date - today).days <= 30:
                            expiring_count += 1
                    except Exception as e:
                        print("Expiry date parsing error:", e)
            session["doc_expiry_count"] = expiring_count


            tab_template = "tab_my_documents.html"
            extra_context = {"documents": documents}

            # Send expiry email if needed
            if expiring_count > 0:
                try:
                    msg = Message(
                        subject="Document Expiry Reminder",
                        sender=app.config['MAIL_USERNAME'],
                        recipients=[user_email]
                    )
                    msg.body = f"Dear {user['name']},\n\nYou have {expiring_count} document(s) expiring within 30 days.\nPlease check your profile on NAGS Maintenance Portal.\n\n- NAGS Maintenance Team"
                    mail.send(msg)
                except Exception as e:
                    print("Email sending error:", e)

        elif tab == "maintenance":
            cursor.execute("SELECT filename FROM maintenance_files ORDER BY upload_time DESC LIMIT 1")
            row = cursor.fetchone()
            maintenance_file = row["filename"] if row else None
            tab_template = "tab_maintenance_nags_docs.html"
            extra_context = {"maintenance_file": maintenance_file}


        elif tab == "engineers":
            tab_template = "tab_engineers_dashboard.html"

        else:
            tab_template = "tab_read_sign.html"
            cursor.execute('''
                SELECT dr.id AS recipient_id, d.filename, d.subject, d.source, dr.is_signed
                FROM document_recipients dr
                JOIN documents d ON dr.document_id = d.id
                WHERE dr.user_id = ?
                ORDER BY dr.is_signed ASC, d.upload_time DESC
            ''', (user_id,))
            documents = cursor.fetchall()
            extra_context = {"documents": documents}

    conn.close()

    return render_template(
        "user_dashboard.html",  # This is the main layout file
        active_tab=tab,  # Pass the active tab for highlighting
        tab_template=tab_template,  # Pass the correct template for the active tab
        name=user['name'],
        now=datetime.utcnow(),
        **extra_context  # Any extra context needed for the tab content
    )

@app.route("/sign-document", methods=["POST"])
def sign_document():
    if "user" not in session:
        return redirect("/login")

    recipient_id = request.form.get("recipient_id")
    file = request.files.get("file")  # Uploaded signature file
    signature_data = request.form.get("signature_data")  # Drawn signature data (base64)

    if not recipient_id:
        return "Invalid signature submission.", 400

    try:
        # Case 1: If file is uploaded
        if file:
            if file.mimetype not in ['image/png', 'image/jpeg']:
                return "Invalid file type. Only PNG and JPEG are allowed.", 400

            # Save uploaded signature
            filename = secure_filename(f"signature_upload_{recipient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file_path = os.path.join(SIGNATURE_FOLDER, filename)
            file.save(file_path)

        # Case 2: If drawn signature is submitted
        elif signature_data:
            header, encoded = signature_data.split(",", 1)
            binary_data = base64.b64decode(encoded)

            # Save drawn signature
            filename = f"signature_drawn_{recipient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            file_path = os.path.join(SIGNATURE_FOLDER, filename)

            with open(file_path, "wb") as f:
                f.write(binary_data)

        else:
            return "No signature data received.", 400

        # Update database with signed status
        conn = sqlite3.connect("nags.db")
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE document_recipients
            SET is_signed = 1,
                signed_time = ?,
                signature_path = ?
            WHERE id = ?
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), filename, recipient_id))
        conn.commit()
        conn.close()

        return "OK"

    except Exception as e:
        print("Error processing signature:", e)
        return "An error occurred while processing the signature.", 500

@app.route("/fetch-user-documents")
def fetch_user_documents():
    user = session.get('user')
    if not user:
        return jsonify([])

    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE name=?", (user['name'],))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify([])

    user_id = row['id']

    cursor.execute('''
        SELECT dr.id AS recipient_id, d.filename, d.subject, d.source, d.upload_time, dr.is_signed
        FROM document_recipients dr
        JOIN documents d ON dr.document_id = d.id
        WHERE dr.user_id = ?
        ORDER BY dr.is_signed ASC, d.upload_time DESC
    ''', (user_id,))
    documents = cursor.fetchall()
    conn.close()

    result = []
    for doc in documents:
        result.append({
            "recipient_id": doc["recipient_id"],
            "filename": doc["filename"],
            "subject": doc["subject"],
            "source": doc["source"],
            "upload_time": doc["upload_time"],
            "is_signed": bool(doc["is_signed"])
        })

    return jsonify(result)

@app.route('/view-doc/<filename>')
def view_document(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    else:
        return "File not found.", 404

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")

        # Check if email exists in database
        conn = sqlite3.connect('nags.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash("Email not registered. Please check again.", "error")
            return redirect("/forgot-password")

        # Generate OTP and store it
        otp = ''.join(random.choices(string.digits, k=6))
        session["reset_email"] = email
        session["reset_otp"] = otp

        # Send OTP email
        msg = Message(
            subject="NAGS Portal - Password Reset OTP",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f"Dear User,\n\nYour OTP for password reset is: {otp}\n\n- NAGS Maintenance Team"
        mail.send(msg)

        flash("OTP sent to your email. Please check your inbox.", "success")
        return redirect("/verify-reset-otp")

    return render_template("forgot_password.html")

@app.route("/verify-reset-otp", methods=["GET", "POST"])
def verify_reset_otp():
    if "reset_email" not in session:
        return redirect("/forgot-password")

    if request.method == "POST":
        entered_otp = request.form.get("otp")
        if entered_otp == session.get("reset_otp"):
            flash("OTP verified successfully. Set your new password.", "success")
            return redirect("/reset-password")
        else:
            flash("Incorrect OTP. Please try again.", "error")
            return redirect("/verify-reset-otp")

    return render_template("verify_reset_otp.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "reset_email" not in session:
        return redirect("/forgot-password")

    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect("/reset-password")

        conn = sqlite3.connect('nags.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET password = ?
            WHERE username = ?
        ''', (new_password, session["reset_email"]))
        conn.commit()
        conn.close()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)

        flash("Password reset successful. Please log in with your new password.", "success")
        return redirect("/login")

    return render_template("reset_password.html")

@app.route("/admin-delete-document/<int:doc_id>", methods=["POST"])
def admin_delete_document(doc_id):
    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # First find the filename to delete from folder
    cursor.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if row:
        filename = row["filename"]
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Now delete from database
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()

    conn.close()
    flash("Document deleted successfully.", "success")
    return redirect("/admin-dashboard?tab=add")

# Route to handle uploading Maintenance Data File
@app.route("/upload-maintenance-file", methods=["POST"])
def upload_maintenance_file():
    if "user" not in session or session.get("user", {}).get("role") != "Admin":
        return redirect("/login")

    file = request.files.get("maintenance_file")

    if not file:
        flash("No file uploaded.", "error")
        return redirect("/admin-dashboard?tab=maintenance")

    # Check file extension
    allowed_extensions = {'pdf', 'docx', 'xlsx'}
    filename = secure_filename(file.filename)
    if not ('.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions):
        flash("Invalid file type. Only PDF, Word (.docx), and Excel (.xlsx) are allowed.", "error")
        return redirect("/admin-dashboard?tab=maintenance")

    # Save folder path
    upload_folder = os.path.join(os.getcwd(), 'maintenance_data')
    os.makedirs(upload_folder, exist_ok=True)

    # Connect to DB
    conn = sqlite3.connect('nags.db')
    cursor = conn.cursor()

    # Check if previous file exists
    cursor.execute("SELECT filename FROM maintenance_files ORDER BY upload_time DESC LIMIT 1")
    row = cursor.fetchone()

    if row:
        old_filename = row[0]
        old_file_path = os.path.join(upload_folder, old_filename)
        if os.path.exists(old_file_path):
            os.remove(old_file_path)
        cursor.execute("DELETE FROM maintenance_files")

    # Save new file
    save_path = os.path.join(upload_folder, filename)
    file.save(save_path)

    # Insert into DB
    cursor.execute('''
        INSERT INTO maintenance_files (filename, upload_time)
        VALUES (?, ?)
    ''', (filename, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    flash("Maintenance data file updated successfully.", "success")
    return redirect("/admin-dashboard?tab=maintenance")

# Route to serve uploaded maintenance files
@app.route('/maintenance_data/<filename>')
def serve_maintenance_file(filename):
    return send_from_directory(os.path.join(os.getcwd(), 'maintenance_data'), filename)

@app.template_filter('todatetime')
def to_datetime_filter(value, input_format='%Y-%m-%d', output_format=None):
    from datetime import datetime
    try:
        dt = datetime.strptime(value, input_format)
        if output_format:
            return dt.strftime(output_format)
        return dt
    except Exception:
        return value

@app.route('/user_docs/<path:filename>')
def view_user_document(filename):
    return send_from_directory('user_docs', filename)


@app.route('/delete-user-document', methods=['POST'])
def delete_user_document():
    doc_id = request.form.get('doc_id')
    if doc_id:
        conn = sqlite3.connect('nags.db')
        cursor = conn.cursor()

        # Get the file path first to delete the physical file
        cursor.execute("SELECT file_path FROM user_documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()

        if row:
            filepath = os.path.join('user_docs', row[0])
            if os.path.exists(filepath):
                os.remove(filepath)

        # Delete from database
        cursor.execute("DELETE FROM user_documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

    return redirect(url_for('user_dashboard', tab='mydocs'))
def send_expiry_reminders():
    from datetime import datetime, timedelta
    today = datetime.now().date()
    
    # Check if today is 1st or 15th
    if today.day not in [1, 15]:
        return

    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, username FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user['id']
        email = user['username']
        name = user['name']

        cursor.execute("SELECT doc_name, expiry_date FROM user_documents WHERE user_id = ?", (user_id,))
        documents = cursor.fetchall()

        expiring_docs = []
        for doc in documents:
            if doc['expiry_date']:
                try:
                    exp_date = datetime.strptime(doc['expiry_date'], '%Y-%m-%d').date()
                    if 0 <= (exp_date - today).days <= 30:
                        expiring_docs.append(f"- {doc['doc_name']} (expires on {exp_date.strftime('%d-%b-%Y')})")
                except Exception:
                    continue

        if expiring_docs:
            msg = Message(
                subject="Document Expiry Reminder",
                sender=app.config['MAIL_USERNAME'],
                recipients=[email]
            )
            msg.body = f"Dear {name},\n\nThe following document(s) are expiring within 30 days:\n\n" + \
                       "\n".join(expiring_docs) + \
                       "\n\nPlease log in to the NAGS Maintenance Portal to update or review them.\n\n- NAGS QA Team"
            try:
                mail.send(msg)
            except Exception as e:
                print(f"Failed to send email to {email}: {e}")

    conn.close()
@app.route("/get-unread-count")
def get_unread_count():
    user = session.get('user')
    if not user:
        return jsonify({"count": 0})

    conn = sqlite3.connect('nags.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE name = ?", (user['name'],))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"count": 0})

    user_id = row['id']

    cursor.execute('''
        SELECT COUNT(*) as unread_count
        FROM document_recipients
        WHERE user_id = ? AND is_signed = 0
    ''', (user_id,))
    result = cursor.fetchone()
    conn.close()

    return jsonify({"count": result["unread_count"] if result else 0})
@app.route('/')
def index():
    return render_template('login.html')



# ----------------- SERVER START -----------------
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    # Runs daily at 00:10 AM and internally filters for 1st and 15th
    scheduler.add_job(send_expiry_reminders, CronTrigger(hour=0, minute=10))
    scheduler.start()

    app.run(debug=True, host="0.0.0.0")

