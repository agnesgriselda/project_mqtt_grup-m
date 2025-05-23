#  Proyek Sistem Pemantauan dan Kontrol Berbasis MQTT (Grup M)

Ini adalah proyek sederhana untuk mendemonstrasikan penggunaan protokol **MQTT** dalam membangun sistem **pemantauan suhu** dan **kontrol lampu**. Proyek ini melibatkan tiga komponen utama: **sensor suhu**, **lampu pintar virtual**, dan **panel kontrol**, yang semuanya berkomunikasi melalui **MQTT broker**.

---

##  Deskripsi Proyek

Sistem ini bertujuan untuk:

1. **Memantau Suhu:**  
   Sensor virtual secara periodik mengirimkan data suhu ke topik MQTT.
2. **Kontrol Lampu:**  
   Lampu pintar mendengarkan perintah ON/OFF dari topik MQTT dan mempublikasikan statusnya.
3. **Panel Kontrol:**  
   Aplikasi konsol yang:
   - Menampilkan data suhu dan status lampu.
   - Mengirim perintah ON/OFF ke lampu.
   - Memantau status online/offline sensor dan lampu.

###  Fitur MQTT yang Diimplementasikan:

- Publish-Subscribe
- QoS level 0, 1, 2 (default: QoS 2)
- Retained Messages
- Last Will and Testament (LWT)

---

##  Struktur Direktori

```
project-mqtt-sederhana/
├── sensor/                 # Sensor suhu virtual
│   └── sensor_client.py
├── lamp/                   # Lampu pintar virtual
│   └── lamp_client.py
├── control_panel/          # Aplikasi panel kontrol
│   └── panel_client.py
├── config/                 # Konfigurasi MQTT
│   └── settings.json
├── common/                 # Utilitas bersama
│   ├── __init__.py
│   └── mqtt_utils.py
├── venv/                   # Virtual Environment (tidak perlu di-commit)
├── .gitignore
├── requirements.txt        # Dependensi Python
└── README.md
```

---

##  Prasyarat

- Python 3.7+
- MQTT Broker (default: `test.mosquitto.org:1883`)
- Virtual environment (disarankan)

---

##  Setup & Instalasi

### 1. Kloning Repositori
```bash
git clone https://github.com/agnesgriselda/project_mqtt_grup-m.git
cd project_mqtt_grup-m
```

### 2. Buat & Aktifkan Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Instal Dependensi
```bash
pip install -r requirements.txt
```

---

##  Konfigurasi

Edit file `config/settings.json` untuk menyesuaikan pengaturan broker dan topik MQTT.

Contoh:
```json
{
  "broker_address": "test.mosquitto.org",
  "broker_port": 1883,
  "client_id_prefix": "my_simple_mqtt_app_",
  "topics": {
    "temperature": "iot/tutorial/python/temperature_qos2_test",
    "lamp_command": "iot/tutorial/python/lamp/command_qos2_test",
    "lamp_status": "iot/tutorial/python/lamp/status_qos2_test",
    "sensor_lwt": "iot/tutorial/python/sensor/lwt_status",
    "lamp_lwt": "iot/tutorial/python/lamp/lwt_status"
  },
  "default_qos": 2,
  "lwt_qos": 1,
  "lwt_retain": true
}
```

---

##  Cara Menjalankan Aplikasi

> Buka **3 terminal terpisah**, aktifkan virtual environment di masing-masing.

### 1. Terminal Panel Kontrol
```bash
python control_panel/panel_client.py
```

### 2. Terminal Sensor Suhu
```bash
python sensor/sensor_client.py
```

### 3. Terminal Lampu Pintar
```bash
python lamp/lamp_client.py
```

### Interaksi

- Ketik `ON` atau `OFF` di terminal panel untuk mengendalikan lampu.
- Panel akan menampilkan status suhu, lampu, dan konektivitas perangkat.

---

## Uji Last Will and Testament (LWT)

- **Uji perangkat offline mendadak:**
  1. Jalankan semua klien.
  2. Tutup paksa terminal **sensor/lampu** (jangan pakai Ctrl+C).
  3. Panel akan menerima pesan LWT ("offline_unexpected").

- **Uji shutdown normal:**
  1. Tekan Ctrl+C di terminal sensor/lampu.
  2. Panel akan menerima status "offline_graceful", bukan LWT.

---

## Dibuat oleh: Grup M

> Proyek ini dibuat sebagai bagian dari pembelajaran protokol komunikasi IoT berbasis MQTT dengan pendekatan sistem modular dan penggunaan broker publik.
