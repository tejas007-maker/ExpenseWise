
import os
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    url_for
)

from flask_sqlalchemy import SQLAlchemy

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from ml_model import predict_category


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "expensewise-development-key"
)


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

database_url = os.environ.get("DATABASE_URL")


# Render may provide postgres://
# Convert it to postgresql+psycopg2://

if database_url:

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

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

else:

    # Local development database

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///expensewise.db"
    )


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# Connection health check

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}


# =========================================================
# SESSION / COOKIE SETTINGS
# =========================================================

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"


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

login_manager.login_message_category = "error"


# =========================================================
# USER LOADER
# =========================================================

@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )


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
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
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
        nullable=True
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
        unique=True
    )


# =========================================================
# BUDGET NOTIFICATION TABLE
# =========================================================

# This table is created automatically in both local SQLite
# and Render PostgreSQL when db.create_all() runs.

budget_notification = db.Table(
    "budget_notification",
    db.metadata,
    db.Column("id", db.Integer, primary_key=True),
    db.Column("user_id", db.Integer, nullable=False),
    db.Column("month", db.String(7), nullable=False),
    db.Column("notification_type", db.String(30), nullable=False),
    db.Column("created_at", db.DateTime, default=datetime.utcnow),
    db.UniqueConstraint(
        "user_id",
        "month",
        "notification_type",
        name="unique_budget_notification"
    )
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def prepare_database():

    # Create tables if they do not exist

    db.create_all()


    # -----------------------------------------------------
    # Legacy SQLite migration
    # -----------------------------------------------------
    #
    # This section runs ONLY for local SQLite.
    #
    # PostgreSQL on Render does not need this because
    # the tables are created fresh using db.create_all().
    # -----------------------------------------------------

    database_uri = app.config[
        "SQLALCHEMY_DATABASE_URI"
    ]


    if not database_uri.startswith("sqlite"):

        return


    # Flask-SQLAlchemy stores relative SQLite DB
    # inside the instance folder.

    database_path = os.path.join(
        app.instance_path,
        "expensewise.db"
    )


    if not os.path.exists(database_path):

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

        expense_columns = [
            row[1]
            for row in cursor.fetchall()
        ]


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

        budget_columns = [
            row[1]
            for row in cursor.fetchall()
        ]


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


# Run database preparation

with app.app_context():

    prepare_database()


# =========================================================
# HELPER FUNCTIONS
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

        db.session.add(budget)

        db.session.commit()


    return budget.amount


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
        # VALIDATION
        # -------------------------------------------------

        if not name:

            flash(
                "Please enter your name.",
                "error"
            )

            return render_template(
                "register.html"
            )


        if not email:

            flash(
                "Please enter your email.",
                "error"
            )

            return render_template(
                "register.html"
            )


        if not password:

            flash(
                "Please enter a password.",
                "error"
            )

            return render_template(
                "register.html"
            )


        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

            return render_template(
                "register.html"
            )


        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # CHECK EXISTING USER
        # -------------------------------------------------

        existing_user = User.query.filter_by(
            email=email
        ).first()


        if existing_user:

            flash(
                "An account with this email already exists.",
                "error"
            )

            return render_template(
                "register.html"
            )


        # -------------------------------------------------
        # CREATE USER
        # -------------------------------------------------

        password_hash = generate_password_hash(
            password
        )


        new_user = User(

            name=name,

            email=email,

            password_hash=password_hash

        )


        db.session.add(new_user)

        db.session.commit()


        # -------------------------------------------------
        # DEFAULT BUDGET
        # -------------------------------------------------

        default_budget = Budget(

            amount=10000,

            user_id=new_user.id

        )


        db.session.add(default_budget)

        db.session.commit()


        flash(
            "Account created successfully! Please login.",
            "success"
        )


        return redirect(
            url_for("login")
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


    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        remember = (
            request.form.get("remember")
            == "on"
        )


        # -------------------------------------------------
        # FIND USER
        # -------------------------------------------------

        user = User.query.filter_by(
            email=email
        ).first()


        if user is None:

            flash(
                "Invalid email or password.",
                "error"
            )

            return render_template(
                "login.html"
            )


        # -------------------------------------------------
        # PASSWORD CHECK
        # -------------------------------------------------

        if not check_password_hash(
            user.password_hash,
            password
        ):

            flash(
                "Invalid email or password.",
                "error"
            )

            return render_template(
                "login.html"
            )


        # -------------------------------------------------
        # LOGIN
        # -------------------------------------------------

        login_user(
            user,
            remember=remember
        )


        flash(
            f"Welcome back, {user.name}!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
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
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def home():

    expenses = Expense.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Expense.id.desc()
    ).all()


    total_spent = sum(
        expense.amount
        for expense in expenses
    )


    monthly_budget = get_budget()


    remaining_budget = (
        monthly_budget - total_spent
    )


    if monthly_budget > 0:

        budget_percentage = (
            total_spent /
            monthly_budget
        ) * 100

    else:

        budget_percentage = 0


    if budget_percentage >= 100:

        budget_status = "Budget Exceeded"

    elif budget_percentage >= 80:

        budget_status = "Budget Almost Reached"

    else:

        budget_status = "Within Budget"


    return render_template(

        "index.html",

        expenses=expenses,

        total_spent=total_spent,

        monthly_budget=monthly_budget,

        remaining_budget=remaining_budget,

        budget_percentage=budget_percentage,

        budget_status=budget_status

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

        db.session.add(user_budget)

        db.session.commit()


    if request.method == "POST":

        budget_value = request.form.get(
            "budget",
            ""
        )


        try:

            budget_value = float(
                budget_value
            )


            if budget_value <= 0:

                flash(
                    "Budget must be greater than zero.",
                    "error"
                )

                return render_template(
                    "budget.html",
                    current_budget=user_budget.amount
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


        user_budget.amount = budget_value

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

        amount = request.form.get(
            "amount",
            ""
        )

        date = request.form.get(
            "date",
            ""
        )


        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        if not description:

            flash(
                "Please enter a description.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # AMOUNT
        # -------------------------------------------------

        try:

            amount = float(amount)


            if amount <= 0:

                flash(
                    "Amount must be greater than zero.",
                    "error"
                )

                return render_template(
                    "add_expense.html"
                )


        except (
            TypeError,
            ValueError
        ):

            flash(
                "Please enter a valid amount.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        if not date:

            flash(
                "Please select a date.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )


        # -------------------------------------------------
        # AI CATEGORY
        # -------------------------------------------------

        category = predict_category(
            description
        )


        # -------------------------------------------------
        # CREATE EXPENSE
        # -------------------------------------------------

        new_expense = Expense(

            description=description,

            amount=amount,

            category=category,

            date=date,

            user_id=current_user.id

        )


        db.session.add(
            new_expense
        )

        db.session.commit()


        # Check the current user's budget notification thresholds.
        try:
            from notify_budget import check_user_budget
            check_user_budget(current_user.id)
        except Exception as error:
            print(
                f"Budget notification check failed: {error}"
            )


        flash(
            f"Expense added successfully! Category: {category}",
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
    "/delete-expense/<int:id>"
)
@login_required
def delete_expense(id):

    expense = Expense.query.filter_by(

        id=id,

        user_id=current_user.id

    ).first_or_404()


    db.session.delete(
        expense
    )

    db.session.commit()


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

        amount = request.form.get(
            "amount",
            ""
        )

        date = request.form.get(
            "date",
            ""
        )


        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        if not description:

            flash(
                "Please enter a description.",
                "error"
            )

            return render_template(

                "edit_expense.html",

                expense=expense

            )


        # -------------------------------------------------
        # AMOUNT
        # -------------------------------------------------

        try:

            amount = float(amount)


            if amount <= 0:

                flash(
                    "Amount must be greater than zero.",
                    "error"
                )

                return render_template(

                    "edit_expense.html",

                    expense=expense

                )


        except (
            TypeError,
            ValueError
        ):

            flash(
                "Please enter a valid amount.",
                "error"
            )

            return render_template(

                "edit_expense.html",

                expense=expense

            )


        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        if not date:

            flash(
                "Please select a date.",
                "error"
            )

            return render_template(

                "edit_expense.html",

                expense=expense

            )


        # -------------------------------------------------
        # AI CATEGORY
        # -------------------------------------------------

        category = predict_category(
            description
        )


        # -------------------------------------------------
        # UPDATE
        # -------------------------------------------------

        expense.description = description

        expense.amount = amount

        expense.category = category

        expense.date = date


        db.session.commit()


        # Re-check the current user's budget after an edit.
        try:
            from notify_budget import check_user_budget
            check_user_budget(current_user.id)
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


    # -----------------------------------------------------
    # CATEGORY TOTALS
    # -----------------------------------------------------

    category_totals = {}


    for expense in expenses:

        if expense.category not in category_totals:

            category_totals[
                expense.category
            ] = 0


        category_totals[
            expense.category
        ] += expense.amount


    # -----------------------------------------------------
    # TOTAL
    # -----------------------------------------------------

    total_spent = sum(

        expense.amount

        for expense in expenses

    )


    # -----------------------------------------------------
    # BUDGET
    # -----------------------------------------------------

    monthly_budget = get_budget()


    remaining_budget = (
        monthly_budget - total_spent
    )


    # -----------------------------------------------------
    # HIGHEST CATEGORY
    # -----------------------------------------------------

    highest_category = "None"

    highest_amount = 0


    if category_totals:

        highest_category = max(

            category_totals,

            key=category_totals.get

        )

        highest_amount = category_totals[
            highest_category
        ]


    # -----------------------------------------------------
    # HIGHEST CATEGORY %
    # -----------------------------------------------------

    if total_spent > 0:

        highest_percentage = (

            highest_amount /

            total_spent

        ) * 100

    else:

        highest_percentage = 0


    # -----------------------------------------------------
    # BUDGET %
    # -----------------------------------------------------

    if monthly_budget > 0:

        budget_percentage = (

            total_spent /

            monthly_budget

        ) * 100

    else:

        budget_percentage = 0


    return render_template(

        "analytics.html",

        category_totals=category_totals,

        total_spent=total_spent,

        monthly_budget=monthly_budget,

        remaining_budget=remaining_budget,

        highest_category=highest_category,

        highest_amount=highest_amount,

        highest_percentage=highest_percentage,

        budget_percentage=budget_percentage

    )


# =========================================================
# ROBOTS.TXT
# =========================================================

@app.route("/robots.txt")
def robots_txt():

    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        "Sitemap: "
        "https://expensewise-aehc.onrender.com/sitemap.xml\n"
    ), 200, {
        "Content-Type": "text/plain"
    }


# =========================================================
# SITEMAP
# =========================================================

@app.route("/sitemap.xml")
def sitemap_xml():

    return """
<?xml version="1.0" encoding="UTF-8"?>

<urlset
    xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/
        </loc>
    </url>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/login
        </loc>
    </url>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/register
        </loc>
    </url>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/add-expense
        </loc>
    </url>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/analytics
        </loc>
    </url>

    <url>
        <loc>
            https://expensewise-aehc.onrender.com/budget
        </loc>
    </url>

</urlset>
""", 200, {
    "Content-Type": "application/xml"
}


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )