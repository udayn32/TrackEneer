from db import get_driver

email = 'udaynaik057@gmail.com'
mid = '30d2fea5-1127-4d20-9b0f-f18bfee4b45a'

if __name__ == '__main__':
    driver = get_driver()
    with driver.session() as session:
        print('Searching for users by email:')
        res = session.run("MATCH (u:User {email:$email}) RETURN u, id(u) as internalId", email=email)
        for r in res:
            try:
                props = dict(r['u'].items())
            except Exception:
                props = {k: r['u'].get(k) for k in r['u'].keys()}
            print('nodeProps=', props, 'internalId=', r['internalId'])

        print('\nSearching for users by id field value:')
        res = session.run("MATCH (u:User {id:$id}) RETURN u, id(u) as internalId", id=mid)
        for r in res:
            try:
                props = dict(r['u'].items())
            except Exception:
                props = {k: r['u'].get(k) for k in r['u'].keys()}
            print('nodeProps=', props, 'internalId=', r['internalId'])

        print('\nProfiles linked to any User with this email:')
        res = session.run("MATCH (u:User)-[r:HAS_PROFILE]->(p:Profile) WHERE u.email=$email RETURN u,p", email=email)
        for r in res:
            try:
                pu = dict(r['u'].items())
                pp = dict(r['p'].items())
            except Exception:
                pu = {}
                pp = {}
            print('User:', pu)
            print('Profile:', pp)
