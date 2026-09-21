from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stop_name: str = Field(default="", max_length=500)
    time: str = Field(default="", max_length=40)
    confidence: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    original_text: str = Field(default="", max_length=2000)
    normalized_text: str = Field(default="", max_length=500)
    original_time: str = Field(default="", max_length=40)
    page: int = Field(default=1, ge=1, le=20)
    trip_index: int = Field(default=1, ge=1, le=100)
    reviewed: bool = False
    issues: list[str] = Field(default_factory=list, max_length=30)
    confidence_level: str = "low"
    needs_review: bool = True
    ambiguous: bool = False


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: float = Field(allow_inf_nan=False)
    top: float = Field(allow_inf_nan=False)
    width: float = Field(ge=0, allow_inf_nan=False)
    height: float = Field(ge=0, allow_inf_nan=False)


class SourceWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=2000)
    confidence: float = Field(ge=0, le=100, allow_inf_nan=False)
    page: int = Field(ge=1, le=20)
    bounding_box: BoundingBox
    block: int = 0
    line: int = 0


class EntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sl_no: int | None = Field(default=None, strict=True, ge=0)
    destination: str = Field(default="", max_length=2000)
    timing: str | None = Field(default=None, max_length=40)
    confidence: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    needs_review: bool = True
    reviewed: bool = False
    ambiguous: bool = False
    issues: list[str] = Field(default_factory=list, max_length=30)
    page: int = Field(default=1, ge=1, le=20)
    y: float | None = Field(default=None, allow_inf_nan=False)
    original_destination: str = Field(default="", max_length=2000)
    original_time: str = Field(default="", max_length=2000)
    raw_text: str = Field(default="", max_length=10000)
    bounding_box: BoundingBox | None = None
    source_words: list[SourceWord] = Field(default_factory=list, max_length=2000)


class TimetableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_name: str | None = Field(default=None, max_length=500)
    origin: str | None = Field(default=None, max_length=500)
    destination: str | None = Field(default=None, max_length=500)
    stops: Annotated[list[StopInput] | None, Field(max_length=3000)] = None
    entries: Annotated[list[EntryInput] | None, Field(max_length=3000)] = None
    # Optimistic concurrency: don't overwrite changes from another editor.
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def one_schema(self):
        if (self.entries is None) == (self.stops is None):
            raise ValueError("Supply either entries or legacy stops.")
        return self
