import sys
import ctypes
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass
import subprocess
import threading
import queue
import time
import math
import os
import json
import shutil

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import websocket
except ImportError:
    websocket = None

# ==================== BẬT CHẾ ĐỘ NÉT CAO (HIGH-DPI) ====================
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
# =======================================================================

ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")  


class MirroredCTkProgressBar(ctk.CTkProgressBar):
    """CTkProgressBar dùng chính DrawEngine của CustomTkinter nhưng tiến từ phải sang trái."""
    def _draw(self, no_color_updates=False):
        # Chỉ gọi phần nền của CTkBaseClass để cập nhật kích thước/màu,
        # sau đó dùng DrawEngine với khoảng progress [1-ratio, 1].
        CTkBaseClass._draw(self, no_color_updates)

        orientation = "w" if self._orientation.lower() == "horizontal" else "s"

        if self._mode == "determinate":
            start = 1.0 - self._determinate_value
            end = 1.0
        else:
            progress_value = (math.sin(self._indeterminate_value * math.pi / 40) + 1) / 2
            start = max(0.0, progress_value - self._indeterminate_width / 2)
            end = min(1.0, progress_value + self._indeterminate_width / 2)

        requires_recoloring = self._draw_engine.draw_rounded_progress_bar_with_border(
            self._apply_widget_scaling(self._current_width),
            self._apply_widget_scaling(self._current_height),
            self._apply_widget_scaling(self._corner_radius),
            self._apply_widget_scaling(self._border_width),
            start, end, orientation
        )

        if no_color_updates is False or requires_recoloring:
            self._canvas.configure(bg=self._apply_appearance_mode(self._bg_color))
            self._canvas.itemconfig(
                "border_parts",
                fill=self._apply_appearance_mode(self._border_color),
                outline=self._apply_appearance_mode(self._border_color)
            )
            self._canvas.itemconfig(
                "inner_parts",
                fill=self._apply_appearance_mode(self._fg_color),
                outline=self._apply_appearance_mode(self._fg_color)
            )
            self._canvas.itemconfig(
                "progress_parts",
                fill=self._apply_appearance_mode(self._progress_color),
                outline=self._apply_appearance_mode(self._progress_color)
            )

winsound = None
if sys.platform == "win32":
    try: 
        import winsound
    except ImportError: 
        pass

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== CẤU HÌNH SERVER ONLINE ====================
SERVER_URL = "wss://caroultra-ai-online.onrender.com" 
# ================================================================

# ==================== ENGINE PATHS ====================
# Windows: Rapfi (Tiêu chuẩn) + AlphaGomoku (Chặn 2 đầu / Caro)
# macOS  : chỉ Rapfi
if sys.platform == "win32":
    ENGINE_FILENAME_STANDARD = "pbrain-rapfi-windows-avx2.exe"
    ENGINE_FILENAME_CARO = "pbrain-alphagomoku-caro.exe"
else:
    ENGINE_FILENAME_STANDARD = "pbrain-rapfi-mac"
    ENGINE_FILENAME_CARO = "pbrain-rapfi-mac"

ENGINE_PATH_STANDARD = os.path.join(BASE_DIR, ENGINE_FILENAME_STANDARD)
ENGINE_PATH_CARO = os.path.join(BASE_DIR, ENGINE_FILENAME_CARO)
ENGINE_PATH = ENGINE_PATH_STANDARD
ENGINE_FILENAME = ENGINE_FILENAME_STANDARD

def get_engine_path_and_rule(standard_rule: bool):
    """Trả về (path, rule_code). Windows + Chặn 2 đầu → AlphaGomoku (rule 8)."""
    if standard_rule or sys.platform != "win32":
        return ENGINE_PATH_STANDARD, 1
    if os.path.isfile(ENGINE_PATH_CARO):
        return ENGINE_PATH_CARO, 8  # Caro
    return ENGINE_PATH_STANDARD, 0

TING_SOUND_PATH = os.path.join(BASE_DIR, "sounds", "ting.wav")
VICTORY_SOUND_PATH = os.path.join(BASE_DIR, "sounds", "victory.wav")
IDEA_SOUND_PATH = os.path.join(BASE_DIR, "sounds", "idea.wav")
TIME_SOUND_PATH = os.path.join(BASE_DIR, "sounds", "time.wav")
ICON_ICO_PATH = os.path.join(BASE_DIR, "Ultra.ico")
ICON_ICNS_PATH = os.path.join(BASE_DIR, "Ultra.icns")

# ==================== MAC: CHUẨN BỊ ENGINE ====================
def _prepare_mac_engine(path: str) -> None:
    """Tự chmod + gỡ quarantine để macOS không chặn engine."""
    if sys.platform != "darwin" or not path or not os.path.exists(path):
        return
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass
    try:
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:
        pass
    try:
        subprocess.run(
            ["xattr", "-cr", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:
        pass

_prepare_mac_engine(ENGINE_PATH_STANDARD)
_prepare_mac_engine(ENGINE_PATH_CARO)
# ==============================================================

if sys.platform == "win32":
    app_data_dir = os.path.join(os.environ.get("APPDATA", BASE_DIR), "XOUltraAI")
elif sys.platform == "darwin":
    app_data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "XOUltraAI")
else:
    app_data_dir = BASE_DIR

os.makedirs(app_data_dir, exist_ok=True)
CONFIG_PATH = os.path.join(app_data_dir, "xoultra_ai_settings.json")

DEFAULT_DIFF = {"Cao thủ (0.2s)": 200, "Đỉnh cao (5s)": 5000, "Siêu cấp (12s)": 12000, "Vô cực (20s)": 20000}
DEFAULT_LANG = {
    "mode": "Chế độ:", "mode_ai": "Ultra-AI", "mode_2p": "2 Người", "mode_ai_vs_ai": "AI vs AI", "mode_online": "Online", "symbol": "Phe:", 
    "symbol_x": "X", "symbol_o": "O", "board": "Bàn cờ:", "diff": "Độ khó:", "diff_x": "Độ khó X:", "diff_o": "Độ khó O:", "rule": "Luật:", "time_limit": "Thời Gian:",
    "new_game": "VÁN MỚI (F5)", "undo": "LÙI (1)", "redo": "TIẾN (2)", "hint": "GỢI Ý (H)",
    "pause": "⏸ DỪNG (SPACE)", "start": "▶ BẮT ĐẦU (SPACE)", "resume": "▶ TIẾP TỤC (SPACE)", "ai_match_paused": "⏸️ Trận đấu đang tạm dừng",
    "init_status": "", "turn_your": "Lượt của bạn", "turn_2p": "Lượt của ({})", "turn_ai_vs_ai": "AI vs AI: Lượt của ({})", 
    "piece_x_status": "X", "piece_o_status": "O", "ai_thinking": "Ultra-AI đang suy nghĩ", "ai_taking_over": "Ultra-AI đang tiếp quản và suy nghĩ",
    "ai_rethinking": "Ultra-AI đang suy nghĩ lại", "hint_calculating": "💡 Ultra-AI đang tìm nước đi gợi ý",
    "hint_result": "💡 Đã tìm thấy nước đi gợi ý tốt nhất trên bàn cờ!", "hint_err": "Không thể tính toán gợi ý lúc này.",
    "win_msg": "NGƯỜI CHƠI ({}) THẮNG!", "ai_win_msg": "ULTRA-AI ({}) THẮNG!", "ai_vs_ai_win": "AI ({}) GIÀNH CHIẾN THẮNG!",
    "timeout_msg": "HẾT GIỜ! NGƯỜI CHƠI ({}) THẮNG DO ĐỐI THỦ CẠN THỜI GIAN!", "resgin_status": "ULTRA-AI ({}) XIN THUA!", 
    "err_title": "Lỗi", "limit_warn": "Kích thước bàn cờ hỗ trợ tối đa là 20x20!", "warning_title": "Thông báo", "rules_list": ["Tiêu chuẩn", "Chặn 2 đầu"],
    "sound_on": "🔊 Bật", "sound_off": "🔇 Tắt", "ai_ready": "Sẵn sàng! Bấm BẮT ĐẦU để AI đấu.", "unlimited_time": "⏱ Không giới hạn thời gian",
    "block_rule_warn": "Luật Chặn 2 đầu dùng engine AlphaGomoku (Caro). Chế độ AI chỉ hỗ trợ bàn 15×15.",
    "engine_err": "Lỗi khởi động engine", "ai_not_resp": "Ultra-AI chưa trả nước đi", "ai_err": "Lỗi AI", "sync_err": "Lỗi đồng bộ AI",
    "undo_msg": "Đã LÙI 1 BƯỚC. ", "redo_msg": "Đã TIẾN 1 BƯỚC. "
}

TRANSLATIONS_PATH = os.path.join(BASE_DIR, "translations.json")
try:
    with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
        trans_data = json.load(f)
        DIFFICULTY = trans_data.get("DIFFICULTY", {"VI": DEFAULT_DIFF})
        LANG = trans_data.get("LANG", {"VI": DEFAULT_LANG})
except Exception:
    DIFFICULTY, LANG = {"VI": DEFAULT_DIFF}, {"VI": DEFAULT_LANG}

if sys.platform == "darwin":
    try:
        if os.path.exists(ENGINE_PATH):
            os.chmod(ENGINE_PATH, 0o755)
    except Exception:
        pass

EMPTY, HUMAN, AI = 0, 1, 2

# Các giá trị dùng chung để tránh lặp literal ở nhiều nơi.
GAME_MODES = ("Ultra-AI", "2 Người", "AI vs AI", "Online")
BOARD_SIZES = ("15x15", "20x20")


class UltraAIEngine:
    def __init__(self, path, board_size=20, time_turn=50, rule=0):
        self.path = path
        self.board_size = board_size
        self.time_turn = time_turn
        self.rule = rule
        self.is_alpha = (rule == 8)  # AlphaGomoku Caro
        self.proc = None
        self.running = False
        self.q = queue.Queue()

    def start(self):
        if not os.path.exists(self.path): 
            raise FileNotFoundError(f"Không tìm thấy engine tại: {self.path}")

        if sys.platform == "darwin":
            try:
                os.chmod(self.path, 0o755)
            except Exception:
                pass
            try:
                subprocess.run(
                    ["xattr", "-d", "com.apple.quarantine", self.path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            except Exception:
                pass
            
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            [self.path], 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1, 
            creationflags=creation_flags
        )
        self.running = True
        threading.Thread(target=self._reader, daemon=True).start()
        
        self.send(f"START {self.board_size}")
        time.sleep(0.1)
        for _ in range(4):
            resp = self.get_response(timeout=0.3)
            if resp and "OK" in resp.upper(): 
                break

        # Rapfi: nhiều thread giúp α-β. AlphaGomoku KHÔNG hỗ trợ INFO thread_num
        # (log: UNKNOWN 'info thread_num N') — chỉ gửi cho Rapfi.
        cpu = os.cpu_count() or 8
        self.send(f"INFO timeout_turn {self.time_turn}")
        self.send(f"INFO rule {self.rule}")
        self.send("INFO max_memory 4294967296")
        if not self.is_alpha:
            thread_num = max(14, min(cpu, 32))
            self.send(f"INFO thread_num {thread_num}")
        self.send("INFO game_type 0")  # 0 = đối thủ người
        self.send("INFO time_left 99999999")
        # Alpha cold-start NN chậm; cho thêm chút thời gian ổn định trước nước đầu
        time.sleep(0.08 if self.is_alpha else 0.05)

    def _reader(self):
        while self.running and self.proc and self.proc.poll() is None:
            try:
                line = self.proc.stdout.readline().strip()
                if line:
                    print(f"[ENGINE] {line}")  # log ra CMD để debug
                    self.q.put(line)
            except (ValueError, OSError):
                break

    def send(self, cmd):
        if self.proc and self.proc.poll() is None:
            try: 
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError): 
                pass

    def send_time_left(self, ms=None):
        """Protocol khuyến nghị gửi time_left trước mỗi TURN/BEGIN/BOARD.
        Giúp Alpha (time manager cải tiến) phân bổ thời gian đúng ở mức ngắn."""
        left = int(ms if ms is not None else max(self.time_turn * 40, 99999999))
        self.send(f"INFO time_left {left}")

    def get_response(self, timeout=6):
        try: 
            return self.q.get(timeout=timeout)
        except queue.Empty: 
            return None

    def stop(self):
        self.running = False
        if self.proc:
            try: 
                self.send("END")
                self.proc.terminate()
            except (OSError, ValueError): 
                pass
            self.proc = None

class XOUltraAI:
    def __init__(self, root):
        self.root = root
        self.root.title("XOUltra-AI")
        
        # === THÊM ĐOẠN NÀY ĐỂ CĂN GIỮA MÀN HÌNH KHI MỞ APP ===
        window_width = 980
        window_height = 1280
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_crd = int((screen_width / 2) - (window_width / 2))
        y_crd = int((screen_height / 2) - (window_height / 2))
        self.root.geometry(f"{window_width}x{window_height}+{x_crd}+{y_crd}")
        # ====================================================

        self.root.minsize(900, 950)
        try:
            if sys.platform == "win32" and os.path.exists(ICON_ICO_PATH):
                self.root.iconbitmap(ICON_ICO_PATH)
            elif sys.platform == "darwin" and os.path.exists(ICON_ICNS_PATH):
                self.root.iconbitmap(ICON_ICNS_PATH)
        except Exception:
            pass

        self.board_size = 20
        self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
        
        self.game_over = self.is_ai_thinking = self.engine_synced = False
        self.is_ai_match_paused = True
        
        self.last_move = self.hover_cell = self.hint_cell = None
        self.winning_cells = []
        self.ghost_winning_cells = []  # đường thắng còn hiện mờ khi LÙI xem lại
        self.history = []
        self.redo_stack = []
        
        self.engine = None
        self._ai_generation = 0
        self.current_turn = HUMAN
        self.sound_enabled = True
        
        self.timer_job = self.dot_animation_job = None
        self.dot_count = 0
        self.current_thinking_msg_key = ""
        self.time_remaining = {"X": 0, "O": 0}
        
        self.turn_time_limit = 35
        self.turn_time_remaining = {"X": 35, "O": 35}
        
        self.turn_timer_job = None
        self.holding_action = None

        # Timer chính xác: dùng monotonic/deadline thay vì -= 1 theo after().
        # after() chỉ là lịch gọi lại UI, không phải đồng hồ chính xác.
        self._turn_deadline_mono = None
        self._online_clock_offset = 0.0
        self._match_precise_remaining = {"X": 0.0, "O": 0.0}
        self._match_deadline_mono = None
        self._match_active_symbol = None
        
        self._last_pause_sig = self._last_btn_new_sig = None
        self._current_status_data = {}

        self.ws = None
        self._ws_generation = 0
        self.is_online_connected = False
        self.is_online_turn = False
        self.online_symbol = None
        self.opponent_name = ""  # rỗng = hiện t("default_opp") theo ngôn ngữ
        self.score_me = 0
        self.score_opp = 0
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        # Online draw-offer / accept flow (cầu hòa)
        self._i_resigned = False
        self._opp_resigned = False
        self._resign_name = ""
        self._my_resign_count = 0  # số lần đã gửi cầu hòa trong ván
        self._resign_offer_job = None  # local countdown cancel

        self.lang_var = ctk.StringVar(value="VI")
        self.game_mode_var = ctk.StringVar(value="Ultra-AI")
        self.player_symbol_var = ctk.StringVar(value="X")
        self.auto_rotate_var = ctk.BooleanVar(value=True)
        self.difficulty_var = ctk.StringVar(value="Cao thủ (0.2s)")
        self.difficulty_x_var = ctk.StringVar(value="Cao thủ (0.2s)")
        self.difficulty_o_var = ctk.StringVar(value="Cao thủ (0.2s)")
        self.rule_var = ctk.StringVar(value="Tiêu chuẩn")
        self.time_minutes_var = ctk.StringVar(value="1")
        self.ui_style_var = ctk.StringVar(value="Cổ điển")
        self.board_size_var = ctk.StringVar(value="20x20")
        self.theme_var = ctk.StringVar(value="Sáng")
        self.room_id_var = ctk.StringVar(value="")
        self.player_name_var = ctk.StringVar(value="Tùng")
        
        # Bật tính năng theo dõi khi gõ phím để giới hạn 16 ký tự
        self.player_name_var.trace_add("write", self.limit_name_length)

        self.load_settings()
        self.load_icons()
        self.board_margin = 22
        self.cell_size = 48
        self._resize_timer = None
        
        self.create_ui()
        self.new_game()
        self.change_theme_init()
        self.change_ui_style_init()
        
        self._bind_shortcuts()

        # Đánh thức Render ở background ngay khi app mở để lần vào phòng đầu tiên nhanh hơn.
        # Không chặn giao diện và không tạo/join phòng thật.
        self.root.after(250, self.warmup_online_server)

    @property
    def is_dark_mode(self):
        return self.theme_var.get() in ["Tối", "Dark"]

    @property
    def is_standard_rule(self):
        return self.rule_to_canonical(self.rule_var.get()) == "standard"

    @staticmethod
    def rule_to_canonical(rule_text):
        """Chuẩn hóa luật về mã trung lập (không phụ thuộc ngôn ngữ UI)."""
        r = str(rule_text or "").strip().lower()
        if r in ("block_both_ends", "block"):
            return "block_both_ends"
        if "block" in r or "chặn 2" in r or "chan 2" in r:
            return "block_both_ends"
        return "standard"

    def rule_to_display(self, rule_text):
        """Đổi mã/chuỗi luật bất kỳ thành nhãn theo ngôn ngữ hiện tại."""
        rules = self.t("rules_list")
        if not isinstance(rules, list) or len(rules) < 2:
            rules = ["Tiêu chuẩn", "Chặn 2 đầu"]
        return rules[1] if self.rule_to_canonical(rule_text) == "block_both_ends" else rules[0]

    def _should_force_15x15_for_caro_ai(self):
        """True khi đang ở chế độ có AI + luật Chặn 2 đầu (AlphaGomoku chỉ hỗ trợ 15x15)."""
        mode = self.game_mode_var.get()
        if mode not in ("Ultra-AI", "AI vs AI"):
            return False
        return not self.is_standard_rule

    def _enforce_board_for_caro_ai(self):
        """Nếu AI + Chặn 2 đầu mà bàn đang 20x20 → tự chuyển về 15x15 và new_game."""
        if not self._should_force_15x15_for_caro_ai():
            return
        if self.board_size_var.get() == "20x20":
            self.board_size_var.set("15x15")
            self.save_settings()
            # Chỉ new_game khi không phải đang Online (Online đã xử lý riêng)
            if self.game_mode_var.get() != "Online":
                self.new_game()

    @staticmethod
    def opposite_symbol(symbol):
        """Trả về quân đối diện của X/O."""
        return "O" if symbol == "X" else "X"

    def symbol_color(self, symbol):
        """Màu hiển thị thống nhất cho X/O theo theme hiện tại."""
        if symbol == "X":
            return "#22d3ee" if self.is_dark_mode else "#1d4ed8"
        return "#ef4444" if self.is_dark_mode else "#b91c1c"

    def cancel_after(self, attr_name):
        """Hủy một Tkinter after-job an toàn và xóa reference."""
        job = getattr(self, attr_name, None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            setattr(self, attr_name, None)

    def load_icons(self):
        """Load icon ảnh cho 4 nút góc phải. Fallback về emoji nếu thiếu file hoặc thiếu PIL.

        Ưu tiên thư mục icons/ cho gọn:
          1) BASE_DIR/icons/
          2) cwd/icons/
          3) BASE_DIR/  (cùng thư mục script — fallback)
          4) cwd/
        Chấp nhận cả tên file có khoảng trắng / viết hoa (style on.png, Style off.png...).
        """
        self.icon_lang_vi = self.icon_lang_en = None
        self.icon_sound_on = self.icon_sound_off = None
        self.icon_theme_light = self.icon_theme_dark = None
        self.icon_style_on = self.icon_style_off = None
        self.icon_swap = None
        self._use_image_icons = False
        self._piece_src = {
            "X": {"light": None, "dark": None},
            "O": {"light": None, "dark": None},
        }
        self._piece_photo_cache = {}

        if Image is None:
            return

        # Kích thước hiển thị trên nút 36x36 (giữ nét khi scale HiDPI)
        size = (32, 32)
        cwd = os.getcwd()
        # Ưu tiên icons/ trước, rồi mới đến thư mục ngoài
        search_dirs = [
            os.path.join(BASE_DIR, "icons"),
            os.path.join(cwd, "icons"),
            BASE_DIR,
            cwd,
        ]
        seen = set()
        unique_dirs = []
        for d in search_dirs:
            try:
                key = os.path.normcase(os.path.abspath(d))
            except Exception:
                key = d
            if key not in seen:
                seen.add(key)
                unique_dirs.append(d)

        def _load(*names):
            """Thử lần lượt nhiều tên file (có/không khoảng trắng, hoa/thường).
            Resize về đúng size vuông để 4 nút nhìn đều nhau."""
            for d in unique_dirs:
                for name in names:
                    path = os.path.join(d, name)
                    if not os.path.isfile(path):
                        continue
                    try:
                        img = Image.open(path).convert("RGBA")
                        # Chuẩn hóa về vuông, giữ tỉ lệ, căn giữa trên nền trong suốt
                        w, h = img.size
                        side = max(w, h)
                        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                        canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
                        canvas = canvas.resize(size, Image.Resampling.LANCZOS)
                        return ctk.CTkImage(
                            light_image=canvas,
                            dark_image=canvas.copy(),
                            size=size,
                        )
                    except Exception:
                        continue
            return None

        self.icon_lang_vi = _load("lang_vi.png", "lang-vi.png", "Lang_vi.png")
        self.icon_lang_en = _load("lang_en.png", "lang-en.png", "Lang_en.png")
        self.icon_sound_on = _load("sound_on.png", "sound-on.png", "Sound_on.png")
        self.icon_sound_off = _load("sound_off.png", "sound-off.png", "Sound_off.png")
        self.icon_theme_light = _load("theme_light.png", "theme-light.png", "Theme_light.png")
        self.icon_theme_dark = _load("theme_dark.png", "theme-dark.png", "Theme_dark.png")
        self.icon_style_on = _load(
            "style_on.png", "style on.png", "style-on.png",
            "Style_on.png", "Style on.png",
        )
        self.icon_style_off = _load(
            "style_off.png", "style off.png", "style-off.png",
            "Style_off.png", "Style off.png",
        )
        # Icon đồng hồ cho nhãn Thời gian / Time (thay chữ)
        self.icon_time = _load(
            "Time.png", "time.png", "time_limit.png", "Time.png",
        )
        send_size = (26, 26)
        def _load_send(*names):
            for d in unique_dirs:
                for name in names:
                    path = os.path.join(d, name)
                    if not os.path.isfile(path):
                        continue
                    try:
                        img = Image.open(path).convert("RGBA")
                        w, h = img.size
                        side = max(w, h)
                        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                        canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
                        canvas = canvas.resize(send_size, Image.Resampling.LANCZOS)
                        return ctk.CTkImage(
                            light_image=canvas,
                            dark_image=canvas.copy(),
                            size=send_size,
                        )
                    except Exception:
                        continue
            return None

        self.icon_send = _load_send("send.png", "Send.png")

        # Icon nút đổi độ khó AI (⇄) — dùng Swap.png, chỉ giữ mũi tên trắng trên nền trong suốt
        swap_size = (22, 22)
        def _load_swap(*names):
            for d in unique_dirs:
                for name in names:
                    path = os.path.join(d, name)
                    if not os.path.isfile(path):
                        continue
                    try:
                        img = Image.open(path).convert("RGBA")
                        # Loại bỏ nền tím: chỉ giữ pixel trắng/sáng (mũi tên)
                        pixels = img.load()
                        w, h = img.size
                        for y in range(h):
                            for x in range(w):
                                r, g, b, a = pixels[x, y]
                                if a > 0 and not (r > 180 and g > 180 and b > 180):
                                    pixels[x, y] = (0, 0, 0, 0)
                        side = max(w, h)
                        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                        canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
                        canvas = canvas.resize(swap_size, Image.Resampling.LANCZOS)
                        return ctk.CTkImage(
                            light_image=canvas,
                            dark_image=canvas.copy(),
                            size=swap_size,
                        )
                    except Exception:
                        continue
            return None

        self.icon_swap = _load_swap(
            "Swap.png", "swap.png", "swap_icon.png",
            "icons/Swap.png", "icons/swap.png",
        )

        # Bật chế độ ảnh khi load đủ cả 8 icon
        loaded = [
            self.icon_lang_vi, self.icon_lang_en,
            self.icon_sound_on, self.icon_sound_off,
            self.icon_theme_light, self.icon_theme_dark,
            self.icon_style_on, self.icon_style_off,
        ]
        self._use_image_icons = all(loaded)

        # Ảnh quân cờ (chỉ dùng ở kiểu Hiện đại): X = xanh, O = đỏ
        # Hỗ trợ biến thể light/dark theo theme (blue light/dark, red light/dark).
        self._piece_src = {
            "X": {"light": None, "dark": None},
            "O": {"light": None, "dark": None},
        }
        self._piece_photo_cache = {}  # (sym, theme, px) -> PhotoImage
        if Image is not None and ImageTk is not None:
            def _load_piece(*names):
                for d in unique_dirs:
                    for name in names:
                        path = os.path.join(d, name)
                        if not os.path.isfile(path):
                            continue
                        try:
                            return Image.open(path).convert("RGBA")
                        except Exception:
                            continue
                return None

            # Ưu tiên tên viết thường + khoảng trắng (đúng file bạn vừa thêm)
            self._piece_src["X"]["light"] = _load_piece(
                "blue light.png", "blue_light.png", "blue-light.png",
                "piece_x_light.png", "piece_x.png", "blue.png", "Blue.png", "piece_blue.png",
            )
            self._piece_src["X"]["dark"] = _load_piece(
                "blue dark.png", "blue_dark.png", "blue-dark.png",
                "piece_x_dark.png", "piece_x.png", "blue.png", "Blue.png", "piece_blue.png",
            )
            self._piece_src["O"]["light"] = _load_piece(
                "red light.png", "red_light.png", "red-light.png",
                "piece_o_light.png", "piece_o.png", "red.png", "Red.png", "piece_red.png",
            )
            self._piece_src["O"]["dark"] = _load_piece(
                "red dark.png", "red_dark.png", "red-dark.png",
                "piece_o_dark.png", "piece_o.png", "red.png", "Red.png", "piece_red.png",
            )

    def _get_piece_photo(self, symbol, pixel_size, ghost=False):
        """PhotoImage quân cờ đã resize; cache theo (symbol, theme, size[, ghost]).
        ghost=True → alpha ~15% để hiện rất mờ các nước đã LÙI (xem lại ván)."""
        if Image is None or ImageTk is None:
            return None
        src_map = getattr(self, "_piece_src", {}).get(symbol)
        if not src_map:
            return None
        theme_key = "dark" if self.is_dark_mode else "light"
        src = src_map.get(theme_key) or src_map.get("light") or src_map.get("dark")
        if src is None:
            return None
        px = max(8, int(pixel_size))
        key = (symbol, theme_key, px, "ghost" if ghost else "solid")
        cache = getattr(self, "_piece_photo_cache", None)
        if cache is None:
            self._piece_photo_cache = {}
            cache = self._piece_photo_cache
        if key not in cache:
            try:
                img = src.resize((px, px), Image.Resampling.LANCZOS)
                if ghost:
                    # Giảm alpha để quân “ma” mờ, vẫn phân biệt X/O
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    alpha = img.split()[3]
                    alpha = alpha.point(lambda a: int(a * 0.15))
                    img.putalpha(alpha)
                cache[key] = ImageTk.PhotoImage(img)
            except Exception:
                return None
        return cache[key]

    def _bind_shortcuts(self):
        self.root.bind("1", self.undo_move)
        self.root.bind("2", self.redo_move)
        self.root.bind("<Configure>", self.on_window_resize)
        self.root.bind("<F5>", self.request_new_game)
        self.root.bind("h", self.get_hint)
        self.root.bind("H", self.get_hint)
        self.root.bind("<space>", self.toggle_pause_resume)
        self.root.bind("<Return>", self.activate_chat_focus)

    def start_move(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def do_move(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def activate_chat_focus(self, event=None):
        if self.game_mode_var.get() == "Online" and hasattr(self, "chat_entry"):
            self.chat_entry.focus_set()

    def _transition_with_fade(self, action_callback):
        """Chuyển theme mượt bằng lớp phủ + easing, tránh cảm giác nhấp nháy.

        Cho phép bấm lại ngay: nếu đang fade thì hủy overlay cũ và bắt đầu
        chuyển mới, không bị khóa đến hết animation.
        """
        # Hủy transition đang chạy (nếu có) để người dùng đổi theme liền tay.
        old_overlay = getattr(self, "_theme_overlay", None)
        if old_overlay is not None:
            try:
                old_overlay.destroy()
            except Exception:
                pass
            self._theme_overlay = None
        self._theme_transitioning = True

        current_bg = "#0b141d" if self.is_dark_mode else "#F5F1E8"
        overlay = tk.Toplevel(self.root)
        self._theme_overlay = overlay
        overlay.overrideredirect(True)
        self.root.update_idletasks()
        geo = (
            f"{self.root.winfo_width()}x{self.root.winfo_height()}"
            f"+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}"
        )
        overlay.geometry(geo)
        overlay.configure(bg=current_bg)
        overlay.attributes("-alpha", 1.0)
        overlay.transient(self.root)
        if sys.platform != "win32":
            overlay.attributes("-topmost", True)

        # Giữ lớp phủ ở trên cùng trong suốt quá trình cập nhật UI.
        try:
            overlay.lift()
        except Exception:
            pass

        try:
            # Toàn bộ thay đổi màu diễn ra khi UI đang được che,
            # nên người dùng không thấy từng widget đổi màu riêng lẻ.
            action_callback()
            self.root.update_idletasks()

            duration_ms = 280
            interval_ms = 12
            steps = max(1, duration_ms // interval_ms)
            step = 0

            def fade_out():
                nonlocal step
                try:
                    if getattr(self, "_theme_overlay", None) is not overlay:
                        return  # Đã bị thay bằng transition mới
                    step += 1
                    progress = min(1.0, step / steps)

                    # Smoothstep: chậm ở đầu/cuối, nhanh ở giữa.
                    eased = progress * progress * (3.0 - 2.0 * progress)
                    alpha = max(0.0, 1.0 - eased)
                    overlay.attributes("-alpha", alpha)

                    if progress < 1.0:
                        self.root.after(interval_ms, fade_out)
                    else:
                        try:
                            overlay.destroy()
                        except Exception:
                            pass
                        if getattr(self, "_theme_overlay", None) is overlay:
                            self._theme_overlay = None
                            self._theme_transitioning = False
                except Exception:
                    try:
                        overlay.destroy()
                    except Exception:
                        pass
                    if getattr(self, "_theme_overlay", None) is overlay:
                        self._theme_overlay = None
                        self._theme_transitioning = False

            fade_out()
        except Exception:
            try:
                overlay.destroy()
            except Exception:
                pass
            if getattr(self, "_theme_overlay", None) is overlay:
                self._theme_overlay = None
            self._theme_transitioning = False
            raise

    def t(self, key): 
        return LANG.get(self.lang_var.get(), LANG.get("VI", {})).get(key, key)
    
    def _status_text_color(self, color):
        """Tăng tương phản chữ status theo theme.

        Hỗ trợ cả mã hex đơn và tuple (light, dark).
        Màu '#notice' → cam đậm trên sáng, vàng sáng trên tối (nổi rõ).
        """
        if color is None:
            return color
        # Tuple (light, dark) của CustomTkinter
        if isinstance(color, (tuple, list)) and len(color) >= 2:
            return (color[0], color[1])

        key = str(color).lower()
        # Màu thông báo đối thủ đổi cài đặt — nổi trên cả 2 theme
        if key in ("#notice", "notice"):
            return ("#c2410c", "#fbbf24")  # cam đậm / vàng sáng

        if self.is_dark_mode:
            # Dark: làm sáng một số màu amber cho dễ đọc
            dark_boost = {
                "#f39c12": "#fbbf24",
            }
            return dark_boost.get(key, color)

        light_status_colors = {
            "#3498db": "#1d4ed8",  # xanh dương đậm
            "#e74c3c": "#b91c1c",  # đỏ đậm
            "#f39c12": "#c2410c",  # cam đậm (nổi hơn #9A5A13 cũ)
            "#ef4444": "#b91c1c",
            "#2ecc71": "#166534",
        }
        return light_status_colors.get(key, color)

    def display_status(self, key, color=None, format_args=None, prefix_key=None, raw_text=False):
        if raw_text:
            text = key
            self._current_status_data = {"type": "raw", "text": text, "color": color}
        else:
            self._current_status_data = {"type": "static", "key": key, "color": color, "format_args": format_args or [], "prefix_key": prefix_key}
            text = self.t(key)
            if format_args: text = text.format(*format_args)
            if prefix_key: text = self.t(prefix_key) + text
            
        self.status.configure(text=text, text_color=self._status_text_color(color) if color else ("black", "white"))

    def update_turn_status(self, mode_type=None, symbol=None):
        mode = self.game_mode_var.get()
        if mode == "Online":
            sym_to_check = self.online_symbol if self.is_online_turn else ("O" if self.online_symbol == "X" else "X")
            col = self.symbol_color(sym_to_check)
            my_name = self.player_name_var.get().strip() or self.t("your_name")
            opp_name = self.display_opponent_name()
            turn_name = my_name if self.is_online_turn else opp_name
            
            # CHẾ ĐỘ ONLINE: Chỉ hiện "Lượt của [Tên]" — lưu key để đổi ngôn ngữ được
            self.display_status("online_turn", color=col, format_args=[turn_name])
            self.update_score_display()
            return

        # AI vs AI: Cố định tuyệt đối: X luôn là AI 1, O luôn là AI 2 bất kể ai đi trước
        if mode == "AI vs AI" or mode_type == "ai_vs_ai":
            first_sym = self.player_symbol_var.get() if hasattr(self, 'player_symbol_var') else "X"
            second_sym = "O" if first_sym == "X" else "X"
            
            # Xác định quân đi ở lượt hiện tại
            symbol = first_sym if len(self.history) % 2 == 0 else second_sym
            
            # ĐÍCH XÁC: X là AI 1, O là AI 2
            ai_name = self.t("ai_1") if symbol == "X" else self.t("ai_2")
            text = self.t("turn_ai_vs_ai").format(ai_name)
            col = self.status_color_for_symbol(symbol)
            self.status.configure(text=text, text_color=self._status_text_color(col))
            self._current_status_data = {"type": "turn", "symbol": symbol, "mode_type": "ai_vs_ai"}
            return

        if symbol is None: symbol = self.player_symbol if self.current_turn == HUMAN else self.ai_symbol
        if mode_type is None: mode_type = "2p" if mode == "2 Người" else "ai"
        
        self._current_status_data = {"type": "turn", "symbol": symbol, "mode_type": mode_type}
        status_text = self.turn_status_text(symbol, mode_type=mode_type)
        self.status.configure(text=status_text, text_color=self._status_text_color(self.status_color_for_symbol(symbol)))

    def turn_status_text(self, symbol, mode_type="ai"):
        # CHẾ ĐỘ 2 NGƯỜI
        if mode_type == "2p": 
            return self.t("turn_2p").format(self.t("player_1") if symbol == "X" else self.t("player_2"))
            
        # CHẾ ĐỘ AI VS AI (Dự phòng)
        if mode_type == "ai_vs_ai": 
            return self.t("turn_ai_vs_ai").format(self.t("ai_1") if symbol == "X" else self.t("ai_2"))
            
        # CHẾ ĐỘ ULTRA-AI
        if symbol == getattr(self, "player_symbol", "X"):
            return self.t("turn_your")
        else:
            return self.t("turn_ai").format("Ultra-AI")

    def status_color_for_symbol(self, symbol):
        return self.symbol_color(symbol)

    def start_thinking_animation(self, msg_key, raw_text=False):
        self.current_thinking_msg_key = msg_key
        self.dot_count = 0
        self._is_raw_thinking = raw_text
        self._update_thinking_dots()

    def _update_thinking_dots(self):
        if (not self.is_ai_thinking and not getattr(self, '_is_waiting_online', False)) or self.is_ai_match_paused: return
        dots = '.' * (self.dot_count % 4)
        spaces = ' ' * (3 - len(dots))
        base_text = self.current_thinking_msg_key if getattr(self, '_is_raw_thinking', False) else self.t(self.current_thinking_msg_key)
        self.status.configure(text=f"{base_text}{dots}{spaces}", text_color=self._status_text_color("#ef4444"))
        self.dot_count += 1
        self.dot_animation_job = self.root.after(400, self._update_thinking_dots)

    def stop_thinking_animation(self):
        if self.dot_animation_job:
            self.root.after_cancel(self.dot_animation_job)
            self.dot_animation_job = None
        self._is_waiting_online = False

    def play_sound(self, path):
        if not self.sound_enabled: return
        try:
            if sys.platform == "win32" and winsound: winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            elif sys.platform == "darwin": subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif shutil.which("paplay"): subprocess.Popen(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif shutil.which("aplay"): subprocess.Popen(["aplay", "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, RuntimeError): pass

    def toggle_sound(self):
        self.sound_enabled = not self.sound_enabled
        if getattr(self, "_use_image_icons", False):
            self.btn_sound.configure(image=self.icon_sound_on if self.sound_enabled else self.icon_sound_off, text="")
        else:
            self.btn_sound.configure(text=self.get_sound_btn_icon())
        self.save_settings()

    def update_time_button_colors(self):
        """Đồng bộ màu 2 nút +/- theo theme hiện tại.

        Không dùng màu cố định vì CustomTkinter giữ màu widget qua lần đổi
        appearance mode; nếu không cập nhật lại, +/- có thể bị sai màu sau khi
        chuyển Sáng/Tối.
        """
        if not hasattr(self, "btn_minus") or not hasattr(self, "btn_plus"):
            return
        if self.btn_minus is None or self.btn_plus is None:
            return
        # Quan trọng: nếu nút đang disabled thì KHÔNG được áp lại màu xanh/đỏ
        # khi đổi theme hoặc khi các hàm refresh UI gọi lại hàm này.
        # CustomTkinter vẫn giữ fg_color tùy chỉnh của widget dù state=disabled.
        try:
            minus_state = self.btn_minus.cget("state")
            plus_state = self.btn_plus.cget("state")
        except Exception:
            minus_state = plus_state = "normal"

        if minus_state == "disabled" or plus_state == "disabled":
            is_dark = self.is_dark_mode
            disabled_bg = "#21262d" if is_dark else "#e2e8f0"
            disabled_fg = "#6e7681" if is_dark else "#64748b"
            self.btn_minus.configure(
                state="disabled", fg_color=disabled_bg,
                hover_color=disabled_bg, text_color=disabled_fg
            )
            self.btn_plus.configure(
                state="disabled", fg_color=disabled_bg,
                hover_color=disabled_bg, text_color=disabled_fg
            )
            return

        try:
            val = int(float(self.time_minutes_var.get().strip())) if self.time_minutes_var.get().strip() else 0
        except (ValueError, TypeError):
            val = 0

        if self.is_dark_mode:
            minus_fg = "#dc2626" if val > 0 else "#475569"
            minus_hover = "#ef4444" if val > 0 else "#64748b"
            plus_fg = "#2563eb"
            plus_hover = "#3b82f6"
            text_fg = "white"
        else:
            minus_fg = "#e74c3c" if val > 0 else "#7f8c8d"
            minus_hover = "#c0392b" if val > 0 else "#95a5a6"
            plus_fg = "#2980b9"
            plus_hover = "#3498db"
            text_fg = "white"

        self.btn_minus.configure(fg_color=minus_fg, hover_color=minus_hover, text_color=text_fg)
        self.btn_plus.configure(fg_color=plus_fg, hover_color=plus_hover, text_color=text_fg)

    def update_minus_button_color(self):
        # Giữ tên hàm cũ để các chỗ khác trong code không phải thay đổi.
        self.update_time_button_colors()

    def set_time_controls_enabled(self, enabled: bool):
        """Khóa / mở khóa: thời gian + bàn cờ + luật — dùng cho Online khi đã có quân"""
        if not hasattr(self, "btn_minus"):
            return
        is_dark = self.is_dark_mode
        disabled_bg = "#21262d" if is_dark else "#e2e8f0"
        disabled_fg = "#6e7681" if is_dark else "#64748b"

        state = "normal" if enabled else "disabled"

        # Nút thời gian
        if enabled:
            self.btn_minus.configure(state="normal")
            self.btn_plus.configure(state="normal")
            self.time_entry.configure(state="normal")
            self.update_time_button_colors()
        else:
            self.btn_minus.configure(state="disabled", fg_color=disabled_bg, hover_color=disabled_bg, text_color=disabled_fg)
            self.btn_plus.configure(state="disabled", fg_color=disabled_bg, hover_color=disabled_bg, text_color=disabled_fg)
            self.time_entry.configure(state="disabled")

        # Bàn cờ + Luật
        if hasattr(self, "size_menu"):
            self.size_menu.configure(state=state)
        if hasattr(self, "rule_menu"):
            self.rule_menu.configure(state=state)
        if hasattr(self, "lbl_board"):
            self.lbl_board.configure(text_color=("black", "white") if enabled else "gray")
        if hasattr(self, "lbl_rule"):
            self.lbl_rule.configure(text_color=("black", "white") if enabled else "gray")
        if hasattr(self, "lbl_time_limit"):
            self.lbl_time_limit.configure(text_color=("black", "white") if enabled else "gray")

    def set_online_symbol(self, symbol, auto_rotate=None, refresh=True):
        """Nguồn sự thật duy nhất cho Phe trong Online. Server/client đều đi qua đây."""
        if symbol not in ("X", "O"):
            return
        self.online_symbol = symbol
        self.player_symbol_var.set(symbol)
        self.player_symbol = symbol
        self.ai_symbol = "O" if symbol == "X" else "X"
        if auto_rotate is not None:
            self.auto_rotate_var.set(bool(auto_rotate))
        self._manually_chose_symbol = not bool(self.auto_rotate_var.get())
        if refresh:
            self.update_symbol_auto_button()
            # Phe đổi thì thẻ điểm bên mình/đối thủ cũng phải đổi X/O ngay.
            # update_ui() chỉ vẽ bàn cờ, không cập nhật các label của thẻ điểm.
            self.update_score_display()
            self.update_ui()

    def send_online_settings(self, include_symbol=False):
        """Gửi cấu hình chung. Symbol chỉ gửi khi người dùng thực sự đổi Phe/AUTO."""
        if self.game_mode_var.get() != "Online" or not self.ws or not self.is_online_connected:
            return
        try:
            payload = {
                "type": "update_settings",
                "board_size": self.board_size_var.get(),
                "rule": self.rule_to_canonical(self.rule_var.get()),
                "time_limit": self.get_selected_time_limit_seconds(),
                "auto_rotate": bool(self.auto_rotate_var.get())
            }
            if include_symbol:
                sym = self.online_symbol if self.online_symbol in ("X", "O") else self.player_symbol_var.get()
                if sym in ("X", "O"):
                    payload["symbol"] = sym
            self.ws.send(json.dumps(payload))
        except Exception:
            pass

    def send_online_symbol_update(self):
        """Gửi thay đổi X/O tức thời cho server, kể cả sau khi ván đã kết thúc."""
        if self.game_mode_var.get() != "Online" or not self.ws or not self.is_online_connected:
            return
        sym = self.player_symbol_var.get()
        if sym not in ("X", "O"):
            return
        try:
            self.ws.send(json.dumps({
                "type": "symbol_update",
                "symbol": sym,
                "auto_rotate": bool(self.auto_rotate_var.get())
            }))
        except Exception:
            pass

    def change_time(self, delta):
        # Không cho đổi thời gian khi đang Online và đã có quân cờ
        if self.game_mode_var.get() == "Online" and (self.history or self.game_over):
            return
        try: current = int(float(self.time_minutes_var.get().strip())) if self.time_minutes_var.get().strip() else 0
        except ValueError: current = 0
        new_time = max(0, current + delta)
        self.time_minutes_var.set(str(new_time))
        self.update_minus_button_color()
        self.save_settings()
        self.init_match_timers()

        self.send_online_settings()

    def on_time_entry_change(self, event=None):
        if self.game_mode_var.get() == "Online" and (self.history or self.game_over):
            return
        self.update_minus_button_color()
        self.save_settings()
        self.init_match_timers()

        self.send_online_settings()

    def start_hold_change(self, delta):
        self.change_time(delta); self.holding_action = self.root.after(400, lambda: self.keep_changing(delta))

    def keep_changing(self, delta):
        if self.holding_action:
            self.change_time(delta); self.holding_action = self.root.after(150, lambda: self.keep_changing(delta))

    def stop_hold_change(self, event=None):
        if self.holding_action: self.root.after_cancel(self.holding_action); self.holding_action = None

    def get_selected_time_limit_seconds(self):
        try:
            val = int(float(self.time_minutes_var.get().strip())) if self.time_minutes_var.get().strip() else 0
            return 0 if val <= 0 else val * 60
        except (ValueError, TypeError): return 0

    def init_match_timers(self):
        self.cancel_after("timer_job")
        self.cancel_after("turn_timer_job")

        limit_secs = self.get_selected_time_limit_seconds()
        self.time_remaining = {"X": limit_secs, "O": limit_secs}
        self._match_precise_remaining = {"X": float(limit_secs), "O": float(limit_secs)}
        self._match_deadline_mono = None
        self._match_active_symbol = None
        self.turn_time_remaining = {"X": self.turn_time_limit, "O": self.turn_time_limit}
        self.update_timer_display()
        self.update_turn_bar()

        # Chỉ đếm SAU nước đi đầu — chưa chơi thì không trừ giờ
        if len(self.history) > 0:
            self.start_turn_timer()
            if limit_secs > 0:
                self.run_match_timer()

    def get_current_symbol(self):
        mode = self.game_mode_var.get()
        if mode == "Online":
            # Online: _server_turn_symbol là nguồn sự thật về lượt hiện tại.
            # Không suy ra lượt từ is_online_turn vì trong vài khoảnh khắc
            # đồng bộ (đặc biệt ngay sau khi chọn X/O), cờ này có thể chưa
            # cập nhật kịp và làm viền xanh nhảy sang thẻ đối thủ.
            server_turn = getattr(self, "_server_turn_symbol", None)
            if server_turn in ("X", "O"):
                return server_turn
            return self.online_symbol if self.is_online_turn else ("O" if self.online_symbol == "X" else "X")
        if mode in ("2 Người", "Ultra-AI"):
            return self.player_symbol if self.current_turn == HUMAN else self.ai_symbol
        return "X" if self.current_turn == HUMAN else "O"

    def start_turn_timer(self, symbol=None, turn_secs=None, deadline=None, server_ts=None):
        self.cancel_after("turn_timer_job")
        
        # Kiểm tra xem tổng thời gian ván đấu có được bật hay không (> 0)
        limit_secs = self.get_selected_time_limit_seconds()
        if limit_secs == 0:
            return

        if self.game_mode_var.get() == "Online" and not self.history:
            return

        symbol = symbol or self.get_current_symbol()
        
        # CỐ ĐỊNH thời gian đếm ngược cho mỗi lượt đi là 35 giây
        self.turn_time_limit = int(turn_secs) if turn_secs else 35

        # Online: dùng deadline từ server — chỉ người đang đi đếm, bên kia đứng yên full
        if self.game_mode_var.get() == "Online" and deadline:
            self._turn_deadline = float(deadline)
            # Đồng bộ thời gian server -> local rồi khóa mốc bằng monotonic.
            # server_ts được tạo cùng lúc với deadline nên network delay đã được
            # tính vào phần thời gian còn lại.
            try:
                if server_ts is not None:
                    self._online_clock_offset = float(server_ts) - time.time()
                remaining_f = max(0.0, self._turn_deadline - (time.time() + self._online_clock_offset))
            except Exception:
                remaining_f = max(0.0, self._turn_deadline - time.time())
            self._turn_deadline_mono = time.monotonic() + remaining_f
            remaining = int(remaining_f)  # floor
            other = self.opposite_symbol(symbol)
            self.turn_time_remaining = {symbol: remaining, other: self.turn_time_limit}
        else:
            self._turn_deadline = None
            self._turn_deadline_mono = time.monotonic() + float(self.turn_time_limit)
            self.turn_time_remaining = {"X": self.turn_time_limit, "O": self.turn_time_limit}

        self.update_turn_bar()
        if not self.game_over and not self.is_ai_match_paused:
            # Tick nhanh để hiện 0 trước khi timeout
            interval = 200 if self.game_mode_var.get() == "Online" else 200
            self.turn_timer_job = self.root.after(interval, self.run_turn_timer)

    def run_turn_timer(self):
        if self.game_over or self.is_ai_match_paused:
            self.turn_timer_job = None
            return
            
        is_online = self.game_mode_var.get() == "Online"
        current_sym = (getattr(self, "_server_turn_symbol", None) or self.get_current_symbol()) if is_online else self.get_current_symbol()

        remaining_f = None
        if getattr(self, "_turn_deadline_mono", None) is not None:
            # after() chỉ đánh thức UI; remaining luôn tính từ deadline thật.
            remaining_f = max(0.0, self._turn_deadline_mono - time.monotonic())
            # floor → hiện 0 trước khi timeout (ceil khiến nhảy 1 → hết giờ)
            remaining = int(remaining_f)
            prev = self.turn_time_remaining.get(current_sym, remaining)
            other = "O" if current_sym == "X" else "X"
            self.turn_time_remaining = {current_sym: remaining, other: self.turn_time_limit}
            if prev > 5 >= remaining and remaining > 0:
                self.play_sound(TIME_SOUND_PATH)

        self.update_turn_bar()
        
        # Timeout theo thời gian thật, không theo số hiển thị (tránh hết giờ khi còn hiện 1)
        if remaining_f is not None and remaining_f <= 0.0:
            if is_online and self.ws and self.is_online_connected:
                try:
                    self.ws.send(json.dumps({"type": "timeout", "loser": current_sym}))
                except Exception:
                    pass
            else:
                self.handle_timeout(current_sym)
            return
            
        interval = 250 if is_online else 200
        self.turn_timer_job = self.root.after(interval, self.run_turn_timer)

    def update_turn_bar(self):
        if not hasattr(self, "turn_bar_left"): return
        
        limit_secs = self.get_selected_time_limit_seconds() if hasattr(self, "get_selected_time_limit_seconds") else 0
        if limit_secs == 0:
            for widget_name in ["turn_bar_left", "turn_bar_right", "lbl_turn_left", "lbl_turn_right"]:
                if hasattr(self, widget_name):
                    w = getattr(self, widget_name)
                    if w.winfo_exists() and w.winfo_ismapped():
                        setattr(self, f"_{widget_name}_info", w.pack_info())
                        w.pack_forget()
            
            if hasattr(self, "lbl_turn_left"): self.lbl_turn_left.configure(text="")
            if hasattr(self, "lbl_turn_right"): self.lbl_turn_right.configure(text="")
            if hasattr(self, "turn_bar_left"): self.turn_bar_left.set(1.0)
            # 1. Trả giá trị dự phòng về 0.0 (vì thanh đã đảo màu)
            if hasattr(self, "turn_bar_right"): self.turn_bar_right.set(0.0) 
            return

        # 2. Khôi phục đúng thứ tự pack để đối xứng
        for widget_name, is_bar in [("lbl_turn_left", False), ("turn_bar_left", True), ("turn_bar_right", True), ("lbl_turn_right", False)]:
            if hasattr(self, widget_name):
                w = getattr(self, widget_name)
                if w.winfo_exists() and not w.winfo_ismapped():
                    info = getattr(self, f"_{widget_name}_info", None)
                    if info:
                        w.pack(**info)
                    else:
                        if widget_name == "lbl_turn_left":
                            w.pack(side="left", padx=(0, 6))
                        elif widget_name == "turn_bar_left":
                            w.pack(side="left", fill="x", expand=True, pady=(4, 0))
                        elif widget_name == "turn_bar_right":
                            w.pack(side="left", fill="x", expand=True, pady=(4, 0))
                        elif widget_name == "lbl_turn_right":
                            w.pack(side="left", padx=(6, 0))

        turn_limit = getattr(self, "turn_time_limit", 0)
        if turn_limit <= 0:
            turn_limit = limit_secs
            self.turn_time_limit = limit_secs

        my_sym = self.online_symbol if self.game_mode_var.get() == "Online" and self.online_symbol else (self.player_symbol if self.game_mode_var.get() == "Ultra-AI" else "X")
        opp_sym = self.opposite_symbol(my_sym)
        
        left_secs = self.turn_time_remaining.get(my_sym, turn_limit)
        right_secs = self.turn_time_remaining.get(opp_sym, turn_limit)
        
        # BÊN TRÁI: Chạy thuận (xanh cạn dần về bên trái)
        self.turn_bar_left.set(max(0, min(1, left_secs / turn_limit)))
        
        # 3. BÊN PHẢI: cùng progressbar với bên trái, nhưng soi gương.
        self.turn_bar_right.set(max(0, min(1, right_secs / turn_limit)))

        if hasattr(self, "lbl_turn_left"): 
            self.lbl_turn_left.configure(text=f'{left_secs}s')
            self.lbl_turn_left.configure(text_color="#ef4444" if left_secs <= 5 else ("#475569", "#cbd5e1"))
        if hasattr(self, "lbl_turn_right"): 
            self.lbl_turn_right.configure(text=f'{right_secs}s')
            self.lbl_turn_right.configure(text_color="#ef4444" if right_secs <= 5 else ("#475569", "#cbd5e1"))

        current = self.get_current_symbol()
        self.update_active_score_card(current)

    def update_active_score_card(self, current_sym):
        if not hasattr(self, "score_left_card"): return
        
        # ĐÃ THÊM: Nếu ván đấu đã kết thúc, luôn bắt viền xanh sáng ở thẻ đang giữ quân X (vì X sẽ đi trước)
        if getattr(self, "game_over", False):
            current_sym = "X"
            
        my_sym = self.online_symbol if self.game_mode_var.get() == "Online" and self.online_symbol else (self.player_symbol if self.game_mode_var.get() == "Ultra-AI" else "X")
        left_active = current_sym == my_sym
        
        active_border = "#22c55e" if not self.is_dark_mode else "#4ade80"
        normal_border = "#94a3b8" if not self.is_dark_mode else "#475569"
        try:
            # Tăng số 3 (hoặc 4) để làm viền xanh dày hơn. Số 2 phía sau là độ dày của viền xám.
            self.score_left_card.configure(
                border_width=3 if left_active else 2, 
                border_color=active_border if left_active else normal_border
            )
            self.score_right_card.configure(
                border_width=3 if not left_active else 2, 
                border_color=active_border if not left_active else normal_border
            )
        except Exception: pass

    def run_match_timer(self):
        if self.game_over or self.is_ai_match_paused: return

        # Online: đồng hồ tổng suy ra từ base times + deadline server (không tự trừ mù)
        if self.game_mode_var.get() == "Online":
            base = getattr(self, "_match_base_times", None)
            deadline = getattr(self, "_turn_deadline", None)
            turn_secs = getattr(self, "turn_time_limit", 35)
            current_sym = getattr(self, "_server_turn_symbol", None) or self.get_current_symbol()
            if base and deadline and self.get_selected_time_limit_seconds() > 0:
                # Dùng deadline monotonic đã đồng bộ từ server; không phụ thuộc
                # vào việc callback after(250) chạy sớm/trễ hay đồng hồ hệ thống đổi.
                remaining_turn = max(0.0, getattr(self, "_turn_deadline_mono", time.monotonic()) - time.monotonic())
                elapsed = max(0.0, turn_secs - remaining_turn)
                display = {
                    "X": int(base.get("X", 0)),
                    "O": int(base.get("O", 0))
                }
                display[current_sym] = max(0, int(display.get(current_sym, 0) - elapsed))
                self.time_remaining = display
                self.update_timer_display()
            self.timer_job = self.root.after(250, self.run_match_timer)
            return

        current_sym = self.get_current_symbol()
        now_mono = time.monotonic()

        # Offline cũng dùng deadline monotonic. Không bao giờ -= 1 theo after().
        # Khi đổi lượt, phần lẻ của giây còn lại được giữ nguyên, nên không mất
        # dần thời gian sau nhiều lượt.
        if self._match_active_symbol != current_sym or self._match_deadline_mono is None:
            if self._match_active_symbol in ("X", "O") and self._match_deadline_mono is not None:
                old = self._match_active_symbol
                self._match_precise_remaining[old] = max(0.0, self._match_deadline_mono - now_mono)
                self.time_remaining[old] = int(self._match_precise_remaining[old])
            self._match_active_symbol = current_sym
            precise = float(self._match_precise_remaining.get(current_sym, self.time_remaining.get(current_sym, 0)))
            self._match_deadline_mono = now_mono + max(0.0, precise)

        remaining_f = max(0.0, self._match_deadline_mono - now_mono)
        self._match_precise_remaining[current_sym] = remaining_f
        # floor → hiện 0 trước khi timeout
        self.time_remaining[current_sym] = int(remaining_f)
        if self.time_remaining[current_sym] <= 5 and self.time_remaining[current_sym] > 0:
            if self.time_remaining[current_sym] == 5:
                self.play_sound(TIME_SOUND_PATH)
        self.update_timer_display()
        if remaining_f <= 0.0:
            self.handle_timeout(current_sym)
            return
        self.timer_job = self.root.after(100, self.run_match_timer)

    def update_timer_display(self):
        limit_secs = self.get_selected_time_limit_seconds()
        if limit_secs == 0:
            if hasattr(self, "lbl_score_left_time"): self.lbl_score_left_time.configure(text="∞")
            if hasattr(self, "lbl_score_right_time"): self.lbl_score_right_time.configure(text="∞")
            # Ẩn hoặc làm trống thanh tiến trình thời gian khi không giới hạn thời gian
            if hasattr(self, "turn_bar_left") and self.turn_bar_left.winfo_exists():
                self.turn_bar_left.pack_forget()
            if hasattr(self, "turn_bar_right") and self.turn_bar_right.winfo_exists():
                self.turn_bar_right.pack_forget()
        else:
            mx, sx = divmod(max(0, self.time_remaining.get("X", 0)), 60)
            mo, so = divmod(max(0, self.time_remaining.get("O", 0)), 60)
            x_text, o_text = f"⏱ {mx:02d}:{sx:02d}", f"⏱ {mo:02d}:{so:02d}"
            mode = self.game_mode_var.get()
            if hasattr(self, "lbl_score_left_time"):
                if mode == "Online":
                    my_sym = self.online_symbol or "X"
                    self.lbl_score_left_time.configure(text=x_text if my_sym == "X" else o_text)
                    self.lbl_score_right_time.configure(text=o_text if my_sym == "X" else x_text)
                else:
                    self.lbl_score_left_time.configure(text=x_text); self.lbl_score_right_time.configure(text=o_text)
            if hasattr(self, "lbl_timer"): self.lbl_timer.configure(text="")
            self.update_turn_bar()

    def add_score(self, winning_symbol):
        mode = self.game_mode_var.get()
        if mode == "Online":
            if winning_symbol == self.online_symbol:
                self.score_me += 1
            else:
                self.score_opp += 1
        else:
            if winning_symbol == "X": self.score_me += 1
            elif winning_symbol == "O": self.score_opp += 1
        self.update_score_display()

    def display_opponent_name(self):
        """Tên đối thủ trên UI. Placeholder mặc định luôn theo ngôn ngữ hiện tại."""
        name = (self.opponent_name or "").strip()
        if not name or name in ("Đối thủ", "Opponent"):
            return self.t("default_opp")
        return name

    def update_score_display(self):
        if not hasattr(self, 'lbl_score_left'): return
        mode = self.game_mode_var.get()
        p_name = self.player_name_var.get().strip() or self.t("your_name")
        opp_name = self.display_opponent_name()
        
        x_color = "#22d3ee" if self.is_dark_mode else "#3498db"
        o_color = "#ef4444" if self.is_dark_mode else "#e74c3c"

        if mode == "Online":
            my_sym = self.online_symbol if self.online_symbol else "X"
            opp_sym = self.opposite_symbol(my_sym)
        elif mode == "Ultra-AI":
            my_sym = self.player_symbol
            opp_sym = self.ai_symbol
        else:
            my_sym = "X"
            opp_sym = "O"

        if mode == "Online":
            left_text = p_name
            right_text = opp_name
            left_color = x_color if my_sym == "X" else o_color
            right_color = x_color if opp_sym == "X" else o_color
        elif mode == "Ultra-AI":
            left_text = p_name
            right_text = self.t("Ultra AI")
            left_color = x_color if my_sym == "X" else o_color
            right_color = x_color if opp_sym == "X" else o_color
        elif mode == "2 Người":
            # Đã xóa [X] và [O] ở đây
            left_text = self.t("player_1")
            right_text = self.t("player_2")
            left_color, right_color = x_color, o_color
        else:
            # Chế độ AI vs AI (Đã xóa [X] và [O])
            left_text = self.t("ai_1")
            right_text = self.t("ai_2")
            left_color, right_color = x_color, o_color
            
        self.lbl_score_left.configure(text=left_text, text_color=left_color)
        self.lbl_score_right.configure(text=right_text, text_color=right_color)
        self.lbl_score_left_points.configure(text=str(self.score_me), text_color=left_color)
        self.lbl_score_right_points.configure(text=str(self.score_opp), text_color=right_color)
        self.lbl_score_left_symbol.configure(text=my_sym, fg_color=left_color)
        self.lbl_score_right_symbol.configure(text=opp_sym, fg_color=right_color)
        self.update_timer_display()
        self.update_active_score_card(self.get_current_symbol())

    def handle_timeout(self, loser_sym):
        if self.game_over: return
        self.cancel_after("timer_job")
        self.cancel_after("turn_timer_job")
        winner_sym = self.opposite_symbol(loser_sym)
        
        self.add_score(winner_sym)
        self.display_status("timeout_msg", color=self.status_color_for_symbol(winner_sym), format_args=[winner_sym])
        self.game_over = True
        # Hủy trạng thái yêu cầu đầu hàng nếu đang pending
        self._i_resigned = False
        self._opp_resigned = False
        self._resign_name = ""
        if self.game_mode_var.get() == "AI vs AI":
            self.is_ai_thinking = False
            self.stop_thinking_animation()
        self.update_symbol_auto_button()
        self.set_time_controls_enabled(True)
        self.update_pause_btn_state()
        self.play_sound(VICTORY_SOUND_PATH)
        self.modern_canvas.configure(cursor="hand2")

    def on_rule_change(self, value):
        if self.game_mode_var.get() == "Online" and (self.history or self.game_over):
            return
        self.save_settings()
        # AI modes + Chặn 2 đầu → AlphaGomoku chỉ hỗ trợ 15x15 → tự chuyển bàn
        self._enforce_board_for_caro_ai()
        self.send_online_settings()

    def load_settings(self):
        if not os.path.exists(CONFIG_PATH): return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f: data = json.load(f)
            lang = data.get("lang", "VI") if data.get("lang") in ("VI", "EN") else "VI"
            self.lang_var.set(lang)
            saved_mode = data.get("game_mode", "Ultra-AI")
            if saved_mode not in GAME_MODES: saved_mode = "Ultra-AI"
            self.game_mode_var.set(saved_mode)
            self.player_symbol_var.set(data.get("player_symbol", "X") if data.get("player_symbol") in ("X", "O") else "X")
            self.board_size_var.set(data.get("board_size", "20x20") if data.get("board_size") in BOARD_SIZES else "20x20")
            self.player_name_var.set(data.get("player_name", "Tùng"))
            
            diff_map = DIFFICULTY.get(lang, DIFFICULTY.get("VI", {}))
            default_diff = list(diff_map.keys())[0] if diff_map else ""
            for var, key in ((self.difficulty_var, "difficulty_ms"), (self.difficulty_x_var, "difficulty_x_ms"), (self.difficulty_o_var, "difficulty_o_ms")):
                saved_ms = data.get(key, 200)
                matched_label = next((label for label, ms in diff_map.items() if ms == saved_ms), default_diff)
                if matched_label: var.set(matched_label)
            
            rules = LANG.get(lang, LANG.get("VI", {})).get("rules_list", ["Tiêu chuẩn", "Chặn 2 đầu"])
            idx = data.get("rule_index", 0)
            self.rule_var.set(rules[idx] if 0 <= idx < len(rules) else rules[0])
            self.ui_style_var.set("Cổ điển" if data.get("ui_style") == "classic" else "Hiện đại")
            self.theme_var.set("Tối" if data.get("theme") == "dark" else "Sáng")
            self.sound_enabled = data.get("sound_enabled", True)
            self.time_minutes_var.set(str(data.get("time_minutes", 0)))
            self.auto_rotate_var.set(data.get("auto_rotate", True))
            self.update_symbol_auto_button()
        except (json.JSONDecodeError, OSError): pass

    def save_settings(self, value=None):
        try:
            lang = self.lang_var.get()
            rules = LANG.get(lang, LANG.get("VI", {})).get("rules_list", ["Tiêu chuẩn", "Chặn 2 đầu"])
            diff_map = DIFFICULTY.get(lang, DIFFICULTY.get("VI", {}))
            config_data = {
                "lang": lang, "game_mode": self.game_mode_var.get(), "player_symbol": self.player_symbol_var.get(), "board_size": self.board_size_var.get(),
                "player_name": self.player_name_var.get(),
                "difficulty_ms": diff_map.get(self.difficulty_var.get(), 200), "difficulty_x_ms": diff_map.get(self.difficulty_x_var.get(), 200),
                "difficulty_o_ms": diff_map.get(self.difficulty_o_var.get(), 200),
                "rule_index": rules.index(self.rule_var.get()) if self.rule_var.get() in rules else 0,
                "ui_style": "classic" if self.ui_style_var.get() in ("Cổ điển", "Classic") else "modern",
                "theme": "dark" if self.is_dark_mode else "light", "sound_enabled": self.sound_enabled, "time_minutes": self.time_minutes_var.get(), "auto_rotate": self.auto_rotate_var.get()
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(config_data, f, ensure_ascii=False, indent=2)
            self.update_score_display()
        except (OSError, TypeError): pass

    def select_game_mode(self, mode):
        if self.is_ai_thinking or getattr(self, '_is_waiting_online', False): return
        if self.is_online_connected and mode != "Online":
            return
        self.game_mode_var.set(mode)
        self.update_mode_buttons()
        self.on_mode_change()
        if mode == "Online":
            # Nếu app đã mở lâu, Render có thể đã ngủ lại; warm-up lần nữa khi người dùng chọn Online.
            self.warmup_online_server()

    def update_mode_buttons(self):
        if not hasattr(self, 'btn_mode_ai'): return
        hover_trans = "#34495e" if self.is_dark_mode else "#e0e0e0"
        border_col = "#34495e" if self.is_dark_mode else "#bdc3c7"
        current_mode = self.game_mode_var.get()
        
        button_map = [(self.btn_mode_ai, "Ultra-AI"), (self.btn_mode_2p, "2 Người"), (self.btn_mode_ai_vs_ai, "AI vs AI"), (self.btn_mode_online, "Online")]
        for btn, m_val in button_map:
            if current_mode == m_val:
                btn.configure(fg_color="#2980b9", hover_color="#2471a3", text_color="white", border_width=0, state="normal")
            else:
                if self.is_online_connected:
                    disabled_bg = "#21262d" if self.is_dark_mode else "#e2e8f0"
                    disabled_border = "#334155" if self.is_dark_mode else "#cbd5e1"
                    btn.configure(fg_color=disabled_bg, hover_color=disabled_bg, text_color="gray", border_width=2, border_color=disabled_border, state="disabled")
                else:
                    btn.configure(fg_color="transparent", hover_color=hover_trans, text_color=("black", "white"), border_width=2, border_color=border_col, state="normal")

    def create_ui(self):
        main_font, bold_font = ctk.CTkFont(family="Segoe UI", size=15, weight="bold"), ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        status_font, timer_display_font = ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        
        # KHUNG CODE MỚI THAY THẾ
        self.control_frame = ctk.CTkFrame(self.root, corner_radius=12, height=175) 
        self.control_frame.pack_propagate(False) 
        self.control_frame.pack(pady=(8, 4), padx=15, fill="x")

        self.main_config_container = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.main_config_container.pack(pady=(0, 8), padx=12, fill="x")

        # Cụm 4 nút icon PNG thuần (không nền màu). Fallback emoji nếu thiếu icon.
        self.right_panel = ctk.CTkFrame(
            self.main_config_container,
            fg_color="transparent",
            width=48,
            height=168
        )
        self.right_panel.pack_propagate(False)
        self.right_panel.pack(side="right", anchor="ne", padx=(0, 0), pady=(4, 0))

        icon_font = ctk.CTkFont(family="Segoe UI Emoji", size=16)
        use_img = getattr(self, "_use_image_icons", False)

        # Hover nhẹ để biết đang hover, không có nền màu cố định
        hover_light = ("#cbd5e1", "#475569")

        def _make_icon_btn(image, fallback_text, command):
            return ctk.CTkButton(
                self.right_panel,
                text="" if use_img else fallback_text,
                image=image if use_img else None,
                command=command,
                font=icon_font,
                fg_color="transparent",
                hover_color=hover_light,
                width=36, height=36,
                corner_radius=8,
                border_width=0,
                anchor="center"
            )

        _gap = 0  # khe đều giữa các nút

        # Language
        lang_img = self.icon_lang_vi if (use_img and self.lang_var.get() == "VI") else (self.icon_lang_en if use_img else None)
        self.btn_lang = _make_icon_btn(lang_img, self.get_lang_btn_icon(), self.toggle_language)
        self.btn_lang.pack(pady=(0, _gap), fill="none", expand=False)

        # Sound
        sound_img = self.icon_sound_on if (use_img and self.sound_enabled) else (self.icon_sound_off if use_img else None)
        self.btn_sound = _make_icon_btn(sound_img, self.get_sound_btn_icon(), self.toggle_sound)
        self.btn_sound.pack(pady=(0, _gap), fill="none", expand=False)

        # Theme
        theme_img = self.icon_theme_dark if (use_img and self.is_dark_mode) else (self.icon_theme_light if use_img else None)
        self.btn_theme = _make_icon_btn(theme_img, self.get_theme_btn_icon(), self.toggle_theme)
        self.btn_theme.pack(pady=(0, _gap), fill="none", expand=False)

        # Style — không pad dưới để không bị cắt mép
        style_img = self.icon_style_on if (use_img and self.ui_style_var.get() in ["Hiện đại", "Modern"]) else (self.icon_style_off if use_img else None)
        self.btn_style = _make_icon_btn(style_img, self.get_style_btn_icon(), self.toggle_ui_style)
        self.btn_style.pack(pady=(0, 0), fill="none", expand=False)

        # === CHAT ONLINE: nằm ở khoảng trống bên trái 4 nút tiện ích ===
        # Chat nằm cùng hàng với cụm Ngôn ngữ / Âm thanh / Giao diện / Phong cách,
        # không nằm bên dưới các nút và không chiếm thêm chiều cao của khu điều khiển.
        self.chat_frame = ctk.CTkFrame(
            self.main_config_container, fg_color=("#dbdbdb", "gray17"),
            corner_radius=10, border_width=2,
            border_color=("#b0c4de", "#374151"), width=370, height=154
        )
        self.chat_frame.pack_propagate(False)

        self.chat_header = ctk.CTkFrame(self.chat_frame, fg_color="transparent", height=24)
        self.chat_header.pack(fill="x", padx=8, pady=(2, 0))
        self.chat_header.pack_propagate(False)
        self.chat_title = ctk.CTkLabel(
            self.chat_header, text=self.t("chat_title"),
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        self.chat_title.pack(side="left", fill="x", expand=True)

        chat_font = ctk.CTkFont(family="Segoe UI", size=13)
        self.chat_box = ctk.CTkTextbox(
    self.chat_frame, font=chat_font, wrap="word",
    activate_scrollbars=True, height=85, corner_radius=8,
    border_width=0, fg_color=("#cbd5e1", "#111827"),
    padx=0, pady=0  # <-- Thêm thông số này để ép chữ sát lề trong
)
        self.chat_box.pack(fill="both", expand=True, padx=8)
        self.chat_box.tag_config("sys_msg", foreground="#64748b")
        self.chat_box.insert("1.0", self.t("chat_empty"), "sys_msg")
        self.chat_box.configure(state="disabled")

        self.chat_input_row = ctk.CTkFrame(self.chat_frame, fg_color="transparent", height=30)
        self.chat_input_row.pack(fill="x", padx=(8, 2), pady=(4, 7))
        self.chat_input_row.pack_propagate(False)

        self.chat_entry = ctk.CTkEntry(
            self.chat_input_row,
            font=chat_font,
            height=28,
            placeholder_text=self.t("chat_placeholder"),
            corner_radius=8
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 0))
        self.chat_entry.bind("<Return>", self.send_chat_message)

        self.btn_chat_send = ctk.CTkButton(
            self.chat_input_row,
            text="" if getattr(self, "icon_send", None) else "➤",
            image=getattr(self, "icon_send", None),
            width=15,
            height=15,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("#dbdbdb", "gray17"),
            anchor="center",
            command=self.send_chat_message
        )
        self.btn_chat_send.pack(side="right", padx=(0, 0))

        # Chat luôn hiển thị trong chế độ Online, ở bên trái cụm 4 nút tiện ích.
        self.chat_frame.pack(side="right", padx=(0, 0), pady=(0, 0), anchor="ne")
        self._chat_open = True
        self.chat_frame.pack_forget()

        self.left_panel = ctk.CTkFrame(self.main_config_container, fg_color="transparent")
        self.left_panel.pack(side="left", anchor="nw", fill="x", expand=True, pady=(8, 0))

        # Khối ngang: hàng 1+2 bên trái, khung X/🔄 sát ngay sau (không đẩy ra mép phải)
        self.top_config_block = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.top_config_block.pack(anchor="w")

        self.rows_12 = ctk.CTkFrame(self.top_config_block, fg_color="transparent")
        self.rows_12.pack(side="left", anchor="n")

        self.row1 = ctk.CTkFrame(self.rows_12, fg_color="transparent")
        self.row1.pack(pady=(0, 8), anchor="w")
        
        self.lbl_mode = ctk.CTkLabel(self.row1, text=self.t("mode"), font=bold_font); self.lbl_mode.pack(side="left", padx=(0, 8))
        self.btn_mode_ai = ctk.CTkButton(self.row1, text=self.t("mode_ai"), font=bold_font, width=90, height=32, corner_radius=16, command=lambda: self.select_game_mode("Ultra-AI"))
        self.btn_mode_ai.pack(side="left", padx=(0, 6))
        self.btn_mode_2p = ctk.CTkButton(self.row1, text=self.t("mode_2p"), font=bold_font, width=90, height=32, corner_radius=16, command=lambda: self.select_game_mode("2 Người"))
        self.btn_mode_2p.pack(side="left", padx=(0, 6))
        self.btn_mode_ai_vs_ai = ctk.CTkButton(self.row1, text=self.t("mode_ai_vs_ai"), font=bold_font, width=90, height=32, corner_radius=16, command=lambda: self.select_game_mode("AI vs AI"))
        self.btn_mode_ai_vs_ai.pack(side="left", padx=(0, 6))
        
        mode_online_text = self.t("mode_online") if "mode_online" in LANG.get("VI", {}) else "Online"
        self.btn_mode_online = ctk.CTkButton(self.row1, text=mode_online_text, font=bold_font, width=90, height=32, corner_radius=16, command=lambda: self.select_game_mode("Online"))
        self.btn_mode_online.pack(side="left", padx=(0, 4))

        self.row2 = ctk.CTkFrame(self.rows_12, fg_color="transparent")
        self.row2.pack(pady=(0, 8), anchor="w")
        self.lbl_board = ctk.CTkLabel(self.row2, text=self.t("board"), font=bold_font); self.lbl_board.pack(side="left", padx=(0, 6))
        self.size_menu = ctk.CTkOptionMenu(self.row2, variable=self.board_size_var, values=["15x15", "20x20"], font=main_font, dropdown_font=main_font, command=self.on_board_size_change, width=75, height=30); self.size_menu.pack(side="left", padx=(0, 14))
        
        self.lbl_rule = ctk.CTkLabel(self.row2, text=self.t("rule"), font=bold_font); self.lbl_rule.pack(side="left", padx=(0, 6))
        
        rule_vals = self.t("rules_list")
        if not isinstance(rule_vals, list) or not rule_vals: 
            rule_vals = ["Tiêu chuẩn", "Chặn 2 đầu"]
        self.rule_menu = ctk.CTkOptionMenu(self.row2, variable=self.rule_var, values=rule_vals, font=main_font, dropdown_font=main_font, command=self.on_rule_change, width=135, height=30)
        self.rule_menu.pack(side="left", padx=(0,4))
        
        self.lbl_time_limit = ctk.CTkLabel(
            self.row2, text="⏱", font=ctk.CTkFont(size=28),
            width=0, height=0
        )
        self.lbl_time_limit.pack(side="left", padx=(0, 0))
        
        self.time_spin_box = ctk.CTkFrame(self.row2, fg_color="transparent")
        self.time_spin_box.pack(side="left", padx=(0, 4))

        self.time_entry = ctk.CTkEntry(
            self.time_spin_box, textvariable=self.time_minutes_var,
            font=bold_font, width=32, height=32, justify="center",
            corner_radius=6
        )
        self.time_entry.pack(side="left", padx=(0, 4))
        self.time_entry.bind("<FocusOut>", self.on_time_entry_change)
        self.time_entry.bind("<Return>", self.on_time_entry_change)

        self.time_btn_frame = ctk.CTkFrame(
            self.time_spin_box, fg_color="transparent", width=24, height=33
        )
        self.time_btn_frame.pack(side="left")
        self.time_btn_frame.pack_propagate(False)

        self.btn_plus = ctk.CTkButton(
            self.time_btn_frame, text="+",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=24, height=14, corner_radius=3,
            fg_color="#2980b9", hover_color="#3498db"
        )
        self.btn_plus.place(x=0, y=0)
        self.btn_plus.bind("<ButtonPress-1>", lambda e: self.start_hold_change(1))
        self.btn_plus.bind("<ButtonRelease-1>", self.stop_hold_change)

        self.btn_minus = ctk.CTkButton(
            self.time_btn_frame, text="−",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=24, height=14, corner_radius=3,
            fg_color="#7f8c8d", hover_color="#95a5a6"
        )
        self.btn_minus.place(x=0, y=16)
        self.btn_minus.bind("<ButtonPress-1>", lambda e: self.start_hold_change(-1))
        self.btn_minus.bind("<ButtonRelease-1>", self.stop_hold_change)

        # Khung chung sát bên phải: nền trong suốt, viền luôn là màu xanh lá
        self.symbol_frame = ctk.CTkFrame(
            self.top_config_block,
            fg_color="transparent",
            border_width=2,
            border_color=("#16a34a", "#22c55e"),
            corner_radius=10,
        )
        self.symbol_frame.pack(side="left", padx=(4, 0), pady=(0, 6), anchor="n")
        self.symbol_frame.grid_rowconfigure(0, weight=1)
        self.symbol_frame.grid_rowconfigure(1, weight=1)
        self.symbol_frame.grid_columnconfigure(0, weight=1)

        self.btn_toggle_symbol = ctk.CTkButton(
            self.symbol_frame, text="X", font=bold_font, width=36, height=28, corner_radius=6,
            command=self.toggle_symbol_only
        )
        self.btn_toggle_symbol.grid(row=0, column=0, padx=4, pady=(2, 1), sticky="")

        self.btn_auto_rotate = ctk.CTkButton(
            self.symbol_frame, text="🔄", font=bold_font, width=36, height=28, corner_radius=6,
            command=self.toggle_auto_only
        )
        self.btn_auto_rotate.grid(row=1, column=0, padx=4, pady=(1, 2), sticky="")

        self.online_room_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        
        self.lbl_name = ctk.CTkLabel(self.online_room_frame, text=self.t("name_label"), font=bold_font)
        self.lbl_name.pack(side="left", padx=(0, 6))
        
        self.name_entry = ctk.CTkEntry(self.online_room_frame, textvariable=self.player_name_var, font=bold_font, width=90, height=32, justify="center")
        self.name_entry.pack(side="left", padx=(0, 10))
        self.name_entry.bind("<FocusOut>", self.save_settings)

        self.lbl_room = ctk.CTkLabel(self.online_room_frame, text=self.t("room_label"), font=bold_font)
        self.lbl_room.pack(side="left", padx=(0, 6))
        self.room_entry = ctk.CTkEntry(self.online_room_frame, textvariable=self.room_id_var, font=bold_font, width=70, height=32, justify="center")
        self.room_entry.pack(side="left", padx=(0, 10))
        
        self.btn_join = ctk.CTkButton(self.online_room_frame, text=self.t("join_room"), font=bold_font, width=90, height=32, fg_color="#27ae60", hover_color="#2ecc71", corner_radius=8, command=self.join_online_room)
        self.btn_join.pack(side="left", padx=(0, 8))
        
        self.btn_leave_online = ctk.CTkButton(self.online_room_frame, text=self.t("leave_online"), font=bold_font, width=100, height=32, fg_color="#64748b", hover_color="#475569", corner_radius=8, command=self.exit_online_mode)
        self.btn_leave_online.pack(side="left")

        # KHỞI TẠO HÀNG 3: ĐỘ KHÓ
        self.row3 = ctk.CTkFrame(self.left_panel, fg_color="transparent", height=32)
        self.row3.pack(anchor="w", fill="x", pady=(0, 4))
        self.row3.pack_propagate(False)

        # Khung chế độ 1 AI (Ultra-AI & 2 Người)
        self.diff_single_frame = ctk.CTkFrame(self.row3, fg_color="transparent", width=350, height=32)
        self.diff_single_frame.pack_propagate(False)
        
        self.lbl_diff = ctk.CTkLabel(self.diff_single_frame, text=self.t("diff"), font=bold_font, width=68, anchor="w")
        self.lbl_diff.pack(side="left", padx=(0, 6))
        
        diff_values = list(DIFFICULTY.get(self.lang_var.get(), DIFFICULTY.get("VI", DEFAULT_DIFF)).keys())
        if not diff_values: diff_values = ["Cao thủ (0.2s)"]
            
        self.diff_menu = ctk.CTkOptionMenu(self.diff_single_frame, variable=self.difficulty_var, values=diff_values, font=main_font, dropdown_font=main_font, command=self.save_settings, width=140, height=30)
        self.diff_menu.pack(side="left")

        # Khung chế độ AI vs AI
        self.diff_vs_frame = ctk.CTkFrame(self.row3, fg_color="transparent", width=650, height=32)
        self.diff_vs_frame.pack_propagate(False)
        
        self.lbl_diff_x = ctk.CTkLabel(self.diff_vs_frame, text=self.t("diff_x"), font=bold_font)
        self.lbl_diff_x.pack(side="left", padx=(0, 6))
        
        self.diff_x_menu = ctk.CTkOptionMenu(self.diff_vs_frame, variable=self.difficulty_x_var, values=diff_values, font=main_font, dropdown_font=main_font, command=self.save_settings, width=140, height=30)
        self.diff_x_menu.pack(side="left", padx=(0, 10))
        
        _swap_img = getattr(self, "icon_swap", None)
        self.btn_swap_diff = ctk.CTkButton(
            self.diff_vs_frame,
            text="" if _swap_img else "⇄",
            image=_swap_img,
            command=self.swap_ai_difficulties,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            fg_color="#8e44ad",
            hover_color="#9b59b6",
            width=38,
            height=30,
            corner_radius=8,
        )
        self.btn_swap_diff.pack(side="left", padx=(4, 10))
        
        self.lbl_diff_o = ctk.CTkLabel(self.diff_vs_frame, text=self.t("diff_o"), font=bold_font)
        self.lbl_diff_o.pack(side="left", padx=(0, 6))
        
        self.diff_o_menu = ctk.CTkOptionMenu(self.diff_vs_frame, variable=self.difficulty_o_var, values=diff_values, font=main_font, dropdown_font=main_font, command=self.save_settings, width=140, height=30)
        self.diff_o_menu.pack(side="left")

        # KHỞI TẠO HÀNG 4: CÁC NÚT ĐIỀU KHIỂN
        self.row4 = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.row4.pack(anchor="w", pady=(7, 4))  # Tăng khoảng cách phía trên từ 4 lên 7 để hạ thấp thêm chút nữa
        
        self.btn_new = ctk.CTkButton(self.row4, text=self.t("new_game"), command=self.request_new_game, font=bold_font, fg_color="#e74c3c", hover_color="#c0392b", width=135, height=35, corner_radius=10)
        self.btn_new.pack(side="left", padx=(0, 8))

        # Nút Đầu hàng / Chấp nhận — chỉ hiện ở tab Online (pack trong refresh_mode_visibility)
        self.btn_resign = ctk.CTkButton(
            self.row4, text=self.t("resign_btn"), command=self.on_resign_or_accept,
            font=bold_font, fg_color="#7f1d1d", hover_color="#991b1b",
            width=130, height=35, corner_radius=10, state="disabled"
        )
        # Đồng hồ đếm ngược hết hạn yêu cầu đầu hàng (đỏ, sau nút ĐẦU HÀNG)
        self.lbl_resign_countdown = ctk.CTkLabel(
            self.row4, text="", font=ctk.CTkFont(size=30, weight="bold"),
            text_color="#ef4444", width=36, height=35
        )
        # không pack mặc định — chỉ hiện khi có yêu cầu đang chờ

        # Đưa nút Bắt đầu / Dừng / Tiếp tục lên trước nút Lùi - Tiến
        disabled_bg = "#21262d" if self.is_dark_mode else "#e2e8f0"
        disabled_fg = "#6e7681" if self.is_dark_mode else "#64748b"
        self.btn_pause_resume = ctk.CTkButton(
            self.row4, text=self.t("start"), command=self.toggle_pause_resume, 
            font=bold_font, width=175, height=35, corner_radius=10,
            fg_color=disabled_bg, text_color=disabled_fg, state="disabled"
        )
        self.btn_pause_resume.pack(side="left", padx=(0, 8))
        
        self.btn_undo = ctk.CTkButton(self.row4, text=self.t("undo"), command=self.undo_move, font=bold_font, fg_color="#e67e22", hover_color="#d35400", width=85, height=35, corner_radius=10)
        self.btn_undo.pack(side="left", padx=(0, 8))
        
        self.btn_redo = ctk.CTkButton(self.row4, text=self.t("redo"), command=self.redo_move, font=bold_font, fg_color="#2980b9", hover_color="#2471a3", width=85, height=35, corner_radius=10)
        self.btn_redo.pack(side="left", padx=(0, 8))
        
        self.btn_hint = ctk.CTkButton(self.row4, text=self.t("hint"), command=self.get_hint, font=bold_font, fg_color="#8e44ad", hover_color="#9b59b6", width=85, height=35, corner_radius=10)
        self.btn_hint.pack(side="left", padx=(0, 8))

        self.status_container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.status_container.pack(pady=(2, 4), fill="x", padx=10)
        self.status = ctk.CTkLabel(self.status_container, text="", font=status_font); self.status.pack(anchor="center", pady=(0, 2)); self.display_status("init_status", color="#3498db")
        
# KHỞI TẠO KHUNG TỈ SỐ VÀ THỜI GIAN CHUNG Ở GIỮA
        self.score_bg = ctk.CTkFrame(self.status_container, fg_color="transparent")
        self.score_bg.pack(anchor="center", fill="x", pady=(0, 2), padx=5)
        
        # THÊM uniform="card" ĐỂ ÉP 2 BÊN LUÔN BẰNG NHAU 100%
        self.score_bg.grid_columnconfigure(0, weight=1, uniform="card")
        self.score_bg.grid_columnconfigure(1, weight=0, minsize=65)
        self.score_bg.grid_columnconfigure(2, weight=1, uniform="card")

        card_fg = ("#f1f5f9", "#1e293b")
        card_border = ("#cbd5e1", "#334155")

        self.score_left_card = ctk.CTkFrame(
            self.score_bg, fg_color=card_fg, border_width=1,
            border_color=card_border, corner_radius=14, height=76
        )
        self.score_left_card.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.score_left_card.grid_propagate(False)

        self.score_right_card = ctk.CTkFrame(
            self.score_bg, fg_color=card_fg, border_width=1,
            border_color=card_border, corner_radius=14, height=76
        )
        self.score_right_card.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.score_right_card.grid_propagate(False)

        name_font = ctk.CTkFont(family="Segoe UI", size=23, weight="bold")
        time_font = ctk.CTkFont(family="Segoe UI", size=23, weight="bold")  # Đổi từ 18 thành 23
        score_font = ctk.CTkFont(family="Segoe UI", size=36, weight="bold")  
        symbol_font = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        bar_font = ctk.CTkFont(family="Segoe UI", size=15, weight="bold") # Tăng lên 15 cho to rõ

        self.score_left_top = ctk.CTkFrame(self.score_left_card, fg_color="transparent", height=42)
        self.score_left_top.pack(fill="x", padx=12, pady=(6, 0))
        self.score_left_top.pack_propagate(False)
        # Cấu hình các cột tỷ lệ/cố định cho thẻ trái để định vị đồng hồ đứng yên
        self.score_left_top.grid_columnconfigure(0, weight=0, minsize=38)  # Ô icon quân cờ
        self.score_left_top.grid_columnconfigure(1, weight=0, minsize=110) # Ô tên người chơi
        self.score_left_top.grid_columnconfigure(2, weight=1)              # Khoảng trống co giãn để giữ đồng hồ đúng giữa
        self.score_left_top.grid_columnconfigure(3, weight=0, minsize=90)  # Ô chứa đồng hồ 01:00 (Cố định tuyệt đối)
        self.score_left_top.grid_columnconfigure(4, weight=0, minsize=45)  # Ô điểm số

        self.score_right_top = ctk.CTkFrame(self.score_right_card, fg_color="transparent", height=42)
        self.score_right_top.pack(fill="x", padx=12, pady=(6, 0))
        self.score_right_top.pack_propagate(False)
        # Cấu hình các cột tỷ lệ/cố định cho thẻ phải
        self.score_right_top.grid_columnconfigure(0, weight=0, minsize=45)  # Ô điểm số
        self.score_right_top.grid_columnconfigure(1, weight=0, minsize=90)  # Ô chứa đồng hồ 01:00 (Cố định tuyệt đối)
        self.score_right_top.grid_columnconfigure(2, weight=1)              # Khoảng trống co giãn
        self.score_right_top.grid_columnconfigure(3, weight=0, minsize=110) # Ô tên đối thủ
        self.score_right_top.grid_columnconfigure(4, weight=0, minsize=38)  # Ô icon quân cờ

        # --- THẺ ĐIỂM BÊN TRÁI (BẠN) ---
        self.lbl_score_left_symbol = ctk.CTkLabel(
            self.score_left_top, text="X", width=38, height=38,
            corner_radius=8, fg_color="#3498db", text_color="white", font=symbol_font
        )
        self.lbl_score_left_symbol.grid(row=0, column=0, sticky="w")

        self.lbl_score_left = ctk.CTkLabel(
            self.score_left_top, text=self.player_name_var.get().strip() or self.t("your_name"), font=name_font, anchor="w",
            text_color="#3498db"
        )
        self.lbl_score_left.grid(row=0, column=1, sticky="w", padx=(6, 0))

        # Đồng hồ thời gian được neo cố định vào cột 3, không bị xê dịch bởi tên dài/ngắn
        self.lbl_score_left_time = ctk.CTkLabel(
            self.score_left_top, text="⏱ 01:00", font=time_font, anchor="center",
            text_color=("#334155", "#e2e8f0")
        )
        self.lbl_score_left_time.grid(row=0, column=3, sticky="ew")

        self.lbl_score_left_points = ctk.CTkLabel(
            self.score_left_top, text="0", font=score_font, text_color="#3498db", anchor="center"
        )
        self.lbl_score_left_points.grid(row=0, column=4, sticky="e", padx=(6, 0))


        # --- THẺ ĐIỂM BÊN PHẢI (ĐỐI THỦ) ---
        self.lbl_score_right_symbol = ctk.CTkLabel(
            self.score_right_top, text="O", width=38, height=38,
            corner_radius=8, fg_color="#e74c3c", text_color="white", font=symbol_font
        )
        # Đã sửa lỗi sai tên biến ở dòng này
        self.lbl_score_right_symbol.grid(row=0, column=4, sticky="e")

        self.lbl_score_right = ctk.CTkLabel(
            self.score_right_top, text=self.display_opponent_name(), font=name_font, anchor="e",
            text_color="#e74c3c"
        )
        self.lbl_score_right.grid(row=0, column=3, sticky="e", padx=(0, 6))

        # Đồng hồ thời gian được neo cố định vào cột 1 bên phải
        self.lbl_score_right_time = ctk.CTkLabel(
            self.score_right_top, text="⏱ 01:00", font=time_font, anchor="center",
            text_color=("#334155", "#e2e8f0")
        )
        self.lbl_score_right_time.grid(row=0, column=1, sticky="ew")

        self.lbl_score_right_points = ctk.CTkLabel(
            self.score_right_top, text="0", font=score_font, text_color="#e74c3c", anchor="center"
        )
        self.lbl_score_right_points.grid(row=0, column=0, sticky="w", padx=(0, 6))


        # --- CÁC HÀNG THANH TIẾN TRÌNH & CHỮ TỈ SỐ Ở GIỮA ---
        
        # KHUNG CHỨA BÊN TRÁI
        self.score_left_timer_row = ctk.CTkFrame(self.score_left_card, fg_color="transparent", height=24)
        self.score_left_timer_row.pack(fill="x", padx=10, pady=(0, 2))
        self.score_left_timer_row.pack_propagate(False)
        
        self.lbl_turn_left = ctk.CTkLabel(self.score_left_timer_row, text="35s", width=36, font=bar_font)
        self.lbl_turn_left.pack(side="left", padx=(0, 6))
        
        # BÊN TRÁI: Dùng corner_radius nhỏ hơn (ví dụ: 3) hoặc chỉnh height khớp với bo tròn
        self.turn_bar_left = ctk.CTkProgressBar(
            self.score_left_timer_row, height=8, corner_radius=3,  
            progress_color="#22c55e", fg_color=("#dbe4ee", "#334155")
        )
        self.turn_bar_left.pack(side="left", fill="x", expand=True, pady=(4, 0))
        self.turn_bar_left.set(1.0)


        # KHUNG CHỨA BÊN PHẢI
        self.score_right_timer_row = ctk.CTkFrame(self.score_right_card, fg_color="transparent", height=24)
        self.score_right_timer_row.pack(fill="x", padx=10, pady=(0, 2))
        self.score_right_timer_row.pack_propagate(False)
        
        # BÊN PHẢI: dùng cùng CTkProgressBar/DrawEngine với bên trái,
        # chỉ đảo chiều progress để phần xanh neo sát mép phải.
        self.turn_bar_right = MirroredCTkProgressBar(
            self.score_right_timer_row, height=8, corner_radius=3,
            progress_color="#22c55e", fg_color=("#dbe4ee", "#334155")
        )
        self.turn_bar_right.pack(side="left", fill="x", expand=True, pady=(4, 0))
        self.turn_bar_right.set(1.0)

        self.lbl_turn_right = ctk.CTkLabel(
            self.score_right_timer_row, text="35s", width=36, font=bar_font
        )
        self.lbl_turn_right.pack(side="left", padx=(6, 0))

        self.lbl_score_dash = ctk.CTkLabel(
            self.score_bg, text=self.t("score_title"), width=65,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=("#334155", "#f1f5f9")
        )
        self.lbl_score_dash.grid(row=0, column=1)

        self.info_row = ctk.CTkFrame(self.status_container, fg_color="transparent")
        self.lbl_timer = ctk.CTkLabel(self.info_row, text="")

        self.update_minus_button_color(); self.update_mode_buttons(); self.refresh_mode_visibility()
        
        self.board_container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.board_container.pack(fill="both", expand=True, padx=10, pady=(2, 2))

        self.modern_canvas = tk.Canvas(self.board_container, highlightthickness=0, cursor="hand2", bd=0)
        self.modern_canvas.place(relx=0.5, rely=0.5, anchor="center")
        
        self.modern_canvas.bind("<Button-1>", self.modern_click)
        self.modern_canvas.bind("<Motion>", self.on_canvas_motion)
        self.modern_canvas.bind("<Leave>", self.on_canvas_leave)

    def update_pause_btn_state(self):
        if not hasattr(self, 'btn_pause_resume') or not self.btn_pause_resume.winfo_exists(): return
        mode, is_dark = self.game_mode_var.get(), self.is_dark_mode
        disabled_bg, disabled_fg = ("#21262d" if is_dark else "#e2e8f0"), ("#6e7681" if is_dark else "#64748b")

        # 1. Nút VÁN MỚI
        # Offline: sáng khi đã có nước hoặc ván kết thúc.
        # Online:
        #   - Đang chờ phản hồi đầu hàng (opp gửi offer): nút = CHẤP NHẬN (xanh)
        #   - Mình đã gửi offer: khóa
        #   - Ván kết thúc bình thường / đã accept resign: VÁN MỚI như cũ
        if mode == "Online":
            pending_offer = bool(
                (getattr(self, "_opp_resigned", False) or getattr(self, "_i_resigned", False))
                and not self.game_over
            )
            pending_resign_done = bool(
                (getattr(self, "_opp_resigned", False) or getattr(self, "_i_resigned", False))
                and self.game_over
            )
            can_accept = bool(
                self.is_online_connected
                and getattr(self, "_opp_resigned", False)
                and not self.game_over
            )
            can_new = bool(
                self.is_online_connected
                and self.game_over
                and not self.my_ready_for_rematch
            )
            new_btn_new_sig = (
                "online",
                can_new,
                can_accept,
                is_dark,
                bool(self.game_over),
                bool(self.my_ready_for_rematch),
                pending_offer,
                pending_resign_done,
                bool(self.is_online_connected),
            )
        else:
            can_accept = False
            can_new = (len(self.history) > 0) or self.game_over
            new_btn_new_sig = ("offline", can_new, is_dark)

        force_apply = mode == "Online" and (
            getattr(self, "_opp_resigned", False)
            or getattr(self, "_i_resigned", False)
        )
        if force_apply or getattr(self, '_last_btn_new_sig', None) != new_btn_new_sig:
            if hasattr(self, 'btn_new') and self.btn_new.winfo_exists():
                if can_accept:
                    # Người nhận yêu cầu đầu hàng → CHẤP NHẬN trên nút VÁN MỚI
                    self.btn_new.configure(
                        text=self.t("accept_btn"),
                        state="normal",
                        fg_color="#166534",
                        hover_color="#15803d",
                        text_color="white",
                    )
                elif not can_new:
                    self.btn_new.configure(
                        text=self.t("new_game"),
                        state="disabled",
                        fg_color=disabled_bg,
                        hover_color=disabled_bg,
                        text_color=disabled_fg,
                    )
                else:
                    self.btn_new.configure(
                        text=self.t("new_game"),
                        state="normal",
                        fg_color="#e74c3c",
                        hover_color="#c0392b",
                        text_color="white",
                    )
            self._last_btn_new_sig = new_btn_new_sig

        # 2. Nếu là chế độ Online, vô hiệu hóa nút Tạm dừng/Bắt đầu và cập nhật nút Đầu hàng
        if mode == "Online":
            self.btn_pause_resume.configure(state="disabled", fg_color=disabled_bg, text_color=disabled_fg)
            self.update_resign_button()
            return

        # 3. Xử lý cho các chế độ Offline (Ultra-AI, 2 Người, AI vs AI)
        if self.game_over: btn_text, btn_fg, btn_hover, btn_state = self.t("start"), "#27ae60", "#2ecc71", "normal"
        elif len(self.history) == 0:
            if mode == "AI vs AI":
                if not self.is_ai_match_paused: btn_text, btn_fg, btn_hover, btn_state = self.t("pause"), "#e74c3c", "#c0392b", "normal"
                else: btn_text, btn_fg, btn_hover, btn_state = self.t("start"), "#27ae60", "#2ecc71", "normal"
            else: btn_text, btn_fg, btn_hover, btn_state = self.t("start"), disabled_bg, disabled_bg, "disabled"
        else:
            btn_text, btn_fg, btn_hover, btn_state = (self.t("resume") if self.is_ai_match_paused else self.t("pause")), ("#27ae60" if self.is_ai_match_paused else "#e74c3c"), ("#2ecc71" if self.is_ai_match_paused else "#c0392b"), "normal"

        new_pause_sig = (btn_text, btn_fg, btn_hover, btn_state, is_dark)
        if getattr(self, '_last_pause_sig', None) != new_pause_sig:
            self.btn_pause_resume.configure(text=btn_text, fg_color=btn_fg, hover_color=btn_hover, text_color="white" if btn_state == "normal" else disabled_fg, state=btn_state)
            self._last_pause_sig = new_pause_sig

    def update_symbol_auto_button(self):
        """Cập nhật nút X/O và nút Tự động.

        Tất cả tab: Tự động BẬT → vô hiệu hóa X/O; Tự động TẮT → X/O bấm được, Auto xám.
        Online thêm: đang trong trận (đã có nước) → khóa cả hai.
        Ultra-AI / 2 Người / AI vs AI: vào trận vẫn không bị khóa vì nước đi.
        """
        if not hasattr(self, "btn_toggle_symbol"):
            return
        try:
            is_online = self.game_mode_var.get() == "Online"
            # Chỉ Online mới khóa khi đang trong trận
            locked = False
            if is_online:
                locked = (
                    self.is_online_connected
                    and not self.game_over
                    and len(self.history) > 0
                )

            auto_on = bool(self.auto_rotate_var.get())
            sym = self.player_symbol_var.get()

            # --- Nút X / O ---
            # Auto bật → vô hiệu hóa X/O (mọi tab). Online đang trận → khóa luôn.
            # Luôn tô màu đúng theo phe: X = xanh, O = đỏ (kể cả khi disabled).
            symbol_disabled = locked or auto_on
            if sym == "X":
                x_fg = "#2980b9" if self.is_dark_mode else "#3498db"
                x_hover = "#2471a3" if self.is_dark_mode else "#2980b9"
                self.btn_toggle_symbol.configure(
                    state="disabled" if symbol_disabled else "normal",
                    text="X",
                    fg_color=x_fg,
                    hover_color=x_hover,
                    text_color="white",
                )
            else:
                o_fg = "#c0392b" if self.is_dark_mode else "#e74c3c"
                o_hover = "#a93226" if self.is_dark_mode else "#c0392b"
                self.btn_toggle_symbol.configure(
                    state="disabled" if symbol_disabled else "normal",
                    text="O",
                    fg_color=o_fg,
                    hover_color=o_hover,
                    text_color="white",
                )

            # --- Nút Tự động ---
            if not hasattr(self, "btn_auto_rotate"):
                return
            if locked:
                self.btn_auto_rotate.configure(
                    state="disabled",
                    text="🔄"
                )
            elif auto_on:
                self.btn_auto_rotate.configure(
                    state="normal",
                    text="🔄",
                    fg_color="#27ae60",
                    hover_color="#2ecc71",
                    text_color="white"
                )
            else:
                # Auto tắt: xám (vô hiệu giao diện), vẫn bấm được để bật lại
                self.btn_auto_rotate.configure(
                    state="normal",
                    text="🔄",
                    fg_color="#475569" if self.is_dark_mode else "#94a3b8",
                    hover_color="#64748b" if self.is_dark_mode else "#64748b",
                    text_color="white"
                )
        except Exception:
            pass

    def _can_change_symbol_or_auto(self):
        """Cho phép đổi phe/auto hay không."""
        if self.is_ai_thinking or getattr(self, '_is_waiting_online', False):
            return False
        mode = self.game_mode_var.get()
        if mode == "Online":
            # Online: khóa khi đang trong trận
            if self.is_online_connected and not self.game_over and len(self.history) > 0:
                return False
            return True
        # Ultra-AI / 2 Người / AI vs AI: luôn cho đổi (kể cả đang trong trận)
        return True

    def toggle_symbol_only(self):
        """Đổi X ↔ O. Chọn X/O thủ công sẽ tắt Tự động (loại trừ lẫn nhau mọi tab)."""
        if not self._can_change_symbol_or_auto():
            return

        new_sym = "O" if self.player_symbol_var.get() == "X" else "X"
        mode = self.game_mode_var.get()

        if mode == "Online":
            # Chọn X/O thủ công → tắt auto
            self.set_online_symbol(new_sym, auto_rotate=False, refresh=True)
            self.send_online_symbol_update()
            opp = self.opposite_symbol(new_sym)
            self.display_status("your_piece", color="#3498db", format_args=[new_sym, opp])
        else:
            self.player_symbol_var.set(new_sym)
            self.auto_rotate_var.set(False)  # chọn X/O → tắt auto
            self.apply_symbols()
            self.update_symbol_auto_button()
            self.save_settings()

    def toggle_auto_only(self):
        """Chỉ bật/tắt Tự động, không đổi X/O hiện tại."""
        if not self._can_change_symbol_or_auto():
            return

        self.auto_rotate_var.set(not bool(self.auto_rotate_var.get()))
        mode = self.game_mode_var.get()

        if mode == "Online":
            # Gửi auto_rotate mới kèm symbol hiện tại
            self.send_online_symbol_update()
            self.update_symbol_auto_button()
            key = "auto_rotate_on" if self.auto_rotate_var.get() else "auto_rotate_off"
            self.display_status(key, color="#f39c12")
        else:
            self.update_symbol_auto_button()
            self.save_settings()

    # Giữ tên cũ để tương thích
    def toggle_symbol_auto_action(self):
        self.toggle_symbol_only()

    def toggle_symbol_action(self):
        self.toggle_symbol_only()

    def refresh_mode_visibility(self):
        mode = self.game_mode_var.get()
        
        if mode == "Online":
            # Chat nằm ngang ở khoảng trống bên trái cụm 4 nút tiện ích,
            # nên không cần mở rộng chiều cao của khu điều khiển.
            self.control_frame.configure(height=175)
            # Giữ nguyên nút chọn quân X/O trong chế độ Online
            if not self.symbol_frame.winfo_ismapped():
                self.symbol_frame.pack(side="left", padx=(4, 0), fill="y", anchor="n")

            # Ẩn độ khó
            self.row3.pack_forget()

            # Hiện khung Online (Tên + Mã phòng)
            self.online_room_frame.pack(anchor="w", pady=(0, 4), before=self.row4)

            # Ẩn các nút: Bắt đầu, Lùi, Tiến, Gợi ý
            self.btn_pause_resume.pack_forget()
            self.btn_undo.pack_forget()
            self.btn_redo.pack_forget()
            self.btn_hint.pack_forget()

            # Online: VÁN MỚI + ĐẦU HÀNG / CHẤP NHẬN
            self.btn_new.pack(side="left", padx=(0, 8))
            if hasattr(self, "btn_resign"):
                self.btn_resign.pack(side="left", padx=(0, 8))
                self.update_resign_button()
            if hasattr(self, "lbl_resign_countdown"):
                # Chỉ hiện khi đang có yêu cầu pending
                if (getattr(self, "_i_resigned", False) or getattr(self, "_opp_resigned", False)) and not self.game_over:
                    self.lbl_resign_countdown.pack(side="left", padx=(0, 8))

            # Chat luôn hiện trong tab Online, ở khoảng trống bên trái 4 nút tiện ích.
            if hasattr(self, "chat_frame") and not self.chat_frame.winfo_ismapped():
                self.chat_frame.pack(side="right", padx=(0, 4), pady=(8, 0), anchor="ne")
            self._chat_open = True

            # Nếu chưa có quân thì mở nút thời gian, đã có quân thì khóa
            self.set_time_controls_enabled(not bool(self.history) and not self.game_over)

        else:
            self.control_frame.configure(height=175)
            # Hiện lại khung chọn quân
            if not self.symbol_frame.winfo_ismapped():
                self.symbol_frame.pack(side="left", padx=(4, 0), fill="y", anchor="n")

            # Ẩn khung Online
            self.online_room_frame.pack_forget()

            # Hiện lại hàng độ khó
            self.row3.pack(anchor="w", fill="x", pady=(0, 4), before=self.row4)

            # Ẩn nút đầu hàng khi rời Online
            if hasattr(self, "btn_resign"):
                self.btn_resign.pack_forget()
            if hasattr(self, "lbl_resign_countdown"):
                self.lbl_resign_countdown.pack_forget()
                self.lbl_resign_countdown.configure(text="")
            self._stop_resign_countdown()

            # Hiện lại các nút điều khiển
            self.btn_new.pack(side="left", padx=(0, 8))
            self.btn_pause_resume.pack(side="left", padx=(0, 8))
            self.btn_undo.pack(side="left", padx=(0, 8))
            self.btn_redo.pack(side="left", padx=(0, 8))

            # Rời Online thì ẩn bảng chat.
            if hasattr(self, "chat_frame"):
                self.chat_frame.pack_forget()
                self._chat_open = False

            # Mở lại nút thời gian khi không còn Online
            self.set_time_controls_enabled(True)

            if mode == "AI vs AI":
                self.diff_single_frame.pack_forget()
                self.diff_vs_frame.pack(side="left")
                self.btn_hint.pack_forget()
            elif mode == "2 Người":
                self.diff_vs_frame.pack_forget()
                self.diff_single_frame.pack(side="left")
                self.lbl_diff.configure(text_color="gray")
                self.diff_menu.configure(state="disabled")
                self.btn_hint.pack(side="left", padx=(0, 8))
            else:  # Ultra-AI
                self.diff_vs_frame.pack_forget()
                self.diff_single_frame.pack(side="left")
                self.lbl_diff.configure(text_color=("black", "white"))
                self.diff_menu.configure(state="normal")
                self.btn_hint.pack(side="left", padx=(0, 8))

        self.update_pause_btn_state()

    def toggle_chat_panel(self):
        # Giữ hàm để tương thích với code cũ; Chat luôn hiển thị khi Online.
        if self.game_mode_var.get() != "Online" or not hasattr(self, "chat_frame"):
            return
        if not self.chat_frame.winfo_ismapped():
            self.chat_frame.pack(side="right", padx=(0, 8), pady=(0, 0), anchor="ne")
        self._chat_open = True
        try:
            self.chat_entry.focus_set()
        except Exception:
            pass

    def append_chat(self, name, text, is_self=False):
        if not hasattr(self, "chat_box"):
            return
        self.chat_box.configure(state="normal")
        prefix = self.t("your_name") if is_self else (name or "???")
        
        # Kiểm tra nếu khung chat đang trống thì không thêm \n
        if self.chat_box.get("1.0", "end-1c") == "":
            self.chat_box.insert("end", f"{prefix}: {text}")
        else:
            self.chat_box.insert("end", f"\n{prefix}: {text}")
            
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def send_chat_message(self, event=None):
        if not hasattr(self, "chat_entry"):
            return "break"
            
        msg = self.chat_entry.get().strip()
        
        if msg:
            if len(msg) > 120:
                msg = msg[:120]
            self.chat_entry.delete(0, "end")
            my_name = self.player_name_var.get().strip() or self.t("your_name")

            # Hiển thị ngay tin nhắn của mình. Server cũng broadcast lại tin nhắn
            # cho chính người gửi, nên lưu một bản chờ để bỏ qua bản echo đó.
            if not hasattr(self, "_pending_chat_messages"):
                self._pending_chat_messages = []
            self._pending_chat_messages.append((my_name, msg))
            self.append_chat(my_name, msg, is_self=True)

            if self.ws and self.is_online_connected:
                try:
                    self.ws.send(json.dumps({
                        "type": "chat",
                        "text": msg,
                        "name": my_name
                    }))
                except Exception:
                    # Gửi thất bại thì bỏ bản chờ để không ảnh hưởng tin nhắn sau.
                    try:
                        self._pending_chat_messages.remove((my_name, msg))
                    except ValueError:
                        pass

        # Trả focus về cửa sổ chính để làm mất con trỏ nhấp nháy ở ô chat
        self.root.focus_set()
        
        # Chặn sự kiện nổi bọt
        return "break"

    def clear_chat(self):
        if hasattr(self, "chat_box"):
            self.chat_box.configure(state="normal")
            self.chat_box.delete("1.0", "end")
            self.chat_box.insert("1.0", self.t("chat_empty"), "sys_msg")
            self.chat_box.configure(state="disabled")

    def exit_online_mode(self):
        self._send_leave_and_close()
        self.is_online_connected = False
        self._is_waiting_online = False
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        
        # === MỞ KHÓA VÀ KHÔI PHỤC LẠI KHẢ NĂNG NHẬP KHI THOÁT ===
        normal_color = ("black", "white")
        self.name_entry.configure(text_color=normal_color)
        self.room_entry.configure(text_color=normal_color)
        self.name_entry.unbind("<Key>")
        self.name_entry.unbind("<Button-1>")
        self.name_entry.bind("<FocusOut>", self.save_settings)
        self.room_entry.unbind("<Key>")
        self.room_entry.unbind("<Button-1>")
        self.btn_join.configure(state="normal")
        # ========================================================

        self.stop_thinking_animation()
        self.modern_canvas.configure(cursor="hand2")
        self.update_mode_buttons()
        self.set_time_controls_enabled(True)  # Mở lại nút thời gian khi thoát Online
        self.new_game()

    def new_game(self):
        # Invalidate any worker that may still be using the previous engine/game.
        self._ai_generation += 1
        self.stop_thinking_animation()
        if self.turn_timer_job:
            self.root.after_cancel(self.turn_timer_job); self.turn_timer_job = None
        if self.engine: self.engine.stop(); self.engine = None
        
        # === TỰ ĐỘNG ĐẢO QUÂN Ở TẤT CẢ CÁC CHẾ ĐỘ KHI KẾT THÚC VÁN NẾU BẬT TÍNH NĂNG ===
        # Online: KHÔNG tự đổi Phe tại client. Server chỉ đổi Phe khi cả hai
        # người chơi rematch; đây là điểm duy nhất quyết định Phe cho ván mới.
        # Tự động đổi X/O áp dụng cho cả Ultra-AI, 2 Người và AI vs AI.
        # Online không tự đổi tại client; server quyết định phe khi rematch.
        if self.game_mode_var.get() in ("Ultra-AI", "2 Người", "AI vs AI") and self.game_over and self.auto_rotate_var.get():
            current_sym = self.player_symbol_var.get()
            new_sym = "O" if current_sym == "X" else "X"
            self.player_symbol_var.set(new_sym)
        # ==============================================================================

        self.rebuild_board_widgets()
        
        self.game_over = self.is_ai_thinking = self.engine_synced = False
        self.is_ai_match_paused = True
        self.last_move = self.hover_cell = self.hint_cell = None
        self.winning_cells, self.history = [], []
        self.ghost_winning_cells = []
        self.redo_stack = []
        self.current_turn = HUMAN
            
        self.modern_canvas.configure(cursor="hand2")
        self.apply_symbols(); self.update_ui(); self.init_match_timers(); self.update_pause_btn_state()

        mode = self.game_mode_var.get()
        if mode == "Online":
            if not self.is_online_connected:
                self.display_status("online_enter_room", color="#f39c12")
            return
            
        if mode == "2 Người": self.update_turn_status(mode_type="2p", symbol=self.player_symbol); return
        if mode == "AI vs AI":
            self.display_status("ai_ready", color="#f39c12")
            if self.init_engine(): self.engine_synced = True
            return

        if self.init_engine(): self.engine_synced = True; self.update_turn_status(symbol=self.player_symbol)

    def toggle_pause_resume(self, event=None):
        mode = self.game_mode_var.get()
        if mode == "Online": return
        if self.game_over or (mode == "AI vs AI" and not self.history):
            self.new_game()
            self.is_ai_match_paused = False
            self.update_pause_btn_state()
            if mode == "AI vs AI" or (mode == "Ultra-AI" and self.current_turn == AI):
                self.is_ai_thinking = True
                self.modern_canvas.configure(cursor="watch")
                self.start_thinking_animation("ai_thinking" if mode == "AI vs AI" else "ai_taking_over")
                self._start_ai_board_sync_worker()
            return
        if not self.history: return
        self.is_ai_match_paused = not self.is_ai_match_paused
        
        if self.is_ai_match_paused:
            self._ai_generation += 1
            if self.timer_job: self.root.after_cancel(self.timer_job); self.timer_job = None
            if self.turn_timer_job: self.root.after_cancel(self.turn_timer_job); self.turn_timer_job = None
            self.update_pause_btn_state(); self.stop_thinking_animation()
            if mode == "AI vs AI": self.is_ai_thinking = False
            self.display_status("ai_match_paused", color="#f39c12")
            self.modern_canvas.configure(cursor="hand2")
        else:
            self.update_pause_btn_state()
            if mode == "AI vs AI":
                self.update_turn_status(mode_type="ai_vs_ai")
                self.is_ai_thinking = True
                self.modern_canvas.configure(cursor="watch")
                self.start_thinking_animation("ai_thinking")
                if not self.history: self.engine_synced = False
                
                # Chỉ khởi động MỘT worker. ai_board_sync_turn() tự đồng bộ
                # engine và tiếp tục đúng lượt hiện tại. Không chạy song song
                # ai_turn()/ai_board_sync_turn() vì hai worker có thể cùng
                # stop/restart engine và khiến AI đánh trùng hoặc lệch lượt.
                self._start_ai_board_sync_worker()
            elif mode == "2 Người": self.update_turn_status(mode_type="2p")
            else:
                self.update_turn_status()
                if self.current_turn == AI:
                    self.is_ai_thinking = True
                    self.modern_canvas.configure(cursor="watch")
                    self.start_thinking_animation("ai_taking_over")
                    self._start_ai_board_sync_worker()
            if len(self.history) > 0 and self.get_selected_time_limit_seconds() > 0 and not self.timer_job: self.run_match_timer()
            if not self.game_over and not self.turn_timer_job: self.start_turn_timer()

    def get_theme_btn_icon(self):
        return "🌙" if self.is_dark_mode else "☀️"

    def get_theme_btn_text(self):
        return self.get_theme_btn_icon()


    def toggle_theme(self):
        def action():
            self.theme_var.set("Sáng" if self.is_dark_mode else "Tối")
            ctk.set_appearance_mode("dark" if self.is_dark_mode else "light")
            # Xóa cache ảnh quân để load đúng biến thể light/dark theo theme mới
            self._piece_photo_cache = {}
            if getattr(self, "_use_image_icons", False):
                self.btn_theme.configure(image=self.icon_theme_dark if self.is_dark_mode else self.icon_theme_light, text="")
            else:
                self.btn_theme.configure(text=self.get_theme_btn_icon())
            self.apply_symbols()
            self.update_mode_buttons()
            self.update_time_button_colors()
            self.update_ui()
            if sys.platform == "win32":
                try:
                    hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                    dark_mode_val = ctypes.c_int(1 if self.is_dark_mode else 0)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode_val), ctypes.sizeof(dark_mode_val))
                except Exception:
                    pass

            # Force reset signature để nút VÁN MỚI + BẮT ĐẦU nhận màu đúng theo theme mới
            self._last_pause_sig = self._last_btn_new_sig = None
            self.update_pause_btn_state()

            self.save_settings()
        self._transition_with_fade(action)

    def change_theme_init(self):
        ctk.set_appearance_mode("dark" if self.is_dark_mode else "light")
        if getattr(self, "_use_image_icons", False):
            self.btn_theme.configure(image=self.icon_theme_dark if self.is_dark_mode else self.icon_theme_light, text="")
        else:
            self.btn_theme.configure(text=self.get_theme_btn_icon())
        self.apply_symbols()
        self.update_mode_buttons()
        self.update_time_button_colors()
        self.update_ui()
        self._last_pause_sig = self._last_btn_new_sig = None
        self.update_pause_btn_state()

    def get_lang_btn_icon(self):
        return "🇻🇳" if self.lang_var.get() == "VI" else "🇬🇧"

    def get_lang_btn_text(self):
        return self.get_lang_btn_icon()

    def get_sound_btn_icon(self):
        return "🔊" if self.sound_enabled else "🔇"


    def toggle_language(self):
        self.lang_var.set("EN" if self.lang_var.get() == "VI" else "VI")
        if getattr(self, "_use_image_icons", False):
            self.btn_lang.configure(image=self.icon_lang_vi if self.lang_var.get() == "VI" else self.icon_lang_en, text="")
        self.change_language_action()

    def change_language_action(self):
        lang = self.lang_var.get()
        self.root.title(self.t("app_title"))

        # --- Nhãn / nút tĩnh ---
        for widget, key in {
            self.lbl_mode: "mode", self.btn_mode_ai: "mode_ai", self.btn_mode_2p: "mode_2p",
            self.btn_mode_ai_vs_ai: "mode_ai_vs_ai",
            self.lbl_board: "board", self.lbl_diff: "diff", self.lbl_diff_x: "diff_x",
            self.lbl_diff_o: "diff_o",
            self.lbl_rule: "rule", self.btn_new: "new_game", self.btn_hint: "hint",
            self.btn_undo: "undo", self.btn_redo: "redo",
            self.lbl_name: "name_label", self.lbl_room: "room_label",
            self.btn_join: "join_room", self.btn_leave_online: "leave_online",
        }.items():
            if hasattr(widget, "configure"):
                try:
                    widget.configure(text=self.t(key))
                except Exception:
                    pass

        if hasattr(self, "btn_mode_online"):
            try:
                self.btn_mode_online.configure(text=self.t("mode_online"))
            except Exception:
                pass

        # Nút Đầu hàng / Chấp nhận
        if hasattr(self, "btn_resign"):
            self.update_resign_button()

        # Nhãn thời gian (icon cố định)
        if hasattr(self, "lbl_time_limit"):
            try:
                self.lbl_time_limit.configure(text="⏱")
            except Exception:
                pass

        # Tiêu đề tỉ số
        if hasattr(self, "lbl_score_dash"):
            try:
                self.lbl_score_dash.configure(text=self.t("score_title"))
            except Exception:
                pass

        # Chat
        if hasattr(self, "btn_chat"):
            try:
                self.btn_chat.configure(text=self.t("chat_button"))
            except Exception:
                pass
        if hasattr(self, "chat_title"):
            try:
                self.chat_title.configure(text=self.t("chat_title"))
            except Exception:
                pass
        if hasattr(self, "chat_entry"):
            try:
                self.chat_entry.configure(placeholder_text=" ")
                self.chat_entry.configure(placeholder_text=self.t("chat_placeholder"))
            except Exception:
                pass
        if hasattr(self, "chat_box"):
            try:
                content = self.chat_box.get("1.0", "end-1c").strip()
                known_empty = {
                    "",
                    "Hãy trò chuyện cùng đối thủ ở đây",
                    "Chat with your opponent here",
                }
                known_empty.add(LANG.get("VI", {}).get("chat_empty", ""))
                known_empty.add(LANG.get("EN", {}).get("chat_empty", ""))
                if content in known_empty:
                    self.chat_box.configure(state="normal")
                    self.chat_box.delete("1.0", "end")
                    self.chat_box.insert("1.0", self.t("chat_empty"), "sys_msg")
                    self.chat_box.configure(state="disabled")
            except Exception:
                pass

        # Nút tạm dừng / ván mới — force refresh để lấy text ngôn ngữ mới
        if hasattr(self, "btn_pause_resume") and self.btn_pause_resume.winfo_exists():
            self._last_pause_sig = self._last_btn_new_sig = None
            self.update_pause_btn_state()

        # Icon góc
        if getattr(self, "_use_image_icons", False):
            try:
                self.btn_sound.configure(
                    image=self.icon_sound_on if self.sound_enabled else self.icon_sound_off, text=""
                )
                self.btn_lang.configure(
                    image=self.icon_lang_vi if self.lang_var.get() == "VI" else self.icon_lang_en, text=""
                )
                self.btn_theme.configure(
                    image=self.icon_theme_dark if self.is_dark_mode else self.icon_theme_light, text=""
                )
                style_img = (
                    self.icon_style_on
                    if self.ui_style_var.get() in ["Hiện đại", "Modern"]
                    else self.icon_style_off
                )
                self.btn_style.configure(image=style_img, text="")
            except Exception:
                pass
        else:
            try:
                for btn, txt in zip(
                    (self.btn_style, self.btn_theme, self.btn_lang, self.btn_sound),
                    (
                        self.get_style_btn_icon(),
                        self.get_theme_btn_icon(),
                        self.get_lang_btn_icon(),
                        self.get_sound_btn_icon(),
                    ),
                ):
                    btn.configure(text=txt)
            except Exception:
                pass

        if hasattr(self, "btn_toggle_symbol"):
            self.update_symbol_auto_button()

        # Độ khó + luật (dịch option hiện tại)
        fallback_diff = {
            "Cao thủ (0.2s)": 200,
            "Đỉnh cao (5s)": 5000,
            "Siêu cấp (12s)": 12000,
            "Vô cực (20s)": 20000,
        }
        d_old = DIFFICULTY.get("VI" if lang == "EN" else "EN", fallback_diff)
        d_new = DIFFICULTY.get(lang, fallback_diff)
        if not isinstance(d_old, dict):
            d_old = fallback_diff
        if not isinstance(d_new, dict):
            d_new = fallback_diff
        old_keys = list(d_old.keys())
        new_keys = list(d_new.keys())
        for var in (self.difficulty_var, self.difficulty_x_var, self.difficulty_o_var):
            self._translate_option(var, old_keys, new_keys)
        for menu in (self.diff_menu, self.diff_x_menu, self.diff_o_menu):
            try:
                menu.configure(values=new_keys)
            except Exception:
                pass

        fallback_rules = ["Tiêu chuẩn", "Chặn 2 đầu"]
        old_rules = LANG.get("EN" if lang == "VI" else "VI", {}).get("rules_list", fallback_rules)
        new_rules = LANG.get(lang, {}).get("rules_list", fallback_rules)
        if not isinstance(old_rules, list):
            old_rules = fallback_rules
        if not isinstance(new_rules, list):
            new_rules = fallback_rules
        self._translate_option(self.rule_var, old_rules, new_rules)
        try:
            self.rule_menu.configure(values=new_rules)
        except Exception:
            pass

        # --- Status / chú thích: luôn dựng lại theo trạng thái hiện tại ---
        self._refresh_status_for_language()

        self.update_score_display()
        self.update_timer_display()
        self.save_settings()

    def _refresh_status_for_language(self):
        """Dựng lại dòng status theo ngôn ngữ mới (không giữ raw text cũ)."""
        mode = self.game_mode_var.get()

        # Đang animation suy nghĩ / chờ → cập nhật text ngay, animation tự chạy tiếp
        if self.is_ai_thinking or getattr(self, "_is_waiting_online", False):
            if mode == "Online" and getattr(self, "_is_waiting_online", False):
                self.display_status("online_waiting", color="#f39c12")
                return
            if getattr(self, "current_thinking_msg_key", None) and not getattr(self, "_is_raw_thinking", False):
                # Cập nhật dòng status ngay (không đợi tick animation)
                dots = "." * (getattr(self, "dot_count", 0) % 4)
                spaces = " " * (3 - len(dots))
                base = self.t(self.current_thinking_msg_key)
                self.status.configure(
                    text=f"{base}{dots}{spaces}",
                    text_color=self._status_text_color("#ef4444"),
                )
                return
            return

        # Online: ưu tiên trạng thái resign / rematch / lượt
        if mode == "Online":
            if getattr(self, "_i_resigned", False):
                self.display_status("you_resigned_wait", color="#f39c12")
                return
            if getattr(self, "_opp_resigned", False):
                name = getattr(self, "_resign_name", "") or self.display_opponent_name()
                if self.game_over:
                    self.display_status("opp_resigned_press_accept", color="#f39c12", format_args=[name])
                else:
                    self.display_status("resign_offer_status", color="#f39c12", format_args=[name])
                return
            if self.my_ready_for_rematch and not self.opponent_ready_for_rematch:
                self.display_status("online_ready_wait", color="#f39c12")
                return
            if self.opponent_ready_for_rematch and not self.my_ready_for_rematch:
                self.display_status("opp_ready_press_new", color="#2ecc71")
                return
            if self.my_ready_for_rematch and self.opponent_ready_for_rematch:
                self.display_status("both_ready", color="#2ecc71")
                return
            if self.game_over:
                data = getattr(self, "_current_status_data", {}) or {}
                if data.get("type") == "static" and data.get("key"):
                    self.display_status(
                        data["key"],
                        color=data.get("color"),
                        format_args=data.get("format_args"),
                        prefix_key=data.get("prefix_key"),
                    )
                elif data.get("type") == "turn":
                    self.update_turn_status(mode_type=data.get("mode_type"), symbol=data.get("symbol"))
                else:
                    # Thắng/thua online thường lưu raw — cố gắng map lại nếu có winner trong data
                    self.update_turn_status(mode_type="online")
                return
            if self.is_online_connected and not getattr(self, "_is_waiting_online", False):
                self.update_turn_status(mode_type="online")
                return
            if not self.is_online_connected:
                data = getattr(self, "_current_status_data", {}) or {}
                if data.get("type") == "static" and data.get("key"):
                    self.display_status(
                        data["key"],
                        color=data.get("color"),
                        format_args=data.get("format_args"),
                        prefix_key=data.get("prefix_key"),
                    )
                return

        # Offline / chung: ưu tiên metadata đã lưu
        data = getattr(self, "_current_status_data", {}) or {}
        if data.get("type") == "turn":
            self.update_turn_status(mode_type=data.get("mode_type"), symbol=data.get("symbol"))
            return
        if data.get("type") == "static" and data.get("key"):
            self.display_status(
                data["key"],
                color=data.get("color"),
                format_args=data.get("format_args"),
                prefix_key=data.get("prefix_key"),
            )
            return
        # Fallback theo trạng thái ván
        if self.game_over:
            return
        if mode == "AI vs AI" and self.is_ai_match_paused and not self.history:
            self.display_status("ai_ready", color="#f39c12")
        elif mode == "AI vs AI":
            self.update_turn_status(mode_type="ai_vs_ai")
        elif mode == "2 Người":
            self.update_turn_status(mode_type="2p")
        else:
            self.update_turn_status()

    def _translate_option(self, var, old_options, new_options):
        if not old_options or not new_options: return
        current = var.get()
        var.set(new_options[old_options.index(current)] if current in old_options else new_options[0])

    def get_style_btn_icon(self):
        # Hiện đại = mắt, Cổ điển = bàn cờ đơn giản
        return "👁" if self.ui_style_var.get() in ["Hiện đại", "Modern"] else "▦"

    def get_style_btn_text(self):
        return self.get_style_btn_icon()

    def toggle_ui_style(self):
        self.ui_style_var.set("Cổ điển" if self.ui_style_var.get() in ["Hiện đại", "Modern"] else "Hiện đại")
        if getattr(self, "_use_image_icons", False):
            style_img = self.icon_style_on if self.ui_style_var.get() in ["Hiện đại", "Modern"] else self.icon_style_off
            self.btn_style.configure(image=style_img, text="")
        else:
            self.btn_style.configure(text=self.get_style_btn_icon())
        self.adjust_board_size()
        self.modern_canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.save_settings()

    def change_ui_style_init(self):
        self.adjust_board_size()
        self.modern_canvas.place(relx=0.5, rely=0.5, anchor="center")

    def on_window_resize(self, event):
        if event.widget == self.root:
            if getattr(self, '_last_win_w', 0) == self.root.winfo_width() and getattr(self, '_last_win_h', 0) == self.root.winfo_height(): return
            self._last_win_w, self._last_win_h = self.root.winfo_width(), self.root.winfo_height()
            if self._resize_timer: self.root.after_cancel(self._resize_timer)
            self._resize_timer = self.root.after(15, self.adjust_board_size)

    def _calculate_board_geometry(self):
        available_w = max(350, self.root.winfo_width() - 15)
        control_h = self.control_frame.winfo_reqheight() if hasattr(self, 'control_frame') else 130
        status_h = self.status_container.winfo_reqheight() if hasattr(self, 'status_container') else 65
        # Giảm trừ thêm một chút ở available_h để canvas tự dịch không gian lên trên
        available_h = max(350, self.root.winfo_height() - control_h - status_h - 10)
        
        if self.ui_style_var.get() in ["Hiện đại", "Modern"]:
            spans = max(1, self.board_size - 1)
        else:
            spans = max(1, self.board_size)
            
        self.cell_size = max(24, min(available_w, available_h) - 2 * self.board_margin) // spans
        self.board_pixels = 2 * self.board_margin + spans * self.cell_size

    def adjust_board_size(self):
        self._calculate_board_geometry()
        self.modern_canvas.config(width=self.board_pixels, height=self.board_pixels)
        # Bổ sung lệnh place này để mỗi khi đổi kích thước, canvas được ép nằm giữa tâm container
        self.modern_canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.update_ui()

    def rebuild_board_widgets(self):
        requested_size = int(self.board_size_var.get().split("x")[0])
        if self.game_mode_var.get() == "Ultra-AI" and requested_size > 20:
            messagebox.showwarning(self.t("warning_title"), self.t("limit_warn"))
            self.board_size_var.set("20x20"); requested_size = 20
        self.board_size = requested_size
        self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
        self.adjust_board_size()

    def on_board_size_change(self, value=None):
        if self.game_mode_var.get() == "Online" and (self.history or self.game_over):
            return
        # AI modes + Chặn 2 đầu không cho chọn 20x20
        if self._should_force_15x15_for_caro_ai() and self.board_size_var.get() == "20x20":
            self.board_size_var.set("15x15")
            messagebox.showinfo(
                self.t("warning_title"),
                "Luật Chặn 2 đầu + chế độ AI chỉ hỗ trợ bàn 15x15 (AlphaGomoku).\nĐã tự động chuyển về 15x15."
            )
        self.save_settings()
        # Đồng bộ ngay lập tức cho cả hai bên. Server sẽ broadcast lại trạng thái cuối cùng.
        if self.game_mode_var.get() == "Online":
            self.send_online_settings()
            # Online: chỉ rebuild board, không gọi new_game (tránh reset connection)
            self.rebuild_board_widgets()
            self.update_ui()
        else:
            self.new_game()

    def _cell_from_canvas(self, event):
        x, y, m, s = self.modern_canvas.canvasx(event.x), self.modern_canvas.canvasy(event.y), self.board_margin, self.cell_size
        if self.ui_style_var.get() in ["Hiện đại", "Modern"]:
            col, row = int(round((x - m) / s)), int(round((y - m) / s))
            if 0 <= row < self.board_size and 0 <= col < self.board_size:
                if abs(x - (m + col * s)) <= s * 0.48 and abs(y - (m + row * s)) <= s * 0.48: 
                    return (row, col)
        else:
            col, row = int((x - m) // s), int((y - m) // s)
            if 0 <= row < self.board_size and 0 <= col < self.board_size: 
                return (row, col)
        return None

    def on_canvas_motion(self, event):
        if self.game_over or self.is_ai_thinking or self.game_mode_var.get() == "AI vs AI" or getattr(self, '_is_waiting_online', False): return
        cell = self._cell_from_canvas(event)
        if cell is not None and self.board[cell[0]][cell[1]] != EMPTY: cell = None
        if cell != self.hover_cell: self.hover_cell = cell; self.update_ui()

    def on_canvas_leave(self, event=None):
        if self.hover_cell is not None: self.hover_cell = None; self.update_ui()

    def modern_click(self, event):
        if self.game_mode_var.get() != "AI vs AI":
            if cell := self._cell_from_canvas(event): self.click(*cell)

    def draw_classic_board(self):
        cv = self.modern_canvas
        cv.delete("all")
        bg_color, grid_color, last_move_bg, hover_color = ("#0b141d", "#243447", "#1e3a5f", "#526574") if self.is_dark_mode else ("#f0f0f0", "#b0b0b0", "#fae19c", "#cccccc")
        m, s = self.board_margin, self.cell_size
        end = m + self.board_size * s
        cv.configure(bg=bg_color)

        if self.last_move:
            r, c = self.last_move
            cv.create_rectangle(m + c * s, m + r * s, m + (c + 1) * s, m + (r + 1) * s, fill=last_move_bg, outline="")

        for i in range(self.board_size + 1):
            p = m + i * s
            cv.create_line(p, m, p, end, fill=grid_color, width=1)
            cv.create_line(m, p, end, p, fill=grid_color, width=1)
            
        for wr, wc in self.winning_cells: 
            cv.create_rectangle(m + wc * s, m + wr * s, m + (wc + 1) * s, m + (wr + 1) * s, outline="#ffb300" if self.is_dark_mode else "#e67e22", width=2)
        if self.hint_cell: 
            hr, hc = self.hint_cell
            cv.create_rectangle(m + hc * s, m + hr * s, m + (hc + 1) * s, m + (hr + 1) * s, outline="#f39c12", width=3, dash=(4, 2))

        if self.hover_cell and self.game_mode_var.get() != "AI vs AI" and (self.game_mode_var.get() != "Online" or self.is_online_turn):
            hr, hc = self.hover_cell
            if 0 <= hr < self.board_size and 0 <= hc < self.board_size and self.board[hr][hc] == EMPTY: 
                cv.create_rectangle(m + hc * s + 1, m + hr * s + 1, m + (hc + 1) * s - 1, m + (hr + 1) * s - 1, outline=hover_color, width=2)

        font = ("Segoe UI", max(15, int(s * 0.58)), "bold")
        for r in range(self.board_size):
            for c in range(self.board_size):
                if self.board[r][c] != EMPTY:
                    sym = self.player_symbol if self.board[r][c] == HUMAN else self.ai_symbol
                    color = ("#22d3ee" if sym == "X" else "#ef4444") if self.is_dark_mode else ("#3498db" if sym == "X" else "#e74c3c")
                    cv.create_text(m + c * s + s / 2, m + r * s + s / 2, text=sym, fill=color, font=font)

        # Quân “ma”: các nước đã LÙI vẫn hiện mờ để xem lại chuỗi kết liễu
        self._draw_ghost_moves_classic(cv, m, s, font)

    def draw_modern_board(self):
        cv = self.modern_canvas
        cv.delete("all")
        bg_color, grid_color, dot_color, hover_color, piece_bg_dark = ("#0b141d", "#243447", "#243447", "#526574", "#060e16") if self.is_dark_mode else ("#fafafa", "#b0b0b0", "#b0b0b0", "#888888", "")
        m, s = self.board_margin, self.cell_size
        end = m + (self.board_size - 1) * s
        cv.configure(bg=bg_color)

        for i in range(self.board_size):
            p = m + i * s
            cv.create_line(p, m, p, end, fill=grid_color, width=1)
            cv.create_line(m, p, end, p, fill=grid_color, width=1)

        if self.board_size >= 15:
            mid = self.board_size // 2
            for r, c in [(3, 3), (3, self.board_size - 4), (mid, mid), (self.board_size - 4, 3), (self.board_size - 4, self.board_size - 4)]: 
                cv.create_oval(m + c * s - 3, m + r * s - 3, m + c * s + 3, m + r * s + 3, fill=dot_color, outline="")

        if self.hint_cell: 
            hr, hc = self.hint_cell
            hx, hy, rr = m + hc * s, m + hr * s, max(6, int(s * 0.45))
            cv.create_oval(hx - rr, hy - rr, hx + rr, hy + rr, outline="#f39c12", width=3, dash=(4, 2))

        if self.hover_cell and self.game_mode_var.get() != "AI vs AI" and (self.game_mode_var.get() != "Online" or self.is_online_turn):
            hr, hc = self.hover_cell
            if 0 <= hr < self.board_size and 0 <= hc < self.board_size and self.board[hr][hc] == EMPTY: 
                hx, hy, rr = m + hc * s, m + hr * s, max(4, int(s * 0.18))
                cv.create_oval(hx - rr, hy - rr, hx + rr, hy + rr, outline=hover_color, width=2)

        radius = int(s * 0.45)
        piece_px = max(10, int(s * 0.90))  # đường kính ảnh quân ≈ 90% ô
        for r in range(self.board_size):
            for c in range(self.board_size):
                if self.board[r][c] == EMPTY: continue
                
                # Tọa độ tâm giao điểm (kiểu hiện đại)
                x = m + c * s
                y = m + r * s
                
                is_human_piece = (self.board[r][c] == HUMAN)
                sym = self.player_symbol if is_human_piece else self.ai_symbol

                photo = self._get_piece_photo(sym, piece_px)
                if photo is not None:
                    cv.create_image(x, y, image=photo, anchor="center")
                else:
                    # Fallback hình tròn màu nếu thiếu file ảnh
                    if self.is_dark_mode:
                        cv.create_oval(x - radius - 1, y - radius - 1, x + radius + 1, y + radius + 1, fill=piece_bg_dark, outline="")
                    piece_color = ("#22d3ee" if sym == "X" else "#ef4444") if self.is_dark_mode else ("#3498db" if sym == "X" else "#e74c3c")
                    cv.create_oval(x - radius, y - radius, x + radius, y + radius, fill=piece_color, outline="")
                
                if self.last_move == (r, c): 
                    cv.create_oval(x - max(2, int(s * 0.15)), y - max(2, int(s * 0.15)), x + max(2, int(s * 0.15)), y + max(2, int(s * 0.15)), fill=bg_color, outline="")

        for wr, wc in self.winning_cells: 
            wx, wy = m + wc * s, m + wr * s
            cv.create_oval(wx - radius - 3, wy - radius - 3, wx + radius + 3, wy + radius + 3, outline="#f1c40f", width=3)

        # Quân “ma” + viền thắng mờ khi đang xem lại (LÙI)
        self._draw_ghost_moves_modern(cv, m, s, radius, piece_px, bg_color)

    def _iter_ghost_moves(self):
        """Các nước trong redo_stack (đã LÙI) — vẽ mờ trên ô trống."""
        stack = getattr(self, "redo_stack", None) or []
        for r, c, piece in stack:
            if 0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == EMPTY:
                yield r, c, piece

    def _draw_ghost_moves_classic(self, cv, m, s, font):
        for r, c, piece in self._iter_ghost_moves():
            sym = self.player_symbol if piece == HUMAN else self.ai_symbol
            # ~15% độ nổi — rất mờ
            if self.is_dark_mode:
                color = "#0c4a6e" if sym == "X" else "#450a0a"
            else:
                color = "#bfdbfe" if sym == "X" else "#fecaca"
            cv.create_text(m + c * s + s / 2, m + r * s + s / 2, text=sym, fill=color, font=font)
        for wr, wc in getattr(self, "ghost_winning_cells", []) or []:
            if self.board[wr][wc] == EMPTY:
                cv.create_rectangle(
                    m + wc * s, m + wr * s, m + (wc + 1) * s, m + (wr + 1) * s,
                    outline="#a16207" if self.is_dark_mode else "#f59e0b",
                    width=2, dash=(3, 3),
                )

    def _draw_ghost_moves_modern(self, cv, m, s, radius, piece_px, bg_color):
        for r, c, piece in self._iter_ghost_moves():
            x = m + c * s
            y = m + r * s
            sym = self.player_symbol if piece == HUMAN else self.ai_symbol
            photo = self._get_piece_photo(sym, piece_px, ghost=True)
            if photo is not None:
                cv.create_image(x, y, image=photo, anchor="center")
            else:
                if self.is_dark_mode:
                    color = "#0c4a6e" if sym == "X" else "#450a0a"
                else:
                    color = "#bfdbfe" if sym == "X" else "#fecaca"
                # gray75 = mờ hơn gray50 (gần ~15–25% cảm nhận)
                cv.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=color, outline="", stipple="gray75",
                )
        ghost_line = getattr(self, "ghost_winning_cells", None) or []
        if ghost_line:
            for wr, wc in ghost_line:
                # Chỉ viền mờ nếu ô đó đang là ghost hoặc vẫn còn trên bàn trong chuỗi thắng
                wx, wy = m + wc * s, m + wr * s
                cv.create_oval(
                    wx - radius - 3, wy - radius - 3, wx + radius + 3, wy + radius + 3,
                    outline="#a16207" if self.is_dark_mode else "#f59e0b",
                    width=2, dash=(4, 3),
                )

    def update_ui(self): 
        if self.ui_style_var.get() in ["Hiện đại", "Modern"]:
            self.draw_modern_board()
        else:
            self.draw_classic_board()

    def on_mode_change(self):
        if self.is_ai_thinking or getattr(self, '_is_waiting_online', False): return
        mode = self.game_mode_var.get()
        
        if mode != "Online" and self.ws:
            self._send_leave_and_close()
            
        self.score_me = 0
        self.score_opp = 0
        self.update_score_display()

        if mode in ("Ultra-AI", "AI vs AI") and self.board_size > 20: self.board_size_var.set("20x20"); self.save_settings(); self.new_game(); return

        # AI modes + Chặn 2 đầu → buộc 15x15
        self._enforce_board_for_caro_ai()
        
        self.is_ai_match_paused = not self.history
        self.refresh_mode_visibility(); self.update_mode_buttons(); self.apply_symbols(); self.save_settings()

        if mode == "Online":
            self.new_game()
            return

        if self.game_over or not self.history:
            if mode == "AI vs AI": self.display_status("ai_ready", color="#f39c12")
            else: self.update_turn_status()
            return

        if mode in ("Ultra-AI", "AI vs AI"):
            self.engine_synced, self.is_ai_thinking = False, True
            self.modern_canvas.configure(cursor="watch"); self.start_thinking_animation("ai_taking_over")
            self._start_ai_board_sync_worker()
        else:
            if self.engine: self.engine.stop(); self.engine = None
            self.update_turn_status(mode_type="2p")

    def apply_symbols(self):
        mode = self.game_mode_var.get()
        if mode == "Online":
            self.player_symbol = self.online_symbol if self.online_symbol in ("X", "O") else "X"
            self.ai_symbol = "O" if self.player_symbol == "X" else "X"
            # Không tự thay đổi online_symbol/player_symbol_var ở đây.
            # Đây chỉ là hàm áp dụng trạng thái đã được chốt.
            self.player_symbol_var.set(self.player_symbol)
        elif mode == "2 Người":
            # 2 Người cũng có phe của người chơi: X hoặc O.
            # HUMAN luôn là người đã chọn, AI chỉ là tên nội bộ cho người còn lại.
            if self.player_symbol_var.get() == "X":
                self.player_symbol, self.ai_symbol = "X", "O"
            else:
                self.player_symbol, self.ai_symbol = "O", "X"
        elif mode == "AI vs AI":
            # AI vs AI cũng dùng lựa chọn X/O/Tự động: player_symbol là phe AI 1,
            # ai_symbol là phe AI 2.
            if self.player_symbol_var.get() == "X":
                self.player_symbol, self.ai_symbol = "X", "O"
            else:
                self.player_symbol, self.ai_symbol = "O", "X"
        else:
            if self.player_symbol_var.get() == "X": self.player_symbol, self.ai_symbol = "X", "O"
            else: self.player_symbol, self.ai_symbol = "O", "X"
            
        self.update_ui()
        self.update_score_display()
        
        self.update_symbol_auto_button()
        
        # ĐÃ SỬA: Phân định rõ chế độ AI vs AI để gọi đúng tên AI 1 / AI 2
        if not self.game_over and not self.is_ai_thinking and not getattr(self, '_is_waiting_online', False):
            if mode == "AI vs AI": 
                self.update_turn_status(mode_type="ai_vs_ai")
            elif mode == "2 Người":
                self.update_turn_status(mode_type="2p")
            elif mode != "Online": 
                self.update_turn_status()
                
        self.save_settings()

    def swap_ai_difficulties(self):
        val_x, val_o = self.difficulty_x_var.get(), self.difficulty_o_var.get()
        self.difficulty_x_var.set(val_o); self.difficulty_o_var.set(val_x)
        if hasattr(self, 'diff_x_menu'): self.diff_x_menu.set(val_o)
        if hasattr(self, 'diff_o_menu'): self.diff_o_menu.set(val_x)
        self.save_settings()

    def get_time_turn(self, side=None): 
        mode, diff_map = self.game_mode_var.get(), DIFFICULTY.get(self.lang_var.get(), DIFFICULTY.get("VI", {}))
        if mode == "AI vs AI":
            base = int(diff_map.get(self.difficulty_x_var.get() if (side == "X" if side is not None else len(self.history) % 2 == 0) else self.difficulty_o_var.get(), 200))
        else:
            base = int(diff_map.get(self.difficulty_var.get(), 200))
        return self._scale_time_for_engine(base)

    def _scale_time_for_engine(self, base_ms):
        """Scale thời gian suy nghĩ theo engine.

        Rapfi (NNUE α-β): giữ nguyên — đã tối ưu mạnh ở 0.2s.
        AlphaGomoku (MCTS + rule Caro, CPU): NN chậm, AI vs AI còn restart/BOARD
        mỗi nước → cần timeout thực cao hơn nhiều để có đủ node tính chặn/cờ kép.
        Nhãn UI vẫn 0.2s / 5s...; timeout thực gửi engine cao hơn.
        """
        if self.is_standard_rule or sys.platform != "win32":
            return int(base_ms)
        # Alpha / Chặn 2 đầu — floor cao vì log thực tế chỉ ~1–50 node ở 0.5s
        if base_ms <= 300:
            # Cao thủ 0.2s → 1.5s thực (mục tiêu vài trăm node trở lên)
            return max(int(base_ms * 7.5), 1500)
        if base_ms <= 6000:
            # Đỉnh cao 5s → ~9s
            return int(base_ms * 1.8)
        if base_ms <= 15000:
            # Siêu cấp 12s → ~18s
            return int(base_ms * 1.5)
        # Vô cực 20s → ~28s
        return int(base_ms * 1.4)

    def init_engine(self):
        try:
            eng_path, rule_code = get_engine_path_and_rule(self.is_standard_rule)
            self.engine = UltraAIEngine(eng_path, self.board_size, self.get_time_turn(), rule_code)
            self.engine.start(); return True
        except Exception as e:
            messagebox.showerror(self.t("err_title"), str(e)); self.display_status("engine_err", color="#e74c3c"); return False


    def _stop_resign_countdown(self):
        """Hủy job đếm ngược yêu cầu đầu hàng và ẩn nhãn."""
        job = getattr(self, "_resign_countdown_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._resign_countdown_job = None
        self._resign_deadline_mono = None
        if hasattr(self, "lbl_resign_countdown") and self.lbl_resign_countdown.winfo_exists():
            self.lbl_resign_countdown.configure(text="")
            try:
                self.lbl_resign_countdown.pack_forget()
            except Exception:
                pass

    def _start_resign_countdown(self, expires_in=15, deadline=None):
        """Hiện đếm ngược đỏ sau nút ĐẦU HÀNG (15s mặc định)."""
        self._stop_resign_countdown()
        import time as _time
        if deadline is not None:
            try:
                self._resign_deadline_mono = float(deadline)
            except (TypeError, ValueError):
                self._resign_deadline_mono = _time.time() + max(1, int(expires_in))
        else:
            self._resign_deadline_mono = _time.time() + max(1, int(expires_in))
        if hasattr(self, "lbl_resign_countdown") and self.lbl_resign_countdown.winfo_exists():
            # Pack ngay sau btn_resign nếu đang Online
            if self.game_mode_var.get() == "Online":
                try:
                    if not self.lbl_resign_countdown.winfo_ismapped():
                        self.lbl_resign_countdown.pack(side="left", padx=(0, 8), after=self.btn_resign)
                except Exception:
                    try:
                        self.lbl_resign_countdown.pack(side="left", padx=(0, 8))
                    except Exception:
                        pass
        self._tick_resign_countdown()

    def _tick_resign_countdown(self):
        """Cập nhật số giây còn lại màu đỏ mỗi 200ms."""
        import time as _time
        deadline = getattr(self, "_resign_deadline_mono", None)
        if deadline is None or not (self._i_resigned or self._opp_resigned) or self.game_over:
            self._stop_resign_countdown()
            return
        left = int(max(0, deadline - _time.time()))
        if hasattr(self, "lbl_resign_countdown") and self.lbl_resign_countdown.winfo_exists():
            self.lbl_resign_countdown.configure(text=str(left), text_color="#ef4444")
        if left <= 0:
            # Đợi server resign_expired; UI sẽ clear khi nhận packet
            self._resign_countdown_job = None
            return
        self._resign_countdown_job = self.root.after(200, self._tick_resign_countdown)

    def update_resign_button(self):
        """Cập nhật nhãn/trạng thái nút Cầu hòa ↔ Từ chối (chỉ Online).

        - Người nhận yêu cầu: nút = TỪ CHỐI
        - Người gửi yêu cầu: khóa nút chờ phản hồi (15s)
        - Tối đa 2 lần cầu hòa / ván
        - Vẫn chơi được khi có yêu cầu đang chờ
        """
        if not hasattr(self, "btn_resign") or not self.btn_resign.winfo_exists():
            return
        if self.game_mode_var.get() != "Online":
            return

        is_dark = self.is_dark_mode
        disabled_bg = "#21262d" if is_dark else "#e2e8f0"
        disabled_fg = "#6e7681" if is_dark else "#64748b"
        has_moves = bool(self.history)
        pending = (self._opp_resigned or self._i_resigned) and not self.game_over
        my_count = getattr(self, "_my_resign_count", 0)

        if self._opp_resigned and not self.game_over:
            # Đối thủ gửi yêu cầu → TỪ CHỐI
            self.btn_resign.configure(
                text=self.t("reject_btn"),
                state="normal",
                fg_color="#7f1d1d",
                hover_color="#991b1b",
                text_color="white",
            )
        elif self._i_resigned and not self.game_over:
            # Mình đã gửi yêu cầu → chờ
            self.btn_resign.configure(
                text=self.t("resign_btn"),
                state="disabled",
                fg_color=disabled_bg,
                hover_color=disabled_bg,
                text_color=disabled_fg,
            )
        elif (
            self.is_online_connected
            and not self.game_over
            and has_moves
            and not self.my_ready_for_rematch
            and not pending
            and my_count < 2
        ):
            self.btn_resign.configure(
                text=self.t("resign_btn"),
                state="normal",
                fg_color="#7f1d1d",
                hover_color="#991b1b",
                text_color="white",
            )
        else:
            self.btn_resign.configure(
                text=self.t("resign_btn"),
                state="disabled",
                fg_color=disabled_bg,
                hover_color=disabled_bg,
                text_color=disabled_fg,
            )


    def on_resign_or_accept(self):
        """Online: Cầu hòa khi đang chơi, hoặc Từ chối khi đối thủ gửi yêu cầu."""
        if self.game_mode_var.get() != "Online" or not self.is_online_connected:
            return
        ws = self.ws
        if ws is None:
            self.display_status("ws_not_connected", color="#ef4444")
            return

        # Từ chối yêu cầu cầu hòa (nút TỪ CHỐI)
        if self._opp_resigned and not self.game_over:
            try:
                ws.send(json.dumps({"type": "resign_reject"}))
            except Exception:
                self.display_status("online_disconnected", color="#ef4444")
                return
            return

        # Gửi yêu cầu cầu hòa (tối đa 2 lần / ván)
        if self.game_over or not self.history or self._i_resigned or self._opp_resigned:
            return
        if getattr(self, "_my_resign_count", 0) >= 2:
            self.display_status("resign_limit_msg", color="#f39c12")
            return
        try:
            ws.send(json.dumps({"type": "resign"}))
        except Exception:
            self.display_status("online_disconnected", color="#ef4444")
            return
        self._i_resigned = True
        self.update_resign_button()
        self.update_pause_btn_state()
        self.display_status("you_resigned_wait", color="#f39c12")


    def request_new_game(self, event=None):
        mode = self.game_mode_var.get()
        if mode == "Online":
            if not self.is_online_connected:
                # Chỉ truyền từ khóa "online_enter_room" và bỏ raw_text=True
                self.display_status("online_enter_room", color="#f39c12")
                return

            # Chấp nhận yêu cầu cầu hòa của đối thủ (nút VÁN MỚI = CHẤP NHẬN)
            if getattr(self, "_opp_resigned", False) and not self.game_over:
                ws = self.ws
                if ws is None:
                    self.display_status("ws_not_connected", color="#ef4444")
                    return
                try:
                    ws.send(json.dumps({"type": "resign_accept"}))
                except Exception:
                    self.display_status("online_disconnected", color="#ef4444")
                return

            # Mình đang chờ phản hồi cầu hòa → không cho bấm VÁN MỚI
            if getattr(self, "_i_resigned", False) and not self.game_over:
                return

            # Sau khi đã chấp nhận (game_over + flags) hoặc ván kết thúc bình thường → rematch
            if getattr(self, "_opp_resigned", False) or getattr(self, "_i_resigned", False):
                # Cho phép bấm VÁN MỚI để gửi rematch sau khi cầu hòa đã được chấp nhận
                pass
            elif not self.game_over and not self.opponent_ready_for_rematch:
                return

            # Không tự lật quân ở phía Client. Server sẽ quyết định quân cho ván mới
            # dựa trên trạng thái auto_rotate đã được đồng bộ cho cả phòng.
            # Điều này tránh tình trạng mỗi máy tự lật một lần rồi bị lật ngược lại.

            # Tạo payload chứa yêu cầu rematch. Server chỉ reset khi cả hai READY.
            payload = {"type": "rematch"}
            self.my_ready_for_rematch = True
            try:
                self.ws.send(json.dumps(payload))
            except Exception:
                self.my_ready_for_rematch = False
                return

            self.display_status("online_ready_wait", color="#f39c12")

            if hasattr(self, "btn_new") and self.btn_new.winfo_exists():
                is_dark = self.is_dark_mode
                disabled_bg = "#21262d" if is_dark else "#e2e8f0"
                disabled_fg = "#6e7681" if is_dark else "#64748b"
                self.btn_new.configure(state="disabled", fg_color=disabled_bg, hover_color=disabled_bg, text_color=disabled_fg)
        else:
            if self.history:
                self.new_game()

    def trigger_online_rematch(self):
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        self._i_resigned = False
        self._opp_resigned = False
        self._resign_name = ""
        self._my_resign_count = 0
        job = getattr(self, "_resign_offer_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._resign_offer_job = None
        self._stop_resign_countdown()

        self.rebuild_board_widgets()
        self.game_over = False
        self.last_move = self.hover_cell = self.hint_cell = None
        self.winning_cells, self.history = [], []

        # Reset cờ đánh dấu bấm chọn quân cho ván tiếp theo
        self._manually_chose_symbol = False
        
        # Server luôn reset lượt về X cho ván mới.
        self._server_turn_symbol = "X"
        self.is_online_turn = (self._server_turn_symbol == self.online_symbol)

        self.apply_symbols()
        self.modern_canvas.configure(cursor="hand2" if self.is_online_turn else "watch")
        self.update_turn_status(mode_type="online", symbol=self.online_symbol)
        self.init_match_timers()
        self.update_pause_btn_state()
        self.set_time_controls_enabled(True)

    def get_winning_line(self, r, c, piece):
        rule = self.rule_var.get().lower()
        for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
            cells, blocked_pos, blocked_neg = [(r, c)], False, False
            nr, nc = r + dr, c + dc
            while 0 <= nr < self.board_size and 0 <= nc < self.board_size:
                if self.board[nr][nc] == piece: cells.append((nr, nc)); nr += dr; nc += dc
                else: blocked_pos = (self.board[nr][nc] != EMPTY); break
            else: blocked_pos = True

            nr, nc = r - dr, c - dc
            while 0 <= nr < self.board_size and 0 <= nc < self.board_size:
                if self.board[nr][nc] == piece: cells.insert(0, (nr, nc)); nr -= dr; nc -= dc
                else: blocked_neg = (self.board[nr][nc] != EMPTY); break
            else: blocked_neg = True

            if len(cells) >= 5:
                if "standard" in rule or "tiêu chuẩn" in rule: return cells
                if ("chặn 2 đầu" in rule or "block" in rule) and (blocked_pos and blocked_neg): continue
                return cells
        return []

    def is_board_full(self):
        """True khi không còn ô trống trên bàn."""
        return all(cell != EMPTY for row in self.board for cell in row)

    def _get_winning_line_on_snapshot(self, board, r, c, piece, board_size, standard_rule):
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            cells = [(r, c)]
            blocked_pos = blocked_neg = False
            nr, nc = r + dr, c + dc
            while 0 <= nr < board_size and 0 <= nc < board_size:
                if board[nr][nc] == piece:
                    cells.append((nr, nc)); nr += dr; nc += dc
                else:
                    blocked_pos = board[nr][nc] != EMPTY
                    break
            else:
                blocked_pos = True

            nr, nc = r - dr, c - dc
            while 0 <= nr < board_size and 0 <= nc < board_size:
                if board[nr][nc] == piece:
                    cells.insert(0, (nr, nc)); nr -= dr; nc -= dc
                else:
                    blocked_neg = board[nr][nc] != EMPTY
                    break
            else:
                blocked_neg = True

            if len(cells) >= 5:
                if standard_rule:
                    return cells
                # Luật Chặn 2 đầu: bị chặn cả hai đầu thì không thắng
                if blocked_pos and blocked_neg:
                    continue
                return cells
        return []

    def find_urgent_move(self, side, board=None, board_size=None, standard_rule=None):
        board = self.board if board is None else board
        board_size = self.board_size if board_size is None else board_size
        if standard_rule is None:
            standard_rule = "standard" in self.rule_var.get().lower() or "tiêu chuẩn" in self.rule_var.get().lower()
        for side_check in (side, HUMAN if side == AI else AI):
            for r in range(board_size):
                for c in range(board_size):
                    if board[r][c] == EMPTY:
                        candidate = [row[:] for row in board]
                        candidate[r][c] = side_check
                        if self._get_winning_line_on_snapshot(candidate, r, c, side_check, board_size, standard_rule):
                            return (r, c)
        return None

    def warmup_online_server(self):
        """Đánh thức Render bằng một websocket request tối giản, chạy hoàn toàn ở background.
        Timeout dài hơn để chịu cold start (Render free có thể mất 30–60s lần đầu).
        """
        if websocket is None:
            return

        # Tránh mở nhiều warm-up đồng thời khi người dùng click Online liên tiếp.
        if getattr(self, "_warmup_in_progress", False):
            return
        self._warmup_in_progress = True

        def _warmup():
            ws = None
            # Thử tối đa 2 lần: lần 1 đánh thức, lần 2 xác nhận đã dậy.
            for attempt in range(2):
                try:
                    # 45s đủ cho cold start Render free; lần 2 nhanh hơn nếu đã dậy.
                    ws = websocket.create_connection(
                        SERVER_URL, timeout=45 if attempt == 0 else 12
                    )
                    ws.send(json.dumps({"action": "warmup"}))
                    try:
                        ws.recv()
                    except Exception:
                        pass
                    break  # Thành công → dừng
                except Exception:
                    # Warm-up chỉ là tối ưu; lỗi không ảnh hưởng app/game.
                    if attempt == 0:
                        time.sleep(2)
                    continue
                finally:
                    try:
                        if ws:
                            ws.close()
                    except Exception:
                        pass
                    ws = None
            self._warmup_in_progress = False

        threading.Thread(target=_warmup, daemon=True).start()


    def _unlock_online_inputs(self):
        """Mở khóa ô tên / mã phòng / nút Join."""
        if hasattr(self, "name_entry"):
            try:
                self.name_entry.unbind("<Key>")
                self.name_entry.unbind("<Button-1>")
                self.name_entry.configure(text_color=("black", "white"))
                self.name_entry.bind("<FocusOut>", self.save_settings)
            except Exception:
                pass
        if hasattr(self, "room_entry"):
            try:
                self.room_entry.unbind("<Key>")
                self.room_entry.unbind("<Button-1>")
                self.room_entry.configure(text_color=("black", "white"))
            except Exception:
                pass
        if hasattr(self, "btn_join"):
            self.btn_join.configure(state="normal")

    def _clear_online_board(self):
        """Xóa bàn cờ + history local (không đụng WebSocket)."""
        self.game_over = False
        self.is_online_turn = False
        self._server_turn_symbol = None
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        self._match_base_times = None
        self._turn_deadline = None
        self._turn_deadline_mono = None
        self._online_clock_offset = 0.0
        self.cancel_after("timer_job")
        self.cancel_after("turn_timer_job")
        self.stop_thinking_animation()
        self.history = []
        self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
        self.winning_cells = []
        self.last_move = None
        self.hint_cell = None
        self.hover_cell = None
        if hasattr(self, "update_ui"):
            self.update_ui()
        if hasattr(self, "update_score_display"):
            self.update_score_display()
        if hasattr(self, "set_time_controls_enabled"):
            self.set_time_controls_enabled(True)
        if hasattr(self, "update_symbol_auto_button"):
            self.update_symbol_auto_button()
        if hasattr(self, "update_pause_btn_state"):
            self.update_pause_btn_state()

    def _reset_online_state(self, full=True):
        """Dọn sạch khi MÌNH thoát / lỗi socket / đóng app.
        full=True: xóa score + chat + board.
        """
        self.is_online_connected = False
        self._is_waiting_online = False
        self.is_online_turn = False
        self._server_turn_symbol = None
        self.online_symbol = None
        self.opponent_name = ""
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        self._i_resigned = False
        self._opp_resigned = False
        self._resign_name = ""
        self._match_base_times = None
        self._turn_deadline = None
        self._turn_deadline_mono = None
        self._online_clock_offset = 0.0

        self.cancel_after("timer_job")
        self.cancel_after("turn_timer_job")
        self.stop_thinking_animation()
        self._unlock_online_inputs()

        if full:
            self.score_me = 0
            self.score_opp = 0
            self.clear_chat()
            self.game_over = False
            self.history = []
            self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
            self.winning_cells = []
            self.last_move = None
            self.hint_cell = None
            self.hover_cell = None
            self.update_score_display()
            self.update_ui()
            self.set_time_controls_enabled(True)
            self.update_symbol_auto_button()
            self.update_mode_buttons()
            self.update_pause_btn_state()

    def _on_opponent_left(self):
        """Đối thủ thoát nhưng MÌNH vẫn giữ WebSocket trong phòng.
        Không set is_online_connected=False để có thể nhận start khi đối thủ vào lại.
        """
        self._is_waiting_online = True
        self.is_online_turn = False
        self._server_turn_symbol = None
        self.my_ready_for_rematch = False
        self.opponent_ready_for_rematch = False
        self._i_resigned = False
        self._opp_resigned = False
        self._resign_name = ""
        self._clear_online_board()
        self.opponent_name = ""
        # Giữ is_online_connected = True (WS còn sống)
        # Mở khóa input để người chơi có thể thoát / đổi phòng nếu muốn
        self._unlock_online_inputs()
        self.modern_canvas.configure(cursor="watch")
        self.update_mode_buttons()
        self.update_resign_button()

    def _send_leave_and_close(self):
        """Gửi leave ngay lập tức rồi đóng socket — đối thủ nhận disconnect tức thì."""
        ws = self.ws
        if not ws:
            return
        try:
            ws.send(json.dumps({"type": "leave"}))
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass
        self.ws = None

    def join_online_room(self):
        # Force kill socket cũ trước khi tạo generation mới (gửi leave để đối thủ biết ngay)
        if self.ws:
            self._send_leave_and_close()

        self._ws_generation = getattr(self, "_ws_generation", 0) + 1
        self._reset_online_state(full=True)

        if websocket is None:
            messagebox.showerror(self.t("system_error_title"), self.t("missing_websocket"))
            return

        room_id = self.room_id_var.get().strip()
        if not room_id:
            self.display_status("online_need_room", color="#ef4444")
            return

        # === LÀM MỜ VÀ CHẶN SỬA TÊN, MÃ PHÒNG AN TOÀN ===
        dim_color = "#64748b" if self.is_dark_mode else "#94a3b8"
        self.name_entry.configure(text_color=dim_color)
        self.room_entry.configure(text_color=dim_color)
        self.name_entry.bind("<Key>", lambda e: "break")
        self.name_entry.bind("<Button-1>", lambda e: "break")
        self.room_entry.bind("<Key>", lambda e: "break")
        self.room_entry.bind("<Button-1>", lambda e: "break")
        self.btn_join.configure(state="disabled")
        # ===============================================

        self._is_waiting_online = True
        self.start_thinking_animation(self.t("online_connecting"), raw_text=True)
        self.modern_canvas.configure(cursor="watch")

        generation = self._ws_generation
        # Snapshot Tk variables on the main thread; worker threads must not read Tk state.
        ws_config = {
            "name": self.player_name_var.get().strip() or self.t("your_name"),
            "symbol": self.player_symbol_var.get(),
            "time_limit": self.get_selected_time_limit_seconds(),
            "board_size": self.board_size_var.get(),
            "rule": self.rule_to_canonical(self.rule_var.get()),
        }
        threading.Thread(target=self._ws_thread, args=(room_id, generation, ws_config), daemon=True).start()

    def _ws_is_current(self, ws, generation=None):
        return (ws is not None and ws is getattr(self, "ws", None) and
                (generation is None or generation == getattr(self, "_ws_generation", 0)))

    def _ws_after(self, generation, callback, *args):
        # A queued callback can outlive its socket; re-check generation on the Tk thread.
        def guarded():
            if generation != getattr(self, "_ws_generation", 0):
                return
            callback(*args)
        self.root.after(0, guarded)

    def _ws_thread(self, room_id, generation, ws_config):
        try:
            ws_app = websocket.WebSocketApp(SERVER_URL,
                on_message=lambda ws, msg, g=generation: self._ws_on_message(ws, msg, g),
                on_error=lambda ws, err, g=generation: self._ws_on_error(ws, err, g),
                on_close=lambda ws, code, msg, g=generation: self._ws_on_close(ws, code, msg, g))
            # Chỉ socket của generation hiện tại mới được trở thành self.ws.
            if generation != getattr(self, "_ws_generation", 0):
                try: ws_app.close()
                except Exception: pass
                return
            self.ws = ws_app
            # ws_config was snapshotted on the Tk main thread before this worker started.
            self.ws.on_open = lambda ws: ws.send(json.dumps({
                "action": "join",
                "room": room_id,
                **ws_config
            }))
            
            # Giữ WebSocket sống chủ động. after()/UI không liên quan đến heartbeat.
            # Ping đều giúp Render/proxy không coi kết nối là idle; ping timeout luôn
            # nhỏ hơn ping interval để websocket-client không báo lỗi cấu hình.
            self.ws.run_forever(
                ping_interval=30,
                ping_timeout=20,
                ping_payload="xoult-ai"
            )
        except Exception as e:
            if generation != getattr(self, "_ws_generation", 0):
                return
            self.root.after(0, lambda err=e: self.display_status("network_error", color="#ef4444", format_args=[err]))
            self.root.after(0, self.stop_thinking_animation)
            self.root.after(0, lambda: self.modern_canvas.configure(cursor="hand2"))

    def _ws_on_message(self, ws, message, generation):
        if not self._ws_is_current(ws, generation):
            return
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        t = data.get("type")
        if t == "waiting":
            def apply_waiting():
                self.stop_thinking_animation()
                msg_key = data.get("msg_key")
                if msg_key:
                    self.display_status(msg_key, color="#f39c12", raw_text=False)
                else:
                    self.display_status(data.get("msg", self.t("online_waiting")), color="#f39c12", raw_text=True)
                self.modern_canvas.configure(cursor="watch")
            self._ws_after(generation, apply_waiting)
            return

        if t == "error":
            msg_key = data.get("msg_key")
            if msg_key:
                self._ws_after(generation, lambda key=msg_key: self.display_status(key, color="#ef4444", raw_text=False))
            else:
                self._ws_after(generation, lambda: self.display_status(data["msg"], color="#ef4444", raw_text=True))
            self._ws_after(generation, self.stop_thinking_animation)
            self._ws_after(generation, lambda: self.modern_canvas.configure(cursor="hand2"))
            ws.close()
            
        elif t == "start":
            start_sym = data.get("symbol", self.player_symbol_var.get())
            self.set_online_symbol(start_sym, data.get("auto_rotate"), refresh=False)
            # Server luôn chốt X đi trước. Lưu lượt server làm nguồn sự thật
            # để không xảy ra tình trạng client O tự đánh trước do lệch trạng thái.
            self._server_turn_symbol = "X"
            self.is_online_turn = (self._server_turn_symbol == self.online_symbol)
            
            opponent_name = (data.get("opponent_name") or data.get("opponent") or data.get("opponentName") or "").strip()
            if opponent_name:
                self.opponent_name = opponent_name

            # Đồng bộ board_size + rule + time từ server (setting của host)
            remote_board = data.get("board_size")
            remote_rule = data.get("rule")
            remote_time = data.get("time_limit")
            remote_times = data.get("times")
            remote_auto_rotate = data.get("auto_rotate")
            
            def init_online_match():
                # Luôn xóa bàn cũ khi nhận start (kể cả đối thủ thoát rồi vào lại).
                self.game_over = False
                self.history = []
                self.board = [[EMPTY] * self.board_size for _ in range(self.board_size)]
                self.winning_cells = []
                self.last_move = None
                self.hint_cell = None
                self.hover_cell = None
                self.my_ready_for_rematch = False
                self.opponent_ready_for_rematch = False
                self._i_resigned = False
                self._opp_resigned = False
                self._resign_name = ""
                self._is_waiting_online = False
                self._match_base_times = None
                self._turn_deadline = None
                self._turn_deadline_mono = None
                self._online_clock_offset = 0.0
                self.cancel_after("timer_job")
                self.cancel_after("turn_timer_job")
                self.set_time_controls_enabled(True)

                # Áp dụng setting từ server
                if remote_board and remote_board in BOARD_SIZES:
                    if self.board_size_var.get() != remote_board:
                        self.board_size_var.set(remote_board)
                        self.rebuild_board_widgets()
                if remote_rule:
                    self.rule_var.set(self.rule_to_display(remote_rule))
                if remote_time is not None:
                    minutes = int(remote_time // 60) if remote_time > 0 else 0
                    self.time_minutes_var.set(str(minutes))
                    self.update_minus_button_color()
                if remote_auto_rotate is not None:
                    self.auto_rotate_var.set(bool(remote_auto_rotate))
                    self.update_symbol_auto_button()

                self.is_online_connected = True
                self.update_mode_buttons()
                self.stop_thinking_animation()
                self.apply_symbols()
                # Khóa lại name/room khi đã vào trận (giống join)
                dim_color = "#64748b" if self.is_dark_mode else "#94a3b8"
                if hasattr(self, "name_entry"):
                    self.name_entry.configure(text_color=dim_color)
                    self.name_entry.bind("<Key>", lambda e: "break")
                    self.name_entry.bind("<Button-1>", lambda e: "break")
                if hasattr(self, "room_entry"):
                    self.room_entry.configure(text_color=dim_color)
                    self.room_entry.bind("<Key>", lambda e: "break")
                    self.room_entry.bind("<Button-1>", lambda e: "break")
                if hasattr(self, "btn_join"):
                    self.btn_join.configure(state="disabled")

                self.modern_canvas.configure(cursor="hand2" if self.is_online_turn else "watch")
                self.update_turn_status(mode_type="online", symbol=self.online_symbol)
                
                self.is_ai_match_paused = False
                self.turn_time_remaining = {"X": self.turn_time_limit, "O": self.turn_time_limit}
                self.init_match_timers()
                if remote_times and isinstance(remote_times, dict):
                    self._match_base_times = {
                        "X": int(remote_times.get("X", 0)),
                        "O": int(remote_times.get("O", 0))
                    }
                    self.time_remaining = dict(self._match_base_times)
                    self.update_timer_display()
                self.update_score_display()
                self.update_ui()
                self.update_pause_btn_state()
            self._ws_after(generation, init_online_match)
            
        elif t == "turn_start":
            turn_symbol = data.get("symbol")
            turn_secs = data.get("turn_secs", 35)
            deadline = data.get("deadline")  # unix timestamp từ server
            server_ts = data.get("server_ts")
            times = data.get("times")
            def apply_turn_start():
                if self.game_over: return
                if turn_symbol in ("X", "O"):
                    self._server_turn_symbol = turn_symbol  # nguồn sự thật từ server
                if self.online_symbol and self._server_turn_symbol in ("X", "O"):
                    self.is_online_turn = (self._server_turn_symbol == self.online_symbol)

                # Đồng bộ đồng hồ tổng từ server — nguồn chuẩn
                if times and isinstance(times, dict):
                    self._match_base_times = {
                        "X": int(times.get("X", 0)),
                        "O": int(times.get("O", 0))
                    }
                    self.time_remaining = dict(self._match_base_times)
                    self.update_timer_display()
                    # Chạy interpolator match clock (Online)
                    if self.get_selected_time_limit_seconds() > 0:
                        if self.timer_job:
                            try: self.root.after_cancel(self.timer_job)
                            except Exception: pass
                            self.timer_job = None
                        if len(self.history) > 0:
                            self.run_match_timer()
                
                if len(self.history) > 0 and deadline:
                    self.start_turn_timer(turn_symbol, turn_secs=turn_secs, deadline=deadline, server_ts=server_ts)
                elif len(self.history) > 0:
                    self.start_turn_timer(turn_symbol, turn_secs=turn_secs)
                else:
                    self.turn_time_limit = int(turn_secs) if turn_secs else 35
                    self.turn_time_remaining = {"X": self.turn_time_limit, "O": self.turn_time_limit}
                    self._turn_deadline = None
                    self.update_turn_bar()

                self.modern_canvas.configure(cursor="hand2" if self.is_online_turn else "watch")
                self.update_turn_status(mode_type="online", symbol=turn_symbol)
                self.update_ui()
            self._ws_after(generation, apply_turn_start)

        elif t == "update_time_limit":
            new_limit_secs = data.get("time_limit", 0)
            changed_by = data.get("changed_by")
            should_notify = bool(data.get("notify", True))
            def apply_remote_time():
                minutes = int(new_limit_secs // 60) if new_limit_secs > 0 else 0
                self.time_minutes_var.set(str(minutes))
                self.update_minus_button_color()
                self.init_match_timers()
                if not should_notify:
                    return
                opp_name = (changed_by or "").strip() or self.display_opponent_name()
                if minutes > 0:
                    self.display_status(
                        f"{opp_name} đã thay đổi thời gian thành {minutes} phút",
                        color="#notice", raw_text=True
                    )
                else:
                    self.display_status(
                        f"{opp_name} đã thay đổi thời gian thành không giới hạn",
                        color="#notice", raw_text=True
                    )
            self._ws_after(generation, apply_remote_time)

        elif t == "symbol_update":
            remote_symbol = data.get("symbol")
            remote_auto = data.get("auto_rotate")
            remote_opp_sym = data.get("opponent_symbol")
            changed_by = data.get("changed_by")
            should_notify = bool(data.get("notify", True))
            if remote_symbol in ("X", "O"):
                def apply_symbol_update():
                    prev_sym = self.player_symbol_var.get()
                    prev_auto = bool(self.auto_rotate_var.get())
                    changed = (
                        prev_sym != remote_symbol
                        or self.online_symbol != remote_symbol
                        or (remote_auto is not None and prev_auto != bool(remote_auto))
                    )
                    self.set_online_symbol(remote_symbol, remote_auto, refresh=False)

                    if getattr(self, "_server_turn_symbol", None) in ("X", "O"):
                        self.is_online_turn = (self._server_turn_symbol == remote_symbol)
                    elif not self.history and not self.game_over:
                        self._server_turn_symbol = "X"
                        self.is_online_turn = (remote_symbol == "X")

                    self.update_symbol_auto_button()
                    self._manually_chose_symbol = not bool(self.auto_rotate_var.get())
                    if changed:
                        self.apply_symbols()
                    self.update_score_display()
                    self.update_symbol_auto_button()
                    self.update_ui()

                    if changed and should_notify:
                        opp_name = (changed_by or "").strip() or self.display_opponent_name()
                        their_sym = remote_opp_sym if remote_opp_sym in ("X", "O") else (
                            "O" if remote_symbol == "X" else "X"
                        )
                        if remote_auto is not None and bool(remote_auto):
                            self.display_status(
                                f"{opp_name} đã thay đổi phe thành Tự động",
                                color="#notice", raw_text=True
                            )
                        else:
                            self.display_status(
                                f"{opp_name} đã thay đổi phe thành {their_sym}",
                                color="#notice", raw_text=True
                            )
                self._ws_after(generation, apply_symbol_update)

        elif t == "update_settings":
            remote_board = data.get("board_size")
            remote_rule = data.get("rule")
            remote_time = data.get("time_limit")
            # Tên khác với biến gán trong nested fn → tránh UnboundLocalError
            remote_auto = data.get("auto_rotate")
            remote_symbol = data.get("symbol")
            remote_opponent_symbol = data.get("opponent_symbol")
            changed_by = data.get("changed_by")
            should_notify = bool(data.get("notify", True))
            changed_fields = set(data.get("changed_fields") or [])

            def apply_remote_settings():
                msgs = []
                opp_name = (changed_by or "").strip() or self.display_opponent_name()
                auto_val = remote_auto

                board_changed = False
                if remote_board and remote_board in BOARD_SIZES:
                    if self.board_size_var.get() != remote_board:
                        board_changed = True
                        self.board_size_var.set(remote_board)
                        if not self.history and not self.game_over:
                            self.rebuild_board_widgets()
                    elif "board_size" in changed_fields:
                        board_changed = True
                    if should_notify and board_changed:
                        msgs.append(f"{opp_name} đã thay đổi bàn cờ thành {remote_board}")

                rule_changed = False
                if remote_rule:
                    display_rule = self.rule_to_display(remote_rule)
                    if self.rule_to_canonical(self.rule_var.get()) != self.rule_to_canonical(remote_rule):
                        rule_changed = True
                        self.rule_var.set(display_rule)
                    elif "rule" in changed_fields:
                        rule_changed = True
                        self.rule_var.set(display_rule)
                    if should_notify and rule_changed:
                        msgs.append(self.t("rule_changed").format(opp_name, display_rule))

                if remote_time is not None:
                    minutes = int(remote_time // 60) if remote_time > 0 else 0
                    try:
                        prev_minutes = int(float(self.time_minutes_var.get().strip() or "0"))
                    except (ValueError, TypeError):
                        prev_minutes = -1
                    self.time_minutes_var.set(str(minutes))
                    self.update_minus_button_color()
                    self.init_match_timers()
                    time_changed = (minutes != prev_minutes) or ("time_limit" in changed_fields)
                    if should_notify and time_changed:
                        if minutes > 0:
                            msgs.append(f"{opp_name} đã thay đổi thời gian thành {minutes} phút")
                        else:
                            msgs.append(f"{opp_name} đã thay đổi thời gian thành không giới hạn")

                auto_changed = False
                if auto_val is not None:
                    auto_val = bool(auto_val)
                    if bool(self.auto_rotate_var.get()) != auto_val:
                        auto_changed = True
                    self.auto_rotate_var.set(auto_val)
                    self.update_symbol_auto_button()
                if "auto_rotate" in changed_fields:
                    auto_changed = True

                changed_symbol = False
                if remote_symbol in ("X", "O"):
                    changed_symbol = (
                        self.player_symbol_var.get() != remote_symbol
                        or self.online_symbol != remote_symbol
                        or "symbol" in changed_fields
                    )
                    self.set_online_symbol(remote_symbol, auto_val, refresh=False)
                    if changed_symbol:
                        self.apply_symbols()
                    self.update_symbol_auto_button()

                if should_notify:
                    if auto_changed and auto_val:
                        msgs.append(f"{opp_name} đã thay đổi phe thành Tự động")
                    elif changed_symbol or (auto_changed and not auto_val):
                        their_sym = remote_opponent_symbol if remote_opponent_symbol in ("X", "O") else (
                            ("O" if remote_symbol == "X" else "X") if remote_symbol in ("X", "O") else None
                        )
                        if their_sym:
                            msgs.append(f"{opp_name} đã thay đổi phe thành {their_sym}")

                self.update_symbol_auto_button()
                self.update_ui()
                if msgs:
                    # #notice → cam đậm (sáng) / vàng sáng (tối)
                    self.display_status(" · ".join(msgs), color="#notice", raw_text=True)
            self._ws_after(generation, apply_remote_settings)

        elif t == "move":
            r, c = data.get("r"), data.get("c")
            opponent_sym = self.opposite_symbol(self.online_symbol)
            if (not isinstance(r, int) or isinstance(r, bool) or
                    not isinstance(c, int) or isinstance(c, bool) or
                    not (0 <= r < self.board_size and 0 <= c < self.board_size)):
                return
            
            def apply_opp_move():
                if self.game_over or self.board[r][c] != EMPTY:
                    return
                self.board[r][c] = AI 
                self.last_move = (r, c)
                self.history.append((r, c, AI))
                # Nước đầu tiên của đối thủ cũng phải khóa X/O/Tự động.
                self.update_symbol_auto_button()
                self.update_resign_button()
                self.play_sound(TING_SOUND_PATH)

                # Khóa nút thời gian ngay khi có quân đầu tiên
                self.set_time_controls_enabled(False)

                # Hủy timer local — đợi turn_start từ server (có deadline chuẩn)
                if self.turn_timer_job:
                    try: self.root.after_cancel(self.turn_timer_job)
                    except Exception: pass
                    self.turn_timer_job = None
                self._turn_deadline = None
                
                win_line = self.get_winning_line(r, c, AI)
                if win_line:
                    self.winning_cells = win_line
                    self.game_over = True
                    self.add_score(opponent_sym)
                    self.display_status("online_opp_win", color="#ef4444", format_args=[opponent_sym])
                    self.play_sound(VICTORY_SOUND_PATH)
                    self.update_symbol_auto_button()
                    self.set_time_controls_enabled(True)
                    self.update_pause_btn_state()   # ← Bật nút VÁN MỚI
                else:
                    self.is_online_turn = True
                    self.modern_canvas.configure(cursor="hand2")
                    self.update_turn_status(mode_type="online", symbol=self.online_symbol)
                self.update_ui()
            self._ws_after(generation, apply_opp_move)
            
        elif t == "move_rejected":
            # Server là nguồn sự thật: hoàn tác nước optimistic nếu server từ chối.
            reason = data.get("reason", "")
            def apply_move_rejected():
                if self.history and self.history[-1][2] == HUMAN:
                    rr, cc, _ = self.history[-1]
                    if self.board[rr][cc] == HUMAN:
                        self.board[rr][cc] = EMPTY
                    self.history.pop()
                    self.last_move = self.history[-1][:2] if self.history else None
                self.is_online_turn = (self._server_turn_symbol == self.online_symbol)
                self.modern_canvas.configure(cursor="hand2" if self.is_online_turn else "watch")
                self.update_ui()
                if reason == "occupied":
                    self.display_status("cell_occupied", color="#f39c12")
            self._ws_after(generation, apply_move_rejected)

        elif t == "game_result":
            result = data.get("result")
            winner = data.get("winner")
            line = data.get("line") or []
            resigned_by = data.get("resigned_by") or ""
            resigned_symbol = data.get("resigned_symbol")
            times = data.get("times")
            def apply_game_result():
                if self.game_over and result not in ("resign", "draw"):
                    return
                self.game_over = True
                if line and isinstance(line, list):
                    self.winning_cells = [tuple(x) for x in line if isinstance(x, (list, tuple)) and len(x) == 2]
                self.cancel_after("timer_job")
                self.cancel_after("turn_timer_job")
                if times and isinstance(times, dict):
                    self._match_base_times = {
                        "X": int(times.get("X", 0)),
                        "O": int(times.get("O", 0)),
                    }
                    self.time_remaining = dict(self._match_base_times)
                    self.update_timer_display()

                if result == "resign":
                    # Legacy: cũ là đầu hàng (có người thắng). Giờ cầu hòa đã chuyển sang result="draw".
                    # Không cộng tỉ số — coi như ván không tính.
                    auto_rm = bool(data.get("auto_rematch"))
                    name = (resigned_by or "").strip() or self.display_opponent_name()
                    job = getattr(self, "_resign_offer_job", None)
                    if job:
                        try:
                            self.root.after_cancel(job)
                        except Exception:
                            pass
                        self._resign_offer_job = None
                    if auto_rm:
                        self._i_resigned = False
                        self._opp_resigned = False
                        self._resign_name = ""
                        self._my_resign_count = 0
                        self._stop_resign_countdown()
                        self.display_status("draw_msg", color="#f39c12")
                    elif resigned_symbol == self.online_symbol or self._i_resigned:
                        self._i_resigned = True
                        self._opp_resigned = False
                        self._resign_name = self.player_name_var.get().strip() or self.t("your_name")
                        self.display_status("you_resigned_wait", color="#f39c12")
                    else:
                        self._opp_resigned = True
                        self._i_resigned = False
                        self._resign_name = name
                        self.display_status("opp_resigned_press_accept", color="#f39c12", format_args=[name])
                elif result == "win" and winner in ("X", "O"):
                    self._i_resigned = False
                    self._opp_resigned = False
                    self.add_score(winner)
                    if winner == self.online_symbol:
                        self.display_status("online_you_win", color="#2ecc71", format_args=[winner])
                    else:
                        self.display_status("online_opp_win", color="#ef4444", format_args=[winner])
                    self.play_sound(VICTORY_SOUND_PATH)
                elif result == "draw":
                    # Hòa (bàn đầy hoặc chấp nhận cầu hòa)
                    self._i_resigned = False
                    self._opp_resigned = False
                    self._resign_name = ""
                    self._my_resign_count = 0
                    self._stop_resign_countdown()
                    job = getattr(self, "_resign_offer_job", None)
                    if job:
                        try:
                            self.root.after_cancel(job)
                        except Exception:
                            pass
                        self._resign_offer_job = None
                    self.display_status("draw_msg", color="#f39c12")
                    # Không cộng điểm, không victory sound
                self.modern_canvas.configure(cursor="hand2")
                self.update_symbol_auto_button()
                self.set_time_controls_enabled(True)
                self.update_pause_btn_state()
                self.update_ui()
            self._ws_after(generation, apply_game_result)

        elif t == "sync_time":
            times = data.get("times")
            if times and not self.game_over:
                def apply_sync():
                    self.time_remaining = times
                    self.update_timer_display()
                self._ws_after(generation, apply_sync)
            
        elif t == "timeout":
            loser_sym = data.get("loser")
            times = data.get("times")
            def apply_timeout():
                if times and isinstance(times, dict):
                    self._match_base_times = {
                        "X": int(times.get("X", 0)),
                        "O": int(times.get("O", 0))
                    }
                    self.time_remaining = dict(self._match_base_times)
                    self.update_timer_display()
                if not self.game_over:
                    self.handle_timeout(loser_sym)
            self._ws_after(generation, apply_timeout)
            
        elif t == "resign_offer":
            # Yêu cầu đầu hàng — vẫn chơi được; tự hết sau ~10s.
            resigned_symbol = data.get("resigned_symbol")
            resigned_by = (data.get("resigned_by") or "").strip()
            expires_in = int(data.get("expires_in") or 15)
            count = int(data.get("count") or 1)
            def apply_resign_offer():
                if self.game_over:
                    return
                # Hủy countdown cũ nếu có
                job = getattr(self, "_resign_offer_job", None)
                if job:
                    try:
                        self.root.after_cancel(job)
                    except Exception:
                        pass
                    self._resign_offer_job = None

                if resigned_symbol == self.online_symbol:
                    self._i_resigned = True
                    self._opp_resigned = False
                    self._resign_name = self.player_name_var.get().strip() or self.t("your_name")
                    self._my_resign_count = max(getattr(self, "_my_resign_count", 0), count)
                    self.display_status("you_resigned_wait", color="#f39c12")
                else:
                    self._opp_resigned = True
                    self._i_resigned = False
                    self._resign_name = resigned_by or self.display_opponent_name()
                    self.display_status(
                        "resign_offer_status",
                        color="#f39c12",
                        format_args=[self._resign_name],
                    )
                self.update_resign_button()
                self.update_pause_btn_state()
                # Đếm ngược đỏ sau nút ĐẦU HÀNG
                self._start_resign_countdown(expires_in=expires_in, deadline=data.get("deadline"))
            self._ws_after(generation, apply_resign_offer)

        elif t == "resign_rejected":
            # Đối thủ từ chối → tiếp tục ván đấu.
            def apply_resign_rejected():
                was_mine = self._i_resigned
                self._i_resigned = False
                self._opp_resigned = False
                self._resign_name = ""
                self._stop_resign_countdown()
                job = getattr(self, "_resign_offer_job", None)
                if job:
                    try:
                        self.root.after_cancel(job)
                    except Exception:
                        pass
                    self._resign_offer_job = None
                if was_mine:
                    self.display_status("resign_rejected_you", color="#f39c12")
                else:
                    self.display_status("resign_rejected_opp", color="#2ecc71")
                self.update_resign_button()
                self.update_pause_btn_state()
                if self.is_online_turn:
                    self.modern_canvas.configure(cursor="hand2")
                else:
                    self.modern_canvas.configure(cursor="watch")
                self.update_turn_status()
            self._ws_after(generation, apply_resign_rejected)

        elif t == "resign_expired":
            # Hết 15s không phản hồi → hủy yêu cầu.
            def apply_resign_expired():
                was_mine = self._i_resigned
                self._i_resigned = False
                self._opp_resigned = False
                self._resign_name = ""
                self._stop_resign_countdown()
                job = getattr(self, "_resign_offer_job", None)
                if job:
                    try:
                        self.root.after_cancel(job)
                    except Exception:
                        pass
                    self._resign_offer_job = None
                self.display_status("resign_expired_msg", color="#f39c12")
                self.update_resign_button()
                self.update_pause_btn_state()
                if self.is_online_turn:
                    self.modern_canvas.configure(cursor="hand2")
                else:
                    self.modern_canvas.configure(cursor="watch")
                self.update_turn_status()
            self._ws_after(generation, apply_resign_expired)

        elif t == "resign_limit":
            def apply_resign_limit():
                self.display_status("resign_limit_msg", color="#f39c12")
                self.update_resign_button()
            self._ws_after(generation, apply_resign_limit)

        elif t == "rematch_waiting":
            # Một người đã bấm VÁN MỚI (hoặc đầu hàng) nhưng server chưa reset bàn vì còn
            # chờ người còn lại. Đồng bộ trạng thái READY sang máy đối diện.
            ready_symbol = data.get("ready_symbol")
            resigned_by = (data.get("resigned_by") or "").strip()
            def apply_rematch_waiting():
                if ready_symbol not in ("X", "O"):
                    return
                if ready_symbol == self.online_symbol:
                    self.my_ready_for_rematch = True
                    # Giữ thông báo đầu hàng nếu mình vừa resign
                    if self._i_resigned:
                        self.display_status("you_resigned_wait", color="#f39c12")
                    else:
                        self.display_status("online_ready_wait", color="#f39c12")
                else:
                    self.opponent_ready_for_rematch = True
                    if self.my_ready_for_rematch:
                        self.display_status("both_ready", color="#2ecc71")
                    elif self._opp_resigned or resigned_by:
                        name = resigned_by or self._resign_name or self.display_opponent_name()
                        self._opp_resigned = True
                        self._resign_name = name
                        self.display_status("opp_resigned_press_accept", color="#f39c12", format_args=[name])
                    else:
                        self.display_status("opp_ready_press_new", color="#2ecc71")
                # Luôn đồng bộ VÁN MỚI + ĐẦU HÀNG theo cờ resign/ready
                self.update_pause_btn_state()
                self.update_resign_button()
            self._ws_after(generation, apply_rematch_waiting)

        elif t == "rematch":
            # Server là nguồn sự thật duy nhất cho ván mới.
            # Client KHÔNG tự đảo quân và KHÔNG tự reset trước khi nhận gói này.
            server_sym = data.get("symbol")
            server_auto = data.get("auto_rotate")

            def apply_rematch():
                if server_sym in ("X", "O"):
                    self.set_online_symbol(server_sym, server_auto, refresh=False)
                elif server_auto is not None:
                    self.auto_rotate_var.set(bool(server_auto))

                self.opponent_ready_for_rematch = False
                self.my_ready_for_rematch = False
                self.trigger_online_rematch()
            self._ws_after(generation, apply_rematch)
            
        elif t == "chat":
            name = data.get("name") or "???"
            text = data.get("text") or ""

            # Server broadcast lại tin nhắn cho cả người gửi. Nếu đây chính là
            # tin mình vừa gửi thì đã hiển thị ở send_chat_message(), bỏ qua
            # bản echo để tránh thành:
            #   Bạn: hi
            #   Tùng: hi
            if not hasattr(self, "_pending_chat_messages"):
                self._pending_chat_messages = []
            pending = (name, text)
            if pending in self._pending_chat_messages:
                self._pending_chat_messages.remove(pending)
                return

            def apply_chat():
                self.append_chat(name, text, is_self=False)
            self._ws_after(generation, apply_chat)

        elif t == "disconnect":
            def apply_dc():
                # Đối thủ thoát — mình vẫn giữ kết nối trong phòng để họ vào lại được ngay.
                self._on_opponent_left()
                msg_key = data.get("msg_key")
                if msg_key:
                    self.display_status(msg_key, color="#f39c12", raw_text=False)
                else:
                    self.display_status(data.get("msg", self.t("online_opp_left")), color="#f39c12", raw_text=True)
            self._ws_after(generation, apply_dc)

    def _ws_on_error(self, ws, error, generation):
        if not self._ws_is_current(ws, generation):
            return
        self._ws_after(generation, self._reset_online_state)
        self._ws_after(generation, lambda: self.display_status("online_disconnected", color="#ef4444"))
        self._ws_after(generation, lambda: self.modern_canvas.configure(cursor="hand2"))

    def _ws_on_close(self, ws, close_status_code, close_msg, generation):
        if not self._ws_is_current(ws, generation):
            return
        self._ws_after(generation, self._reset_online_state)

    def click(self, r, c):
        if self.game_mode_var.get() == "AI vs AI" or self.game_over or self.is_ai_thinking or self.board[r][c] != EMPTY: return
        
        if self.game_mode_var.get() == "Online":
            # Vẫn được đánh khi có yêu cầu đầu hàng đang chờ.
            # Client chỉ được đánh khi đúng lượt mà SERVER đã chốt.
            # X luôn là lượt đầu tiên; O không thể tự đánh trước dù UI vừa đổi phe.
            server_turn = getattr(self, "_server_turn_symbol", None)
            if (not self.is_online_turn or
                    getattr(self, '_is_waiting_online', False) or
                    (server_turn in ("X", "O") and server_turn != self.online_symbol)):
                return
            
            self.board[r][c] = HUMAN
            self.last_move = (r, c)
            self.history.append((r, c, HUMAN))
            # Nước đầu tiên đã xuất hiện: khóa X/O/Tự động ngay lập tức.
            self.update_symbol_auto_button()
            self.update_resign_button()
            self.play_sound(TING_SOUND_PATH)
            self.is_online_turn = False

            # Khóa nút thời gian ngay khi có quân đầu tiên
            self.set_time_controls_enabled(False)
            
            # Hủy timer local — đợi turn_start từ server (có deadline chuẩn)
            if self.turn_timer_job:
                self.root.after_cancel(self.turn_timer_job); self.turn_timer_job = None
            self._turn_deadline = None
            
            try:
                ws = self.ws
                if ws is None or not self.is_online_connected:
                    raise ConnectionError("WebSocket chưa kết nối")
                ws.send(json.dumps({
                    "type": "move",
                    "r": r,
                    "c": c
                }))
            except Exception:
                # Không để lỗi socket làm hỏng callback Tkinter; hoàn tác nước optimistic.
                if self.board[r][c] == HUMAN:
                    self.board[r][c] = EMPTY
                if self.history and self.history[-1][:2] == (r, c):
                    self.history.pop()
                self.last_move = self.history[-1][:2] if self.history else None
                self.is_online_turn = True
                self.update_symbol_auto_button()
                self.display_status("online_disconnected", color="#ef4444")
                self.update_ui()
                return
            
            # Không tự kết thúc ván ở client. Server mới là nguồn sự thật cho
            # kết quả thắng/hòa và còn phải kiểm tra deadline tại thời điểm
            # nhận packet. Nếu client tự chốt thắng trước, một nước sát giờ có
            # thể bị server xử lý thành timeout nhưng client đã game_over=True.
            self.modern_canvas.configure(cursor="watch")
            self.update_turn_status(mode_type="online", symbol=self.online_symbol)
            self.update_ui()
            return
            
        self.hint_cell = None 
        if self.is_ai_match_paused:
            self.is_ai_match_paused = False

        self.board[r][c] = self.current_turn
        self.last_move = (r, c)
        self.history.append((r, c, self.current_turn))
        # A new branch invalidates redo history + ghost preview.
        if hasattr(self, "redo_stack"):
            self.redo_stack.clear()
        self.ghost_winning_cells = []
        self.update_symbol_auto_button()
        
        self.play_sound(TING_SOUND_PATH); self.update_ui(); self.update_pause_btn_state()
        # Bắt đầu đếm sau nước đi (không đếm khi chưa đánh)
        if self.get_selected_time_limit_seconds() > 0 and not self.timer_job:
            self.run_match_timer()

        win_line = self.get_winning_line(r, c, self.current_turn)
        if win_line:
            if self.timer_job: self.root.after_cancel(self.timer_job)
            self.winning_cells = win_line; self.hover_cell = None; self.update_ui()
            winner_sym = self.player_symbol if self.current_turn == HUMAN else self.ai_symbol
            self.add_score(winner_sym)
            self.display_status("win_msg", color=self.status_color_for_symbol(winner_sym), format_args=[winner_sym])
            self.game_over = True; self.is_ai_thinking = False
            self.update_symbol_auto_button()
            self.set_time_controls_enabled(True)
            self.play_sound(VICTORY_SOUND_PATH); self.update_pause_btn_state()
            return

        # Full bàn → hòa (không cộng tỉ số)
        if self.is_board_full():
            if self.timer_job: self.root.after_cancel(self.timer_job)
            self.cancel_after("turn_timer_job")
            self.hover_cell = None
            self.game_over = True
            self.is_ai_thinking = False
            self.update_ui()
            self.display_status("draw_msg", color="#f39c12")
            self.update_symbol_auto_button()
            self.set_time_controls_enabled(True)
            self.update_pause_btn_state()
            self.modern_canvas.configure(cursor="hand2")
            return

        self.current_turn = AI if self.current_turn == HUMAN else HUMAN
        self.start_turn_timer()
        if self.game_mode_var.get() == "2 Người": self.update_turn_status(mode_type="2p"); return

        self.is_ai_thinking = True; self.hover_cell = None; self.modern_canvas.configure(cursor="watch"); self.start_thinking_animation("ai_thinking")
        if self.engine_synced:
            threading.Thread(
                target=self.ai_turn,
                args=(c, r, self._ai_generation),
                daemon=True
            ).start()
        else:
            # Phải dùng snapshot đầy đủ — không được truyền mỗi generation (int)
            self._start_ai_board_sync_worker()

    def _handle_ai_error(self, error_msg_key, exc=None):
        self.stop_thinking_animation()
        self.display_status(error_msg_key, color="#ef4444")
        self.is_ai_thinking = False
        self.modern_canvas.configure(cursor="hand2")
        self.update_pause_btn_state()
        # In chi tiết ra CMD để lần sau chụp gửi debug
        print(f"\n[AI ERROR] key={error_msg_key}")
        if exc is not None:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        else:
            import traceback
            traceback.print_stack()

    def ai_resign(self, ai_side):
        self.stop_thinking_animation()
        if self.timer_job: self.root.after_cancel(self.timer_job)
        self.update_ui()
        sym = "X" if ai_side == HUMAN else "O" if self.game_mode_var.get() == "AI vs AI" else (self.player_symbol if ai_side == HUMAN else self.ai_symbol)
        
        winner_sym = "O" if sym == "X" else "X"
        self.add_score(winner_sym)
        
        self.display_status("resgin_status", color="#ef4444", format_args=[sym])
        self.game_over = True; self.is_ai_thinking = False
        self.update_symbol_auto_button()
        self.set_time_controls_enabled(True)
        self.update_pause_btn_state(); self.modern_canvas.configure(cursor="hand2")

    def _process_engine_turn(self, ai_side, opp_side, generation=None, engine=None):
        generation = self._ai_generation if generation is None else generation
        engine = self.engine if engine is None else engine
        for _ in range(40):
            if generation != self._ai_generation or engine is None or self.is_ai_match_paused: return
            response = engine.get_response(timeout=max(10, int(engine.time_turn) // 1000 + 3))
            if generation != self._ai_generation or self.is_ai_match_paused: return
            if not response:
                continue
            if any(k in response.upper() for k in ("ERROR", "MESSAGE")):
                print(f"[ENGINE SKIP] {response}")
                continue
            if "RESIGN" in response.upper(): self.root.after(0, self.ai_resign, ai_side); return
            if "," in response:
                parts = response.replace(" ", "").split(",")
                if len(parts) >= 2 and parts[0].lstrip("-").isdigit() and parts[1].lstrip("-").isdigit():
                    ax, ay = int(parts[0]), int(parts[1])
                    if 0 <= ax < self.board_size and 0 <= ay < self.board_size:
                        if generation != self._ai_generation or self.is_ai_match_paused: return
                        # Worker only computes. Board/history/UI are committed on Tk main thread.
                        self.root.after(0, self._commit_ai_move, ay, ax, ai_side, opp_side, generation)
                        return
        if generation == self._ai_generation and engine is not None and not self.is_ai_match_paused:
            print(f"\n[AI NO RESPONSE] gen={generation} — engine không trả nước đi hợp lệ (timeout / ERROR / MESSAGE)")
            self.root.after(0, self._handle_ai_error, "ai_not_resp")

    def ai_turn(self, x, y, generation=None):
        generation = self._ai_generation if generation is None else generation
        try:
            if generation != self._ai_generation or not self.engine: return
            urgent = self.find_urgent_move(self.current_turn)
            if urgent: self._apply_ai_move(*urgent, self.current_turn, generation=generation); return
            if generation != self._ai_generation or not self.engine: return
            # Gửi time_left trước TURN — giúp Alpha phân bổ thời gian đúng
            self.engine.send_time_left()
            self.engine.send(f"TURN {x},{y}")
            self._process_engine_turn(self.current_turn, HUMAN if self.current_turn == AI else AI, generation)
        except Exception as e:
            print(f"\n[ai_turn EXCEPTION] gen={generation}")
            import traceback
            traceback.print_exc()
            if generation == self._ai_generation and self.engine and not self.is_ai_match_paused:
                self.root.after(0, self._handle_ai_error, "ai_err", e)

    def _start_ai_board_sync_worker(self):
        # Snapshot all Tk/game state on the main thread before starting the worker.
        mode = self.game_mode_var.get()
        board_size = self.board_size
        standard_rule = self.is_standard_rule
        history_snapshot = list(self.history)
        board_snapshot = [row[:] for row in self.board]
        if mode == "AI vs AI":
            first_sym = self.player_symbol_var.get() if hasattr(self, 'player_symbol_var') else "X"
            second_sym = "O" if first_sym == "X" else "X"
            current_sym = first_sym if len(history_snapshot) % 2 == 0 else second_sym
            ai_side = HUMAN if current_sym == self.player_symbol else AI
            turn_time = self.get_time_turn("X" if ai_side == HUMAN else "O")
        else:
            ai_side = self.current_turn
            turn_time = self.get_time_turn()
        snapshot = (self._ai_generation, mode, board_size, standard_rule, board_snapshot, history_snapshot, ai_side, int(turn_time))
        threading.Thread(target=self.ai_board_sync_turn, args=(snapshot,), daemon=True).start()

    def ai_board_sync_turn(self, snapshot=None):
        # Chỉ nhận snapshot tuple từ _start_ai_board_sync_worker.
        # Nếu bị gọi nhầm với int (generation) thì bỏ qua, tránh TypeError.
        if snapshot is None or not isinstance(snapshot, (tuple, list)) or len(snapshot) < 8:
            print(f"[ai_board_sync_turn] bỏ qua snapshot không hợp lệ: {type(snapshot).__name__}={snapshot!r}")
            return
        generation, mode, board_size, standard_rule, board_snapshot, history_snapshot, ai_side, turn_time = snapshot
        try:
            if generation != self._ai_generation:
                return
            if generation != self._ai_generation or self.is_ai_match_paused:
                return

            eng_path, rule_code = get_engine_path_and_rule(standard_rule)

            # Tái sử dụng engine đang chạy nếu cùng path/size/rule/time — tránh cold-start
            # NN của Alpha mỗi nước (log: n=1 vì phần lớn thời gian tốn vào khởi động).
            local_engine = None
            reuse = False
            existing = self.engine
            if (existing is not None and existing.running and existing.proc
                    and existing.proc.poll() is None
                    and existing.path == eng_path
                    and existing.board_size == board_size
                    and existing.rule == rule_code
                    and int(existing.time_turn) == int(turn_time)):
                local_engine = existing
                reuse = True
            else:
                if existing is not None:
                    try:
                        existing.stop()
                    except Exception:
                        pass
                    # Không đụng self.engine ở worker thread — giao main thread dọn
                    self.root.after(0, self._clear_engine_if, existing, generation)
                local_engine = UltraAIEngine(eng_path, board_size, turn_time, rule_code)
                local_engine.start()

            if generation != self._ai_generation or self.is_ai_match_paused:
                if not reuse:
                    try: local_engine.stop()
                    except Exception: pass
                return
            # Engine lifecycle is committed on the Tk main thread; the worker only owns
            # and drives this local engine while calculating.
            if not reuse:
                self.root.after(0, self._install_synced_engine, local_engine, generation)
            if urgent := self.find_urgent_move(ai_side, board_snapshot, board_size, standard_rule):
                self._apply_ai_move(*urgent, ai_side, generation=generation); return
            # Gửi time_left trước khi bắt đầu suy nghĩ (protocol + Alpha time manager)
            local_engine.send_time_left()
            if history_snapshot:
                local_engine.send("BOARD")
                for r, c, p in history_snapshot:
                    local_engine.send(f"{c},{r},{1 if p == ai_side else 2}")
                local_engine.send("DONE")
            else:
                local_engine.send("BEGIN")
            self._process_engine_turn(ai_side, HUMAN if ai_side == AI else AI, generation, local_engine)
            if generation != self._ai_generation or self.is_ai_match_paused:
                if not reuse:
                    try: local_engine.stop()
                    except Exception: pass
        except Exception as e:
            print(f"\n[ai_board_sync_turn EXCEPTION] gen={generation if 'generation' in dir() else '?'}")
            import traceback
            traceback.print_exc()
            if 'generation' in dir() and generation == self._ai_generation and not self.is_ai_match_paused:
                self.root.after(0, self._handle_ai_error, "sync_err", e)

    def _clear_engine_if(self, engine, generation):
        """Chỉ xóa self.engine nếu vẫn là instance cũ (gọi từ main thread)."""
        if self.engine is engine:
            self.engine = None
            self.engine_synced = False

    def _install_synced_engine(self, engine, generation):
        if generation != self._ai_generation or self.is_ai_match_paused:
            try: engine.stop()
            except Exception: pass
            return
        if self.engine is not None and self.engine is not engine:
            try: self.engine.stop()
            except Exception: pass
        self.engine = engine
        self.engine_synced = True

    def _commit_ai_move(self, r, c, ai_side, opp_side=None, generation=None):
        if generation is not None and generation != self._ai_generation:
            return
        if self.is_ai_match_paused or self.game_over:
            return
        if not (0 <= r < self.board_size and 0 <= c < self.board_size):
            print(f"[AI INVALID] tọa độ ngoài bàn: r={r}, c={c}, size={self.board_size}")
            self._handle_ai_error("ai_err")
            return
        if self.board[r][c] != EMPTY:
            # Engine lệch trạng thái (thường sau DỪNG/TIẾP TỤC hoặc LÙI).
            # Không báo lỗi chết — tự đồng bộ lại bàn cờ và tính lại 1 lần.
            occupied = self.board[r][c]
            print(
                f"[AI OCCUPIED] engine muốn đánh ({r},{c}) nhưng ô đã có quân={occupied}. "
                f"history_len={len(self.history)}. Tự đồng bộ lại..."
            )
            self.engine_synced = False
            if self.engine:
                try:
                    self.engine.stop()
                except Exception:
                    pass
                self.engine = None
            if generation == self._ai_generation and not self.is_ai_match_paused and not self.game_over:
                self.is_ai_thinking = True
                self.modern_canvas.configure(cursor="watch")
                self.start_thinking_animation("ai_rethinking")
                self._start_ai_board_sync_worker()
            else:
                self._handle_ai_error("ai_err")
            return
        self.board[r][c] = ai_side
        self.last_move = (r, c)
        self.history.append((r, c, ai_side))
        self.update_symbol_auto_button()
        self.play_sound(TING_SOUND_PATH)
        self.current_turn = (HUMAN if ai_side == AI else AI) if opp_side is None else opp_side
        self.finish_ai()

    def _apply_ai_move(self, r, c, ai_side, generation=None):
        if generation is not None and generation != self._ai_generation:
            return
        # This method may be called by an AI worker; never mutate Tk/game state there.
        self.root.after(0, self._commit_ai_move, r, c, ai_side, None, generation)

    def finish_ai(self):
        if self.is_ai_match_paused: return
        self.stop_thinking_animation(); self.update_ui(); self.update_pause_btn_state()
        if not self.game_over: self.start_turn_timer()
        if not self.history: return
        if len(self.history) == 1 and self.get_selected_time_limit_seconds() > 0 and not self.timer_job: self.run_match_timer()

        last_piece, lr, lc = self.history[-1][2], self.history[-1][0], self.history[-1][1]
        mode = self.game_mode_var.get()
        if win_line := self.get_winning_line(lr, lc, last_piece):
            if self.timer_job: self.root.after_cancel(self.timer_job)
            self.winning_cells = win_line; self.hover_cell = None; self.update_ui()
            winner_sym = self.player_symbol if last_piece == HUMAN else self.ai_symbol
            self.add_score(winner_sym)
            self.display_status("ai_vs_ai_win" if mode == "AI vs AI" else "ai_win_msg", color=self.status_color_for_symbol(winner_sym), format_args=[winner_sym])
            self.game_over = True; self.is_ai_thinking = False
            self.play_sound(VICTORY_SOUND_PATH)
            self.modern_canvas.configure(cursor="hand2")
            self.update_symbol_auto_button()
            self.set_time_controls_enabled(True)
            self.update_pause_btn_state()
        elif self.is_board_full():
            # Full bàn → hòa (không cộng tỉ số)
            if self.timer_job: self.root.after_cancel(self.timer_job)
            self.cancel_after("turn_timer_job")
            self.hover_cell = None
            self.game_over = True
            self.is_ai_thinking = False
            self.update_ui()
            self.display_status("draw_msg", color="#f39c12")
            self.modern_canvas.configure(cursor="hand2")
            self.update_symbol_auto_button()
            self.set_time_controls_enabled(True)
            self.update_pause_btn_state()
        else:
            if mode == "AI vs AI" and not self.game_over and not self.is_ai_match_paused:
                self.update_turn_status(mode_type="ai_vs_ai"); self.is_ai_thinking = True; self.modern_canvas.configure(cursor="watch"); self.start_thinking_animation("ai_thinking")
                self._start_ai_board_sync_worker()
            else:
                self.update_turn_status(); self.is_ai_thinking = False; self.game_over = False; self.modern_canvas.configure(cursor="hand2"); self.update_pause_btn_state()

    def get_hint(self, event=None):
        mode = self.game_mode_var.get()
        if self.game_over or self.is_ai_thinking or mode in ("AI vs AI", "Online"): return
        self.hint_cell = None; self.is_ai_thinking = True; self.modern_canvas.configure(cursor="watch"); self.start_thinking_animation("hint_calculating")
        generation = self._ai_generation
        board_snapshot = [row[:] for row in self.board]
        history_snapshot = list(self.history)
        board_size = self.board_size
        standard_rule = self.is_standard_rule
        side = self.current_turn if mode == "2 Người" else HUMAN
        threading.Thread(target=self._calc_hint_thread, args=(generation, board_snapshot, history_snapshot, board_size, standard_rule, mode, side), daemon=True).start()

    def _calc_hint_thread(self, generation, board_snapshot, history_snapshot, board_size, standard_rule, mode, side):
        hint_cell = None
        try:
            eng_path, rule_code = get_engine_path_and_rule(standard_rule)
            # Hint: Alpha cần thêm thời gian để gợi ý chất lượng gần Rapfi
            hint_ms = 1200 if rule_code == 8 else 500
            temp_engine = UltraAIEngine(eng_path, board_size, hint_ms, rule_code)
            temp_engine.start()
            temp_engine.send_time_left(hint_ms * 20)
            if history_snapshot:
                temp_engine.send("BOARD")
                for r, c, p in history_snapshot:
                    temp_engine.send(f"{c},{r},{1 if (p == side if mode == '2 Người' else p == HUMAN) else 2}")
                temp_engine.send("DONE")
            else:
                temp_engine.send("BEGIN")
            for _ in range(40):
                resp = temp_engine.get_response(timeout=4)
                if not resp or any(k in resp.upper() for k in ("ERROR", "MESSAGE")): continue
                if "," in resp:
                    parts = resp.replace(" ", "").split(",")
                    if len(parts) >= 2 and parts[0].lstrip("-").isdigit() and parts[1].lstrip("-").isdigit():
                        ax, ay = int(parts[0]), int(parts[1])
                        if 0 <= ax < board_size and 0 <= ay < board_size and board_snapshot[ay][ax] == EMPTY:
                            hint_cell = (ay, ax); break
            temp_engine.stop()
        except Exception as e:
            print("\n[HINT EXCEPTION]")
            import traceback
            traceback.print_exc()
        self.root.after(0, self.finish_hint, generation, hint_cell)

    def finish_hint(self, generation=None, hint_cell=None):
        if generation is not None and generation != self._ai_generation:
            return
        self.hint_cell = hint_cell
        self.stop_thinking_animation(); self.is_ai_thinking = False; self.modern_canvas.configure(cursor="hand2"); self.update_ui()
        if self.hint_cell: self.play_sound(IDEA_SOUND_PATH); self.display_status("hint_result", color="#ef4444")
        else: self.display_status("hint_err", color="#ef4444")

    def _stop_and_reset_ai(self):
        self._ai_generation += 1
        if self.is_ai_thinking:
            if self.engine: self.engine.stop(); self.engine = None
            self.is_ai_thinking = False; self.stop_thinking_animation(); self.modern_canvas.configure(cursor="hand2")

    def _finalize_history_action(self, msg_prefix_key):
        self.apply_symbols(); self.update_ui(); self.update_pause_btn_state()
        if not self.history:
            if self.game_mode_var.get() == "AI vs AI": self.display_status("ai_ready", color="#f39c12")
            else: self.update_turn_status()
        else: self.display_status("ai_match_paused", color="#f39c12", prefix_key=msg_prefix_key)

    def undo_move(self, event=None):
        mode = self.game_mode_var.get()
        # Chỉ chặn Online.
        if mode == "Online" or getattr(self, '_is_waiting_online', False):
            return
            
        # RẤT QUAN TRỌNG: Nếu đang đánh AI hoặc AI vs AI, phải DỪNG ván đấu hoặc đợi HẾT VÁN mới được lùi
        if self.is_ai_thinking and not self.is_ai_match_paused and not self.game_over:
            return
            
        if not self.history:
            return
            
        if not hasattr(self, 'redo_stack'): self.redo_stack = []

        # Ultra-AI lùi 2 bước (về lượt mình). AI vs AI và 2 Người lùi 1 bước.
        moves_to_undo = 1
        if mode == "Ultra-AI" and len(self.history) >= 2:
            moves_to_undo = 2

        if self.game_over and self.winning_cells:
            # Giữ đường thắng dạng “ma” để khi LÙI vẫn thấy chuỗi kết liễu
            self.ghost_winning_cells = list(self.winning_cells)
            winner_sym = self.player_symbol if self.history[-1][2] == HUMAN else self.ai_symbol
            if winner_sym == "X": self.score_me = max(0, self.score_me - 1)
            else: self.score_opp = max(0, self.score_opp - 1)
            self.update_score_display()

        for _ in range(moves_to_undo):
            if self.history:
                r, c, piece = self.history.pop()
                self.board[r][c] = EMPTY
                self.redo_stack.append((r, c, piece))
                
        self.winning_cells = []
        self.game_over = False
        self.hint_cell = None
        self.last_move = (self.history[-1][0], self.history[-1][1]) if self.history else None
        
        # Đặt lại lượt
        if mode in ("2 Người", "AI vs AI"):
            self.current_turn = HUMAN if len(self.history) % 2 == 0 else AI
        elif mode == "Ultra-AI":
            if len(self.history) % 2 == 0:
                self.current_turn = HUMAN if self.player_symbol == "X" else AI
            else:
                self.current_turn = AI if self.player_symbol == "X" else HUMAN
                
            if self.current_turn == AI and not self.is_ai_match_paused:
                self.is_ai_thinking = True
                self.modern_canvas.configure(cursor="watch")
                self.start_thinking_animation("ai_taking_over")
                self._start_ai_board_sync_worker()

        self.update_ui()
        if not self.is_ai_thinking:
            if mode == "AI vs AI":
                self.update_turn_status(mode_type="ai_vs_ai")
            else:
                self.update_turn_status()
            self.modern_canvas.configure(cursor="hand2")
            
        self.update_pause_btn_state()
        if not self.is_ai_match_paused:
            self.start_turn_timer()

    def redo_move(self, event=None):
        mode = self.game_mode_var.get()
        if mode == "Online" or getattr(self, '_is_waiting_online', False):
            return
            
        if self.is_ai_thinking and not self.is_ai_match_paused and not self.game_over:
            return
            
        if not getattr(self, 'redo_stack', []):
            return

        moves_to_redo = 1
        if mode == "Ultra-AI" and len(self.redo_stack) >= 2:
            moves_to_redo = 2

        for _ in range(moves_to_redo):
            if self.redo_stack:
                r, c, piece = self.redo_stack.pop()
                self.board[r][c] = piece
                self.history.append((r, c, piece))
                self.update_symbol_auto_button()
                self.last_move = (r, c)
                
                win_line = self.get_winning_line(r, c, piece)
                if win_line:
                    self.winning_cells = win_line
                    self.ghost_winning_cells = []  # đã TIẾN lại đến nước thắng → bỏ lớp mờ
                    self.game_over = True
                    winner_sym = self.player_symbol if piece == HUMAN else self.ai_symbol
                    self.add_score(winner_sym)
                    self.display_status("win_msg" if mode != "AI vs AI" else "ai_vs_ai_win", color=self.status_color_for_symbol(winner_sym), format_args=[winner_sym])
                    self.play_sound(VICTORY_SOUND_PATH)
                    self.update_symbol_auto_button()
                    self.set_time_controls_enabled(True)
                    if self.timer_job: self.root.after_cancel(self.timer_job)
                    break
                if self.is_board_full():
                    self.game_over = True
                    self.display_status("draw_msg", color="#f39c12")
                    self.update_symbol_auto_button()
                    self.set_time_controls_enabled(True)
                    if self.timer_job: self.root.after_cancel(self.timer_job)
                    self.cancel_after("turn_timer_job")
                    break

        self.hint_cell = None
        
        if not self.game_over:
            if mode in ("2 Người", "AI vs AI"):
                self.current_turn = HUMAN if len(self.history) % 2 == 0 else AI
            elif mode == "Ultra-AI":
                if len(self.history) % 2 == 0:
                    self.current_turn = HUMAN if self.player_symbol == "X" else AI
                else:
                    self.current_turn = AI if self.player_symbol == "X" else HUMAN
                    
                if self.current_turn == AI and not self.is_ai_match_paused:
                    self.is_ai_thinking = True
                    self.modern_canvas.configure(cursor="watch")
                    self.start_thinking_animation("ai_taking_over")
                    self._start_ai_board_sync_worker()

        self.update_ui()
        if not self.game_over and not self.is_ai_thinking:
            if mode == "AI vs AI":
                self.update_turn_status(mode_type="ai_vs_ai")
            else:
                self.update_turn_status()
                
            if not self.is_ai_match_paused:
                self.start_turn_timer()
        self.update_pause_btn_state()

    def limit_name_length(self, *args):
        current_name = self.player_name_var.get()
        if len(current_name) > 16:
            self.player_name_var.set(current_name[:16])

    def on_close(self, event=None):
        self.stop_thinking_animation(); self.save_settings()
        self._send_leave_and_close()
        if self.timer_job: self.root.after_cancel(self.timer_job)
        if self.engine: self.engine.stop()
        self.root.destroy()

if __name__ == "__main__":
    try:
        root = ctk.CTk()
        root.configure(fg_color=("#F5F1E8", "#1c1b1b"))
        app = XOUltraAI(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
        root.mainloop()

    except Exception as e:
        import traceback
        import tkinter as tk
        from tkinter import messagebox
        err_msg = traceback.format_exc()
        
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror(
            LANG.get(getattr(app, "lang_var", None).get() if "app" in locals() and hasattr(app, "lang_var") else "VI", {}).get("startup_crash_title", "Startup Error (Crash)"),
            LANG.get(getattr(app, "lang_var", None).get() if "app" in locals() and hasattr(app, "lang_var") else "VI", {}).get("startup_crash_message", "The app crashed due to the following error:\n\n{}\n\n(Please take a screenshot of this message for troubleshooting.)").format(err_msg)
        )