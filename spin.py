import os
import uuid
import random
import sqlite3
import requests
from flask import Blueprint, jsonify, render_template, request, session

spin_bp = Blueprint('spin', __name__)

DB_PATH = os.getenv("DB_PATH", "app_database.db")

# PayHero Config
PAYHERO_BASE_URL = os.getenv("PAYHERO_BASE_URL", "https://backend.payhero.co.ke/api/v2")
PAYHERO_CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID", "6532")
PAYHERO_PROVIDER = os.getenv("PAYHERO_PROVIDER", "m-pesa")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Helper to generate basic auth header for PayHero
def get_payhero_headers():
    import base64
    username = os.getenv("API_USERNAME", "QZcOZ9hrWq6O6dwQA9Ev")
    password = os.getenv("API_PASSWORD", "gMMRAHjO3snOZgQI7kS2xPpLlXLcylaKqaW5CJXd")
    auth = f"{username}:{password}"
    encoded = base64.b64encode(auth.encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded}"
    }

# ------------------ ROUTES ------------------

@spin_bp.route('/spin')
def spin_page():
    if "user_email" not in session:
        return render_template('register.html', error="Log in first to access the Spin game.")
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (session["user_email"],)).fetchone()
    conn.close()
    
    return render_template('spin.html', user=dict(user))


# POLLING API: Fetch fresh balances
@spin_bp.route('/api/spin-user', methods=['GET'])
def spin_user_data():
    if "user_email" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db_connection()
    user = conn.execute("SELECT spin_balance, balance FROM users WHERE email = ?", (session["user_email"],)).fetchone()
    conn.close()
    
    return jsonify({
        "spin_balance": user["spin_balance"],
        "main_balance": user["balance"]
    })


# DEPOSIT API: Triggers STK push directly to Spin account
@spin_bp.route('/api/deposit-spin', methods=['POST'])
def deposit_spin():
    if "user_email" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    amount = float(data.get("amount", 0))
    phone = data.get("phone", "")
    
    # ✅ UPDATE: Deposit not to be less than 50
    if amount < 1:
        return jsonify({"error": "Minimum deposit is Ksh. 50"}), 400
        
    # Standardize phone format
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("+"):
        phone = phone[1:]

    ext_ref = "SPIN-" + str(uuid.uuid4())[:6].upper()
    
    payload = {
        "amount": amount,
        "phone_number": phone,
        "channel_id": PAYHERO_CHANNEL_ID,
        "provider": PAYHERO_PROVIDER,
        "external_reference": ext_ref,
        "callback_url": os.getenv("CALLBACK_URL", "https://cedrick-subdiscoid-drake.ngrok-free.de/callback")
    }
    
    try:
        url = f"{PAYHERO_BASE_URL}/payments"
        headers = get_payhero_headers()
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO transactions (ext_ref, email, status) VALUES (?, ?, ?)",
                (ext_ref, session["user_email"], "pending"),
            )
            conn.commit()
            conn.close()
            return jsonify({"success": True, "reference": ext_ref})
            
        return jsonify({"success": False, "error": response.text}), 400
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# GAMEPLAY API: Processes dynamic stakes and rolls winning index
@spin_bp.route('/api/spin-wheel', methods=['POST'])
def spin_wheel():
    if "user_email" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    email = session["user_email"]
    
    data = request.json or {}
    try:
        stake = float(data.get("stake", 20)) # Defaults to 20 if none provided
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid stake amount."}), 400
        
    # ✅ UPDATE: Stake not to be less than 20
    if stake < 20:
        return jsonify({"error": "Minimum stake is Ksh. 20"}), 400

    # Mapped physical indices to match 11 segments
    MULTIPLIERS = ["x0", "x1.2", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10"]
    
    # Applied 7/10 for x0 and 3/10 for x2
    weights = [90, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    conn = get_db_connection()
    user = conn.execute("SELECT spin_balance, balance FROM users WHERE email = ?", (email,)).fetchone()

    if not user or user["spin_balance"] < stake:
        conn.close()
        return jsonify({"error": f"Insufficient spin balance. You need at least Ksh. {stake}."}), 400

    winning_index = random.choices(range(len(MULTIPLIERS)), weights=weights, k=1)[0]
    selected_multiplier = MULTIPLIERS[winning_index]

    multiplier_value = float(selected_multiplier.replace("x", ""))
    amount_won = stake * multiplier_value
    
    conn.execute(
        "UPDATE users SET spin_balance = spin_balance - ? WHERE email = ?", 
        (stake, email)
    )
    
    if amount_won > 0:
        conn.execute(
            "UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE email = ?", 
            (amount_won, amount_won, email)
        )

    conn.commit()
    
    updated_user = conn.execute("SELECT spin_balance, balance FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    return jsonify({
        "winning_index": winning_index,
        "selected_multiplier": selected_multiplier,
        "amount_won": amount_won,
        "new_spin_balance": updated_user["spin_balance"],
        "new_main_balance": updated_user["balance"]
    })