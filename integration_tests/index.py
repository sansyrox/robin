from robyn import Robyn
from robyn import logger

app = Robyn(__file__)

logger.logging_file("logs.logs")


@app.get("/")
async def h():
    logger.info("Hello logging file")

    return "Hello, world!"


app.start()
