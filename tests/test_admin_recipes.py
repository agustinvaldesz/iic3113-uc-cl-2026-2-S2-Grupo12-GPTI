"""Pruebas del panel del gestor de recetas (RN-01 y RN-03). La IA se reemplaza por un borrador fijo."""
import uuid
import pytest
from app.database import SessionLocal
from app.models_db import UserDB
from app.schemas.admin_recipes import RecipeIn
from app.services import recipe_generator

RECETA = {
    "title": "Porotos con longaniza económicos",
    "servings": 4,
    "prep_time": "60 mins",
    "diet_type": "con_carne",
    "allergens": [],
    "diet_focus": ["balanceada"],
    "ingredients": ["500 g de porotos", "200 g de tallarines", "250 g de longaniza", "1 cebolla"],
    "instructions": "Cocer los porotos remojados, agregar el sofrito y los tallarines al final.",
}

@pytest.fixture
def manager_headers(client):
    email = f"gestor_{uuid.uuid4().hex[:8]}@nutricart.cl"
    client.post("/api/auth/register", json={"full_name": "Gestor", "email": email, "password": "clave1234"})
    with SessionLocal() as db:
        db.query(UserDB).filter(UserDB.email == email).update({"role": "gestor"})
        db.commit()
    token = client.post("/api/auth/login", json={"email": email, "password": "clave1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_consumidor_no_accede_al_panel(client, auth_headers):
    assert client.get("/api/admin/recipes", headers=auth_headers).status_code == 403

def test_receta_manual_queda_aprobada(client, manager_headers):
    r = client.post("/api/admin/recipes", headers=manager_headers, json=RECETA)
    assert r.status_code == 201 and r.json()["status"] == "aprobada"
    assert any("gluten" in w for w in r.json()["warnings"])  # Tallarines sin declarar gluten

def test_receta_ia_pendiente_hasta_aprobar(client, manager_headers, monkeypatch):
    monkeypatch.setattr(recipe_generator, "generate_drafts",
                        lambda req: ([RecipeIn(**{**RECETA, "title": "Borrador IA"})], ["Otra: formato inválido"]))
    data = client.post("/api/admin/recipes/generate", headers=manager_headers, json={"count": 1}).json()
    receta = data["created"][0]
    assert receta["status"] == "pendiente" and receta["source"] == "llm" and data["discarded"]

    pendientes = client.get("/api/admin/recipes", headers=manager_headers).json()
    assert receta["id"] in [p["id"] for p in pendientes]

    corregida = {**RECETA, "title": "Borrador IA", "allergens": ["gluten"]}
    assert client.put(f"/api/admin/recipes/{receta['id']}", headers=manager_headers, json=corregida).json()["warnings"] == []
    aprobada = client.post(f"/api/admin/recipes/{receta['id']}/approve", headers=manager_headers, json={}).json()
    assert aprobada["status"] == "aprobada"

def test_rechazo_exige_motivo(client, manager_headers, monkeypatch):
    monkeypatch.setattr(recipe_generator, "generate_drafts",
                        lambda req: ([RecipeIn(**{**RECETA, "title": "Para rechazar"})], []))
    rid = client.post("/api/admin/recipes/generate", headers=manager_headers, json={"count": 1}).json()["created"][0]["id"]
    assert client.post(f"/api/admin/recipes/{rid}/reject", headers=manager_headers, json={}).status_code == 422
    r = client.post(f"/api/admin/recipes/{rid}/reject", headers=manager_headers, json={"notes": "Poco sabrosa"})
    assert r.json()["status"] == "rechazada"

def test_sin_clave_de_ia_responde_503(client, manager_headers, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)  # Simula que no hay clave, aunque esté en el .env
    assert client.post("/api/admin/recipes/generate", headers=manager_headers, json={"count": 1}).status_code == 503

def test_formato_invalido_se_rechaza(client, manager_headers):
    malo = {**RECETA, "diet_focus": [], "ingredients": ["solo uno"]}
    assert client.post("/api/admin/recipes", headers=manager_headers, json=malo).status_code == 422