from qgis.PyQt import uic, QtWidgets
import os

from qgis.core import QgsFillSymbol

from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QVBoxLayout
)

from qgis.PyQt.QtCore import Qt

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY
)

from qgis.gui import QgsMapCanvas

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(
        os.path.dirname(__file__),
        'derogation_dialog.ui'
    )
)


class DerogationDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setupUi(self)

        
        # CREATE REAL MAP CANVAS
        
        self.canvas = QgsMapCanvas()

        self.canvas.setCanvasColor(Qt.white)

        self.canvas.enableAntiAliasing(True)

        # INSERT CANVAS INTO PLACEHOLDER
        self.canvas_layout = QVBoxLayout(self.mapCanvasWidget)

        self.canvas_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas_layout.addWidget(self.canvas)

       
        # VARIABLES
    
        self.project_layer = None

        # =========================
        # SIGNALS
        # =========================

        self.btnImportShp.clicked.connect(
            self.import_shp
        )

        self.btnAfficherProjet.clicked.connect(
            self.display_project
        )

        self.radioPointWizard.toggled.connect(
            self.toggle_input_mode
        )

        # =========================
        # INITIAL STATE
        # =========================

        self.radioPointWizard.setChecked(True)

        self.toggle_input_mode()

    # =====================================================
    # TOGGLE INPUT MODE
    # =====================================================

    def toggle_input_mode(self):

        is_point = self.radioPointWizard.isChecked()

        self.lineXWizard.setEnabled(is_point)

        self.lineYWizard.setEnabled(is_point)

        self.btnImportShp.setEnabled(not is_point)

    # =====================================================
    # IMPORT SHP
    # =====================================================

    def import_shp(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir shapefile",
            "",
            "Shapefile (*.shp)"
        )

        if not path:
            return

        layer = QgsVectorLayer(
            path,
            "Projet",
            "ogr"
        )

        if not layer.isValid():

            QMessageBox.warning(
                self,
                "Erreur",
                "Couche invalide"
            )

            return

        # Vérification CRS
        """if layer.crs().authid() != "EPSG:26191":

            QMessageBox.warning(
                self,
                "CRS",
                "Le projet doit être en EPSG:26191"
            )

            return""" 

        self.project_layer = layer

        QgsProject.instance().addMapLayer(layer)

        self.refresh_canvas()

    # =====================================================
    # CREATE PROJECT POINT
    # =====================================================

    def create_project_point(self):

        try:

            x = float(self.lineXWizard.text())

            y = float(self.lineYWizard.text())

        except:

            QMessageBox.warning(
                self,
                "Erreur",
                "Coordonnées invalides"
            )

            return None

        layer = QgsVectorLayer(
            "Point?crs=EPSG:26191",
            "Projet_Point",
            "memory"
        )

        provider = layer.dataProvider()

        feat = QgsFeature()

        point = QgsPointXY(x, y)

        feat.setGeometry(
            QgsGeometry.fromPointXY(point)
        )

        provider.addFeature(feat)

        layer.updateExtents()

        return layer

    # =====================================================
    # DISPLAY PROJECT
    # =====================================================

    def display_project(self):

        # CAS POINT
        if self.radioPointWizard.isChecked():

            layer = self.create_project_point()

            if layer is None:
                return

            self.project_layer = layer

            QgsProject.instance().addMapLayer(layer)

        # CAS SHP
        elif self.radioShpWizard.isChecked():

            if self.project_layer is None:

                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Importer un SHP"
                )

                return

        # CRÉER ET AFFICHER LE BUFFER AUTOUR DE L'OBJET
        self.create_buffer_layer()

        self.refresh_canvas()

    # =====================================================
    # REFRESH CANVAS
    # =====================================================

    def refresh_canvas(self):

        layers = list(
            QgsProject.instance().mapLayers().values()
        )

        self.canvas.setLayers(layers)

        self.canvas.zoomToFullExtent()

        self.canvas.refresh()


    def create_buffer_layer(self):
        """Crée une couche buffer autour du point ou du shapefile importé"""
        
        # Récupérer la valeur du buffer en mètres
        buffer_value = self.spinBufferValue.value()
        buffer_unit = self.comboBufferUnit.currentText()
        
        # Convertir en mètres si nécessaire
        if buffer_unit == "km":
            buffer_distance = buffer_value * 1000
        else:
            buffer_distance = buffer_value
        
        if buffer_distance <= 0:
            QMessageBox.warning(
                self,
                "Erreur",
                "La distance du buffer doit être supérieure à 0"
            )
            return None
        
        # SUPPRIMER L'ANCIEN BUFFER S'IL EXISTE
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name().startswith("Buffer_"):
                QgsProject.instance().removeMapLayer(layer.id())
        
        # Créer une couche mémoire pour le buffer
        buffer_layer = QgsVectorLayer(
            "Polygon?crs=EPSG:26191",
            f"Buffer_{buffer_distance}m",
            "memory"
        )
        
        if not buffer_layer.isValid():
            QMessageBox.warning(
                self,
                "Erreur",
                "Impossible de créer la couche buffer"
            )
            return None
        
        provider = buffer_layer.dataProvider()
        features_to_buffer = []
        
        # CAS 1: Point projet
        if self.radioPointWizard.isChecked():
            try:
                x = float(self.lineXWizard.text())
                y = float(self.lineYWizard.text())
                point = QgsPointXY(x, y)
                point_geometry = QgsGeometry.fromPointXY(point)
                
                # Créer le buffer autour du point
                buffer_geometry = point_geometry.buffer(buffer_distance, 20)
                
                if not buffer_geometry.isNull():
                    feat = QgsFeature()
                    feat.setGeometry(buffer_geometry)
                    features_to_buffer.append(feat)
                    
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Coordonnées du point invalides"
                )
                return None
        
        # CAS 2: Shapefile importé
        elif self.radioShpWizard.isChecked():
            if self.project_layer is None:
                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Aucun shapefile importé"
                )
                return None
            
            # Parcourir toutes les entités du shapefile
            for feature in self.project_layer.getFeatures():
                geom = feature.geometry()
                
                if not geom.isNull():
                    # Convertir la géométrie en une seule entité si multi-parties
                    if geom.isMultipart():
                        # Rassembler toutes les parties
                        single_geom = geom.mergeLines()
                        buffer_geometry = single_geom.buffer(buffer_distance, 20)
                    else:
                        # Créer le buffer autour de la géométrie
                        buffer_geometry = geom.buffer(buffer_distance, 20)
                    
                    if not buffer_geometry.isNull():
                        feat = QgsFeature()
                        feat.setGeometry(buffer_geometry)
                        features_to_buffer.append(feat)
            
            if not features_to_buffer:
                QMessageBox.warning(
                    self,
                    "Erreur",
                    "Aucune géométrie valide trouvée pour créer le buffer"
                )
                return None
        
        # Ajouter les features à la couche buffer
        provider.addFeatures(features_to_buffer)
        buffer_layer.updateExtents()
        
        # Ajouter la couche buffer au projet (au-dessus de la couche source)
        QgsProject.instance().addMapLayer(buffer_layer)
        
        # Style pour le buffer (transparent avec contour rouge)
        
        
        symbol = QgsFillSymbol.createSimple({
            'color': 'rgba(255, 0, 0, 0.2)',  # Rouge transparent
            'outline_color': 'red',
            'outline_width': '0.5',
            'outline_style': 'solid'
        })
        buffer_layer.renderer().setSymbol(symbol)
        buffer_layer.triggerRepaint()
        
        # Afficher un message de succès
        QMessageBox.information(
            self,
            "Buffer créé",
            f"Buffer de {buffer_value} {buffer_unit} créé autour de l'objet\n"
            f"({len(features_to_buffer)} entité(s) traitée(s))"
        )
        
        return buffer_layer