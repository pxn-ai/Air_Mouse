#!/usr/bin/env python3
"""
Air Mouse Pointer Simulation
Reads pitch/roll data from ESP32-S3 via serial and moves an arrow pointer on screen.
Uses tkinter (built-in) for graphics.
"""

import sys
import re
import math
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
import threading
import time

# Check for pyserial
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required. Install with: pip install pyserial")
    print("Or run: source venv/bin/activate && pip install pyserial")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
SERIAL_BAUDRATE = 115200
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# Sensitivity - how much the pointer moves per degree of tilt
SENSITIVITY_X = 10.0  # Roll affects X axis
SENSITIVITY_Y = 10.0  # Pitch affects Y axis

# Smoothing - number of samples to average
SMOOTHING_SAMPLES = 5

# Colors (Dark theme)
BG_COLOR = "#0f0f19"
GRID_COLOR = "#1e1e32"
POINTER_COLOR = "#00c8ff"
POINTER_OUTLINE = "#ffffff"
TEXT_COLOR = "#c8c8dc"
ACCENT_COLOR = "#ff6496"
SUCCESS_COLOR = "#64ff96"
WARNING_COLOR = "#ffc864"
PANEL_COLOR = "#19192d"


# ═══════════════════════════════════════════════════════════════════════════════
# SERIAL PORT UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════
def list_serial_ports():
    """List all available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [(p.device, p.description) for p in ports]


def find_esp32_port():
    """Try to auto-detect ESP32 port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = port.description.lower()
        if 'esp32' in desc or 'usb' in desc or 'uart' in desc or 'serial' in desc or 'cp210' in desc:
            return port.device
    return None


def parse_sensor_data(line):
    """
    Parse the serial output from ESP32.
    Expected format: "Pitch: 12.34  | Roll: 56.78    (Accel Z: 0.99)"
    """
    try:
        match = re.search(r'Pitch:\s*([-\d.]+).*Roll:\s*([-\d.]+)', line)
        if match:
            pitch = float(match.group(1))
            roll = float(match.group(2))
            return pitch, roll
    except (ValueError, AttributeError):
        pass
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class AirMouseSimulation:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎮 Air Mouse Simulation")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        
        # Serial connection
        self.serial_port = None
        self.connected = False
        self.running = True
        
        # Pointer state
        self.pointer_x = WINDOW_WIDTH // 2
        self.pointer_y = WINDOW_HEIGHT // 2
        self.target_x = self.pointer_x
        self.target_y = self.pointer_y
        self.pointer_angle = -45  # degrees
        
        # Sensor data
        self.last_pitch = 0.0
        self.last_roll = 0.0
        self.pitch_buffer = deque(maxlen=SMOOTHING_SAMPLES)
        self.roll_buffer = deque(maxlen=SMOOTHING_SAMPLES)
        
        # Trail
        self.trail = deque(maxlen=30)
        
        # Demo mode
        self.demo_mode = tk.BooleanVar(value=False)
        self.demo_time = 0
        
        # Setup UI
        self._setup_ui()
        
        # Try auto-connect
        self._try_auto_connect()
        
        # Start update loop
        self._update()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _setup_ui(self):
        """Setup the user interface."""
        # Main canvas
        self.canvas = tk.Canvas(
            self.root, 
            width=WINDOW_WIDTH, 
            height=WINDOW_HEIGHT,
            bg=BG_COLOR,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Draw grid
        self._draw_grid()
        
        # Create pointer
        self.pointer_items = []
        self.trail_items = []
        self.glow_items = []
        self._create_pointer()
        
        # Info panel
        self._create_info_panel()
        
        # Bind keys
        self.root.bind('<d>', lambda e: self.demo_mode.set(not self.demo_mode.get()))
        self.root.bind('<D>', lambda e: self.demo_mode.set(not self.demo_mode.get()))
        self.root.bind('<r>', lambda e: self._recenter())
        self.root.bind('<R>', lambda e: self._recenter())
        self.root.bind('<c>', lambda e: self._show_port_dialog())
        self.root.bind('<C>', lambda e: self._show_port_dialog())
        self.root.bind('<q>', lambda e: self._on_close())
        self.root.bind('<Q>', lambda e: self._on_close())
        self.root.bind('<Escape>', lambda e: self._on_close())
    
    def _draw_grid(self):
        """Draw background grid."""
        grid_spacing = 50
        for x in range(0, WINDOW_WIDTH + grid_spacing, grid_spacing):
            self.canvas.create_line(x, 0, x, WINDOW_HEIGHT, fill=GRID_COLOR, width=1)
        for y in range(0, WINDOW_HEIGHT + grid_spacing, grid_spacing):
            self.canvas.create_line(0, y, WINDOW_WIDTH, y, fill=GRID_COLOR, width=1)
        
        # Center crosshair
        cx, cy = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2
        self.canvas.create_line(cx - 40, cy, cx + 40, cy, fill=ACCENT_COLOR, width=2, dash=(5, 3))
        self.canvas.create_line(cx, cy - 40, cx, cy + 40, fill=ACCENT_COLOR, width=2, dash=(5, 3))
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, outline=ACCENT_COLOR, width=2)
    
    def _create_pointer(self):
        """Create the arrow pointer."""
        # Glow circles
        for i in range(3):
            glow = self.canvas.create_oval(0, 0, 0, 0, 
                fill="", outline=POINTER_COLOR, width=2-i*0.5)
            self.glow_items.append(glow)
        
        # Main arrow polygon
        self.arrow = self.canvas.create_polygon(
            0, 0, 0, 0, 0, 0, 0, 0,
            fill=POINTER_COLOR,
            outline=POINTER_OUTLINE,
            width=2
        )
    
    def _create_info_panel(self):
        """Create the info display panel."""
        # Title
        self.canvas.create_text(
            30, 30, 
            text="Air Mouse Simulation",
            font=("Helvetica", 28, "bold"),
            fill=TEXT_COLOR,
            anchor="nw"
        )
        
        # Status indicator
        self.status_dot = self.canvas.create_oval(30, 80, 42, 92, fill=ACCENT_COLOR, outline="")
        self.status_text = self.canvas.create_text(
            50, 86,
            text="Not Connected",
            font=("Helvetica", 14),
            fill=TEXT_COLOR,
            anchor="w"
        )
        
        # Data panel background
        panel_y = WINDOW_HEIGHT - 130
        self.canvas.create_rectangle(
            15, panel_y - 10,
            320, panel_y + 110,
            fill=PANEL_COLOR,
            outline=GRID_COLOR,
            width=2
        )
        
        # Data labels
        self.pitch_label = self.canvas.create_text(
            30, panel_y + 10,
            text="Pitch:   0.00°",
            font=("Menlo", 16),
            fill=TEXT_COLOR,
            anchor="w"
        )
        self.roll_label = self.canvas.create_text(
            30, panel_y + 40,
            text="Roll:    0.00°",
            font=("Menlo", 16),
            fill=TEXT_COLOR,
            anchor="w"
        )
        self.pos_label = self.canvas.create_text(
            30, panel_y + 70,
            text=f"Pointer: ({self.pointer_x}, {self.pointer_y})",
            font=("Menlo", 14),
            fill=TEXT_COLOR,
            anchor="w"
        )
        
        # Instructions
        instructions = [
            "D - Demo Mode",
            "R - Recenter",
            "C - Connect",
            "Q - Quit"
        ]
        for i, text in enumerate(instructions):
            self.canvas.create_text(
                WINDOW_WIDTH - 150, 30 + i * 25,
                text=text,
                font=("Helvetica", 12),
                fill="#646478",
                anchor="w"
            )
    
    def _try_auto_connect(self):
        """Try to auto-connect to ESP32."""
        port = find_esp32_port()
        if port:
            self._connect_serial(port)
        else:
            self.demo_mode.set(True)
            print("No ESP32 detected. Running in Demo Mode.")
            print("Connect your Air Mouse and press 'C' to connect.")
    
    def _connect_serial(self, port):
        """Connect to serial port."""
        try:
            if self.serial_port:
                self.serial_port.close()
            self.serial_port = serial.Serial(port, SERIAL_BAUDRATE, timeout=0.05)
            self.connected = True
            self.demo_mode.set(False)
            self._update_status(f"Connected: {port}", SUCCESS_COLOR)
            print(f"✓ Connected to {port}")
            
            # Start serial reading thread
            self.serial_thread = threading.Thread(target=self._read_serial_loop, daemon=True)
            self.serial_thread.start()
            
        except serial.SerialException as e:
            self.connected = False
            self._update_status(f"Failed: {str(e)[:30]}", ACCENT_COLOR)
            print(f"✗ Failed to connect: {e}")
    
    def _read_serial_loop(self):
        """Background thread to read serial data."""
        while self.running and self.connected:
            try:
                if self.serial_port and self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        pitch, roll = parse_sensor_data(line)
                        if pitch is not None:
                            self.pitch_buffer.append(pitch)
                            self.roll_buffer.append(roll)
            except:
                self.connected = False
                break
            time.sleep(0.01)
    
    def _show_port_dialog(self):
        """Show port selection dialog."""
        ports = list_serial_ports()
        if not ports:
            messagebox.showwarning("No Ports", "No serial ports found!")
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Serial Port")
        dialog.geometry("400x300")
        dialog.configure(bg=BG_COLOR)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Select Port:", font=("Helvetica", 14), 
                 bg=BG_COLOR, fg=TEXT_COLOR).pack(pady=10)
        
        listbox = tk.Listbox(dialog, font=("Menlo", 12), bg=PANEL_COLOR, 
                            fg=TEXT_COLOR, selectbackground=POINTER_COLOR,
                            height=8)
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for device, desc in ports:
            listbox.insert(tk.END, f"{device} - {desc}")
        
        def on_select():
            sel = listbox.curselection()
            if sel:
                port = ports[sel[0]][0]
                self._connect_serial(port)
            dialog.destroy()
        
        tk.Button(dialog, text="Connect", command=on_select,
                  bg=POINTER_COLOR, fg="black", font=("Helvetica", 12, "bold"),
                  padx=20, pady=5).pack(pady=10)
    
    def _update_status(self, text, color):
        """Update connection status display."""
        self.canvas.itemconfig(self.status_dot, fill=color)
        self.canvas.itemconfig(self.status_text, text=text)
    
    def _recenter(self):
        """Recenter the pointer."""
        self.pointer_x = WINDOW_WIDTH // 2
        self.pointer_y = WINDOW_HEIGHT // 2
        self.target_x = self.pointer_x
        self.target_y = self.pointer_y
        self.trail.clear()
        for item in self.trail_items:
            self.canvas.delete(item)
        self.trail_items.clear()
    
    def _update(self):
        """Main update loop."""
        if not self.running:
            return
        
        # Get sensor data
        dx, dy = 0, 0
        
        if self.connected and self.pitch_buffer:
            # Calculate smoothed values
            self.last_pitch = sum(self.pitch_buffer) / len(self.pitch_buffer)
            self.last_roll = sum(self.roll_buffer) / len(self.roll_buffer)
            
            # Convert to movement
            dx = self.last_roll * SENSITIVITY_X * 0.1
            dy = -self.last_pitch * SENSITIVITY_Y * 0.1
        
        elif self.demo_mode.get():
            # Demo mode - figure-8 motion
            self.demo_time += 0.03
            self.last_pitch = 20 * math.sin(self.demo_time)
            self.last_roll = 20 * math.sin(self.demo_time * 0.5)
            dx = self.last_roll * SENSITIVITY_X * 0.08
            dy = -self.last_pitch * SENSITIVITY_Y * 0.08
            self._update_status("Demo Mode", WARNING_COLOR)
        
        # Update target position
        self.target_x += dx
        self.target_y += dy
        
        # Clamp to bounds
        margin = 50
        self.target_x = max(margin, min(WINDOW_WIDTH - margin, self.target_x))
        self.target_y = max(margin, min(WINDOW_HEIGHT - margin, self.target_y))
        
        # Smooth movement (lerp)
        self.pointer_x += (self.target_x - self.pointer_x) * 0.2
        self.pointer_y += (self.target_y - self.pointer_y) * 0.2
        
        # Update pointer angle based on movement
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            self.pointer_angle = math.degrees(math.atan2(dy, dx)) - 45
        
        # Add to trail
        self.trail.append((self.pointer_x, self.pointer_y))
        
        # Update visuals
        self._update_pointer()
        self._update_trail()
        self._update_labels()
        
        # Schedule next update (60 FPS)
        self.root.after(16, self._update)
    
    def _update_pointer(self):
        """Update pointer position and rotation."""
        x, y = self.pointer_x, self.pointer_y
        size = 35
        
        # Arrow points (pointing right, then rotated)
        points = [
            (size, 0),           # Tip
            (-size/2, -size/2),  # Top back
            (-size/4, 0),        # Notch
            (-size/2, size/2),   # Bottom back
        ]
        
        # Rotate points
        angle = math.radians(self.pointer_angle)
        rotated = []
        for px, py in points:
            rx = px * math.cos(angle) - py * math.sin(angle)
            ry = px * math.sin(angle) + py * math.cos(angle)
            rotated.extend([x + rx, y + ry])
        
        # Update arrow
        self.canvas.coords(self.arrow, *rotated)
        
        # Update glow
        for i, glow in enumerate(self.glow_items):
            r = size + 15 + i * 10
            self.canvas.coords(glow, x - r, y - r, x + r, y + r)
    
    def _update_trail(self):
        """Update the motion trail."""
        # Remove old trail items
        for item in self.trail_items:
            self.canvas.delete(item)
        self.trail_items.clear()
        
        # Draw new trail
        if len(self.trail) > 1:
            points = list(self.trail)
            for i in range(1, len(points)):
                alpha = int(255 * (i / len(points)) * 0.5)
                # Convert alpha to hex color with transparency simulation
                color = f"#{alpha:02x}{int(200*i/len(points)):02x}{int(255*i/len(points)):02x}"
                width = 1 + (i / len(points)) * 4
                
                line = self.canvas.create_line(
                    points[i-1][0], points[i-1][1],
                    points[i][0], points[i][1],
                    fill=color, width=width, capstyle=tk.ROUND
                )
                self.trail_items.append(line)
                self.canvas.tag_lower(line)
    
    def _update_labels(self):
        """Update sensor value labels."""
        self.canvas.itemconfig(self.pitch_label, text=f"Pitch: {self.last_pitch:>7.2f}°")
        self.canvas.itemconfig(self.roll_label, text=f"Roll:  {self.last_roll:>7.2f}°")
        self.canvas.itemconfig(self.pos_label, 
            text=f"Pointer: ({int(self.pointer_x)}, {int(self.pointer_y)})")
    
    def _on_close(self):
        """Handle window close."""
        self.running = False
        if self.serial_port:
            self.serial_port.close()
        self.root.destroy()
    
    def run(self):
        """Start the application."""
        print("\n" + "="*60)
        print("       🎮 AIR MOUSE SIMULATION")
        print("="*60)
        print("\nControls:")
        print("  D - Toggle Demo Mode")
        print("  R - Recenter Pointer")
        print("  C - Connect to Serial Port")
        print("  Q - Quit")
        print("="*60 + "\n")
        
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = AirMouseSimulation()
    app.run()
