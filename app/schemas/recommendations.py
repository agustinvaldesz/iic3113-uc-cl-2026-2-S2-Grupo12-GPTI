from pydantic import BaseModel, Field
from typing import List, Optional

class RecommendationRequest(BaseModel):
    user_id: str
    intent: str = Field(..., description="ahorro, saludable, balance, vegano, vegetariano")
    servings: int = Field(default=2, ge=1, le=20, description="Cantidad de personas que comerán")
    dietary_restrictions: Optional[List[str]] = Field(
        default=[], 
        description="Lista de restricciones: sin gluten, intolerancia a la lactosa, keto, etc."
    )
    extra_preferences: Optional[dict] = Field(
        default={}, 
        description="Ej: presupuesto_max, tiempo_max, nivel_cocina"
    )
    shopping_list: Optional[List[str]] = Field(
        default=[], 
        description="Ingredientes ya disponibles en despensa"
    )

class CheaperAlternative(BaseModel):
    product_name: str
    price: float
    savings: float
    url: Optional[str] = None

class LiderMatch(BaseModel):
    matched: bool
    source: str
    product_name: str
    price: float
    sku: Optional[str] = None
    url: Optional[str] = None
    cheaper_alternatives: List[CheaperAlternative] = Field(default=[])

class IngredientDetail(BaseModel):
    original_name: str
    catalog_query: str
    quantity_needed: str
    in_pantry: bool = False
    lider_match: Optional[LiderMatch] = None

class RecipeRecommendation(BaseModel):
    recipe_id: int
    title: str
    servings: int = 2
    prep_time: str
    category: str
    why_recommended: str
    ingredients: List[IngredientDetail]
    instructions: str
    total_estimated_cost: float = 0.0

class RecommendationResponse(BaseModel):
    user_intent: str
    recommendations: List[RecipeRecommendation]