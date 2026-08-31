import streamlit as st
from supabase import create_client, Client
import uuid
import pandas as pd
from fpdf import FPDF
import io
import urllib.request
from datetime import datetime
import json

# Configuración de la página
st.set_page_config(page_title="Cotizador & Compras Online", page_icon="📄", layout="wide")

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


# Función para determinar si un texto debe considerarse "vacío" u "oculto"
def es_vacio_o_none(texto):
    if texto is None:
        return True
    txt = str(texto).strip().lower()
    return txt in ["", "none", "empty", "null", "n/a", "undefined", "omitir"]


# Función para extraer lista de cuentas bancarias
def obtener_cuentas_bancarias(empresa_obj):
    if not empresa_obj:
        return []
    raw = empresa_obj.get("datos_bancarios", "")
    if es_vacio_o_none(raw):
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [{"alias": "Cuenta Principal", "detalles": raw}]
    return []


# Función para limpiar caracteres especiales incompatibles con PDF
def limpiar_texto(texto):
    if es_vacio_o_none(texto):
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


# Helper para calcular cuántas líneas ocupará un texto envuelto en cierto ancho
def calcular_lineas_multiline(pdf, texto, ancho, font_name="Helvetica", font_style="", font_size=8.5):
    if es_vacio_o_none(texto):
        return 1
    pdf.set_font(font_name, font_style, font_size)
    ancho_util = max(5.0, ancho - 2.0)
    lineas_totales = 0
    for parrafo in str(texto).split("\n"):
        parrafo_limpio = parrafo.strip()
        if not parrafo_limpio:
            continue
        words = parrafo_limpio.split(" ")
        linea_actual = ""
        for w in words:
            w_limpio = limpiar_texto(w)
            w_width = pdf.get_string_width(w_limpio)
            
            if w_width > ancho_util:
                if linea_actual:
                    lineas_totales += 1
                    linea_actual = ""
                lineas_totales += max(1, int(w_width / ancho_util) + 1)
                continue

            test_line = (linea_actual + " " + w).strip()
            if pdf.get_string_width(limpiar_texto(test_line)) <= ancho_util:
                linea_actual = test_line
            else:
                lineas_totales += 1
                linea_actual = w
        if linea_actual:
            lineas_totales += 1
    return max(1, lineas_totales)


# Helper para calcular el número exacto de renglones impresos por render_texto_con_dospuntos
def calcular_lineas_totales_texto(pdf, texto, max_w, font_size=8.5):
    if es_vacio_o_none(texto):
        return 0
    lineas_count = 0
    for linea in str(texto).split("\n"):
        linea = linea.strip()
        if not linea or es_vacio_o_none(linea):
            continue
        if ":" in linea:
            partes = linea.split(":", 1)
            clave = partes[0].strip() + ":"
            valor = " " + partes[1].strip()
            pdf.set_font("Helvetica", "B", font_size)
            w_clave = pdf.get_string_width(limpiar_texto(clave)) + 1.5
            if w_clave > (max_w - 10):
                lineas_count += calcular_lineas_multiline(pdf, linea, max_w, font_size=font_size)
            else:
                lineas_count += calcular_lineas_multiline(pdf, valor, max_w - w_clave, font_size=font_size)
        else:
            font_style = "B" if (linea.startswith("[") and linea.endswith("]")) else ""
            lineas_count += calcular_lineas_multiline(pdf, linea, max_w, font_style=font_style, font_size=font_size)
    return lineas_count


# Función para imprimir bloques de texto formateando en NEGRITA lo que está antes de ':'
def render_texto_con_dospuntos(pdf, texto, x_start, max_w, font_size=8.5, line_h=4.5):
    if es_vacio_o_none(texto):
        return
    for linea in str(texto).split("\n"):
        linea = linea.strip()
        if not linea or es_vacio_o_none(linea):
            continue
        if ":" in linea:
            partes = linea.split(":", 1)
            clave = partes[0].strip() + ":"
            valor = " " + partes[1].strip()
            
            pdf.set_x(x_start)
            pdf.set_font("Helvetica", "B", font_size)
            w_clave = pdf.get_string_width(limpiar_texto(clave)) + 1.5
            
            if w_clave > (max_w - 10):
                pdf.multi_cell(max_w, line_h, limpiar_texto(linea))
            else:
                pdf.cell(w_clave, line_h, limpiar_texto(clave), ln=0)
                pdf.set_font("Helvetica", "", font_size)
                pdf.multi_cell(max_w - w_clave, line_h, limpiar_texto(valor))
        else:
            pdf.set_x(x_start)
            pdf.set_font("Helvetica", "B" if linea.startswith("[") and linea.endswith("]") else "", font_size)
            pdf.multi_cell(max_w, line_h, limpiar_texto(linea))


# Función auxiliar para descargar imágenes de URL para el PDF
def obtener_bytes_imagen(url_img):
    if es_vacio_o_none(url_img):
        return None
    try:
        req = urllib.request.Request(url_img, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return io.BytesIO(response.read())
    except Exception:
        return None


# ==========================================
# MOTOR DE PDF PROFESIONAL MULTI-ESTILO
# ==========================================
def crear_pdf_documento(
    empresa, cliente_nombre, cliente_rif, cliente_dir, moneda, items, 
    subtotal, monto_iva, alicuota_iva, total, num_cotizacion,
    tipo_documento, idioma, validez, incoterm, condiciones_pago, notas, tipo_item,
    bancos_texto_custom=None,
    datos_envio=None
):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    es_ingles = (idioma == "Inglés")
    es_producto = (tipo_item == "Producto")
    es_oc = (tipo_documento == "Orden de Compra")

    # PALETA DE COLORES SEGÚN TIPO DE DOCUMENTO
    if es_oc:
        # Tema Verde Esmeralda / Compras Internacionales
        c_primary = (27, 67, 50)        # #1B4332 (Verde bosque oscuro)
        c_bg_box = (242, 247, 244)       # Fondo suave verde menta
        c_border_box = (200, 222, 210)   # Borde verde suave
    else:
        # Tema Azul Marino / Cotizaciones y Facturas
        c_primary = (26, 54, 93)        # #1A365D (Azul corporativo)
        c_bg_box = (248, 250, 252)       # Fondo suave gris/azul
        c_border_box = (226, 232, 240)   # Borde gris suave

    # TÍTULO DEL DOCUMENTO
    if es_oc:
        titulo_doc = "PURCHASE ORDER (PO)" if es_ingles else "ORDEN DE COMPRA"
    elif tipo_documento == "Proforma Invoice":
        titulo_doc = "PROFORMA INVOICE"
    elif tipo_documento == "Factura Comercial":
        titulo_doc = "COMMERCIAL INVOICE" if es_ingles else "FACTURA COMERCIAL"
    else:
        titulo_doc = "QUOTATION" if es_ingles else "COTIZACION"

    # ETIQUETAS DINÁMICAS (En OC los roles se invierten: Empresa = Comprador, Tercero = Proveedor)
    lbl_num = "PO No.:" if (es_ingles and es_oc) else ("O.C. N°:" if es_oc else ("No.:" if es_ingles else "N°:"))
    lbl_fecha = "Date:" if es_ingles else "Fecha:"
    lbl_validez = "Validity / Lead Time:" if es_ingles else "Validez / Tiempo Entrega:"
    
    if es_oc:
        lbl_emisor = "BUYER / IMPORTER (COMPRADOR)" if es_ingles else "COMPRADOR / SOLICITANTE"
        lbl_cliente = "SUPPLIER / VENDOR (PROVEEDOR)" if es_ingles else "PROVEEDOR / BENEFICIARIO"
    else:
        lbl_emisor = "ISSUER / SUPPLIER" if es_ingles else "EMISOR / PROVEEDOR"
        lbl_cliente = "CLIENT / RECIPIENT" if es_ingles else "CLIENTE / DESTINATARIO"

    lbl_desc = " Description of Goods / Specs" if (es_ingles and es_producto) else (" Description of Services" if es_ingles else (" Descripcion de Mercancia / Especificaciones" if es_producto else " Descripcion del Servicio"))
    lbl_um = "UOM" if es_ingles else "U.M."
    lbl_cant = "Qty" if es_ingles else "Cant."
    lbl_precio = "Unit Price" if es_ingles else "P. Unitario"
    lbl_sub = "Subtotal "
    
    lbl_bancos = "PAYMENT & BANKING DETAILS:" if es_ingles else "DATOS BANCARIOS E INSTRUCCIONES DE PAGO:"
    lbl_cond_pago = "Payment Terms:" if es_ingles else "Condiciones de Pago:"
    lbl_incoterm = "Incoterm & Port:" if es_ingles else "Incoterm y Puerto:"
    lbl_notas = "SPECIAL INSTRUCTIONS / REMARKS:" if es_ingles else "INSTRUCCIONES Y OBSERVACIONES:"
    lbl_firma = "Authorized Signature / Procurement Stamp" if es_ingles else "Firma / Sello de Aprobacion"

    # 1. ENCABEZADO Y LOGO
    logo_bytes = obtener_bytes_imagen(empresa.get("logo_url"))
    sello_bytes = obtener_bytes_imagen(empresa.get("sello_firma_url"))

    if logo_bytes:
        try:
            pdf.image(logo_bytes, x=15, y=14, w=45)
        except Exception:
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(*c_primary)
            pdf.cell(90, 10, limpiar_texto(empresa['nombre']), ln=False)
    else:
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*c_primary)
        pdf.cell(90, 10, limpiar_texto(empresa['nombre']), ln=False)

    pdf.set_xy(105, 12)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*c_primary)
    pdf.cell(90, 7, titulo_doc, align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(105)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(90, 4.5, limpiar_texto(f"{lbl_num} {num_cotizacion}"), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(105)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 4, f"{lbl_fecha} {datetime.now().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")

    if not es_vacio_o_none(validez):
        pdf.set_x(105)
        pdf.cell(90, 4, limpiar_texto(f"{lbl_validez} {validez}"), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    
    pdf.set_draw_color(*c_primary)
    pdf.set_line_width(0.8)
    pdf.line(15, 42, 195, 42)
    pdf.ln(4)

    # 2. BLOQUE EMISOR Y RECEPTOR (COMPRADOR / PROVEEDOR)
    y_bloque = pdf.get_y()
    
    l_emp_nom = calcular_lineas_multiline(pdf, empresa['nombre'], 81, font_name="Helvetica", font_style="B", font_size=9.5)
    l_emp_rif = 1 if not es_vacio_o_none(empresa.get('rif')) else 0
    l_emp_dir = calcular_lineas_multiline(pdf, f"Dir: {empresa.get('direccion', '')}", 81, font_size=8) if not es_vacio_o_none(empresa.get('direccion')) else 0
    h_emisor = 3 + 4 + (l_emp_nom * 4.5) + (l_emp_rif * 4) + (l_emp_dir * 3.8) + 3

    l_cli_nom = calcular_lineas_multiline(pdf, cliente_nombre, 81, font_name="Helvetica", font_style="B", font_size=9.5)
    l_cli_rif = 1 if not es_vacio_o_none(cliente_rif) else 0
    l_cli_dir = calcular_lineas_multiline(pdf, f"Dir: {cliente_dir}", 81, font_size=8) if not es_vacio_o_none(cliente_dir) else 0
    h_cliente = 3 + 4 + (l_cli_nom * 4.5) + (l_cli_rif * 4) + (l_cli_dir * 3.8) + 3

    box_h_cabecera = max(34, h_emisor, h_cliente)

    pdf.set_fill_color(*c_bg_box)
    pdf.set_draw_color(*c_border_box)
    pdf.rect(15, y_bloque, 87, box_h_cabecera, style="FD")
    pdf.rect(108, y_bloque, 87, box_h_cabecera, style="FD")

    # Contenido Izquierdo (Emisor)
    pdf.set_xy(18, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_primary)
    pdf.cell(81, 4, lbl_emisor, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(81, 4.5, limpiar_texto(empresa['nombre']))
    
    if not es_vacio_o_none(empresa.get('rif')):
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(81, 4, limpiar_texto(f"Tax ID / RIF: {empresa['rif']}"), new_x="LMARGIN", new_y="NEXT")
    
    if not es_vacio_o_none(empresa.get('direccion')):
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(81, 3.8, limpiar_texto(f"Dir: {empresa['direccion']}"))

    # Contenido Derecho (Proveedor / Cliente)
    pdf.set_xy(111, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_primary)
    pdf.cell(81, 4, lbl_cliente, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(81, 4.5, limpiar_texto(cliente_nombre))
    
    if not es_vacio_o_none(cliente_rif):
        pdf.set_x(111)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(81, 4, limpiar_texto(f"Tax ID / RIF: {cliente_rif}"), new_x="LMARGIN", new_y="NEXT")
    
    if not es_vacio_o_none(cliente_dir):
        pdf.set_x(111)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(81, 3.8, limpiar_texto(f"Dir: {cliente_dir}"))

    pdf.set_y(y_bloque + box_h_cabecera + 4)

    # 2.1 BLOQUE LOGÍSTICO EXCLUSIVO PARA ÓRDENES DE COMPRA (SHIP TO / ENTREGA)
    if es_oc and datos_envio and any(datos_envio.values()):
        y_envio = pdf.get_y()
        txt_logistica = ""
        if datos_envio.get("lugar_entrega"):
            txt_logistica += f"Lugar de Entrega / Ship To Address: {datos_envio['lugar_entrega']}\n"
        if datos_envio.get("puertos"):
            txt_logistica += f"Puerto de Carga / Destino (POL / POD): {datos_envio['puertos']}\n"
        if datos_envio.get("fecha_despacho"):
            txt_logistica += f"Fecha Estimada Despacho / ETD: {datos_envio['fecha_despacho']}\n"

        if txt_logistica:
            n_lin_envio = calcular_lineas_totales_texto(pdf, txt_logistica, max_w=174, font_size=8.5)
            h_box_envio = max(16, (n_lin_envio * 4.5) + 8)

            pdf.set_fill_color(*c_bg_box)
            pdf.set_draw_color(*c_border_box)
            pdf.rect(15, y_envio, 180, h_box_envio, style="FD")

            pdf.set_xy(18, y_envio + 2.5)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(*c_primary)
            pdf.cell(174, 4, "INSTRUCCIONES DE ENVIO Y LOGISTICA / SHIPPING INSTRUCTIONS:", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.5)

            render_texto_con_dospuntos(pdf, txt_logistica, x_start=18, max_w=174, font_size=8.5, line_h=4.2)
            pdf.set_y(y_envio + h_box_envio + 4)

    # 3. TABLA DE PRODUCTOS / SERVICIOS
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*c_primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(*c_primary)

    if es_producto:
        w_desc, w_um, w_cant, w_prec, w_sub = 75, 20, 15, 32, 38
        pdf.cell(w_desc, 8, lbl_desc, border=1, fill=True)
        pdf.cell(w_um, 8, lbl_um, border=1, fill=True, align="C")
        pdf.cell(w_cant, 8, lbl_cant, border=1, fill=True, align="C")
        pdf.cell(w_prec, 8, lbl_precio, border=1, fill=True, align="R")
        pdf.cell(w_sub, 8, lbl_sub, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
    else:
        w_desc, w_cant, w_prec, w_sub = 95, 20, 30, 35
        pdf.cell(w_desc, 8, lbl_desc, border=1, fill=True)
        pdf.cell(w_cant, 8, lbl_cant, border=1, fill=True, align="C")
        pdf.cell(w_prec, 8, lbl_precio, border=1, fill=True, align="R")
        pdf.cell(w_sub, 8, lbl_sub, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(51, 65, 85)
    pdf.set_draw_color(*c_border_box)
    
    fill = False
    for item in items:
        desc_texto = limpiar_texto(item['descripcion'])
        if es_producto and not es_vacio_o_none(item.get("presentacion")):
            desc_texto += f" [{limpiar_texto(item['presentacion'])}]"
            
        um_texto = limpiar_texto(item.get("uom", "Uds")) if es_producto else ""
        cant_texto = str(item['cantidad'])
        prec_texto = f"{item['precio']:,.2f}"
        sub_texto = f"{item['subtotal']:,.2f} "

        l_desc = calcular_lineas_multiline(pdf, desc_texto, w_desc, font_size=8.5)
        l_um = calcular_lineas_multiline(pdf, um_texto, w_um, font_size=8.5) if es_producto else 1
        l_cant = calcular_lineas_multiline(pdf, cant_texto, w_cant, font_size=8.5)
        l_prec = calcular_lineas_multiline(pdf, prec_texto, w_prec, font_size=8.5)
        l_sub = calcular_lineas_multiline(pdf, sub_texto, w_sub, font_size=8.5)
        
        n_lineas_max = max(l_desc, l_um, l_cant, l_prec, l_sub, 1)
        h_fila = max(8.0, (n_lineas_max * 4.5) + 2.5)

        if pdf.get_y() + h_fila > 275:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(*c_primary)
            pdf.set_text_color(255, 255, 255)
            pdf.set_draw_color(*c_primary)
            if es_producto:
                pdf.cell(w_desc, 8, lbl_desc, border=1, fill=True)
                pdf.cell(w_um, 8, lbl_um, border=1, fill=True, align="C")
                pdf.cell(w_cant, 8, lbl_cant, border=1, fill=True, align="C")
                pdf.cell(w_prec, 8, lbl_precio, border=1, fill=True, align="R")
                pdf.cell(w_sub, 8, lbl_sub, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(w_desc, 8, lbl_desc, border=1, fill=True)
                pdf.cell(w_cant, 8, lbl_cant, border=1, fill=True, align="C")
                pdf.cell(w_prec, 8, lbl_precio, border=1, fill=True, align="R")
                pdf.cell(w_sub, 8, lbl_sub, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(51, 65, 85)
            pdf.set_draw_color(*c_border_box)

        y_inicio = pdf.get_y()
        fill_color = (241, 245, 249) if fill else (255, 255, 255)
        pdf.set_fill_color(*fill_color)

        if es_producto:
            pdf.rect(15, y_inicio, w_desc, h_fila, style="FD")
            pdf.rect(15 + w_desc, y_inicio, w_um, h_fila, style="FD")
            pdf.rect(15 + w_desc + w_um, y_inicio, w_cant, h_fila, style="FD")
            pdf.rect(15 + w_desc + w_um + w_cant, y_inicio, w_prec, h_fila, style="FD")
            pdf.rect(15 + w_desc + w_um + w_cant + w_prec, y_inicio, w_sub, h_fila, style="FD")
        else:
            pdf.rect(15, y_inicio, w_desc, h_fila, style="FD")
            pdf.rect(15 + w_desc, y_inicio, w_cant, h_fila, style="FD")
            pdf.rect(15 + w_desc + w_cant, y_inicio, w_prec, h_fila, style="FD")
            pdf.rect(15 + w_desc + w_cant + w_prec, y_inicio, w_sub, h_fila, style="FD")

        pdf.set_xy(16, y_inicio + 1.2)
        pdf.multi_cell(w_desc - 2, 4.2, desc_texto, border=0, align="L")

        if es_producto:
            pdf.set_xy(15 + w_desc + 1, y_inicio + 1.2)
            pdf.multi_cell(w_um - 2, 4.2, um_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_um + 1, y_inicio + 1.2)
            pdf.multi_cell(w_cant - 2, 4.2, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_um + w_cant + 1, y_inicio + 1.2)
            pdf.multi_cell(w_prec - 2, 4.2, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_desc + w_um + w_cant + w_prec + 1, y_inicio + 1.2)
            pdf.multi_cell(w_sub - 2, 4.2, sub_texto, border=0, align="R")
        else:
            pdf.set_xy(15 + w_desc + 1, y_inicio + 1.2)
            pdf.multi_cell(w_cant - 2, 4.2, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_cant + 1, y_inicio + 1.2)
            pdf.multi_cell(w_prec - 2, 4.2, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_desc + w_cant + w_prec + 1, y_inicio + 1.2)
            pdf.multi_cell(w_sub - 2, 4.2, sub_texto, border=0, align="R")

        pdf.set_y(y_inicio + h_fila)
        fill = not fill

    pdf.ln(5)

    # 4. MÓDULO BANCARIO / TOTALES
    y_seccion4 = pdf.get_y()
    
    if bancos_texto_custom is not None:
        bancos_texto = bancos_texto_custom
    else:
        bancos_raw = empresa.get("datos_bancarios", "")
        cuentas_list = obtener_cuentas_bancarias({"datos_bancarios": bancos_raw})
        bancos_texto = "\n\n".join([f"[{c['alias']}]\n{c['detalles']}" for c in cuentas_list])
    
    box_h_bancos = 32
    if not es_vacio_o_none(bancos_texto):
        total_lineas_bancos = calcular_lineas_totales_texto(pdf, bancos_texto, max_w=96, font_size=8.5)
        box_h_bancos = max(32, (total_lineas_bancos * 4.8) + 10)

        pdf.set_fill_color(*c_bg_box)
        pdf.set_draw_color(*c_border_box)
        pdf.rect(15, y_seccion4, 102, box_h_bancos, style="FD")
        
        pdf.set_xy(18, y_seccion4 + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*c_primary)
        pdf.cell(96, 4, lbl_bancos, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        render_texto_con_dospuntos(pdf, bancos_texto, x_start=18, max_w=96, font_size=8.5, line_h=4.8)

    pdf.set_xy(123, y_seccion4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(71, 85, 105)
    
    pdf.cell(32, 6, "Currency / Moneda:" if es_ingles else "Moneda:", align="L")
    pdf.cell(40, 6, limpiar_texto(moneda), align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(123)
    pdf.cell(32, 6, "Subtotal:", align="L")
    pdf.cell(40, 6, f"{subtotal:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    if monto_iva > 0:
        pdf.set_x(123)
        lbl_tax = f"Tax/VAT ({alicuota_iva:.0f}%):" if es_ingles else f"IVA ({alicuota_iva:.0f}%):"
        pdf.cell(32, 6, lbl_tax, align="L")
        pdf.cell(40, 6, f"{monto_iva:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(123)
    pdf.set_fill_color(*c_primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(32, 8.5, " TOTAL:", fill=True)
    pdf.cell(40, 8.5, f"{total:,.2f} ", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    y_pos_siguiente = max(y_seccion4 + box_h_bancos + 5, pdf.get_y() + 6)
    pdf.set_y(y_pos_siguiente)

    # 5. CONDICIONES COMERCIALES / TÉRMINOS DE COMPRA
    tiene_cond = not es_vacio_o_none(condiciones_pago) or (not es_vacio_o_none(incoterm) and incoterm != "N/A") or not es_vacio_o_none(validez)
    if tiene_cond:
        y_cond = pdf.get_y()
        texto_cond_total = ""
        if not es_vacio_o_none(condiciones_pago): texto_cond_total += f"{lbl_cond_pago} {condiciones_pago}\n"
        if not es_vacio_o_none(incoterm) and incoterm != "N/A": texto_cond_total += f"{lbl_incoterm} {incoterm}\n"
        if not es_vacio_o_none(validez): texto_cond_total += f"{lbl_validez} {validez}\n"

        total_lineas_cond = calcular_lineas_totales_texto(pdf, texto_cond_total, max_w=174, font_size=8.5)
        box_h_cond = max(16, (total_lineas_cond * 4.8) + 8)
        
        pdf.set_fill_color(*c_bg_box)
        pdf.set_draw_color(*c_border_box)
        pdf.rect(15, y_cond, 180, box_h_cond, style="FD")
        
        pdf.set_xy(18, y_cond + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*c_primary)
        lbl_cond_title = "TERMS OF PURCHASE / SALE:" if (es_ingles and es_oc) else ("CONDICIONES DE COMPRA Y PAGO:" if es_oc else ("CONDICIONES COMERCIALES / TERMS OF SALE:" if es_ingles else "CONDICIONES COMERCIALES Y DE PAGO:"))
        pdf.cell(174, 4, lbl_cond_title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        if not es_vacio_o_none(condiciones_pago):
            render_texto_con_dospuntos(pdf, f"{lbl_cond_pago} {condiciones_pago}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if not es_vacio_o_none(incoterm) and incoterm != "N/A":
            render_texto_con_dospuntos(pdf, f"{lbl_incoterm} {incoterm}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if not es_vacio_o_none(validez):
            render_texto_con_dospuntos(pdf, f"{lbl_validez} {validez}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
            
        pdf.set_y(y_cond + box_h_cond + 5)

    # 6. NOTAS Y OBSERVACIONES
    if not es_vacio_o_none(notas):
        y_notas = pdf.get_y()
        total_lineas_notas = calcular_lineas_totales_texto(pdf, notas, max_w=174, font_size=8.5)
        box_h_notas = max(16, (total_lineas_notas * 4.8) + 8)
        
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*c_border_box)
        pdf.rect(15, y_notas, 180, box_h_notas, style="FD")
        
        pdf.set_xy(18, y_notas + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*c_primary)
        pdf.cell(174, 4, lbl_notas, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        render_texto_con_dospuntos(pdf, notas, x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        pdf.set_y(y_notas + box_h_notas + 5)

    # 7. SELLO Y FIRMA
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
st.sidebar.title("📌 Menú Principal")

if "cotiz_edit_data" not in st.session_state:
    st.session_state["cotiz_edit_data"] = None
if "modo_formulario" not in st.session_state:
    st.session_state["modo_formulario"] = "crear"

opcion = st.sidebar.radio("Selecciona un módulo:", [
    "1. Empresas", 
    "2. Directorio (Clientes / Proveedores)", 
    "3. Emitir Documento (Cotizar / O.C.)", 
    "4. Historial de Documentos"
])

with st.sidebar.expander("🔍 Verificación de Conexión"):
    st.write(f"**URL:** `{url}`")
    st.write(f"**Clave activa:** `{key[:10]}...`")

# ------------------------------------------
# MÓDULO 1: EMPRESAS
# ------------------------------------------
if opcion == "1. Empresas":
    st.title("🏢 Gestión de Empresas (Emisoras / Compradoras)")
    st.write("Registra o edita los datos de la empresa emisora, sus cuentas bancarias y sus sellos/firmas.")

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
            st.info("No hay empresas registradas aún.")
        else:
            nombres = [e["nombre"] for e in empresas]
            seleccion = st.selectbox("Selecciona la empresa a editar:", nombres)
            empresa_sel = next(e for e in empresas if e["nombre"] == seleccion)

    st.divider()

    nombre_val = empresa_sel["nombre"] if empresa_sel else ""
    direccion_val = empresa_sel["direccion"] if empresa_sel else ""
    rif_val = empresa_sel["rif"] if empresa_sel else ""
    cuentas_existentes = obtener_cuentas_bancarias(empresa_sel)

    with st.form("form_empresa", clear_on_submit=False):
        nombre = st.text_input("Nombre de la Empresa *", value=nombre_val)
        rif = st.text_input("Número de RIF / Tax ID *", value=rif_val)
        direccion = st.text_area("Dirección Fiscal (Escribe 'None' u 'Omitir' para no mostrar en PDF)", value=direccion_val)
        
        st.subheader("🏦 Cuentas Bancarias Registradas")
        st.caption("Agrega una o varias cuentas bancarias en la tabla. Luego en el cotizador elegirás cuál(es) incluir en cada documento.")
        
        if not cuentas_existentes:
            df_cuentas_init = pd.DataFrame([
                {"Alias de Cuenta": "Banesco Panamá (USD)", "Detalles": "Banco: Banesco Panamá\nCuenta: 0134-XXXX-XX\nSWIFT: XXXXX"},
                {"Alias de Cuenta": "Zelle (USD)", "Detalles": "Correo: pagos@miempresa.com\nTitular: Mi Empresa LLC"}
            ])
        else:
            df_cuentas_init = pd.DataFrame([
                {"Alias de Cuenta": c.get("alias", "Cuenta"), "Detalles": c.get("detalles", "")}
                for c in cuentas_existentes
            ])

        df_cuentas_edit = st.data_editor(
            df_cuentas_init,
            num_rows="dynamic",
            column_config={
                "Alias de Cuenta": st.column_config.TextColumn("Alias / Nombre Corto *", help="Ej: Banesco USD, Zelle, Mercantil BS", width="medium"),
                "Detalles": st.column_config.TextColumn("Datos de la Cuenta (Banco, Nro, SWIFT, Titular)", help="Escribe los datos de la cuenta usando dos puntos (:)", width="large")
            },
            use_container_width=True,
            key="editor_cuentas_empresa"
        )

        st.subheader("🖼️ Imágenes Corporativas")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Logotipo (Fondo Blanco)**")
            if empresa_sel and empresa_sel.get("logo_url"):
                st.image(empresa_sel["logo_url"], width=150, caption="Logo Actual")
            logo_file = st.file_uploader("Subir Logo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="logo")

        with col2:
            st.markdown("**Sello Húmedo y Firma**")
            if empresa_sel and empresa_sel.get("sello_firma_url"):
                st.image(empresa_sel["sello_firma_url"], width=150, caption="Sello Actual")
            sello_file = st.file_uploader("Subir Sello/Firma (PNG/JPG)", type=["png", "jpg", "jpeg"], key="sello")

        guardar = st.form_submit_button("💾 Guardar Empresa", use_container_width=True)

    if guardar:
        if not nombre or not rif:
            st.error("El Nombre y el RIF son obligatorios.")
        else:
            logo_url = empresa_sel.get("logo_url") if empresa_sel else None
            sello_url = empresa_sel.get("sello_firma_url") if empresa_sel else None

            if logo_file:
                ext = logo_file.name.split(".")[-1]
                path_logo = f"logos/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("archivos-cotizador").upload(
                    path=path_logo, file=logo_file.getvalue(), 
                    file_options={"content-type": logo_file.type, "upsert": "true"}
                )
                logo_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_logo)

            if sello_file:
                ext = sello_file.name.split(".")[-1]
                path_sello = f"sellos/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("archivos-cotizador").upload(
                    path=path_sello, file=sello_file.getvalue(), 
                    file_options={"content-type": sello_file.type, "upsert": "true"}
                )
                sello_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_sello)

            cuentas_list = []
            for _, r in df_cuentas_edit.iterrows():
                alias_val = str(r.get("Alias de Cuenta", "")).strip()
                det_val = str(r.get("Detalles", "")).strip()
                if alias_val and det_val and not es_vacio_o_none(alias_val):
                    cuentas_list.append({"alias": alias_val, "detalles": det_val})

            datos_bancarios_json = json.dumps(cuentas_list, ensure_ascii=False)

            datos_empresa = {
                "nombre": nombre, "rif": rif, "direccion": direccion,
                "datos_bancarios": datos_bancarios_json, "logo_url": logo_url, "sello_firma_url": sello_url
            }

            if empresa_sel:
                supabase.table("empresas").update(datos_empresa).eq("id", empresa_sel["id"]).execute()
                st.success(f"¡Empresa '{nombre}' actualizada!")
            else:
                supabase.table("empresas").insert(datos_empresa).execute()
                st.success(f"¡Empresa '{nombre}' registrada!")
            st.rerun()

# ------------------------------------------
# MÓDULO 2: CLIENTES / PROVEEDORES
# ------------------------------------------
elif opcion == "2. Directorio (Clientes / Proveedores)":
    st.title("📇 Directorio de Terceros (Clientes y Proveedores)")
    st.write("Administra tus contactos comerciales para cargar sus datos al emitir documentos.")

    try:
        res_cli = supabase.table("clientes").select("*").order("nombre").execute()
        clientes_db = res_cli.data
    except Exception:
        clientes_db = []

    modo_cli = st.radio("Acción:", ["Registrar Nuevo Contacto", "Editar Contacto Existente"], horizontal=True)

    cli_sel = None
    if modo_cli == "Editar Contacto Existente":
        if not clientes_db:
            st.info("No hay contactos guardados aún.")
        else:
            nombres_cli = [c["nombre"] for c in clientes_db]
            sel_nombre = st.selectbox("Selecciona contacto a editar:", nombres_cli)
            cli_sel = next(c for c in clientes_db if c["nombre"] == sel_nombre)

    st.divider()

    with st.form("form_cliente"):
        cli_nombre_val = cli_sel["nombre"] if cli_sel else ""
        cli_rif_val = cli_sel["rif"] if cli_sel else ""
        cli_dir_val = cli_sel["direccion"] if cli_sel else ""

        nombre_c = st.text_input("Nombre / Razón Social *", value=cli_nombre_val, help="Nombre del Cliente o Proveedor")
        rif_c = st.text_input("RIF / Tax ID / EIN", value=cli_rif_val)
        dir_c = st.text_area("Dirección / País / Ciudad", value=cli_dir_val)

        guardar_cli = st.form_submit_button("💾 Guardar Contacto", use_container_width=True)

    if guardar_cli:
        if not nombre_c:
            st.error("El nombre es obligatorio.")
        else:
            payload_cli = {"nombre": nombre_c, "rif": rif_c, "direccion": dir_c}
            if cli_sel:
                supabase.table("clientes").update(payload_cli).eq("id", cli_sel["id"]).execute()
                st.success("¡Contacto actualizado!")
            else:
                supabase.table("clientes").insert(payload_cli).execute()
                st.success("¡Contacto registrado con éxito!")
            st.rerun()

    if clientes_db:
        st.subheader("📋 Lista de Contactos Guardados")
        st.dataframe(pd.DataFrame(clientes_db)[["nombre", "rif", "direccion"]], use_container_width=True)

# ------------------------------------------
# MÓDULO 3: EMITIR DOCUMENTO (COTIZAR / O.C.)
# ------------------------------------------
elif opcion == "3. Emitir Documento (Cotizar / O.C.)":
    datos_cargados = st.session_state.get("cotiz_edit_data")
    modo_form = st.session_state.get("modo_formulario", "crear")

    if modo_form == "editar":
        st.title("✏️ Editando Documento")
        st.info(f"Modificando el documento: **{datos_cargados.get('numero_cotizacion')}**")
    elif modo_form == "duplicar":
        st.title("📋 Duplicando Documento")
        st.info(f"Generando un nuevo documento basado en la referencia: **{datos_cargados.get('numero_cotizacion')}**")
    else:
        st.title("📝 Generar Documento Comercial")

    try:
        res_emp = supabase.table("empresas").select("*").execute()
        empresas = res_emp.data
        res_cli = supabase.table("clientes").select("*").order("nombre").execute()
        clientes_db = res_cli.data
    except Exception:
        empresas = []
        clientes_db = []

    if not empresas:
        st.warning("⚠️ Primero debes registrar al menos una Empresa en el Módulo 1.")
        st.stop()

    nombres_emp = [e["nombre"] for e in empresas]
    
    idx_emp = 0
    if datos_cargados and "empresa_id" in datos_cargados:
        for idx, e in enumerate(empresas):
            if e["id"] == datos_cargados["empresa_id"]:
                idx_emp = idx
                break

    st.subheader("⚙️ Configuración del Documento")
    col_t0, col_t1, col_t2, col_t3 = st.columns(4)
    
    tipo_item_val = datos_cargados.get("tipo_item", "Producto") if datos_cargados else "Producto"
    doc_default = datos_cargados.get("tipo_documento", "Cotización") if datos_cargados else "Cotización"
    id_default = datos_cargados.get("idioma", "Español") if datos_cargados else "Español"
    mon_default = datos_cargados.get("moneda", "USD ($)") if datos_cargados else "USD ($)"

    opciones_docs = ["Cotización", "Proforma Invoice", "Factura Comercial", "Orden de Compra"]

    with col_t0:
        tipo_item = st.radio("¿Qué vas a procesar? *", ["Producto", "Servicio"], index=0 if tipo_item_val == "Producto" else 1, horizontal=True)
    with col_t1:
        tipo_documento = st.selectbox("Tipo de Documento *", opciones_docs, index=opciones_docs.index(doc_default) if doc_default in opciones_docs else 0)
    with col_t2:
        idioma = st.selectbox("Idioma *", ["Español", "Inglés"], index=0 if id_default == "Español" else 1)
    with col_t3:
        moneda = st.selectbox("Moneda *", ["USD ($)", "EUR (€)", "RMB (¥)"], index=["USD ($)", "EUR (€)", "RMB (¥)"].index(mon_default) if mon_default in ["USD ($)", "EUR (€)", "RMB (¥)"] else 0)

    es_orden_compra = (tipo_documento == "Orden de Compra")

    st.divider()

    # Empresa emisora / Compradora
    lbl_emp_select = "Empresa Compradora (Buyer) *" if es_orden_compra else "Empresa Emisora *"
    emp_seleccionada = st.selectbox(lbl_emp_select, nombres_emp, index=idx_emp)
    empresa = next(e for e in empresas if e["nombre"] == emp_seleccionada)
    cuentas_disponibles = obtener_cuentas_bancarias(empresa)

    st.divider()

    # Datos del Tercero (Cliente o Proveedor)
    lbl_seccion_tercero = "🏭 Datos del Proveedor / Fabricante (Vendor/Supplier)" if es_orden_compra else "👤 Datos del Cliente (Client/Recipient)"
    st.subheader(lbl_seccion_tercero)
    
    opciones_clientes = ["➕ Escribir manualmente / Nuevo"] + [c["nombre"] for c in clientes_db]
    cliente_sel_box = st.selectbox(f"Seleccionar del Directorio (Opcional):", opciones_clientes)

    cli_nombre_def = datos_cargados.get("cliente_nombre", "") if datos_cargados else ""
    cli_rif_def = datos_cargados.get("cliente_rif", "") if datos_cargados else ""
    cli_dir_def = datos_cargados.get("cliente_direccion", "") if datos_cargados else ""

    if cliente_sel_box != "➕ Escribir manualmente / Nuevo":
        c_obj = next(c for c in clientes_db if c["nombre"] == cliente_sel_box)
        cli_nombre_def = c_obj["nombre"]
        cli_rif_def = c_obj["rif"]
        cli_dir_def = c_obj["direccion"]

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        lbl_nombre_input = "Nombre / Razón Social del Proveedor *" if es_orden_compra else "Nombre / Razón Social del Cliente *"
        cliente_nombre = st.text_input(lbl_nombre_input, value=cli_nombre_def)
        cliente_rif = st.text_input("RIF / Tax ID / Tax Number", value=cli_rif_def)
        cliente_dir = st.text_area("Dirección del Proveedor / Cliente", value=cli_dir_def, height=80)
        
        guardar_en_bd = st.checkbox("💾 Guardar automáticamente en mi directorio", value=False)

    with col_c2:
        st.subheader("📋 Detalle del Documento")
        prefijo_def = "OC-" if es_orden_compra else "COT-"
        num_def = f"{prefijo_def}{datetime.now().strftime('%Y%m%d%H%M')}"
        if datos_cargados:
            if modo_form == "editar":
                num_def = datos_cargados.get("numero_cotizacion", num_def)
            elif modo_form == "duplicar":
                num_def = f"{prefijo_def}{datetime.now().strftime('%Y%m%d%H%M')}"

        num_cotizacion = st.text_input("Número de Documento *", value=num_def)
        lbl_validez_input = "Tiempo de Entrega / Validez" if es_orden_compra else "Tiempo de Validez"
        val_default_text = "30 Días" if es_orden_compra else "15 Días"
        validez = st.text_input(lbl_validez_input, value=datos_cargados.get("validez", val_default_text) if datos_cargados else val_default_text)
        
        incoterm = st.selectbox(
            "Incoterm (Comercio Internacional)", 
            ["N/A", "FOB - Free on Board", "EXW - Ex Works", "FCA - Free Carrier", "CIF - Cost, Insurance & Freight", "CFR - Cost and Freight", "DDP - Delivered Duty Paid", "DAP - Delivered at Place", "CIP - Carriage and Insurance Paid to", "CPT - Carriage Paid To", "DPU - Delivered at Place Unloaded", "FAS - Free Alongside Ship"]
        )
        cond_default = "30% Anticipo, 70% contra BL" if es_orden_compra else "100% Anticipado"
        condiciones_pago = st.text_input("Condiciones de Pago", value=datos_cargados.get("condiciones_pago", cond_default) if datos_cargados else cond_default)

    # 3.1 CAMPOS ESPECIALES PARA ORDEN DE COMPRA INTERNACIONAL
    datos_envio_dict = {}
    if es_orden_compra:
        st.subheader("🚢 Datos de Envío y Logística Internacional (Ship To / Destination)")
        with st.expander("📍 Abrir detalles de Entrega, Puertos y Fechas", expanded=True):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                lugar_entrega = st.text_area(
                    "Dirección de Entrega / Ship To (Casillero / Forwarder / Almacén):",
                    value="Ej: Almacén Freight Forwarder Miami / ShenZhen / Aduana Local",
                    height=70
                )
            with col_e2:
                puertos = st.text_input("Puerto de Embarque y Destino (POL / POD):", value="Ej: Ningbo Port / Miami / Puerto Cabello")
                fecha_despacho = st.text_input("Fecha Estimada de Despacho (ETD / Lead Time):", value="Ej: 15-20 días tras confirmar anticipo")
            datos_envio_dict = {
                "lugar_entrega": lugar_entrega if not es_vacio_o_none(lugar_entrega) else "",
                "puertos": puertos if not es_vacio_o_none(puertos) else "",
                "fecha_despacho": fecha_despacho if not es_vacio_o_none(fecha_despacho) else ""
            }

    # Cuentas bancarias
    bancos_texto_para_pdf = ""
    if cuentas_disponibles and not es_orden_compra:
        st.subheader("🏦 Cuentas Bancarias a Mostrar en el PDF")
        opciones_alias = [c["alias"] for c in cuentas_disponibles]
        cuentas_seleccionadas = st.multiselect(
            "Selecciona la(s) cuenta(s) a incluir:",
            options=opciones_alias,
            default=opciones_alias,
            help="Desmarca todas si no deseas mostrar el recuadro bancario."
        )
        bloques_bancarios = []
        for c in cuentas_disponibles:
            if c["alias"] in cuentas_seleccionadas:
                bloques_bancarios.append(f"[{c['alias']}]\n{c['detalles']}")
        bancos_texto_para_pdf = "\n\n".join(bloques_bancarios)

    st.subheader("📦 Lista de Ítems / Precios")
    lista_uoms = ["Unidades (Uds)", "Par", "m²", "m³ (CBM)", "Paquete (Pkt)", "Bulto", "Caja (CTN)", "Pieza (Pza)", "Set / Juego", "Metro (m)", "Kg", "Tonelada (TN)", "Litro (L)"]

    if datos_cargados and "items" in datos_cargados:
        items_cargados = []
        for it in datos_cargados["items"]:
            if tipo_item == "Producto":
                items_cargados.append({
                    "Descripción": it.get("descripcion", ""),
                    "Presentación / Empaque / SKU": it.get("presentacion", ""),
                    "Unidad de Medida": it.get("uom", "Unidades (Uds)"),
                    "Cantidad": it.get("cantidad", 1),
                    "Precio Unitario": it.get("precio", 0.0)
                })
            else:
                items_cargados.append({
                    "Descripción": it.get("descripcion", ""),
                    "Cantidad / Horas": it.get("cantidad", 1),
                    "Precio Unitario": it.get("precio", 0.0)
                })
        df_inicial = pd.DataFrame(items_cargados)
    else:
        if tipo_item == "Producto":
            df_inicial = pd.DataFrame([{
                "Descripción": "Ej: Repuesto / Materia Prima / Producto Modelo A",
                "Presentación / Empaque / SKU": "Ej: Caja master x 50 pcs (HS: 8409.91)",
                "Unidad de Medida": "Unidades (Uds)",
                "Cantidad": 100,
                "Precio Unitario": 12.50
            }])
        else:
            df_inicial = pd.DataFrame([{
                "Descripción": "Ej: Servicio Técnico Especializado",
                "Cantidad / Horas": 1,
                "Precio Unitario": 200.0
            }])

    if tipo_item == "Producto":
        df_editado = st.data_editor(
            df_inicial,
            num_rows="dynamic",
            column_config={
                "Unidad de Medida": st.column_config.SelectboxColumn("Unidad de Medida", options=lista_uoms, default="Unidades (Uds)"),
                "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1, default=1),
                "Precio Unitario": st.column_config.NumberColumn("Precio Unitario", min_value=0.0, format="%.2f", default=0.0),
            },
            use_container_width=True
        )
        df_editado["Subtotal"] = df_editado["Cantidad"] * df_editado["Precio Unitario"]
    else:
        df_editado = st.data_editor(
            df_inicial,
            num_rows="dynamic",
            column_config={
                "Cantidad / Horas": st.column_config.NumberColumn("Cantidad / Horas", min_value=1, step=1, default=1),
                "Precio Unitario": st.column_config.NumberColumn("Precio Unitario", min_value=0.0, format="%.2f", default=0.0),
            },
            use_container_width=True
        )
        df_editado["Subtotal"] = df_editado["Cantidad / Horas"] * df_editado["Precio Unitario"]

    subtotal_cotizacion = df_editado["Subtotal"].sum()

    st.divider()
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        aplica_iva_def = True if (datos_cargados and datos_cargados.get("monto_iva", 0) > 0) else False
        aplica_iva = st.checkbox("¿Aplica Impuestos / IVA?", value=aplica_iva_def)
        alicuota_def = datos_cargados.get("alicuota_iva", 16.0) if datos_cargados else 16.0
        alicuota_iva = st.number_input("Alícuota de Impuesto (%)", min_value=0.0, max_value=100.0, value=alicuota_def, step=1.0) if aplica_iva else 0.0
        monto_iva = subtotal_cotizacion * (alicuota_iva / 100.0) if aplica_iva else 0.0
        total_cotizacion = subtotal_cotizacion + monto_iva

        st.markdown(f"**Subtotal:** `{moneda} {subtotal_cotizacion:,.2f}`")
        if aplica_iva:
            st.markdown(f"**Impuesto ({alicuota_iva:.0f}%):** `{moneda} {monto_iva:,.2f}`")
        st.markdown(f"### 💰 **Total:** `{moneda} {total_cotizacion:,.2f}`")

    with col_i2:
        notas_def = datos_cargados.get("notas", "") if datos_cargados else ""
        notas = st.text_area("Notas / Especificaciones de Compra / Observaciones", value=notas_def, help="Escribe 'None' u 'Omitir' para no incluir este bloque")

    st.divider()

    txt_boton = "💾 Actualizar Documento" if modo_form == "editar" else f"📄 Generar y Guardar {tipo_documento}"
    
    if st.button(txt_boton, use_container_width=True, type="primary"):
        if not cliente_nombre or total_cotizacion <= 0:
            st.error("Por favor ingresa el nombre de la contraparte y al menos un ítem con valor.")
        else:
            if guardar_en_bd and cliente_sel_box == "➕ Escribir manualmente / Nuevo":
                try:
                    supabase.table("clientes").insert({
                        "nombre": cliente_nombre, "rif": cliente_rif, "direccion": cliente_dir
                    }).execute()
                except Exception:
                    pass

            items_list = []
            for _, row in df_editado.iterrows():
                if tipo_item == "Producto":
                    items_list.append({
                        "descripcion": row["Descripción"],
                        "presentacion": row.get("Presentación / Empaque / SKU", ""),
                        "uom": row.get("Unidad de Medida", "Uds"),
                        "cantidad": int(row["Cantidad"]),
                        "precio": float(row["Precio Unitario"]),
                        "subtotal": float(row["Subtotal"])
                    })
                else:
                    items_list.append({
                        "descripcion": row["Descripción"],
                        "cantidad": int(row["Cantidad / Horas"]),
                        "precio": float(row["Precio Unitario"]),
                        "subtotal": float(row["Subtotal"])
                    })
                
            pdf_bytes = crear_pdf_documento(
                empresa, cliente_nombre, cliente_rif, cliente_dir, moneda,
                items_list, subtotal_cotizacion, monto_iva, alicuota_iva, 
                total_cotizacion, num_cotizacion, tipo_documento, idioma, 
                validez, incoterm, condiciones_pago, notas, tipo_item,
                bancos_texto_custom=bancos_texto_para_pdf,
                datos_envio=datos_envio_dict
            )
            
            path_pdf = f"cotizaciones/{num_cotizacion}_{uuid.uuid4()}.pdf"
            supabase.storage.from_("archivos-cotizador").upload(
                path=path_pdf, file=pdf_bytes, 
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
                "pdf_url": pdf_url,
                "tipo_item": tipo_item
            }
            
            try:
                if modo_form == "editar" and datos_cargados:
                    supabase.table("cotizaciones").update(datos_cotizacion).eq("id", datos_cargados["id"]).execute()
                else:
                    supabase.table("cotizaciones").insert(datos_cotizacion).execute()
                st.success(f"🎉 ¡{tipo_documento} guardado con éxito!")
            except Exception as e_db:
                if "tipo_item" in str(e_db):
                    try:
                        datos_cotizacion_bak = datos_cotizacion.copy()
                        del datos_cotizacion_bak["tipo_item"]
                        if modo_form == "editar" and datos_cargados:
                            supabase.table("cotizaciones").update(datos_cotizacion_bak).eq("id", datos_cargados["id"]).execute()
                        else:
                            supabase.table("cotizaciones").insert(datos_cotizacion_bak).execute()
                        st.success(f"🎉 ¡{tipo_documento} guardado con éxito!")
                    except Exception as e_db2:
                        st.error(f"🚨 Error al guardar en Base de Datos: {e_db2}")
                else:
                    st.error(f"🚨 Error al guardar en Base de Datos: {e_db}")

            # Limpiar estado
            st.session_state["cotiz_edit_data"] = None
            st.session_state["modo_formulario"] = "crear"

            st.download_button(
                label=f"⬇️ Descargar {tipo_documento} (PDF)",
                data=pdf_bytes,
                file_name=f"{num_cotizacion}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    if modo_form in ["editar", "duplicar"]:
        if st.button("❌ Cancelar edición/duplicación"):
            st.session_state["cotiz_edit_data"] = None
            st.session_state["modo_formulario"] = "crear"
            st.rerun()

# ------------------------------------------
# MÓDULO 4: HISTORIAL DE DOCUMENTOS
# ------------------------------------------
elif opcion == "4. Historial de Documentos":
    st.title("📚 Historial de Documentos Emitidos")
    st.write("Consulta, edita, duplica o elimina Cotizaciones, Facturas y Órdenes de Compra.")

    try:
        res_cot = supabase.table("cotizaciones").select("*").order("created_at", desc=True).execute()
        cotizaciones = res_cot.data

        res_emp = supabase.table("empresas").select("*").execute()
        empresas_dict = {e["id"]: e["nombre"] for e in res_emp.data}
    except Exception as e:
        st.error("🚨 Error al consultar el historial:")
        st.write(e)
        st.stop()

    if not cotizaciones:
        st.info("ℹ️ Aún no se han emitido documentos.")
    else:
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            busqueda = st.text_input("🔍 Buscar por nombre o número:", placeholder="Ej: Proveedor Asia, OC-2026, COT...")
        with col_f2:
            tipo_filtro = st.selectbox("Filtrar por Tipo:", ["Todos", "Cotización", "Proforma Invoice", "Factura Comercial", "Orden de Compra"])

        cotizaciones_filtradas = cotizaciones
        if busqueda:
            b_low = busqueda.lower()
            cotizaciones_filtradas = [
                q for q in cotizaciones_filtradas 
                if b_low in str(q.get("cliente_nombre", "")).lower() or b_low in str(q.get("numero_cotizacion", "")).lower()
            ]
        if tipo_filtro != "Todos":
            cotizaciones_filtradas = [q for q in cotizaciones_filtradas if q.get("tipo_documento") == tipo_filtro]

        st.caption(f"Mostrando **{len(cotizaciones_filtradas)}** de **{len(cotizaciones)}** documentos.")
        st.divider()

        for q in cotizaciones_filtradas:
            emp_nom = empresas_dict.get(q.get("empresa_id"), "Empresa")
            fecha_str = str(q.get("created_at", ""))[:10]
            doc_tipo_item = q.get("tipo_documento", "Cotización")
            
            icono_doc = "🛒" if doc_tipo_item == "Orden de Compra" else "📄"
            titulo_card = f"{icono_doc} {q.get('numero_cotizacion', 'DOC')} | {q.get('cliente_nombre')} | {q.get('moneda', '')} {q.get('total', 0):,.2f}"
            
            with st.expander(titulo_card):
                col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
                
                with col_d1:
                    st.markdown(f"**Tipo:** `{doc_tipo_item}` ({q.get('tipo_item', 'Producto')})")
                    st.write(f"**Empresa:** {emp_nom}")
                    lbl_contraparte = "Proveedor:" if doc_tipo_item == "Orden de Compra" else "Cliente:"
                    st.write(f"**{lbl_contraparte}** {q.get('cliente_nombre')}")
                    
                with col_d2:
                    st.write(f"**Fecha:** {fecha_str}")
                    st.write(f"**Idioma:** {q.get('idioma', 'Español')}")
                    st.write(f"**Validez / Lead Time:** {q.get('validez', 'N/A')}")

                with col_d3:
                    st.markdown(f"### **Total:**\n`{q.get('moneda', '')} {q.get('total', 0):,.2f}`")
                    if q.get("pdf_url"):
                        st.link_button("🌐 Ver PDF", q["pdf_url"], use_container_width=True)

                if q.get("items"):
                    st.markdown("**📦 Desglose de Ítems:**")
                    st.dataframe(pd.DataFrame(q["items"]), use_container_width=True, hide_index=True)

                st.divider()
                
                col_b1, col_b2, col_b3 = st.columns(3)
                with col_b1:
                    if st.button("✏️ Editar Documento", key=f"edit_{q['id']}", use_container_width=True):
                        st.session_state["cotiz_edit_data"] = q
                        st.session_state["modo_formulario"] = "editar"
                        st.info("Cargando datos... ve a la pestaña '3. Emitir Documento' en el menú.")
                        st.rerun()

                with col_b2:
                    if st.button("📋 Duplicar", key=f"dup_{q['id']}", use_container_width=True):
                        st.session_state["cotiz_edit_data"] = q
                        st.session_state["modo_formulario"] = "duplicar"
                        st.info("Duplicando datos... ve a la pestaña '3. Emitir Documento' en el menú.")
                        st.rerun()

                with col_b3:
                    if st.button("🗑️ Eliminar", key=f"del_{q['id']}", type="secondary", use_container_width=True):
                        try:
                            supabase.table("cotizaciones").delete().eq("id", q["id"]).execute()
                            st.success(f"Documento {q['numero_cotizacion']} eliminado.")
                            st.rerun()
                        except Exception as e_del:
                            st.error(f"Error al eliminar: {e_del}")
