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
        df_liq.to_excel(writer, index=False, sheet_name='Liquidacion')
        workbook = writer.book
        ws_liq = writer.sheets['Liquidacion']
        
        df_abonos.to_excel(writer, index=False, sheet_name='Detalle_Abonos')
        ws_abo = writer.sheets['Detalle_Abonos']
        
        fmt_money = workbook.add_format({'num_format': '$#,##0', 'align': 'right'})
        fmt_pct = workbook.add_format({'num_format': '0.00%', 'align': 'center'})
        fmt_date = workbook.add_format({'num_format': 'dd/mm/yyyy', 'align': 'center'})
        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})

        # B:Mesada, C:%CP, D:CapBruto, E:Fecha, F:Tasa, G:Días, H:IntBruto, I:AbonoInt, J:AbonoCap, K:Saldo
        ws_liq.set_column('B:B', 18, fmt_money)
        ws_liq.set_column('C:C', 10, fmt_pct)
        ws_liq.set_column('D:D', 18, fmt_money)
        ws_liq.set_column('E:E', 15, fmt_date)
        ws_liq.set_column('F:F', 12, fmt_pct)
        ws_liq.set_column('H:K', 18, fmt_money)
        
        ws_abo.set_column('A:A', 15, fmt_date)
        ws_abo.set_column('B:B', 20, fmt_money)

    return output.getvalue()

# --- INTERFAZ STREAMLIT ---

st.title("🏦 Liquidador Pro - Cuotas Partes con Imputación de Pagos")
st.markdown("Sincronizado con **UGPP**. Los abonos pagan primero los **intereses pendientes** del periodo más antiguo.")

with st.sidebar:
    st.header("1. Datos Técnicos")
    archivo_excel = st.file_uploader("Excel BanRep (Serie DTF)", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0)

    st.divider()
    st.header("2. Información del Caso")
    pensionado = st.text_input("Nombre del Pensionado", "JOSE OSCAR ORTIZ")
    porcentaje_cp = st.number_input("% Cuota Parte", value=37.38, step=0.01)
    fecha_corte = st.date_input("Fecha de Corte (Liquidación)", value=date(2026, 4, 30))

tabs_input = st.tabs(["💰 Mesadas y Periodos", "💸 Abonos / Pagos Realizados"])

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
    st.subheader("Registro de Abonos")
    st.info("Los abonos ingresados se aplicarán siguiendo el orden cronológico: primero a intereses vencidos y luego a capital.")
    
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

if st.button("🚀 Calcular Liquidación e Imputar Pagos", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas cargadas satisfactoriamente.")

    # 1. Calcular Deuda Bruta por Periodo
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
            "Cap. Bruto": float(cp_principal),
            "Fecha Causación": f_causacion,
            "Tasa DTF": float(tasa_usada / 100),
            "Días (n)": int(dias_n),
            "Int. Bruto": float(interes_v),
            "Abono a Int.": 0.0,
            "Abono a Cap.": 0.0,
            "Saldo Periodo": 0.0
        })
        fecha_actual += relativedelta(months=1)

    # 2. Imputación de Pagos (Primero Interés, luego Capital)
    total_abonos_disponibles = edit_abonos[edit_abonos["Valor_Abono"] > 0]["Valor_Abono"].sum()
    bolsa_pagos = total_abonos_disponibles

    for res in resultados_liq:
        # Pago a Interés
        pago_al_interes = min(res["Int. Bruto"], bolsa_pagos)
        res["Abono a Int."] = round(pago_al_interes, 2)
        bolsa_pagos -= pago_al_interes
        
        # Pago a Capital
        pago_al_capital = min(res["Cap. Bruto"], bolsa_pagos)
        res["Abono a Cap."] = round(pago_al_capital, 2)
        bolsa_pagos -= pago_al_capital
        
        # Saldo Final del Periodo
        res["Saldo Periodo"] = round((res["Cap. Bruto"] + res["Int. Bruto"]) - (res["Abono a Int."] + res["Abono a Cap."]), 2)

    df_final = pd.DataFrame(resultados_liq)

    # --- SECCIÓN DE RESULTADOS ---
    st.divider()
    st.subheader("📋 Resumen de Liquidación Post-Abonos")
    
    cap_bruto_total = df_final['Cap. Bruto'].sum()
    int_bruto_total = df_final['Int. Bruto'].sum()
    saldo_final_total = df_final['Saldo Periodo'].sum()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deuda Bruta Total", f"$ {cap_bruto_total + int_bruto_total:,.0f}")
    c2.metric("Total Abonos", f"$ {total_abonos_disponibles:,.0f}", delta=f"-{total_abonos_disponibles:,.0f}", delta_color="inverse")
    c3.metric("Intereses Pendientes", f"$ {df_final['Int. Bruto'].sum() - df_final['Abono a Int.'].sum():,.0f}")
    c4.metric("SALDO NETO FINAL", f"$ {saldo_final_total:,.0f}")

    st.write("### Detalle Cronológico e Imputación de Pagos")
    st.dataframe(
        df_final.style.format({
            "Mesada Pensional": "${:,.0f}",
            "% Cuota Parte": "{:.2%}",
            "Cap. Bruto": "${:,.0f}",
            "Tasa DTF": "{:.2%}",
            "Int. Bruto": "${:,.0f}",
            "Abono a Int.": "${:,.0f}",
            "Abono a Cap.": "${:,.0f}",
            "Saldo Periodo": "${:,.0f}"
        }),
        use_container_width=True
    )

    # Botones de Acción
    st.write("---")
    excel_data = to_excel(df_final, edit_abonos, pensionado)
    st.download_button(
        label="📥 Descargar Reporte Completo (Excel)",
        data=excel_data,
        file_name=f"Liquidacion_Imputada_{pensionado}_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
