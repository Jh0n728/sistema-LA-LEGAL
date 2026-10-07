import sqlite3
import pandas as pd

# 1. Pon aquí el nombre exacto de tu archivo Excel de la cuenta 14
excel_path = 'BASE VALORES PARA SISTEMA.xlsx'
db_path = 'db_cuenta_14.db'

print('Leyendo el archivo Excel...')
df = pd.read_excel(excel_path)

# 2. Renombramos las columnas exactamente como las lee tu app.py de Streamlit:
# (Asegúrate de que las columnas de la izquierda coincidan con los títulos de tu Excel)
df.columns = [
    'fecha',
    'nro_deposito',
    'nombre',
    'participante',
    'monto',
    'hoja_de_ruta',
    'programa_descripcion',
    'mes_declaracion',
    'fecha_de_canje',
    'obs',
]

# Formatear la fecha para que SQLite la guarde de forma uniforme (YYYY-MM-DD)
if 'fecha' in df.columns:
  df['fecha'] = pd.to_datetime(df['fecha']).dt.strftime('%Y-%m-%d')

print(f'Conectando a {db_path} y escribiendo la tabla "pagos"...')
conn = sqlite3.connect(db_path)

# Guardamos directamente en la tabla 'pagos' que usa tu sistema
df.to_sql('pagos', conn, if_exists='replace', index=False)

conn.close()
print('¡Listo! La base de datos de la cuenta 14 ha sido reparada con éxito.')