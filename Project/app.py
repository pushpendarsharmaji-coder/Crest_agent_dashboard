from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secure_secret_key"  # Required for flash & session

# ---------- DB Connection ----------
def get_db():
    try:
        conn = mysql.connector.connect(
            host="database-1.cuh68eog8q9a.us-east-1.rds.amazonaws.com",
            user="admin",
            password="Ps5638806",
            database="agent_kyc_documents",  # Make sure this matches your RDS DB
            port=3306,
            autocommit=True
        )
        cursor = conn.cursor(dictionary=True)
        return conn, cursor
    except mysql.connector.Error as e:
        print("DB CONNECTION ERROR:", e)
        return None, None

# ---------- Home Route ----------
@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception as e:
        print("ERROR in / route:", e)
        return "Something went wrong.", 500

# ---------- Signup ----------
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
        if not conn:
            flash("Database connection failed", "error")
            return redirect(url_for("signup"))

        try:
            # Check duplicates
            cursor.execute("""
                SELECT email, mobile, pan 
                FROM users 
                WHERE email=%s OR mobile=%s OR pan=%s
            """, (email, mobile, pan))
            if cursor.fetchone():
                flash("Email, Mobile, or PAN already registered", "error")
                return redirect(url_for("signup"))

            # Generate password
            password = "TempPass123!"  # Or use your generate_password()
            password_hash = generate_password_hash(password)

            cursor.execute("""
                INSERT INTO users (email, mobile, pan, password_hash)
                VALUES (%s, %s, %s, %s)
            """, (email, mobile, pan, password_hash))
            conn.commit()

            # Optionally send email (wrap in try/except)
            try:
                # send_password_email(email, password, pan)
                pass
            except Exception as e:
                print("EMAIL ERROR:", e)

            session["user"] = email
            flash("Signup successful! Password sent to your email.", "success")
            return redirect(url_for("index"))

        except IntegrityError as e:
            conn.rollback()
            print("DB IntegrityError:", e)
            flash("PAN already registered. Please login.", "error")
            return redirect(url_for("login"))

        except Exception as e:
            print("Signup ERROR:", e)
            flash("Something went wrong during signup.", "error")
            return redirect(url_for("signup"))

        finally:
            conn.close()

    return render_template("signup.html")

# ---------- Login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Email and password are required", "error")
            return redirect(url_for("login"))

        conn, cursor = get_db()
        if not conn:
            flash("Database connection failed", "error")
            return redirect(url_for("login"))

        try:
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()

            if not user:
                flash("User not found", "error")
                return redirect(url_for("login"))

            if not check_password_hash(user["password_hash"], password):
                flash("Incorrect password", "error")
                return redirect(url_for("login"))

            session["user"] = email
            flash("Login successful", "success")
            return redirect(url_for("index"))

        except Exception as e:
            print("Login ERROR:", e)
            flash("Something went wrong during login.", "error")
            return redirect(url_for("login"))

        finally:
            conn.close()

    return render_template("login.html")

# ---------- Logout ----------
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))

# ---------- Run ----------
if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0", port=5000)
