"""Searchable, paged archive; the overlay can keep a small widget budget."""
import time
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QTextEdit,QPushButton,QLabel,QMessageBox


class HistoryDialog(QDialog):
    cleared=Signal()
    def __init__(self,store,parent=None):
        super().__init__(parent)
        self.store=store;self.offset=0;self.page_size=200
        self.setWindowTitle('번역 내역 · 직접 지우기 전까지 보관')
        self.resize(740,610)
        layout=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText('닉네임, 원문, 번역 검색')
        layout.addWidget(self.search)
        self.contents=QTextEdit();self.contents.setReadOnly(True);layout.addWidget(self.contents,1)
        controls=QHBoxLayout();self.newer=QPushButton('최근 페이지');self.older=QPushButton('이전 페이지')
        self.status=QLabel();clear=QPushButton('내역 전체 지우기')
        clear.setObjectName('danger')   # the game's lime DELETE / CLEAR ALL
        for w in (self.newer,self.older,self.status,clear):controls.addWidget(w)
        layout.addLayout(controls)
        self.newer.clicked.connect(lambda:self.turn(-1));self.older.clicked.connect(lambda:self.turn(1))
        self.search.textChanged.connect(self.find);clear.clicked.connect(self.clear_history)
        self.refresh()

    def find(self,_text):self.offset=0;self.refresh()
    def turn(self,direction):self.offset=max(0,self.offset+direction*self.page_size);self.refresh()

    def refresh(self):
        query=self.search.text();total=self.store.count(query)
        rows=self.store.page(self.offset,self.page_size,query)
        lines=[]
        for row in rows:
            stamp=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(row['captured_unix']))
            lines.append(f"[{stamp}] {row.get('prefix','')} {row.get('nickname','')}\n원문: {row.get('original','')}\n번역: {row.get('translated','')}")
        self.contents.setPlainText('\n\n'.join(lines) or '저장된 번역 내역이 없습니다.')
        self.status.setText(f'{total:,}건 · {self.offset//self.page_size+1}페이지')
        self.newer.setEnabled(self.offset>0);self.older.setEnabled(self.offset+len(rows)<total)

    def clear_history(self):
        answer=QMessageBox.question(self,'번역 내역 지우기','저장된 번역 내역을 모두 지울까요? 직접 지운 내역은 복구할 수 없습니다.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.store.clear();self.offset=0;self.cleared.emit();self.refresh()
