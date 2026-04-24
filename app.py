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
        # Leer la hoja específica saltando las filas de metadatos (usualmente las primeras 7)
        df = pd.read_excel(file, sheet_name="Series de datos", skiprows=2)
        
        # Limpiar nombres de columnas (quitar saltos de línea y espacios)
        df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
        
        # Identificar columnas clave
        col_fecha = df.columns[0] # Usualmente 'Fecha'
        col_dtf = [c for c in df.columns if "1. DTF promedio mensual" in c]
        
        if not col_dtf:
            st.error("No se encontró la columna '1. DTF promedio mensual' en el Excel.")
            return None
        
        col_dtf = col_dtf[0]
        
        # Convertir fecha y filtrar nulos
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        df = df.dropna(subset=[col_fecha, col_dtf])
        
        # Crear un diccionario {(año, mes): tasa}
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
    n = días desde el último día del mes siguiente al pago.
    """
    # El interés inicia el último día del mes siguiente al pago
    fecha_inicio_mora = (fecha_pago_mesada + relativedelta(months=1)).replace(day=1) + relativedelta(months=1, days=-1)
    
    if fecha_corte <= fecha_inicio_mora:
        return 0, 0
    
    dias = (fecha_corte - fecha_inicio_mora).days
    i_decimal = tasa_anual / 100
    interes = capital * ((1 + i_decimal)**(dias / 365) - 1)
    return interes, dias

# --- INTERFAZ ---

st.title("🏦 Liquidador de Cuotas Partes - Pasivocol")
st.markdown("Cálculo detallado con **tasas mensuales DTF** y **valores de mesada por año**.")

with st.sidebar:
    st.header("1. Configuración de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    
    st.divider()
    st.header("2. Datos de Liquidación")
    pensionado = st.text_input("Pensionado", "Nombre Ejemplo")
    porcentaje_cp = st.number_input("% Cuota Parte", value=50.0, step=0.1)
    fecha_corte = st.date_input("Fecha de Corte para intereses", value=date.today())
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=12.0, help="Se usa si el mes no está en el Excel")

# 3. ENTRADA DE SALARIOS POR AÑO
st.subheader("Configuración de Mesadas por Año")
col_a1, col_a2 = st.columns(2)
with col_a1:
    anio_inicio = st.number_input("Año de inicio", value=2021, step=1)
with col_a2:
    anio_fin = st.number_input("Año final", value=date.today().year, step=1)

anios = list(range(int(anio_inicio), int(anio_fin) + 1))
df_config_anual = pd.DataFrame({
    "Año": anios,
    "Mesada_Mensual_Base": [2500000.0] * len(anios)
})

edit_anual = st.data_editor(
    df_config_anual,
    column_config={
        "Año": st.column_config.NumberColumn(disabled=True, format="%d"),
        "Mesada_Mensual_Base": st.column_config.NumberColumn("Valor Mesada ($)", format="$ %d")
    },
    use_container_width=True
)

# 4. PROCESAMIENTO
if st.button("Generar Liquidación Mensualizada", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas mensuales cargadas satisfactoriamente.")
    
    # Construcción de la sábana de liquidación
    resultados = []
    fecha_limite_prescripcion = fecha_corte - relativedelta(years=3)
    
    for _, fila in edit_anual.iterrows():
        anio = int(fila["Año"])
        mesada_base = fila["Mesada_Mensual_Base"]
        
        # Generar los 12 meses del año + Mesada adicional (Diciembre)
        # Nota: Puedes añadir mesada 13 o 14 según el caso
        meses_a_liquidar = list(range(1, 13)) + [12.1] # 12.1 representa mesada adicional
        
        for m in meses_a_liquidar:
            es_adicional = (m == 12.1)
            mes_num = 12 if es_adicional else int(m)
            
            # Fecha de pago: último día del mes
            fecha_pago = (date(anio, mes_num, 1) + relativedelta(months=1, days=-1))
            
            # Obtener tasa específica del mes/año
            tasa_aplicable = tasas_db.get((anio, mes_num), tasa_manual) if tasas_db else tasa_manual
            
            cp_principal = mesada_base * (porcentaje_cp / 100)
            interes_v, dias_m = calcular_interes_pasivocol(cp_principal, tasa_aplicable, fecha_pago, fecha_corte)
            
            es_prescrita = "🔴 Prescrita" if fecha_pago < fecha_limite_prescripcion else "🟢 Vigente"
            
            resultados.append({
                "Año": anio,
                "Mes": "Mesada Adicional" if es_adicional else f"Mes {mes_num}",
                "Fecha Pago": fecha_pago,
                "Tasa DTF (%)": tasa_aplicable,
                "Mesada Total": mesada_base,
                "Cuota Parte (Cap)": cp_principal,
                "Días Mora": dias_m,
                "Intereses": interes_v,
                "Total Periodo": cp_principal + interes_v,
                "Estado": es_prescrita
            })

    df_final = pd.DataFrame(resultados)

    # --- MÉTRICAS Y TABLA ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    vigentes = df_final[df_final["Estado"] == "🟢 Vigente"]
    
    c1.metric("Total Capital Vigente", f"$ {vigentes['Cuota Parte (Cap)'].sum():,.0f}")
    c2.metric("Total Intereses Vigentes", f"$ {vigentes['Intereses'].sum():,.0f}")
    c3.metric("GRAN TOTAL COBRO", f"$ {vigentes['Total Periodo'].sum():,.0f}")

    st.dataframe(
        df_final.style.format({
            "Tasa DTF (%)": "{:.2f}%",
            "Mesada Total": "${:,.0f}",
            "Cuota Parte (Cap)": "${:,.0f}",
            "Intereses": "${:,.0f}",
            "Total Periodo": "${:,.0f}"
        }),
        use_container_width=True
    )

    # Descargas
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar Liquidación Completa", csv, f"liquidacion_{pensionado}.csv", "text/csv")
