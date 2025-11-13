# -*- coding: utf-8 -*-
import streamlit as st
import time
import pandas as pd
from collections import deque
import datetime
import altair as alt # Importar Altair
import requests 
import io 

# --- URL de Configuración ---
GSHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTOEpNlhuiq7ibLw3LYuhP4medT5zdf0GgytMyUiD9px600IaRMwqgIjdMsVk8xP8paEH56Hpj4Yh2K/pub?gid=805865158&single=true&output=csv"

# --- Configuración de la página ---
st.set_page_config(
    page_title="Gemelo Digital: Flujo de KG",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={'About': "Gemelo Digital de Flujo de Producción"}
)

# --- CLASE PARA MODELAR LOS TÚNELES ---
# <--- CAMBIO: V.8 - Lógica basada en Palés ---
class Tunnel:
    # <--- CAMBIO: Constructor ya no recibe max_kg
    def __init__(self, name, max_pallets, rows, cols):
        self.name = name
        self.max_pallets = float(max_pallets) # Límite físico
        self.rows = rows
        self.cols = cols
        
        self.kg_actual = 0.0 # Variable
        self.pallets_actual = 0.0 # Variable
        self.queue = deque()
        
        # Contadores de palés por tipo (para visualización)
        self.pallets_huesos = 0.0 
        self.pallets_carne = 0.0 
        self.affinity = "None" 
    
    def update_affinity(self):
        if not self.queue:
            self.affinity = "None"
            return
        tipos_en_cola = set(lote["tipo_producto"] for lote in self.queue if lote["tipo_producto"] != "Congelado")
        if not tipos_en_cola:
            self.affinity = "None" 
        elif len(tipos_en_cola) == 1:
            self.affinity = tipos_en_cola.pop() 
        else:
            self.affinity = "Mixed" 

    # <--- CAMBIO: La restricción principal es esta
    def get_pallets_disponibles(self): 
        return max(0, self.max_pallets - self.pallets_actual)

    # <--- CAMBIO: 'add_kg' ahora piensa en palés primero
    def add_kg(self, kg_a_anadir, hora_actual, tipo_producto, kg_per_pallet_huesos, kg_per_pallet_carne, force_mix=False):
        
        # 1. Lógica de Afinidad (sin cambios)
        if (self.affinity != "None" and self.affinity != "Mixed" and 
            self.affinity != tipo_producto and not force_mix):
            return kg_a_anadir 

        # 2. Determinar peso por palé para este lote
        if tipo_producto == "Huesos":
            kg_por_pale_este_tipo = kg_per_pallet_huesos
        else:
            kg_por_pale_este_tipo = kg_per_pallet_carne
            
        if kg_por_pale_este_tipo <= 0: # Evitar división por cero
            return kg_a_anadir 

        # 3. Calcular palés necesarios vs disponibles
        pallets_necesarios = kg_a_anadir / kg_por_pale_este_tipo
        pallets_que_caben = self.get_pallets_disponibles()
        
        pallets_reales_a_meter = max(0, min(pallets_necesarios, pallets_que_caben))
        
        if pallets_reales_a_meter > 0.001: # Si cabe algo
            # 4. Calcular KG reales y sobrantes
            kg_reales_a_meter = pallets_reales_a_meter * kg_por_pale_este_tipo
            kg_sobrantes = kg_a_anadir - kg_reales_a_meter
            
            # 5. Añadir lote a la cola
            horas_congelacion = 18 if tipo_producto == "Huesos" else 33
            self.queue.append({
                "kg": kg_reales_a_meter, 
                "pallets": pallets_reales_a_meter, 
                "hora_entrada": hora_actual, 
                "tipo_producto": tipo_producto, 
                "horas_congelacion": horas_congelacion
            })
            
            # 6. Actualizar totales del túnel
            self.kg_actual += kg_reales_a_meter
            self.pallets_actual += pallets_reales_a_meter
            if tipo_producto == "Huesos":
                self.pallets_huesos += pallets_reales_a_meter
            else:
                self.pallets_carne += pallets_reales_a_meter
            
            self.update_affinity()
            return kg_sobrantes
        else:
            # No cabe nada
            return kg_a_anadir

    # <--- CAMBIO: 'add_initial_kg' también basado en palés
    def add_initial_kg(self, kg_iniciales, hora_entrada_calculada, porcentaje_huesos, kg_per_pallet_huesos, kg_per_pallet_carne):
        
        pallets_que_caben_total = self.get_pallets_disponibles()
        if pallets_que_caben_total <= 0.01:
            return 0.0 # No cabe nada

        kg_metidos_total = 0.0
        
        # Caso 1: Producto ya congelado (-999)
        if hora_entrada_calculada == -999:
            # Asumimos un peso promedio para los iniciales congelados
            avg_kg_pallet = (kg_per_pallet_huesos + kg_per_pallet_carne) / 2
            if avg_kg_pallet < 1: avg_kg_pallet = 1000 # Failsafe
            
            pallets_necesarios = kg_iniciales / avg_kg_pallet
            pallets_reales_a_meter = min(pallets_necesarios, pallets_que_caben_total)
            kg_reales_a_meter = pallets_reales_a_meter * avg_kg_pallet
            
            if pallets_reales_a_meter > 0.01:
                self.queue.appendleft({
                    "kg": kg_reales_a_meter, "pallets": pallets_reales_a_meter, 
                    "hora_entrada": -999, "tipo_producto": "Congelado", "horas_congelacion": 0
                })
                self.kg_actual += kg_reales_a_meter
                self.pallets_actual += pallets_reales_a_meter
                kg_metidos_total = kg_reales_a_meter

        # Caso 2: Producto fresco (en proceso)
        else:
            kg_huesos_iniciales = kg_iniciales * (porcentaje_huesos / 100.0)
            kg_carne_iniciales = kg_iniciales - kg_huesos_iniciales
            
            pallets_huesos_nec = (kg_huesos_iniciales / kg_per_pallet_huesos) if kg_per_pallet_huesos > 0 else 0
            pallets_carne_nec = (kg_carne_iniciales / kg_per_pallet_carne) if kg_per_pallet_carne > 0 else 0
            pallets_necesarios_total = pallets_huesos_nec + pallets_carne_nec

            # Calcular ratio de llenado si no cabe todo
            ratio = 1.0
            if pallets_necesarios_total > pallets_que_caben_total:
                ratio = pallets_que_caben_total / pallets_necesarios_total
                
            # Añadir Carne (primero al fondo)
            if pallets_carne_nec > 0:
                pallets_carne_a_meter = pallets_carne_nec * ratio
                kg_carne_a_meter = pallets_carne_a_meter * kg_per_pallet_carne
                self.queue.appendleft({
                    "kg": kg_carne_a_meter, "pallets": pallets_carne_a_meter, 
                    "hora_entrada": hora_entrada_calculada, "tipo_producto": "Carne", "horas_congelacion": 33
                })
                self.kg_actual += kg_carne_a_meter
                self.pallets_actual += pallets_carne_a_meter
                self.pallets_carne += pallets_carne_a_meter
                kg_metidos_total += kg_carne_a_meter
            
            # Añadir Huesos (después, quedan más al frente)
            if pallets_huesos_nec > 0:
                pallets_huesos_a_meter = pallets_huesos_nec * ratio
                kg_huesos_a_meter = pallets_huesos_a_meter * kg_per_pallet_huesos
                self.queue.appendleft({
                    "kg": kg_huesos_a_meter, "pallets": pallets_huesos_a_meter, 
                    "hora_entrada": hora_entrada_calculada, "tipo_producto": "Huesos", "horas_congelacion": 18
                })
                self.kg_actual += kg_huesos_a_meter
                self.pallets_actual += pallets_huesos_a_meter
                self.pallets_huesos += pallets_huesos_a_meter
                kg_metidos_total += kg_huesos_a_meter
        
        self.update_affinity() 
        return kg_metidos_total

    # <--- CAMBIO: Lógica de vaciado proporcional
    def vaciar_kg(self, kg_a_vaciar_disponibles, hora_actual):
        kg_realmente_vaciados = 0.0
        while kg_a_vaciar_disponibles > 0.01 and len(self.queue) > 0:
            lote_frontal = self.queue[0]
            
            horas_requeridas = lote_frontal["horas_congelacion"]
            listo_para_sacar = (horas_requeridas <= 0) or (hora_actual >= (lote_frontal["hora_entrada"] + horas_requeridas))
            
            if listo_para_sacar:
                kg_a_sacar_del_lote = min(kg_a_vaciar_disponibles, lote_frontal["kg"])
                
                # Calcular palés proporcionales
                kg_por_pale_lote = 1000 # Failsafe
                if lote_frontal["pallets"] > 0.001:
                    kg_por_pale_lote = lote_frontal["kg"] / lote_frontal["pallets"]
                
                pallets_a_sacar_del_lote = kg_a_sacar_del_lote / kg_por_pale_lote
                
                tipo_lote = lote_frontal["tipo_producto"]
                
                if tipo_lote == "Huesos": self.pallets_huesos = max(0, self.pallets_huesos - pallets_a_sacar_del_lote)
                elif tipo_lote == "Carne": self.pallets_carne = max(0, self.pallets_carne - pallets_a_sacar_del_lote)

                lote_frontal["kg"] -= kg_a_sacar_del_lote
                lote_frontal["pallets"] -= pallets_a_sacar_del_lote
                self.kg_actual -= kg_a_sacar_del_lote
                self.pallets_actual -= pallets_a_sacar_del_lote
                kg_realmente_vaciados += kg_a_sacar_del_lote
                kg_a_vaciar_disponibles -= kg_a_sacar_del_lote
                
                if lote_frontal["kg"] <= 0.01 or lote_frontal["pallets"] <= 0.01:
                    # Ajustar residuos
                    if tipo_lote == "Huesos": self.pallets_huesos = max(0, self.pallets_huesos - lote_frontal["pallets"])
                    elif tipo_lote == "Carne": self.pallets_carne = max(0, self.pallets_carne - lote_frontal["pallets"])
                    self.queue.popleft()
                    self.update_affinity() 
            else: 
                break 
        
        if kg_realmente_vaciados > 0: self.update_affinity() 
        return kg_realmente_vaciados

    # <--- CAMBIO: Visualización ya no muestra max_kg
    def get_html_viz(self):
        total_celdas = self.cols * self.rows
        num_pallets_llenos_total_visual = min(int(round(self.pallets_actual)), total_celdas)
        num_pallets_huesos_visual = min(int(round(self.pallets_huesos)), num_pallets_llenos_total_visual)
        num_pallets_carne_visual = min(int(round(self.pallets_carne)), num_pallets_llenos_total_visual - num_pallets_huesos_visual)
        num_pallets_otros_visual = num_pallets_llenos_total_visual - num_pallets_huesos_visual - num_pallets_carne_visual
        celdas_html = ""
        celdas_html += f'<div class="tunnel-cell filled-huesos"></div>' * num_pallets_huesos_visual
        celdas_html += f'<div class="tunnel-cell filled-carne"></div>' * num_pallets_carne_visual
        celdas_html += f'<div class="tunnel-cell filled"></div>' * num_pallets_otros_visual
        num_celdas_vacias = total_celdas - num_pallets_llenos_total_visual
        celdas_html += f'<div class="tunnel-cell"></div>' * num_celdas_vacias
        
        pallets_str = f"{num_pallets_llenos_total_visual} / {int(self.max_pallets)}"
        # Mostramos solo KG actuales, max_kg ya no es fijo
        kg_str = f"({self.kg_actual:,.0f} kg)".replace(',', '.')
        
        affinity_label = f" ({self.affinity})" if self.affinity != "None" else " (Vacío)"
        
        return f"""<div class="tunnel-visualization">
                   <div class="tunnel-label">{self.name}{affinity_label}</div> 
                   <div class="tunnel-stats">{pallets_str} palés<br>{kg_str}</div>
                   <div class="tunnel-grid-container" style="--rows: {self.rows};">{celdas_html}</div>
               </div>"""


# --- Lógica de Carga de Configuración ---
# (Función load_config_from_gsheet sin cambios)
@st.cache_data(ttl=60)
def load_config_from_gsheet(csv_url):
    try:
        response = requests.get(csv_url)
        response.raise_for_status() 
        csv_data = response.content.decode('utf-8')
        df = pd.read_csv(io.StringIO(csv_data), usecols=["Parametro", "Valor"])
        df = df.dropna(subset=["Parametro"]) 
        df = df.set_index("Parametro")
        config_dict = df["Valor"].to_dict()
        
        processed_config = {}
        for key, value in config_dict.items():
            try:
                key = key.strip() 
                if not key: continue 
                if isinstance(value, str):
                    value_str = value.strip()
                    if value_str.upper() == 'TRUE':
                        processed_config[key] = True
                    elif value_str.upper() == 'FALSE':
                        processed_config[key] = False
                    elif key == 'fecha_inicio':
                        try:
                            processed_config[key] = datetime.datetime.strptime(value_str, '%Y-%m-%d').date()
                        except ValueError:
                            processed_config[key] = datetime.datetime.strptime(value_str, '%d/%m/%Y').date()
                    else:
                        try:
                            value_str_cleaned = value_str.replace(',', '.')
                            float_val = float(value_str_cleaned)
                            if float_val.is_integer():
                                processed_config[key] = int(float_val)
                            else:
                                processed_config[key] = float_val
                        except (ValueError, TypeError):
                            processed_config[key] = value_str
                else:
                    processed_config[key] = value
            except Exception as e:
                st.warning(f"Error procesando parámetro '{key}' (Valor: {value}). Error: {e}")
                processed_config[key] = value 

        return processed_config, None
    
    except Exception as e:
        return None, str(e)

# (Bloque de carga sin cambios)
if 'config_loaded' not in st.session_state:
    loading_placeholder = st.empty()
    loading_placeholder.info(f"🔄 Cargando configuración desde Google Sheet...")
    config_data, error = load_config_from_gsheet(GSHEET_URL)
    if error:
        loading_placeholder.error(f"Error al cargar la configuración: {error}. Usando valores por defecto (si existen).")
        if 'fecha_inicio' not in st.session_state: st.session_state['fecha_inicio'] = datetime.date.today()
    else:
        for key, value in config_data.items():
            if key not in st.session_state:
                st.session_state[key] = value
        st.session_state['config_loaded'] = True
        loading_placeholder.success("✅ Configuración cargada.")
        time.sleep(1) 
        loading_placeholder.empty()

# (Cálculo de kg_hora_cajas_total sin cambios)
try:
    st.session_state.kg_hora_cajas_total = sum(st.session_state.get(f"c_linea_{i}", 0) for i in range(7))
except Exception as e:
    st.error(f"Error al calcular 'kg_hora_cajas_total': {e}")
    st.session_state.kg_hora_cajas_total = 0

# --- CSS Personalizado ---
# (CSS sin cambios)
st.markdown("""
<style>
:root {
    --primary-color: #3498db; --secondary-color: #e67e22; --danger-color: #e74c3c;
    --background-color: #ecf0f1; --card-background-color: #ffffff; --text-color: #2c3e50;
    --light-gray: #f9f9f9; --dark-blue: #2980b9;
    --color-huesos: #2ecc71;   /* Verde para Huesos (18h) */
    --color-carne: #f39c12;    /* Naranja/Amarillo para Carne (33h) */
}
body { background-color: var(--background-color); color: var(--text-color); }
div.stApp { background-color: var(--background-color); }
div[data-testid="stAppViewContainer"] { background-color: var(--background-color); }
h1 { color: var(--dark-blue); text-align: center; font-size: 2.8rem; margin-bottom: 1.5rem; }
div[data-testid="stTabs"] h2 { color: var(--text-color); font-size: 2.2rem !important; font-weight: 600; }
div[data-testid="stTabs"] h3 { color: var(--dark-blue); font-size: 2rem !important; font-weight: 600; margin-top: 1.5rem; margin-bottom: 1rem; }
div[data-testid="stVerticalBlock"] { background-color: var(--background-color); padding: 1rem; border-radius: 8px; }
div[data-baseweb="tab-list"] { background-color: var(--light-gray) !important; border-radius: 8px; padding: 0.5rem 0.5rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
div[data-baseweb="tab-list"] button { font-size: 2.5rem !important; padding: 1rem 2rem !important; font-weight: 600 !important; }
div[data-baseweb="tab-list"] button[aria-selected="true"] { background-color: var(--primary-color) !important; color: white !important; border-radius: 6px; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
div[data-baseweb="tab-list"] button[aria-selected="false"] { background-color: transparent !important; color: var(--text-color) !important; }
div[data-testid="stNumberInput"] label p, div[data-testid="stSlider"] label p,
div[data-testid="stCheckbox"] label p, div[data-testid="stDateInput"] label p { font-size: 1.3rem !important; font-weight: 600 !important; color: var(--text-color); }
div[data-testid="stNumberInput"] input, div[data-testid="stDateInput"] input { font-size: 1.3rem !important; padding: 0.5rem 1rem; border-radius: 5px; border: 1px solid #ccc; }
div[data-testid="stNumberInput"] input:focus, div[data-testid="stDateInput"] input:focus { border-color: var(--primary-color); box-shadow: 0 0 0 0.1rem rgba(52, 152, 219, 0.25); }
.st-expander label p { font-size: 1.35rem !important; font-weight: 600 !important; color: var(--dark-blue); }
div[data-testid="stMetric"] { background-color: var(--card-background-color); padding: 1rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; margin-bottom: 1rem; }
div[data-testid="stMetric"] label { font-size: 1.1rem; color: var(--dark-blue); font-weight: bold; }
div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: var(--primary-color); font-weight: bolder; }
div[data-testid="stMetricDelta"] { font-size: 1rem; color: var(--text-color); }
button[kind="primary"] { background-color: var(--primary-color) !important; color: white !important; font-size: 1.5rem !important; padding: 0.8rem 2rem !important; border-radius: 8px !important; border: none !important; transition: background-color 0.3s ease !important; }
button[kind="primary"]:hover { background-color: var(--dark-blue) !important; color: white !important; }
.stDataFrame, .st-empty, .stPlotlyChart, .stAreaChart { background-color: var(--card-background-color); padding: 1rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
div[data-testid="stAlert"] { font-size: 1.2rem; padding: 1rem; border-radius: 8px; }
div[data-testid="stAlert"] > div { font-size: 1.2rem; }
.stDataFrame { text-align: center; }
.stDataFrame th.col_heading { font-size: 2.5rem !important; text-align: center !important; font-weight: bold; color: var(--dark-blue); background-color: var(--light-gray) !important; padding: 12px 8px; }
.stDataFrame th.row_heading { font-size: 2.5rem !important; text-align: center !important; font-weight: bold; color: var(--dark-blue); background-color: var(--light-gray) !important; padding: 12px 8px; }
.stDataFrame td { font-size: 2.2rem !important; text-align: center !important; padding: 10px 8px; vertical-align: middle; }
.tunnel-grid-container { 
    display: grid; grid-template-rows: repeat(var(--rows, 11), 1fr); grid-auto-flow: column;
    grid-auto-columns: 1fr; gap: 3px; border: 2px solid var(--dark-blue); 
    background-color: var(--light-gray); padding: 5px; border-radius: 5px; 
    max-width: 300px; margin-left: auto; margin-right: auto; 
}
.tunnel-cell { width: 100%; padding-bottom: 100%; background-color: #bdc3c7; border-radius: 2px; }
.tunnel-cell.filled { background-color: var(--primary-color); }
.tunnel-cell.filled-huesos { background-color: var(--color-huesos); }
.tunnel-cell.filled-carne { background-color: var(--color-carne); }
.tunnel-label { font-size: 1.5rem; font-weight: bold; color: var(--dark-blue); text-align: center; margin-bottom: 0.5rem; }
.tunnel-stats { font-size: 1.6rem !important; text-align: center; color: var(--text-color); margin-bottom: 0.5rem; line-height: 1.3; }
.tunnel-legend { display: flex; justify-content: center; gap: 20px; margin-bottom: 1rem; font-size: 1.2rem; font-weight: bold; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-color-box { width: 20px; height: 20px; border: 1px solid #7f8c8d; }
</style>
""", unsafe_allow_html=True)


# --- Título ---
st.markdown("<h1 style='text-align: center;'>Gemelo digital V.3", unsafe_allow_html=True) # <--- CAMBIO: Título


# --- Pestañas ---
tab_cfg, tab_sim = st.tabs(["⚙️ Configuración de Parámetros", "🚀 Simulación y Resultados"])

# --- PESTAÑA 1: CONFIGURACIÓN ---
with tab_cfg:
    st.markdown("<h2>⚙️ Parámetros Globales</h2>", unsafe_allow_html=True)
    if st.button("Recargar Configuración desde Google Sheet", key="reload_button"):
        st.cache_data.clear()
        st.session_state.pop('config_loaded', None)
        st.rerun()

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.number_input("Horas Totales (Base)", min_value=1, key="duracion_simulacion")
    with col_g2:
        st.number_input("Kg Iniciales Cámara", min_value=0, key="kg_iniciales_camara")
    with col_g3:
        if 'fecha_inicio' not in st.session_state: st.session_state['fecha_inicio'] = datetime.date.today()
        st.date_input("Fecha Inicio Simulación", key="fecha_inicio", format="DD.MM.YYYY")
    
    st.slider(
        "Porcentaje de Huesos (18h) (El resto será Carne (33h))", 
        min_value=0, max_value=100, 
        key="porcentaje_huesos", 
        format="%d%%"
    )
    
    # <--- CAMBIO: Añadir inputs para los nuevos pesos de palé ---
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.number_input("Peso Palé Huesos (kg)", min_value=1, key="kg_pallet_huesos")
    with col_p2:
        st.number_input("Peso Palé Carne (kg)", min_value=1, key="kg_pallet_carne")


    st.markdown("<h4>Inventario Inicial en Túneles</h4>", unsafe_allow_html=True)
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.number_input("Kg Iniciales YA Congelados (Total)", min_value=0, key="kg_iniciales_tunel_congelado", help="Listos para sacar.")
    with col_t2:
        st.number_input("Kg Iniciales AÚN Congelando (Total)", min_value=0, key="kg_iniciales_tunel_frescos", help="Deben esperar.")
    if st.session_state.get("kg_iniciales_tunel_frescos", 0) > 0:
        with col_t3:
            st.number_input("Horas Restantes Congelación", min_value=1, max_value=32, key="horas_restantes_congelacion", help="¿Cuántas horas les falta? (Max 32h)")
    st.slider("Velocidad Simulación (s/h)", 0.0, 5.0, step=0.05, key="segundos_por_hora_sim")

    # (Resto de la pestaña de configuración sin cambios)
    # --- Despiece ---
    st.markdown("---"); st.markdown("<h2>🐷 Despiece (Diario)</h2>", unsafe_allow_html=True)
    st.number_input("Hora Inicio Despiece (0-23)", min_value=0, max_value=23, key="d_inicio")
    st.number_input("Cerdos/DÍA", key="d_cerdos")
    st.number_input("Velocidad Teórica (cerdos/h)", key="d_velo")
    st.slider("OEE (%)", 1, 100, key="d_oee")
    col_peso_1, col_peso_2 = st.columns(2)
    with col_peso_1: st.number_input("Peso Medio Canal (kg)", key="d_peso")
    with col_peso_2: st.number_input("Kg Despojos por Cerdo", key="d_peso_despojos")
    st.checkbox("¿Día extra?", key="d_extra_check")
    if st.session_state.get("d_extra_check", False):
        with st.expander("Parámetros Día Extra (Despiece)"):
            st.number_input("Hora Inicio Extra", min_value=0, max_value=23, key="d_inicio_extra")
            st.number_input("Cerdos Extra", key="d_cerdos_extra")
            col_peso_e1, col_peso_e2 = st.columns(2)
            peso_canal_base = st.session_state.get('d_peso', 80.0)
            with col_peso_e1: st.number_input("Peso Medio Canal (kg) (Extra)", value=peso_canal_base, key="d_peso_extra", disabled=True, help="El peso de la canal se asume igual al de los días normales.")
            with col_peso_e2: st.number_input("Kg Despojos por Cerdo (Extra)", key="d_peso_despojos_extra")

    # --- Salidas Cámara ---
    st.markdown("---"); st.markdown("<h2>🧊 Salidas Cámara (Diario)</h2>", unsafe_allow_html=True)
    with st.expander("📦 Cajas (Alimenta Túneles)"):
        st.number_input("Hora Inicio Cajas (0-23)", min_value=0, max_value=23, key="c_inicio")
        st.number_input("Horas Trabajo Cajas", min_value=1, key="c_duracion")
        lineas_cajas = []
        for i in range(7):
            lineas_cajas.append(st.number_input(f"Línea {i+1} (kg/h)", min_value=0, key=f"c_linea_{i}"))
        st.session_state.kg_hora_cajas_total = sum(lineas_cajas) 
        
        st.checkbox("¿Día extra?", key="c_extra_check")
        if st.session_state.get("c_extra_check", False):
            with st.expander("Parámetros Día Extra (Cajas)"):
                st.number_input("Hora Inicio Extra", min_value=0, max_value=23, key="c_inicio_extra")
                st.number_input("Horas Trabajo Extra", min_value=1, key="c_duracion_extra")
                st.number_input("Total Cajas (kg/h) Extra", min_value=0, key="c_kg_extra")
    with st.expander("📉 Placas"):
         st.number_input("Hora Inicio Placas (0-23)", min_value=0, max_value=23, key="p_inicio")
         st.number_input("Horas Trabajo Placas", min_value=1, key="p_duracion")
         st.number_input("Placas (kg/h)", min_value=0, key="p_kg")
         st.checkbox("¿Día extra?", key="p_extra_check")
         if st.session_state.get("p_extra_check", False):
             with st.expander("Parámetros Día Extra (Placas)"):
                 st.number_input("Hora Inicio Extra", min_value=0, max_value=23, key="p_inicio_extra")
                 st.number_input("Horas Trabajo Extra", min_value=1, key="p_duracion_extra")
                 st.number_input("Placas (kg/h) Extra", min_value=0, key="p_kg_extra")
    with st.expander("🚛 Fresco"):
         st.number_input("Hora Inicio Fresco (0-23)", min_value=0, max_value=23, key="f_inicio")
         st.number_input("Horas Trabajo Fresco", min_value=1, key="f_duracion")
         st.number_input("Kg/DÍA Fresco", key="f_kg_dia")
         st.checkbox("¿Día extra?", key="f_extra_check")
         if st.session_state.get("f_extra_check", False):
             with st.expander("Parámetros Día Extra (Fresco)"):
                 st.number_input("Hora Inicio Extra", min_value=0, max_value=23, key="f_inicio_extra")
                 st.number_input("Horas Trabajo Extra", min_value=1, key="f_duracion_extra")
                 st.number_input("Kg Extra Fresco", key="f_kg_dia_extra")
    st.markdown("---"); st.markdown("<h2>❄️ Salida Túnel (Diario)</h2>", unsafe_allow_html=True)
    with st.expander("📤 Vaciado (General)"):
         st.number_input("Hora Inicio Vaciado (0-23)", min_value=0, max_value=23, key="v_inicio")
         st.number_input("Horas Trabajo Vaciado", min_value=1, key="v_duracion")
         st.number_input("Capacidad Vaciado (kg/h)", min_value=0, key="v_kg")
         st.checkbox("¿Día extra?", key="v_extra_check")
         if st.session_state.get("v_extra_check", False):
             with st.expander("Parámetros Día Extra (Vaciado)"):
                 st.number_input("Hora Inicio Extra", min_value=0, max_value=23, key="v_inicio_extra")
                 st.number_input("Horas Trabajo Extra", min_value=1, key="v_duracion_extra")
                 st.number_input("Capacidad Vaciado (kg/h) Extra", min_value=0, key="v_kg_extra")


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
             st.error("Error: Faltan parámetros de configuración. Intenta recargar la configuración.")
        else:
            
            # (Cálculos preliminares sin cambios)
            pct_huesos = st.session_state.get("porcentaje_huesos", 50)
            v_real = st.session_state.get("d_velo", 0) * (st.session_state.get("d_oee", 0) / 100.0);
            kg_canal_por_cerdo = st.session_state.get("d_peso", 0)
            kg_despojos_por_cerdo = st.session_state.get("d_peso_despojos", 0)
            kg_total_por_cerdo = kg_canal_por_cerdo + kg_despojos_por_cerdo
            kg_por_hora_despiece = v_real * kg_total_por_cerdo
            kg_por_dia_canal_total = st.session_state.get("d_cerdos", 0) * kg_canal_por_cerdo
            kg_por_dia_despojos_total = st.session_state.get("d_cerdos", 0) * kg_despojos_por_cerdo
            kg_por_dia_despiece_total = kg_por_dia_canal_total + kg_por_dia_despojos_total
            horas_trabajo_despiece = (st.session_state.get("d_cerdos", 0) / v_real) if v_real > 0 else 0;
            kg_hora_fresco = (st.session_state.get("f_kg_dia", 0) / st.session_state.get("f_duracion", 1)) if st.session_state.get("f_duracion", 0) > 0 else 0;
            fin_despiece = st.session_state.get("d_inicio", 0) + horas_trabajo_despiece; fin_cajas = st.session_state.get("c_inicio", 0) + st.session_state.get("c_duracion", 0); fin_placas = st.session_state.get("p_inicio", 0) + st.session_state.get("p_duracion", 0); fin_fresco = st.session_state.get("f_inicio", 0) + st.session_state.get("f_duracion", 0); fin_vaciado = st.session_state.get("v_inicio", 0) + st.session_state.get("v_duracion", 0);
            if st.session_state.get("d_extra_check", False):
                kg_canal_por_cerdo_extra = st.session_state.get("d_peso", 0)
                kg_despojos_por_cerdo_extra = st.session_state.get("d_peso_despojos_extra", 0)
                kg_total_por_cerdo_extra = kg_canal_por_cerdo_extra + kg_despojos_por_cerdo_extra
                kg_por_hora_despiece_extra = v_real * kg_total_por_cerdo_extra
                kg_por_dia_canal_total_extra = st.session_state.get("d_cerdos_extra", 0) * kg_canal_por_cerdo_extra
                kg_por_dia_despojos_total_extra = st.session_state.get("d_cerdos_extra", 0) * kg_despojos_por_cerdo_extra
                kg_por_dia_despiece_total_extra = kg_por_dia_canal_total_extra + kg_por_dia_despojos_total_extra
                horas_trabajo_despiece_extra = (st.session_state.get("d_cerdos_extra", 0) / v_real) if v_real > 0 else 0
                fin_despiece_extra = st.session_state.get("d_inicio_extra", 0) + horas_trabajo_despiece_extra
            if st.session_state.get("c_extra_check", False): fin_cajas_extra = st.session_state.get("c_inicio_extra", 0) + st.session_state.get("c_duracion_extra", 0)
            if st.session_state.get("p_extra_check", False): fin_placas_extra = st.session_state.get("p_inicio_extra", 0) + st.session_state.get("p_duracion_extra", 0)
            if st.session_state.get("f_extra_check", False): kg_hora_fresco_extra = (st.session_state.get("f_kg_dia_extra", 0) / st.session_state.get("f_duracion_extra", 1)) if st.session_state.get("f_duracion_extra", 0) > 0 else 0; fin_fresco_extra = st.session_state.get("f_inicio_extra", 0) + st.session_state.get("f_duracion_extra", 0)
            if st.session_state.get("v_extra_check", False): fin_vaciado_extra = st.session_state.get("v_inicio_extra", 0) + st.session_state.get("v_duracion_extra", 0)
            duracion_total_real = st.session_state.get("duracion_simulacion", 0); extra_day_flags = [st.session_state.get(k, False) for k in ["d_extra_check", "c_extra_check", "p_extra_check", "f_extra_check", "v_extra_check"]];
            if any(extra_day_flags): duracion_total_real += 24

            # --- MOSTRAR RESUMEN ---
            # (Resumen sin cambios)
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
                    st.metric("Ritmo Cajas", f"{st.session_state.get('kg_hora_cajas_total', 0):,.0f}".replace(',', '.') + " kg/h")
                    st.metric("Ritmo Placas", f"{st.session_state.get('p_kg', 0):,.0f}".replace(',', '.') + " kg/h")
                    st.metric("Ritmo Fresco", f"{kg_hora_fresco:,.0f}".replace(',', '.') + " kg/h")
                with col3:
                    st.markdown("<h5 style='text-align: center; color:var(--dark-blue)'>❄️ Salida Túneles</h5>", unsafe_allow_html=True)
                    st.metric("Capacidad Vaciado", f"{st.session_state.get('v_kg', 0):,.0f}".replace(',', '.') + " kg/h")
                st.markdown("---")

            # --- INICIO BUCLE ---
            
            # <--- CAMBIO: Coger pesos de palé del state (con defaults por si acaso)
            kg_huesos_pallet = st.session_state.get("kg_pallet_huesos", 1100)
            kg_carne_pallet = st.session_state.get("kg_pallet_carne", 1250)
            
            # <--- CAMBIO: Constructor de Tunnel ya no usa max_kg
            tuneles = [ 
                Tunnel("CC037", 44, 11, 4), Tunnel("CC038", 44, 11, 4), 
                Tunnel("CC058", 44, 11, 4), Tunnel("CC059", 55, 11, 5), 
                Tunnel("CC062", 168, 21, 8)
            ]
            
            kg_camara_fresco = float(st.session_state.get("kg_iniciales_camara", 0)); kg_congelar_fuera = 0.0
            kg_procesados_despiece_hoy = 0.0; kg_cargados_fresco_hoy = 0.0
            historial_inventarios = []; resumen_diario = []
            start_datetime = datetime.datetime.combine(st.session_state.get('fecha_inicio', datetime.date.today()), datetime.time(0, 0))
            kg_total_congelados_acumulado = 0.0

            # Distribuir KG iniciales en túneles
            kg_iniciales_congelado = float(st.session_state.get("kg_iniciales_tunel_congelado", 0)); kg_iniciales_frescos = float(st.session_state.get("kg_iniciales_tunel_frescos", 0)); horas_restantes = int(st.session_state.get("horas_restantes_congelacion", 0)) if st.session_state.get("kg_iniciales_tunel_frescos", 0) > 0 else 0
            max_horas_congelacion = 33 
            hora_entrada_frescos = -(max_horas_congelacion - horas_restantes) if horas_restantes > 0 else -999;
            kg_sobrantes_iniciales_congelado = 0.0; kg_sobrantes_iniciales_frescos = 0.0;
            
            if kg_iniciales_congelado > 0:
                kg_a_distribuir_congelado = kg_iniciales_congelado
                for i, t in enumerate(tuneles):
                    # <--- CAMBIO: Pasar pesos de palé
                    metidos = t.add_initial_kg(kg_a_distribuir_congelado, hora_entrada_calculada=-999, porcentaje_huesos=pct_huesos, kg_per_pallet_huesos=kg_huesos_pallet, kg_per_pallet_carne=kg_carne_pallet)
                    kg_a_distribuir_congelado -= metidos
                    if kg_a_distribuir_congelado <= 0.01: break
                kg_sobrantes_iniciales_congelado = max(0, kg_a_distribuir_congelado)
            
            if kg_iniciales_frescos > 0:
                kg_a_distribuir_frescos = kg_iniciales_frescos
                for i, t in enumerate(tuneles):
                    # <--- CAMBIO: Pasar pesos de palé
                    metidos = t.add_initial_kg(kg_a_distribuir_frescos, hora_entrada_calculada=hora_entrada_frescos, porcentaje_huesos=pct_huesos, kg_per_pallet_huesos=kg_huesos_pallet, kg_per_pallet_carne=kg_carne_pallet)
                    kg_a_distribuir_frescos -= metidos
                    if kg_a_distribuir_frescos <= 0.01: break
                kg_sobrantes_iniciales_frescos = max(0, kg_a_distribuir_frescos)
            
            kg_congelar_fuera = kg_sobrantes_iniciales_congelado + kg_sobrantes_iniciales_frescos


            for hora_actual in range(1, duracion_total_real + 1):
                hora_del_dia = (hora_actual - 1) % 24; es_dia_extra = hora_actual > st.session_state.get("duracion_simulacion", 0)
                if hora_del_dia == 0: kg_procesados_despiece_hoy = 0.0; kg_cargados_fresco_hoy = 0.0
                current_datetime = start_datetime + datetime.timedelta(hours=hora_actual - 1)

                # --- 1. Despiece ---
                # (Despiece sin cambios)
                kg_hora = 0.0
                if (es_dia_extra and st.session_state.get("d_extra_check", False)):
                    if (hora_del_dia >= st.session_state.get("d_inicio_extra", 0)) and (hora_del_dia < fin_despiece_extra) and (kg_procesados_despiece_hoy < kg_por_dia_despiece_total_extra):
                        kg_hora = kg_por_hora_despiece_extra
                        if (kg_procesados_despiece_hoy + kg_hora) > kg_por_dia_despiece_total_extra: kg_hora = kg_por_dia_despiece_total_extra - kg_procesados_despiece_hoy
                        if kg_hora > 0.01: kg_camara_fresco += kg_hora; kg_procesados_despiece_hoy += kg_hora
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.get("d_inicio", 0)) and (hora_del_dia < fin_despiece) and (kg_procesados_despiece_hoy < kg_por_dia_despiece_total):
                        kg_hora = kg_por_hora_despiece
                        if (kg_procesados_despiece_hoy + kg_hora) > kg_por_dia_despiece_total: kg_hora = kg_por_dia_despiece_total - kg_procesados_despiece_hoy
                        if kg_hora > 0.01: kg_camara_fresco += kg_hora; kg_procesados_despiece_hoy += kg_hora

                # --- 2. Salidas Cámara ---
                # A. Cajas
                kg_a_distribuir_cajas = 0.0;
                if (es_dia_extra and st.session_state.get("c_extra_check", False)):
                    if (hora_del_dia >= st.session_state.get("c_inicio_extra", 0)) and (hora_del_dia < fin_cajas_extra): kg_a_distribuir_cajas = min(st.session_state.get("c_kg_extra", 0), kg_camara_fresco)
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.get("c_inicio", 0)) and (hora_del_dia < fin_cajas): kg_a_distribuir_cajas = min(st.session_state.get("kg_hora_cajas_total", 0), kg_camara_fresco)
                
                kg_total_congelados_acumulado += kg_a_distribuir_cajas

                if kg_a_distribuir_cajas > 0: 
                    kg_camara_fresco -= kg_a_distribuir_cajas
                    kg_huesos_hora = kg_a_distribuir_cajas * (pct_huesos / 100.0)
                    kg_carne_hora = kg_a_distribuir_cajas - kg_huesos_hora
                    
                    # PASADA 1 (PREFERIDA / VACÍA / MIXTA)
                    for tunel in tuneles:
                        if kg_huesos_hora > 0.01: 
                            # <--- CAMBIO: Pasar pesos
                            kg_huesos_hora = tunel.add_kg(kg_huesos_hora, hora_actual, "Huesos", kg_huesos_pallet, kg_carne_pallet, force_mix=False)
                    for tunel in tuneles:
                        if kg_carne_hora > 0.01: 
                            # <--- CAMBIO: Pasar pesos
                            kg_carne_hora = tunel.add_kg(kg_carne_hora, hora_actual, "Carne", kg_huesos_pallet, kg_carne_pallet, force_mix=False)
                    
                    # PASADA 2 (FORZAR MEZCLA)
                    for tunel in tuneles:
                        if kg_huesos_hora > 0.01: 
                            # <--- CAMBIO: Pasar pesos
                            kg_huesos_hora = tunel.add_kg(kg_huesos_hora, hora_actual, "Huesos", kg_huesos_pallet, kg_carne_pallet, force_mix=True)
                    for tunel in tuneles:
                        if kg_carne_hora > 0.01: 
                            # <--- CAMBIO: Pasar pesos
                            kg_carne_hora = tunel.add_kg(kg_carne_hora, hora_actual, "Carne", kg_huesos_pallet, kg_carne_pallet, force_mix=True)
                    
                    kg_congelar_fuera += kg_huesos_hora + kg_carne_hora
                
                # B. Placas
                procesado_placas = 0.0
                if (es_dia_extra and st.session_state.get("p_extra_check", False)):
                    if (hora_del_dia >= st.session_state.get("p_inicio_extra", 0)) and (hora_del_dia < fin_placas_extra): 
                        procesado_placas = min(st.session_state.get("p_kg_extra", 0), kg_camara_fresco)
                        kg_camara_fresco -= procesado_placas
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.get("p_inicio", 0)) and (hora_del_dia < fin_placas): 
                        procesado_placas = min(st.session_state.get("p_kg", 0), kg_camara_fresco)
                        kg_camara_fresco -= procesado_placas
                
                kg_total_congelados_acumulado += procesado_placas

                # C. Fresco
                # (Fresco sin cambios)
                demanda_fresco = 0.0
                if (es_dia_extra and st.session_state.get("f_extra_check", False)):
                    if (hora_del_dia >= st.session_state.get("f_inicio_extra", 0)) and (hora_del_dia < fin_fresco_extra) and (kg_cargados_fresco_hoy < st.session_state.get("f_kg_dia_extra", 0)):
                        demanda_fresco = kg_hora_fresco_extra
                        if (kg_cargados_fresco_hoy + demanda_fresco) > st.session_state.get("f_kg_dia_extra", 0): demanda_fresco = st.session_state.get("f_kg_dia_extra", 0) - kg_cargados_fresco_hoy
                        if demanda_fresco > 0.01: procesado_fresco = min(demanda_fresco, kg_camara_fresco); kg_camara_fresco -= procesado_fresco; kg_cargados_fresco_hoy += procesado_fresco
                elif (not es_dia_extra):
                     if (hora_del_dia >= st.session_state.get("f_inicio", 0)) and (hora_del_dia < fin_fresco) and (kg_cargados_fresco_hoy < st.session_state.get("f_kg_dia", 0)):
                        demanda_fresco = kg_hora_fresco
                        if (kg_cargados_fresco_hoy + demanda_fresco) > st.session_state.get("f_kg_dia", 0): demanda_fresco = st.session_state.get("f_kg_dia", 0) - kg_cargados_fresco_hoy
                        if demanda_fresco > 0.01: procesado_fresco = min(demanda_fresco, kg_camara_fresco); kg_camara_fresco -= procesado_fresco; kg_cargados_fresco_hoy += procesado_fresco

                # --- 3. Salida Túnel (Vaciado) ---
                # (Vaciado sin cambios, la lógica interna de la clase ya está ok)
                kg_por_vaciar_esta_hora = 0.0
                if (es_dia_extra and st.session_state.get("v_extra_check", False)):
                    if (hora_del_dia >= st.session_state.get("v_inicio_extra", 0)) and (hora_del_dia < fin_vaciado_extra): kg_por_vaciar_esta_hora = st.session_state.get("v_kg_extra", 0)
                elif (not es_dia_extra):
                    if (hora_del_dia >= st.session_state.get("v_inicio", 0)) and (hora_del_dia < fin_vaciado): kg_por_vaciar_esta_hora = st.session_state.get("v_kg", 0)
                if kg_por_vaciar_esta_hora > 0:
                    for tunel in tuneles:
                        if kg_por_vaciar_esta_hora <= 0.01: break
                        kg_vaciados_del_tunel = tunel.vaciar_kg(kg_por_vaciar_esta_hora, hora_actual)
                        kg_por_vaciar_esta_hora -= kg_vaciados_del_tunel

                # --- 4. Registro y UI ---
                # (Registro de historial sin cambios)
                kg_total_en_tuneles = sum(t.kg_actual for t in tuneles)
                historial_inventarios.append({'datetime': current_datetime,'Kg Cámara Refrigerado': kg_camara_fresco, 'Kg en Túneles (Total)': kg_total_en_tuneles, 'Kg Congelar Fuera': kg_congelar_fuera})
                df_historial = pd.DataFrame(historial_inventarios).set_index('datetime')
                if hora_del_dia == 23 or hora_actual == duracion_total_real:
                    dia = (hora_actual - 1) // 24 + 1; etiqueta_dia = f"Día {dia}"
                    if es_dia_extra and (hora_del_dia == 23 or hora_actual == duracion_total_real): etiqueta_dia = f"Día {dia} (Extra)"
                    resumen_diario.append({'Día': etiqueta_dia, 'Kg Cámara Refrigerado': kg_camara_fresco, 'Kg en Túneles (Total)': kg_total_en_tuneles, 'Kg Congelar Fuera': kg_congelar_fuera})

                # (Métricas sin cambios, 4 columnas)
                with placeholder_metricas.container():
                    msg = f"**Día { (hora_actual - 1) // 24 + 1 } - Hora: {hora_actual} / {duracion_total_real} ({current_datetime.strftime('%d.%m %H:%M')})**"
                    if es_dia_extra: st.warning(f"**DÍA EXTRA - Hora: {hora_actual} / {duracion_total_real} ({current_datetime.strftime('%d.%m %H:%M')})**")
                    else: st.info(msg)
                    col1_m, col_m2, col_m3, col_m4 = st.columns(4) 
                    col1_m.metric("🧊 Inv. Cámara", f"{kg_camara_fresco:,.0f}".replace(',', '.') + " kg")
                    label_tunel = "❄️ Inv. Túneles" + (" ⚠️" if kg_congelar_fuera > 0.01 else "")
                    col_m2.metric(label_tunel, f"{kg_total_en_tuneles:,.0f}".replace(',', '.') + " kg")
                    col_m3.metric("🔥 Congelar Fuera", f"{kg_congelar_fuera:,.0f}".replace(',', '.') + " kg")
                    col_m4.metric("🥶 Total Congelado", f"{kg_total_congelados_acumulado:,.0f}".replace(',', '.') + " kg")

                # (Gráfico sin cambios)
                with placeholder_grafico.container():
                    st.markdown("<h6>Evolución Inventarios (KG) vs Tiempo</h6>", unsafe_allow_html=True)
                    df_grafico_largo = df_historial.reset_index().melt('datetime', var_name='Inventario', value_name='Kg')
                    domain_ = ['Kg Cámara Refrigerado', 'Kg en Túneles (Total)', 'Kg Congelar Fuera']
                    range_ = ['#3498db', '#e67e22', '#e74c3c'] 
                    base = alt.Chart(df_grafico_largo).mark_area().encode(
                        x=alt.X('datetime:T', 
                            axis=alt.Axis(title='Fecha y Hora', format="%d.%m %H:%M", labelFontSize=18, titleFontSize=20)),
                        y=alt.Y('Kg:Q', stack=None, 
                            axis=alt.Axis(title='Kilogramos (kg)', labelFontSize=18, titleFontSize=20)),
                        color=alt.Color('Inventario', 
                                    scale=alt.Scale(domain=domain_, range=range_),
                                    legend=alt.Legend(title="Inventarios", labelFontSize=14, titleFontSize=16)),
                        opacity=alt.value(0.5),
                        tooltip=[alt.Tooltip('datetime:T', title='Fecha', format="%d.%m.%Y %H:%M"), 
                                 alt.Tooltip('Inventario'), 
                                 alt.Tooltip('Kg:Q', title='Kilos', format=',.0f')]
                    ).interactive()
                    st.altair_chart(base.properties(height=500), use_container_width=True)

                # (Visualización de túneles sin cambios)
                with placeholder_viz.container():
                    st.markdown("<h6 style='text-align: center;'>Ocupación Túneles (Palés)</h6>", unsafe_allow_html=True)
                    st.markdown("""
                    <div class="tunnel-legend">
                        <div class="legend-item">
                            <div class="legend-color-box" style="background-color: var(--color-huesos);"></div>
                            <span>Huesos (18h)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color-box" style="background-color: var(--color-carne);"></div>
                            <span>Carne (33h)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color-box" style="background-color: var(--primary-color);"></div>
                            <span>Congelado (Inicial)</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color-box" style="background-color: #bdc3c7;"></div>
                            <span>Vacío</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    cols_viz = st.columns(5)
                    if tuneles:
                        for i, tunel in enumerate(tuneles):
                            try:
                                cols_viz[i].markdown(tunel.get_html_viz(), unsafe_allow_html=True)
                            except Exception as e:
                                cols_viz[i].error(f"Error VIZ Tunel {i}: {e}")
                    else:
                        st.warning("No hay túneles definidos.")

                # (Progreso sin cambios)
                with placeholder_progreso.container():
                    st.markdown("---")
                    col_p1, col_p2 = st.columns(2)
                    objetivo_despiece_dia = kg_por_dia_despiece_total_extra if (es_dia_extra and st.session_state.get("d_extra_check", False)) else kg_por_dia_despiece_total
                    objetivo_fresco_dia = st.session_state.get("f_kg_dia_extra", 0) if (es_dia_extra and st.session_state.get("f_extra_check", False)) else st.session_state.get("f_kg_dia", 0)
                    with col_p1:
                        st.write(f"Prog. Despiece: {kg_procesados_despiece_hoy:,.0f}".replace(',', '.') + f" / {objetivo_despiece_dia:,.0f}".replace(',', '.') + " kg")
                        st.progress(int(kg_procesados_despiece_hoy / objetivo_despiece_dia * 100) if objetivo_despiece_dia > 0 else 0)
                    with col_p2:
                        st.write(f"Prog. C. Fresco: {kg_cargados_fresco_hoy:,.0f}".replace(',', '.') + f" / {objetivo_fresco_dia:,.0f}".replace(',', '.') + " kg")
                        st.progress(int(kg_cargados_fresco_hoy / objetivo_fresco_dia * 100) if objetivo_fresco_dia > 0 else 0)

                time.sleep(st.session_state.get("segundos_por_hora_sim", 0.1)) # Espera

            # --- FIN BUCLE ---
            st.success("✅ ¡Simulación Completada!")
            st.balloons()

            # --- TABLA FINAL ---
            # (Tabla final sin cambios)
            with placeholder_tabla_final.container():
                st.markdown("---")
                st.markdown("<h3>📈 Resumen Inventarios Fin de Día (Kg)</h3>", unsafe_allow_html=True)
                df_resumen = pd.DataFrame(resumen_diario).set_index('Día')
                st.dataframe(df_resumen.T.applymap(lambda x: f"{x:,.0f}".replace(',', '.') + " kg"), use_container_width=True)
