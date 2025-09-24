import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASS', ''),
    'db': os.getenv('DB_NAME', 'tel'),
    'cursorclass': pymysql.cursors.DictCursor
}

def get_connection_database():
    return pymysql.connect(**CONFIG)