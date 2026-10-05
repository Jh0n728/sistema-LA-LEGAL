import time
import pandas as pd
from sqlalchemy import create_engine

# --- CONFIGURACIÓN DE CONEXIÓN ---
USUARIO = "root"
PASSWORD = ""
HOST = "localhost"
PUERTO = "3306"
BASE_DATOS = "db_cuenta_14"  # Cambia a db_cuenta_14 según corresponda
TABLA = "pagos"

# Conexión con SQLAlchemy y PyMySQL
conexion_str = f"mysql+pymysql://{USUARIO}:{PASSWORD}@{HOST}:{PUERTO}/{BASE_DATOS}"
engine = create_engine(conexion_str)

# Ruta de tu archivo Excel
archivo_excel = r"C:\Users\ACADEMICA\Desktop\sistema de revisiones\BASE CUOTAS PARA SISTEMA.xlsx"  # <--- Cambia por la ruta real de tu Excel

print("Leyendo el archivo Excel (esto puede tardar unos momentos por la cantidad de registros)...")
inicio_tiempo = time.time()

# Leer el archivo Excel completo
df = pd.read_excel(archivo_excel)

print(f"Excel leído. Total de filas encontradas: {len(df):,}".replace(",", "."))

# --- MAPEO Y LIMPIEZA DE COLUMNAS ---
# Asegura que coincidan con las columnas de tu tabla en MySQL
renombres = {
    "FECHA": "fecha",
    "N° DE DEPOSITO": "nro_deposito",
    "NOMBRE": "nombre",
    "PARTICIPANTE": "participante",
    "MONTO": "monto",
    "HOJA DE RUTA": "hoja_de_ruta",
    "PROGRAMA-DESCRIPCION": "programa_descripcion",
    "MES DECLARACION": "mes_declaracion",
    "OBS.": "obs",
}

df = df.rename(columns=renombres)

# Filtrar columnas válidas
columnas_validas = [
    "fecha", "nro_deposito", "nombre", "participante", 
    "monto", "hoja_de_ruta", "programa_descripcion", 
    "mes_declaracion", "obs"
]

for col in columnas_validas:
    if col not in df.columns:
        df[col] = None

df = df[columnas_validas]

# Limpiar nulos para evitar errores en MySQL
df = df.where(pd.notnull(df), None)

# Convertir tipos de datos correctos
df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
df["monto"] = pd.to_numeric(df["monto"], errors="coerce")

print("Iniciando la inserción masiva a MySQL...")

# --- INSERCIÓN EN BLOQUES (CHUNKS) ---
try:
    df.to_sql(
        name=TABLA,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=5000,  # Inserta en bloques de 5,000 registros para optimizar memoria y velocidad
        method="multi"
    )

    tiempo_total = time.time() - inicio_tiempo
    print(f"¡Importación completada con éxito! Se insertaron {len(df):,} registros en {tiempo_total:.2f} segundos.".replace(",", "."))

except Exception as e:
    print(f"Ocurrió un error al insertar en la base de datos: {e}")