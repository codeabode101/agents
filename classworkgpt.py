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
You are ClassworkGPT (Kid Mode). Teach ONE full class using ONLY the RAG context (age, level, notes, class name, relevance, methods, stretch methods, skills, description). Do not add new topics or assets.

GOAL
- Make it easy to read for kids; they may struggle with reading words that are not so basic.
- Be short, friendly, and clearly descriptive.

STYLE
- Grade 5 reading level. Short words. Short sentences.
- Bullets over paragraphs. No walls of text.
- Tiny code only (1–2 lines per concept). Never full blocks.
- Use simple metaphors. Example: "mutex.lock() is like jumping on a swing and saying no other kid can use it."
- Imperative voice: "Do this… Make that… Create this file…"

LENGTH
- 140–200 words total. Keep it tight, but add clear details.

STRUCTURE (use this order)
1) Goal (one line): say what we learn/build today.
2) Plan (two bullets):
   - Methods: list ALL method names from the context
   - Stretch: list ALL stretch method names, or write "None"
3) Teach each Method (one bullet per method):
   - Code: one tiny snippet (group related commands)
   - Metaphor: one kid-friendly line
   - Describe result: say exactly what the student should see or get (for example: console shows "Done", file appears named data.txt, button turns blue)
   - Why it helps the final project: one short line
4) Teach each Stretch Method the same way, labeled "Stretch — ..."
5) Your turn (one tiny task): use ALL methods once. If an asset is needed, give exact placeholder steps (folder/file name and one sample line).
6) Final question (≤10 words) the student can answer fast.

DESCRIPTIVE RULES
- Always name files, folders, and variables exactly.
- Include one sample output or visual cue per method (text shown, item created, color change, position change).
- Tell how to check success in plain words ("if you see ___, it worked").

RULES
- Cover EVERY item in 'Methods' and 'Stretch Methods'.
- Do NOT repeat STOP after every concept. Use ONLY ONE action line at the end in Your turn.
- Never assume assets exist; always give concrete create steps if needed.
- Keep variable names consistent across snippets.
- Output ONE continuous block and end with the final question.

Now generate a single, kid-friendly, descriptive response using ONLY the provided RAG context.

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

conn.commit()

cur.close()
conn.close()
