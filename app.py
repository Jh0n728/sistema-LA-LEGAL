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
except Exception as e:
    st.error(f"Error al conectar con la base de datos local: {e}")
    st.stop()

# Encabezado principal
nombre_cuenta_visible = "Cuenta 33" if "33" in cuenta_seleccionada else "Cuenta 14"
st.title(f"Consulta de Pagos - {nombre_cuenta_visible}")

# --- PESTAÑAS PRINCIPALES (Opción 4: Dashboard y Consultas) ---
tab_consulta, tab_dashboard = st.tabs(["📋 Consulta y Gestión", "📊 Panel de Estadísticas"])

with tab_consulta:
    st.markdown("Escriba los criterios de búsqueda y presione **Enter** para filtrar los datos.")
    st.markdown("### Búsqueda y Filtros")

    col_busq, col_monto, col_fecha = st.columns(3)

    with col_busq:
        busqueda = st.text_input("Escriba el Nombre o N° de Depósito:", placeholder="Ej: Juan Pérez o 15271987")
        st.markdown("**Filtro Especial de Control:**")
        solo_sin_hoja = st.checkbox("Mostrar SOLO depósitos SIN Hoja de Ruta")
        
    with col_monto:
        st.markdown("**Filtrar por Rango de Montos:** (Opción 6)")
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
            condiciones_palabras.append("(nombre LIKE ? OR nro_deposito LIKE ? OR participante LIKE ?)")
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
    query_tabla = f"SELECT fecha, nro_deposito, nombre, participante, monto, hoja_de_ruta, programa_descripcion, mes_declaracion, obs FROM pagos" + where_sql + " LIMIT 500"

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

# --- PESTAÑA 2: DASHBOARD DE ESTADÍSTICAS (Opción 4) ---
with tab_dashboard:
    st.subheader("Panel de Estadísticas y Control General")
    try:
        with engine.connect() as conn:
            df_dash = pd.read_sql("SELECT monto, hoja_de_ruta, mes_declaracion FROM pagos", con=conn)
        
        if not df_dash.empty:
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.metric("Total Registros en Base de Datos", f"{len(df_dash):,}")
            with col_d2:
                sin_hr_count = df_dash['hoja_de_ruta'].isna() | (df_dash['hoja_de_ruta'].astype(str).str.strip() == '') | (df_dash['hoja_de_ruta'].astype(str).str.lower() == 'none')
                st.metric("Depósitos sin Hoja de Ruta", f"{sin_hr_count.sum():,}")
            with col_d3:
                con_hr_count = len(df_dash) - sin_hr_count.sum()
                st.metric("Depósitos Procesados", f"{con_hr_count:,}")
            
            st.markdown("---")
            st.markdown("#### Distribución de Ingresos por Mes de Declaración")
            if 'mes_declaracion' in df_dash.columns:
                df_mes = df_dash.groupby('mes_declaracion')['monto'].sum().reset_index()
                st.bar_chart(df_mes.set_index('mes_declaracion'))
        else:
            st.info("La base de datos está vacía, no hay estadísticas para mostrar.")
    except Exception as e:
        st.error(f"Error al cargar las estadísticas: {e}")

# --- SECCIÓN: CARGAR DATOS INTELIGENTE (Opción 5: Sin duplicados) ---
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
                    
                    # Cargar los números de depósito ya existentes para evitar duplicados (Opción 5)
                    try:
                        df_existentes = pd.read_sql("SELECT nro_deposito FROM pagos", con=engine_actualizacion)
                        set_existentes = set(df_existentes['nro_deposito'].astype(str))
                    except:
                        set_existentes = set()
                    
                    # Filtrar filas cuyo nro_deposito no esté registrado previamente
                    df_nuevos['nro_deposito_str'] = df_nuevos['nro_deposito'].astype(str)
                    df_filtrado = df_nuevos[~df_nuevos['nro_deposito_str'].isin(set_existentes)].copy()
                    df_filtrado = df_filtrado.drop(columns=['nro_deposito_str'])
                    
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

# --- SECCIÓN: MODIFICAR REGISTRO COMPLETO (Opción 1) ---
with st.sidebar.expander("Modificar Registro"):
    st.markdown("### Editar Datos del Depósito")
    deposito_a_editar = st.text_input("N° de Depósito a buscar", value="")
    
    if deposito_a_editar.strip():
        try:
            engine_edicion = conectar_db(cuenta_seleccionada)
            df_busqueda_dep = pd.read_sql(f"SELECT * FROM pagos WHERE nro_deposito = '{deposito_a_editar.strip()}'", con=engine_edicion)
            
            if not df_busqueda_dep.empty:
                reg = df_busqueda_dep.iloc[0]
                st.success("¡Depósito encontrado!")
                
                # Campos editables
                nuevo_monto = st.number_input("Monto (Bs):", value=float(reg['monto']) if pd.notna(reg['monto']) else 0.0, step=10.0, key="edit_monto")
                nueva_hr = st.text_input("Hoja de Ruta:", value=str(reg['hoja_de_ruta']) if pd.notna(reg['hoja_de_ruta']) else "", key="edit_hr")
                nueva_obs = st.text_area("Observaciones:", value=str(reg['obs']) if pd.notna(reg['obs']) else "", key="edit_obs")
                nuevo_prog = st.text_input("Descripción Programa:", value=str(reg['programa_descripcion']) if pd.notna(reg['programa_descripcion']) else "", key="edit_prog")
                
                if st.button("Guardar Cambios Completos", key="btn_guardar_completo"):
                    with engine_edicion.begin() as conn:
                        query_update = text("""
                            UPDATE pagos 
                            SET monto = :monto, hoja_de_ruta = :hr, obs = :obs, programa_descripcion = :prog 
                            WHERE nro_deposito = :nro
                        """)
                        conn.execute(query_update, {
                            "monto": nuevo_monto,
                            "hr": nueva_hr,
                            "obs": nueva_obs,
                            "prog": nuevo_prog,
                            "nro": deposito_a_editar.strip()
                        })
                    
                    st.success(f"¡Depósito {deposito_a_editar} actualizado exitosamente!")
                    st.rerun()
            else:
                st.info("No se encontró ningún depósito con ese número en la cuenta seleccionada.")
        except Exception as e:
            st.error(f"Error al buscar/actualizar el registro: {e}")