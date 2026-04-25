import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, MenuButtonCommands
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters,
    Application
)

# ───────────────────────────────────────────────
#  配置区  ← 只需改这里
# ───────────────────────────────────────────────
BOT_TOKEN = "8218703598:AAENjgmoumV26rQkrMbytEgoiKMUGW2SW-I"    # @BotFather 获取
# ───────────────────────────────────────────────

WAITING_TASK        = 1
WAITING_REMIND_TIME = 2

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  数据库
# ══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect("couple_memo.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            task      TEXT    NOT NULL,
            added_by  TEXT,
            added_at  TEXT,
            remind_at TEXT,
            done      INTEGER DEFAULT 0,
            done_at   TEXT
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("couple_memo.db")


# ══════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════
def get_name(user) -> str:
    """用 Telegram 的 first_name，不需要预设 ID"""
    return user.first_name or "你"

def fmt_time(dt_str: str) -> str:
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%m月%d日 %H:%M")
    except Exception:
        return dt_str or ""

def pending_count() -> int:
    c = db().execute("SELECT COUNT(*) FROM tasks WHERE done=0").fetchone()
    return c[0] if c else 0

def done_count() -> int:
    c = db().execute("SELECT COUNT(*) FROM tasks WHERE done=1").fetchone()
    return c[0] if c else 0


# ══════════════════════════════════════════════
#  键盘 & 消息模板
# ══════════════════════════════════════════════
def main_keyboard():
    p = pending_count()
    d = done_count()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕  添加事项", callback_data="add")],
        [
            InlineKeyboardButton(f"📋  待办清单  ({p})", callback_data="list_pending"),
            InlineKeyboardButton(f"✅  已完成  ({d})",   callback_data="list_done"),
        ],
        [
            InlineKeyboardButton("🔔  标记完成", callback_data="mark_done"),
            InlineKeyboardButton("🗑️  删除事项", callback_data="delete"),
        ],
    ])

def home_message() -> str:
    p = pending_count()
    return (
        "┌──────────────────────────\n"
        "│  💑  *情侣备忘录*\n"
        "├──────────────────────────\n"
        f"│  📌  待完成事项：*{p} 件*\n"
        "│  两人共同管理，一起搞定！\n"
        "└──────────────────────────"
    )


# ══════════════════════════════════════════════
#  启动时注册命令菜单（让用户打开就看到按钮）
# ══════════════════════════════════════════════
async def post_init(app: Application):
    """Bot 启动后自动设置命令列表和菜单按钮"""
    commands = [
        BotCommand("menu",  "📋 打开主菜单"),
        BotCommand("add",   "➕ 添加事项"),
        BotCommand("list",  "📋 查看待办"),
        BotCommand("done",  "✅ 标记完成"),
        BotCommand("cancel","✖️ 取消当前操作"),
    ]
    await app.bot.set_my_commands(commands)
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("命令菜单已注册")


# ══════════════════════════════════════════════
#  /start  /menu  /list  /add  /done
# ══════════════════════════════════════════════
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = get_name(update.effective_user)
    await update.message.reply_text(
        f"你好 *{name}*！\n\n" + home_message(),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        home_message(),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/list 命令直接显示待办"""
    rows = db().execute(
        "SELECT id, task, added_by, added_at, remind_at FROM tasks WHERE done=0 ORDER BY id ASC"
    ).fetchall()
    if not rows:
        await update.message.reply_text(
            "🎉  *待办清单是空的！*",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return
    lines = ["📋  *待办清单*\n"]
    for i, (id_, task, by, at, remind) in enumerate(rows, 1):
        remind_line = f"\n        🔔 {fmt_time(remind)}" if remind else ""
        lines.append(f"`{i:02d}`  {task}\n        {by}  ·  {fmt_time(at)}{remind_line}\n")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/add 命令直接进入添加流程"""
    await update.message.reply_text(
        "✏️  *请输入要添加的事项：*\n\n每行一个，可以一次发多条。\n发送 /cancel 取消。",
        parse_mode="Markdown"
    )
    return WAITING_TASK

async def done_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/done 命令直接进入标记完成"""
    rows = db().execute(
        "SELECT id, task, added_by FROM tasks WHERE done=0 ORDER BY id ASC"
    ).fetchall()
    if not rows:
        await update.message.reply_text("🎉  没有待完成的事项！", reply_markup=main_keyboard())
        return
    buttons = [
        [InlineKeyboardButton(f"✦  {r[1]}  ({r[2]})", callback_data=f"done_{r[0]}")]
        for r in rows
    ]
    buttons.append([InlineKeyboardButton("← 返回", callback_data="back")])
    await update.message.reply_text(
        "✅  *选择要完成的事项：*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ══════════════════════════════════════════════
#  查看待办（按钮触发）
# ══════════════════════════════════════════════
async def cb_list_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db().execute(
        "SELECT id, task, added_by, added_at, remind_at FROM tasks WHERE done=0 ORDER BY id ASC"
    ).fetchall()
    if not rows:
        await query.message.reply_text(
            "🎉  *待办清单是空的！*",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return
    lines = ["📋  *待办清单*\n"]
    for i, (id_, task, by, at, remind) in enumerate(rows, 1):
        remind_line = f"\n        🔔 {fmt_time(remind)}" if remind else ""
        lines.append(f"`{i:02d}`  {task}\n        {by}  ·  {fmt_time(at)}{remind_line}\n")
    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════
#  查看已完成
# ══════════════════════════════════════════════
async def cb_list_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db().execute(
        "SELECT task, added_by, done_at FROM tasks WHERE done=1 ORDER BY done_at DESC LIMIT 20"
    ).fetchall()
    if not rows:
        await query.message.reply_text("还没有完成的事项哦，加油！💪", reply_markup=main_keyboard())
        return
    lines = ["✅  *已完成*\n"]
    for task, by, done_at in rows:
        lines.append(f"~{task}~\n        {by}  ·  {fmt_time(done_at)}\n")
    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════
#  添加事项（对话流程）
# ══════════════════════════════════════════════
async def cb_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "✏️  *请输入要添加的事项：*\n\n每行一个，可以一次发多条。\n发送 /cancel 取消。",
        parse_mode="Markdown"
    )
    return WAITING_TASK

async def receive_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]
    ctx.user_data["pending_tasks"] = lines
    ctx.user_data["pending_name"]  = get_name(update.effective_user)
    preview = "\n".join(f"  ✦ {l}" for l in lines)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰  设置提醒时间", callback_data="set_remind")],
        [InlineKeyboardButton("⚡  直接保存",    callback_data="skip_remind")],
    ])
    await update.message.reply_text(
        f"📝  *即将添加：*\n{preview}\n\n是否设置提醒？",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return WAITING_REMIND_TIME

async def cb_set_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔔  请输入提醒时间：\n`格式：2025-06-01 14:30`",
        parse_mode="Markdown"
    )
    return WAITING_REMIND_TIME

async def cb_skip_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _save_tasks(query.message, ctx, remind_at=None)
    return ConversationHandler.END

async def receive_remind_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        remind_dt  = datetime.strptime(text, "%Y-%m-%d %H:%M")
        remind_str = remind_dt.strftime("%Y-%m-%d %H:%M")
        delay      = (remind_dt - datetime.now()).total_seconds()
        if delay > 0:
            tasks_str = "、".join(ctx.user_data.get("pending_tasks", []))
            ctx.job_queue.run_once(
                _send_reminder,
                when=delay,
                data={"tasks": tasks_str, "chat_id": update.effective_chat.id},
            )
        await _save_tasks(update.message, ctx, remind_at=remind_str)
    except ValueError:
        await update.message.reply_text(
            "❌  格式不对，请用：`2025-06-01 14:30`",
            parse_mode="Markdown"
        )
        return WAITING_REMIND_TIME
    return ConversationHandler.END

async def _save_tasks(msg, ctx, remind_at):
    tasks  = ctx.user_data.get("pending_tasks", [])
    by     = ctx.user_data.get("pending_name", "未知")
    at_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn   = db()
    for task in tasks:
        conn.execute(
            "INSERT INTO tasks (task, added_by, added_at, remind_at) VALUES (?,?,?,?)",
            (task, by, at_str, remind_at)
        )
    conn.commit()
    conn.close()
    remind_line = f"\n🔔  提醒：{fmt_time(remind_at)}" if remind_at else ""
    preview     = "\n".join(f"  ✦ {t}" for t in tasks)
    await msg.reply_text(
        f"✅  *已添加 {len(tasks)} 件事项！*\n\n{preview}{remind_line}",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def _send_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    job = ctx.job
    await ctx.bot.send_message(
        chat_id=job.data["chat_id"],
        text=f"🔔  *提醒到啦！*\n\n📌  {job.data['tasks']}",
        parse_mode="Markdown"
    )

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("已取消。", reply_markup=main_keyboard())
    return ConversationHandler.END


# ══════════════════════════════════════════════
#  标记完成
# ══════════════════════════════════════════════
async def cb_mark_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db().execute(
        "SELECT id, task, added_by FROM tasks WHERE done=0 ORDER BY id ASC"
    ).fetchall()
    if not rows:
        await query.message.reply_text("🎉  没有待完成的事项了！", reply_markup=main_keyboard())
        return
    buttons = [
        [InlineKeyboardButton(f"✦  {r[1]}  ({r[2]})", callback_data=f"done_{r[0]}")]
        for r in rows
    ]
    buttons.append([InlineKeyboardButton("← 返回", callback_data="back")])
    await query.message.reply_text(
        "✅  *选择要完成的事项：*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cb_do_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[1])
    done_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn    = db()
    row     = conn.execute("SELECT task FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.execute("UPDATE tasks SET done=1, done_at=? WHERE id=?", (done_at, task_id))
    conn.commit()
    conn.close()
    task_name = row[0] if row else "事项"
    who       = get_name(update.effective_user)
    await query.message.reply_text(
        f"🎉  *完成！*\n\n✦  {task_name}\n    {who} 标记完成",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════
#  删除事项
# ══════════════════════════════════════════════
async def cb_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = db().execute(
        "SELECT id, task, done FROM tasks ORDER BY done ASC, id DESC LIMIT 30"
    ).fetchall()
    if not rows:
        await query.message.reply_text("清单是空的！", reply_markup=main_keyboard())
        return
    buttons = []
    for id_, task, done in rows:
        status = "✅" if done else "○"
        buttons.append([InlineKeyboardButton(f"{status}  {task}", callback_data=f"del_{id_}")])
    buttons.append([InlineKeyboardButton("← 返回", callback_data="back")])
    await query.message.reply_text(
        "🗑️  *选择要删除的事项：*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cb_do_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[1])
    conn    = db()
    row     = conn.execute("SELECT task FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    task_name = row[0] if row else "事项"
    await query.message.reply_text(
        f"🗑️  已删除：*{task_name}*",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════
#  返回主菜单
# ══════════════════════════════════════════════
async def cb_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        home_message(),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════
def main():
    init_db()
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)   # ← 启动后自动注册命令菜单
        .build()
    )

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_add, pattern="^add$"),
            CommandHandler("add", add_cmd),
        ],
        states={
            WAITING_TASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task)
            ],
            WAITING_REMIND_TIME: [
                CallbackQueryHandler(cb_set_remind,  pattern="^set_remind$"),
                CallbackQueryHandler(cb_skip_remind, pattern="^skip_remind$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remind_time),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("menu",   menu_cmd))
    app.add_handler(CommandHandler("list",   list_cmd))
    app.add_handler(CommandHandler("done",   done_cmd))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_list_pending, pattern="^list_pending$"))
    app.add_handler(CallbackQueryHandler(cb_list_done,    pattern="^list_done$"))
    app.add_handler(CallbackQueryHandler(cb_mark_done,    pattern="^mark_done$"))
    app.add_handler(CallbackQueryHandler(cb_do_done,      pattern="^done_\\d+$"))
    app.add_handler(CallbackQueryHandler(cb_delete,       pattern="^delete$"))
    app.add_handler(CallbackQueryHandler(cb_do_delete,    pattern="^del_\\d+$"))
    app.add_handler(CallbackQueryHandler(cb_back,         pattern="^back$"))

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  💑  情侣备忘录 Bot 已启动")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling()

if __name__ == "__main__":
    main()