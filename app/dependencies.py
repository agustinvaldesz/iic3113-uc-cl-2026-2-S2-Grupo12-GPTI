import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import UserDB
from app.routers.auth import SECRET_KEY, ALGORITHM

# Lee el header "Authorization: Bearer <token>" de cada petición
bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),) -> UserDB:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado. Inicia sesión nuevamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise credentials_error

    if user_id is None:
        raise credentials_error

    # 2. Buscar al usuario en la base de datos
    user = db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_error

    return user