from pathlib import Path
import duckdb
from flask import Flask, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["http://127.0.0.1:5000", "http://localhost:5000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

class AnalyticsDB:
    def __init__(self, data_dir="data"):
        # Set up directory structure
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.db_dir = self.data_dir / "user_dbs"
        self.db_dir.mkdir(exist_ok=True)
        
        # Create registry db to track user databases
        self.registry_db = self.data_dir / "registry.db"
        with duckdb.connect(str(self.registry_db)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_registry (
                    user_id INTEGER PRIMARY KEY,
                    db_path VARCHAR
                )
            """)
    
    def get_user_db_path(self, user_id):
        return str(self.db_dir / f"user_{user_id}.db")
    
    def register_user(self, user_id, db_path):
        with duckdb.connect(str(self.registry_db)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_registry (user_id, db_path)
                VALUES (?, ?)
            """, [user_id, db_path])
    
    def init_user_db(self, user_id):
        db_path = self.get_user_db_path(user_id)
        with duckdb.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_counts (
                    date DATE PRIMARY KEY,
                    count INTEGER
                )
            """)
        return db_path
    
    def generate_sample_data(self):
        # First create user DBs and register them
        for user_id in range(1, 6):  # Create 5 users
            db_path = self.init_user_db(user_id)
            self.register_user(user_id, db_path)
            
            # Generate data for this user
            with duckdb.connect(db_path) as conn:
                # First create a sequence of dates
                conn.execute("""
                    CREATE TEMPORARY TABLE date_sequence AS
                    WITH RECURSIVE dates(date) AS (
                        SELECT DATE '2024-01-01'
                        UNION ALL
                        SELECT date + INTERVAL '1' day
                        FROM dates
                        WHERE date < DATE '2024-02-01'
                    )
                    SELECT * FROM dates
                """)
                
                # Then insert data using these dates
                conn.execute("""
                    INSERT OR REPLACE INTO daily_counts
                    SELECT 
                        date,
                        (abs(random()) * 100)::INTEGER as count
                    FROM date_sequence
                """)
    
    def get_users(self):
        with duckdb.connect(str(self.registry_db)) as conn:
            return conn.execute("""
                SELECT user_id 
                FROM user_registry 
                ORDER BY user_id
            """).fetchall()
    
    def get_user_metrics(self, user_id):
        with duckdb.connect(str(self.registry_db)) as conn:
            result = conn.execute("""
                SELECT db_path 
                FROM user_registry 
                WHERE user_id = ?
            """, [user_id]).fetchone()
            
            if not result:
                return []
            
            db_path = result[0]
            with duckdb.connect(db_path) as user_conn:
                result = user_conn.execute("""
                    SELECT 
                        date,
                        count as value
                    FROM daily_counts
                    ORDER BY date
                """).fetchall()
                
                return [{"date": str(r[0]), "value": r[1]} for r in result]

# Initialize DB and sample data
db = AnalyticsDB()
db.generate_sample_data()

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/users')
def get_users():
    users = db.get_users()
    return jsonify([u[0] for u in users])

@app.route('/metrics/<int:user_id>')
def get_metrics(user_id):
    metrics = db.get_user_metrics(user_id)
    return jsonify(metrics)

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='127.0.0.1')