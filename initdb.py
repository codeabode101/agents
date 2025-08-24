import dotenv
import os
import psycopg2

dotenv.load_dotenv()

conn = psycopg2.connect(os.getenv("DB_STR"))



cur = conn.cursor()

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        age INTEGER NOT NULL,
        current_level TEXT NOT NULL,
        final_goal TEXT NOT NULL,
        future_concepts TEXT[] NOT NULL,
        notes TEXT,
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
        description TEXT
    );
    """
)

conn.commit()

cur.close()
conn.close()
