"""Visible, narrated demonstration of the real MLA app with fictitious data (isolated data folder).

Usage:  .venv\\Scripts\\python demo\\run_demo.py            (MLA_DEMO_SPEED=2 halves the pauses)

- Data lives in demo/demo-data (never %LOCALAPPDATA%\\MLA). Only the simulated marketplace is automated.
- The script drives the real UI (native animateClick + character-by-character typing; QtTest is not used: its
  internal asserts abort the process outside a test runner) and plays the human in the simulated
  marketplace (login, CAPTCHA). Native Windows file dialogs are replaced by fixed paths (not automatable).
- Recording: frames are composed from the MLA windows (Qt rendering) and the simulated-marketplace Edge window
  (window capture), so other apps and notifications are never recorded. Output: demo/recordings/*.mp4.
- Every check is recorded in demo/output/demo-results.json; screenshots go to demo/screenshots/.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import sys

import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DEMO = ROOT / "demo"
DATA = DEMO / "demo-data"
SHOTS = DEMO / "screenshots"
REC = DEMO / "recordings"
OUT = DEMO / "output"
FIX = DEMO / "fixtures"
SPEED = float(os.environ.get("MLA_DEMO_SPEED", "1"))
os.environ["MLA_DATA_DIR"] = str(DATA)  # belt and braces: nothing may touch the real data folder

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QSize, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QImage, QPainter  # noqa: E402
from PySide6.QtMultimedia import (  # noqa: E402
    QMediaCaptureSession, QMediaFormat, QMediaRecorder, QVideoFrame, QVideoFrameInput, QVideoSink, QWindowCapture,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QVBoxLayout,
)

log = logging.getLogger("mla.demo")


# ============================================================================ results
class Results:
    def __init__(self, path: Path):
        self.path = path
        self.section = ""
        self.items: list[dict] = []
        self.started = datetime.now().isoformat(timespec="seconds")

    def _add(self, kind: str, name: str, detail: str = "") -> None:
        self.items.append({"section": self.section, "kind": kind, "name": name, "detail": detail,
                           "at": datetime.now().strftime("%H:%M:%S")})
        log.info("[%s] %s: %s %s", kind, self.section, name, detail)
        self.save()

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self._add("ok" if ok else "fail", name, detail)
        return ok

    def skip(self, name: str, reason: str) -> None:
        self._add("skip", name, reason)

    def note(self, text: str) -> None:
        self._add("note", text)

    def bug(self, text: str) -> None:
        self._add("bug", text)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"started": self.started, "items": self.items}, ensure_ascii=False,
                                        indent=1), encoding="utf-8")


R = Results(OUT / "demo-results.json")


# ============================================================================ narration banner
class Banner(QFrame):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        from mla.ui.theme import T
        self.setObjectName("demoBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(f"QFrame#demoBanner {{ background: {T.raised_hi}; border: 1px solid {T.violet}; "
                           f"border-radius: 10px; }} QLabel {{ background: transparent; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 9)
        layout.setSpacing(1)
        self.title = QLabel("")
        self.title.setStyleSheet(f"color: {T.violet_text}; font-size: 12px; font-weight: 600;")
        self.text = QLabel("")
        self.text.setStyleSheet(f"color: {T.text}; font-size: 14px;")
        self.text.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.text)
        screen = QApplication.primaryScreen().availableGeometry()
        self.setFixedWidth(min(940, screen.width() - 40))
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - 84)

    def set(self, title: str, text: str) -> None:
        self.title.setText(f"DEMONSTRAÇÃO MLA (dados fictícios)  |  {title}")
        self.text.setText(text)
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 14)
        self.show()
        self.raise_()


# ============================================================================ window helpers (Win32)
user32 = ctypes.windll.user32
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_FLAGS = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW


def bring_front(hwnd: int) -> None:
    if hwnd:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_FLAGS)


def edge_hwnd() -> int:
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if "Feira Local" in buffer.value:
                found.append(hwnd)
        return True

    user32.EnumWindows(proto(callback), 0)
    return found[0] if found else 0


# ============================================================================ recorder (MLA windows + simulated Edge only)
class Recorder(QObject):
    OUT_SIZE = QSize(1280, 720)

    def __init__(self, path: Path, banner: Banner, fps: int = 5):
        super().__init__()
        from mla.ui.theme import T
        self.bg = QColor(T.canvas)
        self.banner, self.main, self.focus = banner, None, "app"
        self.period_us = int(1_000_000 / fps)
        self.clock = QElapsedTimer()
        self.frames = 0
        self.edge_image: QImage | None = None
        self.frame_input = QVideoFrameInput()
        self.session = QMediaCaptureSession()
        self.session.setVideoFrameInput(self.frame_input)
        self.recorder = QMediaRecorder()
        self.session.setRecorder(self.recorder)
        fmt = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        fmt.setVideoCodec(QMediaFormat.VideoCodec.H264)
        self.recorder.setMediaFormat(fmt)
        self.recorder.setVideoResolution(self.OUT_SIZE)
        self.recorder.setVideoFrameRate(fps)
        self.recorder.setVideoBitRate(1_600_000)
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(path)))
        self.recorder.errorOccurred.connect(lambda e, s: R.note(f"Gravação: erro {e} {s}"))
        self.edge_session = QMediaCaptureSession()
        self.edge_capture = QWindowCapture()
        self.edge_sink = QVideoSink()
        self.edge_session.setWindowCapture(self.edge_capture)
        self.edge_session.setVideoSink(self.edge_sink)
        self.edge_sink.videoFrameChanged.connect(self._edge_frame)
        self.edge_capture.errorOccurred.connect(self._edge_lost)
        self.timer = QTimer(self, interval=int(1000 / fps), timeout=self._tick)
        self.watch = QTimer(self, interval=1000, timeout=self._find_edge)
        self.path = path

    def start(self) -> None:
        self.recorder.record()
        self.clock.start()
        self.timer.start()
        self.watch.start()

    def stop(self) -> None:
        self.timer.stop()
        self.watch.stop()
        self.edge_capture.stop()
        self.recorder.stop()

    def _edge_frame(self, frame) -> None:
        if frame.isValid():
            self.edge_image = frame.toImage()

    def _edge_lost(self, *_args) -> None:
        self.edge_capture.stop()
        self.edge_image = None

    def _find_edge(self) -> None:
        if self.edge_capture.isActive():
            return
        for window in QWindowCapture.capturableWindows():
            if "Feira Local" in window.description():  # only the simulated marketplace
                self.edge_capture.setWindow(window)
                self.edge_capture.start()
                return

    def compose(self) -> QImage:
        main = self.main
        size = main.size() if main is not None and main.isVisible() else QSize(1366, 697)
        canvas = QImage(size, QImage.Format.Format_RGB32)
        canvas.fill(self.bg)
        painter = QPainter(canvas)
        origin = main.geometry().topLeft() if main is not None else QPoint(0, 0)
        if self.focus == "browser" and self.edge_image is not None and self.edge_capture.isActive():
            image = self.edge_image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
            painter.drawImage((size.width() - image.width()) // 2, (size.height() - image.height()) // 2, image)
        elif main is not None and main.isVisible():
            painter.drawPixmap(0, 0, main.grab())
            for widget in QApplication.topLevelWidgets():
                # only MLA dialogs and menus: tooltips are created/destroyed while the cursor moves
                if not isinstance(widget, (QDialog, QMenu)) or not widget.isVisible() or widget is main:
                    continue
                painter.drawPixmap(widget.geometry().topLeft() - origin, widget.grab())
        if self.banner.isVisible():
            painter.drawPixmap(self.banner.geometry().topLeft() - origin, self.banner.grab())
        painter.end()
        return canvas

    def _tick(self) -> None:
        try:
            frame_image = QImage(self.OUT_SIZE, QImage.Format.Format_RGB32)
            frame_image.fill(self.bg)
            composed = self.compose().scaled(self.OUT_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
            painter = QPainter(frame_image)
            painter.drawImage((self.OUT_SIZE.width() - composed.width()) // 2,
                              (self.OUT_SIZE.height() - composed.height()) // 2, composed)
            painter.end()
            frame = QVideoFrame(frame_image.convertToFormat(QImage.Format.Format_RGBA8888))
            start = self.clock.elapsed() * 1000
            frame.setStartTime(start)
            frame.setEndTime(start + self.period_us)
            self.frame_input.sendVideoFrame(frame)
            self.frames += 1
        except Exception as exc:  # never let recording break the demo
            log.warning("quadro de gravação descartado: %s", exc)


# ============================================================================ driver
class Bus(QObject):
    banner = Signal(str, str)  # thread-safe banner updates from the automation worker


class Demo:
    def __init__(self, app: QApplication):
        self.app = app
        self.banner = Banner()
        self.bus = Bus()
        self.bus.banner.connect(self.banner.set)
        self.rec = Recorder(REC / f"mla-demo-{datetime.now():%Y%m%d-%H%M}.mp4", self.banner)
        self.shot_no = 0
        self.reviews: list = []
        self.reviews_handled = 0
        self.manual: list[str] = []
        self.manual_handled = 0
        self.finished_items: list = []
        self.window = None
        self.ctx = None
        self.title = ""
        self.gen = None

    # ------------------------------------------------------------------ app lifecycle
    def open_app(self) -> None:
        from mla.config.paths import AppPaths
        from mla.services.context import AppContext
        from mla.ui.main_window import MainWindow
        self.paths = AppPaths(DATA).ensure()
        self.ctx = AppContext.open(self.paths)
        self.window = MainWindow(self.ctx)
        self.window.showMaximized()
        self.rec.main = self.window
        bridge = self.window.services.bridge
        bridge.reviewRequested.connect(self.reviews.append)
        bridge.manualActionRequested.connect(lambda _item, message: self.manual.append(message))
        bridge.itemFinished.connect(lambda item, status, message: self.finished_items.append((item, status, message)))
        executor = self.window.services.executor
        original = bridge.manual_action_requested

        def human(item, message):  # worker thread: plays the user in the simulated marketplace
            try:
                page = executor._browser.session.page
                if "login.html" in page.url:
                    self.bus.banner.emit(self.title, "Login simulado: o roteiro digita e-mail e senha no navegador "
                                                     "dedicado da conta (o MLA esperaria você fazer isso).")
                    page.click("#email")
                    page.type("#email", "demo@feiralocal.test", delay=int(70 / SPEED))
                    page.type("#password", "senha-demo", delay=int(70 / SPEED))
                    page.wait_for_timeout(int(700 / SPEED))
                    page.click("#login-submit")
                    page.wait_for_load_state("domcontentloaded")
                elif page.locator("#captcha").is_visible():
                    self.bus.banner.emit(self.title, "CAPTCHA simulado: o MLA parou e pediu ajuda; o roteiro faz o "
                                                     "papel do usuário e clica em “Sou humano”.")
                    page.wait_for_timeout(int(2500 / SPEED))
                    page.click("#captcha-ok")
            except Exception as exc:
                log.warning("ação humana simulada falhou: %s", exc)
            original(item, message)

        bridge.manual_action_requested = human

    def nav(self, key: str, **kwargs) -> None:
        self.window.navigate(key, **kwargs)

    def page(self, key: str):
        return self.window.pages[key]

    # ------------------------------------------------------------------ generator helpers
    def say(self, text: str, ms: int = 1800):
        self.banner.set(self.title, text)
        yield ms

    def wait_for(self, predicate, timeout: int = 20000, what: str = "condição"):
        waited = 0
        while not predicate():
            if waited >= timeout:
                raise TimeoutError(f"tempo esgotado esperando: {what}")
            yield 150
            waited += 150

    @staticmethod
    def later(fn) -> None:
        QTimer.singleShot(0, fn)

    def click(self, widget, pause: int = 700):
        """Visible native click (no QtTest: its internal asserts abort the process outside a test runner)."""
        if widget is None:
            raise RuntimeError("botão não encontrado")
        QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
        yield 350
        self.later(widget.animateClick)
        yield pause

    def type(self, widget, text: str, cps: int = 28, full: int = 60):
        """Types character by character (same textChanged signals as a user)."""
        widget.setFocus()
        QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
        if isinstance(widget, QLineEdit):
            widget.clear()
        insert = widget.insert if isinstance(widget, QLineEdit) else widget.insertPlainText
        for ch in text[:full]:
            insert(ch)
            yield max(5, int(1000 / cps))
        if len(text) > full:
            insert(text[full:])
        yield 250

    def choose(self, combo: QComboBox, data=None, text: str | None = None):
        index = combo.findData(data) if data is not None else combo.findText(text)
        if index < 0:
            raise RuntimeError(f"opção não encontrada: {data or text}")
        QCursor.setPos(combo.mapToGlobal(combo.rect().center()))
        yield 300
        combo.setCurrentIndex(index)
        yield 600

    @staticmethod
    def find_top(cls, text_in_title: str = ""):
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, cls) and widget.isVisible() and text_in_title in widget.windowTitle():
                return widget
        return None

    def wait_dialog(self, cls, timeout: int = 15000, title: str = ""):
        yield from self.wait_for(lambda: self.find_top(cls, title) is not None, timeout, cls.__name__)

    @staticmethod
    def button(parent, text: str) -> QPushButton | None:
        for b in parent.findChildren(QPushButton):
            if b.text().strip() == text and b.isVisible():
                return b
        return None

    def answer_box(self, contains: str = "", button_text: str | None = None, timeout: int = 15000):
        """Wait for a message box, screenshot it and press a button (default: the accept button)."""
        yield from self.wait_for(lambda: isinstance(QApplication.activeModalWidget(), QMessageBox), timeout,
                                 "caixa de mensagem")
        box: QMessageBox = QApplication.activeModalWidget()
        text = box.text()
        if contains and contains.lower() not in text.lower():
            R.note(f"Mensagem diferente do esperado ({contains!r}): {text[:160]}")
        yield 1400
        self.snap(f"mensagem-{box.windowTitle()}")
        target = None
        for b in box.buttons():
            if (button_text and b.text() == button_text) or (
                    not button_text and box.buttonRole(b) == QMessageBox.ButtonRole.AcceptRole):
                target = b
        yield from self.click(target or box.buttons()[0])
        return text

    def snap(self, name: str) -> Path:
        self.shot_no += 1
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())[:60].strip("-")
        path = SHOTS / f"{self.shot_no:03d}-{safe}.png"
        try:
            self.rec.compose().save(str(path))
        except Exception as exc:
            log.warning("captura falhou: %s", exc)
        return path

    def focus_browser(self, on: bool):
        self.rec.focus = "browser" if on else "app"
        bring_front(edge_hwnd() if on else int(self.window.winId()))
        yield 300

    def close_modals(self):
        for _ in range(6):
            widget = QApplication.activeModalWidget()
            if widget is None:
                break
            if isinstance(widget, QMessageBox):
                widget.done(0)
            elif isinstance(widget, QDialog):
                widget.reject()
            yield 400

    # ------------------------------------------------------------------ runner
    def start(self) -> None:
        SHOTS.mkdir(parents=True, exist_ok=True)
        REC.mkdir(parents=True, exist_ok=True)
        if os.environ.get("MLA_DEMO_NOREC") != "1":
            self.rec.start()
        else:
            R.note("Gravação desligada nesta execução (MLA_DEMO_NOREC=1).")
        self.gen = self.sections()
        QTimer.singleShot(1500, self._step)

    def _step(self) -> None:
        try:
            delay = next(self.gen)
        except StopIteration:
            self.finish()
            return
        except Exception as exc:  # a failure outside a section guard
            R.check("roteiro executado sem erro", False, f"{type(exc).__name__}: {exc}")
            self.finish()
            return
        QTimer.singleShot(max(10, int((delay or 0) / SPEED)), self._step)

    def sections(self):
        plan = [
            ("A. Dashboard", self.sec_dashboard),
            ("B. Catálogo mestre", self.sec_catalog),
            ("C. Central de Importações", self.sec_imports),
            ("D. Compatibilidades", self.sec_compat),
            ("E. Grupos", self.sec_groups),
            ("G. Marketplaces e contas", self.sec_accounts),
            ("F. Preparação de anúncios", self.sec_listings),
            ("H. Automação no marketplace simulado", self.sec_automation),
            ("G. Teste de conexão (simulado)", self.sec_connection),
            ("I. Histórico e relatórios", self.sec_history),
            ("J. Configurações, backup, licença e logs", self.sec_settings),
            ("A. Dashboard final", self.sec_dashboard_end),
        ]
        for title, section in plan:
            self.title = R.section = title
            try:
                yield from section()
            except Exception as exc:
                R.check("seção concluída sem erro", False, f"{type(exc).__name__}: {exc}")
                log.error("seção %s interrompida:\n%s", title, traceback.format_exc())
                self.snap(f"erro-{title}")
                yield from self.close_modals()
                try:
                    self.nav("dashboard")
                except Exception:
                    pass
                yield 1000

    def finish(self) -> None:
        self.banner.set("Concluída", "Demonstração encerrada. O MLA continua aberto no Dashboard com os dados de "
                                     "demonstração para a sua avaliação.")
        try:
            self.nav("dashboard")
            bring_front(int(self.window.winId()))
        except Exception:
            pass
        QTimer.singleShot(4000, self._stop_recording)

    def _stop_recording(self) -> None:
        self.rec.stop()
        R.note(f"Gravação salva em {self.rec.path} ({self.rec.frames} quadros)")
        self.banner.hide()

    # ============================================================================ sections
    def sec_dashboard(self):
        self.nav("dashboard")
        yield from self.say("Painel principal com o banco de demonstração vazio: catálogo, anúncios, pendências e "
                            "situação por marketplace.", 2500)
        subtitle = self.page("dashboard").header.subtitle.text()
        R.check("Dashboard abre com dados reais do banco (vazio)", "0 produtos" in subtitle, subtitle)
        self.snap("dashboard-vazio")
        yield from self.say("Navegação pela barra lateral: cada botão abre a sua tela.", 1200)
        ok = True
        for key in ("products", "imports", "compatibility", "listings", "groups", "automations", "history",
                    "marketplaces", "settings", "license", "dashboard"):
            yield from self.click(self.window.nav_buttons[key], 650)
            ok = ok and self.window.stack.currentWidget() is self.page(key)
        R.check("Todos os botões de navegação abrem a tela certa", ok)

    def sec_catalog(self):
        from mla.core.enums import CatalogStatus, Marketplace
        from mla.core.models import ProductVariant
        from mla.ui.pages.product_editor import ProductEditor, _kv_add
        from make_fixtures import gtin13
        self.nav("products")
        page = self.page("products")
        yield from self.say("Cadastro manual de um produto fictício no editor do catálogo mestre.")
        yield from self.click(self.button(page, "Novo produto"))
        yield from self.wait_dialog(ProductEditor)
        ed: ProductEditor = self.find_top(ProductEditor)
        yield 800
        self.snap("editor-vazio-validacao")
        R.check("Editor mostra pendências ao vivo antes de preencher", ed.issue_box.count() > 2)
        yield from self.say("Identificação: nome, SKU, título, marca, modelo, código do fabricante, GTIN e fornecedor.")
        yield from self.type(ed.internal_name, "Suporte veicular magnético")
        yield from self.type(ed.sku, "HZ-SUP-20")
        yield from self.type(ed.title_edit, "Suporte veicular magnético para celular Horizonte")
        yield from self.type(ed.category, "Acessórios")
        yield from self.type(ed.brand, "Horizonte")
        yield from self.type(ed.model, "MAG-360")
        yield from self.type(ed.manufacturer_code, "HZ-MAG-360")
        yield from self.say("Validação: um GTIN com dígito verificador errado gera aviso.", 600)
        yield from self.type(ed.gtin, "7891234567890")
        ed._revalidate()
        yield 900
        warned = any(i.field == "gtin" and "verificador" in i.message
                     for i in self.ctx.catalog.validate(ed._collect()).issues)
        self.snap("editor-gtin-invalido")
        R.check("GTIN com dígito verificador inválido é sinalizado", warned)
        valid_gtin = gtin13("789100002020")
        yield from self.type(ed.gtin, valid_gtin)
        yield from self.type(ed.supplier, "Distribuidora Sul (fictícia)")
        ed.tabs.setCurrentIndex(1)
        yield from self.say("Descrição e características.")
        yield from self.type(ed.description, "Suporte magnético com giro de 360 graus, fixação na saída de ar e ímã de "
                                             "neodímio. Produto fictício criado para a demonstração do MLA.", cps=40)
        yield from self.type(ed.material, "ABS e neodímio")
        yield from self.type(ed.warranty, "90 dias")
        ed.tabs.setCurrentIndex(2)
        yield from self.say("Informações técnicas: especificações e atributos personalizados.")
        yield from self.type(ed.technical_description, "Compatível com celulares de 4 a 7 polegadas.", cps=40)
        _kv_add(ed.specs, "Força do ímã", "1,2 kg")
        _kv_add(ed.custom_attributes, "Linha", "Horizonte Mobile")
        yield 1200
        ed.tabs.setCurrentIndex(3)
        yield from self.say("Imagens: duas fotos (a primeira vira a capa). O seletor de arquivos do Windows é "
                            "substituído pelo caminho direto no roteiro.")
        ed.gallery.add_files(sorted((FIX / "fotos-cadastro-manual").glob("*.jpg")))
        yield 1800
        ed.tabs.setCurrentIndex(4)
        yield from self.say("Comercial: preços e variações de cor com SKU próprio. Primeiro um preço inválido.")
        yield from self.type(ed.price, "12,3x")
        ed._revalidate()
        yield 900
        self.snap("editor-preco-invalido")
        R.check("Preço em formato inválido é recusado", ed._money_error)
        yield from self.type(ed.price, "79,90")
        yield from self.type(ed.cost, "35,00")
        ed._add_variant(ProductVariant("Cor: Preto", sku="HZ-SUP-20-PT", stock=10))
        yield 600
        ed._add_variant(ProductVariant("Cor: Prata", sku="HZ-SUP-20-PR", stock=5))
        yield 1200
        ed.tabs.setCurrentIndex(5)
        yield from self.say("Logística: peso e dimensões da embalagem.")
        ed.weight.setValue(320)
        ed.length.setValue(15)
        ed.width.setValue(10)
        ed.height.setValue(8)
        yield 1200
        ed.tabs.setCurrentIndex(7)
        ed.sections[Marketplace.SIMULATED].enabled.setChecked(True)
        yield from self.say("Marketplaces: ativado no marketplace simulado (usado no fluxo “Executar” por produto).")
        ed._revalidate()
        yield 900
        self.snap("editor-completo")
        R.check("Cadastro fica Pronto quando completo", ed.chip._text == CatalogStatus.READY.label, ed.chip._text)
        yield from self.click(ed.save_btn, 1500)
        pid = self.ctx.products.id_for_sku("HZ-SUP-20")
        product = self.ctx.catalog.get(pid) if pid else None
        R.check("Produto salvo com 2 imagens, 2 variações, GTIN e especificações",
                bool(product) and len(product.images) == 2 and len(product.variants) == 2 and product.gtin == valid_gtin
                and product.specs.get("Força do ímã") == "1,2 kg",
                f"imagens={len(product.images) if product else '-'} variações={len(product.variants) if product else '-'}")
        self.snap("catalogo-produto-salvo")

        yield from self.say("Edição: alterar o preço do produto salvo.")
        self.later(lambda: page.edit_product(pid))
        yield from self.wait_dialog(ProductEditor)
        ed = self.find_top(ProductEditor)
        ed.tabs.setCurrentIndex(4)
        yield 700
        yield from self.type(ed.price, "84,90")
        yield from self.click(ed.save_btn, 1400)
        R.check("Edição gravada (preço R$ 84,90)", self.ctx.products.get(pid).price_cents == 8490)

        yield from self.say("Busca pelo SKU de uma variação encontra o produto pai.")
        yield from self.type(page.search, "HZ-SUP-20-PR")
        yield 900
        R.check("Busca por SKU de variação", [r.sku for r in page.model.rows] == ["HZ-SUP-20"])
        self.snap("busca-sku-variacao")
        page.search.clear()
        yield 600

        yield from self.say("Duplicar e excluir (só a cópia de teste).")
        page.table.selectRow(0)
        yield 500
        yield from self.click(page.dup_btn, 1400)
        copy_id = self.ctx.products.id_for_sku("HZ-SUP-20-COPIA")
        R.check("Duplicação cria cópia com SKU novo", copy_id is not None)
        row = next(i for i, r in enumerate(page.model.rows) if r.id == copy_id)
        page.table.clearSelection()
        page.table.selectRow(row)
        yield 700
        yield from self.click(page.del_btn, 300)
        yield from self.answer_box("Excluir", "Excluir")
        yield 900
        R.check("Exclusão remove só a cópia", self.ctx.products.id_for_sku("HZ-SUP-20-COPIA") is None
                and self.ctx.products.id_for_sku("HZ-SUP-20") is not None)

    # ------------------------------------------------------------------ imports
    def run_wizard(self, path: Path, target: str = "products", prepare=None, decide=None, commit: bool = True,
                   name: str = ""):
        """Open the import wizard on `path` and walk it; returns the batch id."""
        from mla.ui.pages.imports import ImportWizard
        imports = self.page("imports")
        self.nav("imports")
        yield 400
        self.later(lambda: imports.open_wizard(Path(path), target))
        yield from self.wait_dialog(ImportWizard)
        wiz: ImportWizard = self.find_top(ImportWizard)
        yield from self.wait_for(lambda: wiz.analysis is not None, 20000, "análise do arquivo")
        yield 1200
        self.snap(f"{name}-1-arquivo")
        if not wiz.analysis.images_only:
            yield from self.click(wiz.next_btn, 1500)
            self.snap(f"{name}-2-previa")
            yield from self.click(wiz.next_btn, 1300)
            self.snap(f"{name}-3-mapeamento")
            if prepare:
                yield from prepare(wiz)
            if not wiz.confirm_probable.isHidden():
                yield from self.say("Colunas com nome ambíguo precisam de confirmação antes de analisar.", 1200)
                yield from self.click(wiz.confirm_probable, 700)
        yield from self.click(wiz.next_btn, 600)
        yield from self.wait_for(lambda: wiz._page == 3 and not wiz.runner.running, 60000, "análise e revisão")
        yield 1300
        self.snap(f"{name}-4-revisao")
        if decide:
            yield from decide(wiz)
        if not commit:
            return wiz
        yield from self.click(wiz.next_btn, 300)
        yield from self.answer_box("Gravar", "Gravar no catálogo")
        yield from self.wait_for(lambda: wiz._page == 4, 120000, "gravação")
        yield 1600
        self.snap(f"{name}-5-relatorio")
        batch_id = wiz.batch_id
        yield from self.click(wiz.next_btn, 1000)  # "Abrir catálogo" closes the wizard
        return batch_id

    def show_row(self, wiz, sku: str):
        for r, row in enumerate(wiz._rows):
            if row.sku == sku:
                wiz.rows_table.selectRow(r)
                yield 1500
                return row
        return None

    def set_mapping(self, wiz, column: str, field: str):
        combo = wiz._combos[column]
        yield from self.choose(combo, field)

    def sec_imports(self):
        from mla.core.enums import ImportStatus
        ctx = self.ctx
        # --- CSV
        yield from self.say("CSV exportado do ERP (Windows-1252, separador ;), com fotos na pasta ao lado.")

        def csv_decide(wiz):
            counts = ctx.imports.repo.counts_by_action(wiz.batch_id)
            R.check("CSV: 6 novos e 2 linhas com erro (SKU repetido e preço inválido)",
                    counts.get("create") == 6 and counts.get("error") == 2, str(counts))
            yield from self.say("Linhas com erro ficam de fora; o motivo aparece por linha.", 600)
            wiz.filter.setCurrentIndex(4)
            yield 1200
            if wiz._rows:
                wiz.rows_table.selectRow(0)
                yield 1600
            self.snap("csv-erros-por-linha")
            wiz.filter.setCurrentIndex(0)
            yield 800
            yield from self.say("O relatório da revisão pode ser exportado em CSV.", 600)
            yield from self.click(self.button(wiz, "Exportar relatório…"), 900)

        batch = yield from self.run_wizard(FIX / "erp-csv" / "produtos-erp.csv", decide=csv_decide, name="csv")
        skus = ["HZ-FIL-01", "HZ-PAS-02", "HZ-VEL-03", "HZ-PAL-04", "HZ-LAM-05", "HZ-TAP-06"]
        found = {s: ctx.catalog.get(ctx.products.id_for_sku(s)) for s in skus if ctx.products.id_for_sku(s)}
        R.check("CSV: 6 produtos conferidos no catálogo", len(found) == 6, ", ".join(found))
        pas = found.get("HZ-PAS-02")
        R.check("CSV: fotos ligadas pela coluna e pelo SKU no nome (HZ-PAS-02 com 2 imagens)",
                bool(pas) and len(pas.images) == 2)
        pal = found.get("HZ-PAL-04")
        R.check("CSV: foto encontrada só pelo SKU (HZ-PAL-04)", bool(pal) and len(pal.images) == 1)
        lam = found.get("HZ-LAM-05")
        R.check("CSV: foto citada e ausente vira mídia pendente (HZ-LAM-05)",
                bool(lam) and [m.reference for m in lam.missing_media] == ["fotos/HZ-LAM-05-frente.jpg"])
        fil = found.get("HZ-FIL-01")
        R.check("CSV: preço e GTIN convertidos (HZ-FIL-01 R$ 29,90)", bool(fil) and fil.price_cents == 2990
                and len(fil.gtin) == 13)
        report = OUT / f"importacao-{batch}.csv"
        R.check("CSV: relatório da importação exportado", report.exists(), str(report))

        # --- XLSX update
        yield from self.say("XLSX com aba de capa: o MLA usa a aba com dados e mostra cada alteração "
                            "“atual → arquivo” antes de gravar.")

        def xlsx_decide(wiz):
            counts = ctx.imports.repo.counts_by_action(wiz.batch_id)
            R.check("XLSX: 3 atualizações e 1 produto novo", counts.get("update") == 3 and counts.get("create") == 1,
                    str(counts))
            row = yield from self.show_row(wiz, "HZ-FIL-01")
            self.snap("xlsx-alteracoes-atual-arquivo")
            R.check("XLSX: alteração exibida com valor atual e novo",
                    bool(row) and any(c["old"] == "R$ 29,90" and c["new"] == "R$ 31,50" for c in row.changes))

        yield from self.run_wizard(FIX / "atualizacao-precos.xlsx", decide=xlsx_decide, name="xlsx")
        fil = ctx.catalog.get(ctx.products.id_for_sku("HZ-FIL-01"))
        R.check("XLSX: preço e estoque atualizados sem perder imagens nem descrição",
                fil.price_cents == 3150 and fil.stock == 55 and len(fil.images) == 1 and bool(fil.description))
        R.check("XLSX: produto novo criado (HZ-CAP-08)", ctx.products.id_for_sku("HZ-CAP-08") is not None)

        # --- JSON with a manual mapping correction
        yield from self.say("JSON de fornecedor (estrutura aninhada). Corrijo o mapeamento: “fabricante.marca” → Marca.")

        def json_prepare(wiz):
            yield from self.set_mapping(wiz, "fabricante.marca", "brand")
            self.snap("json-mapeamento-corrigido")

        yield from self.run_wizard(FIX / "fornecedor-json" / "feed-fornecedor.json", prepare=json_prepare,
                                   name="json")
        org = ctx.catalog.get(ctx.products.id_for_sku("HZ-ORG-09")) if ctx.products.id_for_sku("HZ-ORG-09") else None
        R.check("JSON: produtos criados com marca do campo aninhado e fotos pendentes",
                bool(org) and org.brand == "Horizonte" and len(org.missing_media) == 1)

        # --- XML
        yield from self.say("XML de parceiro: o SKU vem num atributo (@codigo_sku); mapeio essa coluna como SKU.")

        def xml_prepare(wiz):
            yield from self.set_mapping(wiz, "@codigo_sku", "sku")

        yield from self.run_wizard(FIX / "catalogo-parceiro.xml", prepare=xml_prepare, name="xml")
        car = ctx.products.id_for_sku("HZ-CAR-12")
        R.check("XML: 2 produtos criados", car is not None and ctx.products.id_for_sku("HZ-CAB-11") is not None)

        # --- PDF
        yield from self.say("PDF com tabela: linhas alinhadas entram; a linha com célula vazia fica em “Revisar” e "
                            "só entra se você incluir.")

        def pdf_decide(wiz):
            counts = ctx.imports.repo.counts_by_action(wiz.batch_id)
            R.check("PDF: 2 linhas seguras e 1 para revisar", counts.get("create") == 2 and counts.get("review") == 1,
                    str(counts))
            yield from self.show_row(wiz, "HZ-TRI-15")
            self.snap("pdf-linha-para-revisar")

        yield from self.run_wizard(FIX / "tabela-fornecedor.pdf", decide=pdf_decide, name="pdf")
        R.check("PDF: linha ambígua não foi gravada sem decisão (HZ-TRI-15 ausente)",
                ctx.products.id_for_sku("HZ-KIT-13") is not None and ctx.products.id_for_sku("HZ-TRI-15") is None)

        # --- ZIP
        yield from self.say("ZIP com planilha, fotos e um instalar.bat: o script é ignorado e nunca executado.")
        yield from self.run_wizard(FIX / "pacote-loja.zip", name="zip")
        ala = ctx.products.id_for_sku("HZ-ALA-16")
        R.check("ZIP: produto criado com a foto de dentro do pacote",
                bool(ala) and len(ctx.catalog.get(ala).images) == 1)
        leftovers = list(self.paths.imports.rglob("*.bat"))
        R.check("ZIP: arquivo .bat não foi extraído", not leftovers, str(leftovers))

        # --- image folder by SKU
        yield from self.say("Pasta de fotos nomeadas pelo SKU: liga fotos aos produtos e resolve a mídia pendente.")
        yield from self.run_wizard(FIX / "fotos-por-sku", name="pasta-fotos")
        lam = ctx.catalog.get(ctx.products.id_for_sku("HZ-LAM-05"))
        R.check("Pasta: mídia pendente resolvida (HZ-LAM-05 com foto)", len(lam.images) == 1 and not lam.missing_media)
        org = ctx.catalog.get(ctx.products.id_for_sku("HZ-ORG-09"))
        R.check("Pasta: fotos adicionadas aos produtos do JSON", len(org.images) == 1)

        # --- cancel during commit, then discard
        yield from self.say("Cancelamento: base com 3.000 linhas; cancelo durante a gravação e nada é alterado.")
        before = ctx.products.count()
        from mla.ui.pages.imports import ImportWizard
        wiz = yield from self.run_wizard(FIX / "base-grande.csv", commit=False, name="cancelamento")
        batch_id = wiz.batch_id
        yield from self.click(wiz.next_btn, 300)
        yield from self.answer_box("Gravar", "Gravar no catálogo")
        yield from self.wait_for(lambda: wiz.runner.running, 10000, "gravação iniciar")
        yield from self.wait_for(lambda: "Gravando" in wiz.progress_text.text(), 60000, "gravação em andamento")
        yield 300
        self.snap("cancelamento-gravando")
        yield from self.click(wiz.cancel_task_btn, 300)
        yield from self.wait_for(lambda: not wiz.runner.running, 60000, "cancelar")
        yield 1500
        self.snap("cancelamento-concluido")
        status = ctx.imports.get(batch_id).status
        R.check("Cancelamento: nenhum produto gravado e importação volta para revisão",
                ctx.products.count() == before and status is ImportStatus.PLANNED,
                f"antes={before} depois={ctx.products.count()} situação={status.value}")
        yield from self.say("Descartar antes de confirmar: o registro fica no histórico como descartado.", 600)
        yield from self.click(wiz.discard_btn, 300)
        yield from self.answer_box("Descartar", "Descartar")
        yield 1200
        R.check("Importação descartada", ctx.imports.get(batch_id).status is ImportStatus.DISCARDED)
        if self.find_top(ImportWizard):
            self.find_top(ImportWizard).reject()
        self.nav("imports")
        yield 1500
        self.snap("historico-de-importacoes")
        self.nav("products")
        yield 1500
        self.snap("catalogo-apos-importacoes")
        R.check("Catálogo com os 15 produtos esperados (1 manual + 14 importados)", ctx.products.count() == 15,
                f"{ctx.products.count()} produtos")

    # ------------------------------------------------------------------ compatibility
    def sec_compat(self):
        from mla.core.enums import DataSource, Verification
        from mla.ui.pages.compatibility import CompatibilityDialog
        from mla.ui.pages.product_editor import ProductEditor
        ctx = self.ctx
        self.nav("compatibility")
        page = self.page("compatibility")
        yield from self.say("Cadastro manual: o filtro de óleo serve no VW Gol 1.0 de 2010 a 2014 (dado do cliente).")
        yield from self.click(self.button(page, "Nova compatibilidade"))
        yield from self.wait_dialog(CompatibilityDialog)
        dlg: CompatibilityDialog = self.find_top(CompatibilityDialog)
        yield from self.type(dlg.sku, "HZ-FIL-01")
        yield from self.type(dlg.brand, "Volkswagen")
        yield from self.type(dlg.model, "Gol")
        yield from self.type(dlg.version, "1.0")
        dlg.year_from.setValue(2010)
        dlg.year_to.setValue(2014)
        yield from self.type(dlg.reference, "OEM-1234")
        yield 700
        self.snap("compat-nova")
        yield from self.click(self.button(dlg, "Salvar"), 1300)
        items = ctx.compatibility.search("Gol")
        R.check("Compatibilidade manual salva como confirmada (cliente)",
                len(items) == 1 and items[0].verification is Verification.CONFIRMED and items[0].years() == "2010–2014")
        yield from self.say("Edição: ajusto a versão para “1.0 Flex”.")
        page.table.selectRow(0)
        yield 600
        yield from self.click(page.edit_btn)
        yield from self.wait_dialog(CompatibilityDialog)
        dlg = self.find_top(CompatibilityDialog)
        yield from self.type(dlg.version, "1.0 Flex")
        yield from self.click(self.button(dlg, "Salvar"), 1200)
        R.check("Edição da compatibilidade gravada", ctx.compatibility.search("Gol")[0].version == "1.0 Flex")

        yield from self.say("Importação em massa da tabela de aplicações do cliente.")

        def compat_decide(wiz):
            actions = [r.action.value for r in ctx.imports.rows(wiz.batch_id)]
            R.check("Importação de compatibilidades: 4 novas, 1 repetida e 1 SKU inexistente",
                    actions.count("create") == 4 and actions.count("unchanged") == 1 and actions.count("error") == 1,
                    str(actions))
            yield 600

        yield from self.run_wizard(FIX / "aplicacoes-cliente.csv", target="compatibility", decide=compat_decide,
                                   name="compat-cliente")
        R.check("Compatibilidades do cliente gravadas e confirmadas",
                len(ctx.compatibility.search("HZ-PAS-02")) == 3)

        yield from self.say("Outra tabela vinda de site de fabricante: origem “Fonte externa” entra como não "
                            "verificada.")

        def external_prepare(wiz):
            yield from self.choose(wiz.source_combo, DataSource.EXTERNAL.value)

        yield from self.run_wizard(FIX / "aplicacoes-site-fabricante.csv", target="compatibility",
                                   prepare=external_prepare, name="compat-externa")
        ext = ctx.compatibility.search("HZ-PAL-04")
        R.check("Fonte externa entra como não verificada",
                len(ext) == 2 and all(c.verification is Verification.UNVERIFIED for c in ext))

        self.nav("compatibility")
        yield from self.say("Filtro “Não verificada”: confirmo uma e rejeito a outra.")
        yield from self.choose(page.verification, Verification.UNVERIFIED)
        yield 900
        self.snap("compat-filtro-nao-verificadas")
        page.table.selectRow(0)
        yield 500
        yield from self.click(page.confirm_btn, 1000)
        page.table.selectRow(0)
        yield 500
        yield from self.click(page.reject_btn, 1000)
        ext = {c.model: c.verification for c in ctx.compatibility.search("HZ-PAL-04")}
        R.check("Confirmar e rejeitar compatibilidades",
                sorted(v.value for v in ext.values()) == ["confirmed", "rejected"], str(ext))
        page.verification.setCurrentIndex(0)
        yield from self.type(page.search, "Uno")
        yield 900
        R.check("Busca de compatibilidade por modelo", len(page._items) == 1)
        page.search.clear()
        yield 600
        yield from self.say("As compatibilidades aparecem também na aba do produto.")
        self.nav("products")
        products = self.page("products")
        self.later(lambda: products.edit_product(ctx.products.id_for_sku("HZ-PAS-02")))
        yield from self.wait_dialog(ProductEditor)
        ed = self.find_top(ProductEditor)
        ed.tabs.setCurrentIndex(6)
        yield 1800
        self.snap("compat-aba-produto")
        R.check("Aba Compatibilidade do produto lista os registros", ed.compat_table.rowCount() == 3)
        ed.reject()
        yield 600

    # ------------------------------------------------------------------ groups
    def sec_groups(self):
        from mla.core.enums import Marketplace
        from mla.ui.pages.groups import ProductPicker
        ctx = self.ctx
        self.nav("groups")
        page = self.page("groups")
        yield from self.say("Novo grupo para organizar a linha de freios e filtros.")
        yield from self.click(self.button(page, "Novo grupo"))
        yield from self.wait_for(lambda: isinstance(QApplication.activeModalWidget(), QInputDialog), 10000,
                                 "nome do grupo")
        dlg = QApplication.activeModalWidget()
        yield from self.type(dlg.findChild(QLineEdit), "Freios e filtros")
        yield 500
        dlg.accept()
        yield 1300
        R.check("Grupo criado", any(g.name == "Freios e filtros" for g in ctx.groups.list()))
        yield from self.say("Adicionar produtos ao grupo.")
        yield from self.click(self.button(page, "Adicionar produtos"))
        yield from self.wait_dialog(ProductPicker)
        picker: ProductPicker = self.find_top(ProductPicker)
        yield from self.type(picker.search, "HZ-")
        yield 600
        wanted = {"HZ-FIL-01", "HZ-PAS-02", "HZ-VEL-03"}
        for i in range(picker.list.count()):
            item = picker.list.item(i)
            if any(s in item.text() for s in wanted):
                item.setSelected(True)
                yield 450
        self.snap("grupo-adicionar-produtos")
        yield from self.click(self.button(picker, "Adicionar selecionados"), 1200)
        group = next(g for g in ctx.groups.list() if g.name == "Freios e filtros")
        R.check("3 produtos adicionados ao grupo", len(group.product_ids) == 3)
        yield from self.say("Remover um produto do grupo.")
        page.items.setCurrentRow(2)
        page.items.item(2).setSelected(True)
        yield 600
        yield from self.click(self.button(page, "Remover do grupo"), 1000)
        group = ctx.groups.get(group.id)
        R.check("Produto removido do grupo (continua no catálogo)", len(group.product_ids) == 2)
        yield from self.say("Editar: renomear o grupo e escolher o marketplace de destino.")
        self.later(page._rename)
        yield from self.wait_for(lambda: isinstance(QApplication.activeModalWidget(), QInputDialog), 10000, "renomear")
        dlg = QApplication.activeModalWidget()
        yield from self.type(dlg.findChild(QLineEdit), "Linha automotiva")
        dlg.accept()
        yield 1000
        yield from self.click(page.market_checks[Marketplace.SIMULATED], 800)
        yield from self.click(self.button(page, "Validar"), 1400)
        self.snap("grupo-validado")
        group = ctx.groups.get(group.id)
        R.check("Grupo renomeado e com marketplace de destino",
                group.name == "Linha automotiva" and Marketplace.SIMULATED in group.marketplaces)
        R.note(f"Validação do grupo exibida: {page.validation.text()[:160]}")

    # ------------------------------------------------------------------ accounts (before preparing listings)
    def sec_accounts(self):
        from mla.core.enums import Marketplace
        from mla.ui.pages.marketplaces import AccountDialog
        ctx = self.ctx
        self.nav("marketplaces")
        page = self.page("marketplaces")
        yield from self.say("Contas: só contas fictícias. Primeiro uma conta do marketplace simulado.")
        self.later(lambda: page._add(Marketplace.SIMULATED))
        yield from self.wait_dialog(AccountDialog)
        dlg = self.find_top(AccountDialog)
        yield from self.type(dlg.name, "Loja Demo Simulada")
        yield 500
        yield from self.click(self.button(dlg, "Salvar conta"), 1300)
        R.check("Conta simulada criada", any(a.label == "Loja Demo Simulada" for a in ctx.accounts.list()))

        yield from self.say("Conta fictícia do Mercado Livre: um endereço que imita o domínio é recusado.")
        self.later(lambda: page._add(Marketplace.MERCADO_LIVRE))
        yield from self.wait_dialog(AccountDialog)
        dlg = self.find_top(AccountDialog)
        yield from self.type(dlg.name, "Loja Demo ML (fictícia)")
        yield from self.type(dlg.url, "https://www.mercadolivre.com.br.golpe.com/")
        yield from self.click(self.button(dlg, "Salvar conta"), 300)
        text = yield from self.answer_box("Mercado Livre")
        R.check("URL de domínio falso é recusada", "mercadolivre.com.br" in text, text[:120])
        yield from self.type(dlg.url, "https://www.mercadolivre.com.br/perfil/LOJA_DEMO_FICTICIA")
        yield from self.click(self.button(dlg, "Salvar conta"), 1300)
        ml = next((a for a in ctx.accounts.list(Marketplace.MERCADO_LIVRE) if a.label.startswith("Loja Demo ML")), None)
        R.check("Conta ML fictícia salva com URL normalizada (sem teste de conexão)",
                bool(ml) and ml.seller_url == "https://www.mercadolivre.com.br/perfil/LOJA_DEMO_FICTICIA")

        yield from self.say("Editar: o diálogo mostra o perfil dedicado do Edge desta conta (isolado do seu navegador).")
        self.later(lambda: page._edit(ml))
        yield from self.wait_dialog(AccountDialog)
        dlg = self.find_top(AccountDialog)
        yield from self.type(dlg.internal_id, "ml-demo")
        yield 1200
        self.snap("conta-editar-perfil-edge")
        yield from self.click(self.button(dlg, "Salvar conta"), 1200)
        R.check("Edição da conta gravada", ctx.accounts.get(ml.id).internal_id == "ml-demo")
        yield from self.say("Conta padrão: a conta demo vira a padrão do Mercado Livre.")
        page._set_default(ml)
        yield 1500
        self.snap("contas")
        R.check("Conta padrão alterada", ctx.accounts.default_for(Marketplace.MERCADO_LIVRE).id == ml.id)
        profiles = {a.label: str(ctx.account_service.profile_dir(a).relative_to(self.paths.root))
                    for a in ctx.accounts.list()}
        R.check("Cada conta tem um perfil de navegador próprio dentro da pasta de dados do MLA",
                len(set(profiles.values())) == len(profiles), str(profiles))

    # ------------------------------------------------------------------ listings
    def sec_listings(self):
        from mla.core.enums import ListingStatus, Marketplace
        from mla.ui.pages.listings import ListingEditor, PrepareListingsDialog
        ctx = self.ctx
        self.nav("products")
        products = self.page("products")
        yield from self.say("Selecionar produtos no catálogo e preparar anúncios para o marketplace simulado.")
        wanted = ["HZ-SUP-20", "HZ-FIL-01", "HZ-PAS-02", "HZ-VEL-03", "HZ-LAM-05", "HZ-CAP-08"]
        products.search.clear()
        yield 600
        products.table.clearSelection()
        from PySide6.QtCore import QItemSelectionModel
        for r, row in enumerate(products.model.rows):
            if row.sku in wanted:
                products.table.selectionModel().select(
                    products.model.index(r, 0), QItemSelectionModel.SelectionFlag.Select |
                    QItemSelectionModel.SelectionFlag.Rows)
                yield 250
        yield 700
        self.snap("catalogo-selecao-para-anuncios")
        yield from self.click(products.prepare_btn)
        yield from self.wait_dialog(PrepareListingsDialog)
        dlg = self.find_top(PrepareListingsDialog)
        yield from self.choose(dlg.marketplace, Marketplace.SIMULATED)
        yield from self.choose(dlg.account, ctx.accounts.default_for(Marketplace.SIMULATED).id)
        self.snap("preparar-anuncios")
        yield from self.click(dlg.ok, 1800)
        page = self.page("listings")
        account = ctx.accounts.default_for(Marketplace.SIMULATED)
        rows = ctx.listings.rows(Marketplace.SIMULATED, account.id)
        states = {r.sku: r.listing.status for r in rows}
        R.check("6 anúncios preparados a partir do catálogo", len(rows) == 6, str({k: v.value for k, v in states.items()}))
        R.check("Produto incompleto gera anúncio Incompleto (HZ-CAP-08)",
                states.get("HZ-CAP-08") in (ListingStatus.INCOMPLETE, ListingStatus.DRAFT))
        self.snap("anuncios-preparados")

        yield from self.say("Editar o anúncio do filtro: título e descrição próprios desta conta (o produto mestre não "
                            "muda).")
        fil = next(r for r in page.model.rows if r.sku == "HZ-FIL-01")
        page.table.selectRow(page.model.rows.index(fil))
        yield 600
        yield from self.click(page.edit_btn)
        yield from self.wait_dialog(ListingEditor)
        ed: ListingEditor = self.find_top(ListingEditor)
        yield 900
        yield from self.type(ed.title_edit, "Filtro de óleo motor 1.0 Horizonte original")
        yield from self.type(ed.description, "Filtro de óleo para motores 1.0. Anúncio de demonstração do MLA com "
                                             "descrição própria desta conta.", cps=40)
        yield from self.type(ed.price, "33,90")
        ed._revalidate()
        yield 1200
        self.snap("anuncio-editor")
        yield from self.click(ed.approve_btn, 1500)
        listing = ctx.listings.repo.get_for(fil.listing.product_id, Marketplace.SIMULATED, account.id)
        master = ctx.catalog.get(fil.listing.product_id)
        R.check("Anúncio editado e aprovado; produto mestre intacto",
                listing.status is ListingStatus.APPROVED and listing.price_cents == 3390 and master.price_cents == 3150)

        yield from self.say("Aprovar em lote: o incompleto é recusado com o motivo.")
        page.refresh()
        yield 600
        page.table.clearSelection()
        for r, row in enumerate(page.model.rows):
            if row.sku in ("HZ-SUP-20", "HZ-PAS-02", "HZ-CAP-08"):
                page.table.selectionModel().select(page.model.index(r, 0), QItemSelectionModel.SelectionFlag.Select |
                                                   QItemSelectionModel.SelectionFlag.Rows)
        yield 800
        yield from self.click(page.approve_btn, 300)
        text = yield from self.answer_box("Pendências")
        R.check("Aprovação em lote recusa o incompleto com motivo", "HZ-CAP" in text or "Capa" in text, text[:160])
        states = {r.sku: r.listing.status for r in ctx.listings.rows(Marketplace.SIMULATED, account.id)}
        R.check("Estados após aprovação", states["HZ-SUP-20"] is ListingStatus.APPROVED
                and states["HZ-PAS-02"] is ListingStatus.APPROVED and states["HZ-VEL-03"] is ListingStatus.READY,
                str({k: v.value for k, v in states.items()}))
        yield from self.say("Filtro “Precisam de correção” mostra só o que falta completar.")
        page.status_filter.setCurrentIndex(1)
        yield 1300
        self.snap("anuncios-precisam-correcao")
        page.status_filter.setCurrentIndex(0)
        yield 600

        yield from self.say("Mercado Livre (conta fictícia): dá para preparar e aprovar, mas o envio fica bloqueado "
                            "até a integração real existir.")
        ml = ctx.accounts.default_for(Marketplace.MERCADO_LIVRE)
        created = ctx.listings.prepare([ctx.products.id_for_sku("HZ-FIL-01")], Marketplace.MERCADO_LIVRE, ml.id).created
        ctx.listings.approve(created)
        page.open_with(marketplace=Marketplace.MERCADO_LIVRE, account_id=ml.id)
        yield 1800
        self.snap("anuncios-mercado-livre-bloqueado")
        R.check("Envio para a fila bloqueado no Mercado Livre", not page.send_btn.isEnabled())
        page.open_with(marketplace=Marketplace.SIMULATED, account_id=account.id)
        yield 1200

    # ------------------------------------------------------------------ automation
    def wait_review(self, count: int, timeout: int = 180000):
        yield from self.wait_for(lambda: len(self.reviews) >= count, timeout, "revisão do anúncio")

    def handle_item(self, decision: str = "approve", show_login: bool = False):
        """Follow one item: browser while filling, review in MLA, then approve or reject."""
        auto = self.page("automations")
        yield from self.focus_browser(True)
        waited = 0
        while len(self.reviews) <= self.reviews_handled:
            if len(self.manual) > self.manual_handled:  # login or CAPTCHA handled in the browser by the "human"
                self.manual_handled += 1
                yield 1500
                self.snap("navegador-acao-manual")
                yield from self.focus_browser(False)
                yield from self.say("O MLA pausou e pediu ação manual; depois de resolver no navegador, clico em "
                                    "Continuar.", 1200)
                self.snap("automacao-continuar")
                yield from self.click(self.button(auto.manual_box, "Continuar"), 800)
                yield from self.focus_browser(True)
            yield 300
            waited += 300
            if waited > 180000:
                raise TimeoutError("anúncio não chegou à revisão")
        self.reviews_handled += 1
        yield 600
        self.snap("navegador-formulario-preenchido")
        yield 2200
        yield from self.focus_browser(False)
        yield from self.say("Revisão obrigatória: o formulário foi preenchido e conferido; nada é publicado sem a sua "
                            "aprovação.", 2200)
        self.snap("automacao-revisao")
        n_finished = len(self.finished_items)
        if decision == "approve":
            yield from self.click(auto.approve_btn, 600)
            yield from self.focus_browser(True)
            yield from self.wait_for(lambda: len(self.finished_items) > n_finished, 60000, "confirmação da publicação")
            yield 600
            self.snap("navegador-publicado")
            yield 1200
            yield from self.focus_browser(False)
        else:
            yield from self.click(self.button(auto.now, "Rejeitar"), 600)
            yield from self.wait_for(lambda: len(self.finished_items) > n_finished, 60000, "encerramento")
        yield 900
        return self.finished_items[-1]

    def sec_automation(self):
        from mla.automation.adapters.simulated import SimulatedMarketplaceAdapter
        from mla.core.enums import ItemStatus, ListingStatus, Marketplace
        from mla.ui.pages.listings import ListingEditor
        ctx = self.ctx
        account = ctx.accounts.default_for(Marketplace.SIMULATED)
        page = self.page("listings")
        auto = self.page("automations")
        yield from self.say("Enviar os 3 anúncios aprovados para a fila de automação.")
        page.open_with(marketplace=Marketplace.SIMULATED, account_id=account.id)
        yield 900
        yield from self.click(page.send_btn, 300)
        yield from self.answer_box("fila", "Enviar para a fila")
        yield 800
        queued = [r.sku for r in ctx.listings.rows(Marketplace.SIMULATED, account.id, [ListingStatus.QUEUED])]
        R.check("3 anúncios aprovados na fila (preparado ≠ publicado)", len(queued) == 3, str(queued))
        self.nav("automations")
        yield from self.say("O executor abre o Edge com o perfil dedicado da conta simulada. Perfil novo: login.", 800)
        yield from self.wait_for(lambda: self.window.services.executor.current_item is not None, 30000, "início")
        _, status, message = yield from self.handle_item("approve")
        first = self.finished_items[-1][0]
        R.check("1º anúncio: login simulado, preenchimento, upload de imagens, revisão e publicação simulada",
                status is ItemStatus.PUBLISHED and any("Entre na sua conta" in m for m in self.manual), message)
        item = ctx.automation_repo.get_item(first.id)
        R.check("Status atualizado no MLA com ID do anúncio simulado", item.external_id.startswith("SIM-"),
                item.external_id)

        yield from self.say("Pausar: o item em andamento termina e a fila para.")
        yield from self.wait_for(lambda: self.window.services.executor.current_item is not None, 30000, "2º item")
        auto.jobs.selectRow(0)
        yield 500
        yield from self.click(auto.pause_btn, 900)
        self.snap("automacao-pausada")
        _, status, _ = yield from self.handle_item("approve")
        R.check("2º anúncio publicado durante a pausa (termina o item atual)", status is ItemStatus.PUBLISHED)
        yield 3000
        job = ctx.automation_repo.list_jobs(limit=1)[0]
        R.check("Fila parada após o item atual", job.status.value == "paused"
                and self.window.services.executor.current_item is None, job.status.value)

        yield from self.say("Retomar com CAPTCHA simulado ativado: o MLA para e pede ajuda; depois rejeito na revisão.")
        SimulatedMarketplaceAdapter.extra_query = "captcha=1"
        auto.jobs.selectRow(0)
        yield 400
        yield from self.click(auto.resume_btn, 600)
        n_manual = len(self.manual)
        rejected_item, status, _ = yield from self.handle_item("reject")
        rejected_sku = rejected_item.sku
        R.note(f"Item rejeitado na revisão: {rejected_sku}")
        SimulatedMarketplaceAdapter.extra_query = ""
        R.check("CAPTCHA simulado tratado como ação manual", any("verificação" in m for m in self.manual[n_manual:]),
                str(self.manual[n_manual:]))
        R.check("Rejeitar na revisão encerra sem publicar", status is ItemStatus.CANCELLED, status.value)

        yield from self.say("Prevenção de duplicatas: tentar executar de novo um produto já publicado.")
        self.nav("products")
        products = self.page("products")
        if rejected_sku == "HZ-SUP-20":
            R.note("HZ-SUP-20 foi o item rejeitado; a checagem de duplicata pode não se aplicar.")
        sup = next(i for i, r in enumerate(products.model.rows) if r.sku == "HZ-SUP-20")
        products.table.clearSelection()
        products.table.selectRow(sup)
        yield 600
        yield from self.click(products.run_btn, 300)
        text = yield from self.answer_box("publicado")
        R.check("Execução duplicada bloqueada", "Já publicado nesta conta" in text, text[:140])

        yield from self.say("Repetir a tarefa rejeitada pelo Histórico (Reexecutar).")
        self.nav("history")
        history = self.page("history")
        yield 900
        row = next(i for i, it in enumerate(history._items) if it.sku == rejected_sku
                   and it.status is ItemStatus.CANCELLED)
        history.table.selectRow(row)
        from mla.ui.pages.history import ItemDetails
        self.later(lambda: history._details(history.table.model().index(row, 0)))
        yield from self.wait_dialog(ItemDetails)
        details = self.find_top(ItemDetails)
        yield 1500
        self.snap("historico-detalhes-rejeitado")
        yield from self.click(self.button(details, "Reexecutar"), 300)
        text = yield from self.answer_box("")
        rerun_blocked = "não está ativado" in text
        R.check("Reexecutar pelo Histórico um anúncio preparado na tela Anúncios", not rerun_blocked, text[:180])
        if rerun_blocked:
            R.bug("Reexecutar no Histórico usa o fluxo por produto e exige o marketplace ativado no cadastro do "
                  "produto; anúncios preparados pela tela Anúncios (sem essa marcação) são recusados. Contorno: "
                  "editar e reaprovar o anúncio na tela Anúncios e enviar de novo.")
        yield from self.say("Contorno pela tela Anúncios: editar, reaprovar e reenviar o anúncio.")
        page.open_with(marketplace=Marketplace.SIMULATED, account_id=account.id)
        yield 900
        pas = next(i for i, r in enumerate(page.model.rows) if r.sku == rejected_sku)
        page.table.selectRow(pas)
        yield 500
        yield from self.click(page.edit_btn)
        yield from self.wait_dialog(ListingEditor)
        ed = self.find_top(ListingEditor)
        yield 1000
        yield from self.click(ed.approve_btn, 1200)
        yield from self.click(page.send_btn, 300)
        yield from self.answer_box("fila", "Enviar para a fila")
        self.nav("automations")
        yield from self.wait_for(lambda: self.window.services.executor.current_item is not None, 30000, "reenvio")
        _, status, _ = yield from self.handle_item("approve")
        R.check("Anúncio rejeitado reenviado e publicado", status is ItemStatus.PUBLISHED)

        yield from self.say("Cancelar execução: envio 2 anúncios e cancelo a fila.")
        ctx.listings.approve([r.listing.id for r in ctx.listings.rows(Marketplace.SIMULATED, account.id)
                              if r.sku in ("HZ-VEL-03", "HZ-LAM-05")])
        page.open_with(marketplace=Marketplace.SIMULATED, account_id=account.id)
        yield 700
        yield from self.click(page.send_btn, 300)
        yield from self.answer_box("fila", "Enviar para a fila")
        self.nav("automations")
        yield 1200
        auto.jobs.selectRow(0)
        yield 500
        yield from self.click(auto.cancel_btn, 1500)
        yield from self.wait_for(lambda: self.window.services.executor.current_item is None, 60000, "cancelamento")
        yield 1500
        self.snap("automacao-cancelada")
        job = ctx.automation_repo.list_jobs(limit=1)[0]
        items = ctx.automation_repo.items_for_job(job.id)
        R.check("Execução cancelada: nenhum item publicado", all(i.status is not ItemStatus.PUBLISHED for i in items),
                str([(i.sku, i.status.value) for i in items]))

        yield from self.say("Recuperação após reiniciar: envio um anúncio e fecho o MLA no meio do preenchimento.")
        vel = [r.listing for r in ctx.listings.rows(Marketplace.SIMULATED, account.id) if r.sku == "HZ-VEL-03"][0]
        ctx.listings.save(vel)  # back to preparation after the cancellation
        ctx.listings.approve([vel.id])
        page.open_with(marketplace=Marketplace.SIMULATED, account_id=account.id)
        yield 700
        yield from self.click(page.send_btn, 300)
        yield from self.answer_box("fila", "Enviar para a fila")
        self.nav("automations")
        yield from self.focus_browser(True)
        yield from self.wait_for(lambda: self.window.services.executor.current_item is not None, 30000, "item iniciar")
        yield 3500
        yield from self.focus_browser(False)
        products_before = ctx.products.count()
        self.later(self.window.close)
        yield from self.answer_box("em execução", "Fechar")
        yield from self.wait_for(lambda: not self.window.isVisible(), 30000, "fechar a janela")
        yield from self.say("MLA fechado com um anúncio em andamento. Reabrindo o aplicativo…", 2000)
        self.ctx.close()
        self.reviews.clear()
        self.reviews_handled = 0
        self.open_app()
        ctx = self.ctx
        yield 2500
        self.snap("reaberto-recuperacao")
        recovered = [i for i in ctx.automation_repo.items_with_status([ItemStatus.QUEUED]) if i.sku == "HZ-VEL-03"]
        R.check("Após reiniciar, o item interrompido volta para a fila e os dados persistem",
                bool(recovered) and ctx.products.count() == products_before, f"produtos={ctx.products.count()}")
        auto = self.page("automations")
        self.nav("automations")
        yield 900
        auto.jobs.selectRow(0)
        yield 500
        yield from self.click(auto.resume_btn, 800)
        yield from self.wait_for(lambda: self.window.services.executor.current_item is not None, 30000, "retomar")
        _, status, _ = yield from self.handle_item("approve")
        R.check("Item recuperado concluído após retomar", status is ItemStatus.PUBLISHED)
        R.skip("Falha real de etapa e “Requer intervenção”",
               "O marketplace simulado não oferece pela interface um modo de falha definitiva (categoria ausente vira "
               "“Outros” com aviso; tempo mínimo por etapa é 5 s). Esses caminhos são cobertos pelos testes "
               "automatizados de navegador.")

    # ------------------------------------------------------------------ connection test (simulated only)
    def sec_connection(self):
        from mla.core.enums import ConnectionStatus, Marketplace
        from mla.ui.pages.marketplaces import ConnectionDialog
        ctx = self.ctx
        self.nav("marketplaces")
        page = self.page("marketplaces")
        account = ctx.accounts.default_for(Marketplace.SIMULATED)
        yield from self.say("Testar conexão da conta simulada: o perfil dedicado guarda a sessão do login feito na "
                            "automação.")
        self.later(lambda: page._test(account))
        yield from self.wait_dialog(ConnectionDialog)
        dlg = self.find_top(ConnectionDialog)
        yield from self.focus_browser(True)
        yield from self.wait_for(lambda: not dlg.runner.running, 90000, "teste de conexão")
        yield from self.focus_browser(False)
        yield 1200
        self.snap("teste-conexao-simulado")
        stored = ctx.accounts.get(account.id)
        R.check("Conexão simulada verificada com a sessão salva no perfil",
                stored.connection_status is ConnectionStatus.CONNECTED, stored.connection_message)
        yield from self.click(dlg.close_btn, 1200)
        R.skip("Teste de conexão com Mercado Livre/Shopee", "Não executado por regra: contas reais não são acessadas.")

    # ------------------------------------------------------------------ history
    def sec_history(self):
        from mla.core.enums import ItemStatus
        from mla.ui.pages.history import ItemDetails
        self.nav("history")
        page = self.page("history")
        yield 1200
        self.snap("historico")
        total = len(page._items)
        yield from self.say("Filtros por status: publicados e cancelados.")
        yield from self.choose(page.status, ItemStatus.PUBLISHED)
        yield 900
        published = len(page._items)
        self.snap("historico-publicados")
        yield from self.choose(page.status, ItemStatus.CANCELLED)
        yield 900
        cancelled = len(page._items)
        page.status.setCurrentIndex(0)
        yield 600
        db_published = self.ctx.automation_repo.count_items_by_status()[ItemStatus.PUBLISHED]
        R.check("Histórico confere com o banco (publicados)", published == db_published,
                f"tela={published} banco={db_published} cancelados={cancelled} total={total}")
        yield from self.say("Busca por SKU e detalhes de uma execução publicada.")
        yield from self.type(page.search, "HZ-FIL-01")
        yield 900
        if page._items:
            self.later(lambda: page._details(page.table.model().index(0, 0)))
            yield from self.wait_dialog(ItemDetails)
            details = self.find_top(ItemDetails)
            yield 2000
            self.snap("historico-detalhes")
            from PySide6.QtWidgets import QListWidget
            logs = details.findChild(QListWidget)
            R.check("Detalhes mostram o registro passo a passo", bool(logs) and logs.count() >= 3,
                    f"{logs.count() if logs else 0} registros")
            yield from self.click(self.button(details, "Fechar"), 800)
        page.search.clear()
        yield 600
        yield from self.say("Exportar o histórico em CSV.")
        yield from self.click(self.button(page, "Exportar CSV"), 1200)
        exported = sorted(OUT.glob("historico-*.csv"))
        lines = exported[-1].read_text(encoding="utf-8-sig").splitlines() if exported else []
        R.check("CSV do histórico exportado com uma linha por execução", bool(exported) and len(lines) - 1 == total,
                f"{exported[-1].name if exported else '-'}: {len(lines) - 1} linhas")

    # ------------------------------------------------------------------ settings, backup, license, logs
    def sec_settings(self):
        ctx = self.ctx
        self.nav("settings")
        page = self.page("settings")
        yield 1000
        self.snap("configuracoes")
        yield from self.say("Backup manual do banco de demonstração.")
        before = set(self.paths.backups.glob("*.db"))
        yield from self.click(self.button(page, "Criar backup agora"), 1500)
        new = set(self.paths.backups.glob("*.db")) - before
        R.check("Backup criado", len(new) == 1, ", ".join(p.name for p in new))
        backup = next(iter(new)) if new else None

        yield from self.say("Restauração isolada: excluo um produto de teste e restauro o backup.")
        target_sku = "HZ-CAR-12"
        self.nav("products")
        products = self.page("products")
        yield 600
        row = next(i for i, r in enumerate(products.model.rows) if r.sku == target_sku)
        products.table.clearSelection()
        products.table.selectRow(row)
        yield 600
        yield from self.click(products.del_btn, 300)
        yield from self.answer_box("Excluir", "Excluir")
        yield 800
        R.check("Produto de teste excluído antes da restauração", ctx.products.id_for_sku(target_sku) is None)
        self.nav("settings")
        yield 800
        for i in range(page.backups.count()):
            if backup and page.backups.item(i).data(256) and Path(page.backups.item(i).data(256)).name == backup.name:
                page.backups.setCurrentRow(i)
        yield 800
        yield from self.click(self.button(page, "Restaurar selecionado"), 300)
        yield from self.answer_box("substituídos", "Restaurar")
        yield 1800
        R.check("Restauração devolve o produto excluído", ctx.products.id_for_sku(target_sku) is not None)

        yield from self.say("Licença: só consulta. Uma chave inválida é recusada; nenhuma ativação é feita.")
        self.nav("license")
        license_page = self.page("license")
        yield 1200
        self.snap("licenca")
        yield from self.type(license_page.key_input, "DEMO-0000-0000")
        yield from self.click(self.button(license_page, "Ativar"), 300)
        text = yield from self.answer_box("")
        R.check("Chave inválida recusada sem ativar nada", "não" in text.lower() or "inválid" in text.lower(),
                text[:140])
        license_page.key_input.clear()

        log_file = self.paths.logs / "mla.log"
        R.check("Log do aplicativo gravado na pasta de dados da demonstração", log_file.exists(), str(log_file))
        if log_file.exists():
            import subprocess
            scan = subprocess.run([sys.executable, str(ROOT / "tools" / "logscan.py"), str(log_file)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
            R.note("Resumo do log (logscan): " + " | ".join(scan.stdout.strip().splitlines()[:6]))

    def sec_dashboard_end(self):
        from mla.core.enums import ListingStatus
        self.nav("dashboard")
        yield from self.say("Dashboard atualizado com o resultado das operações.", 2500)
        stats = self.ctx.dashboard.stats()
        self.snap("dashboard-final")
        published = sum(c.get(ListingStatus.PUBLISHED, 0) for c in stats.by_marketplace.values())
        R.check("Dashboard reflete produtos e publicações (simuladas)",
                stats.total_products == 15 and published == stats.published,
                f"produtos={stats.total_products} publicados={stats.published}")


# ============================================================================ main
def main() -> int:
    import faulthandler
    from mla.config.logging_setup import configure_logging
    from mla.config.paths import AppPaths
    if DATA.exists():
        shutil.rmtree(DATA)  # demo data only, recreated on every run
    for folder in (SHOTS, OUT):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    configure_logging(AppPaths(DATA).ensure().logs)
    crash_log = (OUT / "crash-trace.txt").open("w", encoding="utf-8")
    faulthandler.enable(crash_log, all_threads=True)  # native crashes leave a trace
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from mla.ui.theme import apply_theme
    apply_theme(app)
    import make_fixtures
    make_fixtures.build(FIX)

    # native dialogs cannot be driven by the script: fixed paths, and nothing opens outside the app
    QFileDialog.getSaveFileName = staticmethod(lambda _p=None, _c="", default="", _f="", *a, **k:
                                               (str(OUT / Path(default).name), ""))
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QDesktopServices.openUrl = staticmethod(lambda url: R.note(f"Abriria fora do app (bloqueado na demo): "
                                                                f"{url.toString()[:80]}") or True)
    from mla.automation.connection import ConnectionTester
    original_wait = ConnectionTester._wait_for_user

    def demo_wait(self, message):  # worker thread of the connection test: plays the user if a login is asked
        try:
            page = self.manager.session.page
            if "login.html" in page.url:
                page.type("#email", "demo@feiralocal.test", delay=60)
                page.type("#password", "senha-demo", delay=60)
                page.click("#login-submit")
        except Exception as exc:
            log.warning("login simulado do teste de conexão falhou: %s", exc)
        original_wait(self, message)

    ConnectionTester._wait_for_user = demo_wait
    demo = Demo(app)
    demo.open_app()
    demo.start()
    R.note(f"Pasta de dados da demonstração: {DATA}")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
