import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# Función de conexión a SQLite
@st.cache_resource
def conectar_db(db_name):
    return create_engine(f"sqlite:///{db_name}.db")

# Configuración de la página (DEBE SER LO PRIMERO)
st.set_page_config(page_title="Sistema de Revisión de Pagos", page_icon="💳", layout="wide")

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
    
    # CORRECCIÓN AQUÍ: Se especifica explícitamente el número 3 para crear las columnas
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

# Conexión persistente y limpia a MySQL (XAMPP)
# Conexión a la base de datos SQLite local/en la nube
    @st.cache_resource
    def conectar_db(db_name):
        # Añade la extensión .db al nombre seleccionado
        return create_engine(f"sqlite:///{db_name}.db")

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
    filtrar_monto = st.checkbox("Activar filtro de cantidad exacta")
    monto_buscado = st.number_input("Monto en Bs:", value=0.0, step=10.0)
    
with col_fecha:
    st.markdown("**Filtrar por Fechas:**")
    filtrar_fecha = st.checkbox("Activar filtro de fechas")
    fecha_inicio = st.date_input("Desde la fecha:", value=pd.to_datetime("2015-01-01").date())
    fecha_fin = st.date_input("Hasta la fecha:", value=pd.to_datetime("2026-12-31").date())

st.markdown("---")

# --- CONSTRUCCIÓN DINÁMICA DE LA CONSULTA SQL ---
where_clauses = []
params = []

# Filtro por cuadro de búsqueda principal
if busqueda.strip():
    palabras = busqueda.strip().split()
    condiciones_palabras = []
    for p in palabras:
        condiciones_palabras.append("(nombre LIKE %s OR nro_deposito LIKE %s)")
        params.extend([f"%{p}%", f"%{p}%"])
    where_clauses.append("(" + " AND ".join(condiciones_palabras) + ")")

# Lógica del filtro para aislar depósitos sin Hoja de Ruta
if solo_sin_hoja:
    where_clauses.append("(hoja_de_ruta IS NULL OR TRIM(hoja_de_ruta) = '' OR LOWER(TRIM(hoja_de_ruta)) = 'none')")

# Filtro por monto exacto
if filtrar_monto and monto_buscado > 0:
    where_clauses.append("monto = %s")
    params.append(monto_buscado)

# Filtro por rango de fechas
if filtrar_fecha:
    where_clauses.append("fecha BETWEEN %s AND %s")
    params.extend([fecha_inicio, fecha_fin])

where_sql = ""
if where_clauses:
    where_sql = " WHERE " + " AND ".join(where_clauses)

# Consultas preparadas
query_total = f"SELECT SUM(monto) as total_monto, COUNT(*) as total_registros FROM pagos" + where_sql
query_tabla = f"SELECT fecha, nro_deposito, nombre, participante, monto, hoja_de_ruta, programa_descripcion, mes_declaracion, obs FROM pagos" + where_sql + " LIMIT 500"

# --- BLOQUE FIJO DE RENDERIZADO ---
with st.container():
    try:
        with engine.connect() as conn:
            # 1. Obtener totales globales de la consulta actual
            df_totales = pd.read_sql(query_total, con=conn, params=tuple(params) if params else None)
            total_registros = int(df_totales["total_registros"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_registros"].iloc[0]) else 0
            monto_global = float(df_totales["total_monto"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_monto"].iloc[0]) else 0.0

            # Mostrar totales usando Métricas estáticas
            c1, c2 = st.columns(2)
            with c1:
                st.metric(label="Monto Total General Acumulado", value=f"{monto_global:,.2f} Bs")
            with c2:
                texto_registros = f"{total_registros:,} (Mostrando primeros 500)" if total_registros > 500 else f"{total_registros:,}"
                st.metric(label="Registros Coincidentes", value=texto_registros)

            st.markdown("#### Detalle de Transacciones")

            if total_registros > 0:
                # 2. Cargar los registros
                df = pd.read_sql(query_tabla, con=conn, params=tuple(params) if params else None)
                
                # Formatear nombres de columnas para la interfaz
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

                # Mostrar el DataFrame directamente en pantalla
                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.info("No hay transacciones registradas o ningún elemento coincide con el filtro aplicado.")
                
    except Exception as e:
        st.error(f"Error al realizar la lectura en MySQL: {e}")




