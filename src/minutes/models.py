"""Pydantic models for structured knowledge extraction."""

from pydantic import BaseModel, Field


class Decision(BaseModel):
    """A decision made during the meeting."""

    summary: str = Field(description="What was decided")
    owner: str = Field(default="", description="Who made it")
    rationale: str = Field(default="", description="Why this choice")
    date: str = Field(default="", description="When")


class Idea(BaseModel):
    """An idea or suggestion discussed."""

    title: str = Field(description="Short idea name")
    description: str = Field(default="", description="What is it")
    category: str = Field(default="suggestion", description="problem|opportunity|suggestion")


class Question(BaseModel):
    """An open question or topic."""

    text: str = Field(description="The question")
    context: str = Field(default="", description="Why it matters")
    owner: str = Field(default="", description="Who answers")


class ActionItem(BaseModel):
    """Something to do after the meeting."""

    description: str = Field(description="What to do")
    owner: str = Field(default="", description="Who owns it")
    deadline: str = Field(default="", description="When")


class Concept(BaseModel):
    """A key concept discussed."""

    name: str = Field(description="Concept name")
    definition: str = Field(default="", description="What it is")


class Term(BaseModel):
    """A technical term or abbreviation."""

    term: str = Field(description="The word or abbreviation")
    definition: str = Field(default="", description="What it means")
    context: str = Field(default="", description="Where mentioned")


class ExtractionResult(BaseModel):
    """The complete result of knowledge extraction from a transcript."""

    decisions: list[Decision] = Field(default_factory=list)
    ideas: list[Idea] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    terms: list[Term] = Field(default_factory=list)
    tldr: str = Field(default="", description="2-3 sentence summary")
