import re


# =========================================================
# EXPENSE CATEGORY KEYWORDS
# =========================================================

CATEGORY_KEYWORDS = {

    "Food": {
        "food",
        "meal",
        "lunch",
        "dinner",
        "breakfast",
        "restaurant",
        "pizza",
        "burger",
        "sandwich",
        "snacks",
        "snack",
        "canteen",
        "swiggy",
        "zomato",
        "coffee",
        "tea",
        "chai",
        "juice",
    },

    "Transport": {
        "uber",
        "ola",
        "bus",
        "train",
        "metro",
        "auto",
        "cab",
        "taxi",
        "fuel",
        "petrol",
        "diesel",
        "parking",
        "travel",
    },

    "Education": {
        "book",
        "books",
        "course",
        "fees",
        "college",
        "exam",
        "study",
        "notebook",
        "stationery",
        "pen",
        "pencil",
        "project",
        "print",
    },

    "Shopping": {
        "shirt",
        "shoes",
        "clothes",
        "shopping",
        "amazon",
        "flipkart",
        "watch",
        "bag",
        "dress",
        "jeans",
        "purchase",
    },

    "Entertainment": {
        "movie",
        "cinema",
        "netflix",
        "spotify",
        "game",
        "gaming",
        "concert",
        "music",
        "subscription",
        "entertainment",
    },

    "Health": {
        "medicine",
        "doctor",
        "hospital",
        "pharmacy",
        "medical",
        "health",
        "gym",
        "fitness",
        "tablet",
    },

    "Bills": {
        "electricity",
        "water",
        "internet",
        "wifi",
        "recharge",
        "bill",
        "phone",
        "mobile",
        "rent",
    },
}


# =========================================================
# TOKENIZER
# =========================================================

def tokenize(text):

    return re.findall(
        r"[a-z0-9]+",
        text.lower()
    )


# =========================================================
# CATEGORY PREDICTION
# =========================================================

def predict_category(description):

    tokens = set(
        tokenize(description)
    )

    best_category = "Other"

    best_score = 0

    for category, keywords in (
        CATEGORY_KEYWORDS.items()
    ):

        score = len(
            tokens.intersection(
                keywords
            )
        )

        if score > best_score:

            best_score = score

            best_category = category

    return best_category


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    tests = [

        "pizza and coffee",

        "metro ticket",

        "python programming book",

        "new shoes",

        "movie ticket",

        "medicine",

        "wifi bill",

    ]

    for item in tests:

        print(
            f"{item} -> "
            f"{predict_category(item)}"
        )