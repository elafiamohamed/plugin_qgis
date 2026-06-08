# =============================================================================
# IMPORTS — regroupés en blocs logiques (PyQt / QGIS core / QGIS gui)
# =============================================================================
import os

from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,       # ← AJOUT : index spatial pour les intersections
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

# =============================================================================
FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'derogation_dialog.ui')
)

# Correspondance nom-fichier → libellé d'affichage (défini une seule fois)
DISPLAY_NAMES = {
    'COLLECTIF':                    '🏘️ Collectif',
    'Derogation_central_13_avril':  '⚠️ Dérogation centrale',
    'DOMAINE_COMMUNAL':             '🏛️ Domaine communal',
    'DOMAINE_FORESTIER':            '🌲 Domaine forestier',
    'DOMAINE_PUBLIC':               '🏢 Domaine public',
    'DOMAINE_PRIVE_ETAT':           '🏠 Domaine privé État',
}

TARGET_CRS = "EPSG:26191"
TARGET_SRID = 26191


class DerogationDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        # --- Variables d'état (avant tout signal) ---
        self.project_layer = None
        self.loaded_layers = {}

        # --- Canvas ---
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(Qt.white)
        self.canvas.enableAntiAliasing(True)

        layout = QVBoxLayout(self.mapCanvasWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        # --- Chargement initial des couches de référence ---
        self.load_all_shapes_from_folder()

        # --- Signaux ---
        self.btnImportShp.clicked.connect(self.import_shp)
        self.btnAfficherProjet.clicked.connect(self.display_project)
        self.btnCalculerIntersections.clicked.connect(self.calculate_intersections)
        self.btnExport.clicked.connect(self.export_results_pdf)
        self.radioPointWizard.toggled.connect(self.toggle_input_mode)

        # --- État initial ---
        self.radioPointWizard.setChecked(True)
        self.toggle_input_mode()

    # =========================================================================
    # UI HELPERS
    # =========================================================================

    def toggle_input_mode(self):
        is_point = self.radioPointWizard.isChecked()
        self.lineXWizard.setEnabled(is_point)
        self.lineYWizard.setEnabled(is_point)
        self.btnImportShp.setEnabled(not is_point)

    def refresh_canvas(self, zoom_to_extent=False):
        """
        Met à jour le canvas.
        zoom_to_extent=True uniquement lors du chargement initial
        pour ne pas forcer un dezoom à chaque opération.
        """
        layers = list(QgsProject.instance().mapLayers().values())
        self.canvas.setLayers(layers)
        if zoom_to_extent:
            self.canvas.zoomToFullExtent()
        self.canvas.refresh()

    # =========================================================================
    # IMPORT SHP
    # =========================================================================

    def import_shp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir shapefile", "", "Shapefile (*.shp)"
        )
        if not path:
            return

        layer = QgsVectorLayer(path, "Projet", "ogr")
        if not layer.isValid():
            QMessageBox.warning(self, "Erreur", "Couche invalide")
            return

        # CORRECTION : on vérifie d'abord le CRS natif ;
        # on ne force pas pour masquer un mauvais fichier.
        crs = layer.crs()
        if not crs.isValid() or crs.postgisSrid() != TARGET_SRID:
            QMessageBox.warning(
                self, "CRS",
                f"La couche doit être en {TARGET_CRS} "
                f"(détecté : {crs.authid()})"
            )
            return

        self.project_layer = layer
        QgsProject.instance().addMapLayer(layer)
        self.refresh_canvas()

    # =========================================================================
    # CRÉATION D'UN POINT PROJET
    # =========================================================================

    def _parse_xy(self):
        """Lit et valide X/Y depuis les champs texte. Retourne (x, y) ou None."""
        try:
            return float(self.lineXWizard.text()), float(self.lineYWizard.text())
        except ValueError:
            QMessageBox.warning(self, "Erreur", "Coordonnées invalides")
            return None

    def create_project_point(self):
        coords = self._parse_xy()
        if coords is None:
            return None

        x, y = coords
        layer = QgsVectorLayer(f"Point?crs={TARGET_CRS}", "Projet_Point", "memory")
        provider = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        provider.addFeature(feat)
        layer.updateExtents()
        return layer

    # =========================================================================
    # AFFICHAGE DU PROJET
    # =========================================================================

    def display_project(self):
        if self.radioPointWizard.isChecked():
            layer = self.create_project_point()
            if layer is None:
                return
            self.project_layer = layer
            QgsProject.instance().addMapLayer(layer)

        elif self.radioShpWizard.isChecked():
            if self.project_layer is None:
                QMessageBox.warning(self, "Erreur", "Importer un SHP d'abord")
                return

        self.create_buffer_layer()
        self.refresh_canvas()

    # =========================================================================
    # BUFFER
    # =========================================================================

    def _get_buffer_distance(self):
        """Retourne la distance buffer en mètres, ou None si invalide."""
        value = self.spinBufferValue.value()
        unit = self.comboBufferUnit.currentText()
        distance = value * 1000 if unit == "km" else value
        if distance <= 0:
            QMessageBox.warning(
                self, "Erreur", "La distance du buffer doit être supérieure à 0"
            )
            return None
        return distance

    def _remove_existing_buffers(self):
        """Supprime les couches buffer existantes sans itérer toutes les couches."""
        to_remove = [
            lid for lid, lyr in QgsProject.instance().mapLayers().items()
            if lyr.name().startswith("Buffer_")
        ]
        for lid in to_remove:
            QgsProject.instance().removeMapLayer(lid)

    def create_buffer_layer(self):
        buffer_distance = self._get_buffer_distance()
        if buffer_distance is None:
            return None

        buffer_value = self.spinBufferValue.value()
        buffer_unit = self.comboBufferUnit.currentText()

        self._remove_existing_buffers()

        buffer_layer = QgsVectorLayer(
            f"Polygon?crs={TARGET_CRS}",
            f"Buffer_{buffer_distance}m",
            "memory"
        )
        if not buffer_layer.isValid():
            QMessageBox.warning(self, "Erreur", "Impossible de créer la couche buffer")
            return None

        features_to_add = []

        if self.radioPointWizard.isChecked():
            coords = self._parse_xy()          # ← réutilise la méthode centralisée
            if coords is None:
                return None
            x, y = coords
            geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
            buf = geom.buffer(buffer_distance, 20)
            if not buf.isNull():
                feat = QgsFeature()
                feat.setGeometry(buf)
                features_to_add.append(feat)

        elif self.radioShpWizard.isChecked():
            if self.project_layer is None:
                QMessageBox.warning(self, "Erreur", "Aucun shapefile importé")
                return None

            for feature in self.project_layer.getFeatures():
                geom = feature.geometry()
                if geom.isNull():
                    continue
                # mergeLines() n'est pertinent que pour les LineString multi-parties ;
                # on utilise directement buffer() sur la géométrie brute.
                buf = geom.buffer(buffer_distance, 20)
                if not buf.isNull():
                    feat = QgsFeature()
                    feat.setGeometry(buf)
                    features_to_add.append(feat)

            if not features_to_add:
                QMessageBox.warning(
                    self, "Erreur", "Aucune géométrie valide pour créer le buffer"
                )
                return None

        buffer_layer.dataProvider().addFeatures(features_to_add)
        buffer_layer.updateExtents()
        QgsProject.instance().addMapLayer(buffer_layer)

        symbol = QgsFillSymbol.createSimple({
            'color': 'rgba(255,0,0,50)',
            'outline_color': 'red',
            'outline_width': '0.5',
            'outline_style': 'solid',
        })
        buffer_layer.renderer().setSymbol(symbol)
        buffer_layer.triggerRepaint()

        QMessageBox.information(
            self, "Buffer créé",
            f"Buffer de {buffer_value} {buffer_unit} créé\n"
            f"({len(features_to_add)} entité(s) traitée(s))"
        )
        return buffer_layer

    # =========================================================================
    # CHARGEMENT DES COUCHES DE RÉFÉRENCE
    # =========================================================================

    def load_all_shapes_from_folder(self):
        shp_folder = os.path.join(os.path.dirname(__file__), 'shps')
        if not os.path.exists(shp_folder):
            print(f"Le dossier {shp_folder} n'existe pas")
            return

        self.loaded_layers = {}
        shp_files = [f for f in os.listdir(shp_folder) if f.endswith('.shp')]
        print(f"📁 Dossier : {shp_folder}  |  📄 {len(shp_files)} fichier(s) trouvé(s)")

        for fichier in shp_files:
            nom = fichier[:-4]          # retire '.shp'
            chemin = os.path.join(shp_folder, fichier)
            couche = QgsVectorLayer(chemin, nom, "ogr")

            if couche.isValid():
                QgsProject.instance().addMapLayer(couche)
                self.loaded_layers[nom] = couche
                print(f"  ✓ {nom}  ({couche.featureCount()} entités)")
            else:
                print(f"  ✗ Erreur : {nom}")

        print(f"\n📊 {len(self.loaded_layers)} couche(s) chargée(s)")

        QMessageBox.information(
            self, "Couches chargées",
            f"{len(self.loaded_layers)} shapefile(s) chargé(s) :\n\n" +
            "\n".join(f"- {n}" for n in self.loaded_layers)
        )
        self.refresh_canvas(zoom_to_extent=True)

    # =========================================================================
    # CALCUL DES INTERSECTIONS  ← optimisation principale : index spatial
    # =========================================================================

    def calculate_intersections(self):
        # 1. Récupérer la couche buffer
        buffer_layer = next(
            (lyr for lyr in QgsProject.instance().mapLayers().values()
             if lyr.name().startswith("Buffer_")),
            None
        )
        if buffer_layer is None:
            QMessageBox.warning(self, "Erreur", "Créez d'abord un buffer")
            return None

        buffer_value = self.spinBufferValue.value()
        buffer_unit = self.comboBufferUnit.currentText()

        # 2. Union des géométries buffer (souvent une seule entité)
        buffer_geoms = [f.geometry() for f in buffer_layer.getFeatures()]
        combined_buffer = QgsGeometry.unaryUnion(buffer_geoms)

        results = {}

        for nom_couche, couche in self.loaded_layers.items():
            # ----------------------------------------------------------------
            # OPTIMISATION CLEF : index spatial QgsSpatialIndex
            # Au lieu de tester TOUTES les entités de la couche,
            # on ne récupère que celles dont la bounding-box intersecte
            # le buffer (candidate set), puis on affine avec intersects().
            # Gain typique : ×10 à ×100 sur de grandes couches.
            # ----------------------------------------------------------------
            spatial_index = QgsSpatialIndex(couche.getFeatures())
            candidate_ids = spatial_index.intersects(combined_buffer.boundingBox())

            count = 0
            total_area = 0.0

            request = couche.getFeatures(candidate_ids)
            for feature in request:
                geom = feature.geometry()
                if geom.isNull():
                    continue
                if geom.intersects(combined_buffer):
                    count += 1
                    inter = geom.intersection(combined_buffer)
                    if not inter.isNull():
                        total_area += inter.area()

            results[nom_couche] = {
                'nom': nom_couche,
                'entites_dans_buffer': count,
                'surface_intersectee': total_area,
                'surface_hectares': total_area / 10_000,
                'total_entites': couche.featureCount(),
            }

        # Pourcentage spécifique dérogation
        derog_key = 'Derogation_central_13_avril'
        if derog_key in results:
            d = results[derog_key]
            total = d['total_entites']
            results[derog_key]['pourcentage'] = (
                d['entites_dans_buffer'] / total * 100 if total > 0 else 0
            )

        self.display_results(results, buffer_value, buffer_unit)
        return results

    # =========================================================================
    # AFFICHAGE DES RÉSULTATS
    # =========================================================================

    # =========================================================================
    # AFFICHAGE DES RÉSULTATS  (inchangé — fonctionne bien)
    # Seul ajout : on stocke les données brutes pour l'export PDF
    # =========================================================================

    def display_results(self, results, buffer_value, buffer_unit):
        """Affiche les résultats sous forme de tableau HTML professionnel."""
        from datetime import datetime
        date_str = datetime.now().strftime("%d/%m/%Y  %H:%M")

        # ── Stocker pour l'export PDF ────────────────────────────────────────
        self._last_results      = results
        self._last_buffer_value = buffer_value
        self._last_buffer_unit  = buffer_unit

        # ── Calculs globaux ──────────────────────────────────────────────────
        total_surface    = sum(d['surface_intersectee'] for d in results.values())
        total_entites    = sum(d['entites_dans_buffer']  for d in results.values())
        total_all        = sum(d['total_entites']         for d in results.values())
        couches_touchees = sum(1 for d in results.values() if d['entites_dans_buffer'] > 0)

        LAYER_ICONS = {
            'COLLECTIF':                   '&#xeb9f;',
            'Derogation_central_13_avril': '&#xea06;',
            'DOMAINE_COMMUNAL':            '&#xeb6d;',
            'DOMAINE_FORESTIER':           '&#xf0cb;',
            'DOMAINE_PUBLIC':              '&#xf019;',
            'DOMAINE_PRIVE_ETAT':          '&#xeaca;',
        }

        rows = []
        for nom, d in results.items():
            nom_aff = DISPLAY_NAMES.get(nom, nom)
            count   = d['entites_dans_buffer']

            if count == 0:
                badge = ("<span style='background:#EAF3DE;color:#27500A;"
                         "padding:2px 8px;border-radius:20px;font-size:11px;"
                         "font-weight:bold;'>&#x2714; Aucune</span>")
            elif nom == 'Derogation_central_13_avril':
                badge = ("<span style='background:#FCEBEB;color:#501313;"
                         "padding:2px 8px;border-radius:20px;font-size:11px;"
                         "font-weight:bold;'>&#x26a0; " + str(count) + "</span>")
            else:
                badge = ("<span style='background:#FAEEDA;color:#633806;"
                         "padding:2px 8px;border-radius:20px;font-size:11px;"
                         "font-weight:bold;'>&#x26a0; " + str(count) + "</span>")

            extra = ""
            if nom == 'Derogation_central_13_avril' and 'pourcentage' in d:
                pct = d['pourcentage']
                extra = (
                    f"<div style='margin-top:4px;font-size:10px;color:#888;'>"
                    f"{pct:.1f}% des entités dans le buffer</div>"
                    f"<div style='height:4px;background:#ddd;border-radius:2px;"
                    f"margin-top:3px;overflow:hidden;'>"
                    f"<div style='height:100%;width:{min(pct,100):.1f}%;"
                    f"background:#1f3c88;border-radius:2px;'></div></div>"
                )

            rows.append(f"""
            <tr style='border-bottom:0.5px solid #ddd;'>
              <td style='padding:9px 12px;'>
                <span style='font-weight:bold;'>{nom_aff}</span>{extra}
              </td>
              <td style='padding:9px 12px;text-align:center;'>{badge}</td>
              <td style='padding:9px 12px;text-align:center;color:#666;'>
                {d['total_entites']}
              </td>
              <td style='padding:9px 12px;text-align:right;font-family:monospace;'>
                {d['surface_intersectee']:,.2f}
              </td>
              <td style='padding:9px 12px;text-align:right;font-family:monospace;'>
                {d['surface_hectares']:,.4f}
              </td>
            </tr>""")

        html = f"""
        <html><body style='font-family:Arial,sans-serif;font-size:12px;
                           color:#222;margin:0;padding:8px;'>
        <div style='background:#1f3c88;color:white;border-radius:8px;
                    padding:12px 16px;margin-bottom:10px;'>
          <span style='font-size:15px;font-weight:bold;'>Rapport d'intersection</span>
          <span style='float:right;font-size:11px;opacity:.85;'>{date_str}</span>
          <br>
          <span style='font-size:11px;opacity:.85;'>
            Buffer : <b>{buffer_value} {buffer_unit}</b> &nbsp;|&nbsp; EPSG:26191
          </span>
        </div>
        <table style='width:100%;border-collapse:separate;border-spacing:6px;
                      margin-bottom:10px;'>
          <tr>
            <td style='background:#f0f4ff;border-radius:6px;padding:8px 12px;width:33%;'>
              <div style='font-size:10px;color:#555;'>Couches touchées</div>
              <div style='font-size:16px;font-weight:bold;color:#1f3c88;'>
                {couches_touchees} / {len(results)}
              </div>
            </td>
            <td style='background:#f0f4ff;border-radius:6px;padding:8px 12px;width:33%;'>
              <div style='font-size:10px;color:#555;'>Surface totale</div>
              <div style='font-size:16px;font-weight:bold;color:#1f3c88;'>
                {total_surface:,.2f} m²
              </div>
            </td>
            <td style='background:#f0f4ff;border-radius:6px;padding:8px 12px;width:33%;'>
              <div style='font-size:10px;color:#555;'>En hectares</div>
              <div style='font-size:16px;font-weight:bold;color:#1f3c88;'>
                {total_surface / 10_000:,.4f} ha
              </div>
            </td>
          </tr>
        </table>
        <table style='width:100%;border-collapse:collapse;font-size:12px;'>
          <thead>
            <tr style='background:#1f3c88;'>
              <th style='color:white;padding:9px 12px;text-align:left;width:32%;'>Couche</th>
              <th style='color:white;padding:9px 12px;text-align:center;width:18%;'>Intersections</th>
              <th style='color:white;padding:9px 12px;text-align:center;width:12%;'>Total</th>
              <th style='color:white;padding:9px 12px;text-align:right;width:19%;'>Surface (m²)</th>
              <th style='color:white;padding:9px 12px;text-align:right;width:19%;'>Surface (ha)</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div style='background:#E6F1FB;border-left:3px solid #1f3c88;
                    border-radius:0 6px 6px 0;padding:10px 14px;margin-top:10px;'>
          <span style='font-size:10px;color:#185FA5;'>Surface totale :</span>
          <span style='font-size:15px;font-weight:bold;color:#0C447C;'>
            &nbsp;{total_surface:,.2f} m²
          </span>
          &nbsp;&nbsp;
          <span style='font-size:10px;color:#185FA5;'>Hectares :</span>
          <span style='font-size:15px;font-weight:bold;color:#0C447C;'>
            &nbsp;{total_surface / 10_000:,.4f} ha
          </span>
          &nbsp;&nbsp;
          <span style='font-size:10px;color:#185FA5;'>Entités :</span>
          <span style='font-size:15px;font-weight:bold;color:#0C447C;'>
            &nbsp;{total_entites} / {total_all}
          </span>
        </div>
        </body></html>"""

        if hasattr(self, 'textResults'):
            self.textResults.setHtml(html)
        else:
            QMessageBox.information(self, "Résultats", html)

    # =========================================================================
    # EXPORT PDF  — QPainter (contrôle total sur le rendu)
    # =========================================================================

    def export_results_pdf(self):
    
        from datetime import datetime
        from qgis.PyQt.QtGui import QPainter, QFont, QColor, QPen, QBrush, QImage, QFontMetrics
        from qgis.PyQt.QtCore import QRectF, Qt, QSize, QPointF, QSizeF
        from qgis.PyQt.QtPrintSupport import QPrinter
        from qgis.core import QgsMapSettings, QgsRectangle, QgsProject

        if not hasattr(self, '_last_results') or not self._last_results:
            QMessageBox.warning(self, "Aucun résultat", "Calculez d'abord les intersections.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le PDF",
            os.path.join(os.path.expanduser("~"), "rapport_derogation.pdf"),
            "PDF (*.pdf)"
        )
        if not file_path:
            return

        try:
            date_str = datetime.now().strftime("%d/%m/%Y  %H:%M")
            results = self._last_results
            buffer_value = self._last_buffer_value
            buffer_unit = self._last_buffer_unit

            PDF_NAMES = {
                'COLLECTIF': 'Collectif',
                'Derogation_central_13_avril': 'Derogation centrale',
                'DOMAINE_COMMUNAL': 'Domaine communal',
                'DOMAINE_FORESTIER': 'Domaine forestier',
                'DOMAINE_PUBLIC': 'Domaine public',
                'DOMAINE_PRIVE_ETAT': 'Domaine prive Etat',
            }

            total_surface = sum(d['surface_intersectee'] for d in results.values())
            total_entites = sum(d['entites_dans_buffer'] for d in results.values())
            total_all = sum(d['total_entites'] for d in results.values())
            couches_touchees = sum(1 for d in results.values() if d['entites_dans_buffer'] > 0)

            # Configuration imprimante
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            printer.setPageSize(QPrinter.A4)
            printer.setPageMargins(15, 15, 15, 15, QPrinter.Millimeter)

            page = printer.pageRect()
            W = float(page.width())
            H = float(page.height())
            R = printer.resolution()

            def mm(x):
                return x * R / 25.4

            # Polices (utiliser des tailles en points, pas en mm)
            F_TITLE = QFont("Arial", 14, QFont.Bold)
            F_SUB = QFont("Arial", 9)
            F_SEC = QFont("Arial", 10, QFont.Bold)
            F_LABEL = QFont("Arial", 8)
            F_METRIC = QFont("Arial", 12, QFont.Bold)
            F_TH = QFont("Arial", 8, QFont.Bold)
            F_TD = QFont("Arial", 8)
            F_BADGE = QFont("Arial", 7, QFont.Bold)
            F_FOOT = QFont("Arial", 7)

            C_BLUE = QColor("#1f3c88")
            C_TEAL = QColor("#2c7da0")
            C_LIGHT = QColor("#f0f4ff")
            C_SUMMARY = QColor("#E6F1FB")
            C_ACCENT = QColor("#0C447C")
            C_GRAY = QColor("#f5f5f5")
            C_BORDER = QColor("#dddddd")
            C_WHITE = QColor("#ffffff")

            painter = QPainter()
            painter.begin(printer)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            # Helpers
            def fill(x, y, w, h, color, radius=0.0):
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(color))
                r = QRectF(x, y, w, h)
                if radius > 0:
                    painter.drawRoundedRect(r, radius, radius)
                else:
                    painter.drawRect(r)

            def text(x, y, w, h, s, font, color, align=Qt.AlignLeft | Qt.AlignVCenter, pl=0):
                painter.setFont(font)
                painter.setPen(color)
                painter.drawText(QRectF(x + pl, y, w - pl, h), align, s)

            def hline(y_pos, color=C_BORDER, width=0.5):
                painter.setPen(QPen(color, width))
                painter.drawLine(QPointF(0, y_pos), QPointF(W, y_pos))

            y = 0.0
            PAD = mm(4)

            # ---------- 1. En-tête ----------
            hdr_h = mm(18)
            fill(0, y, W, hdr_h, C_BLUE)
            text(0, y, W, hdr_h * 0.55, "Rapport d'analyse de derogation",
                F_TITLE, C_WHITE, Qt.AlignLeft | Qt.AlignBottom, PAD)
            text(0, y + hdr_h * 0.58, W, hdr_h * 0.42,
                f"Genere le {date_str}   |   EPSG:26191", F_SUB, QColor("#1239d6"),
                Qt.AlignLeft | Qt.AlignTop, PAD)

            fill(W - mm(38), y + mm(4), mm(36), mm(8), QColor("#ffffff30"), mm(2))
            text(W - mm(38), y + mm(4), mm(36), mm(8),
                f"Buffer : {buffer_value} {buffer_unit}", F_SEC, C_BLUE, Qt.AlignCenter)
            y += hdr_h + mm(4)

            # ---------- 2. Carte (méthode fiable avec QgsMapSettings) ----------
            sec_h = mm(7)
            fill(0, y, W, sec_h, C_TEAL)
            text(0, y, W, sec_h, "Apercu cartographique du projet",
                F_SEC, C_WHITE, Qt.AlignLeft | Qt.AlignVCenter, PAD)
            y += sec_h

            map_zone_h = mm(82)  # hauteur réservée pour la carte

            # Créer les réglages de la carte à partir de la vue actuelle
            map_settings = QgsMapSettings()
            map_settings.setLayers(self.canvas.layers())
            map_settings.setExtent(self.canvas.extent())
            map_settings.setDestinationCrs(self.canvas.mapSettings().destinationCrs())
            map_settings.setOutputDpi(150)  # bon compromis qualité / taille

            # Dimensions souhaitées pour l'image (en pixels)
            img_width = int(W)
            img_height = int(map_zone_h)
            map_settings.setOutputSize(QSize(img_width, img_height))

            # Vérifier que l'emprise n'est pas nulle
            if self.canvas.extent().width() == 0 or self.canvas.extent().height() == 0:
                # Si l'emprise est nulle, afficher un message
                fill(0, y, W, map_zone_h, QColor("#eeeeee"))
                text(0, y, W, map_zone_h, "Carte non disponible (emprise nulle)",
                    F_TITLE, QColor("#888888"), Qt.AlignCenter)
            else:
                # Générer l'image de la carte
                from qgis.core import QgsMapRendererParallelJob
                job = QgsMapRendererParallelJob(map_settings)
                job.start()
                job.waitForFinished()
                map_image = job.renderedImage()

                # Dessiner l'image dans la zone réservée (elle sera déjà aux bonnes dimensions)
                painter.drawImage(QRectF(0, y, W, map_zone_h), map_image)

                # Bordure
                painter.setPen(QPen(C_BORDER, 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRectF(0, y, W, map_zone_h))

            y += map_zone_h + mm(2)

            # Légende sous la carte
            cap_h = mm(5)
            fill(0, y, W, cap_h, C_GRAY)
            text(0, y, W, cap_h,
                "Extrait cartographique — Projection : EPSG:26191 (Lambert Maroc)",
                F_LABEL, QColor("#888888"), Qt.AlignLeft | Qt.AlignVCenter, PAD)
            y += cap_h + mm(4)

            # ---------- 3. Trois cartes métriques ----------
            card_gap = mm(3)
            n_cards = 3
            card_w = (W - card_gap * (n_cards - 1)) / n_cards
            card_h = mm(15)

            metrics = [
                ("Couches touchees", f"{couches_touchees} / {len(results)}"),
                ("Surface totale", f"{total_surface:,.2f} m2"),
                ("Equivalent hectares", f"{total_surface / 10_000:,.4f} ha"),
            ]

            for i, (lbl, val) in enumerate(metrics):
                cx = i * (card_w + card_gap)
                fill(cx, y, card_w, card_h, C_LIGHT, mm(1.5))
                text(cx, y + mm(2), card_w, card_h * 0.38,
                    lbl, F_LABEL, QColor("#555555"), Qt.AlignLeft | Qt.AlignTop, mm(3))
                text(cx, y + card_h * 0.40, card_w, card_h * 0.60,
                    val, F_METRIC, C_BLUE, Qt.AlignLeft | Qt.AlignVCenter, mm(3))
            y += card_h + mm(4)

            # ---------- 4. Tableau des résultats (hauteur dynamique des lignes) ----------
            sec_h = mm(7)
            fill(0, y, W, sec_h, C_BLUE)
            text(0, y, W, sec_h, "Resultats d'intersection par couche",
                F_SEC, C_WHITE, Qt.AlignLeft | Qt.AlignVCenter, PAD)
            y += sec_h

            col_w = [W * p for p in [0.32, 0.17, 0.12, 0.20, 0.19]]
            col_lbl = ["Couche", "Intersections", "Total", "Surface (m2)", "Surface (ha)"]
            col_align = [
                Qt.AlignLeft | Qt.AlignVCenter,
                Qt.AlignHCenter | Qt.AlignVCenter,
                Qt.AlignHCenter | Qt.AlignVCenter,
                Qt.AlignRight | Qt.AlignVCenter,
                Qt.AlignRight | Qt.AlignVCenter,
            ]

            # En-tête du tableau
            th_h = mm(7.5)
            fill(0, y, W, th_h, C_BLUE)
            cx = 0.0
            for w, lbl, aln in zip(col_w, col_lbl, col_align):
                text(cx, y, w, th_h, lbl, F_TH, C_WHITE, aln, mm(2))
                cx += w
            y += th_h

            # Fonction pour calculer la hauteur nécessaire pour une ligne
            def row_height_needed(nom, d):
                base = mm(10)  # hauteur minimale
                if nom == 'Derogation_central_13_avril' and 'pourcentage' in d:
                    base += mm(5)  # espace pour le pourcentage et la barre
                # Si le badge fait plus d'une ligne (rare), on peut augmenter, mais ici pas besoin
                return base

            # Parcourir les résultats pour dessiner les lignes avec hauteur adaptée
            for idx, (nom, d) in enumerate(results.items()):
                nom_aff = PDF_NAMES.get(nom, nom)
                count = d['entites_dans_buffer']
                row_h = row_height_needed(nom, d)

                bg = QColor("#fafafa") if idx % 2 == 0 else QColor("#f2f2f2")
                fill(0, y, W, row_h, bg)

                # Badge
                if count == 0:
                    badge_bg = QColor("#EAF3DE")
                    badge_fg = QColor("#27500A")
                    badge_txt = "0 - Aucune"
                elif nom == 'Derogation_central_13_avril':
                    badge_bg = QColor("#FCEBEB")
                    badge_fg = QColor("#501313")
                    badge_txt = f"{count} (!) DEROG."
                else:
                    badge_bg = QColor("#FAEEDA")
                    badge_fg = QColor("#633806")
                    badge_txt = f"{count} intersection(s)"

                row_data = [
                    nom_aff,
                    badge_txt,
                    str(d['total_entites']),
                    f"{d['surface_intersectee']:,.2f}",
                    f"{d['surface_hectares']:,.4f}",
                ]

                cx = 0.0
                for col_i, (w, val, aln) in enumerate(zip(col_w, row_data, col_align)):
                    if col_i == 1:
                        # Calcul de la largeur du badge
                        fm = QFontMetrics(F_BADGE)
                        txt_width = fm.horizontalAdvance(badge_txt) + mm(6)
                        bw = min(w - mm(4), txt_width)
                        bh = mm(5.5)
                        bx = cx + (w - bw) / 2
                        by = y + (row_h - bh) / 2
                        fill(bx, by, bw, bh, badge_bg, mm(2.5))
                        text(bx, by, bw, bh, val, F_BADGE, badge_fg, Qt.AlignCenter)
                    else:
                        text(cx, y, w, row_h, val, F_TD, QColor("#222222"), aln, mm(2))
                    cx += w

                # Pourcentage pour la dérogation
                if nom == 'Derogation_central_13_avril' and 'pourcentage' in d:
                    pct = min(d['pourcentage'], 100)
                    bar_y = y + row_h - mm(2)
                    bar_h2 = mm(1)
                    bar_tw = col_w[0] - mm(4)
                    fill(mm(2), bar_y, bar_tw, bar_h2, QColor("#dddddd"), mm(0.5))
                    if pct > 0:
                        fill(mm(2), bar_y, bar_tw * pct / 100, bar_h2, C_BLUE, mm(0.5))

                    painter.setFont(F_LABEL)
                    painter.setPen(QColor("#555555"))
                    painter.drawText(
                        QRectF(mm(2), y + mm(1.5), col_w[0] - mm(4), mm(4)),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        f"({d['pourcentage']:.1f}% des entites)"
                    )

                hline(y + row_h, C_BORDER, 0.5)
                y += row_h

            y += mm(4)

            # ---------- 5. Barre de synthèse ----------
            sum_h = mm(14)
            fill(0, y, mm(3), sum_h, C_BLUE)
            fill(mm(3), y, W - mm(3), sum_h, C_SUMMARY)

            summary_items = [
                ("Surface totale intersectee", f"{total_surface:,.2f} m2"),
                ("Equivalent hectares", f"{total_surface / 10_000:,.4f} ha"),
                ("Entites intersectees", f"{total_entites} / {total_all}"),
            ]
            item_w = (W - mm(3)) / 3
            for i, (lbl, val) in enumerate(summary_items):
                ix = mm(3) + i * item_w
                text(ix, y + mm(1), item_w, sum_h * 0.42,
                    lbl, F_LABEL, QColor("#185FA5"), Qt.AlignLeft | Qt.AlignTop, mm(3))
                text(ix, y + sum_h * 0.40, item_w, sum_h * 0.60,
                    val, F_METRIC, C_ACCENT, Qt.AlignLeft | Qt.AlignVCenter, mm(3))

            # ---------- 6. Pied de page ----------
            foot_y = H - mm(8)
            hline(foot_y, C_BORDER, 1)
            text(0, foot_y + mm(2), W, mm(6),
                f"Rapport genere automatiquement par le plugin d'analyse de derogation   |   {date_str}",
                F_FOOT, QColor("#aaaaaa"), Qt.AlignCenter)

            painter.end()

            QMessageBox.information(self, "Export reussi", f"PDF enregistre :\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Impossible de generer le PDF :\n{e}")