"""
Crea db_cpt.db con los pagos en línea (CPT): código de seguimiento <-> código de transacción.

Uso (desde la carpeta del proyecto):
    python crear_cpt.py "C:\\ruta\\PAGOS CPT.xlsx"
    python crear_cpt.py "C:\\ruta\\PAGOS CPT.xlsx" --hoja todas      (si hay varias hojas)

Se puede repetir cuando el Excel tenga pagos nuevos: guarda la base anterior como respaldo
y crea una nueva con todo lo que diga el Excel.
"""
import argparse
import csv
import os
import shutil
import sqlite3
import sys
from datetime import datetime

import pandas as pd

from cargar import _limpiar, norm_nro

# encabezados (sin tildes, mayúsculas y SIN espacios) -> columna de la base
ALIAS = {
    "NRO": "nro", "FECHADEPAGO": "fecha", "DESCRIPCION": "descripcion", "METODOPAGO": "metodo",
    "CANALPAGO": "canal", "CODIGOSEGUIMIENTO": "codigo_seguimiento",
    "CODIGOTRANSACCION": "codigo_transaccion", "NOMBRE": "nombre", "MONTO": "monto",
    "PROGRAMA": "programa", "SEDEESFM": "sede", "DEPARTAMENTO": "departamento",
}
CAMPOS = ["fecha", "descripcion", "metodo", "canal", "codigo_seguimiento", "codigo_transaccion",
          "nombre", "monto", "programa", "sede", "departamento"]


def clave(t):
    return _limpiar(t).replace(" ", "")


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
    ap.add_argument("--hoja", default="primera", help="'primera' (por defecto), 'todas' o el nombre de una hoja")
    a = ap.parse_args()

    print("Leyendo el Excel (puede tardar unos minutos si es grande)...")
    xls = pd.ExcelFile(a.excel, engine="openpyxl")
    hojas = xls.sheet_names
    print("Hojas del archivo:", ", ".join(hojas))
    if a.hoja == "todas":
        usar = hojas
    elif a.hoja == "primera":
        usar = hojas[:1]
        if len(hojas) > 1:
            print("AVISO: hay varias hojas y solo leí la primera. Si hace falta, repite con:  --hoja todas")
    elif a.hoja in hojas:
        usar = [a.hoja]
    else:
        sys.exit(f"No existe la hoja '{a.hoja}'. Hojas disponibles: {hojas}")

    registros, avisos, leidas, suma = [], [], 0, 0.0
    vistos_t, vistos_s = {}, {}
    for h in usar:
        df = xls.parse(h, header=None, dtype=object)
        fila_enc = None
        for i in range(min(20, len(df))):  # el encabezado no está en la fila 1: arriba hay un título
            claves = {clave(c) for c in df.iloc[i] if txt(c)}
            if {"CODIGOSEGUIMIENTO", "CODIGOTRANSACCION"} <= claves:
                fila_enc = i
                break
        if fila_enc is None:
            print(f"  Hoja '{h}' OMITIDA: no encontré la fila con CODIGO SEGUIMIENTO y CODIGO TRANSACCION.")
            continue
        destino = {}
        for j, c in enumerate(df.iloc[fila_enc]):
            campo = ALIAS.get(clave(c)) if txt(c) else None
            if campo and campo not in destino.values():
                destino[j] = campo
        datos = df.iloc[fila_enc + 1:]
        n_hoja = 0
        for idx, fila_df in datos.iterrows():
            r = {campo: fila_df[j] for j, campo in destino.items()}
            if all(txt(v) is None for v in r.values()):
                continue
            fila = idx + 1  # fila real en Excel (el índice empieza en 0)
            leidas += 1
            n_hoja += 1
            seg = norm_nro(txt(r.get("codigo_seguimiento")) or "") or None
            tra = norm_nro(txt(r.get("codigo_transaccion")) or "") or None
            f, mo = fecha_iso(r.get("fecha")), monto(r.get("monto"))
            if seg is None and tra is None:
                avisos.append((h, fila, "sin código de seguimiento ni de transacción (se guardó igual)", ""))
            if f is None:
                avisos.append((h, fila, "fecha vacía o no reconocida (se guardó sin fecha)", txt(r.get("fecha")) or ""))
            if mo is None:
                avisos.append((h, fila, "monto vacío o no reconocido (se guardó sin monto)", txt(r.get("monto")) or ""))
            else:
                suma += mo
            if tra:
                if tra in vistos_t:
                    avisos.append((h, fila, f"código de transacción repetido (fila {vistos_t[tra]})", tra))
                else:
                    vistos_t[tra] = fila
            if seg:
                if seg in vistos_s:
                    avisos.append((h, fila, f"código de seguimiento repetido (fila {vistos_s[seg]})", seg))
                else:
                    vistos_s[seg] = fila
            registros.append((f, txt(r.get("descripcion")), txt(r.get("metodo")), txt(r.get("canal")), seg, tra,
                              txt(r.get("nombre")), mo, txt(r.get("programa")), txt(r.get("sede")),
                              txt(r.get("departamento"))))
        print(f"  Hoja '{h}': {n_hoja} filas con datos")

    if not registros:
        sys.exit("No se leyó ninguna fila. No se creó ni se cambió ninguna base.")

    destino_db = "db_cpt.db"
    if os.path.exists(destino_db):
        respaldo = f"db_cpt_respaldo_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.move(destino_db, respaldo)
        print(f"La base anterior se guardó como {respaldo}")
    con = sqlite3.connect(destino_db)
    con.execute("CREATE TABLE cpt (fecha TEXT, descripcion TEXT, metodo TEXT, canal TEXT, "
                "codigo_seguimiento TEXT, codigo_transaccion TEXT, nombre TEXT, monto REAL, "
                "programa TEXT, sede TEXT, departamento TEXT)")
    con.executemany("INSERT INTO cpt VALUES (?,?,?,?,?,?,?,?,?,?,?)", registros)
    con.execute("CREATE INDEX ix_cpt_seg ON cpt(codigo_seguimiento)")
    con.execute("CREATE INDEX ix_cpt_tra ON cpt(codigo_transaccion)")
    con.commit()
    n_bd, suma_bd = con.execute("SELECT COUNT(*), COALESCE(SUM(monto), 0) FROM cpt").fetchone()
    con.close()

    ruta = "avisos_creacion_cpt.csv"
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["hoja", "fila_excel", "aviso", "dato"])
        w.writerows(avisos)

    print(f"\n=== Pagos en línea: {destino_db} ===")
    print(f"Filas con datos en el Excel: {leidas}")
    print(f"Filas guardadas en la base:  {n_bd}   {'✔ coinciden' if n_bd == leidas else '✘ NO COINCIDEN, avísame'}")
    print(f"Suma de montos en el Excel:  {suma:,.2f}")
    print(f"Suma de montos en la base:   {suma_bd:,.2f}")
    print(f"Avisos: {len(avisos)} (revisa {ruta})")


if __name__ == "__main__":
    main()
