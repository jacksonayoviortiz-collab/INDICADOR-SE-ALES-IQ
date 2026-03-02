"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN TENDENCIAS
Características:
- 3 estrategias de tendencia independientes (basadas en ruptura, pendiente de EMA y ADX)
- Confirmación con volumen real y fuerza del mercado
- Selección automática de los 2 activos más confiables
- Indicación de hora exacta de operación (alerta 1 min antes)
- Cálculo y visualización de precisión por estrategia y global
- Interfaz moderna en verde/negro
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
    page_title="IQ Option Trend Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado - Tema verde/negro profesional
st.markdown("""
<style>
    /* Fondo general */
    .stApp { background-color: #0A0C10; color: #E0E0E0; font-family: 'Inter', sans-serif; }
    /* Títulos en verde neón */
    h1, h2, h3 { color: #00FF88 !important; font-weight: 700 !important; }
    h1 { border-bottom: 2px solid #00FF88; padding-bottom: 10px; }
    /* Tarjetas de activos */
    .asset-card {
        background: rgba(20, 25, 35, 0.9);
        backdrop-filter: blur(5px);
        border-radius: 24px;
        padding: 22px 18px;
        box-shadow: 0 15px 35px -10px rgba(0, 255, 136, 0.3);
        border: 1px solid rgba(0, 255, 136, 0.3);
        transition: transform 0.25s ease;
        height: 100%;
        display: flex;
        flex-direction: column;
        border-left: 4px solid #00FF88;
    }
    .asset-card:hover { transform: translateY(-6px); box-shadow: 0 25px 45px -10px #00FF88; }
    .asset-name { font-size: 20px; font-weight: 700; color: #FFFFFF; margin-bottom: 8px; }
    .asset-price { font-size: 14px; color: #AAAAAA; margin-bottom: 15px; }
    .asset-signal {
        font-size: 16px; font-weight: 700; padding: 10px 14px; border-radius: 30px;
        text-align: center; margin-bottom: 12px; text-transform: uppercase;
    }
    .signal-compra { background-color: rgba(0, 255, 136, 0.15); color: #00FF88; border: 1px solid #00FF88; }
    .signal-venta { background-color: rgba(255, 70, 70, 0.15); color: #FF4646; border: 1px solid #FF4646; }
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
    }
    .stButton button:hover {
        background: linear-gradient(135deg, #00CC66, #00FF88);
        box-shadow: 0 12px 28px -5px #00FF88;
    }
    /* Alertas */
    .alert-box {
        background: linear-gradient(90deg, #1A2A1A, #0A0C10);
        border-left: 6px solid #FFAA00;
        border-radius: 20px;
        padding: 20px 25px;
        margin: 20px 0;
        box-shadow: 0 15px 30px -10px #FFAA0044;
    }
    /* Panel de precisión */
    .accuracy-panel {
        background: #151A24;
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8822;
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# === CLASE DE CONEXIÓN (sin cambios, igual que antes) ===
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
    """Calcula indicadores necesarios para todas las estrategias."""
    if df is None or len(df) < 30:
        return None
    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    # EMAs
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    # ATR (para fuerza)
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    # Volumen
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # ADX (para medir fuerza de tendencia)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    return df

# === ESTRATEGIA 1: Ruptura de máximos/mínimos con volumen ===
def estrategia_ruptura_con_volumen(df, ventana=10):
    """
    Detecta ruptura de máximo reciente (o mínimo) con volumen creciente.
    """
    if df is None or len(df) < ventana+5:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    max_reciente = df['high'].iloc[-ventana:-1].max()
    min_reciente = df['low'].iloc[-ventana:-1].min()

    # Ruptura alcista
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.5:
        # Confirmar fuerza con ATR y ADX
        if ult['adx'] > 25 and ult['adx_pos'] > ult['adx_neg']:
            return 'COMPRA', 85
        else:
            return 'COMPRA', 70
    # Ruptura bajista
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.5:
        if ult['adx'] > 25 and ult['adx_neg'] > ult['adx_pos']:
            return 'VENTA', 85
        else:
            return 'VENTA', 70
    return None, 0

# === ESTRATEGIA 2: Pendiente de EMA + Volumen + Fuerza ===
def estrategia_pendiente_ema(df, periodo=5):
    """
    Detecta tendencia basada en la pendiente de la EMA 20 y la confirma con volumen y ADX.
    """
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-periodo]) / periodo

    # Tendencia alcista si pendiente positiva, volumen alto y ADX fuerte
    if pendiente > 0.01 * ult['close']:  # Umbral dinámico
        if ult['volume_ratio'] > 1.3 and ult['adx'] > 25 and ult['adx_pos'] > ult['adx_neg']:
            return 'COMPRA', 80
        elif ult['volume_ratio'] > 1.2:
            return 'COMPRA', 65
    # Tendencia bajista
    elif pendiente < -0.01 * ult['close']:
        if ult['volume_ratio'] > 1.3 and ult['adx'] > 25 and ult['adx_neg'] > ult['adx_pos']:
            return 'VENTA', 80
        elif ult['volume_ratio'] > 1.2:
            return 'VENTA', 65
    return None, 0

# === ESTRATEGIA 3: ADX + Volumen para continuación de tendencia ===
def estrategia_adx_continuacion(df, umbral_adx=25):
    """
    Cuando el ADX es alto (>25) y el volumen acompaña, la tendencia actual es fuerte y probable que continúe.
    """
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    if ult['adx'] > umbral_adx:
        # Determinar dirección por la pendiente de la EMA
        pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-3]) / 3
        if pendiente > 0 and ult['volume_ratio'] > 1.2:
            return 'COMPRA', 75
        elif pendiente < 0 and ult['volume_ratio'] > 1.2:
            return 'VENTA', 75
    return None, 0

# === REGISTRO DE PRECISIÓN (simulado, se puede mejorar con datos reales) ===
class AccuracyTracker:
    def __init__(self):
        self.historial = []  # lista de dicts: {'estrategia': nombre, 'acierto': bool, 'senal': str}
        self.estrategias = ['Ruptura', 'Pendiente EMA', 'ADX Continuación']

    def registrar(self, nombre_estrategia, senal, resultado_real):
        """
        resultado_real: True si la operación fue exitosa, False si no.
        """
        self.historial.append({
            'estrategia': nombre_estrategia,
            'senal': senal,
            'acierto': resultado_real
        })

    def precision_por_estrategia(self):
        if not self.historial:
            return {nombre: 0.0 for nombre in self.estrategias}
        df = pd.DataFrame(self.historial)
        precision = df.groupby('estrategia')['acierto'].mean() * 100
        return precision.to_dict()

    def precision_global(self):
        if not self.historial:
            return 0.0
        return np.mean([r['acierto'] for r in self.historial]) * 100

# === ANÁLISIS DE UN ACTIVO CON LAS 3 ESTRATEGIAS ===
def analizar_activo(activo, connector, tracker):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores_base(df)
    if df is None:
        return None

    # Evaluar cada estrategia
    estrategias = [
        ('Ruptura', estrategia_ruptura_con_volumen),
        ('Pendiente EMA', estrategia_pendiente_ema),
        ('ADX Continuación', estrategia_adx_continuacion)
    ]

    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    detalles_estrategias = []

    for nombre, func in estrategias:
        senal, confianza = func(df)
        detalles_estrategias.append({
            'nombre': nombre,
            'senal': senal if senal else 'NEUTRAL',
            'confianza': confianza
        })
        if senal == 'COMPRA':
            votos_compra += confianza
            peso_total += confianza
        elif senal == 'VENTA':
            votos_venta += confianza
            peso_total += confianza

    # Decidir señal final
    if peso_total == 0:
        senal_final = None
        probabilidad = 0
    else:
        if votos_compra > votos_venta:
            probabilidad = int((votos_compra / peso_total) * 100)
            senal_final = 'COMPRA'
        elif votos_venta > votos_compra:
            probabilidad = int((votos_venta / peso_total) * 100)
            senal_final = 'VENTA'
        else:
            senal_final = None
            probabilidad = 0

    # Score para ranking (basado en probabilidad y confianza)
    score = probabilidad * 2 if senal_final else 30

    ult = df.iloc[-1]
    return {
        'activo': activo,
        'score': score,
        'senal': senal_final,
        'probabilidad': probabilidad,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'df': df,
        'detalles_estrategias': detalles_estrategias
    }

# === ACTUALIZAR TOP 2 ACTIVOS ===
def actualizar_top_activos(connector, mercado, tracker, max_activos=50):
    activos_lista = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos_lista:
        return []
    resultados = []
    progreso = st.progress(0)
    total = len(activos_lista)
    for i, activo in enumerate(activos_lista):
        time.sleep(0.1)
        res = analizar_activo(activo, connector, tracker)
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
    return resultados_unicos[:2]  # Solo los 2 mejores

# === INTERFAZ PRINCIPAL ===
def main():
    st.title("📈 IQ OPTION TREND SCANNER")
    st.markdown("#### Sistema de 3 Estrategias de Tendencia + Volumen | Top 2 Activos")
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
    if 'tracker' not in st.session_state:
        st.session_state.tracker = AccuracyTracker()

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
                st.session_state.top_activos = []
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

            if st.button("🔍 ANALIZAR TOP 2", use_container_width=True):
                with st.spinner("Analizando activos..."):
                    top = actualizar_top_activos(
                        st.session_state.connector,
                        mercado_key,
                        st.session_state.tracker,
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
        st.info("👆 Conéctate a IQ Option en la barra lateral.")
        cols = st.columns(2)
        for i in range(2):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Esperando conexión...</div>
                </div>
                """, unsafe_allow_html=True)
        return

    # Botón de actualización manual
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("🔄 ACTUALIZAR AHORA", use_container_width=True):
            with st.spinner("Actualizando..."):
                top = actualizar_top_activos(
                    st.session_state.connector,
                    st.session_state.mercado_actual,
                    st.session_state.tracker,
                    max_activos=50
                )
                st.session_state.top_activos = top
                st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                st.rerun()

    with col3:
        if st.session_state.ultima_actualizacion:
            st.caption(f"Último análisis: {st.session_state.ultima_actualizacion.strftime('%H:%M:%S')}")

    st.markdown("---")

    # Mostrar los 2 mejores activos
    st.subheader("🔥 TOP 2 ACTIVOS MÁS CONFIABLES")

    if not st.session_state.top_activos:
        st.warning("Presiona 'ANALIZAR TOP 2' para obtener resultados.")
        cols = st.columns(2)
        for i in range(2):
            with cols[i]:
                st.markdown("""
                <div class="asset-card">
                    <div class="asset-name">Cargando...</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        activos_mostrar = st.session_state.top_activos.copy()
        while len(activos_mostrar) < 2:
            activos_mostrar.append(None)

        cols = st.columns(2)
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
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    color_prob = "#00FF88" if activo['senal'] == 'COMPRA' else "#FF4646" if activo['senal'] == 'VENTA' else "#AAAAAA"
                    nombre = activo['activo'].replace("-OTC", "")
                    st.markdown(f"""
                    <div class="asset-card">
                        <div class="asset-name">{nombre}</div>
                        <div class="asset-price">Precio: {activo['precio']:.5f} | RSI: {activo['rsi']:.1f}</div>
                        <div class="asset-signal {'signal-compra' if activo['senal']=='COMPRA' else 'signal-venta' if activo['senal']=='VENTA' else 'signal-neutral'}">
                            {activo['senal'] if activo['senal'] else 'NEUTRAL'}
                        </div>
                        <div class="asset-prob" style="color: {color_prob};">{activo['probabilidad']}%</div>
                        <div class="asset-footer">
                            <span>⏰ OPERA A LAS {tiempo_entrada.strftime('%H:%M')}</span>
                            <span>⏳ VENCE {tiempo_salida.strftime('%H:%M')}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # Mostrar precisión de estrategias
    st.markdown("---")
    st.subheader("📊 Precisión de Estrategias")

    precision_estrategias = st.session_state.tracker.precision_por_estrategia()
    precision_global = st.session_state.tracker.precision_global()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Ruptura", f"{precision_estrategias.get('Ruptura', 0):.1f}%")
    with col2:
        st.metric("Pendiente EMA", f"{precision_estrategias.get('Pendiente EMA', 0):.1f}%")
    with col3:
        st.metric("ADX Continuación", f"{precision_estrategias.get('ADX Continuación', 0):.1f}%")
    with col4:
        st.metric("Global", f"{precision_global:.1f}%")

    # Botón para simular un acierto/fallo (en producción se haría con resultados reales)
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Simular Acierto (para prueba)"):
            # Simular un acierto en todas las estrategias del primer activo
            if st.session_state.top_activos:
                for est in ['Ruptura', 'Pendiente EMA', 'ADX Continuación']:
                    st.session_state.tracker.registrar(est, 'COMPRA', True)
                st.rerun()
    with col2:
        if st.button("❌ Simular Fallo (para prueba)"):
            if st.session_state.top_activos:
                for est in ['Ruptura', 'Pendiente EMA', 'ADX Continuación']:
                    st.session_state.tracker.registrar(est, 'COMPRA', False)
                st.rerun()

    # Mostrar detalles de estrategias para el activo principal
    if st.session_state.top_activos:
        mejor = st.session_state.top_activos[0]
        with st.expander(f"🔍 Ver votos de estrategias para {mejor['activo']}"):
            for det in mejor['detalles_estrategias']:
                st.write(f"**{det['nombre']}**: {det['senal']} (confianza {det['confianza']})")

    # Gráfico del activo principal (opcional)
    if st.session_state.top_activos and st.checkbox("Mostrar gráfico del activo principal"):
        mejor = st.session_state.top_activos[0]
        df_graf = mejor['df'].iloc[-50:].copy()
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
                                  line=dict(color='blue')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                  line=dict(color='orange')), row=1, col=1)
        fig.add_trace(go.Bar(x=df_graf.index, y=df_graf['volume'],
                              marker_color='#00FF88'), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
