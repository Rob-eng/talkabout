import asyncio
import logging
import os
import tempfile
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from dotenv import load_dotenv
from openai import AsyncOpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database

# Carrega variáveis de ambiente
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("Verifique as chaves TELEGRAM_BOT_TOKEN e OPENAI_API_KEY no .env")

# Instancia o bot e o dispatcher
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Cliente Async da OpenAI
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Dicionário de inatividade na memória
inactivity_timers = {}

# Variável global para o pool do banco
db_pool = None

with open("system_prompt.md", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

async def inactivity_trigger(chat_id: int):
    try:
        await asyncio.sleep(300) # Aguarda 5 Minutos
        
        # Puxamos apenas o ultimos turnos do BD 
        history = await database.get_conversation_history(db_pool, chat_id, SYSTEM_PROMPT, limit=5)
        
        # O bd ja insere o "system" no id 0. Se history tiver so 1, não houve coversa.
        if len(history) <= 1:
            return  
            
        logging.info(f"Gerando Deep Feedback Report para {chat_id}")
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        
        analysis_prompt = (
            "The 5-minute inactivity timer has been triggered. "
            "Based on our recent conversation history, please generate a [Deep Feedback Report]. "
            "Analyze my sentence structures, suggest advanced synonyms for words I used, and point out any bad habits. "
            "End your message with a compelling/engaging question to resume the class."
        )
        
        messages_to_send = history.copy()
        messages_to_send.append({"role": "user", "content": analysis_prompt})
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages_to_send,
            temperature=0.7
        )
        
        report_text = response.choices[0].message.content
        
        # Grava a mensagem do analista no banco
        await database.append_message(db_pool, chat_id, "assistant", report_text)
        await bot.send_message(chat_id=chat_id, text=report_text)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"Erro no timer de inatividade para {chat_id}: {e}")

def reset_inactivity_timer(chat_id: int):
    if chat_id in inactivity_timers and not inactivity_timers[chat_id].done():
        inactivity_timers[chat_id].cancel()
    inactivity_timers[chat_id] = asyncio.create_task(inactivity_trigger(chat_id))

async def send_weekly_summaries(pool):
    """
    Função rodada nas Segundas-Feiras.
    Coleta tudo que foi conversado por cada aluno e gera + manda um resumo pro ADMIN.
    """
    if not ADMIN_CHAT_ID:
        logging.warning("ADMIN_CHAT_ID não definido. Impossível enviar relatórios semanais.")
        return
        
    users_data = await database.get_week_messages_for_reports(pool)
    
    if not users_data:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text="📊 <b>Relatório Semanal:</b>\nNenhum aluno praticou inglês nesta última semana.")
        except Exception:
            pass
        return
        
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"📊 <b>Relatório Semanal Iniciado:</b>\nGerando análise para {len(users_data)} aluno(s)...")

    for u_id, data in users_data.items():
        # Vamos concatenar o histórico dele pra enviar ao GPT, limitando ao tamanho p/ ninguem falir em tokens
        # Junta todas as mensagens pra mandar como 1 bloção, limitando aos últimos 50 turnos (+- 20.000 chars)
        compiled_chat = "\n".join(data["messages"][-50:]) 
        
        prompt = (
            f"Você é um gerente pedagógico. Analise o histórico recente de conversas do aluno '{data['name']}' "
            "com nosso tutor de inglês e faça um resumo direto em Português sobre:\n"
            "- O que ele aprendeu/praticou (ex: vocabulário focado em negócios, falsos cognatos, correções frequentes).\n"
            "- O nível de engajamento do aluno.\n"
            "Mantenha o resumo em um formato claro e com bullet points (Max 3 parágrafos).\n\n"
            f"HISTÓRICO:\n{compiled_chat}"
        )
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",  
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            admin_report = f"👤 <b>Relatório do Aluno:</b> {html.quote(data['name'])}\n\n{response.choices[0].message.content}"
            # Usa o ID do admin para enviar a DM
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_report)
            
        except Exception as e:
            logging.error(f"Falha ao gerar relatório para {u_id}: {e}")

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    chat_id = message.chat.id
    user_name = message.from_user.full_name
    
    # Processa usuário no banco. Retorna True se for Novo!
    is_new = await database.process_new_user(db_pool, chat_id, user_name)
    
    if is_new and ADMIN_CHAT_ID:
        try:
            # Avisa o Administrador
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID, 
                text=f"🚀 <b>Novo Cadastro de Aluno!</b>\nO usuário <b>{html.quote(user_name)}</b> acabou de iniciar a primeira aula."
            )
        except Exception as e:
            logging.error(f"Erro ao avisar admin {ADMIN_CHAT_ID}: {e}")
            
    welcome_text = (
        f"Hi, {html.bold(user_name)}! 🇬🇧\n\n"
        "I'm your AI English Tutor. Let's chat!\n"
        "Podemos praticar sobre qualquer tema que desejar. Além disso, se precisar do modo dicionário, basta me mandar qualquer palavra *isolada* e eu vou te responder com a pronúncia, função gramatical e exemplos!"
    )
    await message.answer(welcome_text)
    reset_inactivity_timer(chat_id)

@dp.message(F.voice | F.text)
async def main_chat_handler(message: Message) -> None:
    chat_id = message.chat.id
    user_name = message.from_user.full_name
    
    # Previne que o bot atropele sem registrar novos se eles não deram start
    await database.process_new_user(db_pool, chat_id, user_name)
    reset_inactivity_timer(chat_id)
    
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    user_text = ""

    if message.voice:
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_audio:
                file_id = message.voice.file_id
                file = await bot.get_file(file_id)
                await bot.download_file(file.file_path, tmp_audio.name)
            
            with open(tmp_audio.name, "rb") as audio_file:
                transcription = await client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    language="en"
                )
            user_text = transcription.text
            os.remove(tmp_audio.name)
            
            await message.reply(f"<i>🎙 Transcribed:</i> {html.quote(user_text)}")
        except Exception as e:
            logging.error(f"Erro ao processar áudio: {e}")
            await message.answer("Desculpe, não consegui entender bem esse áudio. Pode repetir ou digitar?")
            return
    elif message.text:
        user_text = message.text

    if not user_text.strip():
        return

    # Registra a mensagem do usuário no Banco de Dados
    await database.append_message(db_pool, chat_id, "user", user_text)
    
    try:
        # Recupera as ultimas 20 msgs do banco
        history = await database.get_conversation_history(db_pool, chat_id, SYSTEM_PROMPT, limit=20)
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=history,
            temperature=0.7
        )
        assistant_reply = response.choices[0].message.content
        
        # Salva a resposta da IA no banco
        await database.append_message(db_pool, chat_id, "assistant", assistant_reply)
        
        await message.answer(assistant_reply)
        
        # Sempre responde com áudio também!
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        
        audio_response = await client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=assistant_reply[:4000],
            response_format="opus"
        )
        
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_tts:
            audio_response.stream_to_file(tmp_tts.name)
        
        voice_file = FSInputFile(tmp_tts.name)
        await bot.send_voice(chat_id=chat_id, voice=voice_file)
        os.remove(tmp_tts.name)
            
    except Exception as e:
        logging.error(f"Erro ao conectar com OpenAI: {e}")
        await message.answer("Oops! Tive um problema para me conectar com meu cérebro criativo (API do ChatGPT).")

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    
    global db_pool
    # 1. Configura e conecta banco de dados PostgreSQL
    db_pool = await database.get_pool()
    await database.init_db(db_pool)
    logging.info("Tabelas SQL verificadas!")
    
    # 2. Configura o Agendador para rodar os relatórios
    # Aqui agendamos para as Segundas ("mon") às 08:00 AM no fuso do Brasil
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(send_weekly_summaries, "cron", day_of_week="mon", hour=8, minute=0, args=(db_pool,))
    scheduler.start()
    logging.info("Agendador de relatórios semanais acionado!")
    
    # 3. Inicia o Bot
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
