import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
import io

# Configuración de página
st.set_page_config(page_title="Liquidador Pasivocol DTF", page_icon="🏦", layout="wide")

# --- FUNCIONES DE CÓMPUTO ACTUARIAL ---

def dias_360(fecha_inicio, fecha_fin):
    """
    Calcula la diferencia de días usando la convención 30/360 (Método SIA/NASD).
    Se suma +1 para que el cálculo sea inclusivo del primer día, 
    ajustándose a los resultados de Pasivocol (ej. n=1515).
    """
    d1 = min(30, fecha_inicio.day)
    d2 = min(30, fecha_fin.day)
    
    # Ajuste para febrero (fin de mes comercial)
    if fecha_fin.month == 2 and (fecha_fin.day == 28 or fecha_fin.day == 29):
        d2 = 30
        
    resultado = (fecha_fin.year - fecha_inicio.year) * 360 + (fecha_fin.month - fecha_inicio.month) * 30 + (d2 - d1)
    return int(resultado + 1)

def cargar_tasas_banrep(file):
    """
    Procesa el archivo de tasas del Banco de la República (Col A: Fecha, Col B: Tasa).
    """
    try:
        df_raw = pd.read_excel(file, sheet_name="Series de datos", header=None)
        start_row = 0
        for i, val in enumerate(df_raw.iloc[:, 0]):
            try:
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
        st.error(f"Error al procesar el Excel: {e}")
        return None

def calcular_interes_pasivocol_preciso(capital, anio_mesada, mes_mesada, fecha_corte, tasas_db, tasa_manual):
    """
    Metodología Pasivocol/UGPP:
    Fórmula = CP * ((1 + i)^(n/365) - 1)
    Se redondea el interés a 2 decimales por periodo para igualar la precisión de Pasivocol.
    """
    f_pago = date(anio_mesada, mes_mesada, 1)
    # Fecha de inicio de intereses (Día 1 del mes siguiente)
    f_inicio_interes = f_pago + relativedelta(months=1)
    
    if fecha_corte < f_inicio_interes:
        return 0.0, 0, f_inicio_interes, tasa_manual
    
    n = dias_360(f_inicio_interes, fecha_corte)
    tasa_aplicable = tasas_db.get((anio_mesada, mes_mesada), tasa_manual)
    
    i_decimal = tasa_aplicable / 100
    # Cálculo con alta precisión y redondeo final de fila
    interes = capital * ((1 + i_decimal)**(n / 365) - 1)
    
    return round(float(interes), 2), n, f_inicio_interes, tasa_aplicable

def to_excel(df, nombre_pensionado):
    """
    Exporta a Excel manteniendo los datos como valores numéricos reales y formatos contables.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Liquidacion')
        workbook = writer.book
        worksheet = writer.sheets['Liquidacion']
        
        # Estilos de Excel
        fmt_money = workbook.add_format({'num_format': '$#,##0', 'align': 'right'})
        fmt_pct = workbook.add_format({'num_format': '0.00%', 'align': 'center'})
        fmt_date = workbook.add_format({'num_format': 'dd/mm/yyyy', 'align': 'center'})
        fmt_num = workbook.add_format({'align': 'center'})
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})

        # Encabezados
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, fmt_header)

        # Aplicar formatos a las columnas (A-I)
        worksheet.set_column('A:A', 12, fmt_num)   # Periodo
        worksheet.set_column('B:B', 18, fmt_money) # Mesada
        worksheet.set_column('C:C', 10, fmt_pct)   # % CP
        worksheet.set_column('D:D', 18, fmt_money) # Cuota Parte
        worksheet.set_column('E:E', 15, fmt_date)  # Fecha
        worksheet.set_column('F:F', 12, fmt_pct)   # Tasa
        worksheet.set_column('G:G', 10, fmt_num)   # Días
        worksheet.set_column('H:I', 18, fmt_money) # Intereses y Total
        
    return output.getvalue()

# --- INTERFAZ STREAMLIT ---

st.title("🏦 Liquidador Pro de Cuotas Partes")
st.markdown("Cálculo sincronizado con la metodología oficial de **Pasivocol/UGPP** (Interés Compuesto 30/360).")

with st.sidebar:
    st.header("1. Datos Técnicos")
    archivo_excel = st.file_uploader("Excel BanRep (Serie DTF)", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0)

    st.divider()
    st.header("2. Información del Caso")
    pensionado = st.text_input("Nombre del Pensionado", "JOSE OSCAR ORTIZ")
    porcentaje_cp = st.number_input("% Cuota Parte", value=37.38, step=0.01)
    fecha_corte = st.date_input("Fecha de Corte (Liquidación)", value=date(2026, 4, 30))

st.subheader("Configuración de Mesadas y Periodos")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha Inicio", value=date(2022, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha Fin", value=date(2026, 4, 30))

años_rango = list(range(f_inicio.year, f_fin.year + 1))
df_mesadas_anuales = pd.DataFrame({
    "Año": años_rango,
    "Mesada_Mensual": [3374717.0] * len(años_rango)
})

edit_mesadas = st.data_editor(
    df_mesadas_anuales,
    column_config={
        "Año": st.column_config.NumberColumn(disabled=True, format="%d"),
        "Mesada_Mensual": st.column_config.NumberColumn("Valor Mesada ($)", format="$ %d")
    },
    use_container_width=True
)

mesadas_map = edit_mesadas.set_index("Año")["Mesada_Mensual"].to_dict()

if st.button("🚀 Ejecutar Liquidación", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas cargadas satisfactoriamente.")

    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        mesada_base = mesadas_map.get(anio, 0)
        # Primas de Junio y Diciembre
        mesada_pensional = mesada_base * 2 if mes in [6, 12] else mesada_base
        cp_principal = round(mesada_pensional * (porcentaje_cp / 100), 2)
        
        interes_v, dias_n, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(
            cp_principal, anio, mes, fecha_corte, tasas_db, tasa_manual
        )
        
        resultados.append({
            "Periodo": f"{anio}-{mes:02d}",
            "Mesada Pensional": float(mesada_pensional),
            "% Cuota Parte": float(porcentaje_cp / 100), # Para que Excel lo tome como %
            "Cuota Parte (Capital)": float(cp_principal),
            "Fecha Inicio Interés": f_causacion,
            "Tasa DTF": float(tasa_usada / 100), # Para que Excel lo tome como %
            "Días (n)": int(dias_n),
            "Intereses": float(interes_v),
            "Total": float(cp_principal + interes_v)
        })
        fecha_actual += relativedelta(months=1)

    df_final = pd.DataFrame(resultados)

    # --- SECCIÓN DE RESULTADOS Y TOTALES ---
    st.divider()
    st.subheader("📋 Resumen de Liquidación")
    
    # Cálculo de totales
    total_capital = df_final['Cuota Parte (Capital)'].sum()
    total_intereses = df_final['Intereses'].sum()
    gran_total = total_capital + total_intereses
    
    # Mostrar métricas destacadas
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Valor Cuotaparte", f"$ {total_capital:,.2f}")
    c2.metric("Total Intereses", f"$ {total_intereses:,.2f}")
    c3.metric("GRAN TOTAL A COBRAR", f"$ {gran_total:,.2f}")

    st.write("### Vista Previa de Resultados Detallados")
    st.dataframe(
        df_final.style.format({
            "Mesada Pensional": "${:,.0f}",
            "% Cuota Parte": "{:.2%}",
            "Cuota Parte (Capital)": "${:,.2f}",
            "Tasa DTF": "{:.2%}",
            "Intereses": "${:,.2f}",
            "Total": "${:,.2f}"
        }),
        use_container_width=True
    )

    # Botones de Acción
    st.write("---")
    col_down1, col_down2 = st.columns([1, 4])
    with col_down1:
        excel_data = to_excel(df_final, pensionado)
        st.download_button(
            label="📥 Descargar Reporte (Excel)",
            data=excel_data,
            file_name=f"Liquidacion_{pensionado}_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary"
        )
