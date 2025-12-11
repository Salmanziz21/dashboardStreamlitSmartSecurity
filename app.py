# ============================================================
#   STREAMLIT MQTT UI — PREMIUM EDITION (Super Clean Aesthetic)
#   + IMAGE (ESP32-CAM) SUPPORT (topic: esp32/motion/gambar)
#   + TIMEZONE INDONESIA (WIB)
# ============================================================

import streamlit as st
import threading
import time
import json
from collections import deque
from datetime import datetime
import pandas as pd
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

# image handling
import base64
from PIL import Image
import io

# timezone
from zoneinfo import ZoneInfo

# ===============================
# CONFIG
# ===============================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_SENSOR = "esp32/motion/datasensor"
TOPIC_PRED = "esp32/motion/prediction"
TOPIC_GAMBAR = "esp32/motion/gambar"   # topic gambar (base64)
HISTORY_MAX = 2000
DEFAULT_REFRESH_MS = 1000  # ms for auto refresh
TIMEZONE = ZoneInfo("Asia/Jakarta")   # WIB

# ===============================
# SESSION STORAGE
# ===============================
if "mqtt_storage" not in st.session_state:
    st.session_state.mqtt_storage = {
        "sensors": deque(maxlen=HISTORY_MAX),
        "predictions": deque(maxlen=HISTORY_MAX),
        "last_sensor": None,
        "last_prediction": None,
        "last_image": None,         # PIL Image object
        "connected": False,
        "client": None,
        "last_update": None
    }

storage = st.session_state.mqtt_storage

# ===============================
# HELPER FUNCTIONS
# ===============================
def to_wib(dt):
    """Convert datetime to WIB"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(TIMEZONE)

def parse_sensor_payload(payload_str):
    try:
        data = json.loads(payload_str)
        ts = to_wib(datetime.now())
        return {
            "timestamp": ts,
            "pir_value": int(data.get("pir_value", 0)),
            "hour": int(data.get("hour", ts.hour)),
            "is_night": int(data.get("is_night", 0))
        }
    except Exception as e:
        print("parse_sensor_payload error:", e)
        return None

def parse_prediction_payload(payload_str):
    try:
        d = json.loads(payload_str)
        if isinstance(d, dict):
            if "prediction" in d and isinstance(d["prediction"], dict):
                label = d["prediction"].get("label")
                conf = d["prediction"].get("confidence")
                return {"timestamp": to_wib(datetime.now()), "label": label, "confidence": conf}
            elif "label" in d:
                return {"timestamp": to_wib(datetime.now()), "label": d["label"], "confidence": d.get("confidence")}
    except Exception:
        mapping = {
            "NO MOTION DETECT": "no_motion",
            "NORMAL MOTION DETECT": "normal_motion",
            "SUSPICIOUS MOTION DETECT": "suspicious_motion"
        }
        t = payload_str.strip().upper()
        return {"timestamp": to_wib(datetime.now()), "label": mapping.get(t, t.lower()), "confidence": None}

def parse_image_payload(payload_bytes):
    try:
        if isinstance(payload_bytes, bytes):
            b64 = payload_bytes
        else:
            b64 = payload_bytes.encode("utf-8")
        img_bytes = base64.b64decode(b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return image
    except Exception as e:
        print("parse_image_payload error:", e)
        return None

# ===============================
# MQTT CALLBACKS
# ===============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        storage["connected"] = True
        client.subscribe([(TOPIC_SENSOR, 0), (TOPIC_PRED, 0), (TOPIC_GAMBAR, 0)])
        print("MQTT connected and subscribed.")
    else:
        storage["connected"] = False
        print("MQTT connect failed rc=", rc)

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload
        if topic == TOPIC_SENSOR:
            payload_str = payload.decode("utf-8", errors="ignore")
            item = parse_sensor_payload(payload_str)
            if item:
                storage["sensors"].append(item)
                storage["last_sensor"] = item
                storage["last_update"] = to_wib(datetime.now())
        elif topic == TOPIC_PRED:
            payload_str = payload.decode("utf-8", errors="ignore")
            pred = parse_prediction_payload(payload_str)
            if pred:
                storage["predictions"].append(pred)
                storage["last_prediction"] = pred
                storage["last_update"] = to_wib(datetime.now())
        elif topic == TOPIC_GAMBAR:
            img = parse_image_payload(payload)
            if img:
                storage["last_image"] = img
                storage["last_update"] = to_wib(datetime.now())
                print("Received image from MQTT, stored in session_state.")
    except Exception as e:
        print("on_message error:", e)

# ===============================
# MQTT BACKGROUND THREAD
# ===============================
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        print("MQTT connect error:", e)
        storage["connected"] = False
        return
    storage["client"] = client
    client.loop_start()
    print("MQTT loop started.")

if storage.get("client") is None:
    threading.Thread(target=start_mqtt, daemon=True).start()
    time.sleep(0.4)

# ============================================================
# STREAMLIT UI
# ============================================================
st.set_page_config(page_title="ESP32 Motion Dashboard", layout="wide")

st.markdown("""
<style>
body {background-color: #0e1117; color: white;}
.card {background: #161b22; padding: 18px; border-radius: 14px; border: 1px solid #2d333b; box-shadow: 0 4px 15px rgba(0,0,0,0.45); margin-bottom: 10px;}
.metric-title {font-size: 14px; font-weight: 600; color: #9da5b4; margin-bottom: 8px;}
.metric-value {font-size: 28px; font-weight: 700; margin-top: -6px;}
.header {background: linear-gradient(90deg, #0ea5e9, #6366f1); padding: 18px; border-radius: 14px; margin-bottom: 12px; color: white; box-shadow: 0 4px 20px rgba(0,0,0,0.25);}
.small-muted {color: #9da5b4; font-size: 0.9rem;}
.card-image {background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.05)); padding: 10px; border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

st_autorefresh(interval=DEFAULT_REFRESH_MS)

st.markdown(f"""
<div class='header'>
    <h2>📡 ESP32 AI MOTION DASHBOARD — Premium Edition</h2>
    <div class="small-muted">Realtime sensor · model prediction · camera image (ESP32-CAM)</div>
</div>
""", unsafe_allow_html=True)

# --------------------------
# TOP METRICS
# --------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown("<div class='card metric-title'>🕒 Last Update</div>", unsafe_allow_html=True)
    if storage["last_update"]:
        st.markdown(f"<div class='card metric-value'>{storage['last_update'].strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='small-muted'>WIB</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='card metric-value'>—</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='card metric-title'>🔌 MQTT Status</div>", unsafe_allow_html=True)
    status = "🟢 Connected" if storage.get("connected") else "🔴 Disconnected"
    st.markdown(f"<div class='card metric-value'>{status}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='small-muted'>broker: {MQTT_BROKER}:{MQTT_PORT}</div>", unsafe_allow_html=True)

with col3:
    st.markdown("<div class='card metric-title'>📊 Sensor Records</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='card metric-value'>{len(storage['sensors'])}</div>", unsafe_allow_html=True)

with col4:
    st.markdown("<div class='card metric-title'>🧠 Predictions</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='card metric-value'>{len(storage['predictions'])}</div>", unsafe_allow_html=True)

st.markdown("---")

# --------------------------
# MAIN CONTENT
# --------------------------
left, right = st.columns([2.3, 1.0])

# LEFT
with left:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='metric-title'>📍 Latest Sensor</div>", unsafe_allow_html=True)
        if storage["last_sensor"]:
            s = storage["last_sensor"]
            st.markdown(f"<div class='metric-value'>{s['pir_value']}</div>", unsafe_allow_html=True)
            st.write(f"- hour: **{s['hour']}**  \n- is_night: **{s['is_night']}**")
            st.write(f"⏱ `{to_wib(s['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}`")
        else:
            st.info("Belum ada data sensor.")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='metric-title'>🧠 Latest Prediction</div>", unsafe_allow_html=True)
        if storage["last_prediction"]:
            p = storage["last_prediction"]
            conf = f"{p['confidence']:.2f}%" if p.get("confidence") is not None else "N/A"
            st.markdown(f"<div class='metric-value'>{p['label']}</div>", unsafe_allow_html=True)
            st.write(f"- Confidence: **{conf}**")
            st.write(f"⏱ `{to_wib(p['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}`")
        else:
            st.info("Belum ada prediksi.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Chart
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-title'>📈 Grafik PIR (Realtime)</div>", unsafe_allow_html=True)
    if storage["sensors"]:
        df = pd.DataFrame(list(storage["sensors"]))
        df["timestamp"] = df["timestamp"].apply(to_wib)
        df_plot = df[["timestamp", "pir_value"]].set_index("timestamp").tail(400)
        st.line_chart(df_plot, height=300)
    else:
        st.info("Menunggu data sensor...")
    st.markdown("</div>", unsafe_allow_html=True)

    # Timeline
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-title'>⏳ Timeline Events (latest)</div>", unsafe_allow_html=True)
    events = [{"time": to_wib(s['timestamp']), "event": f"PIR={s['pir_value']}"} for s in storage["sensors"]]
    events += [{"time": to_wib(p['timestamp']), "event": f"PRED={p['label']}"} for p in storage["predictions"]]
    if events:
        df_event = pd.DataFrame(events).sort_values("time").tail(200)
        st.dataframe(df_event.reset_index(drop=True), use_container_width=True, height=260)
    else:
        st.info("Belum ada event.")
    st.markdown("</div>", unsafe_allow_html=True)

# RIGHT
with right:
    # Export
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-title'>📥 Export Data</div>", unsafe_allow_html=True)
    if storage["sensors"]:
        df_all = pd.DataFrame(list(storage["sensors"]))
        df_all["timestamp"] = df_all["timestamp"].apply(lambda x: to_wib(x).strftime("%Y-%m-%d %H:%M:%S"))
        csv = df_all.to_csv(index=False).encode()
        st.download_button("Download CSV Sensor", csv, "sensor_data.csv")
    else:
        st.write("Tidak ada data sensor untuk di-export.")
    st.markdown("</div>", unsafe_allow_html=True)

    # Latest image
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-title'>📸 Latest Captured Image</div>", unsafe_allow_html=True)
    if storage.get("last_image"):
        img = storage["last_image"]
        st.image(img, caption="Gambar terbaru dari ESP32-CAM", use_column_width=True)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        st.download_button("Download Image (JPEG)", data=buf.getvalue(),
                           file_name=f"esp32_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                           mime="image/jpeg")
    else:
        st.info("Belum ada gambar dari ESP32-CAM.")
    st.markdown("</div>", unsafe_allow_html=True)

    # Quick filter
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='metric-title'>🔍 Quick Filter</div>", unsafe_allow_html=True)
    if st.button("Tampilkan 10 Sensor Terakhir"):
        last10 = list(storage["sensors"])[-10:]
        if last10:
            st.table(pd.DataFrame(last10))
        else:
            st.write("Tidak ada data.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<div style='text-align:center; opacity:0.6'>Made with ❤️ — Premium Dashboard Edition (WIB + ESP32-CAM)</div>", unsafe_allow_html=True)
