"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN AVANZADA
Características nuevas:
- Detección de tendencias por máximos/mínimos (pivotes)
- Uso de volumen real de operaciones
- Múltiples estrategias independientes (voto ponderado)
- Filtro MACD para evitar falsas señales
- Interfaz renovada en verde/negro
- Sensibilidad ajustada para no perder oportunidades
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

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# Importar API de IQ Option
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError:
    IQ_AVAILABLE = False
    st.error("""
    ⚠️ **Error crítico:** No se pudo importar la librería `iqoptionapi`.
    Verifica que esté correctamente instalada desde GitHub.
    """)

# Configuración de página
st.set_page_config(
    page_title="IQ Option Pro Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado - Tema verde/negro moderno
st.markdown("""
<style>
    /* Fondo general - negro profundo */
    .stApp { background-color: #0A0C10; color: #E0E0E0; font-family: 'Inter', sans-serif; }
    /* Títulos en verde neón */
    h1, h2, h3 { color: #00FF88 !important; font-weight: 700 !important; letter-spacing: -0.5px; }
    h1 { border-bottom: 2px solid #00FF88; padding-bottom: 10px; }
    /* Tarjetas de activos - estilo glassmorphism */
    .asset-card {
        background: rgba(20, 25, 35, 0.8);
        backdrop-filter: blur(10px);
        border-radius: 24px;
        padding: 22px 18px;
        box-shadow: 0 15px 35px -10px rgba(0, 255, 136, 0.2);
        border: 1px solid rgba(0, 255, 136, 0.3);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        height: 100%;
        display: flex;
        flex-direction: column;
        border-left: 4px solid #00FF88;
    }
    .asset-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 25px 45px -10px #00FF88;
        border-color: #00FF88;
    }
    .asset-name { font-size: 20px; font-weight: 700; color: #FFFFFF; margin-bottom: 8px; }
    .asset-price { font-size: 14px; color: #AAAAAA; margin-bottom: 15px; }
    .asset-signal {
        font-size: 16px; font-weight: 700; padding: 10px 14px; border-radius: 30px;
        text-align: center; margin-bottom: 12px; text-transform: uppercase;
    }
    .signal-compra { background-color: rgba(0, 255, 136, 0.15); color: #00FF88; border: 1px solid #00FF88; }
    .signal-venta { background-color: rgba(255, 70, 70, 0.15); color: #FF4646; border: 1px solid #FF4646; }
    .signal-neutral { background-color: rgba(255, 255, 255, 0.05); color: #AAAAAA; border: 1px solid #333; }
    .asset-footer {
        font-size: 13px; color: #888; margin-top: auto; padding-top: 15px;
        border-top: 1px solid #222; display: flex; justify-content: space-between;
    }
    .asset-prob { font-size: 24px; font-weight: 800; margin: 8px 0; }
    /* Botones */
    .stButton button {
        background: linear-gradient(135deg, #00FF88, #00CC66);
        color: #0A0C10;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 12px 28px;
        transition: all 0.2s;
        box-shadow: 0 8px 20px -5px #00FF88;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stButton button:hover {
        background: linear-gradient(135deg, #00CC66, #00FF88);
        box-shadow: 0 12px 28px -5px #00FF88;
        transform: scale(1.02);
    }
    /* Alertas anticipadas */
    .alert-box {
        background: linear-gradient(90deg, #1A2A1A, #0A0C10);
        border-left: 6px solid #FFAA00;
        border-radius: 20px;
        padding: 20px 25px;
        margin: 20px 0;
        box-shadow: 0 15px 30px -10px #FFAA0044;
    }
    /* Selector de mercado */
    .mercado-selector {
        background: #151A24; padding: 8px; border-radius: 60px; display: flex;
        gap: 10px; border: 1px solid #00FF8833; margin-bottom: 25px;
    }
    /* Métricas */
    .metric-card {
        background: #151A24; border-radius: 20px; padding: 18px; border: 1px solid #00FF8822;
        box-shadow: 0 10px 20px -10px #00FF8822;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# === CLASE DE CONEXIÓN Y DATOS DE IQ OPTION ===
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.activos_cache = {}
        self.ultima_actualizacion_activos = None

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                return True, "Conexión exitosa"
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
            else:
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
        """Obtiene velas incluyendo VOLUMEN real (número de ticks)"""
        if not self.conectado:
            return None
        try:
            time.sleep(0.15)
            velas = self.api.get_candles(activo, 60, limite * 5, time.time())
            if not velas:
                return None

            df = pd.DataFrame(velas)
            df['datetime'] = pd.to_datetime(df['from'], unit='s')
            df = df.set_index('datetime')
            # Incluir todas las columnas: open, max, min, close, volume
            df = df.rename(columns={
                'open': 'open',
                'max': 'high',
                'min': 'low',
                'close': 'close',
                'volume': 'volume'  # Volumen real de ticks
            })
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float).sort_index()

            if intervalo == 5:
                df = df.resample('5T').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'  # Sumar el volumen en el período de 5 minutos
                }).dropna()
            return df
        except Exception as e:
            logging.error(f"Error obteniendo velas de {activo}: {e}")
            return None

# === FUNCIONES DE ANÁLISIS TÉCNICO AVANZADO ===

def detectar_tendencia_por_pivotes(df, ventana=5):
    """
    Detecta tendencia alcista/bajista basada en máximos y mínimos crecientes/decrecientes.
    Retorna: 'alcista', 'bajista' o 'lateral'.
    """
    if df is None or len(df) < ventana * 2:
        return 'lateral'
    # Encontrar máximos y mínimos locales (pivotes)
    highs = df['high'].values
    lows = df['low'].values
    pivots_high = []
    pivots_low = []
    for i in range(ventana, len(df)-ventana):
        if highs[i] == max(highs[i-ventana:i+ventana+1]):
            pivots_high.append((i, highs[i]))
        if lows[i] == min(lows[i-ventana:i+ventana+1]):
            pivots_low.append((i, lows[i]))

    if len(pivots_high) < 2 and len(pivots_low) < 2:
        return 'lateral'

    # Evaluar tendencia de máximos
    if len(pivots_high) >= 2:
        high_increasing = all(pivots_high[j][1] < pivots_high[j+1][1] for j in range(len(pivots_high)-1))
        high_decreasing = all(pivots_high[j][1] > pivots_high[j+1][1] for j in range(len(pivots_high)-1))
    else:
        high_increasing = high_decreasing = False

    # Evaluar tendencia de mínimos
    if len(pivots_low) >= 2:
        low_increasing = all(pivots_low[j][1] < pivots_low[j+1][1] for j in range(len(pivots_low)-1))
        low_decreasing = all(pivots_low[j][1] > pivots_low[j+1][1] for j in range(len(pivots_low)-1))
    else:
        low_increasing = low_decreasing = False

    if (high_increasing and low_increasing) or (high_increasing and not low_decreasing):
        return 'alcista'
    elif (high_decreasing and low_decreasing) or (high_decreasing and not low_increasing):
        return 'bajista'
    else:
        return 'lateral'

def calcular_indicadores_completos(df):
    """Calcula todos los indicadores necesarios: RSI, MACD, EMAs, Bandas, Volumen, etc."""
    if df is None or len(df) < 30:
        return None

    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    # MACD
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    # Bandas de Bollinger
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['BBU'] = bb.bollinger_hband()
    df['BBL'] = bb.bollinger_lband()
    df['bb_pos'] = (df['close'] - df['BBL']) / (df['BBU'] - df['BBL']).clip(lower=0.001)
    # Volumen
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # ATR y volatilidad
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['volatilidad'] = df['atr'] / df['close'] * 100

    return df

# === ESTRATEGIAS INDEPENDIENTES ===
# Cada estrategia devuelve una señal (COMPRA, VENTA o None) y un nivel de confianza (0-100)

def estrategia_cruce_emas(df):
    """Estrategia clásica de cruce de EMAs 20/50"""
    if df is None or len(df) < 50:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ema_20'] < prev['ema_50'] and ult['ema_20'] > ult['ema_50']:
        return 'COMPRA', 75
    elif prev['ema_20'] > prev['ema_50'] and ult['ema_20'] < ult['ema_50']:
        return 'VENTA', 75
    return None, 0

def estrategia_rsi_extremo(df):
    """RSI extremo con confirmación de volumen"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    if ult['rsi'] < 30 and ult['volume_ratio'] > 1.2:
        return 'COMPRA', 70
    elif ult['rsi'] > 70 and ult['volume_ratio'] > 1.2:
        return 'VENTA', 70
    elif ult['rsi'] < 30:
        return 'COMPRA', 55  # Señal más débil si no hay volumen
    elif ult['rsi'] > 70:
        return 'VENTA', 55
    return None, 0

def estrategia_bandas_bollinger(df):
    """Rebotes en bandas de Bollinger + RSI"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    if ult['close'] <= ult['BBL'] and ult['rsi'] < 40:
        return 'COMPRA', 80
    elif ult['close'] >= ult['BBU'] and ult['rsi'] > 60:
        return 'VENTA', 80
    return None, 0

def estrategia_macd(df):
    """Cruce de MACD"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] < prev['macd_signal'] and ult['macd'] > ult['macd_signal']:
        return 'COMPRA', 70
    elif prev['macd'] > prev['macd_signal'] and ult['macd'] < ult['macd_signal']:
        return 'VENTA', 70
    return None, 0

def estrategia_tendencia_pivotes(df):
    """Detección de tendencia por máximos/mínimos"""
    tendencia = detectar_tendencia_por_pivotes(df)
    if tendencia == 'alcista':
        return 'COMPRA', 65
    elif tendencia == 'bajista':
        return 'VENTA', 65
    return None, 0

def estrategia_volumen_fuerza(df):
    """Detección de fuerza por volumen y momentum"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    # Si el volumen es muy alto y el momentum positivo, es compra
    if ult['volume_ratio'] > 1.8 and ult['momentum'] > 0:
        return 'COMPRA', 75
    elif ult['volume_ratio'] > 1.8 and ult['momentum'] < 0:
        return 'VENTA', 75
    return None, 0

# === ENSAMBLE DE ESTRATEGIAS ===
def evaluar_activo_con_ia(df):
    """
    Ejecuta todas las estrategias y combina sus votos para obtener una señal final
    y un nivel de probabilidad.
    """
    estrategias = [
        estrategia_cruce_emas,
        estrategia_rsi_extremo,
        estrategia_bandas_bollinger,
        estrategia_macd,
        estrategia_tendencia_pivotes,
        estrategia_volumen_fuerza
    ]

    votos_compra = 0
    votos_venta = 0
    peso_total = 0

    for est in estrategias:
        señal, confianza = est(df)
        if señal == 'COMPRA':
            votos_compra += confianza
            peso_total += confianza
        elif señal == 'VENTA':
            votos_venta += confianza
            peso_total += confianza

    if peso_total == 0:
        return None, 0

    # Decidir señal por mayoría ponderada
    if votos_compra > votos_venta:
        probabilidad = int((votos_compra / peso_total) * 100)
        return 'COMPRA', max(50, min(95, probabilidad))
    elif votos_venta > votos_compra:
        probabilidad = int((votos_venta / peso_total) * 100)
        return 'VENTA', max(50, min(95, probabilidad))
    else:
        return None, 0

def generar_score_ia(df):
    """Genera un score basado en las estrategias (para ranking)"""
    señal, prob = evaluar_activo_con_ia(df)
    # Score base: 50 + (prob-50)*2 si hay señal, sino 0
    if señal:
        return 50 + (prob - 50) * 2
    else:
        # Si no hay señal, dar un puntaje bajo pero no cero para que pueda aparecer
        return 30

# === ANÁLISIS DE UN ACTIVO ===
def analizar_activo(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores_completos(df)
    if df is None:
        return None
    señal, probabilidad = evaluar_activo_con_ia(df)
    score = generar_score_ia(df)
    ult = df.iloc[-1] if len(df) > 0 else None
    if ult is None:
        return None
    return {
        'activo': activo,
        'score': score,
        'senal': señal,
        'probabilidad': probabilidad,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volatilidad': ult['volatilidad'],
        'volume_ratio': ult['volume_ratio'],
        'df': df
    }

def actualizar_top_activos(connector, mercado, max_activos=50):
    activos_lista = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos_lista:
        return []
    resultados = []
    progreso = st.progress(0)
    total = len(activos_lista)
    for i, activo in enumerate(activos_lista):
        time.sleep(0.1)
        res = analizar_activo(activo, connector)
        if res:
            resultados.append(res)
        progreso.progress((i + 1) / total)
    progreso.empty()

    # Eliminar duplicados
    vistos = set()
    resultados_unicos = []
    for r in resultados:
        if r['activo'] not in vistos:
            vistos.add(r['activo'])
            resultados_unicos.append(r)

    resultados_unicos.sort(key=lambda x: x['score'], reverse=True)
    return resultados_unicos[:4]

# === INTERFAZ PRINCIPAL ===
def main():
    st.title("📊 IQ OPTION PRO SCANNER")
    st.markdown("#### Sistema Avanzado con Múltiples Estrategias y Volumen Real")
    st.markdown("---")

    # Inicializar estado
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

    # Barra lateral
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Acceso a IQ Option")

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
            st.success(f"✅ Conectado")
            saldo = st.session_state.connector.obtener_saldo()
            st.metric("Saldo", f"${saldo:.2f}" if saldo else "N/A")
            if st.button("🚪 Desconectar"):
                st.session_state.conectado = False
                st.session_state.connector = IQOptionConnector()
                st.session_state.top_activos = []
                st.rerun()

        st.markdown("---")

        if st.session_state.conectado:
            st.markdown("### ⚙️ Configuración")
            mercado = st.radio(
                "Mercado a analizar",
                ["🌙 OTC (24/7)", "📊 Normal (Forex)"],
                index=0,
                horizontal=True
            )
            mercado_key = "otc" if "OTC" in mercado else "forex"
            st.session_state.mercado_actual = mercado_key

            if st.button("🔍 ANALIZAR TOP 4", use_container_width=True):
                with st.spinner("Analizando activos en tiempo real..."):
                    top = actualizar_top_activos(
                        st.session_state.connector,
                        mercado_key,
                        max_activos=50
                    )
                    st.session_state.top_activos = top
                    st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                    if top:
                        st.success(f"✅ Análisis completado. {len(top)} activos encontrados.")
                    else:
                        st.warning("No se encontraron activos con datos suficientes.")
                    st.rerun()

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral para comenzar.")
        cols = st.columns(4)
        for i in range(4):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Esperando conexión...</div>
                    <div class="asset-price">---</div>
                </div>
                """, unsafe_allow_html=True)
        return

    # Botón de actualización manual y timestamp
    col1, col2, col3 = st.columns([1.5, 2, 1.5])
    with col1:
        if st.button("🔄 ACTUALIZAR AHORA", use_container_width=True):
            with st.spinner("Actualizando análisis..."):
                top = actualizar_top_activos(
                    st.session_state.connector,
                    st.session_state.mercado_actual,
                    max_activos=50
                )
                st.session_state.top_activos = top
                st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                st.rerun()

    with col3:
        if st.session_state.ultima_actualizacion:
            st.caption(f"Último análisis: {st.session_state.ultima_actualizacion.strftime('%H:%M:%S')}")

    st.markdown("---")

    # Mostrar los 4 mejores activos
    st.subheader("🔥 TOP 4 ACTIVOS CON MAYOR PROBABILIDAD")

    if not st.session_state.top_activos:
        st.warning("Presiona 'ANALIZAR TOP 4' para obtener resultados.")
        cols = st.columns(4)
        for i in range(4):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Cargando...</div>
                    <div class="asset-price">Escanea para ver datos</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        activos_mostrar = st.session_state.top_activos.copy()
        while len(activos_mostrar) < 4:
            activos_mostrar.append(None)

        cols = st.columns(4)
        ahora = datetime.now(ecuador_tz)
        minutos = ahora.minute
        minuto_base = (minutos // 5) * 5
        tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
        tiempo_salida = tiempo_entrada + timedelta(minutes=5)

        for idx, activo in enumerate(activos_mostrar):
            with cols[idx]:
                if activo is None:
                    st.markdown("""
                    <div class="asset-card" style="opacity:0.5;">
                        <div class="asset-name">En espera...</div>
                        <div class="asset-price">Próximo activo</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Determinar estilo de señal
                    if activo['senal'] == 'COMPRA':
                        signal_class = "signal-compra"
                        signal_text = f"📈 COMPRA"
                        color_prob = "#00FF88"
                    elif activo['senal'] == 'VENTA':
                        signal_class = "signal-venta"
                        signal_text = f"📉 VENTA"
                        color_prob = "#FF4646"
                    else:
                        signal_class = "signal-neutral"
                        signal_text = "⚪ NEUTRAL"
                        color_prob = "#AAAAAA"

                    nombre_activo = activo['activo'].replace("-OTC", "")

                    st.markdown(f"""
                    <div class="asset-card">
                        <div class="asset-name">{nombre_activo}</div>
                        <div class="asset-price">Precio: {activo['precio']:.5f} | RSI: {activo['rsi']:.1f}</div>
                        <div class="asset-signal {signal_class}">{signal_text}</div>
                        <div class="asset-prob" style="color: {color_prob};">{activo['probabilidad']}%</div>
                        <div class="asset-footer">
                            <span>⏰ {tiempo_entrada.strftime('%H:%M')}</span>
                            <span>⏳ {tiempo_salida.strftime('%H:%M')}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    st.markdown("---")

    # Activo principal (el #1) con gráfico detallado
    if st.session_state.top_activos:
        mejor = st.session_state.top_activos[0]
        st.subheader(f"📈 Análisis Detallado: {mejor['activo'].replace('-OTC', '')}")

        # Alerta anticipada
        ahora = datetime.now(ecuador_tz)
        minutos = ahora.minute
        minuto_base = (minutos // 5) * 5
        tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
        segundos_restantes = (tiempo_entrada - ahora).seconds

        if mejor['senal'] and segundos_restantes <= 60 and segundos_restantes > 0:
            st.markdown(f"""
            <div class="alert-box">
                <h3 style="color:#FFAA00; margin:0;">⚠️ SEÑAL CONFIRMADA - 1 MINUTO DE ANTICIPACIÓN</h3>
                <p style="font-size:1.2rem; margin:10px 0 0 0;">
                    <strong>{mejor['activo'].replace('-OTC', '')}</strong> - {mejor['senal']} a las {tiempo_entrada.strftime('%H:%M')}<br>
                    Vencimiento: {(tiempo_entrada+timedelta(minutes=5)).strftime('%H:%M')} | Probabilidad: {mejor['probabilidad']}%
                </p>
            </div>
            """, unsafe_allow_html=True)

        # Gráfico
        if mejor['df'] is not None and len(mejor['df']) > 20:
            df_graf = mejor['df'].iloc[-50:].copy()
            fig = make_subplots(
                rows=4, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                row_heights=[0.5, 0.15, 0.2, 0.15],
                subplot_titles=("Precio con EMAs y BB", "RSI", "Volumen", "MACD")
            )
            # Velas
            fig.add_trace(go.Candlestick(
                x=df_graf.index,
                open=df_graf['open'],
                high=df_graf['high'],
                low=df_graf['low'],
                close=df_graf['close'],
                name="",
                increasing_line_color='#00FF88',
                decreasing_line_color='#FF4646',
                showlegend=False
            ), row=1, col=1)
            # EMAs
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_20'],
                                      line=dict(color='#2962FF', width=2.5), name="EMA 20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                      line=dict(color='#FFAA00', width=2.5), name="EMA 50"), row=1, col=1)
            # Bandas
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBU'],
                                      line=dict(color='#888', dash='dash'), name="BB Sup"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBL'],
                                      line=dict(color='#888', dash='dash'), name="BB Inf"), row=1, col=1)
            # RSI
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['rsi'],
                                      line=dict(color='#FFFFFF', width=2), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#FF4646", row=2)
            fig.add_hline(y=30, line_dash="dash", line_color="#00FF88", row=2)
            # Volumen
            colors_vol = ['#00FF88' if df_graf['close'].iloc[i] >= df_graf['close'].iloc[i-1]
                         else '#FF4646' for i in range(1, len(df_graf))]
            colors_vol.insert(0, '#00FF88')
            fig.add_trace(go.Bar(x=df_graf.index, y=df_graf['volume'],
                                  marker_color=colors_vol, name="Volumen"), row=3, col=1)
            # MACD
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['macd'],
                                      line=dict(color='cyan', width=2), name="MACD"), row=4, col=1)
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['macd_signal'],
                                      line=dict(color='orange', width=2), name="Señal"), row=4, col=1)

            fig.update_layout(
                height=850,
                template="plotly_dark",
                paper_bgcolor="#0A0C10",
                plot_bgcolor="#0A0C10",
                font_color="#E0E0E0",
                hovermode="x unified",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

            # Métricas
            st.subheader("🔍 Detalles Clave")
            ult = mejor['df'].iloc[-1]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Precio", f"{ult['close']:.5f}")
            with col2:
                st.metric("RSI", f"{ult['rsi']:.2f}")
            with col3:
                st.metric("Volumen Ratio", f"{ult['volume_ratio']:.2f}x")
            with col4:
                st.metric("Volatilidad", f"{ult['volatilidad']:.2f}%")
        else:
            st.warning("Datos insuficientes para gráfico.")

    # Modo replay
    st.markdown("---")
    if st.button("🎮 Modo Replay (Siguiente vela)", use_container_width=True):
        st.session_state.ultima_actualizacion = None
        st.rerun()

if __name__ == "__main__":
    main()
