import os
from datetime import datetime

import resend

from app import (
    app,
    db,
    User,
    Expense,
    Budget,
    budget_notification
)


RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def already_sent(user_id, month, notification_type):
    result = db.session.execute(
        db.select(budget_notification).where(
            budget_notification.c.user_id == user_id,
            budget_notification.c.month == month,
            budget_notification.c.notification_type == notification_type
        )
    ).first()

    return result is not None


def record_notification(user_id, month, notification_type):
    db.session.execute(
        budget_notification.insert().values(
            user_id=user_id,
            month=month,
            notification_type=notification_type,
            created_at=datetime.utcnow()
        )
    )
    db.session.commit()


def send_budget_email(
    user,
    budget_amount,
    spent_amount,
    percentage,
    threshold
):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY is not configured.")
        return False

    try:
        resend.Emails.send(
            {
                "from": "ExpenseWise <onboarding@resend.dev>",
                "to": [user.email],
                "subject": (
                    f"ExpenseWise Budget Alert - {threshold}% Used"
                ),
                "html": f"""
                <html>
                <body>
                    <h2>ExpenseWise Budget Alert</h2>

                    <p>Hello {user.name},</p>

                    <p>
                        You have used
                        <strong>{percentage:.1f}%</strong>
                        of your monthly budget.
                    </p>

                    <p>
                        <strong>Monthly Budget:</strong>
                        ₹{budget_amount:.2f}<br>
                        <strong>Total Spent:</strong>
                        ₹{spent_amount:.2f}<br>
                        <strong>Budget Used:</strong>
                        {percentage:.1f}%
                    </p>

                    <p>
                        You have reached the
                        <strong>{threshold}%</strong>
                        budget threshold.
                    </p>

                    <p>
                        Please review your expenses in ExpenseWise.
                    </p>

                    <br>

                    <p>
                        Regards,<br>
                        <strong>ExpenseWise</strong>
                    </p>
                </body>
                </html>
                """
            }
        )

        print(
            f"Budget email sent to {user.email} "
            f"for {threshold}% threshold."
        )

        return True

    except Exception as error:
        print(f"Email sending failed: {error}")
        return False


def check_user_budget(user_id):
    """
    Check one user's current-month spending and send the
    highest reached budget alert (75%, 90%, or 100%).
    """

    with app.app_context():
        current_month = datetime.utcnow().strftime("%Y-%m")

        user = db.session.get(User, user_id)

        if user is None:
            return

        budget = Budget.query.filter_by(
            user_id=user.id
        ).first()

        if budget is None or budget.amount <= 0:
            return

        expenses = Expense.query.filter_by(
            user_id=user.id
        ).all()

        spent_amount = 0.0

        for expense in expenses:
            expense_date = str(expense.date or "")

            if expense_date[:7] == current_month:
                spent_amount += float(expense.amount or 0)

        percentage = (
            spent_amount / budget.amount
        ) * 100

        threshold = None

        if percentage >= 100:
            threshold = "100"
        elif percentage >= 90:
            threshold = "90"
        elif percentage >= 75:
            threshold = "75"

        if threshold is None:
            return

        if already_sent(
            user.id,
            current_month,
            threshold
        ):
            return

        email_sent = send_budget_email(
            user,
            budget.amount,
            spent_amount,
            percentage,
            threshold
        )

        if email_sent:
            record_notification(
                user.id,
                current_month,
                threshold
            )


def check_budgets():
    """Check all users. Useful for manual testing or future scheduling."""

    with app.app_context():
        users = User.query.all()

        for user in users:
            check_user_budget(user.id)


if __name__ == "__main__":
    check_budgets()
