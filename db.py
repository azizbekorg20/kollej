import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Database:
    def __init__(self, path: str):
        self.path = path
        self.init()

    @contextmanager
    def conn(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys = ON')
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def init(self):
        with self.conn() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS groups_ (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK(capacity > 0),
                created_at TEXT NOT NULL,
                UNIQUE(section_id, name),
                FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                section_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE CASCADE,
                FOREIGN KEY(group_id) REFERENCES groups_(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                birth_certificate_file_id TEXT NOT NULL,
                birth_certificate_type TEXT NOT NULL DEFAULT 'document',
                photo_file_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','rejected')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(section_id) REFERENCES sections(id) ON DELETE CASCADE,
                FOREIGN KEY(group_id) REFERENCES groups_(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS admin_application_messages (
                application_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY(application_id, admin_id),
                FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS bot_info (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            ''')

    def seed_admins(self, ids):
        with self.conn() as c:
            for uid in ids:
                c.execute('INSERT OR IGNORE INTO admins(user_id, added_at) VALUES (?,?)', (uid, now_iso()))

    def is_admin(self, user_id):
        with self.conn() as c:
            return c.execute('SELECT 1 FROM admins WHERE user_id=?', (user_id,)).fetchone() is not None

    def add_admin(self, user_id):
        with self.conn() as c:
            c.execute('INSERT OR IGNORE INTO admins(user_id, added_at) VALUES (?,?)', (user_id, now_iso()))
            return c.rowcount > 0

    def upsert_user(self, user):
        with self.conn() as c:
            c.execute('''INSERT INTO users(user_id,username,first_name,last_name,created_at) VALUES(?,?,?,?,?)
                         ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, last_name=excluded.last_name''',
                      (user.id, user.username, user.first_name, user.last_name, now_iso()))

    def list_sections(self):
        with self.conn() as c:
            return c.execute('SELECT * FROM sections ORDER BY id').fetchall()

    def get_section(self, section_id):
        with self.conn() as c:
            return c.execute('SELECT * FROM sections WHERE id=?', (section_id,)).fetchone()

    def add_section(self, name):
        with self.conn() as c:
            try:
                cur = c.execute('INSERT INTO sections(name,created_at) VALUES(?,?)', (name, now_iso()))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def delete_section(self, section_id):
        with self.conn() as c:
            # Do not silently delete existing members/applications.
            busy = c.execute('''SELECT
                (SELECT COUNT(*) FROM memberships WHERE section_id=?) +
                (SELECT COUNT(*) FROM applications WHERE section_id=?)''', (section_id, section_id)).fetchone()[0]
            if busy:
                return False, 'Bu bo‘limda a’zolar yoki arizalar bor. Avval ularni hal qiling.'
            cur = c.execute('DELETE FROM sections WHERE id=?', (section_id,))
            return cur.rowcount > 0, None

    def list_groups(self, section_id):
        with self.conn() as c:
            return c.execute('''SELECT g.*, COUNT(m.id) AS member_count
                                FROM groups_ g LEFT JOIN memberships m ON m.group_id=g.id
                                WHERE g.section_id=? GROUP BY g.id ORDER BY g.id''', (section_id,)).fetchall()

    def get_group(self, group_id):
        with self.conn() as c:
            return c.execute('''SELECT g.*, s.name AS section_name,
                               (SELECT COUNT(*) FROM memberships m WHERE m.group_id=g.id) AS member_count
                               FROM groups_ g JOIN sections s ON s.id=g.section_id WHERE g.id=?''', (group_id,)).fetchone()

    def add_group(self, section_id, name, capacity):
        with self.conn() as c:
            try:
                cur = c.execute('INSERT INTO groups_(section_id,name,capacity,created_at) VALUES(?,?,?,?)',
                                (section_id, name, capacity, now_iso()))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def delete_group(self, group_id):
        with self.conn() as c:
            members = c.execute('SELECT COUNT(*) FROM memberships WHERE group_id=?', (group_id,)).fetchone()[0]
            apps = c.execute('SELECT COUNT(*) FROM applications WHERE group_id=?', (group_id,)).fetchone()[0]
            if members or apps:
                return False, 'Bu guruhda a’zolar yoki arizalar bor. Avval ularni hal qiling.'
            cur = c.execute('DELETE FROM groups_ WHERE id=?', (group_id,))
            return cur.rowcount > 0, None

    def get_info(self):
        with self.conn() as c:
            return c.execute('SELECT text FROM bot_info WHERE id=1').fetchone()

    def set_info(self, text):
        with self.conn() as c:
            c.execute('''INSERT INTO bot_info(id,text,updated_at) VALUES(1,?,?)
                         ON CONFLICT(id) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at''', (text, now_iso()))

    def group_available(self, group_id):
        with self.conn() as c:
            row = c.execute('''SELECT g.capacity, COUNT(m.id) member_count FROM groups_ g
                               LEFT JOIN memberships m ON m.group_id=g.id WHERE g.id=? GROUP BY g.id''', (group_id,)).fetchone()
            return bool(row and row['member_count'] < row['capacity'])

    def user_membership(self, user_id):
        with self.conn() as c:
            return c.execute('''SELECT m.*, s.name section_name, g.name group_name
                                FROM memberships m JOIN sections s ON s.id=m.section_id
                                JOIN groups_ g ON g.id=m.group_id WHERE m.user_id=?''', (user_id,)).fetchone()

    def has_pending(self, user_id):
        with self.conn() as c:
            return c.execute("SELECT 1 FROM applications WHERE user_id=? AND status='pending'", (user_id,)).fetchone() is not None

    def create_application(self, user_id, section_id, group_id, birth_id, birth_type, photo_id):
        with self.conn() as c:
            if c.execute('SELECT 1 FROM memberships WHERE user_id=?', (user_id,)).fetchone():
                return False, 'Siz allaqachon guruhga qabul qilingansiz.'
            if c.execute("SELECT 1 FROM applications WHERE user_id=? AND status='pending'", (user_id,)).fetchone():
                return False, 'Sizda allaqachon ko‘rib chiqilayotgan ariza bor.'
            row = c.execute('SELECT capacity, (SELECT COUNT(*) FROM memberships WHERE group_id=g.id) cnt FROM groups_ g WHERE id=?', (group_id,)).fetchone()
            if not row:
                return False, 'Guruh topilmadi.'
            if row['cnt'] >= row['capacity']:
                return False, 'Bu guruh to‘lib qolgan.'
            c.execute('''INSERT INTO applications(user_id,section_id,group_id,birth_certificate_file_id,birth_certificate_type,photo_file_id,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?)''', (user_id,section_id,group_id,birth_id,birth_type,photo_id,'pending',now_iso(),now_iso()))
            return True, c.execute('SELECT last_insert_rowid()').fetchone()[0]

    def save_admin_application_message(self, application_id, admin_id, message_id):
        with self.conn() as c:
            c.execute('INSERT OR REPLACE INTO admin_application_messages(application_id,admin_id,message_id) VALUES(?,?,?)',
                      (application_id, admin_id, message_id))

    def get_admin_application_messages(self, application_id):
        with self.conn() as c:
            return c.execute('SELECT admin_id,message_id FROM admin_application_messages WHERE application_id=?', (application_id,)).fetchall()

    def list_applications(self):
        with self.conn() as c:
            return c.execute('''SELECT a.*, u.username,u.first_name,u.last_name,s.name section_name,g.name group_name,
                               g.capacity,(SELECT COUNT(*) FROM memberships m WHERE m.group_id=g.id) member_count
                               FROM applications a JOIN users u ON u.user_id=a.user_id
                               JOIN sections s ON s.id=a.section_id JOIN groups_ g ON g.id=a.group_id
                               ORDER BY a.id''').fetchall()

    def get_application(self, app_id):
        with self.conn() as c:
            return c.execute('''SELECT a.*,u.username,u.first_name,u.last_name,s.name section_name,g.name group_name,g.capacity,
                               (SELECT COUNT(*) FROM memberships m WHERE m.group_id=g.id) member_count
                               FROM applications a JOIN users u ON u.user_id=a.user_id
                               JOIN sections s ON s.id=a.section_id JOIN groups_ g ON g.id=a.group_id WHERE a.id=?''', (app_id,)).fetchone()

    def approve_application(self, app_id):
        # Atomic capacity check prevents two admins from exceeding capacity.
        with self.conn() as c:
            c.execute('BEGIN IMMEDIATE')
            a = c.execute("SELECT * FROM applications WHERE id=? AND status='pending'", (app_id,)).fetchone()
            if not a:
                return False, 'Ariza topilmadi yoki allaqachon ko‘rib chiqilgan.', None
            if c.execute('SELECT 1 FROM memberships WHERE user_id=?', (a['user_id'],)).fetchone():
                c.execute('DELETE FROM applications WHERE id=?', (app_id,))
                return False, 'Foydalanuvchi allaqachon guruhga qabul qilingan.', a
            g = c.execute('SELECT capacity FROM groups_ WHERE id=?', (a['group_id'],)).fetchone()
            if not g:
                return False, 'Guruh mavjud emas.', a
            count = c.execute('SELECT COUNT(*) FROM memberships WHERE group_id=?', (a['group_id'],)).fetchone()[0]
            if count >= g['capacity']:
                return False, 'Guruh ayni paytda to‘lib qolgan.', a
            c.execute('INSERT INTO memberships(user_id,section_id,group_id,joined_at) VALUES(?,?,?,?)',
                      (a['user_id'],a['section_id'],a['group_id'],now_iso()))
            c.execute('DELETE FROM applications WHERE id=?', (app_id,))
            return True, None, a

    def reject_application(self, app_id):
        with self.conn() as c:
            a = c.execute("SELECT * FROM applications WHERE id=? AND status='pending'", (app_id,)).fetchone()
            if not a:
                return False, 'Ariza topilmadi yoki allaqachon ko‘rib chiqilgan.', None
            c.execute("UPDATE applications SET status='rejected', updated_at=? WHERE id=?", (now_iso(),app_id))
            return True, None, a

    def delete_rejected(self, app_id):
        with self.conn() as c:
            c.execute("DELETE FROM applications WHERE id=? AND status='rejected'", (app_id,))

    def stats(self):
        with self.conn() as c:
            total = c.execute('SELECT COUNT(*) FROM memberships').fetchone()[0]
            sections = c.execute('''SELECT s.id,s.name,COUNT(m.id) member_count FROM sections s
                                    LEFT JOIN memberships m ON m.section_id=s.id GROUP BY s.id ORDER BY s.id''').fetchall()
            groups = c.execute('''SELECT g.id,g.name,g.capacity,s.name section_name,COUNT(m.id) member_count
                                  FROM groups_ g JOIN sections s ON s.id=g.section_id
                                  LEFT JOIN memberships m ON m.group_id=g.id
                                  GROUP BY g.id ORDER BY g.id''').fetchall()
            pending = c.execute("SELECT COUNT(*) FROM applications WHERE status='pending'").fetchone()[0]
            rejected = c.execute("SELECT COUNT(*) FROM applications WHERE status='rejected'").fetchone()[0]
            return total, sections, groups, pending, rejected
