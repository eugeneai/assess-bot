from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.config import settings

security = HTTPBasic(auto_error=False)


async def verify_password(credentials: HTTPBasicCredentials | None = Depends(security)):
    if not settings.admin_password:
        return True

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    if credentials.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True
