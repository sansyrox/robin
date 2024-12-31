from conf import settings

from robyn import Robyn
from robyn.helpers import discover_routes

app: Robyn = discover_routes("api.handlers")
# note: if you prefer to manuall refine routes, use your build_routes function instead


if __name__ == "__main__":
    app.start(host="0.0.0.0", port=settings.service_port)
