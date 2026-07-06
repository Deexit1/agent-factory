from app import app


def test_create_item_returns_201_for_valid_payload():
    client = app.test_client()
    response = client.post("/items", json={"name": "widget", "price": 9.99})
    assert response.status_code == 201
    assert response.get_json() == {"name": "widget", "price": 9.99}


def test_create_item_returns_400_for_negative_price():
    client = app.test_client()
    response = client.post("/items", json={"name": "widget", "price": -1})
    assert response.status_code == 400
    assert response.get_json()["error"] == "price must be non-negative"


def test_create_item_returns_400_for_missing_name():
    client = app.test_client()
    response = client.post("/items", json={"price": 9.99})
    assert response.status_code == 400
    assert response.get_json()["error"] == "name is required"
