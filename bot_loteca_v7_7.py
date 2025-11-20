# bot_loteca_v7_7.py
# Versão V7.7 — compatível com python-telegram-bot v21+ e Python 3.11/3.13 (com imghdr stub)
# - Planilha única no grupo
# - Numeração 1..14
# - Emoji ✔️ nas seleções
# - Salva palpites em sqlite (via database.py)
# - Compatível para deploy em Render (Application.run_polling)

import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from database import Database
from config import BOT_TOKEN, ADMIN_ID, GRUPO_ID

# logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("🔧 Iniciando bot v7.7...")
print(f"📋 Token: {BOT_TOKEN[:10]}...")
print(f"👤 Admin ID: {ADMIN_ID}")
print(f"🏠 Grupo ID: {GRUPO_ID}")

db = Database()

# In-memory state
user_palpites = {}                # user_id -> [14 choices]
global_display = [None] * 14      # display in group message
last_planilha_msg = {"chat_id": None, "message_id": None, "rodada_id": None}

def safe_group_id():
    try:
        return int(GRUPO_ID)
    except Exception:
        try:
            return int(str(GRUPO_ID).strip().replace("'", "").replace('"', ""))
        except Exception:
            return None

# ---------------- Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Bot do Bolão da Loteca — v7.7*\n\n"
        "Comandos:\n"
        "• /nova_rodada — Criar nova rodada (admin)\n"
        "• /planilha — Abrir planilha (se disponível)\n"
        "• /estatisticas — Ver percentuais\n"
        "• /ver_palpites — Ver palpites (admin)",
        parse_mode="Markdown"
    )

# Admin creates a new rodada (multi-step)
async def nova_rodada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != ADMIN_ID:
        # silencioso ou resposta curta — evitar spam no grupo
        try:
            await update.message.reply_text("❌ Apenas o administrador pode usar este comando.")
        except:
            pass
        return

    # Use application_data? Using user_data is fine since admin is single user, keep simple:
    context.user_data["criando_rodada"] = True
    context.user_data["etapa"] = "nome"
    await update.message.reply_text(
        "🆕 *CRIAR NOVA RODADA*\n\n"
        "Digite o *nome do concurso* (ex: Concurso Loteca 1220).\n"
        "🛑 Para cancelar: /cancelar",
        parse_mode="Markdown"
    )

async def processar_mensagens_rodada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only proceed when admin is creating a rodada
    if not context.user_data.get("criando_rodada"):
        return

    user = update.effective_user
    if str(user.id) != ADMIN_ID:
        # ignore messages from others in this flow
        return

    texto = update.message.text.strip()
    if texto.lower() in ("/cancelar", "cancelar"):
        context.user_data.clear()
        await update.message.reply_text("❌ Criação de rodada cancelada.")
        return

    etapa = context.user_data.get("etapa")
    if etapa == "nome":
        context.user_data["nome_concurso"] = texto
        context.user_data["etapa"] = "jogos"
        await update.message.reply_text(
            "📋 Agora envie os *14 jogos de uma só vez*, separados por vírgula.\n\n"
            "Exemplo:\nFlamengo x Vasco, Sao Paulo x Corinthians, ... , Nautico x Sport",
            parse_mode="Markdown"
        )
        return

    if etapa == "jogos":
        partes = [p.strip() for p in texto.split(",") if p.strip()]
        if len(partes) != 14:
            await update.message.reply_text(f"❌ Você enviou {len(partes)} itens. Envie *exatamente 14 jogos*.")
            return
        jogos = []
        for p in partes:
            if " x " in p:
                t1, t2 = p.split(" x ", 1)
            elif "x" in p:
                t1, t2 = p.split("x", 1)
            else:
                await update.message.reply_text("❌ Formato inválido. Use: Time1 x Time2")
                return
            jogos.append((t1.strip(), t2.strip()))

        nome = context.user_data.get("nome_concurso", "Rodada")
        try:
            rodada_id = db.criar_nova_rodada(nome)
            try:
                db.inserir_jogos(jogos, rodada_id)
            except TypeError:
                db.inserir_jogos(rodada_id, jogos)

            # reset in-memory
            global user_palpites, global_display, last_planilha_msg
            user_palpites = {}
            global_display = [None] * 14
            last_planilha_msg = {"chat_id": None, "message_id": None, "rodada_id": rodada_id}

            context.user_data.clear()
            await update.message.reply_text(f"🎉 Rodada *{nome}* criada com sucesso!", parse_mode="Markdown")

            # post planilha in group
            await postar_planilha_no_grupo(context, rodada_id)

        except Exception as e:
            logger.exception("Erro ao criar rodada")
            await update.message.reply_text(f"❌ Erro ao criar rodada: {e}")

# ---------------- Render planilha ----------------

def build_planilha_text_and_keyboard(display_palpites, jogos):
    lines = []
    lines.append("📊 *Planilha Oficial da Rodada*\n")
    lines.append("┌────┬────────────────────────────┬─────┬────────────────────────────┐")
    lines.append("│ Nº │ Time 1                     │  X  │ Time 2                     │")
    lines.append("├────┼────────────────────────────┼─────┼────────────────────────────┤")
    for i in range(14):
        numero = i + 1
        # jogos rows may be (id, rodada_id, time1, time2) or (time1, time2)
        row = jogos[i]
        if len(row) >= 4:
            t1 = str(row[2])
            t2 = str(row[3])
        else:
            t1 = str(row[0])
            t2 = str(row[1])
        p = display_palpites[i] if i < len(display_palpites) else None

        t1_cell = t1[:26].ljust(26)
        t2_cell = t2[:26].ljust(26)
        x_cell = "X"

        if p == "1":
            t1_cell = f"✔️ {t1_cell}"
        if p == "X":
            x_cell = "✔️"
        if p == "2":
            t2_cell = f"{t2_cell} ✔️"

        lines.append(f"│ {numero:2d} │ {t1_cell} │  {x_cell}  │ {t2_cell} │")

    lines.append("└────┴────────────────────────────┴─────┴────────────────────────────┘")
    lines.append("\nFaça os seus palpites clicando sobre a célula correspondente à sua seleção.")
    texto = "\n".join(lines)

    # keyboard
    keyboard = []
    for i in range(14):
        row = jogos[i]
        if len(row) >= 4:
            short_t1 = str(row[2])[:16]
            short_t2 = str(row[3])[:16]
        else:
            short_t1 = str(row[0])[:16]
            short_t2 = str(row[1])[:16]
        keyboard.append([
            InlineKeyboardButton(short_t1, callback_data=f"t1_{i}"),
            InlineKeyboardButton("X", callback_data=f"x_{i}"),
            InlineKeyboardButton(short_t2, callback_data=f"t2_{i}")
        ])
    keyboard.append([InlineKeyboardButton("🚀 ENVIAR PALPITES", callback_data="enviar")])
    return texto, InlineKeyboardMarkup(keyboard)

async def postar_planilha_no_grupo(context: ContextTypes.DEFAULT_TYPE, rodada_id: int):
    gid = safe_group_id()
    if not gid:
        logger.error("GRUPO_ID inválido")
        return
    try:
        jogos = db.obter_jogos(rodada_id)
        texto, reply = build_planilha_text_and_keyboard(global_display, jogos)
        msg = await context.bot.send_message(chat_id=gid, text=texto, parse_mode="Markdown", reply_markup=reply)
        last_planilha_msg["chat_id"] = msg.chat_id
        last_planilha_msg["message_id"] = msg.message_id
        last_planilha_msg["rodada_id"] = rodada_id
        logger.info("Planilha publicada no grupo")
    except Exception as e:
        logger.exception("Erro ao postar planilha: %s", e)

# ---------------- Callbacks ----------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data
    user = query.from_user

    await query.answer()

    # ensure user_data has rodada_id
    if "rodada_id" not in context.user_data:
        if last_planilha_msg.get("rodada_id"):
            context.user_data["rodada_id"] = last_planilha_msg["rodada_id"]
        else:
            r = db.obter_rodada_ativa()
            if r:
                context.user_data["rodada_id"] = r[0]

    rodada_id = context.user_data.get("rodada_id")

    if data == "abrir_planilha":
        # open planilha in the group message (edit) so users only see the second planilha
        await abrir_planilha(update, context, user.id)
        return

    # initialize user rascunho
    if user.id not in user_palpites:
        user_palpites[user.id] = [None] * 14

    if data.startswith(("t1_", "x_", "t2_")):
        tipo, idx_s = data.split("_", 1)
        try:
            idx = int(idx_s)
        except:
            return

        if tipo == "t1":
            user_palpites[user.id][idx] = "1"
            global_display[idx] = "1"
        elif tipo == "x":
            user_palpites[user.id][idx] = "X"
            global_display[idx] = "X"
        elif tipo == "t2":
            user_palpites[user.id][idx] = "2"
            global_display[idx] = "2"

        # update the group message
        try:
            jogos = db.obter_jogos(rodada_id) if rodada_id else db.obter_jogos(db.obter_rodada_ativa()[0])
            texto, reply = build_planilha_text_and_keyboard(global_display, jogos)
            if last_planilha_msg["chat_id"] and last_planilha_msg["message_id"]:
                await context.bot.edit_message_text(chat_id=last_planilha_msg["chat_id"], message_id=last_planilha_msg["message_id"], text=texto, parse_mode="Markdown", reply_markup=reply)
            else:
                gid = safe_group_id()
                if gid:
                    msg = await context.bot.send_message(chat_id=gid, text=texto, parse_mode="Markdown", reply_markup=reply)
                    last_planilha_msg["chat_id"] = msg.chat_id
                    last_planilha_msg["message_id"] = msg.message_id
                    last_planilha_msg["rodada_id"] = rodada_id or db.obter_rodada_ativa()[0]
        except Exception as e:
            logger.exception("Erro ao atualizar exibição da planilha: %s", e)
        return

    if data == "enviar":
        # must have rascunho
        if user.id not in user_palpites:
            try:
                await query.answer("⚠️ Você ainda não fez seleções.", show_alert=True)
            except:
                pass
            return

        pal = user_palpites[user.id]
        if len(pal) != 14 or any(p not in ("1", "X", "2") for p in pal):
            try:
                await query.answer("⚠️ Complete os 14 palpites antes de enviar.", show_alert=True)
            except:
                pass
            return

        # determine rodada_id
        if not rodada_id:
            r = db.obter_rodada_ativa()
            if r:
                rodada_id = r[0]
            else:
                try:
                    await query.answer("❌ Rodada não identificada.", show_alert=True)
                except:
                    pass
                return

        try:
            if db.usuario_ja_enviou_rodada(user.id, rodada_id):
                try:
                    await query.answer("✅ Você já enviou palpites para esta rodada.", show_alert=True)
                except:
                    pass
                user_palpites.pop(user.id, None)
                return
        except Exception:
            pass

        try:
            db.salvar_palpite(rodada_id, user.id, user.full_name, user.username or "", pal)
            try:
                await query.answer("🎉 Palpites enviados com sucesso!", show_alert=True)
            except:
                pass
            user_palpites.pop(user.id, None)
        except Exception as e:
            logger.exception("Erro ao salvar palpites: %s", e)
            try:
                await query.answer("❌ Erro ao salvar palpites.", show_alert=True)
            except:
                pass
        return

# ---------------- abrir_planilha (edita a mensagem do grupo) ----------------

async def abrir_planilha(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    query = update.callback_query
    user = query.from_user if query else update.effective_user
    user_id = user_id or user.id

    rodada = db.obter_rodada_ativa()
    if not rodada:
        if query:
            await query.answer("❌ Nenhuma rodada ativa.", show_alert=True)
        return

    # check if user already sent
    if db.usuario_ja_enviou_rodada(user_id, rodada[0]):
        if query:
            await query.answer("❌ Você já enviou seus palpites!", show_alert=True)
        return

    # initialize rascunho for user
    context.user_data["palpites"] = [None] * 14
    context.user_data["rodada_id"] = rodada[0]
    context.user_data["nome"] = user.full_name
    context.user_data["username"] = user.username or "Não informado"

    jogos = db.obter_jogos(rodada[0])
    texto, reply = build_planilha_text_and_keyboard(context.user_data["palpites"], jogos)

    # Edit the group message so the "second planilha" is the only visible
    if query:
        try:
            await query.edit_message_text(text=texto, parse_mode="Markdown", reply_markup=reply)
        except Exception:
            # fallback send privately
            try:
                await context.bot.send_message(chat_id=user.id, text=texto, parse_mode="Markdown", reply_markup=reply)
            except Exception:
                pass
    else:
        await context.bot.send_message(chat_id=user_id, text=texto, parse_mode="Markdown", reply_markup=reply)

# ---------------- estatísticas ----------------

async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rodada = db.obter_rodada_ativa()
    if not rodada:
        await update.message.reply_text("❌ Nenhuma rodada ativa.")
        return
    stats = db.obter_estatisticas_rodada(rodada[0])
    if not stats:
        await update.message.reply_text("📊 Ainda não há palpites.")
        return
    texto = f"📊 *ESTATÍSTICAS - {rodada[1]}* \n\n"
    texto += f"👥 Total de palpitadores: {stats['total_palpitadores']}\n\n"
    jogos = stats["jogos"]
    est = stats["estatisticas"]
    for i in range(14):
        try:
            t1 = jogos[i][2]
            t2 = jogos[i][3]
        except Exception:
            t1 = jogos[i][0]
            t2 = jogos[i][1]
        total = est[i]["1"] + est[i]["X"] + est[i]["2"]
        if total == 0:
            texto += f"{i+1}. {t1} x {t2}\nNinguém votou ainda.\n\n"
            continue
        texto += (
            f"{i+1}. *{t1} x {t2}*\n"
            f"1: {est[i]['1']} ({est[i]['1']/total*100:.1f}%) | "
            f"X: {est[i]['X']} ({est[i]['X']/total*100:.1f}%) | "
            f"2: {est[i]['2']} ({est[i]['2']/total*100:.1f}%)\n\n"
        )
    await update.message.reply_text(texto, parse_mode="Markdown")

# ---------------- ver_palpites (admin) ----------------

async def ver_palpites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != ADMIN_ID:
        await update.message.reply_text("❌ Apenas o admin pode usar este comando.")
        return

    rodada = db.obter_rodada_ativa()
    if not rodada:
        await update.message.reply_text("❌ Nenhuma rodada ativa.")
        return

    lista = db.obter_palpites_rodada(rodada[0])
    if not lista:
        await update.message.reply_text("❌ Nenhum palpite enviado.")
        return

    txt = f"📋 *Palpites — {rodada[1]}*\n\n"
    for p in lista:
        try:
            arr = json.loads(p[5])
        except Exception:
            arr = []
        txt += f"👤 {p[3]} (@{p[4]}) → {' '.join(arr)}\n⏰ {p[6]}\n---\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ---------------- main ----------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nova_rodada", nova_rodada))
    app.add_handler(CommandHandler("planilha", lambda u, c: abrir_planilha(u, c, u.effective_user.id)))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("ver_palpites", ver_palpites))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagens_rodada))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot v7.7 iniciando (run_polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()


