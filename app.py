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


# Función para limpiar caracteres especiales incompatibles con PDF
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


# Función para imprimir bloques de texto formateando en NEGRITA lo que está antes de ':'
def render_texto_con_dospuntos(pdf, texto, x_start, max_w, font_size=8.5, line_h=4.5):
    if not texto:
        return
    for linea in str(texto).split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        if ":" in linea:
            partes = linea.split(":", 1)
            clave = partes[0].strip() + ":"
            valor = " " + partes[1].strip()
            
            pdf.set_x(x_start)
            pdf.set_font("Helvetica", "B", font_size)
            w_clave = pdf.get_string_width(limpiar_texto(clave)) + 1.5
            
            # Si la clave es muy larga para la línea, hacer multi_cell
            if w_clave > (max_w - 10):
                pdf.multi_cell(max_w, line_h, limpiar_texto(linea))
            else:
                pdf.cell(w_clave, line_h, limpiar_texto(clave), ln=0)
                pdf.set_font("Helvetica", "", font_size)
                pdf.multi_cell(max_w - w_clave, line_h, limpiar_texto(valor))
        else:
            pdf.set_x(x_start)
            pdf.set_font("Helvetica", "", font_size)
            pdf.multi_cell(max_w, line_h, limpiar_texto(linea))


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
# DISEÑADOR DE PDF PROFESIONAL MULTI-IDIOMA
# ==========================================
def crear_pdf_cotizacion(
    empresa, cliente_nombre, cliente_rif, cliente_dir, moneda, items, 
    subtotal, monto_iva, alicuota_iva, total, num_cotizacion,
    tipo_documento, idioma, validez, incoterm, condiciones_pago, notas
):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    es_ingles = (idioma == "Inglés")
    
    # Títulos principales según tipo e idioma
    if tipo_documento == "Proforma Invoice":
        titulo_doc = "PROFORMA INVOICE"
    elif tipo_documento == "Factura Comercial":
        titulo_doc = "COMMERCIAL INVOICE" if es_ingles else "FACTURA COMERCIAL"
    else:
        titulo_doc = "QUOTATION" if es_ingles else "COTIZACION"

    lbl_num = "No.:" if es_ingles else "N°:"
    lbl_fecha = "Date:" if es_ingles else "Fecha:"
    lbl_validez = "Validity:" if es_ingles else "Validez:"
    lbl_emisor = "ISSUER / SUPPLIER" if es_ingles else "EMISOR / PROVEEDOR"
    lbl_cliente = "CLIENT / RECIPIENT" if es_ingles else "CLIENTE / DESTINATARIO"
    lbl_desc = "  Description of Goods / Services" if es_ingles else "  Descripcion del Producto / Servicio"
    lbl_cant = "Qty" if es_ingles else "Cant."
    lbl_precio = "Unit Price" if es_ingles else "P. Unitario"
    lbl_sub = "Subtotal  "
    lbl_bancos = "BANK DETAILS / PAYMENT INSTRUCTIONS:" if es_ingles else "DATOS BANCARIOS PARA TRANSFERENCIA:"
    lbl_cond_pago = "Payment Terms:" if es_ingles else "Condiciones de Pago:"
    lbl_incoterm = "Incoterm:" if es_ingles else "Incoterm:"
    lbl_notas = "REMARKS / COMPLEMENTARY NOTES:" if es_ingles else "NOTAS COMPLEMENTARIAS / OBSERVACIONES:"
    lbl_firma = "Authorized Signature / Stamp" if es_ingles else "Firma / Sello Autorizado"

    # ------------------------------------
    # 1. ENCABEZADO Y LOGO
    # ------------------------------------
    logo_bytes = obtener_bytes_imagen(empresa.get("logo_url"))
    sello_bytes = obtener_bytes_imagen(empresa.get("sello_firma_url"))

    if logo_bytes:
        try:
            pdf.image(logo_bytes, x=15, y=14, w=45)
        except Exception:
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(90, 10, limpiar_texto(empresa['nombre'])[:25], ln=False)
    else:
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(90, 10, limpiar_texto(empresa['nombre'])[:30], ln=False)

    pdf.set_xy(105, 12)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(90, 7, titulo_doc, align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(105)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(90, 4.5, limpiar_texto(f"{lbl_num} {num_cotizacion}"), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(105)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 4, f"{lbl_fecha} {datetime.now().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")

    if validez:
        pdf.set_x(105)
        pdf.cell(90, 4, limpiar_texto(f"{lbl_validez} {validez}"), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    
    # Línea Divisoria
    pdf.set_draw_color(26, 54, 93)
    pdf.set_line_width(0.8)
    pdf.line(15, 42, 195, 42)
    pdf.ln(4)

    # ------------------------------------
    # 2. BLOQUE EMISOR Y CLIENTE
    # ------------------------------------
    y_bloque = pdf.get_y()
    
    # Caja Emisor
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(15, y_bloque, 87, 34, style="FD")
    
    pdf.set_xy(18, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(80, 4, lbl_emisor, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(80, 4.5, limpiar_texto(empresa['nombre'])[:38], new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(80, 4, limpiar_texto(f"RIF/Tax ID: {empresa['rif']}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.multi_cell(80, 3.8, limpiar_texto(f"Dir: {empresa['direccion']}")[:80])

    # Caja Cliente
    pdf.rect(108, y_bloque, 87, 34, style="FD")
    
    pdf.set_xy(111, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(80, 4, lbl_cliente, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(80, 4.5, limpiar_texto(cliente_nombre)[:38], new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(80, 4, limpiar_texto(f"RIF/Tax ID: {cliente_rif if cliente_rif else 'N/A'}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.multi_cell(80, 3.8, limpiar_texto(f"Dir: {cliente_dir if cliente_dir else 'N/A'}")[:80])

    pdf.set_y(y_bloque + 38)

    # ------------------------------------
    # 3. TABLA DE PRODUCTOS Y SERVICIOS
    # ------------------------------------
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(26, 54, 93)

    pdf.cell(95, 8, lbl_desc, border=1, fill=True)
    pdf.cell(20, 8, lbl_cant, border=1, fill=True, align="C")
    pdf.cell(30, 8, lbl_precio, border=1, fill=True, align="R")
    pdf.cell(35, 8, lbl_sub, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

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

    pdf.ln(5)

    # ------------------------------------
    # 4. MÓDULO BANCARIO Y TOTALES
    # ------------------------------------
    y_seccion4 = pdf.get_y()

    # --- 4A. MÓDULO EXCLUSIVO DE DATOS BANCARIOS (Izquierda) ---
    bancos_texto = empresa.get("datos_bancarios", "")
    lineas_bancos = [l for l in str(bancos_texto).split("\n") if l.strip()]
    num_lineas_bancos = len(lineas_bancos)

    # Cálculo dinámico de altura para que la caja contenga TODO holgadamente
    box_h_bancos = max(32, (num_lineas_bancos * 5) + 8)

    if bancos_texto:
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_seccion4, 102, box_h_bancos, style="FD")
        
        pdf.set_xy(18, y_seccion4 + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(96, 4, lbl_bancos, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        # Renderizado con letra más grande (8.5pt) y negrita antes de ':'
        render_texto_con_dospuntos(pdf, bancos_texto, x_start=18, max_w=96, font_size=8.5, line_h=4.8)

    # --- 4B. MÓDULO RESUMEN DE TOTALES (Derecha) ---
    pdf.set_xy(123, y_seccion4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(71, 85, 105)
    
    pdf.cell(32, 6, "Moneda / Currency:" if es_ingles else "Moneda:", align="L")
    pdf.cell(40, 6, limpiar_texto(moneda), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(123)
    pdf.cell(32, 6, "Subtotal:", align="L")
    pdf.cell(40, 6, f"{subtotal:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    if monto_iva > 0:
        pdf.set_x(123)
        lbl_tax = f"Tax/VAT ({alicuota_iva:.0f}%):" if es_ingles else f"IVA ({alicuota_iva:.0f}%):"
        pdf.cell(32, 6, lbl_tax, align="L")
        pdf.cell(40, 6, f"{monto_iva:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    # Destacado del Total
    pdf.set_x(123)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(32, 8.5, "  TOTAL:", fill=True)
    pdf.cell(40, 8.5, f"{total:,.2f}  ", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    # Definir posición Y para los siguientes módulos
    y_pos_siguiente = max(y_seccion4 + box_h_bancos + 5, pdf.get_y() + 6)
    pdf.set_y(y_pos_siguiente)

    # ------------------------------------
    # 5. MÓDULO EXCLUSIVO DE CONDICIONES COMERCIALES
    # ------------------------------------
    if condiciones_pago or (incoterm and incoterm != "N/A") or validez:
        y_cond = pdf.get_y()
        
        lineas_cond = 0
        if condiciones_pago: lineas_cond += 1
        if incoterm and incoterm != "N/A": lineas_cond += 1
        if validez: lineas_cond += 1
        
        box_h_cond = (lineas_cond * 5) + 8
        
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_cond, 180, box_h_cond, style="FD")
        
        pdf.set_xy(18, y_cond + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(174, 4, "CONDICIONES COMERCIALES / TERMS OF SALE:" if es_ingles else "CONDICIONES COMERCIALES Y DE PAGO:", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        if condiciones_pago:
            render_texto_con_dospuntos(pdf, f"{lbl_cond_pago} {condiciones_pago}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if incoterm and incoterm != "N/A":
            render_texto_con_dospuntos(pdf, f"{lbl_incoterm} {incoterm}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if validez:
            render_texto_con_dospuntos(pdf, f"{lbl_validez} {validez}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
            
        pdf.set_y(y_cond + box_h_cond + 5)

    # ------------------------------------
    # 6. MÓDULO EXCLUSIVO DE NOTAS COMPLEMENTARIAS
    # ------------------------------------
    if notas:
        y_notas = pdf.get_y()
        lineas_notas_count = len([l for l in str(notas).split("\n") if l.strip()])
        box_h_notas = max(16, (lineas_notas_count * 5) + 8)
        
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_notas, 180, box_h_notas, style="FD")
        
        pdf.set_xy(18, y_notas + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(174, 4, lbl_notas, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        render_texto_con_dospuntos(pdf, notas, x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        pdf.set_y(y_notas + box_h_notas + 5)

    # ------------------------------------
    # 7. SELLO Y FIRMA HÚMEDA
    # ------------------------------------
    y_final = pdf.get_y() + 2
    if sello_bytes:
        try:
            if y_final + 28 > 280:
                pdf.add_page()
                y_final = 20
                
            pdf.image(sello_bytes, x=135, y=y_final, w=45)
            pdf.set_xy(135, y_final + 24)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(45, 4, lbl_firma, align="C")
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
        datos_bancarios = st.text_area(
            "Datos Bancarios para Transferencias", 
            value=bancos_val, 
            help="Escribe cada dato en su línea con dos puntos (:), ejemplo:\nBank Name: Bank of America\nAccount Number: 1234567"
        )

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
    st.title("📝 Generar Nueva Cotización / Factura Proforma")
    
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
    
    # 1. Configuración Principal del Documento
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        tipo_documento = st.selectbox("Tipo de Documento *", ["Cotización", "Proforma Invoice", "Factura Comercial"])
    with col_t2:
        idioma = st.selectbox("Idioma del Documento *", ["Español", "Inglés"])
    with col_t3:
        moneda = st.selectbox("Moneda *", ["USD ($)", "EUR (€)", "RMB (¥)"])

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("👤 Datos del Cliente")
        cliente_nombre = st.text_input("Nombre / Razón Social del Cliente *")
        cliente_rif = st.text_input("RIF / Tax ID del Cliente")
        cliente_dir = st.text_area("Dirección del Cliente", height=80)
        
    with col_c2:
        st.subheader("⚙️ Detalles Comerciales")
        num_cotizacion = st.text_input("Número de Documento *", value=f"COT-{datetime.now().strftime('%Y%m%d%H%M')}")
        validez = st.text_input("Tiempo de Validez", value="15 Días")
        incoterm = st.selectbox(
            "Incoterm (Opcional)", 
            ["N/A", "EXW - Ex Works", "FOB - Free on Board", "FCA - Free Carrier", "CIF - Cost, Insurance & Freight", "CFR - Cost and Freight", "DDP - Delivered Duty Paid", "DAP - Delivered at Place", "CIP - Carriage and Insurance Paid to", "CPT - Carriage Paid To", "DPU - Delivered at Place Unloaded", "FAS - Free Alongside Ship"]
        )
        condiciones_pago = st.text_input("Condiciones de Pago", value="100% Anticipado")

    st.subheader("📦 Productos / Servicios")
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
    
    # Cálculos
    df_editado["Subtotal"] = df_editado["Cantidad"] * df_editado["Precio Unitario"]
    subtotal_cotizacion = df_editado["Subtotal"].sum()

    st.divider()
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        aplica_iva = st.checkbox("¿Aplica Impuestos / IVA?", value=False)
        alicuota_iva = st.number_input("Alícuota de Impuesto (%)", min_value=0.0, max_value=100.0, value=16.0, step=1.0) if aplica_iva else 0.0
        monto_iva = subtotal_cotizacion * (alicuota_iva / 100.0) if aplica_iva else 0.0
        total_cotizacion = subtotal_cotizacion + monto_iva

        st.markdown(f"**Subtotal:** `{moneda} {subtotal_cotizacion:,.2f}`")
        if aplica_iva:
            st.markdown(f"**Impuesto ({alicuota_iva:.0f}%):** `{moneda} {monto_iva:,.2f}`")
        st.markdown(f"### 💰 **Total:** `{moneda} {total_cotizacion:,.2f}`")

    with col_i2:
        notas = st.text_area("Notas Complementarias / Observaciones", help="Aclaratorias de despacho, garantías, etc.")

    st.divider()

    if st.button("📄 Generar y Guardar Documento", use_container_width=True, type="primary"):
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
                items_list, subtotal_cotizacion, monto_iva, alicuota_iva, 
                total_cotizacion, num_cotizacion, tipo_documento, idioma, 
                validez, incoterm, condiciones_pago, notas
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
                "subtotal": float(subtotal_cotizacion),
                "alicuota_iva": float(alicuota_iva),
                "monto_iva": float(monto_iva),
                "total": float(total_cotizacion),
                "tipo_documento": tipo_documento,
                "idioma": idioma,
                "validez": validez,
                "incoterm": incoterm,
                "condiciones_pago": condiciones_pago,
                "notas": notas,
                "pdf_url": pdf_url
            }
            
            try:
                supabase.table("cotizaciones").insert(datos_cotizacion).execute()
                st.success("🎉 ¡Documento emitido y guardado con éxito!")
                st.download_button(
                    label=f"⬇️ Descargar {tipo_documento} (PDF)",
                    data=pdf_bytes,
                    file_name=f"{num_cotizacion}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e_db:
                st.error("🚨 Error al guardar en la Base de Datos:")
                st.write(e_db)

# ------------------------------------------
# MÓDULO 3: HISTORIAL
# ------------------------------------------
elif opcion == "3. Historial":
    st.title("📚 Historial de Cotizaciones")
    st.info("Próximamente: Lista de cotizaciones emitidas y descargas.")
