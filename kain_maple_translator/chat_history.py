"""Durable, unlimited local translation history. Deletion is explicit only."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path


class ChatHistoryStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(self.path),timeout=8)
        try:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA busy_timeout=8000')
            self.db.execute('''CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, captured REAL NOT NULL,
                nickname TEXT NOT NULL, original TEXT NOT NULL,
                translated TEXT NOT NULL, payload TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS message_time ON messages(captured,id)')
            self.db.commit()
        except BaseException:
            # Failed constructors have no caller able to close the store.
            # Release the handle before propagating, including while an
            # exception traceback still retains this object on Windows.
            self.db.close()
            raise

    def append(self,record):
        payload=dict(record)
        message_id=str(payload['id'])
        captured=float(payload.get('captured_unix') or time.time())
        payload['captured_unix']=captured
        with self.db:
            cursor=self.db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?)',
                (message_id,captured,str(payload.get('nickname','')),str(payload.get('original','')),
                 str(payload.get('translated','')),json.dumps(payload,ensure_ascii=False)))
        return bool(cursor.rowcount)

    @staticmethod
    def _where(search):
        if not search:return '',()
        pattern='%'+str(search).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        return " WHERE (nickname LIKE ? ESCAPE '\\' OR original LIKE ? ESCAPE '\\' OR translated LIKE ? ESCAPE '\\')",(pattern,)*3

    def count(self,search=''):
        where,args=self._where(search)
        return self.db.execute('SELECT COUNT(*) FROM messages'+where,args).fetchone()[0]

    def page(self,offset=0,limit=200,search=''):
        where,args=self._where(search)
        rows=self.db.execute('SELECT payload FROM messages'+where+
            ' ORDER BY captured DESC,rowid DESC LIMIT ? OFFSET ?',(*args,int(limit),int(offset)))
        return [json.loads(row[0]) for row in rows]

    def recent(self,limit=95):
        return list(reversed(self.page(limit=limit)))

    def contains_startup_pixels(self,record):
        """Suppress a recent persisted row only on the initial live screen."""
        ink=record.get('source_ink');rect=record.get('source_local_rect')
        if not ink or not rect:return False
        now=float(record['captured_unix'])
        matches=self.db.execute('SELECT payload FROM messages WHERE captured BETWEEN ? AND ? AND nickname=? AND original=? ORDER BY captured DESC LIMIT 16',
            (now-180,now+1,record['nickname'],record.get('original','')))
        for raw, in matches:
            old=json.loads(raw);position=old.get('source_local_rect')
            if old.get('source_ink')==ink and position and abs(position[1]-rect[1])<=3:return True
        return False

    def clear(self):
        with self.db:self.db.execute('DELETE FROM messages')

    def close(self):self.db.close()
