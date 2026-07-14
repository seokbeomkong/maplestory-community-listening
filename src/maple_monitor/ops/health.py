from sqlalchemy import Engine, text


def database_health(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        value = connection.execute(text("SELECT 1")).scalar_one()
    return {"database": "ok" if value == 1 else "error"}
