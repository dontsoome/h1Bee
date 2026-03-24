from dotenv import load_dotenv; load_dotenv('.env')
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT ats_platform, COUNT(*) FROM company_ats GROUP BY ats_platform ORDER BY COUNT(*) DESC')
for r in cur.fetchall(): print(r)
