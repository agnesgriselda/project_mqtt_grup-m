# Proyek Sistem Pemantauan dan Kontrol Cerdas Berbasis MQTT 5.0 (Grup M)

Ini adalah proyek untuk mendemonstrasikan penggunaan protokol **MQTT 5.0** dalam membangun sistem **pemantauan suhu & kelembaban** serta **kontrol lampu pintar**. Proyek ini dirancang dengan pendekatan modular dan aman, melibatkan tiga komponen utama: sensor virtual, lampu pintar virtual, dan panel kontrol, yang berkomunikasi melalui MQTT broker lokal yang diamankan.

---

## Deskripsi Proyek

Sistem ini dirancang untuk menyediakan fungsionalitas berikut secara aman dan andal:

1.  **Pemantauan Lingkungan:**
    *   Sensor virtual secara periodik mempublikasikan data suhu dan kelembaban ke topik MQTT.
    *   Data sensor dikirim sebagai *request* menggunakan pola Request/Response MQTT 5.0, memungkinkan panel untuk mengirim *acknowledgment*.
2.  **Kontrol Perangkat Cerdas (Lampu):**
    *   Lampu pintar virtual mendengarkan perintah (ON, OFF, TOGGLE) dari topik MQTT.
    *   Panel mengirim perintah ke lampu menggunakan pola Request/Response MQTT 5.0, sehingga lampu dapat memberikan konfirmasi atau status error kembali ke panel.
    *   Lampu juga mempublikasikan status terkininya (menyala/mati) ke topik status reguler dengan Retained Message.
3.  **Panel Kontrol Terpusat:**
    *   Aplikasi konsol interaktif yang berfungsi sebagai dashboard dan pusat kendali:
        *   Menampilkan data suhu dan kelembaban terkini.
        *   Menampilkan status lampu pintar (ON/OFF).
        *   Memungkinkan pengguna mengirim perintah untuk mengendalikan lampu.
        *   Memantau status konektivitas (ONLINE, OFFLINE_UNEXPECTED, OFFLINE_GRACEFUL) dari sensor dan lampu menggunakan Last Will and Testament (LWT) dan pesan status eksplisit.
4.  **Keamanan Komunikasi:**
    *   Semua komunikasi dengan broker MQTT lokal diamankan menggunakan **TLS (enkripsi)**.
    *   Koneksi klien ke broker MQTT lokal diwajibkan menggunakan **Autentikasi Username/Password**.

### Fitur MQTT yang Diimplementasikan:

*   **Protokol MQTT Versi 5.0** beserta fitur-fitur spesifiknya.
*   **Pola Publish-Subscribe** sebagai dasar komunikasi.
*   **Quality of Service (QoS):** Penggunaan QoS level 0, 1, dan 2 (default dikonfigurasi untuk QoS tinggi, misal QoS 1 atau 2 untuk data penting dan perintah).
*   **Retained Messages:** Digunakan untuk memastikan status terakhir perangkat (misalnya, status lampu ON/OFF, status konektivitas "online") langsung tersedia bagi klien yang baru terhubung.
*   **Last Will and Testament (LWT):** Setiap perangkat (sensor, lampu, panel) mendaftarkan LWT untuk memberitahukan status "offline_unexpected" jika koneksi terputus secara tidak normal. Status "online" dan "offline_graceful" juga dipublikasikan ke topik LWT.
*   **MQTT Secure (TLS/SSL):** Enkripsi end-to-end antara klien dan broker MQTT lokal menggunakan sertifikat self-signed untuk lingkungan pengembangan.
*   **Authentication:** Klien diwajibkan menggunakan username dan password untuk terhubung ke broker MQTT lokal.
*   **MQTT 5.0 Properties:**
    *   **Message Expiry Interval:** Pesan dapat dikonfigurasi untuk kadaluarsa setelah periode tertentu jika tidak terkirim ke subscriber.
    *   **Request/Response Pattern:** Diimplementasikan menggunakan properti `ResponseTopic` dan `CorrelationData` untuk komunikasi dua arah yang lebih sinkron antara sensor-panel dan panel-lampu.
    *   **User Properties:** Digunakan untuk mengirim metadata tambahan bersama pesan (misalnya, tipe sensor, sumber perintah).
    *   **Content Type:** Menandakan tipe payload (misalnya, `application/json`).
    *   **Reason Code & Reason String (on Disconnect):** Memberikan informasi lebih detail saat klien disconnect.
*   **Modularitas Kode:** Penggunaan `common/mqtt_utils.py` untuk abstraksi logika koneksi dan publish/subscribe MQTT.

---

## Struktur Direktori

```
PROJECT_MQTT_GRUP-M/
├── certs/                    # Sertifikat (myca.pem untuk klien, mosquitto.org.crt opsional)
│   ├── myca.pem
│   └── mosquitto.org.crt
├── common/                   # Utilitas bersama Python
│   ├── __init__.py
│   └── mqtt_utils.py
├── config/                   # File konfigurasi proyek
│   └── settings.json
├── control_panel/            # Logika untuk aplikasi panel kontrol
│   └── panel_client.py
├── lamp/                     # Logika untuk perangkat lampu pintar virtual
│   └── lamp_client.py
├── sensor/                   # Logika untuk perangkat sensor suhu & kelembaban virtual
│   └── sensor_client.py
├── venv/                     # Direktori Virtual Environment (diabaikan oleh .gitignore)
├── .vscode/                  # Pengaturan VS Code (opsional, settings.json bisa di-commit)
│   └── settings.json
├── .gitignore                # File dan folder yang diabaikan oleh Git
├── README.md                 # File ini
└── requirements.txt          # Dependensi Python
```
*(Asumsi folder `D:\mosquitto\` atau lokasi instalasi Mosquitto lainnya berisi file sertifikat server/kunci privatnya, yang TIDAK di-commit ke repo ini).*

---

## Prasyarat

*   Python 3.8 atau lebih tinggi.
*   `pip` (Python package installer).
*   Git (untuk kloning repository).
*   **Mosquitto MQTT Broker** terinstal dan berjalan secara lokal.
*   **OpenSSL** terinstal (untuk membuat sertifikat jika ingin setup dari awal).

---

## Setup & Instalasi

### 1. Kloning Repositori
```bash
git clone https://github.com/agnesgriselda/project_mqtt_grup-m.git
cd project_mqtt_grup-m
```

### 2. Buat & Aktifkan Virtual Environment
```bash
python -m venv venv
# Windows (Command Prompt/PowerShell):
venv\Scripts\activate
# macOS/Linux (Bash/Zsh):
source venv/bin/activate
```
*(Kamu akan melihat `(venv)` di awal prompt terminalmu).*

### 3. Instal Dependensi Python
Pastikan virtual environment sudah aktif, kemudian jalankan:
```bash
pip install -r requirements.txt
```
Ini akan menginstal `paho-mqtt`.

### 4. Setup Broker Mosquitto Lokal (Wajib untuk Autentikasi & TLS Lokal)

Proyek ini dirancang untuk berjalan dengan broker Mosquitto lokal yang diamankan dengan Autentikasi dan TLS.

*   **Instal Mosquitto:** Ikuti panduan instalasi Mosquitto untuk OS-mu.
*   **Buat Sertifikat Self-Signed (jika belum ada):**
    1.  Gunakan OpenSSL untuk membuat CA pribadi (`myca.key`, `myca.pem`) dan sertifikat server (`mosquitto_server.key`, `mosquitto_server.crt` yang ditandatangani oleh `myca.pem` dengan **Common Name `localhost`**). Simpan file-file ini di direktori yang aman di luar folder proyek ini (misalnya, di direktori instalasi Mosquitto).
    2.  **Salin `myca.pem` (sertifikat publik CA) ke folder `certs/` di dalam proyek Python ini.**
*   **Buat File Password Mosquitto:**
    ```bash
    # Navigasi ke direktori instalasi Mosquitto (misal D:\mosquitto)
    # Ganti user_mqtt_kita dan passwordnya sesuai keinginan
    mosquitto_passwd -c pwfile user_mqtt_kita 
    ```
*   **Konfigurasi `mosquitto.conf`:**
    Pastikan file `mosquitto.conf` (biasanya di direktori instalasi Mosquitto) berisi:
    ```conf
    allow_anonymous false
    password_file D:/path/ke/pwfile # Sesuaikan path dan nama file password

    # listener 1883 # Opsional, untuk koneksi tanpa TLS jika diperlukan

    listener 8883
    protocol mqtt
    cafile D:/path/ke/certs_local/myca.pem
    certfile D:/path/ke/certs_local/mosquitto_server.crt
    keyfile D:/path/ke/certs_local/mosquitto_server.key
    require_certificate false 
    ```
    Ganti `D:/path/ke/` dengan path absolut yang benar ke file-file tersebut di sistemmu.

### 5. Konfigurasi Proyek Python

Edit file `config/settings.json` di dalam proyek Python. Pastikan konfigurasinya sesuai untuk koneksi ke broker lokalmu dengan Auth + TLS:
```json
{
    "broker_address": "localhost",
    "client_id_prefix": "my_secure_local_app_",
    "topics": {
        "temperature": "iot/project/temperature_m5_test",
        "lamp_command": "iot/project/lamp/command_m5",
        "lamp_status": "iot/project/lamp/status_m5",
        "sensor_lwt": "iot/project/sensor/lwt_m5",
        "lamp_lwt": "iot/project/lamp/lwt_m5",
        "humidity_data": "iot/project/humidity_data_m5",
        "panel_lwt": "iot/project/panel/lwt_m5",
        "temperature_response_base": "iot/project/temperature/response_m5/",
        "lamp_command_response_base": "iot/project/lamp/command/response_m5/"
    },
    "default_qos": 1,
    "lwt_qos": 1,
    "lwt_retain": true,
    "mqtt_advanced_settings": {
        "port_tls": 8883,
        "use_tls": true,
        "ca_cert_path": "certs/myca.pem",
        "use_auth": true,
        "username": "user_mqtt_kita",     
        "password": "password_anda",      
        "keepalive": 60,
        "v5_receive_maximum": 10,
        "default_message_expiry_interval": 10 
    },
    "panel_specific_settings": {
        "subscribed_topics_list": [ 
            "iot/project/temperature_m5_test",
            "iot/project/lamp/status_m5",
            "iot/project/humidity_data_m5",
            "iot/project/sensor/lwt_m5",
            "iot/project/lamp/lwt_m5"
        ]
    }
}
```
Ganti `"user_mqtt_kita"` dan `"password_anda"` dengan kredensial Mosquitto yang kamu buat. Sesuaikan nama topik jika perlu.

---

## Cara Menjalankan Aplikasi

> Buka **minimal 4 terminal terpisah** (1 untuk Mosquitto, 3 untuk klien Python). Pastikan virtual environment diaktifkan di terminal klien Python.

### 1. Terminal A: Jalankan Broker Mosquitto Lokal
```bash
# Navigasi ke direktori instalasi Mosquitto (misal D:\mosquitto)
.\mosquitto.exe -c mosquitto.conf -v 
# (Gunakan ./mosquitto di PowerShell atau mosquitto di cmd biasa)
```
Pastikan Mosquitto berjalan tanpa error dan listening di port 8883.

### 2. Terminal B: Jalankan Panel Kontrol
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python control_panel/panel_client.py
```
Panel akan terhubung dan menampilkan dashboard awal.

### 3. Terminal C: Jalankan Sensor Suhu & Kelembaban
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python sensor/sensor_client.py
```
Sensor akan terhubung, mengirim status "online", dan mulai mempublikasikan data. Panel akan menampilkan update.

### 4. Terminal D: Jalankan Lampu Pintar
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python lamp/lamp_client.py
```
Lampu akan terhubung, mengirim status "online", mengirim status ON/OFF awalnya, dan menunggu perintah. Panel akan menampilkan update.

### Interaksi dan Pengujian Fitur

*   **Kontrol Lampu:** Di terminal **Panel Kontrol**, ketik `ON`, `OFF`, `TOGGLE` untuk mengendalikan lampu. Coba juga kirim perintah tidak valid seperti `INVALIDCMD` untuk melihat respons error dari lampu.
*   **Data Sensor:** Amati panel menerima data suhu dan kelembaban dari sensor.
*   **Request/Response:** Perhatikan log di sensor dan panel yang menunjukkan pengiriman data suhu sebagai request dan penerimaan acknowledgment. Perhatikan juga log di panel dan lampu saat mengirim perintah lampu dan menerima konfirmasi atau error.
*   **Message Expiry:**
    1.  Hentikan panel.
    2.  Biarkan sensor mengirim beberapa pesan (dengan expiry sesuai `default_message_expiry_interval`). Hentikan sensor.
    3.  Tunggu lebih lama dari interval expiry tersebut.
    4.  Jalankan panel lagi. Panel **tidak** boleh menerima data suhu lama.
*   **Last Will and Testament (LWT):**
    *   **Crash Test:** Tutup paksa terminal sensor atau lampu (jangan pakai Ctrl+C). Panel akan menerima pesan LWT `status: "offline_unexpected"`.
    *   **Normal Shutdown:** Hentikan sensor atau lampu dengan `Ctrl+C`. Panel akan menerima pesan `status: "offline_graceful"`.
*   **Keamanan:** Semua komunikasi ini sekarang berjalan melalui koneksi TLS terenkripsi dan memerlukan autentikasi.

---

## Dibuat oleh: Grup M
