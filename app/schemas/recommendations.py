from pydantic import BaseModel, Field
from typing import List, Optional

class RecommendationRequest(BaseModel):
    user_id: str
    intent: str = Field(..., description="ahorro, saludable, balance, vegano, vegetariano")
    dietary_restrictions: Optional[List[str]] = Field(
        default=[], 
        description="Lista de restricciones: sin gluten, intolerancia a la lactosa, keto, etc."
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