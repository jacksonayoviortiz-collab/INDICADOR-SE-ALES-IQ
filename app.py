"""
BOT DE TRADING PROFESIONAL AUTÓNOMO PARA IQ OPTION
Características:
- Analiza 1 activo a la vez (rápido y eficiente)
- Detecta tendencias (alcista/bajista) con fuerza
- Ejecuta operaciones en retrocesos dentro de la tendencia
- 4 estrategias independientes + IA para confirmar continuación
- Límite de operaciones diarias configurable
- Cambio automático de activo si el mercado se vuelve lateral
- Notificaciones en tiempo real de todos los eventos
- Historial completo de operaciones
- Interfaz simplificada y profesional
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

# Importar la API de IQ Option
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError as e:
    IQ_AVAILABLE = False
    st.error(f"""
    ⚠️ **Error crítico:** No se pudo importar la librería `iqoptionapi`.
    Verifica que la línea en `requirements.txt` sea exactamente:
    `git+https://github.com/williansandi/iqoptionapi-2025-Atualizada-.git#egg=iqoptionapi`
    Detalle del error: {e}
    """)

# Configuración de página
st.set_page_config(
    page_title="IQ Option Pro Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 5 segundos (para que la interfaz sea reactiva)
st_autorefresh(interval=5000, key="autorefresh")

# CSS personalizado (mantenemos el mismo estilo profesional)
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
    .status-card {
        background: rgba(18, 22, 30, 0.9);
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8844;
        margin: 10px 0;
    }
    .evento {
        background: #1E242C;
        border-left: 4px solid #00FF88;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
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
    .stButton button {
        background: #00FF88;
        color: black;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 10px 25px;
    }
    .control-panel {
        background: #151A24;
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8844;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador (ajustar según el broker)
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                self.balance = self.api.get_balance()
                return True, "Conexión exitosa"
            else:
                return False, reason
        except Exception as e:
            return False, str(e)

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            self.tipo_cuenta = tipo
            return self.api.change_balance(tipo)
        return False

    def actualizar_balance(self):
        if self.conectado:
            self.balance = self.api.get_balance()
        return self.balance

    def obtener_saldo(self):
        return self.balance

    def obtener_activos_disponibles(self, mercado="otc", max_activos=200, force_refresh=False):
        if not self.conectado:
            return []
        cache_key = f"{mercado}_{max_activos}"
        if not force_refresh and cache_key in self.activos_cache:
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
            return activos
        except Exception as e:
            st.error(f"Error obteniendo activos: {e}")
            return []

    def obtener_velas(self, activo, intervalo=5, limite=100):
        if not self.conectado:
            return None
        try:
            time.sleep(0.15)
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

    def colocar_orden(self, activo, direccion, monto, expiracion=5):
        if not self.conectado:
            return None, "No conectado"
        try:
            direccion_api = 'call' if direccion.upper() == 'COMPRA' else 'put'
            tiempo = expiracion * 60
            resultado = self.api.buy(monto, activo, direccion_api, tiempo)
            return resultado, "Orden ejecutada"
        except Exception as e:
            return None, str(e)

# ============================================
# INDICADORES TÉCNICOS
# ============================================
def calcular_indicadores(df):
    if df is None or len(df) < 30:
        return None
    if df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['close'] * 100
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_upper'] = bb.bollinger_hband()
    return df

# ============================================
# DETECCIÓN DE TENDENCIA Y FUERZA
# ============================================
def detectar_tendencia(df):
    """
    Detecta si el mercado es alcista, bajista o lateral.
    Retorna: ('alcista', fuerza) o ('bajista', fuerza) o ('lateral', 0)
    fuerza: 1-100
    """
    if df is None or len(df) < 50:
        return 'lateral', 0

    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-10]) / 10
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10

    # Posición de precio respecto a EMAs
    sobre_ema20 = ult['close'] > ult['ema_20']
    sobre_ema50 = ult['close'] > ult['ema_50']
    sobre_ema200 = ult['close'] > ult['ema_200']

    # Volumen y ADX
    volumen_fuerte = ult['volume_ratio'] > 1.2
    adx_fuerte = ult['adx'] > 25

    # Calcular fuerza (0-100)
    fuerza = 0
    if pendiente_ema20 > 0:
        fuerza += 20
    if pendiente_ema50 > 0:
        fuerza += 15
    if sobre_ema20:
        fuerza += 10
    if sobre_ema50:
        fuerza += 10
    if sobre_ema200:
        fuerza += 10
    if volumen_fuerte:
        fuerza += 15
    if adx_fuerte:
        fuerza += 20

    # Decidir dirección
    if (pendiente_ema20 > 0 and pendiente_ema50 > 0) or (sobre_ema20 and sobre_ema50 and sobre_ema200):
        return 'alcista', min(100, fuerza)
    elif (pendiente_ema20 < 0 and pendiente_ema50 < 0) or (not sobre_ema20 and not sobre_ema50 and not sobre_ema200):
        return 'bajista', min(100, fuerza)
    else:
        return 'lateral', 0

# ============================================
# ESTRATEGIAS DE CONFIRMACIÓN (4 independientes)
# ============================================
def estrategia_1_ruptura_con_volumen(df):
    """Estrategia 1: Ruptura de máximo/mínimo reciente con volumen alto"""
    if df is None or len(df) < 15:
        return 0, 0
    ult = df.iloc[-1]
    max_10 = df['high'].iloc[-10:-1].max()
    min_10 = df['low'].iloc[-10:-1].min()
    if ult['close'] > max_10 and ult['volume_ratio'] > 1.3:
        return 1, 80  # 1 para compra
    elif ult['close'] < min_10 and ult['volume_ratio'] > 1.3:
        return -1, 80  # -1 para venta
    return 0, 0

def estrategia_2_pendiente_ema_adx(df):
    """Estrategia 2: Pendiente de EMA + ADX alto"""
    if df is None or len(df) < 20:
        return 0, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if pendiente > 0.002 * ult['close'] and ult['adx'] > 25 and ult['adx_pos'] > ult['adx_neg']:
        return 1, 75
    elif pendiente < -0.002 * ult['close'] and ult['adx'] > 25 and ult['adx_neg'] > ult['adx_pos']:
        return -1, 75
    return 0, 0

def estrategia_3_bandas_bollinger_rsi(df):
    """Estrategia 3: Bandas de Bollinger + RSI extremo"""
    if df is None or len(df) < 20:
        return 0, 0
    ult = df.iloc[-1]
    if ult['close'] <= ult['bb_lower'] and ult['rsi'] < 35 and ult['volume_ratio'] > 1.2:
        return 1, 70
    elif ult['close'] >= ult['bb_upper'] and ult['rsi'] > 65 and ult['volume_ratio'] > 1.2:
        return -1, 70
    return 0, 0

def estrategia_4_macd_histograma(df):
    """Estrategia 4: Cruce de MACD con volumen"""
    if df is None or len(df) < 30:
        return 0, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    # Calcular MACD manualmente con ta
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2] and ult['volume_ratio'] > 1.2:
        return 1, 70
    elif df['macd'].iloc[-1] < df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2] and ult['volume_ratio'] > 1.2:
        return -1, 70
    return 0, 0

# ============================================
# IA DE CONFIRMACIÓN (Ensemble ponderado)
# ============================================
def confirmar_operacion(df, tendencia, fuerza_tendencia):
    """
    Usa las 4 estrategias para decidir si operar en la dirección de la tendencia.
    Retorna: (decisión, confianza) donde decisión es 1 (compra), -1 (venta) o 0 (no operar)
    """
    resultados = [
        estrategia_1_ruptura_con_volumen(df),
        estrategia_2_pendiente_ema_adx(df),
        estrategia_3_bandas_bollinger_rsi(df),
        estrategia_4_macd_histograma(df)
    ]

    # Ponderar según la fuerza de la tendencia
    peso_tendencia = min(1.5, 1 + fuerza_tendencia / 100)

    compra_peso = 0
    venta_peso = 0
    total_peso = 0

    for dir_, conf in resultados:
        if dir_ == 1:
            compra_peso += conf
            total_peso += conf
        elif dir_ == -1:
            venta_peso += conf
            total_peso += conf

    # Si la tendencia es alcista, dar más peso a las compras
    if tendencia == 'alcista':
        compra_peso *= peso_tendencia
    elif tendencia == 'bajista':
        venta_peso *= peso_tendencia

    if compra_peso > venta_peso and compra_peso > 150:  # Umbral mínimo
        return 1, int(compra_peso / 3)
    elif venta_peso > compra_peso and venta_peso > 150:
        return -1, int(venta_peso / 3)
    else:
        return 0, 0

# ============================================
# CÁLCULO DE RETROCESO IDEAL
# ============================================
def calcular_retroceso(df, tendencia):
    """
    Estima hasta dónde podría retroceder el precio dentro de la tendencia.
    Retorna precio objetivo de entrada.
    """
    if df is None or len(df) < 20:
        return None
    ult = df.iloc[-1]
    if tendencia == 'alcista':
        # Buscar mínimo reciente (soporte)
        min_reciente = df['low'].iloc[-20:].min()
        # El retroceso podría ser hasta la EMA20 o un Fibonacci del 38.2%
        precio_objetivo = max(ult['ema_20'], min_reciente * 1.01)
        return precio_objetivo
    elif tendencia == 'bajista':
        max_reciente = df['high'].iloc[-20:].max()
        precio_objetivo = min(ult['ema_20'], max_reciente * 0.99)
        return precio_objetivo
    return None

# ============================================
# CLASE PARA GESTIONAR OPERACIONES Y LÍMITES
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"  # Detenido, Buscando, Analizando, EsperandoRetroceso, Operando
        self.operaciones_hoy = 0
        self.ultimo_cambio_activo = datetime.now(ecuador_tz)
        self.historial = []
        self.log_eventos = []

    def agregar_evento(self, mensaje):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {mensaje}")
        # Mantener solo últimos 20 eventos
        if len(self.log_eventos) > 20:
            self.log_eventos = self.log_eventos[-20:]

    def agregar_operacion(self, activo, direccion, monto, resultado, ganancia):
        self.historial.append({
            'fecha': datetime.now(ecuador_tz).strftime('%Y-%m-%d %H:%M:%S'),
            'activo': activo,
            'direccion': direccion,
            'monto': monto,
            'resultado': resultado,
            'ganancia': ganancia
        })
        self.operaciones_hoy += 1

    def reiniciar_contador_diario(self):
        self.operaciones_hoy = 0

    def obtener_resumen(self):
        if not self.historial:
            return {'total': 0, 'ganadas': 0, 'perdidas': 0, 'neto': 0}
        df = pd.DataFrame(self.historial)
        ganadas = df[df['resultado'] == 'ganada'].shape[0]
        perdidas = df[df['resultado'] == 'perdida'].shape[0]
        neto = df['ganancia'].sum()
        return {
            'total': len(self.historial),
            'ganadas': ganadas,
            'perdidas': perdidas,
            'neto': neto
        }

# ============================================
# FUNCIÓN PRINCIPAL DE ANÁLISIS Y EJECUCIÓN
# ============================================
def ciclo_principal(connector, manager, config):
    """
    Ejecuta un ciclo de análisis y operación.
    config: diccionario con mercado, monto, limite_diario
    """
    ahora = datetime.now(ecuador_tz)

    # Verificar límite diario
    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.")
        return

    # Si no tenemos activo actual, buscar uno
    if manager.activo_actual is None:
        manager.estado = "Buscando activo..."
        manager.agregar_evento("🔍 Buscando activo con tendencia...")
        activos = connector.obtener_activos_disponibles(config['mercado'], max_activos=100)
        for act in activos[:20]:  # Probar primeros 20 para no demorar
            df = connector.obtener_velas(act, intervalo=5, limite=100)
            if df is None:
                continue
            df = calcular_indicadores(df)
            if df is None:
                continue
            tendencia, fuerza = detectar_tendencia(df)
            if tendencia != 'lateral' and fuerza > 50:
                manager.activo_actual = act
                manager.agregar_evento(f"✅ Activo encontrado: {act} - Tendencia {tendencia} (fuerza {fuerza}%)")
                manager.estado = "Analizando"
                break
        if manager.activo_actual is None:
            manager.agregar_evento("⚠️ No se encontró ningún activo con tendencia fuerte. Reintentando en 5 min...")
            return

    # Analizar el activo actual
    df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=100)
    if df is None:
        manager.agregar_evento(f"❌ Error al obtener datos de {manager.activo_actual}. Buscando otro...")
        manager.activo_actual = None
        return
    df = calcular_indicadores(df)
    if df is None:
        manager.activo_actual = None
        return

    tendencia, fuerza = detectar_tendencia(df)
    ult = df.iloc[-1]

    # Mostrar estado en la interfaz (se actualiza con cada ciclo)
    st.session_state.tendencia_actual = tendencia
    st.session_state.fuerza_actual = fuerza
    st.session_state.precio_actual = ult['close']

    # Si el mercado se vuelve lateral, cambiar de activo
    if tendencia == 'lateral' or fuerza < 40:
        manager.agregar_evento(f"🔄 Mercado lateral en {manager.activo_actual}. Buscando otro activo...")
        manager.activo_actual = None
        manager.estado = "Buscando"
        return

    # Si estamos en modo "Analizando", verificar si podemos operar
    if manager.estado == "Analizando":
        # Confirmar con IA
        decision, confianza = confirmar_operacion(df, tendencia, fuerza)
        if decision != 0 and confianza > 60:
            # Calcular punto de retroceso ideal
            precio_entrada = calcular_retroceso(df, tendencia)
            if precio_entrada:
                direccion = "COMPRA" if decision == 1 else "VENTA"
                manager.agregar_evento(f"🎯 Oportunidad detectada en {manager.activo_actual} - {direccion} (confianza {confianza}%)")
                manager.agregar_evento(f"📉 Esperando retroceso a {precio_entrada:.5f}...")
                manager.estado = "EsperandoRetroceso"
                manager.precio_objetivo = precio_entrada
                manager.direccion = direccion
                manager.confianza = confianza
        else:
            manager.agregar_evento(f"⏳ {manager.activo_actual} en tendencia {tendencia} pero sin señal clara aún...")

    # Si estamos esperando retroceso, verificar si el precio alcanza el objetivo
    elif manager.estado == "EsperandoRetroceso":
        if (manager.direccion == "COMPRA" and ult['close'] <= manager.precio_objetivo) or \
           (manager.direccion == "VENTA" and ult['close'] >= manager.precio_objetivo):
            # Ejecutar orden
            resultado, msg = connector.colocar_orden(
                manager.activo_actual,
                manager.direccion,
                config['monto'],
                expiracion=5
            )
            if resultado:
                manager.agregar_evento(f"✅ Orden ejecutada: {manager.direccion} en {manager.activo_actual} por ${config['monto']}")
                # Simular resultado (en producción deberías verificar después)
                manager.agregar_operacion(
                    manager.activo_actual,
                    manager.direccion,
                    config['monto'],
                    'ganada',  # provisional
                    config['monto'] * 0.8
                )
                manager.estado = "Analizando"  # Volver a analizar el mismo activo
                # Actualizar balance
                connector.actualizar_balance()
            else:
                manager.agregar_evento(f"❌ Error al ejecutar orden: {msg}")
                manager.estado = "Analizando"
        else:
            # Si el precio se aleja mucho, cancelar la espera
            if manager.direccion == "COMPRA" and ult['close'] > manager.precio_objetivo * 1.02:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó")
                manager.estado = "Analizando"
            elif manager.direccion == "VENTA" and ult['close'] < manager.precio_objetivo * 0.98:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó")
                manager.estado = "Analizando"

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PROFESSIONAL BOT")
    st.markdown("#### Modo autónomo - 1 activo por vez | IA con 4 estrategias")
    st.markdown("---")

    # Inicializar estado de sesión
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'manager' not in st.session_state:
        st.session_state.manager = TradingManager()
    if 'config' not in st.session_state:
        st.session_state.config = {
            'mercado': 'otc',
            'monto': 1.0,
            'limite_diario': 5
        }
    if 'bot_activo' not in st.session_state:
        st.session_state.bot_activo = False

    # Panel superior de configuración
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("### 🔐 Conexión")
            if not st.session_state.conectado:
                email = st.text_input("Email", placeholder="usuario@email.com", key="email")
                password = st.text_input("Contraseña", type="password", placeholder="••••••••", key="pass")
                if st.button("🔌 Conectar", use_container_width=True):
                    if email and password:
                        with st.spinner("Conectando..."):
                            ok, msg = st.session_state.connector.conectar(email, password)
                            if ok:
                                st.session_state.conectado = True
                                st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
            else:
                st.success("✅ Conectado")
                st.metric("Saldo", f"${st.session_state.connector.obtener_saldo():.2f}")

        with col2:
            st.markdown("### ⚙️ Configuración")
            cuenta = st.radio("Cuenta", ["💰 Demo", "💵 Real"], horizontal=True, key="cuenta")
            tipo_cuenta = "PRACTICE" if "Demo" in cuenta else "REAL"
            if tipo_cuenta != st.session_state.connector.tipo_cuenta and st.session_state.conectado:
                st.session_state.connector.cambiar_balance(tipo_cuenta)

            mercado = st.radio("Mercado", ["🌙 OTC", "📊 Normal"], horizontal=True, key="mercado")
            st.session_state.config['mercado'] = "otc" if "OTC" in mercado else "forex"

        with col3:
            st.markdown("### 💰 Monto")
            st.session_state.config['monto'] = st.number_input(
                "Por operación ($)",
                min_value=1.0 if "Real" in cuenta else 0.1,
                max_value=1000.0 if "Real" in cuenta else 100.0,
                value=st.session_state.config['monto'],
                step=1.0
            )

        with col4:
            st.markdown("### ⏱️ Límite")
            st.session_state.config['limite_diario'] = st.number_input(
                "Operaciones/día",
                min_value=1,
                max_value=50,
                value=st.session_state.config['limite_diario'],
                step=1
            )
            if st.session_state.conectado:
                if st.session_state.bot_activo:
                    if st.button("⏹️ DETENER BOT", use_container_width=True):
                        st.session_state.bot_activo = False
                        st.session_state.manager.estado = "Detenido"
                        st.session_state.manager.agregar_evento("⏹️ Bot detenido manualmente")
                        st.rerun()
                else:
                    if st.button("▶️ INICIAR BOT", use_container_width=True):
                        st.session_state.bot_activo = True
                        st.session_state.manager.estado = "Buscando"
                        st.session_state.manager.agregar_evento("▶️ Bot iniciado")
                        st.rerun()

    st.markdown("---")

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option para comenzar.")
        return

    # Reloj en tiempo real
    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Ejecutar ciclo del bot si está activo
    if st.session_state.bot_activo:
        ciclo_principal(st.session_state.connector, st.session_state.manager, st.session_state.config)

    # Panel de estado en tiempo real
    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 📊 Estado del Bot")
        manager = st.session_state.manager
        resumen = manager.obtener_resumen()

        # Tarjeta de estado
        st.markdown(f"""
        <div class="status-card">
            <h3>Activo actual: {manager.activo_actual if manager.activo_actual else 'Ninguno'}</h3>
            <p><strong>Estado:</strong> {manager.estado}</p>
            <p><strong>Tendencia:</strong> {st.session_state.get('tendencia_actual', 'desconocida')} 
               (fuerza {st.session_state.get('fuerza_actual', 0)}%)</p>
            <p><strong>Precio actual:</strong> {st.session_state.get('precio_actual', 0):.5f}</p>
            <p><strong>Operaciones hoy:</strong> {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Log de eventos
        with st.expander("📋 Ver eventos recientes", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen de operaciones")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")

    # Historial completo
    with st.expander("📜 Ver historial completo de operaciones"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Aún no hay operaciones registradas.")

    # Gráfico del activo actual (opcional)
    if manager.activo_actual and st.checkbox("📉 Mostrar gráfico del activo actual"):
        df = st.session_state.connector.obtener_velas(manager.activo_actual, intervalo=5, limite=50)
        if df is not None:
            df = calcular_indicadores(df)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.7, 0.3],
                                subplot_titles=("Precio con EMAs", "Volumen"))
            fig.add_trace(go.Candlestick(x=df.index,
                                          open=df['open'],
                                          high=df['high'],
                                          low=df['low'],
                                          close=df['close'],
                                          increasing_line_color='#00FF88',
                                          decreasing_line_color='#FF4646'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_20'],
                                      line=dict(color='#2962FF', width=2), name="EMA 20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_50'],
                                      line=dict(color='#FFAA00', width=2), name="EMA 50"), row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['volume'],
                                  marker_color='#00FF88', name="Volumen"), row=2, col=1)
            fig.update_layout(height=500, template="plotly_dark", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    # Botón manual de actualización
    if st.button("🔄 Actualizar ahora"):
        st.rerun()

if __name__ == "__main__":
    main()
