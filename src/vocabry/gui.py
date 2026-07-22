from __future__ import annotations

import html
import importlib.resources
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket
import sys
import uuid
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover - depends on Qt distribution
    QWebEngineView = None  # type: ignore[assignment]

from . import __version__
from .config import Settings
from .credentials import delete_deepseek_key, get_deepseek_key, set_deepseek_key
from .generator_protocol import GeneratorManifest, MAX_INPUT_LENGTH, decode_message, encode_message


def configure_logging(settings: Settings) -> Path:
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "gui.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return log_dir


def load_manifests() -> list[GeneratorManifest]:
    root = importlib.resources.files("vocabry.generators")
    manifests: list[GeneratorManifest] = []
    for item in root.iterdir():
        if item.name.endswith(".json"):
            manifests.append(GeneratorManifest.from_mapping(json.loads(item.read_text(encoding="utf-8"))))
    return sorted(manifests, key=lambda value: value.name.casefold())


def enlarge_application_font(application: QApplication, points: float = 1.5) -> None:
    font = application.font()
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() + points)
    elif font.pixelSize() > 0:
        font.setPixelSize(font.pixelSize() + 2)
    application.setFont(font)


class ApiCall(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, method: str, url: str, *, token: str | None = None, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> None:
        super().__init__()
        self.method, self.url, self.token, self.json_body = method, url, token, json_body
        self.headers = dict(headers or {})

    def run(self) -> None:
        try:
            if self.token:
                self.headers["Authorization"] = f"Bearer {self.token}"
            response = httpx.request(self.method, self.url, headers=self.headers, json=self.json_body, timeout=10)
            response.raise_for_status()
            self.succeeded.emit(response.json() if response.content else {})
        except Exception as exc:
            logging.exception("API call failed: %s %s", self.method, self.url)
            self.failed.emit(type(exc).__name__)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vocabry 设置")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("DeepSeek API Key"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setText(get_deepseek_key() or "")
        layout.addWidget(self.key)
        self.status = QLabel("已保存 API Key。" if get_deepseek_key() else "尚未保存 API Key。")
        layout.addWidget(self.status)
        note = QLabel("修改只对保存后新启动的生成器生效。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        remove = buttons.addButton("删除 Key", QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        remove.clicked.connect(self.remove_key)
        layout.addWidget(buttons)

    def save(self) -> None:
        value = self.key.text()
        try:
            if value:
                set_deepseek_key(value)
                if get_deepseek_key() != value:
                    raise RuntimeError("凭据回读校验失败")
            else:
                delete_deepseek_key()
        except Exception as exc:
            logging.exception("Could not save DeepSeek credential")
            QMessageBox.critical(self, "保存失败", f"Windows 凭据管理器无法保存 API Key（{type(exc).__name__}）。")
            self.status.setText("API Key 未保存。")
            return
        QMessageBox.information(self, "保存成功", "DeepSeek API Key 已保存到 Windows 凭据管理器并通过回读校验。")
        self.accept()

    def remove_key(self) -> None:
        try:
            delete_deepseek_key()
        except Exception as exc:
            logging.exception("Could not delete DeepSeek credential")
            QMessageBox.critical(self, "删除失败", f"Windows 凭据管理器无法删除 API Key（{type(exc).__name__}）。")
            return
        self.key.clear()
        QMessageBox.information(self, "删除成功", "DeepSeek API Key 已从 Windows 凭据管理器删除。")
        self.accept()


class GeneratorHost(QObject):
    message = Signal(object)
    failed = Signal(str)
    stopped = Signal()

    def __init__(self, manifest: GeneratorManifest, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-m", manifest.module])
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        self.process.setProcessEnvironment(environment)
        log_dir = settings.data_dir / "logs" / "generators"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.process.setStandardErrorFile(str(log_dir / f"{manifest.id}.log"), QProcess.OpenModeFlag.Append)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.errorOccurred.connect(lambda _: self.failed.emit("generator_process_error"))
        self.process.finished.connect(lambda *_: self.stopped.emit())
        self.buffer = ""
        self.phase = "awaiting_hello"

    def start(self) -> bool:
        credentials: dict[str, str] = {}
        if "deepseek" in self.manifest.required_credentials:
            key = get_deepseek_key()
            if not key:
                return False
            credentials["deepseek"] = key
        self._credentials = credentials
        self.process.start()
        QTimer.singleShot(5000, self._handshake_timeout)
        return True

    def send(self, message: dict[str, Any]) -> None:
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write((encode_message(message) + "\n").encode("utf-8"))

    def shutdown(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.send({"type": "shutdown"})
        if not self.process.waitForFinished(2000):
            self.process.kill()
            self.process.waitForFinished(2000)

    def _read_stdout(self) -> None:
        self.buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if not line:
                continue
            try:
                value = decode_message(line)
            except Exception:
                logging.exception("Generator emitted invalid protocol output")
                self.failed.emit("invalid_generator_output")
                self.process.kill()
                return
            if self.phase == "awaiting_hello":
                if value.get("type") != "hello" or value.get("id") != self.manifest.id or value.get("protocol_version") != self.manifest.protocol_version or value.get("layout") != self.manifest.layout:
                    self.failed.emit("generator_handshake_mismatch")
                    self.process.kill()
                    return
                self.phase = "awaiting_initialized"
                self.send({"type": "initialize", "credentials": self._credentials})
                continue
            if self.phase == "awaiting_initialized":
                if value.get("type") != "initialized":
                    self.failed.emit("generator_initialization_mismatch")
                    self.process.kill()
                    return
                self.phase = "ready"
            self.message.emit(value)

    def _handshake_timeout(self) -> None:
        if self.phase != "ready" and self.process.state() != QProcess.ProcessState.NotRunning:
            self.failed.emit("generator_handshake_timeout")
            self.process.kill()


class ChatPage(QWidget):
    leave_requested = Signal()

    def __init__(self, host: GeneratorHost, base_url: str, token: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.host, self.base_url, self.token = host, base_url, token
        self.task_id: str | None = None
        self.candidate: dict[str, Any] | None = None
        self.calls: set[ApiCall] = set()
        self.busy = True
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        back = QPushButton("← 返回生成器列表")
        back.clicked.connect(self.leave_requested)
        top.addWidget(back)
        top.addWidget(QLabel(f"<b>{html.escape(host.manifest.name)}</b>"))
        top.addStretch()
        root.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages_widget = QWidget()
        self.messages = QVBoxLayout(self.messages_widget)
        self.messages.addStretch()
        self.scroll.setWidget(self.messages_widget)
        root.addWidget(self.scroll, 1)
        controls = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(MAX_INPUT_LENGTH)
        self.input.setPlaceholderText("输入一个英语单词")
        self.input.setEnabled(False)
        self.input.textChanged.connect(self._refresh_send_button)
        self.input.returnPressed.connect(self.submit)
        self.send_button = QPushButton("发送")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.submit)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        controls.addWidget(self.input, 1)
        controls.addWidget(self.send_button)
        controls.addWidget(self.cancel_button)
        root.addLayout(controls)
        host.message.connect(self.on_message)
        host.failed.connect(self.technical_error)

    def has_unfinished_work(self) -> bool:
        return self.task_id is not None

    def submit(self) -> None:
        content = self.input.text()
        if not content.strip():
            return
        self.task_id = str(uuid.uuid4())
        self.candidate = None
        self._bubble("你", content)
        self.input.clear()
        self._set_busy(True)
        self.host.send({"type": "user_input", "task_id": self.task_id, "content": content})

    def cancel(self) -> None:
        if self.task_id:
            self.host.send({"type": "cancel", "task_id": self.task_id})

    def on_message(self, value: dict[str, Any]) -> None:
        kind = value.get("type")
        if kind == "initialized":
            self._set_busy(False)
        elif kind == "message":
            self._bubble("单词查询", str(value.get("content", "")))
        elif kind == "status":
            self._bubble("状态", str(value.get("content", "")), muted=True)
        elif kind == "candidate":
            self.candidate = value["card"]
            self._preview_candidate()
        elif kind == "network_timeout":
            self._timeout_message()
        elif kind == "cancelled":
            self._bubble("状态", "查询已取消。", muted=True)
            self.task_id = None
            self._set_busy(False)
        elif kind == "ready_for_input":
            self.task_id = None
            self.candidate = None
            self._set_busy(False)
        elif kind == "error":
            self.technical_error(str(value.get("code", "generator_error")))

    def _preview_candidate(self) -> None:
        assert self.candidate is not None
        body = {"card_type": self.candidate["card_type"], **self.candidate["fields"]}
        self._api("POST", "/api/v1/preview/candidate", body, self._show_preview)

    def _show_preview(self, value: dict[str, Any]) -> None:
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("<b>候选卡片</b>"))
        faces = QHBoxLayout()
        faces.addWidget(self._html_face("正面", value["front_html"]))
        faces.addWidget(self._html_face("背面", value["back_html"]))
        layout.addLayout(faces)
        actions = QHBoxLayout()
        add = QPushButton("添加")
        discard = QPushButton("放弃")
        add.clicked.connect(lambda: self._check_duplicate(add, discard))
        discard.clicked.connect(lambda: self._finish_candidate("discarded", add, discard))
        actions.addWidget(add)
        actions.addWidget(discard)
        actions.addStretch()
        layout.addLayout(actions)
        self._insert_widget(box)

    def _html_face(self, title: str, content: str) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel(f"<b>{title}</b>"))
        if QWebEngineView is not None:
            view = QWebEngineView()
            view.setMinimumHeight(220)
            view.setHtml(f"<!doctype html><meta charset=utf-8>{content}")
            layout.addWidget(view)
        else:
            label = QLabel(content)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            layout.addWidget(label)
        return panel

    def _check_duplicate(self, add: QPushButton, discard: QPushButton) -> None:
        assert self.candidate is not None
        word = self.candidate["fields"]["word"]
        self._api("GET", f"/api/v1/cards?{urlencode({'word': word})}", None, lambda value: self._confirm_add(value, add, discard))

    def _confirm_add(self, value: dict[str, Any], add: QPushButton, discard: QPushButton) -> None:
        if value.get("items"):
            answer = QMessageBox.question(self, "发现同词卡片", "卡片库中已经存在这个单词。仍然添加一张新卡吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return
        assert self.candidate is not None
        body = {"card_type": self.candidate["card_type"], **self.candidate["fields"]}
        headers = {"Idempotency-Key": self.task_id or str(uuid.uuid4())}
        self._api("POST", "/api/v1/cards", body, lambda result: self._added(result, add, discard), headers=headers)

    def _added(self, result: dict[str, Any], add: QPushButton, discard: QPushButton) -> None:
        add.setText("已添加")
        self._finish_candidate("added", add, discard, card_id=result["card_id"])

    def _finish_candidate(self, action: str, add: QPushButton, discard: QPushButton, *, card_id: str | None = None) -> None:
        add.setEnabled(False)
        discard.setEnabled(False)
        if action == "discarded":
            discard.setText("已放弃")
        message: dict[str, Any] = {"type": "candidate_action", "task_id": self.task_id, "action": action}
        if card_id:
            message["card_id"] = card_id
        self.host.send(message)

    def _timeout_message(self) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.addWidget(QLabel("访问 DeepSeek 超时。"))
        retry = QPushButton("原样重试")
        retry.clicked.connect(lambda: (retry.setEnabled(False), self.host.send({"type": "retry", "task_id": self.task_id})))
        layout.addWidget(retry)
        self._insert_widget(row)

    def technical_error(self, code: str) -> None:
        logging.error("Task %s failed: %s", self.task_id, code)
        self._bubble("错误", f"发生非预期技术故障（任务 ID：{self.task_id or '无'}），请查看日志。")
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.cancel_button.hide()

    def _api(self, method: str, path: str, body: dict[str, Any] | None, success: Callable[[dict[str, Any]], None], *, headers: dict[str, str] | None = None) -> None:
        call = ApiCall(method, self.base_url + path, token=self.token, json_body=body, headers=headers)
        self.calls.add(call)
        call.succeeded.connect(success)
        call.failed.connect(self.technical_error)
        call.finished.connect(lambda: self.calls.discard(call))
        call.start()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.input.setEnabled(not busy)
        self._refresh_send_button()
        self.cancel_button.setVisible(busy)

    def _refresh_send_button(self) -> None:
        self.send_button.setEnabled(not self.busy and bool(self.input.text().strip()))

    def _bubble(self, author: str, content: str, *, muted: bool = False) -> None:
        label = QLabel(f"<b>{html.escape(author)}</b><br>{html.escape(content).replace(chr(10), '<br>')}")
        label.setWordWrap(True)
        if muted:
            label.setStyleSheet("color:#666")
        self._insert_widget(label)

    def _insert_widget(self, widget: QWidget) -> None:
        self.messages.insertWidget(self.messages.count() - 1, widget)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.base_url = f"http://{settings.host}:{settings.port}"
        self.token = ""
        self.host: GeneratorHost | None = None
        self.chat: ChatPage | None = None
        self.closing = False
        self.close_ready = False
        self.health_attempts = 0
        self.calls: set[ApiCall] = set()
        self.reconciliation_id: str | None = None
        self.reconciliation_poll_busy = False
        self.reconciliation_timer = QTimer(self)
        self.reconciliation_timer.setInterval(1_000)
        self.reconciliation_timer.timeout.connect(self._poll_reconciliation)
        self.setWindowTitle(f"Vocabry {__version__}")
        self.resize(1050, 720)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.loading = QLabel("正在启动 Vocabry...")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.loading)
        self.home = self._build_home()
        self.stack.addWidget(self.home)
        self.service = QProcess(self)
        self.service.setProgram(sys.executable)
        self.service.setArguments(["-m", "vocabry", "start", "--data-dir", str(settings.data_dir), "--port", str(settings.port)])
        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.service.setStandardOutputFile(str(log_dir / "vocabd.log"), QProcess.OpenModeFlag.Append)
        self.service.setStandardErrorFile(str(log_dir / "vocabd.log"), QProcess.OpenModeFlag.Append)
        self.service.finished.connect(self._service_finished)
        self._start_service()

    def _build_home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("<h1>卡片生成器</h1>")
        layout.addWidget(title)
        row = QHBoxLayout()
        for manifest in load_manifests():
            button = QPushButton(manifest.name)
            button.setMinimumHeight(70)
            button.clicked.connect(lambda _=False, value=manifest: self.open_generator(value))
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        settings = QPushButton("设置")
        settings.clicked.connect(lambda: SettingsDialog(self).exec())
        layout.addWidget(settings)
        pair = QPushButton("配对 Anki")
        pair.clicked.connect(self.create_pairing_code)
        layout.addWidget(pair)
        reconcile = QPushButton("全量对账 Anki")
        reconcile.clicked.connect(self.start_reconciliation)
        layout.addWidget(reconcile)
        return page

    def start_reconciliation(self) -> None:
        if self.reconciliation_id is not None:
            QMessageBox.information(self, "全量对账", "已有对账任务正在进行，请保持 Anki 打开。")
            return
        call = ApiCall("POST", self.base_url + "/api/v1/sync/reconcile", token=self.token)
        self.calls.add(call)
        call.succeeded.connect(self._reconciliation_started)
        call.failed.connect(lambda code: QMessageBox.critical(self, "全量对账失败", f"无法创建对账任务（{code}）。"))
        call.finished.connect(lambda: self.calls.discard(call))
        call.start()

    def _reconciliation_started(self, value: dict[str, Any]) -> None:
        self.reconciliation_id = value["request_id"]
        self.reconciliation_timer.start()
        QMessageBox.information(self, "全量对账", "已请求 Anki 扫描全部 Vocabry Note。请保持 Anki 和当前 profile 打开。")

    def _poll_reconciliation(self) -> None:
        if not self.reconciliation_id or self.reconciliation_poll_busy:
            return
        self.reconciliation_poll_busy = True
        call = ApiCall(
            "GET", self.base_url + f"/api/v1/sync/reconcile/{self.reconciliation_id}", token=self.token
        )
        self.calls.add(call)
        call.succeeded.connect(self._handle_reconciliation_status)
        call.failed.connect(self._reconciliation_poll_failed)
        call.finished.connect(lambda: self.calls.discard(call))
        call.finished.connect(lambda: setattr(self, "reconciliation_poll_busy", False))
        call.start()

    def _reconciliation_poll_failed(self, code: str) -> None:
        self.reconciliation_timer.stop()
        self.reconciliation_id = None
        QMessageBox.critical(self, "全量对账失败", f"无法读取对账状态（{code}），请查看日志。")

    def _handle_reconciliation_status(self, value: dict[str, Any]) -> None:
        status = value["status"]
        if status == "ready":
            self.reconciliation_timer.stop()
            report = value["report"]
            message = (
                f"Anki Vocabry Note：{report['anki_notes']}\n"
                f"Vocabry 活动卡片：{report['active_cards']}\n\n"
                f"需要补建：{report['missing']}\n"
                f"旧版 Note 归属迁移：{report['legacy_adoptions']}\n"
                f"重复 Note：{report['duplicates']}\n"
                f"已删除卡片残留：{report['deleted_card_notes']}\n"
                f"孤立 Note：{report['orphans']}\n"
                f"其他数据库 Note：{report['foreign_database_notes']}\n\n"
                f"确认后将更新全部活动卡片，并删除 {report['delete_count']} 个残留 Note。是否执行？"
            )
            answer = QMessageBox.question(self, "全量对账报告", message)
            action = "execute" if answer == QMessageBox.StandardButton.Yes else "cancel"
            call = ApiCall(
                "POST", self.base_url + f"/api/v1/sync/reconcile/{self.reconciliation_id}/{action}", token=self.token
            )
            self.calls.add(call)
            call.succeeded.connect(self._reconciliation_approved if action == "execute" else self._reconciliation_cancelled)
            call.failed.connect(lambda code: self._reconciliation_poll_failed(code))
            call.finished.connect(lambda: self.calls.discard(call))
            call.start()
        elif status == "completed":
            self.reconciliation_timer.stop()
            result = value.get("result") or {}
            self.reconciliation_id = None
            QMessageBox.information(
                self,
                "全量对账完成",
                f"已同步 {len(result.get('mappings', []))} 张活动卡片，删除 {len(result.get('deleted_note_ids', []))} 个残留 Note。",
            )
        elif status in {"cancelled", "failed"}:
            self.reconciliation_timer.stop()
            self.reconciliation_id = None

    def _reconciliation_approved(self, _value: dict[str, Any]) -> None:
        self.reconciliation_timer.start()

    def _reconciliation_cancelled(self, _value: dict[str, Any]) -> None:
        self.reconciliation_id = None
        QMessageBox.information(self, "全量对账", "已取消，没有修改 Anki 卡片。")

    def create_pairing_code(self) -> None:
        call = ApiCall("POST", self.base_url + "/api/v1/pairing/codes", token=self.token)
        self.calls.add(call)
        call.succeeded.connect(self._show_pairing_code)
        call.failed.connect(lambda code: QMessageBox.critical(self, "配对失败", f"无法生成 Anki 配对码（{code}），请查看日志。"))
        call.finished.connect(lambda: self.calls.discard(call))
        call.start()

    def _show_pairing_code(self, value: dict[str, Any]) -> None:
        QMessageBox.information(
            self,
            "Anki 配对码",
            f"配对码：{value['code']}\n\n请在 5 分钟内打开 Anki 的“工具 → 配对 Vocabry...”，输入此配对码。",
        )

    def _start_service(self) -> None:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((self.settings.host, self.settings.port)) == 0:
                QMessageBox.critical(self, "Vocabry", f"端口 {self.settings.port} 已被占用，请先关闭现有服务或占用该端口的程序。")
                self.close_ready = True
                QTimer.singleShot(0, self.close)
                return
        self.service.start()
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self._check_health)
        self.health_timer.start(200)

    def _check_health(self) -> None:
        self.health_attempts += 1
        try:
            response = httpx.get(self.base_url + "/api/v1/health", timeout=0.15)
            value = response.json()
            if value.get("service") == "vocabry" and value.get("api_version") == 1:
                self.health_timer.stop()
                self.token = self.settings.token_path.read_text(encoding="utf-8").strip()
                self.stack.setCurrentWidget(self.home)
                return
        except Exception:
            pass
        if self.health_attempts >= 50 or self.service.state() == QProcess.ProcessState.NotRunning:
            self.health_timer.stop()
            QMessageBox.critical(self, "Vocabry", "核心服务启动失败，请查看 vocabd.log。")
            self.initiate_close()

    def open_generator(self, manifest: GeneratorManifest) -> None:
        key = get_deepseek_key() if "deepseek" in manifest.required_credentials else "available"
        if not key:
            QMessageBox.information(self, "DeepSeek API Key", "请先在设置中配置共享的 DeepSeek API Key。")
            SettingsDialog(self).exec()
            if not get_deepseek_key():
                return
        self.host = GeneratorHost(manifest, self.settings, self)
        self.chat = ChatPage(self.host, self.base_url, self.token, self)
        self.chat.leave_requested.connect(self.leave_generator)
        self.stack.addWidget(self.chat)
        self.stack.setCurrentWidget(self.chat)
        if not self.host.start():
            self.chat.technical_error("missing_credential")

    def leave_generator(self) -> None:
        if self.chat and self.chat.has_unfinished_work():
            answer = QMessageBox.question(self, "离开生成器", "离开将取消并丢弃当前任务，是否继续？")
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.chat.cancel()
        if self.host:
            self.host.shutdown()
        if self.chat:
            self.stack.removeWidget(self.chat)
            self.chat.deleteLater()
        self.host = None
        self.chat = None
        self.stack.setCurrentWidget(self.home)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.close_ready:
            event.accept()
            return
        event.ignore()
        self.initiate_close()

    def initiate_close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.loading.setText("正在关闭 Vocabry...")
        self.stack.setCurrentWidget(self.loading)
        if self.host:
            if self.chat and self.chat.task_id:
                self.chat.cancel()
            self.host.shutdown()
        if self.service.state() == QProcess.ProcessState.NotRunning:
            self._finish_close()
            return
        call = ApiCall("POST", self.base_url + "/api/v1/admin/shutdown", token=self.token)
        self.calls.add(call)
        call.finished.connect(lambda: self.calls.discard(call))
        call.finished.connect(self._wait_for_service)
        call.start()

    def _wait_for_service(self) -> None:
        self.shutdown_ticks = 0
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.timeout.connect(self._poll_shutdown)
        self.shutdown_timer.start(200)

    def _poll_shutdown(self) -> None:
        if self.service.state() == QProcess.ProcessState.NotRunning:
            self.shutdown_timer.stop()
            self._finish_close()
            return
        self.shutdown_ticks += 1
        if self.shutdown_ticks >= 50:
            logging.error("vocabd did not exit after shutdown request; forcing termination")
            self.loading.setText("服务未能正常关闭，正在强制结束...")
            self.service.kill()

    def _service_finished(self, *_: Any) -> None:
        if self.closing:
            self._finish_close()

    def _finish_close(self) -> None:
        if self.service.state() != QProcess.ProcessState.NotRunning:
            return
        self.close_ready = True
        QTimer.singleShot(0, self.close)


def main() -> None:
    settings = Settings.load()
    configure_logging(settings)
    application = QApplication(sys.argv)
    application.setApplicationName("Vocabry")
    enlarge_application_font(application)
    window = MainWindow(settings)
    window.show()
    raise SystemExit(application.exec())


if __name__ == "__main__":
    main()
