# bot_loteca_v6.py

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

# ---------------- logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("🔧 Iniciando bot v5...")
print(f"📋 Token: {BOT_TOKEN[:10]}...")
print(f"👤 Admin ID: {ADMIN_ID}")
print(f"🏠 Grupo ID: {GRUPO_ID}")

db = Database()

# ---------------- Estados em memória ----------------
# Cada usuário → [14 palpites]
user_palpites = {}

# Dados da última planilha enviada ao grupo
last_msg = {"chat_id": None, "message_id": None, "rodada_id": None, "nome_rodada": None}

# ---------------- Util ----------------
def safe_group_id():
    try:
        return int(GRUPO_ID)
    except:
        return int(str(GRUPO_ID).replace('"', "").replace("'", ""))

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🤖 *Bot da Loteca — v5*\n\n"
            "Use o botão *PREENCHER PALPITES* quando a rodada for aberta.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🤖 *Bot da Loteca — v5*\n\n"
            "Comandos disponíveis:\n"
            "/nova_rodada (admin)\n"
            "/estatisticas\n"
            "/ver_palpites\n"
            "/meus_palpites\n\n"
            "A planilha aparece *no grupo*, não aqui.",
            parse_mode="Markdown"
        )

# ------------------ CRIAR NOVA RODADA ------------------
async def nova_rodada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ Apenas o administrador pode usar /nova_rodada.")
        return

    context.user_data["criando"] = True
    context.user_data["etapa"] = "nome"

    await update.message.reply_text(
        "🆕 *Criar nova rodada*\n\n"
        "Envie o *nome do concurso*.\n"
        "Ex.: Concurso Loteca 1234",
        parse_mode="Markdown"
    )

async def processar_mensagens_rodada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("criando"):
        return

    if str(update.effective_user.id) != ADMIN_ID:
        return

    texto = update.message.text.strip()

    if texto.lower() == "/cancelar":
        context.user_data.clear()
        await update.message.reply_text("❌ Operação cancelada.")
        return

    etapa = context.user_data["etapa"]

    # ---- etapa 1: nome ----
    if etapa == "nome":
        context.user_data["nome"] = texto
        context.user_data["etapa"] = "jogos"

        await update.message.reply_text(
            "📋 Envie agora os *14 jogos separados por vírgula*.\n\n"
            "Exemplo:\n"
            "Flamengo x Vasco, São Paulo x Corinthians, ... , Náutico x Sport",
            parse_mode="Markdown"
        )
        return

    # ---- etapa 2: jogos ----
    if etapa == "jogos":
        partes = [p.strip() for p in texto.split(",") if p.strip() != ""]
        if len(partes) != 14:
            await update.message.reply_text("❌ Envie exatamente 14 jogos separados por vírgula.")
            return

        jogos = []
        for p in partes:
            if " x " in p:
                t1, t2 = p.split(" x ", 1)
            elif "x" in p:
                t1, t2 = p.split("x", 1)
            else:
                await update.message.reply_text("❌ Formato inválido. Use Time1 x Time2.")
                return
            jogos.append((t1.strip(), t2.strip()))

        nome = context.user_data["nome"]

        try:
            rodada_id = db.criar_nova_rodada(nome)
            db.inserir_jogos(jogos, rodada_id)

            # Reset global state
            global user_palpites, last_msg
            user_palpites = {}
            last_msg = {"chat_id": None, "message_id": None, "rodada_id": rodada_id, "nome_rodada": nome}

            await update.message.reply_text(f"🎉 Rodada *{nome}* criada com sucesso!", parse_mode="Markdown")

            await postar_planilha_no_grupo(context, rodada_id, nome)

            context.user_data.clear()

        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao criar rodada: {e}")
            logger.exception(e)

# ------------------ CONSTRUIR PLANILHA INTERATIVA ------------------
def montar_planilha_interativa(jogos, nome_rodada, user_palpite=None):
    linhas = []
    linhas.append(f"📊 *{nome_rodada.upper()}*")
    linhas.append("")
    
    if user_palpite:
        # Mostra visualização dos palpites atuais
        palpites_display = []
        for i, pal in enumerate(user_palpite):
            if pal == "1":
                palpites_display.append(f"{i+1}:✅")
            elif pal == "X":
                palpites_display.append(f"{i+1}:✅") 
            elif pal == "2":
                palpites_display.append(f"{i+1}:✅")
            else:
                palpites_display.append(f"{i+1}:⚪")
        
        linhas.append("📝 *SEUS PALPITES ATUAIS:*")
        linhas.append(" ".join(palpites_display))
        linhas.append("")
        
        # Conta quantos faltam
        faltando = user_palpite.count(None)
        if faltando > 0:
            linhas.append(f"⚠️ *Faltam {faltando} jogos*")
        else:
            linhas.append("✅ *Todos os jogos preenchidos!*")
            
        linhas.append("")
    
    linhas.append("Clique nos botões abaixo para fazer seus palpites!")
    linhas.append("")

    texto = "\n".join(linhas)

    # Teclado com 4 colunas: Nº (inativo), Time1, X, Time2
    kb = []
    for i in range(14):
        row = jogos[i]
        if len(row) >= 4:
            short_t1 = row[2][:12]
            short_t2 = row[3][:12]
        else:
            short_t1 = row[0][:12]
            short_t2 = row[1][:12]

        # Destaca o botão selecionado
        palpite_atual = user_palpite[i] if user_palpite else None
        
        btn_t1 = f"✅{short_t1}" if palpite_atual == "1" else short_t1
        btn_x = "✅X" if palpite_atual == "X" else "X"
        btn_t2 = f"{short_t2}✅" if palpite_atual == "2" else short_t2

        kb.append([
            InlineKeyboardButton(str(i+1), callback_data=f"noop_{i}"),
            InlineKeyboardButton(btn_t1, callback_data=f"t1_{i}"),
            InlineKeyboardButton(btn_x, callback_data=f"x_{i}"),
            InlineKeyboardButton(btn_t2, callback_data=f"t2_{i}")
        ])

    kb.append([InlineKeyboardButton("🚀 ENVIAR PALPITES", callback_data="enviar")])
    kb.append([InlineKeyboardButton("📊 VER MEUS PALPITES", callback_data="meus_palpites")])

    return texto, InlineKeyboardMarkup(kb)

# ------------------ CONSTRUIR PLANILHA FINAL ------------------
def montar_planilha_final(display, jogos, user_name, nome_rodada):
    linhas = []
    linhas.append(f"📊 *{nome_rodada.upper()}*")
    linhas.append(f"✅ *PALPITES DE {user_name.upper()}*")
    linhas.append("")
    linhas.append("| JG | 1 | MANDANTE | X | VISITANTE | 2 |")
    linhas.append("|----|---|----------|---|-----------|---|")
    
    for i in range(14):
        n = i + 1
        row = jogos[i]
        if len(row) >= 4:
            t1 = row[2]
            t2 = row[3]
        else:
            t1 = row[0]
            t2 = row[1]

        pal = display[i]
        
        # Formata os times para caber na tabela
        t1_short = t1[:10] if len(t1) > 10 else t1.ljust(10)
        t2_short = t2[:10] if len(t2) > 10 else t2.ljust(10)
        
        # Define os emojis baseados na seleção
        emoji_1 = "✅" if pal == "1" else "□"
        emoji_x = "✅" if pal == "X" else "□" 
        emoji_2 = "✅" if pal == "2" else "□"
        
        linhas.append(f"| {n:2d} | {emoji_1} | {t1_short} | {emoji_x} | {t2_short} | {emoji_2} |")

    linhas.append("")
    linhas.append("🎉 *Palpites enviados com sucesso!*")

    texto = "\n".join(linhas)
    return texto, None

# ------------------ POSTAR PLANILHA NO GRUPO ------------------
async def postar_planilha_no_grupo(context, rodada_id, nome_rodada):
    gid = safe_group_id()
    jogos = db.obter_jogos(rodada_id)

    texto, reply = montar_planilha_interativa(jogos, nome_rodada)

    msg = await context.bot.send_message(
        gid, texto, reply_markup=reply, parse_mode="Markdown"
    )

    last_msg["chat_id"] = msg.chat_id
    last_msg["message_id"] = msg.message_id
    last_msg["rodada_id"] = rodada_id
    last_msg["nome_rodada"] = nome_rodada

# ------------------ ATUALIZAR PLANILHA NO GRUPO ------------------
async def atualizar_planilha_grupo(context, user_id, rodada_id, user_name=None, enviado=False):
    jogos = db.obter_jogos(rodada_id)
    nome_rodada = last_msg["nome_rodada"]
    
    if enviado and user_name:
        # Mostra a planilha final no estilo da imagem
        user_palpite = user_palpites.get(user_id, [None] * 14)
        texto, reply = montar_planilha_final(user_palpite, jogos, user_name, nome_rodada)
    else:
        # Mostra a planilha interativa com visualização do usuário
        user_palpite = user_palpites.get(user_id, [None] * 14)
        texto, reply = montar_planilha_interativa(jogos, nome_rodada, user_palpite)

    try:
        if reply:
            await context.bot.edit_message_text(
                chat_id=last_msg["chat_id"],
                message_id=last_msg["message_id"],
                text=texto,
                reply_markup=reply,
                parse_mode="Markdown"
            )
        else:
            await context.bot.edit_message_text(
                chat_id=last_msg["chat_id"],
                message_id=last_msg["message_id"],
                text=texto,
                parse_mode="Markdown"
            )
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar planilha: {e}")
        return False

# ------------------ CALLBACK ------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    await query.answer()

    # ---- garantir rodada do user ----
    if "rodada_id" not in context.user_data:
        context.user_data["rodada_id"] = last_msg["rodada_id"]

    rodada_id = context.user_data["rodada_id"]

    # ---- NOOP ----
    if data.startswith("noop_"):
        return

    # ---- MEUS PALPITES ----
    if data == "meus_palpites":
        await mostrar_meus_palpites(user, rodada_id, query)
        return

    # ---- garantir rascunho por usuário ----
    if user.id not in user_palpites:
        user_palpites[user.id] = [None] * 14

    # ---- Clique Time1/X/Time2 ----
    if data.startswith(("t1_", "x_", "t2_")):
        tipo, idx = data.split("_")
        idx = int(idx)

        # Atualiza apenas o palpite do usuário atual
        if tipo == "t1":
            user_palpites[user.id][idx] = "1"
            await query.answer(f"✅ Jogo {idx+1}: Time 1", show_alert=False)
        elif tipo == "x":
            user_palpites[user.id][idx] = "X"
            await query.answer(f"✅ Jogo {idx+1}: Empate", show_alert=False)
        elif tipo == "t2":
            user_palpites[user.id][idx] = "2"
            await query.answer(f"✅ Jogo {idx+1}: Time 2", show_alert=False)

        # Atualiza a planilha no grupo com visualização do usuário
        await atualizar_planilha_grupo(context, user.id, rodada_id)

        return

    # ---- ENVIAR PALPITES ----
    if data == "enviar":
        pal = user_palpites.get(user.id, [None] * 14)

        # Verifica se todos os palpites estão preenchidos
        if None in pal:
            jogos_faltando = [i+1 for i, p in enumerate(pal) if p is None]
            await query.answer(f"⚠️ Complete os jogos: {', '.join(map(str, jogos_faltando))}", show_alert=True)
            return

        # verifica duplicata
        if db.usuario_ja_enviou_rodada(user.id, rodada_id):
            await query.answer("⚠️ Você já enviou seus palpites para esta rodada.", show_alert=True)
            return

        try:
            success = db.salvar_palpite(
                rodada_id,
                user.id,
                user.full_name,
                user.username or "",
                pal
            )
            
            if success:
                await query.answer("🎉 Palpites enviados com sucesso!", show_alert=True)
                
                # FECHA A PLANILHA NO GRUPO (mostra planilha final no estilo da imagem)
                await atualizar_planilha_grupo(context, user.id, rodada_id, user.full_name, enviado=True)
                
                # Remove os palpites temporários do usuário
                if user.id in user_palpites:
                    del user_palpites[user.id]
                    
                # Envia confirmação por mensagem privada
                try:
                    palpites_str = " ".join(pal)
                    await context.bot.send_message(
                        user.id,
                        f"✅ *Palpites enviados com sucesso!*\n\n"
                        f"📋 Seus palpites para a rodada:\n"
                        f"`{palpites_str}`\n\n"
                        f"Boa sorte! 🍀",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f" Não foi possível enviar mensagem privada para {user.id}: {e}")
                    
            else:
                await query.answer("❌ Erro ao salvar palpites.", show_alert=True)

        except Exception as e:
            logger.exception(f"Erro ao salvar palpite: {e}")
            await query.answer("❌ Erro interno ao salvar.", show_alert=True)

        return

# ------------------ MOSTRAR MEUS PALPITES ------------------
async def mostrar_meus_palpites(user, rodada_id, query):
    rodada = db.obter_rodada_ativa()
    if not rodada:
        await query.answer("❌ Nenhuma rodada ativa.", show_alert=True)
        return

    # Verifica se já enviou palpites
    if db.usuario_ja_enviou_rodada(user.id, rodada_id):
        palpites = db.obter_palpites_rodada(rodada_id)
        meus_palpites = next((p for p in palpites if p[2] == user.id), None)
        if meus_palpites:
            arr = json.loads(meus_palpites[5])
            palpites_str = " ".join(arr)
            await query.answer(f"📋 SEUS PALPITES ENVIADOS:\n{palpites_str}", show_alert=True)
        return

    # Mostra rascunho atual
    if user.id in user_palpites:
        pal = user_palpites[user.id]
        palpites_display = []
        for i, p in enumerate(pal):
            if p == "1":
                palpites_display.append(f"{i+1}:✅")
            elif p == "X":
                palpites_display.append(f"{i+1}:✅")
            elif p == "2":
                palpites_display.append(f"{i+1}:✅")
            else:
                palpites_display.append(f"{i+1}:⚪")
        
        palpites_str = " ".join(palpites_display)
        completos = all(p is not None for p in pal)
        status = "✅ PRONTO PARA ENVIAR" if completos else "⚠️ INCOMPLETO"
        await query.answer(f"📝 SEUS RASCUNHOS ({status}):\n{palpites_str}\n\n{'🚀 Clique em ENVIAR para confirmar!' if completos else '⚠️ Complete todos os jogos!'}", show_alert=True)
    else:
        await query.answer("📝 Você ainda não começou a preencher seus palpites.", show_alert=True)

# ------------------ MEUS PALPITES (COMANDO) ------------------
async def meus_palpites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rodada = db.obter_rodada_ativa()
    
    if not rodada:
        await update.message.reply_text("❌ Nenhuma rodada ativa no momento.")
        return

    # Verifica se já enviou palpites
    if db.usuario_ja_enviou_rodada(user.id, rodada[0]):
        palpites = db.obter_palpites_rodada(rodada[0])
        meus_palpites = next((p for p in palpites if p[2] == user.id), None)
        if meus_palpites:
            arr = json.loads(meus_palpites[5])
            texto = f"📋 *SEUS PALPITES - {rodada[1]}*\n\n"
            texto += f"`{' '.join(arr)}`"
            texto += f"\n\n⏰ Enviado em: {meus_palpites[6]}"
            await update.message.reply_text(texto, parse_mode="Markdown")
        return

    # Mostra rascunho atual
    if user.id in user_palpites:
        pal = user_palpites[user.id]
        texto = f"📋 *RASCUNHO ATUAL - {rodada[1]}*\n\n"
        palpites_display = []
        for i, p in enumerate(pal):
            if p == "1":
                palpites_display.append(f"{i+1}:✅")
            elif p == "X":
                palpites_display.append(f"{i+1}:✅")
            elif p == "2":
                palpites_display.append(f"{i+1}:✅")
            else:
                palpites_display.append(f"{i+1}:⚪")
        
        texto += " ".join(palpites_display)
        completos = all(p is not None for p in pal)
        status = "✅ PRONTO PARA ENVIAR" if completos else "⚠️ INCOMPLETO"
        texto += f"\n\n*Status:* {status}"
        texto += "\n\n⚠️ *Atenção:* Estes são apenas rascunhos. Clique em 'ENVIAR PALPITES' na planilha do grupo para confirmar."
        await update.message.reply_text(texto, parse_mode="Markdown")
    else:
        await update.message.reply_text("📝 Você ainda não começou a preencher seus palpites. Vá para o grupo e clique na planilha!")

# ------------------ ESTATÍSTICAS ------------------
async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rodada = db.obter_rodada_ativa()
    if not rodada:
        await update.message.reply_text("❌ Nenhuma rodada ativa.")
        return

    stats = db.obter_estatisticas_rodada(rodada[0])
    if not stats:
        await update.message.reply_text("📊 Nenhum palpite ainda.")
        return

    texto = f"📊 *ESTATÍSTICAS - {rodada[1]}*\n\n"
    texto += f"👥 Total de palpitadores: {stats['total_palpitadores']}\n\n"

    jogos = stats["jogos"]
    est = stats["estatisticas"]

    for i in range(14):
        try:
            t1 = jogos[i][2]
            t2 = jogos[i][3]
        except:
            t1, t2 = jogos[i]

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

# ------------------ VER PALPITES ADMIN ------------------
async def ver_palpites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ Apenas o admin pode usar.")
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
    txt += f"👥 Total: {len(lista)} palpitadores\n\n"

    for p in lista:
        arr = json.loads(p[5])
        username = f"@{p[4]}" if p[4] else "(sem username)"
        txt += f"👤 {p[3]} ({username})\n"
        txt += f"📋 {' '.join(arr)}\n"
        txt += f"⏰ {p[6]}\n"
        txt += "─" * 30 + "\n"

    # Divide em partes se for muito longo
    if len(txt) > 4000:
        parts = [txt[i:i+4000] for i in range(0, len(txt), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(txt, parse_mode="Markdown")

# ------------------ MAIN ------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nova_rodada", nova_rodada))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("ver_palpites", ver_palpites))
    app.add_handler(CommandHandler("meus_palpites", meus_palpites))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagens_rodada))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Bot v5 iniciado!")
    app.run_polling()

if __name__ == "__main__":
    main()
