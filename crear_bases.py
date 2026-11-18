"""
Crea desde cero la base SQLite de una cuenta a partir de su Excel, SIN omitir filas.

Uso (desde la carpeta del proyecto):
    python crear_bases.py "C:\\ruta\\cuenta14.xlsx" --cuenta 14
    python crear_bases.py "C:\\ruta\\cuenta33.xlsx" --cuenta 33
    python crear_bases.py "C:\\ruta\\archivo.xlsx" --cuenta 33 --hoja todas   (si el Excel tiene varias hojas)

Si ya existe db_cuenta_XX.db, la guarda antes como db_cuenta_XX_respaldo_FECHA.db.
Al final compara cuántas filas con datos tenía el Excel contra cuántas quedaron en la base.
"""
import argparse
import csv
import os
import shutil
import sqlite3
import sys
from datetime import datetime

import pandas as pd

from busqueda import limpiar
from cargar import ALIAS, _limpiar, clave_pago, norm_nro

CREAR = """CREATE TABLE pagos (
    fecha TEXT, nro_deposito TEXT, nombre TEXT, participante TEXT, monto REAL,
    hoja_de_ruta TEXT, programa_descripcion TEXT, mes_declaracion TEXT,
    fecha_canje TEXT, obs TEXT, busqueda TEXT)"""


def txt(v):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def fecha_iso(v):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    d = pd.to_datetime(str(v).strip(), dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def monto(v):
    if v is None or pd.isna(v):
        return None
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("excel")
    ap.add_argument("--cuenta", type=int, choices=[14, 33], required=True)
    ap.add_argument("--hoja", default="primera", help="'primera' (por defecto), 'todas' o el nombre de una hoja")
    a = ap.parse_args()
    destino_db = f"db_cuenta_{a.cuenta}.db"

    print("Leyendo el Excel (puede tardar unos minutos si es grande)...")
    xls = pd.ExcelFile(a.excel, engine="openpyxl")
    hojas = xls.sheet_names
    print("Hojas del archivo:", ", ".join(hojas))
    if a.hoja == "todas":
        usar = hojas
    elif a.hoja == "primera":
        usar = hojas[:1]
        if len(hojas) > 1:
            print("AVISO: el archivo tiene varias hojas y solo leí la primera. "
                  "Si los datos están repartidos, vuelve a ejecutar con:  --hoja todas")
    elif a.hoja in hojas:
        usar = [a.hoja]
    else:
        sys.exit(f"No existe la hoja '{a.hoja}'. Hojas disponibles: {hojas}")

    registros, avisos, vistas = [], [], {}
    leidas, suma_excel = 0, 0.0
    for h in usar:
        df = xls.parse(h, dtype=object)
        destino = {}
        for c in df.columns:
            campo = ALIAS.get(_limpiar(c))
            if campo and campo not in destino.values():
                destino[c] = campo
        campos = set(destino.values())
        falta = [k for k in ("fecha", "nro_deposito", "monto") if k not in campos]
        if falta or not ({"nombre", "participante"} & campos):
            print(f"  Hoja '{h}' OMITIDA: faltan las columnas {falta or 'de nombre'}. Encabezados: {list(df.columns)}")
            continue
        sin_usar = [str(c) for c in df.columns if c not in destino and not str(c).startswith("Unnamed")]
        if sin_usar:
            print(f"  Hoja '{h}': columnas que no se guardan: {sin_usar}")
        n_hoja = 0
        for i, r in enumerate(df[list(destino)].rename(columns=destino).to_dict("records")):
            fila = i + 2
            if all(txt(v) is None for v in r.values()):
                continue  # fila totalmente vacía
            leidas += 1
            n_hoja += 1
            nro = norm_nro(txt(r.get("nro_deposito")) or "") or None
            f, mo = fecha_iso(r.get("fecha")), monto(r.get("monto"))
            if nro is None:
                avisos.append((h, fila, "sin número de depósito (se guardó igual)", ""))
            if f is None:
                avisos.append((h, fila, "fecha vacía o no reconocida (se guardó sin fecha)", txt(r.get("fecha")) or ""))
            if mo is None:
                avisos.append((h, fila, "monto vacío o no reconocido (se guardó sin monto)", txt(r.get("monto")) or ""))
            else:
                suma_excel += mo
            if nro:
                clave = clave_pago(nro, f, mo)
                if clave in vistas:
                    avisos.append((h, fila, f"posible duplicado de la fila {vistas[clave][1]} (se guardó igual)", nro))
                else:
                    vistas[clave] = (h, fila)
            nombre, part = txt(r.get("nombre")), txt(r.get("participante"))
            busq = limpiar(" ".join(x for x in (nombre, part) if x and x.lower() not in ("none", "nan")))
            registros.append((f, nro, nombre, part, mo, txt(r.get("hoja_de_ruta")),
                              txt(r.get("programa_descripcion")), txt(r.get("mes_declaracion")),
                              txt(r.get("fecha_canje")), txt(r.get("obs")), busq))
        print(f"  Hoja '{h}': {n_hoja} filas con datos")

    if not registros:
        sys.exit("No se leyó ninguna fila. No se creó ni se cambió ninguna base.")

    if os.path.exists(destino_db):
        respaldo = f"db_cuenta_{a.cuenta}_respaldo_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.move(destino_db, respaldo)
        print(f"La base anterior se guardó como {respaldo}")
    con = sqlite3.connect(destino_db)
    con.execute(CREAR)
    con.executemany("INSERT INTO pagos VALUES (?,?,?,?,?,?,?,?,?,?,?)", registros)
    con.execute("CREATE INDEX ix_pagos_nro ON pagos(nro_deposito)")
    con.execute("CREATE INDEX ix_pagos_fecha ON pagos(fecha)")
    con.commit()
    n_bd, suma_bd = con.execute("SELECT COUNT(*), COALESCE(SUM(monto), 0) FROM pagos").fetchone()
    con.close()

    ruta = f"avisos_creacion_cuenta{a.cuenta}.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["hoja", "fila_excel", "aviso", "dato"])
        w.writerows(avisos)

    print(f"\n=== Cuenta {a.cuenta}: {destino_db} ===")
    print(f"Filas con datos en el Excel: {leidas}")
    print(f"Filas guardadas en la base:  {n_bd}   {'✔ coinciden' if n_bd == leidas else '✘ NO COINCIDEN, avísame'}")
    print(f"Suma de montos en el Excel:  {suma_excel:,.2f}")
    print(f"Suma de montos en la base:   {suma_bd:,.2f}")
    print(f"Avisos: {len(avisos)} (revisa {ruta})")


if __name__ == "__main__":
    main()
