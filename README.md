# Proyek Sistem Pemantauan dan Kontrol Berbasis MQTT (Grup M)

Ini adalah proyek sederhana untuk mendemonstrasikan penggunaan protokol MQTT dalam membangun sistem pemantauan suhu dan kontrol lampu. Proyek ini melibatkan tiga komponen utama: sensor suhu, lampu pintar (virtual), dan panel kontrol, yang semuanya berkomunikasi melalui MQTT broker.

## Deskripsi Proyek

Sistem ini bertujuan untuk:
1.  **Memantau Suhu:** Sebuah sensor (virtual) akan secara periodik mempublikasikan data suhu ke topik MQTT.
2.  **Kontrol Lampu:** Sebuah lampu pintar (virtual) akan mendengarkan perintah (ON/OFF) dari topik MQTT dan mengubah statusnya. Lampu juga akan mempublikasikan status terkininya (menyala/mati) ke topik MQTT lain.
3.  **Panel Kontrol Terpusat:** Sebuah panel kontrol (aplikasi konsol) akan:
    *   Menampilkan data suhu yang diterima.
    *   Menampilkan status lampu terkini.
    *   Memungkinkan pengguna mengirim perintah untuk menyalakan atau mematikan lampu.
    *   Memantau status konektivitas (online/offline) dari sensor dan lampu.

Proyek ini mengimplementasikan beberapa fitur penting MQTT, termasuk:
*   Komunikasi Publish-Subscribe dasar.
*   Quality of Service (QoS) level 0, 1, dan 2 (saat ini dikonfigurasi untuk QoS 2).
*   Retained Messages untuk status lampu dan status konektivitas.
*   Last Will and Testament (LWT) untuk deteksi perangkat offline yang tidak terduga.

## Struktur Direktori

project-mqtt-sederhana/
├── sensor/                     # Logika untuk perangkat sensor suhu
│   └── sensor_client.py
├── lamp/                       # Logika untuk perangkat lampu pintar
│   └── lamp_client.py
├── control_panel/              # Logika untuk aplikasi panel kontrol
│   └── panel_client.py
├── config/                     # File konfigurasi
│   └── settings.json
├── common/                     # (Opsional) Utilitas bersama
│   ├── __init__.py
│   └── mqtt_utils.py
├── venv/                       # (Direktori Virtual Environment, diabaikan oleh Git)
├── .gitignore                  # File yang diabaikan Git
├── requirements.txt            # Dependensi Python
└── README.md                   # File ini

## Prasyarat
*   Sebuah MQTT Broker yang dapat diakses. Proyek ini dikonfigurasi untuk menggunakan broker publik `test.mosquitto.org` pada port `1883` (tanpa enkripsi dan autentikasi untuk saat ini). Kamu bisa mengubah ini di `config/settings.json` jika menggunakan broker lokal atau broker lain.

## Setup dan Instalasi

1.  **Kloning Repository (jika belum):**
    ```bash
    git clone https://github.com/agnesgriselda/project_mqtt_grup-m.git
    cd project_mqtt_grup-m
    ```

2.  **Buat dan Aktifkan Virtual Environment:**
    Sangat disarankan untuk menggunakan virtual environment untuk mengisolasi dependensi proyek.
    *   **Buat venv (jika belum ada):**
        ```bash
        python -m venv venv
        ```
    *   **Aktifkan venv:**
        *   Di Windows (Command Prompt/PowerShell):
            ```bash
            venv\Scripts\activate
            ```
        *   Di macOS/Linux (Bash/Zsh):
            ```bash
            source venv/bin/activate
            ```
        Kamu akan melihat `(venv)` di awal prompt terminalmu.

3.  **Instal Dependensi:**
    Pastikan virtual environment sudah aktif, kemudian jalankan:
    ```bash
    pip install -r requirements.txt
    ```
    Ini akan menginstal `paho-mqtt` dan library lain yang mungkin dibutuhkan.

## Konfigurasi

File konfigurasi utama adalah `config/settings.json`. Kamu bisa menyesuaikan:
*   `broker_address` dan `broker_port`.
*   Nama-nama topik MQTT.
*   Level QoS default (`default_qos`, `lwt_qos`).
*   Pengaturan retain untuk LWT (`lwt_retain`).

Contoh `config/settings.json`:
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

## Cara Menjalankan Aplikasi

Kamu perlu membuka tiga terminal terpisah. Di setiap terminal, pastikan kamu berada di direktori root proyek (`project_mqtt_grup-m/`) dan **virtual environment sudah diaktifkan**.

1.  **Terminal 1: Jalankan Panel Kontrol**
    ```bash
    python control_panel/panel_client.py
    ```
    Panel akan terhubung dan menunggu pesan serta siap menerima input untuk mengontrol lampu.

2.  **Terminal 2: Jalankan Sensor Suhu**
    ```bash
    python sensor/sensor_client.py
    ```
    Sensor akan terhubung, mengirim status "online" (jika LWT dikonfigurasi), dan mulai mempublikasikan data suhu. Panel akan mulai menampilkan data suhu dan status online sensor.

3.  **Terminal 3: Jalankan Lampu Pintar**
    ```bash
    python lamp/lamp_client.py
    ```
    Lampu akan terhubung, mengirim status "online" (jika LWT dikonfigurasi), mengirim status ON/OFF awalnya (retained), dan menunggu perintah. Panel akan menampilkan status online lampu dan status ON/OFF awalnya.

**Interaksi:**
*   Di terminal **Panel Kontrol**, kamu bisa mengetik `ON` atau `OFF` untuk mengontrol lampu.
*   Amati log di semua terminal untuk melihat alur pesan MQTT.

**Menguji Last Will and Testament (LWT):**
1.  Setelah semua klien berjalan, tutup paksa terminal **Sensor** atau **Lampu** (misalnya, dengan menutup jendela terminal, **JANGAN Ctrl+C**).
2.  Amati terminal **Panel Kontrol**. Setelah beberapa saat, panel akan menerima pesan LWT yang memberitahukan bahwa perangkat tersebut "offline_unexpected".
3.  Jika kamu menghentikan sensor atau lampu dengan `Ctrl+C` (keluar normal), panel akan menerima pesan "offline_graceful" dan LWT "offline_unexpected" tidak akan terpicu.

---
*Dibuat oleh Grup M*
```
