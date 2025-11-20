import sqlite3
import json
from datetime import datetime
from config import DB_PATH

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Tabela de rodadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rodadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                ativa BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de jogos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jogos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER NOT NULL,
                time1 TEXT NOT NULL,
                time2 TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rodada_id) REFERENCES rodadas (id)
            )
        ''')
        
        # Tabela de palpites
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS palpites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                user_phone TEXT,
                palpites TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rodada_id) REFERENCES rodadas (id),
                UNIQUE(rodada_id, user_id)
            )
        ''')
        
        self.conn.commit()
    
    def criar_nova_rodada(self, nome="Rodada Atual"):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE rodadas SET ativa = FALSE')
        cursor.execute('INSERT INTO rodadas (nome, ativa) VALUES (?, ?)', (nome, True))
        rodada_id = cursor.lastrowid
        self.conn.commit()
        return rodada_id
    
    def obter_rodada_ativa(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM rodadas WHERE ativa = TRUE ORDER BY id DESC LIMIT 1')
        return cursor.fetchone()
    
    def inserir_jogos(self, jogos, rodada_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM jogos WHERE rodada_id = ?', (rodada_id,))
        for time1, time2 in jogos:
            cursor.execute('INSERT INTO jogos (rodada_id, time1, time2) VALUES (?, ?, ?)', 
                           (rodada_id, time1, time2))
        self.conn.commit()
    
    def obter_jogos(self, rodada_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, rodada_id, time1, time2 FROM jogos WHERE rodada_id = ? ORDER BY id', (rodada_id,))
        return cursor.fetchall()
    
    def usuario_ja_enviou_rodada(self, user_id, rodada_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM palpites WHERE rodada_id = ? AND user_id = ?', (rodada_id, user_id))
        return cursor.fetchone() is not None
    
    def salvar_palpite(self, rodada_id, user_id, user_name, user_phone, palpites):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO palpites 
                (rodada_id, user_id, user_name, user_phone, palpites)
                VALUES (?, ?, ?, ?, ?)
            ''', (rodada_id, user_id, user_name, user_phone, json.dumps(palpites)))
            self.conn.commit()
            return True
        except:
            return False
    
    def obter_palpites_rodada(self, rodada_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM palpites WHERE rodada_id = ? ORDER BY created_at', (rodada_id,))
        return cursor.fetchall()
    
    def obter_estatisticas_rodada(self, rodada_id):
        palpites = self.obter_palpites_rodada(rodada_id)
        jogos = self.obter_jogos(rodada_id)
        if not palpites:
            return None
        
        estatisticas = [{"1":0,"X":0,"2":0} for _ in range(len(jogos))]
        for palpite in palpites:
            arr = json.loads(palpite[5])
            for i,p in enumerate(arr):
                if p in estatisticas[i]:
                    estatisticas[i][p] += 1
        
        return {
            "total_palpitadores": len(palpites),
            "estatisticas": estatisticas,
            "jogos": jogos
        }
