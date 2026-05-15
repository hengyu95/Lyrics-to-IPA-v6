from PyQt5.QtWidgets import QApplication, QTextEdit

app = QApplication([])
editor = QTextEdit()
editor.setOpenExternalLinks(False)  # Test setting without subclassing
editor.show()
app.exec_()