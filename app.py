import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

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

from flask_wtf.csrf import (
    CSRFProtect,
    generate_csrf,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from ml_model import predict_category


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)


# ---------------------------------------------------------
# SECRET KEY
# ---------------------------------------------------------

secret_key = os.environ.get("SECRET_KEY")

if not secret_key:

    if os.environ.get("RENDER") == "true":

        raise RuntimeError(
            "SECRET_KEY environment variable is required in production."
        )

    secret_key = "expensewise-local-development-key-change-me"

app.config["SECRET_KEY"] = secret_key


# ---------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------

is_production = (
    os.environ.get("RENDER") == "true"
)


# ---------------------------------------------------------
# REQUEST SIZE LIMIT
# ---------------------------------------------------------

# Maximum request body size: 1 MB
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024


# =========================================================
# CSRF PROTECTION
# =========================================================

# CSRF token lifetime
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

csrf = CSRFProtect(app)


@app.context_processor
def inject_csrf_token():

    return {
        "csrf_token": generate_csrf
    }


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

database_url = os.environ.get(
    "DATABASE_URL"
)


if database_url:

    # Render / legacy PostgreSQL URL support

    if database_url.startswith("postgres://"):

        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1
        )

    elif database_url.startswith("postgresql://"):

        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        database_url
    )

else:

    # Local development database

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///expensewise.db"
    )


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}


# =========================================================
# SESSION / COOKIE SECURITY
# =========================================================

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SECURE"] = (
    is_production
)

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


app.config["REMEMBER_COOKIE_HTTPONLY"] = True

app.config["REMEMBER_COOKIE_SECURE"] = (
    is_production
)

app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

app.config["REMEMBER_COOKIE_DURATION"] = (
    60 * 60 * 24 * 30
)


# =========================================================
# DATABASE
# =========================================================

db = SQLAlchemy(app)


# =========================================================
# FLASK LOGIN
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"

login_manager.login_message = (
    "Please login to continue."
)

login_manager.login_message_category = (
    "error"
)


# =========================================================
# USER LOADER
# =========================================================

@login_manager.user_loader
def load_user(user_id):

    try:

        return db.session.get(
            User,
            int(user_id)
        )

    except (TypeError, ValueError):

        return None


# =========================================================
# DATABASE MODELS
# =========================================================

class User(UserMixin, db.Model):

    __tablename__ = "user"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(150),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    expenses = db.relationship(
        "Expense",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )

    budget = db.relationship(
        "Budget",
        backref="owner",
        uselist=False,
        lazy=True,
        cascade="all, delete-orphan"
    )


class Expense(db.Model):

    __tablename__ = "expense"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    description = db.Column(
        db.String(200),
        nullable=False
    )

    amount = db.Column(
        db.Float,
        nullable=False
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    date = db.Column(
        db.String(50),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True
    )


class Budget(db.Model):

    __tablename__ = "budget"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    amount = db.Column(
        db.Float,
        nullable=False,
        default=10000
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        unique=True,
        index=True
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
        primary_key=True
    ),

    db.Column(
        "user_id",
        db.Integer,
        nullable=False,
        index=True
    ),

    db.Column(
        "month",
        db.String(7),
        nullable=False
    ),

    db.Column(
        "notification_type",
        db.String(30),
        nullable=False
    ),

    db.Column(
        "created_at",
        db.DateTime,
        default=datetime.utcnow
    ),

    db.UniqueConstraint(
        "user_id",
        "month",
        "notification_type",
        name="unique_budget_notification"
    ),
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def prepare_database():

    db.create_all()

    database_uri = app.config[
        "SQLALCHEMY_DATABASE_URI"
    ]

    # PostgreSQL doesn't need legacy SQLite migration

    if not database_uri.startswith("sqlite"):

        return

    database_path = os.path.join(
        app.instance_path,
        "expensewise.db"
    )

    if not os.path.exists(
        database_path
    ):

        return

    connection = sqlite3.connect(
        database_path
    )

    cursor = connection.cursor()


    # -----------------------------------------------------
    # EXPENSE USER_ID
    # -----------------------------------------------------

    try:

        cursor.execute(
            "PRAGMA table_info(expense)"
        )

        expense_columns = {
            row[1]
            for row in cursor.fetchall()
        }

        if "user_id" not in expense_columns:

            cursor.execute(
                """
                ALTER TABLE expense
                ADD COLUMN user_id INTEGER
                """
            )

    except sqlite3.OperationalError:

        pass


    # -----------------------------------------------------
    # BUDGET USER_ID
    # -----------------------------------------------------

    try:

        cursor.execute(
            "PRAGMA table_info(budget)"
        )

        budget_columns = {
            row[1]
            for row in cursor.fetchall()
        }

        if "user_id" not in budget_columns:

            cursor.execute(
                """
                ALTER TABLE budget
                ADD COLUMN user_id INTEGER
                """
            )

    except sqlite3.OperationalError:

        pass


    connection.commit()

    connection.close()


with app.app_context():

    prepare_database()


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def add_security_headers(response):

    # Prevent MIME sniffing
    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"


    # Prevent clickjacking
    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"


    # Control referrer information
    response.headers[
        "Referrer-Policy"
    ] = "strict-origin-when-cross-origin"


    # Disable unnecessary browser capabilities
    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), "
        "microphone=(), "
        "geolocation=()"
    )


    # Basic Content Security Policy
    #
    # 'unsafe-inline' is currently required because
    # ExpenseWise templates contain inline CSS/JS.
    #
    # We can tighten this further later by moving
    # inline CSS/JS into external files.

    response.headers[
        "Content-Security-Policy"
    ] = (
        "default-src 'self'; "
        "script-src 'self' "
        "https://cdn.jsdelivr.net "
        "'unsafe-inline'; "
        "style-src 'self' "
        "https://fonts.googleapis.com "
        "'unsafe-inline'; "
        "font-src 'self' "
        "https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


    # HSTS only over HTTPS production
    if is_production:

        response.headers[
            "Strict-Transport-Security"
        ] = (
            "max-age=31536000; "
            "includeSubDomains"
        )


    return response


# =========================================================
# HELPERS
# =========================================================

def get_budget():

    if not current_user.is_authenticated:

        return 10000


    budget = Budget.query.filter_by(
        user_id=current_user.id
    ).first()


    if budget is None:

        budget = Budget(
            amount=10000,
            user_id=current_user.id
        )

        db.session.add(
            budget
        )

        db.session.commit()


    return float(
        budget.amount
    )


def get_user_expenses():

    return Expense.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Expense.id.desc()
    ).all()


# =========================================================
# VALIDATION HELPERS
# =========================================================

def validate_name(name):

    if not name:

        return False

    if len(name) < 2:

        return False

    if len(name) > 100:

        return False

    return True


def validate_email(email):

    if not email:

        return False

    if len(email) > 150:

        return False

    # Basic email format validation
    pattern = (
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    return re.match(
        pattern,
        email
    ) is not None


def validate_password(password):

    if not password:

        return False

    # Minimum 8 characters
    if len(password) < 8:

        return False

    # Maximum reasonable password length
    if len(password) > 128:

        return False

    # At least one letter
    if not any(
        character.isalpha()
        for character in password
    ):

        return False

    # At least one number
    if not any(
        character.isdigit()
        for character in password
    ):

        return False

    return True


def validate_expense_description(
    description
):

    if not description:

        return False

    if len(description) > 200:

        return False

    return True


def validate_amount(
    amount
):

    try:

        value = float(amount)

    except (
        TypeError,
        ValueError
    ):

        return None


    if value <= 0:

        return None


    if value > 100000000:

        return None


    return round(
        value,
        2
    )


def validate_date(date_value):

    if not date_value:

        return False

    try:

        datetime.strptime(
            date_value,
            "%Y-%m-%d"
        )

        return True

    except ValueError:

        return False


# =========================================================
# SAFE REDIRECT
# =========================================================

def safe_next_url(target):

    if not target:

        return None

    parsed = urlparse(
        target
    )


    # Reject external URLs

    if parsed.scheme:

        return None

    if parsed.netloc:

        return None


    # Must start with /

    if not target.startswith("/"):

        return None


    # Reject protocol-relative URLs

    if target.startswith("//"):

        return None


    return target


# =========================================================
# LOGIN THROTTLING
# =========================================================

# Simple in-memory login protection.
#
# This protects the running Flask instance against
# repeated password guessing.
#
# For a multi-instance production deployment,
# this should later be moved to Redis/database storage.

_login_attempts = {}


def login_throttled(
    ip_address
):

    now = datetime.utcnow().timestamp()

    data = _login_attempts.get(
        ip_address
    )


    if not data:

        return False


    attempts, first_time, blocked_until = data


    # Currently blocked

    if (
        blocked_until
        and now < blocked_until
    ):

        return True


    # Reset after 15 minutes

    if now - first_time > 900:

        _login_attempts.pop(
            ip_address,
            None
        )

        return False


    return False


def register_login_failure(
    ip_address
):

    now = datetime.utcnow().timestamp()


    data = _login_attempts.get(
        ip_address
    )


    if data:

        attempts, first_time, blocked_until = data

    else:

        attempts = 0
        first_time = now
        blocked_until = 0


    # Reset the attempt window

    if now - first_time > 900:

        attempts = 0
        first_time = now
        blocked_until = 0


    attempts += 1


    # 8 failed attempts = 15 minute block

    if attempts >= 8:

        blocked_until = (
            now + 900
        )


    _login_attempts[
        ip_address
    ] = (
        attempts,
        first_time,
        blocked_until
    )


def clear_login_failures(
    ip_address
):

    _login_attempts.pop(
        ip_address,
        None
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
        message=(
            "The request could not be processed."
        )
    ), 400


@app.errorhandler(403)
def forbidden(error):

    return render_template(
        "error.html",
        code=403,
        title="Access Denied",
        message=(
            "You do not have permission "
            "to access this resource."
        )
    ), 403


@app.errorhandler(404)
def not_found(error):

    return render_template(
        "error.html",
        code=404,
        title="Page Not Found",
        message=(
            "The page you requested "
            "does not exist."
        )
    ), 404


@app.errorhandler(413)
def request_too_large(error):

    return render_template(
        "error.html",
        code=413,
        title="Request Too Large",
        message=(
            "The submitted request is too large."
        )
    ), 413


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()

    return render_template(
        "error.html",
        code=500,
        title="Something Went Wrong",
        message=(
            "An unexpected error occurred. "
            "Please try again."
        )
    ), 500


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user.is_authenticated:

        return redirect(
            url_for("home")
        )


    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        # -------------------------------------------------
        # NAME
        # -------------------------------------------------

        if not validate_name(
            name
        ):

            flash(
                "Name must be between "
                "2 and 100 characters.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # EMAIL
        # -------------------------------------------------

        if not validate_email(
            email
        ):

            flash(
                "Please enter a valid email address.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # PASSWORD
        # -------------------------------------------------

        if not validate_password(
            password
        ):

            flash(
                "Password must be at least "
                "8 characters and contain "
                "at least one letter and one number.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # CONFIRM PASSWORD
        # -------------------------------------------------

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # EXISTING USER
        # -------------------------------------------------

        existing_user = User.query.filter_by(
            email=email
        ).first()


        if existing_user:

            flash(
                "An account with this email "
                "already exists.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # CREATE USER
        # -------------------------------------------------

        try:

            new_user = User(
                name=name,
                email=email,
                password_hash=(
                    generate_password_hash(
                        password
                    )
                )
            )


            db.session.add(
                new_user
            )


            db.session.flush()


            # Default budget

            default_budget = Budget(
                amount=10000,
                user_id=new_user.id
            )


            db.session.add(
                default_budget
            )


            db.session.commit()


            # -------------------------------------------------
            # WELCOME EMAIL
            # -------------------------------------------------

            try:

                from notify_budget import (
                    send_welcome_email
                )

                send_welcome_email(
                    new_user
                )

            except Exception as error:

                # Email failure must not prevent
                # account creation

                print(
                    f"Welcome email failed: {error}"
                )


            flash(
                "Account created successfully! "
                "Please login.",
                "success"
            )


            return redirect(
                url_for("login")
            )


        except Exception as error:

            db.session.rollback()

            print(
                f"Registration error: {error}"
            )

            flash(
                "Could not create the account. "
                "Please try again.",
                "error"
            )


    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user.is_authenticated:

        return redirect(
            url_for("home")
        )


    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    if request.method == "GET":

        next_url = safe_next_url(
            request.args.get(
                "next"
            )
        )

        return render_template(
            "login.html",
            next=next_url
        )


    # -----------------------------------------------------
    # IP ADDRESS
    # -----------------------------------------------------

    ip_address = (
        request.remote_addr
        or "unknown"
    )


    # -----------------------------------------------------
    # THROTTLING
    # -----------------------------------------------------

    if login_throttled(
        ip_address
    ):

        flash(
            "Too many failed login attempts. "
            "Please wait 15 minutes and try again.",
            "error"
        )

        return render_template(
            "login.html"
        ), 429


    # -----------------------------------------------------
    # FORM DATA
    # -----------------------------------------------------

    email = request.form.get(
        "email",
        ""
    ).strip().lower()


    password = request.form.get(
        "password",
        ""
    )


    remember = (
        request.form.get(
            "remember"
        ) == "1"
        or
        request.form.get(
            "remember"
        ) == "on"
    )


    next_url = safe_next_url(
        request.form.get(
            "next"
        )
    )


    # -----------------------------------------------------
    # FIND USER
    # -----------------------------------------------------

    user = User.query.filter_by(
        email=email
    ).first()


    # -----------------------------------------------------
    # VERIFY PASSWORD
    # -----------------------------------------------------

    if (
        user is None
        or not check_password_hash(
            user.password_hash,
            password
        )
    ):

        register_login_failure(
            ip_address
        )

        # Deliberately generic message
        # so attackers cannot determine
        # whether an email exists.

        flash(
            "Invalid email or password.",
            "error"
        )

        return render_template(
            "login.html"
        )


    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    clear_login_failures(
        ip_address
    )


    login_user(
        user,
        remember=remember,
        fresh=True
    )


    flash(
        f"Welcome back, {user.name}!",
        "success"
    )


    return redirect(
        next_url
        or url_for("home")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route(
    "/logout",
    methods=["POST"]
)
@login_required
def logout():

    logout_user()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# =========================================================
# LANDING PAGE
# =========================================================

@app.route("/")
def landing():

    if current_user.is_authenticated:

        return redirect(
            url_for("home")
        )

    return render_template(
        "landing.html"
    )


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


    remaining_budget = (
        monthly_budget
        - total_spent
    )


    if monthly_budget > 0:

        budget_percentage = (
            total_spent
            / monthly_budget
            * 100
        )

    else:

        budget_percentage = 0


    # Keep these exact names aligned
    # with index.html.

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
# BUDGET
# =========================================================

@app.route(
    "/budget",
    methods=["GET", "POST"]
)
@login_required
def budget():

    user_budget = Budget.query.filter_by(
        user_id=current_user.id
    ).first()


    if user_budget is None:

        user_budget = Budget(
            amount=10000,
            user_id=current_user.id
        )

        db.session.add(
            user_budget
        )

        db.session.commit()


    # -----------------------------------------------------
    # UPDATE BUDGET
    # -----------------------------------------------------

    if request.method == "POST":

        raw_value = request.form.get(
            "budget",
            ""
        ).strip()


        try:

            budget_value = float(
                raw_value
            )

        except (
            TypeError,
            ValueError
        ):

            flash(
                "Please enter a valid budget.",
                "error"
            )

            return render_template(
                "budget.html",
                current_budget=user_budget.amount
            )


        if not 1 <= budget_value <= 100000000:

            flash(
                "Budget must be between "
                "₹1 and ₹10,00,00,000.",
                "error"
            )

            return render_template(
                "budget.html",
                current_budget=user_budget.amount
            )


        user_budget.amount = round(
            budget_value,
            2
        )


        db.session.commit()


        flash(
            "Budget updated successfully!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "budget.html",
        current_budget=user_budget.amount
    )


# =========================================================
# ADD EXPENSE
# =========================================================

@app.route(
    "/add-expense",
    methods=["GET", "POST"]
)
@login_required
def add_expense():

    if request.method == "POST":

        description = request.form.get(
            "description",
            ""
        ).strip()


        raw_amount = request.form.get(
            "amount",
            ""
        ).strip()


        date = request.form.get(
            "date",
            ""
        ).strip()


        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        if not validate_expense_description(
            description
        ):

            flash(
                "Description must be between "
                "1 and 200 characters.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # AMOUNT
        # -------------------------------------------------

        amount = validate_amount(
            raw_amount
        )


        if amount is None:

            flash(
                "Please enter a valid amount "
                "greater than zero.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        if not validate_date(
            date
        ):

            flash(
                "Please select a valid date.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # AI CATEGORY
        # -------------------------------------------------

        try:

            category = predict_category(
                description
            )

        except Exception as error:

            print(
                f"Category prediction failed: {error}"
            )

            category = "Other"


        # -------------------------------------------------
        # CREATE EXPENSE
        # -------------------------------------------------

        expense = Expense(
            description=description,
            amount=amount,
            category=category,
            date=date,
            user_id=current_user.id,
        )


        try:

            db.session.add(
                expense
            )

            db.session.commit()


        except Exception as error:

            db.session.rollback()

            print(
                f"Expense creation error: {error}"
            )

            flash(
                "Could not add the expense. "
                "Please try again.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # BUDGET NOTIFICATION
        # -------------------------------------------------

        try:

            from notify_budget import (
                check_user_budget
            )

            check_user_budget(
                current_user.id
            )

        except Exception as error:

            print(
                f"Budget notification check failed: {error}"
            )


        flash(
            f"Expense added successfully! "
            f"Category: {category}",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "add_expense.html"
    )


# =========================================================
# DELETE EXPENSE
# =========================================================

@app.route(
    "/delete-expense/<int:id>",
    methods=["POST"]
)
@login_required
def delete_expense(id):

    expense = Expense.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()


    try:

        db.session.delete(
            expense
        )

        db.session.commit()


    except Exception as error:

        db.session.rollback()

        print(
            f"Expense deletion error: {error}"
        )

        flash(
            "Could not delete the expense.",
            "error"
        )

        return redirect(
            url_for("home")
        )


    flash(
        "Expense deleted successfully!",
        "success"
    )


    return redirect(
        url_for("home")
    )


# =========================================================
# EDIT EXPENSE
# =========================================================

@app.route(
    "/edit-expense/<int:id>",
    methods=["GET", "POST"]
)
@login_required
def edit_expense(id):

    expense = Expense.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()


    if request.method == "POST":

        description = request.form.get(
            "description",
            ""
        ).strip()


        raw_amount = request.form.get(
            "amount",
            ""
        ).strip()


        date = request.form.get(
            "date",
            ""
        ).strip()


        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        if not validate_expense_description(
            description
        ):

            flash(
                "Description must be between "
                "1 and 200 characters.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )


        # -------------------------------------------------
        # AMOUNT
        # -------------------------------------------------

        amount = validate_amount(
            raw_amount
        )


        if amount is None:

            flash(
                "Please enter a valid amount "
                "greater than zero.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )


        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        if not validate_date(
            date
        ):

            flash(
                "Please select a valid date.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )


        # -------------------------------------------------
        # AI CATEGORY
        # -------------------------------------------------

        try:

            category = predict_category(
                description
            )

        except Exception as error:

            print(
                f"Category prediction failed: {error}"
            )

            category = "Other"


        # -------------------------------------------------
        # UPDATE EXPENSE
        # -------------------------------------------------

        expense.description = (
            description
        )

        expense.amount = amount

        expense.category = category

        expense.date = date


        try:

            db.session.commit()


        except Exception as error:

            db.session.rollback()

            print(
                f"Expense update error: {error}"
            )

            flash(
                "Could not update the expense. "
                "Please try again.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )


        # -------------------------------------------------
        # BUDGET NOTIFICATION
        # -------------------------------------------------

        try:

            from notify_budget import (
                check_user_budget
            )

            check_user_budget(
                current_user.id
            )

        except Exception as error:

            print(
                f"Budget notification check failed: {error}"
            )


        flash(
            "Expense updated successfully!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "edit_expense.html",
        expense=expense
    )


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
            category_totals.get(
                category,
                0
            )
            + float(expense.amount)
        )


    total_spent = sum(
        float(expense.amount)
        for expense in expenses
    )


    monthly_budget = get_budget()


    remaining_budget = (
        monthly_budget
        - total_spent
    )


    # -----------------------------------------------------
    # HIGHEST CATEGORY
    # -----------------------------------------------------

    highest_category = None

    highest_amount = 0


    if category_totals:

        highest_category = max(
            category_totals,
            key=category_totals.get
        )

        highest_amount = (
            category_totals[
                highest_category
            ]
        )


    # -----------------------------------------------------
    # HIGHEST CATEGORY %
    # -----------------------------------------------------

    if total_spent > 0:

        highest_percentage = (
            highest_amount
            / total_spent
            * 100
        )

    else:

        highest_percentage = 0


    # -----------------------------------------------------
    # BUDGET %
    # -----------------------------------------------------

    if monthly_budget > 0:

        budget_percentage = (
            total_spent
            / monthly_budget
            * 100
        )

    else:

        budget_percentage = 0


    # -----------------------------------------------------
    # CHART DATA
    # -----------------------------------------------------

    chart_labels = list(
        category_totals.keys()
    )


    chart_values = [

        round(
            category_totals[key],
            2
        )

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
        "Sitemap: "
        "https://expensewise-aehc.onrender.com/"
        "sitemap.xml\n"
    )


    return robots, 200, {
        "Content-Type":
            "text/plain; charset=utf-8"
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
        "Content-Type":
            "application/xml; charset=utf-8"
    }


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=(
            os.environ.get(
                "FLASK_DEBUG"
            ) == "1"
        )
    )