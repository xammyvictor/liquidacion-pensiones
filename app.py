import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go

# Configuración
st.set_page_config(page_title="Liquidador Cuotas Partes", page_icon="📝", layout="wide")

def calcular_intereses_compuestos(capital, dtf_anual, dias):
    """
    Fórmula según PDF: I = CP * ((1 + DTF)^(n/365) - 1)
    Donde DTF es la tasa anual expresada en decimal.
    """
    i_decimal = dtf_anual / 100
    factor = (1 + i_decimal)**(dias / 365) - 1
    return capital * factor

# --- INTERFAZ ---
st.title("📝 Liquidador de Cuotas Partes Vencidas")
st.info("Basado en la Carta Circular 2-2016-039942 (Metodología Pasivocol / MinHacienda)")

with st.sidebar:
    st.header("Configuración General")
    entidad_emisora = st.text_input("Entidad que Pagó", "Entidad A")
    entidad_deudora = st.text_input("Entidad Deudora", "Entidad B")
    pensionado = st.text_input("Nombre del Pensionado", "Juan Pérez")
    porcentaje_cuota = st.number_input("% Cuota Parte", min_value=0.0, max_value=100.0, value=50.0, step=0.01)
    
    st.divider()
    st.subheader("Parámetros Financieros")
    dtf_referencia = st.number_input("DTF Anual Referencia (%)", value=12.0, help="Tasa para el cálculo de intereses")
    fecha_corte = st.date_input("Fecha de Corte de Liquidación", value=date.today())

st.subheader("1. Periodo y Valores de Mesada")
col_f1, col_f2 = st.columns(2)
with col_f1:
    fecha_inicio = st.date_input("Fecha Inicio Liquidación", value=date.today() - relativedelta(years=1))
with col_f2:
    fecha_fin = st.date_input("Fecha Fin Liquidación", value=date.today())

# Generar lista de meses entre fechas
def generar_meses(inicio, fin):
    meses = []
    actual = inicio.replace(day=1)
    while actual <= fin:
        meses.append(actual)
        actual += relativedelta(months=1)
    return meses

lista_meses = generar_meses(fecha_inicio, fecha_fin)

st.markdown("---")
st.write("### 2. Ingreso de Valores Pagados")
st.caption("Ingrese el valor total de la mesada pagada en cada periodo. El sistema calculará automáticamente la cuota parte.")

# Tabla editable para valores
data_inicial = {
    "Periodo": [m.strftime("%Y-%m") for m in lista_meses],
    "Mesada_Pagada": [2500000.0] * len(lista_meses)
}
df_input = pd.DataFrame(data_inicial)

edited_df = st.data_editor(
    df_input,
    column_config={
        "Periodo": st.column_config.TextColumn("Periodo", disabled=True),
        "Mesada_Pagada": st.column_config.NumberColumn("Valor Mesada ($)", format="$ %d")
    },
    num_rows="dynamic",
    use_container_width=True
)

if st.button("🚀 Generar Liquidación Detallada", type="primary"):
    # Procesamiento de datos
    resultados = []
    total_capital = 0
    total_intereses = 0
    
    # Fecha para cálculo de prescripción (3 años atrás desde hoy o fecha de corte)
    fecha_limite_prescripcion = fecha_corte - relativedelta(years=3)

    for index, row in edited_df.iterrows():
        periodo_date = datetime.strptime(row["Periodo"], "%Y-%m").date()
        # El interés se causa a partir del mes siguiente al pago (último día del mes siguiente)
        fecha_causacion_interes = periodo_date + relativedelta(months=1)
        
        # Días para intereses: Desde el primer día del mes siguiente al pago hasta la fecha de corte
        if fecha_corte > fecha_causacion_interes:
            dias_mora = (fecha_corte - fecha_causacion_interes).days
        else:
            dias_mora = 0
            
        cuota_parte_principal = row["Mesada_Pagada"] * (porcentaje_cuota / 100)
        interes_calculado = calcular_intereses_compuestos(cuota_parte_principal, dtf_referencia, dias_mora)
        
        # Validación de prescripción
        estado_prescripcion = "Vigente" if periodo_date >= fecha_limite_prescripcion else "⚠️ Posible Prescripción"
        
        resultados.append({
            "Periodo": row["Periodo"],
            "Mesada Total": row["Mesada_Pagada"],
            "Cuota Parte (Cap)": cuota_parte_principal,
            "Días Mora": dias_mora,
            "Intereses DTF": interes_calculado,
            "Total Mes": cuota_parte_principal + interes_calculado,
            "Estado": estado_prescripcion
        })
        
        if estado_prescripcion == "Vigente":
            total_capital += cuota_parte_principal
            total_intereses += interes_calculado

    df_res = pd.DataFrame(resultados)

    # --- MÉTRICAS ---
    st.markdown("### 3. Resumen de Liquidación")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Capital (Vigente)", f"$ {total_capital:,.0f}")
    m2.metric("Total Intereses", f"$ {total_intereses:,.0f}")
    m3.metric("GRAN TOTAL", f"$ {total_capital + total_intereses:,.0f}")

    # --- TABLA FINAL ---
    st.dataframe(
        df_res.style.format({
            "Mesada Total": "${:,.0f}",
            "Cuota Parte (Cap)": "${:,.0f}",
            "Intereses DTF": "${:,.0f}",
            "Total Mes": "${:,.0f}"
        }).applymap(lambda x: 'color: red' if x == "⚠️ Posible Prescripción" else '', subset=['Estado']),
        use_container_width=True
    )

    # Gráfico de composición
    fig = go.Figure(data=[
        go.Bar(name='Capital', x=df_res['Periodo'], y=df_res['Cuota Parte (Cap)']),
        go.Bar(name='Intereses', x=df_res['Periodo'], y=df_res['Intereses DTF'])
    ])
    fig.update_layout(barmode='stack', title="Evolución de la Deuda por Periodo")
    st.plotly_chart(fig, use_container_width=True)

    # Exportar
    csv = df_res.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Descargar Liquidación (CSV)",
        csv,
        f"liquidacion_{pensionado}.csv",
        "text/csv",
        key='download-csv'
    )
