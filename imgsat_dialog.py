from qgis.PyQt import uic, QtWidgets
import os

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'imgsat_dialog.ui')
)

class ImgSatDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)