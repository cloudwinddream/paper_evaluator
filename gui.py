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

        load_dotenv()
        self._env_path = Path(".env")
        env = self._load_env()
        score_range = self._load_score_range()

        self.running = False
        self.process = None

        self._build_menu()
        self._build_ui(env, score_range)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_score_range(self) -> dict:
        settings_path = Path("config/settings.yaml")
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = yaml.safe_load(f) or {}
                return settings.get("score_range", {"min": 60, "max": 89})
            except Exception:
                pass
        return {"min": 60, "max": 89}

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

    def _build_ui(self, env, score_range):
        top_frame = ttk.LabelFrame(self, text="配置", padding=12)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))

        self._build_config(top_frame, env, score_range)

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

        self.stop_btn = ttk.Button(
            btn_frame, text="■ 停止", command=self._stop_pipeline, width=10,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=8)

        self.status_label = ttk.Label(btn_frame, text="就绪", foreground="gray")
        self.status_label.pack(side="right", padx=8)

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

    def _build_config(self, parent, env, score_range):
        parent.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(parent, text="论文文件夹:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.papers_var = StringVar(value=env.get("PAPERS_DIR", ""))
        self.papers_entry = ttk.Entry(parent, textvariable=self.papers_var)
        self.papers_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_dir(self.papers_var)
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        ttk.Label(parent, text="题目要求文档:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.req_var = StringVar(value=env.get("REQUIREMENTS_DOC", ""))
        self.req_entry = ttk.Entry(parent, textvariable=self.req_var)
        self.req_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_file(self.req_var, [("文档", "*.doc *.docx *.pdf")])
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        ttk.Label(parent, text="输出目录:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.out_var = StringVar(value=env.get("OUTPUT_DIR", "./outputs"))
        self.out_entry = ttk.Entry(parent, textvariable=self.out_var)
        self.out_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_dir(self.out_var)
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        ttk.Label(parent, text="评分标准文件:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        self.cfg_var = StringVar(value="config/requirements.yaml")
        self.cfg_entry = ttk.Entry(parent, textvariable=self.cfg_var)
        self.cfg_entry.grid(row=row, column=1, sticky="ew", padx=2)
        ttk.Button(parent, text="浏览…", command=lambda: self._browse_file(self.cfg_var, [("YAML", "*.yaml *.yml")])
                   ).grid(row=row, column=2, padx=(4, 0))
        row += 1

        # ── API 配置 ──
        sep = ttk.Separator(parent, orient="horizontal")
        sep.grid(row=row, column=0, columnspan=4, sticky="ew", pady=6)
        row += 1

        ttk.Label(parent, text="LLM 配置", font=("", 10, "bold")
                  ).grid(row=row, column=0, columnspan=4, sticky="w")
        row += 1

        # Provider 1
        self._add_provider_fields(parent, row, 1, env)
        row += 4

        # Provider 2 + 互换按钮
        has_2 = env.get("API_BASE_URL_2") or env.get("API_KEY_2") or env.get("API_MODEL_2")
        self.show_provider_2 = BooleanVar(value=bool(has_2))
        cb_row = row
        chk = ttk.Checkbutton(parent, text="配置备用 Provider（限流/故障时自动切换）",
                              variable=self.show_provider_2,
                              command=lambda: self._toggle_provider_2(parent, cb_row, env))
        chk.grid(row=cb_row, column=0, columnspan=2, sticky="w")
        swap_btn = ttk.Button(parent, text="⇅ 互换", command=self._swap_providers, width=8)
        swap_btn.grid(row=cb_row, column=2, padx=(4, 0))
        self.provider_2_frame = ttk.Frame(parent)
        self.provider_2_frame.grid(row=cb_row + 1, column=0, columnspan=4, sticky="ew",
                                   padx=(0, 0), pady=(2, 0))
        self.provider_2_frame.columnconfigure(1, weight=1)
        if has_2:
            self._add_provider_fields(self.provider_2_frame, 0, 2, env)
        else:
            self.provider_2_frame.grid_remove()
        row = cb_row + 2

        # ── 分数范围 ──
        score_frame = ttk.Frame(parent)
        score_frame.grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(score_frame, text="分数范围:").pack(side="left", padx=(0, 4))
        self.score_min_var = StringVar(value=str(score_range.get("min", 60)))
        ttk.Entry(score_frame, textvariable=self.score_min_var, width=5).pack(side="left")
        ttk.Label(score_frame, text="~").pack(side="left", padx=2)
        self.score_max_var = StringVar(value=str(score_range.get("max", 89)))
        ttk.Entry(score_frame, textvariable=self.score_max_var, width=5).pack(side="left")
        ttk.Label(score_frame, text="（修改后需点击开始评审才会生效）",
                  foreground="gray", font=("", 9)).pack(side="left", padx=(8, 0))
        row += 1

        # ── 选项 ──
        opt_frame = ttk.Frame(parent)
        opt_frame.grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.skip_ai_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="跳过 AI 评审", variable=self.skip_ai_var).pack(side="left", padx=(0, 12))

        self.plagiarism_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="启用查重检测", variable=self.plagiarism_var).pack(side="left", padx=(0, 12))

        self.skip_std_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="使用已有评分标准", variable=self.skip_std_var).pack(side="left", padx=(0, 12))

        self.force_std_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="强制重新生成标准", variable=self.force_std_var).pack(side="left")

    # ── 工具方法 ──

    def _add_provider_fields(self, parent, row, idx, env):
        suffix = f"_{idx}" if idx > 1 else ""
        ttk.Label(parent, text=f"API 地址 {idx}:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        var = StringVar(value=env.get(f"API_BASE_URL{suffix}", ""))
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=2)
        setattr(self, f"api_url_{idx}_var", var)
        row += 1

        ttk.Label(parent, text=f"API 密钥 {idx}:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        var = StringVar(value=env.get(f"API_KEY{suffix}", ""))
        entry = ttk.Entry(parent, textvariable=var, show="*")
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=2)
        show_btn = ttk.Button(parent, text="👁", width=3,
                              command=lambda e=entry: self._toggle_key_visibility(e))
        show_btn.grid(row=row, column=3, padx=(2, 0))
        setattr(self, f"api_key_{idx}_var", var)
        row += 1

        ttk.Label(parent, text=f"模型 {idx}:").grid(row=row, column=0, sticky="w", padx=(0, 6))
        var = StringVar(value=env.get(f"API_MODEL{suffix}", "gpt-4o-mini"))
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=2)
        setattr(self, f"api_model_{idx}_var", var)
        row += 1

    def _swap_providers(self):
        for attr in ["api_url", "api_key", "api_model"]:
            v1 = getattr(self, f"{attr}_1_var", None)
            v2 = getattr(self, f"{attr}_2_var", None)
            if v1 is not None and v2 is not None:
                tmp = v1.get()
                v1.set(v2.get())
                v2.set(tmp)

    def _toggle_key_visibility(self, entry):
        if entry.cget("show") == "*":
            entry.config(show="")
        else:
            entry.config(show="*")

    def _toggle_provider_2(self, parent, row, env):
        if self.show_provider_2.get():
            self.provider_2_frame.grid()
            if not hasattr(self, "api_url_2_var"):
                self._add_provider_fields(self.provider_2_frame, 0, 2,
                                          {"API_BASE_URL_2": "", "API_KEY_2": "", "API_MODEL_2": "gpt-4o-mini"})
        else:
            self.provider_2_frame.grid_remove()

    def _load_env(self) -> dict:
        if self._env_path.exists():
            load_dotenv(self._env_path)
        env = {
            "PAPERS_DIR": os.getenv("PAPERS_DIR", ""),
            "REQUIREMENTS_DOC": os.getenv("REQUIREMENTS_DOC", ""),
            "OUTPUT_DIR": os.getenv("OUTPUT_DIR", "./outputs"),
        }
        for suffix in ["", "_2"]:
            for key in ["API_BASE_URL", "API_KEY", "API_MODEL"]:
                env[f"{key}{suffix}"] = os.getenv(f"{key}{suffix}", "")
        return env

    def _save_to_env(self):
        pairs = [
            ("PAPERS_DIR", self.papers_var.get()),
            ("REQUIREMENTS_DOC", self.req_var.get()),
            ("OUTPUT_DIR", self.out_var.get()),
        ]
        for idx in [1, 2]:
            suffix = f"_{idx}" if idx > 1 else ""
            pairs.append((f"API_BASE_URL{suffix}", getattr(self, f"api_url_{idx}_var").get()))
            pairs.append((f"API_KEY{suffix}", getattr(self, f"api_key_{idx}_var").get()))
            pairs.append((f"API_MODEL{suffix}", getattr(self, f"api_model_{idx}_var").get()))
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
        self.output_text.config(state="normal")
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def _set_running(self, running: bool):
        self.running = running
        state = "disabled" if running else "normal"
        stop_state = "normal" if running else "disabled"
        self.run_btn.config(state=state)
        self.gen_btn.config(state=state)
        self.stop_btn.config(state=stop_state)
        self.status_label.config(text="运行中…" if running else "就绪", foreground="red" if running else "gray")
        if not running:
            self.status_label.config(text="完成", foreground="green")

    def _stop_pipeline(self):
        if self.process:
            self._log("\n⏹ 用户终止\n")
            self.process.kill()
            self.process = None
        self._set_running(False)

    def _on_close(self):
        if self.running and self.process:
            if messagebox.askyesno("确认", "评审正在进行，确定要终止吗？"):
                self._stop_pipeline()
                self.destroy()
            return
        self.destroy()

    # ── 执行流水线 ──

    def _build_args(self, generate_only: bool = False) -> list[str]:
        args = [sys.executable, "main.py"]

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

        args.extend(["--score-min", self.score_min_var.get().strip()])
        args.extend(["--score-max", self.score_max_var.get().strip()])

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

        self._save_to_env()
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
