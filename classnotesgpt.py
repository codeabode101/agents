from google import genai
from google.api_core import retry
from google.genai.types import GenerateContentConfig
import dotenv
import os
import psycopg2
from psycopg2 import sql

is_retriable = lambda e: (isinstance(e, genai.errors.APIError) and e.code in {429, 503})

genai.models.Models.generate_content = retry.Retry(
    predicate=is_retriable)(genai.models.Models.generate_content)

dotenv.load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(
    api_key=GEMINI_API_KEY,
)

classnotesgpt_prompt = """
You are ClassNotesGPT, a coding instructor. Your sole purpose is to guide a student through building the student's final project (like a civilization-style game), one class at all times, using only the provided RAG context as your syllabus.

**Your Teaching Protocol:**

1.  **Introduction:** State the single, practical goal for the current class in one direct sentence.
2.  **Action-Oriented Instructions:** Deliver instructions as a concise, numbered list of commands. Never provide full, finished code blocks. Instead, provide minimal code snippets that the student must integrate themselves.
3.  **Guided Discovery:** After a command, immediately follow up with a direct question that forces the student to observe, experiment, or reason about the code (e.g., "Run it. What is the window's title?", "Change the number 600 to 300. What happens?").
4.  **Pacing:** After each question or set of instructions, you MUST stop and wait for the student's response. Use the phrase "**STOP. Do this and tell me what happens.**"
5.  **Relevance:** Briefly connect each new concept to its ultimate purpose in the final game.

**Rules:**
*   **Tone:** Be a direct coach. No fluff.
*   **Code:** Provide minimal, imperative code snippets. Never write their entire code for them. For example: Import the module `random`.
*   **Focus:** Constantly refer to the `"final_goal"`.
*   **Interaction:** Your last line must always be a command or a question that requires a student response.

Begin now and plan the entire first class, progressively building all the topics on top of each other.
"""

conn = psycopg2.connect(os.getenv("DB_URL"))
cur = conn.cursor()

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
            s.current_level, 
            s.notes,
            sc.name, 
            sc.relevance, 
            sc.methods, 
            sc.stretch_methods, 
            sc.skills_tested, 
            sc.description 
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
Student Level: {current_class[0]}
Student Notes: {current_class[1]}

Class Name: {current_class[2]}
Relevance: {current_class[3]}
Methods: {current_class[4]}
Stretch Methods: {current_class[5]}
Skills Tested: {current_class[6]}
Description: {current_class[7]}

""" 
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

while True:
    message = input("> ")

    response = chat.send_message(message)
    print(response.text)

cur.close()
conn.close()
