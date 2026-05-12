#!/usr/bin/env python3
"""
Database setup script - Creates the users table for authentication
Run this script once to set up the users table:
    python setup_db.py
"""

import mysql.connector
from db import get_db

def setup_database():
    """Create the users table if it doesn't exist"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.commit()
        cursor.close()
        db.close()

        print("✓ Database setup complete!")
        print("✓ Users table created successfully")
        print("\nYou can now use the application with login/register functionality.")

    except mysql.connector.Error as err:
        print(f"✗ Database error: {err}")
    except Exception as err:
        print(f"✗ Error: {err}")

if __name__ == "__main__":
    setup_database()
