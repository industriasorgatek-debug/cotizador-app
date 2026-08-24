import streamlit as st
from supabase import create_client, Client
import uuid

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
    st.info("Próximamente: Módulo para cotizar en USD, EUR, RMB con generación de PDF.")

elif opcion == "3. Historial":
    st.title("📚 Historial de Cotizaciones")
    st.info("Próximamente: Lista de cotizaciones emitidas y descargas.")
