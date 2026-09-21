import os
from flask import Flask, render_template, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from ml_model import predict_category

app = Flask(__name__)

# Flask secret key


app.secret_key = os.environ.get(
    "SECRET_KEY",
    "expensewise-development-key"
)

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///expensewise.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================
# DATABASE MODELS
# =========================

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(50), nullable=False)


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False, default=10000)


# =========================
# DATABASE INITIALIZATION
# =========================

with app.app_context():
    db.create_all()

    # Create default budget if none exists
    if Budget.query.first() is None:
        default_budget = Budget(amount=10000)
        db.session.add(default_budget)
        db.session.commit()


# =========================
# HELPER FUNCTIONS
# =========================

def get_budget():
    budget = Budget.query.first()

    if budget:
        return budget.amount

    return 10000


# =========================
# DASHBOARD
# =========================

@app.route("/")
def home():

    expenses = Expense.query.order_by(Expense.id.desc()).all()

    total_spent = sum(expense.amount for expense in expenses)

    monthly_budget = get_budget()

    remaining_budget = monthly_budget - total_spent

    if monthly_budget > 0:
        budget_percentage = (total_spent / monthly_budget) * 100
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


# =========================
# BUDGET
# =========================

@app.route("/budget", methods=["GET", "POST"])
def budget():

    budget = Budget.query.first()

    if request.method == "POST":

        budget_value = request.form.get("budget")

        try:

            budget_value = float(budget_value)

            if budget_value <= 0:

                flash(
                    "Budget must be greater than zero.",
                    "error"
                )

                return render_template(
                    "budget.html",
                    current_budget=budget.amount
                )

        except (TypeError, ValueError):

            flash(
                "Please enter a valid budget.",
                "error"
            )

            return render_template(
                "budget.html",
                current_budget=budget.amount
            )

        budget.amount = budget_value

        db.session.commit()

        flash(
            "Budget updated successfully!",
            "success"
        )

        return redirect("/")

    return render_template(
        "budget.html",
        current_budget=budget.amount
    )


# =========================
# ADD EXPENSE
# =========================

@app.route("/add-expense", methods=["GET", "POST"])
def add_expense():

    if request.method == "POST":

        description = request.form.get("description")
        amount = request.form.get("amount")
        date = request.form.get("date")

        # Validate description
        if not description:

            flash(
                "Please enter a description.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )

        # Validate amount
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

        except (TypeError, ValueError):

            flash(
                "Please enter a valid amount.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )

        # Validate date
        if not date:

            flash(
                "Please select a date.",
                "error"
            )

            return render_template(
                "add_expense.html"
            )

        # AI-based category prediction
        category = predict_category(description)

        # Create new expense
        new_expense = Expense(
            description=description,
            amount=amount,
            category=category,
            date=date
        )

        db.session.add(new_expense)

        db.session.commit()

        flash(
            f"Expense added successfully! Category: {category}",
            "success"
        )

        return redirect("/")

    return render_template(
        "add_expense.html"
    )


# =========================
# DELETE EXPENSE
# =========================

@app.route("/delete-expense/<int:id>")
def delete_expense(id):

    expense = Expense.query.get_or_404(id)

    db.session.delete(expense)

    db.session.commit()

    flash(
        "Expense deleted successfully!",
        "success"
    )

    return redirect("/")


# =========================
# EDIT EXPENSE
# =========================

@app.route("/edit-expense/<int:id>", methods=["GET", "POST"])
def edit_expense(id):

    expense = Expense.query.get_or_404(id)

    if request.method == "POST":

        description = request.form.get("description")
        amount = request.form.get("amount")
        category = request.form.get("category")
        date = request.form.get("date")

        # Validate description
        if not description:

            flash(
                "Please enter a description.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )

        # Validate amount
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

        except (TypeError, ValueError):

            flash(
                "Please enter a valid amount.",
                "error"
            )

            return render_template(
                "edit_expense.html",
                expense=expense
            )

        # Update expense
        expense.description = description
        expense.amount = amount
        expense.category = category
        expense.date = date

        db.session.commit()

        flash(
            "Expense updated successfully!",
            "success"
        )

        return redirect("/")

    return render_template(
        "edit_expense.html",
        expense=expense
    )


# =========================
# ANALYTICS
# =========================

@app.route("/analytics")
def analytics():

    expenses = Expense.query.all()

    category_totals = {}

    # Calculate spending by category
    for expense in expenses:

        if expense.category not in category_totals:

            category_totals[expense.category] = 0

        category_totals[expense.category] += expense.amount

    # Total spending
    total_spent = sum(
        expense.amount
        for expense in expenses
    )

    # Highest spending category
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

    # Highest category percentage
    if total_spent > 0:

        highest_percentage = (
            highest_amount / total_spent
        ) * 100

    else:

        highest_percentage = 0

    # Budget percentage
    monthly_budget = get_budget()

    if monthly_budget > 0:

        budget_percentage = (
            total_spent / monthly_budget
        ) * 100

    else:

        budget_percentage = 0

    return render_template(
        "analytics.html",
        category_totals=category_totals,
        total_spent=total_spent,
        highest_category=highest_category,
        highest_amount=highest_amount,
        highest_percentage=highest_percentage,
        budget_percentage=budget_percentage
    )


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    app.run(debug=True)