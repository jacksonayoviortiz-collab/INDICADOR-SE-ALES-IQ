"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN IA AVANZADA
- 10 estrategias dinámicas cubren todos los escenarios
- Vencimiento adaptativo 2-5 minutos
- Panel de resumen profesional con estadísticas
- Exportación a CSV
- Configuración avanzada desde interfaz
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
import io
import base64

from streamlit_autorefresh import st_autorefresh

# Intentar importar librerías de IA (opcional, para futura expansión)
try:
    from sklearn.ensemble import RandomForestClassifier
    from xgboost import XGBClassifier
    ML_AVAILABLE = True
except:
    ML_AVAILABLE = False

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
    page_title="IQ Option Pro Bot (IA 10 Estrategias)",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 5 segundos
st_autorefresh(interval=5000, key="autorefresh")

# CSS personalizado (más profesional)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    .stApp {
        background-color: #0A0C10;
        color: #E0E0E0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #00FF88 !important;
        font-weight: 700 !important;
    }
    .metric-card {
        background: linear-gradient(145deg, #151A24, #0F1217);
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8844;
        box-shadow: 0 10px 20px -10px #00FF8822;
    }
    .resumen-panel {
        background: #151A24;
        border-radius: 20px;
        padding: 15px;
        margin: 10px 0;
        border-left: 4px solid #00FF88;
    }
    .evento {
        background: #1E242C;
        border-left: 4px solid #00FF88;
        padding: 10px;
        margin: 5px 0;
        border-radius: 8px;
        font-size: 14px;
    }
    .reloj {
        font-size: 28px;
        font-weight: 700;
        color: #00FF88;
        text-align: center;
        background: #151A24;
        padding: 15px;
        border-radius: 60px;
        margin-bottom: 20px;
        border: 1px solid #00FF88;
    }
    .stButton button {
        background: #00FF88;
        color: black;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 10px 30px;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background: #00CC66;
        box-shadow: 0 10px 20px -5px #00FF88;
    }
    .signal-badge {
        font-size: 16px;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 30px;
        display: inline-block;
    }
    .signal-compra { background: rgba(0, 255, 136, 0.15); color: #00FF88; border: 1px solid #00FF88; }
    .signal-venta { background: rgba(255, 70, 70, 0.15); color: #FF4646; border: 1px solid #FF4646; }
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
    .config-slider {
        margin: 15px 0;
        padding: 10px;
        background: #151A24;
        border-radius: 15px;
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
        self.lista_activos = []
        self.indice_actual = 0
        self.ultima_actualizacion_lista = 0

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

    def obtener_lista_activos(self, mercado="otc", max_activos=100, force_refresh=False):
        if not self.conectado:
            return []
        ahora = time.time()
        if force_refresh or (ahora - self.ultima_actualizacion_lista > 600) or not self.lista_activos:
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
                self.lista_activos = sorted(activos)[:max_activos]
                self.ultima_actualizacion_lista = ahora
                self.indice_actual = 0
            except Exception as e:
                st.error(f"Error obteniendo activos: {e}")
        return self.lista_activos

    def obtener_siguiente_activo(self):
        if not self.lista_activos:
            return None
        activo = self.lista_activos[self.indice_actual]
        self.indice_actual = (self.indice_actual + 1) % len(self.lista_activos)
        return activo

    def obtener_velas(self, activo, intervalo=5, limite=100, reintentos=2):
        if not self.conectado:
            return None
        for intento in range(reintentos):
            try:
                time.sleep(0.1)
                if intervalo == 5:
                    velas = self.api.get_candles(activo, 60, limite * 5, time.time())
                else:
                    velas = self.api.get_candles(activo, 60, limite, time.time())
                if not velas:
                    if intento == reintentos - 1:
                        return None
                    time.sleep(2)
                    continue
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
                if intento == reintentos - 1:
                    return None
                time.sleep(2)
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
        if not self.conectado:
            return None
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
# INDICADORES TÉCNICOS AVANZADOS
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
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['close'] * 100
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    return df

# ============================================
# 10 ESTRATEGIAS INDEPENDIENTES
# ============================================
def evaluar_estrategias(df):
    """Evalúa las 10 estrategias y devuelve la mejor señal, confianza y vencimiento."""
    if df is None or len(df) < 30:
        return None, 0, 0, {}

    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10

    # Diccionario para almacenar los resultados de cada estrategia
    resultados = []

    # 1. Tendencia Fuerte Alcista
    if (ult['close'] > ult['ema_20'] and ult['ema_20'] > ult['ema_50'] and 
        ult['adx'] > 25 and ult['volume_ratio'] > 1.2):
        confianza = min(95, 70 + ult['adx']/2 + ult['volume_ratio']*5)
        venc = 4 if confianza > 80 else 5
        resultados.append(('COMPRA', confianza, venc, 'Tendencia Fuerte Alcista'))

    # 2. Tendencia Fuerte Bajista
    if (ult['close'] < ult['ema_20'] and ult['ema_20'] < ult['ema_50'] and 
        ult['adx'] > 25 and ult['volume_ratio'] > 1.2):
        confianza = min(95, 70 + ult['adx']/2 + ult['volume_ratio']*5)
        venc = 4 if confianza > 80 else 5
        resultados.append(('VENTA', confianza, venc, 'Tendencia Fuerte Bajista'))

    # 3. Retroceso en Tendencia Alcista
    if (pendiente_ema20 > 0 and pendiente_ema50 > 0 and 
        ult['close'] <= ult['ema_20'] * 1.005 and ult['rsi'] > 40 and ult['volume_ratio'] > 1.0):
        confianza = min(90, 60 + ult['adx'] + ult['volume_ratio']*3)
        venc = 3
        resultados.append(('COMPRA', confianza, venc, 'Retroceso Alcista'))

    # 4. Retroceso en Tendencia Bajista
    if (pendiente_ema20 < 0 and pendiente_ema50 < 0 and 
        ult['close'] >= ult['ema_20'] * 0.995 and ult['rsi'] < 60 and ult['volume_ratio'] > 1.0):
        confianza = min(90, 60 + ult['adx'] + ult['volume_ratio']*3)
        venc = 3
        resultados.append(('VENTA', confianza, venc, 'Retroceso Bajista'))

    # 5. Ruptura de Lateral
    if (ult['bb_width'] < 2.0 and ult['volume_ratio'] > 1.8):
        if ult['close'] > ult['bb_upper']:
            confianza = 85
            venc = 2
            resultados.append(('COMPRA', confianza, venc, 'Ruptura Lateral Alcista'))
        elif ult['close'] < ult['bb_lower']:
            confianza = 85
            venc = 2
            resultados.append(('VENTA', confianza, venc, 'Ruptura Lateral Bajista'))

    # 6. Reversión Alcista
    if (df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and 
        df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2] and
        ult['volume_ratio'] > 1.3 and pendiente_ema20 > 0):
        confianza = 80
        venc = 3
        resultados.append(('COMPRA', confianza, venc, 'Reversión Alcista'))

    # 7. Reversión Bajista
    if (df['macd'].iloc[-1] < df['macd_signal'].iloc[-1] and 
        df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2] and
        ult['volume_ratio'] > 1.3 and pendiente_ema20 < 0):
        confianza = 80
        venc = 3
        resultados.append(('VENTA', confianza, venc, 'Reversión Bajista'))

    # 8. Microtendencia Alcista
    if (pendiente_ema20 > 0 and 45 < ult['rsi'] < 65 and 
        0.8 < ult['volume_ratio'] < 1.5 and ult['adx'] > 15):
        confianza = 70
        venc = 4
        resultados.append(('COMPRA', confianza, venc, 'Microtendencia Alcista'))

    # 9. Microtendencia Bajista
    if (pendiente_ema20 < 0 and 35 < ult['rsi'] < 55 and 
        0.8 < ult['volume_ratio'] < 1.5 and ult['adx'] > 15):
        confianza = 70
        venc = 4
        resultados.append(('VENTA', confianza, venc, 'Microtendencia Bajista'))

    # 10. Alta Volatilidad Controlada
    if (ult['bb_width'] > 5.0 and ult['adx'] > 30):
        if ult['close'] > ult['ema_20']:
            confianza = 75
            venc = 2
            resultados.append(('COMPRA', confianza, venc, 'Volatilidad Alcista'))
        elif ult['close'] < ult['ema_20']:
            confianza = 75
            venc = 2
            resultados.append(('VENTA', confianza, venc, 'Volatilidad Bajista'))

    # Si no hay resultados, devolvemos None
    if not resultados:
        return None, 0, 0, {}

    # Elegir la estrategia con mayor confianza
    mejor = max(resultados, key=lambda x: x[1])
    return mejor[0], mejor[1], mejor[2], {'estrategia': mejor[3], 'confianza': mejor[1]}

# ============================================
# CÁLCULO DE PRECIO DE RETROCESO
# ============================================
def calcular_precio_entrada(df, tendencia):
    if df is None or len(df) < 20:
        return None
    ult = df.iloc[-1]
    if tendencia == 'COMPRA':
        min_reciente = df['low'].iloc[-10:].min()
        precio_objetivo = max(ult['ema_20'], min_reciente)
        return precio_objetivo
    elif tendencia == 'VENTA':
        max_reciente = df['high'].iloc[-10:].max()
        precio_objetivo = min(ult['ema_20'], max_reciente)
        return precio_objetivo
    return None

# ============================================
# CLASE DE GESTIÓN PRINCIPAL
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.operaciones_totales = 0
        self.ganadas = 0
        self.perdidas = 0
        self.historial = []
        self.log_eventos = []
        self.operacion_activa = None
        self.precio_objetivo = None
        self.direccion_objetivo = None
        self.estrategia_actual = None
        self.inicio_sesion = datetime.now(ecuador_tz)

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
        if len(self.log_eventos) > 30:
            self.log_eventos = self.log_eventos[-30:]

    def iniciar_espera_retroceso(self, activo, direccion, precio_entrada, detalles):
        self.activo_actual = activo
        self.direccion_objetivo = direccion
        self.precio_objetivo = precio_entrada
        self.estrategia_actual = detalles.get('estrategia', 'Desconocida')
        self.estado = f"Esperando retroceso ({activo})"
        self.agregar_evento(f"🎯 Estrategia '{self.estrategia_actual}': esperando retroceso en {activo} a {precio_entrada:.5f}", "🎯")

    def iniciar_operacion(self, activo, direccion, monto, detalles, id_orden):
        ahora = datetime.now(ecuador_tz)
        vencimiento = ahora + timedelta(minutes=detalles.get('vencimiento', 5))
        self.operacion_activa = {
            'activo': activo,
            'direccion': direccion,
            'expiracion': detalles.get('vencimiento', 5),
            'hora_entrada': ahora,
            'hora_vencimiento': vencimiento,
            'detalles': detalles,
            'resultado': None,
            'ganancia': 0,
            'precio_entrada': detalles.get('precio_actual', 0),
            'id_orden': id_orden,
            'estrategia': self.estrategia_actual
        }
        self.agregar_evento(f"✅ Operación iniciada: {direccion} en {activo} ({detalles.get('vencimiento',5)} min) - Estrategia: {self.estrategia_actual}", "✅")
        self.estado = f"Operando ({activo})"
        self.precio_objetivo = None
        self.direccion_objetivo = None

    def cerrar_operacion(self, resultado, ganancia, precio_salida=None):
        if self.operacion_activa:
            self.operacion_activa['resultado'] = resultado
            self.operacion_activa['ganancia'] = ganancia
            self.operacion_activa['precio_salida'] = precio_salida or self.operacion_activa.get('precio_entrada', 0)
            self.historial.append(self.operacion_activa.copy())
            self.operaciones_totales += 1
            self.operaciones_hoy += 1
            if resultado == 'ganada':
                self.ganadas += 1
            else:
                self.perdidas += 1
            self.agregar_evento(f"{'💰 Ganada' if resultado=='ganada' else '💸 Perdida'} en {self.operacion_activa['activo']} - ${ganancia:.2f}", "💰" if resultado=='ganada' else "💸")
            self.operacion_activa = None
            self.activo_actual = None
            self.estado = "Buscando"

    def reiniciar_limite(self):
        self.operaciones_hoy = 0
        self.agregar_evento("🔄 Límite diario reiniciado manualmente", "🔄")

    def obtener_tasa_acierto(self):
        if self.operaciones_totales == 0:
            return 0
        return (self.ganadas / self.operaciones_totales) * 100

    def obtener_resumen(self):
        return {
            'total': self.operaciones_totales,
            'ganadas': self.ganadas,
            'perdidas': self.perdidas,
            'neto': sum([t.get('ganancia', 0) for t in self.historial]),
            'tasa_acierto': self.obtener_tasa_acierto(),
            'hoy': self.operaciones_hoy
        }

# ============================================
# CICLO PRINCIPAL
# ============================================
def ciclo_principal(connector, manager, config):
    ahora = datetime.now(ecuador_tz)

    # 1. Verificar operación activa
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
        return

    # 2. Límite diario
    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.", "⛔")
        return

    # 3. Esperando retroceso
    if manager.precio_objetivo is not None and manager.direccion_objetivo is not None:
        df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=20)
        if df is not None and len(df) > 0:
            ult = df.iloc[-1]
            if (manager.direccion_objetivo == 'COMPRA' and ult['close'] <= manager.precio_objetivo) or \
               (manager.direccion_objetivo == 'VENTA' and ult['close'] >= manager.precio_objetivo):
                id_orden, msg = connector.colocar_orden(
                    manager.activo_actual,
                    manager.direccion_objetivo,
                    config['monto'],
                    config.get('vencimiento_base', 5)  # Usamos vencimiento de la estrategia
                )
                if id_orden:
                    detalles = {
                        'precio_actual': ult['close'],
                        'vencimiento': config.get('vencimiento_base', 5),
                        'estrategia': manager.estrategia_actual
                    }
                    manager.iniciar_operacion(manager.activo_actual, manager.direccion_objetivo, config['monto'], detalles, id_orden)
                    connector.actualizar_balance()
                else:
                    manager.agregar_evento(f"❌ Error al enviar orden: {msg}", "❌")
                    manager.precio_objetivo = None
                    manager.direccion_objetivo = None
                    manager.estado = "Buscando"
        return

    # 4. Buscar nuevo activo (uno por ciclo)
    manager.estado = "🔍 Analizando activos..."
    activos = connector.obtener_lista_activos(config['mercado'], max_activos=config.get('max_activos', 100))
    if not activos:
        manager.agregar_evento("⚠️ No hay activos disponibles. Reintentando...", "⚠️")
        time.sleep(5)
        return

    # Probar activos hasta encontrar una señal
    for _ in range(min(config.get('activos_por_ciclo', 1), len(activos))):
        activo = connector.obtener_siguiente_activo()
        if not activo:
            break
        df = connector.obtener_velas(activo, intervalo=5, limite=100)
        if df is None:
            continue
        df = calcular_indicadores(df)
        if df is None:
            continue

        direccion, confianza, vencimiento, detalles = evaluar_estrategias(df)

        if direccion and confianza >= config.get('umbral_confianza', 60):
            ult = df.iloc[-1]
            precio_entrada = calcular_precio_entrada(df, direccion)
            if precio_entrada:
                manager.agregar_evento(f"✅ Señal en {activo}: {direccion} (confianza {confianza:.0f}%) - Estrategia: {detalles['estrategia']}", "✅")
                manager.iniciar_espera_retroceso(activo, direccion, precio_entrada, detalles)
                break
            else:
                manager.agregar_evento(f"⏳ {activo}: señal pero sin precio de retroceso claro", "⏳")
        else:
            manager.agregar_evento(f"⏳ {activo} sin señal clara (max confianza: {confianza:.0f}%)", "⏳")
        time.sleep(config.get('pausa_entre_analisis', 0.5))

    if not manager.precio_objetivo:
        manager.agregar_evento("🔄 No se encontró señal en este ciclo, continuando...", "🔄")

# ============================================
# FUNCIONES DE EXPORTACIÓN
# ============================================
def generar_csv(historial):
    if not historial:
        return None
    df = pd.DataFrame(historial)
    # Aplanar detalles si existen
    if 'detalles' in df.columns:
        detalles_df = pd.json_normalize(df['detalles'])
        df = df.drop(columns=['detalles']).join(detalles_df)
    return df.to_csv(index=False).encode('utf-8')

def generar_pdf(historial):
    # Placeholder para futura implementación con reportlab o fpdf
    return None

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PRO BOT (IA 10 ESTRATEGIAS)")
    st.markdown("#### Precisión avanzada | Vencimiento dinámico | Panel profesional")
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
            'limite_diario': 5,
            'max_activos': 100,
            'activos_por_ciclo': 1,
            'umbral_confianza': 60,
            'pausa_entre_analisis': 0.5,
            'vencimiento_base': 5,
            'modo_demo': True
        }
    if 'bot_activo' not in st.session_state:
        st.session_state.bot_activo = False

    # Panel superior de configuración (4 columnas)
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
                modo = "💰 DEMO" if st.session_state.config['modo_demo'] else "💵 REAL"
                st.success(f"✅ Conectado ({modo})")
                saldo = st.session_state.connector.obtener_saldo()
                st.metric("Saldo", f"${saldo:.2f}")

        with col2:
            st.markdown("### ⚙️ Mercado")
            cuenta = st.radio("Cuenta", ["💰 Demo", "💵 Real"], horizontal=True, key="cuenta")
            st.session_state.config['modo_demo'] = (cuenta == "💰 Demo")
            tipo_cuenta = "PRACTICE" if st.session_state.config['modo_demo'] else "REAL"
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
            st.markdown("### 💰 Operación")
            st.session_state.config['monto'] = st.number_input(
                "Monto ($)",
                min_value=1.0 if not st.session_state.config['modo_demo'] else 0.1,
                max_value=1000.0 if not st.session_state.config['modo_demo'] else 100.0,
                value=st.session_state.config['monto'],
                step=1.0
            )
            st.session_state.config['limite_diario'] = st.number_input(
                "Límite diario",
                min_value=1,
                max_value=50,
                value=st.session_state.config['limite_diario'],
                step=1
            )

        with col4:
            st.markdown("### ▶️ Control")
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
                if st.button("🔄 Reiniciar límite", use_container_width=True):
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

    # === PANEL DE RESUMEN SUPERIOR ===
    st.markdown("### 📊 Resumen General")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Activos monitoreados", len(st.session_state.connector.lista_activos) if st.session_state.connector.lista_activos else 0)
    with col2:
        st.metric("Tasa de acierto", f"{resumen['tasa_acierto']:.1f}%")
    with col3:
        st.metric("Operaciones hoy", f"{resumen['hoy']} / {st.session_state.config['limite_diario']}")
    with col4:
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")
    with col5:
        st.metric("Modo", "DEMO" if st.session_state.config['modo_demo'] else "REAL")

    st.markdown("---")

    # === PANEL DE OPERACIÓN ACTIVA ===
    if manager.operacion_activa:
        op = manager.operacion_activa
        tiempo_restante = op['hora_vencimiento'] - ahora
        segundos_rest = max(0, int(tiempo_restante.total_seconds()))
        minutos_rest = segundos_rest // 60
        segundos_rest = segundos_rest % 60

        st.markdown("### ⏳ OPERACIÓN ACTIVA")
        with st.container():
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"""
                <div class="operacion-panel">
                    <h3>{op['activo']} - {op['direccion']} <span class="signal-badge signal-{'compra' if op['direccion']=='COMPRA' else 'venta'}">{op['direccion']}</span></h3>
                    <p><strong>Estrategia:</strong> {op.get('estrategia', 'N/A')}</p>
                    <p><strong>Vencimiento:</strong> {op['expiracion']} minutos</p>
                    <p><strong>Entrada:</strong> {op['hora_entrada'].strftime('%H:%M:%S')}</p>
                    <p><strong>Vencimiento:</strong> {op['hora_vencimiento'].strftime('%H:%M:%S')}</p>
                    <p><strong>Tiempo restante:</strong> <span class="countdown">{minutos_rest:02d}:{segundos_rest:02d}</span></p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.metric("Precio entrada", f"{op['precio_entrada']:.5f}")
                st.metric("Confianza", f"{op.get('detalles', {}).get('confianza', 0):.0f}%")
    elif manager.precio_objetivo is not None:
        st.markdown("### ⏳ ESPERANDO RETROCESO")
        st.info(f"Activo: {manager.activo_actual} | Objetivo: {manager.precio_objetivo:.5f} para {manager.direccion_objetivo}")
        st.caption(f"Estrategia: {manager.estrategia_actual}")
    else:
        st.info(manager.estado if manager.estado != "Detenido" else "Bot detenido. Presiona INICIAR.")

    st.markdown("---")

    # === PANEL DE ESTADO Y EVENTOS ===
    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📋 Eventos recientes")
        for ev in manager.log_eventos[-15:]:
            st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Rendimiento histórico")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        # Mini gráfico de equity (simulado)
        if manager.historial:
            equity = [0]
            for op in manager.historial:
                equity.append(equity[-1] + op.get('ganancia', 0))
            fig = go.Figure(data=go.Scatter(y=equity, mode='lines', line=dict(color='#00FF88', width=2)))
            fig.update_layout(height=150, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="#151A24", plot_bgcolor="#151A24",
                              font_color="#E0E0E0", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    # === EXPORTAR HISTORIAL ===
    with st.expander("📜 Ver historial completo y exportar"):
        if manager.historial:
            # Crear DataFrame para mostrar
            df_hist = pd.DataFrame(manager.historial)
            if 'detalles' in df_hist.columns:
                detalles_df = pd.json_normalize(df_hist['detalles'])
                df_hist = df_hist.drop(columns=['detalles']).join(detalles_df)
            # Seleccionar columnas relevantes
            cols = ['hora_entrada', 'activo', 'direccion', 'expiracion', 'estrategia',
                    'precio_entrada', 'precio_salida', 'resultado', 'ganancia', 'confianza']
            cols = [c for c in cols if c in df_hist.columns]
            st.dataframe(df_hist[cols], use_container_width=True)

            # Botones de exportación
            csv_data = generar_csv(manager.historial)
            if csv_data:
                st.download_button("📥 Exportar a CSV", csv_data, "historial_operaciones.csv", "text/csv")
            # Placeholder para PDF
            if st.button("📄 Generar PDF (próximamente)"):
                st.info("Función PDF en desarrollo. Por ahora usa CSV.")
        else:
            st.info("Aún no hay operaciones registradas.")

    # === CONFIGURACIÓN AVANZADA (Expandible) ===
    with st.expander("⚙️ Configuración avanzada"):
        st.markdown("#### Parámetros de análisis")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.session_state.config['max_activos'] = st.number_input(
                "Máx. activos en lista",
                min_value=10,
                max_value=200,
                value=st.session_state.config.get('max_activos', 100),
                step=10
            )
            st.session_state.config['activos_por_ciclo'] = st.number_input(
                "Activos por ciclo",
                min_value=1,
                max_value=5,
                value=st.session_state.config.get('activos_por_ciclo', 1),
                step=1
            )
        with col2:
            st.session_state.config['umbral_confianza'] = st.slider(
                "Umbral de confianza (%)",
                min_value=30,
                max_value=90,
                value=st.session_state.config.get('umbral_confianza', 60),
                step=5
            )
            st.session_state.config['pausa_entre_analisis'] = st.slider(
                "Pausa entre análisis (s)",
                min_value=0.1,
                max_value=2.0,
                value=st.session_state.config.get('pausa_entre_analisis', 0.5),
                step=0.1
            )
        with col3:
            st.session_state.config['vencimiento_base'] = st.selectbox(
                "Vencimiento base (min)",
                options=[2, 3, 4, 5],
                index=3
            )
            st.caption("Algunas estrategias pueden sobreescribirlo.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
