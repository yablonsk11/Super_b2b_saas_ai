import html
import json
import math
import threading
from datetime import datetime

from PyQt6.QtCore import (QObject, QPointF, QTimer, Qt, pyqtSignal)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (QLabel, QMainWindow, QPushButton, QTextEdit,
                             QVBoxLayout, QWidget)

from server_controller import ServerController

BG = "#0a0d14"
PANEL = "#0f141d"
TEXT = "#d5dbe6"
MUTED = "#5b6478"
GREEN = "#2ee66b"
RED = "#ff4d5e"
BLUE = "#4da3ff"
IDLE = "#4a5468"

STYLE = f"""
QMainWindow, QWidget#central {{ background: {BG}; }}
QLabel {{ color: {TEXT}; }}
QTextEdit {{
    background: {PANEL}; color: {TEXT}; border: 1px solid #1b2230;
    border-radius: 10px; padding: 8px;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 12px;
}}
"""

START_BTN = f"""
QPushButton {{
    background: transparent; color: {TEXT}; border: 1px solid {GREEN};
    border-radius: 10px; padding: 10px 22px; font-size: 14px;
}}
QPushButton:hover {{ background: rgba(46, 230, 107, 40); }}
QPushButton:disabled {{ color: {MUTED}; border-color: {MUTED}; }}
"""

STOP_BTN = f"""
QPushButton {{
    background: transparent; color: {TEXT}; border: 1px solid {RED};
    border-radius: 10px; padding: 10px 22px; font-size: 14px;
}}
QPushButton:hover {{ background: rgba(255, 77, 94, 40); }}
QPushButton:disabled {{ color: {MUTED}; border-color: {MUTED}; }}
"""


class Bridge(QObject):
    log = pyqtSignal(str, str)        # текст, цвет
    state = pyqtSignal(str)           # "idle" | "starting" | "running" | "error"
    event = pyqtSignal(object, bool, str)   # команда, успех, сообщение
    command_start = pyqtSignal(object)      # команда принята в выполнение
    error = pyqtSignal(str)


class GlowCircle(QWidget):
    def __init__(self, color=IDLE):
        super().__init__()
        self._color = QColor(color)
        self._target_color = QColor(color)
        self._glow = 0.0
        self._level = 0.0
        self._active = False
        self._pulse = False
        self._phase = 0.0
        self.setMinimumSize(140, 140)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_color(self, color):
        self._target_color = QColor(color)

    def set_active(self, value):
        self._active = value

    def set_pulse(self, value):
        self._pulse = value

    def set_level(self, value):
        self._level = value

    def _tick(self):
        self._phase += 0.06
        if self._active:
            target = 0.35 + 0.65 * self._level
        elif self._pulse:
            target = 0.35 + 0.25 * math.sin(self._phase)
        else:
            target = 0.0
        self._glow += (target - self._glow) * 0.15

        c, t = self._color, self._target_color
        self._color = QColor(
            round(c.red() + (t.red() - c.red()) * 0.15),
            round(c.green() + (t.green() - c.green()) * 0.15),
            round(c.blue() + (t.blue() - c.blue()) * 0.15),
        )
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        base = min(self.width(), self.height()) * 0.22
        g = max(0.0, self._glow)

        glow_r = base * (1.5 + 1.0 * g)
        grad = QRadialGradient(center, glow_r)
        inner = QColor(self._color)
        inner.setAlphaF(min(1.0, 0.12 + 0.7 * g))
        outer = QColor(self._color)
        outer.setAlphaF(0.0)
        grad.setColorAt(0.0, inner)
        grad.setColorAt(min(0.99, base / glow_r * 0.9), inner)
        grad.setColorAt(1.0, outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(center, glow_r, glow_r)

        r = base * (1 + 0.1 * g)
        fill = QColor(self._color)
        fill.setAlphaF(0.15 + 0.25 * g)
        p.setBrush(fill)
        p.setPen(QPen(self._color, 3))
        p.drawEllipse(center, r, r)


class ServerWindow(QMainWindow):

    IDLE_TEXT = "Сервер остановлен"

    CMD_STYLE = (
        "background: {bg}; color: {fg}; "
        "border: 1px solid {border}; border-radius: 10px; "
        "padding: 10px 14px; font-size: 13px;"
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Server")
        self.resize(520, 760)
        self.setStyleSheet(STYLE)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        self.circle = GlowCircle(IDLE)
        lay.addWidget(self.circle, stretch=1)

        self.status = QLabel(self.IDLE_TEXT)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(f"color: {MUTED}; font-size: 17px;")
        lay.addWidget(self.status)

        self.address = QLabel("")
        self.address.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.address.setStyleSheet(
            f'color: {MUTED}; font-size: 13px; '
            f'font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;'
        )
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.address)

        self.current_cmd = QLabel("")
        self.current_cmd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_cmd.setWordWrap(True)
        self.current_cmd.setMinimumHeight(52)
        self._set_cmd_idle()
        lay.addWidget(self.current_cmd)

        self.button = QPushButton("Запустить сервер")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setStyleSheet(START_BTN)
        self.button.clicked.connect(self._on_button)
        lay.addWidget(self.button)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(180)
        lay.addWidget(self.log)

        # --- логика ---
        self.bridge = b = Bridge()
        b.log.connect(self.add_log)
        b.state.connect(self._on_state)
        b.event.connect(self._on_event)
        b.command_start.connect(self._on_command_start)
        b.error.connect(lambda m: self.add_log(m, RED))

        self.controller = ServerController(
            on_log=b.log.emit,
            on_event=lambda c, ok, m: b.event.emit(c, ok, m),
            on_command_start=lambda c: b.command_start.emit(c),
            on_error=b.error.emit,
        )
        self._busy = False

        self.add_log("Готов к запуску", MUTED)

    # ---------- вспомогательное ----------

    def add_log(self, text, color=TEXT):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(
            f'<span style="color:{MUTED}">{stamp}</span>&nbsp;&nbsp;'
            f'<span style="color:{color}">{html.escape(text)}</span>'
        )

    def _set_status(self, text, color=TEXT):
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; font-size: 17px;")

    # ---------- панель текущей команды ----------

    def _set_cmd_idle(self):
        self.current_cmd.setText("Ожидание команд")
        self.current_cmd.setStyleSheet(self.CMD_STYLE.format(
            bg=PANEL, fg=MUTED, border="#1b2230"
        ))

    @staticmethod
    def _format_command(command) -> str:
        if not isinstance(command, dict):
            return str(command)
        action = command.get("action") or "?"
        parts = [action]
        query = command.get("query")
        if query:
            parts.append(f"«{query}»")
        value = command.get("value")
        if value is not None:
            parts.append(str(value))
        return " ".join(parts)

    def _on_command_start(self, command):
        text = self._format_command(command)
        self.current_cmd.setText(f"▶ Выполняется: {text}")
        self.current_cmd.setStyleSheet(self.CMD_STYLE.format(
            bg=PANEL, fg=BLUE, border=BLUE
        ))

    # ---------- состояния ----------

    def _on_state(self, state):
        self._busy = False

        if state == "starting":
            self._busy = True
            self.button.setEnabled(False)
            self.circle.set_color(BLUE)
            self.circle.set_pulse(True)
            self.circle.set_active(False)
            self._set_status("Запуск…", BLUE)
            self.address.setText("")
            self._set_cmd_idle()

        elif state == "running":
            self.button.setEnabled(True)
            self.button.setText("Остановить сервер")
            self.button.setStyleSheet(STOP_BTN)
            self.circle.set_color(GREEN)
            self.circle.set_pulse(False)
            self.circle.set_active(True)
            self.circle.set_level(0.6)
            self._set_status("Работает", GREEN)
            self.address.setText(f"▶ {self.controller.address}")
            self._set_cmd_idle()

        elif state == "error":
            self.button.setEnabled(True)
            self.button.setText("Запустить сервер")
            self.button.setStyleSheet(START_BTN)
            self.circle.set_color(RED)
            self.circle.set_pulse(False)
            self.circle.set_active(True)
            self.circle.set_level(0.3)
            self._set_status("Ошибка запуска", RED)
            self.address.setText("")
            self._set_cmd_idle()

        else:  # idle
            self.button.setEnabled(True)
            self.button.setText("Запустить сервер")
            self.button.setStyleSheet(START_BTN)
            self.circle.set_color(IDLE)
            self.circle.set_pulse(False)
            self.circle.set_active(False)
            self._set_status(self.IDLE_TEXT, MUTED)
            self.address.setText("")
            self._set_cmd_idle()

    # ---------- управление ----------

    def _on_button(self):
        if self._busy:
            return
        if self.controller.running:
            self._stop_async()
        else:
            self._start_async()

    def _start_async(self):
        if self._busy:
            return
        self._busy = True
        self.bridge.state.emit("starting")
        threading.Thread(target=self._start_worker, daemon=True).start()

    def _start_worker(self):
        try:
            self.controller.start()
            self.add_log(f"HTTP-сервер: {self.controller.address}", GREEN)
            self.add_log("UDP-discovery активен (порт 37020)", GREEN)
            self.add_log("Ожидаю команды от клиента", GREEN)
            self.bridge.state.emit("running")
        except Exception:
            self.bridge.state.emit("error")

    def _stop_async(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        try:
            self.controller.stop()
            self.add_log("Сервер остановлен", MUTED)
        except Exception as e:
            self.bridge.error.emit(f"Ошибка остановки: {e}")
        finally:
            self.bridge.state.emit("idle")

    # ---------- команды от клиента ----------

    def _on_event(self, command, ok, message):
        if not isinstance(command, dict):
            self.add_log(f"Некорректный запрос: {message}", RED)
            self.current_cmd.setText(f"✗ Ошибка: {message}")
            self.current_cmd.setStyleSheet(self.CMD_STYLE.format(
                bg=PANEL, fg=RED, border=RED
            ))
            return

        text = self._format_command(command)
        if ok:
            self.current_cmd.setText(f"✓ {text}")
            self.current_cmd.setStyleSheet(self.CMD_STYLE.format(
                bg=PANEL, fg=GREEN, border=GREEN
            ))
        else:
            self.current_cmd.setText(f"✗ {text} — {message}")
            self.current_cmd.setStyleSheet(self.CMD_STYLE.format(
                bg=PANEL, fg=RED, border=RED
            ))

        action = command.get("action", "?")
        color = GREEN if ok else RED
        self.add_log(
            f"{action}: {json.dumps(command, ensure_ascii=False)} → {message}",
            color,
        )

    # ---------- закрытие ----------

    def closeEvent(self, event):
        if self.controller.running:
            try:
                self.controller.stop()
            except Exception:
                pass
        event.accept()
