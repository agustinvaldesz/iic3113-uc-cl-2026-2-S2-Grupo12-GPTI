"""Pruebas del mapeo y cotización (REQ-09 a REQ-12) y de la Solicitud de cambio SC-2 (alternativa más económica)."""
from app.services.catalog_service import match_ingredient, parse_quantity


def _quote(client, **body):
    return client.post("/api/basket/quote", json=body)


def test_parseo_de_cantidades():
    assert parse_quantity("450 g de carne molida") == (450, "g")
    assert parse_quantity("1/2 taza de leche") == (120, "g")
    assert parse_quantity("1 lata de 225 g de piña") == (225, "g")
    assert parse_quantity("1 paquete de sazonador") == (1, "paquete")
    assert parse_quantity("Albahaca fresca picada") == (None, None)


def test_mapeo_de_ingredientes():
    assert match_ingredient("1 cucharadita de sal") == "sal"
    assert match_ingredient("1/2 taza de salsa de tomate") == "salsa de tomate"   # no confunde con "sal"
    assert match_ingredient("1 cucharadita de aceite de sésamo tostado") == "aceite de sesamo"
    assert match_ingredient("280 g de arroz de coliflor congelado") == "arroz de coliflor"
    assert match_ingredient("crema o leche de coco en lata") == "leche de coco"
    assert match_ingredient("esencia de vainilla") is None


def test_cotizacion_muestra_alternativa_mas_barata(client):
    data = _quote(client, recipe_ids=[1]).json()
    assert data["total"] == data["total_default"] > 0
    con_alternativa = [l for l in data["lines"] if l["cheaper_alternative"]]
    assert con_alternativa
    for l in con_alternativa:
        assert l["cheaper_alternative"]["cost"] < l["selected"]["cost"]
        assert l["cheaper_alternative"]["savings"] == l["selected"]["cost"] - l["cheaper_alternative"]["cost"]


def test_reemplazo_recalcula_total_y_ahorro(client):
    base = _quote(client, recipe_ids=[1]).json()
    selections = {l["ingredient"]: l["cheaper_alternative"]["sku"] for l in base["lines"] if l["cheaper_alternative"]}
    data = _quote(client, recipe_ids=[1], selections=selections).json()
    assert data["total"] == base["total"] - base["potential_savings"]
    assert data["savings"] == base["potential_savings"]
    assert data["potential_savings"] == 0


def test_sku_invalido_no_rompe_la_cotizacion(client):
    data = _quote(client, recipe_ids=[1], selections={"sal": "SKU-INEXISTENTE"}).json()
    assert data["warnings"]
    assert data["total"] == data["total_default"]


def test_ingrediente_no_cotizable_se_omite_y_se_avisa(client):
    data = _quote(client, items=[{"original_name": "450 g de carne molida"},
                                 {"original_name": "1 cucharadita de esencia de vainilla"}]).json()
    assert data["not_quoted"] == ["1 cucharadita de esencia de vainilla"]
    assert data["message"]
    assert len(data["lines"]) == 1


def test_despensa_no_se_cotiza(client):
    data = _quote(client, items=[{"original_name": "450 g de carne molida"}, {"original_name": "1 cebolla"}],
                  pantry=["cebolla"]).json()
    assert data["in_pantry"] == ["1 cebolla"]
    assert [l["ingredient"] for l in data["lines"]] == ["carne molida"]


def test_ingredientes_repetidos_se_agrupan(client):
    data = _quote(client, items=[{"original_name": "1 cucharada de aceite de sésamo"},
                                 {"original_name": "1 cucharadita de aceite de sésamo"}]).json()
    assert len(data["lines"]) == 1
    assert data["lines"][0]["quantity_needed"] == 20


def test_cotizacion_vacia_es_rechazada(client):
    assert _quote(client).status_code == 400
