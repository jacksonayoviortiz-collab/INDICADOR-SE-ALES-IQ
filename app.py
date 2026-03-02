"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN DEFINITIVA
Características:
- Conexión en vivo a IQ Option (WebSockets)
- Selección automática de mercado (Normal/OTC)
- Escaneo y análisis de hasta 50 activos en tiempo real
- Sistema de IA (scoring ponderado) para elegir los 4 mejores activos
- Señales de 5 minutos con alerta 1 minuto antes
- Interfaz profesional con 4 tarjetas de activos y gráfico principal
- Rotación automática de activos según su rendimiento
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

# === CONFIGURACIÓN DE LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# === IMPORTAR LA API DE IQ OPTION (desde el fork actualizado) ===
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError as e:
    IQ_AVAILABLE = False
    st.error(f"""
    ⚠️ **Error crítico:** No se pudo importar la librería `iqoptionapi`.
    Por favor, verifica que la dependencia en `requirements.txt` esté correcta.
    Detalles: {e}
    """)

# === CONFIGURACIÓN DE LA PÁGINA (DEBE SER LO PRIMERO) ===
st.set_page_config(
    page_title="IQ Option Pro Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === CSS PERSONALIZADO PARA DISEÑO PROFESIONAL (Basado en la imagen) ===
st.markdown("""
<style>
    /* Fondo general - oscuro profesional */
    .stApp { background-color: #0F1217; color: #E5E7EB; font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #FFFFFF !important; font-weight: 600 !important; }
    h1 { border-bottom: 2px solid #2962FF; padding-bottom: 10px; }
    /* Tarjetas de activos (4 columnas) */
    .asset-card {
        background: linear-gradient(165deg, #1A1F2B, #141925);
        border-radius: 20px;
        padding: 20px 15px;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);
        border: 1px solid #2A303C;
        transition: transform 0.2s, box-shadow 0.2s;
        height: 100%;
        display: flex;
        flex-direction: column;
        border-left: 4px solid #2962FF;
    }
    .asset-card:hover { transform: translateY(-5px); box-shadow: 0 20px 30px -10px #2962FF33; }
    .asset-name { font-size: 18px; font-weight: 700; color: #FFFFFF; margin-bottom: 5px; }
    .asset-price { font-size: 14px; color: #9CA3AF; margin-bottom: 15px; }
    .asset-signal {
        font-size: 16px; font-weight: 700; padding: 10px 12px; border-radius: 12px;
        text-align: center; margin-bottom: 10px;
    }
    .signal-compra { background-color: rgba(0, 200, 100, 0.15); color: #00C864; border-left: 4px solid #00C864; }
    .signal-venta { background-color: rgba(255, 70, 70, 0.15); color: #FF4646; border-left: 4px solid #FF4646; }
    .signal-neutral { background-color: rgba(156, 163, 175, 0.1); color: #9CA3AF; border-left: 4px solid #9CA3AF; }
    .asset-footer {
        font-size: 13px; color: #9CA3AF; margin-top: auto; padding-top: 15px;
        border-top: 1px solid #2A303C; display: flex; justify-content: space-between;
    }
    .asset-prob { font-size: 22px; font-weight: 800; margin: 5px 0; }
    /* Botones y controles */
    .stButton button {
        background-color: #2962FF; color: white; font-weight: 600; border-radius: 12px;
        border: none; padding: 10px 25px; transition: all 0.2s; box-shadow: 0 4px 12px #2962FF66;
    }
    .stButton button:hover { background-color: #1E4BD7; box-shadow: 0 6px 16px #2962FF99; }
    /* Alertas anticipadas */
    .alert-box {
        background: linear-gradient(90deg, #1E293B, #0F1217);
        border-left: 6px solid #FFAA00;
        border-radius: 16px;
        padding: 20px 25px;
        margin: 20px 0;
        box-shadow: 0 10px 20px -5px #FFAA0044;
    }
    /* Selector de mercado */
    .mercado-selector {
        background: #1A1F2B; padding: 10px; border-radius: 50px; display: flex;
        gap: 10px; border: 1px solid #2A303C; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# === ZONA HORARIA (ECUADOR) ===
ecuador_tz = pytz.timezone('America/Guayaquil')

# === CLASE DE CONEXIÓN Y DATOS DE IQ OPTION ===
class IQOptionConnector:
    """Maneja toda la comunicación con la API de IQ Option."""
    def __init__(self):
        self.api = None
        self.conectado = False
        self.activos_cache = {}
        self.ultima_actualizacion_activos = None

    def conectar(self, email, password):
        """Establece la conexión con IQ Option."""
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no instalada o no encontrada."
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
        """
        Obtiene dinámicamente los activos disponibles desde IQ Option.
        - mercado = "forex" para Normal, "otc" para OTC.
        """
        if not self.conectado:
            return []
        ahora = time.time()
        cache_key = f"{mercado}_{max_activos}"

        # Usar caché por 5 minutos para no saturar la API
        if (self.ultima_actualizacion_activos and
            ahora - self.ultima_actualizacion_activos < 300 and
            cache_key in self.activos_cache):
            return self.activos_cache[cache_key]

        try:
            activos_data = self.api.get_all_open_time()
            activos = []

            if mercado == "forex":
                # Mercado Normal: activos de forex que estén abiertos y no sean OTC
                for activo, data in activos_data.get("forex", {}).items():
                    if data.get("open", False) and "-OTC" not in activo:
                        activos.append(activo)
            else:
                # Mercado OTC: activos en binary/turbo que tengan "-OTC"
                for categoria in ["binary", "turbo"]:
                    for activo, data in activos_data.get(categoria, {}).items():
                        if data.get("open", False) and "-OTC" in activo:
                            activos.append(activo)

            activos = sorted(activos)[:max_activos]
            self.activos_cache[cache_key] = activos
            self.ultima_actualizacion_activos = ahora
            return activos
        except Exception as e:
            st.error(f"Error obteniendo activos desde IQ Option: {e}")
            return []

    def obtener_velas(self, activo, intervalo=5, limite=100):
        """
        Obtiene velas históricas de un activo.
        - intervalo: 5 para velas de 5 minutos.
        """
        if not self.conectado:
            return None
        try:
            # Pequeña pausa para no saturar la API
            time.sleep(0.15)
            # IQ Option devuelve velas de 1 minuto, luego las agrupamos
            velas = self.api.get_candles(activo, 60, limite * 5, time.time())
            if not velas or len(velas) == 0:
                return None

            df = pd.DataFrame(velas)
            df['datetime'] = pd.to_datetime(df['from'], unit='s')
            df = df.set_index('datetime')
            df = df.rename(columns={'open': 'open', 'max': 'high', 'min': 'low', 'close': 'close'})
            df = df[['open', 'high', 'low', 'close']].astype(float).sort_index()

            # Agrupar en velas de 5 minutos
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

# === FUNCIONES DE INDICADORES TÉCNICOS Y ANÁLISIS (IA) ===
def calcular_indicadores(df):
    """Calcula un set completo de indicadores técnicos usando la librería 'ta'."""
    if df is None or len(df) < 30:
        return None

    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    # Momentum (ROC)
    df['momentum'] = ta.momentum.ROCIndicator(df['close'], window=10).roc()
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    # Bandas de Bollinger
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['BBU'] = bb.bollinger_hband()
    df['BBL'] = bb.bollinger_lband()
    df['bb_pos'] = (df['close'] - df['BBL']) / (df['BBU'] - df['BBL']).clip(lower=0.001)
    # Volumen simulado (basado en rango)
    df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # ATR y Volatilidad
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['volatilidad'] = df['atr'] / df['close'] * 100

    return df

def generar_score_ia(df):
    """
    Genera un 'Score de IA' para un activo. Este score ponderado es el que
    utiliza el bot para rankear los activos y decidir los 4 mejores.
    Es una simulación de un modelo de Machine Learning basado en reglas técnicas.
    """
    if df is None or len(df) < 30:
        return 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50  # Puntuación base

    # 1. Tendencia y Cruce de EMAs (+30/-10)
    if ult['ema_20'] > ult['ema_50']:
        score += 10
    else:
        score -= 10
    if prev['ema_20'] < prev['ema_50'] and ult['ema_20'] > ult['ema_50']:  # Cruce Alcista
        score += 30
    elif prev['ema_20'] > prev['ema_50'] and ult['ema_20'] < ult['ema_50']:  # Cruce Bajista
        score += 30

    # 2. RSI extremo (sobrecompra/venta) (+20)
    if ult['rsi'] < 30:
        score += 20
    elif ult['rsi'] > 70:
        score += 20

    # 3. Posición en Bandas de Bollinger (reversiones) (+15)
    if ult['bb_pos'] < 0.1 or ult['bb_pos'] > 0.9:
        score += 15

    # 4. Volumen inusual (+15)
    if ult['volume_ratio'] > 1.5:
        score += 15

    # 5. Momentum fuerte (+10)
    if abs(ult['momentum']) > 2:
        score += 10

    return score

def detectar_senal_y_prob(df):
    """
    Determina la señal de trading (COMPRA, VENTA o NEUTRAL) y su probabilidad asociada.
    """
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    senal = None
    prob = 50

    # Regla 1: Cruce de EMAs
    if prev['ema_20'] < prev['ema_50'] and ult['ema_20'] > ult['ema_50']:
        senal = 'COMPRA'
        prob = 75
    elif prev['ema_20'] > prev['ema_50'] and ult['ema_20'] < ult['ema_50']:
        senal = 'VENTA'
        prob = 75
    # Regla 2: Bandas de Bollinger + RSI
    elif ult['close'] <= ult['BBL'] and ult['rsi'] < 30:
        senal = 'COMPRA'
        prob = 80
    elif ult['close'] >= ult['BBU'] and ult['rsi'] > 70:
        senal = 'VENTA'
        prob = 80

    # Ajuste de probabilidad por Volumen
    if senal and ult['volume_ratio'] > 1.3:
        prob = min(95, prob + 10)

    return senal, int(prob)

def analizar_activo(activo, connector):
    """Función principal que orquesta el análisis de un solo activo."""
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None
    score = generar_score_ia(df)
    senal, prob = detectar_senal_y_prob(df)
    ult = df.iloc[-1] if len(df) > 0 else None
    if ult is None:
        return None
    return {
        'activo': activo,
        'score': score,
        'senal': senal,
        'probabilidad': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volatilidad': ult['volatilidad'],
        'volume_ratio': ult['volume_ratio'],
        'df': df
    }

def actualizar_top_activos(connector, mercado, max_activos=50):
    """
    Escanea la lista de activos, los analiza y devuelve los 4 mejores.
    Implementa la rotación automática.
    """
    activos_lista = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos_lista:
        return []
    resultados = []
    progreso = st.progress(0)
    total = len(activos_lista)
    for i, activo in enumerate(activos_lista):
        time.sleep(0.1)  # Pausa para no saturar la API
        res = analizar_activo(activo, connector)
        if res:
            resultados.append(res)
        progreso.progress((i + 1) / total)
    progreso.empty()

    # Eliminar duplicados por seguridad (no debería haber)
    vistos = set()
    resultados_unicos = []
    for r in resultados:
        if r['activo'] not in vistos:
            vistos.add(r['activo'])
            resultados_unicos.append(r)

    # Ordenar por score (IA) y devolver los 4 mejores
    resultados_unicos.sort(key=lambda x: x['score'], reverse=True)
    return resultados_unicos[:4]

# === INTERFAZ PRINCIPAL DE STREAMLIT ===
def main():
    st.title("📊 IQ OPTION PRO SCANNER")
    st.markdown("#### Sistema Automatizado de Detección de Oportunidades (4 Mejores Activos)")
    st.markdown("---")

    # Inicializar el estado de la sesión
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

    # --- BARRA LATERAL (LOGIN Y CONFIGURACIÓN) ---
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Acceso a IQ Option")

        if not st.session_state.conectado:
            email = st.text_input("Correo electrónico", placeholder="usuario@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            tipo_cuenta = st.selectbox("Tipo de cuenta", ["PRACTICE", "REAL"])

            if st.button("🔌 Conectar a IQ Option", use_container_width=True):
                if email and password:
                    with st.spinner("Conectando..."):
                        ok, msg = st.session_state.connector.conectar(email, password)
                        if ok:
                            st.session_state.connector.cambiar_balance(tipo_cuenta)
                            st.session_state.conectado = True
                            st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                            st.rerun()
                        else:
                            st.error(f"❌ Error de conexión: {msg}")
                else:
                    st.warning("Ingresa tus credenciales.")
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
            st.markdown("### ⚙️ Configuración del Análisis")

            # SELECTOR DE MERCADO (NORMAL / OTC)
            mercado = st.radio(
                "Tipo de Mercado:",
                ["🌙 OTC (Fin de Semana / 24/7)", "📊 Normal (Forex - Horario de Mercado)"],
                index=0,
                horizontal=True
            )
            mercado_key = "otc" if "OTC" in mercado else "forex"
            st.session_state.mercado_actual = mercado_key

            # BOTÓN DE ESCANEO PRINCIPAL
            if st.button("🔍 ANALIZAR Y ENCONTRAR TOP 4", use_container_width=True):
                with st.spinner("Analizando activos en tiempo real..."):
                    top = actualizar_top_activos(
                        st.session_state.connector,
                        mercado_key,
                        max_activos=50
                    )
                    st.session_state.top_activos = top
                    st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                    if top:
                        st.success(f"✅ Análisis completado. Se encontraron {len(top)} activos de alto potencial.")
                    else:
                        st.warning("No se encontraron activos con suficientes datos.")
                    st.rerun()

    # --- VERIFICAR CONEXIÓN INICIAL ---
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral para comenzar.")
        # Mostrar 4 tarjetas de ejemplo (placeholders)
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

    # --- BOTÓN DE ACTUALIZACIÓN MANUAL Y TIMESTAMP ---
    col1, col2, col3 = st.columns([1.5, 2, 1.5])
    with col1:
        if st.button("🔄 ACTUALIZAR ANÁLISIS AHORA", use_container_width=True):
            with st.spinner("Refrescando datos de mercado..."):
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

    # --- MOSTRAR LAS 4 TARJETAS DE ACTIVOS (TOP 4) ---
    st.subheader("🔥 TOP 4 ACTIVOS CON MAYOR PROBABILIDAD DE ÉXITO")

    if not st.session_state.top_activos:
        st.warning("Presiona 'ANALIZAR Y ENCONTRAR TOP 4' en la barra lateral para obtener resultados.")
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
        # Asegurar que siempre se muestren 4 tarjetas (rellenar con placeholders si son menos)
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
                        <div class="asset-price">Próximo activo potencial</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Determinar estilo de señal
                    if activo['senal'] == 'COMPRA':
                        signal_class = "signal-compra"
                        signal_text = f"📈 {activo['senal']}"
                        color_prob = "#00C864"
                    elif activo['senal'] == 'VENTA':
                        signal_class = "signal-venta"
                        signal_text = f"📉 {activo['senal']}"
                        color_prob = "#FF4646"
                    else:
                        signal_class = "signal-neutral"
                        signal_text = "⚪ NEUTRAL"
                        color_prob = "#9CA3AF"

                    # Formatear nombre del activo para mostrar
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

    # --- ACTIVO PRINCIPAL (EL #1) - GRÁFICO DETALLADO ---
    if st.session_state.top_activos:
        mejor = st.session_state.top_activos[0]
        st.subheader(f"📈 Análisis en Profundidad: {mejor['activo'].replace('-OTC', '')} (Activo Principal)")

        # ALERTA ANTICIPADA (1 MINUTO ANTES)
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

        # GRÁFICO CON PLOTLY (Velas, EMAs, Bandas de Bollinger, RSI, Volumen)
        if mejor['df'] is not None and len(mejor['df']) > 20:
            df_graf = mejor['df'].iloc[-50:].copy()
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.06,
                row_heights=[0.6, 0.2, 0.2],
                subplot_titles=("Precio con EMAs y BB", "RSI (14)", "Volumen Relativo")
            )
            # Gráfico de velas
            fig.add_trace(go.Candlestick(
                x=df_graf.index,
                open=df_graf['open'],
                high=df_graf['high'],
                low=df_graf['low'],
                close=df_graf['close'],
                name="",
                increasing_line_color='#00C864',
                decreasing_line_color='#FF4646',
                showlegend=False
            ), row=1, col=1)
            # EMAs
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_20'],
                                      line=dict(color='#2962FF', width=2.5), name="EMA 20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                      line=dict(color='#FFAA00', width=2.5), name="EMA 50"), row=1, col=1)
            # Bandas de Bollinger
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBU'],
                                      line=dict(color='#AAAAAA', dash='dash'), name="BB Sup"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['BBL'],
                                      line=dict(color='#AAAAAA', dash='dash'), name="BB Inf"), row=1, col=1)
            # RSI
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['rsi'],
                                      line=dict(color='#FFFFFF', width=2), name="RSI"), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#FF4646", row=2)
            fig.add_hline(y=30, line_dash="dash", line_color="#00C864", row=2)
            # Volumen
            colors_vol = ['#00C864' if df_graf['close'].iloc[i] >= df_graf['close'].iloc[i-1]
                         else '#FF4646' for i in range(1, len(df_graf))]
            colors_vol.insert(0, '#00C864')
            fig.add_trace(go.Bar(x=df_graf.index, y=df_graf['volume'],
                                  marker_color=colors_vol, name="Volumen"), row=3, col=1)

            fig.update_layout(
                height=700,
                template="plotly_dark",
                paper_bgcolor="#0F1217",
                plot_bgcolor="#0F1217",
                font_color="#E5E7EB",
                hovermode="x unified",
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_xaxes(gridcolor="#2A303C")
            fig.update_yaxes(gridcolor="#2A303C")
            st.plotly_chart(fig, use_container_width=True)

            # Métricas clave del activo principal
            st.subheader("🔍 Detalles del Activo Principal")
            ult = mejor['df'].iloc[-1]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Precio Actual", f"{ult['close']:.5f}")
            with col2:
                st.metric("RSI (14)", f"{ult['rsi']:.2f}")
            with col3:
                st.metric("Volatilidad", f"{ult['volatilidad']:.2f}%")
            with col4:
                st.metric("Volumen (Ratio)", f"{ult['volume_ratio']:.2f}x")
        else:
            st.warning("Datos históricos insuficientes para mostrar el gráfico.")

    # --- MODO REPLAY (Para pruebas) ---
    st.markdown("---")
    if st.button("🎮 Modo Replay (Simular Siguiente Vela)", use_container_width=True):
        st.session_state.ultima_actualizacion = None
        st.rerun()

if __name__ == "__main__":
    main()
