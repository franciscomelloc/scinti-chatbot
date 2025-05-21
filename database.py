import sqlite3

DB_PATH = "chatbot.db"

def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def obter_usuario(whatsapp_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE whatsapp_id = ?", (whatsapp_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def criar_usuario(whatsapp_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usuarios (whatsapp_id, etapa, finalizado)
        VALUES (?, 'nome', 0)
    """, (whatsapp_id,))
    conn.commit()
    conn.close()

def atualizar_usuario(whatsapp_id, campo, valor):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE usuarios SET {campo} = ? WHERE whatsapp_id = ?", (valor, whatsapp_id))
    conn.commit()
    conn.close()

def marcar_finalizado(whatsapp_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET finalizado = 1 WHERE whatsapp_id = ?", (whatsapp_id,))
    conn.commit()
    conn.close()

def apagar_usuario(whatsapp_id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE whatsapp_id = ?", (whatsapp_id,))
    conn.commit()
    conn.close()
