# database.py
import sqlite3
import json
from datetime import datetime
from typing import List, Tuple, Optional

class Database:
    def __init__(self, path: str = None):
        # default path: env or fallback
        if path:
            self.db_path = path
        else:
            self.db_path = "/tmp/palpites.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS rodadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                ativa INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS jogos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER NOT NULL,
                time1 TEXT NOT NULL,
                time2 TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rodada_id) REFERENCES rodadas(id)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS palpites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                user_phone TEXT,
                palpites TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rodada_id) REFERENCES rodadas(id),
                UNIQUE(rodada_id, user_id)
            )
        ''')
        self.conn.commit()

    # criar nova rodada (desativa outras)
    def criar_nova_rodada(self, nome: str = "Rodada Atual") -> int:
        cur = self.conn.cursor()
        cur.execute('UPDATE rodadas SET ativa = 0')
        cur.execute('INSERT INTO rodadas (nome, ativa) VALUES (?, ?)', (nome, 1))
        self.conn.commit()
        return cur.lastrowid

    def obter_rodada_ativa(self) -> Optional[Tuple]:
        cur = self.conn.cursor()
        cur.execute('SELECT id, nome, ativa, created_at FROM rodadas WHERE ativa = 1 ORDER BY id DESC LIMIT 1')
        return cur.fetchone()

    def inserir_jogos(self, jogos: List[Tuple[str, str]], rodada_id: int):
        cur = self.conn.cursor()
        # remove jogos existentes para a rodada
        cur.execute('DELETE FROM jogos WHERE rodada_id = ?', (rodada_id,))
        for t1, t2 in jogos:
            cur.execute('INSERT INTO jogos (rodada_id, time1, time2) VALUES (?, ?, ?)', (rodada_id, t1, t2))
        self.conn.commit()

    def obter_jogos(self, rodada_id: int):
        cur = self.conn.cursor()
        cur.execute('SELECT id, rodada_id, time1, time2 FROM jogos WHERE rodada_id = ? ORDER BY id', (rodada_id,))
        return cur.fetchall()

    def usuario_ja_enviou_rodada(self, user_id: int, rodada_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute('SELECT id FROM palpites WHERE rodada_id = ? AND user_id = ?', (rodada_id, user_id))
        return cur.fetchone() is not None

    def salvar_palpite(self, rodada_id: int, user_id: int, user_name: str, user_phone: str, palpites):
        cur = self.conn.cursor()
        cur.execute('INSERT OR REPLACE INTO palpites (rodada_id, user_id, user_name, user_phone, palpites) VALUES (?, ?, ?, ?, ?)',
                    (rodada_id, user_id, user_name, user_phone, json.dumps(palpites)))
        self.conn.commit()
        return True

    def obter_palpites_rodada(self, rodada_id: int):
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM palpites WHERE rodada_id = ? ORDER BY created_at', (rodada_id,))
        return cur.fetchall()

    def obter_estatisticas_rodada(self, rodada_id: int):
        palpites = self.obter_palpites_rodada(rodada_id)
        jogos = self.obter_jogos(rodada_id)
        if not palpites:
            return None
        estatisticas = [{"1":0,"X":0,"2":0} for _ in range(len(jogos))]
        for p in palpites:
            try:
                arr = json.loads(p[5])
            except:
                arr = []
            for i, choice in enumerate(arr):
                if choice in estatisticas[i]:
                    estatisticas[i][choice] += 1
        return {"total_palpitadores": len(palpites), "estatisticas": estatisticas, "jogos": jogos}



