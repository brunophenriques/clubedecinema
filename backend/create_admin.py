from app.db import SessionLocal
from app.models import User
from app.main import hash_password  # <-- IMPORTANTE: usa o mesmo hashing do backend

USERNAME = "brunomaquina"
PASSWORD = "lolz"

db = SessionLocal()

u = db.query(User).filter(User.username == USERNAME).first()

if not u:
    u = User(username=USERNAME, password_hash=hash_password(PASSWORD), is_admin=True)
    db.add(u)
    db.commit()
    print("Admin criado (PBKDF2).")
else:
    u.password_hash = hash_password(PASSWORD)
    u.is_admin = True
    db.commit()
    print("Admin atualizado (password reset + is_admin=True).")

db.close()