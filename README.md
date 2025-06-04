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

---

### Fitur MQTT yang Diimplementasikan (Ringkasan):

*   **Protokol MQTT Versi 5.0** beserta fitur-fitur spesifiknya.
*   **Pola Publish-Subscribe** sebagai dasar komunikasi.
*   **Quality of Service (QoS):** Penggunaan QoS level 0, 1, dan 2.
*   **Retained Messages:** Untuk status perangkat yang persisten.
*   **Last Will and Testament (LWT):** Untuk deteksi koneksi tak terduga.
*   **MQTT Secure (MQTTS - TLS/SSL):** Enkripsi end-to-end.
*   **Authentication:** Username dan password untuk koneksi klien.
*   **MQTT 5.0 Properties:**
    *   **Message Expiry Interval:** Kadaluarsa pesan.
    *   **Request/Response Pattern:** Komunikasi dua arah sinkron.
    *   **User Properties:** Metadata tambahan.
    *   **Content Type:** Tipe payload.
    *   **Reason Code & Reason String:** Info detail saat disconnect/operasi lain.
    *   **Receive Maximum (Flow Control):** Mengatur aliran pesan dari broker.
*   **Modularitas Kode:** Logika MQTT terpusat di `common/mqtt_utils.py`.

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
    1.  Gunakan OpenSSL untuk membuat CA pribadi (`myca.key`, `myca.pem`) dan sertifikat server (`mosquitto_server.key`, `mosquitto_server.crt` yang ditandatangani oleh `myca.pem` dengan **Common Name `localhost`**). Simpan file-file ini di direktori yang aman di luar folder proyek ini (misalnya, di direktori instalasi Mosquitto). Panduan detail pembuatan sertifikat dapat ditemukan di berbagai tutorial OpenSSL.
    2.  **Salin `myca.pem` (sertifikat publik CA) ke folder `certs/` di dalam proyek Python ini.**
*   **Buat File Password Mosquitto:**
    ```bash
    # Navigasi ke direktori instalasi Mosquitto
    # Ganti user_mqtt_kita dan passwordnya sesuai keinginan
    mosquitto_passwd -c pwfile user_mqtt_kita 
    ```
*   **Konfigurasi `mosquitto.conf`:**
    Pastikan file `mosquitto.conf` (biasanya di direktori instalasi Mosquitto) berisi (sesuaikan path):
    ```conf
    allow_anonymous false
    password_file /path/to/your/pwfile # Ganti dengan path absolut pwfile Anda

    listener 8883
    protocol mqtt
    cafile /path/to/your/certs_local/myca.pem     # Path absolut ke myca.pem di sisi broker
    certfile /path/to/your/certs_local/mosquitto_server.crt # Path absolut
    keyfile /path/to/your/certs_local/mosquitto_server.key  # Path absolut
    require_certificate false 
    ```
    Ganti `/path/to/your/` dengan path absolut yang benar ke file-file tersebut di sistemmu.

### 5. Konfigurasi Proyek Python

Edit file `config/settings.json` di dalam proyek Python.
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
    "sensor_publish_interval": 5, // Interval publish sensor dalam detik
    "mqtt_advanced_settings": {
        "port_tls": 8883,
        "use_tls": true,
        "ca_cert_path": "certs/myca.pem", // Path relatif dari root proyek
        "client_cert_path": null, // Tidak digunakan jika require_certificate false di broker
        "client_key_path": null,  // Tidak digunakan jika require_certificate false di broker
        "use_auth": true,
        "username": "user_mqtt_kita",     // Ganti dengan username Anda
        "password": "password_anda",      // Ganti dengan password Anda
        "keepalive": 60,
        "v5_receive_maximum": 10,
        "default_message_expiry_interval": 30 // Misal, pesan non-retained kadaluarsa setelah 30 detik
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
Ganti `"user_mqtt_kita"` dan `"password_anda"` dengan kredensial Mosquitto yang kamu buat.

---

## Cara Menjalankan Aplikasi

> Buka **minimal 4 terminal terpisah** (1 untuk Mosquitto, 3 untuk klien Python). Pastikan virtual environment diaktifkan di terminal klien Python.

Masuk ke venv dulu
```bash
source venv/bin/activate
```

### 1. Terminal A: Jalankan Broker Mosquitto Lokal
```bash
# Navigasi ke direktori instalasi Mosquitto
mosquitto -c mosquitto.conf -v 
```
Pastikan Mosquitto berjalan tanpa error dan listening di port 8883.
Misalkan sudah berjalan (Error: Address already in use) jalankan `pkill mosquitto`

### 2. Terminal B: Jalankan Panel Kontrol
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python control_panel/panel_client.py
```

### 3. Terminal C: Jalankan Sensor Suhu & Kelembaban
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python sensor/sensor_client.py
```

### 4. Terminal D: Jalankan Lampu Pintar
```bash
# Navigasi ke root direktori proyek PROJECT_MQTT_GRUP-M
# Aktifkan venv
python lamp/lamp_client.py
```
Jalankan (ON/OFF/TOGGLE/INVALID/EXIT) pada terminal Dashboard (panel)
---

## Demonstrasi Fitur MQTT Secara Detail

Berikut adalah cara untuk mendemonstrasikan berbagai fitur MQTT yang telah diimplementasikan dalam proyek ini:

1.  **`mqtt` (Komunikasi Dasar Publish-Subscribe)**
    *   **Implementasi**: Seluruh proyek menggunakan pola publish-subscribe melalui `common/mqtt_utils.py`. Sensor mempublikasikan data, lampu mempublikasikan status, dan panel mempublikasikan perintah serta men-subscribe ke data dan status.
    *   **Demonstrasi**:
        1.  Jalankan semua komponen (Broker, Panel, Sensor, Lampu).
        2.  Amati log di terminal Sensor: `Sensor (...) Publishing Temperature...` dan `Sensor (...) Publishing Humidity...`.
        3.  Amati log di terminal Panel: `[MESSAGE] Panel (...) received on 'iot/project/temperature_m5_test'...` dan `[MESSAGE] Panel (...) received on 'iot/project/humidity_data_m5'...`.
        4.  Amati log di terminal Lampu saat dinyalakan/dimatikan oleh Panel: `Lamp (...) Regular Status Published...`. Panel akan menerima status ini.

2.  **`mqtts` (MQTT Secure dengan TLS/SSL)**
    *   **Implementasi**: Di `config/settings.json`, `"use_tls": true` dan `"port_tls": 8883` mengarahkan `common/mqtt_utils.py` untuk menggunakan `client.tls_set()` dengan `ca_cert_path` yang disediakan. Broker Mosquitto juga dikonfigurasi untuk listener 8883 dengan sertifikat.
    *   **Demonstrasi**:
        1.  Pastikan broker Mosquitto berjalan dengan konfigurasi TLS (listener 8883, `cafile`, `certfile`, `keyfile`).
        2.  Semua klien Python (Panel, Sensor, Lampu) akan terhubung ke port 8883. Komunikasi secara otomatis dienkripsi.
        3.  **Uji Negatif**: Coba ubah `ca_cert_path` di `settings.json` ke file yang salah atau hapus `certs/myca.pem`. Klien akan gagal terhubung karena tidak dapat memverifikasi sertifikat server (error TLS handshake akan muncul di log klien). Atau, jika broker diset `require_certificate true` dan klien tidak menyediakan sertifikat klien yang valid, koneksi juga gagal.

3.  **`authentication` (Autentikasi Username/Password)**
    *   **Implementasi**: Di `config/settings.json`, `"use_auth": true` bersama dengan `"username"` dan `"password"` digunakan oleh `common/mqtt_utils.py` (`client.username_pw_set()`). Broker Mosquitto dikonfigurasi dengan `allow_anonymous false` dan `password_file`.
    *   **Demonstrasi**:
        1.  Pastikan broker berjalan dengan `allow_anonymous false` dan `password_file` yang benar.
        2.  Semua klien Python akan menggunakan username/password dari `settings.json` untuk terhubung.
        3.  **Uji Negatif**: Ubah `"password"` di `settings.json` menjadi salah. Jalankan salah satu klien (misal, `sensor_client.py`). Klien akan gagal terhubung, dan log klien akan menunjukkan `Connection failed (RC: 4)` (Bad username or password) atau `RC: 5` (Not authorised). Log Mosquitto juga akan menunjukkan upaya koneksi yang gagal karena autentikasi.

4.  **`QoS 0,1,2` (Quality of Service)**

    *   **Implementasi**: `common/mqtt_utils.py` memungkinkan pengaturan QoS untuk publish dan LWT. Konfigurasi default (`"default_qos": 1`, `"lwt_qos": 1`) ada di `settings.json`.
    QoS 0: Maksimal kirim 1 kali
    QoS 1 : Minimal kirim 1 kali
    QoS 2 : Kirim 1 kali saja
    *   **Demonstrasi**:
        *   **QoS 1 (Default)**: Pesan LWT, status lampu, data sensor, dan perintah lampu dikirim dengan QoS 1. Ini menjamin pesan setidaknya sampai satu kali. Anda dapat mengamati log broker (dengan level verbose) untuk melihat `PUBACK` dari klien ke broker (untuk publish klien) atau dari broker ke klien (untuk pesan yang diterima klien).
        *   **Mengubah QoS**:
            1.  Ubah `"default_qos"` di `config/settings.json` menjadi `0` atau `2`.
            2.  Restart klien.
            3.  **Untuk QoS 0**: Pengiriman lebih cepat, tidak ada `PUBACK`. Kehilangan pesan mungkin terjadi jika jaringan tidak stabil (sulit disimulasikan di localhost).
            4.  **Untuk QoS 2**: Pengiriman paling andal. Amati log broker (verbose) untuk melihat handshake 4 tahap: `PUBLISH` (dari pengirim), `PUBREC` (dari penerima), `PUBREL` (dari pengirim), `PUBCOMP` (dari penerima). Ini memastikan pesan diterima tepat satu kali.

5.  **`retained msg` (Retained Messages)**
    *   **Implementasi**:
        *   `lamp_client.py`: `publish_regular_lamp_status_v5` mempublikasikan status lampu (ON/OFF) dengan `retain=True`.
        *   `common/mqtt_utils.py`: LWT dipublikasikan dengan `retain=True` (dari `"lwt_retain": true` di `settings.json`), sehingga status konektivitas "online" juga di-retain.
    *   **Demonstrasi**:
        1.  Jalankan Broker, Sensor, dan Lampu. Biarkan mereka mempublikasikan status "online" dan status lampu.
        2.  Hentikan Panel Kontrol.
        3.  Hentikan Sensor dan Lampu.
        4.  Tunggu beberapa detik.
        5.  Jalankan kembali Panel Kontrol. Panel akan **langsung** menampilkan status konektivitas terakhir dari Sensor dan Lampu (misalnya, "OFFLINE_GRACEFUL" atau "ONLINE" jika masih di-retain dari sesi sebelumnya dan tidak dioverwrite LWT) dan status terakhir lampu (misalnya, "ON" atau "OFF"). Ini karena pesan tersebut disimpan oleh broker.

6.  **`expiry` (Message Expiry Interval - MQTT 5.0)**
    *   **Implementasi**: Properti `MessageExpiryInterval` diatur di `common/mqtt_utils.py` untuk pesan yang dipublikasikan, berdasarkan `"default_message_expiry_interval"` (misalnya, 30 detik) di `config/settings.json`.
    *   **Demonstrasi**:
        1.  Pastikan `"default_message_expiry_interval"` di `settings.json` diset ke nilai yang relatif singkat, misal 10 detik.
        2.  Jalankan Broker dan Sensor. Biarkan Sensor mengirim beberapa data suhu/kelembaban.
        3.  Hentikan Panel Kontrol (jika sedang berjalan).
        4.  Biarkan Sensor berjalan selama ~10 detik lagi untuk mempublikasikan beberapa pesan baru, lalu hentikan Sensor.
        5.  Tunggu lebih lama dari interval expiry (misalnya, tunggu 20-25 detik setelah Sensor dihentikan).
        6.  Jalankan Panel Kontrol. Panel **tidak** boleh menerima data suhu/kelembaban lama yang dikirim oleh Sensor sebelum ia dihentikan dan interval expiry berlalu. Panel hanya akan menerima pesan yang masih valid atau pesan retained (seperti LWT).

7.  **`request response` (Pola Request/Response - MQTT 5.0)**
    *   **Implementasi**: Menggunakan properti `ResponseTopic` dan `CorrelationData`.
        *   `sensor_client.py` mengirim data suhu dengan `ResponseTopic` dan `CorrelationData`. `control_panel/panel_client.py` mengirim ACK.
        *   `control_panel/panel_client.py` mengirim perintah lampu dengan `ResponseTopic` dan `CorrelationData`. `lamp_client.py` mengirim konfirmasi/error.
    *   **Demonstrasi**:
        1.  Jalankan semua komponen.
        2.  **Sensor ke Panel**: Amati log Sensor. Ia akan mencetak sesuatu seperti `Subscribed to 'iot/project/temperature/response_m5/<uuid>' for temp response`. Lalu, `Temperature (...) enqueued as REQUEST. Expecting response with Correlation ID: <uuid>`. Di log Panel, Anda akan melihat `Temperature data from <sensor_id> is a REQUEST. Sending ACK...`. Sensor kemudian akan mencetak `Received RESPONSE on 'iot/project/temperature/response_m5/<uuid>'... Parsed Response Data from Panel/Subscriber: { "status": "temperature_acknowledged_by_panel", ... }`.
        3.  **Panel ke Lampu**: Di Panel, kirim perintah `ON`. Log Panel akan menunjukkan `Command 'ON' sent as REQUEST. Expecting response (CorrID: <uuid>...)`. Log Lampu akan menunjukkan penerimaan perintah dan pengiriman response. Log Panel kemudian akan menampilkan `[RESPONSE] For command 'ON' (CorrID: <uuid>): ... Status: SUCCESS - Lamp is now ON`. Coba kirim `INVALIDCMD` dari Panel untuk melihat respons error.

8.  **`flow control` (Receive Maximum - MQTT 5.0)**
    *   **Implementasi**: Properti `ReceiveMaximum` diatur saat koneksi klien (`common/mqtt_utils.py`) berdasarkan `"v5_receive_maximum": 10` di `config/settings.json`.
    *   **Demonstrasi**:
        *   Ini adalah fitur yang bekerja di latar belakang untuk mencegah klien kewalahan. Klien memberitahu broker bahwa ia hanya mau menerima maksimal 10 pesan QoS 1/2 yang belum di-acknowledge pada satu waktu.
        *   Untuk benar-benar melihat efeknya, Anda memerlukan skenario di mana broker mengirim pesan ke satu klien dengan sangat cepat (lebih cepat dari kemampuan klien untuk memproses dan mengirim `PUBACK`). Dalam proyek ini dengan interval publish yang wajar, efeknya mungkin tidak terlihat jelas tanpa alat khusus. Namun, pengaturannya menunjukkan bahwa fitur ini aktif. Anda bisa mengamati log broker jika ia melaporkan penundaan pengiriman karena batasan `ReceiveMaximum` klien (beberapa broker mungkin memiliki log seperti itu).

9.  **`ping-pong` (Keepalive untuk Deteksi Koneksi & LWT)**
    *   **Implementasi**:
        *   **Keepalive**: Parameter `keepalive` (misal, 60 detik) di `config/settings.json` digunakan saat `client.connect()`. Paho-MQTT secara otomatis menangani pengiriman `PINGREQ` dan pemrosesan `PINGRESP`.
        *   **LWT (Last Will and Testament)**: Setiap klien mendaftarkan LWT (`client.will_set()`) yang berisi status `offline_unexpected`. Klien juga secara eksplisit mempublikasikan status `online` dan `offline_graceful`.
    *   **Demonstrasi**:
        1.  **Keepalive**:
            *   Jalankan Broker dan salah satu klien (misal, Sensor).
            *   Jika tidak ada traffic MQTT lain, setelah interval `keepalive` (60 detik), klien akan mengirim `PINGREQ` dan broker akan merespons dengan `PINGRESP`. Ini bisa diamati dengan packet sniffer (seperti Wireshark) yang memantau port broker, atau di log broker yang sangat verbose (beberapa konfigurasi Mosquitto dapat menampilkan ini).
        2.  **LWT & Deteksi Putus Koneksi**:
            *   Jalankan Broker, Panel, dan Sensor. Pastikan Sensor terhubung dan Panel menampilkan status Sensor "ONLINE".
            *   **Crash Test (Simulasi Putus Tiba-tiba)**: Tutup paksa terminal Sensor (misalnya, menggunakan `kill` atau menutup window terminal, **jangan** Ctrl+C).
            *   Broker tidak akan menerima `PINGREQ` atau pesan lain dari Sensor setelah `1.5 * keepalive` detik. Broker kemudian akan mempublikasikan pesan LWT Sensor.
            *   Panel Kontrol akan menerima pesan LWT ini dan menampilkan status Sensor sebagai `OFFLINE_UNEXPECTED`.
            *   **Normal Shutdown**: Hentikan Sensor dengan `Ctrl+C`. Sebelum disconnect, Sensor akan mempublikasikan pesan `offline_graceful` ke topik LWT-nya. Panel akan menerima ini dan menampilkan status Sensor sebagai `OFFLINE_GRACEFUL`.

---

## Benchmark: Uji Latensi Request-Response

Sebuah skrip benchmark `benchmark_req_res.py` disertakan untuk menguji latensi request-response dari setup MQTT Anda. Skrip ini mensimulasikan klien *requester* yang mengirim pesan dan klien *responder* yang membalasnya, sambil mengukur waktu bolak-balik (*round-trip time* / RTT).

### Tujuan Benchmark

Benchmark ini dirancang untuk mengukur latensi dan throughput sistem MQTT dalam skenario request-response. Untuk pengujian performa dasar yang terisolasi, Anda dapat menjalankan instance broker Mosquitto terpisah tanpa enkripsi atau autentikasi. Skrip benchmark juga menyediakan opsi baris perintah untuk terhubung ke broker tertentu, termasuk yang menggunakan TLS dan autentikasi, jika Anda ingin menguji konfigurasi tersebut secara spesifik.

### Prasyarat Benchmark

*   **Broker Mosquitto Lokal Berjalan:** Anda memerlukan instance Mosquitto yang berjalan.
*   **Lingkungan Virtual Python (venv) Aktif:** Pastikan venv proyek Anda sudah diaktifkan.
*   **File Skrip `benchmark_req_res.py`:** Pastikan skrip ini ada di root direktori proyek.

### Cara Menjalankan Benchmark

Anda akan memerlukan minimal 3 terminal: satu untuk broker Mosquitto (yang akan digunakan untuk benchmark), satu untuk responder, dan satu untuk requester.

#### Terminal 1: Jalankan Broker Mosquitto (Konfigurasi Benchmark Sederhana)

Untuk benchmark dasar tanpa TLS/Auth, buat file konfigurasi sederhana, misalnya `mosquitto_benchmark.conf`:
```conf
# mosquitto_benchmark.conf
listener 1884
allow_anonymous true
# Optional:
# log_type all
# connection_messages true
# log_timestamp true
```
Jalankan Mosquitto dengan konfigurasi ini:
```bash
# Navigasi ke direktori tempat Anda menyimpan mosquitto_benchmark.conf
mosquitto -c mosquitto_benchmark.conf -v
```
Ini akan menjalankan broker di port 1884 tanpa TLS atau autentikasi.

#### Terminal 2: Jalankan Klien Responder

```bash
# Navigasi ke root direktori proyek
# Aktifkan venv
```bash
python benchmark_req_res.py responder --bench_broker_host localhost --bench_broker_port 1884 --request_topic "benchmark/rtt_test" --qos 1
```

#### Terminal 3: Jalankan Klien Requester

```bash
# Navigasi ke root direktori proyek
# Aktifkan venv
```bash
python benchmark_req_res.py requester --bench_broker_host localhost --bench_broker_port 1884 --num_requests 100 --request_topic "benchmark/rtt_test" --qos 1 --req_payload_size 128
```

**Penting:**
*   Nilai untuk `--request_topic` harus sama persis antara responder dan requester.
*   Jika menguji broker utama Anda yang menggunakan TLS/Auth, gunakan opsi `--bench_use_tls`, `--bench_ca_cert`, `--bench_username`, dan `--bench_password` pada skrip benchmark sesuai dengan konfigurasi `config/settings.json` Anda.

### Opsi Command-Line Utama untuk `benchmark_req_res.py`

*   `role`: `requester` atau `responder` (argumen posisi, wajib).
*   `--num_requests N`: (Hanya Requester) Jumlah request yang akan dikirim (default: 100).
*   `--req_payload_size BYTES`: (Requester) Ukuran payload request dalam byte (default: 128).
*   `--res_payload_size BYTES`: (Responder) Ukuran payload response dalam byte (default: 128).
*   `--qos LEVEL`: Level QoS MQTT (0, 1, atau 2) untuk pesan benchmark (default: 1).
*   `--request_topic TOPIC_PATH`: Topik utama untuk mengirim request (default: `benchmark/request`).
*   `--response_topic_base TOPIC_PATH_BASE`: (Requester) Topik dasar untuk response. Requester akan menambahkan ID unik (default: `benchmark/response/`).
*   `--delay DETIK`: (Hanya Requester) Jeda dalam detik antar pengiriman request (default: 0.0).
*   `--bench_broker_host HOST`: Alamat host broker MQTT untuk benchmark (default: `localhost`).
*   `--bench_broker_port PORT`: Port broker MQTT untuk benchmark (default: 1884).
*   `--bench_use_tls`: Gunakan TLS untuk koneksi benchmark. Jika digunakan, biasanya `--bench_ca_cert` juga diperlukan.
*   `--bench_ca_cert PATH`: Path ke CA certificate untuk TLS jika `--bench_use_tls` diaktifkan.
*   `--bench_username USER`: Username untuk autentikasi broker.
*   `--bench_password PASS`: Password untuk autentikasi broker.

### Menginterpretasikan Hasil (Output Requester)

Setelah selesai, klien requester akan menampilkan statistik berikut:
*   `Total requests attempted`: Jumlah total request yang coba dikirim.
*   `Successful requests (response received)`: Jumlah request yang menerima balasan dalam batas waktu.
*   `Timed-out requests`: Jumlah request yang tidak menerima balasan dalam `REQUEST_TIMEOUT_SECONDS`.
*   `Publish errors`: Jumlah kegagalan saat mempublikasikan request.
*   `Subscribe errors`: Jumlah kegagalan saat berlangganan topik balasan.
*   Statistik RTT (Round-Trip Time) dalam milidetik (ms) untuk request yang berhasil:
    *   Minimum RTT
    *   Maximum RTT
    *   Average RTT
    *   StdDev RTT (jika lebih dari 1 RTT tercatat)
*   `Total benchmark duration`: Total waktu pelaksanaan benchmark.
*   `Throughput (successful requests/sec)`: Jumlah request sukses per detik.

Statistik ini memungkinkan Anda untuk mengamati bagaimana faktor-faktor seperti level QoS, ukuran payload, konfigurasi broker (dengan atau tanpa TLS/Auth), dan kondisi jaringan memengaruhi latensi dan throughput komunikasi MQTT.

### Catatan Penting Mengenai Isu Timeout
Jika Anda mengalami banyak `Timed-out requests`, pastikan:
1.  Broker berjalan dan dapat diakses oleh skrip benchmark pada host dan port yang benar (sesuai argumen `--bench_broker_host` dan `--bench_broker_port`).
2.  Responder telah dijalankan **SEBELUM** requester dan berhasil terhubung ke broker.
3.  Responder dan Requester menggunakan `--request_topic` yang **SAMA**.
4.  Firewall tidak memblokir koneksi ke port broker.
5.  Tidak ada error koneksi atau subskripsi yang signifikan di log responder atau requester.
6.  Jika menguji koneksi dengan TLS/Auth, pastikan sertifikat dan kredensial sudah benar.

---

## Dibuat oleh: Grup M
```