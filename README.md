# 🌀 WebSocket Proxy - By Namydevx

Proxy WebSocket powerful untuk forwarding SSH, lengkap dengan pembatasan IP & monitoring real-time.

---

## 🚀 Instalasi 1 Klik

Klik tombol di bawah ini untuk menyalin perintah instalasi:

<!-- Tombol Copy -->
<p>
  <code><kbd id="copyText">bash &lt;(curl -sSL https://raw.githubusercontent.com/Namydevx/Proxy-/main/proxy.py) --start</kbd></code>
  <button onclick="navigator.clipboard.writeText(document.getElementById('copyText').innerText)">📋 Copy</button>
</p>

---

## 🧰 Fitur
- ✅ WebSocket proxy ke `127.0.0.1:22`
- ✅ Batasi jumlah koneksi per IP
- ✅ Monitoring koneksi IP aktif
- ✅ Logging otomatis ke `proxy.log`

---

## 🖥️ Manual
Jika tidak auto-jalan:
```bash
chmod +x proxy.py
./proxy.py --start
