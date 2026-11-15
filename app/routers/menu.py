from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models_db import MealPlanDB, UserDB
from app.schemas.menu import GenerarMenuRequest, MenuOut, MenuSummary
from app.services.menu_service import generate_menu, menu_detail

router = APIRouter(prefix="/api", tags=["Armado del menú"])

@router.post("/generar-menu", response_model=MenuOut, status_code=status.HTTP_201_CREATED)
def create_menu(req: GenerarMenuRequest, user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Arma el menú según el formulario del front y el perfil alimentario, y devuelve la canasta cotizada."""
    return generate_menu(db, user, req)

@router.get("/menus", response_model=List[MenuSummary])
def list_menus(user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Historial de menús del usuario, del más nuevo al más antiguo."""
    plans = db.query(MealPlanDB).filter(MealPlanDB.user_id == user.id).order_by(MealPlanDB.id.desc()).all()
    return [{"id": p.id, "name": p.name, "created_at": p.created_at, "start_date": p.start_date,
             "end_date": p.end_date, "diners": p.diners, "total_cost": p.total_cost,
             "home_meals": sum(s.origin == "casera" for s in p.slots),
             "meals_out": sum(s.origin == "fuera" for s in p.slots)} for p in plans]

@router.get("/menus/{menu_id}", response_model=MenuOut)
def read_menu(menu_id: int, user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detalle de un menú guardado."""
    plan = db.query(MealPlanDB).filter(MealPlanDB.id == menu_id, MealPlanDB.user_id == user.id).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menú no encontrado.")
    return menu_detail(db, plan, user)