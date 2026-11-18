"""Búsqueda sin tildes ni mayúsculas: 'munoz' encuentra 'MUÑOZ'.

Mantiene en la tabla `pagos` una columna `busqueda` con el nombre y el participante
en mayúsculas y sin tildes. Si la base se vuelve a cargar y la columna no existe, se
crea y se llena sola al conectar; los registros nuevos se completan con asegurar_busqueda().
"""
import re
import unicodedata


def limpiar(texto):
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()


def _v(x):
    return "" if x is None or str(x).strip().lower() in ("none", "nan") else str(x)


def asegurar_busqueda(engine):
    """Crea la columna si falta y completa los registros que no la tienen. Devuelve cuántos completó."""
    with engine.begin() as con:
        cols = [r[1] for r in con.exec_driver_sql("PRAGMA table_info(pagos)").fetchall()]
        if not cols:  # la base no tiene tabla pagos (por ejemplo db_cpt)
            return 0
        if "busqueda" not in cols:
            con.exec_driver_sql("ALTER TABLE pagos ADD COLUMN busqueda TEXT")
        pendientes = con.exec_driver_sql(
            "SELECT rowid, nombre, participante FROM pagos WHERE busqueda IS NULL"
        ).fetchall()
        if pendientes:
            datos = [(limpiar(f"{_v(n)} {_v(p)}"), rid) for rid, n, p in pendientes]
            con.exec_driver_sql("UPDATE pagos SET busqueda = ? WHERE rowid = ?", datos)
    return len(pendientes)
