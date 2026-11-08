"""M01 configuration exercise: core implementation belongs to the learner."""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
from typing import Literal

# Learner: define Settings below. First implement the port field and its limits.
class Setting(BaseSettings):
    port: int = Field(default=8000,ge=1,le=65535)
    host: Literal['127.0.0.1'] = '127.0.0.1'
    token:SecretStr=Field(min_length=32)
    model_config = SettingsConfigDict(
        hide_input_in_errors=True,
        env_prefix="PG_",
    )

def load_settings() ->Setting:
    setting = Setting()
    return setting
