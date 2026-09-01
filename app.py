import streamlit as st
from supabase import create_client, Client
import uuid
import pandas as pd
from fpdf import FPDF
import io
import urllib.request
from datetime import datetime, date
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


# Lista de Entidades Predefinidas para Transferencias
ENTIDADES_PREDEFINIDAS = [
    "United Hardware Corp",
    "Convenio RMB Alina",
    "Sistema Simkin",
    "HYDE suelen"
]


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


# Función para extraer URLs de comprobantes (soporta texto simple o listas JSON)
def obtener_urls_comprobantes(raw):
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
        return [raw]
    return []


# Función para limpiar caracteres especiales incompatibles con PDF
def limpiar_texto(texto):
    if es_vacio_o_none(texto):
        return ""
    texto = str(texto).replace("\r\n", "\n").replace("\r", "\n")
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


# Helper para calcular líneas de un texto envuelto en PDF
def calcular_lineas_multiline(pdf, texto, ancho, font_name="Helvetica", font_style="", font_size=8.5):
    if es_vacio_o_none(texto):
        return 1
    pdf.set_font(font_name, font_style, font_size)
    ancho_util = max(5.0, ancho - 4.5)
    texto_norm = str(texto).replace("\r\n", "\n").replace("\r", "\n")
    lineas_totales = 0
    
    for parrafo in texto_norm.split("\n"):
        parrafo_limpio = parrafo.strip()
        if not parrafo_limpio:
            lineas_totales += 1
            continue
            
        palabras = parrafo_limpio.split(" ")
        linea_actual = ""
        for w in palabras:
            if not w:
                continue
            w_limpio = limpiar_texto(w)
            test_line = (linea_actual + " " + w_limpio).strip()
            
            if pdf.get_string_width(test_line) <= ancho_util:
                linea_actual = test_line
            else:
                if linea_actual:
                    lineas_totales += 1
                w_w = pdf.get_string_width(w_limpio)
                if w_w > ancho_util:
                    lineas_totales += max(1, int(w_w / ancho_util))
                    linea_actual = ""
                else:
                    linea_actual = w_limpio
        if linea_actual:
            lineas_totales += 1
            
    return max(1, lineas_totales)


# Helper para calcular líneas impresas por render_texto_con_dospuntos
def calcular_lineas_totales_texto(pdf, texto, max_w, font_size=8.5):
    if es_vacio_o_none(texto):
        return 0
    lineas_count = 0
    texto_norm = str(texto).replace("\r\n", "\n").replace("\r", "\n")
    for linea in texto_norm.split("\n"):
        linea = linea.strip()
        if not linea or es_vacio_o_none(linea):
            continue
        if ":" in linea:
            partes = linea.split(":", 1)
            clave = partes[0].strip() + ":"
            valor = " " + partes[1].strip()
            pdf.set_font("Helvetica", "B", font_size)
            w_clave = pdf.get_string_width(limpiar_texto(clave)) + 2.0
            if w_clave > (max_w - 10):
                lineas_count += calcular_lineas_multiline(pdf, linea, max_w, font_size=font_size)
            else:
                lineas_count += calcular_lineas_multiline(pdf, valor, max_w - w_clave, font_size=font_size)
        else:
            font_style = "B" if (linea.startswith("[") and linea.endswith("]")) else ""
            lineas_count += calcular_lineas_multiline(pdf, linea, max_w, font_style=font_style, font_size=font_size)
    return lineas_count


# Imprimir bloques con clave en negrita antes de ':'
def render_texto_con_dospuntos(pdf, texto, x_start, max_w, font_size=8.5, line_h=4.5):
    if es_vacio_o_none(texto):
        return
    texto_norm = str(texto).replace("\r\n", "\n").replace("\r", "\n")
    for linea in texto_norm.split("\n"):
        linea = linea.strip()
        if not linea or es_vacio_o_none(linea):
            continue
        if ":" in linea:
            partes = linea.split(":", 1)
            clave = partes[0].strip() + ":"
            valor = " " + partes[1].strip()
            
            pdf.set_x(x_start)
            pdf.set_font("Helvetica", "B", font_size)
            w_clave = pdf.get_string_width(limpiar_texto(clave)) + 2.0
            
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


# Descargar imágenes remotas para el PDF
def obtener_bytes_imagen(url_img):
    if es_vacio_o_none(url_img):
        return None
    try:
        req = urllib.request.Request(url_img, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return io.BytesIO(response.read())
    except Exception:
        return None


# =========================================================================
# MOTOR 1: DISEÑADOR EXCLUSIVO PARA ÓRDENES DE COMPRA (PURCHASE ORDERS)
# =========================================================================
def crear_pdf_orden_compra(
    empresa, proveedor_nombre, proveedor_rif, proveedor_dir, moneda, items, 
    subtotal, monto_iva, alicuota_iva, total, num_doc,
    idioma, validez, incoterm, condiciones_pago, notas, tipo_item,
    datos_envio=None
):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    es_ingles = (idioma == "Inglés")
    es_producto = (tipo_item == "Producto")

    c_dark = (15, 23, 42)
    c_emerald = (4, 120, 87)
    c_line = (203, 213, 225)
    c_text_mut = (100, 116, 139)

    logo_bytes = obtener_bytes_imagen(empresa.get("logo_url"))
    sello_bytes = obtener_bytes_imagen(empresa.get("sello_firma_url"))

    # 1. Encabezado
    if logo_bytes:
        try:
            pdf.image(logo_bytes, x=15, y=14, w=45)
        except Exception:
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(*c_dark)
            pdf.cell(85, 8, limpiar_texto(empresa['nombre']), ln=False)
    else:
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*c_dark)
        pdf.cell(85, 8, limpiar_texto(empresa['nombre']), ln=False)

    pdf.set_xy(105, 12)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*c_emerald)
    titulo_po = "PURCHASE ORDER" if es_ingles else "ORDEN DE COMPRA"
    pdf.cell(90, 7, titulo_po, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(105)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*c_dark)
    lbl_po_no = "PO NO.:" if es_ingles else "O.C. N°:"
    pdf.cell(90, 5, f"{lbl_po_no} {limpiar_texto(num_doc)}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(105)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*c_text_mut)
    lbl_fecha = "DATE:" if es_ingles else "FECHA:"
    pdf.cell(90, 4, f"{lbl_fecha} {datetime.now().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(38)
    pdf.set_draw_color(*c_dark)
    pdf.set_line_width(0.6)
    pdf.line(15, 38, 195, 38)
    pdf.ln(4)

    # 2. Partes
    y_partes = pdf.get_y()

    pdf.set_xy(15, y_partes)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_emerald)
    lbl_buyer = "1. BUYER / IMPORTER (COMPRADOR):" if es_ingles else "1. COMPRADOR / EMISOR:"
    pdf.cell(85, 4.5, lbl_buyer, new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*c_dark)
    pdf.multi_cell(85, 4.5, limpiar_texto(empresa['nombre']))

    if not es_vacio_o_none(empresa.get('rif')):
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*c_text_mut)
        pdf.cell(85, 4, f"Tax ID / RIF: {limpiar_texto(empresa['rif'])}", new_x="LMARGIN", new_y="NEXT")

    if not es_vacio_o_none(empresa.get('direccion')):
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(85, 3.8, f"Address: {limpiar_texto(empresa['direccion'])}")

    y_pos_izq = pdf.get_y()

    pdf.set_xy(108, y_partes)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_emerald)
    lbl_vendor = "2. VENDOR / SUPPLIER (PROVEEDOR):" if es_ingles else "2. PROVEEDOR / BENEFICIARIO:"
    pdf.cell(87, 4.5, lbl_vendor, new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(108)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*c_dark)
    pdf.multi_cell(87, 4.5, limpiar_texto(proveedor_nombre))

    if not es_vacio_o_none(proveedor_rif):
        pdf.set_x(108)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*c_text_mut)
        pdf.cell(87, 4, f"Tax ID / EIN: {limpiar_texto(proveedor_rif)}", new_x="LMARGIN", new_y="NEXT")

    if not es_vacio_o_none(proveedor_dir):
        pdf.set_x(108)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(87, 3.8, f"Address: {limpiar_texto(proveedor_dir)}")

    y_pos_der = pdf.get_y()
    y_max_partes = max(y_pos_izq, y_pos_der, y_partes + 25) + 3

    # 3. Franja Logística
    pdf.set_xy(15, y_max_partes)
    pdf.set_draw_color(*c_line)
    pdf.set_line_width(0.3)
    pdf.line(15, y_max_partes, 195, y_max_partes)
    pdf.ln(1.5)

    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*c_text_mut)
    pdf.cell(45, 3.5, "INCOTERM / TERMS:", border=0)
    pdf.cell(65, 3.5, "PAYMENT TERMS:", border=0)
    pdf.cell(70, 3.5, "LEAD TIME / ESTIMATED ETD:", border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_dark)
    txt_inco = incoterm if (not es_vacio_o_none(incoterm) and incoterm != "N/A") else "Standard Terms"
    txt_pago = condiciones_pago if not es_vacio_o_none(condiciones_pago) else "As Agreed"
    txt_lead = validez if not es_vacio_o_none(validez) else "Immediate"

    pdf.cell(45, 4.5, limpiar_texto(txt_inco), border=0)
    pdf.cell(65, 4.5, limpiar_texto(txt_pago), border=0)
    pdf.cell(70, 4.5, limpiar_texto(txt_lead), border=0, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    if datos_envio and (datos_envio.get("lugar_entrega") or datos_envio.get("puertos")):
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_text_color(*c_text_mut)
        pdf.cell(90, 3.5, "SHIP TO ADDRESS (LUGAR DE ENTREGA):", border=0)
        pdf.cell(90, 3.5, "PORTS (POL / POD):", border=0, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(51, 65, 85)
        txt_shipto = datos_envio.get("lugar_entrega", "Standard Warehouse")
        txt_ports = datos_envio.get("puertos", "N/A")
        pdf.cell(90, 4, limpiar_texto(txt_shipto), border=0)
        pdf.cell(90, 4, limpiar_texto(txt_ports), border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)

    # 4. Tabla de Productos
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*c_dark)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(*c_dark)

    w_num = 10
    if es_producto:
        w_desc, w_uom, w_cant, w_prec, w_sub = 75, 18, 18, 27, 32
        pdf.cell(w_num, 7.5, "#", border=1, fill=True, align="C")
        pdf.cell(w_desc, 7.5, " ITEM DESCRIPTION & SPECIFICATIONS" if es_ingles else " DESCRIPCION DEL ITEM Y ESPECIFICACIONES", border=1, fill=True)
        pdf.cell(w_uom, 7.5, "UOM", border=1, fill=True, align="C")
        pdf.cell(w_cant, 7.5, "QTY", border=1, fill=True, align="C")
        pdf.cell(w_prec, 7.5, "UNIT RATE", border=1, fill=True, align="R")
        pdf.cell(w_sub, 7.5, "TOTAL AMOUNT ", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
    else:
        w_desc, w_cant, w_prec, w_sub = 93, 22, 25, 30
        pdf.cell(w_num, 7.5, "#", border=1, fill=True, align="C")
        pdf.cell(w_desc, 7.5, " SERVICE DESCRIPTION / SCOPE", border=1, fill=True)
        pdf.cell(w_cant, 7.5, "QTY / HRS", border=1, fill=True, align="C")
        pdf.cell(w_prec, 7.5, "UNIT RATE", border=1, fill=True, align="R")
        pdf.cell(w_sub, 7.5, "TOTAL AMOUNT ", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.set_draw_color(*c_line)

    fill = False
    for idx_item, item in enumerate(items, start=1):
        desc_texto = limpiar_texto(item['descripcion'])
        if es_producto and not es_vacio_o_none(item.get("presentacion")):
            desc_texto += f"\n[Specs/SKU: {limpiar_texto(item['presentacion'])}]"
            
        uom_texto = limpiar_texto(item.get("uom", "PCS")) if es_producto else ""
        cant_texto = str(item['cantidad'])
        prec_texto = f"{item['precio']:,.2f}"
        sub_texto = f"{item['subtotal']:,.2f} "

        l_desc = calcular_lineas_multiline(pdf, desc_texto, w_desc, font_size=8.5)
        l_cant = calcular_lineas_multiline(pdf, cant_texto, w_cant, font_size=8.5)
        l_prec = calcular_lineas_multiline(pdf, prec_texto, w_prec, font_size=8.5)
        l_sub = calcular_lineas_multiline(pdf, sub_texto, w_sub, font_size=8.5)
        
        n_lineas_max = max(l_desc, l_cant, l_prec, l_sub, 1)
        h_fila = max(8.0, (n_lineas_max * 4.0) + 4.0)

        if pdf.get_y() + h_fila > 275:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(*c_dark)
            pdf.set_text_color(255, 255, 255)
            pdf.set_draw_color(*c_dark)
            if es_producto:
                pdf.cell(w_num, 7.5, "#", border=1, fill=True, align="C")
                pdf.cell(w_desc, 7.5, " ITEM DESCRIPTION & SPECIFICATIONS", border=1, fill=True)
                pdf.cell(w_uom, 7.5, "UOM", border=1, fill=True, align="C")
                pdf.cell(w_cant, 7.5, "QTY", border=1, fill=True, align="C")
                pdf.cell(w_prec, 7.5, "UNIT RATE", border=1, fill=True, align="R")
                pdf.cell(w_sub, 7.5, "TOTAL AMOUNT ", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(w_num, 7.5, "#", border=1, fill=True, align="C")
                pdf.cell(w_desc, 7.5, " SERVICE DESCRIPTION / SCOPE", border=1, fill=True)
                pdf.cell(w_cant, 7.5, "QTY / HRS", border=1, fill=True, align="C")
                pdf.cell(w_prec, 7.5, "UNIT RATE", border=1, fill=True, align="R")
                pdf.cell(w_sub, 7.5, "TOTAL AMOUNT ", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(30, 41, 59)
            pdf.set_draw_color(*c_line)

        y_inicio = pdf.get_y()
        fill_color = (248, 250, 252) if fill else (255, 255, 255)
        pdf.set_fill_color(*fill_color)

        if es_producto:
            pdf.rect(15, y_inicio, w_num, h_fila, style="FD")
            pdf.rect(15 + w_num, y_inicio, w_desc, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc, y_inicio, w_uom, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc + w_uom, y_inicio, w_cant, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc + w_uom + w_cant, y_inicio, w_prec, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc + w_uom + w_cant + w_prec, y_inicio, w_sub, h_fila, style="FD")
        else:
            pdf.rect(15, y_inicio, w_num, h_fila, style="FD")
            pdf.rect(15 + w_num, y_inicio, w_desc, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc, y_inicio, w_cant, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc + w_cant, y_inicio, w_prec, h_fila, style="FD")
            pdf.rect(15 + w_num + w_desc + w_cant + w_prec, y_inicio, w_sub, h_fila, style="FD")

        pdf.set_xy(15, y_inicio + 2.0)
        pdf.cell(w_num, 4.0, str(idx_item), border=0, align="C")

        pdf.set_xy(15 + w_num + 1.5, y_inicio + 2.0)
        pdf.multi_cell(w_desc - 3.0, 4.0, desc_texto, border=0, align="L")

        if es_producto:
            pdf.set_xy(15 + w_num + w_desc, y_inicio + 2.0)
            pdf.cell(w_uom, 4.0, uom_texto, border=0, align="C")

            pdf.set_xy(15 + w_num + w_desc + w_uom, y_inicio + 2.0)
            pdf.cell(w_cant, 4.0, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_num + w_desc + w_uom + w_cant, y_inicio + 2.0)
            pdf.cell(w_prec - 1.5, 4.0, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_num + w_desc + w_uom + w_cant + w_prec, y_inicio + 2.0)
            pdf.cell(w_sub - 1.5, 4.0, sub_texto, border=0, align="R")
        else:
            pdf.set_xy(15 + w_num + w_desc, y_inicio + 2.0)
            pdf.cell(w_cant, 4.0, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_num + w_desc + w_cant, y_inicio + 2.0)
            pdf.cell(w_prec - 1.5, 4.0, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_num + w_desc + w_cant + w_prec, y_inicio + 2.0)
            pdf.cell(w_sub - 1.5, 4.0, sub_texto, border=0, align="R")

        pdf.set_y(y_inicio + h_fila)
        fill = not fill

    pdf.ln(4)

    # 5. Desglose y Totales
    y_fin = pdf.get_y()

    pdf.set_xy(15, y_fin)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*c_emerald)
    pdf.cell(100, 4, "PURCHASE INSTRUCTIONS / SPECIAL REMARKS:" if es_ingles else "INSTRUCCIONES Y OBSERVACIONES DE COMPRA:", new_x="LMARGIN", new_y="NEXT")
    
    txt_instrucciones = notas if not es_vacio_o_none(notas) else "Please confirm receipt and acceptance of this Purchase Order."
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(100, 3.8, limpiar_texto(txt_instrucciones))
    y_fin_izq = pdf.get_y()

    pdf.set_xy(122, y_fin)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*c_text_mut)
    pdf.cell(33, 5, "Currency / Moneda:", align="L")
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_dark)
    pdf.cell(40, 5, limpiar_texto(moneda), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(122)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*c_text_mut)
    pdf.cell(33, 5, "Net Subtotal:", align="L")
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*c_dark)
    pdf.cell(40, 5, f"{subtotal:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    if monto_iva > 0:
        pdf.set_x(122)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*c_text_mut)
        pdf.cell(33, 5, f"Tax / VAT ({alicuota_iva:.0f}%):", align="L")
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*c_dark)
        pdf.cell(40, 5, f"{monto_iva:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(122)
    pdf.set_fill_color(*c_emerald)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(33, 8, " TOTAL PO:", fill=True)
    pdf.cell(40, 8, f"{total:,.2f} ", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    y_sig = max(y_fin_izq, pdf.get_y()) + 10

    # 6. Firmas
    if y_sig + 32 > 280:
        pdf.add_page()
        y_sig = 20

    pdf.set_y(y_sig)
    
    pdf.set_draw_color(*c_line)
    pdf.line(15, y_sig + 16, 85, y_sig + 16)
    pdf.set_xy(15, y_sig + 17)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*c_text_mut)
    pdf.cell(70, 3.5, "Vendor Acceptance / Signature & Date", align="C")

    if sello_bytes:
        try:
            pdf.image(sello_bytes, x=135, y=y_sig - 2, w=42)
        except Exception:
            pass
    pdf.line(125, y_sig + 16, 195, y_sig + 16)
    pdf.set_xy(125, y_sig + 17)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*c_text_mut)
    pdf.cell(70, 3.5, "Authorized Procurement Signature / Stamp", align="C")

    return bytes(pdf.output())


# =========================================================================
# MOTOR 2: COTIZACIONES, PROFORMAS Y FACTURAS
# =========================================================================
def crear_pdf_cotizacion(
    empresa, cliente_nombre, cliente_rif, cliente_dir, moneda, items, 
    subtotal, monto_iva, alicuota_iva, total, num_cotizacion,
    tipo_documento, idioma, validez, incoterm, condiciones_pago, notas, tipo_item,
    bancos_texto_custom=None
):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    es_ingles = (idioma == "Inglés")
    es_producto = (tipo_item == "Producto")
    
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
    lbl_desc = " Description of Goods" if (es_ingles and es_producto) else (" Description of Services" if es_ingles else (" Descripcion del Producto" if es_producto else " Descripcion del Servicio"))
    lbl_um = "UOM" if es_ingles else "U.M."
    lbl_cant = "Qty" if es_ingles else "Cant."
    lbl_precio = "Unit Price" if es_ingles else "P. Unitario"
    lbl_sub = "Subtotal "
    lbl_bancos = "BANK DETAILS / PAYMENT INSTRUCTIONS:" if es_ingles else "DATOS BANCARIOS PARA TRANSFERENCIA:"
    lbl_cond_pago = "Payment Terms:" if es_ingles else "Condiciones de Pago:"
    lbl_incoterm = "Incoterm:" if es_ingles else "Incoterm:"
    lbl_notas = "REMARKS / COMPLEMENTARY NOTES:" if es_ingles else "NOTAS COMPLEMENTARIAS / OBSERVACIONES:"
    lbl_firma = "Authorized Signature / Stamp" if es_ingles else "Firma / Sello Autorizado"

    logo_bytes = obtener_bytes_imagen(empresa.get("logo_url"))
    sello_bytes = obtener_bytes_imagen(empresa.get("sello_firma_url"))

    if logo_bytes:
        try:
            pdf.image(logo_bytes, x=15, y=14, w=45)
        except Exception:
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(90, 10, limpiar_texto(empresa['nombre']), ln=False)
    else:
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(90, 10, limpiar_texto(empresa['nombre']), ln=False)

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

    if not es_vacio_o_none(validez):
        pdf.set_x(105)
        pdf.cell(90, 4, limpiar_texto(f"{lbl_validez} {validez}"), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    
    pdf.set_draw_color(26, 54, 93)
    pdf.set_line_width(0.8)
    pdf.line(15, 42, 195, 42)
    pdf.ln(4)

    # 2. Bloque Emisor y Cliente
    y_bloque = pdf.get_y()
    
    l_emp_nom = calcular_lineas_multiline(pdf, empresa['nombre'], 81, font_name="Helvetica", font_style="B", font_size=9.5)
    l_emp_rif = 1 if not es_vacio_o_none(empresa.get('rif')) else 0
    l_emp_dir = calcular_lineas_multiline(pdf, f"Dir: {empresa.get('direccion', '')}", 81, font_size=8) if not es_vacio_o_none(empresa.get('direccion')) else 0
    h_emisor = 4 + (l_emp_nom * 4.5) + (l_emp_rif * 4.0) + (l_emp_dir * 4.0) + 4

    l_cli_nom = calcular_lineas_multiline(pdf, cliente_nombre, 81, font_name="Helvetica", font_style="B", font_size=9.5)
    l_cli_rif = 1 if not es_vacio_o_none(cliente_rif) else 0
    l_cli_dir = calcular_lineas_multiline(pdf, f"Dir: {cliente_dir}", 81, font_size=8) if not es_vacio_o_none(cliente_dir) else 0
    h_cliente = 4 + (l_cli_nom * 4.5) + (l_cli_rif * 4.0) + (l_cli_dir * 4.0) + 4

    box_h_cabecera = max(34, h_emisor, h_cliente)

    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(15, y_bloque, 87, box_h_cabecera, style="FD")
    pdf.rect(108, y_bloque, 87, box_h_cabecera, style="FD")

    pdf.set_xy(18, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(81, 4, lbl_emisor, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(18)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(81, 4.5, limpiar_texto(empresa['nombre']))
    
    if not es_vacio_o_none(empresa.get('rif')):
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(81, 4, limpiar_texto(f"RIF/Tax ID: {empresa['rif']}"), new_x="LMARGIN", new_y="NEXT")
    
    if not es_vacio_o_none(empresa.get('direccion')):
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(81, 3.8, limpiar_texto(f"Dir: {empresa['direccion']}"))

    pdf.set_xy(111, y_bloque + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 54, 93)
    pdf.cell(81, 4, lbl_cliente, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_x(111)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(81, 4.5, limpiar_texto(cliente_nombre))
    
    if not es_vacio_o_none(cliente_rif):
        pdf.set_x(111)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(81, 4, limpiar_texto(f"RIF/Tax ID: {cliente_rif}"), new_x="LMARGIN", new_y="NEXT")
    
    if not es_vacio_o_none(cliente_dir):
        pdf.set_x(111)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(81, 3.8, limpiar_texto(f"Dir: {cliente_dir}"))

    pdf.set_y(y_bloque + box_h_cabecera + 4)

    # 3. Tabla de Productos / Servicios
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(26, 54, 93)

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
    pdf.set_draw_color(226, 232, 240)
    
    fill = False
    for item in items:
        desc_texto = limpiar_texto(item['descripcion'])
        if es_producto and not es_vacio_o_none(item.get("presentacion")):
            desc_texto += f"\n[Specs/SKU: {limpiar_texto(item['presentacion'])}]"
            
        um_texto = limpiar_texto(item.get("uom", "PCS")) if es_producto else ""
        cant_texto = str(item['cantidad'])
        prec_texto = f"{item['precio']:,.2f}"
        sub_texto = f"{item['subtotal']:,.2f} "

        l_desc = calcular_lineas_multiline(pdf, desc_texto, w_desc, font_size=8.5)
        l_um = calcular_lineas_multiline(pdf, um_texto, w_um, font_size=8.5) if es_producto else 1
        l_cant = calcular_lineas_multiline(pdf, cant_texto, w_cant, font_size=8.5)
        l_prec = calcular_lineas_multiline(pdf, prec_texto, w_prec, font_size=8.5)
        l_sub = calcular_lineas_multiline(pdf, sub_texto, w_sub, font_size=8.5)
        
        n_lineas_max = max(l_desc, l_um, l_cant, l_prec, l_sub, 1)
        h_fila = max(8.0, (n_lineas_max * 4.0) + 4.0)

        if pdf.get_y() + h_fila > 275:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(26, 54, 93)
            pdf.set_text_color(255, 255, 255)
            pdf.set_draw_color(26, 54, 93)
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
            pdf.set_draw_color(226, 232, 240)

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

        pdf.set_xy(16.5, y_inicio + 2.0)
        pdf.multi_cell(w_desc - 3.0, 4.0, desc_texto, border=0, align="L")

        if es_producto:
            pdf.set_xy(15 + w_desc, y_inicio + 2.0)
            pdf.multi_cell(w_um, 4.0, um_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_um, y_inicio + 2.0)
            pdf.multi_cell(w_cant, 4.0, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_um + w_cant, y_inicio + 2.0)
            pdf.multi_cell(w_prec - 1.5, 4.0, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_desc + w_um + w_cant + w_prec, y_inicio + 2.0)
            pdf.multi_cell(w_sub - 1.5, 4.0, sub_texto, border=0, align="R")
        else:
            pdf.set_xy(15 + w_desc, y_inicio + 2.0)
            pdf.multi_cell(w_cant, 4.0, cant_texto, border=0, align="C")

            pdf.set_xy(15 + w_desc + w_cant, y_inicio + 2.0)
            pdf.multi_cell(w_prec - 1.5, 4.0, prec_texto, border=0, align="R")

            pdf.set_xy(15 + w_desc + w_cant + w_prec, y_inicio + 2.0)
            pdf.multi_cell(w_sub - 1.5, 4.0, sub_texto, border=0, align="R")

        pdf.set_y(y_inicio + h_fila)
        fill = not fill

    pdf.ln(5)

    # 4. Módulo Bancario y Totales
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

        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_seccion4, 102, box_h_bancos, style="FD")
        
        pdf.set_xy(18, y_seccion4 + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(96, 4, lbl_bancos, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        render_texto_con_dospuntos(pdf, bancos_texto, x_start=18, max_w=96, font_size=8.5, line_h=4.8)

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

    pdf.set_x(123)
    pdf.set_fill_color(26, 54, 93)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(32, 8.5, " TOTAL:", fill=True)
    pdf.cell(40, 8.5, f"{total:,.2f} ", fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    y_pos_siguiente = max(y_seccion4 + box_h_bancos + 5, pdf.get_y() + 6)
    pdf.set_y(y_pos_siguiente)

    # 5. Módulo Condiciones Comerciales
    tiene_cond = not es_vacio_o_none(condiciones_pago) or (not es_vacio_o_none(incoterm) and incoterm != "N/A") or not es_vacio_o_none(validez)
    if tiene_cond:
        y_cond = pdf.get_y()
        texto_cond_total = ""
        if not es_vacio_o_none(condiciones_pago): texto_cond_total += f"{lbl_cond_pago} {condiciones_pago}\n"
        if not es_vacio_o_none(incoterm) and incoterm != "N/A": texto_cond_total += f"{lbl_incoterm} {incoterm}\n"
        if not es_vacio_o_none(validez): texto_cond_total += f"{lbl_validez} {validez}\n"

        total_lineas_cond = calcular_lineas_totales_texto(pdf, texto_cond_total, max_w=174, font_size=8.5)
        box_h_cond = max(18, (total_lineas_cond * 4.8) + 10)
        
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(15, y_cond, 180, box_h_cond, style="FD")
        
        pdf.set_xy(18, y_cond + 3)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(26, 54, 93)
        pdf.cell(174, 4, "CONDICIONES COMERCIALES / TERMS OF SALE:" if es_ingles else "CONDICIONES COMERCIALES Y DE PAGO:", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        
        if not es_vacio_o_none(condiciones_pago):
            render_texto_con_dospuntos(pdf, f"{lbl_cond_pago} {condiciones_pago}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if not es_vacio_o_none(incoterm) and incoterm != "N/A":
            render_texto_con_dospuntos(pdf, f"{lbl_incoterm} {incoterm}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
        if not es_vacio_o_none(validez):
            render_texto_con_dospuntos(pdf, f"{lbl_validez} {validez}", x_start=18, max_w=174, font_size=8.5, line_h=4.5)
            
        pdf.set_y(y_cond + box_h_cond + 5)

    # 6. Módulo Notas
    if not es_vacio_o_none(notas):
        y_notas = pdf.get_y()
        total_lineas_notas = calcular_lineas_totales_texto(pdf, notas, max_w=174, font_size=8.5)
        box_h_notas = max(18, (total_lineas_notas * 4.8) + 10)
        
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

    # 7. Sello y Firma
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
# =========================================================================
# MOTOR 3: REPORTE DE TRANSFERENCIAS Y PAGOS EN PDF
# =========================================================================
def crear_pdf_reporte_transferencias(lista_transferencias):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_margins(10, 10, 10)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    c_dark = (15, 23, 42)
    c_blue = (26, 54, 93)
    c_line = (203, 213, 225)
    c_bg_alt = (241, 245, 249)

    # 1. Encabezado del Reporte
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*c_blue)
    pdf.cell(180, 8, limpiar_texto("REPORTE DE TRANSFERENCIAS Y PAGOS"), ln=False)

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(100, 116, 139)
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(97, 8, limpiar_texto(f"Generado: {fecha_hoy}"), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_draw_color(*c_blue)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(3)

    # Resumen de registros y totales
    total_registros = len(lista_transferencias)
    suma_base_usd = 0.0
    suma_gran_total_usd = 0.0

    for tr in lista_transferencias:
        m_base = float(tr.get("monto", 0.0) or 0.0)
        c_flat = float(tr.get("comision_flat", 0.0) or 0.0)
        c_porc = float(tr.get("comision_porc", 0.0) or 0.0)
        c_tot = float(tr.get("total_comision", (c_flat + (m_base * c_porc / 100.0))) or 0.0)
        g_tot = float(tr.get("gran_total", (m_base + c_tot)) or (m_base + c_tot))
        
        m_usd = float(tr.get("monto_usd", m_base) or m_base)
        g_usd = float(tr.get("gran_total_usd", m_usd) or m_usd)

        suma_base_usd += m_usd
        suma_gran_total_usd += g_usd

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(30, 41, 59)
    resumen_txt = f"Total registros: {total_registros}  |  Consolidado Base USD: ${suma_base_usd:,.2f} USD  |  Consolidado Gran Total USD: ${suma_gran_total_usd:,.2f} USD"
    pdf.cell(277, 5, limpiar_texto(resumen_txt), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # 2. Encabezado de la Tabla
    w_fecha, w_est, w_ori, w_des = 20, 24, 46, 46
    w_monto, w_mon, w_musd, w_com = 26, 15, 25, 22
    w_gtusd, w_ref = 27, 26

    def render_tabla_header():
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(*c_dark)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(*c_dark)

        pdf.cell(w_fecha, 7, "FECHA", border=1, fill=True, align="C")
        pdf.cell(w_est, 7, "ESTADO", border=1, fill=True, align="C")
        pdf.cell(w_ori, 7, "ORIGEN / EMISOR", border=1, fill=True, align="L")
        pdf.cell(w_des, 7, "DESTINO / BENEFICIARIO", border=1, fill=True, align="L")
        pdf.cell(w_monto, 7, "MONTO ORIG.", border=1, fill=True, align="R")
        pdf.cell(w_mon, 7, "MONEDA", border=1, fill=True, align="C")
        pdf.cell(w_musd, 7, "BASE USD ($)", border=1, fill=True, align="R")
        pdf.cell(w_com, 7, "COMISION", border=1, fill=True, align="R")
        pdf.cell(w_gtusd, 7, "GRAN TOTAL USD", border=1, fill=True, align="R")
        pdf.cell(w_ref, 7, "N REF", border=1, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

    render_tabla_header()

    # 3. Filas de la Tabla
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(30, 41, 59)
    pdf.set_draw_color(*c_line)

    fill = False
    for tr in lista_transferencias:
        if pdf.get_y() > 180:
            pdf.add_page()
            render_tabla_header()
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(30, 41, 59)
            pdf.set_draw_color(*c_line)

        fecha_str = str(tr.get("fecha", ""))[:10]
        estado_str = str(tr.get("estado", ""))
        origen_str = str(tr.get("origen", ""))
        destino_str = str(tr.get("destino", ""))
        moneda_str = str(tr.get("moneda", "USD")).split()[0]
        ref_str = str(tr.get("referencia", "")) if tr.get("referencia") else "-"

        m_base = float(tr.get("monto", 0.0) or 0.0)
        c_flat = float(tr.get("comision_flat", 0.0) or 0.0)
        c_porc = float(tr.get("comision_porc", 0.0) or 0.0)
        c_tot = float(tr.get("total_comision", (c_flat + (m_base * c_porc / 100.0))) or 0.0)
        g_tot = float(tr.get("gran_total", (m_base + c_tot)) or (m_base + c_tot))

        m_usd = float(tr.get("monto_usd", m_base) or m_base)
        g_usd = float(tr.get("gran_total_usd", m_usd) or m_usd)

        l_ori = calcular_lineas_multiline(pdf, origen_str, w_ori, font_size=7.5)
        l_des = calcular_lineas_multiline(pdf, destino_str, w_des, font_size=7.5)
        l_ref = calcular_lineas_multiline(pdf, ref_str, w_ref, font_size=7.5)
        
        n_lineas = max(l_ori, l_des, l_ref, 1)
        h_fila = max(6.5, (n_lineas * 3.5) + 3.0)

        y_ini = pdf.get_y()
        fill_color = c_bg_alt if fill else (255, 255, 255)
        pdf.set_fill_color(*fill_color)

        x_curr = 10
        widths = [w_fecha, w_est, w_ori, w_des, w_monto, w_mon, w_musd, w_com, w_gtusd, w_ref]
        for w in widths:
            pdf.rect(x_curr, y_ini, w, h_fila, style="FD")
            x_curr += w

        y_text = y_ini + 1.5

        pdf.set_xy(10, y_text)
        pdf.cell(w_fecha, 3.5, limpiar_texto(fecha_str), align="C")

        pdf.set_xy(10 + w_fecha, y_text)
        pdf.cell(w_est, 3.5, limpiar_texto(estado_str[:15]), align="C")

        pdf.set_xy(10 + w_fecha + w_est + 1.0, y_text)
        pdf.multi_cell(w_ori - 2.0, 3.5, limpiar_texto(origen_str), align="L")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + 1.0, y_text)
        pdf.multi_cell(w_des - 2.0, 3.5, limpiar_texto(destino_str), align="L")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des, y_text)
        pdf.cell(w_monto - 1.0, 3.5, f"{m_base:,.2f}", align="R")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des + w_monto, y_text)
        pdf.cell(w_mon, 3.5, limpiar_texto(moneda_str), align="C")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des + w_monto + w_mon, y_text)
        pdf.cell(w_musd - 1.0, 3.5, f"${m_usd:,.2f}", align="R")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des + w_monto + w_mon + w_musd, y_text)
        pdf.cell(w_com - 1.0, 3.5, f"{c_tot:,.2f}", align="R")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des + w_monto + w_mon + w_musd + w_com, y_text)
        pdf.cell(w_gtusd - 1.0, 3.5, f"${g_usd:,.2f}", align="R")

        pdf.set_xy(10 + w_fecha + w_est + w_ori + w_des + w_monto + w_mon + w_musd + w_com + w_gtusd + 1.0, y_text)
        pdf.multi_cell(w_ref - 2.0, 3.5, limpiar_texto(ref_str), align="C")

        pdf.set_y(y_ini + h_fila)
        fill = not fill

    # Fila de Totales Consolidados
    if pdf.get_y() > 175:
        pdf.add_page()

    y_tot = pdf.get_y()
    pdf.set_fill_color(*c_dark)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)

    w_tot_label = w_fecha + w_est + w_ori + w_des + w_monto + w_mon
    pdf.rect(10, y_tot, 277, 7, style="FD")
    
    pdf.set_xy(10, y_tot + 1.5)
    pdf.cell(w_tot_label - 2.0, 4, "TOTALES CONSOLIDADOS:", align="R")

    pdf.set_xy(10 + w_tot_label, y_tot + 1.5)
    pdf.cell(w_musd - 1.0, 4, f"${suma_base_usd:,.2f}", align="R")

    pdf.set_xy(10 + w_tot_label + w_musd + w_com, y_tot + 1.5)
    pdf.cell(w_gtusd - 1.0, 4, f"${suma_gran_total_usd:,.2f}", align="R")

    return bytes(pdf.output())

# ==========================================
# MENÚ DE LA APLICACIÓN (STREAMLIT)
# ==========================================
st.sidebar.title("📌 Menú Principal")

if "cotiz_edit_data" not in st.session_state:
    st.session_state["cotiz_edit_data"] = None
if "modo_formulario" not in st.session_state:
    st.session_state["modo_formulario"] = "crear"
if "transf_edit_data" not in st.session_state:
    st.session_state["transf_edit_data"] = None
if "pestana_transf_activa" not in st.session_state:
    st.session_state["pestana_transf_activa"] = "➕ Registrar / Editar Transferencia"

opcion = st.sidebar.radio("Selecciona un módulo:", [
    "1. Empresas", 
    "2. Directorio (Clientes / Proveedores)", 
    "3. Emitir Documento (Cotizar / O.C.)", 
    "4. Historial de Documentos",
    "5. Control de Transferencias"
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
        st.caption("Agrega una o varias cuentas bancarias en la tabla.")
        
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
                "Alias de Cuenta": st.column_config.TextColumn("Alias / Nombre Corto *", width="medium"),
                "Detalles": st.column_config.TextColumn("Datos de la Cuenta (Banco, Nro, SWIFT, Titular)", width="large")
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

    lbl_emp_select = "Empresa Compradora (Buyer) *" if es_orden_compra else "Empresa Emisora *"
    emp_seleccionada = st.selectbox(lbl_emp_select, nombres_emp, index=idx_emp)
    empresa = next(e for e in empresas if e["nombre"] == emp_seleccionada)
    cuentas_disponibles = obtener_cuentas_bancarias(empresa)

    st.divider()

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
        prefijo_def = "PO-" if es_orden_compra else "COT-"
        num_def = f"{prefijo_def}{datetime.now().strftime('%Y%m%d%H%M')}"
        if datos_cargados:
            if modo_form == "editar":
                num_def = datos_cargados.get("numero_cotizacion", num_def)
            elif modo_form == "duplicar":
                num_def = f"{prefijo_def}{datetime.now().strftime('%Y%m%d%H%M')}"

        num_cotizacion = st.text_input("Número de Documento *", value=num_def)
        lbl_validez_input = "Tiempo de Entrega / Lead Time" if es_orden_compra else "Tiempo de Validez"
        val_default_text = "20-25 Días" if es_orden_compra else "15 Días"
        validez = st.text_input(lbl_validez_input, value=datos_cargados.get("validez", val_default_text) if datos_cargados else val_default_text)
        
        incoterm = st.selectbox(
            "Incoterm (Comercio Internacional)", 
            ["FOB - Free on Board", "EXW - Ex Works", "CIF - Cost, Insurance & Freight", "CFR - Cost and Freight", "DDP - Delivered Duty Paid", "DAP - Delivered at Place", "FCA - Free Carrier", "CIP - Carriage & Insurance Paid", "CPT - Carriage Paid To", "N/A"]
        )
        cond_default = "30% Deposit, 70% against BL Copy" if es_orden_compra else "100% Anticipado"
        condiciones_pago = st.text_input("Condiciones de Pago", value=datos_cargados.get("condiciones_pago", cond_default) if datos_cargados else cond_default)

    datos_envio_dict = {}
    if es_orden_compra:
        st.subheader("🚢 Datos de Envío y Logística Internacional (Ship To / Destination)")
        with st.expander("📍 Abrir detalles de Entrega, Puertos y Fechas", expanded=True):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                lugar_entrega = st.text_area(
                    "Dirección de Entrega / Ship To (Casillero / Forwarder / Almacén):",
                    value="Warehouse & Logistics Forwarder Miami / ShenZhen / Local Customs",
                    height=70
                )
            with col_e2:
                puertos = st.text_input("Puerto de Embarque y Destino (POL / POD):", value="Ningbo Port (POL) -> Miami / La Guaira (POD)")
                fecha_despacho = st.text_input("Fecha Estimada de Despacho (ETD):", value="15-20 days after advance confirmation")
            datos_envio_dict = {
                "lugar_entrega": lugar_entrega if not es_vacio_o_none(lugar_entrega) else "",
                "puertos": puertos if not es_vacio_o_none(puertos) else "",
                "fecha_despacho": fecha_despacho if not es_vacio_o_none(fecha_despacho) else ""
            }

    bancos_texto_para_pdf = ""
    if cuentas_disponibles and not es_orden_compra:
        st.subheader("🏦 Cuentas Bancarias a Mostrar en el PDF")
        opciones_alias = [c["alias"] for c in cuentas_disponibles]
        cuentas_seleccionadas = st.multiselect(
            "Selecciona la(s) cuenta(s) a incluir:",
            options=opciones_alias,
            default=opciones_alias
        )
        bloques_bancarios = []
        for c in cuentas_disponibles:
            if c["alias"] in cuentas_seleccionadas:
                bloques_bancarios.append(f"[{c['alias']}]\n{c['detalles']}")
        bancos_texto_para_pdf = "\n\n".join(bloques_bancarios)

    st.subheader("📦 Lista de Ítems / Precios")
    
    lista_uoms = ["PCS", "UNT", "SET", "CTN", "BOX", "PKT", "PR", "KG", "TON", "M", "M²", "CBM", "LTR", "ROL", "BAG"]

    if datos_cargados and "items" in datos_cargados:
        items_cargados = []
        for it in datos_cargados["items"]:
            uom_cargada = it.get("uom", "PCS")
            if uom_cargada not in lista_uoms:
                uom_cargada = "PCS"

            if tipo_item == "Producto":
                items_cargados.append({
                    "Descripción": it.get("descripcion", ""),
                    "Presentación / Empaque / SKU": it.get("presentacion", ""),
                    "UOM": uom_cargada,
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
                "Descripción": "Ej: Commercial Raw Material / Product Spec A",
                "Presentación / Empaque / SKU": "CTN x 50 PCS (HS Code: 8409.91)",
                "UOM": "PCS",
                "Cantidad": 100,
                "Precio Unitario": 12.50
            }])
        else:
            df_inicial = pd.DataFrame([{
                "Descripción": "Ej: Specialized Technical Consulting",
                "Cantidad / Horas": 1,
                "Precio Unitario": 200.0
            }])

    if tipo_item == "Producto":
        df_editado = st.data_editor(
            df_inicial,
            num_rows="dynamic",
            column_config={
                "UOM": st.column_config.SelectboxColumn("UOM", options=lista_uoms, default="PCS", width="small"),
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
        lbl_notas_box = "Instrucciones de Compra / Observaciones" if es_orden_compra else "Notas Complementarias / Observaciones"
        notas = st.text_area(lbl_notas_box, value=notas_def)

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
                        "uom": row.get("UOM", "PCS"),
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
                
            if es_orden_compra:
                pdf_bytes = crear_pdf_orden_compra(
                    empresa, cliente_nombre, cliente_rif, cliente_dir, moneda,
                    items_list, subtotal_cotizacion, monto_iva, alicuota_iva, 
                    total_cotizacion, num_cotizacion, idioma, 
                    validez, incoterm, condiciones_pago, notas, tipo_item,
                    datos_envio=datos_envio_dict
                )
            else:
                pdf_bytes = crear_pdf_cotizacion(
                    empresa, cliente_nombre, cliente_rif, cliente_dir, moneda,
                    items_list, subtotal_cotizacion, monto_iva, alicuota_iva, 
                    total_cotizacion, num_cotizacion, tipo_documento, idioma, 
                    validez, incoterm, condiciones_pago, notas, tipo_item,
                    bancos_texto_custom=bancos_texto_para_pdf
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
            busqueda = st.text_input("🔍 Buscar por nombre o número:", placeholder="Ej: Proveedor Asia, PO-2026, COT...")
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
                        st.rerun()

                with col_b2:
                    if st.button("📋 Duplicar", key=f"dup_{q['id']}", use_container_width=True):
                        st.session_state["cotiz_edit_data"] = q
                        st.session_state["modo_formulario"] = "duplicar"
                        st.rerun()

                with col_b3:
                    if st.button("🗑️ Eliminar", key=f"del_{q['id']}", type="secondary", use_container_width=True):
                        try:
                            supabase.table("cotizaciones").delete().eq("id", q["id"]).execute()
                            st.success(f"Documento {q['numero_cotizacion']} eliminado.")
                            st.rerun()
                        except Exception as e_del:
                            st.error(f"Error al eliminar: {e_del}")

# -------------------------------------------------------------------------
# MÓDULO 5: CONTROL Y REGISTRO DE TRANSFERENCIAS (MEJORADO Y BLINDADO)
# -------------------------------------------------------------------------
elif opcion == "5. Control de Transferencias":
    st.title("💸 Control de Transferencias y Órdenes de Pago")
    st.write("Registra pagos multimoneda con conversión precisa a USD, cálculo de comisiones (flat y %), desglose de Gran Total y exportación a Excel / CSV.")

    try:
        res_emp = supabase.table("empresas").select("nombre").execute()
        lista_empresas_db = [e["nombre"] for e in res_emp.data]
        res_cli = supabase.table("clientes").select("nombre").execute()
        lista_clientes_db = [c["nombre"] for c in res_cli.data]
    except Exception:
        lista_empresas_db = []
        lista_clientes_db = []

    entidades_base = list(dict.fromkeys(ENTIDADES_PREDEFINIDAS + lista_empresas_db + lista_clientes_db))
    opciones_select = ["➕ Escribir Manualmente / Otro"] + entidades_base

    # NAVEGACIÓN LIMPIA SIN CONFLICTOS DE WIDGET
    opciones_seccion_transf = ["➕ Registrar / Editar Transferencia", "📊 Historial, Reportes y Descarga"]
    
    idx_pestana_nav = 1 if st.session_state.get("pestana_transf_activa") == "📊 Historial, Reportes y Descarga" else 0

    def cambio_de_pestana_callback():
        st.session_state["pestana_transf_activa"] = st.session_state["radio_nav_transf_key"]

    pestana_activa = st.radio(
        "Navegación:",
        options=opciones_seccion_transf,
        index=idx_pestana_nav,
        horizontal=True,
        key="radio_nav_transf_key",
        on_change=cambio_de_pestana_callback,
        label_visibility="collapsed"
    )
    st.session_state["pestana_transf_activa"] = pestana_activa

    st.divider()

    # ------------------ SECCIÓN 1: FORMULARIO ------------------
    if pestana_activa == "➕ Registrar / Editar Transferencia":
        transf_edit = st.session_state.get("transf_edit_data")
        if transf_edit:
            st.info(f"✏️ **Modo Edición Activo**: Modificando registro `{transf_edit.get('origen', '')} ➡️ {transf_edit.get('destino', '')}`")

        with st.form("form_transferencia", clear_on_submit=False):
            col_t1, col_t2 = st.columns(2)

            # ORIGEN
            with col_t1:
                st.markdown("### 📤 Emisor / Origen (¿Desde dónde?)")
                origen_def = transf_edit.get("origen", "") if transf_edit else ""
                idx_orig = 0
                if origen_def in opciones_select:
                    idx_orig = opciones_select.index(origen_def)

                sel_origen = st.selectbox("Seleccionar Origen:", opciones_select, index=idx_orig, key="sel_origen")
                if sel_origen == "➕ Escribir Manualmente / Otro":
                    origen_final = st.text_input("Escribe el nombre del Origen / Cuenta:", value=origen_def if origen_def not in opciones_select else "")
                else:
                    origen_final = sel_origen

            # DESTINO
            with col_t2:
                st.markdown("### 📥 Beneficiario / Destino (¿A quién?)")
                destino_def = transf_edit.get("destino", "") if transf_edit else ""
                idx_dest = 0
                if destino_def in opciones_select:
                    idx_dest = opciones_select.index(destino_def)

                sel_destino = st.selectbox("Seleccionar Destino:", opciones_select, index=idx_dest, key="sel_destino")
                if sel_destino == "➕ Escribir Manualmente / Otro":
                    destino_final = st.text_input("Escribe el nombre del Beneficiario / Destino:", value=destino_def if destino_def not in opciones_select else "")
                else:
                    destino_final = sel_destino

            st.divider()

            # DETALLES FINANCIEROS Y MONEDA
            st.markdown("### 💰 Detalles Financieros")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                fecha_val = date.today()
                if transf_edit and transf_edit.get("fecha"):
                    try:
                        fecha_val = datetime.strptime(str(transf_edit["fecha"])[:10], "%Y-%m-%d").date()
                    except Exception:
                        fecha_val = date.today()
                fecha_transf = st.date_input("Fecha *", value=fecha_val)
            with col_m2:
                monedas_list = ["USD ($)", "EUR (€)", "RMB (¥)", "VES (Bs.)", "USDT (Crypto)"]
                mon_idx = 0
                if transf_edit and transf_edit.get("moneda") in monedas_list:
                    mon_idx = monedas_list.index(transf_edit.get("moneda"))
                moneda_transf = st.selectbox("Moneda *", monedas_list, index=mon_idx)
            with col_m3:
                monto_val = float(transf_edit.get("monto", 0.0)) if transf_edit else 0.0
                monto_transf = st.number_input("Monto en Divisa Original *", min_value=0.0, value=monto_val, step=100.0, format="%.2f")
            with col_m4:
                estados_list = ["Completada", "Pendiente / Por Pagar", "En Proceso", "Cancelada"]
                est_idx = 0
                if transf_edit and transf_edit.get("estado") in estados_list:
                    est_idx = estados_list.index(transf_edit.get("estado"))
                estado_transf = st.selectbox("Estado *", estados_list, index=est_idx)

# CONVERSIÓN DE DIVISA (SI NO ES USD)
            col_conv1, col_conv2 = st.columns(2)
            tasa_val_default = float(transf_edit.get("tasa_cambio", 1.0)) if (transf_edit and transf_edit.get("tasa_cambio")) else 1.0
            
            with col_conv1:
                if moneda_transf == "EUR (€)":
                    tasa_eur_def = tasa_val_default if tasa_val_default > 0 else 1.08
                    tasa_cambio = st.number_input(
                        "💱 Tasa EUR to USD (Multiplicador -> 1 EUR = X USD):",
                        min_value=0.0001,
                        value=tasa_eur_def,
                        step=0.005,
                        format="%.4f",
                        help="La tasa multiplica el monto en EUR. Ejemplo: 100 EUR × 1.08 = $108.00 USD"
                    )
                    # MULTIPLICACIÓN DIRECTA PARA EUR:
                    monto_en_usd = round(monto_transf * tasa_cambio, 2)
                    calculo_label = f"{monto_transf:,.2f} EUR × {tasa_cambio:.4f} = ${monto_en_usd:,.2f} USD"
                elif moneda_transf in ["RMB (¥)", "VES (Bs.)"]:
                    simb_m = "RMB" if "RMB" in moneda_transf else "Bs."
                    def_tasa = tasa_val_default if tasa_val_default > 0 else (7.25 if simb_m == "RMB" else 36.50)
                    tasa_cambio = st.number_input(
                        f"💱 Tasa de Cambio (1 USD = X {simb_m}):",
                        min_value=0.0001,
                        value=def_tasa,
                        step=0.01,
                        format="%.4f",
                        help=f"Ejemplo: {def_tasa} {simb_m} por cada 1 USD"
                    )
                    monto_en_usd = round(monto_transf / tasa_cambio, 2) if tasa_cambio > 0 else 0.0
                    calculo_label = f"{monto_transf:,.2f} {simb_m} ÷ {tasa_cambio:.4f} = ${monto_en_usd:,.2f} USD"
                else:
                    tasa_cambio = 1.0
                    monto_en_usd = monto_transf
                    calculo_label = f"${monto_en_usd:,.2f} USD"

            with col_conv2:
                if moneda_transf not in ["USD ($)", "USDT (Crypto)"]:
                    st.info(f"💵 **Conversión a USD:** `{calculo_label}`")
                else:
                    st.caption("ℹ️ Transacción en moneda base USD / USDT.")

# SECCIÓN DE COMISIONES
            st.markdown("### 🏷️ Comisiones Aplicables")
            col_com1, col_com2, col_com3 = st.columns(3)
            
            with col_com1:
                com_porc_def = float(transf_edit.get("comision_porc", 0.0)) if (transf_edit and transf_edit.get("comision_porc")) else 0.0
                comision_porc = st.number_input(
                    "1️⃣ Comisión Porcentual (%)", 
                    min_value=0.0, 
                    max_value=100.0, 
                    value=com_porc_def, 
                    step=0.1, 
                    format="%.2f",
                    help="Se calcula y se suma primero sobre el monto base"
                )

            with col_com2:
                com_flat_def = float(transf_edit.get("comision_flat", 0.0)) if (transf_edit and transf_edit.get("comision_flat")) else 0.0
                comision_flat = st.number_input(
                    "2️⃣ Comisión Flat (Monto Fijo)", 
                    min_value=0.0, 
                    value=com_flat_def, 
                    step=1.0, 
                    format="%.2f",
                    help="Se adiciona después de haber sumado la comisión porcentual"
                )

            # PASO 1: Sumar primero la comisión porcentual al monto base
            monto_com_porc = monto_transf * (comision_porc / 100.0) if comision_porc > 0 else 0.0
            subtotal_con_porc = monto_transf + monto_com_porc

            # PASO 2: Adicionar la comisión flat
            gran_total = subtotal_con_porc + comision_flat
            total_comisiones = monto_com_porc + comision_flat

            # Calcular Gran Total en USD (EUR multiplica)
            if moneda_transf == "EUR (€)":
                gran_total_usd = round(gran_total * tasa_cambio, 2)
            elif moneda_transf in ["RMB (¥)", "VES (Bs.)"]:
                gran_total_usd = round(gran_total / tasa_cambio, 2) if tasa_cambio > 0 else gran_total
            else:
                gran_total_usd = gran_total

            with col_com3:
                txt_usd_extra = f" (≈ ${gran_total_usd:,.2f} USD)" if moneda_transf not in ["USD ($)", "USDT (Crypto)"] else ""
                
                if total_comisiones > 0:
                    desglose_texto = (
                        f"• Base + {comision_porc:.2f}%: `{moneda_transf} {subtotal_con_porc:,.2f}`\n\n"
                        f"• + Flat: `+{comision_flat:,.2f}`\n\n"
                        f"### 🏆 **Gran Total:** `{moneda_transf} {gran_total:,.2f}`{txt_usd_extra}"
                    )
                    st.success(desglose_texto)
                else:
                    st.success(f"### 🏆 **Gran Total:** `{moneda_transf} {gran_total:,.2f}`{txt_usd_extra}")

            st.divider()

            col_n1, col_n2 = st.columns(2)
            with col_n1:
                ref_val = transf_edit.get("referencia", "") if transf_edit else ""
                referencia_transf = st.text_input("N° de Referencia / ID de Transacción:", value=ref_val, placeholder="Ej: 9837482910 o Ref Zelle / Swift")
                obs_val = transf_edit.get("observaciones", "") if transf_edit else ""
                obs_transf = st.text_area("Concepto / Observaciones / Instrucciones:", value=obs_val, placeholder="Ej: Pago anticipo orden #402 / Factura comercial adjunta")

            with col_n2:
                st.markdown("📎 **Comprobantes y Facturas (Múltiples Archivos)**")
                comprobantes_existentes = obtener_urls_comprobantes(transf_edit.get("comprobante_url")) if transf_edit else []
                comprobantes_conservar = []

                if comprobantes_existentes:
                    st.write("Archivos adjuntos actuales:")
                    for idx_c, url_c in enumerate(comprobantes_existentes, start=1):
                        chk = st.checkbox(f"Mantener Archivo #{idx_c}", value=True, key=f"chk_prev_{idx_c}")
                        if chk:
                            comprobantes_conservar.append(url_c)
                        st.caption(f"[🔗 Ver Archivo #{idx_c}]({url_c})")
                
                archivos_comprobantes = st.file_uploader(
                    "Subir archivos nuevos (PNG, JPG, PDF, WEBP, etc.)", 
                    type=["png", "jpg", "jpeg", "pdf", "webp"], 
                    accept_multiple_files=True, 
                    key="files_comp_multi"
                )

            guardar_t = st.form_submit_button("💾 Guardar Transferencia", use_container_width=True, type="primary")

        if guardar_t:
            if not origen_final or not destino_final or monto_transf <= 0:
                st.error("⚠️ Por favor completa el Origen, Destino y un Monto mayor a 0.")
            else:
                lista_urls_final = list(comprobantes_conservar)

                if archivos_comprobantes:
                    for arch in archivos_comprobantes:
                        ext = arch.name.split(".")[-1]
                        path_comp = f"comprobantes/{fecha_transf}_{uuid.uuid4()}.{ext}"
                        supabase.storage.from_("archivos-cotizador").upload(
                            path=path_comp, file=arch.getvalue(),
                            file_options={"content-type": arch.type, "upsert": "true"}
                        )
                        url_subida = supabase.storage.from_("archivos-cotizador").get_public_url(path_comp)
                        lista_urls_final.append(url_subida)

                comprobante_url_db = json.dumps(lista_urls_final, ensure_ascii=False) if lista_urls_final else None

                datos_t = {
                    "fecha": str(fecha_transf),
                    "origen": origen_final.strip(),
                    "destino": destino_final.strip(),
                    "monto": float(monto_transf),
                    "moneda": moneda_transf,
                    "referencia": referencia_transf.strip(),
                    "estado": estado_transf,
                    "comprobante_url": comprobante_url_db,
                    "observaciones": obs_transf.strip(),
                    "comision_flat": float(comision_flat),
                    "comision_porc": float(comision_porc),
                    "total_comision": float(total_comisiones),
                    "gran_total": float(gran_total),
                    "tasa_cambio": float(tasa_cambio),
                    "monto_usd": float(monto_en_usd),
                    "gran_total_usd": float(gran_total_usd)
                }

                guardado_exitoso = False
                try:
                    if transf_edit:
                        supabase.table("transferencias").update(datos_t).eq("id", transf_edit["id"]).execute()
                    else:
                        supabase.table("transferencias").insert(datos_t).execute()
                    guardado_exitoso = True
                except Exception as e_t:
                    # Respaldo automático para bases de datos sin las columnas nuevas
                    try:
                        obs_con_detalles = f"{obs_transf.strip()} | [Comisión: Flat={comision_flat:.2f}, %={comision_porc:.2f} | Gran Total: {gran_total:,.2f} | Equiv USD: ${monto_en_usd:,.2f} | Gran Total USD: ${gran_total_usd:,.2f}]".strip(" | ")
                        datos_t_backup = {
                            "fecha": str(fecha_transf),
                            "origen": origen_final.strip(),
                            "destino": destino_final.strip(),
                            "monto": float(monto_transf),
                            "moneda": moneda_transf,
                            "referencia": referencia_transf.strip(),
                            "estado": estado_transf,
                            "comprobante_url": comprobante_url_db,
                            "observaciones": obs_con_detalles
                        }
                        if transf_edit:
                            supabase.table("transferencias").update(datos_t_backup).eq("id", transf_edit["id"]).execute()
                        else:
                            supabase.table("transferencias").insert(datos_t_backup).execute()
                        guardado_exitoso = True
                    except Exception as e_t2:
                        st.error(f"🚨 Error al guardar en base de datos: {e_t2}")

                if guardado_exitoso:
                    st.session_state["transf_edit_data"] = None
                    st.session_state["pestana_transf_activa"] = "📊 Historial, Reportes y Descarga"
                    st.rerun()

        if transf_edit:
            if st.button("❌ Cancelar Modo Edición", use_container_width=True):
                st.session_state["transf_edit_data"] = None
                st.session_state["pestana_transf_activa"] = "📊 Historial, Reportes y Descarga"
                st.rerun()

    # ------------------ SECCIÓN 2: HISTORIAL Y REPORTES ------------------
    elif pestana_activa == "📊 Historial, Reportes y Descarga":
        try:
            res_tr = supabase.table("transferencias").select("*").order("fecha", desc=True).execute()
            transferencias = res_tr.data
        except Exception as e:
            st.error("🚨 Error al consultar la tabla 'transferencias':")
            st.write(e)
            transferencias = []

        if not transferencias:
            st.info("ℹ️ Aún no hay transferencias registradas.")
        else:
            st.subheader("🔍 Filtros de Búsqueda")
            col_f1, col_f2, col_f3 = st.columns(3)

            with col_f1:
                busq_t = st.text_input("Buscar por palabra clave:", placeholder="Ej: United, Alina, Simkin, Suelen, N° Ref...")
            
            with col_f2:
                todas_entidades = sorted(list(set([t.get("origen", "") for t in transferencias if t.get("origen")] + [t.get("destino", "") for t in transferencias if t.get("destino")])))
                filtro_entidad = st.selectbox("Filtrar por Proveedor / Cliente / Cuenta:", ["Todas"] + todas_entidades)

            with col_f3:
                filtro_estado = st.selectbox("Filtrar por Estado:", ["Todos", "Completada", "Pendiente / Por Pagar", "En Proceso", "Cancelada"])

            # Aplicar filtros
            tf_filtradas = transferencias

            if busq_t:
                b_low = busq_t.lower()
                tf_filtradas = [
                    t for t in tf_filtradas
                    if b_low in str(t.get("origen", "")).lower()
                    or b_low in str(t.get("destino", "")).lower()
                    or b_low in str(t.get("referencia", "")).lower()
                    or b_low in str(t.get("observaciones", "")).lower()
                ]

            if filtro_entidad != "Todas":
                tf_filtradas = [t for t in tf_filtradas if t.get("origen") == filtro_entidad or t.get("destino") == filtro_entidad]

            if filtro_estado != "Todos":
                tf_filtradas = [t for t in tf_filtradas if t.get("estado") == filtro_estado]

            # TOTALES / MÉTRICAS FINANCIERAS
            st.divider()
            df_tf = pd.DataFrame(tf_filtradas)
            
            if not df_tf.empty:
                st.markdown("#### 📈 Resumen Financiero:")
                
                # Consolidado en USD
                total_usd_consolidado = 0.0
                if "monto_usd" in df_tf.columns:
                    total_usd_consolidado = df_tf["monto_usd"].fillna(0.0).sum()
                
                monedas_encontradas = df_tf["moneda"].unique()
                cols_met = st.columns(len(monedas_encontradas) + (1 if total_usd_consolidado > 0 else 0))
                
                for idx_m, m_nom in enumerate(monedas_encontradas):
                    suma_m = df_tf[df_tf["moneda"] == m_nom]["monto"].sum()
                    with cols_met[idx_m]:
                        st.metric(label=f"Total Base {m_nom}", value=f"{suma_m:,.2f}")
                
                if total_usd_consolidado > 0:
                    with cols_met[-1]:
                        st.metric(label="💵 Consolidado Total Base (USD)", value=f"${total_usd_consolidado:,.2f}")

            st.divider()

            # SECCIÓN DE DESCARGA (EXCEL Y CSV LIMPIO Y ORGANIZADO)
col_exp1, col_exp2, col_exp3 = st.columns(3)
                
                # 1. Botón CSV
                csv_bytes = df_export_limpio.to_csv(index=False).encode('utf-8-sig')
                with col_exp1:
                    st.download_button(
                        label="📄 Descargar CSV Detallado",
                        data=csv_bytes,
                        file_name=f"transferencias_detallado_{date.today()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                # 2. Botón Excel (.xlsx)
                try:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df_export_limpio.to_excel(writer, index=False, sheet_name="Transferencias")
                    excel_bytes = excel_buffer.getvalue()
                    with col_exp2:
                        st.download_button(
                            label="📊 Descargar Excel (.xlsx)",
                            data=excel_bytes,
                            file_name=f"transferencias_detallado_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                except Exception:
                    pass

                # 3. Botón PDF (Exporta solo lo filtrado)
                try:
                    pdf_transf_bytes = crear_pdf_reporte_transferencias(tf_filtradas)
                    with col_exp3:
                        st.download_button(
                            label="📕 Descargar PDF del Historial",
                            data=pdf_transf_bytes,
                            file_name=f"reporte_transferencias_{date.today()}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                except Exception as e_pdf:
                    with col_exp3:
                        st.error(f"Error generando PDF: {e_pdf}")
