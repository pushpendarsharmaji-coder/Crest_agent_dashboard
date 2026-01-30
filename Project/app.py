from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
import random
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import msal
import requests
import secrets, string, os
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, jsonify, send_file
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
import random, string, mysql.connector, requests, json, base64
from reportlab.lib.colors import HexColor, lightgrey
from reportlab.lib.utils import ImageReader
now = datetime.now()
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime
import os
from mysql.connector import IntegrityError

# ---------------- CONFIG ----------------
CLIENT_ID = "a0dd7a8c-dad5-4a70-ad9a-efa2a5961e4d"
CLIENT_SECRET = "RjR8Q~RjUKHscjOPkAq_wOej6ctqjrxbRGP9MbSj"
TENANT_ID = "b9760e09-fe65-4283-8c15-5ec4de5e4007"
SENDER_EMAIL = "pospsupport@crestinsure.com"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://graph.microsoft.com/.default"]

# ---------------- FLASK APP ----------------
app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------

def get_db():
    conn = mysql.connector.connect(
        host="database-1.cuh68eog8q9a.us-east-1.rds.amazonaws.com",
        user="admin",
        password="Ps5638806",
        database="agent_kyc_document",
        port=3306,
        autocommit=True
    )
    cursor = conn.cursor(dictionary=True)
    return conn, cursor
otp_store = {}           # store OTP
verified_emails = {}     # store verified emails
# ---------------- PASSWORD GENERATOR ----------------
def generate_password(length=10):
    chars = string.ascii_letters + string.digits + "@#$%&*"
    return ''.join(secrets.choice(chars) for _ in range(length))

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

# ---------------- MICROSOFT GRAPH TOKEN ----------------
def get_access_token():
    app_msal = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    result = app_msal.acquire_token_for_client(scopes=SCOPE)
    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(result)

# ---------------- SEND PASSWORD EMAIL ----------------
def send_password_email(to_email, password, pan):
    token = get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    body = {
        "message": {
            "subject": "Your POSP Login Password",
            "body": {
                "contentType": "HTML",
                "content": f"""
                <p>Dear Agent,</p>
                <p>Your POSP account has been created successfully.</p>
                <p>
                <b>PAN Number:</b> {pan}<br>
                <b>Login Email:</b> {to_email}<br>
                <b>Temporary Password:</b> {password}
                </p>
                <p>Please change your password after first login.</p>
                <p>Regards,<br>POSP Support Team<br>Crest Insure</p>
                """
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ]
        },
        "saveToSentItems": True
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 202:
        raise Exception(response.text)


@app.route("/")
@app.route("/posp")
def posp():
    return render_template("posp.html")




# ---------------- LOGIN ROUTE ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Please fill in both email and password.", "danger")
            return redirect(url_for("login"))

        conn, cursor = get_db()
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user"] = email 
            session["email"] = email          # ✅ FIXED
            session["user_id"] = user["id"]   # optional but recommended
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "danger")

    return render_template("login.html")


# ---------------- SIGNUP ROUTE ----------------




@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        mobile = request.form.get("mobile")
        pan = request.form.get("pan", "").upper()

        if not email or not mobile or not pan:
            flash("All fields are required", "error")
            return redirect(url_for("signup"))

        conn, cursor = get_db()

        # ✅ Check email / mobile / PAN
        cursor.execute("""
            SELECT email, mobile, pan 
            FROM users 
            WHERE email=%s OR mobile=%s OR pan=%s
        """, (email, mobile, pan))

        existing = cursor.fetchone()
        if existing:
            conn.close()
            flash("Email, Mobile or PAN already registered", "error")
            return redirect(url_for("signup"))

        password = generate_password()
        password_hash = generate_password_hash(password)

        try:
            cursor.execute("""
                INSERT INTO users (email, mobile, pan, password_hash)
                VALUES (%s, %s, %s, %s)
            """, (email, mobile, pan, password_hash))
            conn.commit()

        except IntegrityError as e:
            conn.rollback()
            conn.close()
            flash("PAN already registered. Please login.", "error")
            return redirect(url_for("login"))

        conn.close()

        # Send password email
        try:
            send_password_email(email, password, pan)
        except Exception as e:
            print("EMAIL ERROR:", e)

        session["user"] = email
        flash("Signup successful! Password sent to your email.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


# ---------------- DASHBOARD ROUTE ----------------

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    # ------------------ GET → load dashboard ------------------
    if request.method == "GET":
        if "user" not in session:
            return redirect(url_for("login"))

        conn, cursor = get_db()
        cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
        user = cursor.fetchone()
        conn.close()
        states = [
            "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
            "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
            "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
            "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
            "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
            "Uttar Pradesh", "Uttarakhand", "West Bengal",
            # Union Territories
            "Andaman and Nicobar Islands", "Chandigarh", 
            "Dadra and Nagar Haveli and Daman and Diu", "Delhi", 
            "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
        ]
        # dropdown lists
        managers = ["Rahul Sharma","Priya Patel","Amit Verma","Sneha Kapoor"]

        return render_template("dashboard.html", user=user, states=states, managers=managers)



# ------------------ POST → SAVE submitted data ------------------
    try:
        conn, cursor = get_db()
        upload_folder = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_folder, exist_ok=True)

        # ---- form values ----
        first_name   = request.form.get("first_name")
        middle_name  = request.form.get("middle_name")
        last_name    = request.form.get("last_name")
        dob          = request.form.get("dob")
        pan          = request.form.get("pan")
        account      = request.form.get("account")
        re_account   = request.form.get("reAccount")
        ifsc         = request.form.get("ifsc")
        bank         = request.form.get("bank")
        branch       = request.form.get("branch")
        address      = request.form.get("address")
        pincode      = request.form.get("pincode")
        emp_id       = request.form.get("emp_id")

        state = request.form.get("state")
        if state == "other":
            state = request.form.get("state_input")

        manager_name = request.form.get("manager_name_select")
        if manager_name == "other":
            manager_name = request.form.get("manager_name")

        # ---- file uploads ----
        def save_file(fieldname):
            file = request.files.get(fieldname)
            if not file or file.filename.strip() == "":
                return None
            filename = file.filename.replace(" ", "_")
            path = os.path.join(upload_folder, filename)
            file.save(path)
            return f"static/uploads/{filename}"

        profile_photo   = save_file("doc1")
        pan_doc         = save_file("doc2")
        address_proof   = save_file("doc3")
        bank_proof      = save_file("doc4")
        education_cert  = save_file("doc5")

        # ---- DB update ----
        cursor.execute("""
            UPDATE users SET
                first_name=%s, middle_name=%s, last_name=%s, dob=%s,
                pan=%s, account=%s, re_account=%s, ifsc=%s,
                bank=%s, branch=%s, address=%s, pincode=%s, state=%s,
                manager_name=%s, emp_id=%s,
                status='Pending Verification',
                profile_photo = COALESCE(%s, profile_photo),
                pan_doc       = COALESCE(%s, pan_doc),
                address_proof = COALESCE(%s, address_proof),
                bank_proof    = COALESCE(%s, bank_proof),
                education_cert= COALESCE(%s, education_cert)
            WHERE email=%s
        """, (
            first_name, middle_name, last_name, dob,
            pan, account, re_account, ifsc,
            bank, branch, address, pincode, state,
            manager_name, emp_id,
            profile_photo, pan_doc, address_proof, bank_proof, education_cert,
            session["user"]
        ))

        conn.commit()

        # ---- Re-fetch user for updated values ----
        cursor.execute("SELECT status, agent_code FROM users WHERE email=%s", (session["user"],))
        updated_user = cursor.fetchone()

        conn.close()
        return jsonify({
            "success": True,
            "message": "Profile updated — Pending verification",
            "status": updated_user["status"],
            "agent_code": updated_user["agent_code"]
        })


    except Exception as e:
        print("\n❌ DASHBOARD ERROR:", e, "\n")
        return jsonify({"success": False, "error": str(e)})



@app.route("/get_user_info")
def get_user_info():
    user_email = session.get("user")
    if not user_email:
        return jsonify({"error": "User not logged in"}), 401

    conn, cursor = get_db()
    cursor.execute("SELECT agent_code, status, doj FROM users WHERE email=%s", (user_email,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "User not found"}), 404

    agent_code, status, doj = row["agent_code"], row["status"], row["doj"]

    if isinstance(doj, date):
        doj_str = doj.isoformat()
    elif doj is None:
        doj_str = ""
    else:
        doj_str = str(doj)

    return jsonify({
        "agent_code": agent_code or "",
        "status": status or "",
        "doj": doj_str
    })



#________Forgot Password_________
  
def send_otp_graph(to_email, otp):
    app_msal = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    token_response = app_msal.acquire_token_for_client(scopes=SCOPE)
    access_token = token_response.get("access_token")
    if not access_token:
        print("❌ Failed to get access token")
        return False

    email_msg = {
        "message": {
            "subject": "Crest Insurance | OTP Verification for Password Reset",
            "body": {
                "contentType": "Text",
                "content": (
                    f"Dear Partner,\n\n"
                    f"We received a request to reset your password for your "
                    f"Crest Insurance Brokers Pvt. Ltd account.\n\n"
                    f"🔐 One-Time Password (OTP): {otp}\n"
                    f"⏳ Validity: 10 minutes\n\n"
                    f"Please use the above OTP to complete your verification process. "
                    f"If you did not initiate this request, kindly ignore this email "
                    f"or contact our support team immediately.\n\n"
                    f"Best regards,\n"
                    f"Crest Insurance Brokers Pvt. Ltd\n"
                    f"📧 pospsupport@crestinsurance.com\n"
                    f"🌐 www.crestinsurance.com\n"
                )
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ]
        }
    }
    endpoint = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(endpoint, json=email_msg, headers=headers)
    return response.status_code == 202

def get_user(email):
    conn, cursor = get_db()
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def update_password(email, new_password_hash):
    conn, cursor = get_db()
    cursor.execute(
        "UPDATE users SET password_hash=%s WHERE email=%s",
        (new_password_hash, email)
    )
    cursor.close()
    conn.close()

# ------------------ FLASK ROUTES ------------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = get_user(email)
        if user:
            otp = random.randint(100000, 999999)
            session["otp"] = otp
            session["otp_expiry"] = (datetime.now() + timedelta(minutes=10)).timestamp()
            session["email"] = email
            if send_otp_graph(email, otp):
                flash("OTP sent to your registered email.", "info")
                return redirect(url_for("verify_otp"))
            else:
                flash("Failed to send OTP. Try again later.", "danger")
        else:
            flash("Email not found!", "danger")
    return render_template("forgot_password.html")

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        input_otp = request.form.get("otp")
        otp = session.get("otp")
        expiry = session.get("otp_expiry")
        if not otp or not expiry or datetime.now().timestamp() > expiry:
            flash("OTP expired. Please request a new one.", "danger")
            return redirect(url_for("forgot_password"))
        if str(input_otp) == str(otp):
            flash("OTP verified. Set your new password.", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Invalid OTP. Try again.", "danger")
    return render_template("verify_otp.html")




@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        new_password = request.form.get("new_password")
        email = session.get("email")
        if email:
            hashed_password = generate_password_hash(new_password)
            update_password(email, hashed_password)
            session.pop("otp", None)
            session.pop("otp_expiry", None)
            session.pop("email", None)
            flash("Password updated successfully!", "success")
            return redirect(url_for("login"))
        else:
            flash("Session expired. Try again.", "danger")
            return redirect(url_for("forgot_password"))
    return render_template("reset_password.html")





@app.route("/get_bank_name")
def get_bank_name():
    ifsc = request.args.get("ifsc", "").upper()

    if not ifsc:
        return {"error": "IFSC required"}, 400

    url = f"https://ifsc.razorpay.com/{ifsc}"
    response = requests.get(url)

    if response.status_code != 200:
        return {"error": "Invalid IFSC"}, 404

    data = response.json()

    return {
        "bank_name": data.get("BANK"),
        "branch_name": data.get("BRANCH"),
        "address": data.get("ADDRESS")
    }



@app.route("/logout")
def logout():
    session.pop("user", None)  # Remove user from session
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

#____agreememnt otp__download_
def send_email(to_email, subject, body_text, pdf_bytes=None, filename=None):
    try:
        token = get_access_token()
        url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        email_msg = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": [{"emailAddress": {"address": to_email}}]
            }
        }

        if pdf_bytes and filename:
            email_msg["message"]["attachments"] = [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentBytes": base64.b64encode(pdf_bytes).decode('utf-8')
            }]

        resp = requests.post(url, headers=headers, json=email_msg)
        return resp.status_code == 202
    except Exception as e:
        print("Email Error:", e)
        return False






# ------------------- SUBMIT EXAM ----------------
@app.route("/submit-exam", methods=["POST"])
def submit_exam():
    data = request.json
    email = data.get("email")
    try:
        score = int(data.get("score", 0))
        total = int(data.get("total_questions", 50))
    except ValueError:
        return jsonify({"error": "Invalid score or total"}), 400

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Determine pass/fail (50% passing)
    passed = score >= (total * 0.5)
    new_status = "Passed" if passed else "Failed"

    # Database connection
    conn, cursor = get_db()

    # Update existing user row
    cursor.execute("""
        UPDATE users
        SET score = %s,
            total_questions = %s,
            passed = %s,
            exam_status = %s
        WHERE email = %s
    """, (score, total, int(passed), new_status, email))
    conn.commit()

    # Check if the user exists / row was updated
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    # Send OTP if passed
    if passed:
        otp = random.randint(100000, 999999)
        otp_store[email] = otp
        send_email(email, "Your OTP Code", f"Your OTP is {otp}")

    conn.close()

    # Return JSON response
    return jsonify({
        "status": new_status,
        "passed": passed,
        "score": score,
        "total_questions": total,
        "email": email,
        "can_download": passed
    })




# ------------------- VERIFY OTP ----------------
@app.route("/verify-otp_2", methods=["POST"])
def verify_otp_2():
    data = request.json
    email = data.get("email")
    otp = str(data.get("otp"))

    if email in otp_store and str(otp_store[email]) == otp:
        otp_store.pop(email)
        return jsonify({"status": "verified"})
    else:
        return jsonify({"status": "failed", "message": "Wrong OTP"})
    
@app.route("/training")
def training_page():
    if "email" not in session:
        return redirect(url_for("login"))  # safety check

    email = session.get("email")
    return render_template("training_page.html", email=email)





# FIRST LOAD (no email yet)
@app.route("/exam_page")
def exam_page_initial():
    return render_template("exam_page.html", email="")

# AFTER PASS (email required)
@app.route("/exam_page/<email>")

def exam_page(email):
    conn, cursor = get_db()
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return "Email not registered!", 404

    return render_template("exam_page.html", email=email, user=user)




# ------------------- AGREEMENT PDF ----------------
def draw_header(c, width, height, logo_path, primary):
    # Outer Border
    c.setStrokeColor(primary)
    c.setLineWidth(3)
    c.rect(25, 25, width - 50, height - 50)

    # Header Bar
    c.setFillColor(primary)
    c.rect(25, height - 130, width - 50, 105, stroke=0, fill=1)

    # Logo
    if os.path.exists(logo_path):
        c.drawImage(
            ImageReader(logo_path),
            40, height - 105, 60, 65, mask="auto"
        )

    # Company Name
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(
        width / 2, height - 65,
        "Crest Insurance Brokers Pvt. Ltd."
    )

    # Company Info
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        width / 2, height - 90,
        "Reg. Office: Unit–12, First Floor, Landmark House, Sector–44, Gurugram–122003"
    )
    c.drawCentredString(
        width / 2, height - 105,
        "CIN: U66000HR2021PTC098960 | IRDAI Reg: 895/2025 | IBAI: 13841"
    )

@app.route("/agreement")
def agreement():
    if "user" not in session:
        return redirect(url_for("login"))

    email = session["user"]

    conn, cursor = get_db()
    cursor.execute("""
        SELECT first_name, middle_name, last_name, pan, address, agent_code, doj
        FROM users WHERE email=%s
    """, (email,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return "Agreement not available."

    # Paths
    agreement_dir = os.path.join(app.root_path, "static", "agreements")
    os.makedirs(agreement_dir, exist_ok=True)

    file_path = os.path.join(
        agreement_dir, f"agreement_{user['agent_code']}.pdf"
    )

    logo_path = os.path.join(app.root_path, "static", "assets", "crest_logo.png")
    sign_path = os.path.join(app.root_path, "static", "assets", "signature.png")
    seal_path = os.path.join(app.root_path, "static", "assets", "seal.png")

    # PDF
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    primary = HexColor("#1f3c88")
    accent = HexColor("#c9a227")
    text = HexColor("#333333")

    # User details
    full_name = " ".join(filter(None, [
        user["first_name"],
        user["middle_name"],
        user["last_name"]
    ]))
    pan = user["pan"]
    doj_raw = user["doj"]
    doj_date = datetime.strptime(doj_raw, "%Y-%m-%d")
    expiry_date = doj_date.replace(year=doj_date.year + 3)

    doj_formatted = doj_date.strftime("%d %B %Y")
    expiry_formatted = expiry_date.strftime("%d %B %Y")

    # -------- AGREEMENT CONTENT (15 PAGES) --------
    agreement_pages = []

    for i in range(1, 16):
        agreement_pages = [

        f"""
        Service Agreement cum Appointment Letter with POSP 

        This Marketing Agreement ("Agreement") is entered into between
        Crest Insurance Brokers Pvt. Ltd. ("Company") and {full_name},
        residing at {user['address']}.
        Agent Code: {user['agent_code']}
        Date of Joining: {doj_formatted}

        This Service Agreement cum Appointment Letter with POSP (hereinafter referred to as the 
        'Agreement', which term shall include the annexures, attachments, addendums and schedules 
        described therein/ appended / attached thereto) is effective from {doj_formatted} by 
        and  {expiry_formatted}
        Between: 
    
        Crest Insurance Brokers Private Limited, a company incorporated under the provisions of 
        Companies Act, 2013 and having its Registered & Corporate office at The Plot - 65, First Floor, 
        Landmark House, Sector - 44, Gurugram, HR 122003 (hereinafter referred to as "the Company" 
        or "Insurance Broker", which expression shall, unless it be repugnant to the context or meaning 
        thereof, be deemed to mean and include its legal representatives, assigns, administrators, 
        representative-in-interest and executors) of the First Part; 
        
                                                    And 
    
        Mr./Ms./Mrs. {full_name}, PAN No. {user['pan']}
        POS 
        Regn. No. - {user['agent_code']} (hereinafter referred to as the "POSP") having 
        its place of residence and/or work at which expression shall, unless repugnant or contrary to
        the context, include its representatives in interest and permitted assigns) of the Other Part. 
        The Company and the POSP shall hereinafter be individually referred to as the "Party" and 
        collectively as the "Parties".
        RECITALS 
        A. Whereas, Company is a composite broker registered by IRDAI vide registration No.841 
        Valid up to 02/08/2028 and renewable thereafter from time to time.""",
        f"""B. Whereas, Company wishes to engage with POSP to solicit the insurance products, as may 
        be specified by IRDAI from time to time, on the terms and conditions provided for herein  
        
        and the POSP desires to enter into an Agreement with Company for the solicitation of such 
        insurance products in accordance with the terms specified in this Agreement.
        NOW THIS AGREEMENT WITNESSETH AND IT IS HEREBY AGREED BY AND 
        BETWEEN THE PARTIES HERETO AS FOLLOWS: 
        
        1. DEFINITIONS 
        
        It is expressly understood by and between the Parties hereto that the terms mentioned in this 
        Agreement shall have the same meaning as ascribed to it under the Regulations. 
        a) "Act" means the Insurance Act, 1938 (4 of 1938). 
        
        b) "Authority" or "IRDAI" means the Insurance Regulatory and Development Authority of 
        India established under the provisions of Section 3 of the Insurance Regulatory and 
        Development Authority Act, 1999 (41 of 1999). 
        
        c) "Effective Date" shall mean the date of acceptance of this Agreement by POSP i.e.  
        
        d) "Insurer" - as defined under Section 2 (9) of lnsurance Act, 1938. 
        e) "IRDAI" means the Insurance Regulatory and Development Authority of lndia; 
        
        f) "IRDAI Guidelines" means master circular on point of sales products and persons - life
        insurance, or any other class of insurance category or product as issued by IRDAI from 
        time to time. 
        
        g) "IRDAI Regulations" means the Act, IRDAI Guidelines, and Insurance Regulatory and 
        Development Authority (Insurance Company) Regulations, 2013 or such other rules, 
        regulations, circular, master circular, or guidelines issued by the IRDAI from time to time 
        and are applicable in relation to the nature of engagement set out in this Agreement; 
        h) "POSP" - means Point of Sale Person as defined in guidelines issued by IRDAI relating to
        the point of sale persons, in relation to the insurance products of life non-life and health;""",
        f"""i) "Website" - shall mean the Insurance Self Networking Platform (ISNP) as approved 
        website and is used by the Insurance Broker. 
        
        2 Interpretation: 
        
        All definitions mentioned in the IRDAI Guidelines, IRDAI Insurance (Broker) Regulations, 2018 
        and guidelines related to POSPs for Insurers (Life, Non-Life & Health) updated from time to 
        time and regulations for Insurance Brokers and POSP shall apply mutatis mutandis to the terms
        of this Agreement. 
        
        In this Agreement, headings are for convenience only and do not affect the interpretation of 
        this Agreement, and, unless the context otherwise requires:
        a) words in the singular include the plural and vice-versa; 
 
        b) words importing a gender include any gender; 
        
        c) a reference to a Clause is to a clause of this Agreement; 
        
        d) All words and expressions used and not defined in this Agreement but defined in the 
        Insurance Act 1938, the Insurance Regulatory and Development Authority Act, 1999 or any of
        the Regulations made thereunder shall have the meanings respectively assigned to them in those
        Acts or Regulations. 
        
        3 APPOINTMENT OF POSP 
        a) Subject to the terms and conditions of this Agreement, the Company hereby appoints - the 
        POSP for the purpose of provisions and providing the services of selling and servicing of 
        insurance policies and insurance products as given in Annexure I on behalf of the Company in
        accordance with applicable laws, including without limitation the Act, IRDAI Guidelines, and
        standard policy practices of the Insurance Broker. 
        
        b) The Company and the POSP expressly agree that the POSP is not an employee of the Company 
        and shall be considered to be an independent contractor for the purposes of this Agreement.""",

        f""" The POSP shall not be reimbursed of any expenses incurred under this Agreement and shall 
        supply his or her own work place, use his or her own supplies and set his or her own work hours,
        at no cost to the Company. 

        4. QUALIFICATIONS 
        
        The POSP shall possess the qualifications prescribed by the IRDAI from time to time, including
        but not limited to the following qualifications: 
        (i) Completion of 10th standard qualification. 
        (ii) Completion of 15 (fifteen) hours of training and also passed the examination conducted by
        the Company in this regard as to Point of Sales Persons. 
        (iii) Compliance with all the formalities under the IRDAI Regulations, from time to time. 
        (iv) Must be in capacity to legally execute, deliver and perform this Agreement, having reached
        the age of majority, having a sound mind and no criminal records against his/her name.

        5. TRAINING AND EXAMINATION 
 
        a) The POSP shall attend an in-house training session for a minimum of 15 (fifteen) hours as
        may conducted by the Company in accordance with the specifications laid down under the IRDAI 
        Guidelines on Point of Sales Person - Life, Non-Life & Health. 
        
        b) Post completion of the in-house training session, the POSP shall be required to undertake
        the exam conducted by the Company in accordance with Company guidelines. 
        
        c) Upon successful completion and passing of the exam and registration of the POSP with the 
        Insurance Information Bureau of India (IIB) the POSP shall receive a certificate from the 
        Company  in the format as prescribed under the IRDAI Guidelines on Point of Sales Person-Life
        and Non-Life and issue unique codes to the successful candidates with appropriate terms and 
        conditions. 

        d) Further, the POSP shall be required to take part in such training or improvement program 
        which may be required and conducted in accordance with the Company policies or IRDAI Regulations
        issued or amended by the IRDAI from time to time.""",

        f"""6. SCOPE OF SERVICES AND COMPENSATION: 
        
        The Parties agree that POSP shall perform the activities as allowed and envisaged under the IRDAI 
        Regulations prescribed from time to time by IRDAI and the applicable laws. 
        
        The Company agrees to make payment to the POSP for the services and discharge of his/her 
        functions as well as obligations to be rendered by the POSP as specified in Annexure II attached 
        hereto. The payment will be subject to deduction of all applicable taxes. 
        
        POSP confirms that the first /incepting policy sale done by him/her, if solicited for himself/herself, 
        the commission for the same policy shall not be payable by the Company and if paid/payable all 
        payments shall be at the discretion of the management. 
        
        7. TERM AND TERMINATION: 
        
        a) This Agreement shall become effective from the Effective Date and shall remain in force till expiry 
        or cancellation of the POSP certification for any reason whatsoever, or termination by the Parties 
        in accordance with this Agreement, whichever is the earliest. 
        
        b) The Parties can renew or enter into another agreement or may on or prior to the expiry of the term 
        aforementioned, mutually agree in writing to extend this Agreement. 
        
        c) Notwithstanding anything contained in this Agreement to the contrary or notwithstanding any 
        separate written communication, either Party may terminate this Agreement at any time by 
        providing one (1) month's prior notice in writing to the other Party during the validity of the 
        Agreement. 
        
        d) The Company will reserve the right to terminate the agreement immediately upon the occurrence 
        of any of the following events by POSP, and upon such occurrence the Parties shall be obligated to 
        make only those payments the right to which accrued till the date of termination: 
        
        • Failure of the POSP to attend the in-house training session as conducted by the Company; 
        • Failure of the POSP to clear the examination as conducted by Company; 
        • Conviction of a felony by POSP;""",

        f"""• Misappropriation (or failure to remit) any funds or property due to the Company from POSP; 
        • Determination that POSP is not in compliance with Company guidelines 
          or the terms of this Agreement and POSP has failed to rectify/resolve the problem within 10 days 
          of the Company providing written notice of same; 
        • In the event of fraud or material breach of any of the conditions or provisions of this Agreement 
          on the part of the POSP, upon which the Company may terminate the Agreement immediately. 
        • Failure to comply with the directions and/or guidelines of the Company communicated to the 
          POSP from time to time. 
        • Furnishing incorrect information or concealing information or failure to disclose material facts of 
          the policy to the policy holder. 
        • Furnishing wrong information, concealing information and/or failure to disclose the material facts 
          in the proposal form that adversely impacts underwriting. 
        • Failure to resolve complaints, unless the circumstances are beyond the POSP's control, emanating 
          from the business procured by him/her and persons he deals with 
        • Indulging in inducement in cash or kind with customer or any other insurance 
          intermediary/agent/insurer or with the employees, directors or supplier/vendor of the Company. 
        • Failure to pay any penalty levied on his account. 
        • Failure to carry out his obligations as prescribed in the agreement and in the provisions of: 
          Act/regulations/circulars or guidelines by IRDAI from time to time. 
        • Acts in a manner prejudicial to the interest of the Company or the customer 
        • Acts in a manner that amounts to diverting funds of his Group/Affiliates or associates rather than 
          engaging in the activity of soliciting and servicing insurance business 
        • Is found guilty of fraud or is charged or convicted in any criminal act. 
        • Indulges in any other misconduct. 
        • Obtaining, seeking, providing and/or giving undue favours from or to any employee of the 
          Company, any Insurer, other POSPs, person and/or policyholder. 
        • Violation of code of conduct or any of the regulations, guidelines and/or operating instructions of 
          the Company, insurance company and/or IRDAI or upon any commission or omission which 
          constitutes a malpractice. 
        
        e) Agreement shall automatically terminate if the POSP acquires a license as or becomes related to, 
        an insurer, insurance agent, corporate agent, a micro-insurance agent, TPA, surveyor, referral 
        partner or loss assessor or employee or director. Upon contravention of this Clause 5(e) by the 
        POSP, the POSP shall be liable to indemnify the Company to the extent of such losses as may be""",

        f"""incurred by the Company arising out of such termination. 
        f) POSP shall be solely and absolutely responsible for the accuracy, truthfulness and completeness 
        of the information furnished in its report and submissions in proposal forms logged by such POSP 
        or otherwise made available to the Company and/or any insurance company. 
        g   ) Notwithstanding anything contained hereinabove, The Company may terminate POSP's appointment with 
        or without assigning any reason. 
        h) The Company, at its sole discretion, reserves the right to conduct a KYC/background verification 
        of the POSP at such intervals, as it may deem appropriate. If, in the sole opinion of Company, the POSP
        does not fulfil the qualifications as prescribed under this Agreement, then the Company may terminate 
        the Agreement immediately.

        8. REPRESENTATIONS AND WARRANTIES

        a) POSP represents and warrants to the Company that:
        (i) He/she has the necessary qualification power or authority and the legal right to provide services to 
            the Company in respect of all or any of the functions.
        (ii) He/she has never been convicted of any crime involving moral turpitude and is not disqualified as 
            per section 42D(5) of the Insurance Act and remains fit and proper as per the format enclosed 
            herewith as Annexure -2;
        (iii) He/she is not associated with or has been simultaneously engaged by any other insurance 
            intermediary or insurer (Life, Non-Life & Health) for providing similar obligations as more 
            specifically provided under Clause 7 of this Agreement;
        (iv) He shall not during the term of this Agreement engage himself/herself with any other insurance 
            intermediary or insurer (Life, Non-Life & Health).
        (v) He has the necessary power or authority and the legal right to execute, deliver and perform this 
            Agreement;
        (vi) He shall comply with all applicable regulatory and other legal requirements to this Agreement.
        (vii) POSP will diligently and to the best of its ability ensure that the facts set forth by any 
            applicant/prospect in any application it solicits are true and correct.

        b) The Company hereby represents and warrants to - that:
        (i) It has obtained all the necessary approvals, permits and authorizations internally or otherwise, as 
            may be required to engage in the business as envisaged under and to enter into this Agreement;
        (ii) It has fulfilled all the criteria provided under the applicable Regulations but not limited to the""",

        f"""IRDAI Guidelines on Point of Sales Person for: Life Insurers, Non-Life & Health Insurers, 
            Guidelines on Point of Sales Person - Life Insurers, Insurance Regulatory and Development 
            Authority (Insurance Broker) Regulations, 2013 and amendments thereof to act as POSP
        (iii) It shall comply with all applicable regulatory and other legal requirements to this Agreement.
        
        9. OBLIGATIONS OF POSP:
            The POSP hereby agrees, covenants and undertakes with - as follows:
            
        a)  POSP will comply with all laws and regulations which relate to this Agreement and shall indemnify 
            and hold the Company harmless for its failure to do so. POS shall maintain in good standing, at its 
            own cost, licenses required by all applicable statutes and regulations.
        b)  POSP shall not solicit any business except: mentioned in Schedule "A" i.e., the insurance policies 
            and products authorized by IRDAI from time to time.
        c)  POSP will comply with the Company's rules and regulations relating to solicitation of the insurance 
            business. As a material part of the consideration for the making of this Agreement by the Company, 
            POSP agrees that there will be made no representations whatsoever with respect to the nature or 
            scope of the benefits of the insurance policies sold except through and by means of the written 
            material either prepared and furnished to POSP for that purpose by the Company or approved in 
            writing by the Company prior to its use. POSP shall have no authority and will not make any oral 
            or written alteration, modification, or waive of any of the terms or conditions ofany insurance policy 
            whatsoever.
        d)  POSP will conduct itself so as not to affect adversely the business, good standing, goodwill and 
            reputation of the Company.
        e)  POSP agrees not to employ or make use of any advertisement in which the Company's (or its 
            affiliate's) name or its registered trademarks are employed without the prior written approval and 
            consent of the Company or as provided by the Company from time to time. Upon request of POSP 
            during the term of this Agreement, the Company may make available for POSP's use, standard 
            visiting cards, and other material. POSP may add, at POSP's sole expense, to the standard 
            advertising only its business name, business address, POSP number and telephone number, as 
            provided for in the advertising. No deletions or changes in the advertising copy are permissible.

        f)  POSP shall act solely as an independent contractor, subject to the control and guidance of the 
            Company, and as such, shall have control on: all matters, its time and effort in the placement of the""",

        f"""Policies offered hereunder. Nothing herein contained shall be construed to create the relationship 
            of employer and employee between POSP and Company.
        g)  POSP shall indemnify and hold the Company and its officers, employees harmless from all 
            expenses, costs, causes of action, claims, demands, liabilities and damages, including reasonable 
            attorney's fees, resulting from or growing out of any unauthorized act or transaction or any negligent 
            act, omission or transaction by POSP or employees of POSP.
            
        h)  Change of Address. POSP shall notify Company in writing of any change of address and/or 
            communication at least thirty (30) days prior to the effective date of such change.
        i)  POSP shall not engage or employ anyone as canvassers or agents for soliciting the insurance 
            business.
        j)  Collection of Premiums. In the event any customer wishes to make payment of premium 
            cash,POSP shall not and shall have no authority, to collect cash or money from any customer/
            prospective customer or provide receipt for premiums to customer and shall assist or direct the
            customer in depositing the premium with the insurer directly by way of directing the customer to
            appropriate officer of the insurer for compliance of section 64VB of the Insurance Act 1938. 
            Notwithstanding anything contained in this Agreement, the POSP agrees to indemnify and hold 
            harmless the Company and its employee against any demand, claim, action or proceeding arising from
            any breach of this Clause.
        k)  Other Expenses. POSP shall have no claim and shall not be entitled to reimbursement for any 
            expenses.
        l)  POSP shall faithfully perform all duties required under the code of conduct prescribed by IRDAI, 
            cooperate with the Company in all matters pertaining to the issuance of policies, cancellations, 
            claims and strive to promote the best interest of the Company.
        m)  This Agreement is exclusive in nature and the POSP will be bound not to work for any other 
            intermediaries or insurance companies.
        n)  POSP will ensure the compliance of all KYC/AML guidelines of the Company and IRDAI as may 
            be issued from time to time and obtain the necessary documents in this regard specifically including 
            but not limited to the provisions of the Anti- Money Laundering Act 2002, IRDAI Master Circular on Anti 
            Money laundering /Counter -Financing of Terrorism (AML-CFT) Guidelines for Life Insurers dated 28th 
            September 2015 and amendments to the same from time to time. POSP will also ensure the compliance of 
            Insurance Regulatory and Development Authority of India (Insurance Brokers) Regulations, 2018 
            SCHEDULE I- Form Hand any other subsequent circulars issued by the Authority. 
        o)  POSP shall not charge any claim consultancy fees and any if such opportunity that comes in this""",

        f"""area, s/he shall be further obliged to immediately bring the same to the notice of the Company for 
            its further action.

        p)  Any penalty levied by the IRDAI based on the violations and non-compliance by the POSP of the 
            applicable laws and regulations shall be borne by the POSP and not the Company. Similarly, in 
            case of any suspension, cancellation or withdrawal of license of the Company because of any 
            breaches/non-compliance on account of POSP, the POSP shall indemnify the Company for actual, 
            direct, indirect and consequential losses specifically arising from violation of IRDAI Guidelines, 
            IRDAI Insurance (Broker) Regulations, 2018 and guidelines related to POSP's for Insurers (Life, 
            Non-Life & Health) as updated from time to time.

        q)  The POSP shall be duty bound to cooperate with the officers of IRDAI for the purpose of inspection 
            as may be required by IRDAI inspectors or investigating authority from time to time.

        r)  The POSP shall carry on its business pertaining to POSP products lawfully and diligently, and in 
            compliance with all applicable laws, rules and regulations including but not limited to the IRDAI 
            Guidelines on Point of Sales Person - Non-Life & Health Insurers, Guidelines on Point of Sales 
            Person -Life Insurers,

        s)  The POSP shall maintain proper records and reports of its activities under in a manner as mutually 
            agreed upon by the Parties and in a manner prescribed by IRDAI.

        t)  The POSP shall comply with all the provisions of the Insurance Act 1938, IRDA Act, 1999 and rules 
            and regulations framed thereunder and such other directions issued and/or amended by the 
            Authority from time to time.

        u)  The Company shall have the right to inspect the POSP including books and records of the POSP as 
            may be required by the Company under this Agreement. Further the Company shall have the right 
            to review the performance of the POSP from time to time.
        
        10. OBLIGATIONS OF COMPANY

        a)  The Company shall be responsible for conducting an in-house training session of the POSP for a""",
        f"""minimum period of 15 (fifteen) hours as per the model syllabus specifically provided under the 
            IRDAI Guidelines on Point of Sales Person- Life and Non-Life which may include features of various 
            products designed by the insurer/s from time to time and may be modified and developed according 
            to the business needs.
        b)  The Company will issue a certificate to the POSP in the format as specified under the IRDAI 
            Guidelines on Point of Sales Person - Life and Non-Life only upon and subject to successfully 
            clearing the exam it conducts and on fulfilling any other conditions that the Company may be 
            required to imposed under applicable laws.
        c)  The Company shall maintain records of all information obtained through the POSP, the details 
            of the policies sold out of such information thus obtained and other functions/activities performed
            by POSP as a part of his engagement/appointment with the Company. The Company shall furnish such 
            records or information in relation to this agreement as and when required by the Authority.

        d)  The Company shall upload the details of the POSP with the Insurance Information Bureau (IIB), 
            Hyderabad and thereafter shall maintain proper record of training and examination for a minimum 
            of 5 (five) years from the end of financial year in which these examinations are conducted and shall 
            make available such records for the purpose of inspection by the respective government authority.

        e) The Company will deliver to the customer all insurance policies and related correspondence or 
            similar documents, in accordance with Company procedures. 
            
        f) The Company shall respond in a reasonable and timely manner to inquiries and questions about the 
            POSP products, raised by POSP, on the dedicated email ID of the Company for this purpose, as 
            communicated to POSP from time to time. 
            
        g) The Company shall maintain reasonable accounting, administrative, and statistical records in 
            accordance with prudent standards of insurance record keeping, including premium, sale or effective 
            date, and any other records needed to verify coverage, pay claims, or underwrite the Company 
            insurance products, of any insured participant covered under the policies.""",
        
        f"""11  RESERVATION OF RIGHTS

        a) The Company reserves the right to reject any and all applications for insurance policies submitted 
            by POSP if they are not found to be of the order of merit required by the customer or the Company or 
            any insurance company.
        b) The Company reserves the right to discontinue writing or offering any of the insurance policies 
            and/or change the scope of work of the POSP. 
            
        c) The Company shall share with the POSP, information relating to its products from time to time.

        12 PRIVACY POLICY

        a) POSP confirms and undertakes that he will not violate privacy covenants stipulated by the Company 
            and/or under any applicable laws, rules and regulations issued by the IRDAI, and in case of any 
            breach of privacy the POSP shall be solely responsible for losses arising out of the same. 
        
        b) POSP shall ensure that there are proper encryption and security measures to prevent any hacking 
            into the information/data pertaining to transactions contemplated under this Agreement. POSP shall 
            adhere to the appropriate security norms including but not limited to the Information Technology 
            (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 
            2011 as amended from time to time. 
        
        c) POSP shall not share any information of the customers and the Company with others without 
            permission of the customer and the Company.

        13. INTELLECTUAL PROPERTY RIGHTS AND BRANDING:

            All intellectual property rights (in the nature of trademark or copyright or any other right)
            in the brand name, product names, logos, designs, colour schemes, names, marks, designs, drawings,
            colour, artistic work / manner etc. (hereafter collectively referred as "Marks") shall vest 
            exclusively and at all times with the Company and the POSP agrees and undertakes not to set up 
            an adverse claim at any time either during the currency of this Agreement or at any time thereafter.""",

        f"""The POSP also agrees and undertakes that it shall not allow the usage of Marks by any other third 
            party.

        14. CONFIDENTIALITY: 

            Both Parties recognize, accept and agree that all tangible and intangible information obtained or 
            disclosed to each other and/or its personnel/representatives, including all details, documents, data, 
            records, reports, systems, papers, notices, statements, business information, practices, trade secrets, 
            client's or customer's details or information (all of which are collectively referred to as 
            "Confidential Information") shall be treated as confidential and both Parties agree and undertake 
            that the same will be kept secret and will not be disclosed, save as provided below, in whole or in

        part to any person/sand/or used and/or be allowed to be used for any purpose other than as may be 
            necessary for the due performance of obligations hereunder, except with written authorization from 
            other Party.
        a) POSP agrees and undertakes that he shall hold all Confidential Information m confidence and in 
            particular shall:    
        
        1. not use or permit or enable any person to use any of the Confidential Information m any manner. 
        2. not disclose or divulge any Confidential Information to any person return all and any Confidential 
        Information which may be in his possession/custody within three years of termination/ expiry of 
        this Agreement. 
        3. not to provide copies of any such materials, documents and other information, which are meant for
        internal circulation only, to any third party 
        
        b) The obligation of confidentiality as above shall not apply to any information which is: 
        (i) in the public domain through no fault of the receiving Party, 
        (ii) rightfully received from a third party without any obligation of confidentiality, 
        (iii) rightfully known to the receiving Party without any limitation on use or disclosure prior to 
        its receipt from the disclosing Party, 
        (iv) independently developed by the receiving Party, 
        (v) generally made available to third parties without any restriction on disclosure, 
        (vi) communicated in response to a valid order by a court or other governmental body, as otherwise 
        required by law, or as necessary to establish the rights of either Party under this Agreement, or.""",
        f"""c) Obligations under this clause to the extent provided shall continue to apply even after the 
        termination or expiry of this Agreement. In case of any breach of this provision by either party, 
        POSP undertakes to indemnify for losses caused due to such breach. 
 
        15. INDEMNITY: 
        
        POSP agrees to indemnify and keep indemnified and hold harmless at all times the Company and its 
        directors and officers from and against any and all losses, claims, actions, proceedings, damages 
        (including reasonable legal and lawyer's fees) which may be incurred by the Company on account 
        of (a) negligence or misconduct on the part of the POSP (b) due to breach any terms and conditions 
        of this Agreement (c) for breach of any intellectual property rights of the Company, or of any third
        
        party which commences an action or makes a claim against the Company and such breach is 
        attributable to the acts of omission/commission by POSP (d) any loss caused to the Company due to
        breach of Confidentiality by the POSP, (e) violation or breach of the IRDAI Regulations.

        16. LAW AND ARBITRATION:

        a) The provisions of this Agreement shall be governed by, and construed in accordance with Indian law.
        
        b) Any dispute, controversy or claims arising out of or relating to this Agreement or the breach, 
        termination or invalidity thereof, shall be settled by arbitration in accordance with the provisions 
        of the Arbitration and Conciliation Act, 1996. Following provisions shall be adhered to for any 
        such arbitral proceedings: 
        
        (i) The arbitral tribunal shall be composed of a sole arbitrator mutually appointed by the Parties. In 
        the event of non-agreement each of the Parties shall individually appoint an arbitrator and there two 
        arbitrators shall thereafter jointly appoint a third arbitrator which three arbitrators shall jointly 
        conduct arbitration proceedings. 
        
        (ii) The place of arbitration shall be Delhi and any award whether interim or final, shall be made, and 
        shall be deemed for all purposes between the Parties to be made, in Delhi. 
        
        (m)  The arbitral procedure shall be conducted in the English language and any award or awards shall""",
        f"""be rendered in English. The procedural law of the arbitration shall be Indian law. 
        
        (N) The rights and obligations of the Parties under, or pursuant to, this Clause, including the 
        arbitration Agreement in this Clause, shall be governed by and be subject to Indian law. 
        
        7. MISCELLANEOUS 
        
        (A) Amendments; No Waivers 
            (i) Any provision of this Agreement may be amended or waived if, and only if such amendment or 
        waiver is in writing and signed, in the case of an amendment by each Party or in the case of a waiver,
        by the Party against whom the waiver is to be effective.
        
        (ii) No failure or delay by any Party in exercising any right, power or privilege hereunder shall operate 
        as a waiver thereof nor shall any single or partial exercise of any other right, power or privilege. 
        The rights and remedies herein provided shall be cumulative and not exclusive of any rights or 
        remedies provided by law.

        C)  Entire Agreement; No Third-Party Rights

        This Agreement constitutes the entire Agreement between the Parties with respect to the subject 
        matter hereof. No representations, inducements, promises, understandings, conditions, indemnities 
        or warranties not set forth herein have been made or relied upon by any Party hereto.
        
        Neither this Agreement nor any provision hereof is intended to confer upon any person other than 
        the Parties to this Agreement any rights or remedies hereunder.
        
        D)  Further Assurances

        In connection with this Agreement, as well as all transactions contemplated by this Agreement, 
        POSP agrees to execute and deliver such additional documents and to perform such additional 
        actions as may be necessary, appropriate or reasonably requested to carry out or evidence the 
        transactions contemplated hereby.""",
        f"""
        E)  Severability

        The invalidity or unenforceability of any prov1s10ns of this Agreement in any jurisdiction shall 
        not affect the validity, legality or enforceability of the remainder of this Agreement in such 
        jurisdiction or the validity, legality or enforceability of this Agreement, including any such 
        provision, in any other jurisdiction, it being intended that all rights and obligations of the Parties 
        hereunder shall be enforceable to the fullest extent permitted by law.
        
        F)  Captions

        The captions herein are included for convenience of reference only and shall be ignored in the 
        construction or interpretation hereof.
        
        G)  Counterparts
        This Agreement may be executed simultaneously in duplicate each of which will be deemed an 
        original, but all of which will constitute one and the same instrument.

        H)  COMPLIANCE WITH LAWS
        
            Each Party represents that it shall abide by and observe all applicable laws, rules, regulations.
""",
        f"""    I)  Communication & Notices

        Any notice or other communication given pursuant to this Agreement must be m writing and (a) 
        delivered personally, (b) sent by facsimile or other similar facsimile transmission, (c) or sent by 
        registered mail, postage prepaid, as follows:
        If to the POSP:



        If to the Broker (Company):


        Crest Insurance Brokers Private Limited,
        Plot - 65, First Floor, Landmark House, Sector - 44, Gurugram, HR 122003
        

        IN WITNESS WHEREOF the Parties have caused these present to be executed on the day and 
        year first hereinabove written:

        Signed and Delivered by the within
        named Crest Insurance Brokers Private Limited by the hands of its Authorized Signatory
        
        Log and sign

        Signed and Delivered by {full_name}, by the hands of POSP Mr./Ms./Mrs.,""",

        
        f"""

        ANNEXURE-1 
        
        IRDAI APPROVED INSURANCE PRODUCTS FOR SOLICITING AND MARKETING BY POSPs

         Description of the Product 
        1 Motor Comprehensive Insurance Package Policy for Two-wheeler 
        2 Motor Comprehensive Insurance Package Policy for Private Car 
        3 Motor Comprehensive Insurance Package Policy for Commercial Vehicle 
        4 Third party liability (Act only) Policy for Two-wheeler 
        5 Third party liability (Act only) Policy for private car. 
        6 Third party liability (Act only) Policy for commercial vehicles. 
        7 Personal Accident Policy 
        8 Travel Insurance Policy 
        9 Home Insurance Policy 
        10 Cattle /Live stock 
        11 Agricultural Pump set Insurance 
        12 Fire & Allied Peril Dwelling Insurance 
        13 (PMFBY), Crop insurance (Government insurance schemes such as Pradhan Mantri Fasal 
        Bima Yojana (PMFBY), without any limit on Sum Insured). 
        14 (WBCIS) Weather Based Crop Insurance Scheme (WBCIS) without any limit on Sum 
        Insured). 
        15 Coconut Palm Insurance Scheme (CPIS) without any limit on Sum Insured). 
        16 Government insurance schemes such as Pradhan Mantri Jeevan Suraksha Bima Yojana 
        (PMJSBY) without any limit on Sum Insured. 
        17 Modification to Guidelines on Point of Sales (POS) - Life Insurance Products 
            1 Sum Assured on Death: Maximum - No Limit 
            (subject to Non - Medical underwriting only) 
            2 "Pure Term Insurance Product with or without return of Premium" wherein the 
            maximum Limit of Sum Assured under the Pure Term Product was capped up to Rs 25 
            Lakhs (excluding ADB Rider) Only""",
        
        f"""18 POS -- Health Insurance product (Fixed Benefit only) 
                    Sum Assured Minimum -As proposed under the product 
                    Maximum - Rs. 15 Lakhs (Individual) - Rs. 20 Lakhs (Floater and Individual) 
                    (Sum Assured would be in the multiples of Rs 5000 only)

        19 Any other product/product category, as and when permitted/approved by the Authority in 
        respect of Life, Non-Life & Health 

        Note: POSPs are only permitted to solicit the products which are allowed and applicable as 
        per the POSP Certification by the Company. The above list of products is dynamic and will
        superseded by any new list published by IRDAI. 
        
        Please refer to the IRDAI website www.irdai.gov.in for latest POSP products.""",]


        annexure_text = f"""
        Annexure II
        Payment

        1. The POSP shall be paid or contract to be paid by way of payment (including royalty administration
        charges or travel charges or reasonable reimbursement of expenses incurred by POSP in
        performance of his duties/functions/obligations or in any other form), an amount not exceeding the
        limits (of remuneration and are reward per case and/or transaction and/or per month basis) as
        specified/notified by the Authority in the circulars/regulations/Company policies issued in this
        behalf and as amended from time to time.

        2. The settlement of accounts by– in respect of remuneration of POSP shall be done on a monthly basis
        and it must be ensured that there is no cross settlement of outstanding balances.

        3. That none of the payments made by the Company to the POSP constitute any legal relationship of
        employee and employer in the usual and general form of contract of employment and thereby POSP
        shall not be entitled to claim any dues such as: PF, Contribution towards medical benefits (including
        ESI Contribution/membership) leave encashment, ESOPs and dues or payments under any provisions
        of the applicable labour laws, etc.

        DECLARATION & ACCEPTANCE

        I, {full_name}, hereby accept and agree to all terms and conditions of this Agreement voluntarily.
        
        """



    # -------- RENDER ALL PAGES --------
    total_pages = len(agreement_pages)

    for page_no, page_text in enumerate(agreement_pages, start=1):

        draw_header(c, width, height, logo_path, primary)

        y = height - 220
        c.setFont("Helvetica", 10)
        c.setFillColor(text)

        for line in page_text.split("\n"):
            if y < 80:
                c.showPage()
                draw_header(c, width, height, logo_path, primary)
                y = height - 220
                c.setFont("Helvetica", 11)

            c.drawString(60, y, line.strip())
            y -= 16

        # Footer
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, 40, f"Page {page_no} of {total_pages}")

        c.showPage()
        


    # -------- SIGNATURE PAGE (LAST PAGE) --------
    textobject = c.beginText(60, height - 80)
    textobject.setFont("Helvetica", 9)

    for line in annexure_text.split("\n"):
        textobject.textLine(line)

    c.drawText(textobject)

    final_y = textobject.getY()   # 👈 THIS decides placement

    c.save()
    return send_file(
        file_path,
        as_attachment=True,
        download_name=f"Marketing agreement {user['agent_code']}.pdf"
    )





# ---------------- CERTIFICATE ----------------






@app.route("/certificate")
def certificate():
    if "user" not in session:
        return redirect(url_for("login"))

    conn, cursor = get_db()
    cursor.execute("SELECT * FROM users WHERE email=%s", (session["user"],))
    user = cursor.fetchone()
    conn.close()

    if not user or user["status"] != "Verified":
        return "Certificate not available. Profile not verified."

    # ---------- PATHS ----------
    cert_dir = os.path.join(app.root_path, "static", "certificates")
    os.makedirs(cert_dir, exist_ok=True)

    file_path = os.path.join(cert_dir, f"certificate_{user['pan']}.pdf")

    logo_path = os.path.join(app.root_path, "static", "assets", "crest_logo.png")
    sign_path = os.path.join(app.root_path, "static", "assets", "signature.png")
    seal_path = os.path.join(app.root_path, "static", "assets", "seal.png")
    # ---------- PDF ----------
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    # COLORS
    primary = HexColor("#1f3c88")
    accent = HexColor("#c9a227")
    text = HexColor("#333333")

    # ---------- BORDER ----------
    c.setStrokeColor(primary)
    c.setLineWidth(3)
    c.rect(25, 25, width - 50, height - 50)

    # ---------- HEADER BAND ----------
    c.setFillColor(primary)
    c.rect(25, height - 130, width - 50, 105, stroke=0, fill=1)

    # LOGO
    if os.path.exists(logo_path):
        c.drawImage(
            ImageReader(logo_path),
            x=40,                # left margin
            y=height - 105,      # keep same vertical position
            width=60,
            height=65,
            mask="auto"
        )

    # COMPANY TEXT
    c.setFillColor("white")
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 65, "Crest Insurance Brokers Pvt. Ltd.")

    c.setFont("Helvetica", 9)
    c.drawCentredString(
        width / 2, height - 85,
        "Reg. Office: Unit–12, First Floor, Landmark House, Plot–65, Sector–44, Gurugram–122003"
    )
    c.drawCentredString(
        width / 2, height - 100,
        "CIN No-U66000HR2021PTC098960 | Reg.No.-IRDAI/BD/895/2025 | IBAI No.-13841"
    )
    c.drawCentredString(
        width / 2, height - 115,
        "License No: 841 | compliance@crestinsure.com"
    )
    # ---------- TITLE ----------
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 165, "CERTIFICATE OF COMPLETION")
    c.line(160, height - 172, width - 160, height - 172)

    # ---------- WATERMARK ----------
    c.saveState()
    c.setFont("Helvetica-Bold", 60)
    c.setFillColor(lightgrey)
    c.translate(width / 2, height / 2)
    c.rotate(30)
    c.drawCentredString(0, 0, "CREST INSURANCE")
    c.restoreState()

    # ---------- BODY ----------
    c.setFillColor(text)
    c.setFont("Helvetica", 11)
    y = height - 245

    c.drawCentredString(width / 2, y, "This is in reference to the application made by")
    y -= 30

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(primary)
    c.drawCentredString(
        width / 2, y,
        f"{user['first_name'].upper()} {user['last_name'].upper()}"
    )

    y -= 30
    c.setFillColor(text)
    c.setFont("Helvetica", 11)
    c.drawCentredString(
        width / 2, y,
        f"residing at {user['address']}, {user['state']} - {user['pincode']}"
    )

    y -= 40
    c.drawCentredString(
        width / 2, y,
        "has successfully completed the prescribed training and examination"
    )
    y -= 20
    c.drawCentredString(
        width / 2, y,
        "as per IRDAI POSP Guidelines."
    )

    # ---------- DETAILS BOX ----------
    y -= 55
    c.setFillColor(HexColor("#f5f7fb"))
    c.rect(120, y - 35, width - 240, 65, stroke=0, fill=1)

    c.setFillColor(text)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(150, y, f"POSP Code : {user['agent_code']}")
    c.drawString(width / 2 + 30, y, f"PAN No : {user['pan']}")

    # ---------- AUTHORIZATION ----------
    y -= 80
    c.setFont("Helvetica", 11)
    c.drawCentredString(
        width / 2, y,
        "This certificate authorizes the holder to act as a Point of Sales Person for"
    )
    y -= 20
    c.drawCentredString(
        width / 2, y,
        "Crest Insurance Brokers Pvt. Ltd. under POSP Regulations."
    )

    # ---------- FOOTER ----------
    y -= 65
    c.setFont("Helvetica", 10)
    c.drawString(80, y, f"Date of Issue: {datetime.now().strftime('%d %B %Y')}")

        # SIGNATURE IMAGE
        # Position constants
    sig_width = 100
    sig_height = 30
    seal_width = 100
    seal_height = 30

    # Vertical reference
    sig_y = y + 25  # y-coordinate for both images
    spacing = 20    # space between signature and seal if needed

    # Draw signature if exists
    if os.path.exists(sign_path):
        c.drawImage(
            ImageReader(sign_path),
            width - 200,   # x-coordinate for signature
            sig_y -20,
            width=sig_width,
            height=sig_height,
            mask="auto"
        )

    # Draw seal and text if exists
    if os.path.exists(seal_path):
        seal_x = width-200 + sig_height -10 # place seal to the right of signature
        seal_y = sig_y -50

        # Draw seal image
        c.drawImage(
            ImageReader(seal_path),
            seal_x,
            seal_y,
            width=seal_width,
            height=seal_height,
            mask="auto"
        )

        # Draw name over the seal (centered)
        c.setFont("Helvetica-Bold", 11)
        text_width = c.stringWidth("Sukhbir Singh Pundir", "Helvetica-Bold", 11)
        c.drawString(seal_x + (seal_width - text_width)/2, seal_y + seal_height/2 - 5, "Sukhbir Singh Pundir")

        # Draw designation below the seal
        c.setFont("Helvetica", 10)
        c.drawString(seal_x - 25, seal_y - 15, "Co-Founder & Principal Officer")
        c.drawString(seal_x -25, seal_y - 30, "Crest Insurance Brokers Pvt. Ltd.")


    c.save()

    # ---------- SEND ----------
    return send_file(
        file_path,
        as_attachment=True,
        download_name="Crest_POSP_Certificate.pdf"
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True)
