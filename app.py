import streamlit as st
import pandas as pd
import plotly.graph_objects as go

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

# --- MODIFICA TU FUNCIÓN DE CARGAR DATOS ---
def cargar_datos():
    try:
        df = conn.query("SELECT * FROM historial", ttl=0)
        return df
    except Exception:
        # Silenciamos el error. Si la tabla no existe, simplemente devolvemos la estructura vacía
        return pd.DataFrame(columns=[
            'Fecha', 'Motogenerador', 'Motor', 'Responsable',
            'P_kW', 'P_V_Nom', 'P_I_Nom', 'P_RPM',
            'V1', 'V2', 'V3', 'V_Prom', 'V_Desb_%',
            'I1', 'I2', 'I3', 'I_Prom', 'I_Desb_%',
            'Vib_LA', 'Temp_C', 'Alarma_General', 'Observaciones'
        ])

# --- MODIFICA TU FUNCIÓN DE GUARDAR EN LA NUBE ---
def guardar_en_nube(nuevo_df):
    try:
        nuevo_df.to_sql("historial", con=conn.engine, if_exists="append", index=False)
        return True # Retorna True si se guardó con éxito
    except Exception as e:
        st.error(f"❌ ERROR REAL DE SUPABASE: {e}")
        return False # Retorna False si falló

# Carga inicial a la memoria
if 'local_db' not in st.session_state:
    st.session_state.local_db = cargar_datos()

def calcular_desbalance(val1, val2, val3):
    if val1 == 0 or val2 == 0 or val3 == 0: return 0.0, 0.0
    promedio = (val1 + val2 + val3) / 3
    max_dev = max(abs(val1 - promedio), abs(val2 - promedio), abs(abs(val3 - promedio)))
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
# MÓDULO: NUEVA INSPECCIÓN
# -------------------------------------------------------------
if menu == "📝 Nueva Inspección":
    st.subheader("Registro de Datos Técnicos")
    
    with st.form("form_inspeccion"):
        c1, c2 = st.columns(2)
        
        with c1:
            st.info("📍 Ubicación y Equipo")
            f_fecha = st.date_input("Fecha")
            f_mg = st.selectbox("Motogenerador", ["ZAN 100", "ZAN 102", "ZAN 104", "ZAN 106"])
            f_motor = st.selectbox("Motor ID", [f"M{str(i).zfill(3)}" for i in range(1, 11)])
            f_resp = st.text_input("Técnico Responsable")

        with c2:
            st.success("📋 Datos de Placa (Nominales)")
            cp1, cp2 = st.columns(2)
            f_p_kw = cp1.number_input("Potencia (kW)", value=11.0)
            f_p_v = cp2.number_input("Voltaje Nom (V)", value=440.0)
            f_p_i = cp1.number_input("Corriente Nom (A)", value=19.0)
            f_p_rpm = cp2.number_input("RPM", value=1760)

        st.divider()
        st.warning("⚡ Toma de Datos en Operación")
        v_col, i_col, m_col = st.columns(3)
        
        with v_col:
            st.write("**Voltajes de Fase (V)**")
            f_v1 = st.number_input("V1-2", min_value=0.0, step=1.0)
            f_v2 = st.number_input("V2-3", min_value=0.0, step=1.0)
            f_v3 = st.number_input("V3-1", min_value=0.0, step=1.0)
            
        with i_col:
            st.write("**Corrientes de Fase (A)**")
            f_i1 = st.number_input("L1", min_value=0.0, step=0.1)
            f_i2 = st.number_input("L2", min_value=0.0, step=0.1)
            f_i3 = st.number_input("L3", min_value=0.0, step=0.1)
            
        with m_col:
            st.write("**Mecánicos y Térmicos**")
            f_vib = st.number_input("Vibración LA (mm/s)", step=0.1)
            f_temp = st.number_input("Temperatura (°C)", step=1.0)
            f_obs = st.text_area("Observaciones")

# --- MODIFICA EL BLOQUE DEL BOTÓN ---
        if st.form_submit_button("💾 GUARDAR REGISTRO", use_container_width=True):
            v_prom, v_desb = calcular_desbalance(f_v1, f_v2, f_v3)
            i_prom, i_desb = calcular_desbalance(f_i1, f_i2, f_i3)
            
            alarma = "NORMAL ✅"
            if i_desb > 10 or f_vib > 4.5 or v_desb > 3: alarma = "CRÍTICO 🚨"
            elif i_desb > 5 or f_vib > 2.8 or v_desb > 1: alarma = "ALERTA ⚠️"

            # Nota: Convertimos la fecha a texto (string) para evitar errores de tipo en PostgreSQL
            nuevo_reg = {
                'Fecha': f_fecha.strftime('%Y-%m-%d'), 'Motogenerador': f_mg, 'Motor': f_motor, 'Responsable': f_resp,
                'P_kW': f_p_kw, 'P_V_Nom': f_p_v, 'P_I_Nom': f_p_i, 'P_RPM': f_p_rpm,
                'V1': f_v1, 'V2': f_v2, 'V3': f_v3, 'V_Prom': v_prom, 'V_Desb_%': v_desb,
                'I1': f_i1, 'I2': f_i2, 'I3': f_i3, 'I_Prom': i_prom, 'I_Desb_%': i_desb,
                'Vib_LA': f_vib, 'Temp_C': f_temp, 'Alarma_General': alarma, 'Observaciones': f_obs
            }
            
            nuevo_df = pd.DataFrame([nuevo_reg])
            
            # 1. Intentamos guardar en la nube primero
            se_guardo_en_nube = guardar_en_nube(nuevo_df)
            
            # 2. SOLO si Supabase lo aceptó, actualizamos la app y reiniciamos
            if se_guardo_en_nube:
                st.session_state.local_db = pd.concat([st.session_state.local_db, nuevo_df], ignore_index=True)
                st.success("¡Registro guardado exitosamente!")
                st.rerun()
            else:
                # Si falló, la app se detiene aquí y podrás leer el recuadro rojo con el error de Supabase
                st.warning("⚠️ El registro no se pudo guardar en la nube. Revisa el mensaje de error de arriba.")

# -------------------------------------------------------------
# MÓDULO: DASHBOARD
# -------------------------------------------------------------
elif menu == "📊 Dashboard":
    df = st.session_state.local_db
    
    if df.empty:
        st.info("No hay datos registrados aún. Registra tu primera inspección para ver el panel.")
    else:
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

        st.divider()
        st.subheader("📈 Análisis de Tendencias y Límites")
        
        tab_i, tab_v, tab_vib = st.tabs(["Corrientes", "Voltajes", "Vibración"])
        
        with tab_i:
            fig_i = go.Figure()
            fig_i.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['I_Desb_%'], name="Desbalance I%", mode='lines+markers'))
            fig_i.add_hline(y=5, line_dash="dash", line_color="orange", annotation_text="Alerta (5%)")
            fig_i.add_hline(y=10, line_dash="dash", line_color="red", annotation_text="Crítico (10%)")
            fig_i.update_layout(title="Desbalance de Corriente (%)", yaxis_range=[0, max(df_f['I_Desb_%'].max()+2 if not df_f.empty else 12, 12)])
            st.plotly_chart(fig_i, use_container_width=True)

        with tab_v:
            fig_v = go.Figure()
            fig_v.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['V_Desb_%'], name="Desbalance V%", mode='lines+markers', line_color='purple'))
            fig_v.add_hline(y=1, line_dash="dash", line_color="orange", annotation_text="Alerta (1%)")
            fig_v.add_hline(y=3, line_dash="dash", line_color="red", annotation_text="Crítico (3%)")
            fig_v.update_layout(title="Desbalance de Voltaje (%)")
            st.plotly_chart(fig_v, use_container_width=True)
            
        with tab_vib:
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
        **1. Registrar una Nueva Inspección:** Llena los datos de placa y las mediciones operativas.
        **2. Visualizar el Dashboard:** Filtra por Motor y observa los umbrales de seguridad en las gráficas.
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
st.sidebar.caption("Wärtsilä Ecuador Maintenance Hub v3.0 (Supabase)")
