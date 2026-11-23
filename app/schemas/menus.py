from datetime import date, datetime, timedelta
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

SlotType = Literal["almuerzo", "cena"]
SourceType = Literal["casera", "fuera"]
DietFocusType = Literal["balanceada", "alta_proteina", "baja_carbohidratos", "baja_grasas"]
CookingFreqType = Literal["diaria", "dias_por_medio", "meal_prep"]
LeftoversType = Literal["sin_problema", "un_dia", "nada"]

class LogisticsConfig(BaseModel):
    diners: int = Field(..., ge=1)
    days: int = Field(..., ge=1, le=14)
    meals: List[SlotType] = Field(..., min_length=1)
    meals_out: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_logistics(self):
        if len(set(self.meals)) != len(self.meals):
            raise ValueError("No se permiten comidas repetidas en meals.")
        total_slots = self.days * len(self.meals)
        if self.meals_out >= total_slots:
            raise ValueError("Las comidas fuera deben ser menos que el total de comidas del menú.")
        return self

class NutritionConfig(BaseModel):
    diet_focus: DietFocusType
    excluded_ingredients: List[str] = Field(default=[])

class CookingConfig(BaseModel):
    cooking_frequency: CookingFreqType
    leftovers_tolerance: LeftoversType

class MenuCreateRequest(BaseModel):
    start_date: Optional[date] = None
    logistics: LogisticsConfig
    nutrition: NutritionConfig
    cooking: CookingConfig

    @model_validator(mode="after")
    def set_default_start_date(self):
        if self.start_date is None:
            self.start_date = date.today() + timedelta(days=1)
        return self

class MealOut(BaseModel):
    id: int
    date: date
    slot: SlotType
    name: str
    source: SourceType
    recipe_id: Optional[int] = None

class MenuSummaryOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    start_date: date
    end_date: date
    home_meals: int
    out_meals: int

class MenuDetailOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    start_date: date
    end_date: date
    config: dict
    meals: List[MealOut]

class SlotRef(BaseModel):
    date: date
    slot: SlotType

class MealMoveRequest(BaseModel):
    from_slot: SlotRef = Field(..., alias="from")
    to_slot: SlotRef = Field(..., alias="to")

class MealMoveResponse(BaseModel):
    meals: List[MealOut]

class RecipeIngredientScaled(BaseModel):
    name: str
    quantity: float
    unit: str
    is_optional: bool = False

class RecipeDetailOut(BaseModel):
    id: int
    title: str
    servings: int
    prep_time: str
    diet_type: str
    allergens: List[str] = Field(default=[])
    ingredients: List[RecipeIngredientScaled]
    steps: List[str]