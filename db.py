import mysql.connector
import os
from dotenv import load_dotenv

def get_db():
    load_dotenv()
    return mysql.connector.connect(
        host=os.getenv("HOST"),
        user=os.getenv("USER"),
        password=os.getenv("PASSWORD"),
        database=os.getenv("DB")
    )