# init_db.py
from db import engine, Base
from models import User, Invoice, Export

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("DB tables created")
