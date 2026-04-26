import os
import asyncpg
import logging
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_pool():
    if not DATABASE_URL:
        # Tenta pegar apenas da variável se já não estiver em ambiente dev/railway
        raise ValueError("DATABASE_URL não configurada. Por favor, adicione esta variável no Railway (PostgreSQL).")
    
    # Se o Heroku / Railway passar sqlite:/// a gente precisa avisar, mas esperamos um postges://
    # Correção para alguns provedores onde a URI começa com postgres:// em vez de postgresql://
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return await asyncpg.create_pool(db_url)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)

async def process_new_user(pool, user_id, user_name):
    """
    Cadastra o usuário e retorna True se for um novo cadastro, 
    ou False se ele já estivesse previamente banco.
    """
    async with pool.acquire() as conn:
        record = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not record:
            await conn.execute("INSERT INTO users (id, name) VALUES ($1, $2)", user_id, user_name)
            return True
        return False

async def append_message(pool, user_id, role, content):
    """
    Insere uma mensagem do histórico para o usuário.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES ($1, $2, $3)",
            user_id, role, content
        )

async def get_conversation_history(pool, user_id, system_prompt, limit=20):
    """
    Retorna o histórico formatado para o ChatGPT. 
    Sempre injeta o System Prompt no início.
    """
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT role, content FROM messages WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
        
    history = [{"role": "system", "content": system_prompt}]
    
    # Os registros estão decrescentes (recente primeiro). Revertemos para a ordem cronológica
    for r in reversed(records):
        history.append({"role": r["role"], "content": r["content"]})
        
    return history

async def get_week_messages_for_reports(pool):
    """
    Retorna mensagens agrupadas dos últimos 7 dias para geração de relatórios.
    """
    async with pool.acquire() as conn:
        query = """
            SELECT m.user_id, u.name, m.role, m.content 
            FROM messages m
            JOIN users u ON m.user_id = u.id
            WHERE m.created_at >= NOW() - INTERVAL '7 days'
            ORDER BY m.user_id, m.created_at ASC
        """
        records = await conn.fetch(query)
        
        users_data = {}
        for r in records:
            u_id = r["user_id"]
            if u_id not in users_data:
                users_data[u_id] = {"name": r["name"], "messages": []}
            users_data[u_id]["messages"].append(f"{r['role']}: {r['content']}")
            
        return users_data
