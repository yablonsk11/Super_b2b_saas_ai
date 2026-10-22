from PyQt6.QtCore import (QEasingCurve, QObject, QPointF, QPropertyAnimation,
                          Qt, QTimer, pyqtSignal)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (QApplication, QGraphicsOpacityEffect, QLabel,
                             QMainWindow, QPushButton, QTextEdit, QVBoxLayout,
                             QWidget)
import html
import json
import math
from datetime import datetime
import client_connection
import client_voice_recognizer
from concurrent.futures import ThreadPoolExecutor
import threading


from config import DEMO_MODE

# =====================================================================
#  ИНТЕРФЕЙС (PyQt6)
# =====================================================================

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
QPushButton {{
    background: transparent; color: {TEXT}; border: 1px solid {RED};
    border-radius: 10px; padding: 10px 22px; font-size: 14px;
}}
QPushButton:hover {{ background: rgba(255, 77, 94, 40); }}
"""


class Bridge(QObject):
    """Переправляет события из фоновых потоков в главный поток Qt."""
    wake = pyqtSignal()
    idle = pyqtSignal()
    level = pyqtSignal(float)
    heard = pyqtSignal(str)
    parsed = pyqtSignal(object)
    sent = pyqtSignal(object, int)
    error = pyqtSignal(str)
    connected = pyqtSignal(bool, str)
    ready = pyqtSignal()


class GlowCircle(QWidget):
    """Круг со свечением. Свечение плавно следует за целевой яркостью."""

    def __init__(self, color=IDLE):
        super().__init__()
        self._color = QColor(color)
        self._target_color = QColor(color)
        self._glow = 0.0
        self._level = 0.0
        self._active = False       # реагирует на голос
        self._pulse = False        # ровная пульсация
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

        # свечение
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

        # сам круг
        r = base * (1 + 0.1 * g)
        fill = QColor(self._color)
        fill.setAlphaF(0.15 + 0.25 * g)
        p.setBrush(fill)
        p.setPen(QPen(self._color, 3))
        p.drawEllipse(center, r, r)


class ConnectOverlay(QWidget):
    """Полупрозрачный экран подключения поверх основного окна."""
    retry = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self._hiding = False

        self.dot = GlowCircle(BLUE)
        self.dot.setFixedSize(150, 150)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 17px; background: transparent;")

        self.hint = QLabel()
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet(f"color: {MUTED}; font-size: 13px; background: transparent;")

        self.button = QPushButton("Повторить подключение")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self.retry.emit)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        lay.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        lay.addWidget(self.hint)
        lay.addSpacing(8)
        lay.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(700)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self._after_fade)

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), QColor(8, 10, 16, 215))

    # ---------- состояния ----------

    def show_connecting(self):
        self._hiding = False
        self.anim.stop()
        self.effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self.dot.set_color(BLUE)
        self.dot.set_active(False)
        self.dot.set_pulse(True)
        self.label.setText("Подключение к серверу…")
        self.hint.setText("Ищу сервер в локальной сети")
        self.button.hide()

    def show_ok(self, address):
        self.dot.set_color(GREEN)
        self.dot.set_pulse(False)
        self.dot.set_level(1.0)
        self.dot.set_active(True)          # яркое ровное свечение
        self.label.setText("Подключено")
        self.hint.setText(address)
        self.button.hide()
        QTimer.singleShot(900, self._fade_out)

    def show_fail(self):
        self.dot.set_color(RED)
        self.dot.set_pulse(False)
        self.dot.set_level(0.3)
        self.dot.set_active(True)
        self.label.setText("Подключение не удалось")
        self.hint.setText("Сервер не отвечает в локальной сети.\n"
                          "Проверьте, что он запущен и порты открыты.")
        self.button.show()

    def _fade_out(self):
        self._hiding = True
        self.anim.start()

    def _after_fade(self):
        if self._hiding:
            self.hide()


class Central(QWidget):
    """Центральный виджет, который растягивает оверлей на всю область."""

    def __init__(self):
        super().__init__()
        self.setObjectName("central")
        self.overlay = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.overlay:
            self.overlay.setGeometry(self.rect())


class JarvisWindow(QMainWindow):
    IDLE_TEXT = "Скажите «Джарвис»"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis")
        self.resize(520, 700)
        self.setStyleSheet(STYLE)

        # ---- интерфейс ----
        central = Central()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        self.circle = GlowCircle(IDLE)
        lay.addWidget(self.circle, stretch=1)

        self.status = QLabel(self.IDLE_TEXT)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(170)
        lay.addWidget(self.log)

        self.overlay = ConnectOverlay(central)
        central.overlay = self.overlay
        self.overlay.retry.connect(self.connect_to_server)

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._reset_status)
        self._listening = False
        self._listener_loading = False
        self.listener = None
        self._set_status(self.IDLE_TEXT, MUTED)

        # ---- логика ----
        self.bridge = b = Bridge()
        b.wake.connect(self.on_wake)
        b.idle.connect(self.on_idle)
        b.level.connect(self.circle.set_level)
        b.heard.connect(self.on_heard)
        b.parsed.connect(self.on_parsed)
        b.sent.connect(self.on_sent)
        b.error.connect(lambda m: self.add_log(m, RED))
        b.connected.connect(self.on_connected)
        b.ready.connect(self.on_ready)

        self.processor = client_voice_recognizer.CommandProcessor()
        self.sender = client_connection.RequestSender(on_error=b.error.emit,
                                    on_result=lambda c, s: b.sent.emit(c, s))
        self.tts = client_voice_recognizer.TTSPlayer(on_speaking=self._on_tts_speaking)
        self.pool = ThreadPoolExecutor(max_workers=1)   # разбор команд по порядку

        if DEMO_MODE:
            self.overlay.hide()
            self.add_log("Демо-режим: поиск сервера пропущен", MUTED)
            self._start_listener()
        else:
            QTimer.singleShot(300, self.connect_to_server)

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

    def _reset_status(self):
        if not self._listening:
            self._set_status(self.IDLE_TEXT, MUTED)

    # ---------- подключение ----------

    def connect_to_server(self):
        self.overlay.show_connecting()
        self.add_log("Поиск сервера в локальной сети…", MUTED)
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        ok = self.sender.connect()
        self.bridge.connected.emit(ok, self.sender.base_url or "")

    def on_connected(self, ok, address):
        if ok:
            self.add_log(f"Сервер найден: {address}", GREEN)
            self.overlay.show_ok(address)
            self._start_listener()
        else:
            self.add_log("Сервер не найден", RED)
            self.overlay.show_fail()

    # ---------- запуск распознавания ----------

    def _start_listener(self):
        if self.listener or self._listener_loading:
            return
        self._listener_loading = True
        self._set_status("Загрузка распознавания речи…", MUTED)
        threading.Thread(target=self._listener_worker, daemon=True).start()

    def _listener_worker(self):
        b = self.bridge
        try:
            self.listener = client_voice_recognizer.VoiceListener(
                on_wake=b.wake.emit, on_idle=b.idle.emit,
                on_command=b.heard.emit, on_level=b.level.emit,
                on_error=b.error.emit,
            )
            self.listener.start()
            b.ready.emit()
        except Exception as e:
            b.error.emit(f"Не удалось запустить распознавание: {e}")
        finally:
            self._listener_loading = False

    def on_ready(self):
        self.add_log("Готов. Скажите «Джарвис»", GREEN)
        self._set_status(self.IDLE_TEXT, MUTED)

    # ---------- события голоса ----------

    def on_wake(self):
        self._listening = True
        self._reset_timer.stop()
        self.circle.set_color(GREEN)
        self.circle.set_active(True)
        self._set_status("Слушаю…", GREEN)

    def on_idle(self):
        self._listening = False
        self.circle.set_active(False)
        self.circle.set_color(IDLE)
        self._set_status(self.IDLE_TEXT, MUTED)

    def _on_tts_speaking(self, active: bool):
        """Глушим микрофон на время озвучки, чтобы не ловить эхо."""
        if self.listener:
            self.listener.set_muted(bool(active))

    def on_heard(self, text):
        self._listening = False
        self.circle.set_active(False)
        self.circle.set_color(IDLE)
        self._set_status("Хорошо, босс", GREEN)
        self._reset_timer.start(2500)
        print(f"[APP] on_heard: {text!r}")
        self.add_log(f"Услышал: «{text}»")
        self.pool.submit(self._process, text)

    def _process(self, text):
        """Разбор → озвучка → отправка. GigaChat может отвечать секунды."""
        print(f"[APP] _process start: {text!r}")
        try:
            command = self.processor.process(text)
            print(f"[APP] command parsed: {command!r}")
        except Exception as e:
            print(f"[APP] command parse exception: {e}")
            self.bridge.error.emit(f"Ошибка разбора команды: {e}")
            command = {"action": "none"}

        speech = self.processor.generate_response_text(command, original_text=text)
        print(f"[APP] speech text: {speech!r}")
        self.tts.clear()
        self.tts.speak(speech)
        self.bridge.parsed.emit(command)
        if command.get("action") != "none":
            self.sender.send(command)

    def on_parsed(self, command):
        if command.get("action") == "none":
            self.add_log("Команда не распознана", MUTED)
            self._set_status("Не понял, босс", MUTED)
            return

        self.add_log(f"Команда: {json.dumps(command, ensure_ascii=False)}", BLUE)

    def on_sent(self, command, status):
        color = GREEN if status < 400 else RED
        self.add_log(f"Отправлено на сервер: "
                     f"{json.dumps(command, ensure_ascii=False)} (HTTP {status})", color)

    # ---------- закрытие ----------

    def closeEvent(self, event):
        if self.listener:
            self.listener.stop()
        self.sender.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        event.accept()
