"""
BOT DE TRADING PROFESIONAL - VERSIÓN CON DATOS REALES DE YFINANCE
- Datos en vivo de Forex (pares principales)
- Selección automática del mejor activo (cada 5 minutos)
- 3 estrategias de tendencia + 1 modelo de IA (LightGBM simulado)
- Notificaciones 1 minuto antes con hora exacta
- Interfaz profesional con reloj en tiempo real
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

from streamlit_autorefresh import st_autorefresh
import yfinance as yf

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# Configuración de página
st.set_page_config(
    page_title="Forex Pro Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 15 segundos (solo para el reloj, el escaneo pesado se hace cada 5 min)
st_autorefresh(interval=15000, key="autorefresh")

# CSS personalizado (profesional, verde/negro)
st.markdown("""
<style>
    .stApp {
        background-color: #0A0C10;
        color: #E0E0E0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #00FF88 !important;
        font-weight: 700 !important;
    }
    .asset-card {
        background: rgba(18, 22, 30, 0.9);
        border-radius: 28px;
        padding: 25px;
        box-shadow: 0 25px 45px -15px rgba(0, 255, 136, 0.3);
        border: 1px solid #00FF8844;
        margin: 10px 0;
    }
    .asset-name {
        font-size: 24px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 10px;
    }
    .asset-signal {
        font-size: 20px;
        font-weight: 700;
        padding: 12px;
        border-radius: 40px;
        text-align: center;
        margin: 15px 0;
    }
    .signal-compra {
        background: rgba(0, 255, 136, 0.2);
        color: #00FF88;
        border: 2px solid #00FF88;
    }
    .signal-venta {
        background: rgba(255, 70, 70, 0.2);
        color: #FF4646;
        border: 2px solid #FF4646;
    }
    .asset-footer {
        font-size: 16px;
        color: #AAA;
        display: flex;
        justify-content: space-between;
        margin-top: 15px;
        padding-top: 15px;
        border-top: 1px solid #333;
    }
    .reloj {
        font-size: 28px;
        font-weight: 700;
        color: #00FF88;
        text-align: center;
        background: #151A24;
        padding: 15px;
        border-radius: 50px;
        margin-bottom: 20px;
        border: 1px solid #00FF88;
    }
    .badge-5min {
        background: #00FF88;
        color: black;
        padding: 5px 15px;
        border-radius: 30px;
        font-size: 14px;
        font-weight: 600;
        margin-left: 10px;
    }
    .stButton button {
        background: #00FF88;
        color: black;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 10px 25px;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CONFIGURACIÓN DE ACTIVOS (Forex principales)
# ============================================
SIMBOLOS_FOREX = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X",
    "USDCAD=X", "USDCHF=X", "NZDUSD=X", "EURGBP=X",
    "EURJPY=X", "GBPJPY=X", "AUDJPY=X", "EURAUD=X",
    "GBPAUD=X", "GBPCAD=X", "EURCAD=X", "AUDCAD=X"
]

# ============================================
# FUNCIONES DE DESCARGA DE DATOS (yfinance)
# ============================================
def obtener_datos_5min(simbolo):
    """Descarga velas de 5 minutos desde yfinance."""
    try:
        df = yf.download(simbolo, period="5d", interval="5m", progress=False)
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        return df
    except Exception as e:
        logging.error(f"Error descargando {simbolo}: {e}")
        return None

def calcular_indicadores(df):
    """Calcula indicadores técnicos incluyendo volumen simulado si es necesario."""
    if df is None or len(df) < 30:
        return None
    # Si el volumen es cero (a veces pasa), lo simulamos
    if df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['close'] * 100
    return df

# ============================================
# ESTRATEGIAS DE TENDENCIA (más flexibles)
# ============================================
def estrategia_ruptura(df):
    if df is None or len(df) < 15:
        return None, 0
    ult = df.iloc[-1]
    max_reciente = df['high'].iloc[-10:-1].max()
    min_reciente = df['low'].iloc[-10:-1].min()
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.1:
        return 'COMPRA', 70
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.1:
        return 'VENTA', 70
    return None, 0

def estrategia_pendiente_ema(df):
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if pendiente > 0.003 * ult['close']:
        return 'COMPRA', 65
    elif pendiente < -0.003 * ult['close']:
        return 'VENTA', 65
    return None, 0

def estrategia_adx_volumen(df):
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    if ult['adx'] > 20 and ult['volume_ratio'] > 1.2:
        pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-3]) / 3
        if pendiente > 0:
            return 'COMPRA', 75
        elif pendiente < 0:
            return 'VENTA', 75
    return None, 0

# ============================================
# MODELO DE IA (LightGBM simulado)
# ============================================
def predecir_con_ia(df):
    """
    Devuelve una señal (COMPRA/VENTA) y una confianza basada en reglas + IA.
    Simula un modelo de LightGBM.
    """
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    # Reglas base (simulando un modelo)
    score = 0
    if ult['rsi'] < 40:
        score += 20
    elif ult['rsi'] > 60:
        score -= 20
    if ult['volume_ratio'] > 1.3:
        score += 15
    if ult['adx'] > 25:
        score += 10 if ult['adx_pos'] > ult['adx_neg'] else -10
    # Simulación de red neuronal
    senal = 'COMPRA' if score > 10 else 'VENTA' if score < -10 else None
    confianza = min(90, max(50, abs(score) + 50))
    return senal, confianza

# ============================================
# ANÁLISIS DE UN ACTIVO (combina estrategias e IA)
# ============================================
def analizar_activo(simbolo):
    df = obtener_datos_5min(simbolo)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None

    # Estrategias
    s1, c1 = estrategia_ruptura(df)
    s2, c2 = estrategia_pendiente_ema(df)
    s3, c3 = estrategia_adx_volumen(df)
    s4, c4 = predecir_con_ia(df)   # IA

    # Votación ponderada
    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    for senal, conf in [(s1,c1), (s2,c2), (s3,c3), (s4,c4)]:
        if senal == 'COMPRA':
            votos_compra += conf
            peso_total += conf
        elif senal == 'VENTA':
            votos_venta += conf
            peso_total += conf

    if peso_total == 0:
        senal_final = None
        prob = 0
    else:
        if votos_compra > votos_venta:
            prob = int((votos_compra / peso_total) * 100)
            senal_final = 'COMPRA'
        elif votos_venta > votos_compra:
            prob = int((votos_venta / peso_total) * 100)
            senal_final = 'VENTA'
        else:
            senal_final = None
            prob = 0

    ult = df.iloc[-1]
    # Score para ranking: probabilidad * volumen * adx normalizado
    score = prob * (1 + ult['volume_ratio']/2) * (1 + ult['adx']/50) if senal_final else 10

    return {
        'simbolo': simbolo,
        'score': score,
        'senal': senal_final,
        'prob': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'df': df
    }

# ============================================
# ESCANEO DE TODOS LOS ACTIVOS Y SELECCIÓN DEL MEJOR
# ============================================
def escanear_mejor_activo():
    activos = SIMBOLOS_FOREX
    mejor = None
    max_score = -1
    progreso = st.progress(0)
    for i, sym in enumerate(activos):
        res = analizar_activo(sym)
        if res and res['score'] > max_score:
            max_score = res['score']
            mejor = res
        progreso.progress((i+1)/len(activos))
        time.sleep(0.1)  # para no saturar
    progreso.empty()
    return mejor

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("📈 FOREX PRO SCANNER")
    st.markdown("#### Análisis en tiempo real del mejor activo Forex (5 min) con IA")
    st.markdown("---")

    # Inicializar estado
    if 'mejor_activo' not in st.session_state:
        st.session_state.mejor_activo = None
    if 'ultima_actualizacion' not in st.session_state:
        st.session_state.ultima_actualizacion = None
    if 'notificadas' not in st.session_state:
        st.session_state.notificadas = set()

    # Barra lateral (solo información)
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### ℹ️ Información")
        st.markdown("""
        **Fuente de datos:** Yahoo Finance (Forex)
        **Activos analizados:** 16 pares principales
        **Estrategias:** Ruptura, Pendiente EMA, ADX + Volumen, IA
        **Actualización:** Cada 5 minutos (escaneo completo)
        """)
        if st.button("🔄 FORZAR ESCANEO AHORA", use_container_width=True):
            with st.spinner("Escaneando activos..."):
                mejor = escanear_mejor_activo()
                st.session_state.mejor_activo = mejor
                st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                st.session_state.notificadas = set()
                if mejor:
                    st.success(f"✅ Mejor activo: {mejor['simbolo']}")
                else:
                    st.warning("No se encontraron datos.")
                st.rerun()

    # Reloj en tiempo real
    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Escaneo automático periódico (cada 5 minutos)
    if (st.session_state.mejor_activo is None or
        st.session_state.ultima_actualizacion is None or
        (ahora - st.session_state.ultima_actualizacion).seconds > 300):
        with st.spinner("Actualizando análisis (cada 5 min)..."):
            mejor = escanear_mejor_activo()
            st.session_state.mejor_activo = mejor
            st.session_state.ultima_actualizacion = ahora
            st.session_state.notificadas = set()
            if mejor:
                st.success(f"✅ Mejor activo actualizado: {mejor['simbolo']}")

    # Mostrar el mejor activo
    st.markdown("## 🔥 ACTIVO MÁS CONFIABLE AHORA")
    if st.session_state.mejor_activo:
        a = st.session_state.mejor_activo
        nombre = a['simbolo'].replace("=X", "")
        color = "#00FF88" if a['senal'] == 'COMPRA' else "#FF4646" if a['senal'] == 'VENTA' else "#AAA"
        signal_class = f"signal-{a['senal'].lower()}" if a['senal'] else "signal-neutral"

        # Calcular hora de entrada (próxima vela de 5 min)
        minutos = ahora.minute
        minuto_base = (minutos // 5) * 5
        tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
        tiempo_salida = tiempo_entrada + timedelta(minutes=5)
        segundos_rest = (tiempo_entrada - ahora).seconds

        # Notificación 1 min antes
        if a['senal'] and segundos_rest <= 60 and segundos_rest > 0:
            clave = f"{a['simbolo']}_{tiempo_entrada}"
            if clave not in st.session_state.notificadas:
                st.toast(f"📢 **¡ATENCIÓN!** Opera a las {tiempo_entrada.strftime('%H:%M')} – {nombre} – {a['senal']}", icon="⏰")
                st.session_state.notificadas.add(clave)

        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">{nombre} <span class="badge-5min">5 MIN</span></div>
            <div class="asset-signal {signal_class}">{a['senal'] if a['senal'] else 'NEUTRAL'}</div>
            <div style="font-size: 32px; font-weight:800; color:{color}; text-align:center;">{a['prob']}%</div>
            <div class="asset-footer">
                <span>⏰ Entrada: {tiempo_entrada.strftime('%H:%M')}</span>
                <span>⏳ Vence: {tiempo_salida.strftime('%H:%M')}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px; color:#AAA;">
                <span>Precio: {a['precio']:.5f}</span>
                <span>RSI: {a['rsi']:.1f}</span>
                <span>Vol: {a['volume_ratio']:.1f}x</span>
                <span>ADX: {a['adx']:.1f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("No se pudo obtener ningún activo. Intenta más tarde.")

    # Gráfico opcional
    if st.session_state.mejor_activo and st.checkbox("📉 Mostrar gráfico del activo"):
        a = st.session_state.mejor_activo
        df_graf = a['df'].iloc[-50:].copy()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.7, 0.3],
                            subplot_titles=("Precio con EMAs", "Volumen"))
        fig.add_trace(go.Candlestick(x=df_graf.index,
                                      open=df_graf['open'],
                                      high=df_graf['high'],
                                      low=df_graf['low'],
                                      close=df_graf['close'],
                                      increasing_line_color='#00FF88',
                                      decreasing_line_color='#FF4646'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_20'],
                                  line=dict(color='#2962FF', width=2), name="EMA 20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                  line=dict(color='#FFAA00', width=2), name="EMA 50"), row=1, col=1)
        fig.add_trace(go.Bar(x=df_graf.index, y=df_graf['volume'],
                              marker_color='#00FF88', name="Volumen"), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", showlegend=False,
                          paper_bgcolor="#0A0C10", plot_bgcolor="#0A0C10")
        st.plotly_chart(fig, use_container_width=True)

    # Botón manual de actualización
    if st.button("🔄 Actualizar ahora"):
        st.rerun()

if __name__ == "__main__":
    main()
