import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import get_db
from app.models_db import UserDB
from app.models import UserCreate, UserLogin, UserResponse, TokenResponse

load_dotenv()

# Configuración de variables para JWT
SECRET_KEY = os.getenv("SECRET_KEY", "nutricart_super_secret_jwt_key_2026_gpti")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

router = APIRouter(
    prefix="/api/auth",
    tags=["Autenticación y Usuarios"]
)

def hash_password(password: str) -> str:
    pwd_bytes = password[:72].encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password[:72].encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    # 1. Verificar si el correo ya existe
    existing_user = db.query(UserDB).filter(UserDB.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado."
        )
    
    # 2. Hashear la contraseña con bcrypt
    hashed_pwd = hash_password(user_in.password)

    # 3. Crear el nuevo usuario
    new_user = UserDB(
        full_name=user_in.full_name,
        email=user_in.email,
        hashed_password=hashed_pwd,
        dietary_preference=user_in.dietary_preference,
        budget_limit=user_in.budget_limit
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@router.post("/login", response_model=TokenResponse)
def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    # 1. Buscar al usuario por correo
    user = db.query(UserDB).filter(UserDB.email == login_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas (correo o contraseña no válidos)."
        )

    # 2. Validar contraseña
    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas (correo o contraseña no válidos)."
        )

    # 3. Generar token de acceso JWT
    token_payload = {
        "sub": str(user.id),
        "email": user.email
    }
    access_token = create_access_token(data=token_payload)

    # 4. Retornar token y datos del usuario
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }