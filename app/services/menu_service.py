"""
Armado del menú (POST /api/generar-menu).

1. Arma los espacios del calendario (fecha x comida) y marca las comidas fuera.
2. Filtra recetas aprobadas por perfil alimentario (SC-1) e ingredientes excluidos.
3. Ordena por enfoque nutricional y, si se prioriza el ahorro, por costo por porción
   (ya descontando la despensa); si no, por aprovechamiento de la despensa.
4. Agrupa los espacios según frecuencia de cocina y tolerancia a sobras.
5. Escala porciones y cotiza la canasta completa con quote_items (SC-2, REQ-12).
"""

import random
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models_db import MealPlanDB, MealPlanSlotDB, UserDB
from app.services.catalog_service import normalize, quote_items
from app.services.recipe_filter import filter_recipes, get_user_restrictions
from app.services.recipe_repository import get_approved_recipes

COOK_EVERY = {"diaria": 1, "dias_por_medio": 2, "meal_prep": 4}   # Espacios que cubre una preparación
LEFTOVER_CAP = {"nada": 1, "un_dia": 2, "sin_problema": 4}        # Máximo que tolera el usuario
FOCUS_LABEL = {"balanceada": "balanceado", "alta_proteina": "alto en proteína",
               "baja_carbohidratos": "bajo en carbohidratos", "baja_grasas": "bajo en grasas"}
MAX_COST_CANDIDATES = 25  # Límite de recetas a cotizar una por una (para cumplir los 8 s)


# Armar calendario
def build_slots(start: date, days: int, meals: list[str], meals_out: int) -> list[dict]:
    slots = [{"date": (start + timedelta(days=d)).isoformat(), "meal": m, "origin": "casera"}
             for d in range(days) for m in meals]
    # Reparte las comidas fuera de forma pareja; el usuario puede moverlas en el calendario
    for k in range(meals_out):
        slots[int((k + 0.5) * len(slots) / meals_out)]["origin"] = "fuera"
    return slots

def group_slots(slots: list[dict], batch: int) -> list[list[dict]]:
    """Agrupa espacios caseros consecutivos de la misma comida: cada grupo es una preparación."""
    groups = []
    for meal in ("almuerzo", "cena"):
        home = [s for s in slots if s["meal"] == meal and s["origin"] == "casera"]
        groups += [home[i:i + batch] for i in range(0, len(home), batch)]
    return sorted(groups, key=lambda g: (g[0]["date"], g[0]["meal"]))

# Selección de recetas

def _uses_excluded(recipe: dict, excluded: list[str]) -> bool:
    text = normalize(" ".join(recipe["ingredients"]))
    return any(normalize(e) in text for e in excluded if e.strip())

def _pantry_matches(recipe: dict, pantry: list[str]) -> int:
    text = normalize(" ".join(recipe["ingredients"]))
    return sum(1 for p in pantry if p.strip() and normalize(p) in text)

def cost_per_serving(db: Session, recipe: dict, pantry: list[str]) -> float:
    quote = quote_items(db, [{"original_name": i} for i in recipe["ingredients"]], pantry=pantry)
    return quote["total"] / (recipe.get("servings") or 4)

def rank_recipes(db: Session, recipes: list[dict], focus: str, pantry: list[str], savings: bool) -> list[dict]:
    pool = recipes[:]
    random.shuffle(pool)  # Variedad entre menús cuando hay empates
    pool.sort(key=lambda r: (focus in r.get("diet_focus", []), _pantry_matches(r, pantry)), reverse=True)
    if not savings:
        return pool
    head = pool[:MAX_COST_CANDIDATES]
    costs = {r["id"]: cost_per_serving(db, r, pantry) for r in head}
    head.sort(key=lambda r: (focus not in r.get("diet_focus", []), costs[r["id"]]))
    return head + pool[MAX_COST_CANDIDATES:]

_AMOUNT = re.compile(r"^\s*(\d+(?:[.,]\d+)?(?:/\d+)?)(?:\s*a\s*(\d+(?:[.,]\d+)?(?:/\d+)?))?")

def _to_float(token: str) -> float:
    token = token.replace(",", ".")
    if "/" in token:
        num, den = token.split("/")
        return float(num) / float(den)
    return float(token)

def _fmt(value: float, unit_text: str) -> str:
    """Redondea según la unidad: gramos y ml a enteros, el resto a medios."""
    if re.match(r"\s*(g|gr|kg|ml|l)\b", unit_text):
        value = round(value) if value >= 10 else round(value, 1)
    elif value < 1:
        # Cantidades pequeñas en fracciones de cocina: 1/4, 1/2 o 3/4 (nunca 0)
        quarter = max(1, round(value * 4))
        return {1: "1/4", 2: "1/2", 3: "3/4", 4: "1"}[quarter]
    else:
        value = round(value * 2) / 2
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")

def scale_line(line: str, factor: float) -> str:
    """Multiplica la cantidad inicial del texto: "450 g de pollo" x 0.75 -> "338 g de pollo".
    Si la línea no empieza con un número ("sal al gusto"), se deja igual."""
    match = _AMOUNT.match(line)
    if not match or factor == 1:
        return line
    rest = line[match.end():]
    first = _fmt(_to_float(match.group(1)) * factor, rest)
    if match.group(2):
        first += " a " + _fmt(_to_float(match.group(2)) * factor, rest)
    return first + rest

# Canasta
def build_recipes_and_basket(db: Session, slots: list[dict], diners: int, pantry: list[str],
                             recipes_by_id: dict) -> tuple[list[dict], Optional[dict]]:
    in_menu, cooked = defaultdict(int), defaultdict(int)
    for s in slots:
        if s.get("recipe_id"):
            in_menu[s["recipe_id"]] += 1
            cooked[s["recipe_id"]] += 0 if s.get("is_leftover") else 1
    info, items = [], []
    for rid, times in in_menu.items():
        recipe = recipes_by_id.get(rid)
        if recipe is None:
            continue
        base = recipe.get("servings") or 4
        portions = diners * times
        factor = round(portions / base, 3)
        # Cada vez que se cocina, se prepara para la comida de ese día más sus sobras
        per_cooking = portions / max(cooked[rid], 1)
        cooking_factor = per_cooking / base
        info.append({
            "recipe_id": rid, "title": recipe["title"], "prep_time": recipe.get("prep_time"),
            "instructions": recipe.get("instructions"), "ingredients": recipe["ingredients"],
            "scaled_ingredients": [scale_line(i, cooking_factor) for i in recipe["ingredients"]],
            "portions_per_cooking": round(per_cooking),
            "times_cooked": cooked[rid], "times_in_menu": times, "portions": portions,
            "base_servings": base, "scale_factor": factor,
        })
        items += [{"original_name": i, "scale": factor} for i in recipe["ingredients"]]
    basket = quote_items(db, items, pantry=pantry) if items else None
    return info, basket

def _assignments(plan_id, slots: list[dict]) -> dict:
    out, n_out = {}, 0
    for i, s in enumerate(slots):
        key = f"{s['date']}|{s['meal']}"
        if s["origin"] == "fuera":
            n_out += 1
            out[key] = {"id": f"{plan_id or 'nuevo'}-fuera-{n_out}", "name": "Comida fuera", "origin": "fuera"}
        else:
            out[key] = {"id": f"{plan_id or 'nuevo'}-{i + 1}", "name": s["recipe_title"], "origin": "casera",
                        "recipe_id": s["recipe_id"], "is_leftover": s.get("is_leftover", False)}
    return out

def _budget_warning(user: UserDB, basket: Optional[dict], days: int) -> list[str]:
    if not basket or not user.budget_limit:
        return []
    limit = user.budget_limit * days / 7  # El presupuesto guardado es semanal
    if basket["total"] > limit:
        return [f"La canasta (${basket['total']:,}) supera tu presupuesto para {days} días (${limit:,.0f}).".replace(",", ".")]
    return []

# Flujo del menú
def generate_menu(db: Session, user: UserDB, req) -> dict:
    lg, nu, ck = req.logistics, req.nutrition, req.cooking
    start = req.start_date or (date.today() + timedelta(days=1))
    slots = build_slots(start, lg.days, lg.meals, lg.meals_out)
    name = f"Menú {FOCUS_LABEL[nu.diet_focus]}" + (" y económico" if req.budget.prioritize_savings else "")
    base = {"name": name, "start_date": slots[0]["date"], "end_date": slots[-1]["date"],
            "diners": lg.diners, "budget_limit": user.budget_limit}

    diet_type, allergies = get_user_restrictions(db, user.id)
    approved = get_approved_recipes(db)
    allowed = [r for r in filter_recipes(approved, diet_type, allergies)
               if not _uses_excluded(r, nu.excluded_ingredients)]
    excluded = len(approved) - len(allowed)
    if not allowed:
        return {**base, "assignments": {}, "recipes": [], "basket": None, "excluded_by_restrictions": excluded,
                "message": "No encontramos recetas compatibles con tus restricciones e ingredientes excluidos."}

    warnings = []
    batch = min(COOK_EVERY[ck.cooking_frequency], LEFTOVER_CAP[ck.leftovers_tolerance])
    if COOK_EVERY[ck.cooking_frequency] > batch:
        warnings.append("Como prefieres pocas sobras, el menú considera cocinar más seguido de lo indicado.")

    groups = group_slots(slots, batch)
    ranked = rank_recipes(db, allowed, nu.diet_focus, req.pantry, req.budget.prioritize_savings)
    if len(ranked) < len(groups):
        warnings.append(f"Solo hay {len(ranked)} recetas compatibles para {len(groups)} preparaciones; algunas se repiten.")
    if ranked and nu.diet_focus not in ranked[0].get("diet_focus", []):
        warnings.append("No hay recetas con ese enfoque nutricional; se usaron otras compatibles.")

    for n, group in enumerate(groups):
        recipe = ranked[n % len(ranked)]
        for k, s in enumerate(group):
            s.update(recipe_id=recipe["id"], recipe_title=recipe["title"], is_leftover=k > 0)

    recipes_by_id = {r["id"]: r for r in allowed}
    info, basket = build_recipes_and_basket(db, slots, lg.diners, req.pantry, recipes_by_id)
    warnings += _budget_warning(user, basket, lg.days)

    plan = MealPlanDB(user_id=user.id, name=name, start_date=base["start_date"], end_date=base["end_date"],
                      diners=lg.diners, request=req.model_dump(mode="json"),
                      total_cost=basket["total"] if basket else None)
    for s in slots:
        plan.slots.append(MealPlanSlotDB(date=s["date"], meal=s["meal"], origin=s["origin"],
                                         recipe_id=s.get("recipe_id"), recipe_title=s.get("recipe_title"),
                                         portions=lg.diners if s["origin"] == "casera" else 0,
                                         is_leftover=s.get("is_leftover", False)))
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return {**base, "id": plan.id, "created_at": plan.created_at, "assignments": _assignments(plan.id, slots),
            "recipes": info, "basket": basket, "excluded_by_restrictions": excluded,
            "message": None, "warnings": warnings}

def menu_detail(db: Session, plan: MealPlanDB, user: UserDB) -> dict:
    """Menú guardado con la canasta recotizada con los últimos precios registrados."""
    slots = [{"date": s.date, "meal": s.meal, "origin": s.origin, "recipe_id": s.recipe_id,
              "recipe_title": s.recipe_title or "Receta no disponible", "is_leftover": s.is_leftover}
             for s in plan.slots]
    recipes_by_id = {r["id"]: r for r in get_approved_recipes(db)}
    info, basket = build_recipes_and_basket(db, slots, plan.diners, plan.request.get("pantry", []), recipes_by_id)
    warnings = []
    if any(s["recipe_id"] and s["recipe_id"] not in recipes_by_id for s in slots):
        warnings.append("Algunas recetas del menú ya no están disponibles y no se cotizaron.")
    diet_type, allergies = get_user_restrictions(db, user.id)
    used = [recipes_by_id[s["recipe_id"]] for s in slots if s["recipe_id"] in recipes_by_id]
    no_longer_ok = {r["title"] for r in used if not filter_recipes([r], diet_type, allergies)}
    if no_longer_ok:
        warnings.append("Según tu perfil alimentario actual, estas recetas ya no son compatibles: "
                        + ", ".join(sorted(no_longer_ok)) + ". Te recomendamos generar un menú nuevo.")
    return {"id": plan.id, "name": plan.name, "created_at": plan.created_at, "start_date": plan.start_date,
            "end_date": plan.end_date, "diners": plan.diners, "budget_limit": user.budget_limit,
            "assignments": _assignments(plan.id, slots), "recipes": info, "basket": basket,
            "message": None, "warnings": warnings + _budget_warning(user, basket, plan.request["logistics"]["days"])}