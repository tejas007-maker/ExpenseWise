import re
from collections import Counter, defaultdict


training_data = [

    # FOOD
    ("pizza", "Food"),
    ("burger", "Food"),
    ("restaurant", "Food"),
    ("food", "Food"),
    ("sandwich", "Food"),
    ("coffee", "Food"),
    ("tea", "Food"),
    ("lunch", "Food"),
    ("dinner", "Food"),
    ("breakfast", "Food"),
    ("snacks", "Food"),
    ("meal", "Food"),
    ("dominos", "Food"),
    ("zomato", "Food"),
    ("swiggy", "Food"),
    ("hotel food", "Food"),
    ("canteen", "Food"),

    # TRAVEL
    ("bus", "Travel"),
    ("train", "Travel"),
    ("uber", "Travel"),
    ("ola", "Travel"),
    ("auto", "Travel"),
    ("taxi", "Travel"),
    ("petrol", "Travel"),
    ("fuel", "Travel"),
    ("travel", "Travel"),
    ("ticket", "Travel"),
    ("metro", "Travel"),
    ("bus pass", "Travel"),
    ("train ticket", "Travel"),
    ("cab", "Travel"),

    # SHOPPING
    ("shirt", "Shopping"),
    ("shoes", "Shopping"),
    ("clothes", "Shopping"),
    ("amazon", "Shopping"),
    ("headphones", "Shopping"),
    ("watch", "Shopping"),
    ("shopping", "Shopping"),
    ("bag", "Shopping"),
    ("tshirt", "Shopping"),
    ("jeans", "Shopping"),
    ("jacket", "Shopping"),
    ("mobile", "Shopping"),
    ("phone", "Shopping"),
    ("accessories", "Shopping"),

    # COLLEGE
    ("notebook", "College"),
    ("books", "College"),
    ("college", "College"),
    ("exam", "College"),
    ("stationery", "College"),
    ("pen", "College"),
    ("project", "College"),
    ("assignment", "College"),
    ("lab", "College"),
    ("practical", "College"),
    ("printing", "College"),
    ("xerox", "College"),
    ("notes", "College"),
    ("engineering books", "College"),
    ("college fees", "College"),

    # ENTERTAINMENT
    ("movie", "Entertainment"),
    ("netflix", "Entertainment"),
    ("game", "Entertainment"),
    ("concert", "Entertainment"),
    ("spotify", "Entertainment"),
    ("entertainment", "Entertainment"),
    ("youtube", "Entertainment"),
    ("prime video", "Entertainment"),
    ("gaming", "Entertainment"),
    ("cinema", "Entertainment"),
    ("subscription", "Entertainment"),
    ("music", "Entertainment")
]


def tokenize(text):

    return re.findall(
        r"\b[a-z]+\b",
        text.lower()
    )


class ExpenseClassifier:

    def __init__(self, data):

        self.class_counts = Counter()

        self.word_counts = defaultdict(
            Counter
        )

        self.total_words = Counter()

        self.vocabulary = set()

        for text, category in data:

            self.class_counts[
                category
            ] += 1

            words = tokenize(text)

            for word in words:

                self.word_counts[
                    category
                ][word] += 1

                self.total_words[
                    category
                ] += 1

                self.vocabulary.add(
                    word
                )

    def predict(self, text):

        words = tokenize(text)

        total_examples = sum(
            self.class_counts.values()
        )

        scores = {}

        for category in self.class_counts:

            probability = (
                self.class_counts[category]
                / total_examples
            )

            for word in words:

                word_count = (
                    self.word_counts[
                        category
                    ][word]
                )

                total = (
                    self.total_words[
                        category
                    ]
                )

                vocabulary_size = len(
                    self.vocabulary
                )

                word_probability = (
                    (word_count + 1)
                    /
                    (
                        total
                        + vocabulary_size
                    )
                )

                probability *= (
                    word_probability
                )

            scores[
                category
            ] = probability

        return max(
            scores,
            key=scores.get
        )


model = ExpenseClassifier(
    training_data
)


def predict_category(description):

    return model.predict(
        description
    )


if __name__ == "__main__":

    test_expenses = [

        "pizza",
        "Uber ride",
        "Amazon headphones",
        "college notebook",
        "Netflix subscription",
        "engineering books",
        "petrol for bike",
        "movie ticket",
        "Swiggy lunch"

    ]

    for expense in test_expenses:

        print(
            expense,
            "->",
            predict_category(expense)
        )