"""imgsat_dialog.py
Plugin ImgSat — Analyse semi-automatique d'images satellitaires pour QGIS 3.x
v4 : onglet Classification fusionné en un seul panneau (classes + run + validation),
     loader sur le bouton Lancer la classification, suppression des sous-onglets
     ① Entraînement / ② Classification / ③ Validation.
"""

from __future__ import annotations

import os
import math
import json
import datetime
import webbrowser
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from qgis.PyQt import QtWidgets, QtCore, QtGui

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsRasterBandStats,
    QgsContrastEnhancement,
    QgsMultiBandColorRenderer,
    QgsSingleBandPseudoColorRenderer,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsGeometry,
    QgsRasterFileWriter,
    QgsRasterPipe,
    QgsRaster,
    QgsRasterShader
)

try:
    from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
    HAS_RASTER_CALC = True
except ImportError:
    HAS_RASTER_CALC = False

from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsMapLayerProxyModel

try:
    import processing
    HAS_PROCESSING = True
except ImportError:
    HAS_PROCESSING = False


# ─────────────────────────────────────────────────────────────────────────────
# PALETTE & STYLES
# ─────────────────────────────────────────────────────────────────────────────

_C_BG        = "#1c2128"
_C_PANEL     = "#22272e"
_C_SURFACE   = "#2d333b"
_C_BORDER    = "#444c56"
_C_ACCENT    = "#2f81f7"
_C_ACCENT2   = "#388bfd"
_C_SUCCESS   = "#3fb950"
_C_WARN      = "#d29922"
_C_DANGER    = "#f85149"
_C_TEXT      = "#e6edf3"
_C_TEXT_SEC  = "#8b949e"
_C_TEXT_HINT = "#6e7681"

DIALOG_STYLE = f"""
QDialog, QWidget {{
    background: {_C_BG};
    color: {_C_TEXT};
    font-family: 'Segoe UI', 'SF Pro Text', 'Helvetica Neue', sans-serif;
    font-size: 12px;
}}
QTabWidget::pane {{
    border: 1px solid {_C_BORDER};
    border-radius: 6px;
    background: {_C_PANEL};
}}
QTabWidget::tab-bar {{ left: 0; }}
QTabBar::tab {{
    background: {_C_SURFACE};
    color: {_C_TEXT_SEC};
    padding: 8px 18px;
    border: 1px solid {_C_BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 500;
    min-width: 100px;
}}
QTabBar::tab:selected {{
    background: {_C_PANEL};
    color: {_C_TEXT};
    border-bottom: 2px solid {_C_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {_C_BG};
    color: {_C_TEXT};
}}
QGroupBox {{
    font-weight: 600;
    font-size: 11px;
    color: {_C_TEXT_SEC};
    border: 1px solid {_C_BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    background: {_C_PANEL};
}}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 12px;
    selection-background-color: {_C_ACCENT};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {_C_ACCENT};
}}
QSpinBox, QDoubleSpinBox {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    padding: 4px 6px;
}}
QComboBox {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    min-width: 80px;
}}
QComboBox:hover {{ border-color: {_C_ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    selection-background-color: {_C_ACCENT};
}}
QTableWidget {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    gridline-color: {_C_BORDER};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    font-size: 12px;
    alternate-background-color: {_C_PANEL};
}}
QTableWidget::item:selected {{ background: {_C_ACCENT}; color: #fff; }}
QHeaderView::section {{
    background: {_C_BG};
    color: {_C_TEXT_SEC};
    font-weight: 600;
    font-size: 11px;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {_C_BORDER};
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}
QListWidget {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    font-size: 12px;
}}
QListWidget::item:selected {{ background: {_C_ACCENT}; color: #fff; border-radius: 3px; }}
QListWidget::item:hover {{ background: {_C_BG}; }}
QProgressBar {{
    background: {_C_SURFACE};
    border: none;
    border-radius: 3px;
    height: 5px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {_C_ACCENT}; border-radius: 3px; }}
QDateEdit, QDateTimeEdit {{
    background: {_C_SURFACE};
    color: {_C_TEXT};
    border: 1px solid {_C_BORDER};
    border-radius: 5px;
    padding: 5px 8px;
}}
QScrollBar:vertical {{
    background: {_C_BG};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {_C_BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QCheckBox {{ color: {_C_TEXT}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {_C_BORDER};
    border-radius: 3px;
    background: {_C_SURFACE};
}}
QCheckBox::indicator:checked {{ background: {_C_ACCENT}; border-color: {_C_ACCENT}; }}
QLabel {{ color: {_C_TEXT}; }}
QSplitter::handle {{ background: {_C_BORDER}; }}
"""

_BTN = lambda bg, hov, txt="#fff": (
    f"QPushButton{{background:{bg};color:{txt};border:none;"
    f"padding:6px 14px;border-radius:5px;font-size:12px;font-weight:500;}}"
    f"QPushButton:hover{{background:{hov};}}"
    f"QPushButton:pressed{{opacity:0.8;}}"
    f"QPushButton:disabled{{background:#3d4450;color:#6e7681;}}"
)
_BTN_PRIMARY = _BTN(_C_ACCENT,  _C_ACCENT2)
_BTN_SUCCESS = _BTN(_C_SUCCESS, "#2ea043")
_BTN_DANGER  = _BTN(_C_DANGER,  "#da3633")
_BTN_WARN    = _BTN(_C_WARN,    "#bb8009")
_BTN_GHOST   = (
    f"QPushButton{{background:transparent;color:{_C_TEXT_SEC};"
    f"border:1px solid {_C_BORDER};padding:6px 14px;border-radius:5px;font-size:12px;}}"
    f"QPushButton:hover{{background:{_C_SURFACE};color:{_C_TEXT};border-color:{_C_ACCENT};}}"
)
_BTN_SMALL = (
    f"QPushButton{{background:{_C_SURFACE};color:{_C_TEXT_SEC};"
    f"border:1px solid {_C_BORDER};padding:3px 8px;border-radius:4px;font-size:11px;}}"
    f"QPushButton:hover{{background:{_C_BG};color:{_C_TEXT};}}"
)
_BTN_LOADING = (
    f"QPushButton{{background:#253348;color:#79c0ff;border:1px solid #1f4e79;"
    f"padding:6px 14px;border-radius:5px;font-size:12px;font-weight:500;}}"
)
_BTN_OP = (
    f"QPushButton{{background:{_C_SURFACE};color:{_C_TEXT};"
    f"border:1px solid {_C_BORDER};padding:5px;border-radius:4px;"
    f"font-size:12px;font-family:monospace;min-width:32px;}}"
    f"QPushButton:hover{{background:{_C_ACCENT};color:#fff;border-color:{_C_ACCENT};}}"
    f"QPushButton:pressed{{background:{_C_ACCENT2};}}"
)

_BOX_INFO = (
    f"QLabel{{background:#162032;border:1px solid #1f4e79;border-radius:5px;"
    f"padding:8px 10px;font-size:11px;color:#79c0ff;line-height:1.4;}}"
)
_BOX_WARN = (
    f"QLabel{{background:#1f1a0e;border:1px solid #5a4000;border-radius:5px;"
    f"padding:8px 10px;font-size:11px;color:#e3b341;line-height:1.4;}}"
)
_BOX_SUCCESS = (
    f"QLabel{{background:#0d2314;border:1px solid #1a4a23;border-radius:5px;"
    f"padding:8px 10px;font-size:11px;color:#56d364;line-height:1.4;}}"
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS UI
# ─────────────────────────────────────────────────────────────────────────────

def _lbl(text, bold=False, color=None, size=None):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    s = ""
    if bold:  s += "font-weight:600;"
    if color: s += f"color:{color};"
    if size:  s += f"font-size:{size}px;"
    if s:     w.setStyleSheet(s)
    return w

def _sep():
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.HLine)
    f.setFrameShadow(QtWidgets.QFrame.Sunken)
    f.setStyleSheet(f"color:{_C_BORDER};background:{_C_BORDER};max-height:1px;")
    return f

def _info(text):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    w.setStyleSheet(_BOX_INFO)
    return w

def _warn(text):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    w.setStyleSheet(_BOX_WARN)
    return w

def _success(text):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    w.setStyleSheet(_BOX_SUCCESS)
    return w

def _group(title):
    return QtWidgets.QGroupBox(title)

def _table_r(text):
    it = QtWidgets.QTableWidgetItem(text)
    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    return it

def _badge(text, color, bg):
    w = QtWidgets.QLabel(f" {text} ")
    w.setStyleSheet(
        f"background:{bg};color:{color};border-radius:3px;"
        f"padding:1px 6px;font-size:10px;font-weight:600;"
    )
    w.setFixedHeight(18)
    return w


# ─────────────────────────────────────────────────────────────────────────────
# WORKERS
# ─────────────────────────────────────────────────────────────────────────────

class CopernicusAuthWorker(QtCore.QThread):
    success = QtCore.pyqtSignal(str)
    failure = QtCore.pyqtSignal(str)

    def __init__(self, user, pwd):
        super().__init__()
        self.user = user
        self.pwd  = pwd

    def run(self):
        try:
            data = urlencode({
                "grant_type": "password",
                "username":   self.user,
                "password":   self.pwd,
                "client_id":  "cdse-public",
            }).encode("utf-8")
            req = Request(
                "https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
                "/protocol/openid-connect/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            token = result.get("access_token", "")
            if token:
                self.success.emit(token)
            else:
                self.failure.emit(f"Réponse inattendue : {result}")
        except HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
                msg = body.get("error_description") or body.get("error") or str(e)
            except Exception:
                msg = f"HTTP {e.code}"
            self.failure.emit(f"Erreur {e.code} : {msg}")
        except URLError as e:
            self.failure.emit(f"Connexion impossible : {e.reason}")
        except Exception as e:
            self.failure.emit(str(e))


class CopernicusSearchWorker(QtCore.QThread):
    success = QtCore.pyqtSignal(list)
    failure = QtCore.pyqtSignal(str)

    def __init__(self, url, token=""):
        super().__init__()
        self.url   = url
        self.token = token

    def run(self):
        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            req = Request(self.url, headers=headers)
            with urlopen(req, timeout=30) as resp:
                raw_data = resp.read()
            data = json.loads(raw_data)
            products = data.get("value", [])
            self.success.emit(products)
        except Exception as e:
            self.failure.emit(str(e))


class GenericWorker(QtCore.QThread):
    success = QtCore.pyqtSignal(object)
    failure = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.success.emit(result)
        except Exception as e:
            self.failure.emit(str(e))


class DownloadWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)
    status   = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, url, dest_path, headers=None):
        super().__init__()
        self.url       = url
        self.dest_path = dest_path
        self.headers   = headers or {}
        self._cancel   = False

    def cancel(self): self._cancel = True

    def run(self):
        try:
            req = Request(self.url, headers=self.headers)
            with urlopen(req, timeout=60) as resp:
                total      = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk      = 65536
                os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)
                with open(self.dest_path, "wb") as f:
                    while not self._cancel:
                        data = resp.read(chunk)
                        if not data: break
                        f.write(data)
                        downloaded += len(data)
                        if total > 0:
                            self.progress.emit(int(downloaded * 100 / total))
                        kb  = downloaded // 1024
                        tot = f" / {total//1024} Ko" if total else ""
                        self.status.emit(f"Téléchargé : {kb} Ko{tot}")
            if self._cancel:
                self.finished.emit(False, "Téléchargement annulé.")
            else:
                self.finished.emit(True, self.dest_path)
        except Exception as e:
            self.finished.emit(False, str(e))


class SchedulerWorker(QtCore.QThread):
    trigger = QtCore.pyqtSignal(dict)

    def __init__(self, tasks_ref):
        super().__init__()
        self._tasks   = tasks_ref
        self._running = True

    def stop(self): self._running = False

    def run(self):
        while self._running:
            now = datetime.datetime.now()
            for task in list(self._tasks):
                if not task.get("enabled", True): continue
                nr = task.get("next_run")
                if nr and now >= nr:
                    self.trigger.emit(task)
                    task["next_run"] = now + datetime.timedelta(hours=task.get("freq_hours", 24))
            QtCore.QThread.sleep(30)


# ─────────────────────────────────────────────────────────────────────────────
# LOADER SPINNER
# ─────────────────────────────────────────────────────────────────────────────

class BtnLoader:
    """
    Gère l'état loading/ready d'un QPushButton.
    Usage :
        loader = BtnLoader(btn, label_ready="Rechercher", label_loading="Recherche…", style_ready=_BTN_PRIMARY)
        loader.start()   # désactive + anime
        loader.stop()    # restaure

    flash(duration_ms) : démarre l'animation puis la stoppe automatiquement
        après `duration_ms` millisecondes. Utile pour donner un feedback
        visuel immédiat même quand l'action s'arrête tout de suite
        (ex : erreur de validation avant tout traitement long).
    """
    SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, btn: QtWidgets.QPushButton, label_ready: str,
                 label_loading: str, style_ready: str):
        self._btn           = btn
        self._label_ready   = label_ready
        self._label_loading = label_loading
        self._style_ready   = style_ready
        self._timer         = QtCore.QTimer()
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self._frame         = 0
        self._flash_timer   = None

    def start(self):
        if self._flash_timer is not None:
            self._flash_timer.stop()
            self._flash_timer = None
        self._btn.setEnabled(False)
        self._btn.setStyleSheet(_BTN_LOADING)
        self._frame = 0
        self._tick()
        self._timer.start()
        QtWidgets.QApplication.processEvents()

    def stop(self):
        self._timer.stop()
        self._btn.setText(self._label_ready)
        self._btn.setStyleSheet(self._style_ready)
        self._btn.setEnabled(True)

    def flash(self, duration_ms=350):
        """Affiche brièvement l'état loading puis revient à l'état normal."""
        self.start()
        if self._flash_timer is None:
            self._flash_timer = QtCore.QTimer()
            self._flash_timer.setSingleShot(True)
            self._flash_timer.timeout.connect(self.stop)
        self._flash_timer.start(duration_ms)

    def _tick(self):
        sp = self.SPINNER[self._frame % len(self.SPINNER)]
        self._btn.setText(f"{sp}  {self._label_loading}")
        self._frame += 1


# ─────────────────────────────────────────────────────────────────────────────
# DIALOGUE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class ImgSatDialog(QtWidgets.QDialog):

    _copernicus_token = ""
    _usgs_token       = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ImgSat — Analyse d'images satellitaires")
        self.setMinimumSize(820, 640)
        self.resize(960, 700)
        self.setStyleSheet(DIALOG_STYLE)

        self._roi_signatures   = {}
        self._download_workers = []
        self._scheduled_tasks  = []
        self._scheduler        = None
        self._stat_data        = []

        self._cop_auth_worker   = None
        self._cop_search_worker = None
        self._usgs_auth_worker  = None
        self._generic_workers   = []

        self._loaders = {}

        self._status_lbl = QtWidgets.QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:11px;padding:3px 8px;color:{_C_TEXT_SEC};")
        self._status_lbl.setWordWrap(True)

        self._build_ui()
        self._init_loaders()
        self._start_scheduler()

    def closeEvent(self, event):
        if self._scheduler:
            self._scheduler.stop()
            self._scheduler.wait(1000)
        for w in self._download_workers:
            w.cancel()
        super().closeEvent(event)

    # ── Structure ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QtWidgets.QWidget()
        header.setStyleSheet(f"background:{_C_PANEL};border-bottom:1px solid {_C_BORDER};")
        header.setFixedHeight(52)
        h_lay = QtWidgets.QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        icon_lbl = QtWidgets.QLabel("🛰")
        icon_lbl.setStyleSheet("font-size:20px;")
        h_lay.addWidget(icon_lbl)
        title = QtWidgets.QLabel("ImgSat")
        title.setStyleSheet(f"font-size:16px;font-weight:700;color:{_C_TEXT};letter-spacing:-0.3px;")
        h_lay.addWidget(title)
        sub = QtWidgets.QLabel("Analyse semi-automatique d'images satellitaires")
        sub.setStyleSheet(f"font-size:11px;color:{_C_TEXT_SEC};margin-left:8px;")
        h_lay.addWidget(sub)
        h_lay.addStretch()
        h_lay.addWidget(_badge("QGIS 3.x", _C_ACCENT, "#1a2d4a"))
        root.addWidget(header)

        body  = QtWidgets.QWidget()
        body.setStyleSheet(f"background:{_C_BG};")
        b_lay = QtWidgets.QVBoxLayout(body)
        b_lay.setContentsMargins(12, 10, 12, 6)
        b_lay.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._tab_acquisition(), "① Acquisition")
        self.tabs.addTab(self._tab_bandes(),      "② Bandes & Formules")
        self.tabs.addTab(self._tab_traitement(),  "③ Traitement")
        self.tabs.addTab(self._tab_export(),      "④ Export")
        b_lay.addWidget(self.tabs)

        status_bar = QtWidgets.QWidget()
        status_bar.setStyleSheet(f"background:{_C_PANEL};border-top:1px solid {_C_BORDER};")
        status_bar.setFixedHeight(28)
        s_lay = QtWidgets.QHBoxLayout(status_bar)
        s_lay.setContentsMargins(10, 0, 10, 0)
        s_lay.addWidget(self._status_lbl)
        s_lay.addStretch()
        b_close = QtWidgets.QPushButton("Fermer")
        b_close.setStyleSheet(_BTN_GHOST)
        b_close.setFixedHeight(22)
        b_close.clicked.connect(self.close)
        s_lay.addWidget(b_close)
        b_lay.addWidget(status_bar)

        root.addWidget(body)

    def _init_loaders(self):
        """Crée les BtnLoader pour chaque bouton d'action après _build_ui."""
        self._loaders = {
            "cop_auth":   BtnLoader(self._cop_btn_auth,   "Connexion OAuth2",           "Connexion…",      _BTN_PRIMARY),
            "cop_search": BtnLoader(self._cop_btn_search, "🔍  Rechercher des produits", "Recherche…",      _BTN_PRIMARY),
            "cop_dl":     BtnLoader(self._cop_btn_dl,     "⬇  Télécharger la sélection","Téléchargement…", _BTN_SUCCESS),
            "usgs_auth":  BtnLoader(self._usgs_btn_auth,  "Connexion M2M API",           "Connexion…",      _BTN_PRIMARY),
            "usgs_search":BtnLoader(self._usgs_btn_search,"🔍  Rechercher des scènes",   "Recherche…",      _BTN_PRIMARY),
            "usgs_dl":    BtnLoader(self._usgs_btn_dl,    "⬇  Télécharger la sélection","Téléchargement…", _BTN_SUCCESS),
            "dos1":       BtnLoader(self._btn_dos1,       "Appliquer DOS1",              "Traitement…",     _BTN_PRIMARY),
            "clip":       BtnLoader(self._btn_clip,       "Découper le raster",          "Découpe…",        _BTN_PRIMARY),
            "reproj":     BtnLoader(self._btn_reproj,     "Reprojeter",                  "Reprojection…",   _BTN_PRIMARY),
            "clf_add":    BtnLoader(self._btn_add_class,  "＋  Ajouter la classe",        "Extraction…",     _BTN_SUCCESS),
            "clf_run":    BtnLoader(self._btn_clf_run,    "▶  Lancer la classification",  "Calcul…",         _BTN_SUCCESS),
            "clf_matrix": BtnLoader(self._btn_conf_mat,  "Calculer la matrice de confusion", "Calcul…",     _BTN_PRIMARY),
            "stats":      BtnLoader(self._btn_stats,      "Calculer",                    "Calcul…",         _BTN_PRIMARY),
            "calc":       BtnLoader(self._btn_calc,       "▶  Calculer",                 "Calcul…",         _BTN_SUCCESS),
            "exp_raster": BtnLoader(self._btn_exp_raster, "⬇  Exporter le raster",       "Export…",         _BTN_PRIMARY),
            "exp_csv":    BtnLoader(self._btn_exp_csv,    "Exporter les statistiques CSV","Export…",        _BTN_PRIMARY),
            "exp_map":    BtnLoader(self._btn_exp_map,    "📷  Capturer la carte",        "Capture…",        _BTN_PRIMARY),
            "report":     BtnLoader(self._btn_report,     "📄  Générer le rapport",       "Génération…",     _BTN_SUCCESS),
        }

    # ═════════════════════════════════════════════════════════════════════
    # ONGLET 1 — ACQUISITION
    # ═════════════════════════════════════════════════════════════════════

    def _tab_acquisition(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        acq_tabs = QtWidgets.QTabWidget()
        acq_tabs.setStyleSheet(f"QTabBar::tab{{min-width:60px;padding:6px 14px;}}")
        acq_tabs.addTab(self._acq_copernicus(), "Copernicus / Sentinel")
        acq_tabs.addTab(self._acq_usgs(),       "USGS / Landsat")
        acq_tabs.addTab(self._acq_scheduler(),  "Planificateur")
        lay.addWidget(acq_tabs)
        return w

    # ── Copernicus ────────────────────────────────────────────────────────

    def _acq_copernicus(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(_info(
            "Compte requis sur dataspace.copernicus.eu (gratuit). "
            "Entrez votre e-mail et mot de passe — le token OAuth2 est récupéré automatiquement."
        ))

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)

        grp_auth = _group("Authentification")
        a_lay = QtWidgets.QGridLayout(grp_auth)
        a_lay.setSpacing(6)
        a_lay.addWidget(_lbl("E-mail :"), 0, 0)
        self._cop_user = QtWidgets.QLineEdit()
        self._cop_user.setPlaceholderText("votre@email.com")
        a_lay.addWidget(self._cop_user, 0, 1)
        a_lay.addWidget(_lbl("Mot de passe :"), 1, 0)
        self._cop_pass = QtWidgets.QLineEdit()
        self._cop_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        a_lay.addWidget(self._cop_pass, 1, 1)

        self._cop_btn_auth = QtWidgets.QPushButton("Connexion OAuth2")
        self._cop_btn_auth.setStyleSheet(_BTN_PRIMARY)
        self._cop_btn_auth.clicked.connect(self._cop_authenticate)
        a_lay.addWidget(self._cop_btn_auth, 2, 0, 1, 2)

        self._cop_auth_lbl = QtWidgets.QLabel("● Non connecté")
        self._cop_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_DANGER};")
        a_lay.addWidget(self._cop_auth_lbl, 3, 0, 1, 2)
        top.addWidget(grp_auth, 1)

        grp_p = _group("Paramètres")
        p_lay = QtWidgets.QGridLayout(grp_p)
        p_lay.setSpacing(5)
        p_lay.addWidget(_lbl("Collection :"), 0, 0)
        self._cop_coll = QtWidgets.QComboBox()
        self._cop_coll.addItems(["SENTINEL-2", "SENTINEL-1", "SENTINEL-3"])
        p_lay.addWidget(self._cop_coll, 0, 1)
        p_lay.addWidget(_lbl("Niveau :"), 1, 0)
        self._cop_level = QtWidgets.QComboBox()
        self._cop_level.addItems(["L2A", "L1C", "GRD", "SLC"])
        p_lay.addWidget(self._cop_level, 1, 1)
        p_lay.addWidget(_lbl("Nuages max :"), 2, 0)
        self._cop_cloud = QtWidgets.QSpinBox()
        self._cop_cloud.setRange(0, 100)
        self._cop_cloud.setValue(20)
        self._cop_cloud.setSuffix(" %")
        p_lay.addWidget(self._cop_cloud, 2, 1)
        top.addWidget(grp_p, 1)
        lay.addLayout(top)

        mid = QtWidgets.QHBoxLayout()
        mid.setSpacing(8)
        grp_d = _group("Période")
        d_lay = QtWidgets.QFormLayout(grp_d)
        d_lay.setSpacing(5)
        self._cop_d_start = QtWidgets.QDateEdit()
        self._cop_d_start.setCalendarPopup(True)
        self._cop_d_start.setDate(QtCore.QDate.currentDate().addDays(-30))
        d_lay.addRow("Début :", self._cop_d_start)
        self._cop_d_end = QtWidgets.QDateEdit()
        self._cop_d_end.setCalendarPopup(True)
        self._cop_d_end.setDate(QtCore.QDate.currentDate())
        d_lay.addRow("Fin :", self._cop_d_end)
        mid.addWidget(grp_d, 1)

        grp_b = _group("Emprise (WGS84)")
        b_lay = QtWidgets.QVBoxLayout(grp_b)
        b_lay.setSpacing(5)
        self._cop_bbox = QtWidgets.QLineEdit()
        self._cop_bbox.setPlaceholderText("xmin,ymin,xmax,ymax")
        b_lay.addWidget(self._cop_bbox)
        btn_bbox = QtWidgets.QPushButton("⊕  Depuis l'emprise du projet")
        btn_bbox.setStyleSheet(_BTN_GHOST)
        btn_bbox.clicked.connect(self._fill_cop_bbox)
        b_lay.addWidget(btn_bbox)
        mid.addWidget(grp_b, 2)
        lay.addLayout(mid)

        self._cop_btn_search = QtWidgets.QPushButton("🔍  Rechercher des produits")
        self._cop_btn_search.setStyleSheet(_BTN_PRIMARY)
        self._cop_btn_search.setFixedHeight(34)
        self._cop_btn_search.clicked.connect(self._cop_search)
        lay.addWidget(self._cop_btn_search)

        self._cop_table = QtWidgets.QTableWidget(0, 5)
        self._cop_table.setHorizontalHeaderLabels(["Titre", "Date", "Nuages", "Taille", "ID"])
        self._cop_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._cop_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._cop_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._cop_table.setAlternatingRowColors(True)
        self._cop_table.setMaximumHeight(140)
        lay.addWidget(self._cop_table)

        self._cop_sel_lbl = QtWidgets.QLabel("Sélectionnez un produit dans la liste ci-dessus puis cliquez Télécharger.")
        self._cop_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_TEXT_HINT};font-style:italic;")
        lay.addWidget(self._cop_sel_lbl)
        self._cop_table.itemSelectionChanged.connect(self._cop_on_selection)

        dl_row = QtWidgets.QHBoxLayout()
        dl_row.addWidget(_lbl("Dossier :"))
        self._cop_dl_dir = QtWidgets.QLineEdit()
        self._cop_dl_dir.setPlaceholderText("Dossier de destination")
        btn_dir = QtWidgets.QPushButton("…")
        btn_dir.setStyleSheet(_BTN_SMALL)
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._browse_cop_dir)
        dl_row.addWidget(self._cop_dl_dir)
        dl_row.addWidget(btn_dir)
        lay.addLayout(dl_row)

        btns = QtWidgets.QHBoxLayout()
        self._cop_btn_dl = QtWidgets.QPushButton("⬇  Télécharger la sélection")
        self._cop_btn_dl.setStyleSheet(_BTN_SUCCESS)
        self._cop_btn_dl.clicked.connect(self._cop_download)
        b_cancel = QtWidgets.QPushButton("✕  Annuler")
        b_cancel.setStyleSheet(_BTN_DANGER)
        b_cancel.clicked.connect(self._cop_cancel)
        btns.addWidget(self._cop_btn_dl)
        btns.addWidget(b_cancel)
        btns.addStretch()
        lay.addLayout(btns)

        self._cop_prog = QtWidgets.QProgressBar()
        self._cop_prog.setMaximumHeight(5)
        self._cop_prog.setTextVisible(False)
        lay.addWidget(self._cop_prog)
        self._cop_dl_lbl = QtWidgets.QLabel("")
        self._cop_dl_lbl.setStyleSheet(f"font-size:11px;color:{_C_TEXT_SEC};")
        lay.addWidget(self._cop_dl_lbl)

        lay.addStretch()
        return w

    # ── USGS ──────────────────────────────────────────────────────────────

    def _acq_usgs(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(_info(
            "Compte requis sur ers.cr.usgs.gov (gratuit). "
            "Activez l'accès M2M dans votre profil → onglet 'Machine to Machine'."
        ))

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)

        grp_auth = _group("Authentification")
        a_lay = QtWidgets.QGridLayout(grp_auth)
        a_lay.setSpacing(6)
        a_lay.addWidget(_lbl("Utilisateur :"), 0, 0)
        self._usgs_user = QtWidgets.QLineEdit()
        a_lay.addWidget(self._usgs_user, 0, 1)
        a_lay.addWidget(_lbl("Mot de passe :"), 1, 0)
        self._usgs_pass = QtWidgets.QLineEdit()
        self._usgs_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        a_lay.addWidget(self._usgs_pass, 1, 1)
        self._usgs_btn_auth = QtWidgets.QPushButton("Connexion M2M API")
        self._usgs_btn_auth.setStyleSheet(_BTN_PRIMARY)
        self._usgs_btn_auth.clicked.connect(self._usgs_authenticate)
        a_lay.addWidget(self._usgs_btn_auth, 2, 0, 1, 2)
        self._usgs_auth_lbl = QtWidgets.QLabel("● Non connecté")
        self._usgs_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_DANGER};")
        a_lay.addWidget(self._usgs_auth_lbl, 3, 0, 1, 2)
        top.addWidget(grp_auth, 1)

        grp_p = _group("Paramètres")
        p_lay = QtWidgets.QGridLayout(grp_p)
        p_lay.setSpacing(5)
        p_lay.addWidget(_lbl("Dataset :"), 0, 0)
        self._usgs_ds = QtWidgets.QComboBox()
        self._usgs_ds.addItems(["landsat_ot_c2_l2", "landsat_ot_c2_l1", "landsat_etm_c2_l2"])
        p_lay.addWidget(self._usgs_ds, 0, 1)
        p_lay.addWidget(_lbl("Nuages max :"), 1, 0)
        self._usgs_cloud = QtWidgets.QSpinBox()
        self._usgs_cloud.setRange(0, 100)
        self._usgs_cloud.setValue(20)
        self._usgs_cloud.setSuffix(" %")
        p_lay.addWidget(self._usgs_cloud, 1, 1)
        top.addWidget(grp_p, 1)
        lay.addLayout(top)

        mid = QtWidgets.QHBoxLayout()
        mid.setSpacing(8)
        grp_d = _group("Période")
        d_lay = QtWidgets.QFormLayout(grp_d)
        d_lay.setSpacing(5)
        self._usgs_d_start = QtWidgets.QDateEdit()
        self._usgs_d_start.setCalendarPopup(True)
        self._usgs_d_start.setDate(QtCore.QDate.currentDate().addDays(-30))
        d_lay.addRow("Début :", self._usgs_d_start)
        self._usgs_d_end = QtWidgets.QDateEdit()
        self._usgs_d_end.setCalendarPopup(True)
        self._usgs_d_end.setDate(QtCore.QDate.currentDate())
        d_lay.addRow("Fin :", self._usgs_d_end)
        mid.addWidget(grp_d, 1)

        grp_b = _group("Emprise (WGS84)")
        b_lay = QtWidgets.QVBoxLayout(grp_b)
        b_lay.setSpacing(5)
        self._usgs_bbox = QtWidgets.QLineEdit()
        self._usgs_bbox.setPlaceholderText("xmin,ymin,xmax,ymax")
        b_lay.addWidget(self._usgs_bbox)
        btn_bb = QtWidgets.QPushButton("⊕  Depuis l'emprise du projet")
        btn_bb.setStyleSheet(_BTN_GHOST)
        btn_bb.clicked.connect(self._fill_usgs_bbox)
        b_lay.addWidget(btn_bb)
        mid.addWidget(grp_b, 2)
        lay.addLayout(mid)

        self._usgs_btn_search = QtWidgets.QPushButton("🔍  Rechercher des scènes")
        self._usgs_btn_search.setStyleSheet(_BTN_PRIMARY)
        self._usgs_btn_search.setFixedHeight(34)
        self._usgs_btn_search.clicked.connect(self._usgs_search)
        lay.addWidget(self._usgs_btn_search)

        self._usgs_table = QtWidgets.QTableWidget(0, 4)
        self._usgs_table.setHorizontalHeaderLabels(["Nom de scène", "Date", "Nuages", "ID entité"])
        self._usgs_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._usgs_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._usgs_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._usgs_table.setAlternatingRowColors(True)
        self._usgs_table.setMaximumHeight(140)
        lay.addWidget(self._usgs_table)

        self._usgs_sel_lbl = QtWidgets.QLabel("Sélectionnez une scène dans la liste ci-dessus puis cliquez Télécharger.")
        self._usgs_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_TEXT_HINT};font-style:italic;")
        lay.addWidget(self._usgs_sel_lbl)
        self._usgs_table.itemSelectionChanged.connect(self._usgs_on_selection)

        dl_row = QtWidgets.QHBoxLayout()
        dl_row.addWidget(_lbl("Dossier :"))
        self._usgs_dl_dir = QtWidgets.QLineEdit()
        btn_dir = QtWidgets.QPushButton("…")
        btn_dir.setStyleSheet(_BTN_SMALL)
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._browse_usgs_dir)
        dl_row.addWidget(self._usgs_dl_dir)
        dl_row.addWidget(btn_dir)
        lay.addLayout(dl_row)

        self._usgs_btn_dl = QtWidgets.QPushButton("⬇  Télécharger la sélection")
        self._usgs_btn_dl.setStyleSheet(_BTN_SUCCESS)
        self._usgs_btn_dl.clicked.connect(self._usgs_download)
        lay.addWidget(self._usgs_btn_dl)

        self._usgs_prog = QtWidgets.QProgressBar()
        self._usgs_prog.setMaximumHeight(5)
        self._usgs_prog.setTextVisible(False)
        lay.addWidget(self._usgs_prog)
        lay.addStretch()
        return w

    # ── Planificateur ─────────────────────────────────────────────────────

    def _acq_scheduler(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(_info(
            "Programmez des téléchargements récurrents. "
            "Le planificateur vérifie toutes les 30 s si une tâche doit s'exécuter."
        ))

        grp   = _group("Nouvelle tâche")
        g_lay = QtWidgets.QGridLayout(grp)
        g_lay.setSpacing(6)

        g_lay.addWidget(_lbl("Nom :"), 0, 0)
        self._sch_name = QtWidgets.QLineEdit()
        self._sch_name.setPlaceholderText("ex. Sentinel-2 mensuel")
        g_lay.addWidget(self._sch_name, 0, 1, 1, 3)

        g_lay.addWidget(_lbl("Source :"), 1, 0)
        self._sch_src = QtWidgets.QComboBox()
        self._sch_src.addItems(["Copernicus Sentinel-2", "Copernicus Sentinel-1", "USGS Landsat"])
        g_lay.addWidget(self._sch_src, 1, 1)

        g_lay.addWidget(_lbl("Fréquence :"), 1, 2)
        self._sch_freq = QtWidgets.QComboBox()
        self._sch_freq.addItems(["Toutes les 6 h", "Quotidienne", "Hebdomadaire", "Mensuelle"])
        g_lay.addWidget(self._sch_freq, 1, 3)

        g_lay.addWidget(_lbl("1ère exécution :"), 2, 0)
        self._sch_first = QtWidgets.QDateTimeEdit()
        self._sch_first.setCalendarPopup(True)
        self._sch_first.setDateTime(QtCore.QDateTime.currentDateTime().addSecs(3600))
        g_lay.addWidget(self._sch_first, 2, 1)

        g_lay.addWidget(_lbl("Nuages max :"), 2, 2)
        self._sch_cloud = QtWidgets.QSpinBox()
        self._sch_cloud.setRange(0, 100)
        self._sch_cloud.setValue(20)
        self._sch_cloud.setSuffix(" %")
        g_lay.addWidget(self._sch_cloud, 2, 3)

        g_lay.addWidget(_lbl("Dossier :"), 3, 0)
        self._sch_dir = QtWidgets.QLineEdit()
        btn_sdir = QtWidgets.QPushButton("…")
        btn_sdir.setStyleSheet(_BTN_SMALL)
        btn_sdir.setFixedWidth(30)
        btn_sdir.clicked.connect(self._browse_sch_dir)
        h = QtWidgets.QHBoxLayout()
        h.addWidget(self._sch_dir)
        h.addWidget(btn_sdir)
        g_lay.addLayout(h, 3, 1, 1, 3)

        btn_add = QtWidgets.QPushButton("＋  Ajouter la tâche")
        btn_add.setStyleSheet(_BTN_SUCCESS)
        btn_add.clicked.connect(self._add_scheduled_task)
        g_lay.addWidget(btn_add, 4, 0, 1, 4)
        lay.addWidget(grp)

        lay.addWidget(_lbl("Tâches planifiées :", bold=True))
        self._sch_list = QtWidgets.QListWidget()
        self._sch_list.setMaximumHeight(130)
        lay.addWidget(self._sch_list)

        btns = QtWidgets.QHBoxLayout()
        b_rm = QtWidgets.QPushButton("Supprimer")
        b_rm.setStyleSheet(_BTN_DANGER)
        b_rm.clicked.connect(self._remove_scheduled_task)
        b_tog = QtWidgets.QPushButton("Activer / Pause")
        b_tog.setStyleSheet(_BTN_WARN)
        b_tog.clicked.connect(self._toggle_scheduled_task)
        btns.addWidget(b_rm)
        btns.addWidget(b_tog)
        btns.addStretch()
        lay.addLayout(btns)
        lay.addStretch()
        return w

    # ═════════════════════════════════════════════════════════════════════
    # ONGLET 2 — BANDES & FORMULES
    # ═════════════════════════════════════════════════════════════════════

    def _tab_bandes(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        sub = QtWidgets.QTabWidget()
        sub.addTab(self._bandes_inventaire(), "Inventaire")
        sub.addTab(self._bandes_composite(),  "Composite RGB")
        sub.addTab(self._bandes_formules(),   "Éditeur de formules")
        lay.addWidget(sub)
        return w

    def _bandes_inventaire(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        btns = QtWidgets.QHBoxLayout()
        b_refresh = QtWidgets.QPushButton("↻  Actualiser")
        b_refresh.setStyleSheet(_BTN_PRIMARY)
        b_refresh.clicked.connect(self._refresh_bands)
        b_load = QtWidgets.QPushButton("⊕  Charger un fichier raster…")
        b_load.setStyleSheet(_BTN_GHOST)
        b_load.clicked.connect(self._load_raster_file)
        btns.addWidget(b_refresh)
        btns.addWidget(b_load)
        btns.addStretch()
        lay.addLayout(btns)

        self._band_table = QtWidgets.QTableWidget(0, 4)
        self._band_table.setHorizontalHeaderLabels(["Nom", "Bandes", "CRS", "Fichier"])
        self._band_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._band_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self._band_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._band_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._band_table.setAlternatingRowColors(True)
        self._band_table.itemSelectionChanged.connect(self._on_band_sel)
        lay.addWidget(self._band_table)

        detail_grp = _group("Détails")
        d_lay = QtWidgets.QVBoxLayout(detail_grp)
        self._band_detail = QtWidgets.QTextEdit()
        self._band_detail.setReadOnly(True)
        self._band_detail.setMaximumHeight(80)
        self._band_detail.setStyleSheet(
            f"QTextEdit{{background:{_C_BG};color:{_C_TEXT_SEC};"
            f"border:none;font-size:11px;font-family:monospace;}}"
        )
        self._band_detail.setPlaceholderText("Sélectionnez une ligne pour voir les détails…")
        d_lay.addWidget(self._band_detail)
        lay.addWidget(detail_grp)

        self._refresh_bands()
        return w

    def _bandes_composite(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(_info("Assigne les canaux R, V, B à des bandes de la couche sélectionnée."))

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(_lbl("Couche source :"))
        self._rgb_layer = QgsMapLayerComboBox()
        self._rgb_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self._rgb_layer.layerChanged.connect(self._rgb_layer_changed)
        row1.addWidget(self._rgb_layer)
        lay.addLayout(row1)

        grp_pre = _group("Presets satellites")
        pre_lay = QtWidgets.QGridLayout(grp_pre)
        pre_lay.setSpacing(5)
        presets = [
            ("Couleurs naturelles",    "R=3 G=2 B=1", (3, 2, 1)),
            ("Fausses couleurs végét.","R=4 G=3 B=2", (4, 3, 2)),
            ("Infrarouge couleur",     "R=5 G=4 B=3", (5, 4, 3)),
            ("Agriculture SWIR",       "R=6 G=5 B=2", (6, 5, 2)),
            ("Bathymétrie / eau",      "R=4 G=3 B=1", (4, 3, 1)),
            ("Analyse géologique",     "R=7 G=5 B=2", (7, 5, 2)),
        ]
        for i, (name, desc, bands) in enumerate(presets):
            btn = QtWidgets.QPushButton(f"{name}\n{desc}")
            btn.setStyleSheet(
                f"QPushButton{{background:{_C_SURFACE};color:{_C_TEXT};"
                f"border:1px solid {_C_BORDER};border-radius:5px;"
                f"padding:6px;font-size:11px;text-align:left;}}"
                f"QPushButton:hover{{border-color:{_C_ACCENT};background:{_C_BG};}}"
            )
            btn.setFixedHeight(44)
            btn.clicked.connect(lambda _, b=bands: self._apply_preset_bands(b))
            pre_lay.addWidget(btn, i // 3, i % 3)
        lay.addWidget(grp_pre)

        grp_rgb = _group("Assignation manuelle")
        rgb_lay = QtWidgets.QGridLayout(grp_rgb)
        rgb_lay.setSpacing(6)
        for i, (label, color) in enumerate([
            ("Rouge (R)", "#f85149"),
            ("Vert  (G)", "#3fb950"),
            ("Bleu  (B)", "#58a6ff"),
        ]):
            lbl_c = QtWidgets.QLabel(f"■ {label}")
            lbl_c.setStyleSheet(f"color:{color};font-weight:600;")
            rgb_lay.addWidget(lbl_c, i, 0)
        self._combo_r = QtWidgets.QComboBox()
        self._combo_g = QtWidgets.QComboBox()
        self._combo_b = QtWidgets.QComboBox()
        for i, c in enumerate([self._combo_r, self._combo_g, self._combo_b]):
            rgb_lay.addWidget(c, i, 1)
        lay.addWidget(grp_rgb)

        btn_apply = QtWidgets.QPushButton("Appliquer le composite")
        btn_apply.setStyleSheet(_BTN_PRIMARY)
        btn_apply.clicked.connect(self._apply_composite)
        lay.addWidget(btn_apply)
        lay.addStretch()
        self._rgb_layer_changed()
        return w

    def _bandes_formules(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        if not HAS_RASTER_CALC:
            lay.addWidget(_warn("QgsRasterCalculator non disponible."))

        src_row = QtWidgets.QHBoxLayout()
        src_row.addWidget(_lbl("Couche source :"))
        self._idx_layer = QgsMapLayerComboBox()
        self._idx_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self._idx_layer.layerChanged.connect(self._idx_layer_changed)
        src_row.addWidget(self._idx_layer)
        lay.addLayout(src_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left  = QtWidgets.QWidget()
        l_lay = QtWidgets.QVBoxLayout(left)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(4)
        l_lay.addWidget(_lbl("Bandes disponibles", bold=True, color=_C_TEXT_SEC))
        l_lay.addWidget(_lbl("Double-clic → insère dans la formule", color=_C_TEXT_HINT, size=10))
        self._band_formula_list = QtWidgets.QListWidget()
        self._band_formula_list.itemDoubleClicked.connect(self._insert_band_ref)
        l_lay.addWidget(self._band_formula_list)

        l_lay.addWidget(_lbl("Indices prédéfinis", bold=True, color=_C_TEXT_SEC))
        presets_idx = [
            ("NDVI", "(NIR−R)/(NIR+R)", "ndvi"),
            ("NDWI", "(V−NIR)/(V+NIR)", "ndwi"),
            ("NDBI", "(SWIR−NIR)/(SWIR+NIR)", "ndbi"),
            ("EVI",  "2.5×(NIR−R)/(...)", "evi"),
            ("Norm.", "(B−min)/(max−min)", "norm"),
        ]
        for name, formula_hint, key in presets_idx:
            btn = QtWidgets.QPushButton(f"{name}   {formula_hint}")
            btn.setStyleSheet(
                f"QPushButton{{background:{_C_SURFACE};color:{_C_TEXT};"
                f"border:1px solid {_C_BORDER};border-radius:4px;"
                f"padding:4px 8px;font-size:11px;text-align:left;}}"
                f"QPushButton:hover{{background:{_C_BG};border-color:{_C_ACCENT};}}"
            )
            btn.clicked.connect(lambda _, k=key: self._load_preset_formula(k))
            l_lay.addWidget(btn)
        splitter.addWidget(left)

        right = QtWidgets.QWidget()
        r_lay = QtWidgets.QVBoxLayout(right)
        r_lay.setContentsMargins(8, 0, 0, 0)
        r_lay.setSpacing(6)
        r_lay.addWidget(_lbl("Formule", bold=True, color=_C_TEXT_SEC))

        self._formula_edit = QtWidgets.QLineEdit()
        self._formula_edit.setStyleSheet(
            f"QLineEdit{{background:{_C_BG};color:{_C_TEXT};"
            f"border:1px solid {_C_BORDER};border-radius:5px;"
            f"padding:8px;font-size:13px;font-family:monospace;}}"
            f"QLineEdit:focus{{border:1px solid {_C_ACCENT};}}"
        )
        self._formula_edit.setPlaceholderText("ex: (b4@1 - b3@1) / (b4@1 + b3@1 + 0.0001)")
        self._formula_edit.setFixedHeight(36)
        r_lay.addWidget(self._formula_edit)

        ops_grp = _group("Opérateurs")
        ops_lay = QtWidgets.QVBoxLayout(ops_grp)
        ops_lay.setSpacing(4)

        row_ops1 = QtWidgets.QHBoxLayout()
        row_ops1.setSpacing(4)
        for op in ["+", "−", "×", "÷", "(", ")", "."]:
            b = QtWidgets.QPushButton(op)
            b.setStyleSheet(_BTN_OP)
            b.setFixedSize(36, 30)
            b.clicked.connect(lambda _, o=op: self._insert_op(o))
            row_ops1.addWidget(b)
        row_ops1.addStretch()
        ops_lay.addLayout(row_ops1)

        row_ops2 = QtWidgets.QHBoxLayout()
        row_ops2.setSpacing(4)
        for f in ["sqrt(", "**2", "log(", "exp(", "abs(", "min(", "max("]:
            b = QtWidgets.QPushButton(f)
            b.setStyleSheet(_BTN_OP)
            b.setFixedHeight(28)
            b.clicked.connect(lambda _, o=f: self._insert_op(o))
            row_ops2.addWidget(b)
        row_ops2.addStretch()
        ops_lay.addLayout(row_ops2)

        row_ops3 = QtWidgets.QHBoxLayout()
        row_ops3.setSpacing(4)
        for val in ["0.0001", "2", "6", "7.5", "255", "10000"]:
            b = QtWidgets.QPushButton(val)
            b.setStyleSheet(_BTN_OP)
            b.setFixedHeight(26)
            b.clicked.connect(lambda _, o=val: self._insert_op(o))
            row_ops3.addWidget(b)
        btn_clr = QtWidgets.QPushButton("⌫ Effacer")
        btn_clr.setStyleSheet(_BTN_DANGER)
        btn_clr.setFixedHeight(26)
        btn_clr.clicked.connect(lambda: self._formula_edit.clear())
        row_ops3.addWidget(btn_clr)
        row_ops3.addStretch()
        ops_lay.addLayout(row_ops3)
        r_lay.addWidget(ops_grp)

        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Fichier de sortie :"))
        self._idx_out = QtWidgets.QLineEdit()
        self._idx_out.setPlaceholderText("chemin/vers/resultat.tif")
        btn_brw = QtWidgets.QPushButton("…")
        btn_brw.setStyleSheet(_BTN_SMALL)
        btn_brw.setFixedWidth(30)
        btn_brw.clicked.connect(lambda: self._browse_output(self._idx_out))
        out_row.addWidget(self._idx_out)
        out_row.addWidget(btn_brw)
        r_lay.addLayout(out_row)

        calc_btns = QtWidgets.QHBoxLayout()
        self._btn_calc = QtWidgets.QPushButton("▶  Calculer")
        self._btn_calc.setStyleSheet(_BTN_SUCCESS)
        self._btn_calc.setFixedHeight(34)
        self._btn_calc.setEnabled(HAS_RASTER_CALC)
        self._btn_calc.clicked.connect(self._compute_custom_formula)
        calc_btns.addWidget(self._btn_calc)
        calc_btns.addStretch()
        r_lay.addLayout(calc_btns)

        self._formula_result = QtWidgets.QLabel("")
        self._formula_result.setWordWrap(True)
        self._formula_result.setStyleSheet(_BOX_SUCCESS)
        self._formula_result.hide()
        r_lay.addWidget(self._formula_result)
        r_lay.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([240, 480])
        lay.addWidget(splitter)

        self._idx_layer_changed()
        return w

    # ═════════════════════════════════════════════════════════════════════
    # ONGLET 3 — TRAITEMENT
    # ═════════════════════════════════════════════════════════════════════

    def _tab_traitement(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        sub = QtWidgets.QTabWidget()
        sub.addTab(self._trait_pretraitement(),  "Prétraitement")
        sub.addTab(self._trait_classification(), "Classification")
        sub.addTab(self._trait_statistiques(),   "Statistiques")
        lay.addWidget(sub)
        return w

    def _trait_pretraitement(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        src_row = QtWidgets.QHBoxLayout()
        src_row.addWidget(_lbl("Couche source :"))
        self._pre_layer = QgsMapLayerComboBox()
        self._pre_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        src_row.addWidget(self._pre_layer)
        lay.addLayout(src_row)
        ops = QtWidgets.QTabWidget()
        ops.setStyleSheet(f"QTabBar::tab{{min-width:50px;padding:5px 12px;font-size:11px;}}")
        ops.addTab(self._pre_dos1(),      "DOS1")
        ops.addTab(self._pre_clip(),      "Découpe ROI")
        ops.addTab(self._pre_reproject(), "Reprojection")
        lay.addWidget(ops)
        lay.addStretch()
        return w

    def _pre_dos1(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_info("Dark Object Subtraction (DOS1) : soustrait la valeur minimale de chaque bande."))
        self._dos1_auto = QtWidgets.QCheckBox("Calculer automatiquement le minimum par bande")
        self._dos1_auto.setChecked(True)
        lay.addWidget(self._dos1_auto)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(_lbl("Valeur fixe (si non auto) :"))
        self._dos1_min = QtWidgets.QDoubleSpinBox()
        self._dos1_min.setRange(0, 10000)
        self._dos1_min.setValue(1.0)
        self._dos1_min.setDecimals(1)
        self._dos1_min.setSuffix(" DN")
        row.addWidget(self._dos1_min)
        row.addStretch()
        lay.addLayout(row)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._dos1_out = QtWidgets.QLineEdit()
        self._dos1_out.setPlaceholderText("sortie_dos1.tif")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._dos1_out))
        out_row.addWidget(self._dos1_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_dos1 = QtWidgets.QPushButton("Appliquer DOS1")
        self._btn_dos1.setStyleSheet(_BTN_PRIMARY)
        self._btn_dos1.clicked.connect(self._apply_dos1)
        lay.addWidget(self._btn_dos1)
        lay.addStretch()
        return w

    def _pre_clip(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_lbl("Couche vecteur de découpe :"))
        self._clip_layer = QgsMapLayerComboBox()
        self._clip_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self._clip_layer.setAllowEmptyLayer(True)
        lay.addWidget(self._clip_layer)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._clip_out = QtWidgets.QLineEdit()
        self._clip_out.setPlaceholderText("sortie_clip.tif")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._clip_out))
        out_row.addWidget(self._clip_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_clip = QtWidgets.QPushButton("Découper le raster")
        self._btn_clip.setStyleSheet(_BTN_PRIMARY)
        self._btn_clip.clicked.connect(self._apply_clip)
        lay.addWidget(self._btn_clip)
        lay.addStretch()
        return w

    def _pre_reproject(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_lbl("CRS cible :"))
        self._reproj_crs = QtWidgets.QLineEdit()
        self._reproj_crs.setPlaceholderText("EPSG:32630")
        self._reproj_crs.setText("EPSG:4326")
        lay.addWidget(self._reproj_crs)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._reproj_out = QtWidgets.QLineEdit()
        self._reproj_out.setPlaceholderText("sortie_reproj.tif")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._reproj_out))
        out_row.addWidget(self._reproj_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_reproj = QtWidgets.QPushButton("Reprojeter")
        self._btn_reproj.setStyleSheet(_BTN_PRIMARY)
        self._btn_reproj.clicked.connect(self._apply_reproject)
        lay.addWidget(self._btn_reproj)
        lay.addStretch()
        return w

    # ═════════════════════════════════════════════════════════════════════
    # ONGLET 3 > Classification — PANNEAU UNIQUE
    # ═════════════════════════════════════════════════════════════════════

    def _trait_classification(self):
        """
        Panneau unique (scrollable) :
          ① Couches source (raster + ROI)
          ② Ajout / liste des classes d'entraînement
          ③ Algorithme + sortie + bouton Lancer (avec loader)
          ④ Validation optionnelle (matrice de confusion)
        """
        outer   = QtWidgets.QWidget()
        o_lay   = QtWidgets.QVBoxLayout(outer)
        o_lay.setContentsMargins(0, 0, 0, 0)
        o_lay.setSpacing(0)

        scroll  = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(_info(
            "① Sélectionnez le raster et un ROI vecteur, nommez la classe et ajoutez-la.  "
            "② Choisissez l'algorithme et le fichier de sortie, puis lancez.  "
            "③ (Optionnel) Calculez la matrice de confusion avec une couche de vérité terrain."
        ))

        # ── ① Couches source ────────────────────────────────────────────
        src_grp = _group("① Couches source")
        src_lay = QtWidgets.QGridLayout(src_grp)
        src_lay.setSpacing(6)

        src_lay.addWidget(_lbl("Couche raster :"), 0, 0)
        self._clf_layer = QgsMapLayerComboBox()
        self._clf_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        src_lay.addWidget(self._clf_layer, 0, 1)

        src_lay.addWidget(_lbl("Couche ROI (vecteur) :"), 1, 0)
        self._clf_roi = QgsMapLayerComboBox()
        self._clf_roi.setFilters(QgsMapLayerProxyModel.VectorLayer)
        src_lay.addWidget(self._clf_roi, 1, 1)
        lay.addWidget(src_grp)

        # ── ② Classes d'entraînement ────────────────────────────────────
        cls_grp = _group("② Classes d'entraînement")
        cls_lay = QtWidgets.QVBoxLayout(cls_grp)
        cls_lay.setSpacing(6)

        row_n = QtWidgets.QHBoxLayout()
        row_n.setSpacing(6)
        row_n.addWidget(_lbl("Nom :"))
        self._class_name = QtWidgets.QLineEdit()
        self._class_name.setPlaceholderText("ex: Eau, Forêt, Sol nu")
        row_n.addWidget(self._class_name)

        from qgis.gui import QgsColorButton
        self._class_color_btn = QgsColorButton()
        self._class_color_btn.setColor(QtGui.QColor("#2f81f7"))
        self._class_color_btn.setFixedWidth(40)
        row_n.addWidget(self._class_color_btn)

        self._btn_add_class = QtWidgets.QPushButton("＋  Ajouter la classe")
        self._btn_add_class.setStyleSheet(_BTN_SUCCESS)
        self._btn_add_class.setFixedHeight(30)
        self._btn_add_class.clicked.connect(self._add_class)
        row_n.addWidget(self._btn_add_class)
        cls_lay.addLayout(row_n)

        self._class_list = QtWidgets.QListWidget()
        self._class_list.setMaximumHeight(100)
        cls_lay.addWidget(self._class_list)

        btn_clear = QtWidgets.QPushButton("✕  Effacer toutes les classes")
        btn_clear.setStyleSheet(_BTN_GHOST)
        btn_clear.setFixedHeight(24)
        btn_clear.clicked.connect(self._clear_classes)
        cls_lay.addWidget(btn_clear)
        lay.addWidget(cls_grp)

        # ── ③ Lancer la classification ──────────────────────────────────
        run_grp = _group("③ Lancer la classification")
        run_lay = QtWidgets.QGridLayout(run_grp)
        run_lay.setSpacing(6)

        run_lay.addWidget(_lbl("Algorithme :"), 0, 0)
        self._alg_combo = QtWidgets.QComboBox()
        self._alg_combo.addItems(["Minimum Distance (euclidien)", "Spectral Angle Mapper (SAM)"])
        run_lay.addWidget(self._alg_combo, 0, 1, 1, 2)

        run_lay.addWidget(_lbl("Sortie :"), 1, 0)
        self._clf_out = QtWidgets.QLineEdit()
        self._clf_out.setPlaceholderText("classification.tif")
        btn_out = QtWidgets.QPushButton("…")
        btn_out.setStyleSheet(_BTN_SMALL)
        btn_out.setFixedWidth(30)
        btn_out.clicked.connect(lambda: self._browse_output(self._clf_out))
        run_lay.addWidget(self._clf_out, 1, 1)
        run_lay.addWidget(btn_out, 1, 2)

        self._btn_clf_run = QtWidgets.QPushButton("▶  Lancer la classification")
        self._btn_clf_run.setStyleSheet(_BTN_SUCCESS)
        self._btn_clf_run.setFixedHeight(38)
        self._btn_clf_run.clicked.connect(self._run_classification)
        run_lay.addWidget(self._btn_clf_run, 2, 0, 1, 3)

        self._clf_prog = QtWidgets.QProgressBar()
        self._clf_prog.setMaximumHeight(5)
        self._clf_prog.setTextVisible(False)
        self._clf_prog.hide()
        run_lay.addWidget(self._clf_prog, 3, 0, 1, 3)
        lay.addWidget(run_grp)

        # ── ④ Validation optionnelle ────────────────────────────────────
        val_grp = _group("④ Validation — Matrice de confusion (optionnel)")
        val_lay = QtWidgets.QGridLayout(val_grp)
        val_lay.setSpacing(6)

        val_lay.addWidget(_lbl("Couche classifiée (raster) :"), 0, 0)
        self._val_clf_layer = QgsMapLayerComboBox()
        self._val_clf_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        val_lay.addWidget(self._val_clf_layer, 0, 1)

        val_lay.addWidget(_lbl("Vérité terrain (vecteur) :"), 1, 0)
        self._val_ref_layer = QgsMapLayerComboBox()
        self._val_ref_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        val_lay.addWidget(self._val_ref_layer, 1, 1)

        val_lay.addWidget(_lbl("Champ nom de classe :"), 2, 0)
        self._val_field = QtWidgets.QLineEdit()
        self._val_field.setPlaceholderText("ex: classe, type, nom…")
        val_lay.addWidget(self._val_field, 2, 1)

        self._btn_conf_mat = QtWidgets.QPushButton("Calculer la matrice de confusion")
        self._btn_conf_mat.setStyleSheet(_BTN_PRIMARY)
        self._btn_conf_mat.clicked.connect(self._compute_confusion_matrix)
        val_lay.addWidget(self._btn_conf_mat, 3, 0, 1, 2)

        self._conf_matrix_text = QtWidgets.QPlainTextEdit()
        self._conf_matrix_text.setReadOnly(True)
        self._conf_matrix_text.setFont(QtGui.QFont("Courier New", 10))
        self._conf_matrix_text.setMaximumHeight(140)
        self._conf_matrix_text.setStyleSheet(
            f"background:#0d1117; color:#fff; border:1px solid {_C_BORDER};"
        )
        val_lay.addWidget(self._conf_matrix_text, 4, 0, 1, 2)
        lay.addWidget(val_grp)

        lay.addStretch()
        scroll.setWidget(w)
        o_lay.addWidget(scroll)
        return outer

    def _trait_statistiques(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        src_row = QtWidgets.QHBoxLayout()
        src_row.addWidget(_lbl("Couche :"))
        self._stat_layer = QgsMapLayerComboBox()
        self._stat_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        src_row.addWidget(self._stat_layer)
        self._btn_stats = QtWidgets.QPushButton("Calculer")
        self._btn_stats.setStyleSheet(_BTN_PRIMARY)
        self._btn_stats.clicked.connect(self._compute_stats)
        src_row.addWidget(self._btn_stats)
        lay.addLayout(src_row)
        self._stat_prog = QtWidgets.QProgressBar()
        self._stat_prog.setMaximumHeight(4)
        self._stat_prog.setTextVisible(False)
        self._stat_prog.hide()
        lay.addWidget(self._stat_prog)
        self._stat_table = QtWidgets.QTableWidget(0, 5)
        self._stat_table.setHorizontalHeaderLabels(["Bande","Minimum","Maximum","Moyenne","Écart-type"])
        self._stat_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self._stat_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._stat_table.setAlternatingRowColors(True)
        self._stat_table.itemSelectionChanged.connect(self._show_band_histogram)
        lay.addWidget(self._stat_table)
        histo_grp = _group("Histogramme — distribution approx.")
        h_inner = QtWidgets.QVBoxLayout(histo_grp)
        self._histo_box = QtWidgets.QTextEdit()
        self._histo_box.setReadOnly(True)
        self._histo_box.setMaximumHeight(110)
        self._histo_box.setFont(QtGui.QFont("Courier New", 10))
        self._histo_box.setStyleSheet(
            f"QTextEdit{{background:#0d1117;color:#3fb950;"
            f"border:1px solid {_C_BORDER};border-radius:5px;"
            f"font-family:'Courier New',monospace;font-size:10px;padding:4px;}}"
        )
        self._histo_box.setPlaceholderText("Sélectionnez une bande ci-dessus…")
        h_inner.addWidget(self._histo_box)
        lay.addWidget(histo_grp)
        return w

    # ═════════════════════════════════════════════════════════════════════
    # ONGLET 4 — EXPORT
    # ═════════════════════════════════════════════════════════════════════

    def _tab_export(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        sub = QtWidgets.QTabWidget()
        sub.addTab(self._exp_raster(), "GeoTIFF / PNG")
        sub.addTab(self._exp_csv(),    "Statistiques CSV")
        sub.addTab(self._exp_map(),    "Capture carte")
        sub.addTab(self._exp_report(), "Rapport texte")
        lay.addWidget(sub)
        return w

    def _exp_raster(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_lbl("Couche à exporter :"))
        self._exp_r_layer = QgsMapLayerComboBox()
        self._exp_r_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        lay.addWidget(self._exp_r_layer)
        lay.addWidget(_lbl("Format :"))
        self._exp_fmt = QtWidgets.QComboBox()
        self._exp_fmt.addItems(["GeoTIFF (.tif)", "PNG (.png)", "JPEG (.jpg)"])
        lay.addWidget(self._exp_fmt)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._exp_r_out = QtWidgets.QLineEdit()
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._exp_r_out))
        out_row.addWidget(self._exp_r_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_exp_raster = QtWidgets.QPushButton("⬇  Exporter le raster")
        self._btn_exp_raster.setStyleSheet(_BTN_PRIMARY)
        self._btn_exp_raster.clicked.connect(self._export_raster)
        lay.addWidget(self._btn_exp_raster)
        lay.addStretch()
        return w

    def _exp_csv(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_info("Exporte min/max/moyenne/écart-type par bande au format CSV."))
        lay.addWidget(_lbl("Couche :"))
        self._exp_csv_layer = QgsMapLayerComboBox()
        self._exp_csv_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        lay.addWidget(self._exp_csv_layer)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Fichier CSV :"))
        self._exp_csv_out = QtWidgets.QLineEdit()
        self._exp_csv_out.setPlaceholderText("statistiques.csv")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._exp_csv_out, "CSV (*.csv)"))
        out_row.addWidget(self._exp_csv_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_exp_csv = QtWidgets.QPushButton("Exporter les statistiques CSV")
        self._btn_exp_csv.setStyleSheet(_BTN_PRIMARY)
        self._btn_exp_csv.clicked.connect(self._export_csv)
        lay.addWidget(self._btn_exp_csv)
        lay.addStretch()
        return w

    def _exp_map(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_info("Capture le canvas QGIS actuel et l'enregistre en PNG."))
        sz_row = QtWidgets.QHBoxLayout()
        sz_row.addWidget(_lbl("Largeur (px) :"))
        self._map_w = QtWidgets.QSpinBox()
        self._map_w.setRange(200, 10000)
        self._map_w.setValue(1920)
        sz_row.addWidget(self._map_w)
        sz_row.addWidget(_lbl("Hauteur (px) :"))
        self._map_h = QtWidgets.QSpinBox()
        self._map_h.setRange(200, 10000)
        self._map_h.setValue(1080)
        sz_row.addWidget(self._map_h)
        sz_row.addStretch()
        lay.addLayout(sz_row)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Fichier PNG :"))
        self._map_out = QtWidgets.QLineEdit()
        self._map_out.setPlaceholderText("carte.png")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._map_out, "PNG (*.png)"))
        out_row.addWidget(self._map_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_exp_map = QtWidgets.QPushButton("📷  Capturer la carte")
        self._btn_exp_map.setStyleSheet(_BTN_PRIMARY)
        self._btn_exp_map.clicked.connect(self._export_map_png)
        lay.addWidget(self._btn_exp_map)
        lay.addStretch()
        return w

    def _exp_report(self):
        w   = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lay.addWidget(_info("Génère un rapport texte récapitulatif."))
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Fichier :"))
        self._report_out = QtWidgets.QLineEdit()
        self._report_out.setPlaceholderText("rapport_imgsat.txt")
        btn = QtWidgets.QPushButton("…")
        btn.setStyleSheet(_BTN_SMALL)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._browse_output(self._report_out, "Texte (*.txt)"))
        out_row.addWidget(self._report_out)
        out_row.addWidget(btn)
        lay.addLayout(out_row)
        self._btn_report = QtWidgets.QPushButton("📄  Générer le rapport")
        self._btn_report.setStyleSheet(_BTN_SUCCESS)
        self._btn_report.clicked.connect(self._generate_report)
        lay.addWidget(self._btn_report)
        self._report_preview = QtWidgets.QTextEdit()
        self._report_preview.setReadOnly(True)
        self._report_preview.setStyleSheet(
            f"QTextEdit{{background:{_C_BG};color:{_C_TEXT_SEC};"
            f"border:1px solid {_C_BORDER};border-radius:5px;"
            f"font-family:monospace;font-size:11px;}}"
        )
        lay.addWidget(self._report_preview)
        return w

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Copernicus
    # ═════════════════════════════════════════════════════════════════════

    def _cop_authenticate(self):
        user = self._cop_user.text().strip()
        pwd  = self._cop_pass.text().strip()
        if not user or not pwd:
            self._loaders["cop_auth"].flash()
            self._msg("Entrez vos identifiants Copernicus.", error=True)
            return
        self._loaders["cop_auth"].start()
        self._cop_auth_lbl.setText("● Connexion en cours…")
        self._cop_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_WARN};")
        self._msg("Authentification Copernicus en cours…")
        self._cop_auth_worker = CopernicusAuthWorker(user, pwd)
        self._cop_auth_worker.success.connect(self._cop_auth_success)
        self._cop_auth_worker.failure.connect(self._cop_auth_failure)
        self._cop_auth_worker.finished.connect(self._cop_auth_worker.deleteLater)
        self._cop_auth_worker.start()

    def _cop_auth_success(self, token):
        self.__class__._copernicus_token = token
        self._cop_auth_lbl.setText("● Connecté — token valide ~1 h")
        self._cop_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_SUCCESS};")
        self._msg("Authentification Copernicus réussie.")
        self._loaders["cop_auth"].stop()

    def _cop_auth_failure(self, error_msg):
        self._cop_auth_lbl.setText(f"● Échec : {error_msg}")
        self._cop_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_DANGER};")
        self._msg(f"Erreur Copernicus : {error_msg}", error=True)
        self._loaders["cop_auth"].stop()

    def _fill_cop_bbox(self):
        ext = self._get_project_bbox_wgs84()
        if ext:
            self._cop_bbox.setText(
                f"{ext.xMinimum():.4f},{ext.yMinimum():.4f},"
                f"{ext.xMaximum():.4f},{ext.yMaximum():.4f}"
            )
        else:
            self._msg("Aucune couche raster dans le projet.", error=True)

    def _cop_search(self):
        d_start = self._cop_d_start.date().toString("yyyy-MM-dd")
        d_end   = self._cop_d_end.date().toString("yyyy-MM-dd")
        cloud   = self._cop_cloud.value()
        coll    = self._cop_coll.currentText()

        name_f  = f"Collection/Name eq '{coll}'"
        date_f  = (
            f"ContentDate/Start gt {d_start}T00:00:00.000Z and "
            f"ContentDate/Start lt {d_end}T23:59:59.999Z"
        )
        cloud_f = (
            f"Attributes/OData.CSC.DoubleAttribute/any(att:"
            f"att/Name eq 'cloudCover' and "
            f"att/OData.CSC.DoubleAttribute/Value le {cloud}.00)"
        )

        geo_f = ""
        bbox_txt = self._cop_bbox.text().strip()
        if bbox_txt:
            try:
                xmin, ymin, xmax, ymax = [float(x) for x in bbox_txt.split(",")]
                wkt = (
                    f"SRID=4326;POLYGON(({xmin} {ymin},{xmax} {ymin},"
                    f"{xmax} {ymax},{xmin} {ymax},{xmin} {ymin}))"
                )
                geo_f = f" and OData.CSC.Intersects(area=geography'{wkt}')"
            except ValueError:
                self._msg("Emprise invalide — ignorée.", error=True)

        filt = f"{name_f} and {date_f} and {cloud_f}{geo_f}"

        import re

        def _encode_filter(f):
            parts = re.split(r"(geography'[^']*(?:'[^']*)*')", f)
            result = []
            for part in parts:
                if part.startswith("geography'"):
                    result.append(part.replace(" ", "%20"))
                else:
                    encoded = part.replace(" ", "%20").replace("(", "%28") \
                                .replace(")", "%29").replace(":", "%3A") \
                                .replace(",", "%2C").replace("=", "%3D")
                    result.append(encoded)
            return "".join(result)

        encoded_filter = _encode_filter(filt)
        url = (
            f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
            f"?$filter={encoded_filter}"
            f"&$orderby=ContentDate/Start%20desc&$top=20"
        )

        self._loaders["cop_search"].start()
        self._msg("Recherche Copernicus en cours…")
        self._cop_table.setRowCount(0)

        self._cop_search_worker = CopernicusSearchWorker(url, self._copernicus_token)
        self._cop_search_worker.success.connect(self._cop_search_done)
        self._cop_search_worker.failure.connect(self._cop_search_error)
        self._cop_search_worker.finished.connect(self._cop_search_worker.deleteLater)
        self._cop_search_worker.start()

    def _cop_search_done(self, products):
        self._loaders["cop_search"].stop()
        self._cop_table.setRowCount(0)
        for prod in products:
            r = self._cop_table.rowCount()
            self._cop_table.insertRow(r)
            name      = prod.get("Name", "")[:60]
            date      = prod.get("ContentDate", {}).get("Start", "")[:10]
            size_b    = prod.get("ContentLength", 0)
            size      = f"{size_b / 1e6:.1f} Mo" if size_b else "?"
            pid       = prod.get("Id", "")
            cloud_val = "?"
            for a in prod.get("Attributes", []):
                if a.get("Name") == "cloudCover":
                    cloud_val = f"{a.get('Value', '?'):.1f} %"
            self._cop_table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
            self._cop_table.setItem(r, 1, QtWidgets.QTableWidgetItem(date))
            self._cop_table.setItem(r, 2, _table_r(cloud_val))
            self._cop_table.setItem(r, 3, _table_r(size))
            self._cop_table.setItem(r, 4, QtWidgets.QTableWidgetItem(pid))
        n = len(products)
        if n > 0:
            self._msg(f"✓ {n} produit(s) trouvé(s). Sélectionnez-en un puis téléchargez.")
            self._cop_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_SUCCESS};font-style:italic;")
            self._cop_sel_lbl.setText(f"↑ {n} produit(s) — cliquez sur une ligne pour la sélectionner.")
        else:
            self._msg("Aucun produit trouvé pour ces critères.", error=True)
            self._cop_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_WARN};font-style:italic;")
            self._cop_sel_lbl.setText("Aucun résultat. Modifiez la période, l'emprise ou le % nuages.")

    def _cop_search_error(self, err):
        self._loaders["cop_search"].stop()
        self._msg(f"Erreur recherche : {err}", error=True)

    def _cop_on_selection(self):
        row = self._cop_table.currentRow()
        if row >= 0:
            name = self._cop_table.item(row, 0)
            size = self._cop_table.item(row, 3)
            nm   = name.text() if name else ""
            sz   = size.text() if size else ""
            self._cop_sel_lbl.setText(f"✓ Sélectionné : {nm}  ({sz})")
            self._cop_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_ACCENT};font-style:italic;")

    def _browse_cop_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier de téléchargement")
        if d: self._cop_dl_dir.setText(d)

    def _cop_download(self):
        row = self._cop_table.currentRow()
        if row < 0:
            self._loaders["cop_dl"].flash()
            self._msg("Sélectionnez un produit dans la liste.", error=True)
            return
        if not self._copernicus_token:
            self._loaders["cop_dl"].flash()
            self._msg("Connectez-vous d'abord via OAuth2.", error=True)
            return
        dest_dir = self._cop_dl_dir.text().strip()
        if not dest_dir:
            self._loaders["cop_dl"].flash()
            self._msg("Spécifiez un dossier de destination.", error=True)
            return
        pid  = self._cop_table.item(row, 4).text()
        pnam = self._cop_table.item(row, 0).text()
        url  = (
            f"https://catalogue.dataspace.copernicus.eu/odata/v1/"
            f"Products({pid})/$value"
        )
        dest   = os.path.join(dest_dir, pnam + ".zip")
        self._loaders["cop_dl"].start()
        worker = DownloadWorker(url, dest, {"Authorization": f"Bearer {self._copernicus_token}"})
        worker.progress.connect(self._cop_prog.setValue)
        worker.status.connect(self._cop_dl_lbl.setText)
        worker.finished.connect(self._cop_dl_done)
        self._download_workers.append(worker)
        self._cop_prog.setValue(0)
        worker.start()
        self._msg(f"Téléchargement démarré : {pnam}")

    def _cop_cancel(self):
        for w in self._download_workers: w.cancel()
        self._loaders["cop_dl"].stop()
        self._msg("Téléchargement annulé.")

    def _cop_dl_done(self, ok, path_or_err):
        self._loaders["cop_dl"].stop()
        if ok:
            self._cop_dl_lbl.setText(f"✓ Terminé : {os.path.basename(path_or_err)}")
            self._msg(f"Téléchargé : {os.path.basename(path_or_err)}")
        else:
            self._cop_dl_lbl.setText(f"✕ Erreur : {path_or_err}")
            self._msg(path_or_err, error=True)

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — USGS
    # ═════════════════════════════════════════════════════════════════════

    def _usgs_authenticate(self):
        user = self._usgs_user.text().strip()
        pwd  = self._usgs_pass.text().strip()
        if not user or not pwd:
            self._loaders["usgs_auth"].flash()
            self._msg("Entrez vos identifiants USGS.", error=True)
            return
        self._loaders["usgs_auth"].start()
        self._usgs_auth_lbl.setText("● Connexion en cours…")
        self._usgs_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_WARN};")
        self._msg("Authentification USGS en cours…")

        def _do():
            payload = json.dumps({"username": user, "password": pwd}).encode()
            req = Request(
                "https://m2m.cr.usgs.gov/api/api/json/stable/login",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            token = data.get("data", "")
            if token:
                return token
            raise Exception(data.get("errorMessage", "Réponse inattendue"))

        w = GenericWorker(_do)
        w.success.connect(self._usgs_auth_success)
        w.failure.connect(self._usgs_auth_failure)
        w.finished.connect(w.deleteLater)
        self._generic_workers.append(w)
        w.start()

    def _usgs_auth_success(self, token):
        self.__class__._usgs_token = token
        self._usgs_auth_lbl.setText("● Connecté — token M2M actif")
        self._usgs_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_SUCCESS};")
        self._msg("Authentification USGS réussie.")
        self._loaders["usgs_auth"].stop()

    def _usgs_auth_failure(self, err):
        self._usgs_auth_lbl.setText(f"● Échec : {err}")
        self._usgs_auth_lbl.setStyleSheet(f"font-size:11px;color:{_C_DANGER};")
        self._msg(err, error=True)
        self._loaders["usgs_auth"].stop()

    def _fill_usgs_bbox(self):
        ext = self._get_project_bbox_wgs84()
        if ext:
            self._usgs_bbox.setText(
                f"{ext.xMinimum():.4f},{ext.yMinimum():.4f},"
                f"{ext.xMaximum():.4f},{ext.yMaximum():.4f}"
            )

    def _usgs_search(self):
        if not self._usgs_token:
            self._loaders["usgs_search"].flash()
            self._msg("Connectez-vous d'abord à USGS.", error=True)
            return
        bbox_txt = self._usgs_bbox.text().strip()
        try:
            xmin, ymin, xmax, ymax = [float(x) for x in bbox_txt.split(",")]
        except Exception:
            xmin, ymin, xmax, ymax = -180, -90, 180, 90
        d_start = self._usgs_d_start.date().toString("yyyy-MM-dd")
        d_end   = self._usgs_d_end.date().toString("yyyy-MM-dd")
        payload = json.dumps({
            "datasetName": self._usgs_ds.currentText(),
            "maxResults": 20,
            "startingNumber": 1,
            "sceneFilter": {
                "spatialFilter": {
                    "filterType": "mbr",
                    "lowerLeft":  {"latitude": ymin, "longitude": xmin},
                    "upperRight": {"latitude": ymax, "longitude": xmax},
                },
                "acquisitionFilter": {"start": d_start, "end": d_end},
                "cloudCoverFilter": {"max": self._usgs_cloud.value(), "includeUnknown": False},
            }
        }).encode()
        token = self._usgs_token

        self._loaders["usgs_search"].start()
        self._msg("Recherche USGS en cours…")

        def _do():
            req = Request(
                "https://m2m.cr.usgs.gov/api/api/json/stable/scene-search",
                data=payload,
                headers={"Content-Type": "application/json", "X-Auth-Token": token}
            )
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return data.get("data", {}).get("results", [])

        w = GenericWorker(_do)
        w.success.connect(self._usgs_search_done)
        w.failure.connect(self._usgs_search_error)
        w.finished.connect(w.deleteLater)
        self._generic_workers.append(w)
        w.start()

    def _usgs_search_done(self, scenes):
        self._loaders["usgs_search"].stop()
        self._usgs_table.setRowCount(0)
        for sc in scenes:
            r    = self._usgs_table.rowCount()
            self._usgs_table.insertRow(r)
            name  = sc.get("displayId", sc.get("entityId", ""))
            date  = sc.get("temporalCoverage", {}).get("startDate", "")[:10]
            cloud = sc.get("cloudCover", "?")
            cs    = f"{cloud:.1f} %" if isinstance(cloud, (int, float)) else "?"
            eid   = sc.get("entityId", "")
            self._usgs_table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
            self._usgs_table.setItem(r, 1, QtWidgets.QTableWidgetItem(date))
            self._usgs_table.setItem(r, 2, _table_r(cs))
            self._usgs_table.setItem(r, 3, QtWidgets.QTableWidgetItem(eid))
        n = len(scenes)
        if n > 0:
            self._msg(f"✓ {n} scène(s) trouvée(s).")
            self._usgs_sel_lbl.setText(f"↑ {n} scène(s) — cliquez sur une ligne pour la sélectionner.")
            self._usgs_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_SUCCESS};font-style:italic;")
        else:
            self._msg("Aucune scène trouvée.", error=True)
            self._usgs_sel_lbl.setText("Aucun résultat. Modifiez les critères.")
            self._usgs_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_WARN};font-style:italic;")

    def _usgs_search_error(self, err):
        self._loaders["usgs_search"].stop()
        self._msg(f"Erreur USGS : {err}", error=True)

    def _usgs_on_selection(self):
        row = self._usgs_table.currentRow()
        if row >= 0:
            name = self._usgs_table.item(row, 0)
            nm   = name.text() if name else ""
            self._usgs_sel_lbl.setText(f"✓ Sélectionné : {nm}")
            self._usgs_sel_lbl.setStyleSheet(f"font-size:10px;color:{_C_ACCENT};font-style:italic;")

    def _browse_usgs_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier")
        if d: self._usgs_dl_dir.setText(d)

    def _usgs_download(self):
        row = self._usgs_table.currentRow()
        if row < 0:
            self._loaders["usgs_dl"].flash()
            self._msg("Sélectionnez une scène.", error=True)
            return
        if not self._usgs_token:
            self._loaders["usgs_dl"].flash()
            self._msg("Connectez-vous d'abord.", error=True)
            return
        dest_dir = self._usgs_dl_dir.text().strip()
        if not dest_dir:
            self._loaders["usgs_dl"].flash()
            self._msg("Spécifiez un dossier.", error=True)
            return
        eid     = self._usgs_table.item(row, 3).text()
        dataset = self._usgs_ds.currentText()
        token   = self._usgs_token
        self._loaders["usgs_dl"].start()

        def _do():
            payload = json.dumps({
                "datasetName": dataset,
                "entityIds": [eid],
                "products": ["STANDARD"]
            }).encode()
            req = Request(
                "https://m2m.cr.usgs.gov/api/api/json/stable/download-options",
                data=payload,
                headers={"Content-Type": "application/json", "X-Auth-Token": token}
            )
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            options = data.get("data", [])
            if not options:
                raise Exception("Aucune option de téléchargement disponible.")
            dl_url = options[0].get("url", "")
            if not dl_url:
                raise Exception("URL de téléchargement introuvable.")
            return dl_url

        w = GenericWorker(_do)
        w.success.connect(lambda url: self._usgs_start_dl(url, eid, dest_dir))
        w.failure.connect(lambda err: (self._loaders["usgs_dl"].stop(), self._msg(err, error=True)))
        w.finished.connect(w.deleteLater)
        self._generic_workers.append(w)
        w.start()
        self._msg(f"Récupération des options de téléchargement pour {eid}…")

    def _usgs_start_dl(self, dl_url, eid, dest_dir):
        dest   = os.path.join(dest_dir, f"{eid}.tar")
        worker = DownloadWorker(dl_url, dest, {"X-Auth-Token": self._usgs_token})
        worker.progress.connect(self._usgs_prog.setValue)
        worker.finished.connect(self._usgs_dl_done)
        self._download_workers.append(worker)
        worker.start()
        self._msg(f"Téléchargement USGS démarré : {eid}")

    def _usgs_dl_done(self, ok, path_or_err):
        self._loaders["usgs_dl"].stop()
        if ok:
            self._msg(f"Téléchargé : {os.path.basename(path_or_err)}")
        else:
            self._msg(path_or_err, error=True)

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Planificateur
    # ═════════════════════════════════════════════════════════════════════

    def _start_scheduler(self):
        self._scheduler = SchedulerWorker(self._scheduled_tasks)
        self._scheduler.trigger.connect(self._execute_scheduled_task)
        self._scheduler.start()

    def _add_scheduled_task(self):
        name = self._sch_name.text().strip()
        if not name:
            self._msg("Entrez un nom.", error=True)
            return
        dest = self._sch_dir.text().strip()
        if not dest:
            self._msg("Spécifiez un dossier.", error=True)
            return
        freq_map = {0: 6, 1: 24, 2: 24*7, 3: 24*30}
        freq_h   = freq_map.get(self._sch_freq.currentIndex(), 24)
        first_dt = self._sch_first.dateTime().toPyDateTime()
        task = {
            "name": name, "source": self._sch_src.currentText(),
            "freq_hours": freq_h, "cloud_max": self._sch_cloud.value(),
            "dest_dir": dest, "next_run": first_dt, "enabled": True,
        }
        self._scheduled_tasks.append(task)
        label = f"{name}  |  {self._sch_src.currentText()}  |  {self._sch_freq.currentText()}"
        self._sch_list.addItem(f"▶  {label}")
        self._msg(f"Tâche « {name} » planifiée.")

    def _remove_scheduled_task(self):
        row = self._sch_list.currentRow()
        if row < 0: return
        if 0 <= row < len(self._scheduled_tasks):
            name = self._scheduled_tasks.pop(row)["name"]
            self._sch_list.takeItem(row)
            self._msg(f"Tâche « {name} » supprimée.")

    def _toggle_scheduled_task(self):
        row = self._sch_list.currentRow()
        if row < 0 or row >= len(self._scheduled_tasks): return
        task = self._scheduled_tasks[row]
        task["enabled"] = not task.get("enabled", True)
        icon = "▶" if task["enabled"] else "⏸"
        item = self._sch_list.item(row)
        if item:
            item.setText(f"{icon}  {item.text()[2:]}")

    def _execute_scheduled_task(self, task):
        self._msg(f"Tâche déclenchée : « {task.get('name', '')} »")

    def _browse_sch_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if d: self._sch_dir.setText(d)

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Bandes / Inventaire
    # ═════════════════════════════════════════════════════════════════════

    def _refresh_bands(self):
        self._band_table.setRowCount(0)
        layers = self._raster_layers()
        for lyr in layers:
            r = self._band_table.rowCount()
            self._band_table.insertRow(r)
            self._band_table.setItem(r, 0, QtWidgets.QTableWidgetItem(lyr.name()))
            self._band_table.setItem(r, 1, _table_r(str(lyr.bandCount())))
            crs = lyr.crs().authid() if lyr.crs().isValid() else "?"
            self._band_table.setItem(r, 2, QtWidgets.QTableWidgetItem(crs))
            self._band_table.setItem(r, 3, QtWidgets.QTableWidgetItem(os.path.basename(lyr.source())))
        self._msg(f"{len(layers)} couche(s) raster chargée(s).")

    def _load_raster_file(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Ouvrir des fichiers raster", "",
            "Rasters (*.tif *.tiff *.img *.vrt *.nc *.jp2 *.png);;Tous (*)"
        )
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            lyr  = QgsRasterLayer(path, name)
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
            else:
                self._msg(f"Impossible de charger : {os.path.basename(path)}", error=True)
        self._refresh_bands()

    def _on_band_sel(self):
        row = self._band_table.currentRow()
        if row < 0: return
        item = self._band_table.item(row, 0)
        if not item: return
        lyrs = QgsProject.instance().mapLayersByName(item.text())
        if not lyrs: return
        lyr = lyrs[0]
        ext = lyr.extent()
        self._band_detail.setHtml(
            f"<b style='color:{_C_TEXT}'>{lyr.name()}</b><br>"
            f"<span style='color:{_C_TEXT_SEC}'>"
            f"Bandes : {lyr.bandCount()} &nbsp;|&nbsp; "
            f"Dimensions : {lyr.width()} × {lyr.height()} px &nbsp;|&nbsp; "
            f"Résolution : {lyr.rasterUnitsPerPixelX():.6g} × {lyr.rasterUnitsPerPixelY():.6g} u/px<br>"
            f"Emprise : ({ext.xMinimum():.4f}, {ext.yMinimum():.4f}) → ({ext.xMaximum():.4f}, {ext.yMaximum():.4f})"
            f"</span>"
        )

    # ── Composite RGB ──────────────────────────────────────────────────────

    def _rgb_layer_changed(self):
        lyr = self._rgb_layer.currentLayer()
        for c in (self._combo_r, self._combo_g, self._combo_b):
            c.clear()
        if lyr and isinstance(lyr, QgsRasterLayer):
            n = lyr.bandCount()
            for b in range(1, n + 1):
                for c in (self._combo_r, self._combo_g, self._combo_b):
                    c.addItem(f"Bande {b}", b)
            self._combo_r.setCurrentIndex(min(3, n) - 1)
            self._combo_g.setCurrentIndex(min(2, n) - 1)
            self._combo_b.setCurrentIndex(min(1, n) - 1)

    def _apply_preset_bands(self, bands):
        lyr = self._rgb_layer.currentLayer()
        if not lyr: return
        n = lyr.bandCount()
        for combo, val in zip((self._combo_r, self._combo_g, self._combo_b), bands):
            if val <= n:
                combo.setCurrentIndex(val - 1)

    def _apply_composite(self):
        lyr = self._rgb_layer.currentLayer()
        if not lyr:
            self._msg("Aucune couche.", error=True)
            return
        r = self._combo_r.currentData()
        g = self._combo_g.currentData()
        b = self._combo_b.currentData()
        if None in (r, g, b):
            self._msg("Sélectionnez les 3 canaux.", error=True)
            return
        renderer = QgsMultiBandColorRenderer(lyr.dataProvider(), r, g, b)
        for band, attr in [(r, "red"), (g, "green"), (b, "blue")]:
            stats = lyr.dataProvider().bandStatistics(band, QgsRasterBandStats.Min | QgsRasterBandStats.Max)
            ce    = QgsContrastEnhancement(lyr.dataProvider().dataType(band))
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            ce.setMinimumValue(stats.minimumValue)
            ce.setMaximumValue(stats.maximumValue)
            if attr == "red":    renderer.setRedContrastEnhancement(ce)
            elif attr == "green": renderer.setGreenContrastEnhancement(ce)
            else:                renderer.setBlueContrastEnhancement(ce)
        lyr.setRenderer(renderer)
        lyr.triggerRepaint()
        self._msg(f"Composite R={r} G={g} B={b} appliqué sur « {lyr.name()} ».")

    # ── Éditeur de formules ────────────────────────────────────────────────

    def _idx_layer_changed(self):
        self._band_formula_list.clear()
        lyr = self._idx_layer.currentLayer()
        if lyr and isinstance(lyr, QgsRasterLayer):
            s2_names = {
                1:"B1 – Aérosols côtiers", 2:"B2 – Bleu", 3:"B3 – Vert",
                4:"B4 – Rouge", 5:"B5 – Red Edge 1", 6:"B6 – Red Edge 2",
                7:"B7 – Red Edge 3", 8:"B8 – NIR", 9:"B8A – NIR étroit",
                10:"B9 – Vapeur d'eau", 11:"B10 – Cirrus",
                12:"B11 – SWIR 1", 13:"B12 – SWIR 2",
            }
            for b in range(1, lyr.bandCount() + 1):
                hint  = s2_names.get(b, "")
                label = f"b{b}@1"
                if hint: label += f"   ({hint})"
                item  = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, f"b{b}@1")
                self._band_formula_list.addItem(item)

    def _insert_band_ref(self, item):
        ref = item.data(QtCore.Qt.UserRole) or item.text().split()[0]
        cur = self._formula_edit.text()
        pos = self._formula_edit.cursorPosition()
        self._formula_edit.setText(cur[:pos] + ref + cur[pos:])
        self._formula_edit.setCursorPosition(pos + len(ref))
        self._formula_edit.setFocus()

    def _insert_op(self, op):
        op_map  = {"−": "-", "×": "*", "÷": "/"}
        real_op = op_map.get(op, op)
        cur     = self._formula_edit.text()
        pos     = self._formula_edit.cursorPosition()
        self._formula_edit.setText(cur[:pos] + real_op + cur[pos:])
        self._formula_edit.setCursorPosition(pos + len(real_op))
        self._formula_edit.setFocus()

    def _load_preset_formula(self, key):
        lyr = self._idx_layer.currentLayer()
        n   = lyr.bandCount() if lyr else 13
        if n >= 13:
            nir, red, grn, swir, blue = "b8@1", "b4@1", "b3@1", "b11@1", "b2@1"
        elif n >= 7:
            nir, red, grn, swir, blue = "b5@1", "b4@1", "b3@1", "b6@1", "b2@1"
        else:
            nir, red, grn, swir, blue = "b4@1", "b3@1", "b2@1", "b5@1", "b1@1"
        formulas = {
            "ndvi": f"({nir} - {red}) / ({nir} + {red} + 0.0001)",
            "ndwi": f"({grn} - {nir}) / ({grn} + {nir} + 0.0001)",
            "ndbi": f"({swir} - {nir}) / ({swir} + {nir} + 0.0001)",
            "evi":  f"2.5 * ({nir} - {red}) / ({nir} + 6 * {red} - 7.5 * {blue} + 1 + 0.0001)",
            "norm": f"(b1@1 - min_val) / (max_val - min_val)",
        }
        self._formula_edit.setText(formulas.get(key, ""))
        self._formula_edit.setFocus()

    def _compute_custom_formula(self):
        if not HAS_RASTER_CALC:
            self._msg("QgsRasterCalculator non disponible.", error=True)
            return
        lyr     = self._idx_layer.currentLayer()
        formula = self._formula_edit.text().strip()
        out     = self._idx_out.text().strip()
        if not lyr:
            self._loaders["calc"].flash()
            self._msg("Aucune couche source.", error=True)
            return
        if not formula:
            self._loaders["calc"].flash()
            self._msg("La formule est vide.", error=True)
            return
        if not out:
            self._loaders["calc"].flash()
            self._msg("Spécifiez un fichier de sortie.", error=True)
            return
        self._loaders["calc"].start()
        entries = []
        for b in range(1, lyr.bandCount() + 1):
            ref = f"b{b}@1"
            if ref in formula:
                e           = QgsRasterCalculatorEntry()
                e.ref       = ref
                e.raster    = lyr
                e.bandNumber = b
                entries.append(e)
        if not entries:
            self._loaders["calc"].stop()
            self._msg("Aucune référence bN@1 trouvée dans la formule.", error=True)
            return
        calc = QgsRasterCalculator(formula, out, "GTiff", lyr.extent(), lyr.width(), lyr.height(), entries)
        code = calc.processCalculation()
        self._loaders["calc"].stop()
        if code == 0:
            result = QgsRasterLayer(out, f"Result_{lyr.name()}")
            if result.isValid():
                self._apply_ndvi_colormap(result)
                QgsProject.instance().addMapLayer(result)
                self._formula_result.setText(f"✓ Calcul terminé. Couche « {result.name()} » ajoutée.")
                self._formula_result.show()
                self._msg("Calcul terminé avec succès.")
        else:
            self._msg(f"Erreur calcul (code {code}). Vérifiez la formule.", error=True)

    def _apply_ndvi_colormap(self, lyr):
        color_ramp = QgsColorRampShader()
        color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
        color_ramp.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(-1.0, QtGui.QColor(100, 100, 100), "-1"),
            QgsColorRampShader.ColorRampItem( 0.0, QtGui.QColor(210, 180, 140), "0"),
            QgsColorRampShader.ColorRampItem( 0.2, QtGui.QColor(255, 255,   0), "0.2"),
            QgsColorRampShader.ColorRampItem( 0.5, QtGui.QColor( 34, 139,  34), "0.5"),
            QgsColorRampShader.ColorRampItem( 1.0, QtGui.QColor(  0,  80,   0), "1"),
        ])
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(color_ramp)
        renderer = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, raster_shader)
        lyr.setRenderer(renderer)

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Prétraitement
    # ═════════════════════════════════════════════════════════════════════

    def _apply_dos1(self):
        lyr = self._pre_layer.currentLayer()
        out = self._dos1_out.text().strip()
        if not lyr:
            self._loaders["dos1"].flash()
            self._msg("Aucune couche source.", error=True)
            return
        if not HAS_RASTER_CALC:
            self._loaders["dos1"].flash()
            self._msg("QgsRasterCalculator requis.", error=True)
            return
        if not out:
            self._loaders["dos1"].flash()
            self._msg("Spécifiez un fichier de sortie.", error=True)
            return
        self._loaders["dos1"].start()
        try:
            entries = []
            for b in range(1, lyr.bandCount() + 1):
                e = QgsRasterCalculatorEntry()
                e.ref = f"b{b}@1"
                e.raster = lyr
                e.bandNumber = b
                entries.append(e)
            vmin = (
                lyr.dataProvider().bandStatistics(1, QgsRasterBandStats.Min).minimumValue
                if self._dos1_auto.isChecked() else self._dos1_min.value()
            )
            formula = f"(b1@1 - {vmin}) * (b1@1 > {vmin})"
            calc    = QgsRasterCalculator(formula, out, "GTiff", lyr.extent(), lyr.width(), lyr.height(), [entries[0]])
            if calc.processCalculation() == 0:
                r = QgsRasterLayer(out, f"DOS1_{lyr.name()}")
                if r.isValid():
                    QgsProject.instance().addMapLayer(r)
                    self._msg(f"DOS1 appliqué → « {r.name()} ».")
                else:
                    self._msg("DOS1 calculé mais la couche résultante est invalide.", error=True)
            else:
                self._msg("Erreur DOS1.", error=True)
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["dos1"].stop()

    def _apply_clip(self):
        lyr  = self._pre_layer.currentLayer()
        clip = self._clip_layer.currentLayer()
        out  = self._clip_out.text().strip()
        if not lyr or not clip or not out:
            self._loaders["clip"].flash()
            self._msg("Couche source, clip et sortie requis.", error=True)
            return
        if not HAS_PROCESSING:
            self._loaders["clip"].flash()
            self._msg("Module 'processing' requis.", error=True)
            return
        self._loaders["clip"].start()
        try:
            processing.run("gdal:cliprasterbymasklayer", {
                "INPUT": lyr, "MASK": clip, "NODATA": -9999,
                "ALPHA_BAND": False, "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True, "OUTPUT": out
            })
            r = QgsRasterLayer(out, f"Clip_{lyr.name()}")
            if r.isValid():
                QgsProject.instance().addMapLayer(r)
                self._msg(f"Découpe terminée → « {r.name()} ».")
            else:
                self._msg("Découpe effectuée mais la couche résultante est invalide.", error=True)
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["clip"].stop()

    def _apply_reproject(self):
        lyr     = self._pre_layer.currentLayer()
        crs_txt = self._reproj_crs.text().strip()
        out     = self._reproj_out.text().strip()
        if not lyr or not crs_txt or not out:
            self._loaders["reproj"].flash()
            self._msg("Couche, CRS et sortie requis.", error=True)
            return
        if not HAS_PROCESSING:
            self._loaders["reproj"].flash()
            self._msg("Module 'processing' requis.", error=True)
            return
        self._loaders["reproj"].start()
        try:
            target_crs = QgsCoordinateReferenceSystem(crs_txt)
            if not target_crs.isValid():
                self._msg(f"CRS invalide : « {crs_txt} ».", error=True)
                return
            processing.run("gdal:warpreproject", {
                "INPUT": lyr, "SOURCE_CRS": lyr.crs(),
                "TARGET_CRS": target_crs,
                "RESAMPLING": 0, "NODATA": None, "TARGET_RESOLUTION": None, "OUTPUT": out
            })
            r = QgsRasterLayer(out, f"Reproj_{lyr.name()}")
            if r.isValid():
                QgsProject.instance().addMapLayer(r)
                self._msg(f"Reprojection vers {crs_txt} terminée.")
            else:
                self._msg("Reprojection effectuée mais la couche résultante est invalide.", error=True)
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["reproj"].stop()

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Classification
    # ═════════════════════════════════════════════════════════════════════

    def _add_class(self):
        name = self._class_name.text().strip()
        lyr  = self._clf_layer.currentLayer()
        roi  = self._clf_roi.currentLayer()
        print(f"DEBUG: name='{name}' | raster={lyr} | roi={roi}")


        if not name:
            self._loaders["clf_add"].flash()
            self._msg("Entrez un nom de classe.", error=True)
            return
        if not lyr or not isinstance(lyr, QgsRasterLayer):
            self._loaders["clf_add"].flash()
            self._msg("Sélectionnez une couche raster.", error=True)
            return
        if not roi or not isinstance(roi, QgsVectorLayer):
            self._loaders["clf_add"].flash()
            self._msg("Sélectionnez une couche ROI (vecteur).", error=True)
            return

        self._loaders["clf_add"].start()
        try:
            sigs = self._extract_signatures(lyr, roi)
            if not sigs:
                self._msg("Aucun pixel extrait. Vérifiez que la couche ROI superpose le raster.", error=True)
                return

            cid   = len(self._roi_signatures) + 1
            color = self._class_color_btn.color()

            self._roi_signatures[cid] = {
                "name": name, "color": color, "signatures": sigs,
            }

            item = QtWidgets.QListWidgetItem(f"  {cid}. {name}  ({len(sigs)} px)")
            px   = QtGui.QPixmap(12, 12)
            px.fill(color)
            item.setIcon(QtGui.QIcon(px))
            self._class_list.addItem(item)

            self._msg(f"✓ Classe « {name} » ajoutée ({len(sigs)} px).")
            self._class_name.clear()
        except Exception as e:
            self._msg(f"Erreur : {str(e)}", error=True)
        finally:
            self._loaders["clf_add"].stop()

    def _extract_signatures(self, raster_lyr, vector_lyr):
        from qgis.core import QgsCoordinateTransform, QgsProject

        provider = raster_lyr.dataProvider()
        n_bands  = raster_lyr.bandCount()
        ext      = raster_lyr.extent()
        w, h     = raster_lyr.width(), raster_lyr.height()
        px_w     = ext.width()  / w
        px_h     = ext.height() / h

        # Reprojection automatique si CRS différents
        need_transform = raster_lyr.crs() != vector_lyr.crs()
        transform = None
        if need_transform:
            transform = QgsCoordinateTransform(
                vector_lyr.crs(),
                raster_lyr.crs(),
                QgsProject.instance()
            )

        # Charge toutes les bandes en mémoire une seule fois
        band_blocks = []
        for b in range(1, n_bands + 1):
            band_blocks.append(provider.block(b, ext, w, h))

        sigs = []
        for feat in vector_lyr.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            # Reprojette la géométrie dans le CRS du raster
            if need_transform and transform:
                geom = QgsGeometry(geom)
                try:
                    geom.transform(transform)
                except Exception:
                    continue

            fb = geom.boundingBox()

            # Ignore si hors emprise raster
            if not ext.intersects(fb):
                continue

            c0 = max(0, int((fb.xMinimum() - ext.xMinimum()) / px_w))
            c1 = min(w - 1, int((fb.xMaximum() - ext.xMinimum()) / px_w))
            r0 = max(0, int((ext.yMaximum() - fb.yMaximum()) / px_h))
            r1 = min(h - 1, int((ext.yMaximum() - fb.yMinimum()) / px_h))

            for row in range(r0, r1 + 1):
                for col in range(c0, c1 + 1):
                    x  = ext.xMinimum() + (col + 0.5) * px_w
                    y  = ext.yMaximum() - (row + 0.5) * px_h
                    pt = QgsPointXY(x, y)

                    if not geom.contains(QgsGeometry.fromPointXY(pt)):
                        continue

                    vals  = []
                    valid = True
                    for b in range(n_bands):
                        v = band_blocks[b].value(row, col)
                        if band_blocks[b].isNoData(row, col):
                            valid = False
                            break
                        vals.append(float(v))

                    if valid and vals:
                        sigs.append(tuple(vals))

        return sigs

    def _clear_classes(self):
        self._roi_signatures.clear()
        self._class_list.clear()
        self._msg("Classes effacées.")

    def _run_classification(self):
        lyr = self._clf_layer.currentLayer()
        out = self._clf_out.text().strip()
        if not self._roi_signatures:
            self._loaders["clf_run"].flash()
            self._msg("Définissez au moins une classe avant de lancer.", error=True)
            return
        if not lyr:
            self._loaders["clf_run"].flash()
            self._msg("Aucune couche raster sélectionnée.", error=True)
            return
        if not out:
            self._loaders["clf_run"].flash()
            self._msg("Spécifiez un fichier de sortie.", error=True)
            return

        # ── Loader démarre ici — bloquera le bouton pendant tout le calcul ──
        self._loaders["clf_run"].start()
        self._clf_prog.setMaximum(lyr.height())
        self._clf_prog.setValue(0)
        self._clf_prog.show()
        self._msg("Classification en cours…")
        QtWidgets.QApplication.processEvents()

        try:
            centroids = {
                cid: tuple(
                    sum(s[b] for s in info["signatures"]) / len(info["signatures"])
                    for b in range(len(info["signatures"][0]))
                )
                for cid, info in self._roi_signatures.items()
                if info["signatures"]
            }
            nb       = lyr.bandCount()
            w, h     = lyr.width(), lyr.height()
            ext      = lyr.extent()
            provider = lyr.dataProvider()
            band_blocks = []
            for b in range(1, nb+1):
                block = provider.block(b, ext, w, h)
                rows  = [[block.value(r, c) for c in range(w)] for r in range(h)]
                band_blocks.append(rows)
            alg  = self._alg_combo.currentIndex()
            grid = [[0]*w for _ in range(h)]
            for row in range(h):
                for col in range(w):
                    pixel             = tuple(band_blocks[b][row][col] for b in range(nb))
                    best_cls, best_sc = 0, float('inf')
                    for cid, centroid in centroids.items():
                        if alg == 0:
                            sc = math.sqrt(sum((pixel[b]-centroid[b])**2 for b in range(nb)))
                        else:
                            np_ = math.sqrt(sum(v**2 for v in pixel))
                            nc  = math.sqrt(sum(v**2 for v in centroid))
                            if np_ < 1e-9 or nc < 1e-9:
                                sc = float('inf')
                            else:
                                dot = sum(pixel[b]*centroid[b] for b in range(nb))
                                cos = max(-1.0, min(1.0, dot/(np_*nc)))
                                sc  = math.acos(cos)
                        if sc < best_sc:
                            best_sc, best_cls = sc, cid
                    grid[row][col] = best_cls
                if row % 20 == 0:
                    self._clf_prog.setValue(row)
                    QtWidgets.QApplication.processEvents()

            self._clf_prog.hide()
            self._write_clf_result(lyr, grid, out)
            self._msg("✓ Classification terminée et ajoutée au projet QGIS.")
        except Exception as e:
            self._clf_prog.hide()
            self._msg(str(e), error=True)
        finally:
            # ── Loader s'arrête toujours, même en cas d'erreur ──
            self._loaders["clf_run"].stop()

    def _write_clf_result(self, src_lyr, grid, out_path):
        """
        Écrit le grid de classification dans un GeoTIFF via gdal (subprocess),
        puis applique une palette de couleurs et ajoute la couche au projet.
        """
        try:
            from osgeo import gdal, osr
        except ImportError:
            self._msg("GDAL Python (osgeo) requis pour écrire le résultat.", error=True)
            return

        h        = src_lyr.height()
        w        = src_lyr.width()
        ext      = src_lyr.extent()
        crs_wkt  = src_lyr.crs().toWkt()

        driver   = gdal.GetDriverByName("GTiff")
        ds       = driver.Create(out_path, w, h, 1, gdal.GDT_Byte)
        if ds is None:
            self._msg(f"Impossible de créer le fichier : {out_path}", error=True)
            return

        # Géoréférencement
        ds.SetGeoTransform([
            ext.xMinimum(), ext.width() / w, 0,
            ext.yMaximum(), 0, -(ext.height() / h)
        ])
        srs = osr.SpatialReference()
        srs.ImportFromWkt(crs_wkt)
        ds.SetProjection(srs.ExportToWkt())

        # Écriture ligne par ligne
        import array
        band_out = ds.GetRasterBand(1)
        for row in range(h):
            line = array.array('B', [grid[row][col] for col in range(w)])
            band_out.WriteArray(__import__('numpy').array(line).reshape(1, w), 0, row)

        band_out.SetNoDataValue(0)
        band_out.FlushCache()
        ds = None  # ferme le fichier

        # Charge et stylise la couche
        lyr = QgsRasterLayer(out_path, f"Classif_{len(self._roi_signatures)}cl")
        if not lyr.isValid():
            self._msg("Le raster de classification généré est invalide.", error=True)
            return

        color_ramp = QgsColorRampShader()
        color_ramp.setColorRampType(QgsColorRampShader.Exact)
        color_ramp.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(cid, info["color"], info["name"])
            for cid, info in self._roi_signatures.items()
        ])
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(color_ramp)
        renderer = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, raster_shader)
        lyr.setRenderer(renderer)
        QgsProject.instance().addMapLayer(lyr)

    def _compute_confusion_matrix(self):
        clf_lyr = self._val_clf_layer.currentLayer()
        ref_lyr = self._val_ref_layer.currentLayer()
        field   = self._val_field.text().strip()

        if not clf_lyr:
            self._loaders["clf_matrix"].flash()
            self._msg("Sélectionnez la couche classifiée (raster).", error=True)
            return
        if not ref_lyr:
            self._loaders["clf_matrix"].flash()
            self._msg("Sélectionnez la couche de vérité terrain (vecteur).", error=True)
            return
        if not field:
            self._loaders["clf_matrix"].flash()
            self._msg("Indiquez le nom du champ contenant le nom de classe.", error=True)
            return
        if not self._roi_signatures:
            self._loaders["clf_matrix"].flash()
            self._msg("Aucune classe définie. Ajoutez des classes d'entraînement.", error=True)
            return

        classes = sorted(self._roi_signatures.keys())
        self._loaders["clf_matrix"].start()
        try:
            if field not in ref_lyr.fields().names():
                self._msg(
                    f"Le champ « {field} » n'existe pas. "
                    f"Champs disponibles : {', '.join(ref_lyr.fields().names())}",
                    error=True
                )
                return

            matrix   = {ci: {cj: 0 for cj in classes} for ci in classes}
            total    = 0
            provider = clf_lyr.dataProvider()

            for feat in ref_lyr.getFeatures():
                ref_cls = str(feat[field])
                ref_id  = next(
                    (cid for cid, info in self._roi_signatures.items()
                     if info["name"].lower() == ref_cls.lower()), None
                )
                if ref_id is None:
                    continue
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                fb = geom.boundingBox()
                cx = (fb.xMinimum() + fb.xMaximum()) / 2
                cy = (fb.yMinimum() + fb.yMaximum()) / 2
                ident = provider.identify(QgsPointXY(cx, cy), QgsRaster.IdentifyFormatValue)
                if not ident.isValid():
                    continue
                results = ident.results()
                if 1 not in results or results[1] is None:
                    continue
                pred_id = int(results[1])
                if pred_id in matrix.get(ref_id, {}):
                    matrix[ref_id][pred_id] += 1
                    total += 1

            if total == 0:
                self._conf_matrix_text.setPlainText(
                    "Aucun pixel apparié.\n\n"
                    "Vérifiez que :\n"
                    f"  • le champ « {field} » contient des noms identiques à ceux saisis\n"
                    "  • la couche de référence superpose la couche classifiée"
                )
                self._msg("Aucun pixel apparié — voir le détail ci-dessous.", error=True)
                return

            names  = [self._roi_signatures[cid]["name"][:8] for cid in classes]
            col_w  = max(max(len(nm) for nm in names), 5) + 2
            header = " " * col_w + "".join(f"{nm:>{col_w}}" for nm in names)
            lines  = [header, "─" * len(header)]
            correct = 0
            for ci in classes:
                cells = [f"{self._roi_signatures[ci]['name'][:col_w]:<{col_w}}"]
                for cj in classes:
                    v = matrix[ci][cj]
                    if ci == cj: correct += v
                    cells.append(f"{v:>{col_w}}")
                lines.append("".join(cells))
            acc = correct / total * 100
            lines += ["", f"Précision globale : {acc:.1f}%  ({correct}/{total} px)"]
            self._conf_matrix_text.setPlainText("\n".join(lines))
            self._msg(f"✓ Matrice calculée — précision globale : {acc:.1f}%.")
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["clf_matrix"].stop()

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Statistiques
    # ═════════════════════════════════════════════════════════════════════

    def _compute_stats(self):
        lyr = self._stat_layer.currentLayer()
        if not lyr:
            self._loaders["stats"].flash()
            self._msg("Aucune couche.", error=True)
            return
        n = lyr.bandCount()
        self._stat_table.setRowCount(0)
        self._stat_data = []
        self._stat_prog.setMaximum(n)
        self._stat_prog.setValue(0)
        self._stat_prog.show()
        self._loaders["stats"].start()
        try:
            for band in range(1, n+1):
                stats = lyr.dataProvider().bandStatistics(
                    band,
                    QgsRasterBandStats.Min | QgsRasterBandStats.Max
                    | QgsRasterBandStats.Mean | QgsRasterBandStats.StdDev,
                )
                r = self._stat_table.rowCount()
                self._stat_table.insertRow(r)
                self._stat_table.setItem(r, 0, QtWidgets.QTableWidgetItem(f"Bande {band}"))
                for col, val in enumerate([stats.minimumValue, stats.maximumValue, stats.mean, stats.stdDev], 1):
                    self._stat_table.setItem(r, col, _table_r(f"{val:.4f}"))
                self._stat_data.append({
                    "band": band, "min": stats.minimumValue,
                    "max": stats.maximumValue, "mean": stats.mean, "std": stats.stdDev,
                })
                self._stat_prog.setValue(band)
                QtWidgets.QApplication.processEvents()
        finally:
            self._stat_prog.hide()
            self._loaders["stats"].stop()
        self._msg(f"Statistiques — {n} bande(s) pour « {lyr.name()} ».")

    def _show_band_histogram(self):
        row = self._stat_table.currentRow()
        if row < 0 or row >= len(self._stat_data): return
        s        = self._stat_data[row]
        mean, std = s["mean"], s["std"]
        cols     = 30
        max_h    = 8
        vmin_h   = mean - 3*std
        vmax_h   = mean + 3*std
        step     = (vmax_h - vmin_h) / cols if (vmax_h - vmin_h) > 0 else 1
        bars     = []
        for i in range(cols):
            x = vmin_h + (i+0.5) * step
            z = (x - mean) / (std + 1e-9)
            bars.append(max(0, int(max_h * math.exp(-0.5 * z**2))))
        lines = []
        for h in range(max_h, 0, -1):
            line = "".join("█" if b >= h else " " for b in bars)
            lines.append(f"│{line}│")
        lines.append("└" + "─"*cols + "┘")
        lines.append(f"  {vmin_h:.2f}{'':>10}{mean:.2f}{'':>10}{vmax_h:.2f}")
        self._histo_box.setPlainText(
            f"Bande {s['band']}  ·  moy={mean:.3f}  std={std:.3f}\n" + "\n".join(lines)
        )

    # ═════════════════════════════════════════════════════════════════════
    # LOGIQUE — Export
    # ═════════════════════════════════════════════════════════════════════

    def _export_raster(self):
        lyr = self._exp_r_layer.currentLayer()
        out = self._exp_r_out.text().strip()
        if not lyr or not out:
            self._loaders["exp_raster"].flash()
            self._msg("Couche et sortie requis.", error=True)
            return
        if not HAS_PROCESSING:
            self._loaders["exp_raster"].flash()
            self._msg("Module 'processing' requis.", error=True)
            return
        self._loaders["exp_raster"].start()
        try:
            processing.run("gdal:translate", {
                "INPUT": lyr, "TARGET_CRS": None, "NODATA": None,
                "COPY_SUBDATASETS": False, "OPTIONS": "", "EXTRA": "",
                "DATA_TYPE": 0, "OUTPUT": out
            })
            self._msg(f"Raster exporté : {os.path.basename(out)}")
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["exp_raster"].stop()

    def _export_csv(self):
        lyr = self._exp_csv_layer.currentLayer()
        out = self._exp_csv_out.text().strip()
        if not lyr or not out:
            self._loaders["exp_csv"].flash()
            self._msg("Couche et sortie requis.", error=True)
            return
        self._loaders["exp_csv"].start()
        try:
            lines = ["Bande,Minimum,Maximum,Moyenne,Ecart-type,Source"]
            for b in range(1, lyr.bandCount()+1):
                s = lyr.dataProvider().bandStatistics(
                    b,
                    QgsRasterBandStats.Min | QgsRasterBandStats.Max
                    | QgsRasterBandStats.Mean | QgsRasterBandStats.StdDev,
                )
                lines.append(
                    f"Bande {b},{s.minimumValue:.6f},{s.maximumValue:.6f},"
                    f"{s.mean:.6f},{s.stdDev:.6f},{lyr.name()}"
                )
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._msg(f"CSV exporté : {os.path.basename(out)}")
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["exp_csv"].stop()

    def _export_map_png(self):
        out = self._map_out.text().strip()
        if not out:
            self._loaders["exp_map"].flash()
            self._msg("Spécifiez un fichier PNG.", error=True)
            return
        self._loaders["exp_map"].start()
        try:
            canvas = None
            try:
                from qgis.utils import iface
                canvas = iface.mapCanvas()
            except Exception:
                pass
            if canvas is None:
                self._msg("Canvas QGIS non accessible.", error=True)
                return
            img = QtGui.QImage(self._map_w.value(), self._map_h.value(), QtGui.QImage.Format_ARGB32)
            img.fill(QtGui.QColor("white"))
            p = QtGui.QPainter(img)
            canvas.render(p)
            p.end()
            img.save(out, "PNG")
            self._msg(f"Carte exportée : {os.path.basename(out)}")
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["exp_map"].stop()

    def _generate_report(self):
        out = self._report_out.text().strip()
        if not out:
            self._loaders["report"].flash()
            self._msg("Spécifiez un fichier.", error=True)
            return
        self._loaders["report"].start()
        try:
            ts    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = [
                "═" * 62,
                "  RAPPORT ImgSat — Analyse d'images satellitaires",
                f"  Généré le : {ts}",
                "═" * 62, "",
                "COUCHES RASTER", "─" * 40,
            ]
            for lyr in self._raster_layers():
                lines += [
                    f"• {lyr.name()}",
                    f"  Source  : {lyr.source()}",
                    f"  Bandes  : {lyr.bandCount()}  |  CRS : {lyr.crs().authid()}",
                    f"  Taille  : {lyr.width()} × {lyr.height()} px", "",
                ]
            lines += ["", "CLASSES DE CLASSIFICATION", "─" * 40]
            if self._roi_signatures:
                for cid, info in self._roi_signatures.items():
                    lines.append(f"  {cid}. {info['name']}  — {len(info['signatures'])} px d'entraînement")
            else:
                lines.append("  Aucune classe.")
            lines += ["", "TÂCHES PLANIFIÉES", "─" * 40]
            if self._scheduled_tasks:
                for t in self._scheduled_tasks:
                    st = "Actif" if t.get("enabled") else "Pause"
                    lines.append(f"  • {t['name']}  [{st}]  — {t['source']} — toutes les {t['freq_hours']} h")
            else:
                lines.append("  Aucune tâche.")
            lines += ["", "═" * 62, "Fin du rapport ImgSat", "═" * 62]
            report = "\n".join(lines)
            with open(out, "w", encoding="utf-8") as f:
                f.write(report)
            self._report_preview.setPlainText(report)
            self._msg(f"Rapport généré : {os.path.basename(out)}")
        except Exception as e:
            self._msg(str(e), error=True)
        finally:
            self._loaders["report"].stop()

    # ═════════════════════════════════════════════════════════════════════
    # UTILITAIRES
    # ═════════════════════════════════════════════════════════════════════

    def _raster_layers(self):
        return [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsRasterLayer) and lyr.isValid()
        ]

    def _msg(self, text, error=False):
        color  = _C_DANGER if error else _C_SUCCESS
        prefix = "✕" if error else "✓"
        self._status_lbl.setStyleSheet(f"font-size:11px;padding:2px 8px;color:{color};")
        self._status_lbl.setText(f"{prefix}  {text}")

    def _browse_output(self, line_edit, filetype="GeoTIFF (*.tif)"):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Fichier de sortie", "", filetype)
        if path:
            ext_map = {
                "GeoTIFF (*.tif)": ".tif", "CSV (*.csv)": ".csv",
                "PNG (*.png)": ".png",      "Texte (*.txt)": ".txt",
            }
            ext = ext_map.get(filetype, "")
            if ext and not path.lower().endswith(ext):
                path += ext
            line_edit.setText(path)

    def _get_project_bbox_wgs84(self):
        project = QgsProject.instance()
        dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        ext     = None
        for lyr in project.mapLayers().values():
            if not isinstance(lyr, QgsRasterLayer) or not lyr.isValid(): continue
            lext    = lyr.extent()
            src_crs = lyr.crs()
            if src_crs.isValid() and src_crs != dst_crs:
                try:
                    lext = QgsCoordinateTransform(src_crs, dst_crs, project).transformBoundingBox(lext)
                except Exception:
                    pass
            ext = lext if ext is None else ext.combineExtentWith(lext) or ext
        return ext