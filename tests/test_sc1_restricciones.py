"""Pruebas de la Solicitud de cambio SC-1: filtro excluyente por dieta y alergias."""
from app.services.llm_service import load_recipes
from app.services.recipe_filter import filter_recipes, is_recipe_allowed


def _profile(client, headers, diet="con_carne", allergies=(), consent=True):
    return client.put("/api/user/dietary-profile", headers=headers,
                      json={"diet_type": diet, "allergies": list(allergies), "consent": consent})


def _recommend(client, headers, intent="balance"):
    return client.post("/api/recipes/recommend", headers=headers, json={"intent": intent})


def test_todas_las_recetas_base_tienen_etiquetas():
    for r in load_recipes():
        assert r.get("diet_type") in {"con_carne", "vegetariana", "vegana"}, r["title"]
        assert isinstance(r.get("allergens"), list), r["title"]


def test_filtro_excluye_alergenos_y_dieta():
    recetas = load_recipes()
    for r in filter_recipes(recetas, "con_carne", ["gluten", "lactosa"]):
        assert not {"gluten", "lactosa"} & set(r["allergens"])
    assert all(r["diet_type"] == "vegana" for r in filter_recipes(recetas, "vegana", []))


def test_receta_sin_etiquetas_no_se_ofrece_a_usuario_con_restricciones():
    assert not is_recipe_allowed({"title": "sin etiquetas"}, "con_carne", ["mariscos"])
    assert is_recipe_allowed({"title": "sin etiquetas"}, "con_carne", [])


def test_guardar_perfil_exige_consentimiento(client, auth_headers):
    assert _profile(client, auth_headers, allergies=["gluten"], consent=False).status_code == 422
    assert _profile(client, auth_headers, allergies=["gluten"]).status_code == 200


def test_recomendacion_respeta_perfil(client, auth_headers):
    _profile(client, auth_headers, diet="con_carne", allergies=["gluten", "lactosa"])
    data = _recommend(client, auth_headers).json()
    assert data["recommendations"], data
    recetas = {r["id"]: r for r in load_recipes()}
    for rec in data["recommendations"]:
        assert not {"gluten", "lactosa"} & set(recetas[rec["recipe_id"]]["allergens"])
    assert data["excluded_by_restrictions"] > 0


def test_sin_recetas_compatibles_avisa_en_vez_de_recomendar(client, auth_headers):
    _profile(client, auth_headers, diet="vegana", allergies=["gluten"])
    data = _recommend(client, auth_headers).json()
    assert data["recommendations"] == []
    assert data["message"]


def test_eliminar_perfil_quita_el_filtro(client, auth_headers):
    _profile(client, auth_headers, diet="vegana", allergies=["gluten"])
    assert client.delete("/api/user/dietary-profile", headers=auth_headers).status_code == 204
    data = _recommend(client, auth_headers).json()
    assert data["excluded_by_restrictions"] == 0
    assert data["recommendations"]


def test_recomendar_requiere_token(client):
    assert _recommend(client, {}).status_code in (401, 403)
