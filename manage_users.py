#!/usr/bin/env python3
"""
User Management Script - Manage the 3 team member accounts
Only 3 users are allowed in this system.

Usage:
    python manage_users.py add <username> <password>
    python manage_users.py list
    python manage_users.py delete <username>
    python manage_users.py change-password <username> <new_password>
"""

import sys
import hashlib
from db import get_db

def add_user(username, password):
    """Add a new team member"""
    if len(password) < 6:
        print("✗ Password must be at least 6 characters")
        return False

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            print(f"✗ User '{username}' already exists")
            cursor.close()
            db.close()
            return False

        # Check if we already have 3 users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        result = cursor.fetchone()
        if result["count"] >= 3:
            print(f"✗ Cannot add user - maximum 3 users allowed. Current: {result['count']}")
            cursor.close()
            db.close()
            return False

        # Hash password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Add user
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )
        db.commit()
        cursor.close()
        db.close()

        print(f"✓ User '{username}' added successfully")
        return True

    except Exception as err:
        print(f"✗ Error: {err}")
        return False

def list_users():
    """List all team members"""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT id, username, created_at FROM users ORDER BY created_at")
        users = cursor.fetchall()
        cursor.close()
        db.close()

        if not users:
            print("No users found")
            return

        print(f"\n{'ID':<5} {'Username':<20} {'Created':<20}")
        print("-" * 45)
        for user in users:
            print(f"{user['id']:<5} {user['username']:<20} {str(user['created_at']):<20}")
        print(f"\nTotal: {len(users)}/3 team members")

    except Exception as err:
        print(f"✗ Error: {err}")

def delete_user(username):
    """Delete a team member"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        db.commit()

        if cursor.rowcount > 0:
            print(f"✓ User '{username}' deleted successfully")
            cursor.close()
            db.close()
            return True
        else:
            print(f"✗ User '{username}' not found")
            cursor.close()
            db.close()
            return False

    except Exception as err:
        print(f"✗ Error: {err}")
        return False

def change_password(username, new_password):
    """Change a user's password"""
    if len(new_password) < 6:
        print("✗ Password must be at least 6 characters")
        return False

    try:
        db = get_db()
        cursor = db.cursor()

        hashed_password = hashlib.sha256(new_password.encode()).hexdigest()

        cursor.execute(
            "UPDATE users SET password = %s WHERE username = %s",
            (hashed_password, username)
        )
        db.commit()

        if cursor.rowcount > 0:
            print(f"✓ Password for '{username}' changed successfully")
            cursor.close()
            db.close()
            return True
        else:
            print(f"✗ User '{username}' not found")
            cursor.close()
            db.close()
            return False

    except Exception as err:
        print(f"✗ Error: {err}")
        return False

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "add" and len(sys.argv) == 4:
        add_user(sys.argv[2], sys.argv[3])

    elif command == "list":
        list_users()

    elif command == "delete" and len(sys.argv) == 3:
        delete_user(sys.argv[2])

    elif command == "change-password" and len(sys.argv) == 4:
        change_password(sys.argv[2], sys.argv[3])

    else:
        print(__doc__)

if __name__ == "__main__":
    main()
