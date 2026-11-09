"""Preparación de archivos nuevos y antiduplicados (N° de depósito + fecha + monto)."""
import re
import unicodedata

import pandas as pd

# Encabezados aceptados (sin tildes, en mayúsculas y sin símbolos) -> columna de la base
ALIAS = {
    "FECHA": "fecha",
    "N DEPOSITO": "nro_deposito", "N DE DEPOSITO": "nro_deposito",
    "NRO DEPOSITO": "nro_deposito", "NUMERO DEPOSITO": "nro_deposito",
    "NOMBRE Y APELLIDO": "nombre", "NOMBRE": "nombre",
    "PARTICIPANTE": "participante",
    "MONTO": "monto",
    "HOJA DE RUTA": "hoja_de_ruta",
    "DESCRIPCION": "programa_descripcion", "PROGRAMA DESCRIPCION": "programa_descripcion",
    "MES DECLARACION": "mes_declaracion",
    "OBS": "obs", "OBSERVACION": "obs", "OBSERVACIONES": "obs",
}


def _limpiar(t):
    t = "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()


def norm_nro(n):
    return re.sub(r"\D", "", re.sub(r"\.0$", "", str(n).strip()))


def clave_pago(nro, fecha, monto):
    m = pd.to_numeric(monto, errors="coerce")
    m = "" if pd.isna(m) else f"{float(m):.2f}"
    f = "" if fecha is None or pd.isna(fecha) else str(fecha)[:10]
    return f"{norm_nro(nro)}|{f}|{m}"


def preparar_y_filtrar(engine, df_raw):
    """Devuelve (registros nuevos, cantidad omitida, máscara 'mismo N° pero distinta fecha/monto',
    columnas ignoradas)."""
    with engine.connect() as con:
        columnas_bd = set(pd.read_sql("PRAGMA table_info(pagos)", con=con)["name"])
        existentes = pd.read_sql("SELECT nro_deposito, fecha, monto FROM pagos", con=con)

    # 1) nombres de columna -> nombres de la base (si dos columnas coinciden, gana la primera)
    destino, vistos = {}, set()
    for c in df_raw.columns:
        nuevo = ALIAS.get(_limpiar(c))
        if nuevo and nuevo not in vistos:
            destino[c] = nuevo
            vistos.add(nuevo)
    ignoradas = [str(c) for c in df_raw.columns if c not in destino and not str(c).startswith("Unnamed")]
    df = df_raw[list(destino)].rename(columns=destino)
    ignoradas += [c for c in df.columns if c not in columnas_bd]
    df = df[[c for c in df.columns if c in columnas_bd]].copy()

    # 2) formatos: fecha AAAA-MM-DD (el día va primero), N° sin ".0", monto numérico
    if "fecha" in df:
        df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    if "nro_deposito" in df:
        df["nro_deposito"] = df["nro_deposito"].map(norm_nro)
    if "monto" in df:
        df["monto"] = pd.to_numeric(df["monto"], errors="coerce")

    if "nro_deposito" not in df:
        return df, 0, pd.Series(False, index=df.index), ignoradas

    # 3) antiduplicados: misma clave ya en la base, o repetida dentro del mismo archivo
    claves_bd = {clave_pago(n, f, m) for n, f, m in
                 zip(existentes["nro_deposito"], existentes["fecha"], existentes["monto"])}
    nros_bd = {norm_nro(n) for n in existentes["nro_deposito"]}
    fechas = df["fecha"] if "fecha" in df else [None] * len(df)
    montos = df["monto"] if "monto" in df else [None] * len(df)
    claves = pd.Series([clave_pago(n, f, m) for n, f, m in zip(df["nro_deposito"], fechas, montos)],
                       index=df.index)
    omitir = claves.isin(claves_bd) | claves.duplicated()
    nuevos = df[~omitir].copy()
    mismo_nro = nuevos["nro_deposito"].isin(nros_bd)
    return nuevos, int(omitir.sum()), mismo_nro, ignoradas
