import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Calculadora de Pasivos Pensionales",
    page_icon="⚖️",
    layout="wide"
)

# --- LÓGICA ACTUARIAL ---

def obtener_tabla_mortalidad():
    """
    Simulación de la Tabla de Mortalidad RV08 (Rentistas Válidos 2008).
    En un entorno real, aquí se cargaría el CSV oficial de la Superfinanciera.
    """
    edades = np.arange(0, 111)
    # Modelo simplificado de Gompertz-Makeham para propósitos ilustrativos
    # qx = prob. de morir a la edad x
    qx = 0.0001 + 0.00001 * (1.1 ** edades)
    qx = np.clip(qx, 0, 1)
    qx[-1] = 1.0 # Probabilidad 1 a los 110 años
    return pd.DataFrame({'Edad': edades, 'qx': qx})

def calcular_renta_vitalicia(edad_inicio, sexo, tasa_interes, tablas):
    """
    Calcula el Factor de Renta Vitalicia Inmediata (a_x).
    """
    i = tasa_interes / 100
    v = 1 / (1 + i) # Factor de descuento
    
    # Filtrar tablas desde la edad de inicio
    tabla_actual = tablas[tablas['Edad'] >= edad_inicio].copy()
    tabla_actual['px'] = 1 - tabla_actual['qx']
    
    # Supervivencia acumulada (npx)
    tabla_actual['npx'] = tabla_actual['px'].shift(1, fill_value=1).cumprod()
    
    # Valor presente de cada pago
    tabla_actual['t'] = np.arange(len(tabla_actual))
    tabla_actual['VP_pago'] = (v ** tabla_actual['t']) * tabla_actual['npx']
    
    factor_ax = tabla_actual['VP_pago'].sum()
    return factor_ax, tabla_actual

# --- INTERFAZ DE USUARIO ---

st.title("⚖️ Liquidación de Pasivos Pensionales")
st.markdown("""
Esta herramienta realiza cálculos de reserva actuarial basados en los principios de **Pasivocol**, 
utilizando tasas técnicas y tablas de mortalidad reguladas en Colombia.
""")

with st.sidebar:
    st.header("Parámetros de Cálculo")
    
    nombre = st.text_input("Nombre del Causante", "Juan Pérez")
    fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=datetime(1965, 5, 20))
    sexo = st.selectbox("Sexo", ["Masculino", "Femenino"])
    
    st.divider()
    
    ibl = st.number_input("Ingreso Base de Liquidación (IBL) $", min_value=1300000, value=2500000, step=100000)
    tasa_tecnica = st.selectbox("Tasa Técnica Anual (%)", [4.0, 4.8], index=0, help="4.0% es la estándar para reservas según la normativa.")
    
    tipo_tabla = st.selectbox("Tabla de Mortalidad", ["RV08 (Rentistas Válidos)", "ISS 2008 (Experiencia General)"])
    
    calcular = st.button("Calcular Liquidación", type="primary")

# Cálculo de edad actual
hoy = datetime.now()
edad_actual = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))

if calcular:
    tablas = obtener_tabla_mortalidad()
    factor, detalle_tabla = calcular_renta_vitalicia(edad_actual, sexo, tasa_tecnica, tablas)
    
    reserva_total = factor * ibl * 13 # Se incluyen 13 mesadas anuales por ley en Colombia
    
    # --- RESULTADOS PRINCIPALES ---
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Edad del Sujeto", f"{edad_actual} años")
    with col2:
        st.metric("Factor Actuarial (ax)", f"{factor:.4f}")
    with col3:
        st.metric("Reserva Total Estimada", f"${reserva_total:,.0f}")

    # --- GRÁFICOS ---
    st.subheader("Análisis de Supervivencia y Descuento")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=detalle_tabla['Edad'], y=detalle_tabla['npx'], name="Prob. Supervivencia (npx)", fill='tozeroy'))
    fig.add_trace(go.Scatter(x=detalle_tabla['Edad'], y=detalle_tabla['VP_pago'], name="Valor Presente de Pagos", line=dict(dash='dash')))
    
    fig.update_layout(
        title="Curva de Probabilidad y Descuento Financiero",
        xaxis_title="Edad",
        yaxis_title="Probabilidad / Valor Relativo",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- TABLA DE DETALLE ---
    with st.expander("Ver detalle de flujos actuariales"):
        st.dataframe(
            detalle_tabla[['Edad', 'qx', 'npx', 'VP_pago']].style.format({
                'qx': '{:.6f}',
                'npx': '{:.4f}',
                'VP_pago': '{:.4f}'
            }),
            use_container_width=True
        )

    # Botón de descarga
    csv = detalle_tabla.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Descargar Reporte en CSV",
        data=csv,
        file_name=f"liquidacion_{nombre}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime='text/csv',
    )
else:
    st.info("Configure los parámetros en la barra lateral y haga clic en 'Calcular Liquidación' para ver los resultados.")

st.divider()
st.caption("Aviso legal: Este aplicativo es una herramienta educativa y de referencia. Los cálculos oficiales deben ser validados por un actuario certificado.")
