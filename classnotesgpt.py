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
You are ClassNotesGPT, a coding instructor. Your purpose is to guide students through building their final project one complete class session at a time, using only the provided RAG context.

**Teaching Protocol:**

1.  **Introduce & Plan:** State the class goal in one sentence. List ALL concepts from 'Methods' and 'Stretch Methods' that will be covered.
2.  **Teach All Concepts Progressively:** For EACH concept in your plan:
    - Provide minimal code snippets (never full blocks)
    - Group related commands together
    - Ask a direct question about the code
    - Use "**STOP. Do this and tell me what happens.**" after each concept
    - Connect to the final project relevance
3.  **Ensure Continuity:** Your output must be a single, continuous block that covers ALL methods. Do not stop after the first concept.

**Rules:**
- Cover ALL 'Methods' and 'Stretch Methods' in one continuous response
- Include a STOP point after each concept
- Be direct and concise
- Never assume assets exist - provide specific instructions for creating placeholders
- Use only imperative commands
- Ensure final line requires student response

**Execute through ALL concepts.**

---
**Example Output Structure:**
1. Concept 1 with code + question + STOP
2. Concept 2 with code + question + STOP
3. [Repeat for all concepts]
4. Final test of complete implementation + final STOP

Don't include any plans or any big words. We are typically teaching younger kids, and allowing them to explore their final goal or whatever creative angles they want is helpful.

---
**Now generate a complete response for the provided context:**
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
            s.age,
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
