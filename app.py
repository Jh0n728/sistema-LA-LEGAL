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

# Función de conexión definitiva
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

# Validar si el usuario está logueado, si no, detener ejecución
if not st.session_state.autenticado:
    mostrar_login()
    st.stop()

# --- INTERFAZ PRINCIPAL DEL SISTEMA (USUARIO LOGUEADO) ---

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
    
    with engine.connect() as conn:
        tables_info = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", con=conn)
        tablas_disponibles = tables_info['name'].tolist() if not tables_info.empty else []
        nombre_tabla = 'pagos' if 'pagos' in tablas_disponibles else (tablas_disponibles[0] if tablas_disponibles else 'pagos')
        
        cols_info = pd.read_sql(f"PRAGMA table_info({nombre_tabla});", con=conn)
        columnas_tabla = cols_info['name'].tolist() if not cols_info.empty else []
        
        # Obtener una pequeña muestra de los primeros registros para ver qué hay realmente en la BD
        df_muestra = pd.read_sql(f"SELECT * FROM {nombre_tabla} LIMIT 3", con=conn)
    
    col_deposito_real = 'nro_deposito' if 'nro_deposito' in columnas_tabla else (columnas_tabla[1] if len(columnas_tabla) > 1 else 'nro_deposito')

except Exception as e:
    st.error(f"Error al conectar con la base de datos local: {e}")
    tablas_disponibles = []
    nombre_tabla = "pagos"
    columnas_tabla = []
    col_deposito_real = "nro_deposito"
    df_muestra = pd.DataFrame()
    st.stop()

# --- PANEL DE DIAGNOSTICO EN LA BARRA LATERAL ---
with st.sidebar.expander("🔍 Diagnóstico Avanzado de Datos"):
    st.write(f"**Base de datos:** {cuenta_seleccionada}")
    st.write(f"**Tabla:** `{nombre_tabla}`")
    st.write("**Primeros registros en bruto (Muestra de la BD):**")
    st.dataframe(df_muestra, use_container_width=True)

# Encabezado principal
nombre_cuenta_visible = "Cuenta 33" if "33" in cuenta_seleccionada else "Cuenta 14"
st.title(f"Consulta de Pagos - {nombre_cuenta_visible}")
st.markdown("Escriba los criterios de búsqueda y presione **Enter** para filtrar los datos.")

# --- SECCIÓN DE FILTROS EN TIEMPO REAL ---
st.markdown("### Búsqueda y Filtros")

col_busq, col_monto, col_fecha = st.columns(3)

with col_busq:
    busqueda = st.text_input("Escriba el Nombre o N° de Depósito (Presione Enter):", placeholder="Ej: Juan Pérez o 15271987")
    st.markdown("**Filtro Especial de Control:**")
    solo_sin_hoja = st.checkbox("Mostrar SOLO depósitos SIN Hoja de Ruta") if "hoja_de_ruta" in columnas_tabla else False
    
with col_monto:
    st.markdown("**Filtrar por Monto:**")
    filtrar_monto = st.checkbox("Activar filtro de cantidad exacta")
    monto_buscado = st.number_input("Monto en Bs:", value=0.0, step=10.0)
    
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
        cond_cols = []
        if "nombre" in columnas_tabla:
            cond_cols.append("nombre LIKE ?")
            params.append(f"%{p}%")
        if col_deposito_real in columnas_tabla:
            cond_cols.append(f"{col_deposito_real} LIKE ?")
            params.append(f"%{p}%")
        if "participante" in columnas_tabla:
            cond_cols.append("participante LIKE ?")
            params.append(f"%{p}%")
            
        if cond_cols:
            condiciones_palabras.append("(" + " OR ".join(cond_cols) + ")")
            
    if condiciones_palabras:
        where_clauses.append("(" + " AND ".join(condiciones_palabras) + ")")

if solo_sin_hoja and "hoja_de_ruta" in columnas_tabla:
    where_clauses.append("(hoja_de_ruta IS NULL OR TRIM(hoja_de_ruta) = '' OR LOWER(TRIM(hoja_de_ruta)) = 'none')")

if filtrar_monto and monto_buscado > 0 and "monto" in columnas_tabla:
    where_clauses.append("monto = ?")
    params.append(monto_buscado)

if filtrar_fecha and "fecha" in columnas_tabla:
    where_clauses.append("fecha BETWEEN ? AND ?")
    params.extend([str(fecha_inicio), str(fecha_fin)])

where_sql = ""
if where_clauses:
    where_sql = " WHERE " + " AND ".join(where_clauses)

query_total = f"SELECT SUM(monto) as total_monto, COUNT(*) as total_registros FROM {nombre_tabla}" + where_sql if "monto" in columnas_tabla else f"SELECT 0 as total_monto, COUNT(*) as total_registros FROM {nombre_tabla}" + where_sql

col_fecha_sel = "fecha" if "fecha" in columnas_tabla else "'' AS fecha"
col_dep_sel = f"{col_deposito_real} AS nro_deposito" if col_deposito_real in columnas_tabla else "'' AS nro_deposito"
col_nom_sel = "nombre" if "nombre" in columnas_tabla else "'' AS nombre"
col_part_sel = "participante" if "participante" in columnas_tabla else "'' AS participante"
col_monto_sel = "monto" if "monto" in columnas_tabla else "0 AS monto"
col_hoja_sel = "hoja_de_ruta" if "hoja_de_ruta" in columnas_tabla else "'' AS hoja_de_ruta"
col_prog_sel = "programa_descripcion" if "programa_descripcion" in columnas_tabla else "'' AS programa_descripcion"
col_mes_sel = "mes_declaracion" if "mes_declaracion" in columnas_tabla else "'' AS mes_declaracion"
col_obs_sel = "obs" if "obs" in columnas_tabla else "'' AS obs"

query_tabla = f"SELECT {col_fecha_sel}, {col_dep_sel}, {col_nom_sel}, {col_part_sel}, {col_monto_sel}, {col_hoja_sel}, {col_prog_sel}, {col_mes_sel}, {col_obs_sel} FROM {nombre_tabla}" + where_sql + " LIMIT 500"

# --- BLOQUE FIJO DE RENDERIZADO ---
with st.container():
    try:
        with engine.connect() as conn:
            df_totales = pd.read_sql(query_total, con=conn, params=tuple(params) if params else None)
            total_registros = int(df_totales["total_registros"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_registros"].iloc[0]) else 0
            monto_global = float(df_totales["total_monto"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_monto"].