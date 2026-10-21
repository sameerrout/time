from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QPushButton
from PySide6.QtCore import Qt


class PlaceholderModuleView(QWidget):
    """Informative placeholder view for modules slated for subsequent checkpoints."""

    def __init__(self, module_num: int, title: str, description: str, next_checkpoint: str, parent=None):
        super().__init__(parent)
        self.init_ui(module_num, title, description, next_checkpoint)

    def init_ui(self, module_num: int, title: str, description: str, next_checkpoint: str):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)

        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedWidth(640)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)
        card_layout.setContentsMargins(30, 30, 30, 30)

        badge = QLabel(f"MODULE {module_num} • {next_checkpoint}")
        badge.setStyleSheet("""
            background-color: #dbeafe;
            color: #1d4ed8;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 4px;
        """)
        badge.setFixedWidth(180)
        card_layout.addWidget(badge)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")
        card_layout.addWidget(lbl_title)

        lbl_desc = QLabel(description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 13px; color: #475569; line-height: 1.4;")
        card_layout.addWidget(lbl_desc)

        info_box = QFrame()
        info_box.setStyleSheet("background-color: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 12px;")
        info_box_layout = QVBoxLayout(info_box)
        info_label = QLabel(
            "🔒 <b>Checkpoint Guard:</b> This module is strictly scheduled for the next development phase.\n"
            "Following the project protocol, this module will be implemented and tested after the current checkpoint is verified."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #64748b; font-size: 12px;")
        info_box_layout.addWidget(info_label)
        card_layout.addWidget(info_box)

        layout.addWidget(card)
