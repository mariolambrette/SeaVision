"""
Style sheet strings for validation GUI buttons.
"""

# --- Main review action buttons ---
_BUTTON_STYLE_CONFIRM = """
    QPushButton {
        background-color: #2d7a4d;
        color: white;
        padding: 8px 16px;
        font-weight: bold;
        border: 1px solid #1e5a35;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #359a5d;
    }
    QPushButton:pressed {
        background-color: #1e5a35;
    }
    QPushButton:disabled {
        background-color: #3a3a3a;
        color: #777;
        border-color: #333;
    }
    QPushButton:focus {
        border: 2px solid #5dba7d;
    }
"""

_BUTTON_STYLE_REJECT = """
    QPushButton {
        background-color: #a03030;
        color: white;
        padding: 8px 16px;
        font-weight: bold;
        border: 1px solid #7a2020;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #c04040;
    }
    QPushButton:pressed {
        background-color: #7a2020;
    }
    QPushButton:disabled {
        background-color: #3a3a3a;
        color: #777;
        border-color: #333;
    }
    QPushButton:focus {
        border: 2px solid #e06060;
    }
"""

_BUTTON_STYLE_SKIP = """
    QPushButton {
        background-color: #4a4a4a;
        color: #ddd;
        padding: 8px 16px;
        font-weight: bold;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #5a5a5a;
    }
    QPushButton:pressed {
        background-color: #3a3a3a;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #555;
        border-color: #222;
    }
    QPushButton:focus {
        border: 2px solid #7a7a7a;
    }
"""

_BUTTON_STYLE_ADD = """
    QPushButton {
        background-color: #2d6da8;
        color: white;
        padding: 8px 16px;
        border: 1px solid #1e4a7a;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #3d8dc8;
    }
    QPushButton:pressed {
        background-color: #1e4a7a;
    }
    QPushButton:disabled {
        background-color: #3a3a3a;
        color: #777;
        border-color: #333;
    }
    QPushButton:checked {
        background-color: #1a4a7a;
        border: 2px solid #88bbee;
    }
    QPushButton:focus {
        border: 2px solid #6daddd;
    }
"""


class ReviewButtonStyles:
    """Predefined styles for the main review action buttons."""

    def __init__(self):
        self.confirm = _BUTTON_STYLE_CONFIRM
        self.reject = _BUTTON_STYLE_REJECT
        self.skip = _BUTTON_STYLE_SKIP
        self.add = _BUTTON_STYLE_ADD


# --- Transport bar buttons ---
_BUTTON_STYLE_TRANSPORT = """
    QPushButton {
        padding: 4px 8px;
        border: 1px solid #555;
        border-radius: 3px;
        background-color: #3a3a3a;
        color: #ddd;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #4a4a4a; }
    QPushButton:pressed { background-color: #2a2a2a; }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #555;
        border-color: #333;
    }
"""


class TransportButtonStyles:
    """Predefined style for transport bar buttons."""

    def __init__(self):
        self.transport = _BUTTON_STYLE_TRANSPORT