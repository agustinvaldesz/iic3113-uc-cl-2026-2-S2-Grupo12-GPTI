from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    original_name: str
    catalog_query: Optional[str] = None
    quantity_needed: Optional[str] = None


class QuoteRequest(BaseModel):
    # Ingredientes a cotizar (por ejemplo, los que devuelve /api/recipes/recommend)
    items: List[QuoteItem] = Field(default_factory=list)
    # Alternativa: cotizar recetas base por su id
    recipe_ids: List[int] = Field(default_factory=list)
    # Ingredientes que el usuario ya tiene en su despensa (no se cotizan)
    pantry: List[str] = Field(default_factory=list)
    # SC-2: {ingrediente: sku} para reemplazar el producto por defecto con la alternativa elegida
    selections: Dict[str, str] = Field(default_factory=dict)


class ProductOption(BaseModel):
    sku: str
    name: str
    price: int
    package_quantity: float
    package_unit: str
    sold_by_weight: bool
    packages: float
    cost: int
    unit_price: float
    is_default: bool
    price_updated_at: Optional[str] = None
    price_stale: bool


class CheaperAlternative(ProductOption):
    savings: int


class QuoteLine(BaseModel):
    ingredient: str
    category: Optional[str] = None
    source_items: List[str]
    quantity_needed: Optional[float] = None
    unit: Optional[str] = None
    selected: ProductOption
    cheaper_alternative: Optional[CheaperAlternative] = None
    options: List[ProductOption]


class QuoteResponse(BaseModel):
    lines: List[QuoteLine]
    total: int
    total_default: int
    savings: int               # Ahorro logrado por los reemplazos elegidos
    potential_savings: int     # Ahorro adicional si se aceptan todas las alternativas sugeridas
    not_quoted: List[str]      # REQ-12
    in_pantry: List[str]
    message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
