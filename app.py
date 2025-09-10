import sys
from pathlib import Path
import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QAction, QKeySequence, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolBar, QStyle,
    QTableView, QFrame, QAbstractItemView, QLineEdit, QGroupBox, QFormLayout,
    QSplitter, QInputDialog, QMenu, QStatusBar
)

import cost_components as cc
from data_engine import Engine, FOUR_KEYS, FALLBACK_LABELS

ACCENT = "#06b6d4"  # cyan-500-ish

def apply_modern_style(app: QApplication, dark: bool = True):
    """Fusion teması + modern palette + sade stylesheet."""
    app.setStyle("Fusion")

    if dark:
        p = app.palette()
        p.setColor(QPalette.ColorRole.Window,        Qt.black)
        p.setColor(QPalette.ColorRole.WindowText,    Qt.white)
        p.setColor(QPalette.ColorRole.Base,          Qt.black)
        p.setColor(QPalette.ColorRole.AlternateBase, Qt.black)
        p.setColor(QPalette.ColorRole.ToolTipBase,   Qt.black)
        p.setColor(QPalette.ColorRole.ToolTipText,   Qt.white)
        p.setColor(QPalette.ColorRole.Text,          Qt.white)
        p.setColor(QPalette.ColorRole.Button,        Qt.black)
        p.setColor(QPalette.ColorRole.ButtonText,    Qt.white)
        p.setColor(QPalette.ColorRole.Highlight,     Qt.cyan)
        p.setColor(QPalette.ColorRole.HighlightedText, Qt.black)
        app.setPalette(p)

    app.setStyleSheet(f"""
        QWidget {{ font-size: 13px; }}
        QToolBar {{ spacing: 6px; padding: 6px; border: 0; }}
        QToolButton {{ padding: 6px 10px; border-radius: 8px; }}
        QLineEdit {{ padding: 6px 8px; border: 1px solid #444; border-radius: 8px; }}
        QPushButton {{ padding: 6px 12px; border-radius: 10px; background: {ACCENT}; color: black; font-weight: 600; }}
        QPushButton:disabled {{ background: #555; color: #999; }}
        QGroupBox {{ border: 1px solid #333; border-radius: 10px; margin-top: 12px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {ACCENT}; }}
        QTableView {{ gridline-color: #333; selection-background-color: {ACCENT}; selection-color: black; }}
        QHeaderView::section {{ padding: 6px; border: none; background: #111; color: #bbb; }}
        QLabel.info {{ color:#9aa0a6; }}
    """)

class DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def set_dataframe(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if self._df is None else len(self._df.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole or self._df is None:
            return None
        if orientation == Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except Exception:
                return ""
        else:
            return str(section + 1)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self._df.iat[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            if pd.isna(value):
                return ""
            return str(value)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        col = index.column()
        row = index.row()
        text = "" if value is None else str(value).strip()
        newval = pd.NA if text == "" else text
        self._df.iat[row, col] = newval
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    # satır silme
    def removeRows(self, row: int, count: int, parent=QModelIndex()) -> bool:
        if self._df is None or row < 0 or row >= len(self._df) or count <= 0:
            return False
        last = min(row + count - 1, len(self._df) - 1)
        self.beginRemoveRows(QModelIndex(), row, last)
        drop_idx = list(range(row, last + 1))
        self._df = self._df.drop(self._df.index[drop_idx]).reset_index(drop=True)
        self.endRemoveRows()
        return True

    # sütun ekleme
    def add_column(self, name: str, default_val=pd.NA):
        if not name:
            return
        self.beginResetModel()
        self._df[name] = default_val
        self.endResetModel()


class DataFrameFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._needle = ""
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def setFilterText(self, text: str):
        self._needle = (text or "").strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        src = self.sourceModel()
        if src is None or not hasattr(src, "_df"):
            return True
        df = src._df
        if df is None or df.empty:
            return True
        for c in df.columns:
            val = df.iat[source_row, df.columns.get_loc(c)]
            if pd.isna(val):
                continue
            if self._needle.casefold() in str(val).casefold():
                return True
        return False

class ManualPanel(QWidget):
    def __init__(self, labels_by_key: dict[str, str]):
        super().__init__()
        self.labels_by_key = labels_by_key
        root = QVBoxLayout(self)

        # Alt dosya seç
        self.btn_open_bottom = QPushButton("Dosya Seç (Alt)…")
        root.addWidget(self.btn_open_bottom)

        grp = QGroupBox("Girişler")
        form = QFormLayout(grp)
        self._edits_by_key: dict[str, QLineEdit] = {}
        for key in FOUR_KEYS:  # 3 alan
            lbl = labels_by_key.get(key, FALLBACK_LABELS.get(key, key))
            e = QLineEdit()
            e.setPlaceholderText(f"{lbl} yazın veya dosyadan otomatik gelsin")
            self._edits_by_key[key] = e
            form.addRow(lbl, e)
        root.addWidget(grp)

    def get_values(self) -> dict[str, str]:
        out = {}
        for k, e in self._edits_by_key.items():
            t = e.text().strip()
            if t != "":
                out[k] = t
        return out

    def set_values(self, values_by_key: dict[str, str]):
        for k, v in (values_by_key or {}).items():
            if k in self._edits_by_key:
                self._edits_by_key[k].setText(str(v))

    def get_label(self, key: str) -> str:
        return self.labels_by_key.get(key, FALLBACK_LABELS.get(key, key))

    def clear(self):
        for e in self._edits_by_key.values():
            e.clear()

class TableContextMixin:
    def _init_table_common(self, tv: QTableView):
        tv.setAlternatingRowColors(True)
        tv.setSortingEnabled(True)
        tv.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        tv.setSelectionBehavior(QAbstractItemView.SelectItems)
        tv.setContextMenuPolicy(Qt.CustomContextMenu)
        tv.customContextMenuRequested.connect(lambda pos, t=tv: self._open_table_menu(t, pos))
        tv.horizontalHeader().setStretchLastSection(True)

    def _open_table_menu(self, tv: QTableView, pos):
        menu = QMenu(tv)
        act_copy = menu.addAction("Kopyala")
        act_resize = menu.addAction("Sütunları Otosığdır")
        act = menu.exec(tv.viewport().mapToGlobal(pos))
        if act is act_copy:
            self._copy_selection_to_clipboard(tv)
        elif act is act_resize:
            tv.resizeColumnsToContents()

    def _copy_selection_to_clipboard(self, tv: QTableView):
        sel = tv.selectionModel()
        if not sel or not sel.hasSelection():
            return
        # Build a matrix from selected indexes
        indexes = sel.selectedIndexes()
        if not indexes:
            return
        indexes.sort(key=lambda ix: (ix.row(), ix.column()))
        rows = {}
        for ix in indexes:
            srow = ix.row()
            # Map proxy->source text for safety
            m = tv.model()
            text = m.data(ix, Qt.DisplayRole)
            rows.setdefault(srow, []).append((ix.column(), str(text)))
        lines = []
        for r in sorted(rows):
            cols = [v for _, v in sorted(rows[r], key=lambda x: x[0])]
            lines.append("\t".join(cols))
        QGuiApplication.clipboard().setText("\n".join(lines))

class MainWindow(QMainWindow, TableContextMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("sampA (İki Dosya + Kaydet)")
        self.resize(1400, 860)

        # İş mantığı
        self.engine = Engine()
        self.engine.load_state()

        # Undo geçmişi ve kirli bayraklar
        self._history: list[tuple] = []
        self._dirty_top = False
        self._dirty_bottom = False
        self._dark_mode = True

        # Label eşlemesi (3 alan)
        self.label_by_key = {k: self.engine.schema.get(k, {}).get("label", FALLBACK_LABELS.get(k, k)) for k in FOUR_KEYS}

        # Central widget / root layout
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ==== Toolbar (ikonlar + kısayollar) ====
        tb = QToolBar("Araçlar"); self.addToolBar(tb)
        style = self.style()
        # Actions
        self.act_open_top = QAction(style.standardIcon(QStyle.SP_DirOpenIcon), "Dosya Seç (Üst)…", self)
        self.act_open_top.setShortcut(QKeySequence.Open)
        self.act_open_bottom = QAction(style.standardIcon(QStyle.SP_DirOpenIcon), "Dosya Seç (Alt)…", self)
        self.act_open_bottom.setShortcut("Ctrl+Shift+O")
        self.act_apply = QAction(style.standardIcon(QStyle.SP_BrowserReload), "Eşlemeyi Uygula", self)
        self.act_calc = QAction(style.standardIcon(QStyle.SP_ComputerIcon), "İşyeri+Masraf → Bileşen/Formula", self)
        self.act_add_row = QAction(style.standardIcon(QStyle.SP_FileDialogNewFolder), "Satır Ekle", self)
        self.act_add_col = QAction(style.standardIcon(QStyle.SP_FileIcon), "Sütun Ekle", self)
        self.act_save_top = QAction(style.standardIcon(QStyle.SP_DialogSaveButton), "Üstü Kaydet", self)
        self.act_save_bottom = QAction(style.standardIcon(QStyle.SP_DialogSaveButton), "Altı Kaydet", self)
        self.act_reset_top = QAction(style.standardIcon(QStyle.SP_BrowserStop), "Üstü Sıfırla", self)
        self.act_reset_bottom = QAction(style.standardIcon(QStyle.SP_BrowserStop), "Altı Sıfırla", self)
        self.act_import = QAction(style.standardIcon(QStyle.SP_ArrowDown), "Sisteme Aktar (Alt→Üst)", self)
        self.act_export_bottom = QAction(style.standardIcon(QStyle.SP_DialogSaveButton), "Altı CSV Dışa Aktar…", self)
        self.act_undo = QAction(style.standardIcon(QStyle.SP_ArrowBack), "Geri Al", self)
        self.act_theme = QAction("Tema: Koyu", self)
        self.act_theme.setCheckable(True); self.act_theme.setChecked(True)

        for a in [self.act_open_top, self.act_open_bottom, None,
                  self.act_apply, self.act_calc, None,
                  self.act_add_row, self.act_add_col, None,
                  self.act_import, self.act_export_bottom, None,
                  self.act_save_top, self.act_save_bottom, self.act_undo, None,
                  self.act_reset_top, self.act_reset_bottom, None,
                  self.act_theme]:
            if a is None:
                tb.addSeparator()
            else:
                tb.addAction(a)

        # ==== Üst bilgi bandı ====
        self.info = QLabel("Üst tablo: sistem verisi | Alt tablo: yeni/staged veriler. 'Sisteme Aktar' aynı İş Yeri + Masraf anahtarına göre günceller.")
        self.info.setObjectName("info")
        self.info.setProperty("class", "info")
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)

        # ==== Sol: Manuel panel ====
        self.manual_panel = ManualPanel(self.label_by_key)

        # ==== ÜST tablo + filtre ====
        self.table_top = QTableView(); self.model_top = DataFrameModel(pd.DataFrame());
        self.proxy_top = DataFrameFilterProxy(); self.proxy_top.setSourceModel(self.model_top)
        self.table_top.setModel(self.proxy_top)
        self._init_table_common(self.table_top)
        self.btn_ack_top = QPushButton("Tamam"); self.btn_ack_top.hide()
        self.ed_filter_top = QLineEdit(); self.ed_filter_top.setPlaceholderText("Üst satırları filtrele…")
        self.btn_filter_clear_top = QPushButton("Temizle")

        top_right = QWidget(); vr = QVBoxLayout(top_right); vr.setContentsMargins(0, 0, 0, 0)
        fr = QHBoxLayout(); fr.addWidget(QLabel("Filtre:")); fr.addWidget(self.ed_filter_top); fr.addWidget(self.btn_filter_clear_top)
        vr.addLayout(fr)
        vr.addWidget(self.table_top)
        ack_bar_top = QHBoxLayout(); ack_bar_top.addStretch(); ack_bar_top.addWidget(self.btn_ack_top)
        vr.addLayout(ack_bar_top)

        # Splitter (sol manuel, sağ üst tablo paneli)
        split_h = QSplitter(Qt.Horizontal)
        split_h.addWidget(self.manual_panel)
        split_h.addWidget(top_right)
        split_h.setStretchFactor(0, 0)
        split_h.setStretchFactor(1, 1)

        # ==== ALT tablo + filtre ====
        self.table_bottom = QTableView(); self.model_bottom = DataFrameModel(pd.DataFrame());
        self.proxy_bottom = DataFrameFilterProxy(); self.proxy_bottom.setSourceModel(self.model_bottom)
        self.table_bottom.setModel(self.proxy_bottom)
        self._init_table_common(self.table_bottom)
        self.btn_ack_bottom = QPushButton("Tamam"); self.btn_ack_bottom.hide()
        self.ed_filter_bottom = QLineEdit(); self.ed_filter_bottom.setPlaceholderText("Alt satırları filtrele…")
        self.btn_filter_clear_bottom = QPushButton("Temizle")

        split_v = QSplitter(Qt.Vertical)
        split_v.addWidget(split_h)
        # bottom composite
        bottom_wrap = QWidget(); vb = QVBoxLayout(bottom_wrap); vb.setContentsMargins(0, 0, 0, 0)
        fb = QHBoxLayout(); fb.addWidget(QLabel("Filtre:")); fb.addWidget(self.ed_filter_bottom); fb.addWidget(self.btn_filter_clear_bottom)
        vb.addLayout(fb)
        vb.addWidget(self.table_bottom)
        ack_bar_bot = QHBoxLayout(); ack_bar_bot.addStretch(); ack_bar_bot.addWidget(self.btn_ack_bottom)
        vb.addLayout(ack_bar_bot)
        split_v.addWidget(bottom_wrap)
        split_v.setStretchFactor(0, 1)
        split_v.setStretchFactor(1, 1)

        # ==== Status bar ====
        self.setStatusBar(QStatusBar(self))

        # ==== Layout ====
        root.addWidget(self.info)
        root.addWidget(line)
        root.addWidget(split_v)

        # State yükle → UI
        self._refresh_from_state()

        # Sinyaller (toolbar)
        self.act_open_top.triggered.connect(self.on_open_top)
        self.manual_panel.btn_open_bottom.clicked.connect(self.on_open_bottom)
        self.act_open_bottom.triggered.connect(self.on_open_bottom)
        self.act_apply.triggered.connect(self.on_apply)
        self.act_calc.triggered.connect(self.on_calc_components)
        self.act_save_top.triggered.connect(lambda: self.on_save(which="top"))
        self.act_save_bottom.triggered.connect(lambda: self.on_save(which="bottom"))
        self.act_reset_bottom.triggered.connect(self.on_reset_bottom)
        self.act_import.triggered.connect(self.on_import_into_system)
        self.act_export_bottom.triggered.connect(self.on_export_bottom)
        self.act_add_row.triggered.connect(self.on_add_row)
        self.act_add_col.triggered.connect(self.on_add_col)
        self.act_reset_top.triggered.connect(self.on_reset_top)
        self.act_undo.triggered.connect(self.on_undo)
        self.act_theme.toggled.connect(self.on_toggle_theme)

        # Sinyaller (filtre)
        self.ed_filter_top.textChanged.connect(self.proxy_top.setFilterText)
        self.btn_filter_clear_top.clicked.connect(lambda: self.ed_filter_top.clear())
        self.ed_filter_bottom.textChanged.connect(self.proxy_bottom.setFilterText)
        self.btn_filter_clear_bottom.clicked.connect(lambda: self.ed_filter_bottom.clear())

        # Satır numarası tıklayınca sil (proxy -> source index mapping)
        self.table_top.verticalHeader().sectionClicked.connect(lambda r: self.on_delete_row("top", r))
        self.table_bottom.verticalHeader().sectionClicked.connect(lambda r: self.on_delete_row("bottom", r))

        # Düzenleme takibi → kirli yap
        self._setup_dirty_tracking()

        # Uygulama teması
        apply_modern_style(QApplication.instance(), dark=True)

    # ---------------- Helpers ----------------
    def _setup_dirty_tracking(self):
        def bind(model, which):
            model.dataChanged.connect(lambda *_: self._mark_dirty(which))
            model.rowsInserted.connect(lambda *_: self._mark_dirty(which))
            model.rowsRemoved.connect(lambda *_: self._mark_dirty(which))
        bind(self.model_top, "top")
        bind(self.model_bottom, "bottom")

    def _mark_dirty(self, which: str):
        if which == "top":
            self._dirty_top = True
            self._show_ack("top")
        else:
            self._dirty_bottom = True
            self._show_ack("bottom")
        self.statusBar().showMessage("Değişiklikler kaydedilmedi.", 3000)

    def _show_ack(self, which: str):
        (self.btn_ack_top if which == "top" else self.btn_ack_bottom).show()

    def _hide_ack(self, which: str):
        (self.btn_ack_top if which == "top" else self.btn_ack_bottom).hide()

    def _on_ack(self, which: str):
        """Tamam: kaydedilmemişse kaydetmeye zorla; kaydedildiyse butonu gizle ve odak ver."""
        dirty = self._dirty_top if which == "top" else self._dirty_bottom
        table = self.table_top if which == "top" else self.table_bottom

        if dirty:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Kaydetmeniz gerekiyor")
            box.setText("Değişiklikler kaydedilmedi. Kaydetmeden devam edemezsiniz.")
            btn_save = box.addButton("Kaydet", QMessageBox.AcceptRole)
            box.addButton("İptal", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not btn_save:
                return  # iptal

            # Kaydetmeyi dene
            self.on_save(which=which)
            dirty = self._dirty_top if which == "top" else self._dirty_bottom
            if dirty:
                # kullanıcı iptal etti veya hata oldu
                return

        # Kaydedilmiş veya hiç kirli değil → devam
        self._hide_ack(which)
        table.setFocus()

    def _refresh_from_state(self):
        # Top
        self.model_top.set_dataframe(self.engine.src_df if (self.engine.src_df is not None and not self.engine.src_df.empty) else pd.DataFrame())
        # Bottom
        self.model_bottom.set_dataframe(self.engine.staged_df if (self.engine.staged_df is not None and not self.engine.staged_df.empty) else pd.DataFrame())
        # Manuel
        if self.engine.manual_values:
            self.manual_panel.set_values(self.engine.manual_values)

        top_rows = 0 if self.engine.src_df is None else len(self.engine.src_df)
        bot_rows = 0 if self.engine.staged_df is None else len(self.engine.staged_df)
        self.info.setText(f"Üst: {top_rows} satır | Alt: {bot_rows} satır.")

    def _ask_save_mode(self) -> str | None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Kaydetme Modu")
        box.setText("Üzerine mi kaydedelim, yoksa farklı kaydet?")
        btn_over = box.addButton("Üzerine Kaydet", QMessageBox.AcceptRole)
        btn_as   = box.addButton("Farklı Kaydet…", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_over:
            return "overwrite"
        elif clicked == btn_as:
            return "saveas"
        return None

    def _choose_overwrite_target(self, sources: list[str], which: str) -> str | None:
        if len(sources) == 1:
            return sources[0]
        if len(sources) > 1:
            items = [str(Path(p)) for p in sources]
            item, ok = QInputDialog.getItem(self, "Hedef Dosya", "Üzerine yazılacak dosya:", items, 0, False)
            return item if ok and item else None
        suggested = "veri_top.xlsx" if which == "top" else "veri_alt.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", suggested, "Excel/CSV (*.xlsx *.xls *.csv)")
        return path or None

    def _choose_save_path(self, which: str, sources: list[str]) -> str | None:
        target_path = None
        if len(sources) == 1:
            target_path = sources[0]
        if target_path is None:
            suggested = Path(sources[0]).name if sources else ("veri_top.xlsx" if which == "top" else "veri_alt.xlsx")
            path, _ = QFileDialog.getSaveFileName(self, "Aynı yere kaydet / Yol seç", suggested, "Excel/CSV (*.xlsx *.xls *.csv)")
            target_path = path or None
        return target_path

    def closeEvent(self, event):
        try:
            self.engine.save_state(window={"w": self.width(), "h": self.height()})
        finally:
            event.accept()

    # ---------------- Actions ----------------
    def on_open_top(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Dosyaları Seç (Üst)", "", "Excel/CSV (*.xlsx *.xls *.csv)")
        if not paths:
            return
        self._snapshot()
        new_df = self.engine.read_files(paths)
        if new_df.empty:
            QMessageBox.warning(self, "Boş", "Uygun veri bulunamadı.")
            return
        self.engine.append_to_top(new_df, paths)
        self.model_top.set_dataframe(self.engine.src_df)
        filled = self.engine.autofill_manual_from_df(new_df, keys=FOUR_KEYS, override=False)
        if filled:
            shown = [self.manual_panel.get_label(k) for k in filled]
            self.info.setText("Üst eklendi. Otomatik: " + ", ".join(shown))
        else:
            self.info.setText("Üst eklendi.")
        self.statusBar().showMessage("Üst dosyalar yüklendi.", 3000)
        self.engine.save_state()

    def on_open_bottom(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Dosyaları Seç (Alt)", "", "Excel/CSV (*.xlsx *.xls *.csv)")
        if not paths:
            return
        self._snapshot()
        new_df = self.engine.read_files(paths)
        if new_df.empty:
            QMessageBox.warning(self, "Boş", "Uygun veri bulunamadı.")
            return
        self.engine.append_to_bottom(new_df, paths)
        self.model_bottom.set_dataframe(self.engine.staged_df)
        filled = self.engine.autofill_manual_from_df(new_df, keys=FOUR_KEYS, override=False)
        if filled:
            shown = [self.manual_panel.get_label(k) for k in filled]
            self.info.setText("Alt eklendi. Otomatik: " + ", ".join(shown))
        else:
            self.info.setText("Alt eklendi.")
        self.statusBar().showMessage("Alt dosyalar yüklendi.", 3000)
        self.engine.save_state()

    def on_apply(self):
        self._snapshot()
        df = self.engine.auto_apply_top()
        if df is None or df.empty:
            QMessageBox.information(self, "Bilgi", "Eşlenecek veri bulunamadı.")
            return
        QMessageBox.information(self, "Tamam", "Üst veriye otomatik eşleme uygulandı. Export için hazır.")
        # Bu bir işlem → Tamam butonu gösterilsin (kullanıcı onaylasın)
        self._show_ack("top")
        self.statusBar().showMessage("Eşleme uygulandı.", 3000)
        self.engine.save_state()

    def on_calc_components(self):
        if self.engine.src_df is None or self.engine.src_df.empty:
            QMessageBox.information(self, "Bilgi", "Önce en az bir kez Üst dosya yükleyin.")
            return
        vals = self.manual_panel.get_values()
        isy = vals.get("is_yeri_kodu", "").strip()
        cct = vals.get("masraf_yeri_kodu", "").strip()
        if not isy or not cct:
            QMessageBox.information(self, "Eksik", "İş Yeri Kodu ve Masraf Yeri Kodu girin.")
            return
        formula_xlsx = Path(__file__).with_name("IS_PLAN_FORMULLER.xlsx")
        formula_path = str(formula_xlsx) if formula_xlsx.exists() else None
        rows_df, summary = cc.compute_by_plant_costcenter(
            src_df=self.engine.src_df,
            isyeri_kodu=isy,
            masraf_yeri_kodu=cct,
            formula_excel_path=formula_path
        )
        if rows_df.empty:
            QMessageBox.information(self, "Sonuç", "Filtreye uyan kayıt veya bileşen yok.")
            self.model_top.set_dataframe(pd.DataFrame())
            return
        self.model_top.set_dataframe(rows_df)
        pretty = " | ".join([f"{k}: {v:.2f}" for k, v in summary.items()])
        self.info.setText("Toplamlar → " + pretty)
        # İşlem sonrası Tamam
        self._show_ack("top")
        self.statusBar().showMessage("Bileşenler ve formüller hesaplandı.", 3000)
        self.engine.save_state()

    def on_save(self, which: str = "top"):
        df = self.model_top._df if which == "top" else self.model_bottom._df
        sources = self.engine.loaded_files_top if which == "top" else self.engine.loaded_files_bottom

        if df is None or df.empty:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek veri yok.")
            return

        mode = self._ask_save_mode()
        if mode is None:
            return

        path = None
        if mode == "overwrite":
            path = self._choose_overwrite_target(sources, which)
            if not path:
                return
        else:
            suggested = Path(sources[0]).name if sources else ("veri_top.xlsx" if which == "top" else "veri_alt.xlsx")
            path, _ = QFileDialog.getSaveFileName(self, "Farklı Kaydet", suggested, "Excel/CSV (*.xlsx *.xls *.csv)")
            if not path:
                return

        ok = False
        try:
            if str(path).lower().endswith(".csv"):
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False)
            ok = True
            QMessageBox.information(self, "Tamam", f"{'Üst' if which=='top' else 'Alt'} veri kaydedildi:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")
        finally:
            if ok:
                if which == "top":
                    self._dirty_top = False
                else:
                    self._dirty_bottom = False
                self.statusBar().showMessage("Kaydedildi.", 3000)
            self.engine.save_state()

    def on_reset_bottom(self):
        self._snapshot()
        self.engine.reset_bottom()
        self.model_bottom.set_dataframe(pd.DataFrame())
        self.info.setText("Alt veri temizlendi.")
        self.statusBar().showMessage("Alt veri temizlendi.", 3000)
        self.engine.save_state()

    def on_import_into_system(self):
        self._snapshot()
        removed, added = self.engine.import_staged_into_system(replace_on_keys=True)
        self.model_top.set_dataframe(self.engine.src_df if self.engine.src_df is not None else pd.DataFrame())
        self.info.setText(f"Sisteme Aktar tamam. Güncellenen (üstten silinen): {removed}, Eklenen: {added}.")
        # Üst değişti → Tamam göster
        self._show_ack("top")
        self.statusBar().showMessage("Sisteme aktarıldı.", 3000)
        self.engine.save_state()

    def on_export_bottom(self):
        df = self.model_bottom._df
        if df is None or df.empty:
            QMessageBox.information(self, "Bilgi", "Alt tabloda dışa aktarılacak veri yok.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Altı CSV olarak dışa aktar", "alt_islenmis.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            df.to_csv(path, index=False)
            QMessageBox.information(self, "Tamam", "Alt veri dışa aktarıldı.")
            self.statusBar().showMessage("Alt CSV dışa aktarıldı.", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")
        finally:
            self.engine.save_state()

    def on_add_row(self):
        self._snapshot()
        which = "bottom" if self.table_bottom.hasFocus() else "top"
        model = self.model_bottom if which == "bottom" else self.model_top
        df = model._df
        if df is None or df.columns.empty:
            QMessageBox.information(self, "Bilgi", "Önce bir tablo oluşturun (dosya açın veya Eşlemeyi Uygula).")
            return
        new_index = len(df)
        model.beginInsertRows(QModelIndex(), new_index, new_index)
        df.loc[new_index] = {col: pd.NA for col in df.columns}
        model.endInsertRows()
        self.info.setText(f"Yeni satır eklendi ({'Alt' if which=='bottom' else 'Üst'}). Toplam satır: {len(df)}")
        # rowsInserted sinyali zaten kirli yapacak;
        # yine de görünür olması için:
        self._show_ack(which)
        self.statusBar().showMessage("Yeni satır eklendi.", 3000)
        self.engine.save_state()

    def on_add_col(self):
        self._snapshot()
        which = "bottom" if self.table_bottom.hasFocus() else "top"
        model = self.model_bottom if which == "bottom" else self.model_top
        name, ok = QInputDialog.getText(self, "Sütun Ekle", "Yeni sütun adı:")
        if not ok or not str(name).strip():
            return
        col = str(name).strip()
        if col in model._df.columns:
            QMessageBox.information(self, "Var", "Bu isimde bir sütun zaten var.")
            return
        model.add_column(col)
        self.info.setText(f"Yeni sütun eklendi: {col}")
        # add_column reset yaptığı için sinyal yakalayamayız → manuel işaretle
        self._mark_dirty(which)
        self.statusBar().showMessage("Yeni sütun eklendi.", 3000)
        self.engine.save_state()

    def on_delete_row(self, which: str, view_row: int):
        # Map proxy index → source row
        proxy = self.proxy_top if which == "top" else self.proxy_bottom
        src_row = proxy.mapToSource(proxy.index(view_row, 0)).row()
        model = self.model_top if which == "top" else self.model_bottom
        if model.rowCount() == 0 or src_row < 0:
            return
        resp = QMessageBox.question(
            self, "Satır Sil",
            f"{('Üst' if which=='top' else 'Alt')} tablodan {src_row+1}. satırı silmek istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp == QMessageBox.Yes:
            self._snapshot()
            model.removeRows(src_row, 1)
            self.info.setText(f"{('Üst' if which=='top' else 'Alt')} tablodan satır silindi.")
            # rowsRemoved sinyali kirli yapacak; yine de göster:
            self._show_ack(which)
            self.statusBar().showMessage("Satır silindi.", 3000)
            self.engine.save_state()

    def on_reset_top(self):
        self._snapshot()
        self.engine.reset_top()
        self.model_top.set_dataframe(pd.DataFrame())
        self.info.setText("Üst tablo sıfırlandı.")
        self._show_ack("top")
        self.statusBar().showMessage("Üst tablo sıfırlandı.", 3000)
        self.engine.save_state()

    def on_undo(self):
        if not self._history:
            QMessageBox.information(self, "Geri Al", "Geri alınacak bir adım yok.")
            return
        snap = self._history.pop()
        self._restore(snap)
        QMessageBox.information(self, "Geri Al", "Önceki adıma dönüldü.")
        self.statusBar().showMessage("Geri alındı.", 3000)
        self.engine.save_state()

    def on_toggle_theme(self, checked: bool):
        self._dark_mode = checked
        self.act_theme.setText("Tema: Koyu" if checked else "Tema: Açık")
        apply_modern_style(QApplication.instance(), dark=checked)

    # ---------------- UNDO ----------------
    def _snapshot(self):
        src = None if self.engine.src_df is None else self.engine.src_df.copy(deep=True)
        staged = None if self.engine.staged_df is None else self.engine.staged_df.copy(deep=True)
        processed = None if self.engine.processed_df is None else self.engine.processed_df.copy(deep=True)
        files_top = list(self.engine.loaded_files_top)
        files_bottom = list(self.engine.loaded_files_bottom)
        manual = dict(self.engine.manual_values)
        self._history.append((src, staged, processed, files_top, files_bottom, manual))
        if len(self._history) > 20:
            self._history.pop(0)

    def _restore(self, snap: tuple):
        (src, staged, processed, files_top, files_bottom, manual) = snap
        self.engine.src_df = src
        self.engine.staged_df = staged
        self.engine.processed_df = processed
        self.engine.loaded_files_top = files_top
        self.engine.loaded_files_bottom = files_bottom
        self.engine.manual_values = manual
        self._refresh_from_state()


# ---------------- Entrypoint ----------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
