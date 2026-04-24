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
        # Cargamos el Excel sin encabezados fijos para buscar los datos
        df_raw = pd.read_excel(file, sheet_name="Series de datos", header=None)
        
        # Buscamos la fila donde comienzan los datos reales. 
        # Buscamos una celda en la columna A que se pueda convertir a fecha.
        start_row = 0
        for i, val in enumerate(df_raw.iloc[:, 0]):
            # Intentamos convertir el valor de la columna A a fecha
            try:
                if pd.notnull(val) and isinstance(pd.to_datetime(val, errors='coerce'), datetime):
                    start_row = i
                    break
            except:
                continue
        
        # Filtramos desde la fila de inicio encontrada
        df_data = df_raw.iloc[start_row:].copy()
        
        # Usamos columna 0 para fecha y 1 para tasa
        tasas_map = {}
        for _, row in df_data.iterrows():
            f_val = row.iloc[0]
            t_val = row.iloc[1]
            
            # Conversión de fecha
            dt = pd.to_datetime(f_val, errors='coerce')
            
            # Conversión de tasa (manejando puntos o caracteres no numéricos)
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

def calcular_interes_pasivocol(capital, tasa_anual, fecha_pago_mesada, fecha_corte):
    """
    Fórmula de Pasivocol: I = CP * ((1 + DTF)^(n/365) - 1)
    """
    # Fecha Causación: último día del mes de pago
    fecha_causacion = (fecha_pago_mesada + relativedelta(day=31))
    
    # El interés inicia el día siguiente a la causación
    if fecha_corte <= fecha_causacion:
        return 0, 0, fecha_causacion
    
    dias = (fecha_corte - fecha_causacion).days
    i_decimal = tasa_anual / 100
    interes = capital * ((1 + i_decimal)**(dias / 365) - 1)
    return interes, dias, fecha_causacion

# --- INTERFAZ ---

st.title("🏦 Liquidador de Cuotas Partes - Estilo Pasivocol")
st.markdown("Liquidación técnica utilizando **Columna A (Fecha)** y **Columna B (Tasa)** del archivo Excel.")

with st.sidebar:
    st.header("1. Carga de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=12.0)

    st.divider()
    st.header("2. Datos de Liquidación")
    pensionado = st.text_input("Nombre del Pensionado", "Juan Pérez")
    porcentaje_cp = st.number_input("% Cuota Parte", value=50.0, step=0.1)
    fecha_corte = st.date_input("Fecha de Corte", value=date.today())

st.subheader("1. Periodo y Mesadas Anuales")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha Inicio Liquidación", value=date(2022, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha Fin Liquidación", value=date(2023, 12, 31))

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
        "Valor_Mesada": st.column_config.NumberColumn("Valor Mesada Mensual ($)", format="$ %d")
    },
    use_container_width=True,
    key="mesadas_editor"
)

mesadas_map = edit_mesadas.set_index("Año")["Valor_Mesada"].to_dict()

# --- PROCESAMIENTO ---
if st.button("🚀 Generar Liquidación Detallada", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success(f"✅ Datos cargados: {len(tasas_db)} periodos encontrados en Columna A y B.")
        else:
            st.warning("⚠️ No se detectaron datos válidos en el Excel. Se usará tasa de respaldo.")

    # Generar todos los meses en el rango
    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        
        mesada_mensual = mesadas_map.get(anio, 0)
        # Buscar tasa en Excel (Columna B mapeada), si no existe usar manual
        tasa_aplicable = tasas_db.get((anio, mes), tasa_manual)
        
        # Lógica de mesada normal + Prima (Junio y Diciembre)
        registros_mes = [{"tipo": "Normal", "label": f"{anio}-{mes:02d}"}]
        if mes == 6:
            registros_mes.append({"tipo": "Prima", "label": f"{anio}-{mes:02d} (Prima Junio)"})
        if mes == 12:
            registros_mes.append({"tipo": "Prima", "label": f"{anio}-{mes:02d} (Prima Diciembre)"})
        
        for reg in registros_mes:
            # Fecha de pago: último día del mes
            f_pago = (fecha_actual + relativedelta(months=1, days=-1))
            
            # Valor de la mesada y cuota parte
            cp_principal = mesada_mensual * (porcentaje_cp / 100)
            
            # Cálculo intereses y fecha causación
            interes_v, dias_m, f_causacion = calcular_interes_pasivocol(cp_principal, tasa_aplicable, f_pago, fecha_corte)
            
            resultados.append({
                "Periodo": reg["label"],
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
    c1.metric("Total Cuota Parte", f"$ {df_final['Cuota Parte'].sum():,.0f}")
    c2.metric("Total Intereses", f"$ {df_final['Intereses'].sum():,.0f}")
    c3.metric("GRAN TOTAL", f"$ {df_final['Total'].sum():,.0f}")

    # Estructura Pasivocol
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
    st.download_button("📥 Descargar Liquidación (CSV)", csv, f"liquidacion_{pensionado}.csv", "text/csv")
