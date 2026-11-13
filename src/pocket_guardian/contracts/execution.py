"""M02 execution contracts. Core implementation belongs to the learner."""
from pydantic import BaseModel, field_validator, AwareDatetime, ConfigDict
from typing import Literal

class SuccessResult(BaseModel):
    status:Literal["succeeded"]="succeeded"
    adapter:str
    provider:str
    requested_model:str
    reported_model:str|None=None
    text:str
    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        if v.strip() == "":
            raise ValueError("text cannot be empty")
        return v
    model_config = ConfigDict(extra="forbid")
    finished_at:AwareDatetime
class FailureResult(BaseModel):
    adapter : str
    provider: str
    requested_model: str
    reported_model: str|None =None
    error_code:str
    message:str
    status:Literal["failed"]="failed"
    finished_at:AwareDatetime
    model_config = ConfigDict(extra="forbid")
    @field_validator("message","error_code")
    @classmethod
    def validate_message(cls, v):
        if v.strip() == "":
            raise ValueError("message cannot be empty")
        return v
class UnknownResult(BaseModel):
    adapter: str
    provider: str
    requested_model: str
    reported_model: str | None = None
    error_code: str
    message: str
    status:Literal["unknown"]="unknown"
    observed_at:AwareDatetime
    model_config = ConfigDict(extra="forbid")
    @field_validator("message","error_code")
    @classmethod
    def validate_message(cls, v):
        if v.strip() == "":
            raise ValueError("message or error_code cannot be empty")
        return v
