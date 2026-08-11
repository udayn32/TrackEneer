import os
from pymongo import MongoClient

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017')
MONGO_DB = os.getenv('MONGO_DB', 'trackeneer')

_client = None


def get_mongo_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[MONGO_DB]
