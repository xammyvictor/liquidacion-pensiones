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
    Inclusivo (+1).
    """
    if fecha_inicio > fecha_fin:
        return 0
    d1 = min(30, fecha_inicio.day)
    d2 = min(30, fecha_fin.day)
    if fecha_fin.month == 2 and (fecha_fin.day == 28 or fecha_fin.day == 29):
        d2 = 30
    resultado = (fecha_fin.year - fecha_inicio.year) * 360 + (fecha_fin.month - fecha_inicio.month) * 30 + (d2 - d1)
    return int(resultado + 1)

def cargar_tasas_banrep(file):
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
            except:
                rate = None
            if pd.notnull(dt) and rate is not None:
                tasas_map[(dt.year, dt.month)] = rate
        return tasas_map
    except Exception as e:
        st.error(f"Error al procesar el Excel: {e}")
        return None

def calcular_interes_pasivocol_preciso(capital, anio_mesada, mes_mesada, fecha_corte, tasas_db, tasa_manual):
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

st.title("🏦 Liquidador Pro - Cuotas Partes con Aplicación Selectiva de Pagos")
st.markdown("Sincronizado con **UGPP**. Permite imputación automática (FIFO) o dirigida a periodos específicos.")

with st.sidebar:
    st.header("1. Datos Técnicos")
    archivo_excel = st.file_uploader("Excel BanRep (Serie DTF)", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=5.0)
    st.divider()
    st.header("2. Información del Caso")
    pensionado = st.text_input("Nombre del Pensionado", "JOSE OSCAR ORTIZ")
    porcentaje_cp = st.number_input("% Cuota Parte", value=37.38, step=0.01)
    fecha_corte = st.date_input("Fecha de Corte", value=date(2026, 4, 30))

# Tabs de configuración
tabs_input = st.tabs(["💰 Mesadas y Periodos", "💸 Configuración de Abonos"])

with tabs_input[0]:
    st.subheader("Mesadas y Periodos")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_inicio = st.date_input("Fecha Inicio", value=date(2022, 1, 1))
    with col_f2:
        f_fin = st.date_input("Fecha Fin", value=date(2026, 4, 30))

    años_rango = list(range(f_inicio.year, f_fin.year + 1))
    df_mesadas_anuales = pd.DataFrame({"Año": años_rango, "Mesada_Mensual": [3374717.0] * len(años_rango)})
    edit_mesadas = st.data_editor(df_mesadas_anuales, column_config={"Año": st.column_config.NumberColumn(disabled=True, format="%d"), "Mesada_Mensual": st.column_config.NumberColumn("Valor Mesada ($)", format="$ %d")}, use_container_width=True)
    mesadas_map = edit_mesadas.set_index("Año")["Mesada_Mensual"].to_dict()

# Generar lista de periodos posibles para el dropdown de abonos
lista_periodos_posibles = []
curr = f_inicio.replace(day=1)
while curr <= f_fin:
    lista_periodos_posibles.append(curr.strftime("%Y-%m"))
    curr += relativedelta(months=1)

with tabs_input[1]:
    st.subheader("Registro y Aplicación de Abonos")
    st.markdown("""
    **Modo de Aplicación:**
    * **FIFO (Hacia Deuda Antigua):** El pago se distribuye automáticamente cubriendo lo más viejo primero.
    * **Periodo Específico:** El pago se aplica únicamente a los intereses y capital del mes seleccionado.
    """)
    
    if 'abonos_data' not in st.session_state:
        st.session_state.abonos_data = pd.DataFrame([
            {"Fecha_Abono": date(2024, 1, 15), "Valor_Abono": 0.0, "Modo": "FIFO (Hacia Deuda Antigua)", "Periodo_Destino": "N/A"}
        ])

    edit_abonos = st.data_editor(
        st.session_state.abonos_data,
        column_config={
            "Fecha_Abono": st.column_config.DateColumn("Fecha Pago"),
            "Valor_Abono": st.column_config.NumberColumn("Valor Pagado ($)", format="$ %d"),
            "Modo": st.column_config.SelectboxColumn("Modo de Aplicación", options=["FIFO (Hacia Deuda Antigua)", "Periodo Específico"]),
            "Periodo_Destino": st.column_config.SelectboxColumn("Periodo Destino", options=["N/A"] + lista_periodos_posibles)
        },
        num_rows="dynamic",
        use_container_width=True
    )

if st.button("🚀 Calcular e Imputar Pagos", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success("✅ Tasas cargadas.")

    # 1. Generar registros de deuda bruta
    resultados_liq = []
    fecha_actual = f_inicio.replace(day=1)
    while fecha_actual <= f_fin:
        anio, mes = fecha_actual.year, fecha_actual.month
        mesada_base = mesadas_map.get(anio, 0)
        mesada_pensional = mesada_base * 2 if mes in [6, 12] else mesada_base
        cp_principal = round(mesada_pensional * (porcentaje_cp / 100), 2)
        interes_v, dias_n, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(cp_principal, anio, mes, fecha_corte, tasas_db, tasa_manual)
        
        resultados_liq.append({
            "Periodo": f"{anio}-{mes:02d}",
            "Mesada Pensional": float(mesada_pensional),
            "Cap. Bruto": float(cp_principal),
            "Int. Bruto": float(interes_v),
            "Tasa DTF": float(tasa_usada / 100),
            "Abono Específico": 0.0,
            "Abono FIFO a Int.": 0.0,
            "Abono FIFO a Cap.": 0.0,
            "Abono Específico a Int.": 0.0,
            "Abono Específico a Cap.": 0.0,
            "Saldo Periodo": 0.0
        })
        fecha_actual += relativedelta(months=1)

    # 2. Procesar Abonos Específicos Primero
    abonos_especificos = edit_abonos[(edit_abonos["Modo"] == "Periodo Específico") & (edit_abonos["Valor_Abono"] > 0)]
    for _, abono in abonos_especificos.iterrows():
        periodo_target = abono["Periodo_Destino"]
        valor_restante = abono["Valor_Abono"]
        for res in resultados_liq:
            if res["Periodo"] == periodo_target:
                # Pagar intereses del periodo específico
                pago_int = min(res["Int. Bruto"], valor_restante)
                res["Abono Específico a Int."] += round(pago_int, 2)
                valor_restante -= pago_int
                # Pagar capital del periodo específico
                pago_cap = min(res["Cap. Bruto"], valor_restante)
                res["Abono Específico a Cap."] += round(pago_cap, 2)
                valor_restante -= pago_cap
                break

    # 3. Procesar Abonos FIFO (Bolsa General)
    bolsa_pagos_fifo = edit_abonos[(edit_abonos["Modo"] == "FIFO (Hacia Deuda Antigua)") & (edit_abonos["Valor_Abono"] > 0)]["Valor_Abono"].sum()
    
    for res in resultados_liq:
        # Calcular remanente después de abonos específicos
        int_remanente = res["Int. Bruto"] - res["Abono Específico a Int."]
        cap_remanente = res["Cap. Bruto"] - res["Abono Específico a Cap."]
        
        # Aplicar FIFO a Intereses
        pago_fifo_int = min(int_remanente, bolsa_pagos_fifo)
        res["Abono FIFO a Int."] = round(pago_fifo_int, 2)
        bolsa_pagos_fifo -= pago_fifo_int
        
        # Aplicar FIFO a Capital
        pago_fifo_cap = min(cap_remanente, bolsa_pagos_fifo)
        res["Abono FIFO a Cap."] = round(pago_fifo_cap, 2)
        bolsa_pagos_fifo -= pago_fifo_cap
        
        # Saldo Final
        total_deuda = res["Cap. Bruto"] + res["Int. Bruto"]
        total_pagos = res["Abono Específico a Int."] + res["Abono Específico a Cap."] + res["Abono FIFO a Int."] + res["Abono FIFO a Cap."]
        res["Saldo Periodo"] = round(total_deuda - total_pagos, 2)

    df_final = pd.DataFrame(resultados_liq)

    # --- RESULTADOS ---
    st.divider()
    st.subheader("📋 Resumen Post-Imputación")
    c1, c2, c3, c4 = st.columns(4)
    total_bruto = df_final["Cap. Bruto"].sum() + df_final["Int. Bruto"].sum()
    abonos_totales = edit_abonos["Valor_Abono"].sum()
    c1.metric("Deuda Bruta Total", f"$ {total_bruto:,.0f}")
    c2.metric("Total Abonos", f"$ {abonos_totales:,.0f}", delta=f"-{abonos_totales:,.0f}", delta_color="inverse")
    c3.metric("Intereses Vigentes", f"$ {df_final['Int. Bruto'].sum() - (df_final['Abono Específico a Int.'].sum() + df_final['Abono FIFO a Int.'].sum()):,.0f}")
    c4.metric("SALDO FINAL", f"$ {df_final['Saldo Periodo'].sum():,.0f}")

    # Tabla Detallada
    # Consolidamos columnas de abonos para la vista
    df_view = df_final.copy()
    df_view["Pagos a Interés"] = df_view["Abono Específico a Int."] + df_view["Abono FIFO a Int."]
    df_view["Pagos a Capital"] = df_view["Abono Específico a Cap."] + df_view["Abono FIFO a Cap."]
    
    cols_mostrar = ["Periodo", "Mesada Pensional", "Cap. Bruto", "Int. Bruto", "Pagos a Interés", "Pagos a Capital", "Saldo Periodo"]
    st.dataframe(df_view[cols_mostrar].style.format({
        "Mesada Pensional": "${:,.0f}", "Cap. Bruto": "${:,.0f}", "Int. Bruto": "${:,.0f}",
        "Pagos a Interés": "${:,.0f}", "Pagos a Capital": "${:,.0f}", "Saldo Periodo": "${:,.0f}"
    }), use_container_width=True)

    # Excel
    excel_data = to_excel(df_final, edit_abonos, pensionado)
    st.download_button("📥 Descargar Reporte Completo (Excel)", excel_data, f"Liquidacion_Pro_{pensionado}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
