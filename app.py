import pandas as pd
from fpdf import FPDF
import io
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="Cotizador Online", page_icon="📄", layout="wide")

# Lectura directa de Secrets SIN memoria caché (para forzar lectura fresca)
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

# Menú Principal
st.sidebar.title("📌 Menú Cotizador")
opcion = st.sidebar.radio("Selecciona un módulo:", ["1. Empresas", "2. Cotizar", "3. Historial"])

# Diagnóstico visible en la barra lateral
with st.sidebar.expander("🔍 Verificación de Datos"):
    st.write(f"**URL:** `{url}`")
    st.write(f"**Clave empieza con:** `{key[:12]}...`")
    st.write(f"**Longitud de Clave:** `{len(key)} caracteres`")
# Función para crear el archivo PDF en memoria
def crear_pdf_cotizacion(empresa, cliente_nombre, cliente_rif, cliente_dir, moneda, items, subtotal, total, num_cotizacion):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # Encabezado
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"COTIZACIÓN N° {num_cotizacion}", ln=True, align="C")
    pdf.ln(5)
    
    # Datos Emisor
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"EMISOR: {empresa['nombre']}", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, f"RIF/Tax ID: {empresa['rif']}", ln=True)
    pdf.cell(0, 5, f"Dirección: {empresa['direccion']}", ln=True)
    pdf.ln(5)
    
    # Datos Cliente
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"CLIENTE: {cliente_nombre}", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, f"RIF/Tax ID: {cliente_rif}", ln=True)
    pdf.cell(0, 5, f"Dirección: {cliente_dir}", ln=True)
    pdf.cell(0, 5, f"Moneda de Cotización: {moneda}", ln=True)
    pdf.ln(8)
    
    # Tabla de Productos
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 7, "Descripción", 1)
    pdf.cell(25, 7, "Cant.", 1, 0, "C")
    pdf.cell(30, 7, "P. Unitario", 1, 0, "R")
    pdf.cell(35, 7, "Subtotal", 1, 1, "R")
    
    pdf.set_font("Helvetica", size=9)
    for item in items:
        pdf.cell(100, 6, str(item['descripcion'])[:50], 1)
        pdf.cell(25, 6, str(item['cantidad']), 1, 0, "C")
        pdf.cell(30, 6, f"{item['precio']:.2f}", 1, 0, "R")
        pdf.cell(35, 6, f"{item['subtotal']:.2f}", 1, 1, "R")
        
    pdf.ln(5)
    # Totales
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(155, 7, "TOTAL:", 0, 0, "R")
    pdf.cell(35, 7, f"{moneda} {total:.2f}", 1, 1, "R")
    
    # Datos Bancarios
    if empresa.get("datos_bancarios"):
        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, "DATOS DE PAGO / BANCOS:", ln=True)
        pdf.set_font("Helvetica", size=9)
        pdf.multi_cell(0, 5, empresa['datos_bancarios'])

    return bytes(pdf.output())
# ==========================================
# MÓDULO 1: REGISTRO Y EDICIÓN DE EMPRESAS
# ==========================================
if opcion == "1. Empresas":
    st.title("🏢 Gestión de Empresas Cotizadoras")
    st.write("Registra o edita los datos de la empresa, su logotipo y el sello/firma.")

    # Consultar empresas existentes
    try:
        res = supabase.table("empresas").select("*").execute()
        empresas = res.data
    except Exception as e:
        st.error("🚨 Error al consultar la tabla 'empresas' de Supabase:")
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

    # Valores por defecto para el formulario
    nombre_val = empresa_sel["nombre"] if empresa_sel else ""
    direccion_val = empresa_sel["direccion"] if empresa_sel else ""
    rif_val = empresa_sel["rif"] if empresa_sel else ""
    bancos_val = empresa_sel["datos_bancarios"] if empresa_sel else ""

    with st.form("form_empresa", clear_on_submit=False):
        nombre = st.text_input("Nombre de la Empresa *", value=nombre_val)
        rif = st.text_input("Número de RIF / Tax ID *", value=rif_val)
        direccion = st.text_area("Dirección Fiscal", value=direccion_val)
        datos_bancarios = st.text_area("Datos Bancarios para Transferencias", value=bancos_val, help="Ejemplo: Banco X, Cuenta Nro..., SWIFT...")

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

            # Subir Logo a Supabase Storage
            if logo_file:
                ext = logo_file.name.split(".")[-1]
                path_logo = f"logos/{uuid.uuid4()}.{ext}"
                supabase.storage.from_("archivos-cotizador").upload(
                    path=path_logo, 
                    file=logo_file.getvalue(), 
                    file_options={"content-type": logo_file.type, "upsert": "true"}
                )
                logo_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_logo)

            # Subir Sello/Firma a Supabase Storage
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
                # Actualizar
                supabase.table("empresas").update(datos_empresa).eq("id", empresa_sel["id"]).execute()
                st.success(f"¡Empresa '{nombre}' actualizada correctamente!")
            else:
                # Insertar
                supabase.table("empresas").insert(datos_empresa).execute()
                st.success(f"¡Empresa '{nombre}' registrada con éxito!")
            
            st.rerun()

# ==========================================
# MÓDULOS EN CONSTRUCCIÓN
# ==========================================
elif opcion == "2. Cotizar":
    st.title("📝 Generar Nueva Cotización")
    
    # Cargar empresas registradas
    try:
        res = supabase.table("empresas").select("*").execute()
        empresas = res.data
    except Exception as e:
        st.error("Error al cargar empresas")
        st.stop()
        
    if not empresas:
        st.warning("⚠️ Primero debes registrar al menos una Empresa en el Módulo 1.")
        st.stop()
        
    # Selección de Empresa Emisora
    nombres_emp = [e["nombre"] for e in empresas]
    emp_seleccionada = st.selectbox("Selecciona la Empresa Emisora:", nombres_emp)
    empresa = next(e for e in empresas if e["nombre"] == emp_seleccionada)
    
    st.divider()
    
    # Formulario de Cotización
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("👤 Datos del Cliente")
        cliente_nombre = st.text_input("Nombre / Razon Social del Cliente *")
        cliente_rif = st.text_input("RIF / Tax ID del Cliente")
        cliente_dir = st.text_area("Dirección del Cliente")
        
    with col_c2:
        st.subheader("⚙️ Configuración")
        moneda = st.selectbox("Moneda de la Cotización *", ["USD ($)", "EUR (€)", "RMB (¥)"])
        num_cotizacion = st.text_input("Número de Cotización *", value=f"COT-{datetime.now().strftime('%Y%m%d%H%M')}")

    st.subheader("📦 Productos / Servicios")
    st.write("Agrega o edita las filas directamente en la tabla:")
    
    # Tabla interactiva para productos
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
    
    # Calcular Totales
    df_editado["Subtotal"] = df_editado["Cantidad"] * df_editado["Precio Unitario"]
    total_cotizacion = df_editado["Subtotal"].sum()
    
    st.markdown(f"### 💰 **Total Cotización:** `{moneda} {total_cotizacion:,.2f}`")
    
    if st.button("📄 Generar y Guardar Cotización", use_container_width=True, type="primary"):
        if not cliente_nombre or total_cotizacion <= 0:
            st.error("Por favor ingresa el nombre del cliente y al menos un producto con precio.")
        else:
            # Preparar lista de items
            items_list = []
            for _, row in df_editado.iterrows():
                items_list.append({
                    "descripcion": row["Descripción"],
                    "cantidad": int(row["Cantidad"]),
                    "precio": float(row["Precio Unitario"]),
                    "subtotal": float(row["Subtotal"])
                })
                
            # Generar PDF
            pdf_bytes = crear_pdf_cotizacion(
                empresa, cliente_nombre, cliente_rif, cliente_dir, moneda,
                items_list, total_cotizacion, total_cotizacion, num_cotizacion
            )
            
            # Guardar PDF en Supabase Storage
            path_pdf = f"cotizaciones/{num_cotizacion}_{uuid.uuid4()}.pdf"
            supabase.storage.from_("archivos-cotizador").upload(
                path=path_pdf, 
                file=pdf_bytes, 
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            pdf_url = supabase.storage.from_("archivos-cotizador").get_public_url(path_pdf)
            
            # Guardar Registro en la Base de Datos
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
            
            supabase.table("cotizaciones").insert(datos_cotizacion).execute()
            
            st.success("🎉 ¡Cotización generada y guardada con éxito!")
            st.download_button(
                label="⬇️ Descargar Cotización en PDF",
                data=pdf_bytes,
                file_name=f"{num_cotizacion}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

elif opcion == "3. Historial":
    st.title("📚 Historial de Cotizaciones")
    st.info("Próximamente: Lista de cotizaciones emitidas y descargas.")
