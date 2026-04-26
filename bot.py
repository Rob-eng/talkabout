import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Verifica se o TOKEN existe
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente.")

# Instancia o bot e o dispatcher
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Dicionário temporário para gerenciar tarefas de timers (5 minutos)
# Formato: {chat_id: asyncio.Task}
inactivity_timers = {}

async def inactivity_trigger(chat_id: int):
    """
    Função chamada após 5 minutos de inatividade para gerar o Deep Feedback Report.
    """
    try:
        # Aguarda 5 minutos (300 segundos)
        await asyncio.sleep(300)
        
        # Aqui chamaremos a API da OpenAI para gerar o Deep Feedback Report!
        report_message = (
            "⏳ <b>5 Minutos de Inatividade!</b>\n\n"
            "Aqui está o seu <b>[Deep Feedback Report]</b> das nossas últimas interações:\n\n"
            "<i>(Esta é uma mensagem temporária de placeholder estrutural, a integração completa com a OpenAI entrará aqui)</i>\n\n"
            "O que acha de retomarmos a aula de onde paramos?"
        )
        await bot.send_message(chat_id=chat_id, text=report_message)
    except asyncio.CancelledError:
        # A tarefa foi cancelada porque o usuário enviou uma mensagem antes dos 5 min
        pass

def reset_inactivity_timer(chat_id: int):
    """
    Cancela o timer existente de um usuário (se houver) e inicia um novo.
    """
    if chat_id in inactivity_timers:
        inactivity_timers[chat_id].cancel()
    
    # Cria uma nova task para o chat_id atual
    inactivity_timers[chat_id] = asyncio.create_task(inactivity_trigger(chat_id))

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Responde ao comando /start.
    """
    with open("system_prompt.md", "r", encoding="utf-8") as f:
        # Só para propósitos de logging
        sys_prompt = f.read()

    welcome_text = (
        f"Hello, {html.bold(message.from_user.full_name)}! 🇬🇧\n"
        "I'm your AI English Tutor. Podemos praticar sobre temas do dia a dia, "
        "ou caso queira apenas saber o significado de uma palavra, pode mandá-la isolada!"
    )
    await message.answer(welcome_text)
    
    # Inicia o monitoramento de inatividade do usuário
    reset_inactivity_timer(message.chat.id)

@dp.message()
async def main_chat_handler(message: Message) -> None:
    """
    Handler principal para receber texto ou áudio.
    """
    # 1. Resetar o timer de 5 minutos, pois recebemos uma nova mensagem!
    reset_inactivity_timer(message.chat.id)

    # 2. Esqueleto: verificar se é áudio (STT) ou texto.
    user_text = ""
    if message.voice:
        # Aqui será baixado o .ogg e feita chamada STT OpenAI Whisper
        user_text = "[Transcrição de Áudio]"
    else:
        user_text = message.text

    # 3. Lógica para bater na API da OpenAI e retornar a resposta
    response_text = (
        f"You said: <i>{html.quote(user_text)}</i>\n\n"
        "<i>(A integração com o prompt de `[Quick Correction]` e ChatGPT entra aqui.)</i>"
    )
    
    # 4. Responder ao usuário
    await message.answer(response_text)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
