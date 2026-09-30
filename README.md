# ExpenseWise 💰

### Smart Student Expense Tracker & Spending Analyzer

ExpenseWise is a web-based expense management application designed to help students track their daily spending, manage monthly budgets, analyze spending patterns, and receive budget alerts.

🔗 **Live Demo:** https://expensewise-aehc.onrender.com/

---

## 📌 Project Overview

Managing daily expenses can be difficult for students because spending is often spread across food, travel, education, entertainment, shopping, and other categories.

ExpenseWise provides a centralized platform where users can:

- Record and manage expenses
- Automatically categorize expenses using an AI-based prediction model
- Set monthly budgets
- Monitor budget utilization
- Analyze spending patterns
- Receive budget threshold email notifications
- Secure their data through individual user accounts

---

## ✨ Features

### 🔐 User Authentication
- User registration
- Login and logout
- Password hashing
- Remember Me functionality
- User-specific expense and budget data

### 💸 Expense Management
- Add expenses
- Edit expenses
- Delete expenses
- Automatic date handling
- Expense descriptions and categories
- Input validation

### 🤖 AI-Based Category Prediction
ExpenseWise uses a lightweight Naive Bayes classification model implemented in Python to suggest an expense category based on the description.

Example:

```text
"Pizza with friends"
        ↓
AI Category Prediction
        ↓
Food