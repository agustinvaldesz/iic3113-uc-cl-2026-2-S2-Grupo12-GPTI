from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

DietType = Literal["con_carne", "vegetariana", "vegana"]
Allergy = Literal["gluten", "lactosa", "frutos_secos", "mariscos"]
DietFocus = Literal["balanceada", "alta_proteina", "baja_carbohidratos", "baja_grasas"]

class RecipeIn(BaseModel):
    """Formato obligatorio de una receta, la suba un gestor o la genere la IA."""
    title: str = Field(..., min_length=3, max_length=120)
    servings: int = Field(..., ge=1, le=12)
    prep_time: Optional[str] = None
    diet_type: DietType
    allergens: List[Allergy] = Field(default_factory=list)
    diet_focus: List[DietFocus] = Field(..., min_length=1)
    ingredients: List[str] = Field(..., min_length=2, description='Una línea por ingrediente, ej: "450 g de carne molida"')
    instructions: str = Field(..., min_length=20)

    @field_validator("ingredients")
    @classmethod
    def clean_lines(cls, lines: List[str]) -> List[str]:
        cleaned = [l.strip() for l in lines if l and l.strip()]
        if len(cleaned) < 2:
            raise ValueError("La receta debe tener al menos 2 ingredientes.")
        return cleaned

class RecipeOut(RecipeIn):
    id: int
    status: str
    source: str
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)  # Alérgenos que podrían faltar

class GenerateRequest(BaseModel):
    count: int = Field(default=2, ge=1, le=3)  # Pocas por llamada por el límite de tokens de Groq
    diet_type: Optional[DietType] = None
    diet_focus: Optional[DietFocus] = None
    prioritize_savings: bool = True
    notes: Optional[str] = Field(default=None, max_length=300)  # Ej: "platos chilenos de invierno"

class GenerateResponse(BaseModel):
    created: List[RecipeOut]
    discarded: List[str]  # Borradores de la IA que no cumplían el formato

class ReviewRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)