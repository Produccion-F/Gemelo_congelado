# -*- coding: utf-8 -*-
import streamlit as st
import time
import pandas as pd
from collections import deque
import datetime
import altair as alt # Importar Altair

# --- Configuración de la página ---
st.set_page_config(
    page_title="Gemelo Digital: Flujo de KG",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={'About': "Gemelo Digital de Flujo de Producción"}
)

# --- Inicializar variables de estado de sesión ---
default_values = {
    "fecha_inicio": datetime.date.today(),
    "duracion_simulacion": 72, "kg_iniciales_camara": 0,
    "kg_iniciales_tunel_congelado": 0, "kg_iniciales_tunel_frescos": 0,
    "horas_restantes_congelacion": 12,
    "segundos_por_hora_sim": 0.25,
    "d_inicio": 4, "d_cerdos": 1000, "d_velo": 565, "d_oee": 85, "d_peso": 80.0,
    "d_peso_despojos": 5.0, # Añadido para que no falte
    "d_extra_check": False, "d_inicio_extra": 4, "d_cerdos_extra": 1000,
    "d_peso_despojos_extra": 5.0, # Añadido para que no falte
    "c_inicio": 6, "c_duracion": 16,
    "c_extra_check": False, "c_inicio_extra": 6, "c_duracion_extra": 16, "c_kg_extra": 8750,
    "p_inicio": 4, "p_duracion": 20, "p_kg": 1500,
    "p_extra_check": False, "p_inicio_extra": 4, "p_duracion_extra": 20, "p_kg_extra": 1500,
    "f_inicio": 6, "f_duracion": 18, "f_kg_dia": 20000,
    "f_extra_check": False, "f_inicio_extra": 6, "f_duracion_extra": 18, "f_kg_dia_extra": 20000,
    "v_inicio": 4, "v_duracion": 20, "v_kg": 5500,
    "v_extra_check": False, "v_inicio_extra": 4, "v_duracion_extra": 20, "v_kg_extra": 5500
}
for i in range(7): default_values[f"c_linea_{i}"] = 1250
for key, value in default_values.items():
    if key not in st.session_state: st.session_state[key] = value
if 'kg_hora_cajas_total' not in st.session_state: st.session_state.kg_hora_cajas_total = sum(st.session_state.get(f"c_linea_{i}", 1250) for i in range(7))

# --- CSS Personalizado ---
st.markdown("""
<style>
/* Colores de la paleta */
:root {
    --primary-color: #3498db;  /* Azul para botones, etc. */
    --secondary-color: #e67e22; /* Naranja para el segundo color del gráfico */
    --danger-color: #e74c3c;   /* Rojo para alertas */
    --background-color: #ecf0f1; /* Gris claro para el fondo principal */
    --card-background-color: #ffffff; /* Blanco para tarjetas/contenedores */
    --text-color: #2c3e50;     /* Gris oscuro para el texto */
    --light-gray: #f9f99;    /* Un gris muy suave */
    --dark-blue: #2980b9;     /* Azul más oscuro */
}

/* Fondo de la aplicación completa */
body { background-color: var(--background-color); color: var(--text-color); }
div.stApp { background-color: var(--background-color); }
div[data-testid="stAppViewContainer"] { background-color: var(--background-color); }

/* Estilo de los headers de la app */
h1 { color: var(--dark-blue); text-align: center; font-size: 2.8rem; margin-bottom: 1.5rem; }
div[data-testid="stTabs"] h2 { color: var(--text-color); font-size: 2.2rem !important; font-weight: 600; }
div[data-testid="stTabs"] h3 { color: var(--dark-blue); font-size: 2rem !important; font-weight: 600; margin-top: 1.5rem; margin-bottom: 1rem; }
div[data-testid="stVerticalBlock"] { background-color: var(--background-color); padding: 1rem; border-radius: 8px; }

/* --- Pestañas --- */
div[data-baseweb="tab-list"] { background-color: var(--light-gray) !important; border-radius: 8px; padding: 0.5rem 0.5rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
/* Texto de las pestañas MUCHO más grande */
div[data-baseweb="tab-list"] button {
    font-size: 2.5rem !important; /* Ajustado */
    padding: 1rem 2rem !important; /* Ajustado */
    font-weight: 600 !important;
}
div[data-baseweb="tab-list"] button[aria-selected="true"] { background-color: var(--primary-color) !important; color: white !important; border-radius: 6px; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
div[data-baseweb="tab-list"] button[aria-selected="false"] { background-color: transparent !important; color: var(--text-color) !important; }

/* --- Formulario de Configuración --- */
div[data-testid="stNumberInput"] label p,
div[data-testid="stSlider"] label p,
div[data-testid="stCheckbox"] label p,
div[data-testid="stDateInput"] label p { font-size: 1.3rem !important; font-weight: 600 !important; color: var(--text-color); }
div[data-testid="stNumberInput"] input,
div[data-testid="stDateInput"] input { font-size: 1.3rem !important; padding: 0.5rem 1rem; border-radius: 5px; border: 1px solid #ccc; }
div[data-testid="stNumberInput"] input:focus,
div[data-testid="stDateInput"] input:focus { border-color: var(--primary-color); box-shadow: 0 0 0 0.1rem rgba(52, 152, 219, 0.25); }
.st-expander label p { font-size: 1.35rem !important; font-weight: 600 !important; color: var(--dark-blue); }

/* --- Métricas (st.metric) --- */
div[data-testid="stMetric"] { background-color: var(--card-background-color); padding: 1rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; margin-bottom: 1rem; }
div[data-testid="stMetric"] label { font-size: 1.1rem; color: var(--dark-blue); font-weight: bold; }
div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: var(--primary-color); font-weight: bolder; }
div[data-testid="stMetricDelta"] { font-size: 1rem; color: var(--text-color); }

/* --- Botón Primario --- */
button[kind="primary"] { background-color: var(--primary-color) !important; color: white !important; font-size: 1.5rem !important; padding: 0.8rem 2rem !important; border-radius: 8px !important; border: none !important; transition: background-color 0.3s ease !important; }
button[kind="primary"]:hover { background-color: var(--dark-blue) !important; color: white !important; }

/* --- Contenedores de Resultados --- */
.stDataFrame, .st-empty, .stPlotlyChart, .stAreaChart { background-color: var(--card-background-color); padding: 1rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
div[data-testid="stAlert"] { font-size: 1.2rem; padding: 1rem; border-radius: 8px; }
div[data-testid="stAlert"] > div { font-size: 1.2rem; }

/* --- Tabla Final de Resumen --- */
.stDataFrame { text-align: center; }
.stDataFrame th.col_heading { font-size: 2.5rem !important; text-align: center !important; font-weight: bold; color: var(--dark-blue); background-color: var(--light-gray) !important; padding: 12px 8px; }
.stDataFrame th.row_heading { font-size: 2.5rem !important; text-align: center !important; font-weight: bold; color: var(--dark-blue); background-color: var(--light-gray) !important; padding: 12px 8px; }
.stDataFrame td { font-size: 2.2rem !important; text-align: center !important; padding: 10px 8px; vertical-align: middle; }

/* --- CAMBIO CSS --- */
/* --- Visualización de Túneles --- */
.tunnel-grid-container { 
    display: grid; 
    /* Definimos las filas y dejamos que las columnas fluyan */
    grid-template-rows: repeat(var(--rows, 11), 1fr); 
    grid-auto-flow: column;
    grid-auto-columns: 1fr; /* Asegura que las columnas tengan ancho */
    
    gap: 3px; 
    border: 2px solid var(--dark-blue); 
    background-color: var(--light-gray); 
    padding: 5px; 
    border-radius: 5px; 
    max-width: 300px; 
    margin-left: auto; 
    margin-right: auto; 
}
.tunnel-cell { width: 100%; padding-bottom: 100%; background-color: #bdc3c7; border-radius: 2px; }
.tunnel-cell.filled { background-color: var(--primary-color); }
.tunnel-label { font-size: 1.5rem; font-weight: bold; color: var(--dark-blue); text-align: center; margin-bottom: 0.5rem; }
.tunnel-stats { font-size: 1.6rem !important; text-align: center; color: var(--text-color); margin-bottom: 0.5rem; line-height: 1.3; }
.metric-overflow { /* No se usa */ }
</style>
""", unsafe_allow_html=True)


# --- CLASE PARA MODELAR LOS TÚNELES ---
class Tunnel:
    def __init__(self, name, max_kg, max_pallets, rows, cols):
        self.name = name; self.max_kg = float(max_kg); self.max_pallets = float(max_pallets); self.rows = rows; self.cols = cols
        self.avg_kg_per_pallet = self.max_kg / self.max_pallets if self.max_pallets > 0 else 0
        self.kg_actual = 0.0; self.pallets_actual = 0.0; self.queue = deque()
    def get_kg_disponibles(self): return max(0, self.max_kg - self.kg_actual)
    def get_pallets_disponibles(self): return max(0, self.max_pallets - self.pallets_actual)
    def add_kg(self, kg_a_anadir, hora_actual):
        if self.avg_kg_per_pallet == 0: return kg_a_anadir
        kg_caben_por_peso = self.get_kg_disponibles(); pallets_caben = self.get_pallets_disponibles(); kg_caben_por_pallets = pallets_caben * self.avg_kg_per_pallet; kg_que_realmente_caben = max(0, min(kg_a_anadir, kg_caben_por_peso, kg_caben_por_pallets))
        if kg_que_realmente_caben > 0.01: pallets_a_anadir = kg_que_realmente_caben / self.avg_kg_per_pallet; self.queue.append({"kg": kg_que_realmente_caben, "pallets": pallets_a_anadir, "hora_entrada": hora_actual}); self.kg_actual += kg_que_realmente_caben; self.pallets_actual += pallets_a_anadir
        return kg_a_anadir - kg_que_realmente_caben
    def add_initial_kg(self, kg_iniciales, hora_entrada_calculada):
        kg_a_meter = min(kg_iniciales, self.get_kg_disponibles()); pallets_a_meter_max = self.get_pallets_disponibles(); kg_caben_por_pallets = pallets_a_meter_max * self.avg_kg_per_pallet; kg_a_meter = min(kg_a_meter, kg_caben_por_pallets)
        if kg_a_meter > 0.01 and self.avg_kg_per_pallet > 0:
            pallets_a_meter = kg_a_meter / self.avg_kg_per_pallet; self.queue.appendleft({"kg": kg_a_meter, "pallets": pallets_a_meter, "hora_entrada": hora_entrada_calculada}); self.kg_actual += kg_a_meter; self.pallets_actual += pallets_a_meter
            return kg_a_meter
        return 0.0
    def vaciar_kg(self, kg_a_vaciar_disponibles, hora_actual):
        kg_realmente_vaciados = 0.0
        while kg_a_vaciar_disponibles > 0.01 and len(self.queue) > 0:
            lote_frontal = self.queue[0]
            if lote_frontal["hora_entrada"] == -999 or hora_actual >= (lote_frontal["hora_entrada"] + 24):
                kg_a_sacar_del_lote = min(kg_a_vaciar_disponibles, lote_frontal["kg"]); lote_frontal["kg"] -= kg_a_sacar_del_lote; pallets_a_sacar_del_lote = kg_a_sacar_del_lote / self.avg_kg_per_pallet
                lote_frontal["pallets"] -= pallets_a_sacar_del_lote; self.kg_actual -= kg_a_sacar_del_lote
                self.pallets_actual -= pallets_a_sacar_del_lote; kg_realmente_vaciados += kg_a_sacar_del_lote
                kg_a_vaciar_disponibles -= kg_a_sacar_del_lote
                if lote_frontal["kg"] <= 0.01: self.queue.popleft()
            else: break
        return kg_realmente_vaciados

    # --- CAMBIO HTML ---
    def get_html_viz(self):
        num_pallets_llenos = min(int(round(self.pallets_actual)), self.cols * self.rows)
        total_celdas = self.cols * self.rows
        celdas_html = "".join([f'<div class="tunnel-cell {"filled" if i < num_pallets_llenos else ""}"></div>' for i in range(total_celdas)])
        pallets_str = f"{num_pallets_llenos} / {int(self.max_pallets)}"
        kg_str = f"{self.kg_actual:,.0f}".replace(',', '.') + f" / {self.max_kg:,.0f}".replace(',', '.')
        
        # Pasamos la variable --rows (que definimos en el CSS) en lugar de --cols
        return f"""<div class="tunnel-visualization">
                   <div class="tunnel-label">{self.name}</div>
                   <div class="tunnel-stats">{pallets_str} palés<br>({kg_str} kg)</div>
                   <div class="tunnel-grid-container" style="--rows: {self.rows};">{celdas_html}</div>
               </div>"""


# --- Título ---
st.markdown("<h1 style='text-align: center;'>Gemelo digital congelación V.2</h1>", unsafe_allow_html=True)


# --- Pestañas ---
tab_cfg, tab_sim = st.tabs(["⚙️ Configuración de Parámetros", "🚀 Simulación y Resultados"])

# --- PESTAÑA 1: CONFIGURACIÓN ---
with tab_cfg:
    st.markdown("<h2>⚙️ Parámetros Globales</h2>", unsafe_allow_html=True)
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.number_input("Horas Totales (Base)", value=st.session_state.duracion_simulacion, min_value=1, key="duracion_simulacion")
    with col_g2:
        st.number_input("Kg Iniciales Cámara", value=st.session_state.kg_iniciales_camara, min_value=0, key="kg_iniciales_camara")
    with col_g3:
        st.date_input("Fecha Inicio Simulación", value=st.session_state.fecha_inicio, key="fecha_inicio", format="DD.MM.YYYY")
    
    st.markdown("<h4>Inventario Inicial en Túneles</h4>", unsafe_allow_html=True)
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.number_input("Kg Iniciales YA Congelados (Total)", value=st.session_state.kg_iniciales_tunel_congelado, min_value=0, key="kg_iniciales_tunel_congelado", help="Listos para sacar.")
    with col_t2:
        st.number_input("Kg Iniciales AÚN Congelando (Total)", value=st.session_state.kg_iniciales_tunel_frescos, min_value=0, key="kg_iniciales_tunel_frescos", help="Deben esperar.")
    if st.session_state.kg_iniciales_tunel_frescos > 0:
        with col_t3:
            st.number_input("Horas Restantes Congelación", value=st.session_state.horas_restantes_congelacion, min_value=1, max_value=23, key="horas_restantes_congelacion", help="¿Cuántas horas les falta?")
    st.slider("Velocidad Simulación (s/h)", 0.0, 5.0, value=st.session_state.segundos_por_hora_sim, step=0.05, key="segundos_por_hora_sim")

    # --- Despiece ---
    st.markdown("---"); st.markdown("<h2>🐷 Despiece (Diario)</h2>", unsafe_allow_html=True)
    st.number_input("Hora Inicio Despiece (0-23)", value=st.session_state.d_inicio, min_value=0, max_value=23, key="d_inicio")
    st.number_input("Cerdos/DÍA", value=st.session_state.d_cerdos, key="d_cerdos")
    st.number_input("Velocidad Teórica (cerdos/h)", value=st.session_state.d_velo, key="d_velo")
    st.slider("OEE (%)", 1, 100, value=st.session_state.d_oee, key="d_oee")
    
    col_peso_1, col_peso_2 = st.columns(2)
    with col_peso_1:
        st.number_input("Peso Medio Canal (kg)", value=st.session_state.d_peso, key="d_peso")
    with col_peso_2:
        st.number_input("Kg Despojos por Cerdo", value=st.session_state.d_peso_despojos, key="d_peso_despojos")

    st.checkbox("¿Día extra?", key="d_extra_check")
    if st.session_state.d_extra_check:
        with st.expander("Parámetros Día Extra (Despiece)"):
            st.number_input("Hora Inicio Extra", value=st.session_state.d_inicio_extra, min_value=0, max_value=23, key="d_inicio_extra")
            st.number_input("Cerdos Extra", value=st.session_state.d_cerdos_extra, key="d_cerdos_extra")
            col_peso_e1, col_peso_e2 = st.columns(2)
            with col_peso_e1:
                st.number_input("Peso Medio Canal (kg) (Extra)", value=st.session_state.d_peso, key="d_peso_extra", disabled=True, help="El peso de la canal se asume igual al de los días normales.")
            with col_peso_e2:
                st.number_input("Kg Despojos por Cerdo (Extra)", value=st.session_state.d_peso_despojos_extra, key="d_peso_despojos_extra")


    # --- Salidas Cámara ---
    st.markdown("---"); st.markdown("<h2>🧊 Salidas Cámara (Diario)</h2>", unsafe_allow_html=True)
    with st.expander("📦 Cajas (Alimenta Túneles)"):
        st.number_input("Hora Inicio Cajas (0-23)", value=st.session_state.c_inicio, min_value=0, max_value=23, key="c_inicio")
        st.number_input("Horas Trabajo Cajas", value=st.session_state.c_duracion, min_value=1, key="c_duracion")
        lineas_cajas = []
        for i in range(7):
            default_line_val = st.session_state.get(f"c_linea_{i}", 1250)
            lineas_cajas.append(st.number_input(f"Línea {i+1} (kg/h)", value=default_line_val, min_value=0, key=f"c_linea_{i}"))
        st.session_state.kg_hora_cajas_total = sum(lineas_cajas)
        st.checkbox("¿Día extra?", key="c_extra_check")
        if st.session_state.c_extra_check:
            with st.expander("Parámetros Día Extra (Cajas)"):
                st.number_input("Hora Inicio Extra", value=st.session_state.c_inicio_extra, min_value=0, max_value=23, key="c_inicio_extra")
                st.number_input("Horas Trabajo Extra", value=st.session_state.c_duracion_extra, min_value=1, key="c_duracion_extra")
                st.number_input("Total Cajas (kg/h) Extra", value=st.session_state.c_kg_extra, min_value=0, key="c_kg_extra")
    with st.expander("📉 Placas"):
         st.number_input("Hora Inicio Placas (0-23)", value=st.session_state.p_inicio, min_value=0, max_value=23, key="p_inicio")
         st.number_input("Horas Trabajo Placas", value=st.session_state.p_duracion, min_value=1, key="p_duracion")
         st.number_input("Placas (kg/h)", value=st.session_state.p_kg, min_value=0, key="p_kg")
         st.checkbox("¿Día extra?", key="p_extra_check")
         if st.session_state.p_extra_check:
             with st.expander("Parámetros Día Extra (Placas)"):
                 st.number_input("Hora Inicio Extra", value=st.session_state.p_inicio_extra, min_value=0, max_value=23, key="p_inicio_extra")
                 st.number_input("Horas Trabajo Extra", value=st.session_state.p_duracion_extra, min_value=1, key="p_duracion_extra")
                 st.number_input("Placas (kg/h) Extra", value=st.session_state.p_kg_extra, min_value=0, key="p_kg_extra")
    with st.expander("🚛 Fresco"):
         st.number_input("Hora Inicio Fresco (0-23)", value=st.session_state.f_inicio, min_value=0, max_value=23, key="f_inicio")
         st.number_input("Horas Trabajo Fresco", value=st.session_state.f_duracion, min_value=1, key="f_duracion")
         st.number_input("Kg/DÍA Fresco", value=st.session_state.f_kg_dia, key="f_kg_dia")
         st.checkbox("¿Día extra?", key="f_extra_check")
         if st.session_state.f_extra_check:
             with st.expander("Parámetros Día Extra (Fresco)"):
                 st.number_input("Hora Inicio Extra", value=st.session_state.f_inicio_extra, min_value=0, max_value=23, key="f_inicio_extra")
                 st.number_input("Horas Trabajo Extra", value=st.session_state.f_duracion_extra, min_value=1, key="f_duracion_extra")
                 st.number_input("Kg Extra Fresco", value=st.session_state.f_kg_dia_extra, key="f_kg_dia_extra")
    st.markdown("---"); st.markdown("<h2>❄️ Salida Túnel (Diario)</h2>", unsafe_allow_html=True)
    with st.expander("📤 Vaciado (General)"):
         st.number_input("Hora Inicio Vaciado (0-23)", value=st.session_state.v_inicio, min_value=0, max_value=23, key="v_inicio")
         st.number_input("Horas Trabajo Vaciado", value=st.session_state.v_duracion, min_value=1, key="v_duracion")
         st.number_input("Capacidad Vaciado (kg/h)", value=st.session_state.v_kg, min_value=0, key="v_kg")
         st.checkbox("¿Día extra?", key="v_extra_check")
         if st.session_state.v_extra_check:
             with st.expander("Parámetros Día Extra (Vaciado)"):
                 st.number_input("Hora Inicio Extra", value=st.session_state.v_inicio_extra, min_value=0, max_value=23, key="v_inicio_extra")
                 st.number_input("Horas Trabajo Extra", value=st.session_state.v_duracion_extra, min_value=1, key="v_duracion_extra")
                 st.number_input("Capacidad Vaciado (kg/h) Extra", value=st.session_state.v_kg_extra, min_value=0, key="v_kg_extra")


# --- PESTAÑA 2: SIMULACIÓN ---
with tab_sim:
    st.markdown("<h3>🔴 Simulación en Tiempo Real</h3>", unsafe_allow_html=True)

    placeholder_resumen = st.empty()
    placeholder_metricas = st.empty()
    placeholder_grafico = st.empty()
    placeholder_viz = st.empty()
    placeholder_progreso = st.empty()
    placeholder_tabla_final = st.empty()

    if st.button("Iniciar Simulación", key="start_sim_button", type="primary"):
        # --- CÁLCULOS PRELIMINARES ---
        if 'v_extra_check' not in st.session_state:
             st.error("Error: Recarga la página. Faltan parámetros.")
        else:
            
            # Cálculos día normal y extra...
            v_real = st.session_state.d_velo * (st.session_state.d_oee / 100.0);
            kg_canal_por_cerdo = st.session_state.d_peso
            kg_despojos_por_cerdo = st.session_state.d_peso_despojos
            kg_total_por_cerdo = kg_canal_por_cerdo + kg_despojos_por_cerdo
            kg_por_hora_despiece = v_real * kg_total_por_cerdo
            kg_por_dia_canal_total = st.session_state.d_cerdos * kg_canal_por_cerdo
            kg_por_dia_despojos_total = st.session_state.d_cerdos * kg_despojos_por_cerdo
            kg_por_dia_despiece_total = kg_por_dia_canal_total + kg_por_dia_despojos_total
            
            horas_trabajo_despiece = (st.session_state.d_cerdos / v_real) if v_real > 0 else 0;
            kg_hora_fresco = (st.session_state.f_kg_dia / st.session_state.f_duracion) if st.session_state.f_duracion > 0 else 0;
            fin_despiece = st.session_state.d_inicio + horas_trabajo_despiece; fin_cajas = st.session_state.c_inicio + st.session_state.c_duracion; fin_placas = st.session_state.p_inicio + st.session_state.p_duracion; fin_fresco = st.session_state.f_inicio + st.session_state.f_duracion; fin_vaciado = st.session_state.v_inicio + st.session_state.v_duracion;
            
            if st.session_state.d_extra_check:
                kg_canal_por_cerdo_extra = st.session_state.d_peso
                kg_despojos_por_cerdo_extra = st.session_state.d_peso_despojos_extra
                kg_total_por_cerdo_extra = kg_canal_por_cerdo_extra + kg_despojos_por_cerdo_extra
                kg_por_hora_despiece_extra = v_real * kg_total_por_cerdo_extra
                kg_por_dia_canal_total_extra = st.session_state.d_cerdos_extra * kg_canal_por_cerdo_extra
                kg_por_dia_despojos_total_extra = st.session_state.d_cerdos_extra * kg_despojos_por_cerdo_extra
                kg_por_dia_despiece_total_extra = kg_por_dia_canal_total_extra + kg_por_dia_despojos_total_extra
                horas_trabajo_despiece_extra = (st.session_state.d_cerdos_extra / v_real) if v_real > 0 else 0
                fin_despiece_extra = st.session_state.d_inicio_extra + horas_trabajo_despiece_extra
            
            if st.session_state.c_extra_check: fin_cajas_extra = st.session_state.c_inicio_extra + st.session_state.c_duracion_extra
            if st.session_state.p_extra_check: fin_placas_extra = st.session_state.p_inicio_extra + st.session_state.p_duracion_extra
            if st.session_state.f_extra_check: kg_hora_fresco_extra = (st.session_state.f_kg_dia_extra / st.session_state.f_duracion_extra) if st.session_state.f_duracion_extra > 0 else 0; fin_fresco_extra = st.session_state.f_inicio_extra + st.session_state.f_duracion_extra
            if st.session_state.v_extra_check: fin_vaciado_extra = st.session_state.v_inicio_extra + st.session_state.v_duracion_extra
            
            duracion_total_real = st.session_state.duracion_simulacion; extra_day_flags = [st.session_state.d_extra_check, st.session_state.c_extra_check, st.session_state.p_extra_check, st.session_state.f_extra_check, st.session_state.v_extra_check];
            if any(extra_day_flags): duracion_total_real += 24

            # --- MOSTRAR RESUMEN ---
            with placeholder_resumen.container():
                st.markdown("<h3>📊 Resumen de Flujos (Días Normales)</h3>", unsafe_allow_html=True)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown("<h5 style='text-align: center; color:var(--dark-blue)'>🐷 Producción</h5>", unsafe_allow_html=True)
                    st.metric("Kg Canales por Día", f"{kg_por_dia_canal_total:,.0f}".replace(',', '.') + " kg")
                    st.metric("Kg Despojos por Día", f"{kg_por_dia_despojos_total:,.0f}".replace(',', '.') + " kg")
                    st.metric("Ritmo Total Entrada", f"{kg_por_hora_despiece:,.0f}".replace(',', '.') + " kg/h")
                    st.metric("Horas", f"{horas_trabajo_despiece:.2f} h/día")
                with col2:
                    st.markdown("<h5 style='text-align: center; color:var(--dark-blue)'>🧊 Salidas Cámara</h5>", unsafe_allow_html=True)
                    st.metric("Ritmo Cajas", f"{st.session_state.kg_hora_cajas_total:,.0f}".replace(',', '.') + " kg/h")
                    st.metric("Ritmo Placas", f"{st.session_state.p_kg:,.0f}".replace(',', '.') + " kg/h")
                    st.metric("Ritmo Fresco", f"{kg_hora_fresco:,.0f}".replace(',', '.') + " kg/h")
                with col3:
                    st.markdown("<h5 style='text-align: center; color:var(--dark-blue)'>❄️ Salida Túneles</h5>", unsafe_allow_html=True)
                    st.metric("Capacidad Vaciado", f"{st.session_state.v_kg:,.0f}".replace(',', '.') + " kg/h")
                st.markdown("---")

            # --- INICIO BUCLE ---
            tuneles = [ Tunnel("CC037", 23000, 44, 11, 4), Tunnel("CC038", 23000, 44, 11, 4), Tunnel("CC058", 23000, 44, 11, 4), Tunnel("CC059", 31000, 55, 11, 5), Tunnel("CC062", 100000, 168, 21, 8)]
            kg_camara_fresco = float(st.session_state.kg_iniciales_camara); kg_congelar_fuera = 0.0
            kg_procesados_despiece_hoy = 0.0; kg_cargados_fresco_hoy = 0.0
            historial_inventarios = []; resumen_diario = []
            start_datetime = datetime.datetime.combine(st.session_state.fecha_inicio, datetime.time(0, 0))

            # Distribuir KG iniciales en túneles
            kg_iniciales_congelado = float(st.session_state.kg_iniciales_tunel_congelado); kg_iniciales_frescos = float(st.session_state.kg_iniciales_tunel_frescos); horas_restantes = int(st.session_state.horas_restantes_congelacion) if st.session_state.kg_iniciales_tunel_frescos > 0 else 0; hora_entrada_frescos = -(24 - horas_restantes) if horas_restantes > 0 else -999; kg_sobrantes_iniciales_congelado = 0.0; kg_sobrantes_iniciales_frescos = 0.0;
            if kg_iniciales_congelado > 0:
                kg_a_distribuir_congelado = kg_iniciales_congelado
                for i, t in enumerate(tuneles):
                    metidos = t.add_initial_kg(kg_a_distribuir_congelado, hora_entrada_calculada=-999)
                    kg_a_distribuir_congelado -= metidos
                    if kg_a_distribuir_congelado <= 0.01: break
                kg_sobrantes_iniciales_congelado = max(0, kg_a_distribuir_congelado)
            if kg_iniciales_frescos > 0:
                kg_a_distribuir_frescos = kg_iniciales_frescos
                for i, t in enumerate(tuneles):
                    metidos = t.add_initial_kg(kg_a_distribuir_frescos, hora_entrada_calculada=hora_entrada_frescos)
                    kg_a_distribuir_frescos -= metidos
                    if kg_a_distribuir_frescos <= 0.01: break
                kg_sobrantes_iniciales_frescos = max(0, kg_a_distribuir_frescos)
            kg_congelar_fuera = kg_sobrantes_iniciales_congelado + kg_sobrantes_iniciales_frescos


            for hora_actual in range(1, duracion_total_real + 1):
                hora_del_dia = (hora_actual - 1) % 24; es_dia_extra = hora_actual > st.session_state.duracion_simulacion
                if hora_del_dia == 0: kg_procesados_despiece_hoy = 0.0; kg_cargados_fresco_hoy = 0.0
                current_datetime = start_datetime + datetime.timedelta(hours=hora_actual - 1)

                # --- 1. Despiece ---
                kg_hora = 0.0
                if (es_dia_extra and st.session_state.d_extra_check):
                    if (hora_del_dia >= st.session_state.d_inicio_extra) and (hora_del_dia < fin_despiece_extra) and (kg_procesados_despiece_hoy < kg_por_dia_despiece_total_extra):
                        kg_hora = kg_por_hora_despiece_extra
                        if (kg_procesados_despiece_hoy + kg_hora) > kg_por_dia_despiece_total_extra: kg_hora = kg_por_dia_despiece_total_extra - kg_procesados_despiece_hoy
                        if kg_hora > 0.01: kg_camara_fresco += kg_hora; kg_procesados_despiece_hoy += kg_hora
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.d_inicio) and (hora_del_dia < fin_despiece) and (kg_procesados_despiece_hoy < kg_por_dia_despiece_total):
                        kg_hora = kg_por_hora_despiece
                        if (kg_procesados_despiece_hoy + kg_hora) > kg_por_dia_despiece_total: kg_hora = kg_por_dia_despiece_total - kg_procesados_despiece_hoy
                        if kg_hora > 0.01: kg_camara_fresco += kg_hora; kg_procesados_despiece_hoy += kg_hora

                # --- 2. Salidas Cámara ---
                # A. Cajas
                kg_a_distribuir_cajas = 0.0;
                if (es_dia_extra and st.session_state.c_extra_check):
                    if (hora_del_dia >= st.session_state.c_inicio_extra) and (hora_del_dia < fin_cajas_extra): kg_a_distribuir_cajas = min(st.session_state.c_kg_extra, kg_camara_fresco)
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.c_inicio) and (hora_del_dia < fin_cajas): kg_a_distribuir_cajas = min(st.session_state.kg_hora_cajas_total, kg_camara_fresco)
                if kg_a_distribuir_cajas > 0: 
                    kg_camara_fresco -= kg_a_distribuir_cajas; kg_sobrantes_hora = kg_a_distribuir_cajas
                    for tunel in tuneles:
                        if kg_sobrantes_hora <= 0.01: break
                        kg_sobrantes_hora = tunel.add_kg(kg_sobrantes_hora, hora_actual)
                    kg_congelar_fuera += kg_sobrantes_hora
                # B. Placas
                if (es_dia_extra and st.session_state.p_extra_check):
                    if (hora_del_dia >= st.session_state.p_inicio_extra) and (hora_del_dia < fin_placas_extra): procesado_placas = min(st.session_state.p_kg_extra, kg_camara_fresco); kg_camara_fresco -= procesado_placas
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.p_inicio) and (hora_del_dia < fin_placas): procesado_placas = min(st.session_state.p_kg, kg_camara_fresco); kg_camara_fresco -= procesado_placas
                # C. Fresco
                demanda_fresco = 0.0
                if (es_dia_extra and st.session_state.f_extra_check):
                    if (hora_del_dia >= st.session_state.f_inicio_extra) and (hora_del_dia < fin_fresco_extra) and (kg_cargados_fresco_hoy < st.session_state.f_kg_dia_extra):
                        demanda_fresco = kg_hora_fresco_extra
                        if (kg_cargados_fresco_hoy + demanda_fresco) > st.session_state.f_kg_dia_extra: demanda_fresco = st.session_state.f_kg_dia_extra - kg_cargados_fresco_hoy
                        if demanda_fresco > 0.01: procesado_fresco = min(demanda_fresco, kg_camara_fresco); kg_camara_fresco -= procesado_fresco; kg_cargados_fresco_hoy += procesado_fresco
                elif (not es_dia_extra):
                     if (hora_del_dia >= st.session_state.f_inicio) and (hora_del_dia < fin_fresco) and (kg_cargados_fresco_hoy < st.session_state.f_kg_dia):
                        demanda_fresco = kg_hora_fresco
                        if (kg_cargados_fresco_hoy + demanda_fresco) > st.session_state.f_kg_dia: demanda_fresco = st.session_state.f_kg_dia - kg_cargados_fresco_hoy
                        if demanda_fresco > 0.01: procesado_fresco = min(demanda_fresco, kg_camara_fresco); kg_camara_fresco -= procesado_fresco; kg_cargados_fresco_hoy += procesado_fresco

                # --- 3. Salida Túnel (Vaciado) ---
                kg_por_vaciar_esta_hora = 0.0
                if (es_dia_extra and st.session_state.v_extra_check):
                    if (hora_del_dia >= st.session_state.v_inicio_extra) and (hora_del_dia < fin_vaciado_extra): kg_por_vaciar_esta_hora = st.session_state.v_kg_extra
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.v_inicio) and (hora_del_dia < fin_vaciado): kg_por_vaciar_esta_hora = st.session_state.v_kg
                if kg_por_vaciar_esta_hora > 0:
                    for tunel in tuneles:
                        if kg_por_vaciar_esta_hora <= 0.01: break
                        kg_vaciados_del_tunel = tunel.vaciar_kg(kg_por_vaciar_esta_hora, hora_actual)
                        kg_por_vaciar_esta_hora -= kg_vaciados_del_tunel

                # --- 4. Registro y UI ---
                kg_total_en_tuneles = sum(t.kg_actual for t in tuneles)
                historial_inventarios.append({'datetime': current_datetime,'Kg Cámara Refrigerado': kg_camara_fresco, 'Kg en Túneles (Total)': kg_total_en_tuneles, 'Kg Congelar Fuera': kg_congelar_fuera})
                df_historial = pd.DataFrame(historial_inventarios).set_index('datetime')
                if hora_del_dia == 23 or hora_actual == duracion_total_real:
                    dia = (hora_actual - 1) // 24 + 1; etiqueta_dia = f"Día {dia}"
                    if es_dia_extra and (hora_del_dia == 23 or hora_actual == duracion_total_real): etiqueta_dia = f"Día {dia} (Extra)"
                    resumen_diario.append({'Día': etiqueta_dia, 'Kg Cámara Refrigerado': kg_camara_fresco, 'Kg en Túneles (Total)': kg_total_en_tuneles, 'Kg Congelar Fuera': kg_congelar_fuera})

                # Actualizar Placeholders Métricas
                with placeholder_metricas.container():
                    msg = f"**Día { (hora_actual - 1) // 24 + 1 } - Hora: {hora_actual} / {duracion_total_real} ({current_datetime.strftime('%d.%m %H:%M')})**"
                    if es_dia_extra: st.warning(f"**DÍA EXTRA - Hora: {hora_actual} / {duracion_total_real} ({current_datetime.strftime('%d.%m %H:%M')})**")
                    else: st.info(msg)
                    col1_m, col_m2, col_m3 = st.columns(3)
                    col1_m.metric("🧊 Inv. Cámara", f"{kg_camara_fresco:,.0f}".replace(',', '.') + " kg")
                    label_tunel = "❄️ Inv. Túneles" + (" ⚠️" if kg_congelar_fuera > 0.01 else "") # Usar tolerancia
                    col_m2.metric(label_tunel, f"{kg_total_en_tuneles:,.0f}".replace(',', '.') + " kg")
                    col_m3.metric("🔥 Congelar Fuera", f"{kg_congelar_fuera:,.0f}".replace(',', '.') + " kg")

                # Actualizar Gráfico (con Altair para ejes más grandes y NO APILADO)
                with placeholder_grafico.container():
                    st.markdown("<h6>Evolución Inventarios (KG) vs Tiempo</h6>", unsafe_allow_html=True)
                    
                    # 1. Preparar datos para Altair (formato "largo")
                    df_grafico_largo = df_historial.reset_index().melt('datetime', var_name='Inventario', value_name='Kg')
                    
                    # 2. Definir colores
                    domain_ = ['Kg Cámara Refrigerado', 'Kg en Túneles (Total)', 'Kg Congelar Fuera']
                    range_ = ['#3498db', '#e67e22', '#e74c3c'] # Azul, Naranja, Rojo

                    # 3. Crear el gráfico base
                    # CAMBIO: Quitado 'opacity' de mark_area()
                    base = alt.Chart(df_grafico_largo).mark_area().encode(
                        
                        # 4. Configurar Eje X (Fecha/Hora) con fuente grande
                        x=alt.X('datetime:T', 
                            axis=alt.Axis(
                                title='Fecha y Hora', 
                                format="%d.%m %H:%M", 
                                labelFontSize=18,
                                titleFontSize=20
                            )),
                        
                        # 5. Configurar Eje Y (KG) con fuente grande
                        # --- CAMBIO CLAVE: stack=None para superponer ---
                        y=alt.Y('Kg:Q', stack=None, 
                            axis=alt.Axis(
                                title='Kilogramos (kg)', 
                                labelFontSize=18,
                                titleFontSize=20
                            )),
                        
                        # 6. Definir colores
                        color=alt.Color('Inventario', 
                                    scale=alt.Scale(domain=domain_, range=range_),
                                    legend=alt.Legend(title="Inventarios", labelFontSize=14, titleFontSize=16)
                                   ),
                        
                        # --- CAMBIO: Opacidad definida aquí ---
                        opacity=alt.value(0.5), # Opacidad media para ver superposiciones

                        # 7. Tooltip
                        tooltip=[alt.Tooltip('datetime:T', title='Fecha', format="%d.%m.%Y %H:%M"), 
                                 alt.Tooltip('Inventario'), 
                                 alt.Tooltip('Kg:Q', title='Kilos', format=',.0f')]
                    ).interactive() # Permite zoom y pan
                    
                    # 8. Mostrar el gráfico Altair
                    st.altair_chart(base.properties(height=500), use_container_width=True)

                # VERIFICADO: Actualizar Visualización de Túneles
                with placeholder_viz.container():
                    st.markdown("<h6 style='text-align: center;'>Ocupación Túneles (Palés)</h6>", unsafe_allow_html=True) # Título centrado
                    cols_viz = st.columns(5)
                    if tuneles:
                        for i, tunel in enumerate(tuneles):
                            try:
                                cols_viz[i].markdown(tunel.get_html_viz(), unsafe_allow_html=True)
                            except Exception as e:
                                cols_viz[i].error(f"Error VIZ Tunel {i}: {e}")
                    else:
                        st.warning("No hay túneles definidos.")


                # Actualizar Progreso
                with placeholder_progreso.container():
                    st.markdown("---")
                    col_p1, col_p2 = st.columns(2)
                    objetivo_despiece_dia = kg_por_dia_despiece_total_extra if (es_dia_extra and st.session_state.d_extra_check) else kg_por_dia_despiece_total
                    objetivo_fresco_dia = st.session_state.f_kg_dia_extra if (es_dia_extra and st.session_state.f_extra_check) else st.session_state.f_kg_dia
                    with col_p1:
                        st.write(f"Prog. Despiece: {kg_procesados_despiece_hoy:,.0f}".replace(',', '.') + f" / {objetivo_despiece_dia:,.0f}".replace(',', '.') + " kg")
                        st.progress(int(kg_procesados_despiece_hoy / objetivo_despiece_dia * 100) if objetivo_despiece_dia > 0 else 0)
                    with col_p2:
                        st.write(f"Prog. C. Fresco: {kg_cargados_fresco_hoy:,.0f}".replace(',', '.') + f" / {objetivo_fresco_dia:,.0f}".replace(',', '.') + " kg")
                        st.progress(int(kg_cargados_fresco_hoy / objetivo_fresco_dia * 100) if objetivo_fresco_dia > 0 else 0)

                time.sleep(st.session_state.segundos_por_hora_sim) # Espera

            # --- FIN BUCLE ---
            st.success("✅ ¡Simulación Completada!")
            st.balloons()

            # --- TABLA FINAL ---
            with placeholder_tabla_final.container():
                st.markdown("---")
                st.markdown("<h3>📈 Resumen Inventarios Fin de Día (Kg)</h3>", unsafe_allow_html=True)
                df_resumen = pd.DataFrame(resumen_diario).set_index('Día')
                st.dataframe(df_resumen.T.applymap(lambda x: f"{x:,.0f}".replace(',', '.') + " kg"), use_container_width=True)