import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# الإعدادات
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
DB_PATH = 'bot_v3.db'
OWNER_ID = 123456789  # !!! يجب استبداله بمعرف المالك الحقيقي !!!
BAN_LOG_CHANNEL = "-100123456789"  # !!! يجب استبداله بمعرف قناة سجل المحظورين (مع -100) !!!

# --- ميثاق الاستخدام ---
TERMS_TEXT = """
⚠️ قوانين وقواعد استخدام البوت (إلزامي)

بإستخدامك لهذا البوت، أنت تقر بالالتزام بالقواعد التالية، وأي مخالفة تعرض حسابك للحظر النهائي ومصادرة النقاط:

1. المتابعة والاشتراك:
 * يمنع منعاً باتاً إلغاء المتابعة من أي قناة حصلت على نقاط منها.
 * يتم مراقبة الاشتراكات بشكل دوري من قبل "فريق العمل" (العمال).
 * في حال إلغاء المتابعة، سيتم خصم 3 أضعاف النقاط التي كسبتها كعقوبة أولية.
2. نظام البلاغات:
 * يحق لكل مستخدم التبليغ عن نقص المتابعين عبر أمر /report.
 * عند تلقيك طلباً من "العامل" لإثبات المتابعة (Screenshot)، يجب الرد خلال المدة المحددة (ساعة واحدة)، والتجاهل يعني إقرارك بالغش والحظر التلقائي.
 * البلاغ الكاذب: إذا قمت بالتبليغ عن مستخدم وهو لا يزال متابعاً لك، سيتم خصم نقاط من رصيدك ومنحها له كتعويض عن الإزعاج.
3. الحسابات والقنوات:
 * يمنع إضافة قنوات تحتوي على محتوى (مخالف للسياسات، إباحي، أو محرض). للأدمن الحق في حذف القناة دون رد النقاط.
 * يمنع استخدام حسابات "وهمية" أو "بوتات" للمتابعة؛ يجب أن يكون الحساب حقيقياً وبصورة شخصية.
4. التعامل مع الإدارة (العمال والأدمن):
 * قرارات العامل في فض النزاعات نهائية، ولا تجوز مراجعتها إلا عبر الأدمن (للمشتركين VIP فقط).
 * أي محاولة للتطاول أو الإساءة لأحد العمال في الدفع الفني تؤدي للحظر الفوري من البوت ومسح جميع بياناتك.
5. المبيعات والاسترداد:
 * جميع عمليات شراء النقاط أو عضويات VIP تتم عبر التواصل المباشر مع الأدمن أو الوكلاء المعتمدين.
 * لا يوجد "استرداد للأموال" بعد شحن النقاط؛ النقاط تستخدم فقط داخل نظام التبادل.
"""

# --- إدارة قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON;') # تفعيل دعم المفاتيح الأجنبية
    cursor.execute('CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, username TEXT, role TEXT DEFAULT "user", 
                       points INTEGER DEFAULT 0, accepted_terms BOOLEAN DEFAULT 0, warnings INTEGER DEFAULT 0, 
                       is_vip BOOLEAN DEFAULT 0, vip_until TIMESTAMP, referred_by INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS tasks 
                      (task_id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, platform TEXT, 
                       url TEXT, reward INTEGER, required_count INTEGER, completed_count INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS disputes 
                      (dispute_id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER, accused_id INTEGER, 
                       task_id INTEGER, status TEXT DEFAULT "open", worker_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS free_channels 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, channel_link TEXT)')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    conn.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
    conn.commit()
    conn.close()

# --- الحماية والصلاحيات ---
def is_owner(user_id):
    return user_id == OWNER_ID

def is_worker(user_id):
    user = get_user(user_id)
    return user and user[2] in ['owner', 'worker']

# --- أوامر الأدمن (Owner) ---
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        update_user(target_id, role='worker')
        await update.message.reply_text(f"✅ تم ترقية المستخدم {target_id} إلى رتبة عامل.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /promote [user_id]")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        update_user(target_id, role='user')
        await update.message.reply_text(f"✅ تم سحب صلاحيات العامل من المستخدم {target_id}.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /demote [worker_id]")

async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        user = get_user(target_id)
        if user:
            new_points = user[3] + amount # user[3] هو حقل النقاط
            update_user(target_id, points=new_points)
            await update.message.reply_text(f"✅ تم إضافة {amount} نقطة للمستخدم {target_id}. الرصيد الجديد: {new_points}")
        else:
            await update.message.reply_text("❌ المستخدم غير موجود.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /add_points [user_id] [amount]")

async def set_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
        vip_until = datetime.now() + timedelta(days=days)
        update_user(target_id, is_vip=True, vip_until=vip_until.strftime("%Y-%m-%d %H:%M:%S"))
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {target_id} لمدة {days} يوم.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /set_vip [user_id] [days]")

async def free_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        channel_link = context.args[0]
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO free_channels (owner_id, channel_link) VALUES (?, ?)", (update.effective_user.id, channel_link))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ تم إضافة القناة {channel_link} لقنواتك المجانية.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /free_channel [channel_link]")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    message_text = " ".join(context.args)
    if not message_text: 
        await update.message.reply_text("❌ الاستخدام: /broadcast [message]")
        return
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users WHERE accepted_terms = 1").fetchall()
    conn.close()
    
    for user_id_tuple in users:
        try:
            await context.bot.send_message(chat_id=user_id_tuple[0], text=message_text)
        except Exception as e:
            logging.error(f"Failed to send broadcast to {user_id_tuple[0]}: {e}")
    await update.message.reply_text("✅ تم إرسال الرسالة لجميع المستخدمين.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    conn = sqlite3.connect(DB_PATH)
    users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    workers_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'worker'").fetchone()[0]
    total_points = conn.execute("SELECT SUM(points) FROM users").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 إحصائيات البوت:\n👥 المستخدمين: {users_count}\n🛠 العمال: {workers_count}\n💰 إجمالي النقاط: {total_points}")

# --- أوامر العامل (Worker) ---
async def disputes_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    conn = sqlite3.connect(DB_PATH)
    disputes = conn.execute("SELECT dispute_id, reporter_id, accused_id, status FROM disputes WHERE status = 'open'").fetchall()
    conn.close()

    if disputes:
        response = "📢 البلاغات المفتوحة:\n"
        for d_id, rep_id, acc_id, status in disputes:
            response += f"- ID: {d_id}, المبلغ: {rep_id}, المتهم: {acc_id}, الحالة: {status}\n"
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("✅ لا توجد بلاغات مفتوحة حالياً.")

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        user = get_user(target_id)
        if user:
            await update.message.reply_text(
                f"🔍 سجل المستخدم {target_id}:\n"
                f"الاسم: {user[1]}\n"
                f"الرتبة: {user[2]}\n"
                f"النقاط: {user[3]}\n"
                f"التحذيرات: {user[5]}\n"
                f"VIP: {'نعم' if user[6] else 'لا'} (حتى: {user[7] if user[7] else 'غير محدد'})"
            )
            # هنا يمكن إضافة سجل المتابعات الخاص بالمستخدم
        else:
            await update.message.reply_text("❌ المستخدم غير موجود.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /check [user_id]")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        user = get_user(target_id)
        if user:
            new_warnings = user[5] + 1
            update_user(target_id, warnings=new_warnings)
            await update.message.reply_text(f"✅ تم إرسال تحذير للمستخدم {target_id}. عدد التحذيرات: {new_warnings}")
            await context.bot.send_message(chat_id=target_id, text=f"⚠️ لقد تلقيت تحذيراً رسمياً من الإدارة. عدد تحذيراتك: {new_warnings}")
        else:
            await update.message.reply_text("❌ المستخدم غير موجود.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /warn [user_id]")

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    
    try:
        target_id = int(context.args[0])
        reason = " ".join(context.args[1:])
        
        # تنفيذ الحظر في القاعدة
        user_to_ban = get_user(target_id)
        if user_to_ban and user_to_ban[2] == 'owner': # لا يمكن للعامل حظر المالك
            await update.message.reply_text("❌ لا يمكنك حظر المالك.")
            return

        update_user(target_id, role='banned', points=0)
        
        # النشر في قناة السجل
        log_msg = (
            f"🚫 تم حظر المستخدم: {target_id}\n"
            f"👤 بواسطة العامل: {update.effective_user.username}\n"
            f"📝 السبب: {reason}\n"
            f"💰 العقوبة: مصادرة كافة النقاط."
        )
        await context.bot.send_message(chat_id=BAN_LOG_CHANNEL, text=log_msg)
        await update.message.reply_text(f"✅ تم الحظر والنشر في سجل المحظورين.")
        await context.bot.send_message(chat_id=target_id, text=f"⚠️ تم حظرك من البوت.\nالسبب: {reason}\nتم مصادرة جميع نقاطك.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /ban [user_id] [reason]")

async def settle_dispute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    try:
        dispute_id = int(context.args[0])
        winner_id = int(context.args[1])
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT reporter_id, accused_id, task_id FROM disputes WHERE dispute_id = ? AND status = 'open'", (dispute_id,))
        dispute = cursor.fetchone()
        
        if dispute:
            reporter_id, accused_id, task_id = dispute
            
            # تحديد الخاسر والفائز
            loser_id = accused_id if winner_id == reporter_id else reporter_id
            
            # افتراض أن هناك نقاط متنازع عليها (مثلاً، 3 أضعاف النقاط التي كسبها المتهم من المهمة)
            # هذا الجزء يحتاج لمنطق أكثر تعقيداً لتحديد النقاط المتنازع عليها بدقة
            # للتبسيط، سنفترض قيمة ثابتة أو نربطها بالمهمة
            disputed_points = 100 # مثال: قيمة النقاط المتنازع عليها
            commission = int(disputed_points * 0.05)
            
            # خصم من الخاسر وإضافة للفائز والعامل
            loser_points = get_user(loser_id)[3] - disputed_points
            winner_points = get_user(winner_id)[3] + disputed_points - commission # الفائز يحصل على النقاط بعد خصم عمولة العامل
            worker_points = get_user(update.effective_user.id)[3] + commission
            
            update_user(loser_id, points=loser_points)
            update_user(winner_id, points=winner_points)
            update_user(update.effective_user.id, points=worker_points)
            
            cursor.execute("UPDATE disputes SET status = 'resolved', worker_id = ? WHERE dispute_id = ?", (update.effective_user.id, dispute_id))
            conn.commit()
            await update.message.reply_text(f"✅ تم حل البلاغ {dispute_id}. تم خصم {disputed_points} من {loser_id} وإضافة {disputed_points - commission} لـ {winner_id} و {commission} لـ العامل.")
            await context.bot.send_message(chat_id=winner_id, text=f"✅ تم حل بلاغك رقم {dispute_id} لصالحك. تم تعويضك بـ {disputed_points - commission} نقطة.")
            await context.bot.send_message(chat_id=loser_id, text=f"⚠️ تم حل البلاغ رقم {dispute_id} ضدك. تم خصم {disputed_points} نقطة.")
        else:
            await update.message.reply_text("❌ البلاغ غير موجود أو تم حله مسبقاً.")
        conn.close()
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /settle [dispute_id] [winner_id]")

async def request_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_worker(update.effective_user.id): return
    try:
        dispute_id = int(context.args[0])
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT accused_id FROM disputes WHERE dispute_id = ? AND status = 'open'", (dispute_id,))
        accused_id = cursor.fetchone()
        conn.close()

        if accused_id:
            update_user(accused_id[0], status='waiting_proof') # تحديث حالة المتهم في النزاع
            await context.bot.send_message(chat_id=accused_id[0], text=f"⚠️ مطلوب منك إرسال صورة إثبات المتابعة للبلاغ رقم {dispute_id} خلال ساعة واحدة. عدم الإرسال يعني إقرارك بالغش.")
            await update.message.reply_text(f"✅ تم طلب صورة إثبات من المتهم في البلاغ {dispute_id}.")
        else:
            await update.message.reply_text("❌ البلاغ غير موجود أو تم حله.")
    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /screenshot [dispute_id]")

# --- أوامر المستخدمين ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    user = get_user(user_id)
    
    if not user:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
        user = get_user(user_id)

    if not user[4]:  # accepted_terms
        keyboard = [
            [InlineKeyboardButton("✅ أوافق وأتعهد بالالتزام", callback_data='accept_terms')],
            [InlineKeyboardButton("❌ لا أوافق", callback_data='reject_terms')]
        ]
        await update.message.reply_text(TERMS_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user or not user[4]: # لم يوافق على الشروط بعد
        return

    text = f"🏠 القائمة الرئيسية\nرصيدك الحالي: {user[3]} نقطة.\nاستخدم الأزرار أدناه للتنقل:"
    keyboard = [
        [InlineKeyboardButton("💰 كسب النقاط", callback_data='earn'), InlineKeyboardButton("📈 زيادة المتابعين", callback_data='promote')],
        [InlineKeyboardButton("👤 حسابي", callback_data='profile'), InlineKeyboardButton("📢 بلاغ عن نقص", callback_data='report_issue')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user and user[4]:
        await update.message.reply_text(f"💰 رصيدك الحالي هو: {user[3]} نقطة.")
    else:
        await update.message.reply_text("يرجى الموافقة على الشروط أولاً باستخدام أمر /start.")

async def report_issue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user(user_id) or not get_user(user_id)[4]: return
    
    # هذا الجزء يحتاج لمنطق لاختيار المتهم من قائمة آخر المتابعين
    # للتبسيط، سنطلب من المستخدم إدخال ID المتهم يدوياً
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: /report [accused_user_id] [task_id] (مثال: /report 12345 5)")
        return
    
    try:
        accused_id = int(context.args[0])
        task_id = int(context.args[1]) # افتراض أن المستخدم يعرف رقم المهمة
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO disputes (reporter_id, accused_id, task_id) VALUES (?, ?, ?)", (user_id, accused_id, task_id))
        dispute_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ تم فتح بلاغك رقم {dispute_id}. سيقوم أحد العمال بمراجعته قريباً.")
        
        # إرسال تنبيه للعمال
        conn = sqlite3.connect(DB_PATH)
        workers = conn.execute("SELECT user_id FROM users WHERE role IN ('owner', 'worker')").fetchall()
        conn.close()
        for worker_id_tuple in workers:
            try:
                await context.bot.send_message(chat_id=worker_id_tuple[0], text=f"📢 بلاغ جديد (ID: {dispute_id}) من {user_id} ضد {accused_id} في المهمة {task_id}. استخدم /disputes للمراجعة.")
            except Exception as e:
                logging.error(f"Failed to notify worker {worker_id_tuple[0]}: {e}")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ الاستخدام: /report [accused_user_id] [task_id]")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user(user_id) or not get_user(user_id)[4]: return
    await update.message.reply_text("💰 لشراء النقاط أو عضوية VIP، يرجى التواصل مباشرة مع الأدمن: @AdminUsername (مثال).\nلا يوجد استرداد للأموال بعد الشحن.")

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user(user_id) or not get_user(user_id)[4]: return
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    await update.message.reply_text(f"👥 رابط الإحالة الخاص بك:\n{ref_link}\nشارك الرابط واكسب نقاطاً عند تسجيل أصدقائك!")

# --- معالجة الأزرار (CallbackQueryHandler) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)

    if query.data == 'accept_terms':
        if user and not user[4]: # إذا لم يوافق بعد
            update_user(user_id, accepted_terms=True)
            await show_main_menu(update, context)
        else:
            await query.edit_message_text("لقد وافقت على الشروط مسبقاً.")
    elif query.data == 'reject_terms':
        await query.edit_message_text("❌ للأسف لا يمكنك استخدام البوت دون الموافقة على الشروط. وداعاً!")
    elif query.data == 'profile':
        if user and user[4]:
            await query.edit_message_text(
                f"👤 معلومات الحساب:\n"
                f"الاسم: {user[1]}\n"
                f"الرصيد: {user[3]} نقطة\n"
                f"المعرف: {user[0]}\n"
                f"الرتبة: {user[2]}\n"
                f"VIP: {'نعم' if user[6] else 'لا'} (حتى: {user[7] if user[7] else 'غير محدد'})"
            )
        else:
            await query.edit_message_text("يرجى الموافقة على الشروط أولاً باستخدام أمر /start.")
    elif query.data == 'earn':
        if user and user[4]:
            await query.edit_message_text("اختر المنصة لكسب النقاط:\n(قيد التطوير...)")
        else:
            await query.edit_message_text("يرجى الموافقة على الشروط أولاً باستخدام أمر /start.")
    elif query.data == 'promote':
        if user and user[4]:
            await query.edit_message_text("اختر المنصة التي تريد دعمها:\n(قيد التطوير...)")
        else:
            await query.edit_message_text("يرجى الموافقة على الشروط أولاً باستخدام أمر /start.")
    elif query.data == 'report_issue':
        if user and user[4]:
            await query.edit_message_text("لفتح بلاغ، استخدم الأمر /report [accused_user_id] [task_id].")
        else:
            await query.edit_message_text("يرجى الموافقة على الشروط أولاً باستخدام أمر /start.")

# --- تشغيل البوت ---
if __name__ == '__main__':
    init_db()
    print("Database initialized with roles, disputes, and terms support.")
    
    # لكي يعمل البوت، يجب استبدال "TOKEN" بالتوكن الخاص بك من BotFather
    # وتعيين OWNER_ID و BAN_LOG_CHANNEL بشكل صحيح.
    # app = ApplicationBuilder().token("YOUR_TELEGRAM_BOT_TOKEN").build()

    # # أوامر الأدمن
    # app.add_handler(CommandHandler("promote", promote))
    # app.add_handler(CommandHandler("demote", demote))
    # app.add_handler(CommandHandler("add_points", add_points))
    # app.add_handler(CommandHandler("set_vip", set_vip))
    # app.add_handler(CommandHandler("free_channel", free_channel))
    # app.add_handler(CommandHandler("broadcast", broadcast))
    # app.add_handler(CommandHandler("stats", stats))

    # # أوامر العامل
    # app.add_handler(CommandHandler("disputes", disputes_list))
    # app.add_handler(CommandHandler("check", check_user))
    # app.add_handler(CommandHandler("warn", warn_user))
    # app.add_handler(CommandHandler("ban", ban_user_command))
    # app.add_handler(CommandHandler("settle", settle_dispute))
    # app.add_handler(CommandHandler("screenshot", request_screenshot))

    # # أوامر المستخدمين
    # app.add_handler(CommandHandler("start", start_command))
    # app.add_handler(CommandHandler("my_points", my_points))
    # app.add_handler(CommandHandler("report", report_issue))
    # app.add_handler(CommandHandler("buy", buy_command))
    # app.add_handler(CommandHandler("link", link_command))

    # # معالجة الأزرار
    # app.add_handler(CallbackQueryHandler(button_handler))

    # # تشغيل البوت
    # app.run_polling()
