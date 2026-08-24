import streamlit as st
from supabase import create_client, Client
import uuid
import pandas as pd
from fpdf import FPDF
import io
import urllib.request
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="Cotizador Online", page_icon="📄", layout="wide")

# Conexión a Supabase
try:
    url = st.secrets["SUPABASE_URL"].strip().rstrip('/')
    if url.endswith("/rest/v1"):
        url = url[:-8].rstrip('/')
    key = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("🚨 Error al inicializar la conexión con Supabase:")
    st.write(e)
    st.stop()


# Función para limpiar caracteres especiales incompatibles con PDF (Euro, Yen, etc.)
def limpiar_texto(texto):
    if texto is None:
        return ""
    texto = str(texto)
    reemplazos = {
        "€": "EUR",
        "¥": "RMB",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "’": "'",
        "…": "..."
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return texto.encode("latin-1", "replace").decode("latin-1")


# Función auxiliar para descargar imágenes de URL para el PDF
def obtener_bytes_imagen(url_img):
    if not url_img:
        return None
    try:
        req = urllib.request.Request(url_img, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return io.BytesIO(response.read())
    except Exception:
        return None


# ==========================================
# DISEÑADOR DE PDF PROFESIONAL / EJECUTIVO
# ==========================================
def crear_pdf_cotizacion(empresa, cliente_nombre, cliente_rif, cliente_dir, moneda, items, subtotal, total, num_cotizacion):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    # ------------------------------------
    # 1. ENCABEZADO Y LOGO
    # ------------------------------------
    logo_bytes = obtener_bytes_imagen(empresa.get("logo_url"))
    sello_bytes = obtener_bytes_imagen(empresa.get("sello_firma_url"))

    # Renderizar Logo
    if logo_bytes:
        try:
            pdf.image(logo_bytes, x=15, y=14, w=45)
        except Exception:
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(90, 10, limpiar_texto(empresa['nombre'])[:25], ln=False)
    else:
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(26, 54, 93) # Azul Marino
        pdf.cell(90, 10, limpiar_texto(empresa['nombre'])[:30], ln=False)

    # Título del Documento a la derecha
    pdf.set_xy(110, 14)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(85, 8, "COTIZACION", align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(110)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(85, 5, limpiar_texto(f"N°: {num_cotizacion}"), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(110)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(85, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(10)
    
    # Línea Divisoria Elegante
    pdf.set_draw_color(26, 54, 93)
    pdf.set_line_width(0.8)
    pdf.line(15, 42, 195, 42)
    pdf.ln(4)

    # ------------------------------------
    # 2. BLOQUE EMISOR Y CLIENTE (2 Cajas)
    # ------------------------------------
    y_bloque = pdf.get_y()
    
    # Caja Emisor (Izquierda)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(15, y_bloque, 87, 34, style="FD")
    
    pdf.set_xy(18, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(80, 4, "EMISOR / PROVEEDOR", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(80, 5, limpiar_texto(empresa['nombre'])[:38], new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(80, 4, limpiar_texto(f"RIF/Tax ID: {empresa['rif']}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.multi_cell(80, 4, limpiar_texto(f"Dir: {empresa['direccion']}")[:80])

    # Caja Cliente (Derecha)
    pdf.rect(108, y_bloque, 87, 34, style="FD")
    
    pdf.set_xy(111, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(80, 4, "CLIENTE / DESTINATARIO", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(80, 5, limpiar_texto(cliente_nombre)[:38], new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(80, 4, limpiar_texto(f"RIF/Tax ID: {cliente_rif if cliente_rif else 'N/A'}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.multi_cell(80, 4, limpiar_texto(f"Dir: {cliente_dir if cliente_dir else 'N/A'}")[:80])

    pdf.set_y(y_bloque + 38)

    # ------------------------------------
    # 3. TABLA DE PRODUCTOS Y SERVICIOS
    # ------------------------------------
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(26, 54, 93)

    pdf.cell(95, 8, "  Descripcion del Producto / Servicio", border=1, fill=True)
    pdf.cell(20, 8, "Cant.", border=1, fill=True, align="C")
    pdf.cell(30, 8, "P. Unitario", border=1, fill=True, align="R")
    pdf.cell(35, 8, "Subtotal  ", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    # Filas de Productos
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.set_draw_color(226, 232, 240)
    
    fill = False
    for item in items:
        pdf.set_fill_color(241, 245, 249) if fill else pdf.set_fill_color(255, 255, 255)
        
        pdf.cell(95, 7, f"  {limpiar_texto(item['descripcion'])[:48]}", border="LRTB", fill=fill)
        pdf.cell(20, 7, str(item['cantidad']), border="LRTB", align="C", fill=fill)
        pdf.cell(30, 7, f"{item['precio']:,.2f}", border="LRTB", align="R", fill=fill)
        pdf.cell(35, 7, f"{item['subtotal']:,.2f}  ", border="LRTB", align="R", fill=fill, new_x="LMARGIN", new_y="NEXT")
        fill = not fill

    pdf.ln(4)

    # ------------------------------------
    # 4. TOTALES Y BANCOS
    # ------------------------------------
    y_totales = pdf.get_y()

    # Caja de Datos Bancarios (Izquierda)
    if empresa.get("datos_bancarios"):
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_totales, 105, 32, style="FD")
        
        pdf.set_xy(18, y_totales + 2)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(98, 4, "DATOS BANCARIOS / INSTRUCCIONES DE PAGO:", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(98, 3.5, limpiar_texto(empresa['datos_bancarios'])[:220])

    # Caja Resumen del Total (Derecha)
    pdf.set_xy(125, y_totales)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(30, 7, "Moneda:", align="L")
    pdf.cell(40, 7, limpiar_texto(moneda), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(125)
    pdf.cell(30, 7, "Subtotal:", align="L")
    pdf.cell(40, 7, f"{subtotal:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    # Destacado del Total
    pdf.set_x(125)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(30, 9, "  TOTAL:", fill=True)
    pdf.cell(40, 9, f"{total:,.2f}  ", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    # ------------------------------------
    # 5. SELLO Y FIRMA HÚMEDA
    # ------------------------------------
    y_final = pdf.get_y() + 8
    if sello_bytes:
        try:
            pdf.image(sello_bytes, x=130, y=y_final, w=48)
            pdf.set_xy(130, y_final + 26)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(48, 4, "Firma / Sello Autorizado", align="C")
        except Exception:
            pass

    return bytes(pdf.output())


# ==========================================
# MENÚ DE LA APLICACIÓN (STREAMLIT)
# ==========================================
st.sidebar.title("📌 Menú Cotizador")
opcion = st.sidebar.radio("Selecciona un módulo:", ["1. Empresas", "2. Cotizar", "3. Historial"])

with st.sidebar.expander("🔍 Verificación de Datos"):
    st.write(f"**URL:** `{url}`")
    st.write(f"**Clave empieza con:** `{key[:12]}...`")

# ------------------------------------------
# MÓDULO 1: EMPRESAS
# ------------------------------------------
if opcion == "1. Empresas":
    st.title("🏢 Gestión de Empresas Cotizadoras")
    st.write("Registra o edita los datos de la empresa, su logotipo y el sello/firma.")

    try:
        res = supabase.table("empresas").select("*").execute()
        empresas = res.data
    except Exception as e:
        st.error("🚨 Error al consultar la tabla 'empresas':")
        st.write(e)
        st.stop()

    modo = st.radio("Acción:", ["Registrar Nueva Empresa", "Editar Empresa Existente"], horizontal=True)

    empresa_sel = None
    if modo == "Editar Empresa Existente":
        if not empresas:
            st.info("No hay empresas registradas aún. Registra una primera empresa.")
        else:
            nombres = [e["nombre"] for e in empresas]
            seleccion = st.selectbox("Selecciona la empresa a editar:", nombres)
            empresa_sel = next(e for e in empresas if e["nombre"] == seleccion)

    st.divider()

    nombre_val = empresa_sel["nombre"] if empresa_sel else ""
    direccion_val = empresa_sel["direccion"] if empresa_sel else ""
    rif_val = empresa_sel["rif"] if empresa_sel else ""
    bancos_val = empresa_sel["datos_bancarios"] if empresa_sel else ""

    with st.form("form_empresa", clear_on_submit=False):
        nombre = st.text_input("Nombre de la Empresa *", value=nombre_val)
        rif = st.text_input("Número de RIF / Tax ID *", value=rif_val)
        direccion = st.text_area("Dirección Fiscal", value=direccion_val)
        datos_bancarios = st.text_area("Datos Bancarios para Transferencias", value=bancos_val, help="Ej: Banco X, Cuenta Nro..., SWIFT...")

        st.subheader("🖼️ Imágenes Corporativas")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Logotipo (Fondo Blanco)**")
            if empresa_sel and empresa_sel.get("logo_url"):
                st.image(empresa_sel["logo_url"], width=150, caption="Logo Actual")
            logo_file = st.file_uploader("Subir/Cambiar Logo (PNG o JPG)", type=["png", "jpg", "jpeg"], key="logo")

        with col2:
            st.markdown("**Sello Húmedo y Firma**")
            if empresa_sel and empresa_sel.get("sello_firma_url"):
                st.image(empresa_sel["sello_firma_url"], width=150, caption="Sello/Firma Actual")
            sello_file = st.file_uploader("Subir/Cambiar Sello y Firma (PNG o JPG)", type=["png", "jpg", "jpeg"], key="sello")

        guardar = st.form_submit_button("💾 Guardar Empresa", use_container_width=True)

    if guardar:
        if not nombre or not rif:
            st.error("El Nombre y el RIF son campos obligatorios.")
        else:
            logo_url = empresa_sel.get("logo_url") if empresa_sel else None
            sello_url = empresa_sel.get("sello_firma_url") if empresa_sel else None

            if logo_file:
                ext = logo_file.name.split(".")[-1]
                path_logo = f"logos/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("archivos-cotizador").upload(
                    path=path_logo, 
                    file=logo_file.getvalue(), 
                    file_options={"content-type": logo_file.type, "upsert": "true"}
                )
                logo_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_logo)

            if sello_file:
                ext = sello_file.name.split(".")[-1]
                path_sello = f"sellos/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("archivos-cotizador").upload(
                    path=path_sello, 
                    file=sello_file.getvalue(), 
                    file_options={"content-type": sello_file.type, "upsert": "true"}
                )
                sello_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_sello)

            datos_empresa = {
                "nombre": nombre,
                "rif": rif,
                "direccion": direccion,
                "datos_bancarios": datos_bancarios,
                "logo_url": logo_url,
                "sello_firma_url": sello_url
            }

            if empresa_sel:
                supabase.table("empresas").update(datos_empresa).eq("id", empresa_sel["id"]).execute()
                st.success(f"¡Empresa '{nombre}' actualizada correctamente!")
            else:
                supabase.table("empresas").insert(datos_empresa).execute()
                st.success(f"¡Empresa '{nombre}' registrada con éxito!")
            
            st.rerun()

# ------------------------------------------
# MÓDULO 2: COTIZAR
# ------------------------------------------
elif opcion == "2. Cotizar":
    st.title("📝 Generar Nueva Cotización")
    
    try:
        res = supabase.table("empresas").select("*").execute()
        empresas = res.data
    except Exception as e:
        st.error("Error al cargar empresas")
        st.stop()
        
    if not empresas:
        st.warning("⚠️ Primero debes registrar al menos una Empresa en el Módulo 1.")
        st.stop()
        
    nombres_emp = [e["nombre"] for e in empresas]
    emp_seleccionada = st.selectbox("Selecciona la Empresa Emisora:", nombres_emp)
    empresa = next(e for e in empresas if e["nombre"] == emp_seleccionada)
    
    st.divider()
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("👤 Datos del Cliente")
        cliente_nombre = st.text_input("Nombre / Razón Social del Cliente *")
        cliente_rif = st.text_input("RIF / Tax ID del Cliente")
        cliente_dir = st.text_area("Dirección del Cliente")
        
    with col_c2:
        st.subheader("⚙️ Configuración")
        moneda = st.selectbox("Moneda de la Cotización *", ["USD ($)", "EUR (€)", "RMB (¥)"])
        num_cotizacion = st.text_input("Número de Cotización *", value=f"COT-{datetime.now().strftime('%Y%m%d%H%M')}")

    st.subheader("📦 Productos / Servicios")
    st.write("Agrega o edita las filas directamente en la tabla:")
    
    df_inicial = pd.DataFrame([
        {"Descripción": "Producto / Servicio Ejemplo", "Cantidad": 1, "Precio Unitario": 100.0}
    ])
    
    df_editado = st.data_editor(
        df_inicial,
        num_rows="dynamic",
        column_config={
            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1, default=1),
            "Precio Unitario": st.column_config.NumberColumn("Precio Unitario", min_value=0.0, format="%.2f", default=0.0),
        },
        use_container_width=True
    )
    
    df_editado["Subtotal"] = df_editado["Cantidad"] * df_editado["Precio Unitario"]
    total_cotizacion = df_editado["Subtotal"].sum()
    
    st.markdown(f"### 💰 **Total Cotización:** `{moneda} {total_cotizacion:,.2f}`")
    
    if st.button("📄 Generar y Guardar Cotización", use_container_width=True, type="primary"):
        if not cliente_nombre or total_cotizacion <= 0:
            st.error("Por favor ingresa el nombre del cliente y al menos un producto con precio.")
        else:
            items_list = []
            for _, row in df_editado.iterrows():
                items_list.append({
                    "descripcion": row["Descripción"],
                    "cantidad": int(row["Cantidad"]),
                    "precio": float(row["Precio Unitario"]),
                    "subtotal": float(row["Subtotal"])
                })
                
            pdf_bytes = crear_pdf_cotizacion(
                empresa, cliente_nombre, cliente_rif, cliente_dir, moneda,
                items_list, total_cotizacion, total_cotizacion, num_cotizacion
            )
            
            path_pdf = f"cotizaciones/{num_cotizacion}_{uuid.uuid4()}.pdf"
            supabase.storage.from_("archivos-cotizador").upload(
                path=path_pdf, 
                file=pdf_bytes, 
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            pdf_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_pdf)
            
            datos_cotizacion = {
                "numero_cotizacion": num_cotizacion,
                "empresa_id": empresa["id"],
                "cliente_nombre": cliente_nombre,
                "cliente_rif": cliente_rif,
                "cliente_direccion": cliente_dir,
                "moneda": moneda,
                "items": items_list,
                "subtotal": float(total_cotizacion),
                "total": float(total_cotizacion),
                "pdf_url": pdf_url
            }
            
            try:
                supabase.table("cotizaciones").insert(datos_cotizacion).execute()
                st.success("🎉 ¡Cotización profesional generada con éxito!")
                st.download_button(
                    label="⬇️ Descargar Cotización PDF Profesional",
                    data=pdf_bytes,
                    file_name=f"{num_cotizacion}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e_db:
                st.error("🚨 Error al guardar la cotización en la Base de Datos:")
                st.write(e_db)

# ------------------------------------------
# MÓDULO 3: HISTORIAL
# ------------------------------------------
elif opcion == "3. Historial":
    st.title("📚 Historial de Cotizaciones")
    st.info("Próximamente: Lista de cotizaciones emitidas y descargas.")
