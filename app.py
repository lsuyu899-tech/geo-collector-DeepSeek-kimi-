#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

try:
    import Queue as queue  # py2 fallback
except Exception:
    import queue

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:
    raise RuntimeError("tkinter is required to run this GUI.")


APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = APP_DIR
COLLECTOR_SCRIPT = os.path.join(ROOT_DIR, "collector.py")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

START_RE = re.compile(r"start\.\s*total=(\d+),\s*pending=(\d+),\s*workers=(\d+),\s*providers=(.+)")


def count_csv_rows(path):
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            n = sum(1 for _ in f) - 1
            return n if n > 0 else 0
    except Exception:
        return 0


def format_seconds(seconds):
    if seconds is None:
        return "--:--"
    try:
        s = int(max(0, seconds))
    except Exception:
        return "--:--"
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return "{:02d}:{:02d}:{:02d}".format(h, m, sec)
    return "{:02d}:{:02d}".format(m, sec)


class App(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.title("GEO 批量来源采集器（独立版）")
        self.geometry("1120x760")
        self.minsize(980, 680)

        self.proc = None
        self.reader_thread = None
        self.log_queue = queue.Queue()
        self.running = False

        self.base_rows = 0
        self.pending_total = 0
        self.run_start_ts = None
        self.output_path_runtime = ""
        self.summary_path_runtime = ""

        self._build_vars()
        self._build_ui()
        self._load_settings()
        self._refresh_summary_path_preview()

    def _build_vars(self):
        self.input_path = tk.StringVar(value=os.path.join(ROOT_DIR, "questions.csv"))
        self.output_path = tk.StringVar(value=os.path.join(ROOT_DIR, "结果_gui.csv"))
        self.summary_path = tk.StringVar(value="")
        self.question_column = tk.StringVar(value="question")
        self.providers = tk.StringVar(value="kimi,doubao,deepseek")
        self.workers = tk.StringVar(value="2")
        self.deepseek_mode = tk.StringVar(value="api")
        self.kimi_model = tk.StringVar(value="kimi-k2.5")
        self.doubao_model = tk.StringVar(value="doubao-seed-2-0-pro-260215")
        self.resume = tk.IntVar(value=1)

        self.moonshot_key = tk.StringVar(value="")
        self.ark_key = tk.StringVar(value="")
        self.deepseek_key = tk.StringVar(value="")
        self.show_api_plain = tk.IntVar(value=0)
        self.moonshot_state = tk.StringVar(value="未填写")
        self.ark_state = tk.StringVar(value="未填写")
        self.deepseek_state = tk.StringVar(value="未填写")

        self.progress_text = tk.StringVar(value="等待开始")
        self.status_text = tk.StringVar(value="就绪")
        self.summary_preview = tk.StringVar(value="")

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(root, text="参数配置", padding=10)
        top.pack(fill=tk.X)

        r = 0
        self._add_path_row(top, r, "问题文件", self.input_path, self._pick_input_file)
        r += 1
        self._add_path_row(top, r, "结果文件", self.output_path, self._pick_output_file)
        r += 1
        self._add_path_row(top, r, "汇总文件（可选）", self.summary_path, self._pick_summary_file)
        r += 1

        ttk.Label(top, text="问题列名").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(top, textvariable=self.question_column, width=20).grid(row=r, column=1, sticky="w", pady=6)
        ttk.Label(top, text="Providers").grid(row=r, column=2, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.providers, width=34).grid(row=r, column=3, sticky="w", pady=6)
        ttk.Label(top, text="DeepSeek模式").grid(row=r, column=4, sticky="w", padx=(16, 8), pady=6)
        ttk.Combobox(top, textvariable=self.deepseek_mode, state="readonly", values=["skip", "api"], width=10).grid(
            row=r, column=5, sticky="w", pady=6
        )
        r += 1

        ttk.Label(top, text="Workers").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=6)
        tk.Spinbox(top, from_=1, to=16, textvariable=self.workers, width=8).grid(row=r, column=1, sticky="w", pady=6)
        ttk.Label(top, text="Kimi模型").grid(row=r, column=2, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.kimi_model, width=26).grid(row=r, column=3, sticky="w", pady=6)
        ttk.Label(top, text="豆包模型/接入点").grid(row=r, column=4, sticky="w", padx=(16, 8), pady=6)
        ttk.Entry(top, textvariable=self.doubao_model, width=24).grid(row=r, column=5, sticky="w", pady=6)
        r += 1

        ttk.Checkbutton(top, text="断点续跑（--resume）", variable=self.resume).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=6
        )
        ttk.Label(top, textvariable=self.summary_preview, foreground="#666").grid(
            row=r, column=2, columnspan=4, sticky="w", padx=(16, 0), pady=6
        )
        r += 1

        key_frame = ttk.LabelFrame(root, text="API Key（仅本次运行使用，不写入配置文件）", padding=10)
        key_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(key_frame, text="MOONSHOT_API_KEY").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry_moonshot = ttk.Entry(key_frame, textvariable=self.moonshot_key, show="*", width=38)
        self.entry_moonshot.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(key_frame, textvariable=self.moonshot_state, foreground="#666").grid(row=0, column=4, sticky="w", padx=(8, 0), pady=4)

        ttk.Label(key_frame, text="ARK_API_KEY").grid(row=0, column=2, sticky="w", padx=(16, 8), pady=4)
        self.entry_ark = ttk.Entry(key_frame, textvariable=self.ark_key, show="*", width=38)
        self.entry_ark.grid(row=0, column=3, sticky="w", pady=4)
        ttk.Label(key_frame, textvariable=self.ark_state, foreground="#666").grid(row=0, column=5, sticky="w", padx=(8, 0), pady=4)

        ttk.Label(key_frame, text="DEEPSEEK_API_KEY").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry_deepseek = ttk.Entry(key_frame, textvariable=self.deepseek_key, show="*", width=38)
        self.entry_deepseek.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(key_frame, textvariable=self.deepseek_state, foreground="#666").grid(row=1, column=4, sticky="w", padx=(8, 0), pady=4)

        self.btn_toggle_api = ttk.Button(key_frame, text="显示API明文", command=self._toggle_api_visibility)
        self.btn_toggle_api.grid(row=1, column=2, sticky="w", padx=(16, 8), pady=4)
        ttk.Button(key_frame, text="清空全部API", command=self._clear_api_fields).grid(row=1, column=3, sticky="w", pady=4)

        action = ttk.Frame(root)
        action.pack(fill=tk.X, pady=(10, 0))
        self.btn_start = ttk.Button(action, text="开始运行", command=self._start)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(action, text="停止", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action, text="打开结果文件", command=self._open_output).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(action, text="打开汇总文件", command=self._open_summary).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action, text="打开项目目录", command=self._open_project_dir).pack(side=tk.RIGHT)

        prog = ttk.Frame(root)
        prog.pack(fill=tk.X, pady=(10, 0))
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)
        ttk.Label(prog, textvariable=self.progress_text).pack(anchor="w", pady=(4, 0))
        ttk.Label(prog, textvariable=self.status_text, foreground="#555").pack(anchor="w", pady=(2, 0))

        log_frame = ttk.LabelFrame(root, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scroll.set)

        self._bind_var_write(self.output_path, self._refresh_summary_path_preview)
        self._bind_var_write(self.summary_path, self._refresh_summary_path_preview)
        self._bind_var_write(self.moonshot_key, self._refresh_api_status)
        self._bind_var_write(self.ark_key, self._refresh_api_status)
        self._bind_var_write(self.deepseek_key, self._refresh_api_status)
        self._refresh_api_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _bind_var_write(self, var, callback):
        try:
            var.trace_add("write", lambda *_: callback())
        except Exception:
            var.trace("w", lambda *_: callback())

    def _toggle_api_visibility(self):
        show_plain = (self.show_api_plain.get() == 0)
        self.show_api_plain.set(1 if show_plain else 0)
        mask = "" if show_plain else "*"
        self.entry_moonshot.configure(show=mask)
        self.entry_ark.configure(show=mask)
        self.entry_deepseek.configure(show=mask)
        self.btn_toggle_api.configure(text=("隐藏API明文" if show_plain else "显示API明文"))

    def _clear_api_fields(self):
        self.moonshot_key.set("")
        self.ark_key.set("")
        self.deepseek_key.set("")
        self._refresh_api_status()

    def _refresh_api_status(self):
        ms = self._sanitize_key(self.moonshot_key.get())
        ark = self._sanitize_key(self.ark_key.get())
        ds = self._sanitize_key(self.deepseek_key.get())
        self.moonshot_state.set("已填写({}位)".format(len(ms)) if ms else "未填写")
        self.ark_state.set("已填写({}位)".format(len(ark)) if ark else "未填写")
        self.deepseek_state.set("已填写({}位)".format(len(ds)) if ds else "未填写")

    def _add_path_row(self, parent, row, label, var, callback):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var, width=92).grid(row=row, column=1, columnspan=4, sticky="we", pady=4)
        ttk.Button(parent, text="浏览", command=callback).grid(row=row, column=5, sticky="w", pady=4)

    def _pick_input_file(self):
        p = filedialog.askopenfilename(
            title="选择问题文件",
            filetypes=[("CSV/TXT", "*.csv *.txt"), ("All Files", "*.*")],
            initialdir=ROOT_DIR,
        )
        if p:
            self.input_path.set(p)

    def _pick_output_file(self):
        p = filedialog.asksaveasfilename(
            title="选择结果文件",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All Files", "*.*")],
            initialdir=ROOT_DIR,
            initialfile=os.path.basename(self.output_path.get() or "结果_gui.csv"),
        )
        if p:
            self.output_path.set(p)

    def _pick_summary_file(self):
        p = filedialog.asksaveasfilename(
            title="选择汇总文件",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All Files", "*.*")],
            initialdir=ROOT_DIR,
            initialfile="渠道统计汇总.csv",
        )
        if p:
            self.summary_path.set(p)

    def _default_summary_path(self, output_path):
        base, ext = os.path.splitext(output_path)
        if not ext:
            ext = ".csv"
        return base + "_渠道统计汇总" + ext

    def _refresh_summary_path_preview(self):
        out = (self.output_path.get() or "").strip()
        if not out:
            self.summary_preview.set("汇总文件：等待你先选择结果文件")
            return
        custom = (self.summary_path.get() or "").strip()
        real_summary = custom if custom else self._default_summary_path(out)
        self.summary_preview.set("汇总文件：{}".format(real_summary))

    def _append_log(self, text):
        if not text:
            return
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _build_cmd(self):
        cmd = [
            sys.executable,
            COLLECTOR_SCRIPT,
            "--input",
            self.input_path.get().strip(),
            "--output",
            self.output_path.get().strip(),
            "--question-column",
            self.question_column.get().strip() or "question",
            "--providers",
            self.providers.get().strip() or "kimi,doubao,deepseek",
            "--workers",
            str(int(self.workers.get().strip())),
            "--deepseek-mode",
            (self.deepseek_mode.get().strip() or "skip"),
            "--kimi-model",
            self.kimi_model.get().strip() or "kimi-k2.5",
        ]

        doubao_model = self.doubao_model.get().strip()
        if doubao_model:
            cmd.extend(["--doubao-model", doubao_model])

        summary_out = self.summary_path.get().strip()
        if summary_out:
            cmd.extend(["--summary-output", summary_out])

        if self.resume.get():
            cmd.append("--resume")
        return cmd

    def _sanitize_key(self, raw):
        k = (raw or "").strip()
        k = k.strip('"').strip("'")
        k = k.replace("\r", "").replace("\n", "").strip()
        return k

    def _selected_providers(self):
        raw = self.providers.get().strip()
        if not raw:
            raw = "kimi,doubao,deepseek"
        return set([x.strip().lower() for x in raw.split(",") if x.strip()])

    def _validate_before_start(self):
        if not os.path.exists(COLLECTOR_SCRIPT):
            messagebox.showerror("错误", "找不到主脚本：\n{}".format(COLLECTOR_SCRIPT))
            return False
        input_file = self.input_path.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "问题文件不存在，请先选择正确路径。")
            return False
        try:
            w = int(self.workers.get().strip())
            if w < 1:
                raise ValueError("workers<1")
        except Exception:
            messagebox.showerror("错误", "Workers 必须是 >= 1 的整数。")
            return False

        providers = self._selected_providers()
        moonshot = self._sanitize_key(self.moonshot_key.get())
        ark = self._sanitize_key(self.ark_key.get())
        deepseek = self._sanitize_key(self.deepseek_key.get())
        deepseek_mode = (self.deepseek_mode.get().strip() or "skip").lower()

        if "kimi" in providers and not moonshot:
            messagebox.showerror("错误", "你选择了 Kimi，但没有填写 MOONSHOT_API_KEY。")
            return False
        if "doubao" in providers:
            if not ark:
                messagebox.showerror("错误", "你选择了豆包，但没有填写 ARK_API_KEY。")
                return False
            if not (self.doubao_model.get().strip()):
                messagebox.showerror("错误", "你选择了豆包，但没有填写豆包模型/接入点。")
                return False
        if "deepseek" in providers and deepseek_mode == "api" and not deepseek:
            messagebox.showerror("错误", "你选择了 DeepSeek(api)，但没有填写 DEEPSEEK_API_KEY。")
            return False
        return True

    def _start(self):
        if self.running:
            return
        if not self._validate_before_start():
            return

        cmd = self._build_cmd()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # Always clear inherited keys first to avoid stale system env interference.
        env.pop("MOONSHOT_API_KEY", None)
        env.pop("ARK_API_KEY", None)
        env.pop("DEEPSEEK_API_KEY", None)

        moonshot = self._sanitize_key(self.moonshot_key.get())
        ark = self._sanitize_key(self.ark_key.get())
        deepseek = self._sanitize_key(self.deepseek_key.get())

        if moonshot:
            env["MOONSHOT_API_KEY"] = moonshot
        if ark:
            env["ARK_API_KEY"] = ark
        if deepseek:
            env["DEEPSEEK_API_KEY"] = deepseek

        self.output_path_runtime = self.output_path.get().strip()
        self.summary_path_runtime = (self.summary_path.get().strip() or self._default_summary_path(self.output_path_runtime))
        self.base_rows = count_csv_rows(self.output_path_runtime)
        self.pending_total = 0
        self.run_start_ts = time.time()
        self.progress["value"] = 0
        self.progress_text.set("准备启动...")
        self.status_text.set("运行中")
        self._append_log("=" * 80)
        self._append_log("启动命令：{}".format(" ".join(['"{}"'.format(x) if " " in x else x for x in cmd])))

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=ROOT_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self.status_text.set("启动失败")
            return

        self.running = True
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self._save_settings()

        self.reader_thread = threading.Thread(target=self._read_output_thread, args=(self.proc,))
        self.reader_thread.daemon = True
        self.reader_thread.start()
        self.after(120, self._drain_log_queue)
        self.after(800, self._refresh_progress_by_output_rows)

    def _read_output_thread(self, proc):
        try:
            while True:
                line = proc.stdout.readline()
                if line == "" and proc.poll() is not None:
                    break
                if line:
                    self.log_queue.put(line.rstrip("\n").rstrip("\r"))
        except Exception as e:
            self.log_queue.put("[GUI读取日志异常] {}".format(str(e)))
        finally:
            code = proc.poll()
            if code is None:
                code = proc.wait()
            self.log_queue.put("__PROCESS_END__:{}".format(code))

    def _drain_log_queue(self):
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, str) and item.startswith("__PROCESS_END__:"):
                code = int(item.split(":", 1)[1])
                self._on_process_end(code)
                continue

            self._append_log(item)
            m = START_RE.search(item)
            if m:
                self.pending_total = int(m.group(2))
                if self.pending_total == 0:
                    self.progress["value"] = 100
                    self.progress_text.set("无需处理（pending=0）")

        if self.running:
            self.after(120, self._drain_log_queue)

    def _refresh_progress_by_output_rows(self):
        if not self.running:
            return

        if self.pending_total <= 0:
            self.progress_text.set("等待任务总数信息...")
            self.after(800, self._refresh_progress_by_output_rows)
            return

        now_rows = count_csv_rows(self.output_path_runtime)
        done = now_rows - self.base_rows
        if done < 0:
            done = 0
        if done > self.pending_total:
            done = self.pending_total

        pct = (float(done) / float(self.pending_total)) * 100.0
        self.progress["value"] = pct

        elapsed = time.time() - self.run_start_ts if self.run_start_ts else 0
        eta = None
        speed = 0.0
        if done > 0 and elapsed > 0:
            speed = float(done) / float(elapsed)
            remain = self.pending_total - done
            if speed > 0:
                eta = remain / speed

        self.progress_text.set(
            "已完成 {}/{} ({:.1f}%)  速度 {:.2f}条/秒  预计剩余 {}".format(
                done, self.pending_total, pct, speed, format_seconds(eta)
            )
        )
        self.after(800, self._refresh_progress_by_output_rows)

    def _stop(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            self._append_log("[GUI] 已发送停止信号（terminate）。")
            self.status_text.set("停止中...")
        except Exception as e:
            self._append_log("[GUI] 停止失败：{}".format(str(e)))

    def _on_process_end(self, code):
        self.running = False
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

        if code == 0:
            self.progress["value"] = 100
            self.status_text.set("已完成")
            self._append_log("[GUI] 任务完成。")
            self._append_log("[GUI] 结果文件：{}".format(self.output_path_runtime))
            self._append_log("[GUI] 汇总文件：{}".format(self.summary_path_runtime))
            messagebox.showinfo(
                "完成",
                "任务已完成。\n\n结果文件：{}\n汇总文件：{}".format(self.output_path_runtime, self.summary_path_runtime),
            )
        else:
            self.status_text.set("异常结束（code={}）".format(code))
            self._append_log("[GUI] 任务异常结束，退出码：{}".format(code))

        self.proc = None

    def _open_output(self):
        p = self.output_path.get().strip()
        if p and os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showwarning("提示", "结果文件不存在，请先运行。")

    def _open_summary(self):
        p = self.summary_path.get().strip()
        if not p:
            out = self.output_path.get().strip()
            if out:
                p = self._default_summary_path(out)
        if p and os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showwarning("提示", "汇总文件不存在，请先运行。")

    def _open_project_dir(self):
        os.startfile(ROOT_DIR)

    def _save_settings(self):
        data = {
            "input_path": self.input_path.get().strip(),
            "output_path": self.output_path.get().strip(),
            "summary_path": self.summary_path.get().strip(),
            "question_column": self.question_column.get().strip(),
            "providers": self.providers.get().strip(),
            "workers": self.workers.get().strip(),
            "deepseek_mode": self.deepseek_mode.get().strip(),
            "kimi_model": self.kimi_model.get().strip(),
            "doubao_model": self.doubao_model.get().strip(),
            "resume": int(self.resume.get()),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        self.input_path.set(data.get("input_path", self.input_path.get()))
        self.output_path.set(data.get("output_path", self.output_path.get()))
        self.summary_path.set(data.get("summary_path", self.summary_path.get()))
        self.question_column.set(data.get("question_column", self.question_column.get()))
        self.providers.set(data.get("providers", self.providers.get()))
        self.workers.set(str(data.get("workers", self.workers.get())))
        self.deepseek_mode.set(data.get("deepseek_mode", self.deepseek_mode.get()))
        self.kimi_model.set(data.get("kimi_model", self.kimi_model.get()))
        self.doubao_model.set(data.get("doubao_model", self.doubao_model.get()))
        self.resume.set(int(data.get("resume", self.resume.get())))

    def _on_close(self):
        if self.running and self.proc and self.proc.poll() is None:
            ok = messagebox.askyesno("确认", "当前任务还在运行，确认退出并终止任务吗？")
            if not ok:
                return
            try:
                self.proc.terminate()
            except Exception:
                pass
        self._save_settings()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.parse_known_args()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
