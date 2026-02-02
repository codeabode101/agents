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
from sys import argv

from codeabode_model import *

is_retriable = lambda e: (isinstance(e, genai.errors.APIError) and e.code in {429, 503})

genai.models.Models.generate_content = retry.Retry(
    predicate=is_retriable)(genai.models.Models.generate_content)

dotenv.load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(
    api_key=GEMINI_API_KEY,
)

# connect to the database and upload for a student
conn = psycopg2.connect(
    os.getenv("DB_URL")
)

cur = conn.cursor()


if len(argv) == 1 or argv[1] == "help":
    print(
 """Usage: ./codeabode.py [COMMAND]

Commands:
    init, i - initialize the database
    curriculum, c - generate a curriculum
    classwork, w - generate a classwork
    homework, hw, h - generate a homework
    refiner, refine, r - refine a curriculum
"""
    )

elif argv[1] in ["init", "i"]:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            age INTEGER NOT NULL,
            current_level TEXT NOT NULL,
            final_goal TEXT NOT NULL,
            future_concepts TEXT[] NOT NULL,
            notes TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students_classes (
            student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
            class_id SERIAL PRIMARY KEY,
            status VARCHAR(15) NOT NULL,
            name TEXT NOT NULL,

            -- if status == "upcoming"
            relevance TEXT,
            methods TEXT[],
            stretch_methods TEXT[],

            -- if status == "assessment"
            skills_tested TEXT[],
            description TEXT,

            classwork TEXT,
            notes TEXT,
            hw TEXT,
            hw_notes TEXT
        );
        """
    )
elif argv[1] in ["curriculum", "curc", "c"]:
    message = input("> ")

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=GenerateContentConfig(
            system_instruction=[curcgpt_prompt],
            response_mime_type="application/json",
            response_schema=Curriculum,
        ),
    )

    response = chat.send_message(message)
    print(response.text)

    next = input("(m)odify or (u)pload? ")

    while next == "m":
        message = input("> ")

        response = chat.send_message(message)
        print(response.text)
        next = input("(m)odify or (u)pload? ")


    name = input("Name: ")
    age = input("Age: ")

    cur.execute(
        """
        INSERT INTO students (name, age, current_level, final_goal, future_concepts)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, age, response.parsed.current_level, response.parsed.final_goal,
        response.parsed.future_concepts)
    )

    student_id = cur.fetchone()[0]

    execute_values(cur, "INSERT INTO students_classes \
                (student_id, status, name, relevance, \
                methods, stretch_methods, skills_tested, description)\
                VALUES %s", 

                [(student_id, x.status, x.name, x.relevance, 
                x.methods, x.stretch_methods, x.skills_tested, 
                x.description) for x in response.parsed.classes])
elif argv[1] in ["classwork", "cw", "w"]:
    cur.execute("select name, id from students")

    students = cur.fetchall()

    choice = -1 
    while choice > len(students) or choice < 0:
        i = 0
        while i < len(students):
            print(f"{i}: {students[i][0]}")
            i += 1

        print("Please choose a student from the list")
        choice = int(input("> "))

    print(f"Generating class notes for {students[choice][0]}")

    cur.execute(
        sql.SQL("""
            SELECT 
                s.age,
                s.current_level, 
                s.notes,
                sc.name, 
                sc.relevance, 
                sc.methods, 
                sc.stretch_methods, 
                sc.skills_tested, 
                sc.description,
                sc.class_id,
                sc.classwork
            FROM students_classes sc
            JOIN students s ON s.id = sc.student_id
            WHERE sc.student_id = {student_id}
            AND sc.status = 'upcoming'
            ORDER BY sc.class_id ASC
            LIMIT 1
        """).format(student_id=sql.Literal(students[choice][1]))
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

    """ 

    if current_class[10] is not None:
        message += "Here are the old class notes: \n\n" + current_class[10]

    print(message)

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=GenerateContentConfig(
            system_instruction=[classnotesgpt_prompt],
        ),
    )


    response = chat.send_message(
    f"""
    {message}
    Teacher notes:
    {input("> ")}
    """)

    print(response.text)

    next = input("(m)odify or (u)pload? ")

    while next == "m":
        message = input("> ")

        response = chat.send_message(message)
        print(response.text)
        next = input("(m)odify or (u)pload? ")

    # upload the class notes
    cur.execute(
        """
        UPDATE students_classes
        SET classwork = %s
        WHERE class_id = %s
        """,
        (response.text, current_class[9])
    )
elif argv[1] in ["homework", "hw", "h"]:
    cur.execute("select name, id from students")

    students = cur.fetchall()

    choice = -1 
    while choice > len(students) or choice < 0:
        i = 0
        while i < len(students):
            print(f"{i}: {students[i][0]}")
            i += 1

        print("Please choose a student from the list")
        choice = int(input("> "))

    print(f"Generating class notes for {students[choice][0]}")

    cur.execute(
        sql.SQL("""
            SELECT 
                s.age,
                s.current_level, 
                s.notes,
                sc.name, 
                sc.relevance, 
                sc.methods, 
                sc.stretch_methods, 
                sc.skills_tested, 
                sc.description,
                sc.class_id,
                sc.classwork
            FROM students_classes sc
            JOIN students s ON s.id = sc.student_id
            WHERE sc.student_id = {student_id}
            AND sc.status = 'upcoming'
            ORDER BY sc.class_id ASC
            LIMIT 1
        """).format(student_id=sql.Literal(students[choice][1]))
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

    {current_class[10]}


    """ 

    print(message)

    first_msg = input("Enter your notes: ")
    message += first_msg

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=GenerateContentConfig(
            system_instruction=[hwgpt_prompt],
        ),
    )

    response = chat.send_message(message)
    print(response.text)

    next = input("(m)odify or (u)pload? ")

    while next == "m":
        message = input("> ")

        response = chat.send_message(message)
        print(response.text)
        next = input("(m)odify or (u)pload? ")

    # just have an index num saying last class completed r smth
    cur.execute("""
        UPDATE students_classes
        SET hw = %s, 
            notes = %s, 
            status = CASE 
                 WHEN status = 'assessment' THEN 'completed_assessment' 
                 ELSE 'completed' 
              END
        WHERE class_id = (
            SELECT MIN(class_id)
            FROM students_classes
            WHERE student_id = %s
            AND status IN ('upcoming', 'assessment')
        )
        """,
        (response.text, first_msg, students[choice][1])
    )
elif argv[1] in ["refine", "refiner", "curc-refiner", "r"]:
    cur.execute("select name, id from students")

    students = cur.fetchall()

    choice = -1 
    while choice > len(students) or choice < 0:
        i = 0
        while i < len(students):
            print(f"{i}: {students[i][0]}")
            i += 1

        print("Please choose a student from the list")
        choice = int(input("> "))

    print(f"Re-optimizing curriculum for {students[choice][0]}... ")


    cur.execute(
        sql.SQL("""
            SELECT 
                s.age,
                s.current_level, 
                s.notes,
                sc.name, 
                sc.relevance, 
                sc.methods, 
                sc.stretch_methods, 
                sc.skills_tested, 
                sc.description,
                sc.notes,
                sc.hw_notes
            FROM students_classes sc
            JOIN students s ON s.id = sc.student_id
            WHERE sc.student_id = {student_id}
            ORDER BY sc.class_id ASC
        """).format(student_id=sql.Literal(students[choice][1]))
    )

    classes = cur.fetchall()

    if len(classes) == 0:
        print("No upcoming or assessment classes found")
        exit()


    message = f"""
    Age: {classes[0][0]}
    Student Level: {classes[0][1]}
    Student Notes: {classes[0][2]}

    """

    for class_ in classes:
        message += f"""
    ===========================

    Class Name: {class_[3]}
    Relevance: {class_[4]}
    Methods: {class_[5]}
    Stretch Methods: {class_[6]}
    Skills Tested: {class_[7]}
    Description: {class_[8]}
    Teacher notes: {class_[9]}
    Teacher notes on homework: {class_[10]}

    """


    print(message)

    last_hw_notes = input("Enter any notes on the last hw: ")
    cur.execute(
        sql.SQL(
            """UPDATE students_classes
            SET hw_notes = {last_hw_notes}
            WHERE student_id = {student_id}
            AND status IN ('upcoming', 'assessment')
            RETURNING class_id
            """).format(student_id=sql.Literal(students[choice][1]), last_hw_notes=sql.Literal(last_hw_notes)))

    message += f"\n\nLast homework notes: {last_hw_notes}"

    last_class = cur.fetchone()[0]


    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=GenerateContentConfig(
            system_instruction=[curcgpt_refiner_prompt],
            response_mime_type="application/json",
            response_schema=Curriculum,
        ),
    )

    response = chat.send_message(message)
    print(response.text)

    next = input("(m)odify or (u)pload? ")

    while next == "m":
        message = input("> ")

        response = chat.send_message(message)
        print(response.text)
        next = input("(m)odify or (u)pload? ")


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
        SET hw_notes = %s
        WHERE class_id = %s
        """,
        (last_hw_notes, last_class)
    )

    cur.execute(
        """
        DELETE FROM students_classes
        WHERE student_id = %s
        AND status IN ('upcoming', 'assessment')
        """,
        (students[choice][1],)
    )

    execute_values(cur, "INSERT INTO students_classes \
                (student_id, status, name, relevance, \
                methods, stretch_methods, skills_tested, description)\
                VALUES %s", 

                [(students[choice][1], x.status, x.name, x.relevance, 
                x.methods, x.stretch_methods, x.skills_tested, 
                x.description) for x in response.parsed.classes])

conn.commit()

cur.close()
conn.close()
