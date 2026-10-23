import os
import sys
import subprocess
import threading
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# 设置界面主题
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Anime4K v4 标准着色器组合预设
ANIME4K_MODES = {
    "Mode A (快速修复+超分 - 适合1080p低画质)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "Mode B (柔和去噪+超分 - 适合有噪点番剧)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_Soft_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "Mode C (仅无损超分 - 适合高画质片源)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Upscale_Denoise_CNN_x2_M.glsl",
    ],
    "Mode A+A (极致高清重制 - 适合高配显卡)": [
        "Anime4K_Clamp_Highlights.glsl",
        "Anime4K_Restore_CNN_VL.glsl",
        "Anime4K_Upscale_CNN_x2_VL.glsl",
        "Anime4K_Restore_CNN_M.glsl",
        "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    "仅基础锐化超分 (最快速度 / 兼容无Vulkan环境)": []
}

RESOLUTION_MAP = {
    "1080P (1920x1080)": (1920, 1080),
    "2K QHD (2560x1440)": (2560, 1440),
    "4K UHD (3840x2160)": (3840, 2160),
}


class Anime4KApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Anime4K 视频超分导出工具 v1.0")
        self.geometry("760x680")
        self.resizable(False, False)

        # 状态变量
        self.input_video_path = ctk.StringVar()
        self.output_dir_path = ctk.StringVar(value=os.path.join(os.getcwd(), "output"))
        self.shader_dir_path = ctk.StringVar(value=os.path.join(os.getcwd(), "shaders"))
        self.selected_mode = ctk.StringVar(value=list(ANIME4K_MODES.keys())[0])
        self.selected_res = ctk.StringVar(value="4K UHD (3840x2160)")
        self.selected_fps = ctk.StringVar(value="保持原视频帧率")
        self.frame_delay_ms = ctk.StringVar(value="0")
        self.frame_interp_mode = ctk.StringVar(value="关闭补帧 (直接帧率转换)")
        self.encoder_choice = ctk.StringVar(value="libx264 (CPU 通用高兼容)")

        self.process = None
        self.is_running = False

        self._build_ui()

    def _build_ui(self):
        # 标题栏
        title_label = ctk.CTkLabel(
            self, text="🎬 Anime4K 视频超分辨率导出程序",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(pady=(15, 10))

        # 1. 文件与目录选择区
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", padx=20, pady=8)

        # 导入视频
        ctk.CTkLabel(file_frame, text="输入视频:", width=85, anchor="w").grid(row=0, column=0, padx=10, pady=8)
        ctk.CTkEntry(file_frame, textvariable=self.input_video_path, width=480).grid(row=0, column=1, padx=5, pady=8)
        ctk.CTkButton(file_frame, text="选择视频", width=110, command=self.browse_input_video).grid(row=0, column=2, padx=10, pady=8)

        # Shader 文件夹
        ctk.CTkLabel(file_frame, text="Shader目录:", width=85, anchor="w").grid(row=1, column=0, padx=10, pady=8)
        ctk.CTkEntry(file_frame, textvariable=self.shader_dir_path, width=480).grid(row=1, column=1, padx=5, pady=8)
        ctk.CTkButton(file_frame, text="选择目录", width=110, command=self.browse_shader_dir).grid(row=1, column=2, padx=10, pady=8)

        # 输出文件夹
        ctk.CTkLabel(file_frame, text="输出目录:", width=85, anchor="w").grid(row=2, column=0, padx=10, pady=8)
        ctk.CTkEntry(file_frame, textvariable=self.output_dir_path, width=480).grid(row=2, column=1, padx=5, pady=8)
        ctk.CTkButton(file_frame, text="目标文件夹", width=110, command=self.browse_output_dir).grid(row=2, column=2, padx=10, pady=8)

        # 2. 超分清晰度与算法设置区
        upscale_frame = ctk.CTkFrame(self)
        upscale_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(upscale_frame, text="⚡ 超分与清晰度设置", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=(10, 5), sticky="w"
        )

        ctk.CTkLabel(upscale_frame, text="目标清晰度:", width=90, anchor="w").grid(row=1, column=0, padx=12, pady=8)
        ctk.CTkOptionMenu(
            upscale_frame, variable=self.selected_res,
            values=list(RESOLUTION_MAP.keys()), width=220
        ).grid(row=1, column=1, padx=5, pady=8, sticky="w")

        ctk.CTkLabel(upscale_frame, text="编码器:", width=70, anchor="w").grid(row=1, column=2, padx=12, pady=8)
        ctk.CTkOptionMenu(
            upscale_frame, variable=self.encoder_choice,
            values=["libx264 (CPU 通用高兼容)", "h264_nvenc (NVIDIA 显卡加速)", "hevc_nvenc (NVIDIA H.265)"],
            width=230
        ).grid(row=1, column=3, padx=5, pady=8, sticky="w")

        ctk.CTkLabel(upscale_frame, text="Anime4K模式:", width=90, anchor="w").grid(row=2, column=0, padx=12, pady=8)
        ctk.CTkOptionMenu(
            upscale_frame, variable=self.selected_mode,
            values=list(ANIME4K_MODES.keys()), width=550
        ).grid(row=2, column=1, columnspan=3, padx=5, pady=8, sticky="w")

        # 3. 帧率与延迟设置区
        fps_frame = ctk.CTkFrame(self)
        fps_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(fps_frame, text="⏱️ 帧率与帧延迟控制", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=4, padx=12, pady=(10, 5), sticky="w"
        )

        ctk.CTkLabel(fps_frame, text="输出帧率:", width=90, anchor="w").grid(row=1, column=0, padx=12, pady=8)
        ctk.CTkOptionMenu(
            fps_frame, variable=self.selected_fps,
            values=["保持原视频帧率", "24 FPS", "30 FPS", "60 FPS", "120 FPS"],
            width=220
        ).grid(row=1, column=1, padx=5, pady=8, sticky="w")

        ctk.CTkLabel(fps_frame, text="帧率延迟(ms):", width=90, anchor="w").grid(row=1, column=2, padx=12, pady=8)
        ctk.CTkEntry(
            fps_frame, textvariable=self.frame_delay_ms,
            placeholder_text="如: 0, 50, -50", width=210
        ).grid(row=1, column=3, padx=5, pady=8, sticky="w")

        ctk.CTkLabel(fps_frame, text="帧补偿策略:", width=90, anchor="w").grid(row=2, column=0, padx=12, pady=8)
        ctk.CTkOptionMenu(
            fps_frame, variable=self.frame_interp_mode,
            values=[
                "关闭补帧 (直接帧率转换)",
                "帧混合平滑 (Frame Blending - 快速)",
                "光流运动补偿补帧 (Motion Interpolation - 较慢)"
            ],
            width=550
        ).grid(row=2, column=1, columnspan=3, padx=5, pady=8, sticky="w")

        # 4. 进度条与控制按钮
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=8)

        self.progress_bar = ctk.CTkProgressBar(ctrl_frame, width=720)
        self.progress_bar.pack(pady=(4, 10))
        self.progress_bar.set(0)

        btn_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_box.pack(fill="x")

        self.start_btn = ctk.CTkButton(
            btn_box, text="🚀 开始超分处理并导出", height=40,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1f6aa5", command=self.start_processing
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            btn_box, text="⏹ 停止任务", height=40,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#b02a37", state="disabled", command=self.stop_processing
        )
        self.stop_btn.pack(side="right", width=150)

        # 5. 日志输出框
        self.log_box = ctk.CTkTextbox(self, height=150, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        self.log("系统就绪。请选择输入视频与目标文件夹后点击开始。")

    # ---------------- 事件处理 ----------------
    def log(self, message: str):
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def browse_input_video(self):
        path = filedialog.askopenfilename(
            title="选择输入视频文件",
            filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm"), ("所有文件", "*.*")]
        )
        if path:
            self.input_video_path.set(path)
            self.log(f"已导入视频: {path}")

    def browse_shader_dir(self):
        path = filedialog.askdirectory(title="选择包含 Anime4K .glsl 文件的文件夹")
        if path:
            self.shader_dir_path.set(path)
            self.log(f"已设置 Shader 目录: {path}")

    def browse_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目标文件夹")
        if path:
            self.output_dir_path.set(path)
            self.log(f"已设置输出目录: {path}")

    def build_ffmpeg_command(self, input_path: str, output_path: str) -> list:
        target_w, target_h = RESOLUTION_MAP[self.selected_res.get()]
        mode_name = self.selected_mode.get()
        shader_files = ANIME4K_MODES[mode_name]
        shader_dir = self.shader_dir_path.get()

        vf_filters = []

        # 1. 构建 Anime4K 超分滤镜链
        valid_shaders = []
        for s in shader_files:
            full_s = os.path.join(shader_dir, s)
            if os.path.exists(full_s):
                valid_shaders.append(full_s)

        if valid_shaders:
            # 使用 FFmpeg 的 libplacebo 加载 Anime4K GLSL 着色器
            # 对 Windows 路径进行转义兼容 FFmpeg 滤镜语法
            for idx, s_path in enumerate(valid_shaders):
                escaped_path = s_path.replace("\\", "/").replace(":", "\\:")
                if idx == len(valid_shaders) - 1:
                    vf_filters.append(f"libplacebo=w={target_w}:h={target_h}:custom_shader_path='{escaped_path}'")
                else:
                    vf_filters.append(f"libplacebo=custom_shader_path='{escaped_path}'")
        else:
            # 如果未找到 .glsl 文件或选择了基础模式，自动回退到高画质 Lanczos + 边缘锐化模拟 Anime4K 基础效果
            self.log("⚠️ 提示: 未检测到本地 .glsl 文件或已选基础模式，将使用 Lanczos + 动漫边缘锐化超分管线。")
            vf_filters.append(f"scale={target_w}:{target_h}:flags=lanczos,unsharp=5:5:0.8:3:3:0.4")

        # 2. 构建帧率延迟 (PTS 偏移)
        try:
            delay_ms = float(self.frame_delay_ms.get().strip())
        except ValueError:
            delay_ms = 0.0

        if delay_ms != 0:
            delay_sec = delay_ms / 1000.0
            vf_filters.append(f"setpts=PTS+({delay_sec}/TB)")

        # 3. 构建目标帧率与补帧控制
        fps_choice = self.selected_fps.get()
        interp_choice = self.frame_interp_mode.get()
        if fps_choice != "保持原视频帧率":
            fps_val = int(fps_choice.split()[0])
            if "光流运动补偿" in interp_choice:
                vf_filters.append(f"minterpolate=fps={fps_val}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
            elif "帧混合平滑" in interp_choice:
                vf_filters.append(f"minterpolate=fps={fps_val}:mi_mode=blend")
            else:
                vf_filters.append(f"fps={fps_val}")

        # 4. 编码器选择
        enc_str = self.encoder_choice.get().split()[0]

        cmd = ["ffmpeg", "-y"]
        if valid_shaders:
            cmd += ["-init_hw_device", "vulkan"]

        cmd += [
            "-i", input_path,
            "-vf", ",".join(vf_filters),
            "-c:v", enc_str,
            "-crf", "18" if "libx264" in enc_str else "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path
        ]
        return cmd

    def get_video_duration(self, input_path: str) -> float:
        """获取视频总时长（秒），用于计算进度条"""
        try:
            res = subprocess.run(
                ["ffmpeg", "-i", input_path],
                stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
            )
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if match:
                h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
                return h * 3600 + m * 60 + s
        except Exception:
            pass
        return 0.0

    def start_processing(self):
        input_path = self.input_video_path.get().strip()
        output_dir = self.output_dir_path.get().strip()

        if not input_path or not os.path.exists(input_path):
            messagebox.showwarning("提示", "请先选择有效的输入视频文件！")
            return

        os.makedirs(output_dir, exist_ok=True)

        base_name, ext = os.path.splitext(os.path.basename(input_path))
        res_tag = self.selected_res.get().split()[0]
        output_path = os.path.join(output_dir, f"{base_name}_Anime4K_{res_tag}.mp4")

        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_bar.set(0)

        threading.Thread(
            target=self._run_ffmpeg_worker,
            args=(input_path, output_path),
            daemon=True
        ).start()

    def _run_ffmpeg_worker(self, input_path: str, output_path: str):
        total_duration = self.get_video_duration(input_path)
        cmd = self.build_ffmpeg_command(input_path, output_path)

        self.log("=" * 55)
        self.log(f"开始执行任务 -> 输出文件: {output_path}")
        self.log(f"执行命令: {' '.join(cmd)}")

        try:
            self.process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore"
            )

            time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            for line in self.process.stderr:
                if not self.is_running:
                    break
                match = time_pattern.search(line)
                if match and total_duration > 0:
                    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
                    current_sec = h * 3600 + m * 60 + s
                    progress = min(current_sec / total_duration, 1.0)
                    self.progress_bar.set(progress)

            self.process.wait()

            if self.is_running and self.process.returncode == 0:
                self.progress_bar.set(1.0)
                self.log(f"✅ 处理完成！文件已保存至: {output_path}")
                messagebox.showinfo("完成", f"视频超分导出成功！\n保存位置:\n{output_path}")
            elif not self.is_running:
                self.log("⏹ 任务已被用户手动终止。")
            else:
                self.log(f"❌ 处理出错，FFmpeg 返回码: {self.process.returncode}")
                messagebox.showerror("错误", "处理过程中发生错误，请检查 FFmpeg 是否安装或查看底部日志。")

        except FileNotFoundError:
            self.log("❌ 未找到 ffmpeg，请先安装 FFmpeg 并将其加入系统环境变量 PATH！")
            messagebox.showerror("缺少组件", "未检测到 FFmpeg！请先下载安装 FFmpeg。")
        except Exception as e:
            self.log(f"❌ 发生异常: {str(e)}")
        finally:
            self.is_running = False
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    def stop_processing(self):
        if self.process and self.is_running:
            self.is_running = False
            self.process.terminate()


if __name__ == "__main__":
    app = Anime4KApp()
    app.mainloop()