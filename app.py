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
except Exception as e:
    st.error(f"Error al conectar con la base de datos local: {e}")
    st.stop()

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
    solo_sin_hoja = st.checkbox("Mostrar SOLO depósitos SIN Hoja de Ruta")
    
with col_monto:
    st.markdown("**Filtrar por Monto:**")
    filtrar_monto = st.checkbox("Activar filtro de monto exacto")
    monto_buscado = st.number_input("Monto exacto en Bs:", value=0.0, step=10.0)
    
    # --- NUEVO: FILTRO POR RANGO DE MONTOS (SLIDER) ---
    st.markdown("---")
    st.markdown("**Rango de Montos (Mín - Máx):**")
    filtrar_rango = st.checkbox("Activar filtro por rango de montos")
    
    # Consultamos los límites reales de la base de datos actual para ajustar el slider
    try:
        with engine.connect() as conn_rango:
            df_limites = pd.read_sql("SELECT MIN(monto) as min_m, MAX(monto) as max_m FROM pagos", con=conn_rango)
            db_min = float(df_limites["min_m"].iloc[0]) if not df_limites.empty and pd.notna(df_limites["min_m"].iloc[0]) else 0.0
            db_max = float(df_limites["max_m"].iloc[0]) if not df_limites.empty and pd.notna(df_limites["max_m"].iloc[0]) else 10000.0
            if db_min == db_max:
                db_max = db_min + 100.0
    except:
        db_min, db_max = 0.0, 10000.0

    rango_montos = st.slider(
        "Seleccione intervalo:",
        min_value=db_min,
        max_value=db_max,
        value=(db_min, db_max),
        step=1.0
    )
    
with col_fecha:
    st.markdown("**Filtrar por Fechas:**")
    filtrar_fecha = st.checkbox("Activar filtro de fechas")
    
    fecha_inicio = st.date_input(
        "Desde la fecha:", 
        value=pd.to_datetime("2025-01-01").date(),