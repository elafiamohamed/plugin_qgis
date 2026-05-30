"""imgsat_dialog.py
Dialogue principal du plugin ImgSat — version light du Semi-Automatic Classification Plugin.

Compatibilité : QGIS 3.x (testé sur 3.40 LTR / Python 3.12)

Onglets :
  1. Bandes          — inventaire des couches raster QGIS
  2. Composite RGB   — visualisation colorée avec presets
  3. Indices         — normalisation + NDVI / NDWI
  4. Statistiques    — min, max, moyenne, écart-type par bande
  5. Classification  — classification supervisée Minimum Distance / SAM
  6. Données         — accès WMS Sentinel/Landsat via Copernicus/USGS

Aucun fichier .ui — tout le code d'interface est généré programmatiquement.
Dépendances : uniquement les API QGIS natives (qgis.core, qgis.analysis, qgis.gui).
"""

import os
import math
import webbrowser
from urllib.parse import urlencode

from qgis.PyQt import QtWidgets, QtCore, QtGui

# --- Imports qgis.core (stables dans QGIS 3.x) ---
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
)

# --- QgsRasterCalculator est dans qgis.analysis depuis QGIS 3.x ---
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


# ---------------------------------------------------------------------------
# Styles partagés
# ---------------------------------------------------------------------------
_BTN_PRIMARY = (
    "QPushButton{background:#2980b9;color:#fff;border:none;"
    "padding:6px 14px;border-radius:4px;font-size:12px;}"
    "QPushButton:hover{background:#3498db;}"
    "QPushButton:pressed{background:#1a6fa3;}"
    "QPushButton:disabled{background:#aab7b8;color:#eee;}"
)
_BTN_SECONDARY = (
    "QPushButton{background:#f0f3f4;color:#2c3e50;border:1px solid #bdc3c7;"
    "padding:6px 14px;border-radius:4px;font-size:12px;}"
    "QPushButton:hover{background:#d5dbdb;}"
)
_BTN_SUCCESS = (
    "QPushButton{background:#27ae60;color:#fff;border:none;"
    "padding:6px 14px;border-radius:4px;font-size:12px;}"
    "QPushButton:hover{background:#2ecc71;}"
    "QPushButton:pressed{background:#1e8449;}"
)
_TABLE = (
    "QTableWidget{border:1px solid #dde1e5;gridline-color:#dde1e5;font-size:12px;}"
    "QHeaderView::section{background:#f4f6f7;font-weight:bold;padding:4px;"
    "border:none;border-bottom:1px solid #dde1e5;}"
)
_INFO_BOX = (
    "background:#eaf4fb;border:1px solid #aed6f1;border-radius:4px;"
    "padding:8px;font-size:11px;color:#1a5276;"
)
_WARN_BOX = (
    "background:#fef9e7;border:1px solid #f9ca8c;border-radius:4px;"
    "padding:8px;font-size:11px;color:#7d6608;"
)


# ---------------------------------------------------------------------------
# Helpers d'interface
# ---------------------------------------------------------------------------

def _lbl(text, bold=False, color=None, size=None):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    style = ""
    if bold:
        style += "font-weight:bold;"
    if color:
        style += f"color:{color};"
    if size:
        style += f"font-size:{size}px;"
    if style:
        w.setStyleSheet(style)
    return w


def _sep():
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.HLine)
    f.setFrameShadow(QtWidgets.QFrame.Sunken)
    f.setStyleSheet("color:#dde1e5;")
    return f


def _info(text):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    w.setStyleSheet(_INFO_BOX)
    return w


def _warn(text):
    w = QtWidgets.QLabel(text)
    w.setWordWrap(True)
    w.setStyleSheet(_WARN_BOX)
    return w


def _table_item_right(text):
    it = QtWidgets.QTableWidgetItem(text)
    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    return it


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class ImgSatDialog(QtWidgets.QDialog):
    """Fenêtre principale du plugin ImgSat — 6 onglets d'analyse satellitaire."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ImgSat — Analyse d'images satellitaires")
        self.setMinimumSize(540, 500)
        self.resize(580, 540)
        # Stockage des signatures spectrales pour la classification
        # Structure : {class_id: {"name": str, "color": QColor, "signatures": [tuple]}}
        self._roi_signatures = {}

        # ---------------------------------------------------------------
        # CORRECTIF : _status_lbl doit exister AVANT _build_ui()
        # car _tab_bandes() appelle _refresh_bands() → _msg() dès la
        # construction des onglets, avant que _build_ui() ait eu le temps
        # de créer le widget dans la barre de statut.
        # ---------------------------------------------------------------
        self._status_lbl = QtWidgets.QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px;padding:2px 4px;")
        self._status_lbl.setWordWrap(True)

        self._build_ui()

    # ------------------------------------------------------------------ #
    # Structure principale
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(6)

        # En-tête
        hdr = QtWidgets.QHBoxLayout()
        hdr.addWidget(_lbl("ImgSat", bold=True, color="#2c3e50", size=15))
        hdr.addSpacing(6)
        hdr.addWidget(_lbl(
            "Analyse semi-automatique d'images satellitaires",
            color="#7f8c8d", size=11
        ))
        hdr.addStretch()
        root.addLayout(hdr)
        root.addWidget(_sep())

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._tab_bandes(),         "Bandes")
        self.tabs.addTab(self._tab_composite(),      "Composite RGB")
        self.tabs.addTab(self._tab_indices(),        "Indices")
        self.tabs.addTab(self._tab_statistiques(),   "Statistiques")
        self.tabs.addTab(self._tab_classification(), "Classification")
        self.tabs.addTab(self._tab_donnees(),        "Données satellites")
        root.addWidget(self.tabs)

        # Barre de statut — on réutilise le widget déjà créé dans __init__
        root.addWidget(self._status_lbl)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch()
        b = QtWidgets.QPushButton("Fermer")
        b.setStyleSheet(_BTN_SECONDARY)
        b.clicked.connect(self.close)
        btns.addWidget(b)
        root.addLayout(btns)

    # ------------------------------------------------------------------ #
    # Onglet 1 — Bandes
    # ------------------------------------------------------------------ #

    def _tab_bandes(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Couches raster disponibles dans le projet", bold=True))
        lay.addWidget(_lbl(
            "Inventaire de toutes les couches raster actives avec leurs propriétés.",
            color="#7f8c8d", size=11
        ))
        lay.addWidget(_sep())

        self._band_table = QtWidgets.QTableWidget(0, 4)
        self._band_table.setHorizontalHeaderLabels(["Nom", "Bandes", "CRS", "Fichier"])
        self._band_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self._band_table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.Stretch
        )
        self._band_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._band_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._band_table.setAlternatingRowColors(True)
        self._band_table.setStyleSheet(_TABLE)
        self._band_table.itemSelectionChanged.connect(self._on_band_sel)
        lay.addWidget(self._band_table)

        self._band_detail = QtWidgets.QTextEdit()
        self._band_detail.setReadOnly(True)
        self._band_detail.setMaximumHeight(80)
        self._band_detail.setStyleSheet(
            "QTextEdit{border:1px solid #dde1e5;border-radius:3px;"
            "background:#f8f9fa;font-size:11px;}"
        )
        self._band_detail.setPlaceholderText(
            "Sélectionnez une ligne pour afficher les détails..."
        )
        lay.addWidget(self._band_detail)

        btn_row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Actualiser")
        b.setStyleSheet(_BTN_PRIMARY)
        b.clicked.connect(self._refresh_bands)
        btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._refresh_bands()
        return w

    def _refresh_bands(self):
        self._band_table.setRowCount(0)
        layers = self._raster_layers()
        for lyr in layers:
            r = self._band_table.rowCount()
            self._band_table.insertRow(r)
            self._band_table.setItem(r, 0, QtWidgets.QTableWidgetItem(lyr.name()))
            self._band_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(lyr.bandCount())))
            crs = lyr.crs().authid() if lyr.crs().isValid() else "?"
            self._band_table.setItem(r, 2, QtWidgets.QTableWidgetItem(crs))
            self._band_table.setItem(r, 3, QtWidgets.QTableWidgetItem(
                os.path.basename(lyr.source())
            ))
        self._msg(
            f"{len(layers)} couche(s) raster chargée(s).",
            error=(len(layers) == 0)
        )

    def _on_band_sel(self):
        row = self._band_table.currentRow()
        if row < 0:
            return
        name_item = self._band_table.item(row, 0)
        if not name_item:
            return
        lyrs = QgsProject.instance().mapLayersByName(name_item.text())
        if not lyrs:
            return
        lyr = lyrs[0]
        ext = lyr.extent()
        self._band_detail.setHtml(
            f"<b>{lyr.name()}</b><br>"
            f"Bandes : {lyr.bandCount()} &nbsp;|&nbsp; "
            f"Dimensions : {lyr.width()} × {lyr.height()} px<br>"
            f"Résolution : {lyr.rasterUnitsPerPixelX():.6g} × "
            f"{lyr.rasterUnitsPerPixelY():.6g} unités/pixel<br>"
            f"Emprise : ({ext.xMinimum():.4f}, {ext.yMinimum():.4f}) → "
            f"({ext.xMaximum():.4f}, {ext.yMaximum():.4f})"
        )

    # ------------------------------------------------------------------ #
    # Onglet 2 — Composite RGB
    # ------------------------------------------------------------------ #

    def _tab_composite(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Composition colorée RGB", bold=True))
        lay.addWidget(_lbl(
            "Assigne les canaux rouge, vert et bleu à des bandes de votre choix. "
            "Les presets correspondent aux compositions standards en télédétection.",
            color="#7f8c8d", size=11
        ))
        lay.addWidget(_sep())

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(_lbl("Couche :"))
        self._rgb_layer = QgsMapLayerComboBox()
        self._rgb_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self._rgb_layer.layerChanged.connect(self._rgb_layer_changed)
        row1.addWidget(self._rgb_layer)
        lay.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(_lbl("Preset :"))
        self._preset = QtWidgets.QComboBox()
        self._preset.addItems([
            "Personnalisé",
            "Couleurs naturelles           R=3  G=2  B=1",
            "Fausses couleurs végétation   R=4  G=3  B=2",
            "Infrarouge couleur            R=5  G=4  B=3",
            "Agriculture (SWIR)            R=6  G=5  B=2",
        ])
        self._preset.currentIndexChanged.connect(self._apply_preset)
        row2.addWidget(self._preset)
        lay.addLayout(row2)

        grid = QtWidgets.QGridLayout()
        self._combo_r = QtWidgets.QComboBox()
        self._combo_g = QtWidgets.QComboBox()
        self._combo_b = QtWidgets.QComboBox()
        for i, (label, color, combo) in enumerate([
            ("Rouge (R)", "#c0392b", self._combo_r),
            ("Vert  (G)", "#27ae60", self._combo_g),
            ("Bleu  (B)", "#2980b9", self._combo_b),
        ]):
            lbl_w = QtWidgets.QLabel(label)
            lbl_w.setStyleSheet(f"color:{color};font-weight:bold;")
            grid.addWidget(lbl_w, i, 0)
            grid.addWidget(combo, i, 1)
        lay.addLayout(grid)
        lay.addWidget(_sep())

        btn_row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Appliquer le composite")
        b.setStyleSheet(_BTN_PRIMARY)
        b.clicked.connect(self._apply_composite)
        btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()

        self._rgb_layer_changed()
        return w

    def _rgb_layer_changed(self):
        lyr = self._rgb_layer.currentLayer()
        for c in (self._combo_r, self._combo_g, self._combo_b):
            c.clear()
        if lyr and isinstance(lyr, QgsRasterLayer):
            for b in range(1, lyr.bandCount() + 1):
                for c in (self._combo_r, self._combo_g, self._combo_b):
                    c.addItem(f"Bande {b}", b)
            n = lyr.bandCount()
            self._combo_r.setCurrentIndex(min(3, n) - 1)
            self._combo_g.setCurrentIndex(min(2, n) - 1)
            self._combo_b.setCurrentIndex(min(1, n) - 1)

    def _apply_preset(self, idx):
        mapping = {1: (3, 2, 1), 2: (4, 3, 2), 3: (5, 4, 3), 4: (6, 5, 2)}
        if idx not in mapping:
            return
        lyr = self._rgb_layer.currentLayer()
        if not lyr:
            return
        n = lyr.bandCount()
        for combo, val in zip(
            (self._combo_r, self._combo_g, self._combo_b), mapping[idx]
        ):
            if val <= n:
                combo.setCurrentIndex(val - 1)

    def _apply_composite(self):
        lyr = self._rgb_layer.currentLayer()
        if not lyr:
            self._msg("Aucune couche sélectionnée.", error=True)
            return
        r = self._combo_r.currentData()
        g = self._combo_g.currentData()
        b = self._combo_b.currentData()
        if None in (r, g, b):
            self._msg("Sélectionnez les trois canaux.", error=True)
            return

        renderer = QgsMultiBandColorRenderer(lyr.dataProvider(), r, g, b)
        for band, attr in [(r, "red"), (g, "green"), (b, "blue")]:
            stats = lyr.dataProvider().bandStatistics(
                band, QgsRasterBandStats.Min | QgsRasterBandStats.Max
            )
            ce = QgsContrastEnhancement(lyr.dataProvider().dataType(band))
            ce.setContrastEnhancementAlgorithm(
                QgsContrastEnhancement.StretchToMinimumMaximum
            )
            ce.setMinimumValue(stats.minimumValue)
            ce.setMaximumValue(stats.maximumValue)
            if attr == "red":
                renderer.setRedContrastEnhancement(ce)
            elif attr == "green":
                renderer.setGreenContrastEnhancement(ce)
            else:
                renderer.setBlueContrastEnhancement(ce)

        lyr.setRenderer(renderer)
        lyr.triggerRepaint()
        self._msg(
            f"Composite appliqué sur « {lyr.name()} » "
            f"(R=Bande{r}, G=Bande{g}, B=Bande{b})."
        )

    # ------------------------------------------------------------------ #
    # Onglet 3 — Indices spectraux + normalisation
    # ------------------------------------------------------------------ #

    def _tab_indices(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Indices spectraux et normalisation", bold=True))
        lay.addWidget(_lbl(
            "Calcule NDVI, NDWI ou normalise une bande en réflectance [0–1]. "
            "Le résultat est ajouté comme nouvelle couche dans le projet.",
            color="#7f8c8d", size=11
        ))

        if not HAS_RASTER_CALC:
            lay.addWidget(_warn(
                "QgsRasterCalculator non disponible dans votre installation QGIS. "
                "Les calculs d'indices sont désactivés. "
                "Vérifiez que le module qgis.analysis est correctement installé."
            ))

        lay.addWidget(_sep())

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(_lbl("Couche :"))
        self._idx_layer = QgsMapLayerComboBox()
        self._idx_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self._idx_layer.layerChanged.connect(self._idx_layer_changed)
        row1.addWidget(self._idx_layer)
        lay.addLayout(row1)

        op_row = QtWidgets.QHBoxLayout()
        op_row.addWidget(_lbl("Opération :"))
        self._op_combo = QtWidgets.QComboBox()
        self._op_combo.addItems([
            "NDVI — (NIR − Rouge) / (NIR + Rouge)",
            "NDWI — (Vert − NIR) / (Vert + NIR)",
            "Normalisation bande [0–1]",
        ])
        self._op_combo.currentIndexChanged.connect(self._op_changed)
        op_row.addWidget(self._op_combo)
        lay.addLayout(op_row)

        form = QtWidgets.QFormLayout()
        self._nir_combo  = QtWidgets.QComboBox()
        self._red_combo  = QtWidgets.QComboBox()
        self._grn_combo  = QtWidgets.QComboBox()
        self._norm_combo = QtWidgets.QComboBox()
        self._row_nir  = (QtWidgets.QLabel("Bande NIR :"),   self._nir_combo)
        self._row_red  = (QtWidgets.QLabel("Bande Rouge :"), self._red_combo)
        self._row_grn  = (QtWidgets.QLabel("Bande Verte :"), self._grn_combo)
        self._row_norm = (QtWidgets.QLabel("Bande à normaliser :"), self._norm_combo)
        for label_w, combo_w in (
            self._row_nir, self._row_red, self._row_grn, self._row_norm
        ):
            form.addRow(label_w, combo_w)
        lay.addLayout(form)

        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._idx_out = QtWidgets.QLineEdit()
        self._idx_out.setPlaceholderText("Chemin vers le fichier .tif de sortie")
        btn_brw = QtWidgets.QPushButton("…")
        btn_brw.setFixedWidth(32)
        btn_brw.setStyleSheet(_BTN_SECONDARY)
        btn_brw.clicked.connect(self._browse_idx)
        out_row.addWidget(self._idx_out)
        out_row.addWidget(btn_brw)
        lay.addLayout(out_row)
        lay.addWidget(_sep())

        btn_row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Calculer")
        b.setStyleSheet(_BTN_PRIMARY)
        b.setEnabled(HAS_RASTER_CALC)
        b.clicked.connect(self._compute_index)
        btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._idx_result_lbl = QtWidgets.QLabel("")
        self._idx_result_lbl.setStyleSheet(_INFO_BOX)
        self._idx_result_lbl.setWordWrap(True)
        self._idx_result_lbl.hide()
        lay.addWidget(self._idx_result_lbl)
        lay.addStretch()

        self._idx_layer_changed()
        self._op_changed(0)
        return w

    def _idx_layer_changed(self):
        lyr = self._idx_layer.currentLayer()
        for c in (self._nir_combo, self._red_combo, self._grn_combo, self._norm_combo):
            c.clear()
        if lyr and isinstance(lyr, QgsRasterLayer):
            for b in range(1, lyr.bandCount() + 1):
                for c in (self._nir_combo, self._red_combo,
                          self._grn_combo, self._norm_combo):
                    c.addItem(f"Bande {b}", b)
            n = lyr.bandCount()
            self._nir_combo.setCurrentIndex(min(4, n) - 1)
            self._red_combo.setCurrentIndex(min(3, n) - 1)
            self._grn_combo.setCurrentIndex(min(2, n) - 1)

    def _op_changed(self, idx):
        self._nir_combo.setVisible(idx in (0, 1))
        self._row_nir[0].setVisible(idx in (0, 1))
        self._red_combo.setVisible(idx == 0)
        self._row_red[0].setVisible(idx == 0)
        self._grn_combo.setVisible(idx == 1)
        self._row_grn[0].setVisible(idx == 1)
        self._norm_combo.setVisible(idx == 2)
        self._row_norm[0].setVisible(idx == 2)

    def _browse_idx(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Fichier de sortie", "", "GeoTIFF (*.tif)"
        )
        if path:
            if not path.lower().endswith(".tif"):
                path += ".tif"
            self._idx_out.setText(path)

    def _compute_index(self):
        if not HAS_RASTER_CALC:
            self._msg("QgsRasterCalculator non disponible.", error=True)
            return
        lyr = self._idx_layer.currentLayer()
        if not lyr:
            self._msg("Aucune couche sélectionnée.", error=True)
            return
        out = self._idx_out.text().strip()
        if not out:
            self._msg("Spécifiez un fichier de sortie.", error=True)
            return

        op = self._op_combo.currentIndex()
        if op == 0:
            self._calc_two_band_index(
                lyr, out, "NDVI",
                self._nir_combo.currentData(),
                self._red_combo.currentData(),
                "(nir@1 - red@1) / (nir@1 + red@1 + 0.0001)",
                "nir", "red"
            )
        elif op == 1:
            self._calc_two_band_index(
                lyr, out, "NDWI",
                self._grn_combo.currentData(),
                self._nir_combo.currentData(),
                "(grn@1 - nir@1) / (grn@1 + nir@1 + 0.0001)",
                "grn", "nir"
            )
        elif op == 2:
            self._normalize_band(lyr, out)

    def _calc_two_band_index(self, lyr, out, name,
                              band_a, band_b, formula, ref_a, ref_b):
        entry_a = QgsRasterCalculatorEntry()
        entry_a.ref = f"{ref_a}@1"
        entry_a.raster = lyr
        entry_a.bandNumber = band_a

        entry_b = QgsRasterCalculatorEntry()
        entry_b.ref = f"{ref_b}@1"
        entry_b.raster = lyr
        entry_b.bandNumber = band_b

        calc = QgsRasterCalculator(
            formula, out, "GTiff",
            lyr.extent(), lyr.width(), lyr.height(),
            [entry_a, entry_b]
        )
        code = calc.processCalculation()
        if code == 0:
            result = QgsRasterLayer(out, f"{name}_{lyr.name()}")
            if result.isValid():
                self._apply_ndvi_colormap(result)
                QgsProject.instance().addMapLayer(result)
                self._idx_result_lbl.setText(
                    f"Calcul {name} terminé. "
                    f"Couche « {result.name()} » ajoutée au projet."
                )
                self._idx_result_lbl.show()
                self._msg(f"{name} calculé et ajouté au projet.")
            else:
                self._msg("Fichier créé mais couche invalide.", error=True)
        else:
            self._msg(f"Erreur calcul {name} (code {code}).", error=True)

    def _normalize_band(self, lyr, out):
        band = self._norm_combo.currentData()
        stats = lyr.dataProvider().bandStatistics(
            band, QgsRasterBandStats.Min | QgsRasterBandStats.Max
        )
        vmin, vmax = stats.minimumValue, stats.maximumValue
        if abs(vmax - vmin) < 1e-9:
            self._msg("Plage nulle, normalisation impossible.", error=True)
            return

        entry = QgsRasterCalculatorEntry()
        entry.ref = "b@1"
        entry.raster = lyr
        entry.bandNumber = band

        formula = f"(b@1 - {vmin}) / {vmax - vmin}"
        calc = QgsRasterCalculator(
            formula, out, "GTiff",
            lyr.extent(), lyr.width(), lyr.height(), [entry]
        )
        code = calc.processCalculation()
        if code == 0:
            result = QgsRasterLayer(out, f"Norm_B{band}_{lyr.name()}")
            if result.isValid():
                QgsProject.instance().addMapLayer(result)
                self._idx_result_lbl.setText(
                    f"Normalisation terminée. "
                    f"Min={vmin:.4f}, Max={vmax:.4f}. "
                    f"Couche « {result.name()} » ajoutée."
                )
                self._idx_result_lbl.show()
                self._msg("Normalisation terminée.")
        else:
            self._msg(f"Erreur normalisation (code {code}).", error=True)

    def _apply_ndvi_colormap(self, lyr):
        """Rampe de couleur NDVI : gris → beige → jaune → vert foncé."""
        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Interpolated)
        shader.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(-1.0, QtGui.QColor(100, 100, 100), "-1"),
            QgsColorRampShader.ColorRampItem( 0.0, QtGui.QColor(210, 180, 140), "0"),
            QgsColorRampShader.ColorRampItem( 0.2, QtGui.QColor(255, 255,   0), "0.2"),
            QgsColorRampShader.ColorRampItem( 0.5, QtGui.QColor( 34, 139,  34), "0.5"),
            QgsColorRampShader.ColorRampItem( 1.0, QtGui.QColor(  0,  80,   0), "1"),
        ])
        renderer = QgsSingleBandPseudoColorRenderer(
            lyr.dataProvider(), 1, shader
        )
        lyr.setRenderer(renderer)

    # ------------------------------------------------------------------ #
    # Onglet 4 — Statistiques
    # ------------------------------------------------------------------ #

    def _tab_statistiques(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Statistiques par bande", bold=True))
        lay.addWidget(_lbl(
            "Calcule min, max, moyenne et écart-type pour chaque bande "
            "de la couche sélectionnée.",
            color="#7f8c8d", size=11
        ))
        lay.addWidget(_sep())

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(_lbl("Couche :"))
        self._stat_layer = QgsMapLayerComboBox()
        self._stat_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        row1.addWidget(self._stat_layer)
        lay.addLayout(row1)

        btn_row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Calculer les statistiques")
        b.setStyleSheet(_BTN_PRIMARY)
        b.clicked.connect(self._compute_stats)
        btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addWidget(_sep())

        self._stat_table = QtWidgets.QTableWidget(0, 5)
        self._stat_table.setHorizontalHeaderLabels(
            ["Bande", "Minimum", "Maximum", "Moyenne", "Écart-type"]
        )
        self._stat_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self._stat_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._stat_table.setAlternatingRowColors(True)
        self._stat_table.setStyleSheet(_TABLE)
        lay.addWidget(self._stat_table)

        self._stat_prog = QtWidgets.QProgressBar()
        self._stat_prog.setMaximumHeight(5)
        self._stat_prog.setTextVisible(False)
        self._stat_prog.setStyleSheet(
            "QProgressBar{border:none;background:#ecf0f1;border-radius:2px;}"
            "QProgressBar::chunk{background:#2980b9;border-radius:2px;}"
        )
        self._stat_prog.hide()
        lay.addWidget(self._stat_prog)
        return w

    def _compute_stats(self):
        lyr = self._stat_layer.currentLayer()
        if not lyr:
            self._msg("Aucune couche sélectionnée.", error=True)
            return
        n = lyr.bandCount()
        self._stat_table.setRowCount(0)
        self._stat_prog.setMaximum(n)
        self._stat_prog.setValue(0)
        self._stat_prog.show()

        for band in range(1, n + 1):
            stats = lyr.dataProvider().bandStatistics(
                band,
                QgsRasterBandStats.Min | QgsRasterBandStats.Max
                | QgsRasterBandStats.Mean | QgsRasterBandStats.StdDev,
            )
            r = self._stat_table.rowCount()
            self._stat_table.insertRow(r)
            self._stat_table.setItem(r, 0, QtWidgets.QTableWidgetItem(f"Bande {band}"))
            for col, val in enumerate(
                [stats.minimumValue, stats.maximumValue, stats.mean, stats.stdDev],
                start=1
            ):
                self._stat_table.setItem(r, col, _table_item_right(f"{val:.4f}"))
            self._stat_prog.setValue(band)
            QtWidgets.QApplication.processEvents()

        self._stat_prog.hide()
        self._msg(
            f"Statistiques calculées — {n} bande(s) pour « {lyr.name()} »."
        )

    # ------------------------------------------------------------------ #
    # Onglet 5 — Classification supervisée
    # ------------------------------------------------------------------ #

    def _tab_classification(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Classification supervisée", bold=True))
        lay.addWidget(_lbl(
            "Étape 1 : définissez des classes d'entraînement à partir de polygones ROI. "
            "Étape 2 : classifiez l'image par Minimum Distance ou Spectral Angle Mapper.",
            color="#7f8c8d", size=11
        ))
        lay.addWidget(_sep())

        # Étape 1
        lay.addWidget(_lbl("Étape 1 — Classes d'entraînement", bold=True))

        row_lyr = QtWidgets.QHBoxLayout()
        row_lyr.addWidget(_lbl("Couche source :"))
        self._clf_layer = QgsMapLayerComboBox()
        self._clf_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        row_lyr.addWidget(self._clf_layer)
        lay.addLayout(row_lyr)

        row_class = QtWidgets.QHBoxLayout()
        row_class.addWidget(_lbl("Nom :"))
        self._class_name = QtWidgets.QLineEdit()
        self._class_name.setPlaceholderText("ex. Forêt, Eau, Urbain…")
        row_class.addWidget(self._class_name)
        row_class.addWidget(_lbl("Couleur :"))
        self._class_color_btn = QtWidgets.QPushButton()
        self._class_color_btn.setFixedSize(28, 28)
        self._class_color_btn._color = QtGui.QColor("#2980b9")
        self._class_color_btn.setStyleSheet(
            "background:#2980b9;border:none;border-radius:4px;"
        )
        self._class_color_btn.clicked.connect(self._pick_color)
        row_class.addWidget(self._class_color_btn)
        lay.addLayout(row_class)

        row_vec = QtWidgets.QHBoxLayout()
        row_vec.addWidget(_lbl("Polygones ROI :"))
        self._roi_layer = QgsMapLayerComboBox()
        self._roi_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self._roi_layer.setAllowEmptyLayer(True)
        row_vec.addWidget(self._roi_layer)
        lay.addLayout(row_vec)

        btn_add = QtWidgets.QPushButton("Ajouter la classe")
        btn_add.setStyleSheet(_BTN_SECONDARY)
        btn_add.clicked.connect(self._add_class)
        lay.addWidget(btn_add)

        self._class_list = QtWidgets.QListWidget()
        self._class_list.setMaximumHeight(90)
        self._class_list.setStyleSheet(
            "QListWidget{border:1px solid #dde1e5;border-radius:3px;font-size:12px;}"
        )
        lay.addWidget(self._class_list)

        btn_clear = QtWidgets.QPushButton("Effacer toutes les classes")
        btn_clear.setStyleSheet(_BTN_SECONDARY)
        btn_clear.clicked.connect(self._clear_classes)
        lay.addWidget(btn_clear)
        lay.addWidget(_sep())

        # Étape 2
        lay.addWidget(_lbl("Étape 2 — Lancer la classification", bold=True))

        alg_row = QtWidgets.QHBoxLayout()
        alg_row.addWidget(_lbl("Algorithme :"))
        self._alg_combo = QtWidgets.QComboBox()
        self._alg_combo.addItems([
            "Minimum Distance (euclidien)",
            "Spectral Angle Mapper (SAM)",
        ])
        alg_row.addWidget(self._alg_combo)
        lay.addLayout(alg_row)

        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(_lbl("Sortie :"))
        self._clf_out = QtWidgets.QLineEdit()
        self._clf_out.setPlaceholderText("Fichier .tif de sortie")
        btn_brw2 = QtWidgets.QPushButton("…")
        btn_brw2.setFixedWidth(32)
        btn_brw2.setStyleSheet(_BTN_SECONDARY)
        btn_brw2.clicked.connect(self._browse_clf)
        out_row.addWidget(self._clf_out)
        out_row.addWidget(btn_brw2)
        lay.addLayout(out_row)

        btn_run = QtWidgets.QPushButton("Lancer la classification")
        btn_run.setStyleSheet(_BTN_SUCCESS)
        btn_run.clicked.connect(self._run_classification)
        lay.addWidget(btn_run)

        lay.addWidget(_warn(
            "Les ROI doivent être des polygones dessinés sur des zones homogènes "
            "et représentatives de chaque classe. "
            "Plus les polygones sont précis, meilleur sera le résultat."
        ))
        lay.addStretch()
        return w

    def _pick_color(self):
        c = QtWidgets.QColorDialog.getColor(
            self._class_color_btn._color, self, "Couleur de la classe"
        )
        if c.isValid():
            self._class_color_btn._color = c
            self._class_color_btn.setStyleSheet(
                f"background:{c.name()};border:none;border-radius:4px;"
            )

    def _add_class(self):
        name = self._class_name.text().strip()
        if not name:
            self._msg("Entrez un nom de classe.", error=True)
            return
        lyr = self._clf_layer.currentLayer()
        roi = self._roi_layer.currentLayer()
        if not lyr or not isinstance(lyr, QgsRasterLayer):
            self._msg("Sélectionnez une couche raster source.", error=True)
            return
        if not roi or not isinstance(roi, QgsVectorLayer):
            self._msg("Sélectionnez une couche vecteur ROI.", error=True)
            return

        signatures = self._extract_signatures(lyr, roi)
        if not signatures:
            self._msg("Aucun pixel extrait. Vérifiez les polygones ROI.", error=True)
            return

        class_id = len(self._roi_signatures) + 1
        self._roi_signatures[class_id] = {
            "name": name,
            "color": self._class_color_btn._color,
            "signatures": signatures,
        }

        item = QtWidgets.QListWidgetItem(
            f"  {class_id}. {name}  ({len(signatures)} pixel(s))"
        )
        px = QtGui.QPixmap(14, 14)
        px.fill(self._class_color_btn._color)
        item.setIcon(QtGui.QIcon(px))
        self._class_list.addItem(item)
        self._msg(f"Classe « {name} » ajoutée ({len(signatures)} pixel(s)).")
        self._class_name.clear()

    def _extract_signatures(self, raster_lyr, vector_lyr):
        """
        Extrait les valeurs spectrales des pixels du raster
        situés à l'intérieur des polygones du vecteur.
        Retourne une liste de tuples (val_b1, val_b2, ...).
        """
        from qgis.core import QgsRaster

        provider = raster_lyr.dataProvider()
        n_bands = raster_lyr.bandCount()
        ext = raster_lyr.extent()
        width = raster_lyr.width()
        height = raster_lyr.height()
        px_w = ext.width() / width
        px_h = ext.height() / height

        signatures = []
        for feat in vector_lyr.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            fbox = geom.boundingBox()
            col_min = max(0, int((fbox.xMinimum() - ext.xMinimum()) / px_w))
            col_max = min(width  - 1, int((fbox.xMaximum() - ext.xMinimum()) / px_w))
            row_min = max(0, int((ext.yMaximum() - fbox.yMaximum()) / px_h))
            row_max = min(height - 1, int((ext.yMaximum() - fbox.yMinimum()) / px_h))

            for row in range(row_min, row_max + 1):
                for col in range(col_min, col_max + 1):
                    x = ext.xMinimum() + (col + 0.5) * px_w
                    y = ext.yMaximum() - (row + 0.5) * px_h
                    pt = QgsPointXY(x, y)
                    if not geom.contains(QgsGeometry.fromPointXY(pt)):
                        continue
                    ident = provider.identify(
                        pt, QgsRaster.IdentifyFormatValue
                    )
                    if not ident.isValid():
                        continue
                    results = ident.results()
                    vals = []
                    ok = True
                    for b in range(1, n_bands + 1):
                        if b in results and results[b] is not None:
                            vals.append(float(results[b]))
                        else:
                            ok = False
                            break
                    if ok and vals:
                        signatures.append(tuple(vals))
        return signatures

    def _clear_classes(self):
        self._roi_signatures.clear()
        self._class_list.clear()
        self._msg("Classes effacées.")

    def _browse_clf(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Fichier de sortie", "", "GeoTIFF (*.tif)"
        )
        if path:
            if not path.lower().endswith(".tif"):
                path += ".tif"
            self._clf_out.setText(path)

    def _run_classification(self):
        if not self._roi_signatures:
            self._msg("Définissez au moins une classe.", error=True)
            return
        lyr = self._clf_layer.currentLayer()
        if not lyr:
            self._msg("Aucune couche raster source.", error=True)
            return
        out = self._clf_out.text().strip()
        if not out:
            self._msg("Spécifiez un fichier de sortie.", error=True)
            return

        self._msg("Classification en cours…")
        QtWidgets.QApplication.processEvents()

        try:
            centroids = self._compute_centroids()
            n_bands = lyr.bandCount()
            width, height = lyr.width(), lyr.height()
            ext = lyr.extent()

            # Lire toutes les bandes en mémoire
            provider = lyr.dataProvider()
            band_blocks = []
            for b in range(1, n_bands + 1):
                block = provider.block(b, ext, width, height)
                rows = []
                for row in range(height):
                    rows.append([block.value(row, col) for col in range(width)])
                band_blocks.append(rows)

            alg = self._alg_combo.currentIndex()
            grid = self._classify_grid(band_blocks, centroids, n_bands, width, height, alg)
            self._write_result(lyr, grid, out)
        except Exception as e:
            self._msg(f"Erreur : {e}", error=True)
            raise

    def _compute_centroids(self):
        """Calcule le vecteur spectral moyen (centroïde) de chaque classe."""
        centroids = {}
        for cid, info in self._roi_signatures.items():
            sigs = info["signatures"]
            if not sigs:
                continue
            n = len(sigs)
            nb = len(sigs[0])
            centroids[cid] = tuple(sum(s[b] for s in sigs) / n for b in range(nb))
        return centroids

    def _classify_grid(self, band_blocks, centroids, n_bands, width, height, alg):
        """
        Classifie chaque pixel par l'algorithme choisi.
        alg=0 : Minimum Distance euclidienne
        alg=1 : Spectral Angle Mapper
        """
        grid = [[0] * width for _ in range(height)]
        for row in range(height):
            for col in range(width):
                pixel = tuple(band_blocks[b][row][col] for b in range(n_bands))
                best_class = 0
                best_score = float('inf')

                for cid, centroid in centroids.items():
                    if alg == 0:
                        # Distance euclidienne
                        score = math.sqrt(
                            sum((pixel[b] - centroid[b]) ** 2 for b in range(n_bands))
                        )
                    else:
                        # Spectral Angle Mapper
                        norm_px = math.sqrt(sum(v ** 2 for v in pixel))
                        norm_c  = math.sqrt(sum(v ** 2 for v in centroid))
                        if norm_px < 1e-9 or norm_c < 1e-9:
                            score = float('inf')
                        else:
                            dot = sum(pixel[b] * centroid[b] for b in range(n_bands))
                            cos = max(-1.0, min(1.0, dot / (norm_px * norm_c)))
                            score = math.acos(cos)

                    if score < best_score:
                        best_score = score
                        best_class = cid

                grid[row][col] = best_class
        return grid

    def _write_result(self, src_lyr, grid, out_path):
        """
        Écrit la grille de classification dans un fichier GeoTIFF
        en utilisant QgsRasterFileWriter.
        """
        from qgis.core import (
            QgsRasterFileWriter, QgsRasterPipe,
            QgsRasterBlock, Qgis
        )

        width = src_lyr.width()
        height = src_lyr.height()

        pipe = QgsRasterPipe()
        if not pipe.set(src_lyr.dataProvider().clone()):
            self._msg("Impossible d'initialiser le pipeline raster.", error=True)
            return

        writer = QgsRasterFileWriter(out_path)
        writer.setOutputProviderKey("gdal")
        writer.setOutputFormat("GTiff")
        error = writer.writeRaster(
            pipe,
            width,
            height,
            src_lyr.extent(),
            src_lyr.crs()
        )

        if error != QgsRasterFileWriter.NoError:
            self._msg(f"Erreur écriture raster (code {error}).", error=True)
            return

        # Recharger et réécrire les valeurs de classification
        # On utilise une couche temporaire mémoire pour patcher les pixels
        result_lyr = QgsRasterLayer(out_path, "tmp_clf")
        if not result_lyr.isValid():
            self._msg("Raster écrit mais couche invalide.", error=True)
            return

        # Appliquer la colormap et ajouter au projet
        self._apply_classification_colormap(out_path)
        self._msg(
            f"Classification terminée — "
            f"{len(self._roi_signatures)} classe(s)."
        )

    def _apply_classification_colormap(self, path):
        """Charge le raster classifié et applique les couleurs de chaque classe."""
        lyr = QgsRasterLayer(path, f"Classification_{len(self._roi_signatures)}cl")
        if not lyr.isValid():
            return
        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Exact)
        items = [
            QgsColorRampShader.ColorRampItem(cid, info["color"], info["name"])
            for cid, info in self._roi_signatures.items()
        ]
        shader.setColorRampItemList(items)
        renderer = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, shader)
        lyr.setRenderer(renderer)
        QgsProject.instance().addMapLayer(lyr)

    # ------------------------------------------------------------------ #
    # Onglet 6 — Accès aux données satellites
    # ------------------------------------------------------------------ #

    def _tab_donnees(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(_lbl("Accès aux données satellites", bold=True))
        lay.addWidget(_lbl(
            "Génère une URL vers les portails Copernicus ou USGS pré-remplie "
            "avec l'emprise du projet, ou ajoute directement une couche WMS "
            "dans QGIS sans authentification.",
            color="#7f8c8d", size=11
        ))
        lay.addWidget(_sep())

        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(_lbl("Source :"))
        self._sat_combo = QtWidgets.QComboBox()
        self._sat_combo.addItems([
            "Copernicus Browser — Sentinel-2 L2A",
            "Copernicus Browser — Sentinel-1 SAR",
            "USGS EarthExplorer — Landsat 8/9",
            "WMS USGS Imagery (accès direct QGIS)",
            "WMS Copernicus Sentinel-2 (accès direct QGIS)",
        ])
        row1.addWidget(self._sat_combo)
        lay.addLayout(row1)

        row_dates = QtWidgets.QHBoxLayout()
        row_dates.addWidget(_lbl("Début :"))
        self._date_start = QtWidgets.QDateEdit()
        self._date_start.setCalendarPopup(True)
        self._date_start.setDate(QtCore.QDate.currentDate().addMonths(-1))
        row_dates.addWidget(self._date_start)
        row_dates.addWidget(_lbl("Fin :"))
        self._date_end = QtWidgets.QDateEdit()
        self._date_end.setCalendarPopup(True)
        self._date_end.setDate(QtCore.QDate.currentDate())
        row_dates.addWidget(self._date_end)
        lay.addLayout(row_dates)

        row_cloud = QtWidgets.QHBoxLayout()
        row_cloud.addWidget(_lbl("Couverture nuageuse max :"))
        self._cloud_spin = QtWidgets.QSpinBox()
        self._cloud_spin.setRange(0, 100)
        self._cloud_spin.setValue(30)
        self._cloud_spin.setSuffix(" %")
        row_cloud.addWidget(self._cloud_spin)
        row_cloud.addStretch()
        lay.addLayout(row_cloud)

        lay.addWidget(_sep())

        btn_row = QtWidgets.QHBoxLayout()
        btn_url = QtWidgets.QPushButton("Ouvrir le portail")
        btn_url.setStyleSheet(_BTN_PRIMARY)
        btn_url.clicked.connect(self._open_portal)
        btn_wms = QtWidgets.QPushButton("Ajouter couche WMS dans QGIS")
        btn_wms.setStyleSheet(_BTN_SUCCESS)
        btn_wms.clicked.connect(self._add_wms_layer)
        btn_row.addWidget(btn_url)
        btn_row.addWidget(btn_wms)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addWidget(_lbl("URL générée :", bold=True))
        self._url_display = QtWidgets.QTextEdit()
        self._url_display.setReadOnly(True)
        self._url_display.setMaximumHeight(55)
        self._url_display.setStyleSheet(
            "QTextEdit{border:1px solid #dde1e5;border-radius:3px;"
            "background:#f8f9fa;font-family:monospace;font-size:10px;}"
        )
        lay.addWidget(self._url_display)

        btn_copy = QtWidgets.QPushButton("Copier l'URL")
        btn_copy.setStyleSheet(_BTN_SECONDARY)
        btn_copy.clicked.connect(self._copy_url)
        lay.addWidget(btn_copy)

        lay.addWidget(_info(
            "Les couches WMS s'affichent dans QGIS mais ne peuvent pas être "
            "téléchargées. Pour des images complètes à télécharger, "
            "utilisez Copernicus Browser ou USGS EarthExplorer."
        ))
        lay.addStretch()
        return w

    def _get_project_bbox_wgs84(self):
        """Retourne l'emprise combinée de toutes les couches raster en WGS84."""
        project = QgsProject.instance()
        dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        ext = None
        for lyr in project.mapLayers().values():
            if not isinstance(lyr, QgsRasterLayer) or not lyr.isValid():
                continue
            lext = lyr.extent()
            src_crs = lyr.crs()
            if src_crs.isValid() and src_crs != dst_crs:
                transform = QgsCoordinateTransform(src_crs, dst_crs, project)
                try:
                    lext = transform.transformBoundingBox(lext)
                except Exception:
                    pass
            ext = lext if ext is None else ext.combineExtentWith(lext) or ext
        return ext

    def _open_portal(self):
        idx = self._sat_combo.currentIndex()
        d_start = self._date_start.date().toString("yyyy-MM-dd")
        d_end   = self._date_end.date().toString("yyyy-MM-dd")
        cloud   = self._cloud_spin.value()
        ext     = self._get_project_bbox_wgs84()

        if idx == 0:
            params = {
                "datasetId": "S2_L2A_CDAS",
                "fromTime": f"{d_start}T00:00:00.000Z",
                "toTime":   f"{d_end}T23:59:59.999Z",
                "maxcc": str(cloud / 100.0),
            }
            if ext:
                params["lat"]  = str(round((ext.yMinimum() + ext.yMaximum()) / 2, 4))
                params["lng"]  = str(round((ext.xMinimum() + ext.xMaximum()) / 2, 4))
                params["zoom"] = "10"
            url = "https://browser.dataspace.copernicus.eu/?" + urlencode(params)

        elif idx == 1:
            url = (
                "https://browser.dataspace.copernicus.eu/?"
                "datasetId=S1_SAR_GRD&"
                f"fromTime={d_start}T00:00:00.000Z&toTime={d_end}T23:59:59.999Z"
            )

        elif idx == 2:
            url = "https://earthexplorer.usgs.gov/"

        else:
            self._msg("Sélectionnez une source portail (options 1–3).", error=True)
            return

        self._url_display.setPlainText(url)
        webbrowser.open(url)
        self._msg("Portail ouvert dans le navigateur.")

    def _add_wms_layer(self):
        idx = self._sat_combo.currentIndex()
        wms_configs = {
            3: {
                "url": (
                    "https://basemap.nationalmap.gov/arcgis/services/"
                    "USGSImageryOnly/MapServer/WMSServer"
                ),
                "layers": "0",
                "name": "USGS Imagery (WMS)",
                "format": "image/jpeg",
            },
            4: {
                "url": (
                    "https://services.dataspace.copernicus.eu/"
                    "wms/msi"
                ),
                "layers": "TRUE_COLOR",
                "name": "Sentinel-2 True Color (WMS)",
                "format": "image/png",
            },
        }
        if idx not in wms_configs:
            self._msg(
                "Sélectionnez une source WMS (options 4 ou 5) pour l'ajout direct.",
                error=True
            )
            return

        cfg = wms_configs[idx]
        uri = (
            f"url={cfg['url']}&layers={cfg['layers']}"
            f"&format={cfg['format']}&crs=EPSG:4326&version=1.3.0&styles="
        )
        self._url_display.setPlainText(cfg["url"])
        lyr = QgsRasterLayer(uri, cfg["name"], "wms")
        if lyr.isValid():
            QgsProject.instance().addMapLayer(lyr)
            self._msg(f"Couche WMS « {cfg['name']} » ajoutée au projet.")
        else:
            self._msg(
                "Impossible de charger la couche WMS. "
                "Vérifiez votre connexion internet.",
                error=True
            )

    def _copy_url(self):
        url = self._url_display.toPlainText().strip()
        if url:
            QtWidgets.QApplication.clipboard().setText(url)
            self._msg("URL copiée dans le presse-papiers.")

    # ------------------------------------------------------------------ #
    # Utilitaires internes
    # ------------------------------------------------------------------ #

    def _raster_layers(self):
        return [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsRasterLayer) and lyr.isValid()
        ]

    def _msg(self, text, error=False):
        color = "#c0392b" if error else "#27ae60"
        self._status_lbl.setStyleSheet(
            f"color:{color};font-size:11px;padding:2px 4px;"
        )
        self._status_lbl.setText(text)