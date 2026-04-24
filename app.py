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
        # Leemos el archivo buscando la hoja correcta
        # Nota: Ajustamos para encontrar el encabezado dinámicamente
        df_raw = pd.read_excel(file, sheet_name="Series de datos")
        
        # Encontrar la fila donde empieza 'Fecha' en la columna A
        header_row = 0
        for i, row in df_raw.iterrows():
            if str(row.iloc[0]).strip().lower() == "fecha":
                header_row = i
                break
        
        # Volver a leer con el encabezado correcto
        df = pd.read_excel(file, sheet_name="Series de datos", skiprows=header_row + 1)
        # La lectura de arriba deja los nombres de columnas en la fila header_row+1. 
        # Intentemos una limpieza más directa de las columnas del dataframe original:
        df = df_raw.iloc[header_row+1:].copy()
        df.columns = df_raw.iloc[header_row] # Asignar la fila 'Fecha', '1. DTF...' como nombres de columna
        
        # Limpiar nombres de columnas
        df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
        
        col_fecha = df.columns[0] 
        col_dtf = [c for c in df.columns if "1. DTF promedio mensual" in c]
        
        if not col_dtf:
            st.error("No se encontró la columna '1. DTF promedio mensual'. Verifique el formato del Excel.")
            return None
        
        col_dtf = col_dtf[0]
        
        # Convertir fecha y limpiar
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
        df = df.dropna(subset=[col_fecha, col_dtf])
        
        # Asegurar que DTF sea numérico
        df[col_dtf] = pd.to_numeric(df[col_dtf], errors='coerce')
        df = df.dropna(subset=[col_dtf])
        
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
    """
    # Fecha Causación: último día del mes de pago
    fecha_causacion = (fecha_pago_mesada + relativedelta(day=31))
    
    # El interés inicia el mes siguiente
    fecha_inicio_interes = fecha_causacion + relativedelta(days=1)
    
    if fecha_corte < fecha_inicio_interes:
        return 0, 0, fecha_causacion
    
    dias = (fecha_corte - fecha_causacion).days
    i_decimal = tasa_anual / 100
    interes = capital * ((1 + i_decimal)**(dias / 365) - 1)
    return interes, dias, fecha_causacion

# --- INTERFAZ ---

st.title("🏦 Liquidador de Cuotas Partes - Estilo Pasivocol")
st.markdown("Liquidación técnica con **DTF mensual del Banco de la República**, mesadas anualizadas y primas de ley.")

with st.sidebar:
    st.header("1. Carga de Tasas")
    archivo_excel = st.file_uploader("Subir Excel de BanRep (Hoja: 'Series de datos')", type=["xlsx"])
    tasa_manual = st.number_input("Tasa de respaldo (%)", value=12.0, help="Se usará solo si el mes no está en el Excel.")

    st.divider()
    st.header("2. Parámetros de Liquidación")
    pensionado = st.text_input("Nombre del Pensionado", "Juan Pérez")
    porcentaje_cp = st.number_input("% Cuota Parte", value=50.0, step=0.1)
    fecha_corte = st.date_input("Fecha de Corte (Hasta cuándo liquidar)", value=date.today())

st.subheader("1. Periodo de Liquidación")
col_f1, col_f2 = st.columns(2)
with col_f1:
    f_inicio = st.date_input("Fecha Inicio", value=date(2022, 1, 1))
with col_f2:
    f_fin = st.date_input("Fecha Fin", value=date(2023, 12, 31))

# --- ENTRADA DE MESADAS POR AÑO ---
st.subheader("2. Valor de Mesada por Año")
st.info("Actualice aquí el valor de la mesada de cada año. Se aplicará a los 12 meses y a las primas de junio/diciembre.")

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
if st.button("🚀 Generar Liquidación Pasivocol", type="primary"):
    tasas_db = {}
    if archivo_excel:
        tasas_db = cargar_tasas_banrep(archivo_excel)
        if tasas_db:
            st.success(f"✅ Se cargaron {len(tasas_db)} periodos de tasas desde el Excel.")
        else:
            st.warning("⚠️ No se pudo extraer la información del Excel. Se usará la tasa de respaldo.")

    # Generar todos los meses en el rango
    resultados = []
    fecha_actual = f_inicio.replace(day=1)
    
    while fecha_actual <= f_fin:
        anio = fecha_actual.year
        mes = fecha_actual.month
        
        mesada_mensual = mesadas_map.get(anio, 0)
        # Intentar obtener tasa del Excel, si no existe usar la manual
        tasa_aplicable = tasas_db.get((anio, mes), tasa_manual)
        
        # Tipos de mesada: Normal + Adicionales en Junio y Diciembre
        tipos_mesada = [{"nombre": f"{anio}-{mes:02d}", "multiplicador": 1}]
        
        if mes == 6:
            tipos_mesada.append({"nombre": f"{anio}-{mes:02d} (Prima)", "multiplicador": 1})
        if mes == 12:
            tipos_mesada.append({"nombre": f"{anio}-{mes:02d} (Prima)", "multiplicador": 1})
        
        for item in tipos_mesada:
            # Fecha de pago: último día del mes
            f_pago = (fecha_actual + relativedelta(months=1, days=-1))
            
            # Valor de la mesada para este registro
            valor_pensional = mesada_mensual * item["multiplicador"]
            cp_principal = valor_pensional * (porcentaje_cp / 100)
            
            # Cálculo intereses
            interes_v, dias_m, f_causacion = calcular_interes_pasivocol(cp_principal, tasa_aplicable, f_pago, fecha_corte)
            
            resultados.append({
                "Periodo": item["nombre"],
                "Mesada Pensional": valor_pensional,
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
    c1.metric("Total Cuota Parte (Principal)", f"$ {df_final['Cuota Parte'].sum():,.0f}")
    c2.metric("Total Intereses", f"$ {df_final['Intereses'].sum():,.0f}")
    c3.metric("GRAN TOTAL DEUDA", f"$ {df_final['Total'].sum():,.0f}")

    # Estructura visual Pasivocol
    st.write("### Cuadro Detallado de Liquidación")
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
    st.download_button("📥 Descargar Reporte (CSV)", csv, f"liquidacion_{pensionado}.csv", "text/csv")

    # Gráfico de barras de la deuda
    fig = go.Figure(data=[
        go.Bar(name='Capital', x=df_final['Periodo'], y=df_final['Cuota Parte']),
        go.Bar(name='Intereses', x=df_final['Periodo'], y=df_final['Intereses'])
    ])
    fig.update_layout(barmode='stack', title="Composición de la Deuda por Periodo", xaxis_title="Periodo", yaxis_title="Valor ($)")
    st.plotly_chart(fig, use_container_width=True)
