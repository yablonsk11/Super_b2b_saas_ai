# 🎛️ Remote Image Changer

A simple client-server system built with Python for remote UI control over a local network. When you click the button in the application on **PC 1 (Client)**, the image in the application on **PC 2 (Server)** changes instantly.

The project uses the **PyQt6** library for the graphical user interface and network **UDP sockets** for low-latency signal transmission without the need to deploy complex web servers.

---

## 🚀 Architecture

The project is split into two independent applications:
1. **Control Panel (`client.py`)** — runs on the client PC. Contains a single button to send the trigger command.
2. **Image Viewer (`server.py`)** — runs on the server PC. Listens to the network in a background thread and cyclically switches images upon receiving the signal.

---

## 🛠️ Installation & Setup

Follow these steps on **both computers**.

### 1. Clone the Repository and Navigate to the Folder
```bash
git clone https://github.com
cd TODO
```

### 2. Create and Activate a Virtual Environment (`venv`)

* **Windows:**
  ```bash
  python -m venv .venv
  # Activate in CMD:
  .venv\Scripts\activate
  # Or activate in PowerShell:
  .venv\Scripts\Activate.ps1
  ```
* **macOS / Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```
*(Alternatively, install manually using: `pip install PyQt6`)*

---

## ⚙️ Configuration & Running

### Step 1. Configure the Server (PC 2)
1. Place your image files (e.g., `image1.png` and `image2.png`) into the same folder as the `receiver.py` script.
2. Find the local IP address of this computer (type `ipconfig` in the Windows command prompt or `ifconfig` in macOS/Linux terminals). For example, let's assume it is `192.168.1.50`.
3. Launch the server application:
   ```bash
   python receiver.py
   ```

### Step 2. Configure the Client (PC 1)
1. Open the `sender.py` file in a text editor or IDE.
2. Locate the `TARGET_IP` variable at the top of the file and replace it with the Server PC's actual IP address:
   ```python
   TARGET_IP = "192.168.1.50"  # Replace with your Server's actual local IP
   ```
3. Launch the client application:
   ```bash
   python sender.py
   ```

Now, clicking the "Сменить картинку" (Change Image) button on the first computer will instantly rotate the images on the second one.

---

## ⚠️ Troubleshooting

* **Image is not changing?** Make sure both computers are connected to the **same Wi-Fi network** or router.
* **Signal still not going through?** The firewall on the Server PC might be blocking incoming traffic. Try temporarily disabling it or add port `5005` (UDP) to your firewall's inbound rules/exceptions.
* **"File not found" Error?** Ensure that the file names in the `receiver.py` image array (`self.images`) exactly match the actual files located in the project directory.

