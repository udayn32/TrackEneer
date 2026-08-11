from mongo import get_mongo_db

if __name__ == '__main__':
    db = get_mongo_db()
    users = db.users
    try:
        docs = list(users.find({}, {'_id':0}).limit(50))
        print(f"Found {len(docs)} user documents in MongoDB (db='{db.name}')")
        for d in docs:
            print(d)
    except Exception as e:
        print('Error querying MongoDB:', e)
