from pydantic import BaseModel, Field
from typing import List, Optional

class RecommendationRequest(BaseModel):
    # El usuario se obtiene del token JWT; se mantiene opcional por compatibilidad con el front
    user_id: Optional[str] = None
    intent: str = Field(..., description="ahorro, saludable, balance, vegano, vegetariano")
    dietary_restrictions: Optional[List[str]] = Field(
        default=[],
        description="Restricciones adicionales en texto libre (las del perfil se aplican siempre)"
    )
    shopping_list: Optional[List[str]] = Field(
        default=[],
        description="Ingredientes ya disponibles en despensa"
    )

class IngredientDetail(BaseModel):
    original_name: str
    catalog_query: str
    quantity_needed: str

class RecipeRecommendation(BaseModel):
    recipe_id: int
    title: str
    prep_time: str
    category: str
    why_recommended: str
    ingredients: List[IngredientDetail]
    instructions: str

class RecommendationResponse(BaseModel):
    user_intent: str
    recommendations: List[RecipeRecommendation]
    excluded_by_restrictions: int = 0  # Recetas descartadas por el perfil alimentario (SC-1)
    message: Optional[str] = None
