from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Preferencias del usuario para NutriCart (RF-01)
    dietary_preference = Column(String, default="balance")  # "ahorro", "saludable", "balance"
    budget_limit = Column(Float, nullable=True)  # Presupuesto semanal estimado
    role = Column(String, nullable=False, default="consumidor")  # "consumidor", "gestor" o "admin"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RecipeDB(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    intent_category = Column(String, nullable=False, default="balance")  # "ahorro", "saludable", "balance"
    diet_type = Column(String, nullable=False) # ej: "con_carne"
    allergens = Column(JSON, nullable=False, default=list)  # ej: ["gluten", "lactosa"]
    servings = Column(Integer, nullable=False) # Porciones por receta
    prep_time = Column(String, nullable=True)
    instructions = Column(Text, nullable=False)
    ingredient_lines = Column(JSON, nullable=False, default=list)  # Ej: ["450 g de carne molida", "1 cebolla"]
    diet_focus = Column(JSON, nullable=False, default=list)  # Ej: ["balanceada", "alta_proteina"]
    status = Column(String, nullable=False, default="pendiente") # "pendiente", "aprobada", "rechazada"
    source = Column(String, nullable=False, default="manual")  # "manual", "llm" o "scraping"
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Usuario que la subió o solicitó al LLM
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Gestor que revisó la receta
    reviewed_at = Column(DateTime, nullable=True) # Fecha de aprobación o rechazo
    review_notes = Column(Text, nullable=True) # Motivo del rechazo u observaciones
    created_at = Column(DateTime, default=datetime.utcnow)
    ingredients = relationship("RecipeIngredientDB", back_populates="recipe", cascade="all, delete-orphan")

class IngredientDB(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)  # nombre normalizado
    category = Column(String, nullable=True)  # "carnes", "verduras" (desglose de la canasta)
    default_unit = Column(String, nullable=False)  # "g", "ml" o "unidad"

class RecipeIngredientDB(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_ingredient"),)
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity = Column(Float, nullable=False)  # Cantidad necesaria
    unit = Column(String, nullable=False) # unidad de medida del ingrediente
    is_optional = Column(Boolean, default=False) # decorativo o elementos para resaltar el sabor, esencia de vainilla

    recipe = relationship("RecipeDB", back_populates="ingredients")
    ingredient = relationship("IngredientDB")
    
class ProductCacheDB(Base):
    __tablename__ = "products_cache"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow)

class UserDietaryProfileDB(Base):
    __tablename__ = "user_dietary_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    diet_type = Column(String, nullable=False, default="con_carne")  # "con_carne", "vegetariana" o "vegana"
    allergies = Column(JSON, nullable=False, default=list)           # Lista de alergias
    consent_at = Column(DateTime, nullable=True) # Fecha en que el usuario dio su consentimiento
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class IngredientProductDB(Base):
    """Asocia un ingrediente con uno o más productos del catálogo de Lider."""
    __tablename__ = "ingredient_products"
    __table_args__ = (UniqueConstraint("ingredient_id", "product_id", name="uq_ingredient_product"),)

    id = Column(Integer, primary_key=True, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products_cache.id", ondelete="CASCADE"), nullable=False)
    package_quantity = Column(Float, nullable=False)  # Contenido del envase, ej: 500
    package_unit = Column(String, nullable=False)  # "g", "ml" o "unidad"
    is_default = Column(Boolean, default=False)  # Producto por defecto en la cotización

    ingredient = relationship("IngredientDB")
    product = relationship("ProductCacheDB")

class MealPlanDB(Base):
    """Menú generado para un usuario."""
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    start_date = Column(String, nullable=False)  # YYYY-MM-DD
    end_date = Column(String, nullable=False)    # YYYY-MM-DD
    diners = Column(Integer, nullable=False)
    request = Column(JSON, nullable=False)       # Formulario original (para regenerar o auditar)
    total_cost = Column(Integer, nullable=True)  # Total al momento de crearlo
    created_at = Column(DateTime, default=datetime.utcnow)

    slots = relationship("MealPlanSlotDB", back_populates="plan", cascade="all, delete-orphan",
                         order_by="MealPlanSlotDB.id")

class MealPlanSlotDB(Base):
    """Una fecha y una comida (almuerzo o cena)."""
    __tablename__ = "meal_plan_slots"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    date = Column(String, nullable=False) # YYYY-MM-DD
    meal = Column(String, nullable=False) # "almuerzo" o "cena"
    origin = Column(String, nullable=False) # "casera" o "fuera"
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True)
    recipe_title = Column(String, nullable=True)  # Copia del título por si la receta cambia
    portions = Column(Integer, nullable=False, default=0)
    is_leftover = Column(Boolean, default=False)  # True si se come lo cocinado en un espacio anterior

    plan = relationship("MealPlanDB", back_populates="slots")