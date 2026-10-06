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

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

RESEND_FROM_EMAIL = os.environ.get(
    "RESEND_FROM_EMAIL",
    "ExpenseWise <onboarding@resend.dev>",
)

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


# =========================================================
# COMMON EMAIL SENDER
# =========================================================

def send_email(
    user,
    subject,
    html,
    email_type,
    force=False,
):
    """
    Send an email to the user.

    force=True is used for important emails such as
    the welcome email.

    Normal notification emails respect the user's
    email_notifications preference.
    """

    if not RESEND_API_KEY:
        print("RESEND_API_KEY is not configured.")
        return False

    if not user or not user.email:
        print("User email is missing.")
        return False

    if not force and not getattr(
        user,
        "email_notifications",
        True,
    ):
        print(
            f"Email notifications disabled for "
            f"{user.email}."
        )
        return False

    try:

        response = resend.Emails.send(
            {
                "from": RESEND_FROM_EMAIL,

                "to": [
                    user.email
                ],

                "subject": subject,

                "html": html,

                "tags": [
                    {
                        "name": "type",
                        "value": email_type,
                    }
                ],
            },

            {
                "idempotencyKey":
                    f"{email_type}-{user.id}-"
                    f"{datetime.utcnow().timestamp()}"
            }
        )

        print(
            f"Email sent successfully: "
            f"{email_type} -> {user.email}"
        )

        print(
            f"Resend response: {response}"
        )

        return True

    except Exception as error:

        print(
            f"Email sending failed "
            f"({email_type}): {error}"
        )

        return False


# =========================================================
# EMAIL LAYOUT
# =========================================================

def email_layout(
    title,
    greeting,
    content,
):
    return f"""
    <!DOCTYPE html>

    <html>

    <head>

        <meta charset="UTF-8">

        <meta name="viewport"
              content="width=device-width,
                       initial-scale=1.0">

    </head>


    <body
        style="
            margin:0;
            padding:0;
            background:#f5f7fb;
            font-family:Arial,
                         Helvetica,
                         sans-serif;
            color:#172033;
        "
    >

        <div
            style="
                max-width:650px;
                margin:30px auto;
                padding:20px;
            "
        >

            <div
                style="
                    background:#172554;
                    color:white;
                    padding:24px;
                    border-radius:16px 16px 0 0;
                    text-align:center;
                "
            >

                <div
                    style="
                        font-size:30px;
                        font-weight:bold;
                    "
                >
                    ₹ ExpenseWise
                </div>

                <div
                    style="
                        margin-top:6px;
                        opacity:.9;
                        font-size:14px;
                    "
                >
                    Smart Student Expense Tracker
                </div>

            </div>


            <div
                style="
                    background:white;
                    padding:30px;
                    border-radius:0 0 16px 16px;
                    border:1px solid #e5e7eb;
                "
            >

                <h1
                    style="
                        margin-top:0;
                        color:#172554;
                        font-size:24px;
                    "
                >
                    {title}
                </h1>


                <p>
                    {greeting}
                </p>


                {content}


                <hr
                    style="
                        border:0;
                        border-top:1px solid #e5e7eb;
                        margin:30px 0;
                    "
                >


                <p
                    style="
                        color:#667085;
                        font-size:13px;
                        margin-bottom:0;
                    "
                >
                    Regards,<br>
                    <strong>
                        ExpenseWise Team
                    </strong>
                </p>

            </div>

        </div>

    </body>

    </html>
    """


# =========================================================
# BUDGET SUMMARY
# =========================================================

def get_budget_summary(user_id):

    current_month = (
        datetime.utcnow()
        .strftime("%Y-%m")
    )

    budget = Budget.query.filter_by(
        user_id=user_id
    ).first()

    budget_amount = (
        float(budget.amount)
        if budget
        else 0.0
    )

    expenses = Expense.query.filter_by(
        user_id=user_id
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

    remaining_amount = (
        budget_amount - spent_amount
    )

    percentage = (
        (spent_amount / budget_amount) * 100
        if budget_amount > 0
        else 0
    )

    return (
        budget_amount,
        spent_amount,
        remaining_amount,
        percentage,
    )


# =========================================================
# WELCOME EMAIL
# =========================================================

def send_welcome_email(user):

    name = escape(
        user.name
    )

    budget_amount = 10000

    content = f"""

    <p>
        Your ExpenseWise account has been
        created successfully. 🎉
    </p>


    <div
        style="
            background:#f8fafc;
            padding:18px;
            border-radius:12px;
            margin:20px 0;
        "
    >

        <strong>Account Email</strong>

        <div style="margin-top:6px;">
            {escape(user.email)}
        </div>

        <br>

        <strong>Starting Monthly Budget</strong>

        <div style="margin-top:6px;">
            ₹{budget_amount:,.2f}
        </div>

    </div>


    <h3>
        What you can do with ExpenseWise
    </h3>


    <ul>

        <li>
            Track your daily expenses
        </li>

        <li>
            Get automatic expense categories
        </li>

        <li>
            Manage your monthly budget
        </li>

        <li>
            View spending analytics
        </li>

        <li>
            Receive budget threshold alerts
        </li>

        <li>
            Receive expense activity emails
        </li>

    </ul>


    <p>
        Welcome to ExpenseWise,
        <strong>{name}</strong>!
    </p>

    """

    html = email_layout(
        "Welcome to ExpenseWise! 🎉",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        "Welcome to ExpenseWise! 🎉",
        html,
        "welcome",
        force=True,
    )


# =========================================================
# EXPENSE ADDED EMAIL
# =========================================================

def send_expense_added_email(
    user,
    expense,
):

    (
        budget_amount,
        spent_amount,
        remaining_amount,
        percentage,
    ) = get_budget_summary(
        user.id
    )

    name = escape(
        user.name
    )

    description = escape(
        expense.description
    )

    category = escape(
        expense.category
    )

    content = f"""

    <p>
        Your expense has been added successfully.
    </p>


    <div
        style="
            background:#f8fafc;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Expense Details
        </h3>


        <p>
            <strong>Description:</strong>
            {description}
        </p>


        <p>
            <strong>Amount:</strong>
            ₹{float(expense.amount):,.2f}
        </p>


        <p>
            <strong>Category:</strong>
            {category}
        </p>


        <p>
            <strong>Date:</strong>
            {escape(str(expense.date))}
        </p>


        <p>
            <strong>Expense ID:</strong>
            #{expense.id}
        </p>

    </div>


    <div
        style="
            margin-top:20px;
            background:#eef4ff;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Current Budget Summary
        </h3>


        <p>
            <strong>Monthly Budget:</strong>
            ₹{budget_amount:,.2f}
        </p>


        <p>
            <strong>Total Spent:</strong>
            ₹{spent_amount:,.2f}
        </p>


        <p>
            <strong>Remaining:</strong>
            ₹{remaining_amount:,.2f}
        </p>


        <p>
            <strong>Budget Used:</strong>
            {percentage:.1f}%
        </p>

    </div>


    <p>
        Hello {name}, your ExpenseWise
        records have been updated.
    </p>

    """

    html = email_layout(
        "Expense Added 🧾",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        "ExpenseWise - Expense Added 🧾",
        html,
        f"expense-added-{expense.id}",
    )


# =========================================================
# EXPENSE UPDATED EMAIL
# =========================================================

def send_expense_updated_email(
    user,
    expense,
    old_description,
    old_amount,
    old_category,
    old_date,
):

    (
        budget_amount,
        spent_amount,
        remaining_amount,
        percentage,
    ) = get_budget_summary(
        user.id
    )

    name = escape(
        user.name
    )

    content = f"""

    <p>
        Your expense has been updated successfully.
    </p>


    <div
        style="
            background:#fff7ed;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Previous Details
        </h3>

        <p>
            <strong>Description:</strong>
            {escape(str(old_description))}
        </p>

        <p>
            <strong>Amount:</strong>
            ₹{old_amount:,.2f}
        </p>

        <p>
            <strong>Category:</strong>
            {escape(str(old_category))}
        </p>

        <p>
            <strong>Date:</strong>
            {escape(str(old_date))}
        </p>

    </div>


    <div
        style="
            margin-top:20px;
            background:#eef4ff;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Updated Details
        </h3>

        <p>
            <strong>Description:</strong>
            {escape(str(expense.description))}
        </p>

        <p>
            <strong>Amount:</strong>
            ₹{float(expense.amount):,.2f}
        </p>

        <p>
            <strong>Category:</strong>
            {escape(str(expense.category))}
        </p>

        <p>
            <strong>Date:</strong>
            {escape(str(expense.date))}
        </p>

    </div>


    <div
        style="
            margin-top:20px;
            background:#f8fafc;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Current Budget
        </h3>

        <p>
            <strong>Budget:</strong>
            ₹{budget_amount:,.2f}
        </p>

        <p>
            <strong>Spent:</strong>
            ₹{spent_amount:,.2f}
        </p>

        <p>
            <strong>Remaining:</strong>
            ₹{remaining_amount:,.2f}
        </p>

        <p>
            <strong>Used:</strong>
            {percentage:.1f}%
        </p>

    </div>

    """

    html = email_layout(
        "Expense Updated ✏️",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        "ExpenseWise - Expense Updated ✏️",
        html,
        f"expense-updated-{expense.id}",
    )


# =========================================================
# EXPENSE DELETED EMAIL
# =========================================================

def send_expense_deleted_email(
    user,
    expense_id,
    description,
    amount,
    category,
    expense_date,
):

    (
        budget_amount,
        spent_amount,
        remaining_amount,
        percentage,
    ) = get_budget_summary(
        user.id
    )

    name = escape(
        user.name
    )

    content = f"""

    <p>
        The following expense was deleted
        from your ExpenseWise account.
    </p>


    <div
        style="
            background:#fef2f2;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Deleted Expense
        </h3>

        <p>
            <strong>Description:</strong>
            {escape(str(description))}
        </p>

        <p>
            <strong>Amount:</strong>
            ₹{amount:,.2f}
        </p>

        <p>
            <strong>Category:</strong>
            {escape(str(category))}
        </p>

        <p>
            <strong>Date:</strong>
            {escape(str(expense_date))}
        </p>

        <p>
            <strong>Expense ID:</strong>
            #{expense_id}
        </p>

    </div>


    <div
        style="
            margin-top:20px;
            background:#f8fafc;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Updated Budget Summary
        </h3>

        <p>
            <strong>Monthly Budget:</strong>
            ₹{budget_amount:,.2f}
        </p>

        <p>
            <strong>Total Spent:</strong>
            ₹{spent_amount:,.2f}
        </p>

        <p>
            <strong>Remaining:</strong>
            ₹{remaining_amount:,.2f}
        </p>

        <p>
            <strong>Budget Used:</strong>
            {percentage:.1f}%
        </p>

    </div>

    """

    html = email_layout(
        "Expense Deleted 🗑️",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        "ExpenseWise - Expense Deleted 🗑️",
        html,
        f"expense-deleted-{expense_id}",
    )


# =========================================================
# BUDGET UPDATED EMAIL
# =========================================================

def send_budget_updated_email(
    user,
    old_budget,
    new_budget,
):

    (
        budget_amount,
        spent_amount,
        remaining_amount,
        percentage,
    ) = get_budget_summary(
        user.id
    )

    name = escape(
        user.name
    )

    content = f"""

    <p>
        Your monthly budget has been updated.
    </p>


    <div
        style="
            background:#eef4ff;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Budget Update
        </h3>

        <p>
            <strong>Previous Budget:</strong>
            ₹{old_budget:,.2f}
        </p>

        <p>
            <strong>New Budget:</strong>
            ₹{new_budget:,.2f}
        </p>

    </div>


    <div
        style="
            margin-top:20px;
            background:#f8fafc;
            padding:20px;
            border-radius:12px;
        "
    >

        <h3>
            Current Spending
        </h3>

        <p>
            <strong>Total Spent:</strong>
            ₹{spent_amount:,.2f}
        </p>

        <p>
            <strong>Remaining:</strong>
            ₹{remaining_amount:,.2f}
        </p>

        <p>
            <strong>Budget Used:</strong>
            {percentage:.1f}%
        </p>

    </div>


    <p>
        Hello {name}, your ExpenseWise
        budget has been updated successfully.
    </p>

    """

    html = email_layout(
        "Budget Updated 💰",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        "ExpenseWise - Budget Updated 💰",
        html,
        f"budget-updated-{user.id}-{datetime.utcnow().timestamp()}",
    )


# =========================================================
# CHECK EXISTING BUDGET NOTIFICATION
# =========================================================

def already_sent(
    user_id,
    month,
    notification_type,
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
# RECORD BUDGET NOTIFICATION
# =========================================================

def record_notification(
    user_id,
    month,
    notification_type,
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
# BUDGET ALERT EMAIL
# =========================================================

def send_budget_email(
    user,
    budget_amount,
    spent_amount,
    percentage,
    threshold,
):

    name = escape(
        user.name
    )

    if threshold == "75":

        emoji = "⚠️"
        title = "Budget Alert - 75% Used"

    elif threshold == "90":

        emoji = "🚨"
        title = "Budget Alert - 90% Used"

    else:

        emoji = "🔴"
        title = "Budget Alert - 100% Used"


    remaining = (
        budget_amount - spent_amount
    )


    content = f"""

    <p>
        Your monthly spending has reached
        the <strong>{threshold}%</strong>
        budget threshold.
    </p>


    <div
        style="
            background:#fff7ed;
            padding:20px;
            border-radius:12px;
        "
    >

        <p>
            <strong>Monthly Budget:</strong>
            ₹{budget_amount:,.2f}
        </p>

        <p>
            <strong>Total Spent:</strong>
            ₹{spent_amount:,.2f}
        </p>

        <p>
            <strong>Remaining:</strong>
            ₹{remaining:,.2f}
        </p>

        <p>
            <strong>Budget Used:</strong>
            {percentage:.1f}%
        </p>

        <p>
            <strong>Threshold:</strong>
            {threshold}%
        </p>

    </div>


    <p>
        Please review your expenses and
        manage your remaining budget carefully.
    </p>

    """

    html = email_layout(
        f"{title} {emoji}",
        f"Hello {name},",
        content,
    )

    return send_email(
        user,
        f"ExpenseWise - {title} {emoji}",
        html,
        f"budget-alert-{user.id}-{threshold}",
    )


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
            user_id,
        )

        if user is None:
            return

        if not getattr(
            user,
            "email_notifications",
            True,
        ):
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
            threshold,
        ):
            return


        sent = send_budget_email(
            user,
            float(budget.amount),
            spent_amount,
            percentage,
            threshold,
        )


        if sent:

            record_notification(
                user.id,
                current_month,
                threshold,
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