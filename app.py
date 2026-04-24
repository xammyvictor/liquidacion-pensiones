import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go

# Configuración de página
st.set_page_config(page_title="Liquidador Pasivocol DTF", page_icon="🏦", layout="wide")

# --- FUNCIONES DE PROCESAMIENTO DE EXCEL ---

def cargar_tasas_banrep(file):
    """
    Procesa el formato específico del Banco de la República:
    Hoja: 'Series de datos'
    Columna A: Fecha, Columna B: 1. DTF promedio mensual
    """
    try:
        df = pd.read_excel(file, sheet_name="Series de datos", skiprows=2)
        df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
        
        col_fecha = df.columns[0] 
        col_dtf = [c for c in df.columns if "1. DTF promedio mensual" in c]
        
        if not col_dtf:
            st.error("No se encontró la columna '1. DTF promedio mensual' en el Excel.")
            return None
        
        col_dtf = col_dtf[0]
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        df = df.dropna(subset=[col_fecha, col_dtf])
        
        tasas_map = {}
        for _, row in df.iterrows():
            f = row[col_fecha]
            tasas_map[(f.year, f.month)] = float(row[col_dtf])
            
        return tasas_map
    except Exception as e:
        st.error(f"Error al procesar el Excel: {e}")
        return None

def calcular_interes_pasivocol(capital, tasa_anual, fecha_pago_mesada, fecha_corte):
    """
    Fórmula: I = CP * ((1 + DTF)^(n/365) - 1)
    n = días desde el último día del mes siguiente al pago (Fecha Causación).
    """
    # Fecha Causación: último día del mes siguiente al pago
    fecha_causacion = (fecha_pago_mesada + relativedelta(months=1)).replace(day=1) + relativedelta(months=1, days=-1)
    
    if fecha_corte <= fecha_causacion:
        return 0, 0, fecha_causacion
    
    dias = (fecha_corte - fecha_causacion).days
    i_decimal = tasa_anual / 100
    interes = capital * ((1 + i_decimal)**(dias / 365) - 1)
    return interes, dias, fecha_causacion

# --- INTERFAZ ---

st.title("🏦 Liquidador de Cuotas Partes - Estilo Pasivocol")
st.markdown("Liquidación técnica con **DTF mensual**, selección de **fechas exactas** y **mesadas anualizadas**.")

with st.sidebar:
    st.header("1. Configuración de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=12.0)

    st.divider()
    st.header("2. Datos Generales")
    pensionado = st.text_input("Nombre del Pensionado", "Juan Pérez")
    porcentaje_cp = st.number_input("% Cuota Parte", value=50.0, step=0.1)
    fecha_corte = st.date_input("Fecha de Corte (Liquidación hasta)", value=date.today())

st.subheader("1. Selección del Periodo de Liquidación")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha de Inicio Liquidación", value=date(2022, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha de Fin Liquidación", value=date(2023, 12, 31))

# --- ENTRADA DE MESADAS POR AÑO ---
st.subheader("2. Valor de Mesada por Año")
st.info("Ingrese el valor de la mesada de cada año. El sistema la aplicará automáticamente a todos los meses correspondientes.")

años_rango = list(range(f_inicio.year, f_fin.year + 1))
df_mesadas_anuales = pd.DataFrame({
    "Año": años_rango,
    "Valor_Mesada": [2000000.0] * len(años_rango)
})

edit_mesadas = st.data_editor(
    df_mesadas_anuales,
    column_config={
        "Año": st.column_config.NumberColumn(disabled=True, format="%d"),
        "Valor_Mesada": st.column_config.NumberColumn("Mesada Mensual ($)", format="$ %d")
    },
    use_container_width=True,
    key="mesadas_editor"
)

# Convertir el editor en un diccionario para fácil acceso
mesadas_map = edit_mesadas.set_index("Año")["Valor_Mesada"].to_dict()

# --- PROCESAMIENTO ---
if st.button("🚀 Generar Liquidación Pasivocol", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas cargadas satisfactoriamente.")

    # Generar todos los meses en el rango
    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        # Solo procesar si el mes está dentro del rango solicitado
        anio = fecha_actual.year
        mes = fecha_actual.month
        
        mesada_mensual = mesadas_map.get(anio, 0)
        tasa_aplicable = tasas_db.get((anio, mes), tasa_manual) if tasas_db else tasa_manual
        
        # Iterar para mesada normal y mesadas adicionales (Junio y Diciembre)
        tipos_mesada = ["Normal"]
        if mes == 6: tipos_mesada.append("Prima Junio")
        if mes == 12: tipos_mesada.append("Prima Diciembre")
        
        for tipo in tipos_mesada:
            # Fecha de pago: último día del mes
            f_pago = (fecha_actual + relativedelta(months=1, days=-1))
            
            # Cálculo capital
            cp_principal = mesada_mensual * (porcentaje_cp / 100)
            
            # Cálculo intereses y fecha causación
            interes_v, dias_m, f_causacion = calcular_interes_pasivocol(cp_principal, tasa_aplicable, f_pago, fecha_corte)
            
            resultados.append({
                "Periodo": f"{anio}-{mes:02d}" + (" (Add)" if tipo != "Normal" else ""),
                "Mesada Pensional": mesada_mensual,
                "% Cuota Parte": porcentaje_cp,
                "Cuota Parte": cp_principal,
                "Fecha Causación": f_causacion,
                "Tasa DTF": tasa_aplicable,
                "Días": dias_m,
                "Intereses": interes_v,
                "Total": cp_principal + interes_v
            })
            
        fecha_actual += relativedelta(months=1)

    df_final = pd.DataFrame(resultados)

    # --- RESULTADOS ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Cuota Parte (Cap)", f"$ {df_final['Cuota Parte'].sum():,.0f}")
    c2.metric("Total Intereses", f"$ {df_final['Intereses'].sum():,.0f}")
    c3.metric("GRAN TOTAL", f"$ {df_final['Total'].sum():,.0f}")

    # Estructura visual Pasivocol
    st.write("### Estructura de Liquidación (Pasivocol)")
    st.dataframe(
        df_final.style.format({
            "Mesada Pensional": "${:,.0f}",
            "% Cuota Parte": "{:.2f}%",
            "Cuota Parte": "${:,.0f}",
            "Tasa DTF": "{:.2f}%",
            "Días": "{:d}",
            "Intereses": "${:,.0f}",
            "Total": "${:,.0f}"
        }),
        use_container_width=True
    )

    # Descargas
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar Reporte Pasivocol", csv, f"liquidacion_{pensionado}.csv", "text/csv")

    # Gráfico
    resumen_periodos = df_final.groupby("Periodo")["Total"].sum().reset_index()
    fig = go.Figure(go.Scatter(x=resumen_periodos['Periodo'], y=resumen_periodos['Total'], mode='lines+markers', name='Total Deuda'))
    fig.update_layout(title="Evolución de la Deuda por Periodo", xaxis_title="Periodo", yaxis_title="Total ($)")
    st.plotly_chart(fig, use_container_width=True)
