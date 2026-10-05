import time
import pandas as pd
from sqlalchemy import create_engine

# --- CONFIGURACIÓN ---
USUARIO = "root"
PASSWORD = ""
HOST = "localhost"
PUERTO = "3306"
BASE_DATOS = "db_cuenta_14"
TABLA = "pagos"

conexion_str = f"mysql+pymysql://{USUARIO}:{PASSWORD}@{HOST}:{PUERTO}/{BASE_DATOS}"
engine = create_engine(conexion_str)

# Ruta de tu archivo Excel de la cuenta 14
archivo_excel = r"C:\Users\ACADEMICA\Desktop\sistema de revisiones\BASE VALORES PARA SISTEMA.xlsx" # <--- Asegúrate de que sea tu ruta exacta

print("Leyendo el archivo Excel...")
df = pd.read_excel(archivo_excel)

# Limpiar espacios en blanco en los nombres de las columnas por seguridad
df.columns = df.columns.astype(str).str.strip()

# --- DICCIONARIO DE RENOMBRES EXACTO ---
renombres = {
    "FECHA": "fecha",
    "N° DE DEPOSITO": "nro_deposito",
    "NOMBRE": "nombre",
    "PARTICIPANTE": "participante",
    "MONTO": "monto",
    "HOJA DE RUTA": "hoja_de_ruta",
    "DESCRIPCION": "programa_descripcion",
    "MES DECLARACION": "mes_declaracion",
    "OBS": "obs"
    # Nota: 'FECHA DE CANJE' se omite intencionalmente porque no existe en la tabla SQL
}

df = df.rename(columns=renombres)

# Seleccionar únicamente las columnas válidas de la base de datos
columnas_validas = [
    "fecha", "nro_deposito", "nombre", "participante", 
    "monto", "hoja_de_ruta", "programa_descripcion", 
    "mes_declaracion", "obs"
]

for col in columnas_validas:
    if col not in df.columns:
        df[col] = None

df = df[columnas_validas]
df = df.where(pd.notnull(df), None)

# Convertir tipos de datos correctos
df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
df["monto"] = pd.to_numeric(df["monto"], errors="coerce")

print("Iniciando la inserción masiva a MySQL...")
inicio_tiempo = time.time()

try:
    df.to_sql(
        name=TABLA,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=5000,
        method="multi"
    )
    tiempo_total = time.time() - inicio_tiempo
    print(f"¡Importación completada con éxito! Se insertaron {len(df):,} registros en {tiempo_total:.2f} segundos.")
except Exception as e:
    print(f"Ocurrió un error al insertar: {e}")