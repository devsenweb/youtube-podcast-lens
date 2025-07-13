from typing import Optional

from sqlmodel import Field, SQLModel, create_engine

# SQLite database stored in local data directory
import os

# Ensure ./data directory exists relative to project root
base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(base_dir, exist_ok=True)
DATABASE_URL = f"sqlite:///{os.path.join(base_dir, 'app.db')}"
engine = create_engine(DATABASE_URL, echo=False)


class Video(SQLModel, table=True):
    """Represents a processed YouTube video."""

    id: str = Field(primary_key=True, index=True, description="YouTube videoId")
    title: Optional[str] = Field(default=None)


class TranscriptLine(SQLModel, table=True):
    video_id: str = Field(index=True, primary_key=True)
    start_sec: int = Field(index=True, primary_key=True)
    text: str


class Segment(SQLModel, table=True):
    """A single topic / transcript segment belonging to a video."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="video.id", index=True)
    start_sec: int
    keyword: str
    text: Optional[str] = None
    image_path: Optional[str] = None


def init_db() -> None:
    """Create tables if they do not already exist."""

    SQLModel.metadata.create_all(engine)


# Run on import so that simply importing db sets up the database
init_db()
