from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from vocabry.gui import ChatPage, enlarge_application_font


class FakeHost(QObject):
    message = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.manifest = SimpleNamespace(name="单词查询")
        self.sent: list[dict[str, object]] = []

    def send(self, value: dict[str, object]) -> None:
        self.sent.append(value)


def test_application_font_is_enlarged_slightly() -> None:
    application = QApplication.instance() or QApplication([])
    original = application.font()
    original_size = original.pointSizeF()

    enlarge_application_font(application)

    assert application.font().pointSizeF() == original_size + 1.5
    application.setFont(original)


def test_send_button_tracks_nonempty_input_while_generator_is_ready() -> None:
    application = QApplication.instance() or QApplication([])
    host = FakeHost()
    page = ChatPage(host, "http://127.0.0.1:8765", "token")

    assert not page.input.isEnabled()
    assert not page.send_button.isEnabled()

    host.message.emit({"type": "initialized"})
    application.processEvents()
    assert page.input.isEnabled()
    assert not page.send_button.isEnabled()

    page.input.setText("  concise  ")
    assert page.send_button.isEnabled()
    page.input.setText("   ")
    assert not page.send_button.isEnabled()

    page.input.setText("concise")
    page.send_button.click()
    assert host.sent[-1]["type"] == "user_input"
    assert not page.send_button.isEnabled()
    assert not page.input.isEnabled()

    page.deleteLater()
