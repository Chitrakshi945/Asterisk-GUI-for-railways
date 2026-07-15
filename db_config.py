import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="your_username",      #replace with your MySQL username
        password="your_password",  #replace with your MySQL root password
        database="your_database"   #replace with database name you created
    )
