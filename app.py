import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io

# Configuración de página
st.set_page_config(page_title="Wärtsilä Maintenance Hub", layout="wide")

# --- ESTILOS PERSONALIZADOS ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stAlert { border-radius: 10px; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXIÓN A SUPABASE (SQL) ---
conn = st.connection("sql")

def cargar_datos():
    try:
        df = conn.query("SELECT * FROM historial", ttl=0)
        # Asegurarnos de tener una columna ID para poder borrar con precisión si la base de datos la tiene
        return df
    except Exception:
        return pd.DataFrame(columns=[
            'Fecha', 'Motogenerador', 'Motor', 'Responsable',
            'P_kW', 'P_V_Nom', 'P_I_Nom', 'P_RPM',
            'V1', 'V2', 'V3', 'V_Prom', 'V_Desb_%',
            'I1', 'I2', 'I3', 'I_Prom', 'I_Desb_%',
            'Vib_LA', 'Temp_C', 'Alarma_General', 'Observaciones'
        ])

def guardar_en_nube(nuevo_df):
    try:
        nuevo_df.to_sql("historial", con=conn.engine, if_exists="append", index=False)
        return True
    except Exception as e:
        st.error(f"❌ ERROR REAL DE SUPABASE: {e}")
        return False

def borrar_en_nube(motogenerador, motor, fecha):
    try:
        # Borrado seguro por composición de llave (Fecha, MG, Motor)
        query = f"DELETE FROM historial WHERE \"Fecha\" = '{fecha}' AND \"Motogenerador\" = '{motogenerador}' AND \"Motor\" = '{motor}'"
        with conn.engine.connect() as con:
            con.execute(go.net.sql.text(query) if hasattr(go, 'net') else query) # Dependiendo de tu versión de sqlalchemy
        return True
    except Exception as e:
        # Si falla SQL directo, intentamos mediante una query de texto normal de la conexión
        try:
            conn.session.execute(f"DELETE FROM historial WHERE \"Fecha\" = '{fecha}' AND \"Motogenerador\" = '{motogenerador}' AND \"Motor\" = '{motor}'")
            conn.session.commit()
            return True
        except Exception as e2:
            st.error(f"❌ No se pudo borrar de la base de datos: {e2}")
            return False

# Carga inicial a la memoria
if 'local_db' not in st.session_state:
    st.session_state.local_db = cargar_datos()

# --- CONSTANTES DE LA RUTA DE INSPECCIÓN ---
MOTOGENERADORES = ["ZAN 100", "ZAN 102", "ZAN 104", "ZAN 106"]
MOTORES = [f"M{str(i).zfill(3)}" for i in range(1, 11)]

# Generamos la lista ordenada de toda la ruta de inspección
RUTA_INSPECCION = []
for mg in MOTOGENERADORES:
    for mot in MOTORES:
        RUTA_INSPECCION.append({"mg": mg, "motor": mot})

# Inicialización de estados de la inspección en progreso
if 'inspeccion_progreso' not in st.session_state:
    st.session_state.inspeccion_progreso = []
if 'idx_ruta' not in st.session_state:
    st.session_state.idx_ruta = 0
if 'en_inspeccion' not in st.session_state:
    st.session_state.en_inspeccion = False
if 'fecha_inspeccion' not in st.session_state:
    st.session_state.fecha_inspeccion = None
if 'resp_inspeccion' not in st.session_state:
    st.session_state.resp_inspeccion = ""

def calcular_desbalance(val1, val2, val3):
    if val1 == 0 or val2 == 0 or val3 == 0: return 0.0, 0.0
    promedio = (val1 + val2 + val3) / 3
    max_dev = max(abs(val1 - promedio), abs(val2 - promedio), abs(val3 - promedio))
    desbalance = (max_dev / promedio) * 100
    return round(promedio, 2), round(desbalance, 2)

# --- CABECERA ---
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.image("https://www.wartsila.com/images/default-source/brand-portal/logo/w_logo_color_pos_rgb.png", width=120)
with col_title:
    st.title("Trazabilidad de Motores de Enfriamiento")
    st.caption("Cumplimiento normativo ISO 10816-3 | NEMA MG1")

# --- SIDEBAR ---
menu = st.sidebar.radio(
    "Navegación", 
    ["📊 Dashboard", "📝 Nueva Inspección", "📘 Info & Normativas"]
)

# -------------------------------------------------------------
# MÓDULO: NUEVA INSPECCIÓN ( FLUJO SECUENCIAL )
# -------------------------------------------------------------
if menu == "📝 Nueva Inspección":
    st.subheader("Ruta de Inspección Automatizada")

    # Si no ha iniciado la ruta, pedimos datos generales
    if not st.session_state.en_inspeccion:
        st.info("📋 Inicializar nueva jornada de inspección completa")
        with st.form("init_inspeccion"):
            f_fecha = st.date_input("Fecha de la Inspección")
            f_resp = st.text_input("Técnico Responsable")
            
            if st.form_submit_button("▶️ COMENZAR RUTA EN ORDEN (ZAN 100 -> ZAN 106)"):
                if not f_resp:
                    st.error("Por favor ingrese el nombre del Técnico Responsable.")
                else:
                    st.session_state.fecha_inspeccion = f_fecha.strftime('%Y-%m-%d')
                    st.session_state.resp_inspeccion = f_resp
                    st.session_state.idx_ruta = 0
                    st.session_state.inspeccion_progreso = []
                    st.session_state.en_inspeccion = True
                    st.rerun()
    else:
        # Estamos en medio de la inspección
        total_motores = len(RUTA_INSPECCION)
        progreso_actual = st.session_state.idx_ruta
        progreso_porcentaje = progreso_actual / total_motores
        
        st.progress(progreso_porcentaje, text=f"Progreso: Motor {progreso_actual} de {total_motores}")
        
        # Obtener el equipo actual según el índice de la ruta
        equipo_actual = RUTA_INSPECCION[progreso_actual]
        mg_actual = equipo_actual["mg"]
        motor_actual = equipo_actual["motor"]
        
        st.warning(f"🔎 **Evaluando actualmente:** {mg_actual} ➔ {motor_actual}")
        
        # Mostramos si ya se había rellenado en este intento para poder corregirlo
        ya_registrado = False
        registro_previo = None
        for reg in st.session_state.inspeccion_progreso:
            if reg["Motogenerador"] == mg_actual and reg["Motor"] == motor_actual:
                ya_registrado = True
                registro_previo = reg
                break

        if ya_registrado:
            st.success(f"✅ ¡Este motor ya tiene una medición guardada en este turno! Puedes modificarla abajo y presionar Guardar de nuevo.")

        with st.form("form_registro_secuencial"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Ubicación fija:** {mg_actual} | **ID:** {motor_actual}")
                st.write(f"**Responsable:** {st.session_state.resp_inspeccion} | **Fecha:** {st.session_state.fecha_inspeccion}")
            with c2:
                st.write("**Datos de Placa (Nominales)**")
                cp1, cp2 = st.columns(2)
                f_p_kw = cp1.number_input("Potencia (kW)", value=float(registro_previo["P_kW"]) if ya_registrado else 11.0)
                f_p_v = cp2.number_input("Voltaje Nom (V)", value=float(registro_previo["P_V_Nom"]) if ya_registrado else 440.0)
                f_p_i = cp1.number_input("Corriente Nom (A)", value=float(registro_previo["P_I_Nom"]) if ya_registrado else 19.0)
                f_p_rpm = cp2.number_input("RPM", value=int(registro_previo["P_RPM"]) if ya_registrado else 1760)

            st.divider()
            v_col, i_col, m_col = st.columns(3)
            
            with v_col:
                st.write("**Voltajes de Fase (V)**")
                f_v1 = st.number_input("V1-2", min_value=0.0, step=1.0, value=float(registro_previo["V1"]) if ya_registrado else 0.0)
                f_v2 = st.number_input("V2-3", min_value=0.0, step=1.0, value=float(registro_previo["V2"]) if ya_registrado else 0.0)
                f_v3 = st.number_input("V3-1", min_value=0.0, step=1.0, value=float(registro_previo["V3"]) if ya_registrado else 0.0)
                
            with i_col:
                st.write("**Corrientes de Fase (A)**")
                f_i1 = st.number_input("L1", min_value=0.0, step=0.1, value=float(registro_previo["I1"]) if ya_registrado else 0.0)
                f_i2 = st.number_input("L2", min_value=0.0, step=0.1, value=float(registro_previo["I2"]) if ya_registrado else 0.0)
                f_i3 = st.number_input("L3", min_value=0.0, step=0.1, value=float(registro_previo["I3"]) if ya_registrado else 0.0)
                
            with m_col:
                st.write("**Mecánicos y Térmicos**")
                f_vib = st.number_input("Vibración LA (mm/s)", step=0.1, value=float(registro_previo["Vib_LA"]) if ya_registrado else 0.0)
                f_temp = st.number_input("Temperatura (°C)", step=1.0, value=float(registro_previo["Temp_C"]) if ya_registrado else 0.0)
                f_obs = st.text_area("Observaciones", value=registro_previo["Observaciones"] if ya_registrado else "")

            # Controles del formulario
            col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
            
            with col_b1:
                btn_atras = st.form_submit_button("⬅️ ANTERIOR", use_container_width=True)
            with col_b2:
                btn_guardar = st.form_submit_button("💾 TEMPORAL: CONFIRMAR MEDICIÓN", use_container_width=True)
            with col_b3:
                btn_siguiente = st.form_submit_button("SIGUIENTE ➡️", use_container_width=True)

            if btn_guardar:
                v_prom, v_desb = calcular_desbalance(f_v1, f_v2, f_v3)
                i_prom, i_desb = calcular_desbalance(f_i1, f_i2, f_i3)
                
                alarma = "NORMAL ✅"
                if i_desb > 10 or f_vib > 4.5 or v_desb > 3: alarma = "CRÍTICO 🚨"
                elif i_desb > 5 or f_vib > 2.8 or v_desb > 1: alarma = "ALERTA ⚠️"

                nuevo_reg = {
                    'Fecha': st.session_state.fecha_inspeccion, 'Motogenerador': mg_actual, 'Motor': motor_actual, 'Responsable': st.session_state.resp_inspeccion,
                    'P_kW': f_p_kw, 'P_V_Nom': f_p_v, 'P_I_Nom': f_p_i, 'P_RPM': f_p_rpm,
                    'V1': f_v1, 'V2': f_v2, 'V3': f_v3, 'V_Prom': v_prom, 'V_Desb_%': v_desb,
                    'I1': f_i1, 'I2': f_i2, 'I3': f_i3, 'I_Prom': i_prom, 'I_Desb_%': i_desb,
                    'Vib_LA': f_vib, 'Temp_C': f_temp, 'Alarma_General': alarma, 'Observaciones': f_obs
                }
                
                # Si ya existía en la lista de este turno, lo eliminamos primero para actualizarlo
                if ya_registrado:
                    st.session_state.inspeccion_progreso = [r for r in st.session_state.inspeccion_progreso if not (r["Motogenerador"] == mg_actual and r["Motor"] == motor_actual)]
                
                st.session_state.inspeccion_progreso.append(nuevo_reg)
                st.toast(f"✔️ {mg_actual} - {motor_actual} Registrado localmente", icon="💾")
                st.rerun()

            if btn_atras:
                if st.session_state.idx_ruta > 0:
                    st.session_state.idx_ruta -= 1
                    st.rerun()

            if btn_siguiente:
                if not ya_registrado:
                    st.error("⚠️ Debes 'CONFIRMAR MEDICIÓN' antes de avanzar de motor.")
                elif st.session_state.idx_ruta < total_motores - 1:
                    st.session_state.idx_ruta += 1
                    st.rerun()

        # Botón maestro para finalizar todo y subir a la nube
        st.divider()
        col_cancelar, col_finalizar = st.columns(2)
        
        with col_cancelar:
            if st.button("❌ Cancelar Inspección (Borrar Progreso actual)", use_container_width=True):
                st.session_state.en_inspeccion = False
                st.rerun()
                
        with col_finalizar:
            total_registrados = len(st.session_state.inspeccion_progreso)
            if st.button(f"🚀 FINALIZAR Y ENVIAR JORNADA ({total_registrados}/{total_motores} Motores)", type="primary", use_container_width=True):
                if total_registrados == 0:
                    st.error("No has guardado ninguna medición válida todavía.")
                else:
                    df_inspeccion_completa = pd.DataFrame(st.session_state.inspeccion_progreso)
                    
                    # Guardamos masivamente en la nube
                    exito = guardar_en_nube(df_inspeccion_completa)
                    if exito:
                        # Unimos al dataframe en memoria
                        st.session_state.local_db = pd.concat([st.session_state.local_db, df_inspeccion_completa], ignore_index=True)
                        st.success(f"🎉 ¡Inspección completa guardada exitosamente en Supabase! Se subieron {total_registrados} registros.")
                        # Reseteamos variables de flujo
                        st.session_state.en_inspeccion = False
                        st.session_state.inspeccion_progreso = []
                        st.session_state.idx_ruta = 0
                    else:
                        st.error("No se pudo subir la inspección masiva. Verifica la consola o los errores superiores.")

# -------------------------------------------------------------
# MÓDULO: DASHBOARD ( CON BORRADO Y EXCEL ÚNICO )
# -------------------------------------------------------------
elif menu == "📊 Dashboard":
    df = st.session_state.local_db
    
    if df.empty:
        st.info("No hay datos registrados aún. Registra tu primera inspección para ver el panel.")
    else:
        # --- FILTROS DE VISUALIZACIÓN ---
        c1, c2 = st.columns(2)
        f_mg = c1.multiselect("Filtrar Motogenerador", df['Motogenerador'].unique(), default=df['Motogenerador'].unique())
        f_motor = c2.selectbox("Filtrar Motor", ["Todos"] + list(df['Motor'].unique()))
        
        df_f = df[df['Motogenerador'].isin(f_mg)]
        if f_motor != "Todos": df_f = df_f[df_f['Motor'] == f_motor]

        st.subheader("📋 Resumen de Estado Actual")
        
        def highlight_alarms(val):
            if "🚨" in str(val): return 'background-color: #ff4b4b; color: white'
            if "⚠️" in str(val): return 'background-color: #ffeb3b; color: black'
            return 'background-color: #c8e6c9; color: black'

        st.dataframe(
            df_f.style.map(highlight_alarms, subset=['Alarma_General'])
            .format("{:.2f}", subset=['V_Desb_%', 'I_Desb_%', 'Vib_LA', 'I_Prom']),
            use_container_width=True
        )

        # --- SECCIÓN: ACCIONES DE BORRADO ---
        with st.expander("🗑️ Zona de Eliminación de Registros"):
            st.write("Selecciona una fila específica que desees eliminar de forma permanente:")
            # Creamos una columna temporal de selección combinada
            df_f['Llave_Eliminar'] = df_f['Fecha'] + " | " + df_f['Motogenerador'] + " | " + df_f['Motor']
            registro_a_borrar = st.selectbox("Seleccione el registro a eliminar:", ["Ninguno"] + list(df_f['Llave_Eliminar'].unique()))
            
            if registro_a_borrar != "Ninguno":
                # Extraer datos de la selección
                partes = registro_a_borrar.split(" | ")
                v_fecha, v_mg, v_motor = partes[0], partes[1], partes[2]
                
                st.warning(f"¿Estás seguro de que deseas eliminar el registro del **{v_fecha}** para el **{v_mg} ({v_motor})**?")
                if st.button("💥 CONFIRMAR ELIMINACIÓN PERMANENTE", use_container_width=True):
                    # 1. Borrar en nube
                    if borrar_en_nube(v_mg, v_motor, v_fecha):
                        # 2. Borrar local
                        st.session_state.local_db = st.session_state.local_db[
                            ~((st.session_state.local_db['Fecha'] == v_fecha) & 
                              (st.session_state.local_db['Motogenerador'] == v_mg) & 
                              (st.session_state.local_db['Motor'] == v_motor))
                        ]
                        st.success("Registro eliminado correctamente.")
                        st.rerun()

        # --- SECCIÓN: DESCARGA DE REPORTES (SOLO EXCEL) ---
        st.divider()
        st.subheader("📥 Descargar Reporte Diario (Excel)")
        
        fechas_disponibles = sorted(df['Fecha'].unique(), reverse=True)
        fecha_sel = st.selectbox("Seleccione la fecha para generar el reporte:", fechas_disponibles)
        
        if fecha_sel:
            df_reporte = df[df['Fecha'] == fecha_sel]
            st.write(f"Se encontraron **{len(df_reporte)}** registros para el día **{fecha_sel}**.")
            
            # Generar solo Excel
            buffer = io.BytesIO()
            try:
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_reporte.to_excel(writer, index=False, sheet_name=f"Datos_{fecha_sel}")
                
                st.download_button(
                    label=f"📊 Descargar Excel ({fecha_sel})",
                    data=buffer.getvalue(),
                    file_name=f"Reporte_Wartsila_{fecha_sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.error("Error al generar archivo de Excel. Asegúrate de que 'openpyxl' esté en requirements.txt")

        # --- GRÁFICAS DE TENDENCIAS ---
        st.divider()
        st.subheader("📈 Análisis de Tendencias y Límites")
        
        tab_i, tab_v, tab_vib = st.tabs(["Corrientes", "Voltajes", "Vibración"])
        
        with tab_i:
            if not df_f.empty:
                fig_i = go.Figure()
                fig_i.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['I_Desb_%'], name="Desbalance I%", mode='lines+markers'))
                fig_i.add_hline(y=5, line_dash="dash", line_color="orange", annotation_text="Alerta (5%)")
                fig_i.add_hline(y=10, line_dash="dash", line_color="red", annotation_text="Crítico (10%)")
                fig_i.update_layout(title="Desbalance de Corriente (%)")
                st.plotly_chart(fig_i, use_container_width=True)

        with tab_v:
            if not df_f.empty:
                fig_v = go.Figure()
                fig_v.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['V_Desb_%'], name="Desbalance V%", mode='lines+markers', line_color='purple'))
                fig_v.add_hline(y=1, line_dash="dash", line_color="orange", annotation_text="Alerta (1%)")
                fig_v.add_hline(y=3, line_dash="dash", line_color="red", annotation_text="Crítico (3%)")
                fig_v.update_layout(title="Desbalance de Voltaje (%)")
                st.plotly_chart(fig_v, use_container_width=True)
                
        with tab_vib:
            if not df_f.empty:
                fig_vib = go.Figure()
                fig_vib.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Vib_LA'], name="Vibración LA", mode='lines+markers', line_color='green'))
                fig_vib.add_hline(y=2.8, line_dash="dash", line_color="orange", annotation_text="Satisfactorio (2.8 mm/s)")
                fig_vib.add_hline(y=4.5, line_dash="dash", line_color="red", annotation_text="Crítico (4.5 mm/s)")
                fig_vib.update_layout(title="Severidad Vibratoria (mm/s RMS)")
                st.plotly_chart(fig_vib, use_container_width=True)

# -------------------------------------------------------------
# MÓDULO: INFO & NORMATIVAS
# -------------------------------------------------------------
elif menu == "📘 Info & Normativas":
    st.header("📘 Documentación Técnica y Guía de Uso")
    tab_info, tab_norm = st.tabs(["📖 Guía de Uso", "📐 Normativas y Fórmulas"])
    
    with tab_info:
        st.subheader("Instrucciones de la Plataforma")
        st.markdown("""
        **1. Registrar una Nueva Inspección:** Inicializa la jornada, llena los datos de placa y mediciones. Debes confirmar la medición antes de avanzar al siguiente motor.
        **2. Finalizar Jornada:** Al terminar todos los motores, pulsa el botón maestro inferior para enviar todo a la nube.
        **3. Borrar Datos:** En el Dashboard encontrarás un menú desplegable para eliminar registros erróneos.
        """)
        
    with tab_norm:
        st.subheader("Criterios de Evaluación y Fórmulas")
        st.markdown("#### 1. Desbalance Eléctrico (Normativa NEMA MG1)")
        st.latex(r"\text{Desbalance (\%)} = \frac{\text{Máxima desviación del promedio}}{\text{Promedio}} \times 100")
        
        c_v, c_i = st.columns(2)
        with c_v:
            st.markdown("**Límites de Voltaje:**\n- **Normal:** $\le 1\%$\n- **Alerta ⚠️:** $> 1\%$ a $3\%$\n- **Crítico 🚨:** $> 3\%$")
        with c_i:
            st.markdown("**Límites de Corriente:**\n- **Normal:** $\le 5\%$\n- **Alerta ⚠️:** $> 5\%$ a $10\%$\n- **Crítico 🚨:** $> 10\%$")
            
        st.divider()
        st.markdown("#### 2. Severidad Vibratoria (Normativa ISO 10816-3)")
        st.markdown("**Límites (Máquinas Clase II):**\n- **Normal:** $\le 2.8 \text{ mm/s RMS}$\n- **Alerta ⚠️:** $> 2.8 \text{ mm/s a } 4.5 \text{ mm/s RMS}$\n- **Crítico 🚨:** $> 4.5 \text{ mm/s RMS}$")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Wärtsilä Ecuador Maintenance Hub v4.0 (Ruta de Inspección)")
