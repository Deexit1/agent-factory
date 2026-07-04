def create_app():
    routes = {"/health": lambda: (200, "ok")}
    return routes
