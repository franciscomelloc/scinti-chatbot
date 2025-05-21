import sqlite3

def criar_tabela():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whatsapp_id TEXT UNIQUE NOT NULL,
            nome TEXT,
            idade TEXT,
            genero TEXT,
            etapa TEXT NOT NULL,
            finalizado INTEGER NOT NULL CHECK (finalizado IN (0, 1))
        )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    criar_tabela()
    print("Tabela criada com sucesso.")
