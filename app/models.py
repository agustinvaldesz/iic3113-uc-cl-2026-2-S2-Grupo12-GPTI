from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Literal
from datetime import datetime

# Lo que envía el frontend al registrarse
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    dietary_preference: Optional[str] = "balance"
    budget_limit: Optional[float] = None

# Esquema para iniciar sesión
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Esquema de respuesta tras iniciar sesión con token
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: "UserResponse"

# Lo que responde la API tras registrar al usuario (seguro, sin password)
class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    dietary_preference: Optional[str]
    budget_limit: Optional[float]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserPreferences(BaseModel):
    intent: Literal["ahorro", "saludable", "balance"]
    budget_limit: Optional[float] = Field(default=None, gt=0)  # Presupuesto semanal, debe ser positivo
    shopping_list: Optional[List[str]] = []

# Por ahora omnívora y vegetariana
DietType = Literal["con_carne", "vegetariana"]

# Alergias disponibles
Allergy = Literal["gluten", "lactosa", "mani", "frutos_secos", "mariscos", "pescado", "huevo", "soya"]

class DietaryProfileUpdate(BaseModel):
    diet_type: DietType = "con_carne"
    allergies: List[Allergy] = []

class DietaryProfileResponse(BaseModel):
    diet_type: DietType
    allergies: List[Allergy]
    updated_at: Optional[datetime] = None

DIET_LABELS = {
    "con_carne": "Con carne",
    "vegetariana": "Vegetariana",
}

ALLERGY_LABELS = {
    "gluten": "Gluten",
    "lactosa": "Lactosa",
    "mani": "Maní",
    "frutos_secos": "Frutos secos",
    "mariscos": "Mariscos",
    "pescado": "Pescado",
    "huevo": "Huevo",
    "soya": "Soya",
}

TokenResponse.model_rebuild()