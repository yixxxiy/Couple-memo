import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, MenuButtonCommands
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
import os

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WAITING_TASK = 1
WAITING_DATE = 2
WAITING_MEMORY = 3

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────
# DATABASE
# ─────────────────────────────
def init_db():
    conn = sqlite3.connect("couple_memo.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            added_by TEXT,
            added_at TEXT,
            due_date TEXT,
            done INTEGER DEFAULT 0,
            done_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            added_by TEXT,
            added_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("couple_memo.db")

# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def safe_answer(query):
    async def inner():
        try:
            await query.answer()
        except:
            pass
    return inner()

def get_name(user):
    return user.first_name or "匿名"

def fmt_time(dt_str):
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        return dt.strftime("%m月%d日")
    except:
        return dt_str or ""

def pending_count():
    conn = db()
    c = conn.execute("SELECT COUNT(*) FROM tasks WHERE done=0").fetchone()[0]
    conn.close()
    return c

def done_count():
    conn = db()
    c = conn.execute("SELECT COUNT(*) FROM tasks WHERE done=1").fetchone()[0]
    conn.close()
    return c

# ─────────────────────────────
# UI
# ─────────────────────────────
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ 添加事项", callback_data="add")],
        [
            InlineKeyboardButton(f"📋 待办 ({pending_count()})", callback_data="list_pending"),
            InlineKeyboardButton(f"✅ 完成 ({done_count()})", callback_data="list_done")
        ],
        [InlineKeyboardButton("🧠 情侣记忆库", callback_data="memory")],
        [
            InlineKeyboardButton("🔔 标记完成", callback_data="mark_done"),
            InlineKeyboardButton("🗑️ 删除事项", callback_data="delete")
        ]
    ])

def home_message():
    return (
        "💑 *CoupleMemo 小助手*\n\n"
        f"当前还有 *{pending_count()}* 件小任务等待你们完成。\n"
        "把琐事交给我，你们负责开心恋爱。"
    )

# ─────────────────────────────
# INIT COMMAND MENU
# ─────────────────────────────
async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("menu", "打开主菜单"),
        BotCommand("add", "添加事项"),
        BotCommand("list", "查看待办"),
        BotCommand("cancel", "取消操作")
    ])
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

# ─────────────────────────────
# BASIC COMMANDS
# ─────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(home_message(), parse_mode="Markdown", reply_markup=main_keyboard())

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(home_message(), parse_mode="Markdown", reply_markup=main_keyboard())

# ─────────────────────────────
# ADD TASK FLOW
# ─────────────────────────────
async def cb_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.message.reply_text("请输入要添加的事项（可一行一条）")
    return WAITING_TASK

async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("请输入要添加的事项（可一行一条）")
    return WAITING_TASK

async def receive_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = [x.strip() for x in update.message.text.splitlines() if x.strip()]
    ctx.user_data['pending_tasks'] = tasks
    ctx.user_data['pending_name'] = get_name(update.effective_user)
    preview = '\n'.join([f'✦ {t}' for t in tasks])
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ 设置期待完成日期", callback_data="set_date")],
        [InlineKeyboardButton("⚡ 直接保存", callback_data="skip_date")]
    ])
    await update.message.reply_text(f"即将添加：\n{preview}\n\n要设置期待完成日期吗？", reply_markup=keyboard)
    return WAITING_DATE

async def cb_set_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.message.reply_text("请输入期待完成日期：\n格式：2026-05-01")
    return WAITING_DATE

async def cb_skip_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await save_tasks(query.message, ctx, None)
    return ConversationHandler.END

async def receive_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        due = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
        await save_tasks(update.message, ctx, due)
        return ConversationHandler.END
    except:
        await update.message.reply_text("日期格式错误，请重新输入：2026-05-01")
        return WAITING_DATE

async def save_tasks(msg, ctx, due_date):
    tasks = ctx.user_data.get('pending_tasks', [])
    by = ctx.user_data.get('pending_name', '匿名')
    at = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    for task in tasks:
        conn.execute("INSERT INTO tasks (task, added_by, added_at, due_date) VALUES (?,?,?,?)", (task, by, at, due_date))
    conn.commit()
    conn.close()
    await msg.reply_text(f"已帮你们记下 {len(tasks)} 件小事 💗", reply_markup=main_keyboard())

# ─────────────────────────────
# LIST TASKS
# ─────────────────────────────
async def cb_list_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    conn = db()
    rows = conn.execute("SELECT task, added_by, due_date FROM tasks WHERE done=0 ORDER BY id ASC").fetchall()
    conn.close()
    if not rows:
        await query.message.reply_text("待办是空的，你们最近很勤快哦。", reply_markup=main_keyboard())
        return
    text = "📋 *待办清单*\n\n"
    for t, by, due in rows:
        due_line = f"\n⏳期待完成：{fmt_time(due)}" if due else ""
        text += f"✦ {t}\n——{by}{due_line}\n\n"
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def cb_list_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    conn = db()
    rows = conn.execute("SELECT task, added_by FROM tasks WHERE done=1 ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    if not rows:
        await query.message.reply_text("还没有完成事项记录哦。", reply_markup=main_keyboard())
        return
    text = "✅ *完成归档*\n\n"
    for t, by in rows:
        text += f"~{t}~\n——{by}\n\n"
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

# ─────────────────────────────
# MEMORY VAULT
# ─────────────────────────────
async def cb_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    conn = db()
    rows = conn.execute("SELECT content, added_by FROM memories ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    text = "🧠 *情侣记忆库*\n\n"
    if rows:
        for m, by in rows:
            text += f"✦ {m}\n——{by}\n\n"
    else:
        text += "这里还没有共同记忆。\n\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ 添加记忆", callback_data="add_memory")],
        [InlineKeyboardButton("← 返回", callback_data="back")]
    ])
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def cb_add_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.message.reply_text("请输入想存进记忆库的话：")
    return WAITING_MEMORY

async def receive_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    by = get_name(update.effective_user)
    at = datetime.now().strftime("%Y-%m-%d")
    conn = db()
    conn.execute("INSERT INTO memories (content, added_by, added_at) VALUES (?,?,?)", (text, by, at))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"已存入共同记忆：\n✦ {text}\n——{by}", reply_markup=main_keyboard())
    return ConversationHandler.END

# ─────────────────────────────
# PLACEHOLDER DELETE/DONE/BACK
# ─────────────────────────────
async def cb_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    await query.message.reply_text(home_message(), parse_mode="Markdown", reply_markup=main_keyboard())

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("已取消当前操作。", reply_markup=main_keyboard())
    return ConversationHandler.END

# ─────────────────────────────
# MAIN
# ─────────────────────────────
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_add, pattern="^add$"),
            CommandHandler("add", add_cmd),
            CallbackQueryHandler(cb_add_memory, pattern="^add_memory$")
        ],
        states={
            WAITING_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task)],
            WAITING_DATE: [
                CallbackQueryHandler(cb_set_date, pattern="^set_date$"),
                CallbackQueryHandler(cb_skip_date, pattern="^skip_date$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)
            ],
            WAITING_MEMORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_memory)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_list_pending, pattern="^list_pending$"))
    app.add_handler(CallbackQueryHandler(cb_list_done, pattern="^list_done$"))
    app.add_handler(CallbackQueryHandler(cb_memory, pattern="^memory$"))
    app.add_handler(CallbackQueryHandler(cb_back, pattern="^back$"))

    print("💑 CoupleMemo Bot V2 Running...")
    app.run_polling()

if __name__ == '__main__':
    main()
