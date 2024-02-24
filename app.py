import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""
    if request.method == "GET":
        current_cash = db.execute("SELECT cash FROM users WHERE id=:id",
                                  id=session["user_id"])

        user_cash = current_cash[0]['cash']

        transactions = db.execute("SELECT symbol, SUM(shares), price FROM transactions WHERE user_id=:id GROUP BY symbol",
                                  id=session["user_id"])

        current_price = {}
        total_shares = {}
        purchase_price = {}
        percentage_change = {}
        holding = 0

        for transaction in transactions:
            symbol = transaction['symbol']
            current_price[symbol] = lookup(symbol)["price"]
            total_shares[symbol] = transaction['SUM(shares)']
            purchase_price[symbol] = transaction['price']
            holding += current_price[symbol] * total_shares[symbol]
            percentage_change[symbol] = (current_price[symbol] - purchase_price[symbol]) / 100

        total = user_cash + holding

        return render_template("index.html",
                               transactions=transactions,
                               current_price=current_price,
                               total_shares=total_shares,
                               purchase_price=purchase_price,
                               percentage_change=percentage_change,
                               user_cash=user_cash,
                               total=total,
                               usd=usd
                               )

    if request.method == "POST":
        action = request.form.get("action")
        symbol = request.form.get("symbol")
        if action == "Buy now":
            return redirect(url_for('buy', symbol=symbol))

        elif action == "Sell now":
            return redirect(url_for('sell', symbol=symbol))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        # If symbol is not provided
        if not symbol:
            return apology("Missing symbol")

        # If symbol is not valid
        stock = lookup(symbol)
        if stock == None:
            return apology("Invalid symbol")

        # If shares are not provided or are invalid
        try:
            shares = int(request.form.get("shares"))
            if not shares or shares < 1:
                return apology("Invalid shares")
        except ValueError:
            return apology("Invalid shares")

        # If symbol and shares are correct create a table to keep track od transactions
        else:
            user_cash = db.execute("SELECT cash FROM users WHERE id = :id",
                                   id=session["user_id"])

            current_cash = user_cash[0]["cash"]
            price = lookup(symbol)["price"]

            # If user can't afford for purchase
            if current_cash < shares * price:
                return apology("Can't afford")

            else:
                # Create table if it doesn't exist
                db.execute("""
                           CREATE TABLE IF NOT EXISTS transactions
                                (
                                id INTEGER PRIMARY KEY,
                                symbol TEXT,
                                shares INTEGER,
                                price NUM,
                                time DATETIME,
                                user_id INTEGER,
                                FOREIGN KEY(user_id) REFERENCES users(id)
                                )"""
                           )

                db.execute("""
                           INSERT into transactions (symbol, shares, price, time, user_id)
                           VALUES (:symbol, :shares, :price, datetime('now'), :user_id)
                           """,
                           symbol=symbol,
                           shares=shares,
                           price=price,
                           user_id=session["user_id"]
                           )

                # Update user current cash
                total_shares_bought = shares * price
                db.execute("UPDATE users SET cash = cash - :total WHERE id = :user_id",
                           total=total_shares_bought,
                           user_id=session["user_id"])

                flash(f"You have bought {shares} share(s) of {symbol} for {usd(price)} per share!")

                return redirect("/")

    else:
        symbol = request.args.get('symbol')
        if symbol:
            return render_template("buy.html", symbol=symbol)
        else:
            return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT symbol, shares, price, time FROM transactions WHERE user_id = :user_id",
                              user_id=session["user_id"])

    return render_template("history.html",
                           transactions=transactions,
                           usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 403)

        # Query database for username
        user = db.execute("SELECT id, hash FROM users WHERE username = :username",
                          username=username)

        # Ensure username exists and password is correct
        if len(user) != 1 or not check_password_hash(user[0]["hash"], password):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = user[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Missing symbol")

        if not lookup(symbol):
            return apology("Invalid symbol")

        else:
            return redirect(url_for('quoted', symbol=symbol))

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")

        if not username:
            return apology("Please provide your username")

        existing_user = db.execute("SELECT * FROM users WHERE username = :username",
                                   username=username)
        if existing_user:
            return apology("Username already exists")

        password = request.form.get("password")
        if not password:
            return apology("Missing password")

        if not re.match(r"(?=.*[A-Za-z])(?=.*\d)", password):
            return apology("Password must contain at least one letter and one number")

        confirmation = request.form.get("confirmation")
        if confirmation != password:
            return apology("Passwords don't match")

        hashed_password = generate_password_hash(request.form.get("password"))

        db.execute("INSERT into users (username, hash) VALUES (:username, :hash)", username=username, hash=hashed_password)
        session["user_id"] = db.execute("SELECT id FROM users WHERE username = :username", username=username)[0]['id']
        return redirect("/")

    else:

        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        # If symbol is not provided
        if not symbol:
            return apology("Missing symbol")

        # If symbol is valid
        owned = db.execute("SELECT symbol, SUM(shares) AS shares FROM transactions WHERE user_id = :user_id GROUP BY symbol",
                           user_id=session["user_id"]
                           )

        symbol_exists = False
        for stock in owned:
            if symbol == stock['symbol']:
                symbol_exists = True
                shares_for_sale = int(request.form.get("shares"))
                owned_shares = stock['shares']

                if shares_for_sale > owned_shares:
                    return apology("Too many shares")

                sold_shares = -shares_for_sale
               # print(sold_shares)

                price = lookup(symbol)["price"]

                total_shares_sold = shares_for_sale * price

                db.execute("""
                           INSERT INTO transactions (symbol, shares, price, time, user_id)
                           VALUES (:symbol, :shares, :price, datetime('now'), :user_id)
                           """,
                           symbol=symbol,
                           shares=sold_shares,
                           price=price,
                           user_id=session["user_id"]
                           )

                db.execute("UPDATE users SET cash = cash + :total WHERE id = :user_id",
                           total=total_shares_sold,
                           user_id=session["user_id"])

                flash(f"You have sold {shares_for_sale} shares of {symbol} for {usd(price)} per share!")

                return redirect("/")

        if not symbol_exists:
            return apology("Symbol not owned")

    else:
        # For symbol in owned
        owned = db.execute("SELECT symbol, SUM(shares) AS shares FROM transactions WHERE user_id=:user_id GROUP BY symbol",
                           user_id=session["user_id"])

        symbol = request.args.get('symbol')
        if symbol:
            return render_template("sell.html", owned=owned, symbol=symbol)
        else:
            return render_template("sell.html", owned=owned)


@app.route("/myprofile", methods=["GET", "POST"])
def myprofile():
    """User profile"""
    user = db.execute("SELECT username, cash FROM users WHERE id = :id",
                      id=session["user_id"])
    username = user[0]["username"]
    cash = user[0]["cash"]

    # User submit a form via POST)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "Top Up":
            try:
                topup = int(request.form.get("topup"))
            except ValueError:
                return apology("top up must be a number")

            if not topup:
                return apology("must provide value")

            if topup < 50:
                return apology("minimal top up is $50")

            db.execute("UPDATE users SET cash = cash + :topup WHERE id = :id",
                       topup=topup,
                       id=session["user_id"])

            flash(f"You have successfully added {usd(topup)} to your cash ballance!")

            return redirect("/myprofile")

        # Ensure password was submitted
        elif action == "Change Password":
            password = request.form.get("password")

        if not password:
            return apology("Missing password")

        confirmation = request.form.get("confirmation")
        if confirmation != password:
            return apology("Passwords don't match")

        hashed_password = generate_password_hash(request.form.get("password"))

        db.execute("UPDATE users SET hash = :hash WHERE id = :id",
                   hash=hashed_password,
                   id=session["user_id"])

        flash(f"You have updated your passord successfully!")

        return redirect("/myprofile")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("myprofile.html", username=username, cash=cash, usd=usd)


@app.route("/quoted")
def quoted():
    symbol = request.args.get("symbol")

    stock = lookup(symbol)

    cash = db.execute("SELECT cash FROM users WHERE id = :id",
                      id=session["user_id"])[0]['cash']

    owned = db.execute("SELECT symbol, SUM(shares) AS shares, price FROM transactions WHERE user_id = :user_id GROUP BY symbol",
                       user_id=session["user_id"])

    share_owned = 0
    symbol_exists = False
    for share in owned:
        if symbol == share["symbol"]:
            symbol_exists = True
            share_owned = share["shares"]
            break

    return render_template("quoted.html", symbol_exists=symbol_exists, stock=stock, usd=usd, cash=cash, share_owned=share_owned)
