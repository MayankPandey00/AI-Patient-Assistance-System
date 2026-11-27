# import os
# import re
# import sqlite3
# from functools import wraps
# from flask import (
#     Blueprint, current_app, render_template, request,
#     redirect, url_for, session, flash, jsonify
# )
# from werkzeug.security import generate_password_hash, check_password_hash

# auth_bp = Blueprint("auth", __name__)


# def _get_db():
#     db_path = current_app.config.get("AUTH_DB_PATH", "medical_data_repository.db")
#     conn = sqlite3.connect(db_path)
#     conn.row_factory = sqlite3.Row
#     return conn


# def init_auth(app, db_path="medical_data_repository.db"):
#     """Initialize secret key, users table, and auth routes on your Flask app."""
#     if not app.secret_key:
#         app.secret_key = os.environ.get(
#             "FLASK_SECRET_KEY",
#             "replace-with-a-secure-random-key-in-env"
#         )
#     app.config["AUTH_DB_PATH"] = db_path

#     conn = sqlite3.connect(db_path)
#     conn.execute("""
#         CREATE TABLE IF NOT EXISTS users (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             full_name TEXT NOT NULL,
#             email TEXT UNIQUE,
#             phone TEXT UNIQUE,
#             password_hash TEXT NOT NULL,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             CHECK (email IS NOT NULL OR phone IS NOT NULL)
#         )
#     """)
#     conn.commit()
#     conn.close()

#     app.register_blueprint(auth_bp)


# def _normalize_email(email: str) -> str:
#     return email.strip().lower()


# def _normalize_phone(phone: str) -> str:
#     return re.sub(r"[^\d+]", "", phone.strip())


# def _is_valid_email(value: str) -> bool:
#     return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))


# def _is_valid_phone(value: str) -> bool:
#     digits = re.sub(r"\D", "", value)
#     return 10 <= len(digits) <= 15


# def _wants_json() -> bool:
#     return (
#         request.is_json
#         or request.headers.get("X-Requested-With") == "XMLHttpRequest"
#         or request.path.startswith("/api/")
#         or request.accept_mimetypes.best == "application/json"
#     )


# def translator_access_required(f):
#     """Allows BOTH logged-in users AND guests (for '/' and Translator endpoints only)."""
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         if not session.get("user_id") and not session.get("is_guest"):
#             if _wants_json():
#                 return jsonify({"error": "Authentication required.", "requires_login": True}), 401
#             return redirect(url_for("auth.login"))
#         return f(*args, **kwargs)
#     return decorated


# def full_login_required(f):
#     """Allows ONLY logged-in Email/Phone users. Blocks Guest users."""
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         if not session.get("user_id") or session.get("is_guest"):
#             if _wants_json() or request.method != "GET":
#                 return jsonify({
#                     "error": "Guest mode is limited to the Translator. Please sign in to use this feature.",
#                     "requires_login": True
#                 }), 403
#             flash("Please sign in with Email or Phone to access that feature.", "error")
#             return redirect(url_for("auth.login"))
#         return f(*args, **kwargs)
#     return decorated


# @auth_bp.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         identifier = request.form.get("identifier", "").strip()
#         password = request.form.get("password", "")

#         if not identifier or not password:
#             flash("Please enter your email/phone and password.", "error")
#             return render_template("login.html", active_tab="login")

#         conn = _get_db()
#         if "@" in identifier:
#             user = conn.execute(
#                 "SELECT * FROM users WHERE email = ?",
#                 (_normalize_email(identifier),)
#             ).fetchone()
#         else:
#             user = conn.execute(
#                 "SELECT * FROM users WHERE phone = ?",
#                 (_normalize_phone(identifier),)
#             ).fetchone()
#         conn.close()

#         if user and check_password_hash(user["password_hash"], password):
#             session.clear()
#             session["user_id"] = user["id"]
#             session["user_name"] = user["full_name"]
#             session["is_guest"] = False
#             return redirect(url_for("index"))

#         flash("Invalid email/phone number or password.", "error")
#         return render_template("login.html", active_tab="login")

#     return render_template("login.html", active_tab="login")


# @auth_bp.route("/register", methods=["POST"])
# def register():
#     full_name = request.form.get("full_name", "").strip()
#     reg_method = request.form.get("reg_method", "email")
#     email_raw = request.form.get("email", "").strip()
#     phone_raw = request.form.get("phone", "").strip()
#     password = request.form.get("password", "")

#     if not full_name or len(password) < 6:
#         flash("Full name is required and password must be at least 6 characters.", "error")
#         return render_template("login.html", active_tab="register")

#     email = None
#     phone = None

#     if reg_method == "email":
#         email = _normalize_email(email_raw)
#         if not _is_valid_email(email):
#             flash("Please enter a valid email address.", "error")
#             return render_template("login.html", active_tab="register")
#     else:
#         phone = _normalize_phone(phone_raw)
#         if not _is_valid_phone(phone):
#             flash("Please enter a valid phone number (10 to 15 digits).", "error")
#             return render_template("login.html", active_tab="register")

#     conn = _get_db()
#     try:
#         cursor = conn.execute(
#             "INSERT INTO users (full_name, email, phone, password_hash) VALUES (?, ?, ?, ?)",
#             (full_name, email, phone, generate_password_hash(password))
#         )
#         conn.commit()
#         new_user_id = cursor.lastrowid
#     except sqlite3.IntegrityError:
#         conn.close()
#         flash("An account with that email or phone number already exists.", "error")
#         return render_template("login.html", active_tab="register")
#     conn.close()

#     session.clear()
#     session["user_id"] = new_user_id
#     session["user_name"] = full_name
#     session["is_guest"] = False
#     return redirect(url_for("index"))


# @auth_bp.route("/guest-login", methods=["POST"])
# def guest_login():
#     session.clear()
#     session["user_id"] = None
#     session["user_name"] = "Guest"
#     session["is_guest"] = True
#     return redirect(url_for("index"))


# @auth_bp.route("/logout")
# def logout():
#     session.clear()
#     return redirect(url_for("auth.login"))


import os
import re
import sqlite3
from functools import wraps
from flask import (
    Blueprint, current_app, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint("auth", __name__)


@auth_bp.app_context_processor
def inject_auth_context():
    """Makes is_guest and user_name available in all templates automatically."""
    return {
        "is_guest": session.get("is_guest", False),
        "user_name": session.get("user_name", "Guest"),
    }


def _get_db():
    db_path = current_app.config.get("AUTH_DB_PATH", "medical_data_repository.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth(app, db_path="medical_data_repository.db"):
    """Initialize secret key, users table, and auth routes on your Flask app."""
    if not app.secret_key:
        app.secret_key = os.environ.get(
            "FLASK_SECRET_KEY",
            "replace-with-a-secure-random-key-in-env"
        )
    app.config["AUTH_DB_PATH"] = db_path

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (email IS NOT NULL OR phone IS NOT NULL)
        )
    """)
    conn.commit()
    conn.close()

    app.register_blueprint(auth_bp)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_phone(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone.strip())


def _is_valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))


def _is_valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _parse_identifier(raw_identifier: str):
    """Returns (id_type, normalized_value) or (None, None) if invalid."""
    raw = raw_identifier.strip()
    if "@" in raw:
        email = _normalize_email(raw)
        if _is_valid_email(email):
            return "email", email
        return None, None
    phone = _normalize_phone(raw)
    if _is_valid_phone(phone):
        return "phone", phone
    return None, None


def _find_user(id_type: str, value: str):
    conn = _get_db()
    if id_type == "email":
        user = conn.execute("SELECT * FROM users WHERE email = ?", (value,)).fetchone()
    else:
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (value,)).fetchone()
    conn.close()
    return user


def _wants_json() -> bool:
    return (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
    )


def translator_access_required(f):
    """Allows BOTH logged-in users AND guests (for '/' and Translator endpoints only)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") and not session.get("is_guest"):
            if _wants_json():
                return jsonify({"error": "Authentication required.", "requires_login": True}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def full_login_required(f):
    """Allows ONLY logged-in Email/Phone users. Blocks Guest users."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") or session.get("is_guest"):
            if _wants_json() or request.method != "GET":
                return jsonify({
                    "error": "Guest mode is limited to the Translator. Please sign in to use this feature.",
                    "requires_login": True
                }), 403
            flash("Please sign in with Email or Phone to access that feature.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", step="check")

    step = request.form.get("step", "check")
    raw_identifier = request.form.get("identifier", "").strip()
    id_type, normalized = _parse_identifier(raw_identifier)

    if not id_type or not normalized:
        flash("Please enter a valid Email ID or Phone Number (10-15 digits).", "error")
        return render_template("login.html", step="check", identifier=raw_identifier)

    # -----------------------------------------------------
    # STEP 1: Check if this Email/Phone is new or returning
    # -----------------------------------------------------
    if step == "check":
        user = _find_user(id_type, normalized)
        if user:
            # Returning user -> ask for existing password
            return render_template(
                "login.html",
                step="enter_password",
                identifier=normalized,
                existing_name=user["full_name"]
            )
        else:
            # First-time user -> ask to create a password
            return render_template(
                "login.html",
                step="create_password",
                identifier=normalized
            )

    # -----------------------------------------------------
    # STEP 2A: First-time user creates their password
    # -----------------------------------------------------
    if step == "create_password":
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name:
            flash("Please enter your full name.", "error")
            return render_template("login.html", step="create_password", identifier=normalized)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template(
                "login.html",
                step="create_password",
                identifier=normalized,
                full_name=full_name
            )

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return render_template(
                "login.html",
                step="create_password",
                identifier=normalized,
                full_name=full_name
            )

        email = normalized if id_type == "email" else None
        phone = normalized if id_type == "phone" else None

        conn = _get_db()
        try:
            cursor = conn.execute(
                "INSERT INTO users (full_name, email, phone, password_hash) VALUES (?, ?, ?, ?)",
                (full_name, email, phone, generate_password_hash(password))
            )
            conn.commit()
            new_user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.close()
            flash("This account already exists. Please enter your password to sign in.", "error")
            return render_template("login.html", step="enter_password", identifier=normalized)
        conn.close()

        session.clear()
        session["user_id"] = new_user_id
        session["user_name"] = full_name
        session["is_guest"] = False
        return redirect(url_for("index"))

    # -----------------------------------------------------
    # STEP 2B: Returning user logs in with their password
    # -----------------------------------------------------
    if step == "enter_password":
        password = request.form.get("password", "")
        user = _find_user(id_type, normalized)

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["is_guest"] = False
            return redirect(url_for("index"))

        flash("Incorrect password. Please try again.", "error")
        return render_template(
            "login.html",
            step="enter_password",
            identifier=normalized,
            existing_name=user["full_name"] if user else ""
        )

    return render_template("login.html", step="check")


@auth_bp.route("/guest-login", methods=["POST"])
def guest_login():
    session.clear()
    session["user_id"] = None
    session["user_name"] = "Guest"
    session["is_guest"] = True
    return redirect(url_for("index"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))