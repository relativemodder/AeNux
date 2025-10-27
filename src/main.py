import os
import sys
from PyQt6.QtWidgets import QApplication, QMessageBox
from app import AeNuxApp
from dependency_checker import check_dependencies


if __name__ == "__main__":
    if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    missing_deps = check_dependencies()

    app = QApplication(sys.argv)

    if len(missing_deps) > 0:
        QMessageBox().critical(
            None, 
            "Missing dependencies!", 
            f"Install these: {', '.join(missing_deps)}.\n\n Use your distro's package manager."
        )
        exit(-1)
    
    win = AeNuxApp()
    win.show()
    sys.exit(app.exec())
