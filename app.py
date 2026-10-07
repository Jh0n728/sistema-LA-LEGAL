import os
import sqlite3
import streamlit as st
from sqlalchemy import create_engine, text

# Función de conexión a SQLite
import sqlite3

# Función de conexión a SQLite compatible con multihilo y escritura forzada
@st.cache_resource
def conectar_db(db_name):
    db_path = os.path.join(BASE_DIR, f"{db_name}.db")
    db_uri = f"file:{db_path}?mode=rw"
    return create_engine(
        db_uri,
        creator=lambda: sqlite3.connect(db_path, uri=True),
        connect_args={"check_same_thread": False}
    )

# Configuración de la página (DEBE SER LO PRIMERO)
st.set_page_config(page_title="Sistema de Revisión de Pagos", layout="wide")

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
        condiciones_palabras.append("(nombre LIKE ? OR nro_deposito LIKE ? OR participante LIKE ?)")
        params.extend([f"%{p}%", f"%{p}%", f"%{p}%"])
    where_clauses.append("(" + " AND ".join(condiciones_palabras) + ")")

if solo_sin_hoja:
    where_clauses.append("(hoja_de_ruta IS NULL OR TRIM(hoja_de_ruta) = '' OR LOWER(TRIM(hoja_de_ruta)) = 'none')")

if filtrar_monto and monto_buscado > 0:
    where_clauses.append("monto = ?")
    params.append(monto_buscado)

if filtrar_fecha:
    where_clauses.append("fecha BETWEEN ? AND ?")
    params.extend([str(fecha_inicio), str(fecha_fin)])

where_sql = ""
if where_clauses:
    where_sql = " WHERE " + " AND ".join(where_clauses)

query_total = f"SELECT SUM(monto) as total_monto, COUNT(*) as total_registros FROM pagos" + where_sql
query_tabla = f"SELECT fecha, nro_deposito, nombre, participante, monto, hoja_de_ruta, programa_descripcion, mes_declaracion, obs FROM pagos" + where_sql + " LIMIT 500"

# --- BLOQUE FIJO DE RENDERIZADO ---
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

# --- SECCIÓN: ACTUALIZAR REGISTROS DIARIOS EN LA BARRA LATERAL ---
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

    # El procesamiento y vista previa ahora están dentro del expander de la barra lateral
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

            if st.button("Confirmar e Insertar", key="btn_confirmar_admin"):
                try:
                    engine_actualizacion = conectar_db(db_para_actualizar)
                    df_nuevos.to_sql("pagos", con=engine_actualizacion, if_exists="append", index=False)
                    st.success(f"¡{len(df_nuevos)} registros agregados a {db_para_actualizar}!")
                except Exception as e:
                    st.error(f"Error al insertar. Revisa las columnas. Detalle: {e}")
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

# --- SECCIÓN: EDITAR MONTO DE UN DEPÓSITO ---
with st.sidebar.expander("Modificar Registro"):
    st.markdown("### Modificar Monto")
    deposito_a_editar = st.text_input("N° de Depósito a corregir", value="5751288549")
    nuevo_monto = st.number_input("Nuevo Monto en Bs:", value=300.0, step=10.0)
    
    if st.button("Actualizar Monto", key="btn_editar_monto"):
        try:
            # Usamos la cuenta seleccionada actualmente en el menú superior de la barra lateral
            engine_edicion = conectar_db(cuenta_seleccionada)
            with engine_edicion.begin() as conn:
                # Ejecutamos la consulta SQL de actualización
                query_update = text("UPDATE pagos SET monto = :monto WHERE nro_deposito = :nro")
                conn.execute(query_update, {"monto": nuevo_monto, "nro": deposito_a_editar})
            
            st.success(f"¡Depósito {deposito_a_editar} actualizado a {nuevo_monto} Bs!")
            st.rerun() # Recarga la app para ver el cambio reflejado inmediatamente
        except Exception as e:
            st.error(f"Error al actualizar: {e}")
#subir a github y ya ta
