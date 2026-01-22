import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
import json
import time
import random
import copy
from datetime import datetime

# ページ設定
st.set_page_config(page_title="Ultimate Game Station", layout="wide")

# ==========================================
# 1. データベース管理 & 共通関数
# ==========================================
DB_PATH = 'game.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # ユーザーテーブル
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, config TEXT)')
    # ルームテーブル
    c.execute('''CREATE TABLE IF NOT EXISTS rooms 
                 (room_id TEXT PRIMARY KEY, password TEXT, host TEXT, 
                  player2 TEXT, turn TEXT, board TEXT, status TEXT, last_updated TIMESTAMP)''')
    conn.commit()
    conn.close()

def run_db(query, args=(), fetch=False, fetch_one=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, args)
    res = None
    if fetch: res = c.fetchall()
    elif fetch_one: res = c.fetchone()
    if commit: conn.commit()
    conn.close()
    return res

def hash_pass(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# 2. 消し四 (Connect 4) ロジック & AI (完全版)
# ==========================================
ROWS, COLS = 6, 7

class Connect4Logic:
    def __init__(self, board=None):
        self.board = board if board else [[0]*COLS for _ in range(ROWS)]

    def drop_piece(self, col, piece):
        for r in range(ROWS-1, -1, -1):
            if self.board[r][col] == 0:
                self.board[r][col] = piece
                return r
        return None

    def is_valid(self, col):
        return self.board[0][col] == 0

    def check_win(self, piece):
        b = self.board
        # 横
        for c in range(COLS-3):
            for r in range(ROWS):
                if b[r][c] == piece and b[r][c+1] == piece and b[r][c+2] == piece and b[r][c+3] == piece: return True
        # 縦
        for c in range(COLS):
            for r in range(ROWS-3):
                if b[r][c] == piece and b[r+1][c] == piece and b[r+2][c] == piece and b[r+3][c] == piece: return True
        # 正の斜め (/)
        for c in range(COLS-3):
            for r in range(ROWS-3):
                if b[r][c] == piece and b[r+1][c+1] == piece and b[r+2][c+2] == piece and b[r+3][c+3] == piece: return True
        # 負の斜め (\)
        for c in range(COLS-3):
            for r in range(3, ROWS):
                if b[r][c] == piece and b[r-1][c+1] == piece and b[r-2][c+2] == piece and b[r-3][c+3] == piece: return True
        return False

# --- AI評価関数 (斜め完全実装) ---
def evaluate_window(window, piece):
    score = 0
    opp_piece = 1 if piece == 2 else 2

    if window.count(piece) == 4:
        score += 100
    elif window.count(piece) == 3 and window.count(0) == 1:
        score += 5
    elif window.count(piece) == 2 and window.count(0) == 2:
        score += 2

    if window.count(opp_piece) == 3 and window.count(0) == 1:
        score -= 4 # 相手のリーチを阻止する評価

    return score

def score_position(board, piece):
    score = 0
    
    # 1. 中央列の支配（戦術的に重要）
    center_array = [row[COLS//2] for row in board]
    center_count = center_array.count(piece)
    score += center_count * 3

    # 2. 横方向の評価
    for r in range(ROWS):
        row_array = board[r]
        for c in range(COLS-3):
            window = row_array[c:c+4]
            score += evaluate_window(window, piece)

    # 3. 縦方向の評価
    for c in range(COLS):
        col_array = [board[r][c] for r in range(ROWS)]
        for r in range(ROWS-3):
            window = col_array[r:r+4]
            score += evaluate_window(window, piece)

    # 4. 正の斜め (右下がり \ ) の評価
    for r in range(ROWS-3):
        for c in range(COLS-3):
            window = [board[r+i][c+i] for i in range(4)]
            score += evaluate_window(window, piece)

    # 5. 負の斜め (右上がり / ) の評価
    for r in range(ROWS-3):
        for c in range(COLS-3):
            window = [board[r+3-i][c+i] for i in range(4)]
            score += evaluate_window(window, piece)

    return score

def minimax(board, depth, alpha, beta, maximizingPlayer):
    logic = Connect4Logic(board)
    valid_locs = [c for c in range(COLS) if logic.is_valid(c)]
    is_terminal = logic.check_win(1) or logic.check_win(2) or len(valid_locs) == 0
    
    if depth == 0 or is_terminal:
        if is_terminal:
            if logic.check_win(2): return (None, 10000000) # CPU Win
            elif logic.check_win(1): return (None, -10000000) # Player Win
            else: return (None, 0)
        else:
            return (None, score_position(board, 2))

    if maximizingPlayer:
        value = -float('inf')
        column = random.choice(valid_locs)
        for col in valid_locs:
            b_copy = copy.deepcopy(board)
            Connect4Logic(b_copy).drop_piece(col, 2)
            new_score = minimax(b_copy, depth-1, alpha, beta, False)[1]
            if new_score > value:
                value = new_score
                column = col
            alpha = max(alpha, value)
            if alpha >= beta: break
        return column, value
    else:
        value = float('inf')
        column = random.choice(valid_locs)
        for col in valid_locs:
            b_copy = copy.deepcopy(board)
            Connect4Logic(b_copy).drop_piece(col, 1)
            new_score = minimax(b_copy, depth-1, alpha, beta, True)[1]
            if new_score < value:
                value = new_score
                column = col
            beta = min(beta, value)
            if alpha >= beta: break
        return column, value

# ==========================================
# 3. テトリス (JS版・変更なし)
# ==========================================
def tetris_game(user_config):
    config_json = json.dumps(user_config)
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <style>
        body {{ background-color: #0e1117; color: white; text-align: center; touch-action: none; margin: 0; font-family: sans-serif; }}
        canvas {{ border: 2px solid #555; background: #000; display: block; margin: 10px auto; width: 90%; max-width: 300px; }}
        .btn-area {{ display: flex; justify-content: center; gap: 10px; margin-top: 10px; }}
        button {{ background: #333; color: white; border: 1px solid #777; padding: 10px 15px; font-size: 16px; border-radius: 5px; cursor: pointer; }}
        button:active {{ background: #555; }}
    </style>
    </head>
    <body>
    <h3>Score: <span id="score">0</span></h3>
    <div style="font-size:0.8em;color:#aaa">画面クリックでキー操作有効</div>
    <canvas id="tetris" width="240" height="400"></canvas>
    <div class="btn-area">
        <button onclick="move(-1)">⬅️</button>
        <button onclick="rotate()">🔄</button>
        <button onclick="move(1)">➡️</button>
    </div>
    <div class="btn-area">
        <button style="width:80%" onclick="drop()">⬇️ DROP</button>
    </div>
    <script>
    const keyConfig = {config_json};
    const cvs = document.getElementById('tetris');
    const ctx = cvs.getContext('2d');
    ctx.scale(20, 20);
    const arena = createMatrix(12, 20);
    const player = {{ pos: {{x:0, y:0}}, matrix:null, score:0 }};
    function createMatrix(w, h) {{ const m=[]; while(h--) m.push(new Array(w).fill(0)); return m; }}
    function createPiece(t) {{
        if (t==='I') return [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]];
        if (t==='O') return [[2,2],[2,2]];
        if (t==='T') return [[0,3,0],[3,3,3],[0,0,0]];
        if (t==='S') return [[0,4,4],[4,4,0],[0,0,0]];
        if (t==='Z') return [[5,5,0],[0,5,5],[0,0,0]];
        if (t==='J') return [[0,6,0],[0,6,0],[6,6,0]];
        if (t==='L') return [[0,7,0],[0,7,0],[0,7,7]];
    }}
    const colors=[null,'#FF0D72','#0DC2FF','#0DFF72','#F538FF','#FF8E0D','#FFE138','#3877FF'];
    function draw() {{
        ctx.fillStyle='#000'; ctx.fillRect(0,0,cvs.width,cvs.height);
        drawMatrix(arena,{{x:0,y:0}}); drawMatrix(player.matrix,player.pos);
    }}
    function drawMatrix(m,o) {{
        m.forEach((r,y)=>{{ r.forEach((v,x)=>{{ if(v!==0){{ ctx.fillStyle=colors[v]; ctx.fillRect(x+o.x,y+o.y,1,1); }} }}); }});
    }}
    function merge(a,p) {{ p.matrix.forEach((r,y)=>{{ r.forEach((v,x)=>{{ if(v!==0) a[y+p.pos.y][x+p.pos.x]=v; }}); }}); }}
    function rotate() {{
        const m=player.matrix; for(let y=0;y<m.length;++y) for(let x=0;x<y;++x) [m[x][y],m[y][x]]=[m[y][x],m[x][y]];
        m.reverse(); if(collide(arena,player)) m.reverse();
    }}
    function collide(a,p) {{
        const [m,o]=[p.matrix,p.pos];
        for(let y=0;y<m.length;++y) for(let x=0;x<m[y].length;++x) if(m[y][x]!==0 && (a[y+o.y] && a[y+o.y][x+o.x])!==0) return true;
        return false;
    }}
    function arenaSweep() {{
        let rc=1; outer: for(let y=arena.length-1;y>0;--y) {{
            for(let x=0;x<arena[y].length;++x) if(arena[y][x]===0) continue outer;
            const r=arena.splice(y,1)[0].fill(0); arena.unshift(r); ++y;
            player.score+=rc*10; rc*=2;
        }}
        document.getElementById('score').innerText=player.score;
    }}
    function drop() {{
        player.pos.y++; if(collide(arena,player)) {{ player.pos.y--; merge(arena,player); playerReset(); arenaSweep(); }}
        dropCounter=0;
    }}
    function move(d) {{ player.pos.x+=d; if(collide(arena,player)) player.pos.x-=d; }}
    function playerReset() {{
        const p='ILJOTSZ'; player.matrix=createPiece(p[p.length*Math.random()|0]);
        player.pos.y=0; player.pos.x=(arena[0].length/2|0)-(player.matrix[0].length/2|0);
        if(collide(arena,player)) {{ arena.forEach(r=>r.fill(0)); player.score=0; document.getElementById('score').innerText=0; }}
    }}
    let dropCounter=0; let lastTime=0;
    function update(t=0) {{
        const dt=t-lastTime; lastTime=t; dropCounter+=dt;
        if(dropCounter>1000) drop(); draw(); requestAnimationFrame(update);
    }}
    document.addEventListener('keydown', e => {{
        const k=e.key;
        if(k===keyConfig.left) {{ move(-1); e.preventDefault(); }}
        else if(k===keyConfig.right) {{ move(1); e.preventDefault(); }}
        else if(k===keyConfig.drop) {{ drop(); e.preventDefault(); }}
        else if(k===keyConfig.rotate) {{ rotate(); e.preventDefault(); }}
    }});
    playerReset(); update();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=600)

# ==========================================
# 4. 消し四 UI & モード処理
# ==========================================
def render_connect4_board(board):
    html = '<div style="background-color:#0055bb; padding:10px; border-radius:10px; display:inline-block;">'
    for row in board:
        html += '<div style="display:flex;">'
        for cell in row:
            color = "#fff"
            if cell == 1: color = "#ff3333" 
            elif cell == 2: color = "#ffcc00" 
            html += f'<div style="width:40px; height:40px; background-color:{color}; border-radius:50%; margin:3px;"></div>'
        html += '</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def connect4_local_cpu_mode(mode):
    if 'c4_board' not in st.session_state:
        st.session_state.c4_board = [[0]*COLS for _ in range(ROWS)]
        st.session_state.c4_turn = 1
        st.session_state.c4_status = 'playing'
    
    logic = Connect4Logic(st.session_state.c4_board)
    
    if st.button("🔄 ゲームリセット"):
        st.session_state.c4_board = [[0]*COLS for _ in range(ROWS)]
        st.session_state.c4_turn = 1
        st.session_state.c4_status = 'playing'
        st.rerun()

    if st.session_state.c4_status != 'playing':
        msg = "Player 1 (赤) の勝ち！" if st.session_state.c4_status == 'p1_win' else "Player 2 (黄) の勝ち！"
        st.success(msg)
    else:
        current_p = "Player 1 (赤)" if st.session_state.c4_turn == 1 else "Player 2 (黄)"
        st.info(f"手番: {current_p}")

    cols = st.columns(COLS)
    for i, col in enumerate(cols):
        if col.button(f"⬇", key=f"drop_{i}"):
            if st.session_state.c4_status == 'playing' and logic.is_valid(i):
                logic.drop_piece(i, st.session_state.c4_turn)
                if logic.check_win(st.session_state.c4_turn):
                    st.session_state.c4_status = 'p1_win' if st.session_state.c4_turn == 1 else 'p2_win'
                else:
                    st.session_state.c4_turn = 3 - st.session_state.c4_turn
                    st.rerun()

    render_connect4_board(st.session_state.c4_board)

    if mode == "CPU" and st.session_state.c4_turn == 2 and st.session_state.c4_status == 'playing':
        with st.spinner(f"CPU (Lv.{st.session_state.cpu_level}) 思考中..."):
            time.sleep(0.5)
            lvl = st.session_state.cpu_level
            if lvl == 1: 
                col = random.choice([c for c in range(COLS) if logic.is_valid(c)])
            else:
                depth = lvl + 1 # レベル補正 (少し強く)
                col, _ = minimax(st.session_state.c4_board, depth, -float('inf'), float('inf'), True)
            
            if col is not None:
                logic.drop_piece(col, 2)
                if logic.check_win(2):
                    st.session_state.c4_status = 'p2_win'
                else:
                    st.session_state.c4_turn = 1
                st.rerun()

def connect4_network_mode(username):
    st.subheader("🌐 ネットワーク対戦")
    
    if 'room_id' not in st.session_state:
        tab1, tab2 = st.tabs(["部屋に参加", "部屋を作成"])
        
        with tab1:
            rooms = run_db("SELECT room_id, host, status FROM rooms WHERE status='waiting'", fetch=True)
            if rooms:
                for r in rooms:
                    with st.expander(f"{r[1]}の部屋 (ID: {r[0]})"):
                        input_pass = st.text_input("パスワード", key=f"p_{r[0]}")
                        if st.button("参加", key=f"j_{r[0]}"):
                            verify = run_db("SELECT * FROM rooms WHERE room_id=? AND password=?", (r[0], input_pass), fetch_one=True)
                            if verify:
                                run_db("UPDATE rooms SET player2=?, status='playing' WHERE room_id=?", (username, r[0]), commit=True)
                                st.session_state.room_id = r[0]
                                st.session_state.is_host = False
                                st.rerun()
                            else:
                                st.error("パスワードが違います")
            else:
                st.info("待機中の部屋はありません")
        
        with tab2:
            c1, c2 = st.columns(2)
            new_id = c1.text_input("ルームID (数字5桁)")
            new_pass = c2.text_input("パスワード")
            if st.button("作成"):
                try:
                    init_board = json.dumps([[0]*COLS for _ in range(ROWS)])
                    run_db("INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?)", 
                           (new_id, new_pass, username, None, username, init_board, 'waiting', datetime.now()), commit=True)
                    st.session_state.room_id = new_id
                    st.session_state.is_host = True
                    st.rerun()
                except:
                    st.error("そのIDは使用済みです")

    else:
        rid = st.session_state.room_id
        data = run_db("SELECT host, player2, turn, board, status FROM rooms WHERE room_id=?", (rid,), fetch_one=True)
        
        if not data:
            st.error("部屋が解散されました")
            del st.session_state.room_id
            st.rerun()
            return

        host, p2, turn_user, board_json, status = data
        board = json.loads(board_json)
        my_piece = 1 if st.session_state.is_host else 2
        
        st.write(f"Room: {rid} | Host: {host} vs Guest: {p2 if p2 else '待機中...'}")
        
        if st.button("退出 / 解散"):
            run_db("DELETE FROM rooms WHERE room_id=?", (rid,), commit=True)
            del st.session_state.room_id
            st.rerun()

        if status == 'waiting':
            st.warning("対戦相手を待っています...")
            time.sleep(3)
            st.rerun()
            return

        render_connect4_board(board)
        
        if status.endswith('win'):
            st.success(f"勝者: {turn_user}") 
            return

        is_my_turn = (turn_user == username)
        
        if is_my_turn:
            st.success("あなたの番です！")
            cols = st.columns(COLS)
            for i, col in enumerate(cols):
                if col.button("⬇", key=f"net_{i}"):
                    logic = Connect4Logic(board)
                    if logic.is_valid(i):
                        logic.drop_piece(i, my_piece)
                        next_turn = p2 if st.session_state.is_host else host
                        next_status = 'playing'
                        
                        if logic.check_win(my_piece):
                            next_status = f"{username} win"
                            st.balloons()
                        
                        run_db("UPDATE rooms SET board=?, turn=?, status=? WHERE room_id=?", 
                               (json.dumps(board), next_turn, next_status, rid), commit=True)
                        st.rerun()
        else:
            st.info(f"相手 ({turn_user}) の思考中...")
            time.sleep(2)
            st.rerun()

# ==========================================
# 5. メインアプリ
# ==========================================
def main():
    init_db()
    if 'user' not in st.session_state: st.session_state.user = None
    if 'config' not in st.session_state: 
        st.session_state.config = {"left": "ArrowLeft", "right": "ArrowRight", "drop": "ArrowDown", "rotate": "ArrowUp"}

    if not st.session_state.user:
        st.title("🔐 Game Station Login")
        tab1, tab2 = st.tabs(["ログイン", "新規登録"])
        with tab1:
            u = st.text_input("ID")
            p = st.text_input("Pass", type="password")
            if st.button("Login"):
                res = run_db("SELECT username, config FROM users WHERE username=? AND password=?", (u, hash_pass(p)), fetch_one=True)
                if res:
                    st.session_state.user = res[0]
                    if res[1]: st.session_state.config = json.loads(res[1])
                    st.rerun()
                else: st.error("認証失敗")
        with tab2:
            nu = st.text_input("New ID")
            np = st.text_input("New Pass", type="password")
            if st.button("Register"):
                try:
                    run_db("INSERT INTO users VALUES (?,?,?)", (nu, hash_pass(np), json.dumps(st.session_state.config)), commit=True)
                    st.success("登録完了")
                except: st.error("ID重複")
    else:
        with st.sidebar:
            st.title(f"👤 {st.session_state.user}")
            if st.button("ログアウト"):
                st.session_state.user = None
                st.rerun()
            st.markdown("---")
            menu = st.radio("ゲーム選択", ["Tetraminos (Solo)", "Connect 4 (消し四)", "設定"])

        if menu == "Tetraminos (Solo)":
            st.title("🧱 Tetraminos (JS High-Speed)")
            st.write(f"Key: L={st.session_state.config['left']} R={st.session_state.config['right']} Drop={st.session_state.config['drop']}")
            st.warning("ゲーム画面をクリックしてから操作してください")
            tetris_game(st.session_state.config)

        elif menu == "Connect 4 (消し四)":
            st.title("🔴 Connect 4")
            mode = st.selectbox("対戦モード", ["CPU対戦", "ローカル対戦 (2P)", "ネットワーク対戦"])
            
            if mode == "CPU対戦":
                st.session_state.cpu_level = st.slider("CPUレベル", 1, 5, 1)
                connect4_local_cpu_mode("CPU")
            elif mode == "ローカル対戦 (2P)":
                connect4_local_cpu_mode("LOCAL")
            elif mode == "ネットワーク対戦":
                connect4_network_mode(st.session_state.user)

        elif menu == "設定":
            st.header("⚙️ キー割り当て")
            c1, c2 = st.columns(2)
            l = c1.text_input("左", st.session_state.config['left'])
            r = c2.text_input("右", st.session_state.config['right'])
            ro = c1.text_input("回転", st.session_state.config['rotate'])
            d = c2.text_input("落下", st.session_state.config['drop'])
            if st.button("保存"):
                conf = {"left":l, "right":r, "rotate":ro, "drop":d}
                st.session_state.config = conf
                run_db("UPDATE users SET config=? WHERE username=?", (json.dumps(conf), st.session_state.user), commit=True)
                st.success("保存しました")

if __name__ == '__main__':
    main()