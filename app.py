"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN COMPLETA
Características:
- 2 activos con vencimiento 5 minutos (arriba)
- 1 activo con vencimiento 1 minuto (abajo)
- Reloj en tiempo real
- Estrategias ajustadas para generar señales visibles
- Alertas para 5 min (1 min antes) y para 1 min ("Opera ahora")
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
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado (se mantiene igual, con pequeños ajustes)
st.markdown("""
<style>
    .stApp {
        background-color: #0A0C10;
        background-image: 
            linear-gradient(rgba(0, 255, 136, 0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 255, 136, 0.02) 1px, transparent 1px);
        background-size: 40px 40px;
        color: #E0E0E0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #00FF88 !important;
        font-weight: 700 !important;
    }
    h1 { border-bottom: 2px solid #00FF88; padding-bottom: 10px; }
    .asset-card {
        background: rgba(18, 22, 30, 0.75);
        backdrop-filter: blur(12px);
        border-radius: 28px;
        padding: 20px;
        box-shadow: 0 25px 45px -15px rgba(0, 255, 136, 0.25);
        border: 1px solid rgba(0, 255, 136, 0.25);
        transition: transform 0.3s;
        height: 100%;
        display: flex;
        flex-direction: column;
    }
    .asset-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 35px 55px -15px #00FF88;
        border-color: #00FF88;
    }
    .asset-name {
        font-size: 20px;
        font-weight: 700;
        color: #FFFFFF;
        display: flex;
        justify-content: space-between;
    }
    .asset-price {
        font-size: 14px;
        color: #AAAAAA;
        margin-bottom: 10px;
    }
    .asset-signal {
        font-size: 16px;
        font-weight: 700;
        padding: 10px;
        border-radius: 30px;
        text-align: center;
        margin: 10px 0;
    }
    .signal-compra {
        background: rgba(0, 255, 136, 0.2);
        color: #00FF88;
        border: 1px solid #00FF88;
    }
    .signal-venta {
        background: rgba(255, 70, 70, 0.2);
        color: #FF4646;
        border: 1px solid #FF4646;
    }
    .signal-neutral {
        background: rgba(255, 255, 255, 0.05);
        color: #AAAAAA;
        border: 1px solid #333;
    }
    .asset-footer {
        font-size: 13px;
        color: #888;
        margin-top: auto;
        padding-top: 10px;
        border-top: 1px solid rgba(255,255,255,0.1);
    }
    .asset-prob {
        font-size: 24px;
        font-weight: 800;
        margin: 5px 0;
    }
    .stButton button {
        background: linear-gradient(135deg, #00FF88, #00CC66);
        color: #0A0C10;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 12px 28px;
        transition: all 0.3s;
        box-shadow: 0 12px 30px -8px #00FF88;
    }
    .stButton button:hover {
        background: linear-gradient(135deg, #00CC66, #00FF88);
        box-shadow: 0 18px 40px -5px #00FF88;
    }
    .reloj {
        font-size: 20px;
        font-weight: 600;
        color: #00FF88;
        text-align: right;
        padding: 10px;
        background: rgba(0,0,0,0.3);
        border-radius: 20px;
        margin-bottom: 10px;
    }
    .badge-1min {
        background: #FFAA00;
        color: black;
        padding: 4px 12px;
        border-radius: 30px;
        font-size: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# === CLASE DE CONEXIÓN (sin cambios) ===
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False

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
            return sorted(activos)[:max_activos]
        except Exception as e:
            st.error(f"Error obteniendo activos: {e}")
            return []

    def obtener_velas(self, activo, intervalo=5, limite=100):
        """
        intervalo: 1 o 5 minutos
        """
        if not self.conectado:
            return None
        try:
            time.sleep(0.15)
            # IQ Option da velas de 1 minuto, así que para 5 min pedimos más y resampleamos
            if intervalo == 5:
                velas = self.api.get_candles(activo, 60, limite * 5, time.time())
            else:
                velas = self.api.get_candles(activo, 60, limite, time.time())
            if not velas:
                return None
            df = pd.DataFrame(velas)
            df['datetime'] = pd.to_datetime(df['from'], unit='s')
            df = df.set_index('datetime')
            df = df.rename(columns={
                'open': 'open',
                'max': 'high',
                'min': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float).sort_index()
            if intervalo == 5:
                df = df.resample('5T').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
            return df
        except Exception as e:
            logging.error(f"Error obteniendo velas de {activo}: {e}")
            return None

# === INDICADORES COMUNES ===
def calcular_indicadores_base(df):
    if df is None or len(df) < 20:
        return None
    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    # Volumen
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # ADX
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    # Bandas de Bollinger
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['close'] * 100
    return df

# === FILTRO DE CONTINUACIÓN (menos estricto) ===
def verificar_continuacion_tendencia(df):
    if df is None or len(df) < 20:
        return False
    ult = df.iloc[-1]
    # Condiciones más suaves para permitir más señales
    cond1 = (ult['adx'] > 20) or (ult['volume_ratio'] > 1.3)
    cond2 = ult['bb_width'] > 0.8  # Ancho de banda mínimo
    return cond1 and cond2

# === ESTRATEGIAS PARA 5 MINUTOS (ajustadas) ===
def estrategia_ruptura_5min(df):
    if not verificar_continuacion_tendencia(df):
        return None, 0
    ult = df.iloc[-1]
    ventana = 10
    max_reciente = df['high'].iloc[-ventana-1:-1].max()
    min_reciente = df['low'].iloc[-ventana-1:-1].min()
    # Ruptura alcista
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.3:
        if ult['adx'] > 20 and ult['adx_pos'] > ult['adx_neg']:
            return 'COMPRA', 80
        else:
            return 'COMPRA', 65
    # Ruptura bajista
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.3:
        if ult['adx'] > 20 and ult['adx_neg'] > ult['adx_pos']:
            return 'VENTA', 80
        else:
            return 'VENTA', 65
    return None, 0

def estrategia_pendiente_ema_5min(df):
    if not verificar_continuacion_tendencia(df):
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if pendiente > 0.005 * ult['close']:
        if ult['volume_ratio'] > 1.3 and ult['adx'] > 20 and ult['adx_pos'] > ult['adx_neg']:
            return 'COMPRA', 75
        elif ult['volume_ratio'] > 1.1:
            return 'COMPRA', 60
    elif pendiente < -0.005 * ult['close']:
        if ult['volume_ratio'] > 1.3 and ult['adx'] > 20 and ult['adx_neg'] > ult['adx_pos']:
            return 'VENTA', 75
        elif ult['volume_ratio'] > 1.1:
            return 'VENTA', 60
    return None, 0

def estrategia_adx_5min(df):
    if not verificar_continuacion_tendencia(df):
        return None, 0
    ult = df.iloc[-1]
    # ADX alto durante al menos 2 velas
    adx_alto = all(df['adx'].iloc[-i] > 20 for i in range(1,3) if len(df) >= i)
    if adx_alto and ult['volume_ratio'] > 1.2:
        pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-3]) / 3
        if pendiente > 0:
            return 'COMPRA', 70
        elif pendiente < 0:
            return 'VENTA', 70
    return None, 0

# === ESTRATEGIAS PARA 1 MINUTO (rápidas) ===
def estrategia_ruptura_1min(df):
    """Ruptura de máximo/mínimo de últimas 5 velas con volumen"""
    if df is None or len(df) < 10:
        return None, 0
    ult = df.iloc[-1]
    ventana = 5
    max_reciente = df['high'].iloc[-ventana-1:-1].max()
    min_reciente = df['low'].iloc[-ventana-1:-1].min()
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.5:
        return 'COMPRA', 75
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.5:
        return 'VENTA', 75
    return None, 0

def estrategia_rsi_rapido_1min(df):
    """RSI extremo con volumen"""
    if df is None or len(df) < 14:
        return None, 0
    ult = df.iloc[-1]
    if ult['rsi'] < 30 and ult['volume_ratio'] > 1.3:
        return 'COMPRA', 70
    elif ult['rsi'] > 70 and ult['volume_ratio'] > 1.3:
        return 'VENTA', 70
    return None, 0

# === ANÁLISIS DE UN ACTIVO PARA 5 MIN ===
def analizar_activo_5min(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores_base(df)
    if df is None:
        return None

    estrategias = [
        ('Ruptura', estrategia_ruptura_5min),
        ('Pendiente EMA', estrategia_pendiente_ema_5min),
        ('ADX', estrategia_adx_5min)
    ]

    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    detalles = []

    for nombre, func in estrategias:
        senal, conf = func(df)
        detalles.append({'nombre': nombre, 'senal': senal if senal else 'NEUTRAL', 'confianza': conf})
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
    # Score ponderado
    score = prob * (1 + ult['volume_ratio']/2) if senal_final else 10

    return {
        'activo': activo,
        'score': score,
        'senal': senal_final,
        'probabilidad': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'detalles': detalles,
        'df': df
    }

# === ANÁLISIS PARA 1 MIN ===
def analizar_activo_1min(activo, connector):
    df = connector.obtener_velas(activo, intervalo=1, limite=100)
    if df is None:
        return None
    # Para 1 min no necesitamos todos los indicadores, solo RSI y volumen
    # Calculamos RSI y volumen ratio
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # También necesitamos máximos/mínimos para ruptura
    if len(df) < 10:
        return None

    # Evaluamos dos estrategias rápidas
    senal1, conf1 = estrategia_ruptura_1min(df)
    senal2, conf2 = estrategia_rsi_rapido_1min(df)

    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    if senal1 == 'COMPRA':
        votos_compra += conf1
        peso_total += conf1
    elif senal1 == 'VENTA':
        votos_venta += conf1
        peso_total += conf1
    if senal2 == 'COMPRA':
        votos_compra += conf2
        peso_total += conf2
    elif senal2 == 'VENTA':
        votos_venta += conf2
        peso_total += conf2

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
    score = prob * (1 + ult['volume_ratio']) if senal_final else 10

    return {
        'activo': activo,
        'score': score,
        'senal': senal_final,
        'probabilidad': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'df': df
    }

# === ESCANEO COMPLETO ===
def escanear_todo(connector, mercado, max_activos=50):
    activos = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos:
        return [], []
    resultados_5min = []
    resultados_1min = []
    progreso = st.progress(0)
    total = len(activos)
    for i, act in enumerate(activos):
        time.sleep(0.1)
        res5 = analizar_activo_5min(act, connector)
        if res5:
            resultados_5min.append(res5)
        res1 = analizar_activo_1min(act, connector)
        if res1:
            resultados_1min.append(res1)
        progreso.progress((i+1)/total)
    progreso.empty()

    # Ordenar por score
    resultados_5min.sort(key=lambda x: x['score'], reverse=True)
    resultados_1min.sort(key=lambda x: x['score'], reverse=True)

    # Tomar top 2 para 5 min y top 1 para 1 min
    top_5min = resultados_5min[:2]
    top_1min = resultados_1min[:1] if resultados_1min else []
    return top_5min, top_1min

# === REGISTRO DE PRECISIÓN (simplificado) ===
class AccuracyTracker:
    def __init__(self):
        self.historial = []

    def registrar(self, nombre_estrategia, senal, resultado):
        self.historial.append({
            'estrategia': nombre_estrategia,
            'senal': senal,
            'acierto': resultado
        })

    def precision_global(self):
        if not self.historial:
            return 0.0
        return np.mean([r['acierto'] for r in self.historial]) * 100

    def total_senales(self):
        return len(self.historial)

# === INTERFAZ PRINCIPAL ===
def main():
    st.title("📈 IQ OPTION PRO SCANNER")
    st.markdown("#### 2 Activos (5 min) + 1 Activo (1 min) | Tiempo real")

    # Reloj en tiempo real
    reloj_placeholder = st.empty()
    def actualizar_reloj():
        ahora = datetime.now(ecuador_tz)
        reloj_placeholder.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Inicializar estado
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'top_5min' not in st.session_state:
        st.session_state.top_5min = []
    if 'top_1min' not in st.session_state:
        st.session_state.top_1min = []
    if 'ultima_actualizacion' not in st.session_state:
        st.session_state.ultima_actualizacion = None
    if 'mercado_actual' not in st.session_state:
        st.session_state.mercado_actual = "otc"
    if 'tracker' not in st.session_state:
        st.session_state.tracker = AccuracyTracker()
    if 'notificaciones_5min' not in st.session_state:
        st.session_state.notificaciones_5min = set()
    if 'notificaciones_1min' not in st.session_state:
        st.session_state.notificaciones_1min = set()

    # Barra lateral
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Acceso a IQ Option")

        if not st.session_state.conectado:
            email = st.text_input("Correo", placeholder="usuario@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            tipo_cuenta = st.selectbox("Tipo", ["PRACTICE", "REAL"])

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
                st.session_state.top_5min = []
                st.session_state.top_1min = []
                st.rerun()

        st.markdown("---")

        if st.session_state.conectado:
            st.markdown("### ⚙️ Configuración")
            mercado = st.radio(
                "Mercado",
                ["🌙 OTC", "📊 Normal"],
                index=0,
                horizontal=True
            )
            mercado_key = "otc" if "OTC" in mercado else "forex"
            st.session_state.mercado_actual = mercado_key

            if st.button("🔍 ANALIZAR TODO", use_container_width=True):
                with st.spinner("Escaneando activos..."):
                    top5, top1 = escanear_todo(
                        st.session_state.connector,
                        mercado_key,
                        max_activos=50
                    )
                    st.session_state.top_5min = top5
                    st.session_state.top_1min = top1
                    st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                    st.session_state.notificaciones_5min = set()
                    st.session_state.notificaciones_1min = set()
                    if top5 or top1:
                        st.success(f"✅ Análisis completado: {len(top5)} activos 5min, {len(top1)} activos 1min")
                    else:
                        st.warning("No se encontraron activos con datos.")
                    st.rerun()

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral.")
        actualizar_reloj()
        return

    # Botón de actualización manual y reloj
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("🔄 ACTUALIZAR TODO", use_container_width=True):
            with st.spinner("Actualizando..."):
                top5, top1 = escanear_todo(
                    st.session_state.connector,
                    st.session_state.mercado_actual,
                    max_activos=50
                )
                st.session_state.top_5min = top5
                st.session_state.top_1min = top1
                st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                st.session_state.notificaciones_5min = set()
                st.session_state.notificaciones_1min = set()
                st.rerun()

    with col3:
        if st.session_state.ultima_actualizacion:
            st.caption(f"Último análisis: {st.session_state.ultima_actualizacion.strftime('%H:%M:%S')}")

    actualizar_reloj()  # Mostrar reloj actualizado
    st.markdown("---")

    # === ACTIVOS DE 5 MINUTOS (arriba) ===
    st.subheader("🔥 TOP 2 ACTIVOS - VENCIMIENTO 5 MINUTOS")

    if not st.session_state.top_5min:
        st.warning("No hay activos de 5 minutos. Presiona 'ANALIZAR TODO'.")
        cols = st.columns(2)
        for i in range(2):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Sin datos</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        cols = st.columns(2)
        ahora = datetime.now(ecuador_tz)
        minutos = ahora.minute
        minuto_base = (minutos // 5) * 5
        tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
        tiempo_salida = tiempo_entrada + timedelta(minutes=5)
        segundos_restantes = (tiempo_entrada - ahora).seconds

        for idx, activo in enumerate(st.session_state.top_5min):
            with cols[idx]:
                color_prob = "#00FF88" if activo['senal'] == 'COMPRA' else "#FF4646" if activo['senal'] == 'VENTA' else "#AAAAAA"
                nombre = activo['activo'].replace("-OTC", "")
                signal_class = f"signal-{activo['senal'].lower()}" if activo['senal'] else "signal-neutral"

                # Notificación 1 min antes
                if activo['senal'] and segundos_restantes <= 60 and segundos_restantes > 0:
                    clave = f"{activo['activo']}_{tiempo_entrada}"
                    if clave not in st.session_state.notificaciones_5min:
                        st.toast(f"📢 **¡ATENCIÓN!** Opera a las {tiempo_entrada.strftime('%H:%M')} – {nombre} – {activo['senal']}", icon="⏰")
                        st.session_state.notificaciones_5min.add(clave)

                st.markdown(f"""
                <div class="asset-card">
                    <div class="asset-name">{nombre} <span>Score: {activo['score']:.0f}</span></div>
                    <div class="asset-price">Precio: {activo['precio']:.5f} | RSI: {activo['rsi']:.1f}</div>
                    <div class="asset-signal {signal_class}">{activo['senal'] if activo['senal'] else 'NEUTRAL'}</div>
                    <div class="asset-prob" style="color: {color_prob};">{activo['probabilidad']}%</div>
                    <div class="asset-footer">
                        ⏰ Entrada: {tiempo_entrada.strftime('%H:%M')} | ⏳ Vence: {tiempo_salida.strftime('%H:%M')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # === ACTIVO DE 1 MINUTO (abajo) ===
    st.subheader("⚡ ACTIVO DESTACADO - VENCIMIENTO 1 MINUTO")

    if not st.session_state.top_1min:
        st.info("No hay activo de 1 minuto en este momento.")
        st.markdown("""
        <div class="asset-card">
            <div class="asset-name">Sin datos</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        activo = st.session_state.top_1min[0]
        ahora = datetime.now(ecuador_tz)
        # Para 1 min, la hora de entrada es el minuto actual (redondeado hacia arriba)
        minutos = ahora.minute
        segundos = ahora.second
        # La próxima vela de 1 minuto empieza en el próximo minuto exacto
        tiempo_entrada = ahora.replace(second=0, microsecond=0) + timedelta(minutes=1)
        tiempo_salida = tiempo_entrada + timedelta(minutes=1)
        # Si faltan menos de 10 segundos, mostramos "Opera ahora"
        if (tiempo_entrada - ahora).seconds <= 10 and activo['senal']:
            mensaje_entrada = "🔥 ¡OPERA AHORA!"
        else:
            mensaje_entrada = f"⏰ Entrada: {tiempo_entrada.strftime('%H:%M:%S')}"

        color_prob = "#00FF88" if activo['senal'] == 'COMPRA' else "#FF4646" if activo['senal'] == 'VENTA' else "#AAAAAA"
        nombre = activo['activo'].replace("-OTC", "")
        signal_class = f"signal-{activo['senal'].lower()}" if activo['senal'] else "signal-neutral"

        # Notificación (solo si es "Opera ahora")
        if activo['senal'] and (tiempo_entrada - ahora).seconds <= 10:
            clave = f"{activo['activo']}_1min_{tiempo_entrada}"
            if clave not in st.session_state.notificaciones_1min:
                st.toast(f"⚡ **¡OPERA AHORA!** {nombre} – {activo['senal']} – Vence a las {tiempo_salida.strftime('%H:%M:%S')}", icon="🚀")
                st.session_state.notificaciones_1min.add(clave)

        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">{nombre} <span class="badge-1min">1 MIN</span></div>
            <div class="asset-price">Precio: {activo['precio']:.5f} | RSI: {activo['rsi']:.1f}</div>
            <div class="asset-signal {signal_class}">{activo['senal'] if activo['senal'] else 'NEUTRAL'}</div>
            <div class="asset-prob" style="color: {color_prob};">{activo['probabilidad']}%</div>
            <div class="asset-footer">
                {mensaje_entrada} | ⏳ Vence: {tiempo_salida.strftime('%H:%M:%S')}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Panel de precisión
    st.markdown("---")
    st.subheader("📊 Precisión Global")
    st.metric("Total de señales registradas", st.session_state.tracker.total_senales())
    st.metric("Precisión global", f"{st.session_state.tracker.precision_global():.1f}%")

    # Botones de simulación (opcional, pero pueden eliminarse en producción)
    with st.expander("🛠️ Simulación de resultados (solo pruebas)"):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Simular acierto"):
                st.session_state.tracker.registrar('Ruptura', 'COMPRA', True)
                st.rerun()
        with col2:
            if st.button("❌ Simular fallo"):
                st.session_state.tracker.registrar('Ruptura', 'COMPRA', False)
                st.rerun()

    # Mostrar detalles de estrategias para el primer activo de 5 min (opcional)
    if st.session_state.top_5min:
        with st.expander("🔍 Ver votos de estrategias (primer activo 5 min)"):
            for det in st.session_state.top_5min[0]['detalles']:
                st.write(f"**{det['nombre']}**: {det['senal']} (confianza {det['confianza']})")

if __name__ == "__main__":
    main()
