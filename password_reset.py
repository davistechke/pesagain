import sqlite3
import os
from werkzeug.security import generate_password_hash

# Must match DB_PATH in app.py
DB_NAME = "app_database.db"

def reset_password():
    print("="*30)
    print("GAINPESA DB PASSWORD RESET")
    print("="*30)
    
    if not os.path.exists(DB_NAME):
        print(f"Error: {DB_NAME} not found. Please run app.py first.")
        return

    email = input("Enter user email: ").strip()
    new_pw = input("Enter new password: ").strip()

    if len(new_pw) < 4:
        print("Error: Password too short.")
        return

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check existence
        cursor.execute("SELECT username FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()

        if row:
            hashed_pw = generate_password_hash(new_pw)
            cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed_pw, email))
            conn.commit()
            print(f"SUCCESS: Password for {row[0]} ({email}) has been updated.")
        else:
            print("ERROR: User email not found in database.")

    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_password()