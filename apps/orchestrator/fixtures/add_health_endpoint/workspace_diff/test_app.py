from app import create_app


def test_health_returns_200():
    routes = create_app()
    status, _body = routes["/health"]()
    assert status == 200
