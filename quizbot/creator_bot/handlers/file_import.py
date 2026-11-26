import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# अपने प्रोजेक्ट के हिसाब से इसे इम्पोर्ट करें (अगर रास्ता अलग है तो बदल लें)
from ..file_import import process_uploaded_file

# डेटा सेव करने के लिए डिक्शनरी (यूजर आईडी के हिसाब से)
user_queues = {}      # फाइलों को कतार में लगाने के लिए
user_tasks = {}       # 5 सेकंड का टाइमर सेट करने के लिए
user_states = {}      # चेक करने के लिए कि यूजर ने कमांड चलाया है या नहीं

# ==========================================
# 1. /txt2set कमांड हैंडलर
# ==========================================
@Client.on_message(filters.command("txt2set") & filters.private)
async def txt2set_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # स्टेट को इनिशियलाइज करें
    user_states[user_id] = "waiting_for_files"
    user_queues[user_id] = []
    
    await message.reply_text(
        "📁 **कृपया .txt फाइलें भेजें।**\n\n"
        "आप एक साथ 10, 20 या जितनी चाहें फाइलें भेज सकते हैं।\n"
        "फाइलें भेजने के **5 सेकंड** बाद बॉट अपने आप सभी फाइलों को एक-एक करके PDF और HTML में बदल देगा।"
    )

# ==========================================
# 2. फाइल रिसीव करने वाला हैंडलर
# ==========================================
@Client.on_message(filters.document & filters.private)
async def receive_txt_files(client: Client, message: Message):
    user_id = message.from_user.id
    
    # चेक करें कि यूजर ने /txt2set कमांड चलाया है या नहीं
    if user_states.get(user_id) != "waiting_for_files":
        return
        
    file_name = message.document.file_name or ""
    if not file_name.endswith(".txt"):
        return
        
    # फाइल को क्यू (Queue) में जोड़ें
    user_queues[user_id].append(message)
    total_files = len(user_queues[user_id])
    
    # अगर पहले से कोई टाइमर चल रहा है, तो उसे रीसेट करें
    if user_id in user_tasks and not user_tasks[user_id].done():
        user_tasks[user_id].cancel()
        
    # 5 सेकंड का नया टाइमर सेट करें (ताकि यूजर को और फाइलें भेजने का टाइम मिले)
    user_tasks[user_id] = asyncio.create_task(start_processing_after_delay(client, user_id, total_files))

# ==========================================
# 3. ऑटोमैटिक प्रोसेसिंग शुरू करने वाला फंक्शन
# ==========================================
async def start_processing_after_delay(client: Client, user_id: int, total_files: int):
    try:
        await asyncio.sleep(5) # 5 सेकंड रुकें ताकि सारी फाइलें आ जाएं
    except asyncio.CancelledError:
        return # अगर इस बीच नई फाइल आई, तो वापस जाएं
        
    files_to_process = user_queues.get(user_id, [])
    if not files_to_process:
        return
        
    # स्टेट बदल दें ताकि नई फाइलें गलती से क्यू में न जुड़ें
    user_states[user_id] = "processing"
    
    status_msg = await client.send_message(
        user_id, 
        f"⏳ कुल **{len(files_to_process)}** फाइलें मिली हैं। प्रोसेसिंग शुरू हो रही है...\n"
        f"*(इसमें थोड़ा समय लग सकता है, कृपया इंतज़ार करें)*"
    )
    
    # एक-एक करके सारी फाइलें प्रोसेस करें
    for index, msg in enumerate(files_to_process, start=1):
        file_name = msg.document.file_name
        
        try:
            await status_msg.edit_text(
                f"⏳ **प्रोसेसिंग ({index}/{len(files_to_process)}):**\n"
                f"📄 `{file_name}`\n\n"
                f"कृपया प्रतीक्षा करें..."
            )
            
            # फाइल डाउनलोड करें
            file_path = await msg.download()
            
            with open(file_path, "rb") as f:
                content = f.read()
                
            out_questions = []
            # आपका file_import.py का फंक्शन
            count, error = process_uploaded_file(content, file_name, out_questions, [])
            
            if error or count == 0:
                await client.send_message(user_id, f"❌ `{file_name}` में कोई सवाल नहीं मिले या एरर आया:\n{error}")
                os.remove(file_path) # डाउनलोड की गई फाइल डिलीट करें
                continue
                
            # -------------------------------------------------------------
            # ⚠️ यहाँ आप अपना PDF और HTML जेनरेट करने वाला कोड लगाएं
            # -------------------------------------------------------------
            # नीचे दिए गए हिस्से को अपने बॉट के हिसाब से बदलें:
            
            # pdf_file = generate_pdf(out_questions) 
            # html_file = generate_html(out_questions)
            
            # await message.reply_document(pdf_file, caption=f"PDF Generated!\nQuestions: {count}")
            # await message.reply_document(html_file, caption=f"HTML Generated!\nQuestions: {count}")
            
            # -------------------------------------------------------------
            # फिलहाल के लिए यह मैसेज भेजेगा (जब तक आप ऊपर वाला कोड नहीं लगाते)
            await client.send_message(
                user_id,
                f"✅ **PDF और HTML तैयार!**\n"
                f"📄 फाइल: `{file_name}`\n"
                f"❓ कुल सवाल: {count}\n\n"
                f"*(नोट: यहाँ आपकी बनी हुई असली PDF और HTML फाइलें भेजी जानी चाहिए)*"
            )
            
            # डाउनलोड की गई अस्थायी फाइल डिलीट करें
            if os.path.exists(file_path):
                os.remove(file_path)
            
        except FloodWait as e:
            # अगर टेलीग्राम लिमिट आ जाए तो रुकें
            await asyncio.sleep(e.value)
            await client.send_message(user_id, f"⚠️ टेलीग्राम लिमिट के कारण {e.value} सेकंड रुकना पड़ा।")
        except Exception as e:
            await client.send_message(user_id, f"⚠️ `{file_name}` प्रोसेस करने में एरर: {str(e)}")
            
        # हर फाइल के बाद 2 सेकंड का गैप दें ताकि अकाउंट स्पैम में न जाए
        await asyncio.sleep(2) 
        
    # काम खत्म होने के बाद सफाई करें
    await status_msg.edit_text("🎉 **सभी फाइलों का प्रोसेसिंग पूरा हो गया!**")
    
    # डिक्शनरी से डेटा हटा दें ताकि मेमोरी खाली हो जाए
    if user_id in user_queues: del user_queues[user_id]
    if user_id in user_states: del user_states[user_id]
    if user_id in user_tasks: del user_tasks[user_id]
