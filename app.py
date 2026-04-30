import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import io

st.set_page_config(
    page_title="Liquidador Pasivocol DTF",
    page_icon="🏦",
    layout="wide"
)

# --- FUNCIONES ---

def dias_360(fecha_inicio, fecha_fin):
    if fecha_inicio > fecha_fin:
        return 0

    d1 = min(30, fecha_inicio.day)
    d2 = min(30, fecha_fin.day)

    if fecha_fin.month == 2 and fecha_fin.day in [28, 29]:
        d2 = 30

    resultado = (
        (fecha_fin.year - fecha_inicio.year) * 360
        + (fecha_fin.month - fecha_inicio.month) * 30
        + (d2 - d1)
    )

    return int(resultado + 1)


def cargar_tasas_banrep(file):
    try:
        df_raw = pd.read_excel(file, sheet_name="Series de datos", header=None)

        start_row = 0
        for i, val in enumerate(df_raw.iloc[:, 0]):
            test_date = pd.to_datetime(val, errors="coerce")
            if pd.notnull(test_date):
                start_row = i
                break

        df_data = df_raw.iloc[start_row:].copy()
        tasas_map = {}

        for _, row in df_data.iterrows():
            dt = pd.to_datetime(row.iloc[0], errors="coerce")

            try:
                rate = float(row.iloc[1])
            except:
                rate = None

            if pd.notnull(dt) and rate is not None:
                tasas_map[(dt.year, dt.month)] = rate

        return tasas_map

    except Exception as e:
        st.error(f"Error al procesar el Excel: {e}")
        return None


def calcular_interes_pasivocol_preciso(
    capital,
    anio_mesada,
    mes_mesada,
    fecha_corte,
    tasas_db,
    tasa_manual
):
    f_pago = date(anio_mesada, mes_mesada, 1)
    f_inicio_interes = f_pago + relativedelta(months=1)

    if fecha_corte < f_inicio_interes:
        return 0.0, 0, f_inicio_interes, tasa_manual

    n = dias_360(f_inicio_interes, fecha_corte)

    tasa_aplicable = tasas_db.get(
        (anio_mesada, mes_mesada),
        tasa_manual
    )

    i_decimal = tasa_aplicable / 100
    interes = capital * ((1 + i_decimal) ** (n / 365) - 1)

    return round(float(interes), 2), n, f_inicio_interes, tasa_aplicable


def to_excel(df_liq, df_abonos, nombre_pensionado):
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_liq.to_excel(writer, index=False, sheet_name="Liquidacion")
        df_abonos.to_excel(writer, index=False, sheet_name="Detalle_Abonos")

        workbook = writer.book
        ws_liq = writer.sheets["Liquidacion"]
        ws_abo = writer.sheets["Detalle_Abonos"]

        fmt_money = workbook.add_format({
            "num_format": "$#,##0",
            "align": "right"
        })

        fmt_pct = workbook.add_format({
            "num_format": "0.00%",
            "align": "center"
        })

        fmt_date = workbook.add_format({
            "num_format": "dd/mm/yyyy",
            "align": "center"
        })

        ws_liq.set_column("A:A", 12)
        ws_liq.set_column("B:D", 18, fmt_money)
        ws_liq.set_column("E:E", 12)
        ws_liq.set_column("F:F", 12, fmt_pct)
        ws_liq.set_column("G:K", 22, fmt_money)
        ws_liq.set_column("L:L", 18, fmt_money)

        ws_abo.set_column("A:A", 15, fmt_date)
        ws_abo.set_column("B:B", 20, fmt_money)
        ws_abo.set_column("C:C", 28)
        ws_abo.set_column("D:D", 45)

    return output.getvalue()


# --- INTERFAZ ---

st.title("🏦 Liquidador Pro - Cuotas Partes con Selección de Periodos")
st.markdown(
    "Sincronizado con **UGPP**. Seleccione los meses específicos para aplicar abonos."
)

with st.sidebar:
    st.header("1. Datos Técnicos")

    archivo_excel = st.file_uploader(
        "Excel BanRep (Serie DTF)",
        type=["xlsx"]
    )

    tasa_manual = st.number_input(
        "Tasa de respaldo (%)",
        value=5.0
    )

    st.divider()

    st.header("2. Información del Caso")

    pensionado = st.text_input(
        "Nombre del Pensionado",
        "JOSE OSCAR ORTIZ"
    )

    porcentaje_cp = st.number_input(
        "% Cuota Parte",
        value=37.38,
        step=0.01
    )

    fecha_corte = st.date_input(
        "Fecha de Corte",
        value=date.today()
    )


tabs_input = st.tabs([
    "💰 Mesadas y Periodos",
    "💸 Configuración de Abonos"
])


with tabs_input[0]:
    st.subheader("Mesadas y Periodos")

    col_f1, col_f2 = st.columns(2)

    with col_f1:
        f_inicio = st.date_input(
            "Fecha Inicio",
            value=date(2022, 1, 1)
        )

    with col_f2:
        f_fin = st.date_input(
            "Fecha Fin",
            value=date(2026, 4, 30)
        )

    años_rango = list(range(f_inicio.year, f_fin.year + 1))

    df_mesadas_anuales = pd.DataFrame({
        "Año": años_rango,
        "Mesada_Mensual": [3374717.0] * len(años_rango)
    })

    edit_mesadas = st.data_editor(
        df_mesadas_anuales,
        column_config={
            "Año": st.column_config.NumberColumn(
                disabled=True,
                format="%d"
            ),
            "Mesada_Mensual": st.column_config.NumberColumn(
                "Valor Mesada ($)",
                format="$ %d"
            )
        },
        use_container_width=True,
        key="editor_mesadas"
    )

    mesadas_map = edit_mesadas.set_index("Año")["Mesada_Mensual"].to_dict()


# --- PERIODOS DISPONIBLES ---

lista_periodos_posibles = []
temp_fecha = f_inicio.replace(day=1)

while temp_fecha <= f_fin:
    lista_periodos_posibles.append(temp_fecha.strftime("%Y-%m"))
    temp_fecha += relativedelta(months=1)


with tabs_input[1]:
    st.subheader("Registro de Abonos con Selección Múltiple")

    st.info(
        "💡 Puede agregar varios abonos. En 'Seleccionar Mes(es)', "
        "el orden elegido será respetado al aplicar el abono específico."
    )

    df_abonos_inicial = pd.DataFrame([
        {
            "Fecha_Abono": date(2024, 1, 15),
            "Valor_Abono": 0.0,
            "Modo": "FIFO (Hacia Deuda Antigua)",
            "Periodos_Destino": []
        }
    ])

    edit_abonos = st.data_editor(
        df_abonos_inicial,
        column_config={
            "Fecha_Abono": st.column_config.DateColumn(
                "Fecha Pago",
                required=True
            ),
            "Valor_Abono": st.column_config.NumberColumn(
                "Valor Pagado ($)",
                format="$ %d",
                min_value=0.0
            ),
            "Modo": st.column_config.SelectboxColumn(
                "Modo de Aplicación",
                options=[
                    "FIFO (Hacia Deuda Antigua)",
                    "Periodo(s) Específico(s)"
                ],
                required=True
            ),
            "Periodos_Destino": st.column_config.MultiselectColumn(
                "Seleccionar Mes(es)",
                options=lista_periodos_posibles,
                help="Seleccione los meses en el orden en que desea aplicar el abono"
            )
        },
        num_rows="dynamic",
        use_container_width=True,
        key="editor_abonos"
    )

    edit_abonos["Periodos_Destino"] = edit_abonos["Periodos_Destino"].apply(
        lambda x: x if isinstance(x, list) else []
    )

    edit_abonos["Valor_Abono"] = pd.to_numeric(
        edit_abonos["Valor_Abono"],
        errors="coerce"
    ).fillna(0.0)

    edit_abonos["Modo"] = edit_abonos["Modo"].fillna(
        "FIFO (Hacia Deuda Antigua)"
    )


# --- CÁLCULO ---

if st.button("🚀 Calcular e Imputar Pagos", type="primary"):

    tasas_db = {}

    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)

        if tasas_db:
            st.success("✅ Tasas cargadas satisfactoriamente.")

    resultados_liq = []
    fecha_actual = f_inicio.replace(day=1)

    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month

        mesada_base = mesadas_map.get(anio, 0)

        mesada_pensional = (
            mesada_base * 2
            if mes in [6, 12]
            else mesada_base
        )

        cp_principal = round(
            mesada_pensional * (porcentaje_cp / 100),
            2
        )

        interes_v, dias_n, f_causacion, tasa_usada = calcular_interes_pasivocol_preciso(
            cp_principal,
            anio,
            mes,
            fecha_corte,
            tasas_db,
            tasa_manual
        )

        resultados_liq.append({
            "Periodo": f"{anio}-{mes:02d}",
            "Mesada Pensional": float(mesada_pensional),
            "Cap. Bruto": float(cp_principal),
            "Int. Bruto": float(interes_v),
            "Días Interés": int(dias_n),
            "Tasa DTF": float(tasa_usada / 100),
            "Abono Específico a Int.": 0.0,
            "Abono Específico a Cap.": 0.0,
            "Abono FIFO a Int.": 0.0,
            "Abono FIFO a Cap.": 0.0,
            "Saldo Periodo": 0.0
        })

        fecha_actual += relativedelta(months=1)

    resultados_por_periodo = {
        res["Periodo"]: res
        for res in resultados_liq
    }

    # --- ABONOS ESPECÍFICOS ---

    sobrante_bolsa_fifo = 0.0

    abonos_especificos = edit_abonos[
        (edit_abonos["Modo"] == "Periodo(s) Específico(s)") &
        (edit_abonos["Valor_Abono"] > 0)
    ]

    for _, abono in abonos_especificos.iterrows():

        targets = abono["Periodos_Destino"]

        if not isinstance(targets, list):
            targets = []

        valor_disponible = float(abono["Valor_Abono"])

        for periodo_destino in targets:

            if periodo_destino not in resultados_por_periodo:
                continue

            res = resultados_por_periodo[periodo_destino]

            int_pdte = (
                res["Int. Bruto"]
                - res["Abono Específico a Int."]
                - res["Abono FIFO a Int."]
            )

            pago_int = min(max(int_pdte, 0), valor_disponible)

            res["Abono Específico a Int."] += round(pago_int, 2)
            valor_disponible -= pago_int

            cap_pdte = (
                res["Cap. Bruto"]
                - res["Abono Específico a Cap."]
                - res["Abono FIFO a Cap."]
            )

            pago_cap = min(max(cap_pdte, 0), valor_disponible)

            res["Abono Específico a Cap."] += round(pago_cap, 2)
            valor_disponible -= pago_cap

            if valor_disponible <= 0:
                break

        if valor_disponible > 0:
            sobrante_bolsa_fifo += valor_disponible

    # --- ABONOS FIFO ---

    bolsa_pagos_fifo = edit_abonos[
        (edit_abonos["Modo"] == "FIFO (Hacia Deuda Antigua)") &
        (edit_abonos["Valor_Abono"] > 0)
    ]["Valor_Abono"].sum()

    bolsa_pagos_fifo += sobrante_bolsa_fifo

    if sobrante_bolsa_fifo > 0:
        st.info(
            f"💡 Se detectó un excedente de "
            f"${sobrante_bolsa_fifo:,.0f} de abonos específicos "
            f"que se aplicó a la deuda más antigua."
        )

    for res in resultados_liq:

        int_remanente = (
            res["Int. Bruto"]
            - res["Abono Específico a Int."]
        )

        pago_fifo_int = min(max(int_remanente, 0), bolsa_pagos_fifo)

        res["Abono FIFO a Int."] = round(pago_fifo_int, 2)
        bolsa_pagos_fifo -= pago_fifo_int

        cap_remanente = (
            res["Cap. Bruto"]
            - res["Abono Específico a Cap."]
        )

        pago_fifo_cap = min(max(cap_remanente, 0), bolsa_pagos_fifo)

        res["Abono FIFO a Cap."] = round(pago_fifo_cap, 2)
        bolsa_pagos_fifo -= pago_fifo_cap

        total_deuda = res["Cap. Bruto"] + res["Int. Bruto"]

        total_pagos = (
            res["Abono Específico a Int."]
            + res["Abono Específico a Cap."]
            + res["Abono FIFO a Int."]
            + res["Abono FIFO a Cap."]
        )

        res["Saldo Periodo"] = round(total_deuda - total_pagos, 2)

    df_final = pd.DataFrame(resultados_liq)

    # --- RESULTADOS ---

    st.divider()
    st.subheader("📋 Resumen Post-Imputación")

    c1, c2, c3, c4, c5 = st.columns(5)

    total_cuota_parte = df_final["Cap. Bruto"].sum()

    total_bruto = (
        df_final["Cap. Bruto"].sum()
        + df_final["Int. Bruto"].sum()
    )

    abonos_totales = edit_abonos["Valor_Abono"].sum()

    intereses_vigentes = (
        df_final["Int. Bruto"].sum()
        - (
            df_final["Abono Específico a Int."].sum()
            + df_final["Abono FIFO a Int."].sum()
        )
    )

    saldo_final = df_final["Saldo Periodo"].sum()

    c1.metric("Valor Total Cuota Parte", f"$ {total_cuota_parte:,.0f}")
    c2.metric("Deuda Bruta Total", f"$ {total_bruto:,.0f}")

    c3.metric(
        "Total Abonos",
        f"$ {abonos_totales:,.0f}",
        delta=f"-{abonos_totales:,.0f}",
        delta_color="inverse"
    )

    c4.metric("Intereses Vigentes", f"$ {intereses_vigentes:,.0f}")
    c5.metric("SALDO FINAL", f"$ {saldo_final:,.0f}")

    df_view = df_final.copy()

    df_view["Pagos a Interés"] = (
        df_view["Abono Específico a Int."]
        + df_view["Abono FIFO a Int."]
    )

    df_view["Pagos a Capital"] = (
        df_view["Abono Específico a Cap."]
        + df_view["Abono FIFO a Cap."]
    )

    cols_mostrar = [
        "Periodo",
        "Cap. Bruto",
        "Int. Bruto",
        "Días Interés",
        "Tasa DTF",
        "Pagos a Interés",
        "Pagos a Capital",
        "Saldo Periodo"
    ]

    st.dataframe(
        df_view[cols_mostrar].style.format({
            "Cap. Bruto": "${:,.0f}",
            "Int. Bruto": "${:,.0f}",
            "Días Interés": "{:,.0f}",
            "Tasa DTF": "{:.2%}",
            "Pagos a Interés": "${:,.0f}",
            "Pagos a Capital": "${:,.0f}",
            "Saldo Periodo": "${:,.0f}"
        }),
        use_container_width=True
    )

    df_abonos_excel = edit_abonos.copy()

    df_abonos_excel["Periodos_Destino"] = (
        df_abonos_excel["Periodos_Destino"]
        .apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
    )

    excel_data = to_excel(
        df_final,
        df_abonos_excel,
        pensionado
    )

    st.download_button(
        "📥 Descargar Reporte Completo (Excel)",
        excel_data,
        f"Liquidacion_Pro_{pensionado}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
