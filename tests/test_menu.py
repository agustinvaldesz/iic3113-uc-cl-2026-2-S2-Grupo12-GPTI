"""Pruebas de POST /api/generar-menu con el contrato del front."""

def _payload(**overrides):
    body = {
        "logistics": {"diners": 2, "days": 7, "meals": ["almuerzo", "cena"], "meals_out": 3},
        "nutrition": {"diet_focus": "alta_proteina", "excluded_ingredients": []},
        "cooking": {"cooking_frequency": "dias_por_medio", "leftovers_tolerance": "un_dia"},
        "budget": {"prioritize_savings": True},
        "pantry": ["arroz"],
        "start_date": "2026-11-16",
    }
    for key, value in overrides.items():
        body[key] = {**body[key], **value} if isinstance(value, dict) else value
    return body

def _menu(client, headers, **overrides):
    return client.post("/api/generar-menu", headers=headers, json=_payload(**overrides))

def test_menu_llena_el_calendario(client, auth_headers):
    r = _menu(client, auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert len(data["assignments"]) == 14
    assert "2026-11-16|almuerzo" in data["assignments"] and data["end_date"] == "2026-11-22"
    assert sum(s["origin"] == "fuera" for s in data["assignments"].values()) == 3
    assert data["basket"]["total"] > 0

def test_porciones_coinciden_con_comensales(client, auth_headers):
    data = _menu(client, auth_headers).json()
    caseras = [s for s in data["assignments"].values() if s["origin"] == "casera"]
    assert sum(r["times_in_menu"] for r in data["recipes"]) == len(caseras)
    for r in data["recipes"]:
        assert r["portions"] == 2 * r["times_in_menu"]

def test_sin_sobras_no_repite_seguido(client, auth_headers):
    data = _menu(client, auth_headers, cooking={"leftovers_tolerance": "nada"}).json()
    assert all(not s.get("is_leftover") for s in data["assignments"].values())
    assert any("cocinar más seguido" in w for w in data["warnings"])

def test_excluir_ingrediente(client, auth_headers):
    data = _menu(client, auth_headers, nutrition={"excluded_ingredients": ["pollo"]}).json()
    for r in data["recipes"]:
        assert not any("pollo" in i.lower() for i in r["ingredients"])

def test_respeta_perfil_alimentario(client, auth_headers):
    client.put("/api/user/dietary-profile", headers=auth_headers,
               json={"diet_type": "vegana", "allergies": ["gluten"], "consent": True})
    data = _menu(client, auth_headers).json()
    assert data["assignments"] == {} and data["message"]

def test_comidas_fuera_deben_ser_menos_que_el_total(client, auth_headers):
    r = _menu(client, auth_headers, logistics={"days": 1, "meals": ["cena"], "meals_out": 1})
    assert r.status_code == 422

def test_historial_y_detalle_solo_del_dueno(client, auth_headers):
    creado = _menu(client, auth_headers).json()
    historial = client.get("/api/menus", headers=auth_headers).json()
    assert historial[0]["id"] == creado["id"] and historial[0]["meals_out"] == 3
    detalle = client.get(f"/api/menus/{creado['id']}", headers=auth_headers).json()
    assert detalle["assignments"] == creado["assignments"]

    client.post("/api/auth/register", json={"full_name": "Otra", "email": "otra_menu@nutricart.cl", "password": "clave1234"})
    token = client.post("/api/auth/login", json={"email": "otra_menu@nutricart.cl", "password": "clave1234"}).json()["access_token"]
    assert client.get(f"/api/menus/{creado['id']}", headers={"Authorization": f"Bearer {token}"}).status_code == 404

def test_cotizacion_escala_cantidades(client):
    base = client.post("/api/basket/quote", json={"items": [{"original_name": "450 g de pechuga de pollo"}]}).json()
    doble = client.post("/api/basket/quote", json={"items": [{"original_name": "450 g de pechuga de pollo", "scale": 2}]}).json()
    assert doble["lines"][0]["quantity_needed"] == 2 * base["lines"][0]["quantity_needed"]

def test_ingredientes_escalados_por_preparacion(client, auth_headers):
    data = _menu(client, auth_headers, logistics={"diners": 3, "days": 1, "meals": ["almuerzo"], "meals_out": 0},
                 cooking={"cooking_frequency": "diaria", "leftovers_tolerance": "nada"}).json()
    receta = data["recipes"][0]
    assert receta["portions_per_cooking"] == 3
    assert len(receta["scaled_ingredients"]) == len(receta["ingredients"])
    if receta["base_servings"] != 3:
        assert receta["scaled_ingredients"] != receta["ingredients"]

def test_escalar_linea_de_ingrediente():
    from app.services.menu_service import scale_line
    assert scale_line("450 g de pechuga de pollo", 0.75) == "338 g de pechuga de pollo"
    assert scale_line("1 a 2 cucharadas de aceite", 1.5) == "1,5 a 3 cucharadas de aceite"
    assert scale_line("Sal al gusto", 2) == "Sal al gusto"
    assert scale_line("1/4 taza de agua", 0.5) == "1/4 taza de agua"
    assert scale_line("1 lata de piña", 0.5) == "1/2 lata de piña"

def test_detalle_avisa_si_cambio_el_perfil(client, auth_headers):
    creado = _menu(client, auth_headers, nutrition={"diet_focus": "alta_proteina"}).json()
    client.put("/api/user/dietary-profile", headers=auth_headers,
               json={"diet_type": "vegana", "allergies": ["gluten"], "consent": True})
    detalle = client.get(f"/api/menus/{creado['id']}", headers=auth_headers).json()
    assert any("ya no son compatibles" in w for w in detalle["warnings"])

def _slots_editables(data):
    return {k: {"origin": v["origin"], "recipe_id": v.get("recipe_id")} for k, v in data["assignments"].items()}

def test_editar_calendario_intercambia_y_recalcula(client, auth_headers):
    creado = _menu(client, auth_headers, logistics={"days": 3, "meals": ["almuerzo"], "meals_out": 0},
                   cooking={"cooking_frequency": "diaria", "leftovers_tolerance": "nada"}).json()
    slots = _slots_editables(creado)
    a, b = "2026-11-16|almuerzo", "2026-11-17|almuerzo"
    slots[a], slots[b] = slots[b], slots[a]
    r = client.put(f"/api/menus/{creado['id']}/assignments", headers=auth_headers, json={"assignments": slots})
    assert r.status_code == 200
    nuevo = r.json()["assignments"]
    assert nuevo[a]["recipe_id"] == creado["assignments"][b]["recipe_id"]
    assert nuevo[b]["recipe_id"] == creado["assignments"][a]["recipe_id"]
    # Se guardó: al reabrir el menú se ve igual
    assert client.get(f"/api/menus/{creado['id']}", headers=auth_headers).json()["assignments"] == nuevo

def test_editar_marca_sobras_y_comidas_fuera(client, auth_headers):
    creado = _menu(client, auth_headers, logistics={"days": 3, "meals": ["almuerzo"], "meals_out": 0}).json()
    receta = creado["assignments"]["2026-11-16|almuerzo"]["recipe_id"]
    slots = {
        "2026-11-16|almuerzo": {"origin": "casera", "recipe_id": receta},
        "2026-11-17|almuerzo": {"origin": "casera", "recipe_id": receta},
        "2026-11-18|almuerzo": {"origin": "fuera"},
    }
    nuevo = client.put(f"/api/menus/{creado['id']}/assignments", headers=auth_headers, json={"assignments": slots}).json()
    assert nuevo["assignments"]["2026-11-17|almuerzo"]["is_leftover"] is True
    assert nuevo["assignments"]["2026-11-18|almuerzo"]["origin"] == "fuera"
    assert nuevo["recipes"][0]["times_in_menu"] == 2

def test_editar_rechaza_espacios_y_recetas_invalidas(client, auth_headers):
    creado = _menu(client, auth_headers, logistics={"days": 2, "meals": ["almuerzo"], "meals_out": 0}).json()
    fuera_de_rango = {"2026-12-01|almuerzo": {"origin": "fuera"}}
    assert client.put(f"/api/menus/{creado['id']}/assignments", headers=auth_headers,
                      json={"assignments": fuera_de_rango}).status_code == 422
    receta_inexistente = {"2026-11-16|almuerzo": {"origin": "casera", "recipe_id": 9999}}
    assert client.put(f"/api/menus/{creado['id']}/assignments", headers=auth_headers,
                      json={"assignments": receta_inexistente}).status_code == 422
    casera_sin_receta = {"2026-11-16|almuerzo": {"origin": "casera"}}
    assert client.put(f"/api/menus/{creado['id']}/assignments", headers=auth_headers,
                      json={"assignments": casera_sin_receta}).status_code == 422

def test_eliminar_menu(client, auth_headers):
    creado = _menu(client, auth_headers).json()
    assert client.delete(f"/api/menus/{creado['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/menus/{creado['id']}", headers=auth_headers).status_code == 404