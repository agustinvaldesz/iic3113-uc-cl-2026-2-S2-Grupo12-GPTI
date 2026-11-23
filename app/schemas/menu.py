"""Contrato de POST /api/generar-menu (definido por el front en ConfigMenuPage.tsx, más budget y pantry)."""
import re
from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.basket import QuoteResponse

Meal = Literal["almuerzo", "cena"]
DietFocus = Literal["balanceada", "alta_proteina", "baja_carbohidratos", "baja_grasas"]

class Logistics(BaseModel):
    diners: int = Field(..., ge=1, le=12)
    days: int = Field(..., ge=1, le=14)
    meals: List[Meal] = Field(..., min_length=1)
    meals_out: int = Field(default=0, ge=0)

    @field_validator("meals")
    @classmethod
    def unique_meals(cls, meals: List[str]) -> List[str]:
        return [m for m in ("almuerzo", "cena") if m in meals]  # Sin repetidos y en orden

    @model_validator(mode="after")
    def meals_out_fits(self):
        if self.meals_out >= self.days * len(self.meals):
            raise ValueError("Las comidas fuera deben ser menos que el total de comidas del menú.")
        return self

class Nutrition(BaseModel):
    diet_focus: DietFocus = "balanceada"
    excluded_ingredients: List[str] = Field(default_factory=list)

class Cooking(BaseModel):
    cooking_frequency: Literal["diaria", "dias_por_medio", "meal_prep"] = "diaria"
    leftovers_tolerance: Literal["sin_problema", "un_dia", "nada"] = "un_dia"

class Budget(BaseModel):
    prioritize_savings: bool = True  # Ahorro como prioridad, aparte del enfoque nutricional

class GenerarMenuRequest(BaseModel):
    logistics: Logistics
    nutrition: Nutrition = Field(default_factory=Nutrition)
    cooking: Cooking = Field(default_factory=Cooking)
    budget: Budget = Field(default_factory=Budget)
    pantry: List[str] = Field(default_factory=list)  # Lo que el usuario ya tiene en casa
    start_date: Optional[date] = None                # Por defecto, mañana

class SlotOut(BaseModel):
    id: str
    name: str
    origin: Literal["casera", "fuera"]
    recipe_id: Optional[int] = None
    is_leftover: bool = False

class MenuRecipeOut(BaseModel):
    recipe_id: int
    title: str
    prep_time: Optional[str] = None
    instructions: Optional[str] = None
    ingredients: List[str]          # Cantidades originales de la receta
    scaled_ingredients: List[str]   # Cantidades para UNA preparación (comida del día + sus sobras)
    portions_per_cooking: int       # Porciones que salen de cada preparación
    times_cooked: int
    times_in_menu: int
    portions: int
    base_servings: int
    scale_factor: float

class MenuOut(BaseModel):
    id: Optional[int] = None
    name: str
    created_at: Optional[datetime] = None
    start_date: str
    end_date: str
    diners: int
    assignments: Dict[str, SlotOut]  # Clave "YYYY-MM-DD|almuerzo"
    recipes: List[MenuRecipeOut]
    basket: Optional[QuoteResponse] = None
    budget_limit: Optional[float] = None
    excluded_by_restrictions: int = 0
    message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

class MenuSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    start_date: str
    end_date: str
    diners: int
    home_meals: int
    meals_out: int
    total_cost: Optional[int] = None

# Edición del calendario (PUT /api/menus/{id}/assignments)
SLOT_KEY = r"^\d{4}-\d{2}-\d{2}\|(almuerzo|cena)$"

class AssignmentIn(BaseModel):
    origin: Literal["casera", "fuera"]
    recipe_id: Optional[int] = None

    @model_validator(mode="after")
    def recipe_matches_origin(self):
        if self.origin == "casera" and self.recipe_id is None:
            raise ValueError("Una comida casera necesita recipe_id.")
        if self.origin == "fuera":
            self.recipe_id = None
        return self

class UpdateAssignmentsRequest(BaseModel):
    """Calendario completo después de editarlo. Un espacio que no viene, queda vacío."""
    assignments: Dict[str, AssignmentIn] = Field(..., min_length=1)

    @field_validator("assignments")
    @classmethod
    def valid_keys(cls, assignments: Dict[str, AssignmentIn]) -> Dict[str, AssignmentIn]:
        bad = [k for k in assignments if not re.match(SLOT_KEY, k)]
        if bad:
            raise ValueError(f"Claves inválidas (formato YYYY-MM-DD|almuerzo): {', '.join(bad)}")
        return assignments