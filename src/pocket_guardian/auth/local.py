"""M01 local authentication exercise: implementation belongs to the learner."""

from secrets import compare_digest

# HTTP request parsing scaffold supplied by Codex.
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)

# Learner: implement verify_token(provided: str | None, expected: str) -> bool.
# expected must come from server configuration; never from a client claim.
def verify_token(provided:str|None,expected:str)->bool:
    if not provided:
        return False
    provided=provided.encode('utf-8')
    expected=expected.encode('utf-8')
    return compare_digest(provided,expected)

def require_local_actor(
    request:Request,
    credentials:HTTPAuthorizationCredentials|None = Depends(bearer)
)->dict[str, str]:
    if credentials:
        Token=request.app.state.settings.token.get_secret_value()
        provided=credentials.credentials
        expected=request.app.state.settings.token.get_secret_value()
        verified=verify_token(provided,expected)
        if not verified:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"actor_id": "local-owner"}
    else:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )