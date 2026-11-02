import mysql.connector
import os
from dotenv import load_dotenv

def get_db():
    load_dotenv()
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DB")
    )
<<<<<<< HEAD
=======

print("Hello")
>>>>>>> origin/main
