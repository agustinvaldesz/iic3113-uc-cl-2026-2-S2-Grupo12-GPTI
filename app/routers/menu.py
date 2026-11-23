from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models_db import MealPlanDB, RecipeDB, UserDB
from app.schemas.menu import GenerarMenuRequest, MealMoveRequest, MealMoveResponse, MenuOut, MenuSummary, RecipeDetailOut, UpdateAssignmentsRequest
from app.services.menu_service import MealMovedError, MenuEditError, NotEnoughRecipesError, generate_menu, menu_detail, move_meal, recipe_detail, update_assignments
from app.services.recipe_repository import recipe_to_dict

router = APIRouter(prefix="/api", tags=["Armado del menú"])

@router.post("/menus", response_model=MenuOut, status_code=status.HTTP_201_CREATED)
@router.post("/generar-menu", response_model=MenuOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_menu(req: GenerarMenuRequest, user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Arma el menú según el formulario del front y el perfil alimentario, y devuelve la canasta cotizada."""
    try:
        return generate_menu(db, user, req)
    except NotEnoughRecipesError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/menus", response_model=List[MenuSummary])
def list_menus(user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Historial de menús del usuario, del más nuevo al más antiguo."""
    plans = db.query(MealPlanDB).filter(MealPlanDB.user_id == user.id).order_by(MealPlanDB.id.desc()).all()
    return [{"id": p.id, "name": p.name, "created_at": p.created_at, "start_date": p.start_date,
             "end_date": p.end_date, "diners": p.diners, "total_cost": p.total_cost,
             "home_meals": sum(s.origin == "casera" for s in p.slots),
             "out_meals": sum(s.origin == "fuera" for s in p.slots)} for p in plans]

@router.get("/menus/{menu_id}", response_model=MenuOut)
def read_menu(menu_id: int, user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detalle de un menú guardado (meals para el calendario, y la canasta recotizada)."""
    return menu_detail(db, _get_own_plan(db, menu_id, user), user)

@router.post("/menus/{menu_id}/meals/move", response_model=MealMoveResponse)
def move_menu_meal(menu_id: int, data: MealMoveRequest,
                   user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mueve un plato (drag & drop). Si el destino está ocupado, intercambia los dos platos."""
    plan = _get_own_plan(db, menu_id, user)
    try:
        return {"meals": move_meal(db, plan, data.from_, data.to)}
    except MealMovedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MenuEditError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    
def _get_own_plan(db: Session, menu_id: int, user: UserDB) -> MealPlanDB:
    plan = db.query(MealPlanDB).filter(MealPlanDB.id == menu_id, MealPlanDB.user_id == user.id).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontramos ese menú.")
    return plan

@router.put("/menus/{menu_id}/assignments", response_model=MenuOut)
def edit_menu(menu_id: int, data: UpdateAssignmentsRequest,
              user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Guarda el calendario completo editado (platos quitados o cambiados) y recotiza la canasta."""
    plan = _get_own_plan(db, menu_id, user)
    try:
        return update_assignments(db, plan, user, data.assignments)
    except MenuEditError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

@router.delete("/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu(menu_id: int, user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina un menú del historial."""
    db.delete(_get_own_plan(db, menu_id, user))
    db.commit()

@router.get("/recipes/{recipe_id}", response_model=RecipeDetailOut, tags=["Recetas"])
def read_recipe(recipe_id: int, servings: Optional[int] = Query(default=None, ge=1, le=50),
                db: Session = Depends(get_db)):
    """Receta paso a paso para el modal, con cantidades escaladas a 'servings' personas."""
    recipe = db.query(RecipeDB).filter(RecipeDB.id == recipe_id, RecipeDB.status == "aprobada").first()
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontramos esta receta.")
    return recipe_detail(recipe_to_dict(recipe), servings)