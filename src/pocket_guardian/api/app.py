"""M01 application exercise: implementation belongs to the learner."""

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import  TrustedHostMiddleware
from pocket_guardian.auth.local import require_local_actor
from pocket_guardian.config import Setting

# Learner: create_app(settings: Setting) -> FastAPI creates and returns a fresh app.
def create_app(settings:Setting)->FastAPI:
    app = FastAPI()
    app.state.settings = settings
    @app.middleware("http")
    async def check_origin(request:Request,call_next):
        if settings.port==80:
            address=f"http://{settings.host}"
        else:
            address=f"http://{settings.host}:{settings.port}"
        origin=request.headers.get("Origin")
        if origin is not None and  request.headers.get("Origin")!=address:
            return JSONResponse({"error":"Untrust origin"},403)
        return await call_next(request)
    @app.get("/health")
    def health():
        return {"status": "ok"}
    @app.get("/identity")
    def identity(actor:dict[str, str]=Depends(require_local_actor)):
        return actor
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[settings.host],
        www_redirect=False
                       )
    return app
