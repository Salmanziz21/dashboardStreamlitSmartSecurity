# ============================================================
#   STREAMLIT MQTT UI — PREMIUM EDITION (Super Clean Aesthetic)
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

# ===============================
# CONFIG
# ===============================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_SENSOR = "esp32/motion/datasensor"
TOPIC_PRED = "esp32/motion/prediction"
HISTORY_MAX = 2000

DEFAULT_REFRESH_MS = 1000

# ===============================
# SESSION STORAGE
# ===============================
if "mqtt_storage" not in st.session_state:
    st.session_state.mqtt_storage = {
        "sensors": deque(maxlen=HISTORY_MAX),
        "predictions": deque(maxlen=HISTORY_MAX),
        "last_sensor": None,
        "last_prediction": None,
        "connected": False,
        "client": None,
        "last_update": None
    }

storage = st.session_state.mqtt_storage


# ===============================
# MQTT CALLBACKS
# ===============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        storage["connected"] = True
        client.subscribe([(TOPIC_SENSOR, 0), (TOPIC_PRED, 0)])
    else:
        storage["connected"] = False


def parse_sensor_payload(payload_str):
    try:
        data = json.loads(payload_str)
        ts = datetime.now()
        return {
            "timestamp": ts,
            "pir_value": int(data.get("pir_value", 0)),
            "hour": int(data.get("hour", ts.hour)),
            "is_night": int(data.get("is_night", 0))
        }
    except:
        return None


def parse_prediction_payload(payload_str):
    try:
        d = json.loads(payload_str)
        if isinstance(d, dict):
            if "prediction" in d:
                label = d["prediction"].get("label")
                conf = d["prediction"].get("confidence")
                return {"timestamp": datetime.now(), "label": label, "confidence": conf}
            elif "label" in d:
                return {"timestamp": datetime.now(), "label": d["label"], "confidence": d.get("confidence")}
    except:
        mapping = {
            "NO MOTION DETECT": "no_motion",
            "NORMAL MOTION DETECT": "normal_motion",
            "SUSPICIOUS MOTION DETECT": "suspicious_motion"
        }
        t = payload_str.strip().upper()
        return {"timestamp": datetime.now(), "label": mapping.get(t, t.lower()), "confidence": None}


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore")

    if msg.topic == TOPIC_SENSOR:
        item = parse_sensor_payload(payload)
        if item:
            storage["sensors"].append(item)
            storage["last_sensor"] = item
            storage["last_update"] = datetime.now()

    elif msg.topic == TOPIC_PRED:
        pred = parse_prediction_payload(payload)
        if pred:
            storage["predictions"].append(pred)
            storage["last_prediction"] = pred
            storage["last_update"] = datetime.now()


# ===============================
# MQTT BACKGROUND THREAD
# ===============================
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except:
        storage["connected"] = False
        return

    storage["client"] = client
    client.loop_start()


if storage.get("client") is None:
    threading.Thread(target=start_mqtt, daemon=True).start()
    time.sleep(0.4)


# ============================================================
# ================     PREMIUM UI SECTION     ================
# ============================================================

st.set_page_config(page_title="ESP32 Motion Dashboard", layout="wide")

st.markdown("""
<style>
body {
    background-color: #0e1117;
    color: white;
}
.card {
    background: #161b22;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #2d333b;
    box-shadow: 0 4px 15px rgba(0,0,0,0.45);
}
.metric-title {
    font-size: 18px;
    font-weight: 600;
    color: #9da5b4;
}
.metric-value {
    font-size: 36px;
    font-weight: 700;
    margin-top: -10px;
}
.header {
    background: linear-gradient(90deg, #0ea5e9, #6366f1);
    padding: 22px;
    border-radius: 14px;
    margin-bottom: 18px;
    color: white;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
table {
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class='header'>
    <h1>📡 ESP32 AI MOTION DASHBOARD — Premium Edition</h1>
    <p>Realtime Monitoring, Prediction Tracking, Clean Aesthetic Design</p>
</div>
""", unsafe_allow_html=True)

st_autorefresh(interval=DEFAULT_REFRESH_MS)


# ============================================================
# TOP METRICS
# ============================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("<div class='card metric-title'>🕒 Last Update</div>", unsafe_allow_html=True)
    if storage["last_update"]:
        st.markdown(f"<div class='card metric-value'>{storage['last_update'].strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='card metric-value'>—</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='card metric-title'>🔌 MQTT Status</div>", unsafe_allow_html=True)
    status = "🟢 Connected" if storage.get("connected") else "🔴 Disconnected"
    st.markdown(f"<div class='card metric-value'>{status}</div>", unsafe_allow_html=True)

with col3:
    st.markdown("<div class='card metric-title'>📊 Sensor Records</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='card metric-value'>{len(storage['sensors'])}</div>", unsafe_allow_html=True)

with col4:
    st.markdown("<div class='card metric-title'>🧠 Predictions</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='card metric-value'>{len(storage['predictions'])}</div>", unsafe_allow_html=True)


st.markdown("---")

# ============================================================
# CONTENT
# ============================================================

left, right = st.columns([2.2, 1.2])

# ----------------- LEFT SIDE -----------------
with left:
    st.subheader("📍 Latest Sensor")
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    if storage["last_sensor"]:
        s = storage["last_sensor"]
        st.write(f"**pir_value:** `{s['pir_value']}`")
        st.write(f"**hour:** `{s['hour']}`")
        st.write(f"**is_night:** `{s['is_night']}`")
        st.write(f"⏱ `{s['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}`")
    else:
        st.info("Belum ada data sensor.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("🧠 Latest Prediction")
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    if storage["last_prediction"]:
        p = storage["last_prediction"]
        st.write(f"**Label:** `{p['label']}`")
        st.write(f"**Confidence:** `{p['confidence']}`")
        st.write(f"⏱ `{p['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}`")
    else:
        st.info("Belum ada prediksi.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("📈 Grafik PIR (Realtime)")
    if len(storage["sensors"]) > 0:
        df = pd.DataFrame(storage["sensors"])[["timestamp", "pir_value"]]
        df = df.set_index("timestamp").tail(400)
        st.line_chart(df, height=300)
    else:
        st.info("Menunggu data...")

    st.subheader("⏳ Timeline Events")
    events = []

    for s in storage["sensors"]:
        events.append({"time": s["timestamp"], "event": f"PIR={s['pir_value']}"})

    for p in storage["predictions"]:
        events.append({"time": p["timestamp"], "event": f"PRED={p['label']}"})

    if events:
        df_event = pd.DataFrame(events).sort_values("time").tail(200)
        st.dataframe(df_event, use_container_width=True)
    else:
        st.info("Belum ada event.")


# ----------------- RIGHT SIDE -----------------
with right:
    st.subheader("📥 Export Data")
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    if len(storage["sensors"]) > 0:
        df_all = pd.DataFrame(storage["sensors"])
        df_all["timestamp"] = df_all["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        csv = df_all.to_csv(index=False).encode()
        st.download_button("Download CSV Sensor", csv, "sensor_data.csv")
    else:
        st.write("Tidak ada data.")

    st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("🔍 Quick Filter")
    if st.button("Tampilkan 10 Sensor Terakhir"):
        last10 = list(storage["sensors"])[-10:]
        st.table(pd.DataFrame(last10))

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# FOOTER
# ============================================================

st.markdown("""
---
<div style='text-align:center; opacity:0.6'>
Made with ❤️ — Premium Dashboard Edition
</div>
""", unsafe_allow_html=True)
