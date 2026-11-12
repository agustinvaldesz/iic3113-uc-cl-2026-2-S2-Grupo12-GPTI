from pydantic import BaseModel, EmailStr, Field, field_validator
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
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserPreferences(BaseModel):
    intent: Literal["ahorro", "saludable", "balance"]
    budget_limit: Optional[float] = Field(default=None, gt=0)  # Presupuesto semanal, debe ser positivo
    shopping_list: Optional[List[str]] = []

# Tipos de dieta y alergias
DietType = Literal["con_carne", "vegetariana", "vegana"]
Allergy = Literal["gluten", "lactosa", "frutos_secos", "mariscos"]

class DietaryProfileUpdate(BaseModel):
    diet_type: DietType = "con_carne"
    allergies: List[Allergy] = []
    consent: bool  # Obligatorio, de lo contrario FastAPI responde 422

    @field_validator("consent")
    @classmethod
    def consent_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Se requiere consentimiento para guardar restricciones alimentarias.")
        return value

class DietaryProfileResponse(BaseModel):
    diet_type: DietType
    allergies: List[Allergy]
    consent_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

DIET_LABELS = {
    "con_carne": "Con carne",
    "vegetariana": "Vegetariana",
    "vegana": "Vegana",
}

ALLERGY_LABELS = {
    "gluten": "Gluten",
    "lactosa": "Lactosa",
    "frutos_secos": "Frutos secos",
    "mariscos": "Mariscos",
}


# Esquemas para la recomendación del LLM
class IngredientItem(BaseModel):
    original_name: str
    catalog_query: str  # Término exacto para buscar en el catálogo de Lider (ej: "Arroz 1kg")
    quantity_needed: str

class RecipeRecommendation(BaseModel):
    recipe_id: Optional[int] = None
    title: str
    prep_time: str
    category: str
    why_recommended: str
    ingredients: List[IngredientItem]
    instructions: str

class RecommendationResponse(BaseModel):
    user_intent: str
    recommendations: List[RecipeRecommendation]

TokenResponse.model_rebuild()