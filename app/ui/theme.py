"""
Modern Light Theme for Industrial Warehouse Desktop Application.
Clean, uncluttered, professional Windows aesthetic with high-contrast typography,
subtle borders, and restrained industrial blue accents.
"""

MODERN_LIGHT_QSS = """
/* Global Window & Fonts */
QWidget {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
    font-size: 13px;
    color: #0f172a;
    background-color: transparent;
}

QMainWindow {
    background-color: #f8fafc;
}

/* Main Top Header */
#appHeaderBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    min-height: 64px;
    max-height: 64px;
}

#companyTitleLabel {
    font-size: 16px;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.2px;
}

#systemNameLabel {
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
    margin-top: 1px;
}

#statusBadgeOnline {
    background-color: #f0fdf4;
    color: #15803d;
    border: 1px solid #bbf7d0;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

/* Header Buttons */
QPushButton.header-btn {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 7px 14px;
    color: #334155;
    font-size: 12px;
    font-weight: 600;
}

QPushButton.header-btn:hover {
    background-color: #f1f5f9;
    border-color: #cbd5e1;
    color: #0f172a;
}

/* Navigation Back Button */
QPushButton.btn-back {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    color: #1e293b;
    font-weight: 600;
    font-size: 13px;
}

QPushButton.btn-back:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
    color: #0f172a;
}

/* Hero Section */
#heroTitleLabel {
    font-size: 24px;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.4px;
}

#heroSubtitleLabel {
    font-size: 14px;
    color: #64748b;
    margin-top: 4px;
}

/* Module Primary Action Cards */
QFrame.module-card {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 24px;
}

QFrame.module-card:hover {
    border: 1.5px solid #2563eb;
    background-color: #ffffff;
}

#cardTitleLabel {
    font-size: 17px;
    font-weight: 700;
    color: #0f172a;
    margin-top: 14px;
}

#cardDescLabel {
    font-size: 13px;
    color: #64748b;
    line-height: 1.4;
    margin-top: 6px;
}

/* Primary Action Buttons inside Cards */
QPushButton.btn-card-action {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton.btn-card-action:hover {
    background-color: #1d4ed8;
}

QPushButton.btn-card-action:pressed {
    background-color: #1e40af;
}

/* Standard Buttons */
QPushButton {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
}

QPushButton:pressed {
    background-color: #e2e8f0;
}

QPushButton.btn-primary {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
}

QPushButton.btn-primary:hover {
    background-color: #1d4ed8;
}

/* Input Fields */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    color: #0f172a;
    font-size: 13px;
    selection-background-color: #2563eb;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 2px solid #2563eb;
}

/* GroupBox & Form Containers */
QGroupBox {
    font-size: 13px;
    font-weight: 700;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    margin-top: 16px;
    padding-top: 16px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 14px;
    color: #0f172a;
}

/* Minimal Modern Status Bar */
QStatusBar {
    background-color: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
    min-height: 32px;
}

QStatusBar QLabel {
    color: #64748b;
    padding: 0 10px;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background: #f8fafc;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
"""
