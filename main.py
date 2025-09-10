import sys
from PySide6.QtWidgets import QApplication # type: ignore
from app import WelcomeScreen

if __name__ == "__main__":
    app = QApplication(sys.argv)
    welcome = WelcomeScreen()
    welcome.show()
    sys.exit(app.exec())
