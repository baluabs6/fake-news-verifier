from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CheckRequest(BaseModel):
    text: str | None = Field(default=None, description="Claim, headline or social post")
    url: str | None = Field(default=None, description="Article URL")
    save: bool = Field(default=True, description="False = do not store this check (no share link)")

    @model_validator(mode="after")
    def one_input(self):
        self.text = (self.text or "").strip() or None
        self.url = (self.url or "").strip() or None
        if bool(self.text) == bool(self.url):
            raise ValueError("Provide either text or url.")
        return self


class FlagRequest(BaseModel):
    reason: Literal["wrong_verdict", "missing_context", "outdated", "other"]
    note: str = Field(default="", max_length=500)


class ReviewRequest(BaseModel):
    verdict: Literal["True", "False", "Misleading", "Unverified"]
    note: str = Field(default="", max_length=1000)
