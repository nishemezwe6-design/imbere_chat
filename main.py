from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime
import uuid

app = FastAPI(title="Social Network Pro")

templates = Jinja2Templates(directory=Path("templates"))
app.mount("/static", StaticFiles(directory=Path("static")), name="static")
app.mount("/uploads", StaticFiles(directory=Path("uploads")), name="uploads")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
Path(UPLOAD_DIR / "photos").mkdir(exist_ok=True)

users = []
posts = []
sessions = {}
subscriptions = {}
chats = {}
notifications = {}

@app.get("/")
async def home(request: Request):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        return templates.TemplateResponse("login.html", {"request": request})
    user_subs = subscriptions.get(current_user, [])
    display_posts = [p for p in posts if p["username"] == current_user or p["username"] in user_subs]
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    return templates.TemplateResponse("index.html", {
        "request": request, "posts": display_posts, "current_user": current_user, "users": users,
        "notifications": user_notifs, "unread_count": unread_count
    })

@app.get("/profile/{username}")
async def profile(request: Request, username: str):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        return templates.TemplateResponse("login.html", {"request": request})
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    user_posts = [p for p in posts if p["username"] == username]
    is_subscribed = username in subscriptions.get(current_user, [])
    followers = [sub for sub, subs in subscriptions.items() if username in subs]
    followers_count = len(followers)
    return templates.TemplateResponse("profile.html", {
        "request": request, "user": user, "posts": user_posts, "current_user": current_user,
        "is_subscribed": is_subscribed, "followers_count": followers_count
    })

@app.get("/conversations")
async def conversations_page(request: Request):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        return templates.TemplateResponse("login.html", {"request": request})
    user_conversations = []
    for chat_key, messages in chats.items():
        user1, user2 = chat_key
        if user1 == current_user or user2 == current_user:
            other_user = user2 if user1 == current_user else user1
            other_user_obj = next((u for u in users if u["username"] == other_user), None)
            last_message = messages[-1] if messages else None
            user_conversations.append({
                "username": other_user,
                "avatar": other_user_obj["avatar"] if other_user_obj else "👤",
                "last_message": last_message["message"] if last_message else None,
                "last_time": last_message["time"] if last_message else None
            })
    return templates.TemplateResponse("conversations.html", {
        "request": request, "current_user": current_user, "conversations": user_conversations
    })

@app.get("/chat/{username}")
async def chat_page(request: Request, username: str):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        return templates.TemplateResponse("login.html", {"request": request})
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    chat_key = (min(current_user, username), max(current_user, username))
    messages = chats.get(chat_key, [])
    return templates.TemplateResponse("chat.html", {
        "request": request, "chat_user": user, "current_user": current_user, "messages": messages
    })

@app.post("/upload-post")
async def upload_post(request: Request, content: str = Form(...), photo: UploadFile = File(None)):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    photo_filename = None
    if photo and photo.filename:
        photo_filename = f"{uuid.uuid4()}.jpg"
        photo_path = UPLOAD_DIR / "photos" / photo_filename
        contents = await photo.read()
        with open(photo_path, "wb") as f:
            f.write(contents)
    posts.append({
        "id": len(posts) + 1, "username": current_user, "content": content, "photo": photo_filename,
        "time": datetime.now().strftime("%H:%M")
    })
    user_subs = subscriptions.get(current_user, [])
    display_posts = [p for p in posts if p["username"] == current_user or p["username"] in user_subs]
    for sub in subscriptions.get(current_user, []):
        if current_user not in notifications:
            notifications[current_user] = []
        notifications[sub].append({
            "type": "post", "from": current_user, "message": "a publié un nouveau post",
            "time": datetime.now().strftime("%H:%M"), "read": False
        })
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": display_posts, "current_user": current_user, "users": users, "message": "✓ Post publié!", "notifications": user_notifs, "unread_count": unread_count
    })
    return response

@app.post("/edit-post/{post_id}")
async def edit_post(request: Request, post_id: int, content: str = Form(...)):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    post = next((p for p in posts if p["id"] == post_id and p["username"] == current_user), None)
    if not post:
        raise HTTPException(status_code=404, detail="Post non trouvé")
    post["content"] = content
    post["time"] = datetime.now().strftime("%H:%M")
    user_subs = subscriptions.get(current_user, [])
    display_posts = [p for p in posts if p["username"] == current_user or p["username"] in user_subs]
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": display_posts, "current_user": current_user, "users": users, "message": "✓ Post modifié!", "notifications": user_notifs, "unread_count": unread_count
    })
    return response

@app.post("/delete-post/{post_id}")
async def delete_post(request: Request, post_id: int):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    post = next((p for p in posts if p["id"] == post_id and p["username"] == current_user), None)
    if not post:
        raise HTTPException(status_code=404, detail="Post non trouvé")
    posts.remove(post)
    user_subs = subscriptions.get(current_user, [])
    display_posts = [p for p in posts if p["username"] == current_user or p["username"] in user_subs]
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": display_posts, "current_user": current_user, "users": users, "message": "✓ Post supprimé!", "notifications": user_notifs, "unread_count": unread_count
    })
    return response

@app.post("/subscribe/{username}")
async def subscribe(request: Request, username: str):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    if username not in subscriptions.get(current_user, []):
        if current_user not in subscriptions:
            subscriptions[current_user] = []
        subscriptions[current_user].append(username)
    user = next((u for u in users if u["username"] == username), None)
    user_posts = [p for p in posts if p["username"] == username]
    is_subscribed = username in subscriptions.get(current_user, [])
    followers = [sub for sub, subs in subscriptions.items() if username in subs]
    followers_count = len(followers)
    if username not in notifications:
        notifications[username] = []
    notifications[username].append({
        "type": "subscribe", "from": current_user, "message": "a commencé à te suivre",
        "time": datetime.now().strftime("%H:%M"), "read": False
    })
    response = templates.TemplateResponse("profile.html", {
        "request": request, "user": user, "posts": user_posts, "current_user": current_user,
        "is_subscribed": is_subscribed, "followers_count": followers_count, "message": f"✓ Abonné à {username}!"
    })
    return response

@app.post("/unsubscribe/{username}")
async def unsubscribe(request: Request, username: str):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    if username in subscriptions.get(current_user, []):
        subscriptions[current_user].remove(username)
    user = next((u for u in users if u["username"] == username), None)
    user_posts = [p for p in posts if p["username"] == username]
    is_subscribed = username in subscriptions.get(current_user, [])
    followers = [sub for sub, subs in subscriptions.items() if username in subs]
    followers_count = len(followers)
    response = templates.TemplateResponse("profile.html", {
        "request": request, "user": user, "posts": user_posts, "current_user": current_user,
        "is_subscribed": is_subscribed, "followers_count": followers_count, "message": f"✓ Désabonné de {username}!"
    })
    return response

@app.post("/send-message/{username}")
async def send_message(request: Request, username: str, message: str = Form(...)):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    if message.strip():
        chat_key = (min(current_user, username), max(current_user, username))
        if chat_key not in chats:
            chats[chat_key] = []
        chats[chat_key].append({"from": current_user, "message": message, "time": datetime.now().strftime("%H:%M")})
    user = next((u for u in users if u["username"] == username), None)
    chat_key = (min(current_user, username), max(current_user, username))
    messages = chats.get(chat_key, [])
    if username not in notifications:
        notifications[username] = []
    notifications[username].append({
        "type": "message", "from": current_user, "message": "a envoyé un message",
        "time": datetime.now().strftime("%H:%M"), "read": False
    })
    response = templates.TemplateResponse("chat.html", {
        "request": request, "chat_user": user, "current_user": current_user, "messages": messages, "message_sent": "✓ Message envoyé!"
    })
    return response

@app.post("/upload-avatar")
async def upload_avatar(request: Request, avatar: str = Form(...)):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    user = next((u for u in users if u["username"] == current_user), None)
    if user:
        user["avatar"] = avatar or "👤"
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": posts, "current_user": current_user, "users": users, "message": "✓ Avatar changé!", "notifications": user_notifs, "unread_count": unread_count
    })
    return response

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = next((u for u in users if u["username"] == username and u["password"] == password), None)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Nom d'utilisateur ou mot de passe incorrect"})
    session_id = str(uuid.uuid4())
    sessions[session_id] = username
    user_notifs = notifications.get(username, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": posts, "current_user": username, "users": users, "message": f"✓ Bienvenue {username}!", "notifications": user_notifs, "unread_count": unread_count
    })
    response.set_cookie(key="session_id", value=session_id)
    return response

@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Nom d'utilisateur et mot de passe requis"})
    if any(u["username"] == username for u in users):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ce nom d'utilisateur existe déjà"})
    users.append({"username": username, "password": password, "avatar": "👤"})
    return templates.TemplateResponse("login.html", {"request": request, "message": "✓ Compte créé! Connectez-vous maintenant."})

@app.post("/logout")
async def logout(request: Request):
    response = templates.TemplateResponse("login.html", {"request": request})
    response.delete_cookie("session_id")
    return response
@app.post("/mark-notification-read")
async def mark_notification_read(request: Request, from_user: str = Form(...), notif_type: str = Form(...), message: str = Form(...)):
    session_id = request.cookies.get("session_id")
    current_user = sessions.get(session_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    
    user_notifs = notifications.get(current_user, [])
    for notif in user_notifs:
        if notif["from"] == from_user and notif["type"] == notif_type and notif["message"] == message:
            notif["read"] = True
    
    user_subs = subscriptions.get(current_user, [])
    display_posts = [p for p in posts if p["username"] == current_user or p["username"] in user_subs]
    user_notifs = notifications.get(current_user, [])
    unread_count = len([n for n in user_notifs if not n["read"]])
    
    response = templates.TemplateResponse("index.html", {
        "request": request, "posts": display_posts, "current_user": current_user, "users": users,
        "notifications": user_notifs, "unread_count": unread_count
    })
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)