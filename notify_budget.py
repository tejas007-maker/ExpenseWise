import os
from datetime import datetime

import resend

from sqlalchemy import (
    Table,
    Column,
    Integer,
    String,
    DateTime,
    UniqueConstraint
)

from app import (
    app,
    db,
    User,
    Expense,
    Budget
)


# =========================================================
# RESEND CONFIGURATION
# =========================================================

RESEND_API_KEY = os.environ.get(
    "RESEND_API_KEY"
)

if not RESEND_API_KEY:

    raise RuntimeError(
        "RESEND_API_KEY environment variable is missing."
    )

resend.api_key = RESEND_API_KEY


# =========================================================
# NOTIFICATION TABLE
# =========================================================

budget_notification = Table(
    "budget_notification",
    db.metadata,

    Column(
        "id",
        Integer,
        primary_key=True
    ),

    Column(
        "user_id",
        Integer,
        nullable=False
    ),

    Column(
        "month",
        String(7),
        nullable=False
    ),

    Column(
        "notification_type",
        String(30),
        nullable=False
    ),

    Column(
        "created_at",
        DateTime,
        default=datetime.utcnow
    ),

    UniqueConstraint(
        "user_id",
        "month",
        "notification_type",
        name="unique_budget_notification"
    )
)


# =========================================================
# SEND BUDGET EMAIL
# =========================================================

def send_budget_email(
    user,
    monthly_budget,
    total_spent,
    percentage,
    notification_type
):

    remaining = (
        monthly_budget -
        total_spent
    )

    if notification_type == "75":

        subject = (
            "ExpenseWise - 75% Budget Alert"
        )

        title = (
            "⚠️ You have used 75% "
            "of your monthly budget"
        )

        message = (
            "Your spending has reached 75% "
            "of your monthly budget."
        )

    elif notification_type == "90":

        subject = (
            "ExpenseWise - 90% Budget Alert"
        )

        title = (
            "🚨 You have used 90% "
            "of your monthly budget"
        )

        message = (
            "Your spending has reached 90% "
            "of your monthly budget. "
            "Consider reducing your remaining expenses."
        )

    else:

        subject = (
            "ExpenseWise - Budget Exceeded"
        )

        title = (
            "🔴 Your monthly budget "
            "has been exceeded"
        )

        message = (
            "Your spending has reached or exceeded "
            "your monthly budget."
        )

    html = f"""
    <html>

    <body style="
        font-family: Arial, sans-serif;
        background: #f4f7fb;
        padding: 30px;
    ">

        <div style="
            max-width: 600px;
            margin: auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
        ">

            <h1>ExpenseWise</h1>

            <h2>{title}</h2>

            <p>
                Hello {user.name},
            </p>

            <p>
                {message}
            </p>

            <hr>

            <p>
                <strong>Monthly Budget:</strong>
                ₹{monthly_budget:,.2f}
            </p>

            <p>
                <strong>Total Spent:</strong>
                ₹{total_spent:,.2f}
            </p>

            <p>
                <strong>Budget Used:</strong>
                {percentage:.1f}%
            </p>

            <p>
                <strong>Remaining:</strong>
                ₹{remaining:,.2f}
            </p>

            <hr>

            <p>
                Open ExpenseWise to review
                your spending and manage
                your budget.
            </p>

            <p style="color: #777;">
                This is an automatic notification
                from ExpenseWise.
            </p>

        </div>

    </body>

    </html>
    """

    response = resend.Emails.send({

        "from":
            "ExpenseWise <onboarding@resend.dev>",

        "to":
            [user.email],

        "subject":
            subject,

        "html":
            html
    })

    print(
        f"Email sent to {user.email}: {response}"
    )


# =========================================================
# CHECK DUPLICATE NOTIFICATION
# =========================================================

def already_sent(
    user_id,
    month,
    notification_type
):

    result = db.session.execute(

        db.select(
            budget_notification.c.id
        ).where(

            budget_notification.c.user_id
            == user_id,

            budget_notification.c.month
            == month,

            budget_notification.c.notification_type
            == notification_type
        )
    ).first()

    return result is not None


# =========================================================
# RECORD NOTIFICATION
# =========================================================

def record_notification(
    user_id,
    month,
    notification_type
):

    db.session.execute(

        budget_notification.insert().values(

            user_id=user_id,

            month=month,

            notification_type=
                notification_type,

            created_at=
                datetime.utcnow()
        )
    )

    db.session.commit()


# =========================================================
# CHECK BUDGETS
# =========================================================

def check_budgets():

    today = datetime.now()

    current_month = (
        today.strftime("%Y-%m")
    )

    print(
        f"Checking ExpenseWise budgets "
        f"for {current_month}..."
    )

    # IMPORTANT:
    # Everything using db must run inside
    # the Flask application context.

    with app.app_context():

        users = User.query.all()

        for user in users:

            budget = Budget.query.filter_by(
                user_id=user.id
            ).first()

            if budget is None:

                continue

            monthly_budget = budget.amount

            if monthly_budget <= 0:

                continue

            expenses = Expense.query.filter(

                Expense.user_id == user.id,

                Expense.date.like(
                    f"{current_month}%"
                )

            ).all()

            total_spent = sum(

                expense.amount

                for expense in expenses

            )

            percentage = (

                total_spent /
                monthly_budget

            ) * 100

            print(

                f"{user.email}: "
                f"₹{total_spent:.2f} / "
                f"₹{monthly_budget:.2f} "
                f"({percentage:.1f}%)"

            )

            notification_type = None

            if percentage >= 100:

                notification_type = "100"

            elif percentage >= 90:

                notification_type = "90"

            elif percentage >= 75:

                notification_type = "75"

            if notification_type is None:

                continue

            if already_sent(

                user.id,

                current_month,

                notification_type

            ):

                print(

                    f"Already sent "
                    f"{notification_type}% alert "
                    f"to {user.email}"

                )

                continue

            try:

                send_budget_email(

                    user=user,

                    monthly_budget=
                        monthly_budget,

                    total_spent=
                        total_spent,

                    percentage=
                        percentage,

                    notification_type=
                        notification_type

                )

                record_notification(

                    user.id,

                    current_month,

                    notification_type

                )

            except Exception as error:

                print(

                    f"Email failed for "
                    f"{user.email}: {error}"

                )


# =========================================================
# RUN DIRECTLY
# =========================================================

if __name__ == "__main__":

    check_budgets()