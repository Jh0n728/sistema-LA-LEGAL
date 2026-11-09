"""Verificación de kardex: lee PDF, captura/foto o texto pegado y lo cruza con las dos bases."""
import os
import re
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st

from resaltar import TEXTO_CONTROL, requiere_hoja, resaltar

CUENTAS = {"Cuenta 33 (cuotas)": "db_cuenta_33", "Cuenta 14 (valores)": "db_cuenta_14"}
COLS = ["N° Depósito", "Fecha", "Monto"]

# "93126452 18/06/2024 150"  (el N° de fila del kardex se ignora solo)
RE_FILA = re.compile(r"(\d{4,12})\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d[\d.,]*)")


def _monto(s):
    s = s.strip().rstrip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):  # 1.500 o 1,500 -> miles
        s = re.sub(r"[.,]", "", s)
    return float(s.replace(",", "."))


def parsear(texto):
    filas = []
    for linea in texto.replace("|", " ").splitlines():
        m = RE_FILA.search(linea)
        if m:
            nro, d, mes, a, monto = m.groups()
            try:
                filas.append({"N° Depósito": nro, "Fecha": f"{int(d):02d}/{int(mes):02d}/{a}",
                              "Monto": _monto(monto)})
            except ValueError:
                pass
    return pd.DataFrame(filas, columns=COLS)


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


def verificar(motores, kardex):
    """motores: {nombre de cuenta: engine}. Devuelve un DataFrame con el estado de cada pago."""
    for eng in motores.values():
        _indices(eng)
    out = []
    for _, r in kardex.iterrows():
        nro = re.sub(r"\D", "", str(r["N° Depósito"]))
        d = pd.to_datetime(r["Fecha"], dayfirst=True, errors="coerce")
        fecha_iso = None if pd.isna(d) else d.strftime("%Y-%m-%d")
        monto = float(r["Monto"])

        hallados, parecidos = [], []
        for cuenta, eng in motores.items():
            with eng.connect() as con:
                df = pd.read_sql("SELECT * FROM pagos WHERE nro_deposito = ? OR nro_deposito = ?",
                                 con=con, params=(nro, nro + ".0"))
                hallados += [(cuenta, f) for _, f in df.iterrows()]
                if df.empty and fecha_iso:
                    cand = pd.read_sql("SELECT * FROM pagos WHERE substr(fecha,1,10) = ? AND monto = ?",
                                       con=con, params=(fecha_iso, monto))
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
            "Estado": estado, "Control": control, "N° Depósito": nro, "Fecha": r["Fecha"], "Monto": monto,
            "Cuenta": cuenta, "Nombre": _v(f, "nombre"), "Participante": _v(f, "participante"),
            "Hoja de Ruta": _v(f, "hoja_de_ruta"), "Descripción": _v(f, "programa_descripcion"),
            "Mes Declaración": _v(f, "mes_declaracion"), "Obs.": _v(f, "obs"), "Nota": nota,
        })
    return pd.DataFrame(out)


def pantalla_verificar(conectar_db):
    st.title("Verificar kardex del participante")
    st.markdown("Carga el kardex, **corrige lo que haya leído mal** y presiona *Verificar*. "
                "Se busca en las dos cuentas.")
    fuente = st.radio("Fuente del kardex", ["PDF", "Captura o foto", "Pegar texto"], horizontal=True)

    texto = None
    try:
        if fuente == "PDF":
            f = st.file_uploader("Kardex en PDF", type=["pdf"], key="k_pdf")
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

    st.markdown("#### Pagos leídos")
    kardex = st.data_editor(kardex, num_rows="dynamic", use_container_width=True,
                            key=f"ed_{hash(texto)}")
    kardex = kardex.dropna(subset=["N° Depósito", "Fecha", "Monto"])

    if st.button("Verificar", type="primary"):
        res = verificar({n: conectar_db(db) for n, db in CUENTAS.items()}, kardex)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ Encontrados", int((res["Estado"].str.startswith("✅")).sum()))
        c2.metric("⚠️ Revisar", int((res["Estado"].str.startswith("⚠️")).sum()))
        c3.metric("❌ No encontrados", int((res["Estado"].str.startswith("❌")).sum()))
        c4.metric("📄 Faltan hoja de ruta", int((res["Control"] != "").sum()))
        st.dataframe(resaltar(res, res["Control"] != ""), use_container_width=True)
        st.download_button("Descargar resultado (CSV)", res.to_csv(index=False).encode("utf-8-sig"),
                           "verificacion_kardex.csv", "text/csv")
