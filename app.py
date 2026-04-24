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
    Procesa el archivo de tasas basándose estrictamente en la ubicación:
    Columna A (índice 0): Periodo/Fecha
    Columna B (índice 1): Tasa (DTF)
    """
    try:
        df_raw = pd.read_excel(file, sheet_name="Series de datos", header=None)
        
        # Búsqueda dinámica de la fila de inicio (donde la col A es una fecha)
        start_row = 0
        for i, val in enumerate(df_raw.iloc[:, 0]):
            try:
                # Comprobamos si el valor es convertible a fecha
                test_date = pd.to_datetime(val, errors='coerce')
                if pd.notnull(test_date):
                    start_row = i
                    break
            except:
                continue
        
        df_data = df_raw.iloc[start_row:].copy()
        
        tasas_map = {}
        for _, row in df_data.iterrows():
            f_val = row.iloc[0]
            t_val = row.iloc[1]
            dt = pd.to_datetime(f_val, errors='coerce')
            
            try:
                rate = float(t_val)
            except (ValueError, TypeError):
                rate = None
            
            if pd.notnull(dt) and rate is not None:
                tasas_map[(dt.year, dt.month)] = rate
                
        return tasas_map
    except Exception as e:
        st.error(f"Error al procesar el Excel (Columnas A y B): {e}")
        return None

def calcular_interes_pasivocol_preciso(capital, anio_mesada, mes_mesada, fecha_corte, tasas_db, tasa_manual):
    """
    Metodología Pasivocol Actualizada:
    1. Fecha de Pago = Periodo de la mesada.
    2. Tasa (i) = Se toma la vigente en la fecha de pago de la mesada (según image_86f2b9.png).
    3. Fecha de Causación = Último día del mes SIGUIENTE a la mesada.
    4. n = Días desde la fecha de causación hasta la fecha de corte.
    5. Interés = CP * ((1 + i)^(n/365) - 1)
    """
    # Mesada base
    f_base = date(anio_mesada, mes_mesada, 1)
    
    # Fecha Causación (Último día del mes siguiente):
    # n empieza a contar desde el día siguiente a esta fecha.
    f_causacion = (f_base + relativedelta(months=1)) + relativedelta(day=31)
    
    if fecha_corte <= f_causacion:
        return 0, 0, f_causacion, tasa_manual
    
    # Días n (Diferencia exacta)
    dias = (fecha_corte - f_causacion).days
    
    # AJUSTE: La tasa i se toma del mes de la MESADA (Fecha de pago), no de la causación.
    tasa_aplicable = tasas_db.get((anio_mesada, mes_mesada), tasa_manual)
    
    # Fórmula de Interés Compuesto
    i_decimal = tasa_aplicable / 100
    interes = capital * ((1 + i_decimal)**(dias / 365) - 1)
    
    return interes, dias, f_causacion, tasa_aplicable

# --- INTERFAZ ---

st.title("🏦 Liquidador de Cuotas Partes - Estilo Pasivocol")
st.markdown("Liquidación técnica ajustada con la **Tasa vigente a la fecha de pago** y **Causación al Mes Siguiente**.")

with st.sidebar:
    st.header("1. Carga de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0, help="Se usa si el mes no está en el archivo Excel.")

    st.divider()
    st.header("2. Datos de Liquidación")
    pensionado = st.text_input("Nombre del Pensionado", "Juan Pérez")
    porcentaje_cp = st.number_input("% Cuota Parte", value=50.0, step=0.1)
    fecha_corte = st.date_input("Fecha de Corte (Liquidación hasta)", value=date.today())

st.subheader("1. Rango de Tiempo y Salarios")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha de Inicio", value=date(2020, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha de Fin", value=date(2023, 12, 31))

# --- ENTRADA DE MESADAS POR AÑO ---
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

mesadas_map = edit_mesadas.set_index("Año")["Valor_Mesada"].to_dict()

# --- PROCESAMIENTO ---
if st.button("🚀 Ejecutar Liquidación Pasivocol", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success(f"✅ Tasas cargadas satisfactoriamente.")
        else:
            st.warning("⚠️ No se detectaron tasas. Usando tasa manual.")

    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        
        # Valor de la mesada según el año ingresado
        mesada_base = mesadas_map.get(anio, 0)
        
        # AJUSTE: Mesada doble en Junio y Diciembre (Mesada + Prima)
        mesada_pensional = mesada_base * 2 if mes in [6, 12] else mesada_base
        
        # Cuota Parte Capital
        cp_principal = mesada_pensional * (porcentaje_cp / 100)
        
        # Cálculo detallado según metodología Pasivocol
        interes_v, dias_m, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(
            cp_principal, 
            anio, 
            mes, 
            fecha_corte,
            tasas_db,
            tasa_manual
        )
        
        resultados.append({
            "Periodo": f"{anio}-{mes:02d}",
            "Mesada Pensional": mesada_pensional,
            "% Cuota Parte": porcentaje_cp,
            "Cuota Parte": cp_principal,
            "Fecha Causación": f_causacion.strftime("%d/%m/%Y"),
            "Tasa DTF": tasa_usada,
            "Días": dias_m,
            "Intereses": interes_v,
            "Total": cp_principal + interes_v
        })
            
        fecha_actual += relativedelta(months=1)

    df_final = pd.DataFrame(resultados)

    # --- RESULTADOS ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Capital Adeudado", f"$ {df_final['Cuota Parte'].sum():,.0f}")
    c2.metric("Intereses Causados", f"$ {df_final['Intereses'].sum():,.0f}")
    c3.metric("GRAN TOTAL", f"$ {df_final['Total'].sum():,.0f}")

    # Visualización Estilo Pasivocol
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

    # Descarga
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar Reporte Pasivocol (CSV)", csv, f"liquidacion_{pensionado}.csv", "text/csv")
