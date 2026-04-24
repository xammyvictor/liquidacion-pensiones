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
    Calcula la diferencia de días entre dos fechas usando la convención 30/360.
    Utilizado por Pasivocol para el cálculo del parámetro 'n'.
    """
    d1 = min(30, fecha_inicio.day)
    d2 = min(30, fecha_fin.day)
    
    # Caso especial: si la fecha fin es el último día de febrero
    if fecha_fin.month == 2 and (fecha_fin.day == 28 or fecha_fin.day == 29):
        d2 = 30
        
    return (fecha_fin.year - fecha_inicio.year) * 360 + (fecha_fin.month - fecha_inicio.month) * 30 + (d2 - d1)

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
    Metodología Pasivocol Final (Sincronizada con UGPP):
    1. Tasa (i) = DTF Efectiva Anual del mes de la mesada.
    2. Inicio Interés = Día 1 del mes SIGUIENTE a la mesada.
    3. n = Días entre Inicio Interés y Fecha Corte (Convención 30/360).
    4. Fórmula = CP * ((1 + i)^(n/365) - 1)
    """
    # Fecha de inicio de intereses (Día 1 del mes siguiente)
    f_pago = date(anio_mesada, mes_mesada, 1)
    f_inicio_interes = f_pago + relativedelta(months=1)
    
    if fecha_corte < f_inicio_interes:
        return 0, 0, f_inicio_interes, tasa_manual
    
    # Cálculo de n usando convención comercial 30/360
    n = dias_360(f_inicio_interes, fecha_corte)
    
    # Tasa i del mes de la mesada
    tasa_aplicable = tasas_db.get((anio_mesada, mes_mesada), tasa_manual)
    
    # Fórmula de Interés Compuesto (Divisor 365 según Circular 2-2016-039942)
    i_decimal = tasa_aplicable / 100
    interes = capital * ((1 + i_decimal)**(n / 365) - 1)
    
    return interes, n, f_inicio_interes, tasa_aplicable

def to_excel(df):
    """
    Convierte el dataframe a un archivo Excel en memoria para descarga.
    """
    output = io.BytesIO()
    # Usamos xlsxwriter para mejor compatibilidad con formatos
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Liquidación')
        workbook = writer.book
        worksheet = writer.sheets['Liquidación']
        
        # Definir formatos numéricos
        format_money = workbook.add_format({'num_format': '"$"#,##0'})
        format_pct = workbook.add_format({'num_format': '0.00"%"'})
        
        # Aplicar formatos a las columnas (ajustar índices según el DF)
        # 0:Periodo, 1:Mesada, 2:%CP, 3:CP, 4:Fecha, 5:Tasa, 6:Días, 7:Intereses, 8:Total
        worksheet.set_column('B:B', 15, format_money) # Mesada
        worksheet.set_column('C:C', 12, format_pct)   # % Cuota Parte
        worksheet.set_column('D:D', 15, format_money) # Cuota Parte
        worksheet.set_column('F:F', 12, format_pct)   # Tasa DTF
        worksheet.set_column('H:I', 15, format_money) # Intereses y Total
        
    processed_data = output.getvalue()
    return processed_data

# --- INTERFAZ DE USUARIO ---

st.title("🏦 Liquidador de Cuotas Partes - Estilo Pasivocol")
st.markdown("Cálculo sincronizado con la metodología de la **UGPP** (Interés Compuesto y Días 30/360).")

with st.sidebar:
    st.header("1. Carga de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0)

    st.divider()
    st.header("2. Datos de Liquidación")
    pensionado = st.text_input("Nombre del Pensionado", "JOSE OSCAR ORTIZ")
    porcentaje_cp = st.number_input("% Cuota Parte", value=37.38, step=0.01)
    fecha_corte = st.date_input("Fecha de Corte (Hasta)", value=date(2026, 4, 30))

st.subheader("1. Configuración de Periodos y Mesadas")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha de Inicio", value=date(2022, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha de Fin", value=date(2026, 4, 30))

# Entrada de mesadas anuales
años_rango = list(range(f_inicio.year, f_fin.year + 1))
df_mesadas_anuales = pd.DataFrame({
    "Año": años_rango,
    "Valor_Mesada": [3374717.0] * len(años_rango)
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
            st.success(f"✅ Tasas cargadas correctamente.")

    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        
        # Valor de mesada del año
        mesada_base = mesadas_map.get(anio, 0)
        
        # En Junio y Diciembre se duplica por Prima
        mesada_pensional = mesada_base * 2 if mes in [6, 12] else mesada_base
        
        # Capital de Cuota Parte
        cp_principal = mesada_pensional * (porcentaje_cp / 100)
        
        # Cálculo bajo norma UGPP/Pasivocol
        interes_v, dias_n, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(
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
            "Cuota Parte (Capital)": cp_principal,
            "Fecha Inicio Interés": f_causacion.strftime("%d/%m/%Y"),
            "Tasa DTF": tasa_usada,
            "Días (n)": dias_n,
            "Intereses": interes_v,
            "Total": cp_principal + interes_v
        })
            
        fecha_actual += relativedelta(months=1)

    df_final = pd.DataFrame(resultados)

    # --- RESULTADOS FINALES ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    total_cap = df_final['Cuota Parte (Capital)'].sum()
    total_int = df_final['Intereses'].sum()
    
    c1.metric("Capital Total", f"$ {total_cap:,.0f}")
    c2.metric("Intereses Totales", f"$ {total_int:,.0f}")
    c3.metric("GRAN TOTAL", f"$ {total_cap + total_int:,.0f}")

    # Tabla Estilo Pasivocol en Streamlit (solo visual)
    st.dataframe(
        df_final.style.format({
            "Mesada Pensional": "${:,.0f}",
            "% Cuota Parte": "{:.2f}%",
            "Cuota Parte (Capital)": "${:,.0f}",
            "Tasa DTF": "{:.2f}%",
            "Días (n)": "{:d}",
            "Intereses": "${:,.0f}",
            "Total": "${:,.0f}"
        }),
        use_container_width=True
    )

    # Exportación a EXCEL (con datos numéricos)
    excel_data = to_excel(df_final)
    st.download_button(
        label="📥 Descargar Liquidación (Excel)",
        data=excel_data,
        file_name=f"liquidacion_{pensionado}_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key='download-excel'
    )
