import random
from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header, status

from app.schemas.menus import (
    MenuCreateRequest,
    MenuSummaryOut,
    MenuDetailOut,
    MealMoveRequest,
    MealMoveResponse,
)
from app.services.supabase_service import supabase
from app.services.llm_service import load_recipes
from app.routers.recommendations import _get_restrictions_from_profile

router = APIRouter(prefix="/api/menus", tags=["Menús y Calendario"])

# Adaptador de autenticación: usa tu dependencia get_current_user existente si está disponible,
# o extrae el user_id del token/header para compatibilidad inmediata.
try:
    from app.routers.auth import get_current_user  # Ajusta la ruta si tu auth está en otro módulo
except ImportError:
    def get_current_user(
        authorization: str = Header(None),
        x_user_id: str = Header(None, alias="X-User-Id")
    ):
        if authorization and authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "").strip()
            # Si usan Supabase Auth JWT, valida el usuario; si no, usa el sub/token
            if supabase:
                try:
                    user_res = supabase.auth.get_user(token)
                    if user_res and user_res.user:
                        return {"id": str(user_res.user.id)}
                except Exception:
                    pass
            return {"id": token}
        if x_user_id:
            return {"id": x_user_id}
        raise HTTPException(status_code=401, detail="No autorizado. Inicia sesión nuevamente.")

def _get_user_id(current_user) -> str:
    if isinstance(current_user, dict):
        return str(current_user.get("id") or current_user.get("user_id"))
    return str(getattr(current_user, "id", current_user))

MENU_TITLES = {
    "balanceada": "Menú balanceado",
    "alta_proteina": "Semana alta en proteína",
    "baja_carbohidratos": "Menú bajo en carbohidratos",
    "baja_grasas": "Menú bajo en grasas",
}

def _filter_compatible_recipes(user_id: str, excluded_ingredients: list[str]) -> list[dict]:
    restrictions = [r.lower() for r in _get_restrictions_from_profile(user_id)]
    excluded = [e.lower().strip() for e in excluded_ingredients]

    recipes = []
    if supabase:
        try:
            res = supabase.table("recipes").select("*").eq("status", "aprobada").execute()
            if res.data:
                recipes = res.data
        except Exception:
            pass
    if not recipes:
        recipes = load_recipes()

    compatible = []
    for r in recipes:
        ing_text = " ".join(r.get("ingredients", [])).lower()
        title_text = r.get("title", "").lower()
        cat_text = (r.get("diet_type") or r.get("category") or "").lower()

        # Verificar ingredientes excluidos por el usuario
        if any(ex in ing_text or ex in title_text for ex in excluded):
            continue

        # Verificar restricciones del perfil alimentario
        if "vegano estricto" in restrictions and "vegan" not in cat_text:
            continue
        if "vegetariano (sin carne ni pescado)" in restrictions and any(
            m in ing_text for m in ["pollo", "carne", "res", "cerdo", "pescado", "atún", "salmón", "camarón"]
        ):
            continue
        if "sin gluten" in restrictions and any(
            g in ing_text for g in ["trigo", "harina de trigo", "pan ", "pasta", "fideos", "cebada"]
        ):
            continue
        if "sin lactosa" in restrictions and any(
            l in ing_text for l in ["leche", "queso", "crema", "mantequilla", "yogur"]
        ) and "sin lactosa" not in ing_text and "vegetal" not in ing_text and "coco" not in ing_text:
            continue

        compatible.append(r)
    return compatible

def _sort_meals(meals: list[dict]) -> list[dict]:
    slot_order = {"almuerzo": 0, "cena": 1}
    return sorted(meals, key=lambda m: (str(m["date"]), slot_order.get(m["slot"], 2)))

# 3.1 Generar un menú (POST /api/menus)
@router.post("", response_model=MenuDetailOut, status_code=status.HTTP_201_CREATED)
def create_menu(payload: MenuCreateRequest, current_user=Depends(get_current_user)):
    if not supabase:
        raise HTTPException(status_code=502, detail="No pudimos conectar con la base de datos.")

    user_id = _get_user_id(current_user)
    start_dt = payload.start_date
    days = payload.logistics.days
    end_dt = start_dt + timedelta(days=days - 1)
    meals_slots = payload.logistics.meals
    meals_out_count = payload.logistics.meals_out

    # Construir todos los slots cronológicos
    all_slots = []
    for d in range(days):
        curr_date = start_dt + timedelta(days=d)
        for s in meals_slots:
            all_slots.append({"date": curr_date.isoformat(), "slot": s})

    total_slots = len(all_slots)
    home_slots_count = total_slots - meals_out_count

    compatible_recipes = _filter_compatible_recipes(user_id, payload.nutrition.excluded_ingredients)
    if not compatible_recipes:
        raise HTTPException(
            status_code=409,
            detail="No encontramos suficientes recetas compatibles con tus restricciones. Prueba con menos días o revisa tus ingredientes excluidos."
        )

    # Si no tolera sobras ("nada"), exigir suficientes recetas distintas para no repetir en días seguidos
    if payload.cooking.leftovers_tolerance == "nada" and len(compatible_recipes) < 2 and home_slots_count > 1:
        raise HTTPException(
            status_code=409,
            detail="No encontramos suficientes recetas compatibles con tus restricciones. Prueba con menos días o revisa tus ingredientes excluidos."
        )

    # Elegir aleatoriamente en qué slots van las comidas fuera de casa
    out_indices = set(random.sample(range(total_slots), meals_out_count))

    generated_meals = []
    last_recipe_id = None
    repeat_streak = 0
    recipe_pool = compatible_recipes.copy()
    random.shuffle(recipe_pool)
    pool_idx = 0

    for idx, slot_info in enumerate(all_slots):
        if idx in out_indices:
            generated_meals.append({
                "date": slot_info["date"],
                "slot": slot_info["slot"],
                "name": "Comida fuera de casa",
                "source": "fuera",
                "recipe_id": None,
            })
            last_recipe_id = None
            repeat_streak = 0
        else:
            # Lógica de repetición según cooking_frequency y leftovers_tolerance
            can_repeat = (
                payload.cooking.leftovers_tolerance != "nada"
                and payload.cooking.cooking_frequency in ("dias_por_medio", "meal_prep")
                and last_recipe_id is not None
                and repeat_streak < (1 if payload.cooking.leftovers_tolerance == "un_dia" else 2)
            )

            if can_repeat:
                chosen = next((r for r in compatible_recipes if r["id"] == last_recipe_id), recipe_pool[0])
                repeat_streak += 1
            else:
                chosen = recipe_pool[pool_idx % len(recipe_pool)]
                # Evitar repetir la misma receta en días consecutivos si leftovers_tolerance == "nada"
                if payload.cooking.leftovers_tolerance == "nada" and chosen["id"] == last_recipe_id and len(recipe_pool) > 1:
                    pool_idx += 1
                    chosen = recipe_pool[pool_idx % len(recipe_pool)]
                pool_idx += 1
                repeat_streak = 0

            last_recipe_id = chosen["id"]
            generated_meals.append({
                "date": slot_info["date"],
                "slot": slot_info["slot"],
                "name": chosen["title"],
                "source": "casera",
                "recipe_id": chosen["id"],
            })

    now_utc = datetime.now(timezone.utc)
    menu_name = MENU_TITLES.get(payload.nutrition.diet_focus, "Menú personalizado")
    config_json = {
        "logistics": payload.logistics.model_dump(),
        "nutrition": payload.nutrition.model_dump(),
        "cooking": payload.cooking.model_dump(),
    }

    try:
        menu_res = supabase.table("menus").insert({
            "user_id": user_id,
            "name": menu_name,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "config": config_json,
            "created_at": now_utc.isoformat(),
        }).execute()

        created_menu = menu_res.data[0]
        menu_id = created_menu["id"]

        for m in generated_meals:
            m["menu_id"] = menu_id

        meals_res = supabase.table("menu_meals").insert(generated_meals).execute()
        saved_meals = _sort_meals(meals_res.data)

        return {
            "id": menu_id,
            "name": menu_name,
            "created_at": now_utc,
            "start_date": start_dt,
            "end_date": end_dt,
            "config": config_json,
            "meals": saved_meals,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail="No pudimos generar tu menú en este momento. Intenta de nuevo.")

# 3.2 Listar mis menús (GET /api/menus)
@router.get("", response_model=List[MenuSummaryOut])
def list_menus(current_user=Depends(get_current_user)):
    user_id = _get_user_id(current_user)
    menus_res = supabase.table("menus")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()

    if not menus_res.data:
        return []

    menu_ids = [m["id"] for m in menus_res.data]
    meals_res = supabase.table("menu_meals")\
        .select("menu_id, source")\
        .in_("menu_id", menu_ids)\
        .execute()

    counts = {mid: {"casera": 0, "fuera": 0} for mid in menu_ids}
    for row in (meals_res.data or []):
        mid = row["menu_id"]
        src = row["source"]
        if mid in counts and src in counts[mid]:
            counts[mid][src] += 1

    summaries = []
    for m in menus_res.data:
        mid = m["id"]
        summaries.append({
            "id": mid,
            "name": m["name"],
            "created_at": m["created_at"],
            "start_date": m["start_date"],
            "end_date": m["end_date"],
            "home_meals": counts[mid]["casera"],
            "out_meals": counts[mid]["fuera"],
        })
    return summaries

# 3.3 Ver un menú completo (GET /api/menus/{menu_id})
@router.get("/{menu_id}", response_model=MenuDetailOut)
def get_menu_detail(menu_id: int, current_user=Depends(get_current_user)):
    user_id = _get_user_id(current_user)
    menu_res = supabase.table("menus")\
        .select("*")\
        .eq("id", menu_id)\
        .eq("user_id", user_id)\
        .execute()

    if not menu_res.data:
        raise HTTPException(status_code=404, detail="No encontramos ese menú.")

    menu = menu_res.data[0]
    meals_res = supabase.table("menu_meals")\
        .select("id, date, slot, name, source, recipe_id")\
        .eq("menu_id", menu_id)\
        .execute()

    return {
        "id": menu["id"],
        "name": menu["name"],
        "created_at": menu["created_at"],
        "start_date": menu["start_date"],
        "end_date": menu["end_date"],
        "config": menu["config"],
        "meals": _sort_meals(meals_res.data or []),
    }

# 3.4 Mover o intercambiar un plato (POST /api/menus/{menu_id}/meals/move)
@router.post("/{menu_id}/meals/move", response_model=MealMoveResponse)
def move_meal(menu_id: int, payload: MealMoveRequest, current_user=Depends(get_current_user)):
    user_id = _get_user_id(current_user)
    menu_res = supabase.table("menus")\
        .select("id, start_date, end_date")\
        .eq("id", menu_id)\
        .eq("user_id", user_id)\
        .execute()

    if not menu_res.data:
        raise HTTPException(status_code=404, detail="No encontramos ese menú.")

    menu = menu_res.data[0]
    start_dt = datetime.strptime(str(menu["start_date"]), "%Y-%m-%d").date()
    end_dt = datetime.strptime(str(menu["end_date"]), "%Y-%m-%d").date()

    src = payload.from_slot
    dst = payload.to_slot

    if not (start_dt <= src.date <= end_dt and start_dt <= dst.date <= end_dt) or (src.date == dst.date and src.slot == dst.slot):
        raise HTTPException(status_code=422, detail="Solo puedes mover platos dentro de las fechas del menú.")

    meals_res = supabase.table("menu_meals")\
        .select("id, date, slot, name, source, recipe_id")\
        .eq("menu_id", menu_id)\
        .execute()
    meals = meals_res.data or []

    source_meal = next((m for m in meals if str(m["date"]) == src.date.isoformat() and m["slot"] == src.slot), None)
    if not source_meal:
        raise HTTPException(status_code=409, detail="Ese plato ya no está en ese lugar. Actualizamos tu calendario.")

    target_meal = next((m for m in meals if str(m["date"]) == dst.date.isoformat() and m["slot"] == dst.slot), None)

    if target_meal:
        # Intercambio seguro usando una fecha temporal fuera del rango para no violar uq_menu_slot
        temp_date = "1970-01-01"
        supabase.table("menu_meals").update({"date": temp_date}).eq("id", source_meal["id"]).execute()
        supabase.table("menu_meals").update({"date": src.date.isoformat(), "slot": src.slot}).eq("id", target_meal["id"]).execute()
        supabase.table("menu_meals").update({"date": dst.date.isoformat(), "slot": dst.slot}).eq("id", source_meal["id"]).execute()
    else:
        # Movimiento simple a slot vacío
        supabase.table("menu_meals").update({"date": dst.date.isoformat(), "slot": dst.slot}).eq("id", source_meal["id"]).execute()

    updated_res = supabase.table("menu_meals")\
        .select("id, date, slot, name, source, recipe_id")\
        .eq("menu_id", menu_id)\
        .execute()

    return {"meals": _sort_meals(updated_res.data or [])}