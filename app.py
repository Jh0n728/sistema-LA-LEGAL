import os
import sqlite3
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from busqueda import asegurar_busqueda, limpiar
from resaltar import SQL_REQUIERE_HOJA, TEXTO_CONTROL, marcar_pendientes, resaltar

# Configuración de la página (DEBE SER LO PRIMERO)
st.set_page_config(page_title="Sistema de Revisión de Pagos", layout="wide")

# Directorio base donde se encuentran las bases de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Función de conexión definitiva
@st.cache_resource
def conectar_db(db_name):
    db_path = os.path.join(BASE_DIR, f"{db_name}.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool
    )
    asegurar_busqueda(engine)  # prepara la búsqueda sin tildes (la primera vez tarda unos segundos)
    return engine

# --- CREDENCIALES DE ACCESO ---
# Las credenciales ya no van en el código: se leen de .streamlit/secrets.toml
try:
    USUARIOS_PERMITIDOS = dict(st.secrets["usuarios"])
except Exception:
    USUARIOS_PERMITIDOS = {}
    st.error("Falta configurar los usuarios en .streamlit/secrets.toml (ver instrucciones).")

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

modo = st.sidebar.radio("Modo", ["Consulta de pagos", "Verificar kardex"])
if modo == "Verificar kardex":
    from kardex import pantalla_verificar
    pantalla_verificar(conectar_db)
    st.stop()

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
    solo_sin_hoja = st.checkbox("Mostrar SOLO depósitos que necesitan Hoja de Ruta y aún no la tienen")
    
with col_monto:
    st.markdown("**Filtrar por Monto:**")
    
    # Selector rápido para elegir el tipo de filtro de dinero
    tipo_filtro_monto = st.selectbox(
        "Modo de filtro de monto",
        ["Desactivado", "Monto Exacto", "Rango (Mín - Máx)"],
        label_visibility="collapsed"
    )
    
    monto_buscado = 0.0
    monto_min, monto_max = 0.0, 0.0
    
    if tipo_filtro_monto == "Monto Exacto":
        monto_buscado = st.number_input("Monto exacto en Bs:", value=0.0, step=10.0)
        
    elif tipo_filtro_monto == "Rango (Mín - Máx)":
        col_min, col_max = st.columns(2)
        with col_min:
            monto_min = st.number_input("Mínimo Bs:", value=0.0, step=50.0)
        with col_max:
            monto_max = st.number_input("Máximo Bs:", value=5000.0, step=50.0)
    
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

palabras = limpiar(busqueda).split()  # sin tildes ni mayúsculas
if palabras:
    condiciones_palabras = []
    for p in palabras:
        condiciones_palabras.append("(busqueda LIKE ? OR nro_deposito LIKE ?)")
        params.extend([f"%{p}%", f"%{p}%"])
    where_clauses.append("(" + " AND ".join(condiciones_palabras) + ")")

if solo_sin_hoja:
    where_clauses.append(SQL_REQUIERE_HOJA)  # no cuenta pagos CPT ni con nombre en Participante

# Aplicar según la opción de monto seleccionada
if tipo_filtro_monto == "Monto Exacto" and monto_buscado > 0:
    where_clauses.append("monto = ?")
    params.append(monto_buscado)
elif tipo_filtro_monto == "Rango (Mín - Máx)":
    where_clauses.append("monto BETWEEN ? AND ?")
    params.extend([monto_min, monto_max])

if filtrar_fecha:
    where_clauses.append("fecha BETWEEN ? AND ?")
    params.extend([str(fecha_inicio), str(fecha_fin)])

# Unir cláusulas WHERE si existen
where_sql = ""
if where_clauses:
    where_sql = "WHERE " + " AND ".join(where_clauses)

# Consultas SQL dinámicas para totales y tabla
query_total = f"SELECT COUNT(*) AS total_registros, SUM(monto) AS total_monto FROM pagos {where_sql}"
query_tabla = f"SELECT * FROM pagos {where_sql} LIMIT 500"
where_pend = (where_sql + " AND " if where_sql else "WHERE ") + SQL_REQUIERE_HOJA
query_pend = f"SELECT COUNT(*) FROM pagos {where_pend}"

# --- BLOQUE FIJO DE RENDERIZADO ---
with st.container():
    try:
        with engine.connect() as conn:
            df_totales = pd.read_sql(query_total, con=conn, params=tuple(params) if params else None)
            total_registros = int(df_totales["total_registros"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_registros"].iloc[0]) else 0
            monto_global = float(df_totales["total_monto"].iloc[0]) if not df_totales.empty and pd.notna(df_totales["total_monto"].iloc[0]) else 0.0

            df_pend = pd.read_sql(query_pend, con=conn, params=tuple(params) if params else None)
            total_pend = int(df_pend.iloc[0, 0])

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric(label="Monto Total General Acumulado", value=f"{monto_global:,.2f} Bs")
            with c2:
                texto_registros = f"{total_registros:,} (Mostrando primeros 500)" if total_registros > 500 else f"{total_registros:,}"
                st.metric(label="Registros Coincidentes", value=texto_registros)
            with c3:
                st.metric(label="📄 Faltan Hoja de Ruta", value=f"{total_pend:,}")

            st.markdown("#### Detalle de Transacciones")

            if total_registros > 0:
                df = pd.read_sql(query_tabla, con=conn, params=tuple(params) if params else None)
                
                df = df.drop(columns=["busqueda"], errors="ignore")
                mask_pend = marcar_pendientes(df)
                df.insert(0, "Control", mask_pend.map({True: TEXTO_CONTROL, False: ""}))
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

                st.dataframe(resaltar(df, mask_pend), use_container_width=True, height=500)
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
      key="select_db_admin",
  )

  archivo_subido = st.file_uploader(
      "Subir nuevos depósitos (Excel/CSV)", type=["xlsx", "csv"], key="uploader_admin"
  )

  if archivo_subido is not None:
    try:
      if archivo_subido.name.endswith(".csv"):
        df_nuevos = pd.read_csv(archivo_subido)
      else:
        df_nuevos = pd.read_excel(archivo_subido)

      # --- PREPARAR ARCHIVO Y ANTIDUPLICADOS (N° de depósito + fecha + monto) ---
      from cargar import preparar_y_filtrar

      engine_temp = conectar_db(db_para_actualizar)
      df_filtrado, duplicados_omitidos, mismo_nro, ignoradas = preparar_y_filtrar(
          engine_temp, df_nuevos
      )
      if ignoradas:
        st.caption(
            "Columnas del archivo que no existen en la base y se ignoran: "
            + ", ".join(ignoradas)
        )
      if mismo_nro.any():
        st.warning(
            f"{int(mismo_nro.sum())} registro(s) tienen un N° de depósito que ya existe"
            " en la base pero con otra fecha o monto. Revísalos antes de insertar."
        )
        st.dataframe(df_filtrado[mismo_nro], use_container_width=True)
        if st.checkbox("No insertar esos registros (los reviso aparte)", key="chk_mismo_nro"):
          df_filtrado = df_filtrado[~mismo_nro]

      st.write("Vista previa de registros nuevos a insertar:")
      st.dataframe(df_filtrado, use_container_width=True)

      if duplicados_omitidos > 0:
        st.info(
            f"Se omitieron {duplicados_omitidos} registros porque ya"
            " existían en la base de datos o estaban repetidos en el archivo."
        )

      if len(df_filtrado) > 0:
        if st.button("Confirmar e Insertar", key="btn_confirmar_admin"):
          try:
            df_filtrado.to_sql(
                "pagos", con=engine_temp, if_exists="append", index=False
            )
            asegurar_busqueda(engine_temp)
            st.success(
                f"¡{len(df_filtrado)} registros nuevos agregados exitosamente a"
                f" {db_para_actualizar}!"
            )
            st.rerun()
          except Exception as e:
            st.error(f"Error al insertar. Revisa las columnas. Detalle: {e}")
      else:
        st.warning(
            "Todos los registros del archivo subido ya existen en la base de datos. No hay nada nuevo que agregar."
        )

    except Exception as e:
      st.error(f"Error al leer el archivo: {e}")

# --- SECCIÓN: EDITAR MONTO DE UN DEPÓSITO ---
with st.sidebar.expander("Modificar Registro"):
    st.markdown("### Modificar Monto")
    deposito_a_editar = st.text_input("N° de Depósito a corregir", placeholder="Ej: 15271987")
    nuevo_monto = st.number_input("Nuevo Monto en Bs:", value=0.0, step=10.0)
    
    if st.button("Actualizar Monto", key="btn_editar_monto"):
        try:
            engine_edicion = conectar_db(cuenta_seleccionada)
            with engine_edicion.connect() as conn:
                trans = conn.begin()
                query_update = text("UPDATE pagos SET monto = :monto WHERE nro_deposito = :nro")
                conn.execute(query_update, {"monto": nuevo_monto, "nro": deposito_a_editar})
                trans.commit()
            
            st.success(f"¡Depósito {deposito_a_editar} actualizado a {nuevo_monto} Bs!")
            st.rerun()
        except Exception as e:
            st.error(f"Error al actualizar: {e}")