from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path
from datetime import datetime
import uuid
import os

from sqlalchemy import create_engine, Column, Integer, String, Text, or_
from sqlalchemy.orm import sessionmaker, Session, declarative_base

app = FastAPI(title="Social Network Pro")

templates = Jinja2Templates(directory=str(Path("templates")))
app.mount("/static", StaticFiles(directory=str(Path("static"))), name="static")
app.mount("/uploads", StaticFiles(directory=str(Path("uploads"))), name="uploads")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "photos").mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./social.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    avatar = Column(String(100), default="👤")


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    photo = Column(String(100), nullable=True)
    time = Column(String(10), nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    subscribed_to = Column(String(50), nullable=False)


class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user1 = Column(String(50), nullable=False)
    user2 = Column(String(50), nullable=False)
    sender = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    time = Column(String(10), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)
    from_user = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    time = Column(String(10), nullable=False)
    read = Column(Integer, default=0)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        return templates.TemplateResponse("login.html", {"request": request})

    subs = db.query(Subscription).filter(Subscription.user_id == current_user).all()
    followed_users = [s.subscribed_to for s in subs]

    users = db.query(User).filter(User.username != current_user).all()
    users_list = [{"username": u.username, "avatar": u.avatar} for u in users]

    all_posts = db.query(Post).order_by(Post.id.desc()).all()

    posts_list = []
    for p in all_posts:
        if p.username in followed_users:
            priority = 0
            label = "Suivi"
        elif p.username == current_user:
            priority = 1
            label = "Moi"
        else:
            priority = 2
            label = "Autre"

        posts_list.append({
            "id": p.id,
            "username": p.username,
            "content": p.content,
            "photo": p.photo,
            "time": p.time,
            "priority": priority,
            "label": label
        })

    posts_list.sort(key=lambda x: (x["priority"], -x["id"]))

    notifs = db.query(Notification).filter(
        Notification.username == current_user,
        Notification.read == 0
    ).order_by(Notification.id.desc()).all()

    notifications_list = [
        {
            "type": n.type,
            "from": n.from_user,
            "message": n.message,
            "time": n.time,
            "read": False
        }
        for n in notifs
    ]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "posts": posts_list,
        "users": users_list,
        "current_user": current_user,
        "current_user_avatar": current_user_obj.avatar,
        "notifications": notifications_list,
        "unread_count": len(notifications_list)
    })


@app.get("/profile/{username}")
async def profile(request: Request, username: str, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        return templates.TemplateResponse("login.html", {"request": request})

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user_posts = db.query(Post).filter(Post.username == username).order_by(Post.id.desc()).all()
    posts_list = [
        {
            "id": p.id,
            "username": p.username,
            "content": p.content,
            "photo": p.photo,
            "time": p.time
        }
        for p in user_posts
    ]

    is_subscribed = db.query(Subscription).filter(
        Subscription.user_id == current_user,
        Subscription.subscribed_to == username
    ).first()

    followers_count = db.query(Subscription).filter(
        Subscription.subscribed_to == username
    ).count()

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": {"username": user.username, "avatar": user.avatar},
        "posts": posts_list,
        "current_user": current_user,
        "is_subscribed": is_subscribed is not None,
        "followers_count": followers_count
    })


@app.get("/conversations")
async def conversations_page(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        return templates.TemplateResponse("login.html", {"request": request})

    conversations = db.query(Chat).filter(
        or_(Chat.user1 == current_user, Chat.user2 == current_user)
    ).order_by(Chat.id.desc()).all()

    conv_dict = {}
    for c in conversations:
        other_user = c.user2 if c.user1 == current_user else c.user1
        if other_user not in conv_dict:
            other_user_obj = db.query(User).filter(User.username == other_user).first()
            conv_dict[other_user] = {
                "username": other_user,
                "avatar": other_user_obj.avatar if other_user_obj else "👤",
                "last_message": c.message,
                "last_time": c.time
            }

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "current_user": current_user,
        "conversations": list(conv_dict.values())
    })


@app.get("/chat/{username}")
async def chat_page(request: Request, username: str, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        return templates.TemplateResponse("login.html", {"request": request})

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    chat_key = (min(current_user, username), max(current_user, username))
    messages = db.query(Chat).filter(
        Chat.user1 == chat_key[0],
        Chat.user2 == chat_key[1]
    ).order_by(Chat.id.asc()).all()

    messages_list = [
        {"from": m.sender, "message": m.message, "time": m.time}
        for m in messages
    ]

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "chat_user": {"username": user.username, "avatar": user.avatar},
        "current_user": current_user,
        "messages": messages_list
    })


@app.post("/upload-post")
async def upload_post(
    request: Request,
    content: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    photo_filename = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix or ".jpg"
        photo_filename = f"{uuid.uuid4()}{ext}"
        photo_path = UPLOAD_DIR / "photos" / photo_filename
        contents = await photo.read()
        with open(photo_path, "wb") as f:
            f.write(contents)

    post = Post(
        username=current_user,
        content=content,
        photo=photo_filename,
        time=datetime.now().strftime("%H:%M")
    )
    db.add(post)
    db.commit()

    subs = db.query(Subscription).filter(
        Subscription.subscribed_to == current_user
    ).all()

    for sub in subs:
        notif = Notification(
            username=sub.user_id,
            type="post",
            from_user=current_user,
            message="a publié un nouveau post",
            time=datetime.now().strftime("%H:%M")
        )
        db.add(notif)

    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/edit-post/{post_id}")
async def edit_post(
    request: Request,
    post_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    post = db.query(Post).filter(
        Post.id == post_id,
        Post.username == current_user
    ).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post non trouvé")

    post.content = content
    post.time = datetime.now().strftime("%H:%M")
    db.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/delete-post/{post_id}")
async def delete_post(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    post = db.query(Post).filter(
        Post.id == post_id,
        Post.username == current_user
    ).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post non trouvé")

    db.delete(post)
    db.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/subscribe/{username}")
async def subscribe(request: Request, username: str, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user,
        Subscription.subscribed_to == username
    ).first()

    if not sub:
        sub = Subscription(user_id=current_user, subscribed_to=username)
        db.add(sub)
        db.commit()

        notif = Notification(
            username=username,
            type="subscribe",
            from_user=current_user,
            message="a commencé à te suivre",
            time=datetime.now().strftime("%H:%M")
        )
        db.add(notif)
        db.commit()

    return RedirectResponse(url=f"/profile/{username}", status_code=303)


@app.post("/unsubscribe/{username}")
async def unsubscribe(request: Request, username: str, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user,
        Subscription.subscribed_to == username
    ).first()

    if sub:
        db.delete(sub)
        db.commit()

    return RedirectResponse(url=f"/profile/{username}", status_code=303)


@app.post("/send-message/{username}")
async def send_message(
    request: Request,
    username: str,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    if message.strip():
        chat_key = (min(current_user, username), max(current_user, username))
        chat = Chat(
            user1=chat_key[0],
            user2=chat_key[1],
            sender=current_user,
            message=message,
            time=datetime.now().strftime("%H:%M")
        )
        db.add(chat)
        db.commit()

        notif = Notification(
            username=username,
            type="message",
            from_user=current_user,
            message="a envoyé un message",
            time=datetime.now().strftime("%H:%M")
        )
        db.add(notif)
        db.commit()

    return RedirectResponse(url=f"/chat/{username}", status_code=303)


@app.post("/upload-avatar")
async def upload_avatar(
    request: Request,
    avatar: str = Form(...),
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    current_user_obj.avatar = avatar or "👤"
    db.commit()

    return RedirectResponse(url=f"/profile/{current_user}", status_code=303)


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.password == password).first()

    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Nom d'utilisateur ou mot de passe incorrect"
        })

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_id", value=username)
    return response


@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not username or not password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Nom d'utilisateur et mot de passe requis"
        })

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Ce nom d'utilisateur existe déjà"
        })

    user = User(username=username, password=password, avatar="👤")
    db.add(user)
    db.commit()

    return templates.TemplateResponse("login.html", {
        "request": request,
        "message": "✓ Compte créé! Connectez-vous maintenant."
    })


@app.post("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_id")
    return response


@app.post("/mark-notification-read")
async def mark_notification_read(
    request: Request,
    from_user: str = Form(...),
    notif_type: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    current_user = session_id

    current_user_obj = db.query(User).filter(User.username == current_user).first()
    if not current_user_obj:
        raise HTTPException(status_code=401, detail="Authentification requise")

    notifs = db.query(Notification).filter(
        Notification.username == current_user,
        Notification.from_user == from_user,
        Notification.type == notif_type,
        Notification.message == message
    ).all()

    for notif in notifs:
        notif.read = 1

    db.commit()
    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)