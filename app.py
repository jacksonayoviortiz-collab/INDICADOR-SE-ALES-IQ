"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN TENDENCIAS + RETROCESOS 5 MIN
- Resultados reales con la librería de williansandi
- Estrategia: detecta tendencia, espera retroceso a EMA20 o soporte/resistencia, opera a 5 min
- Analiza todos los activos uno por uno (rápido) y elige el mejor
- Parámetros: monto, cuenta demo/real, límite diario, mercado OTC/normal
- Botón para reiniciar el límite diario manualmente
- Historial con resultados reales y exportable
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
    page_title="IQ Option Trend Bot",
    page_icon="📈",
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
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION (CON RESULTADOS REALES)
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}
        self.ordenes_pendientes = {}

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
            try:
                self.api.change_balance(tipo)
                self.tipo_cuenta = tipo
                time.sleep(1)
                self.balance = self.api.get_balance()
                return True
            except:
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

    def obtener_activos_disponibles(self, mercado="otc", max_activos=200):
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
        if not self.conectado:
            return None
        try:
            time.sleep(0.1)  # Reducido para ser más rápido
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
        """Obtiene el resultado real de una orden."""
        if not self.conectado:
            return None
        # Intentar con get_option_result
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
        # Fallback a get_optioninfo
        if hasattr(self.api, 'get_optioninfo'):
            try:
                info = self.api.get_optioninfo(id_orden)
                if info:
                    win = info.get('win', False) or info.get('result') == 'win'
                    profit = info.get('profit', 0) or info.get('amount', 0)
                    close_price = info.get('close_price', 0)
                    return {'win': win, 'profit': profit, 'close_price': close_price}
            except Exception as e:
                logging.error(f"Error en get_optioninfo: {e}")
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
    return df

# ============================================
# DETECCIÓN DE TENDENCIA (SOLO ALCISTA/BAJISTA)
# ============================================
def detectar_tendencia(df):
    """Retorna: 'alcista', 'bajista' o 'lateral', y fuerza (0-100)"""
    if df is None or len(df) < 30:
        return 'lateral', 0
    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10
    sobre_ema20 = ult['close'] > ult['ema_20']
    sobre_ema50 = ult['close'] > ult['ema_50']
    volumen_bueno = ult['volume_ratio'] > 1.0  # Cualquier volumen positivo ayuda
    adx_bueno = ult['adx'] > 20  # ADX moderado

    fuerza = 0
    if pendiente_ema20 > 0:
        fuerza += 25
    if pendiente_ema50 > 0:
        fuerza += 20
    if sobre_ema20:
        fuerza += 15
    if sobre_ema50:
        fuerza += 15
    if volumen_bueno:
        fuerza += 10
    if adx_bueno:
        fuerza += 15

    direccion = 'lateral'
    if (pendiente_ema20 > 0 and pendiente_ema50 > 0) or (sobre_ema20 and sobre_ema50):
        direccion = 'alcista'
    elif (pendiente_ema20 < 0 and pendiente_ema50 < 0) or (not sobre_ema20 and not sobre_ema50):
        direccion = 'bajista'

    return direccion, min(100, fuerza)

# ============================================
# DETECCIÓN DE RETROCESO PARA OPERAR
# ============================================
def calcular_precio_entrada(df, tendencia):
    """Calcula el precio al que se debe entrar (retroceso a EMA20 o soporte/resistencia cercano)."""
    if df is None or len(df) < 20:
        return None
    ult = df.iloc[-1]
    if tendencia == 'alcista':
        # Buscar soporte cercano (mínimo reciente)
        min_reciente = df['low'].iloc[-10:].min()
        # Precio objetivo: el mayor entre EMA20 y el soporte
        precio_objetivo = max(ult['ema_20'], min_reciente)
        # No esperar una diferencia exacta, cualquier precio <= objetivo es bueno
        return precio_objetivo
    elif tendencia == 'bajista':
        max_reciente = df['high'].iloc[-10:].max()
        precio_objetivo = min(ult['ema_20'], max_reciente)
        return precio_objetivo
    return None

# ============================================
# ANÁLISIS RÁPIDO DE UN ACTIVO (PARA ESCANEO)
# ============================================
def analizar_activo(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None
    tendencia, fuerza = detectar_tendencia(df)
    if tendencia == 'lateral' or fuerza < 30:
        return None
    ult = df.iloc[-1]
    precio_entrada = calcular_precio_entrada(df, tendencia)
    if precio_entrada is None:
        return None
    return {
        'activo': activo,
        'tendencia': tendencia,
        'fuerza': fuerza,
        'precio_actual': ult['close'],
        'precio_entrada': precio_entrada,
        'volumen': ult['volume_ratio'],
        'adx': ult['adx'],
        'df': df
    }

# ============================================
# CLASE DE GESTIÓN PRINCIPAL
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.historial = []
        self.log_eventos = []
        self.operacion_activa = None
        self.precio_objetivo = None
        self.direccion_objetivo = None

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
        if len(self.log_eventos) > 20:
            self.log_eventos = self.log_eventos[-20:]

    def iniciar_espera_retroceso(self, activo, direccion, precio_entrada, detalles):
        """Inicia la espera de retroceso para una operación de 5 minutos."""
        self.activo_actual = activo
        self.direccion_objetivo = direccion
        self.precio_objetivo = precio_entrada
        self.estado = f"Esperando retroceso ({activo})"
        self.agregar_evento(f"🎯 Esperando retroceso en {activo} a {precio_entrada:.5f} para {direccion}", "🎯")

    def iniciar_operacion(self, activo, direccion, monto, detalles, id_orden):
        """Inicia una operación (se llama cuando se alcanza el retroceso)."""
        ahora = datetime.now(ecuador_tz)
        vencimiento = ahora + timedelta(minutes=5)
        self.operacion_activa = {
            'activo': activo,
            'direccion': direccion,
            'expiracion': 5,
            'hora_entrada': ahora,
            'hora_vencimiento': vencimiento,
            'detalles': detalles,
            'resultado': None,
            'ganancia': 0,
            'precio_entrada': detalles.get('precio_actual', 0),
            'id_orden': id_orden
        }
        self.agregar_evento(f"✅ Operación iniciada: {direccion} en {activo} (5 min)", "✅")
        self.estado = f"Operando ({activo})"
        self.precio_objetivo = None
        self.direccion_objetivo = None

    def cerrar_operacion(self, resultado, ganancia, precio_salida=None):
        if self.operacion_activa:
            self.operacion_activa['resultado'] = resultado
            self.operacion_activa['ganancia'] = ganancia
            self.operacion_activa['precio_salida'] = precio_salida or self.operacion_activa.get('precio_entrada', 0)
            self.historial.append(self.operacion_activa.copy())
            self.operaciones_hoy += 1
            self.agregar_evento(f"{'💰 Ganada' if resultado=='ganada' else '💸 Perdida'} en {self.operacion_activa['activo']} - ${ganancia:.2f}", "💰" if resultado=='ganada' else "💸")
            self.operacion_activa = None
            self.activo_actual = None
            self.estado = "Buscando"

    def reiniciar_limite(self):
        """Reinicia el contador de operaciones diarias."""
        self.operaciones_hoy = 0
        self.agregar_evento("🔄 Límite diario reiniciado manualmente", "🔄")

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
# CICLO PRINCIPAL
# ============================================
def ciclo_principal(connector, manager, config):
    ahora = datetime.now(ecuador_tz)

    # 1. Verificar operación activa (vencimiento)
    if manager.operacion_activa:
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
                    manager.cerrar_operacion('perdida', -config['monto'])
            else:
                manager.cerrar_operacion('perdida', -config['monto'])
            connector.actualizar_balance()
        return  # Si hay operación activa, no hacemos más en este ciclo

    # 2. Verificar límite diario
    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.", "⛔")
        return

    # 3. Si estamos esperando un retroceso, verificar si se cumple
    if manager.precio_objetivo is not None and manager.direccion_objetivo is not None:
        df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=20)
        if df is not None and len(df) > 0:
            ult = df.iloc[-1]
            if (manager.direccion_objetivo == 'COMPRA' and ult['close'] <= manager.precio_objetivo) or \
               (manager.direccion_objetivo == 'VENTA' and ult['close'] >= manager.precio_objetivo):
                # Retroceso alcanzado: ejecutar orden
                id_orden, msg = connector.colocar_orden(
                    manager.activo_actual,
                    manager.direccion_objetivo,
                    config['monto'],
                    5
                )
                if id_orden:
                    detalles = {
                        'activo': manager.activo_actual,
                        'precio_actual': ult['close'],
                        'fuerza': 0,  # Podríamos calcularla de nuevo
                        'volumen': ult['volume_ratio'] if 'volume_ratio' in df.columns else 0,
                        'adx': ult['adx'] if 'adx' in df.columns else 0
                    }
                    manager.iniciar_operacion(manager.activo_actual, manager.direccion_objetivo, config['monto'], detalles, id_orden)
                    connector.actualizar_balance()
                else:
                    manager.agregar_evento(f"❌ Error al enviar orden: {msg}", "❌")
                    manager.precio_objetivo = None
                    manager.direccion_objetivo = None
                    manager.estado = "Buscando"
        return

    # 4. No hay operación ni espera: buscar el mejor activo
    manager.estado = "🔍 Escaneando activos..."
    activos = connector.obtener_activos_disponibles(config['mercado'], max_activos=100)
    mejor = None
    mejor_fuerza = 0

    for act in activos[:50]:  # Analizar hasta 50 activos rápidamente
        analisis = analizar_activo(act, connector)
        if analisis and analisis['fuerza'] > mejor_fuerza:
            mejor_fuerza = analisis['fuerza']
            mejor = analisis

    if mejor:
        manager.agregar_evento(f"✅ Mejor activo encontrado: {mejor['activo']} - Tendencia {mejor['tendencia']} (fuerza {mejor['fuerza']}%)", "✅")
        # Iniciar espera de retroceso
        direccion = 'COMPRA' if mejor['tendencia'] == 'alcista' else 'VENTA'
        manager.iniciar_espera_retroceso(mejor['activo'], direccion, mejor['precio_entrada'], mejor)
    else:
        manager.agregar_evento("⏳ No se encontró ningún activo con tendencia clara. Reintentando...", "⏳")
        time.sleep(5)

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("📈 IQ OPTION TREND BOT (5 MIN RETROCESOS)")
    st.markdown("#### Analiza todos los activos, espera retroceso y opera con resultados reales")
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
            st.markdown("### ⏱️ Límite diario")
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
                # Botón para reiniciar límite
                if st.button("🔄 Reiniciar límite diario", use_container_width=True):
                    st.session_state.manager.reiniciar_limite()
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

    # PANEL DE OPERACIÓN ACTIVA O ESPERA
    if manager.operacion_activa:
        op = manager.operacion_activa
        tiempo_restante = op['hora_vencimiento'] - ahora
        segundos_rest = max(0, int(tiempo_restante.total_seconds()))
        minutos_rest = segundos_rest // 60
        segundos_rest = segundos_rest % 60

        st.markdown("### ⏳ OPERACIÓN ACTIVA (5 MIN)")
        with st.container():
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"""
                <div class="operacion-panel">
                    <h3>{op['activo']} - {op['direccion']}</h3>
                    <p><strong>Hora entrada:</strong> {op['hora_entrada'].strftime('%H:%M:%S')}</p>
                    <p><strong>Hora vencimiento:</strong> {op['hora_vencimiento'].strftime('%H:%M:%S')}</p>
                    <p><strong>Tiempo restante:</strong> <span class="countdown">{minutos_rest:02d}:{segundos_rest:02d}</span></p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.metric("Precio entrada", f"{op['precio_entrada']:.5f}")
    elif manager.precio_objetivo is not None:
        st.markdown("### ⏳ ESPERANDO RETROCESO")
        st.info(f"Activo: {manager.activo_actual} | Objetivo: {manager.precio_objetivo:.5f} para {manager.direccion_objetivo}")
    else:
        st.info(manager.estado if manager.estado != "Detenido" else "Bot detenido. Presiona INICIAR.")

    st.markdown("---")

    # PANEL DE ESTADO
    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📊 Estado del Bot")
        icono_estado = {
            "Detenido": "⏹️",
            "Buscando": "🔍",
            "Escaneando": "🔍",
            "Límite alcanzado": "⛔"
        }.get(manager.estado.split()[0] if manager.estado else "Detenido", "🤖")

        st.markdown(f"""
        <div class="status-card">
            <h3><span class="icono-estado">{icono_estado}</span> {manager.estado}</h3>
            <p><strong>Operaciones hoy:</strong> {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📋 Ver eventos recientes", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")

    # HISTORIAL
    with st.expander("📜 Ver historial completo de operaciones"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            # Extraer detalles si existen
            if 'detalles' in df_hist.columns:
                detalles_df = pd.json_normalize(df_hist['detalles'])
                df_hist = df_hist.drop(columns=['detalles']).join(detalles_df)
            # Seleccionar columnas
            cols = ['hora_entrada', 'activo', 'direccion', 'expiracion', 'precio_entrada', 'precio_salida', 'resultado', 'ganancia', 'fuerza', 'volumen', 'adx']
            cols = [c for c in cols if c in df_hist.columns]
            df_hist = df_hist[cols]
            st.dataframe(df_hist, use_container_width=True)
            csv = df_hist.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Exportar historial a CSV", csv, "historial_operaciones.csv", "text/csv")
        else:
            st.info("Aún no hay operaciones registradas.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
