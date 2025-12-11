# app.py
import streamlit as st
import threading
import time
import json
from collections import deque
from datetime import datetime
import pandas as pd
import paho.mqtt.client as mqtt

# ---------------------------
# CONFIG
# ---------------------------
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_SENSOR = "esp32/motion/datasensor"
TOPIC_PRED = "esp32/motion/prediction"

HISTORY_MAX = 1000  # jumlah maksimum record historis yang disimpan

# ---------------------------
# SHARED STORAGE (thread-safe-ish)
# ---------------------------
if "mqtt_storage" not in st.session_state:
    st.session_state.mqtt_storage = {
        "sensors": deque(maxlen=HISTORY_MAX),      # each item: {timestamp: dt, pir_value:int, hour:int, is_night:int}
        "predictions": deque(maxlen=HISTORY_MAX),  # each item: {timestamp: dt, label:str, confidence: float (0-100) or None}
        "last_sensor": None,
        "last_prediction": None,
        "connected": False,
        "client": None
    }

storage = st.session_state.mqtt_storage

# ---------------------------
# MQTT CALLBACKS
# ---------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.connected_flag = True
        storage["connected"] = True
        client.subscribe([(TOPIC_SENSOR, 0), (TOPIC_PRED, 0)])
        print("MQTT connected, subscribed to topics.")
    else:
        storage["connected"] = False
        print("MQTT failed to connect, rc:", rc)

def parse_sensor_payload(payload_str):
    try:
        data = json.loads(payload_str)
        # handle if timestamp is millis from Arduino; convert to datetime now if not present or not usable
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            # assume millis since device started — better to use server time
            dt = datetime.now()
        else:
            dt = datetime.now()
        item = {
            "timestamp": dt,
            "pir_value": int(data.get("pir_value", 0)),
            "hour": int(data.get("hour", dt.hour)),
            "is_night": int(data.get("is_night", 0))
        }
        return item
    except Exception as e:
        print("parse_sensor_payload error:", e)
        return None

def parse_prediction_payload(payload_str):
    # payload might be plain text like "NO MOTION DETECT" or it might be JSON
    try:
        # try JSON first
        data = json.loads(payload_str)
        label = None
        confidence = None
        # Common shapes:
        # { "prediction": {"label": "...", "confidence": 90.0, ...}, "timestamp":... }
        if isinstance(data, dict):
            if "prediction" in data and isinstance(data["prediction"], dict):
                label = data["prediction"].get("label")
                confidence = data["prediction"].get("confidence")
            elif "label" in data:
                label = data.get("label")
                confidence = data.get("confidence")
        if label is not None:
            return {"timestamp": datetime.now(), "label": str(label), "confidence": float(confidence) if confidence is not None else None}
    except Exception:
        # not JSON, treat payload as plain text
        text = payload_str.strip()
        # Normalize known mapping used in your publisher
        mapping = {
            "NO MOTION DETECT": "no_motion",
            "NORMAL MOTION DETECT": "normal_motion",
            "SUSPICIOUS MOTION DETECT": "suspicious_motion"
        }
        label = mapping.get(text.upper(), text.lower().replace(" ", "_"))
        return {"timestamp": datetime.now(), "label": label, "confidence": None}

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="ignore")
    except Exception as e:
        print("Failed decode payload:", e)
        return

    topic = msg.topic
    # sensor topic -> JSON
    if topic == TOPIC_SENSOR:
        item = parse_sensor_payload(payload)
        if item:
            storage["sensors"].append(item)
            storage["last_sensor"] = item
    elif topic == TOPIC_PRED:
        pred = parse_prediction_payload(payload)
        if pred:
            storage["predictions"].append(pred)
            storage["last_prediction"] = pred

# ---------------------------
# MQTT CLIENT THREAD
# ---------------------------
def start_mqtt_client():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connected_flag = False
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        print("MQTT connect error:", e)
        storage["connected"] = False
        return
    storage["client"] = client

    # run loop forever in background thread
    client.loop_start()

# Launch MQTT client once
if storage.get("client") is None:
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    # give small time to attempt connection
    time.sleep(0.5)

# ---------------------------
# STREAMLIT UI
# ---------------------------
st.set_page_config(page_title="ESP32 Motion Dashboard", layout="wide", initial_sidebar_state="expanded")

st.title("📡 ESP32 Motion — Dashboard (MQTT real-time)")
st.markdown("Dashboard ini menampilkan **data sensor real-time**, **hasil prediksi model**, dan **grafik historis**.\n\nSource: MQTT topics `esp32/motion/datasensor` & `esp32/motion/prediction`.")

# Sidebar: connection info & controls
with st.sidebar:
    st.header("Koneksi MQTT")
    conn_status = "Terhubung" if storage["connected"] else "Terputus"
    st.write(f"Broker: `{MQTT_BROKER}:{MQTT_PORT}`")
    st.write(f"Status: **{conn_status}**")
    st.write("Subscribed topics:")
    st.code(TOPIC_SENSOR)
    st.code(TOPIC_PRED)
    st.markdown("---")
    st.write("Pengaturan tampilan:")
    max_points = st.slider("Jumlah titik historis pada chart", min_value=50, max_value=HISTORY_MAX, value=300, step=50)
    if st.button("Hapus history lokal"):
        storage["sensors"].clear()
        storage["predictions"].clear()
        storage["last_sensor"] = None
        storage["last_prediction"] = None
        st.success("History dibersihkan")

# Main layout: three columns
col1, col2, col3 = st.columns([1.2, 1.2, 1.0])

# Latest sensor metrics
with col1:
    st.subheader("Latest Sensor (real-time)")
    last = storage["last_sensor"]
    if last:
        st.metric("pir_value", last["pir_value"])
        st.metric("hour", last["hour"], delta=None)
        st.metric("is_night", last["is_night"])
        st.write("Terakhir diterima:", last["timestamp"].strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.info("Belum ada data sensor diterima.")

    # show small table of recent sensor rows
    st.markdown("**Recent sensor rows**")
    sensors_list = list(storage["sensors"])[-10:][::-1]
    if sensors_list:
        df_recent = pd.DataFrame([{
            "time": s["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "pir_value": s["pir_value"],
            "hour": s["hour"],
            "is_night": s["is_night"]
        } for s in sensors_list])
        st.dataframe(df_recent, height=220)
    else:
        st.write("—")

# Latest prediction
with col2:
    st.subheader("Latest Prediction (real-time)")
    lastp = storage["last_prediction"]
    if lastp:
        st.metric("Label", lastp["label"])
        conf_text = f"{lastp['confidence']:.2f}%" if lastp.get("confidence") is not None else "N/A"
        st.metric("Confidence", conf_text)
        st.write("Terakhir diterima:", lastp["timestamp"].strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.info("Belum ada prediksi diterima.")

    # small list of last predictions
    st.markdown("**Recent predictions**")
    preds_list = list(storage["predictions"])[-10:][::-1]
    if preds_list:
        dfp = pd.DataFrame([{
            "time": p["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "label": p["label"],
            "confidence": (p["confidence"] if p["confidence"] is not None else "")
        } for p in preds_list])
        st.dataframe(dfp, height=220)
    else:
        st.write("—")

# Historical chart & controls
with col3:
    st.subheader("Kontrol & Export")
    st.write("Download data historis (CSV)")
    if len(storage["sensors"]) > 0:
        df_all = pd.DataFrame([{
            "timestamp": s["timestamp"],
            "pir_value": s["pir_value"],
            "hour": s["hour"],
            "is_night": s["is_night"]
        } for s in list(storage["sensors"])])

        csv = df_all.to_csv(index=False).encode("utf-8")
        st.download_button("Download sensor CSV", csv, "sensors_history.csv", "text/csv")
    else:
        st.write("Belum ada data untuk di-export")

    st.markdown("---")
    st.write("Informasi koneksi MQTT:")
    st.write(f"- Client aktif: {'Ya' if storage.get('client') else 'Tidak'}")
    st.write("- Jika tidak terhubung: periksa koneksi internet atau broker.")

# Full-width historical chart
st.markdown("## 📈 Grafik Historis")
st.markdown("Grafik menampilkan `pir_value` sepanjang waktu (data server time saat diterima).")

# Build DataFrame for plotting
if len(storage["sensors"]) == 0:
    st.info("Menunggu data sensor... pastikan ESP32 mengirim ke topic yang benar.")
else:
    df = pd.DataFrame([{"timestamp": s["timestamp"], "pir_value": s["pir_value"]} for s in storage["sensors"]])
    df = df.sort_values("timestamp").tail(max_points)
    df_plot = df.set_index("timestamp")
    st.line_chart(df_plot["pir_value"])

# Optional: show combined timeline of predictions overlay (simple)
st.markdown("### Timeline gabungan (Sensor + Prediksi)")
if len(storage["sensors"]) == 0 and len(storage["predictions"]) == 0:
    st.write("Belum ada data.")
else:
    # create combined table of events
    events = []
    for s in storage["sensors"]:
        events.append({"time": s["timestamp"], "type":"sensor", "value": s["pir_value"], "detail": ""})
    for p in storage["predictions"]:
        events.append({"time": p["timestamp"], "type":"prediction", "value": None, "detail": p["label"]})
    df_events = pd.DataFrame(events).sort_values("time").tail(200)
    # show last 50 events table
    st.dataframe(df_events.tail(50), height=280)

# Auto refresh small: use st.experimental_rerun with timer is heavy; we can ask user to use the button to start live updates
st.markdown("---")
cola, colb = st.columns([1,3])
with cola:
    if st.button("Refresh sekarang"):
        st.experimental_rerun()
with colb:
    st.write("Untuk tampilan 'live', gunakan tombol Refresh sekarang sesekali atau deploy ke Streamlit Cloud yang akan mempertahankan loop MQTT di server.")

st.markdown("**Catatan**: UI ini mengambil waktu server ketika pesan diterima. Jika Anda ingin sinkron waktu device, ubah payload Arduino agar mengirimkan ISO timestamp.")

st.markdown("---")
st.caption("Dibuat oleh Anda — integrasi Streamlit + MQTT untuk monitoring ESP32 PIR.")

