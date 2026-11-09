"""Regla de control: qué depósitos deben tener hoja de ruta y resaltado de los que les falta.

Un depósito REQUIERE hoja de ruta salvo que sea un pago en línea:
  - su nombre es un código CPT, o
  - tiene el nombre en la columna PARTICIPANTE.
Si requiere hoja de ruta y la columna HOJA DE RUTA está vacía, se resalta.
"""
import pandas as pd

TEXTO_CONTROL = "📄 Falta hoja de ruta"

# Misma regla, escrita en SQL para los filtros y el conteo de la pantalla de consulta
SQL_REQUIERE_HOJA = """(
 (hoja_de_ruta IS NULL OR TRIM(hoja_de_ruta) = '' OR LOWER(TRIM(hoja_de_ruta)) IN ('none','nan'))
 AND (participante IS NULL OR TRIM(participante) = '' OR LOWER(TRIM(participante)) IN ('none','nan'))
 AND UPPER(TRIM(COALESCE(nombre,''))) NOT LIKE 'CPT%'
)"""


def _vacio(x):
    if x is None:
        return True
    try:
        if pd.isna(x):
            return True
    except (TypeError, ValueError):
        pass
    return str(x).strip().lower() in ("", "none", "nan")


def requiere_hoja(hoja, nombre, participante):
    """True si el depósito no tiene hoja de ruta y debería tenerla (los pagos en línea no la necesitan)."""
    if not _vacio(hoja):
        return False
    if not _vacio(participante):
        return False
    if not _vacio(nombre) and str(nombre).strip().upper().startswith("CPT"):
        return False
    return True


def marcar_pendientes(df):
    """Serie True/False por fila; el DataFrame debe tener hoja_de_ruta, nombre y participante."""
    return pd.Series([requiere_hoja(h, n, p) for h, n, p in
                      zip(df["hoja_de_ruta"], df["nombre"], df["participante"])], index=df.index)


def resaltar(df, mascara):
    """Devuelve la tabla con fondo amarillo en las filas donde la máscara es True."""
    estilo = "background-color: rgba(255, 193, 7, 0.35)"
    mascara = pd.Series(list(mascara), index=df.index)
    return df.style.apply(lambda fila: [estilo if mascara.loc[fila.name] else ""] * len(fila), axis=1)
