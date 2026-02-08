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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(
    api_key=GEMINI_API_KEY,
)

# connect to the database and upload for a student
conn = psycopg2.connect(
    os.getenv("DB_URL")
)

cur = conn.cursor()

def get_finished_response(client, model, config, initial_message):
    """
    Get a finished response from the chat, with options to modify, restart, upload, or save.
    
    Args:
        client: The Gemini API client
        model: The model to use
        config: Model configuration
        initial_message: The initial message to send
    
    Returns:
        The final response from the model
    """

    chat = client.chats.create(model=model, config=config)
    chat_history = []  # Track conversation manually if API doesn't provide it
    
    # Store initial message and response
    response = chat.send_message(initial_message)
    chat_history.append({"role": "user", "content": initial_message})
    chat_history.append({"role": "assistant", "content": response.text})
    
    print(response.text)
    
    next_choice = input("(m)odify, (r)estart, (u)pload, or (s)ave? ").lower()
    
    while next_choice in ("m", "r", "s"):
        if next_choice == "r":
            # Create a new chat session (empty history)
            chat = client.chats.create(model=model, config=config)
            chat_history = []  # Reset history
            
            message = input("> ")
            response = chat.send_message(message)
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": response.text})
            print(response.text)
        
        elif next_choice == "m":
            message = input("> ")
            response = chat.send_message(message)
            chat_history.append({"role": "user", "content": message})
            chat_history.append({"role": "assistant", "content": response.text})
            print(response.text)
        
        elif next_choice == "s":
            # Save the entire chat context to a JSON file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chat_history_{timestamp}.json"
            
            try:
                # Prepare comprehensive chat data
                chat_data = {
                    "metadata": {
                        "model": model,
                        "timestamp": timestamp,
                        "config": str(config) if config else None
                    },
                    "conversation": chat_history,
                    "last_response": response.text
                }
                
                # Save to file
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f, indent=2, ensure_ascii=False, default=str)
                
                print(f"✓ Chat saved to {filename}")
                
            except Exception as e:
                print(f"Error saving chat: {e}")
                # Try a simpler save
                try:
                    with open(f"backup_{filename}", 'w', encoding='utf-8') as f:
                        json.dump({
                            "error": str(e),
                            "last_message": initial_message if len(chat_history) == 0 else chat_history[-2]["content"] if len(chat_history) >= 2 else "No history",
                            "last_response": response.text
                        }, f, indent=2)
                    print(f"Backup saved to backup_{filename}")
                except:
                    print("Could not save backup file")
        
        # Ask for next action
        next_choice = input("(m)odify, (r)estart, (u)pload, or (s)ave? ").lower()
    
    return response

def print_with_pager(text):
    """
    Prints a string using the 'less' pager.
    Works on Linux, macOS, and Windows (if less is installed).
    """
    # Start the less process
    pager = subprocess.Popen(['less'], stdin=subprocess.PIPE, text=True)
    
    # Write the text to less's input
    # Use flush=True to ensure all data is sent immediately[citation:3][citation:5]
    try:
        pager.communicate(input=text, timeout=None)
    except KeyboardInterrupt:
        pass  # Allow user to quit with Ctrl+C

if len(argv) == 1 or argv[1] == "help":
    print(
 """Usage: ./codeabode.py [COMMAND]

Commands:
    new, n - create a new student
    continue, cont, c - continue for existing student (from options)
"""
    )

elif argv[1] in ["new", "n"]:
    print("Give me information about the student then hit Ctrl + D.")
    message = stdin.read()
    print("Done reading.")

    response = get_finished_response(
        client, 'gemini-2.5-flash', 
        GenerateContentConfig(
            system_instruction=[curcgpt_prompt],
            response_mime_type="application/json",
            response_schema=Curriculum
        ), message
    )

    name = input("Name: ")
    age = input("Age: ")

    cur.execute(
        """
        INSERT INTO students (name, age, current_level, final_goal, future_concepts, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, age, response.parsed.current_level, response.parsed.final_goal,
        response.parsed.future_concepts, response.parsed.notes)
    )

    student_id = cur.fetchone()[0]

    # Fetch all inserted ids and get the minimum
    inserted_ids = execute_values(
        cur, "INSERT INTO students_classes \
        (student_id, status, name,  \
        methods, stretch_methods, description) \
        VALUES %s \
        RETURNING class_id",  # Add RETURNING clause
        
        [(student_id, 'upcoming', x.name,
        x.methods, x.stretch_methods, x.description) 
        for x in response.parsed.classes],
        fetch=True  # Need to fetch the returned values
    )

    # After executing new classes and before asking for input choice
    lowest_class_id = min([row[0] for row in inserted_ids]) if inserted_ids else None

    cur.execute(
        """
        UPDATE students
        SET current_class = %s
        WHERE id = %s
        """,
        (lowest_class_id, students[choice][1])
    )

    # Get the minimum id

    current_class = response.parsed.classes[0]

    # TODO: assessment on first day?

    input_choice = input("(u)pload or (g)enerate the first class? ")
    response_text = None

    if input_choice == 'g':
        message = f"""
        Age: {age}
        Student Level: {response.parsed.current_level}
        Student Notes: {response.parsed.notes}

        Class Name: {current_class.name}
        Methods: {current_class.methods}
        Stretch Methods: {current_class.stretch_methods}
        Description: {current_class.description}
        This is the first class for the student.

        """ 
        print(message)

        chat = client.chats.create(
            model="gemini-2.5-flash",
            config=GenerateContentConfig(
                system_instruction=[classnotesgpt_prompt],
            ),
        )


        response_text = get_response(chat, 
            f"""
            {message}
            Teacher notes:
            {input("> ")}
            """
        ).text
    else:
        response_text = stdin.read()

    # upload the class notes
    cur.execute(
        """
        UPDATE students_classes
        SET classwork = %s
        WHERE class_id = %s
        """,
        (response_text, lowest_class_id)
    )

    cur.execute(
        """
        UPDATE students
        SET step = 2
        WHERE id = %s
        """,
        (student_id,)
    )

elif argv[1] in ["continue", "cont", "c"]:
    cur.execute("select name, id, step from students")
    students = cur.fetchall()

    choice = -1 
    while choice > len(students) or choice < 0:
        i = 0
        while i < len(students):
            print(f"{i}: {students[i][0]}")
            i += 1

        print("Please choose a student from the list")
        choice = int(input("> "))

    if students[choice][2] == 1:
        # step 3 no homework, u can assume it may have been more than one class since the last time the system was used (or hw notes will say that lol ig
        print(f"Re-optimizing curriculum for {students[choice][0]}... ")

        cur.execute(
            sql.SQL("""
                SELECT 
                    COUNT(*) FILTER (WHERE sc.status = 'completed') OVER (PARTITION BY sc.student_id) as completed_count,
                    s.age,
                    s.current_level, 
                    s.notes,
                    sc.name, 
                    sc.methods, 
                    sc.stretch_methods, 
                    sc.description,
                    sc.classwork,
                    sc.notes,
                    sc.hw,
                    sc.hw_notes,
                    sc.status
                FROM students_classes sc
                JOIN students s ON s.id = sc.student_id
                WHERE sc.student_id = {student_id}
                ORDER BY sc.class_id ASC
            """).format(student_id=sql.Literal(students[choice][1]))
        )

        # TODO: final goal missing?
        # this can be optimized out
        # they dont need to update everything each time

        classes = cur.fetchall()

        if len(classes) == 0:
            print("No upcoming or assessment classes found")
            exit()

        if classes[0][0] == 0:
            print("No past classes")
            exit()

        curc_message = f"""
        Age: {classes[0][1]}
        Student Level: {classes[0][2]}
        Student Notes: {classes[0][3]}

        """

        last_completed = None
        last_completed_index = -1

        i = 0
        while i < len(classes):
            curc_message += f"""
            ===========================

            Class Name: {classes[i][4]}
            Methods: {classes[i][5]}
            Stretch Methods: {classes[i][6]}
            Description: {classes[i][7]}
            Teacher notes: {classes[i][9]}
            Teacher notes on homework: {classes[i][11]}

            """

            if classes[i][12] == "completed":
                last_completed_index = i
                last_completed = classes[i]

            i += 1

        print_with_pager(curc_message)

        print("Enter any notes on the last hw (Ctrl+D when done): ")
        last_hw_notes = stdin.read()
        print("Done reading.")
        cur.execute(
            sql.SQL(
                """UPDATE students_classes
                SET hw_notes = {last_hw_notes}
                WHERE student_id = {student_id}
                AND status IN ('upcoming', 'assessment')
                RETURNING class_id
                """).format(student_id=sql.Literal(students[choice][1]), last_hw_notes=sql.Literal(last_hw_notes)))

        curc_message += f"\n\nLast homework notes: {last_hw_notes}"

        last_class = cur.fetchone()[0]

        response = get_finished_response(
            client, 'gemini-2.5-flash', 
            GenerateContentConfig(
                system_instruction=[curcgpt_refiner_prompt],
                response_mime_type="application/json",
                response_schema=Curriculum
            ), curc_message
        )

        cur.execute(
            """
            UPDATE students 
            SET current_level = %s, 
                final_goal = %s, 
                future_concepts = %s,
                notes = %s
            WHERE id = %s
            """,
            (response.parsed.current_level, response.parsed.final_goal,
            response.parsed.future_concepts, response.parsed.notes, 
             students[choice][1])
        )

        cur.execute(
            """
            UPDATE students_classes
            SET hw_notes = %s,
            status = 'completed'
            WHERE class_id = %s
            """,
            (last_hw_notes, last_class)
        )

        cur.execute(
            """
            DELETE FROM students_classes
            WHERE student_id = %s
            AND status = 'upcoming'
            """,
            (students[choice][1],)
        )

        execute_values(cur, 
            """
            INSERT INTO students_classes 
            (student_id, status, name,
            methods, stretch_methods, description)
            VALUES %s
            """, 
            [(students[choice][1], 'upcoming', x.name,
            x.methods, x.stretch_methods, 
            x.description) for x in response.parsed.classes]
        )

        # change lowest class

        cur.execute(
            """
            UPDATE students
            SET current_class = (
                SELECT MIN(class_id)
                FROM students_classes
                WHERE student_id = %s
                AND status = 'upcoming'
            )
            WHERE id = %s
            RETURNING current_class
            """,
            (students[choice][1], students[choice][1])
        )

        current_class_num = cur.fetchone()[0]
                        
        input_choice = input("(A)ssessment, 10-(m)inute warm up, (u)pload assignment, (g)enerate, (n)one, or (q)uit: ")
        
            # nerfed assessment then normal class
        if input_choice == "u":
            cur.execute(
                """
                UPDATE students_classes
                SET classwork = %s,
                status = 'completed'
                WHERE class_id = %s
                """,
                (stdin.read(), current_class_num)
            )

        elif input_choice == "q":
            exit()
        elif input_choice == "n":
            print("No class notes this time")

        else:
            print(f"Generating class notes for {students[choice][0]}")

            message = f"""
            Age: {classes[0][1]}
            Student Level: {classes[0][2]}
            Student Notes: {classes[0][3]}

            Previous Class as Context (if you want to bridge new classwork to previous homework):
            {last_completed[4]}
            Methods: {last_completed[5]}
            Stretch Methods: {last_completed[6]}
            Description: {last_completed[7]}
            Classwork Notes: {last_completed[9]}

            Homework:
            {last_completed[10]}

            Homework Notes: {last_completed[11]}

            Class to Generate for:

            """ 

            # TODO: class name, description, stretch_methods removed
            # class notes is "actually taught concepts" because this is made after re-adjusting the curriculum for homework 
            # homework notes is "homework performance" and "homework" can be turned into "homework summary" to save bytes

            # u forgot to add the class after this

            if classes[last_completed_index + 1][8] is not None:
                message += "Here are the old class notes: \n\n" + current_class[10]

            print(message)

            prompt = None
            response = ""
            if input_choice == "a":
                prompt = assessmentgpt_prompt
            elif input_choice == "m":
                response = get_finished_response(
                    client, 'gemini-2.5-flash',
                    GenerateContentConfig(
                        system_instruction=[classwork_with_warmup_prompt],
                    ),
                    f"""
                    {message}
                    Teacher notes:
                    {input("> ")}
                    """
                ).text
                prompt = classnotesgpt_prompt

            else:
                prompt = classnotesgpt_prompt

            response += get_finished_response(
                client, 'gemini-2.5-flash',
                GenerateContentConfig(
                    system_instruction=[prompt],
                ),
                f"""
                {message}
                Teacher notes:
                {input("> ")}
                """
            ).text

            # upload the class notes
            cur.execute(
                """
                UPDATE students_classes
                SET classwork = %s,
                status = 'completed'
                WHERE class_id = %s
                """,
                (response, current_class_num)
            )

        cur.execute(
            """
            UPDATE students
            SET step = 2
            WHERE id = %s
            """,
            (students[choice][1],)
        )

    elif students[choice][2] == 2:
        print(f"Generating homework for {students[choice][0]}")

        cur.execute("""
            SELECT 
                s.age,
                s.current_level, 
                s.notes,
                sc.name, 
                sc.description, 
                sc.methods, 
                sc.stretch_methods, 
                sc.description,
                sc.class_id,
                sc.classwork,
                s.name
            FROM students_classes sc
            JOIN students s ON s.id = sc.student_id
            WHERE sc.class_id = (
                SELECT current_class
                FROM students
                WHERE id = %s
            )
            """,
            (students[choice][1],)
        )

        current_class = cur.fetchone()

        message = f"""
        Age: {current_class[0]}
        Student Level: {current_class[1]}
        Student Notes: {current_class[2]}

        Class Name: {current_class[3]}
        Relevance: {current_class[4]}
        Methods: {current_class[5]}
        Stretch Methods: {current_class[6]}
        Skills Tested: {current_class[7]}
        Description: {current_class[8]}

        Classwork:

        {current_class[9]}


        """ 

        print(message)

        print("How did he do in class? (Ctrl + D to finish)")
        first_msg = stdin.read()
        message += first_msg
        print("\nDone reading.")

        # first we generate the info for CompletedClass and insert that information

        response = get_finished_response(
            client, "gemini-2.5-flash",
            GenerateContentConfig(
                system_instruction=[classanalysis_prompt],
                response_mime_type="application/json",
                response_schema=CompletedClass,
            ),
            message
        )

        message += f"""
        Notes on Class: {response.parsed.notes}
        """

        if response.parsed.taught_methods:
            message += f"""
            Taught Methods: {response.parsed.taught_methods}
            """

        if response.parsed.needs_practice:
            message += f"""
            Stretch Methods: {response.parsed.needs_practice}
            """

        input_choice = input("(u)pload assignment, (5) day, or (c)reative generated: ")
        response_text = None

        if input_choice == "u":
            response_text = stdin.read()
        else:
            prompt = None
            if input_choice == "5":
                prompt = hwgpt_prompt
            elif input_choice == "c":
                prompt = creative_hwgpt_prompt

            response_text = get_finished_response(
                client, 'gemini-2.5-flash', 
                GenerateContentConfig(
                    system_instruction=[prompt],
                ), message
            ).text



        cur.execute(
            """
            UPDATE students_classes
            SET notes = %s,
            taught_methods = %s,
            needs_practice = %s,
            hw = %s
            WHERE class_id = (
                SELECT current_class
                FROM students
                WHERE id = %s
            )
            """,
            (response.parsed.notes, response.parsed.taught_methods, response.parsed.needs_practice, response_text, students[choice][1])
        )

        print("Done. Sending email to student's accounts...")

        cur.execute(
            """
            UPDATE students
            SET step = 1,
            sent_email = false
            WHERE id = %s
            RETURNING account_id 
            """, (students[choice][1],))

        account_id_array = cur.fetchone()[0]

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

            email = os.getenv("EMAIL_ADDRESS")
            password = os.getenv("EMAIL_PASSWORD")
            for account in accounts:
                if account[1]:
                    msg = MIMEMultipart()
                    msg['From'] = f"Codeabode <{email}>"
                    msg['To'] = f"{account[0]} <{account[1]}>"
                    msg['Subject'] = f"Assignment Uploaded for {current_class[10]}"
                    
                    # Create the email body
                    body = f"""
Hi {account[0]},

Your son/daughter completed the {current_class[3]} class. Homework is available at https://app.codeabode.co

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
