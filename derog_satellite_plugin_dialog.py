
import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

from .derogation_dialog import DerogationDialog
from .imgsat_dialog import ImgSatDialog

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'derog_satellite_plugin_dialog_base.ui'))


class DerogSatellitePluginDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(DerogSatellitePluginDialog, self).__init__(parent)
        
        self.setupUi(self)

        self.btnDerogation.clicked.connect(self.openDerogation)

        self.btnSat.clicked.connect(self.openSat)

    def openDerogation(self):
        self.window_derogation = DerogationDialog()
        self.window_derogation.show()

    def openSat(self):
        self.window_imgsat = ImgSatDialog()
        self.window_imgsat.show()
