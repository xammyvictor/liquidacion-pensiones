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
    if fecha_inicio > fecha_fin:
        return 0
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
    """
    f_pago = date(anio_mesada, mes_mesada, 1)
    f_inicio_interes = f_pago + relativedelta(months=1)
    
    if fecha_corte < f_inicio_interes:
        return 0.0, 0, f_inicio_interes, tasa_manual
    
    n = dias_360(f_inicio_interes, fecha_corte)
    tasa_aplicable = tasas_db.get((anio_mesada, mes_mesada), tasa_manual)
    
    i_decimal = tasa_aplicable / 100
    interes = capital * ((1 + i_decimal)**(n / 365) - 1)
    
    return round(float(interes), 2), n, f_inicio_interes, tasa_aplicable

def to_excel(df_liq, df_abonos, nombre_pensionado):
    """
    Exporta a Excel manteniendo los datos numéricos y dos hojas: Liquidación y Abonos.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Hoja de Liquidación
        df_liq.to_excel(writer, index=False, sheet_name='Liquidacion')
        workbook = writer.book
        ws_liq = writer.sheets['Liquidacion']
        
        # Hoja de Abonos
        df_abonos.to_excel(writer, index=False, sheet_name='Abonos_Realizados')
        ws_abo = writer.sheets['Abonos_Realizados']
        
        # Estilos
        fmt_money = workbook.add_format({'num_format': '$#,##0', 'align': 'right'})
        fmt_pct = workbook.add_format({'num_format': '0.00%', 'align': 'center'})
        fmt_date = workbook.add_format({'num_format': 'dd/mm/yyyy', 'align': 'center'})
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})

        # Aplicar formatos a liquidación
        ws_liq.set_column('B:B', 18, fmt_money)
        ws_liq.set_column('C:C', 10, fmt_pct)
        ws_liq.set_column('D:D', 18, fmt_money)
        ws_liq.set_column('E:E', 15, fmt_date)
        ws_liq.set_column('F:F', 12, fmt_pct)
        ws_liq.set_column('H:I', 18, fmt_money)
        
        # Aplicar formatos a abonos
        ws_abo.set_column('A:A', 15, fmt_date)
        ws_abo.set_column('B:B', 20, fmt_money)
        ws_abo.set_column('D:D', 10, fmt_pct)
        ws_abo.set_column('F:F', 18, fmt_money)

    return output.getvalue()

# --- INTERFAZ STREAMLIT ---

st.title("🏦 Liquidador Pro de Cuotas Partes con Abonos")
st.markdown("Cálculo sincronizado con la metodología **UGPP** que permite aplicar pagos parciales.")

with st.sidebar:
    st.header("1. Datos Técnicos")
    archivo_excel = st.file_uploader("Excel BanRep (Serie DTF)", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0)

    st.divider()
    st.header("2. Información del Caso")
    pensionado = st.text_input("Nombre del Pensionado", "JOSE OSCAR ORTIZ")
    porcentaje_cp = st.number_input("% Cuota Parte", value=37.38, step=0.01)
    fecha_corte = st.date_input("Fecha de Corte (Liquidación)", value=date(2026, 4, 30))

# Secciones de entrada
tabs_input = st.tabs(["💰 Mesadas y Periodos", "💸 Abonos Realizados"])

with tabs_input[0]:
    st.subheader("Configuración de Mesadas")
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

with tabs_input[1]:
    st.subheader("Registro de Abonos / Pagos")
    st.info("Ingrese la fecha y el valor de los pagos realizados. El sistema calculará el interés que estos abonos ahorran.")
    
    # Tabla para abonos
    if 'abonos_data' not in st.session_state:
        st.session_state.abonos_data = pd.DataFrame([
            {"Fecha_Abono": date(2024, 1, 15), "Valor_Abono": 0.0}
        ])

    edit_abonos = st.data_editor(
        st.session_state.abonos_data,
        column_config={
            "Fecha_Abono": st.column_config.DateColumn("Fecha del Abono"),
            "Valor_Abono": st.column_config.NumberColumn("Valor Pagado ($)", format="$ %d")
        },
        num_rows="dynamic",
        use_container_width=True
    )

if st.button("🚀 Ejecutar Liquidación con Abonos", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas cargadas satisfactoriamente.")

    # 1. Calcular Deuda Bruta (Mesadas)
    resultados_liq = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        mesada_base = mesadas_map.get(anio, 0)
        mesada_pensional = mesada_base * 2 if mes in [6, 12] else mesada_base
        cp_principal = round(mesada_pensional * (porcentaje_cp / 100), 2)
        
        interes_v, dias_n, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(
            cp_principal, anio, mes, fecha_corte, tasas_db, tasa_manual
        )
        
        resultados_liq.append({
            "Periodo": f"{anio}-{mes:02d}",
            "Mesada Pensional": float(mesada_pensional),
            "% Cuota Parte": float(porcentaje_cp / 100),
            "Cuota Parte (Capital)": float(cp_principal),
            "Fecha Inicio Interés": f_causacion,
            "Tasa DTF": float(tasa_usada / 100),
            "Días (n)": int(dias_n),
            "Intereses": float(interes_v),
            "Total": float(cp_principal + interes_v)
        })
        fecha_actual += relativedelta(months=1)

    df_final_liq = pd.DataFrame(resultados_liq)

    # 2. Calcular Interés Ahorrado por Abonos
    resultados_abonos = []
    total_valor_abonos = 0.0
    total_interes_ahorrado = 0.0

    for _, row in edit_abonos.iterrows():
        val = row["Valor_Abono"]
        f_abono = row["Fecha_Abono"]
        
        if val > 0:
            # Cálculo de interés que el abono "cancela" desde su fecha hasta el corte
            n_abono = dias_360(f_abono, fecha_corte)
            t_abono = tasas_db.get((f_abono.year, f_abono.month), tasa_manual)
            i_abono = (t_abono / 100)
            int_ahorrado = round(val * ((1 + i_abono)**(n_abono / 365) - 1), 2)
            
            resultados_abonos.append({
                "Fecha Abono": f_abono,
                "Valor Abono": float(val),
                "Días al Corte": n_abono,
                "Tasa Mes Abono": float(t_abono / 100),
                "Interés Ahorrado": float(int_ahorrado),
                "Crédito Total": float(val + int_ahorrado)
            })
            total_valor_abonos += val
            total_interes_ahorrado += int_ahorrado

    df_final_abonos = pd.DataFrame(resultados_abonos)

    # --- SECCIÓN DE RESULTADOS ---
    st.divider()
    st.subheader("📋 Resumen Consolidado")
    
    cap_bruto = df_final_liq['Cuota Parte (Capital)'].sum()
    int_bruto = df_final_liq['Intereses'].sum()
    
    saldo_capital = cap_bruto - total_valor_abonos
    saldo_interes = int_bruto - total_interes_ahorrado
    gran_total = saldo_capital + saldo_interes
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital Bruto", f"$ {cap_bruto:,.0f}")
    c2.metric("Intereses Brutos", f"$ {int_bruto:,.0f}")
    c3.metric("Total Abonos (Cap+Int)", f"$ {total_valor_abonos + total_interes_ahorrado:,.0f}", delta=f"-{total_valor_abonos:,.0f}", delta_color="inverse")
    c4.metric("SALDO NETO FINAL", f"$ {gran_total:,.0f}", help="Saldo después de restar capital pagado e intereses ahorrados por el abono.")

    st.write("### Detalle de la Liquidación")
    st.dataframe(
        df_final_liq.style.format({
            "Mesada Pensional": "${:,.0f}",
            "% Cuota Parte": "{:.2%}",
            "Cuota Parte (Capital)": "${:,.0f}",
            "Tasa DTF": "{:.2%}",
            "Intereses": "${:,.0f}",
            "Total": "${:,.0f}"
        }),
        use_container_width=True
    )

    if not df_final_abonos.empty:
        st.write("### Detalle de Abonos Aplicados")
        st.dataframe(
            df_final_abonos.style.format({
                "Valor Abono": "${:,.0f}",
                "Tasa Mes Abono": "{:.2%}",
                "Interés Ahorrado": "${:,.0f}",
                "Crédito Total": "${:,.0f}"
            }),
            use_container_width=True
        )

    # Botones de Acción
    st.write("---")
    excel_data = to_excel(df_final_liq, df_final_abonos, pensionado)
    st.download_button(
        label="📥 Descargar Liquidación con Abonos (Excel)",
        data=excel_data,
        file_name=f"Liquidacion_Abonos_{pensionado}_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
