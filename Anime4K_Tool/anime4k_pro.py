import os
import sys
import shutil
import subprocess
import threading
import time
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

# 自动加载同目录下的 libmpv-2.dll
os.environ["PATH"] = os.path.abspath(".") + os.pathsep + os.environ.get("PATH", "")
if hasattr(sys, "_MEIPASS"):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ["PATH"]

try:
    import mpv
    HAS_LIBMPV = True
except Exception:
    HAS_LIBMPV = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

ctk.set_appearance_mode("Light")

ANIME4K_MODES = {
    "关闭": [],
    "效率档 (Mode A)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "质量档 (Mode A+A)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_VL.glsl",
        "Anime4K_Upscale_CNN_x2_VL.glsl",
        "Anime4K_Restore_CNN_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "降噪档 (Mode B)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_Soft_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "无损档 (Mode C)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Upscale_Denoise_CNN_x2_M.glsl",
    ],
}

RESOLUTION_MAP = {
    "1080P": (1920, 1080),
    "2K": (2560, 1440),
    "4K": (3840, 2160),
}

SPEED_LIST = ["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]


def get_resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class Anime4KApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Anime4K Studio")
        self.geometry("1120x630")
        self.resizable(False, False)

        ico_path = get_resource_path("app_icon.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        # 核心队列与播放器状态
        self.video_queue = []
        self.selected_index = None
        self.is_running = False
        self.current_process = None
        self.mpv_player = None

        self.is_paused = False
        self.is_seeking = False
        self.is_web_fullscreen = False   # 铺满软件窗口模式
        self.is_os_fullscreen = False    # 铺满显示器真全屏
        self.is_topmost = False          # 画中画置顶
        self.is_favorited = False        # 追番收藏红心
        self.playlist_drawer_open = False

        # 绑定变量
        self.stream_url_var = ctk.StringVar()
        self.cookie_browser_var = ctk.StringVar(value="无Cookie")
        self.output_dir_path = ctk.StringVar(value=os.path.join(os.getcwd(), "output"))
        self.shader_dir_path = ctk.StringVar(value=get_resource_path("shaders"))
        self.selected_mode = ctk.StringVar(value="效率档 (Mode A)")
        self.selected_res = ctk.StringVar(value="4K")
        self.selected_fps = ctk.StringVar(value="原帧率")
        self.frame_delay_ms = ctk.StringVar(value="0")
        self.frame_interp_mode = ctk.StringVar(value="不补帧")
        self.encoder_choice = ctk.StringVar(value="CPU (x264)")
        self.status_text = ctk.StringVar(
            value="就绪 · 双击列表视频即可进入 Kazumi 沉浸式内嵌超分播放"
        )

        # Kazumi 播放器内部动态变量
        self.player_title_var = ctk.StringVar(value="未加载视频  [1]")
        self.time_label_var = ctk.StringVar(value="00:00 / 00:00")
        self.current_speed_idx = 2  # 默认 1.0x

        # 颜色配置
        self.card_bg = "#F4F8FB"
        self.card_border = "#B8D8F0"
        self.primary_blue = "#3A8FB7"
        self.hover_blue = "#2B7396"
        self.accent_pink = "#E87A90"
        self.kazumi_teal = "#00BFA5"     # 截图同款青绿色进度条与点缀色
        self.text_dark = "#2C3E50"

        self._load_background()
        self._build_main_ui()
        self._build_kazumi_player_ui()

        # 绑定快捷键 (Esc退出全屏，空格暂停)
        self.bind("<Escape>", lambda e: self.exit_fullscreen_if_needed())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_background(self):
        bg_path = get_resource_path("ecy.jpg")
        if os.path.exists(bg_path):
            pil_img = Image.open(bg_path).resize((1120, 630), Image.Resampling.LANCZOS)
            self.bg_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(1120, 630))
            self.bg_label = ctk.CTkLabel(self, text="", image=self.bg_image)
            self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            self.configure(fg_color="#D6EAF8")

    # ==================== 主界面 (二次元卡片布局) ====================
    def _build_main_ui(self):
        font_title = ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold")
        font_body = ctk.CTkFont(family="Microsoft YaHei UI", size=12)

        # 左侧卡片
        self.left_card = ctk.CTkFrame(
            self, width=300, height=530, corner_radius=14,
            fg_color=self.card_bg, border_width=1, border_color=self.card_border
        )
        self.left_card.place(x=18, y=18)
        self.left_card.pack_propagate(False)

        top_row = ctk.CTkFrame(self.left_card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(top_row, text="视频列表", font=font_title, text_color=self.text_dark).pack(side="left")

        ctk.CTkButton(top_row, text="清空", width=44, height=25, font=font_body, fg_color="#E2E8F0", text_color=self.text_dark, hover_color="#CBD5E1", command=self.clear_queue).pack(side="right", padx=(4, 0))
        ctk.CTkButton(top_row, text="删除", width=44, height=25, font=font_body, fg_color="#E2E8F0", text_color=self.text_dark, hover_color="#CBD5E1", command=self.remove_selected).pack(side="right", padx=4)
        ctk.CTkButton(top_row, text="添加", width=50, height=25, font=font_body, fg_color=self.primary_blue, hover_color=self.hover_blue, command=self.add_videos_to_queue).pack(side="right")

        list_wrap = ctk.CTkFrame(self.left_card, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color="#E2E8F0")
        list_wrap.pack(fill="both", expand=True, padx=14, pady=4)

        self.queue_listbox = tk.Listbox(
            list_wrap, bg="#FFFFFF", fg=self.text_dark,
            selectbackground=self.primary_blue, selectforeground="#FFFFFF",
            font=("Microsoft YaHei UI", 9), borderwidth=0, highlightthickness=0
        )
        self.queue_listbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.queue_listbox.bind("<<ListboxSelect>>", self.on_queue_select)
        self.queue_listbox.bind("<Double-Button-1>", lambda e: self.open_kazumi_player())

        url_box = ctk.CTkFrame(self.left_card, fg_color="transparent")
        url_box.pack(fill="x", padx=14, pady=(4, 4))

        url_head = ctk.CTkFrame(url_box, fg_color="transparent")
        url_head.pack(fill="x", pady=(0, 3))
        ctk.CTkLabel(url_head, text="在线链接 (B站/YouTube)", font=font_body, text_color=self.text_dark).pack(side="left")
        ctk.CTkOptionMenu(
            url_head, variable=self.cookie_browser_var,
            values=["无Cookie", "edge", "chrome", "firefox"],
            width=86, height=22, font=font_body,
            fg_color="#E2E8F0", button_color="#CBD5E1", text_color=self.text_dark
        ).pack(side="right")

        ctk.CTkEntry(
            url_box, textvariable=self.stream_url_var, height=28, font=font_body,
            placeholder_text="粘贴网页地址或双击列表播放...",
            fg_color="#FFFFFF", border_color="#CBD5E1"
        ).pack(fill="x")

        ctk.CTkButton(
            self.left_card, text="▶ 进入内嵌超分播放器", height=36, font=font_title,
            fg_color=self.primary_blue, hover_color=self.hover_blue,
            command=self.open_kazumi_player
        ).pack(fill="x", padx=14, pady=(8, 14))

        # 右侧卡片
        self.right_card = ctk.CTkFrame(
            self, width=320, height=530, corner_radius=14,
            fg_color=self.card_bg, border_width=1, border_color=self.card_border
        )
        self.right_card.place(x=782, y=18)
        self.right_card.pack_propagate(False)

        ctk.CTkLabel(self.right_card, text="超分与导出设置", font=font_title, text_color=self.text_dark).pack(
            anchor="w", padx=16, pady=(12, 6)
        )

        form = ctk.CTkFrame(self.right_card, fg_color="transparent")
        form.pack(fill="x", padx=16)
        form.grid_columnconfigure(1, weight=1)

        def add_row(r, label, widget):
            ctk.CTkLabel(form, text=label, font=font_body, text_color=self.text_dark, width=70, anchor="w").grid(row=r, column=0, pady=6, sticky="w")
            widget.grid(row=r, column=1, pady=6, sticky="ew")

        add_row(0, "超分档位", ctk.CTkOptionMenu(
            form, variable=self.selected_mode, values=list(ANIME4K_MODES.keys()),
            height=28, font=font_body, fg_color="#FFFFFF", button_color=self.primary_blue, text_color=self.text_dark
        ))
        add_row(1, "清晰度", ctk.CTkSegmentedButton(
            form, variable=self.selected_res, values=list(RESOLUTION_MAP.keys()),
            height=28, font=font_body, selected_color=self.primary_blue
        ))
        add_row(2, "输出帧率", ctk.CTkOptionMenu(
            form, variable=self.selected_fps, values=["原帧率", "24 FPS", "30 FPS", "60 FPS", "120 FPS"],
            height=28, font=font_body, fg_color="#FFFFFF", button_color=self.primary_blue, text_color=self.text_dark
        ))
        add_row(3, "帧延迟(ms)", ctk.CTkEntry(
            form, textvariable=self.frame_delay_ms, height=28, font=font_body, fg_color="#FFFFFF", border_color="#CBD5E1"
        ))
        add_row(4, "补帧方式", ctk.CTkOptionMenu(
            form, variable=self.frame_interp_mode, values=["不补帧", "帧混合平滑", "光流补帧"],
            height=28, font=font_body, fg_color="#FFFFFF", button_color=self.primary_blue, text_color=self.text_dark
        ))
        add_row(5, "编码方式", ctk.CTkOptionMenu(
            form, variable=self.encoder_choice, values=["CPU (x264)", "N卡加速 (h264)", "N卡加速 (hevc)"],
            height=28, font=font_body, fg_color="#FFFFFF", button_color=self.primary_blue, text_color=self.text_dark
        ))

        dir_box = ctk.CTkFrame(self.right_card, fg_color="transparent")
        dir_box.pack(fill="x", padx=16, pady=(8, 4))

        out_row = ctk.CTkFrame(dir_box, fg_color="transparent")
        out_row.pack(fill="x", pady=3)
        ctk.CTkLabel(out_row, text="输出目录", font=font_body, text_color=self.text_dark, width=62, anchor="w").pack(side="left")
        ctk.CTkEntry(out_row, textvariable=self.output_dir_path, height=26, font=font_body, fg_color="#FFFFFF", border_color="#CBD5E1").pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(out_row, text="选择", width=44, height=26, font=font_body, fg_color="#E2E8F0", text_color=self.text_dark, command=self.browse_output_dir).pack(side="right")

        shd_row = ctk.CTkFrame(dir_box, fg_color="transparent")
        shd_row.pack(fill="x", pady=3)
        ctk.CTkLabel(shd_row, text="Shader库", font=font_body, text_color=self.text_dark, width=62, anchor="w").pack(side="left")
        ctk.CTkEntry(shd_row, textvariable=self.shader_dir_path, height=26, font=font_body, fg_color="#FFFFFF", border_color="#CBD5E1").pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(shd_row, text="选择", width=44, height=26, font=font_body, fg_color="#E2E8F0", text_color=self.text_dark, command=self.browse_shader_dir).pack(side="right")

        action_row = ctk.CTkFrame(self.right_card, fg_color="transparent")
        action_row.pack(fill="x", side="bottom", padx=16, pady=14)

        self.start_batch_btn = ctk.CTkButton(
            action_row, text="批量导出队列", height=36, font=font_title,
            fg_color=self.primary_blue, hover_color=self.hover_blue,
            command=self.start_batch_export
        )
        self.start_batch_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            action_row, text="停止", width=60, height=36, font=font_body,
            fg_color="#E2E8F0", text_color=self.text_dark, state="disabled",
            command=self.stop_batch_export
        )
        self.stop_btn.pack(side="right")

        # 底部状态条
        self.bottom_bar = ctk.CTkFrame(
            self, width=1084, height=42, corner_radius=10,
            fg_color=self.card_bg, border_width=1, border_color=self.card_border
        )
        self.bottom_bar.place(x=18, y=566)
        self.bottom_bar.pack_propagate(False)

        ctk.CTkLabel(self.bottom_bar, textvariable=self.status_text, font=font_body, text_color=self.text_dark, width=380, anchor="w").pack(side="left", padx=12)
        self.progress_bar = ctk.CTkProgressBar(self.bottom_bar, height=10, progress_color=self.primary_blue)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=12)
        self.progress_bar.set(0)

    # ==================== Kazumi 1:1 复刻内嵌播放器界面 ====================
    def _build_kazumi_player_ui(self):
        """完全按照截图样式构建的深色沉浸式内嵌播放器容器"""
        font_top = ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold")
        font_icon = ctk.CTkFont(family="Segoe UI Symbol", size=15)
        font_ctrl = ctk.CTkFont(family="Microsoft YaHei UI", size=12)

        # 主播放器外框 (默认悬浮在中央，点击网页全屏或全屏时可自动铺满整個窗口)
        self.player_container = ctk.CTkFrame(
            self, width=760, height=480, corner_radius=0,
            fg_color="#000000", border_width=0
        )

        # ---------------- 1. 顶部栏 (Top Bar: 返回 + 番名集数 + 快进85秒/截图/画中画/追番/更多) ----------------
        self.top_osd = ctk.CTkFrame(self.player_container, height=44, corner_radius=0, fg_color="#0A0A0A")
        self.top_osd.pack(fill="x", side="top")
        self.top_osd.pack_propagate(False)

        # 左侧返回按钮与标题
        ctk.CTkButton(
            self.top_osd, text="←", width=36, height=32, font=ctk.CTkFont(size=18, weight="bold"),
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=self.close_kazumi_player
        ).pack(side="left", padx=(8, 4))

        ctk.CTkLabel(
            self.top_osd, textvariable=self.player_title_var,
            font=font_top, text_color="#FFFFFF"
        ).pack(side="left", padx=4)

        # 右侧 5 个功能图标按钮 (倒序 pack side="right")
        # ⋮ 更多信息
        ctk.CTkButton(
            self.top_osd, text="⋮", width=34, height=32, font=font_icon,
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=self.show_media_stats
        ).pack(side="right", padx=(2, 8))

        # ♡ 收藏/追番
        self.fav_btn = ctk.CTkButton(
            self.top_osd, text="♡", width=34, height=32, font=font_icon,
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=self.toggle_favorite
        )
        self.fav_btn.pack(side="right", padx=2)

        # ❐ 画中画置顶小窗
        self.pip_btn = ctk.CTkButton(
            self.top_osd, text="❐", width=34, height=32, font=font_icon,
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=self.toggle_pip_topmost
        )
        self.pip_btn.pack(side="right", padx=2)

        # 📷 超分截图
        ctk.CTkButton(
            self.top_osd, text="📷", width=34, height=32, font=font_icon,
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=self.take_upscaled_screenshot
        ).pack(side="right", padx=2)

        # ↻85 跳过片头曲 (快进85秒)
        ctk.CTkButton(
            self.top_osd, text="↻85", width=48, height=30, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="transparent", hover_color="#222222", text_color="#FFFFFF",
            command=lambda: self.seek_relative(85)
        ).pack(side="right", padx=4)

        # ---------------- 2. 中间视频画布区 + 右侧选集抽屉 ----------------
        middle_area = ctk.CTkFrame(self.player_container, fg_color="#000000", corner_radius=0)
        middle_area.pack(fill="both", expand=True)

        self.video_canvas = tk.Frame(middle_area, bg="#000000")
        self.video_canvas.pack(side="left", fill="both", expand=True)
        # 双击视频区域切换全屏
        self.video_canvas.bind("<Double-Button-1>", lambda e: self.toggle_os_fullscreen())

        # 选集侧边抽屉 (点击底部 ☰ 展开)
        self.episode_drawer = ctk.CTkFrame(middle_area, width=180, fg_color="#141414", corner_radius=0)
        ctk.CTkLabel(self.episode_drawer, text="播放列表选集", font=font_ctrl, text_color="#FFFFFF").pack(anchor="w", padx=10, pady=8)
        self.drawer_listbox = tk.Listbox(
            self.episode_drawer, bg="#141414", fg="#E2E8F0",
            selectbackground=self.kazumi_teal, selectforeground="#FFFFFF",
            font=("Microsoft YaHei UI", 9), borderwidth=0, highlightthickness=0
        )
        self.drawer_listbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.drawer_listbox.bind("<Double-Button-1>", self._on_drawer_episode_double_click)

        # ---------------- 3. 底部栏 (Bottom Bar: 青色细进度条 + 播放/下一集/时间 + 弹幕框 + 超分辨率/倍速/宽屏/选集/全屏) ----------------
        self.bottom_osd = ctk.CTkFrame(self.player_container, height=64, corner_radius=0, fg_color="#0A0A0A")
        self.bottom_osd.pack(fill="x", side="bottom")
        self.bottom_osd.pack_propagate(False)

        # 截图同款青绿色细进度条
        self.seek_slider = ctk.CTkSlider(
            self.bottom_osd, from_=0, to=100, height=12,
            fg_color="#262626", progress_color=self.kazumi_teal,
            button_color=self.kazumi_teal, button_hover_color="#00E5C3",
            command=self._on_slider_drag
        )
        self.seek_slider.set(0)
        self.seek_slider.pack(fill="x", padx=6, pady=(4, 2))

        # 底部按钮行
        ctrl_row = ctk.CTkFrame(self.bottom_osd, fg_color="transparent")
        ctrl_row.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # [左下角] 暂停/播放 + 下一集 + 时间显示
        self.play_pause_btn = ctk.CTkButton(
            ctrl_row, text="⏸", width=36, height=36, font=ctk.CTkFont(family="Segoe UI Symbol", size=18),
            corner_radius=18, fg_color="#2E2E36", hover_color="#3F3F46", text_color="#FFFFFF",
            command=self.toggle_pause
        )
        self.play_pause_btn.pack(side="left", padx=6)

        ctk.CTkButton(
            ctrl_row, text="⏭", width=36, height=36, font=ctk.CTkFont(family="Segoe UI Symbol", size=18),
            corner_radius=18, fg_color="#2E2E36", hover_color="#3F3F46", text_color="#FFFFFF",
            command=self.play_next_in_queue
        ).pack(side="left", padx=2)

        ctk.CTkLabel(
            ctrl_row, textvariable=self.time_label_var,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#E2E8F0"
        ).pack(side="left", padx=(12, 14))

        # 中间占位，让右侧按钮靠右
        spacer = ctk.CTkFrame(ctrl_row, fg_color="transparent")
        spacer.pack(side="left", expand=True, fill="x")

        # [右下角] 全屏 + 选集 + 网页宽屏 + 倍速 + 超分辨率 (从右往左排列，还原截图顺序)
        ctk.CTkButton(
            ctrl_row, text="⛶", width=36, height=36, font=ctk.CTkFont(family="Segoe UI Symbol", size=18),
            corner_radius=18, fg_color="transparent", hover_color="#2E2E36", text_color="#FFFFFF",
            command=self.toggle_os_fullscreen
        ).pack(side="right", padx=4)

        ctk.CTkButton(
            ctrl_row, text="☰", width=36, height=36, font=ctk.CTkFont(family="Segoe UI Symbol", size=18),
            corner_radius=18, fg_color="transparent", hover_color="#2E2E36", text_color="#FFFFFF",
            command=self.toggle_episode_drawer
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            ctrl_row, text="🗖", width=36, height=36, font=ctk.CTkFont(family="Segoe UI Symbol", size=18),
            corner_radius=18, fg_color="transparent", hover_color="#2E2E36", text_color="#FFFFFF",
            command=self.toggle_web_fullscreen
        ).pack(side="right", padx=2)

        self.speed_var = ctk.StringVar(value="倍速")
        self.speed_menu = ctk.CTkOptionMenu(
            ctrl_row, variable=self.speed_var, values=SPEED_LIST[::-1],
            width=76, height=30, font=font_ctrl, corner_radius=15,
            fg_color="#2E2E36", button_color="#2E2E36", button_hover_color="#3F3F46",
            dropdown_fg_color="#2E2E36", dropdown_hover_color="#3F3F46", text_color="#FFFFFF",
            command=self.set_playback_speed
        )
        self.speed_menu.pack(side="right", padx=6)

        self.sr_var = ctk.StringVar(value="超分:效率档")
        modes = list(ANIME4K_MODES.keys())
        self.sr_menu = ctk.CTkOptionMenu(
            ctrl_row, variable=self.sr_var, values=modes,
            width=120, height=30, font=font_ctrl, corner_radius=15,
            fg_color="#2E2E36", button_color="#2E2E36", button_hover_color="#3F3F46",
            dropdown_fg_color="#2E2E36", dropdown_hover_color="#3F3F46", text_color=self.kazumi_teal,
            command=self.set_super_resolution
        )
        self.sr_menu.pack(side="right", padx=6)

    # ==================== Kazumi 播放器各项细节功能实现 ====================
    def _ensure_mpv_instance(self):
        if self.mpv_player is not None:
            return True
        if not HAS_LIBMPV:
            messagebox.showwarning(
                "缺少 libmpv-2.dll",
                "请将 libmpv-2.dll 放在本程序同一文件夹下，并确保运行过: pip install python-mpv"
            )
            return False

        self.update_idletasks()
        wid = int(self.video_canvas.winfo_id())
        self.mpv_player = mpv.MPV(
            wid=str(wid),
            vo="gpu-next",
            gpu_api="vulkan" if os.name == "nt" else "auto",
            hwdec="auto-safe",
            keep_open="yes",
            osd_level=1,
            osd_font_size=28,
            osd_color="#FFFFFF"
        )

        @self.mpv_player.property_observer("time-pos")
        def _on_time(_name, val):
            if val is not None and not self.is_seeking:
                dur = self.mpv_player.duration or 0
                if dur > 0:
                    pct = min(max((val / dur) * 100, 0), 100)
                    t_str = f"{int(val)//60:02d}:{int(val)%60:02d} / {int(dur)//60:02d}:{int(dur)%60:02d}"
                    self.after(0, lambda p=pct, s=t_str: (self.seek_slider.set(p), self.time_label_var.set(s)))

        return True

    def open_kazumi_player(self):
        target = self.get_active_media_target()
        if not target:
            messagebox.showwarning("提示", "请先添加视频或输入在线链接")
            return

        # 默认以铺满软件主窗口模式打开（还原截图沉浸式视觉，按左上角 ← 即可退回二次元壁纸主界面）
        self.is_web_fullscreen = True
        self.player_container.place(x=0, y=0, relwidth=1, relheight=1)
        self.player_container.lift()

        if not self._ensure_mpv_instance():
            self.player_container.place_forget()
            return

        self._sync_drawer_list()
        threading.Thread(target=self._play_target_worker, args=(target,), daemon=True).start()

    def _play_target_worker(self, target: str):
        try:
            stream_data = self.resolve_webpage_stream(target)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("解析失败", str(e)))
            return

        v_url = stream_data["video_url"]
        a_url = stream_data["audio_url"]
        headers = stream_data["headers"]
        title = os.path.splitext(stream_data["title"])[0]
        ep_num = (self.selected_index + 1) if self.selected_index is not None else 1

        self.after(0, lambda: self.player_title_var.set(f"{title}  [{ep_num}]"))

        if headers:
            if "User-Agent" in headers:
                self.mpv_player["user-agent"] = headers["User-Agent"]
            if "Referer" in headers:
                self.mpv_player["referrer"] = headers["Referer"]
            extra = [f"{k}: {v}" for k, v in headers.items() if k not in ("User-Agent", "Referer")]
            if extra:
                self.mpv_player["http-header-fields"] = extra

        try:
            delay_sec = float(self.frame_delay_ms.get().strip()) / 1000.0
        except ValueError:
            delay_sec = 0.0
        self.mpv_player.audio_delay = -delay_sec

        self.after(0, lambda: self.apply_anime4k_shader(self.selected_mode.get()))

        self.mpv_player.play(v_url)
        if a_url:
            self.after(300, lambda: self.mpv_player.command("audio-add", a_url, "select"))

        self.is_paused = False
        self.after(0, lambda: self.play_pause_btn.configure(text="⏸"))

    def close_kazumi_player(self):
        """左上角 ← 返回按钮：退出播放器回到二次元主界面"""
        if self.is_os_fullscreen:
            self.toggle_os_fullscreen()
        if self.mpv_player:
            self.mpv_player.command("stop")
        self.player_container.place_forget()
        self.status_text.set("已返回主界面")

    def seek_relative(self, seconds: float):
        """右上角 ↻85 一键跳过片头曲"""
        if self.mpv_player:
            self.mpv_player.command("seek", str(seconds), "relative")
            self.mpv_player.show_text(f"已快进 +{int(seconds)} 秒 (跳过OP)", 1500)

    def take_upscaled_screenshot(self):
        """右上角 📷 截取经过 Anime4K 渲染后的高清画面"""
        if not self.mpv_player:
            return
        shot_dir = os.path.join(self.output_dir_path.get().strip(), "screenshots")
        os.makedirs(shot_dir, exist_ok=True)
        shot_file = os.path.join(shot_dir, f"Anime4K_Shot_{int(time.time())}.png")
        try:
            # window 模式会連同 GLSL 超分着色器效果一起截下
            self.mpv_player.command("screenshot-to-file", shot_file, "window")
            self.mpv_player.show_text(f"📷 截图已保存: {os.path.basename(shot_file)}", 2000)
        except Exception as e:
            self.status_text.set(f"截图失败: {e}")

    def toggle_pip_topmost(self):
        """右上角 ❐ 切换窗口置顶画中画模式"""
        self.is_topmost = not self.is_topmost
        self.attributes("-topmost", self.is_topmost)
        self.pip_btn.configure(text_color=self.kazumi_teal if self.is_topmost else "#FFFFFF")
        if self.mpv_player:
            msg = "已开启窗口置顶 (PiP)" if self.is_topmost else "已关闭窗口置顶"
            self.mpv_player.show_text(msg, 1500)

    def toggle_favorite(self):
        """右上角 ♡ 追番收藏红心"""
        self.is_favorited = not self.is_favorited
        self.fav_btn.configure(
            text="♥" if self.is_favorited else "♡",
            text_color=self.accent_pink if self.is_favorited else "#FFFFFF"
        )
        if self.mpv_player:
            self.mpv_player.show_text("♥ 已加入追番收藏" if self.is_favorited else "已取消收藏", 1500)

    def show_media_stats(self):
        """右上角 ⋮ 显示当前超分管线与视频流参数"""
        if not self.mpv_player:
            return
        w = getattr(self.mpv_player, "width", "未知")
        h = getattr(self.mpv_player, "height", "未知")
        fps = getattr(self.mpv_player, "container_fps", 0) or 0
        codec = getattr(self.mpv_player, "video_format", "未知")
        mode = self.selected_mode.get()
        info_text = f"原始分辨率: {w}x{h} ({fps:.2f} FPS)\n视频编码: {codec}\n当前超分管线: Anime4K [{mode}]"
        self.mpv_player.show_text(info_text, 3500)

    def toggle_pause(self):
        if self.mpv_player:
            self.is_paused = not self.is_paused
            self.mpv_player.pause = self.is_paused
            self.play_pause_btn.configure(text="▶" if self.is_paused else "⏸")

    def play_next_in_queue(self):
        """左下角 ⏭ 播放队列中的下一集"""
        if not self.video_queue:
            return
        next_idx = 0 if self.selected_index is None else (self.selected_index + 1) % len(self.video_queue)
        self.selected_index = next_idx
        self.refresh_queue_listbox()
        self._sync_drawer_list()
        target = self.video_queue[next_idx]["path"]
        threading.Thread(target=self._play_target_worker, args=(target,), daemon=True).start()

    def set_super_resolution(self, mode_name: str):
        """右下角 [超分辨率] 菜单选择回调"""
        self.selected_mode.set(mode_name)
        self.apply_anime4k_shader(mode_name)

    def apply_anime4k_shader(self, mode_name: str):
        if not self.mpv_player:
            return
        if mode_name == "关闭":
            self.mpv_player.glsl_shaders = ""
            self.mpv_player.vf = ""
            self.sr_var.set("超分辨率")
            self.sr_menu.configure(text_color="#9CA3AF")
            self.mpv_player.show_text("Anime4K 超分辨率: 已关闭 (原画)", 1800)
            return

        shader_dir = self.shader_dir_path.get().strip()
        files = ANIME4K_MODES.get(mode_name, [])
        valid = [os.path.join(shader_dir, f) for f in files if os.path.exists(os.path.join(shader_dir, f))]

        short_tag = mode_name.split()[0]
        self.sr_var.set(f"超分:{short_tag}")
        self.sr_menu.configure(text_color=self.kazumi_teal)

        if valid:
            sep = ";" if os.name == "nt" else ":"
            self.mpv_player.glsl_shaders = sep.join(valid)
            self.mpv_player.show_text(f"⚡ Anime4K 超分辨率: {mode_name}", 1800)
        else:
            strength = "1.5" if "质量" in mode_name else "1.0"
            self.mpv_player.vf = f"unsharp=5:5:{strength}:3:3:0.5"
            self.mpv_player.show_text(f"⚡ 内置动漫超分: {mode_name}", 1800)

    def set_playback_speed(self, sp_str: str):
        """右下角 [倍速] 菜单选择回调"""
        sp_val = float(sp_str.replace("x", ""))
        self.speed_var.set("倍速" if sp_str == "1.0x" else sp_str)
        self.speed_menu.configure(
            text_color="#FFFFFF" if sp_str == "1.0x" else self.kazumi_teal
        )
        if self.mpv_player:
            self.mpv_player.speed = sp_val
            self.mpv_player.show_text(f"播放倍速: {sp_str}", 1200)

    def toggle_web_fullscreen(self):
        """右下角 🗖 切换铺满窗口 / 居中悬浮小窗（露出两侧设置面板）"""
        self.is_web_fullscreen = not self.is_web_fullscreen
        if self.is_web_fullscreen:
            self.player_container.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            # 缩小到正中央，露出左右两侧面板
            self.player_container.place(x=326, y=18, width=448, height=530)

    def toggle_episode_drawer(self):
        """右下角 ☰ 展开/收起右侧选集列表抽屉"""
        if self.playlist_drawer_open:
            self.episode_drawer.pack_forget()
            self.playlist_drawer_open = False
        else:
            self.episode_drawer.pack(side="right", fill="y")
            self._sync_drawer_list()
            self.playlist_drawer_open = True

    def _sync_drawer_list(self):
        self.drawer_listbox.delete(0, "end")
        for idx, item in enumerate(self.video_queue):
            name = os.path.basename(item["path"])
            self.drawer_listbox.insert("end", f"[{idx+1}] {name}")
        if self.selected_index is not None and 0 <= self.selected_index < len(self.video_queue):
            self.drawer_listbox.selection_set(self.selected_index)

    def _on_drawer_episode_double_click(self, event):
        sel = self.drawer_listbox.curselection()
        if sel:
            self.selected_index = sel[0]
            self.refresh_queue_listbox()
            target = self.video_queue[self.selected_index]["path"]
            threading.Thread(target=self._play_target_worker, args=(target,), daemon=True).start()

    def toggle_os_fullscreen(self):
        """右下角 ⛶ 切换显示器真全屏"""
        self.is_os_fullscreen = not self.is_os_fullscreen
        if self.is_os_fullscreen:
            self._pre_fs_web_state = self.is_web_fullscreen
            
            # 在 Windows 上，通常使用 state("zoomed") 结合 overrideredirect 或者直接 "-fullscreen"
            self.resizable(True, True)
            self.attributes("-fullscreen", True)
            self.state("zoomed")  # 强制最大化
            
            self.player_container.place(x=0, y=0, relwidth=1, relheight=1)
            # 强制刷新布局
            self.update_idletasks()
        else:
            self.attributes("-fullscreen", False)
            self.state("normal")
            self.resizable(False, False)
            self.geometry("1120x630")
            
            if hasattr(self, '_pre_fs_web_state') and not self._pre_fs_web_state:
                self.is_web_fullscreen = False
                self.player_container.place(x=326, y=18, width=448, height=530)
            else:
                self.is_web_fullscreen = True
                self.player_container.place(x=0, y=0, relwidth=1, relheight=1)
            self.update_idletasks()

    def exit_fullscreen_if_needed(self):
        if self.is_os_fullscreen:
            self.toggle_os_fullscreen()

    def _on_slider_drag(self, val):
        if self.mpv_player and self.mpv_player.duration:
            target_sec = (float(val) / 100.0) * self.mpv_player.duration
            self.mpv_player.seek(target_sec, reference="absolute")

    # ==================== 队列与导出逻辑 ====================
    def refresh_queue_listbox(self):
        self.queue_listbox.delete(0, "end")
        for idx, item in enumerate(self.video_queue):
            name = os.path.basename(item["path"])
            self.queue_listbox.insert("end", f"{idx+1}. [{item['status']}] {name}")
        if self.selected_index is not None and 0 <= self.selected_index < len(self.video_queue):
            self.queue_listbox.selection_set(self.selected_index)

    def on_queue_select(self, event):
        sel = self.queue_listbox.curselection()
        if sel:
            self.selected_index = sel[0]

    def add_videos_to_queue(self):
        paths = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts"), ("所有文件", "*.*")]
        )
        if paths:
            for p in paths:
                if not any(item["path"] == p for item in self.video_queue):
                    self.video_queue.append({"path": p, "status": "待处理"})
            if self.selected_index is None and self.video_queue:
                self.selected_index = 0
            self.refresh_queue_listbox()
            self.status_text.set(f"已导入 {len(paths)} 个视频 · 双击即可进入播放器")

    def remove_selected(self):
        sel = self.queue_listbox.curselection()
        if sel:
            idx = sel[0]
            self.video_queue.pop(idx)
            self.selected_index = min(idx, len(self.video_queue) - 1) if self.video_queue else None
            self.refresh_queue_listbox()

    def clear_queue(self):
        self.video_queue.clear()
        self.selected_index = None
        self.refresh_queue_listbox()

    def browse_shader_dir(self):
        p = filedialog.askdirectory(title="选择 Shader 文件夹")
        if p:
            self.shader_dir_path.set(p)

    def browse_output_dir(self):
        p = filedialog.askdirectory(title="选择输出文件夹")
        if p:
            self.output_dir_path.set(p)

    def get_active_media_target(self) -> str:
        stream_url = self.stream_url_var.get().strip()
        if stream_url:
            return stream_url
        if self.selected_index is not None and 0 <= self.selected_index < len(self.video_queue):
            return self.video_queue[self.selected_index]["path"]
        if self.video_queue:
            return self.video_queue[0]["path"]
        return ""

    def get_valid_shader_paths(self) -> list:
        shader_dir = self.shader_dir_path.get().strip()
        files = ANIME4K_MODES.get(self.selected_mode.get(), [])
        return [os.path.join(shader_dir, f) for f in files if os.path.exists(os.path.join(shader_dir, f))]

    def resolve_webpage_stream(self, url: str) -> dict:
        if os.path.exists(url):
            return {"is_web": False, "title": os.path.basename(url), "video_url": url, "audio_url": None, "headers": {}}

        if not HAS_YTDLP:
            raise RuntimeError("请先安装 yt-dlp: pip install -U yt-dlp")

        cookie_browser = self.cookie_browser_var.get()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        }
        if cookie_browser != "无Cookie":
            ydl_opts["cookiesfrombrowser"] = (cookie_browser.lower(),)

        self.after(0, lambda: self.status_text.set("正在解析在线视频流..."))
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "Online_Video")
            headers = dict(info.get("http_headers", {}))
            if "bilibili.com" in url or "b23.tv" in url:
                headers["Referer"] = "https://www.bilibili.com/"

            if "requested_formats" in info and len(info["requested_formats"]) >= 2:
                v_fmt, a_fmt = info["requested_formats"][0], info["requested_formats"][1]
                merged_headers = dict(v_fmt.get("http_headers", headers))
                if "bilibili.com" in url or "b23.tv" in url:
                    merged_headers["Referer"] = "https://www.bilibili.com/"
                return {"is_web": True, "title": title, "video_url": v_fmt["url"], "audio_url": a_fmt["url"], "headers": merged_headers}
            return {"is_web": True, "title": title, "video_url": info["url"], "audio_url": None, "headers": headers}

    def build_ffmpeg_export_cmd(self, input_path: str, output_path: str) -> list:
        target_w, target_h = RESOLUTION_MAP[self.selected_res.get()]
        valid_shaders = self.get_valid_shader_paths()
        vf_filters = []

        if valid_shaders:
            for idx, s_path in enumerate(valid_shaders):
                escaped_path = s_path.replace("\\", "/").replace(":", "\\:")
                if idx == len(valid_shaders) - 1:
                    vf_filters.append(f"libplacebo=w={target_w}:h={target_h}:custom_shader_path='{escaped_path}'")
                else:
                    vf_filters.append(f"libplacebo=custom_shader_path='{escaped_path}'")
        else:
            vf_filters.append(f"scale={target_w}:{target_h}:flags=lanczos,unsharp=5:5:1.0:3:3:0.5")

        try:
            delay_ms = float(self.frame_delay_ms.get().strip())
        except ValueError:
            delay_ms = 0.0
        if delay_ms != 0:
            vf_filters.append(f"setpts=PTS+({delay_ms / 1000.0}/TB)")

        fps_choice = self.selected_fps.get()
        interp_choice = self.frame_interp_mode.get()
        if fps_choice != "原帧率":
            fps_val = int(fps_choice.split()[0])
            if interp_choice == "光流补帧":
                vf_filters.append(f"minterpolate=fps={fps_val}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
            elif interp_choice == "帧混合平滑":
                vf_filters.append(f"minterpolate=fps={fps_val}:mi_mode=blend")
            else:
                vf_filters.append(f"fps={fps_val}")

        enc_map = {"CPU (x264)": "libx264", "N卡加速 (h264)": "h264_nvenc", "N卡加速 (hevc)": "hevc_nvenc"}
        enc_str = enc_map.get(self.encoder_choice.get(), "libx264")

        cmd = ["ffmpeg", "-y"]
        if valid_shaders:
            cmd += ["-init_hw_device", "vulkan"]
        cmd += ["-i", input_path, "-vf", ",".join(vf_filters), "-c:v", enc_str, "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", output_path]
        return cmd

    def get_video_duration(self, input_path: str) -> float:
        try:
            res = subprocess.run(["ffmpeg", "-i", input_path], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if match:
                return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        except Exception:
            pass
        return 0.0

    def start_batch_export(self):
        if not self.video_queue:
            messagebox.showwarning("提示", "请先添加视频文件")
            return
        output_dir = self.output_dir_path.get().strip()
        os.makedirs(output_dir, exist_ok=True)
        self.is_running = True
        self.start_batch_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._batch_worker, args=(output_dir,), daemon=True).start()

    def _batch_worker(self, output_dir: str):
        res_tag = self.selected_res.get()
        for item in self.video_queue:
            if not self.is_running:
                break
            if item["status"] == "完成":
                continue

            input_path = item["path"]
            base_name, _ = os.path.splitext(os.path.basename(input_path))
            output_path = os.path.join(output_dir, f"{base_name}_{res_tag}.mp4")

            item["status"] = "处理中"
            self.after(0, self.refresh_queue_listbox)
            self.after(0, lambda: self.progress_bar.set(0))
            self.after(0, lambda b=base_name: self.status_text.set(f"正在导出: {b}"))

            duration = self.get_video_duration(input_path)
            cmd = self.build_ffmpeg_export_cmd(input_path, output_path)

            try:
                self.current_process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True, encoding="utf-8", errors="ignore")
                time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
                for line in self.current_process.stderr:
                    if not self.is_running:
                        break
                    match = time_pattern.search(line)
                    if match and duration > 0:
                        cur_sec = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
                        self.after(0, lambda v=min(cur_sec / duration, 1.0): self.progress_bar.set(v))

                self.current_process.wait()
                if self.is_running and self.current_process.returncode == 0:
                    item["status"] = "完成"
                    self.after(0, lambda: self.progress_bar.set(1.0))
                    self.after(0, lambda b=base_name: self.status_text.set(f"导出完成: {b}"))
                elif not self.is_running:
                    item["status"] = "已取消"
                else:
                    item["status"] = "失败"
            except FileNotFoundError:
                item["status"] = "无FFmpeg"
                break
            self.after(0, self.refresh_queue_listbox)

        self.is_running = False
        self.after(0, lambda: self.start_batch_btn.configure(state="normal"))
        self.after(0, lambda: self.stop_btn.configure(state="disabled"))

    def stop_batch_export(self):
        if self.is_running and self.current_process:
            self.is_running = False
            self.current_process.terminate()

    def _on_close(self):
        if self.mpv_player:
            try:
                self.mpv_player.terminate()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = Anime4KApp()
    app.mainloop()