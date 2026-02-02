#!venv/bin/python3
from google import genai
from google.api_core import retry
from google.genai.types import GenerateContentConfig
from typing import Literal, Optional
import dotenv
import os
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from sys import argv, stdin
import subprocess
import smtplib
import ssl
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from codeabode_model import *

is_retriable = lambda e: (isinstance(e, genai.errors.APIError) and e.code in {429, 503})

genai.models.Models.generate_content = retry.Retry(
    predicate=is_retriable)(genai.models.Models.generate_content)

dotenv.load_dotenv(override=True)

# connect to the database and upload for a student
conn = psycopg2.connect(
    os.getenv("DB_URL")
)

cur = conn.cursor()

print("Done. Sending email to student's accounts...")

cur.execute(
    """
    SELECT account_id
    FROM students
    WHERE id = %s
    """, (1,))

account_id_array = cur.fetchone()[0]

print(account_id_array)

if account_id_array:
    cur.execute(
        """
        SELECT name, email
        FROM accounts
        WHERE id = ANY(%s)
        """,
        (account_id_array,)
    )

    accounts = cur.fetchall()

    print(accounts)

    email = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    for account in accounts:
        if account[1]:
            msg = MIMEMultipart()
            msg['From'] = f"Codeabode <{email}>"
            msg['To'] = f"{account[0]} <{account[1]}>"
            msg['Subject'] = "Assignment Uploaded for {current_class[10]}"
            
            # Create the email body
            body = """
Hi {account[0]},

Your son/daughter completed the {current_class[3]} class. Homework is available on the dashboard.

Class info:
Methods taught: {response.parsed.taught_methods}
What needs practice: {response.parsed.needs_practice}
Class Description: {current_class[4]}
Methods intended to be taught: {current_class[5]}
Stretch Methods: {current_class[6]}

Best,
Om
            """

            msg.attach(MIMEText(body, 'plain'))
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(email, password)
                server.send_message(msg)
print("Email sent to student accounts.")

conn.commit()

cur.close()
conn.close()
