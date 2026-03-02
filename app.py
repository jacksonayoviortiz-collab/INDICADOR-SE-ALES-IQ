"""
BOT DE TRADING PROFESIONAL AUTÓNOMO PARA IQ OPTION - VERSIÓN CON ESTRATEGIAS INDEPENDIENTES
- Cada estrategia opera por sí sola, con acceso a fuerza y volumen.
- Análisis de múltiples activos en secuencia.
- Registro de operaciones con resultados reales.
- Interfaz profesional con señales claras.
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

# Autorefresh cada 5 segundos
st_autorefresh(interval=5000, key="autorefresh")

# CSS personalizado
st.markdown("""
<style>
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css');
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
        backdrop-filter: blur(10px);
    }
    .evento {
        background: #1E242C;
        border-left: 4px solid #00FF88;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        font-size: 14px;
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
        transition: all 0.3s;
    }
    .stButton button:hover {
        background: #00CC66;
        transform: scale(1.05);
        box-shadow: 0 0 15px #00FF88;
    }
    .metric-card {
        background: #151A24;
        border-radius: 15px;
        padding: 15px;
        border: 1px solid #00FF8844;
    }
    .icono-estado {
        font-size: 24px;
        margin-right: 10px;
    }
    .signal-badge {
        font-size: 18px;
        font-weight: 700;
        padding: 5px 10px;
        border-radius: 20px;
        display: inline-block;
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
    .signal-neutro {
        background: rgba(255, 255, 255, 0.1);
        color: #AAAAAA;
        border: 1px solid #AAAAAA;
    }
    .signal-ejecutada {
        background: rgba(255, 215, 0, 0.2);
        color: gold;
        border: 1px solid gold;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION (MEJORADA)
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}
        self.ordenes_pendientes = {}
        self.max_reintentos = 3
        self.timeout = 30

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        for intento in range(1, self.max_reintentos + 1):
            try:
                self.api = IQ_Option(email, password)
                check, reason = self.api.connect()
                if check:
                    self.conectado = True
                    self.balance = self.api.get_balance()
                    return True, f"Conexión exitosa en intento {intento}"
                else:
                    if "authentication" in reason.lower() or "credenciales" in reason.lower():
                        return False, f"Error de autenticación: {reason}"
                    if intento < self.max_reintentos:
                        time.sleep(2)
                        continue
                    else:
                        return False, f"Error tras {intento} intentos: {reason}"
            except Exception as e:
                error_msg = str(e)
                if intento < self.max_reintentos:
                    time.sleep(2)
                else:
                    return False, f"Excepción en conexión: {error_msg}"
        return False, "No se pudo conectar después de reintentos"

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            try:
                self.api.change_balance(tipo)
                self.tipo_cuenta = tipo
                time.sleep(1)
                self.balance = self.api.get_balance()
                return True
            except Exception as e:
                logging.error(f"Error al cambiar balance: {e}")
                return False
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
            if resultado and len(resultado) > 0:
                id_orden = resultado[0] if isinstance(resultado, list) else resultado
                self.ordenes_pendientes[id_orden] = {
                    'activo': activo,
                    'direccion': direccion,
                    'monto': monto,
                    'timestamp': time.time()
                }
                return id_orden, "Orden ejecutada"
            else:
                return None, "Error al ejecutar orden"
        except Exception as e:
            return None, str(e)

    def verificar_orden(self, id_orden):
        """Consulta el resultado de una orden por su ID (debes adaptarlo según tu API)."""
        try:
            # Ejemplo: self.api.get_optioninfo(id_orden)
            # Retorna un dict con 'win' booleano y 'amount'
            return None  # Implementar según la API
        except Exception as e:
            logging.error(f"Error verificando orden {id_orden}: {e}")
            return None

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
    df['psar'] = ta.trend.PSARIndicator(df['high'], df['low'], df['close']).psar()
    return df

# ============================================
# DETECCIÓN DE TENDENCIA PRINCIPAL
# ============================================
def detectar_tendencia_principal(df):
    """Determina la dirección de la tendencia principal y su fuerza."""
    if df is None or len(df) < 50:
        return 'lateral', 0
    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-10]) / 10
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10
    sobre_ema20 = ult['close'] > ult['ema_20']
    sobre_ema50 = ult['close'] > ult['ema_50']
    sobre_ema200 = ult['close'] > ult['ema_200']
    
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
    if ult['volume_ratio'] > 1.2:
        fuerza += 15
    if ult['adx'] > 25:
        fuerza += 20

    if (pendiente_ema20 > 0 and pendiente_ema50 > 0) or (sobre_ema20 and sobre_ema50 and sobre_ema200):
        return 'alcista', min(100, fuerza)
    elif (pendiente_ema20 < 0 and pendiente_ema50 < 0) or (not sobre_ema20 and not sobre_ema50 and not sobre_ema200):
        return 'bajista', min(100, fuerza)
    else:
        return 'lateral', 0

# ============================================
# ESTRATEGIAS INDEPENDIENTES
# ============================================
def estrategia_1_ruptura_con_volumen(df, tendencia_principal):
    """Estrategia 1: Ruptura de máximo/mínimo reciente con volumen"""
    if df is None or len(df) < 15:
        return None, 0
    ult = df.iloc[-1]
    max_10 = df['high'].iloc[-10:-1].max()
    min_10 = df['low'].iloc[-10:-1].min()
    if tendencia_principal == 'alcista' and ult['close'] > max_10 and ult['volume_ratio'] > 1.1:
        return 'COMPRA', 75
    elif tendencia_principal == 'bajista' and ult['close'] < min_10 and ult['volume_ratio'] > 1.1:
        return 'VENTA', 75
    return None, 0

def estrategia_2_pendiente_ema_adx(df, tendencia_principal):
    """Estrategia 2: Pendiente de EMA + ADX"""
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if tendencia_principal == 'alcista' and pendiente > 0.0015 * ult['close'] and ult['adx'] > 20:
        return 'COMPRA', 70
    elif tendencia_principal == 'bajista' and pendiente < -0.0015 * ult['close'] and ult['adx'] > 20:
        return 'VENTA', 70
    return None, 0

def estrategia_3_bandas_bollinger_rsi(df, tendencia_principal):
    """Estrategia 3: Bandas de Bollinger + RSI"""
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    if tendencia_principal == 'alcista' and ult['close'] <= ult['bb_lower'] and ult['rsi'] < 45 and ult['volume_ratio'] > 1.0:
        return 'COMPRA', 65
    elif tendencia_principal == 'bajista' and ult['close'] >= ult['bb_upper'] and ult['rsi'] > 55 and ult['volume_ratio'] > 1.0:
        return 'VENTA', 65
    return None, 0

def estrategia_4_macd_histograma(df, tendencia_principal):
    """Estrategia 4: Cruce de MACD"""
    if df is None or len(df) < 30:
        return None, 0
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    ult = df.iloc[-1]
    if tendencia_principal == 'alcista' and ult['macd'] > ult['macd_signal'] and df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2] and ult['volume_ratio'] > 1.0:
        return 'COMPRA', 68
    elif tendencia_principal == 'bajista' and ult['macd'] < ult['macd_signal'] and df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2] and ult['volume_ratio'] > 1.0:
        return 'VENTA', 68
    return None, 0

def estrategia_5_parabolic_sar_volumen(df, tendencia_principal):
    """Estrategia 5: Parabolic SAR + Volumen"""
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    if tendencia_principal == 'alcista' and prev['psar'] > prev['close'] and ult['psar'] < ult['close'] and ult['volume_ratio'] > 1.1:
        return 'COMPRA', 72
    elif tendencia_principal == 'bajista' and prev['psar'] < prev['close'] and ult['psar'] > ult['close'] and ult['volume_ratio'] > 1.1:
        return 'VENTA', 72
    return None, 0

# ============================================
# CÁLCULO DE RETROCESO
# ============================================
def calcular_retroceso(df, tendencia):
    """Calcula un punto de retroceso razonable dentro de la tendencia."""
    if df is None or len(df) < 20:
        return None
    ult = df.iloc[-1]
    if tendencia == 'alcista':
        # Buscar un soporte cercano o la EMA20
        soporte_cercano = df['low'].iloc[-10:].min()
        precio_objetivo = max(ult['ema_20'], soporte_cercano * 1.002)
        return precio_objetivo
    elif tendencia == 'bajista':
        resistencia_cercana = df['high'].iloc[-10:].max()
        precio_objetivo = min(ult['ema_20'], resistencia_cercana * 0.998)
        return precio_objetivo
    return None

# ============================================
# CLASE PARA GESTIONAR OPERACIONES Y LÍMITES
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.ultimo_cambio_activo = datetime.now(ecuador_tz)
        self.historial = []
        self.log_eventos = []
        self.ordenes_pendientes = {}
        self.indice_activo = 0  # para iterar sobre la lista

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
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
        self.agregar_evento(f"Operación {resultado.upper()}: {direccion} en {activo} - ${ganancia:.2f}", "💰" if resultado=='ganada' else "💸")

    def actualizar_resultados(self, connector):
        for id_orden, info in list(self.ordenes_pendientes.items()):
            if time.time() - info['timestamp'] > 300:
                resultado = connector.verificar_orden(id_orden)
                if resultado:
                    if resultado.get('win'):
                        ganancia = info['monto'] * 0.8
                        self.agregar_operacion(info['activo'], info['direccion'], info['monto'], 'ganada', ganancia)
                    else:
                        perdida = -info['monto']
                        self.agregar_operacion(info['activo'], info['direccion'], info['monto'], 'perdida', perdida)
                    del self.ordenes_pendientes[id_orden]

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
# CICLO PRINCIPAL (ACTIVO POR ACTIVO)
# ============================================
def ciclo_principal(connector, manager, config):
    ahora = datetime.now(ecuador_tz)
    tiempo_actual = time.time()

    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.", "⛔")
        return

    manager.actualizar_resultados(connector)

    # Obtener lista de activos si no la tenemos
    if 'lista_activos' not in st.session_state:
        st.session_state.lista_activos = connector.obtener_activos_disponibles(config['mercado'], max_activos=100)
        manager.indice_activo = 0

    # Si no hay activos, esperar
    if not st.session_state.lista_activos:
        manager.agregar_evento("⚠️ No hay activos disponibles. Reintentando en 5 min...", "⚠️")
        return

    # Cambiar de activo si no tenemos uno actual o si llevamos más de 5 minutos sin señal
    if manager.activo_actual is None:
        manager.activo_actual = st.session_state.lista_activos[manager.indice_activo % len(st.session_state.lista_activos)]
        manager.estado = "Analizando"
        manager.agregar_evento(f"🔍 Analizando activo: {manager.activo_actual}", "🔍")
    else:
        # Si llevamos más de 5 minutos sin señal, pasar al siguiente
        if tiempo_actual - manager.ultimo_cambio_activo > 300:
            manager.indice_activo += 1
            manager.activo_actual = st.session_state.lista_activos[manager.indice_activo % len(st.session_state.lista_activos)]
            manager.ultimo_cambio_activo = tiempo_actual
            manager.agregar_evento(f"⏭️ Cambiando a siguiente activo: {manager.activo_actual}", "⏭️")
            manager.estado = "Analizando"

    # Obtener datos del activo actual
    df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=100)
    if df is None:
        manager.agregar_evento(f"❌ Error al obtener datos de {manager.activo_actual}. Pasando al siguiente...", "❌")
        manager.indice_activo += 1
        manager.activo_actual = None
        return
    df = calcular_indicadores(df)
    if df is None:
        manager.indice_activo += 1
        manager.activo_actual = None
        return

    # Detectar tendencia principal
    tendencia_principal, fuerza = detectar_tendencia_principal(df)
    ult = df.iloc[-1]

    # Guardar en session_state para la interfaz
    st.session_state.tendencia_actual = tendencia_principal
    st.session_state.fuerza_actual = fuerza
    st.session_state.precio_actual = ult['close']
    st.session_state.volumen_actual = ult['volume_ratio']
    st.session_state.volumen_tipo = "COMPRA" if ult['close'] > ult['open'] else "VENTA"
    st.session_state.activo_actual = manager.activo_actual

    # Si la tendencia es lateral, pasar al siguiente
    if tendencia_principal == 'lateral' or fuerza < 20:
        manager.agregar_evento(f"🔄 {manager.activo_actual} en lateral o fuerza baja ({fuerza}%). Pasando al siguiente...", "🔄")
        manager.indice_activo += 1
        manager.activo_actual = None
        return

    # Evaluar cada estrategia independientemente
    estrategias = [
        (estrategia_1_ruptura_con_volumen, "Ruptura+Vol"),
        (estrategia_2_pendiente_ema_adx, "Pendiente+ADX"),
        (estrategia_3_bandas_bollinger_rsi, "BB+RSI"),
        (estrategia_4_macd_histograma, "MACD"),
        (estrategia_5_parabolic_sar_volumen, "Parabolic")
    ]

    mejor_senal = None
    mejor_confianza = 0
    for estrategia, nombre in estrategias:
        senal, confianza = estrategia(df, tendencia_principal)
        if senal and confianza > mejor_confianza:
            mejor_senal = senal
            mejor_confianza = confianza
            mejor_nombre = nombre

    if mejor_senal:
        # Calcular punto de retroceso
        precio_objetivo = calcular_retroceso(df, tendencia_principal)
        if precio_objetivo:
            manager.agregar_evento(f"🎯 Señal {mejor_senal} detectada por {mejor_nombre} (confianza {mejor_confianza}%)", "🎯")
            manager.agregar_evento(f"📉 Esperando retroceso a {precio_objetivo:.5f}...", "📉")
            manager.estado = "EsperandoRetroceso"
            manager.precio_objetivo = precio_objetivo
            manager.direccion = mejor_senal
            manager.confianza = mejor_confianza
            st.session_state.senal_actual = mejor_senal
        else:
            st.session_state.senal_actual = "NEUTRO"
    else:
        st.session_state.senal_actual = "NEUTRO"
        manager.agregar_evento(f"⏳ {manager.activo_actual} sin señales de estrategias...", "⏳")

    # Estado de espera de retroceso
    if manager.estado == "EsperandoRetroceso":
        if (manager.direccion == "COMPRA" and ult['close'] <= manager.precio_objetivo) or \
           (manager.direccion == "VENTA" and ult['close'] >= manager.precio_objetivo):
            id_orden, msg = connector.colocar_orden(
                manager.activo_actual,
                manager.direccion,
                config['monto'],
                expiracion=5
            )
            if id_orden:
                manager.agregar_evento(f"✅ Orden ejecutada: {manager.direccion} en {manager.activo_actual} por ${config['monto']} (ID: {id_orden})", "✅")
                manager.ordenes_pendientes[id_orden] = {
                    'activo': manager.activo_actual,
                    'direccion': manager.direccion,
                    'monto': config['monto'],
                    'timestamp': time.time()
                }
                manager.estado = "Analizando"
                manager.ultimo_cambio_activo = tiempo_actual  # reset para no cambiar de activo tras operar
                connector.actualizar_balance()
                st.session_state.senal_actual = "EJECUTADA"
            else:
                manager.agregar_evento(f"❌ Error al ejecutar orden: {msg}", "❌")
                manager.estado = "Analizando"
        else:
            # Si el precio se aleja demasiado, cancelar espera
            if manager.direccion == "COMPRA" and ult['close'] > manager.precio_objetivo * 1.01:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó", "⏹️")
                manager.estado = "Analizando"
            elif manager.direccion == "VENTA" and ult['close'] < manager.precio_objetivo * 0.99:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó", "⏹️")
                manager.estado = "Analizando"

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PROFESSIONAL BOT")
    st.markdown("#### Modo autónomo | Estrategias independientes | Múltiples activos")
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
    if 'tendencia_actual' not in st.session_state:
        st.session_state.tendencia_actual = 'desconocida'
        st.session_state.fuerza_actual = 0
        st.session_state.precio_actual = 0
        st.session_state.volumen_actual = 0
        st.session_state.volumen_tipo = 'N/A'
        st.session_state.senal_actual = 'NEUTRO'
        st.session_state.activo_actual = 'Ninguno'

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
                with st.spinner("Cambiando cuenta..."):
                    exito = st.session_state.connector.cambiar_balance(tipo_cuenta)
                    if exito:
                        st.success(f"Cuenta cambiada a {tipo_cuenta}")
                    else:
                        st.error("Error al cambiar cuenta")
                st.rerun()

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
                        st.session_state.manager.agregar_evento("⏹️ Bot detenido manualmente", "⏹️")
                        st.rerun()
                else:
                    if st.button("▶️ INICIAR BOT", use_container_width=True):
                        st.session_state.bot_activo = True
                        st.session_state.manager.estado = "Buscando"
                        st.session_state.manager.agregar_evento("▶️ Bot iniciado", "▶️")
                        st.rerun()

    st.markdown("---")

    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option para comenzar.")
        return

    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    if st.session_state.bot_activo:
        ciclo_principal(st.session_state.connector, st.session_state.manager, st.session_state.config)

    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📊 Estado del Bot")
        manager = st.session_state.manager
        resumen = manager.obtener_resumen()

        icono_estado = {
            "Detenido": "⏹️",
            "Buscando": "🔍",
            "Analizando": "📊",
            "EsperandoRetroceso": "⏳",
            "Límite alcanzado": "⛔"
        }.get(manager.estado, "🤖")

        if st.session_state.senal_actual == 'COMPRA':
            signal_class = 'signal-compra'
            signal_text = 'COMPRA'
        elif st.session_state.senal_actual == 'VENTA':
            signal_class = 'signal-venta'
            signal_text = 'VENTA'
        elif st.session_state.senal_actual == 'EJECUTADA':
            signal_class = 'signal-ejecutada'
            signal_text = 'EJECUTADA'
        else:
            signal_class = 'signal-neutro'
            signal_text = 'NEUTRO'

        st.markdown(f"""
        <div class="status-card">
            <h3><span class="icono-estado">{icono_estado}</span> {manager.estado}</h3>
            <p><strong>Activo actual:</strong> {st.session_state.activo_actual}</p>
            <p><strong>Tendencia:</strong> {st.session_state.tendencia_actual} - Fuerza {st.session_state.fuerza_actual}%</p>
            <p><strong>Precio actual:</strong> {st.session_state.precio_actual:.5f}</p>
            <p><strong>Volumen:</strong> {st.session_state.volumen_actual:.2f}x ({st.session_state.volumen_tipo})</p>
            <p><strong>Señal:</strong> <span class="signal-badge {signal_class}">{signal_text}</span></p>
            <p><strong>Operaciones hoy:</strong> {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.bot_activo and manager.estado not in ["Detenido", "Límite alcanzado"]:
            st.progress(0.5, text="Analizando mercado...")

        with st.expander("📋 Ver eventos recientes", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen de operaciones")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")

    if manager.activo_actual:
        st.markdown("### 📉 Gráfico en tiempo real")
        df = st.session_state.connector.obtener_velas(manager.activo_actual, intervalo=5, limite=50)
        if df is not None:
            df = calcular_indicadores(df)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.7, 0.3],
                                subplot_titles=(f"{manager.activo_actual}", "Volumen"))
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
            fig.update_layout(height=500, template="plotly_dark", showlegend=False,
                              paper_bgcolor="#0A0C10", plot_bgcolor="#0A0C10")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding:50px; background:#151A24; border-radius:20px;">
            <i class="fas fa-chart-line" style="font-size:60px; color:#00FF88;"></i>
            <h3 style="color:#00FF88;">Esperando activo...</h3>
            <p>El bot está buscando el mejor activo para operar.</p>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📜 Ver historial completo de operaciones"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Aún no hay operaciones registradas.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
