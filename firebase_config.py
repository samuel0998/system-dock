import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("firebase_key.json")

# 🔥 Inicializa apenas se ainda não existir app
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
