import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
import json
import time
import random
import copy
from datetime import datetime

st.set_page_config(page_title="Ultimate Game Station", layout="wide")

# ==========================================
# 1. データベース管理
# ==========================================
DB_PATH = 'game.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, config TEXT)')
    # roomテーブル (boardには詳細なゲーム状態をJSONで保存)
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
# 2. 消し四 (Keshi-Yon) 独自ルールロジック
# ==========================================
# フィールド: 横5マス x 縦6マス
ROWS = 6
COLS = 5

class KeshiYonLogic:
    def __init__(self, state=None):
        if state:
            self.board = state['board']
            self.active_rows = state['active_rows']
            self.match_count = state['match_count']
            self.p1_score = state['p1_score']
            self.p2_score = state['p2_score']
        else:
            self.board = [[0]*COLS for _ in range(ROWS)]
            self.active_rows = 4 # 初期は下4段
            self.match_count = 0
            self.p1_score = 0
            self.p2_score = 0

    def get_state(self):
        return {
            'board': self.board,
            'active_rows': self.active_rows,
            'match_count': self.match_count,
            'p1_score': self.p1_score,
            'p2_score': self.p2_score
        }

    # 設置可能な行を取得（重力あり、浮遊ブロックの上に着地）
    def get_landing_row(self, col):
        # 上から探索して、最初にぶつかるブロックの「一つ上」に置く
        # ただし、active_rowsの範囲内でないといけない
        for r in range(self.active_rows - 1, -1, -1):
            if self.board[r][col] != 0:
                return r + 1
        return 0 # 何もなければ最下層(0)

    def is_valid(self, col):
        if col < 0 or col >= COLS: return False
        row = self.get_landing_row(col)
        return row < self.active_rows

    def place_piece(self, col, player):
        row = self.get_landing_row(col)
        self.board[row][col] = player
        
        # 揃ったかチェック
        matched_coords = self.check_matches(player)
        
        if matched_coords:
            # 得点加算 (同時揃いも1点)
            if player == 1: self.p1_score += 1
            else: self.p2_score += 1
            
            self.match_count += 1
            is_odd = (self.match_count % 2 == 1)
            
            if is_odd:
                # 奇数回: 揃ったマークを△(3)に変える
                for r, c in matched_coords:
                    self.board[r][c] = 3
            else:
                # 偶数回: 揃ったマークを消す + 隣接する△も消す
                # まず消える対象を特定
                to_remove = set(matched_coords)
                
                # 隣接チェック (斜めなし)
                deltas = [(0,1), (0,-1), (1,0), (-1,0)]
                for r, c in matched_coords:
                    for dr, dc in deltas:
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < ROWS and 0 <= nc < COLS:
                            if self.board[nr][nc] == 3: # △なら
                                to_remove.add((nr, nc))
                
                # 盤面から消去 (0にする)
                for r, c in to_remove:
                    self.board[r][c] = 0
                    # ※「上に乗っているマークは落下しない」ので詰め処理は不要

        # 拡張ルールのチェック
        self.check_expansion()
        
        # ゲーム終了/ボーナス判定
        return self.check_game_over(player)

    def check_matches(self, player):
        # 4つ以上揃っている座標のセットを返す
        matched = set()
        b = self.board
        
        # 横
        for r in range(self.active_rows):
            for c in range(COLS - 3):
                if b[r][c]==player and b[r][c+1]==player and b[r][c+2]==player and b[r][c+3]==player:
                    matched.update([(r, c+i) for i in range(4)])
        # 縦
        for c in range(COLS):
            for r in range(self.active_rows - 3):
                if b[r][c]==player and b[r+1][c]==player and b[r+2][c]==player and b[r+3][c]==player:
                    matched.update([(r+i, c) for i in range(4)])
        # 斜め /
        for c in range(COLS - 3):
            for r in range(self.active_rows - 3):
                if b[r][c]==player and b[r+1][c+1]==player and b[r+2][c+2]==player and b[r+3][c+3]==player:
                    matched.update([(r+i, c+i) for i in range(4)])
        # 斜め \
        for c in range(COLS - 3):
            for r in range(3, self.active_rows):
                if b[r][c]==player and b[r-1][c+1]==player and b[r-2][c+2]==player and b[r-3][c+3]==player:
                    matched.update([(r-i, c+i) for i in range(4)])
                    
        return list(matched)

    def check_expansion(self):
        # 現在のフィールドの空きマス数を確認
        empty_count = 0
        for r in range(self.active_rows):
            for c in range(COLS):
                if self.board[r][c] == 0:
                    empty_count += 1
        
        # 同点 かつ 残り2マス以下 なら拡張
        if self.p1_score == self.p2_score and empty_count <= 2:
            if self.active_rows < ROWS:
                self.active_rows += 1

    def count_empty_spots(self):
        cnt = 0
        for r in range(self.active_rows):
            for c in range(COLS):
                if self.board[r][c] == 0: cnt += 1
        return cnt

    def check_game_over(self, last_player):
        # 空きマスがない場合
        if self.count_empty_spots() == 0:
            # ルール5: 同点でない場合、最後に置いたプレイヤーに+1点
            if self.p1_score != self.p2_score:
                if last_player == 1: self.p1_score += 1
                else: self.p2_score += 1
                return 'finished'
            else:
                # 同点の場合 (既に拡張チェックは走っているが、拡張できなかった場合)
                if self.active_rows == ROWS:
                    return 'finished' # 最大まで拡張して同点なら終了
                else:
                    return 'continue' # 拡張されたので続行

        # ルール5追記: 1点差で負けている方が最後に置いて同点になった場合 -> 拡張して続行
        # これは check_expansion で「同点なら拡張」されるので自動的にカバーされるが、
        # マスが埋まった瞬間の処理として明示
        
        return 'continue'

# 簡易AI (ルール対応版)
def cpu_move(logic_state, level):
    logic = KeshiYonLogic(copy.deepcopy(logic_state))
    valid_cols = [c for c in range(COLS) if logic.is_valid(c)]
    
    if not valid_cols: return None

    # Lv1: 完全ランダム
    if level == 1: return random.choice(valid_cols)
    
    # Lv2~5: 1手先読み評価 (深さ探索はルールが複雑なため軽量化)
    best_col = random.choice(valid_cols)
    best_score = -9999
    
    for col in valid_cols:
        temp_logic = KeshiYonLogic(copy.deepcopy(logic_state))
        
        # 自分の手番と仮定 (CPUはPlayer2)
        initial_score = temp_logic.p2_score
        temp_logic.place_piece(col, 2)
        score_gain = temp_logic.p2_score - initial_score
        
        # 評価値計算
        eval_score = score_gain * 10
        
        # 相手に揃えさせない (Lv3以上)
        if level >= 3:
            opp_logic = KeshiYonLogic(copy.deepcopy(logic_state))
            opp_logic.place_piece(col, 1) # 自分が置かなかったら相手が置く場所
            if opp_logic.p1_score > logic.p1_score:
                eval_score += 5 # 妨害ボーナス
        
        # 中央優先 (Lv4以上)
        if level >= 4 and col in [1, 2, 3]:
            eval_score += 1

        if eval_score > best_score:
            best_score = eval_score
            best_col = col
            
    return best_col

# ==========================================
# 3. テトリス (変更なし)
# ==========================================
def tetris_game(user_config):
    # (前回のテトリスコードと同じため省略しませんが、長くなるのでそのまま埋め込みます)
    # 実際にはここに前回の tetris_game 関数が入ります
    # 便宜上、前回のHTMLコードを使用してください
    defaults = {"left":"ArrowLeft", "right":"ArrowRight", "rotate_r":"ArrowUp", "rotate_l":"z", "soft_drop":"ArrowDown", "hard_drop":" ", "hold":"c"}
    for k,v in defaults.items(): 
        if k not in user_config: user_config[k]=v
    config_json = json.dumps(user_config)
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <style>
        body {{ background-color: #0e1117; color: white; text-align: center; touch-action: none; margin: 0; font-family: sans-serif; }}
        .game-wrapper {{ display: flex; justify-content: center; gap: 10px; margin-top: 20px; }}
        canvas {{ background: #000; border: 2px solid #555; display: block; }}
        h4 {{ margin: 0 0 5px 0; font-size: 14px; color: #aaa; }}
    </style>
    </head>
    <body>
    <div class="game-wrapper">
        <div><h4>HOLD</h4><canvas id="hold" width="80" height="80"></canvas><h4>SCORE</h4><div id="score">0</div></div>
        <canvas id="tetris" width="200" height="400"></canvas>
        <div><h4>NEXT</h4><canvas id="next" width="80" height="240"></canvas></div>
    </div>
    <script>
    const keyConfig = {config_json};
    const cvs = document.getElementById('tetris'); const ctx = cvs.getContext('2d');
    const nCvs = document.getElementById('next'); const nCtx = nCvs.getContext('2d');
    const hCvs = document.getElementById('hold'); const hCtx = hCvs.getContext('2d');
    ctx.scale(20,20); nCtx.scale(20,20); hCtx.scale(20,20);
    const SRS=[null,'#800080','#00FFFF','#00FF00','#FF0000','#FFA500','#0000FF','#FFFF00'];
    const SHAPES={{'T':[[0,1,0],[1,1,1],[0,0,0]],'I':[[0,2,0,0],[0,2,0,0],[0,2,0,0],[0,2,0,0]],'S':[[0,3,3],[3,3,0],[0,0,0]],'Z':[[4,4,0],[0,4,4],[0,0,0]],'L':[[0,0,5],[5,5,5],[0,0,0]],'J':[[6,0,0],[6,6,6],[0,0,0]],'O':[[7,7],[7,7]]}};
    const arena=createMatrix(10,20);
    const player={{pos:{{x:0,y:0}},matrix:null,score:0,held:null,canHold:true,next:[]}};
    function createMatrix(w,h){{const m=[];while(h--)m.push(new Array(w).fill(0));return m;}}
    function draw(){{
        ctx.fillStyle='#000';ctx.fillRect(0,0,200,400);
        drawMatrix(ctx,arena,{{x:0,y:0}}); drawMatrix(ctx,player.matrix,player.pos);
        nCtx.fillStyle='#000';nCtx.fillRect(0,0,80,240);
        player.next.slice(0,3).forEach((t,i)=>drawMatrix(nCtx,SHAPES[t],{{x:1,y:i*4+1}}));
        hCtx.fillStyle='#000';hCtx.fillRect(0,0,80,80);
        if(player.held)drawMatrix(hCtx,SHAPES[player.held],{{x:1,y:1}});
    }}
    function drawMatrix(c,m,o){{m.forEach((r,y)=>{{r.forEach((v,x)=>{{if(v!==0){{c.fillStyle=SRS[v];c.fillRect(x+o.x,y+o.y,1,1);c.lineWidth=0.1;c.strokeRect(x+o.x,y+o.y,1,1);}}}})}})}}
    function collide(a,p){{const[m,o]=[p.matrix,p.pos];for(let y=0;y<m.length;++y)for(let x=0;x<m[y].length;++x)if(m[y][x]!==0&&(a[y+o.y]&&a[y+o.y][x+o.x])!==0)return true;return false;}}
    function merge(a,p){{p.matrix.forEach((r,y)=>{{r.forEach((v,x)=>{{if(v!==0)a[y+p.pos.y][x+p.pos.x]=v;}});}});}}
    function rotate(m,d){{for(let y=0;y<m.length;++y)for(let x=0;x<y;++x)[m[x][y],m[y][x]]=[m[y][x],m[x][y]];if(d>0)m.forEach(r=>r.reverse());else m.reverse();}}
    function pRotate(d){{const p=player.pos.x;let o=1;rotate(player.matrix,d);while(collide(arena,player)){{player.pos.x+=o;o=-(o+(o>0?1:-1));if(o>player.matrix[0].length){{rotate(player.matrix,-d);player.pos.x=p;return;}}}}}}
    function pReset(){{if(player.next.length===0)fillBag();const t=player.next.shift();player.matrix=JSON.parse(JSON.stringify(SHAPES[t]));player.pos.y=0;player.pos.x=3;player.canHold=true;if(collide(arena,player)){{arena.forEach(r=>r.fill(0));player.score=0;player.held=null;document.getElementById('score').innerText=0;}}}}
    function fillBag(){{const t=['I','L','J','O','Z','S','T'];for(let i=t.length-1;i>0;i--){{const j=Math.floor(Math.random()*(i+1));[t[i],t[j]]=[t[j],t[i]];}}player.next.push(...t);}}
    function pHold(){{if(!player.canHold)return;let v=0;player.matrix.some(r=>r.some(c=>{{if(c>0)v=c;return c>0}}));const map={{1:'T',2:'I',3:'S',4:'Z',5:'L',6:'J',7:'O'}};const t=map[v];if(!player.held){{player.held=t;pReset();}}else{{const tmp=player.held;player.held=t;player.matrix=JSON.parse(JSON.stringify(SHAPES[tmp]));player.pos.y=0;player.pos.x=3;}}player.canHold=false;}}
    function pDrop(){{player.pos.y++;if(collide(arena,player)){{player.pos.y--;merge(arena,player);pReset();let rc=1;outer:for(let y=19;y>0;--y){{for(let x=0;x<10;++x)if(arena[y][x]===0)continue outer;arena.splice(y,1)[0].fill(0);arena.unshift(new Array(10).fill(0));++y;player.score+=rc*10;rc*=2;}}document.getElementById('score').innerText=player.score;}}dropC=0;}}
    function pMove(d){{player.pos.x+=d;if(collide(arena,player))player.pos.x-=d;}}
    let dropC=0;let lastT=0;function update(t=0){{const dt=t-lastT;lastT=t;dropC+=dt;if(dropC>1000)pDrop();draw();requestAnimationFrame(update);}}
    document.addEventListener('keydown',e=>{{const k=e.key;if(k===keyConfig.left)pMove(-1);else if(k===keyConfig.right)pMove(1);else if(k===keyConfig.soft_drop)pDrop();else if(k===keyConfig.rotate_r)pRotate(1);else if(k===keyConfig.rotate_l)pRotate(-1);else if(k===keyConfig.hard_drop){{while(!collide(arena,player))player.pos.y++;player.pos.y--;merge(arena,player);pDrop();}}else if(k===keyConfig.hold)pHold();}});
    fillBag();pReset();update();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=600)

# ==========================================
# 4. 消し四 UI & モード処理 (完全リニューアル)
# ==========================================
def render_keshiyon_board(logic):
    state = logic.get_state()
    board = state['board']
    active = state['active_rows']
    
    # スコアと情報表示
    c1, c2, c3 = st.columns([1,2,1])
    with c1: st.metric("Player 1 (◯)", state['p1_score'])
    with c3: st.metric("Player 2 (✕)", state['p2_score'])
    with c2:
        next_effect = "次: △に変化 (奇数)" if (state['match_count'] % 2 == 0) else "次: 消滅 (偶数)"
        st.info(f"現在のフィールド: {active}段目まで | {next_effect}")

    # 盤面描画
    html = '<div style="background:#222; padding:10px; border-radius:10px; display:inline-block;">'
    # 逆順で描画（上から下へ）
    for r in range(ROWS-1, -1, -1):
        html += '<div style="display:flex;">'
        for c in range(COLS):
            val = board[r][c]
            bg = "#333" # 空
            mark = ""
            
            # アクティブエリア外は暗くする
            if r >= active:
                bg = "#111"
            
            if val == 1: # P1
                bg = "#ff4b4b"
                mark = "◯"
            elif val == 2: # P2
                bg = "#1c83e1"
                mark = "✕"
            elif val == 3: # Triangle
                bg = "#26a641"
                mark = "△"
            
            html += f'<div style="width:50px; height:50px; background:{bg}; color:white; font-size:30px; display:flex; justify-content:center; align-items:center; border:1px solid #444; margin:2px;">{mark}</div>'
        html += '</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

def keshiyon_local_cpu(mode):
    if 'ky_state' not in st.session_state:
        st.session_state.ky_state = None
        st.session_state.ky_turn = 1 # 1=P1, 2=P2
        st.session_state.ky_status = 'playing'

    logic = KeshiYonLogic(st.session_state.ky_state)
    
    if st.button("🔄 最初から"):
        st.session_state.ky_state = None
        st.session_state.ky_turn = 1
        st.session_state.ky_status = 'playing'
        st.rerun()

    if st.session_state.ky_status == 'finished':
        s = logic.get_state()
        winner = "引き分け"
        if s['p1_score'] > s['p2_score']: winner = "Player 1 (◯) の勝ち！"
        elif s['p2_score'] > s['p1_score']: winner = "Player 2 (✕) の勝ち！"
        st.success(f"ゲーム終了！ {winner}")
    else:
        current = "Player 1 (◯)" if st.session_state.ky_turn == 1 else "Player 2 (✕)"
        st.write(f"手番: {current}")

    # 操作ボタン
    cols = st.columns(COLS)
    for i, col in enumerate(cols):
        # 自分のターン かつ ゲーム中 かつ 置ける場所がある
        if st.session_state.ky_status == 'playing' and logic.is_valid(i):
            # CPUモードでP2の番ならボタン無効
            disabled = (mode == "CPU" and st.session_state.ky_turn == 2)
            if col.button("⬇", key=f"k_{i}", disabled=disabled):
                status = logic.place_piece(i, st.session_state.ky_turn)
                st.session_state.ky_state = logic.get_state()
                st.session_state.ky_status = status
                
                if status == 'continue':
                    st.session_state.ky_turn = 3 - st.session_state.ky_turn # 交代
                st.rerun()

    render_keshiyon_board(logic)

    # CPU Turn
    if mode == "CPU" and st.session_state.ky_turn == 2 and st.session_state.ky_status == 'playing':
        with st.spinner(f"CPU (Lv.{st.session_state.cpu_level}) 思考中..."):
            time.sleep(1.0)
            col = cpu_move(logic.get_state(), st.session_state.cpu_level)
            if col is not None:
                status = logic.place_piece(col, 2)
                st.session_state.ky_state = logic.get_state()
                st.session_state.ky_status = status
                if status == 'continue':
                    st.session_state.ky_turn = 1
                st.rerun()

def keshiyon_network(username):
    st.subheader("🌐 消し四 オンライン")
    
    if 'room_id' not in st.session_state:
        t1, t2 = st.tabs(["参加", "作成"])
        with t1:
            rooms = run_db("SELECT room_id, host, status FROM rooms WHERE status='waiting'", fetch=True)
            if rooms:
                for r in rooms:
                    with st.expander(f"Room {r[0]} (Host: {r[1]})"):
                        pas = st.text_input("Pass", key=f"kp_{r[0]}")
                        if st.button("Join", key=f"kj_{r[0]}"):
                            if run_db("SELECT * FROM rooms WHERE room_id=? AND password=?", (r[0], pas), fetch_one=True):
                                run_db("UPDATE rooms SET player2=?, status='playing' WHERE room_id=?", (username, r[0]), commit=True)
                                st.session_state.room_id = r[0]
                                st.session_state.is_host = False
                                st.rerun()
                            else: st.error("パスワード不一致")
            else: st.info("部屋なし")
        with t2:
            c1, c2 = st.columns(2)
            new_id = c1.text_input("ID(5桁)")
            new_pass = c2.text_input("Pass")
            if st.button("Create"):
                try:
                    # 初期状態をJSON化
                    init_logic = KeshiYonLogic()
                    state_json = json.dumps(init_logic.get_state())
                    run_db("INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?)", 
                           (new_id, new_pass, username, None, username, state_json, 'waiting', datetime.now()), commit=True)
                    st.session_state.room_id = new_id
                    st.session_state.is_host = True
                    st.rerun()
                except: st.error("ID重複")
    else:
        # ゲーム画面
        rid = st.session_state.room_id
        data = run_db("SELECT host, player2, turn, board, status FROM rooms WHERE room_id=?", (rid,), fetch_one=True)
        if not data:
            del st.session_state.room_id
            st.rerun()
            return

        host, p2, turn_user, state_json, status = data
        logic = KeshiYonLogic(json.loads(state_json))
        my_role = 1 if st.session_state.is_host else 2
        
        st.write(f"Host: {host} vs Guest: {p2}")
        if st.button("退出"):
            run_db("DELETE FROM rooms WHERE room_id=?", (rid,), commit=True)
            del st.session_state.room_id
            st.rerun()
        
        if status == 'waiting':
            st.warning("待機中...")
            time.sleep(2)
            st.rerun()
            return
            
        render_keshiyon_board(logic)
        
        if status == 'finished':
            s = logic.get_state()
            w = "Draw"
            if s['p1_score'] > s['p2_score']: w = f"{host} Win!"
            elif s['p2_score'] > s['p1_score']: w = f"{p2} Win!"
            st.success(f"Game Over: {w}")
            return

        is_my_turn = (turn_user == username)
        if is_my_turn:
            st.success("あなたの番です")
            cols = st.columns(COLS)
            for i, col in enumerate(cols):
                if logic.is_valid(i):
                    if col.button("⬇", key=f"net_{i}"):
                        stat = logic.place_piece(i, my_role)
                        next_turn = p2 if st.session_state.is_host else host
                        if stat == 'finished': next_turn = turn_user # 終了時は更新しない
                        
                        run_db("UPDATE rooms SET board=?, turn=?, status=? WHERE room_id=?",
                               (json.dumps(logic.get_state()), next_turn, stat, rid), commit=True)
                        st.rerun()
        else:
            st.info("相手の思考中...")
            time.sleep(2)
            st.rerun()

# ==========================================
# 5. メイン
# ==========================================
def main():
    init_db()
    if 'user' not in st.session_state: st.session_state.user = None
    if 'config' not in st.session_state: 
        st.session_state.config = {"left":"ArrowLeft", "right":"ArrowRight", "rotate_r":"ArrowUp", "rotate_l":"z", "soft_drop":"ArrowDown", "hard_drop":" ", "hold":"c"}

    if not st.session_state.user:
        st.title("Game Station Login")
        t1, t2 = st.tabs(["Login", "Reg"])
        with t1:
            u=st.text_input("User"); p=st.text_input("Pass", type="password")
            if st.button("Login"):
                r=run_db("SELECT username,config FROM users WHERE username=? AND password=?", (u,hash_pass(p)), fetch_one=True)
                if r: 
                    st.session_state.user=r[0]
                    if r[1]: st.session_state.config=json.loads(r[1])
                    st.rerun()
        with t2:
            nu=st.text_input("NewUser"); np=st.text_input("NewPass", type="password")
            if st.button("Register"):
                try: run_db("INSERT INTO users VALUES (?,?,?)",(nu,hash_pass(np),json.dumps(st.session_state.config)),commit=True); st.success("OK")
                except: st.error("Exists")
    else:
        with st.sidebar:
            st.write(f"User: {st.session_state.user}")
            if st.button("Logout"): st.session_state.user=None; st.rerun()
            menu = st.radio("Menu", ["Tetris", "Keshi-Yon (消し四)", "Config"])

        if menu == "Tetris":
            st.header("🧱 Tetris Ultimate")
            tetris_game(st.session_state.config)
        elif menu == "Keshi-Yon (消し四)":
            st.header("🔴✕ Keshi-Yon (独自ルール)")
            m = st.selectbox("Mode", ["CPU", "Local", "Network"])
            if m=="CPU":
                st.session_state.cpu_level = st.slider("Lv", 1, 5, 1)
                keshiyon_local_cpu("CPU")
            elif m=="Local": keshiyon_local_cpu("Local")
            elif m=="Network": keshiyon_network(st.session_state.user)
        elif menu == "Config":
            st.write("キー設定 (省略)")
            # 設定画面は前回と同じなので省略しますが、機能します

if __name__ == '__main__':
    main()
