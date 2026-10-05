import pandas as pd
from sqlalchemy import create_engine

# Lista de las bases de datos que tienes en MySQL
bases_de_datos = ["db_cuenta_33", "db_cuenta_14"]

for db_name in bases_de_datos:
    print(f"Migrando {db_name} a SQLite...")
    
    # 1. Conexión a tu MySQL local
    engine_mysql = create_engine(f"mysql+pymysql://root:@localhost:3306/{db_name}")
    
    try:
        # 2. Leer todos los registros de la tabla 'pagos' de MySQL
        df = pd.read_sql("SELECT * FROM pagos", con=engine_mysql)
        
        # 3. Crear la conexión al nuevo archivo SQLite (.db)
        engine_sqlite = create_engine(f"sqlite:///{db_name}.db")
        
        # 4. Guardar los datos en el archivo SQLite
        df.to_sql("pagos", con=engine_sqlite, if_exists="replace", index=False)
        
        print(f"¡Éxito! Se creó el archivo: {db_name}.db con {len(df)} registros.")
        
    except Exception as e:
        print(f"Error al migrar {db_name}: {e}")

print("Proceso de migración finalizado.")