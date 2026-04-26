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

# Carrega variáveis de ambiente
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN or not OPENAI_API_KEY:
    raise ValueError("Verifique as chaves TELEGRAM_BOT_TOKEN e OPENAI_API_KEY no .env")

# Instancia o bot e o dispatcher
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Cliente Async da OpenAI
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Dicionários de Memória
inactivity_timers = {}
conversations = {}

# Carrega o System Prompt
with open("system_prompt.md", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

def init_history(chat_id: int):
    # Inicializa ou zera o hitórico usando o System Prompt
    conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

def append_to_history(chat_id: int, role: str, content: str):
    if chat_id not in conversations:
        init_history(chat_id)
    conversations[chat_id].append({"role": role, "content": content})
    # Limita o histórico das últimas 20 interações p/ economizar tokens e memória
    if len(conversations[chat_id]) > 21:
        conversations[chat_id] = [conversations[chat_id][0]] + conversations[chat_id][-20:]

async def inactivity_trigger(chat_id: int):
    """
    Acionado após 5 minutos. Analisa as últimas mensagens e manda um "Deep Feedback Report".
    """
    try:
        await asyncio.sleep(300) # Aguarda 5 Minutos
        
        # Evita mandar feedback se não houveram trocas além do system prompt
        if chat_id not in conversations or len(conversations[chat_id]) <= 2:
            return  
            
        logging.info(f"Gerando Deep Feedback Report para {chat_id}")
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        
        analysis_prompt = (
            "The 5-minute inactivity timer has been triggered. "
            "Based on our recent conversation history, please generate a [Deep Feedback Report]. "
            "Analyze my sentence structures, suggest advanced synonyms for words I used, and point out any bad habits. "
            "End your message with a compelling/engaging question to resume the class."
        )
        
        # Cria uma cópia temporária e adiciona o prompt de timeout
        messages_to_send = conversations[chat_id].copy()
        messages_to_send.append({"role": "user", "content": analysis_prompt})
        
        response = await client.chat.completions.create(
            model="gpt-4o",  # Troque para gpt-3.5-turbo se quiser reduzir o custo
            messages=messages_to_send,
            temperature=0.7
        )
        
        report_text = response.choices[0].message.content
        append_to_history(chat_id, "assistant", report_text)
        await bot.send_message(chat_id=chat_id, text=report_text)
        
    except asyncio.CancelledError:
        # Usuário enviou nova mensagem e cancelou o alarme antes de ser disparado
        pass
    except Exception as e:
        logging.error(f"Erro no timer de inatividade para {chat_id}: {e}")

def reset_inactivity_timer(chat_id: int):
    if chat_id in inactivity_timers and not inactivity_timers[chat_id].done():
        inactivity_timers[chat_id].cancel()
    inactivity_timers[chat_id] = asyncio.create_task(inactivity_trigger(chat_id))

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    init_history(message.chat.id)
    
    welcome_text = (
        f"Hi, {html.bold(message.from_user.full_name)}! 🇬🇧\n\n"
        "I'm your AI English Tutor. Let's chat!\n"
        "Podemos praticar sobre qualquer tema que desejar. Além disso, se precisar do modo dicionário, basta me mandar qualquer palavra *isolada* e eu vou te responder com a pronúncia, função gramatical e exemplos!"
    )
    await message.answer(welcome_text)
    reset_inactivity_timer(message.chat.id)

@dp.message(F.voice | F.text)
async def main_chat_handler(message: Message) -> None:
    chat_id = message.chat.id
    reset_inactivity_timer(chat_id)
    
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    user_text = ""

    # Captura caso áudio
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
            
            # Avisa o que escutou pra dar confirmação visual
            await message.reply(f"<i>🎙 Transcribed:</i> {html.quote(user_text)}")
            
        except Exception as e:
            logging.error(f"Erro ao processar áudio: {e}")
            await message.answer("Desculpe, não consegui entender bem esse áudio. Pode repetir ou digitar?")
            return
    elif message.text:
        user_text = message.text

    if not user_text.strip():
        return

    # Registra no histórico e bate no gpt-4o
    append_to_history(chat_id, "user", user_text)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=conversations[chat_id],
            temperature=0.7
        )
        assistant_reply = response.choices[0].message.content
        append_to_history(chat_id, "assistant", assistant_reply)
        
        await message.answer(assistant_reply)
        
        # Sempre responde com áudio também!
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        
        # Gera audio opus pro telegram pegar como 'Voice' message nativa
        audio_response = await client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=assistant_reply[:4000], # Limite da openai api
            response_format="opus"
        )
        
        # Salvar temporariamente
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
