"""
论文评审系统 - 本地 GUI 界面
保留 CLI（main.py）的同时提供图形化操作入口
"""

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import *
from tkinter import filedialog, messagebox, ttk

import yaml
from dotenv import load_dotenv, set_key


class OutputCapture:
    """捕获子进程输出并回调"""

    def __init__(self, callback):
        self.callback = callback

    def write(self, text):
        if text:
            self.callback(text)

    def flush(self):
        pass


class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("论文评审系统")
        self.geometry("1000x720")
        self.minsize(800, 600)

        # 加载 .env 初始值
        load_dotenv()
        self._env_path = Path(".env")
        env = self._load_env()

        self.running = False
        self.process = None

        self._build_menu()
        self._build_ui(env)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 构建 UI ──

    def _build_menu(self):
        menubar = Menu(self)
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开输出目录", command=self._open_output)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.config(menu=menubar)

    def _build_ui(self, env):
        # ── 主布局：上方配置区 + 下方输出区 ──
        top_frame = ttk.LabelFrame(self, text="配置", padding=12)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))

        self._build_config(top_frame, env)

        # ── 操作按钮 ──
        btn_frame = ttk.Frame(self, padding=8)
        btn_frame.pack(fill="x", padx=10)

        self.run_btn = ttk.Button(
            btn_frame, text="▶ 开始评审", command=self._run_pipeline, width=20
        )
        self.run_btn.pack(side="left", padx=(0, 8))

        self.gen_btn = ttk.Button(
            btn_frame, text="仅生成评分标准", command=self._generate_only, width=18
        )
        self.gen_btn.pack(side="left", padx=8)

        self.status_label = ttk.Label(btn_frame, text="就绪", foreground="gray")
        self.status_label.pack(side="right", padx=8)

        # ── 输出区 ──
        out_frame = ttk.LabelFrame(self, text="运行日志", padding=8)
        out_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.output_text = Text(out_frame, wrap="word", state="disabled",
                                font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white")
        scrollbar = ttk.Scrollbar(out_frame, orient="vertical",
                                  command=self.output_text.yview)
        self.output_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.output_text.pack(fill="both", expand=True)

    def _build_config(self, parent, env):
        # 使用 grid 布局
        parent.columnconfigure(1, weight=1)

        row = 0
        # 论文文件夹
        ttk.Label(parent, text="论文文件夹:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.papers_var = StringVar(value=env.get("PAPERS_DIR", ""))
        self.papers_entry = ttk.Entry(parent, textvariable=self.papers_var)
        self.papers_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_dir(self.papers_var)
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        # 题目要求
        ttk.Label(parent, text="题目要求文档:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.req_var = StringVar(value=env.get("REQUIREMENTS_DOC", ""))
        self.req_entry = ttk.Entry(parent, textvariable=self.req_var)
        self.req_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_file(self.req_var, [("Word文档", "*.doc *.docx")])
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        # 输出目录
        ttk.Label(parent, text="输出目录:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.out_var = StringVar(value=env.get("OUTPUT_DIR", "./outputs"))
        self.out_entry = ttk.Entry(parent, textvariable=self.out_var)
        self.out_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_dir(self.out_var)
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        # 配置文件
        ttk.Label(parent, text="评分标准文件:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.cfg_var = StringVar(value="config/requirements.yaml")
        self.cfg_entry = ttk.Entry(parent, textvariable=self.cfg_var)
        self.cfg_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_file(self.cfg_var, [("YAML", "*.yaml *.yml")])
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        # ── 选项（第二行） ──
        opt_frame = ttk.Frame(parent)
        opt_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.skip_ai_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="跳过 AI 评审", variable=self.skip_ai_var).pack(side="left", padx=(0, 12))

        self.plagiarism_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="启用查重检测", variable=self.plagiarism_var).pack(side="left", padx=(0, 12))

        self.skip_std_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="使用已有评分标准", variable=self.skip_std_var).pack(side="left", padx=(0, 12))

        self.force_std_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="强制重新生成标准", variable=self.force_std_var).pack(side="left")

    # ── 工具方法 ──

    def _load_env(self) -> dict:
        if self._env_path.exists():
            load_dotenv(self._env_path)
        return {
            "PAPERS_DIR": os.getenv("PAPERS_DIR", ""),
            "REQUIREMENTS_DOC": os.getenv("REQUIREMENTS_DOC", ""),
            "OUTPUT_DIR": os.getenv("OUTPUT_DIR", "./outputs"),
        }

    def _save_to_env(self):
        """将当前界面值写入 .env"""
        pairs = [
            ("PAPERS_DIR", self.papers_var.get()),
            ("REQUIREMENTS_DOC", self.req_var.get()),
            ("OUTPUT_DIR", self.out_var.get()),
        ]
        for key, val in pairs:
            set_key(str(self._env_path), key, val)

    def _browse_dir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _browse_file(self, var, filetypes):
        f = filedialog.askopenfilename(filetypes=filetypes)
        if f:
            var.set(f)

    def _open_output(self):
        out = self.out_var.get() or "./outputs"
        p = Path(out)
        if p.exists():
            os.startfile(p)

    def _show_about(self):
        messagebox.showinfo("关于", "论文评审系统 v1.0\n课程设计报告自动检测与评分")

    def _log(self, text):
        """向输出框追加文本"""
        self.output_text.config(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def _set_running(self, running: bool):
        self.running = running
        state = "disabled" if running else "normal"
        self.run_btn.config(state=state)
        self.gen_btn.config(state=state)
        self.status_label.config(text="运行中…" if running else "就绪", foreground="red" if running else "gray")
        if not running:
            self.status_label.config(text="完成", foreground="green")

    def _on_close(self):
        if self.running and self.process:
            if messagebox.askyesno("确认", "评审正在进行，确定要终止吗？"):
                self.process.kill()
                self.destroy()
            return
        self.destroy()

    # ── 执行流水线 ──

    def _build_args(self, generate_only: bool = False) -> list[str]:
        args = ["python", "main.py"]

        # 路径参数
        papers = self.papers_var.get().strip()
        if papers:
            args.extend(["--papers", papers])

        req = self.req_var.get().strip()
        if req:
            args.extend(["--requirements-doc", req])

        out = self.out_var.get().strip()
        if out:
            args.extend(["--output", out])

        cfg = self.cfg_var.get().strip()
        if cfg:
            args.extend(["--config", cfg])

        # 选项
        if self.skip_ai_var.get():
            args.append("--skip-ai")
        if self.plagiarism_var.get():
            args.append("--plagiarism")
        if generate_only:
            args.append("--generate-standards")
        else:
            if self.skip_std_var.get():
                args.append("--skip-standards")
            if self.force_std_var.get():
                args.append("--force-standards")

        return args

    def _run_pipeline(self):
        if self.running:
            return

        # 先保存 .env
        self._save_to_env()

        # 清空输出
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")

        self._set_running(True)
        args = self._build_args(generate_only=False)
        self._log(f"{' '.join(args)}\n{'='*60}\n")
        threading.Thread(target=self._run_subprocess, args=(args,), daemon=True).start()

    def _generate_only(self):
        if self.running:
            return

        self._save_to_env()
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")

        self._set_running(True)
        args = self._build_args(generate_only=True)
        self._log(f"{' '.join(args)}\n{'='*60}\n")
        threading.Thread(target=self._run_subprocess, args=(args,), daemon=True).start()

    def _run_subprocess(self, args: list[str]):
        """在后台线程运行 main.py 子进程"""
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                bufsize=1,
            )

            for line in iter(self.process.stdout.readline, ""):
                if not line:
                    break
                self.after(0, self._log, line)

            self.process.wait()
            if self.process.returncode == 0:
                self.after(0, lambda: self._set_running(False))
            else:
                self.after(0, lambda: self._log(f"\n✗ 进程退出码: {self.process.returncode}\n"))
                self.after(0, lambda: self._set_running(False))

        except Exception as e:
            self.after(0, lambda: self._log(f"\n✗ 错误: {e}\n"))
            self.after(0, lambda: self._set_running(False))
        finally:
            self.process = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
