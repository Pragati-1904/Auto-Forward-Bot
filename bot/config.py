from decouple import config


class Var:
    API_ID: int = config("API_ID", cast=int)
    API_HASH: str = config("API_HASH")
    BOT_TOKEN: str = config("BOT_TOKEN")
    REDIS_URL: str = config("REDIS_URL")
    ADMINS: list[int] = [int(i) for i in config("ADMINS").split()]
    SESSION_STRING: str | None = config("SESSION_STRING", default=None)
