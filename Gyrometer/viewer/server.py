from flask import Flask, render_template
from flask_socketio import SocketIO
import serial
import threading
import socket
import time
import argparse
import sys
import glob

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# Global state
current_euler = [0.0, 0.0, 0.0]  # roll, pitch, yaw
running = True
euler_count = 0
status_count = 0
last_log_time = 0

def serial_scanner():
    """Scans for available serial ports."""
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    # Filter out macOS system ports (not real USB devices)
    ignore = ['wlan-debug', 'Bluetooth', 'debug-console']
    ports = [p for p in ports if not any(bad in p for bad in ignore)]

    usual_ports = { '/dev/cu.usbmodem101', '/dev/tty.usbmodem101', '/dev/cu.usbserial-A5069RR4', '/dev/tty.usbserial-A5069RR4' }

    ports = usual_ports.intersection(ports)

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

def process_line(line):
    """Process a data line from either serial or UDP."""
    global current_euler, euler_count, status_count, last_log_time
    line = line.strip()
    if not line:
        return

    # Log unrecognized lines for debugging
    if not (line.startswith('EULER') or line.startswith('STATUS') or line.startswith('TRANSPORT')):
        if not line.startswith('=') and not line.startswith('WiFi') and not line.startswith('MPU') and not line.startswith('HMC') and not line.startswith('ERROR') and not line.startswith('DIAG'):
            print(f"[WARN] Unknown line: {repr(line[:80])}")
        return

    if line.startswith('EULER'):
        parts = line.split(',')
        if len(parts) == 4:
            try:
                roll = float(parts[1])
                pitch = float(parts[2])
                yaw = float(parts[3])
                # Reject nan/inf values
                import math
                if any(math.isnan(v) or math.isinf(v) for v in (roll, pitch, yaw)):
                    return
                current_euler = [roll, pitch, yaw]
                socketio.emit('euler_data', {'roll': roll, 'pitch': pitch, 'yaw': yaw})
                euler_count += 1
                # Log stats every 5 seconds
                now = time.time()
                if now - last_log_time >= 5:
                    print(f"[INFO] EULER received: {euler_count} total | STATUS: {status_count} | roll={roll:.2f} pitch={pitch:.2f} yaw={yaw:.2f}")
                    last_log_time = now
            except ValueError as e:
                print(f"[ERROR] Bad EULER parse: {repr(line)} -> {e}")
        else:
            print(f"[ERROR] EULER wrong field count ({len(parts)}): {repr(line[:80])}")

    elif line.startswith('STATUS'):
        parts = line.split(',')
        if len(parts) == 3:
            try:
                imu_ok = int(parts[1]) == 1
                mag_ok = int(parts[2]) == 1
                socketio.emit('device_status', {'imu': imu_ok, 'mag': mag_ok})
                status_count += 1
            except ValueError:
                print(f"[ERROR] Bad STATUS parse: {repr(line)}")

    elif line.startswith('TRANSPORT'):
        parts = line.split(',')
        if len(parts) == 2:
            mode = parts[1].strip()
            print(f"Transport mode: {mode}")
            socketio.emit('transport_mode', {'mode': mode})

def serial_reader(port_name, baud_rate):
    """Read data from serial port with auto-reconnect."""
    global running
    ser = None

    while running:
        # Connect / reconnect
        if ser is None or not ser.is_open:
            try:
                ser = serial.Serial(port_name, baud_rate, timeout=0.1)
                print(f"Serial: Connected to {port_name} at {baud_rate} baud")
                # Flush any garbage in the buffer after connecting
                ser.reset_input_buffer()
            except serial.SerialException as e:
                print(f"Serial: Waiting for {port_name}... ({e})")
                time.sleep(2)
                continue

        # Read loop
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                process_line(line)
        except Exception:
            print(f"Serial: Lost connection to {port_name}, reconnecting...")
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(2)
            continue

        time.sleep(0.001)

    if ser and ser.is_open:
        ser.close()

def udp_listener(udp_port):
    """Listen for UDP packets from ESP32 WiFi."""
    global running
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', udp_port))
    sock.settimeout(1.0)
    print(f"UDP: Listening on port {udp_port}")

    while running:
        try:
            data, addr = sock.recvfrom(1024)
            line = data.decode('utf-8', errors='ignore').strip()
            if line:
                process_line(line)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"UDP error: {e}")
            time.sleep(0.5)

    sock.close()

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web-based Orientation Viewer')
    parser.add_argument('--port', type=str, default=None,
                        help='Serial port (e.g., COM3 or /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=921600, help='Baud rate')
    parser.add_argument('--web-port', type=int, default=5001, help='Web server port')
    parser.add_argument('--udp-port', type=int, default=4210, help='UDP listen port')
    parser.add_argument('--no-serial', action='store_true',
                        help='WiFi-only mode (skip serial)')
    args = parser.parse_args()

    web_port = args.web_port

    # ── Start UDP listener (always) ──
    udp_thread = threading.Thread(target=udp_listener, args=(args.udp_port,), daemon=True)
    udp_thread.start()

    # ── Start serial reader (unless --no-serial) ──
    if not args.no_serial:
        target_port = args.port
        if target_port is None:
            print("Serial: Scanning ports...")
            ports = serial_scanner()
            if ports:
                preferred = [p for p in ports if 'usb' in p.lower()]
                target_port = preferred[0] if preferred else ports[0]
                print(f"Serial: Auto-selected {target_port}")
            else:
                print("Serial: No ports found (WiFi-only)")

        if target_port:
            serial_thread = threading.Thread(
                target=serial_reader, args=(target_port, args.baud), daemon=True)
            serial_thread.start()

    print(f"Starting Flask server at http://0.0.0.0:{web_port}")
    socketio.run(app, host='0.0.0.0', port=web_port, allow_unsafe_werkzeug=True)
