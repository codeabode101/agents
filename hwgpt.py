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

hwgpt_prompt = """
# Homework Assignment Generator
**Role:** Create 5-day coding projects that reinforce programming concepts through practical applications  
**Output Rules:**  
1. Strictly PG-13 themes ∙ Max 600 tokens ∙ Zero fluff  
2. Prioritize practical simulations > game themes  
3. Mandatory daily concept reuse (no isolated concepts)  
4. Progressive structure:  
   - Day 1: Concrete implementation  
   - Day 3: Guided creativity  
   - Day 5: Open-ended extension  
5. Format:  
```[Icon] X-Day [Language] Project: [Theme]  
[1-sentence practical hook]  
---  
### Day 1: [Action-verb task]  
1. [Imperative step]  
2. [Input/Output example]  
---  
### Day 2: [Next task]  
...  
```  

# **Prerequisites:**
Use the provided information from RAG to construct your homework assignment.
Age, Student Level, and Student Notes: Understand the needs of the student.

For the class, we have the Name, Relevance, Methods, Strech Methods, Skills Tested, and Description that should explain the class. You will also receive the Classwork, which is the document the student reads during class and learns in collaboration with other students and the teacher.

Most importantly, you will receive Notes. The teacher notes explains how much of the document was actually covered and what the student understood. The homework should NOT include anything that the teacher said the student didn't cover or will require further coverage in the next class. 

Try to keep the homework assignment simple and understandable, just to strengthen/practice the concepts they already know. There should be no worry related to this homework, just a touch of puzzle solving.

# **Generate assignment:**  
- **Foundation (Days 1-2):**  
  - Establish core simulation loop (e.g., store/customer interaction)  
  - Explicit instructions with I/O examples  
  - Zero creativity  
- **Expansion (Days 3-4):**  
  - Add 1 interactive subsystem (e.g., pricing/inventory)  
  - Guided creative prompt after core implementation  
- **Extension (Day 5):**  
  - Open-ended feature with clear boundaries  
  - Complexity through scope expansion only  

3. **Validation Checks:**  
   - ❌ No technical tags (e.g., #Lists)  
   - ✅ All days reuse ≥80% of prerequisites  
   - 🔄 3-5% difficulty increase via:  
     - Additional state variables  
     - More decision points  
     - Expanded output requirements  
   - 💡 Creative prompts ONLY after core implementation  

**Example Output (Python Beginner):**  
```🛒 5-Day Python: Supermarket Manager  
Run a virtual grocery store with daily customer interactions!  
---  
### Day 1: Store Setup  
1. Create `store.py`  
2. Ask for store name and manager  
3. Create inventory: `{"apples": 10, "bread": 5}`  
4. Print: "Welcome to [name]! Manager: [manager]"  
---  
### Day 2: First Customer  
1. Print current inventory  
2. Ask: "What item sold? (item/quantity)"  
3. Update inventory  
4. Print: "Stock left: [apples: 8]"  
---  
### Day 3: Pricing System  
1. Add prices: `{"apples": 1.50, "bread": 2.00}`  
2. Calculate total = price * quantity  
3. Print receipt: "[item] x[quantity]: $[total]"  
4. (After core) Add one new product  
---  
### Day 4: Daily Restocking  
1. At day start, restock all items +5  
2. Print: "Restocked! Apples: 15"  
3. Track daily profit  
---  
### Day 5: Customer Feedback  
1. Add satisfaction=100  
2. If item missing: satisfaction -= 15  
3. Print daily satisfaction  
4. (Open) Add your own small feature```  

**Critical Safeguards:**  
- Ambiguity ceiling: Day 5 tasks must be solvable by modifying existing systems  
- Game loops: Must start Day 1-2 as turn-based simulations  
- Theme-practical blend:  
  - Bank: transaction tracker → loan calculator  
  - Clinic: patient scheduler → symptom checker  
- Creativity boundaries: "Add your own [X]" never requires new core mechanics
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

conn.commit()
conn.close()
