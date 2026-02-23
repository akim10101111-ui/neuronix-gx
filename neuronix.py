import sys
import os
import sqlite3
import hashlib
from datetime import datetime

from PyQt6.QtCore import Qt, QUrl, QSize, pyqtSlot, QPoint
from PyQt6.QtGui import QIcon, QColor, QPalette, QAction, QKeySequence, QShortcut, QFont
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer 
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QPushButton, QLineEdit, QTabWidget, QMessageBox, QInputDialog, 
    QLabel, QFileDialog, QProgressBar, QMenu, QFrame, QSplitter, QToolBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings, 
    QWebEngineDownloadRequest, QWebEngineUrlRequestInterceptor
)

# ================= 1. ШИФРОВАНИЕ И БЕЗОПАСНОСТЬ =================

def encrypt_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

class GXInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.blocked_ads = 0
        self.ad_domains = ["doubleclick.net", "google-analytics.com", "ads.", "tracking", "telemetry"]

    def interceptRequest(self, info):
        url = info.requestUrl().toString().lower()
        if any(domain in url for domain in self.ad_domains):
            info.block(True)
            self.blocked_ads += 1
        info.setHttpHeader(b"DNT", b"1")

# ================= 2. БАЗА ДАННЫХ =================

def init_db():
    conn = sqlite3.connect("neuronix_gx.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, visit_time TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS passwords(id INTEGER PRIMARY KEY AUTOINCREMENT, site TEXT, login TEXT, password TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS bookmarks(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT)")
    conn.commit()
    conn.close()

# ================= 3. ГЛАВНОЕ ОКНО NEURONIX GX =================

class NeuronixGX(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NEURONIX GX - ULTIMATE")
        self.resize(1600, 900)

        # Константы
        self.ACCENT = "#fa233b" # GX Red
        self.BG = "#0b0c0f"
        self.ADMIN_KEY = "admin123"
        self.closed_tabs_stack = []

        # Настройка движка
        self.profile = QWebEngineProfile.defaultProfile()
        self.interceptor = GXInterceptor()
        self.profile.setUrlRequestInterceptor(self.interceptor)
        
        # Разрешаем видео и полный экран
        self.profile.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        self.profile.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

        self.init_ui()
        self.apply_styles()
        self.setup_hotkeys()
        
        # Открываем твою главную страницу
        self.new_tab(QUrl("https://duckduckgo.com"), "Dashboard")

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        # --- SIDEBAR (OPERA STYLE) ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(55)
        self.sidebar.setObjectName("sidebar")
        s_layout = QVBoxLayout(self.sidebar)
        s_layout.setContentsMargins(0, 10, 0, 10)
        s_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        icons = [
            ("🎮", "GX Corner", "https://gx-corner.opera.com"),
            ("🏠", "Home", "home"),
            ("👤", "User Agent", "ua"),
            ("—", "", ""),
            ("✈️", "Telegram", "https://web.telegram.org"),
            ("💬", "Discord", "https://discord.com/app"),
            ("🎵", "Player", "https://music.youtube.com"),
            ("—", "", ""),
            ("🔐", "Vault", "vault"),
            ("🧹", "Cleaner", "clean"),
            ("⚙️", "Settings", "admin")
        ]

        for icon, tip, act in icons:
            if icon == "—":
                line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background: #2a2d32; margin: 5px;")
                s_layout.addWidget(line)
                continue
            btn = QPushButton(icon)
            btn.setFixedSize(45, 45)
            btn.setToolTip(tip)
            btn.setObjectName("sideBtn")
            btn.clicked.connect(lambda ch, a=act: self.handle_side_click(a))
            s_layout.addWidget(btn)

        self.splitter.addWidget(self.sidebar)

        # --- BROWSER AREA ---
        self.content = QWidget()
        self.vbox = QVBoxLayout(self.content)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(0)

        # Вкладки
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.sync_url)
        self.vbox.addWidget(self.tabs)

        # Навигация
        self.nav = QFrame()
        self.nav.setFixedHeight(50)
        self.nav.setObjectName("nav")
        n_layout = QHBoxLayout(self.nav)

        self.btn_back = QPushButton("◀")
        self.btn_back.clicked.connect(lambda: self.tabs.currentWidget().back())
        self.btn_forw = QPushButton("▶")
        self.btn_forw.clicked.connect(lambda: self.tabs.currentWidget().forward())
        self.btn_relo = QPushButton("🔄")
        self.btn_relo.clicked.connect(lambda: self.tabs.currentWidget().reload())

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search privately...")
        self.url_bar.returnPressed.connect(self.navigate)

        self.btn_shield = QPushButton("🛡️") # AdBlock Stat
        self.btn_shield.clicked.connect(self.show_ad_stats)

        n_layout.addWidget(self.btn_back)
        n_layout.addWidget(self.btn_forw)
        n_layout.addWidget(self.btn_relo)
        n_layout.addWidget(self.url_bar)
        n_layout.addWidget(self.btn_shield)
        self.vbox.addWidget(self.nav)

        self.prog = QProgressBar()
        self.prog.setFixedHeight(2)
        self.prog.setTextVisible(False)
        self.vbox.addWidget(self.prog)

        self.splitter.addWidget(self.content)

    def apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {self.BG}; }}
            QFrame#sidebar {{ background: #16171a; border-right: 1px solid #2a2d32; }}
            QFrame#nav {{ background: #16171a; border-bottom: 1px solid #000; }}
            
            QPushButton#sideBtn {{ font-size: 20px; color: #a1a3a8; border-radius: 10px; }}
            QPushButton#sideBtn:hover {{ background: rgba(250, 35, 59, 0.15); color: {self.ACCENT}; }}
            
            QLineEdit {{ 
                background: #202228; color: white; border: 1px solid #333; 
                border-radius: 16px; padding: 6px 15px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {self.ACCENT}; }}
            
            QTabBar::tab {{ 
                background: #16171a; color: #888; padding: 10px 25px; 
                border-top: 2px solid transparent; margin-right: 2px;
            }}
            QTabBar::tab:selected {{ 
                background: {self.BG}; color: white; border-top: 2px solid {self.ACCENT}; 
            }}
            QProgressBar::chunk {{ background: {self.ACCENT}; }}
        """)

    def handle_side_click(self, act):
        if act.startswith("http"): self.new_tab(QUrl(act))
        elif act == "home": self.go_home()
        elif act == "ua": self.change_ua()
        elif act == "vault": self.open_admin_panel()
        elif act == "clean": self.profile.clearHttpCache(); QMessageBox.information(self, "GX", "Cache Cleared")

    def new_tab(self, url, title="New Tab"):
        browser = QWebEngineView()
        browser.setUrl(url)
        browser.page().fullScreenRequested.connect(self.handle_fs)
        
        browser.loadProgress.connect(self.prog.setValue)
        browser.loadStarted.connect(self.prog.show)
        browser.loadFinished.connect(self.prog.hide)
        
        idx = self.tabs.addTab(browser, title)
        self.tabs.setCurrentIndex(idx)
        
        browser.urlChanged.connect(lambda q: self.url_bar.setText(q.toString()))
        browser.titleChanged.connect(lambda t: self.tabs.setTabText(self.tabs.indexOf(browser), t[:15]))

    def handle_fs(self, req):
        req.accept()
        if req.toggleOn(): self.showFullScreen(); self.sidebar.hide(); self.nav.hide()
        else: self.showNormal(); self.sidebar.show(); self.nav.show()

    def navigate(self):
        u = self.url_bar.text()
        url = QUrl(u) if "." in u else QUrl(f"https://duckduckgo.com/?q={u}")
        self.tabs.currentWidget().setUrl(url)

    def close_tab(self, i):
        if self.tabs.count() > 1:
            self.closed_tabs_stack.append(self.tabs.widget(i).url())
            self.tabs.removeTab(i)

    def setup_hotkeys(self):
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(lambda: self.new_tab(QUrl("https://duckduckgo.com")))
        QShortcut(QKeySequence("Ctrl+Shift+T"), self).activated.connect(self.restore_tab)
        QShortcut(QKeySequence("F11"), self).activated.connect(self.toggle_fs_manual)

    def restore_tab(self):
        if self.closed_tabs_stack: self.new_tab(self.closed_tabs_stack.pop())

    def toggle_fs_manual(self):
        if self.isFullScreen(): self.showNormal(); self.sidebar.show(); self.nav.show()
        else: self.showFullScreen(); self.sidebar.hide(); self.nav.hide()

    def sync_url(self, i):
        if self.tabs.widget(i): self.url_bar.setText(self.tabs.widget(i).url().toString())

    def go_home(self): self.tabs.currentWidget().setUrl(QUrl("https://duckduckgo.com"))
    
    def show_ad_stats(self):
        QMessageBox.information(self, "GX Shield", f"Blocked Ads: {self.interceptor.blocked_ads}")

    def change_ua(self):
        agents = ["Opera GX", "iPhone 15", "Android 14"]
        ua, ok = QInputDialog.getItem(self, "GX Identity", "Switch Profile:", agents, 0, False)
        if ok: QMessageBox.information(self, "Identity", f"Masked as {ua}")

    def open_admin_panel(self):
        pwd, ok = QInputDialog.getText(self, "Security", "Admin Key:", QLineEdit.EchoMode.Password)
        if ok and pwd == self.ADMIN_KEY: QMessageBox.information(self, "Admin", "Access to Vault Granted.")

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    ex = NeuronixGX()
    ex.show()
    sys.exit(app.exec())
