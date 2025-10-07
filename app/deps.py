from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from jose import jwt, JWTError
from typing import Dict, Any

from .config import get_settings

settings = get_settings()

# ---- JWT Auth untuk Reseller ----
security_jwt = HTTPBearer(auto_error=False)

async def auth_reseller_jwt(credentials: HTTPAuthorizationCredentials = Depends(security_jwt)) -> Dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        reseller_id: str = payload.get("sub")
        if reseller_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT payload")
        return {"reseller_id": reseller_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token")


# ---- Basic Auth untuk Admin ----
security_basic = HTTPBasic()

async def admin_basic_auth(credentials: HTTPBasicCredentials = Depends(security_basic)) -> Dict[str, Any]:
    correct_username = settings.ADMIN_BASIC_USER
    correct_password = settings.ADMIN_BASIC_PASS

    if credentials.username != correct_username or credentials.password != correct_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")

    return {"admin": True}


# ---- Pagination ----
async def pagination(page: int = 1, per_page: int = 20) -> Dict[str, int]:
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if per_page < 1 or per_page > 100:
        raise HTTPException(status_code=400, detail="per_page must be between 1 and 100")

    offset = (page - 1) * per_page
    return {"page": page, "per_page": per_page, "offset": offset, "limit": per_page}

async def auth_reseller_jwt(credentials: HTTPAuthorizationCredentials = Depends(security_jwt)) -> Dict[str, Any]:
    if not settings.USE_JWT:
        # Mode non-JWT → auto return reseller default
        return {"reseller_id": settings.DEFAULT_RESELLER_ID}

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        reseller_id: str = payload.get("sub")
        if reseller_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT payload")
        return {"reseller_id": reseller_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token")
