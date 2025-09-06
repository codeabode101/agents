from pydantic import BaseModel
from typing import Literal, Optional

class Class(BaseModel):
    status: Literal["upcoming", "assessment"]
    name: str

    # if "upcoming"
    relevance: Optional[str]
    methods: Optional[list[str]]
    stretch_methods: Optional[list[str]]

    # if "assessment"
    skills_tested: Optional[list[str]]
    description: Optional[str]

class Curriculum(BaseModel):
    current_level: str
    final_goal: str
    classes: list[Class]
    future_concepts: list[str]
    notes: Optional[str]
