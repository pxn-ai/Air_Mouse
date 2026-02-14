import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import serial
import threading
import numpy as np

# Modern Tech Palette
COLOR_PCB = (0.05, 0.2, 0.1)
COLOR_HUD = (0, 1.0, 0.8)  # Cyan
COLOR_ACCENT = (1.0, 0.2, 0.4) # Pink/Red

class AdvancedViewer:
    def __init__(self, port):
        self.quat = [1.0, 0.0, 0.0, 0.0]
        self.running = True
        
        # Initialize Pygame with Multi-sampling (Anti-aliasing)
        pygame.init()
        pygame.display.gl_set_attribute(GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(GL_MULTISAMPLESAMPLES, 4)
        self.display = (1000, 700)
        pygame.display.set_mode(self.display, DOUBLEBUF | OPENGL)
        pygame.display.set_caption("ESP32-S3 9-Axis Pro-Viewer")
        
        # OpenGL setup (must be after display mode is set)
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        gluPerspective(45, self.display[0]/self.display[1], 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)
        
        # Start Serial
        self.ser = serial.Serial(port, 921600, timeout=0.01)
        threading.Thread(target=self.update_data, daemon=True).start()

    def update_data(self):
        while self.running:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('QUAT'):
                try:
                    p = line.split(',')
                    self.quat = [float(p[1]), float(p[2]), float(p[3]), float(p[4])]
                except: pass

    def draw_styled_board(self):
        # Draw a detailed PCB
        glBegin(GL_QUADS)
        # Main Board
        glColor3f(*COLOR_PCB)
        for v in [(-2,-0.1,-1.5), (2,-0.1,-1.5), (2,0.1,-1.5), (-2,0.1,-1.5)]: glVertex3f(*v) # Back
        # Chip with "Silk Screen"
        glColor3f(0.1, 0.1, 0.1)
        glVertex3f(-0.3, 0.11, -0.3); glVertex3f(0.3, 0.11, -0.3)
        glVertex3f(0.3, 0.11, 0.3); glVertex3f(-0.3, 0.11, 0.3)
        glEnd()

    def render(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glClearColor(0.02, 0.02, 0.05, 1.0) # Deep Space Blue
        
        glLoadIdentity()
        gluLookAt(6, 4, 6, 0, 0, 0, 0, 1, 0)
        
        # Fusion Rotation
        glPushMatrix()
        w, x, y, z = self.quat
        # Convert Quat to Matrix
        m = [1-2*y*y-2*z*z, 2*x*y-2*z*w, 2*x*z+2*y*w, 0,
             2*x*y+2*z*w, 1-2*x*x-2*z*z, 2*y*z-2*x*w, 0,
             2*x*z-2*y*w, 2*y*z+2*x*w, 1-2*x*x-2*y*y, 0,
             0, 0, 0, 1]
        glMultMatrixf(m)
        self.draw_styled_board()
        glPopMatrix()
        
        pygame.display.flip()

if __name__ == "__main__":
    v = AdvancedViewer('/dev/cu.usbserial-A5069RR4')
    clock = pygame.time.Clock()
    while v.running:
        for event in pygame.event.get():
            if event.type == QUIT:
                v.running = False
        v.render()
        clock.tick(60)
    pygame.quit()