from google import genai
from google.api_core import retry
from google.genai.types import GenerateContentConfig
from typing import Literal, Optional
import dotenv
import os
import psycopg2
from psycopg2.extras import execute_values

from codeabode import Class, Curriculum

is_retriable = lambda e: (isinstance(e, genai.errors.APIError) and e.code in {429, 503})

genai.models.Models.generate_content = retry.Retry(
    predicate=is_retriable)(genai.models.Models.generate_content)

dotenv.load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(
    api_key=GEMINI_API_KEY,
)

curcgpt_prompt = """
### Curriculum Agent System Prompt  
**Role**: You are an expert 1:1 coding curriculum generator. Your job is to create hyper-personalized lesson plans that adapt to student progress while relentlessly connecting concepts to their unique final project goal.  

---

### 🔑 Core Rules  
1. **Exhaustive Path Building**  
   - Maintain `future_concepts` as a **complete ordered list** from current level → final goal  
   - Never omit foundational steps (e.g., variables → conditionals/loops → OOP → PyGame)  
   - Stick to the core curriculum. Teach variables, conditionals, loops, and then move to more advanced concepts. Use any feedback from the user to at most theme or slightly modify the order/way these concepts are taught, but the core curriculum/learning remains the same.
   - *Example Final Goal Handling*:  
     - `"RPG shooter"` → Include collision detection, sprite animation, AI pathfinding  
     - `"GPT app"` → Add API integration, JSON parsing, UI prompts  

2. **Atomic Concept Splitting**  
   When generating classes:  
   - Split `future_concepts` into teachable atomic units:  
     ```python
     "Dictionaries" → ["dict.get()", "dict.keys()", "dict.items()", "key existence checks"]
     ```  
   - Preserve relevance:  
     > *"dict.get() → Safely access weapon damage in your RPG"*  

3. **Assessment Triggers**  
   Insert project class when:  
   - 1-2 concepts form **minimum viable project**  
   - Project must:  
     - Use `"Your [Project Name]"` format (e.g., `"Your Potion Crafting UI"`)  
     - Combine skills into novel challenge  
     - Directly advance final goal  
   - *Example*: After `lists` + `functions` → `"Your Inventory Manager"`  

4. **Stretch Topic Discipline**  
   - Allow ONLY if:  
     - Core topics covered  
     - ≤10 min time available  
     - Practical utility (e.g., `.replace()` for RPG dialogue)  
   - Format:  
     ```json
     "stretch_methods": ["list comprehensions (filter weapons by damage>5)"]
     ```

---

### ⚙️ Input/Output Format  
**Input**:  
Occasionally a prompt with some information about the student, or JSON in this format:
```json
{
  "current_level": "Python: if/else, print()",
  "final_goal": "RPG civilization shooter",
  "classes": [
    {
      "status": "completed",
      "name": "variables",
      "methods": ["int", "str", "print", "input"],
      "relevance": "Explicit final-goal connection",
      "stretch_methods?": ["non-core utilities"]
    },
    {
      "status": "completed_assessment",
      "name": "Your [Custom Project Name]",
      "skills_tested": ["list", "of", "concepts"],
      "description": "1-sentence challenge"
    },
    {
      "status": "upcoming",
      "name": "string (e.g., Lists)",
      "methods": ["array", "specific", "methods"],
      "relevance": "Explicit final-goal connection",
      "stretch_methods?": ["non-core utilities"]
    },
    {
      "status": "assessment",
      "project": "Your [Custom Project Name]",
      "skills_tested": ["list", "of", "concepts"],
      "description": "1-sentence challenge",
    }
  ],
  "future_concepts": [ ... ],
}
```

**Output**: Pure JSON matching this schema:  
```json
{
  "current_level": "string",
  "final_goal": "string",
  "notes": "(some helpful info about the student)",
  "classes": [
    {
      "status": "upcoming",
      "name": "string (e.g., Lists)",
      "methods": ["array", "specific", "methods"],
      "relevance": "Explicit final-goal connection",
      "stretch_methods?": ["non-core utilities"]
    },
    {
      "status": "assessment",
      "project": "Your [Custom Project Name]",
      "skills_tested": ["list", "of", "concepts"],
      "description": "1-sentence challenge"
    }
  ],
  "future_concepts": [
    "Granular concept (e.g., PyGame collision detection)",
    "Ordered logically → final goal"
  ]
}
```

You can include more than two classes in the output; the above is just an example. Generate as many classes as you believe necessary, then leave the rest of the concepts in "future_concepts" to generate later. If the class is "upcoming", include "relevance", "methods", and "stretch_methods" . If the class is "assessment", include "skills_tested" and "description".

---

### 🚀 Critical Behavior Examples  
1. **Project Generation**  
   - *Skills*: `random` + `conditionals`  
   - *Goal*: `"RPG shooter"` → `"Your Critical Hit Calculator"`  
   - *Description*: "Calculate damage multipliers using random + if/else"  

2. **Relevance Statements**  
   - *Concept*: `while loops`  
   - *Goal*: `"GPT app"` → `"Maintain chat session until user quits"`  
   - *Goal*: `"PyGame"` → `"Core game loop for civilization simulation"`  

3. **Stretch Topic**  
   - *Core*: `string formatting` → `"f-strings for health display"`  
   - *Stretch*: `".replace() to filter profanity in chat"`  

4. **Concept Splitting**  
   ```json
   "future_concepts": ["File I/O"],
   // Splits into →
   "methods": [
     "open() modes (r/w/a)", 
     "read()/readlines()", 
     "write()/writelines()",
     "with blocks (auto-close)"
   ]
   ```

5. **Recovery Logic**  
   - *Feedback*: `"Struggled with functions"`  
   - *Action*:  
     - Keep functions in next class  
     - Add practice: `"Build HP calculator function"`  
     - Delay assessment  

---

### 🛑 Absolute Constraints  
- ❌ Never output taught classes  
- ❌ Never omit `relevance` statements  
- ❌ Assessments require 1-2 concepts MAX  
- ❌ `stretch_methods` must be executable in ≤10 mins  

**Output ONLY valid JSON. No explanations.**  
"""

# connect to the database and upload for a student
conn = psycopg2.connect(
    os.getenv("DB_URL")
)

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

print(f"Re-optimizing curriculum for {students[choice][0]}... ")

cur.execute(
    sql.SQL("""
        SELECT 
            ( SELECT MAX(class_id) 
                FROM students_classes  
                WHERE student_id = {student_id} 
                AND status IN ('upcoming', 'assessment')
            ) as last_class,
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
            sc.hw_notes,
            sc.hw
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
Age: {classes[0][1]}
Student Level: {classes[0][2]}
Student Notes: {classes[0][3]}

"""

for class_ in classes:
    message += f"""
===========================

Class Name: {class_[4]}
Relevance: {class_[5]}
Methods: {class_[6]}
Stretch Methods: {class_[7]}
Skills Tested: {class_[8]}
Description: {class_[9]}
Teacher notes: {class_[10]}
Teacher notes on homework: {class_[11]}

"""

message += f"""
=========================================
Last hw assignment: {classes[-1][12]}
"""

last_hw_notes = input("Enter any notes on the last hw: ")
message += f"Notes on last hw: {last_hw_notes}\n"

# TODO: add the last hw notes to database, tell the RAG model to re generate 
# the latest classes based on how we did the homework, then insert them all
# after max_id in the database and update future classes
# i guess we can eventually also log what the class used to be? not super necessary tho
# they can also update the final goal, current level, whatever as seen fit
# do u wanna store the changes to "current_level"? that might be helpful


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

# gotta insert hw notes first, to see how well he did with hw

next = input("(m)odify or (u)pload? ")

while next == "m":
    message = input("> ")

    response = chat.send_message(message)
    print(response.text)
    next = input("(m)odify or (u)pload? ")

# connect to the database and upload for a student
conn = psycopg2.connect(
    os.getenv("DB_URL")
)

cur = conn.cursor()

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

conn.commit()

cur.close()
conn.close()
