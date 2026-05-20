from qgis.PyQt import uic, QtWidgets
import os

from qgis.core import QgsCoordinateReferenceSystem


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
    #branch

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





        self.load_all_shapes_from_folder()
    
        # Identifier les types de couches (optionnel)
        self.identify_layers()

        self.btnCalculerIntersections.clicked.connect(self.calculate_intersections)

       
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

        crs = layer.crs()
        

        # Forcer le CRS de la couche
        layer.setCrs(QgsCoordinateReferenceSystem("EPSG:26191"))

        # Vérification
        crs = layer.crs()

        if not crs.isValid():

            QMessageBox.warning(
                self,
                "CRS",
                "CRS invalide"
            )

            return

        if crs.postgisSrid() != 26191:

            QMessageBox.warning(
                self,
                "CRS",
                "La couche doit être en EPSG:26191"
            )

            return

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
    









    def load_all_shapes_from_folder(self):
        """Charge tous les shapefiles du dossier 'shps'"""
        
        # Chemin du dossier shps
        shp_folder = os.path.join(os.path.dirname(__file__), 'shps')
        
        if not os.path.exists(shp_folder):
            print(f"Le dossier {shp_folder} n'existe pas")
            return
        
        # Nettoyer les anciennes couches
        self.loaded_layers = {}
        
        # Liste de tous les fichiers .shp dans le dossier
        shp_files = [f for f in os.listdir(shp_folder) if f.endswith('.shp')]
        
        print(f"📁 Dossier trouvé : {shp_folder}")
        print(f"📄 Shapefiles trouvés : {len(shp_files)}")
        
        for fichier in shp_files:
            chemin_complet = os.path.join(shp_folder, fichier)
            nom_couche = fichier.replace('.shp', '')
            
            # Charger la couche
            couche = QgsVectorLayer(chemin_complet, nom_couche, "ogr")
            
            if couche.isValid():
                QgsProject.instance().addMapLayer(couche)
                self.loaded_layers[nom_couche] = couche
                print(f"✓ Chargé : {nom_couche} ({couche.featureCount()} entités)")
            else:
                print(f"✗ Erreur : {nom_couche}")
        
        # Afficher un résumé
        print(f"\n📊 Résumé : {len(self.loaded_layers)} couches chargées")
        
        # Optionnel : afficher une boîte de message
        QMessageBox.information(
            self,
            "Couches chargées",
            f"{len(self.loaded_layers)} shapefiles chargés avec succès\n\n" +
            "\n".join([f"- {nom}" for nom in self.loaded_layers.keys()])
        )
        
        self.refresh_canvas()

    
    def identify_layers(self):
        """Identifie quel type de couche est chaque shapefile"""
        
        layer_types = {
            'COLLECTIF': 'collectif',
            'Derogation_central_13_avril': 'derogation',
            'DOMAINE_COMMUNAL': 'communal',
            'DOMAINE_FORESTIER': 'forestier',
            'DOMAINE_PUBLIC': 'public',
            'DOMAINE_PRIVE_ETAT': 'prive_etat'
        }
        
        classified_layers = {
            'collectif': None,
            'derogation': None,
            'communal': None,
            'forestier': None,
            'public': None,
            'prive_etat': None
        }
        
        for nom, couche in self.loaded_layers.items():
            for key, value in layer_types.items():
                if key == nom:
                    classified_layers[value] = couche
                    print(f"🔍 Identifié : {nom} → {value}")
                    break
        
        return classified_layers
    


    def calculate_intersections(self):
        """Calcule les intersections entre le buffer et TOUTES les couches chargées"""
        
        # Récupérer le buffer
        buffer_layer = None
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name().startswith("Buffer_"):
                buffer_layer = layer
                break
        
        if buffer_layer is None:
            QMessageBox.warning(self, "Erreur", "Créez d'abord un buffer")
            return None
        
        # Récupérer la valeur du buffer
        buffer_value = self.spinBufferValue.value()
        buffer_unit = self.comboBufferUnit.currentText()
        
        results = {}
        
        # Analyser CHAQUE couche chargée
        for nom_couche, couche in self.loaded_layers.items():
            count = 0
            surface = 0
            
            for feature in couche.getFeatures():
                geom = feature.geometry()
                if geom.isNull():
                    continue
                
                for buffer_feature in buffer_layer.getFeatures():
                    buffer_geom = buffer_feature.geometry()
                    
                    if geom.intersects(buffer_geom):
                        count += 1
                        intersection = geom.intersection(buffer_geom)
                        if not intersection.isNull():
                            surface += intersection.area()
                        break
            
            results[nom_couche] = {
                'nom': nom_couche,
                'entites_dans_buffer': count,
                'surface_intersectee': surface,
                'surface_hectares': surface / 10000,
                'total_entites': couche.featureCount()
            }
        
        # Calcul spécial pour la couche de dérogation
        if 'Derogation_central_13_avril' in results:
            derog_data = results['Derogation_central_13_avril']
            total_derog = derog_data['total_entites']
            in_buffer = derog_data['entites_dans_buffer']
            results['Derogation_central_13_avril']['pourcentage'] = (in_buffer / total_derog * 100) if total_derog > 0 else 0
        
        # Afficher les résultats
        self.display_results(results, buffer_value, buffer_unit)
        
        return results
    
    def display_results(self, results, buffer_value, buffer_unit):
        """Affiche les résultats avec les noms de vos shapefiles"""
        
        html = f"""
        <style>
            .title {{ color: #1f3c88; font-size: 14px; font-weight: bold; }}
            .success {{ color: green; }}
            .warning {{ color: orange; }}
            .error {{ color: red; }}
            .value {{ font-weight: bold; color: #1f3c88; }}
        </style>
        
        <div>
            <h3 class='title'>📊 Résultats d'intersection</h3>
            <p><b>Buffer:</b> <span class='value'>{buffer_value} {buffer_unit}</span></p>
            <hr>
        """
        
        total_surface = 0
        total_entites = 0
        
        # Noms d'affichage plus lisibles
        display_names = {
            'COLLECTIF': '🏘️ Collectif',
            'Derogation_central_13_avril': '⚠️ Dérogation centrale',
            'DOMAINE_COMMUNAL': '🏛️ Domaine communal',
            'DOMAINE_FORESTIER': '🌲 Domaine forestier',
            'DOMAINE_PUBLIC': '🏢 Domaine public',
            'DOMAINE_PRIVE_ETAT': '🏠 Domaine privé État'
        }
        
        for nom, data in results.items():
            total_surface += data['surface_intersectee']
            total_entites += data['entites_dans_buffer']
            
            # Nom affichable
            nom_affichable = display_names.get(nom, nom)
            
            # Ajouter le pourcentage pour la dérogation
            pourcentage_html = ""
            if nom == 'Derogation_central_13_avril' and 'pourcentage' in data:
                pourcentage_html = f"<br>- 📊 Pourcentage: <span class='value'>{data['pourcentage']:.1f}%</span>"
            
            html += f"""
            <div>
                <b>{nom_affichable}:</b><br>
                - 🎯 Entités dans buffer: <span class='value'>{data['entites_dans_buffer']} / {data['total_entites']}</span><br>
                - 📐 Surface intersectée: <span class='value'>{data['surface_intersectee']:.2f} m²</span> ({data['surface_hectares']:.2f} ha){pourcentage_html}
            </div>
            <br>
            """
        
        html += f"""
            <hr>
            <div class='title'>📈 TOTAL GÉNÉRAL:</div>
            - 🌍 Surface totale intersectée: <span class='value'>{total_surface:.2f} m²</span> ({total_surface/10000:.2f} ha)<br>
            - 🎯 Nombre total d'entités: <span class='value'>{total_entites}</span>
        </div>
        """
        
        # Afficher dans le widget
        if hasattr(self, 'textResults'):
            self.textResults.setHtml(html)
        else:
            QMessageBox.information(self, "Résultats", html)