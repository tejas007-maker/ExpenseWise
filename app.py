from dotenv import load_dotenv
load_dotenv()
import os
import re
import sqlite3
from datetime import date, datetime
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
from PIL import Image, UnidentifiedImageError

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)
from sqlalchemy import inspect, text

from ml_model import predict_category


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

secret_key = os.environ.get("SECRET_KEY")

if not secret_key:
    if os.environ.get("RENDER") == "true":
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production."
        )
    secret_key = "expensewise-local-development-key-change-me"

app.config["SECRET_KEY"] = secret_key

is_production = os.environ.get("RENDER") == "true"

# Maximum upload/request size: 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

app.config["WTF_CSRF_TIME_LIMIT"] = 3600

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = is_production
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = is_production
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 60 * 60 * 24 * 30


# =========================================================
# CSRF PROTECTION
# =========================================================

csrf = CSRFProtect(app)


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": generate_csrf}


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///expensewise.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}


# =========================================================
# CLOUDINARY CONFIGURATION
# =========================================================

cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
cloud_api_key = os.environ.get("CLOUDINARY_API_KEY")
cloud_api_secret = os.environ.get("CLOUDINARY_API_SECRET")

if cloud_name and cloud_api_key and cloud_api_secret:
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=cloud_api_key,
        api_secret=cloud_api_secret,
        secure=True,
    )


# =========================================================
# DATABASE AND LOGIN MANAGER
# =========================================================

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please login to continue."
login_manager.login_message_category = "error"


# =========================================================
# USER MODEL
# =========================================================

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(
        db.String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(db.String(255), nullable=False)

    # Profile information
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(30), nullable=True)
    phone = db.Column(db.String(25), nullable=True)
    occupation = db.Column(db.String(100), nullable=True)
    organization = db.Column(db.String(150), nullable=True)
    bio = db.Column(db.String(500), nullable=True)

    # Cloudinary profile photo
    profile_photo = db.Column(db.String(500), nullable=True)
    profile_photo_public_id = db.Column(db.String(255), nullable=True)

    # Preferences
    currency = db.Column(
        db.String(10),
        nullable=False,
        default="INR",
    )

    email_notifications = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    expenses = db.relationship(
        "Expense",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    budget = db.relationship(
        "Budget",
        backref="owner",
        uselist=False,
        lazy=True,
        cascade="all, delete-orphan",
    )


# =========================================================
# EXPENSE MODEL
# =========================================================

class Expense(db.Model):
    __tablename__ = "expense"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(50), nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )


# =========================================================
# BUDGET MODEL
# =========================================================

class Budget(db.Model):
    __tablename__ = "budget"

    id = db.Column(db.Integer, primary_key=True)

    amount = db.Column(
        db.Float,
        nullable=False,
        default=10000,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        unique=True,
        index=True,
    )


# =========================================================
# BUDGET NOTIFICATION TABLE
# =========================================================

budget_notification = db.Table(
    "budget_notification",
    db.metadata,

    db.Column(
        "id",
        db.Integer,
        primary_key=True,
    ),

    db.Column(
        "user_id",
        db.Integer,
        nullable=False,
        index=True,
    ),

    db.Column(
        "month",
        db.String(7),
        nullable=False,
    ),

    db.Column(
        "notification_type",
        db.String(30),
        nullable=False,
    ),

    db.Column(
        "created_at",
        db.DateTime,
        default=datetime.utcnow,
    ),

    db.UniqueConstraint(
        "user_id",
        "month",
        "notification_type",
        name="unique_budget_notification",
    ),
)


# =========================================================
# DATABASE MIGRATION
# =========================================================

def prepare_database():
    db.create_all()

    # Add profile columns to existing user tables.
    # Existing records and tables are not intentionally dropped.
    user_columns_to_add = {
        "date_of_birth": "DATE",
        "gender": "VARCHAR(30)",
        "phone": "VARCHAR(25)",
        "occupation": "VARCHAR(100)",
        "organization": "VARCHAR(150)",
        "bio": "VARCHAR(500)",
        "profile_photo": "VARCHAR(500)",
        "profile_photo_public_id": "VARCHAR(255)",
        "currency": "VARCHAR(10) NOT NULL DEFAULT 'INR'",
        "email_notifications": "BOOLEAN NOT NULL DEFAULT TRUE",
        "created_at": "TIMESTAMP",
    }

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    if "user" in existing_tables:
        existing_columns = {
            column["name"]
            for column in inspector.get_columns("user")
        }

        with db.engine.begin() as connection:
            for column_name, column_type in user_columns_to_add.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(
                            f'ALTER TABLE "user" '
                            f'ADD COLUMN "{column_name}" {column_type}'
                        )
                    )

            # Historical creation dates cannot be recovered if never stored.
            connection.execute(
                text(
                    'UPDATE "user" '
                    'SET created_at = CURRENT_TIMESTAMP '
                    'WHERE created_at IS NULL'
                )
            )

    # Legacy SQLite ownership-column migration.
    if db.engine.dialect.name == "sqlite":
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        with db.engine.begin() as connection:
            if "expense" in existing_tables:
                columns = {
                    column["name"]
                    for column in inspect(db.engine).get_columns("expense")
                }

                if "user_id" not in columns:
                    connection.execute(
                        text(
                            "ALTER TABLE expense "
                            "ADD COLUMN user_id INTEGER"
                        )
                    )

            if "budget" in existing_tables:
                columns = {
                    column["name"]
                    for column in inspect(db.engine).get_columns("budget")
                }

                if "user_id" not in columns:
                    connection.execute(
                        text(
                            "ALTER TABLE budget "
                            "ADD COLUMN user_id INTEGER"
                        )
                    )


with app.app_context():
    prepare_database()


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://res.cloudinary.com; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# =========================================================
# GENERAL HELPERS
# =========================================================

def get_budget():
    if not current_user.is_authenticated:
        return 10000.0

    budget_record = Budget.query.filter_by(
        user_id=current_user.id
    ).first()

    if budget_record is None:
        budget_record = Budget(
            amount=10000,
            user_id=current_user.id,
        )
        db.session.add(budget_record)
        db.session.commit()

    return float(budget_record.amount)


def get_user_expenses():
    return Expense.query.filter_by(
        user_id=current_user.id
    ).order_by(Expense.id.desc()).all()


def validate_name(name):
    return bool(name and 2 <= len(name) <= 100)


def validate_email(email):
    if not email or len(email) > 150:
        return False

    return re.match(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        email,
    ) is not None


def validate_password(password):
    if not password or len(password) < 8 or len(password) > 128:
        return False

    has_letter = any(character.isalpha() for character in password)
    has_number = any(character.isdigit() for character in password)

    return has_letter and has_number


def validate_expense_description(description):
    return bool(description and len(description) <= 200)


def validate_amount(amount):
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None

    if value <= 0 or value > 100000000:
        return None

    return round(value, 2)


def validate_date(date_value):
    if not date_value:
        return False

    try:
        datetime.strptime(date_value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def safe_next_url(target):
    if not target:
        return None

    parsed = urlparse(target)

    if parsed.scheme or parsed.netloc:
        return None

    if not target.startswith("/") or target.startswith("//"):
        return None

    return target


# =========================================================
# LOGIN THROTTLING
# =========================================================

_login_attempts = {}


def login_throttled(ip_address):
    now = datetime.utcnow().timestamp()
    data = _login_attempts.get(ip_address)

    if not data:
        return False

    attempts, first_time, blocked_until = data

    if blocked_until and now < blocked_until:
        return True

    if now - first_time > 900:
        _login_attempts.pop(ip_address, None)
        return False

    return False


def register_login_failure(ip_address):
    now = datetime.utcnow().timestamp()
    data = _login_attempts.get(ip_address)

    if data:
        attempts, first_time, blocked_until = data
    else:
        attempts, first_time, blocked_until = 0, now, 0

    if now - first_time > 900:
        attempts, first_time, blocked_until = 0, now, 0

    attempts += 1

    if attempts >= 8:
        blocked_until = now + 900

    _login_attempts[ip_address] = (
        attempts,
        first_time,
        blocked_until,
    )


def clear_login_failures(ip_address):
    _login_attempts.pop(ip_address, None)


# =========================================================
# CLOUDINARY PROFILE PHOTO HELPERS
# =========================================================

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def upload_profile_photo(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Please select a profile photo.")

    if not (cloud_name and cloud_api_key and cloud_api_secret):
        raise RuntimeError(
            "Cloudinary is not configured. Check your environment variables."
        )

    extension = os.path.splitext(file_storage.filename)[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Use JPG, JPEG, PNG, or WEBP images only.")

    try:
        file_storage.stream.seek(0)
        image = Image.open(file_storage.stream)
        image.verify()

        file_storage.stream.seek(0)
        image = Image.open(file_storage.stream)
        width, height = image.size

        if not width or not height or width > 10000 or height > 10000:
            raise ValueError("Image dimensions are not supported.")

    except (UnidentifiedImageError, OSError):
        raise ValueError("The selected file is not a valid image.")

    finally:
        file_storage.stream.seek(0)

    result = cloudinary.uploader.upload(
        file_storage,
        folder="expensewise/profiles",
        resource_type="image",
        allowed_formats=["jpg", "jpeg", "png", "webp"],
        transformation=[
            {
                "width": 500,
                "height": 500,
                "crop": "fill",
                "gravity": "face",
            }
        ],
    )

    return result["secure_url"], result["public_id"]


def delete_cloudinary_photo(public_id):
    if not public_id:
        return

    if not (cloud_name and cloud_api_key and cloud_api_secret):
        app.logger.warning("Cloudinary not configured; photo was not deleted.")
        return

    if not public_id.startswith("expensewise/profiles/"):
        app.logger.warning("Unexpected Cloudinary public ID; deletion skipped.")
        return

    cloudinary.uploader.destroy(
        public_id,
        resource_type="image",
        invalidate=True,
    )


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(400)
def bad_request(error):
    return render_template(
        "error.html",
        code=400,
        title="Bad Request",
        message="The request could not be processed.",
    ), 400


@app.errorhandler(403)
def forbidden(error):
    return render_template(
        "error.html",
        code=403,
        title="Access Denied",
        message="You do not have permission to access this resource.",
    ), 403


@app.errorhandler(404)
def not_found(error):
    return render_template(
        "error.html",
        code=404,
        title="Page Not Found",
        message="The page you requested does not exist.",
    ), 404


@app.errorhandler(413)
def request_too_large(error):
    return render_template(
        "error.html",
        code=413,
        title="Request Too Large",
        message="The request exceeds the 5 MB upload limit.",
    ), 413


@app.errorhandler(500)
def server_error(error):
    db.session.rollback()

    return render_template(
        "error.html",
        code=500,
        title="Something Went Wrong",
        message="An unexpected error occurred. Please try again.",
    ), 500


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not validate_name(name):
            flash("Name must be between 2 and 100 characters.", "error")
            return render_template("register.html")

        if not validate_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")

        if not validate_password(password):
            flash(
                "Password must be at least 8 characters and contain "
                "at least one letter and one number.",
                "error",
            )
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return render_template("register.html")

        try:
            new_user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                created_at=datetime.utcnow(),
            )

            db.session.add(new_user)
            db.session.flush()

            db.session.add(
                Budget(
                    amount=10000,
                    user_id=new_user.id,
                )
            )

            db.session.commit()

            try:
                from notify_budget import send_welcome_email
                send_welcome_email(new_user)
            except Exception:
                app.logger.exception("Welcome email failed")

            flash(
                "Account created successfully! Please login.",
                "success",
            )
            return redirect(url_for("login"))

        except Exception:
            db.session.rollback()
            app.logger.exception("Registration failed")
            flash("Could not create the account. Please try again.", "error")

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "GET":
        return render_template(
            "login.html",
            next=safe_next_url(request.args.get("next")),
        )

    ip_address = request.remote_addr or "unknown"

    if login_throttled(ip_address):
        flash(
            "Too many failed login attempts. "
            "Please wait 15 minutes and try again.",
            "error",
        )
        return render_template("login.html"), 429

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    remember = request.form.get("remember") in ("1", "on")
    next_url = safe_next_url(request.form.get("next"))

    user = User.query.filter_by(email=email).first()

    if user is None or not check_password_hash(user.password_hash, password):
        register_login_failure(ip_address)
        flash("Invalid email or password.", "error")
        return render_template("login.html")

    clear_login_failures(ip_address)

    login_user(user, remember=remember, fresh=True)

    flash(f"Welcome back, {user.name}!", "success")

    return redirect(next_url or url_for("home"))


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))


# =========================================================
# LANDING PAGE
# =========================================================

@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return render_template("landing.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def home():
    expenses = get_user_expenses()

    total_spent = sum(
        float(expense.amount)
        for expense in expenses
    )

    monthly_budget = get_budget()
    remaining_budget = monthly_budget - total_spent

    budget_percentage = (
        total_spent / monthly_budget * 100
        if monthly_budget > 0
        else 0
    )

    if budget_percentage >= 100:
        budget_status = "Over Budget"
    elif budget_percentage >= 80:
        budget_status = "Near Limit"
    else:
        budget_status = "Within Budget"

    return render_template(
        "index.html",
        expenses=expenses,
        total_spent=total_spent,
        monthly_budget=monthly_budget,
        remaining_budget=remaining_budget,
        budget_percentage=budget_percentage,
        budget_status=budget_status,
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        gender = request.form.get("gender", "").strip()
        occupation = request.form.get("occupation", "").strip()
        organization = request.form.get("organization", "").strip()
        bio = request.form.get("bio", "").strip()
        dob_raw = request.form.get("date_of_birth", "").strip()
        currency = request.form.get("currency", "INR").strip().upper()
        email_notifications = (
            request.form.get("email_notifications") == "on"
        )

        if not validate_name(name):
            flash("Name must be between 2 and 100 characters.", "error")
            return render_template("profile.html")

        if not validate_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("profile.html")

        if len(phone) > 25:
            flash("Phone number must be 25 characters or fewer.", "error")
            return render_template("profile.html")

        if len(occupation) > 100 or len(organization) > 150:
            flash("Occupation or organization is too long.", "error")
            return render_template("profile.html")

        if len(bio) > 500:
            flash("Bio must be 500 characters or fewer.", "error")
            return render_template("profile.html")

        valid_genders = {
            "",
            "Male",
            "Female",
            "Non-binary",
            "Prefer not to say",
            "Other",
        }

        if gender not in valid_genders:
            flash("Please select a valid gender option.", "error")
            return render_template("profile.html")

        valid_currencies = {
            "INR", "USD", "EUR", "GBP", "AED", "CAD", "AUD"
        }

        if currency not in valid_currencies:
            flash("Please select a supported currency.", "error")
            return render_template("profile.html")

        date_of_birth = None

        if dob_raw:
            try:
                date_of_birth = datetime.strptime(
                    dob_raw, "%Y-%m-%d"
                ).date()

                if date_of_birth > date.today():
                    flash("Date of birth cannot be in the future.", "error")
                    return render_template("profile.html")

            except ValueError:
                flash("Please enter a valid date of birth.", "error")
                return render_template("profile.html")

        duplicate_email = User.query.filter(
            User.email == email,
            User.id != current_user.id,
        ).first()

        if duplicate_email:
            flash("This email is already associated with another account.", "error")
            return render_template("profile.html")

        old_photo_public_id = current_user.profile_photo_public_id
        new_photo_url = None
        new_photo_public_id = None

        photo = request.files.get("profile_photo")

        if photo and photo.filename:
            try:
                new_photo_url, new_photo_public_id = upload_profile_photo(photo)
            except ValueError as error:
                flash(str(error), "error")
                return render_template("profile.html")
            except Exception:
                app.logger.exception("Profile photo upload failed")
                flash("Could not upload the profile photo.", "error")
                return render_template("profile.html")

        try:
            current_user.name = name
            current_user.email = email
            current_user.phone = phone or None
            current_user.gender = gender or None
            current_user.occupation = occupation or None
            current_user.organization = organization or None
            current_user.bio = bio or None
            current_user.date_of_birth = date_of_birth
            current_user.currency = currency
            current_user.email_notifications = email_notifications

            if new_photo_url and new_photo_public_id:
                current_user.profile_photo = new_photo_url
                current_user.profile_photo_public_id = new_photo_public_id

            db.session.commit()

        except Exception:
            db.session.rollback()
            app.logger.exception("Profile update failed")

            if new_photo_public_id:
                try:
                    delete_cloudinary_photo(new_photo_public_id)
                except Exception:
                    app.logger.exception("Photo cleanup failed")

            flash("Could not save your profile. Please try again.", "error")
            return render_template("profile.html")

        if (
            new_photo_public_id
            and old_photo_public_id
            and old_photo_public_id != new_photo_public_id
        ):
            try:
                delete_cloudinary_photo(old_photo_public_id)
            except Exception:
                app.logger.exception("Old photo cleanup failed")

        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html")


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(
            current_user.password_hash,
            current_password,
        ):
            flash("Your current password is incorrect.", "error")
            return render_template("change_password.html")

        if not validate_password(new_password):
            flash(
                "Password must be at least 8 characters and contain "
                "at least one letter and one number.",
                "error",
            )
            return render_template("change_password.html")

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return render_template("change_password.html")

        if check_password_hash(current_user.password_hash, new_password):
            flash("Choose a password different from your current password.", "error")
            return render_template("change_password.html")

        try:
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("profile"))

        except Exception:
            db.session.rollback()
            app.logger.exception("Password change failed")
            flash("Could not change your password. Please try again.", "error")

    return render_template("change_password.html")


# =========================================================
# DELETE ACCOUNT
# =========================================================

@app.route("/delete-account", methods=["GET", "POST"])
@login_required
def delete_account():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "").strip()

        if not check_password_hash(current_user.password_hash, password):
            flash("Password is incorrect. Account was not deleted.", "error")
            return render_template("delete_account.html")

        if confirmation != "DELETE":
            flash('Type DELETE exactly in the confirmation field.', "error")
            return render_template("delete_account.html")

        user_id = current_user.id
        photo_public_id = current_user.profile_photo_public_id

        try:
            # Remove notification records before deleting the user.
            db.session.execute(
                budget_notification.delete().where(
                    budget_notification.c.user_id == user_id
                )
            )

            user_to_delete = db.session.get(User, user_id)

            if user_to_delete is not None:
                db.session.delete(user_to_delete)

            db.session.commit()

        except Exception:
            db.session.rollback()
            app.logger.exception("Account deletion failed")
            flash("Could not delete your account. Please try again.", "error")
            return render_template("delete_account.html")

        logout_user()

        if photo_public_id:
            try:
                delete_cloudinary_photo(photo_public_id)
            except Exception:
                app.logger.exception("Cloudinary cleanup failed after deletion")

        flash("Your account has been deleted.", "success")
        return redirect(url_for("landing"))

    return render_template("delete_account.html")


# =========================================================
# BUDGET
# =========================================================

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    user_budget = Budget.query.filter_by(
        user_id=current_user.id
    ).first()

    if user_budget is None:
        user_budget = Budget(
            amount=10000,
            user_id=current_user.id,
        )
        db.session.add(user_budget)
        db.session.commit()

    if request.method == "POST":
        raw_value = request.form.get("budget", "").strip()

        try:
            budget_value = float(raw_value)
        except (TypeError, ValueError):
            flash("Please enter a valid budget.", "error")
            return render_template(
                "budget.html",
                current_budget=user_budget.amount,
            )

        if not 1 <= budget_value <= 100000000:
            flash(
                "Budget must be between ₹1 and ₹10,00,00,000.",
                "error",
            )
            return render_template(
                "budget.html",
                current_budget=user_budget.amount,
            )

        try:
            user_budget.amount = round(budget_value, 2)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Budget update failed")
            flash("Could not update the budget.", "error")
            return render_template(
                "budget.html",
                current_budget=user_budget.amount,
            )

        flash("Budget updated successfully!", "success")
        return redirect(url_for("home"))

    return render_template(
        "budget.html",
        current_budget=user_budget.amount,
    )


# =========================================================
# ADD EXPENSE
# =========================================================

@app.route("/add-expense", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        raw_amount = request.form.get("amount", "").strip()
        expense_date = request.form.get("date", "").strip()

        if not validate_expense_description(description):
            flash(
                "Description must be between 1 and 200 characters.",
                "error",
            )
            return render_template("add_expense.html")

        amount = validate_amount(raw_amount)

        if amount is None:
            flash("Please enter a valid amount greater than zero.", "error")
            return render_template("add_expense.html")

        if not validate_date(expense_date):
            flash("Please select a valid date.", "error")
            return render_template("add_expense.html")

        try:
            category = predict_category(description)
        except Exception:
            app.logger.exception("Category prediction failed")
            category = "Other"

        expense = Expense(
            description=description,
            amount=amount,
            category=category,
            date=expense_date,
            user_id=current_user.id,
        )

        try:
            db.session.add(expense)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Expense creation failed")
            flash("Could not add the expense. Please try again.", "error")
            return render_template("add_expense.html")

        try:
            from notify_budget import check_user_budget
            check_user_budget(current_user.id)
        except Exception:
            app.logger.exception("Budget notification check failed")

        flash(f"Expense added successfully! Category: {category}", "success")
        return redirect(url_for("home"))

    return render_template("add_expense.html")


# =========================================================
# DELETE EXPENSE
# =========================================================

@app.route("/delete-expense/<int:id>", methods=["POST"])
@login_required
def delete_expense(id):
    expense = Expense.query.filter_by(
        id=id,
        user_id=current_user.id,
    ).first_or_404()

    try:
        db.session.delete(expense)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Expense deletion failed")
        flash("Could not delete the expense.", "error")
        return redirect(url_for("home"))

    flash("Expense deleted successfully!", "success")
    return redirect(url_for("home"))


# =========================================================
# EDIT EXPENSE
# =========================================================

@app.route("/edit-expense/<int:id>", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    expense = Expense.query.filter_by(
        id=id,
        user_id=current_user.id,
    ).first_or_404()

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        raw_amount = request.form.get("amount", "").strip()
        expense_date = request.form.get("date", "").strip()

        if not validate_expense_description(description):
            flash(
                "Description must be between 1 and 200 characters.",
                "error",
            )
            return render_template("edit_expense.html", expense=expense)

        amount = validate_amount(raw_amount)

        if amount is None:
            flash("Please enter a valid amount greater than zero.", "error")
            return render_template("edit_expense.html", expense=expense)

        if not validate_date(expense_date):
            flash("Please select a valid date.", "error")
            return render_template("edit_expense.html", expense=expense)

        try:
            category = predict_category(description)
        except Exception:
            app.logger.exception("Category prediction failed")
            category = "Other"

        expense.description = description
        expense.amount = amount
        expense.category = category
        expense.date = expense_date

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Expense update failed")
            flash("Could not update the expense. Please try again.", "error")
            return render_template("edit_expense.html", expense=expense)

        try:
            from notify_budget import check_user_budget
            check_user_budget(current_user.id)
        except Exception:
            app.logger.exception("Budget notification check failed")

        flash("Expense updated successfully!", "success")
        return redirect(url_for("home"))

    return render_template("edit_expense.html", expense=expense)


# =========================================================
# ANALYTICS
# =========================================================

@app.route("/analytics")
@login_required
def analytics():
    expenses = Expense.query.filter_by(
        user_id=current_user.id
    ).all()

    category_totals = {}

    for expense in expenses:
        category = expense.category
        category_totals[category] = (
            category_totals.get(category, 0)
            + float(expense.amount)
        )

    total_spent = sum(
        float(expense.amount)
        for expense in expenses
    )

    monthly_budget = get_budget()
    remaining_budget = monthly_budget - total_spent

    highest_category = None
    highest_amount = 0

    if category_totals:
        highest_category = max(
            category_totals,
            key=category_totals.get,
        )
        highest_amount = category_totals[highest_category]

    highest_percentage = (
        highest_amount / total_spent * 100
        if total_spent > 0
        else 0
    )

    budget_percentage = (
        total_spent / monthly_budget * 100
        if monthly_budget > 0
        else 0
    )

    chart_labels = list(category_totals.keys())
    chart_values = [
        round(category_totals[key], 2)
        for key in chart_labels
    ]

    return render_template(
        "analytics.html",
        category_totals=category_totals,
        total_spent=total_spent,
        monthly_budget=monthly_budget,
        remaining_budget=remaining_budget,
        highest_category=highest_category,
        highest_amount=highest_amount,
        highest_percentage=highest_percentage,
        budget_percentage=budget_percentage,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


# =========================================================
# ROBOTS.TXT
# =========================================================

@app.route("/robots.txt")
def robots_txt():
    robots = (
        "User-agent: *\n"
        "Allow: /\n\n"
        "Sitemap: https://expensewise-aehc.onrender.com/sitemap.xml\n"
    )

    return robots, 200, {
        "Content-Type": "text/plain; charset=utf-8"
    }


# =========================================================
# SITEMAP
# =========================================================

@app.route("/sitemap.xml")
def sitemap_xml():
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://expensewise-aehc.onrender.com/</loc>
    </url>
    <url>
        <loc>https://expensewise-aehc.onrender.com/login</loc>
    </url>
    <url>
        <loc>https://expensewise-aehc.onrender.com/register</loc>
    </url>
</urlset>"""

    return sitemap, 200, {
        "Content-Type": "application/xml; charset=utf-8"
    }


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1"
    )
