import os

from datetime import datetime

from html import escape

import resend

from app import (
    app,
    db,
    User,
    Expense,
    Budget,
    budget_notification,
)


# =========================================================
# RESEND CONFIGURATION
# =========================================================

RESEND_API_KEY = os.environ.get(
    "RESEND_API_KEY"
)

if RESEND_API_KEY:

    resend.api_key = RESEND_API_KEY


# =========================================================
# WELCOME EMAIL
# =========================================================

def send_welcome_email(user):

    if not RESEND_API_KEY:

        print(
            "RESEND_API_KEY is not configured."
        )

        return False

    name = escape(
        user.name
    )

    try:

        resend.Emails.send(
            {
                "from":
                    "ExpenseWise "
                    "<onboarding@resend.dev>",

                "to":
                    [user.email],

                "subject":
                    "Welcome to ExpenseWise! 🎉",

                "html":
                    f"""
                    <html>

                    <body
                        style="
                        font-family:Arial,sans-serif;
                        line-height:1.6;
                        "
                    >

                    <h2>
                        Welcome to ExpenseWise,
                        {name}! 🎉
                    </h2>

                    <p>
                        Your ExpenseWise account
                        has been created successfully.
                    </p>

                    <p>
                        With ExpenseWise you can:
                    </p>

                    <ul>

                        <li>
                            Track daily expenses
                        </li>

                        <li>
                            Get AI-based
                            expense categories
                        </li>

                        <li>
                            Set and manage
                            your monthly budget
                        </li>

                        <li>
                            Analyze
                            spending patterns
                        </li>

                        <li>
                            Receive budget
                            threshold alerts
                        </li>

                    </ul>

                    <p>
                        Start tracking your expenses
                        and manage your money smarter.
                    </p>

                    <p>
                        Regards,<br>
                        <strong>
                            ExpenseWise Team
                        </strong>
                    </p>

                    </body>
                    </html>
                    """
            }
        )

        print(
            f"Welcome email sent to "
            f"{user.email}."
        )

        return True

    except Exception as error:

        print(
            f"Welcome email sending failed: "
            f"{error}"
        )

        return False


# =========================================================
# CHECK EXISTING NOTIFICATION
# =========================================================

def already_sent(
    user_id,
    month,
    notification_type
):

    result = db.session.execute(

        db.select(
            budget_notification
        ).where(

            budget_notification.c.user_id
            == user_id,

            budget_notification.c.month
            == month,

            budget_notification.c.notification_type
            == notification_type,

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

    try:

        db.session.execute(

            budget_notification.insert().values(

                user_id=user_id,

                month=month,

                notification_type=(
                    notification_type
                ),

                created_at=datetime.utcnow(),

            )

        )

        db.session.commit()

    except Exception:

        db.session.rollback()

        raise


# =========================================================
# BUDGET EMAIL
# =========================================================

def send_budget_email(
    user,
    budget_amount,
    spent_amount,
    percentage,
    threshold
):

    if not RESEND_API_KEY:

        print(
            "RESEND_API_KEY is not configured."
        )

        return False

    name = escape(
        user.name
    )

    try:

        resend.Emails.send(
            {
                "from":
                    "ExpenseWise "
                    "<onboarding@resend.dev>",

                "to":
                    [user.email],

                "subject":
                    (
                        "ExpenseWise Budget Alert - "
                        f"{threshold}% Used"
                    ),

                "html":
                    f"""
                    <html>

                    <body
                        style="
                        font-family:Arial,sans-serif;
                        line-height:1.6;
                        "
                    >

                    <h2>
                        ExpenseWise Budget Alert
                    </h2>

                    <p>
                        Hello {name},
                    </p>

                    <p>
                        You have used
                        <strong>
                            {percentage:.1f}%
                        </strong>
                        of your monthly budget.
                    </p>

                    <p>

                        <strong>
                            Monthly Budget:
                        </strong>
                        ₹{budget_amount:.2f}

                        <br>

                        <strong>
                            Total Spent:
                        </strong>
                        ₹{spent_amount:.2f}

                        <br>

                        <strong>
                            Budget Used:
                        </strong>
                        {percentage:.1f}%

                    </p>

                    <p>
                        You have reached the
                        <strong>
                            {threshold}%
                        </strong>
                        budget threshold.
                    </p>

                    <p>
                        Please review your expenses
                        in ExpenseWise.
                    </p>

                    <p>
                        Regards,<br>
                        <strong>
                            ExpenseWise Team
                        </strong>
                    </p>

                    </body>
                    </html>
                    """
            }
        )

        print(
            f"Budget email sent to "
            f"{user.email} for "
            f"{threshold}% threshold."
        )

        return True

    except Exception as error:

        print(
            f"Email sending failed: "
            f"{error}"
        )

        return False


# =========================================================
# CHECK ONE USER BUDGET
# =========================================================

def check_user_budget(user_id):

    with app.app_context():

        current_month = (
            datetime.utcnow()
            .strftime("%Y-%m")
        )

        user = db.session.get(
            User,
            user_id
        )

        if user is None:
            return

        budget = Budget.query.filter_by(
            user_id=user.id
        ).first()

        if (
            budget is None
            or budget.amount <= 0
        ):
            return

        expenses = Expense.query.filter_by(
            user_id=user.id
        ).all()

        spent_amount = 0.0

        for expense in expenses:

            if (
                str(expense.date or "")[:7]
                == current_month
            ):

                spent_amount += float(
                    expense.amount or 0
                )

        percentage = (
            spent_amount
            / float(budget.amount)
            * 100
        )

        if percentage >= 100:

            threshold = "100"

        elif percentage >= 90:

            threshold = "90"

        elif percentage >= 75:

            threshold = "75"

        else:

            return

        if already_sent(
            user.id,
            current_month,
            threshold
        ):

            return

        sent = send_budget_email(
            user,
            budget.amount,
            spent_amount,
            percentage,
            threshold
        )

        if sent:

            record_notification(
                user.id,
                current_month,
                threshold
            )


# =========================================================
# CHECK ALL USERS
# =========================================================

def check_budgets():

    with app.app_context():

        user_ids = [

            user.id

            for user
            in User.query.with_entities(
                User.id
            ).all()

        ]

        for user_id in user_ids:

            check_user_budget(
                user_id
            )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    check_budgets()