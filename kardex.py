"""Verificación de kardex: PDF (uno o muchos participantes), captura/foto o texto pegado.
Permite filtrar los pagos (nombre, depósito, fechas, montos) y cruzarlos con las dos bases."""
import os
import re
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st

from busqueda import limpiar
from resaltar import TEXTO_CONTROL, requiere_hoja, resaltar

CUENTAS = {"Cuenta 33 (cuotas)": "db_cuenta_33", "Cuenta 14 (valores)": "db_cuenta_14"}
COLS = ["Participante", "Cédula", "Programa", "N° Depósito", "Fecha", "Monto"]

# "93126452 18/06/2024 150"  (el N° de fila del kardex se ignora solo)
RE_FILA = re.compile(r"(\d{4,12})\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d[\d.,]*)")
RE_TITULO = re.compile(r"^\s*DEP[ÓO]SITOS\s*$", re.I)
RE_CEDULA = re.compile(r"C[ée]dula\s+de\s+Identidad\s*:?\s*([0-9A-Za-z-]+)", re.I)


def _monto(s):
    s = s.strip().rstrip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):  # 1.500 o 1,500 -> miles
        s = re.sub(r"[.,]", "", s)
    return float(s.replace(",", "."))


def parsear(texto):
    """Lee uno o varios kardex. Cada kardex empieza en el título DEPÓSITOS; el nombre es la línea
    que está justo encima de 'Paterno Materno Nombre(s)'."""
    lineas = [l.strip() for l in texto.replace("|", " ").splitlines()]
    nombre = cedula = programa = ""
    filas = []
    for i, linea in enumerate(lineas):
        if not linea:
            continue
        if RE_TITULO.match(linea):
            nombre = cedula = programa = ""
            continue
        m = RE_CEDULA.search(linea)
        if m:
            cedula = m.group(1)
        if linea.upper().startswith("PROGRAMA"):
            programa = linea.split(":", 1)[-1].strip()
            sig = lineas[i + 1] if i + 1 < len(lineas) else ""
            if sig and ":" not in sig and not re.search(r"\d", sig):
                programa += " " + sig
            continue
        bajo = linea.lower()
        if "paterno" in bajo and "materno" in bajo:
            j = i - 1
            while j >= 0 and not lineas[j]:
                j -= 1
            if j >= 0 and ":" not in lineas[j]:
                nombre = lineas[j]
            continue
        m = RE_FILA.search(linea)
        if m:
            nro, d, mes, a, monto = m.groups()
            try:
                filas.append({"Participante": nombre or "(sin nombre)", "Cédula": cedula,
                              "Programa": programa, "N° Depósito": nro,
                              "Fecha": f"{int(d):02d}/{int(mes):02d}/{a}", "Monto": _monto(monto)})
            except ValueError:
                pass
    return pd.DataFrame(filas, columns=COLS)


def aplicar_filtros(df, nombre="", nro="", modo="Todos", exacto=0.0, mn=0.0, mx=0.0,
                    usar_fecha=False, desde=None, hasta=None):
    """Máscara de filas que cumplen todos los filtros. El nombre se busca sin importar el orden."""
    mask = pd.Series(True, index=df.index)
    palabras = limpiar(nombre).split()
    if palabras:
        norm = df["Participante"].map(limpiar)
        for p in palabras:
            mask &= norm.str.contains(p, regex=False)
    d = re.sub(r"\D", "", nro or "")
    if d:
        mask &= df["N° Depósito"].astype(str).str.contains(d, regex=False)
    montos = pd.to_numeric(df["Monto"], errors="coerce")
    if modo == "Monto exacto":
        mask &= (montos - exacto).abs() < 0.01
    elif modo == "Rango (Mín - Máx)":
        mask &= montos.between(mn, mx)
    if usar_fecha and desde and hasta:
        fechas = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
        mask &= fechas.between(pd.Timestamp(desde), pd.Timestamp(hasta))
    return mask


def leer_pdf(archivo):
    import pdfplumber
    with pdfplumber.open(archivo) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def leer_imagen(archivo):
    import pytesseract
    from PIL import Image
    ruta = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(ruta):
        pytesseract.pytesseract.tesseract_cmd = ruta
    img = Image.open(archivo).convert("L")
    img = img.resize((img.width * 2, img.height * 2))  # ayuda con letra pequeña
    return pytesseract.image_to_string(img, config="--psm 6")


def _v(fila, campo):
    x = fila.get(campo)
    return "" if x is None or pd.isna(x) else x


def _indices(eng):
    try:
        with eng.begin() as con:
            con.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_pagos_nro ON pagos(nro_deposito)")
            con.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_pagos_fecha ON pagos(fecha)")
    except Exception:
        pass


def verificar(motores, kardex, progreso=None):
    """motores: {nombre de cuenta: engine}. Devuelve un DataFrame con el estado de cada pago."""
    for eng in motores.values():
        _indices(eng)
    out, total = [], max(len(kardex), 1)
    for n, (_, r) in enumerate(kardex.iterrows(), start=1):
        if progreso:
            progreso(n / total)
        nro = re.sub(r"\D", "", str(r["N° Depósito"]))
        d = pd.to_datetime(r["Fecha"], dayfirst=True, errors="coerce")
        fecha_iso = None if pd.isna(d) else d.strftime("%Y-%m-%d")
        dia_sig = None if pd.isna(d) else (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        monto = float(r["Monto"])

        hallados, parecidos = [], []
        for cuenta, eng in motores.items():
            with eng.connect() as con:
                df = pd.read_sql("SELECT * FROM pagos WHERE nro_deposito = ? OR nro_deposito = ?",
                                 con=con, params=(nro, nro + ".0"))
                hallados += [(cuenta, f) for _, f in df.iterrows()]
                if df.empty and fecha_iso:
                    cand = pd.read_sql("SELECT * FROM pagos WHERE fecha >= ? AND fecha < ? AND monto = ?",
                                       con=con, params=(fecha_iso, dia_sig, monto))
                    for _, f in cand.iterrows():
                        otro = re.sub(r"\.0$", "", str(f["nro_deposito"]).strip())
                        if SequenceMatcher(None, otro, nro).ratio() >= 0.8:
                            parecidos.append((cuenta, f, otro))

        exactos = [h for h in hallados
                   if str(_v(h[1], "fecha"))[:10] == fecha_iso
                   and abs(pd.to_numeric(_v(h[1], "monto"), errors="coerce") - monto) < 0.01]
        nota = ""
        if exactos:
            estado, (cuenta, f) = "✅ Encontrado", exactos[0]
            if len(exactos) > 1:
                nota = f"Aparece {len(exactos)} veces en las bases"
        elif hallados:
            estado, (cuenta, f) = "⚠️ Revisar", hallados[0]
            dif = []
            if str(_v(f, "fecha"))[:10] != fecha_iso:
                dif.append(f"fecha en base: {str(_v(f, 'fecha'))[:10]}")
            if abs(pd.to_numeric(_v(f, "monto"), errors="coerce") - monto) >= 0.01:
                dif.append(f"monto en base: {_v(f, 'monto')}")
            nota = "Coincide el N° pero difiere " + " / ".join(dif)
        elif parecidos:
            estado, (cuenta, f, otro) = "⚠️ Revisar", parecidos[0]
            nota = f"No existe ese N°; hay uno parecido con misma fecha y monto: {otro}"
        else:
            estado, cuenta, f, nota = "❌ No encontrado", "", pd.Series(dtype=object), ""

        control = TEXTO_CONTROL if (not estado.startswith("❌") and requiere_hoja(
            _v(f, "hoja_de_ruta"), _v(f, "nombre"), _v(f, "participante"))) else ""
        out.append({
            "Estado": estado, "Control": control,
            "Participante (kardex)": _v(r, "Participante"),
            "N° Depósito": nro, "Fecha": r["Fecha"], "Monto": monto,
            "Cuenta": cuenta, "Nombre": _v(f, "nombre"), "Participante": _v(f, "participante"),
            "Hoja de Ruta": _v(f, "hoja_de_ruta"), "Descripción": _v(f, "programa_descripcion"),
            "Mes Declaración": _v(f, "mes_declaracion"), "Obs.": _v(f, "obs"), "Nota": nota,
        })
    return pd.DataFrame(out)


def _panel_filtros(df):
    """Dibuja los filtros y devuelve la máscara de filas que se deben mostrar."""
    st.markdown("#### Filtros")
    c1, c2, c3 = st.columns(3)
    with c1:
        nombre = st.text_input("Participante (nombre y apellidos, en cualquier orden)", key="kf_nombre")
        nro = st.text_input("N° de depósito", key="kf_nro")
    exacto = mn = mx = 0.0
    with c2:
        modo = st.selectbox("Filtrar por monto", ["Todos", "Monto exacto", "Rango (Mín - Máx)"], key="kf_modo")
        if modo == "Monto exacto":
            exacto = st.number_input("Monto exacto en Bs:", value=0.0, step=10.0, key="kf_exacto")
        elif modo == "Rango (Mín - Máx)":
            a, b = st.columns(2)
            mn = a.number_input("Mínimo Bs:", value=0.0, step=50.0, key="kf_min")
            mx = b.number_input("Máximo Bs:", value=5000.0, step=50.0, key="kf_max")
    desde = hasta = None
    with c3:
        usar_fecha = st.checkbox("Filtrar por fechas", key="kf_usar_fecha")
        if usar_fecha:
            f = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce").dropna()
            lo = f.min().date() if len(f) else pd.Timestamp.today().date()
            hi = f.max().date() if len(f) else lo
            desde = st.date_input("Desde:", value=lo, min_value=lo, max_value=hi)
            hasta = st.date_input("Hasta:", value=hi, min_value=lo, max_value=hi)
    return aplicar_filtros(df, nombre, nro, modo, exacto, mn, mx, usar_fecha, desde, hasta)


def _mostrar_resultado(res):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Encontrados", int((res["Estado"].str.startswith("✅")).sum()))
    c2.metric("⚠️ Revisar", int((res["Estado"].str.startswith("⚠️")).sum()))
    c3.metric("❌ No encontrados", int((res["Estado"].str.startswith("❌")).sum()))
    c4.metric("📄 Faltan hoja de ruta", int((res["Control"] != "").sum()))
    if res["Participante (kardex)"].nunique() > 1:
        st.markdown("#### Resumen por participante")
        resumen = res.groupby("Participante (kardex)", sort=False).agg(
            Pagos=("Monto", "size"), Monto_total=("Monto", "sum"),
            Encontrados=("Estado", lambda s: int(s.str.startswith("✅").sum())),
            Revisar=("Estado", lambda s: int(s.str.startswith("⚠️").sum())),
            No_encontrados=("Estado", lambda s: int(s.str.startswith("❌").sum())),
            Sin_hoja_de_ruta=("Control", lambda s: int((s != "").sum())),
        ).reset_index()
        st.dataframe(resumen, use_container_width=True)
    st.markdown("#### Detalle de pagos")
    st.dataframe(resaltar(res, res["Control"] != ""), use_container_width=True)
    st.download_button("Descargar resultado (CSV)", res.to_csv(index=False).encode("utf-8-sig"),
                       "verificacion_kardex.csv", "text/csv")


def pantalla_verificar(conectar_db):
    st.title("Verificar kardex de participantes")
    st.markdown("Carga uno o varios kardex, **filtra** los pagos que quieres revisar, corrige lo que "
                "haya leído mal y presiona *Verificar*. Se busca en las dos cuentas.")
    fuente = st.radio("Fuente del kardex", ["PDF", "Captura o foto", "Pegar texto"], horizontal=True)

    texto = None
    try:
        if fuente == "PDF":
            f = st.file_uploader("Kardex en PDF (puede traer varios participantes)", type=["pdf"], key="k_pdf")
            texto = leer_pdf(f) if f else None
        elif fuente == "Captura o foto":
            f = st.file_uploader("Captura o foto del kardex", type=["png", "jpg", "jpeg"], key="k_img")
            if f:
                st.image(f, width=450)
                texto = leer_imagen(f)
        else:
            t = st.text_area("Pega aquí la tabla copiada de la página del kardex", height=200)
            texto = t if t.strip() else None
    except ImportError as e:
        st.error(f"Falta instalar una librería: {e}. Revisa requirements.txt.")
        return
    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")
        return

    if texto is None:
        return
    kardex = parsear(texto)
    if kardex.empty:
        st.warning("No encontré filas con depósito, fecha y monto. Si es un PDF escaneado o una foto "
                   "borrosa, prueba con 'Pegar texto' o con una captura más nítida.")
        with st.expander("Texto leído"):
            st.text(texto)
        return

    n_part = kardex["Participante"].nunique()
    st.success(f"Se leyeron {len(kardex)} pagos de {n_part} participante(s).")
    if (kardex["Participante"] == "(sin nombre)").any():
        st.warning("Algunos pagos no tienen nombre de participante (no se detectó en el kardex).")
        with st.expander("Ver texto leído"):
            st.text(texto)

    mask = _panel_filtros(kardex)
    vista = kardex[mask].reset_index(drop=True)
    st.markdown(f"#### Pagos a verificar: {len(vista)} de {len(kardex)}")
    vista = st.data_editor(vista, num_rows="dynamic", use_container_width=True,
                           key=f"ed_{hash(texto)}_{hash(tuple(mask.tolist()))}")
    vista = vista.dropna(subset=["N° Depósito", "Fecha", "Monto"]).fillna({"Participante": ""})

    if st.button(f"Verificar estos {len(vista)} pagos", type="primary", disabled=vista.empty):
        barra = st.progress(0.0, text="Verificando...")
        res = verificar({n: conectar_db(db) for n, db in CUENTAS.items()}, vista,
                        progreso=lambda p: barra.progress(p, text="Verificando..."))
        barra.empty()
        st.session_state["resultado_kardex"] = (hash(texto), res)

    guardado = st.session_state.get("resultado_kardex")
    if guardado and guardado[0] == hash(texto):
        _mostrar_resultado(guardado[1])
