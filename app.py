"""
Sistema Profesional de Trading IQ Option - TOP 4 SCANNER
Versión: 8.1 (corregidos errores de ta, indicadores válidos)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz
from datetime import datetime, timedelta
import ta
import time
import logging
import warnings
warnings.filterwarnings('ignore')

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# Intentar importar la API de IQ Option
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError:
    IQ_AVAILABLE = False
    st.error("""
    ⚠️ No se pudo importar la librería iqoptionapi.
    Por favor instala la versión actualizada desde:
    https://github.com/williansandi/iqoptionapi-2025-Atualizada-
    """)

# ============================================
# CONFIGURACIÓN DE PÁGINA Y TEMA PROFESIONAL
# ============================================
st.set_page_config(
    page_title="IQ Option Pro Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado para diseño profesional
st.markdown("""
<style>
    /* Fondo general */
    .stApp {
        background-color: #131722;
        color: #d1d4dc;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Títulos */
    h1, h2, h3 {
        color: #ffffff !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px;
    }
    h1 {
        border-bottom: 2px solid #2962ff;
        padding-bottom: 10px;
    }
    
    /* Tarjetas de activos */
    .asset-card {
        background: linear-gradient(145deg, #1e222d, #1a1e28);
        border-radius: 16px;
        padding: 20px 15px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.5);
        border: 1px solid #2a2e39;
        transition: transform 0.2s, box-shadow 0.2s;
        height: 100%;
        display: flex;
        flex-direction: column;
    }
    .asset-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 28px rgba(41,98,255,0.2);
        border-color: #2962ff;
    }
    .asset-name {
        font-size: 18px;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 8px;
    }
    .asset-status {
        font-size: 14px;
        color: #9ca3af;
        margin-bottom: 12px;
    }
    .asset-signal {
        font-size: 16px;
        font-weight: 700;
        padding: 8px 12px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 10px;
    }
    .signal-compra {
        background-color: rgba(0, 200, 100, 0.15);
        color: #00c864;
        border-left: 4px solid #00c864;
    }
    .signal-venta {
        background-color: rgba(255, 70, 70, 0.15);
        color: #ff4646;
        border-left: 4px solid #ff4646;
    }
    .signal-neutral {
        background-color: rgba(156, 163, 175, 0.1);
        color: #9ca3af;
        border-left: 4px solid #9ca3af;
    }
    .asset-time {
        font-size: 13px;
        color: #9ca3af;
        margin-top: auto;
        padding-top: 10px;
        border-top: 1px solid #2a2e39;
    }
    .asset-prob {
        font-size: 20px;
        font-weight: 700;
        margin: 10px 0;
    }
    
    /* Botones */
    .stButton button {
        background-color: #2962ff;
        color: white;
        font-weight: 600;
        border-radius: 8px;
        border: none;
        padding: 10px 20px;
        transition: background 0.2s;
    }
    .stButton button:hover {
        background-color: #1e4bd7;
    }
    
    /* Panel de alerta anticipada */
    .alert-box {
        background: linear-gradient(90deg, #1e2a3a, #131722);
        border-left: 6px solid #ffaa00;
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
        box-shadow: 0 4px 12px rgba(255,170,0,0.2);
    }
    
    /* Métricas */
    .metric-card {
        background-color: #1e222d;
        border-radius: 12px;
        padding: 15px;
        border: 1px solid #2a2e39;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #1a1e28 !important;
    }
    
    /* Inputs */
    .stTextInput input {
        background-color: #1e222d;
        border: 1px solid #2a2e39;
        color: white;
        border-radius: 8px;
    }
    
    /* Selectbox */
    .stSelectbox div[data-baseweb="select"] > div {
        background-color: #1e222d;
        border-color: #2a2e39;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN CON IQ OPTION
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.activos_cache = {}
        self.ultima_actualizacion_activos = None
        
    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible"
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                return True, "Conectado"
            else:
                return False, reason
        except Exception as e:
            return False, str(e)
    
    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            return self.api.change_balance(tipo)
        return False
    
    def obtener_saldo(self):
        if self.conectado:
            return self.api.get_balance()
        return 0
    
    def obtener_activos_disponibles(self, mercado="otc", max_activos=50):
        if not self.conectado:
            return []
        ahora = time.time()
        cache_key = f"{mercado}_{max_activos}"
        if (self.ultima_actualizacion_activos and 
            ahora - self.ultima_actualizacion_activos < 300 and
            cache_key in self.activos_cache):
            return self.activos_cache[cache_key]
        try:
            activos_data = self.api.get_all_open_time()
            activos = []
            if mercado == "forex":
                for activo, data in activos_data.get("forex", {}).items():
                    if data.get("open", False) and "-OTC" not in activo:
                        activos.append(activo)
            else:  # OTC
                for categoria in ["binary", "turbo"]:
                    for activo, data in activos_data.get(categoria, {}).items():
                        if data.get("open", False) and "-OTC" in activo:
                            activos.append(activo)
            activos = sorted(activos)[:max_activos]
            self.activos_cache[cache_key] = activos
            self.ultima_actualizacion_activos = ahora
            return activos
        except Exception as e:
            st.error(f"Error obteniendo activos: {e}")
            return []
    
    def obtener_velas(self, activo, intervalo=5, limite=100):
        if not self.conectado:
            return None
        try:
            velas = self.api.get_candles(activo, 60, limite * 5, time.time())
            if not velas:
                return None
            df = pd.DataFrame(velas)
            df['datetime'] = pd.to_datetime(df['from'], unit='s')
            df = df.set_index('datetime')
            df = df.rename(columns={'open': 'open', 'max': 'high', 'min': 'low', 'close': 'close'})
            df = df[['open', 'high', 'low', 'close']].astype(float).sort_index()
            if intervalo == 5:
                df = df.resample('5T').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last'
                }).dropna()
            return df
        except Exception as e:
            logging.error(f"Error obteniendo velas de {activo}: {e}")
            return None

# ============================================
# FUNCIONES DE INDICADORES TÉCNICOS (CORREGIDAS)
# ============================================
def calcular_indicadores(df):
    """Calcula indicadores técnicos usando ta correctamente"""
    if df is None or len(df) < 30:
        return None
    
    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    
    # Momentum usando ROC (Rate of Change) - ¡CORREGIDO!
    df['momentum'] = ta.momentum.ROCIndicator(df['close'], window=10).roc()
    
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    
    # Bandas de Bollinger
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['BBU'] = bb.bollinger_hband()
    df['BBL'] = bb.bollinger_lband()
    df['bb_pos'] = (df['close'] - df['BBL']) / (df['BBU'] - df['BBL']).clip(lower=0.001)
    
    # Volumen simulado
    df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    
    # ATR y volatilidad
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['volatilidad'] = df['atr'] / df['close'] * 100
    
    return df

def generar_score(df):
    """Genera score basado en indicadores"""
    if df is None or len(df) < 30:
        return 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50
    if ult['ema_20'] > ult['ema_50']:
        score += 10
    else:
        score -= 10
    if prev['ema_20'] < prev['ema_50'] and ult['ema_20'] > ult['ema_50']:
        score += 30
    elif prev['ema_20'] > prev['ema_50'] and ult['ema_20'] < ult['ema_50']:
        score += 30
    if ult['rsi'] < 30:
        score += 20
    elif ult['rsi'] > 70:
        score += 20
    if ult['bb_pos'] < 0.1:
        score += 15
    elif ult['bb_pos'] > 0.9:
        score += 15
    if ult['volume_ratio'] > 1.5:
        score += 15
    if abs(ult['momentum']) > 2:
        score += 10
    return score

def detectar_senal(df):
    """Detecta señal de compra/venta"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    senal = None
    prob = 50
    if prev['ema_20'] < prev['ema_50'] and ult['ema_20'] > ult['ema_50']:
        senal = 'COMPRA'
        prob = 75
    elif prev['ema_20'] > prev['ema_50'] and ult['ema_20'] < ult['ema_50']:
        senal = 'VENTA'
        prob = 75
    elif ult['close'] <= ult['BBL'] and ult['rsi'] < 30:
        senal = 'COMPRA'
        prob = 80
    elif ult['close'] >= ult['BBU'] and ult['rsi'] > 70:
        senal = 'VENTA'
        prob = 80
    if senal and ult['volume_ratio'] > 1.3:
        prob = min(95, prob + 10)
    return senal, int(prob)

# ============================================
# FUNCIÓN DE ANÁLISIS DE ACTIVOS
# ============================================
def analizar_activo(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None
    score = generar_score(df)
    senal, prob = detectar_senal(df)
    ult = df.iloc[-1]
    return {
        'activo': activo,
        'score': score,
        'senal': senal,
        'probabilidad': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volatilidad': ult['volatilidad'],
        'df': df
    }

# ============================================
# FUNCIÓN PARA ACTUALIZAR TOP 4
# ============================================
def actualizar_top_activos(connector, mercado, max_activos=50):
    activos_lista = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos_lista:
        return []
    resultados = []
    progreso = st.progress(0)
    for i, activo in enumerate(activos_lista):
        res = analizar_activo(activo, connector)
        if res:
            resultados.append(res)
        progreso.progress((i + 1) / len(activos_lista))
    progreso.empty()
    resultados.sort(key=lambda x: x['score'], reverse=True)
    return resultados[:4]

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("📊 IQ OPTION PRO SCANNER")
    st.markdown("#### Sistema de detección de oportunidades - 4 Mejores Activos en Tiempo Real")
    st.markdown("---")
    
    # Inicializar estado de sesión
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'top_activos' not in st.session_state:
        st.session_state.top_activos = []
    if 'ultima_actualizacion' not in st.session_state:
        st.session_state.ultima_actualizacion = None
    if 'mercado_actual' not in st.session_state:
        st.session_state.mercado_actual = "otc"
    if 'activo_principal' not in st.session_state:
        st.session_state.activo_principal = None
    
    # Barra lateral - Login y controles
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Acceso IQ Option")
        
        if not st.session_state.conectado:
            email = st.text_input("Correo electrónico", placeholder="usuario@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            tipo_cuenta = st.selectbox("Tipo de cuenta", ["PRACTICE", "REAL"])
            
            if st.button("🔌 Conectar", use_container_width=True):
                if email and password:
                    with st.spinner("Conectando..."):
                        ok, msg = st.session_state.connector.conectar(email, password)
                        if ok:
                            st.session_state.connector.cambiar_balance(tipo_cuenta)
                            st.session_state.conectado = True
                            st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {msg}")
                else:
                    st.warning("Ingresa credenciales")
        else:
            st.success(f"✅ Conectado: {tipo_cuenta if 'tipo_cuenta' in locals() else 'PRACTICE'}")
            st.metric("Saldo", f"${st.session_state.connector.obtener_saldo():.2f}")
            if st.button("🚪 Desconectar"):
                st.session_state.conectado = False
                st.session_state.connector = IQOptionConnector()
                st.rerun()
        
        st.markdown("---")
        
        if st.session_state.conectado:
            st.markdown("### ⚙️ Configuración")
            mercado = st.radio(
                "Mercado a analizar",
                ["🌙 OTC (Fin de semana)", "📊 Normal (Forex)"],
                index=0
            )
            mercado_key = "otc" if "OTC" in mercado else "forex"
            st.session_state.mercado_actual = mercado_key
            
            if st.button("🔍 ESCANEAR TOP 4", use_container_width=True):
                with st.spinner("Analizando activos..."):
                    top = actualizar_top_activos(
                        st.session_state.connector,
                        mercado_key,
                        max_activos=50
                    )
                    st.session_state.top_activos = top
                    st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                    if top:
                        st.session_state.activo_principal = top[0]['activo']
                    st.success("✅ Análisis completado")
                    st.rerun()
    
    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral para comenzar")
        # Mostrar 4 tarjetas vacías
        cols = st.columns(4)
        for i in range(4):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Ejemplo OTC</div>
                    <div class="asset-status">⏳ Conéctate para ver datos</div>
                </div>
                """, unsafe_allow_html=True)
        return
    
    # Actualización automática cada 5 min si no hay datos
    ahora = datetime.now(ecuador_tz)
    if (st.session_state.ultima_actualizacion is None or 
        (ahora - st.session_state.ultima_actualizacion).seconds > 300):
        if not st.session_state.top_activos:
            with st.spinner("Escaneando activos por primera vez..."):
                top = actualizar_top_activos(
                    st.session_state.connector,
                    st.session_state.mercado_actual,
                    max_activos=50
                )
                st.session_state.top_activos = top
                st.session_state.ultima_actualizacion = ahora
                if top:
                    st.session_state.activo_principal = top[0]['activo']
                st.rerun()
    
    # Botón de actualización manual
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("🔄 ACTUALIZAR ANÁLISIS", use_container_width=True):
            with st.spinner("Actualizando..."):
                top = actualizar_top_activos(
                    st.session_state.connector,
                    st.session_state.mercado_actual,
                    max_activos=50
                )
                st.session_state.top_activos = top
                st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                if top:
                    st.session_state.activo_principal = top[0]['activo']
                st.rerun()
    
    with col3:
        if st.session_state.ultima_actualizacion:
            st.caption(f"Última actualización: {st.session_state.ultima_actualizacion.strftime('%H:%M:%S')}")
    
    st.markdown("---")
    
    # Mostrar las 4 tarjetas
    st.subheader("🔥 TOP 4 ACTIVOS CON MAYOR POTENCIAL")
    
    if not st.session_state.top_activos:
        st.warning("No hay datos disponibles. Presiona 'ESCANEAR TOP 4' en la barra lateral.")
        cols = st.columns(4)
        for i in range(4):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Cargando...</div>
                    <div class="asset-status">⏳ Escanea para ver datos</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        activos_mostrar = st.session_state.top_activos.copy()
        while len(activos_mostrar) < 4:
            activos_mostrar.append(None)
        
        cols = st.columns(4)
        for idx, activo in enumerate(activos_mostrar):
            with cols[idx]:
                if activo is None:
                    st.markdown("""
                    <div class="asset-card" style="opacity:0.5;">
                        <div class="asset-name">Esperando...</div>
                        <div class="asset-status">⏳ Nuevo activo pronto</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    if activo['senal'] == 'COMPRA':
                        signal_class = "signal-compra"
                        signal_text = f"📈 {activo['senal']} - {activo['probabilidad']}%"
                    elif activo['senal'] == 'VENTA':
                        signal_class = "signal-venta"
                        signal_text = f"📉 {activo['senal']} - {activo['probabilidad']}%"
                    else:
                        signal_class = "signal-neutral"
                        signal_text = "⚪ NEUTRAL"
                    
                    minutos = ahora.minute
                    minuto_base = (minutos // 5) * 5
                    tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
                    tiempo_salida = tiempo_entrada + timedelta(minutes=5)
                    
                    st.markdown(f"""
                    <div class="asset-card">
                        <div class="asset-name">{activo['activo']}</div>
                        <div class="asset-status">Score: {activo['score']} | RSI: {activo['rsi']:.1f}</div>
                        <div class="asset-signal {signal_class}">{signal_text}</div>
                        <div class="asset-prob" style="color: {'#00c864' if activo['senal']=='COMPRA' else '#ff4646' if activo['senal']=='VENTA' else '#9ca3af'};">
                            {activo['probabilidad']}% probabilidad
                        </div>
                        <div class="asset-time">
                            ⏰ Entrada: {tiempo_entrada.strftime('%H:%M')}<br>
                            ⏳ Vencimiento: {tiempo_salida.strftime('%H:%M')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Activo principal (el mejor) - gráfico detallado
    if st.session_state.top_activos:
        mejor = st.session_state.top_activos[0]
        st.subheader(f"📈 Análisis Detallado: {mejor['activo']}")
        
        # Alerta anticipada
        minutos = ahora.minute
        minuto_base = (minutos // 5) * 5
        tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
        segundos_restantes = (tiempo_entrada - ahora).seconds
        if mejor['senal'] and segundos_restantes <= 60 and segundos_restantes > 0:
            st.markdown(f"""
            <div class="alert-box">
                <h3 style="color:#ffaa00; margin:0;">⚠️ SEÑAL CONFIRMADA - 1 MINUTO DE ANTICIPACIÓN</h3>
                <p style="font-size:18px; margin:10px 0 0 0;">
                    <strong>{mejor['activo']}</strong> - {mejor['senal']} a las {tiempo_entrada.strftime('%H:%M')} - 
                    Vencimiento {(tiempo_entrada+timedelta(minutes=5)).strftime('%H:%M')} - Probabilidad {mejor['probabilidad']}%
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        # Gráfico con Plotly
        df_graf = mejor['df'].iloc[-50:].copy()
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            row_heights=[0.6, 0.2, 0.2],
                            subplot_titles=("Precio", "RSI", "Volumen"))
        # Velas
        fig.add_trace(go.Candlestick(
            x=df_graf.index,
            open=df_graf['open'],
            high=df_graf['high'],
            low=df_graf['low'],
            close=df_graf['close'],
            name="",
            increasing_line_color='#00c864',
            decreasing_line_color='#ff4646'
        ), row=1, col=1)
        # EMAs
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_20'],
                                  line=dict(color='#2962ff', width=2), name="EMA 20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                  line=dict(color='#ffaa00', width=2), name="EMA 50"), row=1, col=1)
        # Bandas de Bollinger
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBU'],
                                  line=dict(color='#888', dash='dash'), name="BB Sup"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBL'],
                                  line=dict(color='#888', dash='dash'), name="BB Inf"), row=1, col=1)
        # RSI
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['rsi'],
                                  line=dict(color='white', width=2), name="RSI"), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2)
        fig.add_hline(y=30, line_dash="dash", line_color="#00c864", row=2)
        # Volumen
        colors_vol = ['#00c864' if df_graf['close'].iloc[i] >= df_graf['close'].iloc[i-1] 
                     else '#ff4646' for i in range(1, len(df_graf))]
        colors_vol.insert(0, '#00c864')
        fig.add_trace(go.Bar(x=df_graf.index, y=df_graf['volume'],
                              marker_color=colors_vol, name="Volumen"), row=3, col=1)
        fig.update_layout(
            height=700,
            template="plotly_dark",
            paper_bgcolor="#131722",
            plot_bgcolor="#131722",
            font_color="#d1d4dc",
            hovermode="x unified",
            showlegend=False
        )
        fig.update_xaxes(gridcolor="#2a2e39")
        fig.update_yaxes(gridcolor="#2a2e39")
        st.plotly_chart(fig, use_container_width=True)
        
        # Panel de detalles
        st.subheader("🔍 Detalles del Activo Principal")
        ult = mejor['df'].iloc[-1]
        cols = st.columns(4)
        with cols[0]:
            st.metric("Precio", f"{ult['close']:.5f}")
        with cols[1]:
            st.metric("RSI", f"{ult['rsi']:.2f}")
        with cols[2]:
            st.metric("Volatilidad", f"{ult['volatilidad']:.2f}%")
        with cols[3]:
            st.metric("Volumen Ratio", f"{ult['volume_ratio']:.2f}x")
    
    # Modo replay
    st.markdown("---")
    if st.button("🎮 Modo Replay (Siguiente vela)"):
        st.session_state.ultima_actualizacion = None
        st.rerun()

if __name__ == "__main__":
    main()
