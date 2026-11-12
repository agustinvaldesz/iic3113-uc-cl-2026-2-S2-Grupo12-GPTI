from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models_db import UserDB
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse
from app.services.llm_service import recommend_and_normalize_recipes, load_recipes
from app.services.recipe_filter import filter_recipes, get_user_restrictions, restrictions_to_text

router = APIRouter(
    prefix="/api/recipes",
    tags=["Recomendaciones y LLM"]
)

ALLOWED_INTENTS = {"ahorro", "saludable", "balance", "vegano", "vegetariano"}


@router.post("/recommend", response_model=RecommendationResponse)
def get_recommendations(
    request: RecommendationRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    intent_clean = request.intent.lower().strip()
    if intent_clean not in ALLOWED_INTENTS:
        valid_options = ", ".join(f"'{i}'" for i in sorted(ALLOWED_INTENTS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Intención no válida. Use una de las siguientes: {valid_options}."
        )

    # SC-1: el perfil alimentario guardado (con consentimiento) se aplica como filtro excluyente
    diet_type, allergies = get_user_restrictions(db, current_user.id)
    all_recipes = load_recipes()
    allowed_recipes = filter_recipes(all_recipes, diet_type, allergies)
    excluded = len(all_recipes) - len(allowed_recipes)

    if not allowed_recipes:
        return {
            "user_intent": request.intent,
            "recommendations": [],
            "excluded_by_restrictions": excluded,
            "message": "No encontramos recetas compatibles con tus restricciones alimentarias. "
                       "Puedes revisar tu perfil alimentario o probar más tarde.",
        }

    dietary_restrictions = restrictions_to_text(diet_type, allergies) + list(request.dietary_restrictions or [])

    llm_results = recommend_and_normalize_recipes(
        intent=intent_clean,
        user_ingredients=request.shopping_list,
        dietary_restrictions=dietary_restrictions,
        recipes=allowed_recipes,
    )

    if not llm_results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible generar las recomendaciones."
        )

    return {
        "user_intent": request.intent,
        "recommendations": llm_results,
        "excluded_by_restrictions": excluded,
        "message": None,
    }
