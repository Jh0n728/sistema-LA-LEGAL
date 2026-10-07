import os
import sqlite3
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Configuración de la página (DEBE SER LO PRIMERO)
st.set_page_config(page_title="Sistema de Revisión de Pagos", layout="wide")

# Directorio base donde se encuentran las bases de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Función de conexión definitiva compatible con multihilo
@st.cache_resource
def conectar_db(db_name):
    db_path = os.path.join(BASE_DIR, f"{db_name}.db")
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool
    )

# --- CREDENCIALES DE ACCESO ---
USUARIOS_PERMITIDOS = {
    "TilinTolon": "TILINTOLON2026",
}

# Inicializar estado de sesión para el Login
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = ""

# --- PANTALLA DE LOGIN ---
def mostrar_login():
    st.markdown("<h2 style='text-align: center;'> Acceso al Sistema </h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col2:
        with st.form("form_login"):
            usuario = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            boton_ingresar = st.form_submit_button("Ingresar")
            
            if boton_ingresar:
                if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == password:
                    st.session_state.autenticado = True
                    st.session_state.usuario = usuario
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

# Validar si el usuario está logueado
if not st.session_state.autenticado:
    mostrar_login()
    st.stop()

# --- INTERFAZ PRINCIPAL DEL SISTEMA ---

# Barra lateral (Sidebar)
st.sidebar.title(f"Usuario: {st.session_state.usuario}")
st.sidebar.markdown("---")

cuenta_seleccionada = st.sidebar.selectbox(
    "Seleccione la Cuenta a Revisar:",
    ["db_cuenta_33", "db_cuenta_14"]
)

st.sidebar.markdown("---")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.autenticado = False
    st.session_state.usuario = ""
    st.rerun()

try:
    engine = conectar_db(cuenta_seleccionada)
    
    # Detectar automáticamente las columnas reales de la tabla pagos
    with engine.connect() as conn:
        cols_info = pd.read_sql("PRAGMA table_info(pagos);", con=conn)
        columnas_tabla = cols_info['name'].tolist() if not cols_info.empty else []
    
    # Buscar el nombre correcto para la columna de depósito
    col_deposito_real = next((c for c in columnas_tabla if 'deposito' in c.lower() or 'nro' in c.lower() or 'numero' in c.lower()), 'nro_deposito')
    
except Exception as e:
    st.error(f"Error al conectar con la base de datos local: {e}")
    st.stop()

# Encabezado principal
nombre_cuenta_visible = "Cuenta 33" if "33" in cuenta_seleccionada else "Cuenta 14"
st.title(f"Consulta de Pagos - {nombre_cuenta_visible}")

st.markdown("Escriba los criterios de búsqueda y presione **Enter** para filtrar los datos.")
st.markdown("### Búsqueda y Filtros")

col_busq, col_monto, col_fecha = st.columns(3)

with col_busq:
    busqueda = st.text_input("Escriba el Nombre o N° de Depósito:", placeholder="Ej: Juan Pérez o 15271987")
    st.markdown("**Filtro Especial de Control:**")
    solo_sin_hoja = st.checkbox("Mostrar SOLO depósitos SIN Hoja de Ruta")
    
with col_monto:
    st.markdown("**Filtrar por Rango de Montos:**")
    filtrar_monto_rango = st.checkbox("Activar filtro de rango de montos")
    monto_min = st.number_input("Monto Mínimo en Bs:", value=0.0, step=10.0)
    monto_max = st.number_input("Monto Máximo en Bs:", value=10000.0, step=10.0)
    
with col_fecha:
    st.markdown("**Filtrar por Fechas:**")
    filtrar_fecha = st.checkbox("Activar filtro de fechas")
    
    fecha_inicio = st.date_input(
        "Desde la fecha:", 
        value=pd.to_datetime("2025-01-01").date(),
        min_value=pd.to_datetime("2015-01-01").date(),
        max_value=pd.to_datetime("2030-12-31").date()
    )
    fecha_fin = st.date_input(
        "Hasta la fecha:", 
        value=pd.to_datetime("2026-12-31").date(),
        min_value=pd.to_datetime("2015-01-01").date(),
        max_value=pd.to_datetime("2030-12-31").date()
    )

st.markdown("---")

# --- CONSTRUCCIÓN DINÁMICA DE LA CONSULTA SQL ---
where_clauses = []
params = []

if busqueda.strip():
    palabras = busqueda.strip().split()
    condiciones_palabras = []
    for p in palabras:
        cond_str = f"(nombre LIKE ? OR {col_deposito_real} LIKE ? OR participante LIKE ?)"
        condiciones_palabras.append(cond_str)
        params.extend([f"%{p}%", f"%{p}%", f"%{p}%"])
    where_clauses.append("(" + " AND ".join(condiciones_palabras) + ")")

if solo_sin_hoja:
    where_clauses.append("(hoja_de_ruta IS NULL OR TRIM(hoja_de_ruta) = '' OR LOWER(TRIM(hoja_de_ruta)) = 'none')")

if filtrar_monto_rango:
    where_clauses.append("monto BETWEEN ? AND ?")
    params.extend([monto_min, monto_max])

if filtrar_fecha:
    where_clauses.append("fecha BETWEEN ? AND ?")
    params.extend([str(fecha_inicio), str(fecha_fin)])

where_sql = ""
if where_clauses:
    where_sql = " WHERE " + " AND ".join(where_clauses)

query_total = f"SELECT SUM(monto) as total_monto, COUNT(*) as total_registros FROM pagos" + where_sql
query_tabla = f"SELECT fecha, {col_deposito_real} AS nro_deposito, nombre, participante, monto, hoja_de_ruta, programa_descripcion, mes_declaracion, obs FROM pagos" + where_sql + " LIMIT 500"

# --- RENDERIZADO DE TABLA Y MÉTRICAS ---
with st.container():
    try:
        with engine.connect() as conn:
            df_totales = pd.read_sql(query_total, con=conn, params=tuple(params) if params else None)
            total_registros = int(df_totales["total_registros"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_registros"].iloc[0]) else 0
            monto_global = float(df_totales["total_monto"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_monto"].iloc[0]) else 0.0

            c1, c2 = st.columns(2)
            with c1:
                st.metric(label="Monto Total General Acumulado", value=f"{monto_global:,.2f} Bs")
            with c2:
                texto_registros = f"{total_registros:,} (Mostrando primeros 500)" if total_registros > 500 else f"{total_registros:,}"
                st.metric(label="Registros Coincidentes", value=texto_registros)

            st.markdown("#### Detalle de Transacciones")

            if total_registros > 0:
                df = pd.read_sql(query_tabla, con=conn, params=tuple(params) if params else None)
                
                df = df.rename(columns={
                    "fecha": "Fecha",
                    "nro_deposito": "N° Depósito",
                    "nombre": "Nombre Completo",
                    "participante": "Participante",
                    "monto": "Monto (Bs)",
                    "hoja_de_ruta": "Hoja de Ruta",
                    "programa_descripcion": "Descripción",
                    "mes_declaracion": "Mes Declaración",
                    "obs": "Observaciones"
                })

                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.info("No hay transacciones registradas o ningún elemento coincide con el filtro aplicado.")
                
    except Exception as e:
        st.error(f"Error al realizar la lectura: {e}")

# --- SECCIÓN: CARGAR DATOS INTELIGENTE (Anti-Duplicados) ---
with st.sidebar.expander("Cargar Datos"):
    st.markdown("### Actualizar Registros")
    
    db_para_actualizar = st.selectbox(
        "Base de datos a actualizar",
        ["db_cuenta_33", "db_cuenta_14"],
        key="select_db_admin"
    )

    archivo_subido = st.file_uploader(
        "Subir nuevos depósitos (Excel/CSV)", 
        type=["xlsx", "csv"],
        key="uploader_admin"
    )

    if archivo_subido is not None:
        try:
            if archivo_subido.name.endswith(".csv"):
                df_nuevos = pd.read_csv(archivo_subido)
            else:
                df_nuevos = pd.read_excel(archivo_subido)
            
            if 'fecha' in df_nuevos.columns:
                df_nuevos['fecha'] = pd.to_datetime(df_nuevos['fecha']).dt.strftime('%Y-%m-%d')

            st.write("Vista previa:")
            st.dataframe(df_nuevos, use_container_width=True)

            if st.button("Confirmar e Insertar (Anti-Duplicados)", key="btn_confirmar_admin"):
                try:
                    engine_actualizacion = conectar_db(db_para_actualizar)
                    
                    # Detectar columna de depósito en la base destino
                    with engine_actualizacion.connect() as c_dest:
                        cols_dest = pd.read_sql("PRAGMA table_info(pagos);", con=c_dest)['name'].tolist()
                    col_dep_dest = next((c for c in cols_dest if 'deposito' in c.lower() or 'nro' in c.lower() or 'numero' in c.lower()), 'nro_deposito')
                    
                    try:
                        df_existentes = pd.read_sql(f"SELECT {col_dep_dest} FROM pagos", con=engine_actualizacion)
                        set_existentes = set(df_existentes[col_dep_dest].astype(str))
                    except:
                        set_existentes = set()
                    
                    # Buscar la columna equivalente en el archivo subido
                    col_dep_subido = next((c for c in df_nuevos.columns if 'deposito' in c.lower() or 'nro' in c.lower() or 'numero' in c.lower()), df_nuevos.columns[1] if len(df_nuevos.columns) > 1 else df_nuevos.columns[0])
                    
                    df_nuevos['dep_str'] = df_nuevos[col_dep_subido].astype(str)
                    df_filtrado = df_nuevos[~df_nuevos['dep_str'].isin(set_existentes)].copy()
                    df_filtrado = df_filtrado.drop(columns=['dep_str'])
                    
                    if not df_filtrado.empty:
                        df_filtrado.to_sql("pagos", con=engine_actualizacion, if_exists="append", index=False)
                        omitidos = len(df_nuevos) - len(df_filtrado)
                        st.success(f"¡{len(df_filtrado)} registros nuevos agregados a {db_para_actualizar}! (Se omitieron {omitidos} duplicados).")
                    else:
                        st.warning("Todos los registros del archivo ya existían en la base de datos. No se agregó ninguno.")
                except Exception as e:
                    st.error(f"Error al insertar: {e}")
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

# --- SECCIÓN: MODIFICAR REGISTRO CON LISTA DESPLEGABLE ---
with st.sidebar.expander("Modificar Registro"):
    st.markdown("### Editar Datos del Depósito")
    try:
        engine_edicion = conectar_db(cuenta_seleccionada)
        df_lista = pd.read_sql(f"SELECT {col_deposito_real} AS nro, nombre FROM pagos", con=engine_edicion)
        
        if not df_lista.empty:
            # Crear opciones legibles para el desplegable (N° Depósito - Nombre)
            df_lista['opcion'] = df_lista['nro'].astype(str) + " - " + df_lista['nombre'].astype(str)
            opciones_dep = df_lista['opcion'].tolist()
            
            deposito_seleccionado_str = st.selectbox("Seleccione el Depósito a Modificar", opciones_dep)
            
            if deposito_seleccionado_str:
                # Extraer el número real de depósito seleccionado
                dep_id = deposito_seleccionado_str.split(" - ")[0]
                
                df_busqueda_dep = pd.read_sql(f"SELECT * FROM pagos WHERE {col_deposito_real} = '{dep_id}'", con=engine_edicion)
                
                if not df_busqueda_dep.empty:
                    reg = df_busqueda_dep.iloc[0]
                    
                    nuevo_monto = st.number_input("Monto (Bs):", value=float(reg['monto']) if pd.notna(reg['monto']) else 0.0, step=10.0, key="edit_monto")
                    nueva_hr = st.text_input("Hoja de Ruta:", value=str(reg['hoja_de_ruta']) if pd.notna(reg['hoja_de_ruta']) else "", key="edit_hr")
                    nueva_obs = st.text_area("Observaciones:", value=str(reg['obs']) if pd.notna(reg['obs']) else "", key="edit_obs")
                    
                    # Manejo flexible de descripción de programa si existe o no en la tabla
                    tiene_prog = 'programa_descripcion' in reg
                    if tiene_prog:
                        nuevo_prog = st.text_input("Descripción Programa:", value=str(reg['programa_descripcion']) if pd.notna(reg['programa_descripcion']) else "", key="edit_prog")
                    
                    if st.button("Guardar Cambios Completos", key="btn_guardar_completo"):
                        with engine_edicion.begin() as conn:
                            if tiene_prog:
                                query_update = text(f"""
                                    UPDATE pagos 
                                    SET monto = :monto, hoja_de_ruta = :hr, obs = :obs, programa_descripcion = :prog 
                                    WHERE {col_deposito_real} = :nro
                                """)
                                conn.execute(query_update, {
                                    "monto": nuevo_monto,
                                    "hr": nueva_hr,
                                    "obs": nueva_obs,
                                    "prog": nuevo_prog,
                                    "nro": dep_id
                                })
                            else:
                                query_update = text(f"""
                                    UPDATE pagos 
                                    SET monto = :monto, hoja_de_ruta = :hr, obs = :obs 
                                    WHERE {col_deposito_real} = :nro
                                """)
                                conn.execute(query_update, {
                                    "monto": nuevo_monto,
                                    "hr": nueva_hr,
                                    "obs": nueva_obs,
                                    "nro": dep_id
                                })
                        
                        st.success(f"¡Depósito {dep_id} actualizado exitosamente!")
                        st.rerun()
        else:
            st.info("No hay registros en esta base de datos.")
    except Exception as e:
        st.error(f"Error al cargar la lista de depósitos: {e}")