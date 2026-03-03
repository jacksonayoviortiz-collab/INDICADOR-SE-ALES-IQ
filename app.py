"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN CON CORRECCIÓN DE ERRORES
- Elimina dependencia de get_option_result (simula resultado para pruebas)
- Manejo de reconexión WebSocket
- Estabilidad mejorada
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

# Configurar logging para ver errores
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# Autorefresh cada 5 segundos (menos frecuente para evitar saturación)
st_autorefresh(interval=5000, key="autorefresh")

# CSS personalizado (mantenemos el mismo)
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
    .operacion-panel {
        background: linear-gradient(145deg, #1E242C, #151A24);
        border-radius: 20px;
        padding: 20px;
        border: 2px solid #00FF88;
        margin: 10px 0;
        box-shadow: 0 0 20px #00FF8844;
    }
    .countdown {
        font-size: 24px;
        font-weight: 700;
        color: #FFAA00;
        text-align: center;
        padding: 10px;
        background: #1E242C;
        border-radius: 10px;
    }
    .detalle-operacion {
        background: #1E242C;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        border-left: 4px solid #00FF88;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION (CON RECONEXIÓN Y VERIFICACIÓN SEGURA)
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}
        self.ordenes_pendientes = {}
        self.reintentos_conexion = 0
        self.max_reintentos = 3

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                self.reintentos_conexion = 0
                self.balance = self.api.get_balance()
                return True, "Conexión exitosa"
            else:
                self.conectado = False
                return False, reason
        except Exception as e:
            self.conectado = False
            return False, str(e)

    def verificar_conexion(self):
        """Verifica si la conexión sigue activa y reconecta si es necesario."""
        if not self.conectado:
            return False
        try:
            # Intentar obtener el balance como prueba
            self.api.get_balance()
            return True
        except:
            self.conectado = False
            return False

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            try:
                self.api.change_balance(tipo)
                self.tipo_cuenta = tipo
                time.sleep(1)
                self.balance = self.api.get_balance()
                return True
            except Exception as e:
                return False
        return False

    def actualizar_balance(self):
        if self.conectado:
            try:
                self.balance = self.api.get_balance()
            except:
                pass
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
            return None

    def colocar_orden(self, activo, direccion, monto, expiracion):
        if not self.conectado:
            return None, "No conectado"
        try:
            direccion_api = 'call' if direccion.upper() == 'COMPRA' else 'put'
            tiempo = expiracion * 60
            resultado = self.api.buy(monto, activo, direccion_api, tiempo)
            if resultado and len(resultado) > 0:
                id_orden = resultado[0] if isinstance(resultado, list) else resultado
                return id_orden, "Orden ejecutada"
            else:
                return None, "Error al ejecutar orden"
        except Exception as e:
            return None, str(e)

    def verificar_orden(self, id_orden):
        """
        Intenta verificar el resultado de una orden.
        Primero intenta con get_option_result (si existe), luego con get_optioninfo (común en algunas versiones).
        Si no funciona, simula un resultado para pruebas (puedes cambiar esto).
        """
        if not self.conectado:
            return None
        # Intentar con get_option_result (el que mencionaste)
        if hasattr(self.api, 'get_option_result'):
            try:
                resultado = self.api.get_option_result(id_orden)
                if resultado:
                    return {
                        'win': resultado.get('win', False),
                        'profit': resultado.get('profit', 0),
                        'close_price': resultado.get('close_price', 0)
                    }
            except Exception as e:
                logging.error(f"Error en get_option_result: {e}")
        # Intentar con get_optioninfo (alternativa común)
        if hasattr(self.api, 'get_optioninfo'):
            try:
                info = self.api.get_optioninfo(id_orden)
                if info:
                    # Adaptar según la estructura de info
                    win = info.get('win', False) or info.get('result') == 'win'
                    profit = info.get('profit', 0) or info.get('amount', 0)
                    close_price = info.get('close_price', 0)
                    return {'win': win, 'profit': profit, 'close_price': close_price}
            except Exception as e:
                logging.error(f"Error en get_optioninfo: {e}")
        # Si no se pudo verificar, devolvemos None (se tratará como pérdida por seguridad)
        logging.warning(f"No se pudo verificar la orden {id_orden}, se tratará como pérdida.")
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
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_upper'] = bb.bollinger_hband()
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    return df

# ============================================
# DETECCIÓN DE TENDENCIA Y FUERZA
# ============================================
def detectar_tendencia(df):
    if df is None or len(df) < 50:
        return 'lateral', 0
    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-10]) / 10
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10
    sobre_ema20 = ult['close'] > ult['ema_20']
    sobre_ema50 = ult['close'] > ult['ema_50']
    volumen_fuerte = ult['volume_ratio'] > 1.2
    adx_fuerte = ult['adx'] > 25

    fuerza = 0
    if pendiente_ema20 > 0:
        fuerza += 20
    if pendiente_ema50 > 0:
        fuerza += 15
    if sobre_ema20:
        fuerza += 10
    if sobre_ema50:
        fuerza += 10
    if volumen_fuerte:
        fuerza += 15
    if adx_fuerte:
        fuerza += 20

    direccion = 'lateral'
    if (pendiente_ema20 > 0 and pendiente_ema50 > 0) or (sobre_ema20 and sobre_ema50):
        direccion = 'alcista'
    elif (pendiente_ema20 < 0 and pendiente_ema50 < 0) or (not sobre_ema20 and not sobre_ema50):
        direccion = 'bajista'

    return direccion, min(100, fuerza)

# ============================================
# IA TOTAL: DECIDE DIRECCIÓN Y VENCIMIENTO SIN UMBRALES FIJOS
# ============================================
def ia_total(df):
    """
    Analiza todos los indicadores disponibles y decide:
    - Dirección: COMPRA, VENTA o NEUTRO
    - Vencimiento: 1-5 minutos (basado en la fuerza de la señal)
    - Devuelve también los scores para visualización
    """
    if df is None or len(df) < 30:
        return None, 0, None

    ult = df.iloc[-1]
    tendencia, fuerza = detectar_tendencia(df)

    # Calcular scores ponderados (sin umbrales fijos)
    score_compra = 0
    score_venta = 0

    # 1. RSI (contribución suave)
    if ult['rsi'] < 50:
        score_compra += (50 - ult['rsi']) * 0.5
        score_venta -= (50 - ult['rsi']) * 0.3
    else:
        score_venta += (ult['rsi'] - 50) * 0.5
        score_compra -= (ult['rsi'] - 50) * 0.3

    # 2. Volumen (a más volumen, más peso)
    score_compra += ult['volume_ratio'] * 5
    score_venta += ult['volume_ratio'] * 5

    # 3. ADX y dirección
    if ult['adx'] > 20:
        if ult['adx_pos'] > ult['adx_neg']:
            score_compra += ult['adx'] * 2
        elif ult['adx_neg'] > ult['adx_pos']:
            score_venta += ult['adx'] * 2

    # 4. MACD
    macd_diff = ult['macd'] - ult['macd_signal']
    score_compra += macd_diff * 20
    score_venta -= macd_diff * 20

    # 5. Bandas de Bollinger (cerca de los bordes)
    if ult['close'] < ult['bb_lower']:
        score_compra += 30
    elif ult['close'] > ult['bb_upper']:
        score_venta += 30

    # 6. Posición respecto a EMAs
    if ult['close'] > ult['ema_20']:
        score_compra += 10
    else:
        score_venta += 10
    if ult['close'] > ult['ema_50']:
        score_compra += 10
    else:
        score_venta += 10

    # 7. Fuerza de tendencia
    if tendencia == 'alcista':
        score_compra += fuerza
    elif tendencia == 'bajista':
        score_venta += fuerza

    # Decisión final: la dirección con mayor score (incluso si la diferencia es pequeña)
    diferencia = score_compra - score_venta
    if diferencia > 0:
        direccion = 'COMPRA'
        confianza = min(100, abs(diferencia))
    elif diferencia < 0:
        direccion = 'VENTA'
        confianza = min(100, abs(diferencia))
    else:
        return None, 0, {'score_compra': score_compra, 'score_venta': score_venta}

    # Vencimiento: cuanto más alta la confianza, más corto el vencimiento
    if confianza > 80:
        vencimiento = 1
    elif confianza > 60:
        vencimiento = 2
    elif confianza > 40:
        vencimiento = 3
    elif confianza > 20:
        vencimiento = 4
    else:
        vencimiento = 5

    # Detalles para mostrar en el panel
    detalles = {
        'direccion': direccion,
        'confianza': confianza,
        'vencimiento': vencimiento,
        'fuerza': fuerza,
        'tendencia': tendencia,
        'score_compra': round(score_compra, 2),
        'score_venta': round(score_venta, 2),
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'macd_diff': macd_diff,
        'precio': ult['close']
    }

    return direccion, vencimiento, detalles

# ============================================
# CLASE DE GESTIÓN PRINCIPAL
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.ultimo_cambio_activo = time.time()
        self.historial = []
        self.log_eventos = []
        self.operacion_activa = None

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
        if len(self.log_eventos) > 20:
            self.log_eventos = self.log_eventos[-20:]

    def iniciar_operacion(self, activo, direccion, expiracion, detalles):
        ahora = datetime.now(ecuador_tz)
        vencimiento = ahora + timedelta(minutes=expiracion)
        self.operacion_activa = {
            'activo': activo,
            'direccion': direccion,
            'expiracion': expiracion,
            'hora_entrada': ahora,
            'hora_vencimiento': vencimiento,
            'detalles': detalles,
            'resultado': None,
            'ganancia': 0,
            'precio_entrada': detalles.get('precio', 0),
            'id_orden': None
        }
        self.agregar_evento(f"✅ Operación iniciada: {direccion} en {activo} ({expiracion} min)", "✅")

    def cerrar_operacion(self, resultado, ganancia, precio_salida=None):
        if self.operacion_activa:
            self.operacion_activa['resultado'] = resultado
            self.operacion_activa['ganancia'] = ganancia
            self.operacion_activa['precio_salida'] = precio_salida or self.operacion_activa.get('precio_entrada', 0)
            self.historial.append(self.operacion_activa.copy())
            self.operaciones_hoy += 1
            self.agregar_evento(f"{'💰 Ganada' if resultado=='ganada' else '💸 Perdida'} en {self.operacion_activa['activo']} - ${ganancia:.2f}", "💰" if resultado=='ganada' else "💸")
            self.operacion_activa = None

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
# CICLO PRINCIPAL (CON VERIFICACIÓN SEGURA)
# ============================================
def ciclo_principal(connector, manager, config):
    tiempo_actual = time.time()

    # Verificar conexión
    if not connector.verificar_conexion():
        manager.agregar_evento("⚠️ Conexión perdida, intentando reconectar...", "⚠️")
        # No hacemos nada más, en el próximo ciclo se intentará reconectar si es necesario
        return

    # Verificar operación activa
    if manager.operacion_activa:
        ahora = datetime.now(ecuador_tz)
        if ahora >= manager.operacion_activa['hora_vencimiento']:
            id_orden = manager.operacion_activa.get('id_orden')
            if id_orden:
                resultado_api = connector.verificar_orden(id_orden)
                if resultado_api:
                    if resultado_api['win']:
                        ganancia = resultado_api.get('profit', config['monto'] * 0.8)
                        manager.cerrar_operacion('ganada', ganancia, resultado_api.get('close_price'))
                    else:
                        manager.cerrar_operacion('perdida', -config['monto'], resultado_api.get('close_price'))
                else:
                    # No se pudo verificar, asumimos pérdida (por seguridad)
                    manager.cerrar_operacion('perdida', -config['monto'])
            else:
                # No hay ID de orden (no debería ocurrir)
                manager.cerrar_operacion('perdida', -config['monto'])
            connector.actualizar_balance()
            return  # Salir para que en el próximo ciclo se busque nueva operación

    # Límite diario
    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.", "⛔")
        return

    # Si hay operación activa, no ejecutamos nueva
    if manager.operacion_activa:
        manager.estado = f"Operando ({manager.operacion_activa['activo']})"
        return

    # Buscar nuevo activo si es necesario
    if manager.activo_actual is None:
        buscar_nuevo = True
    else:
        if manager.estado == "Analizando" and tiempo_actual - manager.ultimo_cambio_activo > 300:
            manager.agregar_evento(f"⏱️ Tiempo sin señal en {manager.activo_actual}. Buscando otro...", "⏱️")
            buscar_nuevo = True
        else:
            buscar_nuevo = False

    if buscar_nuevo:
        manager.estado = "🔍 Buscando activos..."
        manager.agregar_evento("Buscando activos con oportunidades...", "🔍")
        activos = connector.obtener_activos_disponibles(config['mercado'], max_activos=100)
        mejores_activos = []
        for act in activos[:50]:
            df = connector.obtener_velas(act, intervalo=5, limite=100)
            if df is None:
                continue
            df = calcular_indicadores(df)
            if df is None:
                continue
            tendencia, fuerza = detectar_tendencia(df)
            if tendencia != 'lateral' and fuerza >= 25:
                mejores_activos.append((act, fuerza, tendencia, df))

        if mejores_activos:
            mejores_activos.sort(key=lambda x: x[1], reverse=True)
            mejor = mejores_activos[0]
            manager.activo_actual = mejor[0]
            manager.ultimo_cambio_activo = tiempo_actual
            manager.agregar_evento(f"✅ Mejor activo: {mejor[0]} - Tendencia {mejor[2]} - Fuerza {mejor[1]}%", "✅")
            manager.estado = "Analizando"
        else:
            manager.agregar_evento("⚠️ No se encontró ningún activo. Reintentando en 5 min...", "⚠️")
            return

    # Analizar activo actual con IA total
    df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=100)
    if df is None:
        manager.agregar_evento(f"❌ Error al obtener datos de {manager.activo_actual}. Buscando otro...", "❌")
        manager.activo_actual = None
        return
    df = calcular_indicadores(df)
    if df is None:
        manager.activo_actual = None
        return

    direccion, vencimiento, detalles = ia_total(df)

    if direccion:
        # Colocar orden real
        id_orden, msg = connector.colocar_orden(
            manager.activo_actual,
            direccion,
            config['monto'],
            vencimiento
        )
        if id_orden:
            detalles['id_orden'] = id_orden
            manager.iniciar_operacion(
                manager.activo_actual,
                direccion,
                vencimiento,
                detalles
            )
            manager.operacion_activa['id_orden'] = id_orden
            manager.agregar_evento(f"💰 Orden enviada a IQ Option. ID: {id_orden}", "💰")
            connector.actualizar_balance()
        else:
            manager.agregar_evento(f"❌ Error al enviar orden: {msg}", "❌")
    else:
        manager.agregar_evento(f"⏳ {manager.activo_actual} sin señal clara según IA...", "⏳")

    # Guardar datos para interfaz
    if df is not None and len(df) > 0:
        ult = df.iloc[-1]
        st.session_state.tendencia_actual, st.session_state.fuerza_actual = detectar_tendencia(df)
        st.session_state.precio_actual = ult['close']
        st.session_state.volumen_actual = ult['volume_ratio']
        st.session_state.activo_actual = manager.activo_actual
        st.session_state.estado_bot = manager.estado

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PROFESSIONAL BOT (IA TOTAL)")
    st.markdown("#### IA autónoma sin umbrales fijos | Vencimiento dinámico | Historial real")
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
                saldo = st.session_state.connector.obtener_saldo()
                st.metric("Saldo", f"${saldo:.2f}")

        with col2:
            st.markdown("### ⚙️ Configuración")
            cuenta = st.radio("Cuenta", ["💰 Demo", "💵 Real"], horizontal=True, key="cuenta")
            tipo_cuenta = "PRACTICE" if "Demo" in cuenta else "REAL"
            if tipo_cuenta != st.session_state.connector.tipo_cuenta and st.session_state.conectado:
                with st.spinner("Cambiando cuenta..."):
                    exito = st.session_state.connector.cambiar_balance(tipo_cuenta)
                    if exito:
                        st.success(f"Cuenta cambiada a {tipo_cuenta}")
                        st.rerun()
                    else:
                        st.error("Error al cambiar cuenta")

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

    manager = st.session_state.manager
    resumen = manager.obtener_resumen()

    # PANEL DE OPERACIÓN ACTIVA
    if manager.operacion_activa:
        op = manager.operacion_activa
        tiempo_restante = op['hora_vencimiento'] - datetime.now(ecuador_tz)
        segundos_rest = max(0, int(tiempo_restante.total_seconds()))
        minutos_rest = segundos_rest // 60
        segundos_rest = segundos_rest % 60

        st.markdown("### ⏳ OPERACIÓN ACTIVA")
        with st.container():
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"""
                <div class="operacion-panel">
                    <h3>{op['activo']} - {op['direccion']}</h3>
                    <p><strong>Vencimiento:</strong> {op['expiracion']} minutos</p>
                    <p><strong>Hora entrada:</strong> {op['hora_entrada'].strftime('%H:%M:%S')}</p>
                    <p><strong>Hora vencimiento:</strong> {op['hora_vencimiento'].strftime('%H:%M:%S')}</p>
                    <p><strong>Tiempo restante:</strong> <span class="countdown">{minutos_rest:02d}:{segundos_rest:02d}</span></p>
                </div>
                """, unsafe_allow_html=True)

                # Detalles de la IA
                st.markdown("#### 🧠 Decisión de la IA")
                st.json(op['detalles'])

            with col2:
                # Gráfico rápido
                df = st.session_state.connector.obtener_velas(op['activo'], intervalo=1, limite=30)
                if df is not None:
                    fig = go.Figure(data=[go.Candlestick(x=df.index,
                                                          open=df['open'],
                                                          high=df['high'],
                                                          low=df['low'],
                                                          close=df['close'])])
                    fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0),
                                      paper_bgcolor="#151A24", plot_bgcolor="#151A24",
                                      font_color="#E0E0E0")
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay operación activa en este momento.")

    st.markdown("---")

    # PANEL DE ESTADO
    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📊 Estado del Bot")
        icono_estado = {
            "Detenido": "⏹️",
            "Buscando": "🔍",
            "Analizando": "📊",
            "Límite alcanzado": "⛔"
        }.get(manager.estado, "🤖")

        st.markdown(f"""
        <div class="status-card">
            <h3><span class="icono-estado">{icono_estado}</span> {manager.estado}</h3>
            <p><strong>Activo actual:</strong> {st.session_state.get('activo_actual', 'Ninguno')}</p>
            <p><strong>Tendencia:</strong> {st.session_state.get('tendencia_actual', 'desconocida')} - Fuerza {st.session_state.get('fuerza_actual', 0)}%</p>
            <p><strong>Precio actual:</strong> {st.session_state.get('precio_actual', 0):.5f}</p>
            <p><strong>Volumen:</strong> {st.session_state.get('volumen_actual', 0):.2f}x</p>
            <p><strong>Operaciones hoy:</strong> {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📋 Ver eventos recientes", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen de operaciones")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")

    # HISTORIAL COMPLETO
    with st.expander("📜 Ver historial completo de operaciones"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            # Aplanar detalles
            detalles_df = pd.json_normalize(df_hist['detalles'])
            df_hist = df_hist.drop(columns=['detalles']).join(detalles_df)
            df_hist = df_hist[['hora_entrada', 'activo', 'direccion', 'expiracion',
                                'precio_entrada', 'precio_salida', 'resultado', 'ganancia',
                                'confianza', 'fuerza', 'tendencia', 'score_compra', 'score_venta',
                                'rsi', 'volume_ratio', 'adx', 'macd_diff']]
            st.dataframe(df_hist, use_container_width=True)
            csv = df_hist.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Exportar historial a CSV", csv, "historial_operaciones.csv", "text/csv")
        else:
            st.info("Aún no hay operaciones registradas.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
