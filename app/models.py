from pydantic import BaseModel, EmailStr
from typing import List, Optional
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
    user_id: str
    intent: str  # Ej: "ahorro", "saludable", "balance"
    shopping_list: Optional[List[str]] = [] # Lista de abarrotes opcional


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