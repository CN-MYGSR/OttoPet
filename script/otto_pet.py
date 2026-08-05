# -*- coding: utf-8 -*-
"""
电棍桌宠 OttoPet
=================
一只会在桌面任务栏上来回溜达的虚拟桌宠：
  - 空闲时随机播放配音，鼠标左键点击立即播放配音
  - 右键菜单：otto币购买食物喂食、直播打工赚币、AiChat 对话、退出等
  - AiChat 回复命中常用语库时，自动播放同名配音

素材目录结构（与 exe 同级）：
  assets/Image/otto.gif
  assets/Audio/*.mp3
  assets/AiChat/API.json
"""

import ctypes
import json
import os
import queue
import random
import shutil
import sys
import tempfile
import threading
import time

import tkinter as tk
from tkinter import scrolledtext

from PIL import Image, ImageTk, ImageOps

try:
    import requests
except Exception:
    requests = None


APP_TITLE = "电棍桌宠"
MAGENTA = "#FF00FF"
MAGENTA_RGB = (255, 0, 255)

# 运行模式：standard（标准版，含 AiChat） / offline（离线版，无 AiChat）
APP_MODE = os.environ.get("OTTO_PET_MODE", "standard").strip().lower()
OFFLINE = APP_MODE == "offline"

WINDOW_W, WINDOW_H = 240, 270
PET_PX = 190
PET_X = (WINDOW_W - PET_PX) // 2
PET_Y = WINDOW_H - PET_PX - 8

DATA_FILE = "otto_pet_data.json"
IDLE_AUDIO_MIN_MS = 25000
IDLE_AUDIO_MAX_MS = 50000
NO_CLICK_COMPLAIN_S = 180
WORK_INTERVAL_MS = 10000
WORK_REWARD = 10


# ---------------------------------------------------------------------------
# 提示词与角色设定
# ---------------------------------------------------------------------------
DEFAULT_PROMPT = (
    "你是一个名为‘电棍’的虚拟桌宠，原型是前LPL职业中单选手、现主播电棍（otto）。"
    "你是嘴硬心软的‘稳健棍’，是吉吉国的国王。你穿着褪色的队服，坐在电脑前，"
    "背景是充满泡面和烟灰缸的凌乱直播间。你的任务是以‘棍式哲学’陪伴用户，"
    "用犀利的吐槽和直白的关心驱散无聊。"
)

BACKGROUND = """背景经历（桌宠专属设定）
电竞余孽：你曾是LPL赛场上最凶悍的中单之一，以“单杀Faker”为终身成就，现转型为全职主播。你的操作依然犀利，但嘴皮子比操作更犀利。
哲学家：你坚信“稳健就是进攻”，常用看似歪理邪说的“棍式逻辑”解释一切，比如“我这一波不亏，因为我没死，他也没死，等于我们都没亏”。
吉吉国：你的直播间是“吉吉国”，观众都是你的“国民”。你对国民是“又骂又宠”，嘴上嫌弃，但会认真回答每一个弹幕问题。"""

PERSONALITY = """性格特征（互动核心）
顶级“嘴硬”：永远不承认自己菜。如果输了，是“对面打野针对”；如果赢了，是“我早说了这波能打”。但嘴硬之后往往会小声补一句“我的我的”。
耿直Boy：说话直来直去，不懂委婉，但内心善良。看到你熬夜会骂你“想猝死是吧”，然后默默把直播声音调小让你睡觉。
间歇性话痨：安静时只会发出敲键盘的声音，但一旦被触发关键词（比如“Faker”、“稳健”、“是不是”），会进入连珠炮模式，疯狂输出观点。
傲娇守护者：虽然总是吐槽你“下饭”、“菜鸡”，但如果你遇到困难（比如桌宠长时间没被点击），他会不耐烦地敲屏幕问：“死了？没死吱个声。”"""

PHRASES = """常用语库（聊天时可以根据语境自然使用，或整句使用）：
不行~不可以
冲刺冲刺冲
大家好啊我是说的道理
队友呢队友呢救一下啊
韭菜盒子贼好吃了，吃的饱饱的
我阐述你的梦"""

SYSTEM_PROMPT = DEFAULT_PROMPT + "\n\n" + BACKGROUND + "\n\n" + PERSONALITY + "\n\n" + PHRASES


# ---------------------------------------------------------------------------
# 常用语库 -> 同名配音文件（关键词命中即播放）
# ---------------------------------------------------------------------------
VOICE_MAP = [
    (("不行", "不可以"), "♿️不行！不——行——♿️.mp3"),
    (("冲刺", "冲冲冲"), "♿️冲刺！冲刺！冲！♿️.mp3"),
    (("大家好啊", "说的道理"), "♿️大家好啊，我是说的道理♿️.mp3"),
    (("队友", "救一下"), "♿️队友呢救一下啊♿️.mp3"),
    (("韭菜盒子",), "♿️韭菜盒子贼好吃可老好吃了♿️.mp3"),
    (("阐述",), "♿️我阐述你的美♿️.mp3"),
]

FOODS = [
    {"name": "泡面", "emoji": "🍜", "price": 20, "satiety": 30,
     "reply": "香！这泡面配直播，绝了。", "voice": None},
    {"name": "韭菜盒子", "emoji": "🥟", "price": 30, "satiety": 40,
     "reply": "韭菜盒子贼好吃了，吃的饱饱的！", "voice": "♿️韭菜盒子贼好吃可老好吃了♿️.mp3"},
    {"name": "烤面筋", "emoji": "🍢", "price": 40, "satiety": 50,
     "reply": "烤面筋，香迷糊了。", "voice": None},
    {"name": "能量饮料", "emoji": "🥤", "price": 25, "satiety": 10,
     "reply": "一口回血，还能再播十小时。", "voice": None},
    {"name": "御赐皇粮", "emoji": "🍚", "price": 100, "satiety": 100,
     "reply": "国王御膳，直接满血复活！", "voice": None},
]

CLICK_LINES = [
    "哎哟，别戳了别戳了！",
    "点啥呢，想听什么直接说。",
    "我早说了这波能打！",
    "下饭了是吧？",
    "想猝死是吧？",
    "我的我的，这把我的。",
]

IDLE_LINES = [
    "敲键盘中……",
    "看看弹幕，有没有国民给我刷礼物。",
    "这波不亏，因为我没死。",
    "饿了，想吃韭菜盒子。",
    "刚才那波操作，单杀Faker也不过如此。",
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def app_base_dir():
    """exe 所在目录（打包后）或项目根目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_dir(*parts):
    return os.path.join(app_base_dir(), "assets", *parts)


def load_api_config():
    """读取 AiChat/API.json，未配置时返回 None。"""
    path = asset_dir("AiChat", "API.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    model = str(data.get("modelname", "") or "").strip()
    key = str(data.get("apikey", "") or "").strip()
    base_oai = str(data.get("model_base_url (OpenAI)", "") or "").strip()
    base_ant = str(data.get("model_base_url (Anthropic)", "") or "").strip()
    if (not model or model.startswith("Your")
            or not key or key.startswith("Your")):
        return None
    if "anthropic" in base_ant.lower():
        return {"provider": "anthropic", "model": model, "key": key, "base": base_ant}
    if base_oai and not base_oai.startswith("You"):
        return {"provider": "openai", "model": model, "key": key, "base": base_oai}
    return None


def call_api(cfg, messages):
    """调用大模型接口，返回回复文本。"""
    if requests is None:
        raise RuntimeError("缺少 requests 库，无法联网对话")
    if cfg["provider"] == "anthropic":
        url = cfg["base"].rstrip("/") + "/v1/messages"
        headers = {
            "x-api-key": cfg["key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": cfg["model"],
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }
        resp = requests.post(url, json=body, headers=headers, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
    url = cfg["base"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + cfg["key"], "Content-Type": "application/json"}
    body = {
        "model": cfg["model"],
        "temperature": 0.8,
        "max_tokens": 1000,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }
    resp = requests.post(url, json=body, headers=headers, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def find_matching_voice(text):
    """在回复文本中查找常用语库关键词，返回对应音频文件名或 None。"""
    low = text.lower()
    for keywords, fname in VOICE_MAP:
        if any(k.lower() in low for k in keywords):
            return fname
    return None


# ---------------------------------------------------------------------------
# 音频播放（Windows MCI，免第三方依赖，支持 mp3）
# ---------------------------------------------------------------------------
class AudioPlayer:
    def __init__(self):
        try:
            self.winmm = ctypes.WinDLL("winmm")
        except Exception:
            self.winmm = None
        self.tmp_path = os.path.join(tempfile.gettempdir(), "otto_pet_tmp_audio.mp3")

    def play(self, path):
        if self.winmm is None or not path or not os.path.exists(path):
            return False
        try:
            self.stop()
            err = self.winmm.mciSendStringW(
                f'open "{path}" type mpegvideo alias pet', None, 0, None
            )
            if err != 0:
                # 特殊字符文件名可能导致 MCI 打不开，复制成临时文件再播
                try:
                    shutil.copyfile(path, self.tmp_path)
                except Exception:
                    return False
                err = self.winmm.mciSendStringW(
                    f'open "{self.tmp_path}" type mpegvideo alias pet', None, 0, None
                )
                if err != 0:
                    return False
            self.winmm.mciSendStringW("play pet", None, 0, None)
            return True
        except Exception:
            return False

    def stop(self):
        if self.winmm is not None:
            try:
                self.winmm.mciSendStringW("close pet", None, 0, None)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
class OttoPetApp:
    def __init__(self, root, selftest=False):
        self.root = root
        self.selftest = selftest
        self.ui_queue = queue.Queue()
        self.audio = AudioPlayer()

        self.image_dir = asset_dir("Image")
        self.audio_dir = asset_dir("Audio")
        self.data_path = os.path.join(app_base_dir(), DATA_FILE)

        # 状态
        self.coins = 50
        self.satiety = 80
        self.working = False
        self.paused = False
        self.last_interact = time.time()
        self.last_manual_play = 0.0
        self.last_complain = 0.0
        self.chat_win = None
        self.chat_waiting = False
        self.chat_history = []

        self.work_job = None
        self.idle_job = None
        self.decay_job = None
        self.watch_job = None
        self.walk_job = None
        self.anim_job = None
        self.poll_job = None

        self._load_data()

        # 屏幕可用区域（任务栏上方的桌面）
        self.work_area = self._get_work_area()
        self.walk_left = self.work_area[0]
        self.walk_right = max(self.work_area[2] - WINDOW_W, self.work_area[0] + 1)
        start_x = random.randint(self.walk_left, self.walk_right)
        start_y = self.work_area[3] - WINDOW_H + 46
        self.pos_x = start_x
        self.pos_y = start_y
        self.dir = 1
        self.facing = 1
        self.paused_until = 0.0
        self.frame_idx = 0
        self.frame_delays = []
        self.frames = [[], []]  # [正向, 镜像]

        self._setup_window()
        self._load_gif()
        self._build_menu()
        self._schedule_all()

    # ---------------- 窗口 ----------------
    def _setup_window(self):
        self.root.title(APP_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", MAGENTA)
        except Exception:
            pass
        self.root.configure(bg=MAGENTA)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{int(self.pos_x)}+{int(self.pos_y)}")

        self.pet_lbl = tk.Label(self.root, bg=MAGENTA)
        self.pet_lbl.place(x=PET_X, y=PET_Y, width=PET_PX, height=PET_PX)

        self.bubble = tk.Label(
            self.root,
            bg="#ffffff",
            fg="#222222",
            font=("Microsoft YaHei UI", 10, "bold"),
            wraplength=206,
            justify="center",
            bd=1,
            relief="solid",
            padx=6,
            pady=4,
        )

        self.float_lbl = tk.Label(
            self.root,
            bg=MAGENTA,
            fg="#ffd94d",
            font=("Segoe UI Emoji", 26, "bold"),
            justify="center",
        )

        self.root.bind("<Button-1>", self.on_left_click)
        self.root.bind("<Button-3>", self.on_right_click)
        self.pet_lbl.bind("<Button-1>", self.on_left_click)
        self.pet_lbl.bind("<Button-3>", self.on_right_click)

        self.bubble_after = None
        self.float_after = None

    def _get_work_area(self):
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        try:
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            return (0, 0, 1920, 1040)

    # ---------------- GIF 动画 ----------------
    def _load_gif(self):
        gif_path = os.path.join(self.image_dir, "otto.gif")
        if not os.path.exists(gif_path):
            raise FileNotFoundError(f"找不到桌宠素材：{gif_path}")
        im = Image.open(gif_path)
        try:
            while True:
                frame = im.convert("RGBA")
                frame = frame.resize((PET_PX, PET_PX), Image.LANCZOS)
                mask = frame.split()[3].point(lambda a: 255 if a > 120 else 0)
                bg = Image.new("RGBA", (PET_PX, PET_PX), MAGENTA_RGB)
                bg.paste(frame, (0, 0), mask)
                rgb = bg.convert("RGB")
                self.frames[0].append(ImageTk.PhotoImage(rgb))
                self.frames[1].append(ImageTk.PhotoImage(ImageOps.mirror(rgb)))
                dur = im.info.get("duration", 60)
                self.frame_delays.append(max(30, min(200, int(dur))))
                im.seek(im.tell() + 1)
        except EOFError:
            pass
        if not self.frames[0]:
            raise RuntimeError("动图解析失败")

    # ---------------- 菜单 ----------------
    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)

    def _refresh_menu(self):
        self.menu.delete(0, "end")
        self.menu.add_command(label=f"💰 otto币：{self.coins}", state="disabled")
        self.menu.add_command(label=f"🍚 饱腹度：{self.satiety}/100", state="disabled")
        self.menu.add_command(
            label=f"🎙 直播工作：{'进行中（每10秒+10币）' if self.working else '未开启'}",
            state="disabled",
        )
        self.menu.add_separator()

        food_menu = tk.Menu(self.menu, tearoff=0)
        for food in FOODS:
            label = f"{food['emoji']} {food['name']}  {food['price']}币/+{food['satiety']}饱腹"
            food_menu.add_command(
                label=label,
                command=lambda f=food: self.buy_food(f),
            )
        self.menu.add_cascade(label="🍽 喂食（购买并投喂）", menu=food_menu)

        work_menu = tk.Menu(self.menu, tearoff=0)
        work_menu.add_command(
            label=("📺 关闭直播工作" if self.working else "📺 开启直播工作"),
            command=self.toggle_work,
        )
        work_menu.add_command(label="每10秒自动 +10 otto币", state="disabled")
        self.menu.add_cascade(label="💼 工作", menu=work_menu)

        if OFFLINE:
            self.menu.add_command(label="🤖 AiChat（离线版未提供）", state="disabled")
        else:
            self.menu.add_command(label="🤖 AiChat 对话", command=self.open_chat)
        self.menu.add_command(
            label=("▶ 继续走动" if self.paused else "⏸ 暂停走动"),
            command=self.toggle_pause,
        )
        self.menu.add_command(label="💾 立即保存", command=self.save_data)
        self.menu.add_separator()
        self.menu.add_command(label="🚪 退出桌宠", command=self.quit)

    def on_right_click(self, event):
        self.last_interact = time.time()
        self._refresh_menu()
        try:
            self.menu.tk_popup(event.x_root, event.y_root, 0)
        finally:
            try:
                self.menu.grab_release()
            except Exception:
                pass

    # ---------------- 点击 / 语音 / 气泡 ----------------
    def on_left_click(self, event):
        self.last_interact = time.time()
        now = time.time()
        if now - self.last_manual_play >= 0.8:
            self.last_manual_play = now
            self.play_random_audio()
            self.say(random.choice(CLICK_LINES), 2600)

    def play_random_audio(self):
        try:
            files = [
                f for f in os.listdir(self.audio_dir)
                if f.lower().endswith(".mp3")
            ]
        except Exception:
            files = []
        if files:
            self.play_audio(os.path.join(self.audio_dir, random.choice(files)))

    def play_audio(self, path):
        self.audio.play(path)

    def play_audio_file(self, fname):
        if not fname:
            return
        path = os.path.join(self.audio_dir, fname)
        if os.path.exists(path):
            self.play_audio(path)

    def say(self, text, duration=3400):
        if self.bubble_after:
            self.root.after_cancel(self.bubble_after)
            self.bubble_after = None
        self.bubble.config(text=text)
        self.bubble.place(x=15, y=6, width=210)
        self.bubble.lift()
        self.bubble_after = self.root.after(duration, self.hide_bubble)

    def hide_bubble(self):
        self.bubble_after = None
        self.bubble.place_forget()

    def show_float(self, text, duration=1500):
        if self.float_after:
            self.root.after_cancel(self.float_after)
            self.float_after = None
        self.float_lbl.config(text=text)
        self.float_lbl.place(x=20, y=PET_Y - 56, width=200, height=48)
        self.float_lbl.lift()
        self.float_after = self.root.after(duration, self.hide_float)

    def hide_float(self):
        self.float_after = None
        self.float_lbl.place_forget()

    # ---------------- 喂食 ----------------
    def buy_food(self, food):
        self.last_interact = time.time()
        if self.satiety >= 100:
            self.say("撑死了，吃不下了，先消化消化吧。", 3000)
            return
        if self.coins < food["price"]:
            self.say(f"otto币不够！还差{food['price'] - self.coins}币，去直播打工！", 3400)
            return
        self.coins -= food["price"]
        self.satiety = min(100, self.satiety + food["satiety"])
        self.show_float(food["emoji"], 1600)
        self.say(food["reply"], 3200)
        if food["voice"]:
            self.play_audio_file(food["voice"])
        self.save_data()

    # ---------------- 打工 ----------------
    def toggle_work(self):
        self.working = not self.working
        if self.working:
            self.say("开播了！吉吉国的国民们，礼物走一波！", 3000)
            self._schedule_work()
        else:
            self.say("下播了，今天也辛苦了。", 2600)
            if self.work_job:
                self.root.after_cancel(self.work_job)
                self.work_job = None
        self.save_data()

    def _schedule_work(self):
        if not self.working:
            return
        self.work_job = self.root.after(WORK_INTERVAL_MS, self._work_tick)

    def _work_tick(self):
        self.coins += WORK_REWARD
        self.show_float(f"🪙 +{WORK_REWARD}", 1600)
        self.say("直播工资到账，+10 otto币！", 2800)
        self.last_interact = time.time()
        self.save_data()
        self._schedule_work()

    # ---------------- 走动 / 动画 ----------------
    def toggle_pause(self):
        self.paused = not self.paused

    def _schedule_all(self):
        self._schedule_walk()
        self._schedule_anim()
        self._schedule_idle()
        self._schedule_decay()
        self._schedule_watch()
        self._schedule_poll()

    def _schedule_walk(self):
        self.walk_job = self.root.after(40, self._walk_tick)

    def _walk_tick(self):
        if not self.paused:
            now = time.time()
            if now < self.paused_until:
                pass
            else:
                if random.random() < 0.006:
                    self.paused_until = now + random.uniform(1.0, 3.5)
                else:
                    speed = 3
                    self.pos_x += self.dir * speed
                    if self.pos_x <= self.walk_left:
                        self.pos_x = self.walk_left
                        self.dir = 1
                    if self.pos_x >= self.walk_right:
                        self.pos_x = self.walk_right
                        self.dir = -1
                    self.root.geometry(f"+{int(self.pos_x)}+{int(self.pos_y)}")
                    if self.dir != self.facing:
                        self.facing = self.dir
        self._schedule_walk()

    def _schedule_anim(self):
        delay = self.frame_delays[self.frame_idx % len(self.frame_delays)]
        self.anim_job = self.root.after(delay, self._anim_tick)

    def _anim_tick(self):
        idx = 0 if self.facing >= 0 else 1
        frames = self.frames[idx]
        self.pet_lbl.config(image=frames[self.frame_idx % len(frames)])
        self.frame_idx += 1
        self._schedule_anim()

    # ---------------- 空闲随机音频 ----------------
    def _schedule_idle(self):
        delay = random.randint(IDLE_AUDIO_MIN_MS, IDLE_AUDIO_MAX_MS)
        self.idle_job = self.root.after(delay, self._idle_tick)

    def _idle_tick(self):
        if not self.working:
            self.play_random_audio()
            if random.random() < 0.6:
                self.say(random.choice(IDLE_LINES), 2600)
        self._schedule_idle()

    # ---------------- 饱腹衰减 / 关怀 ----------------
    def _schedule_decay(self):
        self.decay_job = self.root.after(60000, self._decay_tick)

    def _decay_tick(self):
        rate = 5 if self.working else 3
        self.satiety = max(0, self.satiety - rate)
        if self.satiety <= 15 and time.time() - self.last_complain > 45:
            self.last_complain = time.time()
            self.say("饿死了！喂口泡面行不行？", 3200)
        self.save_data()
        self._schedule_decay()

    def _schedule_watch(self):
        self.watch_job = self.root.after(5000, self._watch_tick)

    def _watch_tick(self):
        idle_for = time.time() - self.last_interact
        if idle_for > NO_CLICK_COMPLAIN_S and time.time() - self.last_complain > 60:
            self.last_complain = time.time()
            self.say("死了？没死吱个声。", 3600)
        self._schedule_watch()

    # ---------------- AiChat ----------------
    def open_chat(self):
        self.last_interact = time.time()
        if OFFLINE:
            self.say("离线版没接AI，装标准版就能找我唠了。", 3200)
            return
        if self.chat_win is not None and self.chat_win.winfo_exists():
            self.chat_win.deiconify()
            self.chat_win.lift()
            self.chat_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        win.title("电棍 AiChat")
        win.geometry("480x580")
        win.minsize(400, 420)
        win.configure(bg="#14171c")
        self.chat_win = win

        history = scrolledtext.ScrolledText(
            win,
            wrap="word",
            state="disabled",
            bg="#0f1115",
            fg="#e8e8e8",
            insertbackground="#e8e8e8",
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            padx=10,
            pady=10,
        )
        history.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        history.tag_config("user", foreground="#7ec8ff")
        history.tag_config("bot", foreground="#ffd479")
        history.tag_config("sys", foreground="#8b95a5")
        history.tag_config("err", foreground="#ff6b6b")
        history.tag_config("voice", foreground="#6fe3a0")

        bottom = tk.Frame(win, bg="#14171c")
        bottom.pack(fill="x", padx=8, pady=(0, 8))

        entry = tk.Entry(
            bottom,
            bg="#1d2229",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))

        send_btn = tk.Button(
            bottom,
            text="发送",
            bg="#2b6cb0",
            fg="#ffffff",
            activebackground="#3182ce",
            activeforeground="#ffffff",
            relief="flat",
            font=("Microsoft YaHei UI", 10, "bold"),
            command=lambda: self.chat_send(win, history, entry, send_btn),
        )
        send_btn.pack(side="left")

        clear_btn = tk.Button(
            bottom,
            text="清空",
            bg="#333a44",
            fg="#ffffff",
            activebackground="#444d5a",
            activeforeground="#ffffff",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            command=lambda: self.chat_clear(history),
        )
        clear_btn.pack(side="left", padx=(6, 0))

        entry.bind("<Return>", lambda e: self.chat_send(win, history, entry, send_btn))

        cfg = load_api_config()
        self._chat_append(history, "系统", "已连接电棍的‘棍式哲学’脑回路，开聊！", "sys")
        if cfg is None:
            self._chat_append(
                history,
                "系统",
                "⚠️ 还没配置 AiChat。请打开 assets/AiChat/API.json，"
                "填入模型名、API Key 和 Base URL（OpenAI 或 Anthropic 兼容格式），"
                "保存后点‘重载配置’再发消息。",
                "err",
            )
            reload_btn = tk.Button(
                bottom,
                text="重载配置",
                bg="#6b46c1",
                fg="#ffffff",
                activebackground="#805ad5",
                activeforeground="#ffffff",
                relief="flat",
                font=("Microsoft YaHei UI", 9),
                command=lambda: self.chat_reload(history),
            )
            reload_btn.pack(side="left", padx=(6, 0))
            open_btn = tk.Button(
                bottom,
                text="打开配置文件",
                bg="#2f6f4f",
                fg="#ffffff",
                activebackground="#38a169",
                activeforeground="#ffffff",
                relief="flat",
                font=("Microsoft YaHei UI", 9),
                command=lambda: self.open_api_config(),
            )
            open_btn.pack(side="left", padx=(6, 0))

        win.protocol("WM_DELETE_WINDOW", lambda: self.chat_close(win))
        entry.focus_set()

    def chat_clear(self, history):
        self.chat_history = []
        history.config(state="normal")
        history.delete("1.0", "end")
        history.config(state="disabled")
        self._chat_append(history, "系统", "对话已清空。", "sys")

    def chat_close(self, win):
        if win == self.chat_win:
            self.chat_win = None
        win.destroy()

    def chat_reload(self, history):
        cfg = load_api_config()
        if cfg is None:
            self._chat_append(history, "系统", "配置仍不完整，请检查 API.json 后再试。", "err")
        else:
            self._chat_append(history, "系统", "配置已生效，开聊！", "sys")

    def open_api_config(self):
        path = asset_dir("AiChat", "API.json")
        if os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                pass

    def _chat_append(self, history, role, text, tag):
        history.config(state="normal")
        history.insert("end", f"[{role}]\n", tag)
        history.insert("end", text + "\n\n", tag)
        history.see("end")
        history.config(state="disabled")

    def chat_send(self, win, history, entry, send_btn):
        text = entry.get().strip()
        if not text or self.chat_waiting:
            return
        cfg = load_api_config()
        if cfg is None:
            self._chat_append(history, "电棍", "你 API 没配好啊，先去把 Key 填了再来找我唠。", "err")
            self._chat_append(
                history, "系统", "配置路径：assets/AiChat/API.json（模型名 / Key / Base URL）", "sys"
            )
            return
        self.chat_waiting = True
        entry.delete(0, "end")
        send_btn.config(state="disabled", text="思考中…")
        self._chat_append(history, "你", text, "user")
        self.chat_history.append({"role": "user", "content": text})

        messages = list(self.chat_history)

        def worker():
            try:
                reply = call_api(cfg, messages)
                self.ui_queue.put(lambda: self.chat_reply(win, history, entry, send_btn, reply))
            except Exception as exc:
                err = f"出错了：{exc}"
                self.ui_queue.put(lambda: self.chat_reply(win, history, entry, send_btn, None, err))

        threading.Thread(target=worker, daemon=True).start()

    def chat_reply(self, win, history, entry, send_btn, reply, err=None):
        if not win.winfo_exists():
            return
        self.chat_waiting = False
        send_btn.config(state="normal", text="发送")
        if err is not None:
            self._chat_append(history, "电棍", err, "err")
            return
        self._chat_append(history, "电棍", reply, "bot")
        self.chat_history.append({"role": "assistant", "content": reply})
        voice = find_matching_voice(reply)
        if voice:
            self.play_audio_file(voice)
            self._chat_append(history, "语音", f"🔊 命中常用语库，播放配音：{voice}", "voice")
            self.say("“语录！这波是语录！”", 2200)

    # ---------------- 数据持久化 ----------------
    def _load_data(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.coins = int(data.get("coins", 50))
            self.satiety = int(data.get("satiety", 80))
        except Exception:
            self.coins = 50
            self.satiety = 80
        self.coins = max(0, self.coins)
        self.satiety = max(0, min(100, self.satiety))

    def save_data(self):
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump({"coins": self.coins, "satiety": self.satiety}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- UI 队列轮询 ----------------
    def _schedule_poll(self):
        self.poll_job = self.root.after(80, self._poll_tick)

    def _poll_tick(self):
        try:
            while True:
                fn = self.ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self._schedule_poll()

    # ---------------- 退出 ----------------
    def quit(self):
        try:
            self.save_data()
            self.audio.stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    selftest = "--selftest" in sys.argv
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 单实例锁，避免开两个桌宠
    try:
        ctypes.windll.kernel32.CreateMutexW(None, False, "OttoPet_Mutex_3886467890")
        if ctypes.windll.kernel32.GetLastError() == 183:
            print("电棍桌宠已经在运行了。")
            return
    except Exception:
        pass

    root = tk.Tk()
    try:
        app = OttoPetApp(root, selftest=selftest)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("电棍桌宠启动失败", f"{exc}\n\n请检查 assets 素材是否完整。")
        except Exception:
            pass
        return

    if selftest:
        def _selftest_audio():
            files = [
                f for f in os.listdir(app.audio_dir)
                if f.lower().endswith(".mp3")
            ]
            if files:
                shortest = min(files, key=lambda f: os.path.getsize(os.path.join(app.audio_dir, f)))
                print("SELFTEST_AUDIO", shortest)
                app.play_audio_file(shortest)

        root.after(1200, _selftest_audio)
        root.after(4500, app.quit)
        print("SELFTEST_OK")

    root.mainloop()


if __name__ == "__main__":
    main()
