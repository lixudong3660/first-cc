# -*- coding: utf-8 -*-
"""桌面番茄钟（Pomodoro Timer）

一个零依赖的桌面番茄钟，使用 Python 自带的 Tkinter 实现。
默认节奏：专注 25 分钟 → 短休息 5 分钟，每完成 4 个番茄进入一次长休息 15 分钟。

用法：`python pomodoro.py`
快捷键：空格 = 开始/暂停，R = 重置，S = 跳过当前阶段
"""

import tkinter as tk
from enum import Enum

# ---------------------------------------------------------------------------
# 可自定义的参数（单位：分钟）
# ---------------------------------------------------------------------------
WORK_MIN = 25           # 专注时长
SHORT_BREAK_MIN = 5     # 短休息时长
LONG_BREAK_MIN = 15     # 长休息时长
POMODOROS_BEFORE_LONG = 4   # 每完成多少个番茄后进入长休息

# ---------------------------------------------------------------------------
# 配色：浅色 UI 配色方案（温暖 · 柔和 · 简洁）
# ---------------------------------------------------------------------------
PRIMARY = "#C65A4A"      # 主色
BG = "#F7F2EC"           # 背景
SECONDARY = "#EAE3DB"    # 辅助
SUB_LIGHT = "#F1E8E0"    # 浅辅助
HIGHLIGHT = "#F8DCCF"    # 高亮
MUTED = "#D9D2CC"        # 弱化
TEXT = "#6F655E"         # 文本
LINE = "#E5E0DA"         # 分割线 / 轮廓

TEXT_SOFT = "#9C9289"    # 次要文字：在“弱化”基础上加深，保证可读性

# ---------------------------------------------------------------------------
# 窗口与字体
# ---------------------------------------------------------------------------
WIN_W, WIN_H = 380, 470      # 卡片式比例（约 4:5），比原来的窄高窗口更舒适
FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

CANVAS_SIZE = 210            # 环形进度画布边长


def shade(color: str, factor: float) -> str:
    """按比例调暗颜色，用于按钮的 active / hover 状态。"""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, round(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class Phase(Enum):
    """当前所处阶段。"""
    WORK = "work"
    SHORT_BREAK = "short"
    LONG_BREAK = "long"


# 不同阶段的主题色： (主色, 阶段名, 时长)
# 专注取配色方案的主色；两个休息阶段用了同色系的低饱和搭配色，
# 在保持整体柔和调性的同时区分阶段。
PHASE_STYLE = {
    Phase.WORK: (PRIMARY, "专注", WORK_MIN),
    Phase.SHORT_BREAK: ("#7E9B76", "短休息", SHORT_BREAK_MIN),
    Phase.LONG_BREAK: ("#8291A6", "长休息", LONG_BREAK_MIN),
}


def mmss(seconds: int) -> str:
    """把秒数格式化为 MM:SS。"""
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"


class PomodoroApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("番茄钟")
        root.resizable(False, False)
        root.configure(bg=BG)

        # 运行状态
        self.phase = Phase.WORK
        self.remaining = WORK_MIN * 60      # 当前阶段剩余秒数
        self.total = WORK_MIN * 60          # 当前阶段总秒数（用于计算进度）
        self.running = False
        self.completed = 0                  # 已完成的番茄数
        self._job = None                    # after() 定时任务的 id

        self._build_ui()
        self._center_window()
        self._render()

        # 绑定快捷键
        root.bind("<space>", lambda _e: self.toggle())
        root.bind("r", lambda _e: self.reset())
        root.bind("s", lambda _e: self.skip())

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # 固定尺寸窗口，内容整体居中，四周留白由窗口承担
        self.card = tk.Frame(self.root, bg=BG)
        self.card.pack(expand=True)

        # 阶段标签：高亮色底片，文字用当前阶段的主题色
        self.phase_chip = tk.Frame(self.card, bg=HIGHLIGHT)
        self.phase_chip.pack(pady=(0, 14))
        self.phase_label = tk.Label(
            self.phase_chip, text="", font=(FONT_UI, 12, "bold"),
            bg=HIGHLIGHT, fg=PRIMARY, padx=16, pady=4)
        self.phase_label.pack()

        # 环形进度 + 时间
        self.canvas_size = CANVAS_SIZE
        self.canvas = tk.Canvas(
            self.card, width=self.canvas_size, height=self.canvas_size,
            bg=BG, highlightthickness=0)
        self.canvas.pack()

        # 按钮行
        btn_row = tk.Frame(self.card, bg=BG)
        btn_row.pack(pady=(16, 0))

        self.start_btn = tk.Button(
            btn_row, text="开始", command=self.toggle, takefocus=0,
            font=(FONT_UI, 11), relief="flat", padx=18, pady=7,
            bg=PRIMARY, fg="#ffffff", activebackground=shade(PRIMARY, 0.84),
            activeforeground="#ffffff", cursor="hand2", borderwidth=0)
        self.start_btn.pack(side="left", padx=5)

        self.reset_btn = tk.Button(
            btn_row, text="重置", command=self.reset, takefocus=0,
            font=(FONT_UI, 11), relief="flat", padx=18, pady=7,
            bg=SECONDARY, fg=TEXT, activebackground=MUTED,
            activeforeground=TEXT, cursor="hand2", borderwidth=0)
        self.reset_btn.pack(side="left", padx=5)

        self.skip_btn = tk.Button(
            btn_row, text="跳过", command=self.skip, takefocus=0,
            font=(FONT_UI, 11), relief="flat", padx=18, pady=7,
            bg=SECONDARY, fg=TEXT, activebackground=MUTED,
            activeforeground=TEXT, cursor="hand2", borderwidth=0)
        self.skip_btn.pack(side="left", padx=5)

        # 番茄计数（每完成 4 个换行显示）
        self.counter_label = tk.Label(
            self.card, text="", font=(FONT_UI, 15), bg=BG, fg=PRIMARY)
        self.counter_label.pack(pady=(14, 0))

        # 置顶开关
        self.topmost_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self.card, text="窗口置顶", variable=self.topmost_var, takefocus=0,
            command=self._toggle_topmost, bg=BG, fg=TEXT_SOFT,
            activebackground=BG, activeforeground=TEXT,
            font=(FONT_UI, 9), selectcolor=SECONDARY,
            highlightthickness=0, borderwidth=0).pack(pady=(8, 0))

        hint = tk.Label(
            self.card,
            text="空格 开始/暂停    R 重置    S 跳过",
            font=(FONT_UI, 8), bg=BG, fg=TEXT_SOFT)
        hint.pack(pady=(4, 0))

    def _center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - WIN_W) // 2
        y = (self.root.winfo_screenheight() - WIN_H) // 3
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

    # ---------------------------------------------------------------- 渲染
    def _render(self):
        color, name, _ = PHASE_STYLE[self.phase]

        # 阶段标签
        self.phase_label.config(text=name, fg=color)

        # 环形进度
        self.canvas.delete("all")
        fraction = 1.0 if self.total == 0 else self.remaining / self.total
        r = self.canvas_size // 2 - 16
        cx = cy = self.canvas_size // 2
        # 背景圆环（用“分割线”色作轨道）
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline=LINE, width=13)
        # 进度圆弧（从顶部顺时针）
        if fraction > 0:
            extent = -360 * fraction
            self.canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                                   start=90, extent=extent, style="arc",
                                   outline=color, width=13)
        # 中间的时间
        self.canvas.create_text(cx, cy, text=mmss(self.remaining),
                                font=(FONT_MONO, 46, "bold"), fill=TEXT)

        # 按钮与计数
        self.start_btn.config(
            text="暂停" if self.running else "开始", bg=color,
            activebackground=shade(color, 0.84))
        self.counter_label.config(text=self._counter_text())

    def _counter_text(self):
        """用 🍅 显示完成数，每 4 个一组换行。"""
        full = self.completed // POMODOROS_BEFORE_LONG
        rest = self.completed % POMODOROS_BEFORE_LONG
        line1 = "🍅" * POMODOROS_BEFORE_LONG if full else ""
        line2 = "🍅" * rest
        if full:
            return f"{line1}\n{line2}".strip()
        return line2 or "尚未完成番茄"

    # ---------------------------------------------------------------- 计时
    def toggle(self):
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        if self.remaining <= 0:
            self.remaining = self.total
        self.running = True
        self._job = self.root.after(1000, self._tick)
        self._render()

    def _pause(self):
        self.running = False
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        self._render()

    def _tick(self):
        if not self.running:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.remaining = 0
            self._render()
            self._advance()
            return
        self._render()
        self._job = self.root.after(1000, self._tick)

    def reset(self):
        """重置当前阶段（不改变完成数）。"""
        self._pause()
        self.remaining = self.total
        self._render()

    def skip(self):
        """跳过当前阶段，直接进入下一阶段。"""
        self._pause()
        self._advance()

    def _advance(self):
        """结束当前阶段，切换到下一阶段并提醒。"""
        if self.phase == Phase.WORK:
            self.completed += 1
            if self.completed % POMODOROS_BEFORE_LONG == 0:
                self._set_phase(Phase.LONG_BREAK)
            else:
                self._set_phase(Phase.SHORT_BREAK)
        else:
            self._set_phase(Phase.WORK)

        self._notify()

    def _set_phase(self, phase: Phase):
        self.phase = phase
        self.total = PHASE_STYLE[phase][2] * 60
        self.remaining = self.total
        self._render()

    def _notify(self):
        """阶段结束时播放提示音并闪烁窗口。"""
        try:
            import winsound
            winsound.PlaySound("SystemExclamation",
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            self.root.bell()
        # 把窗口带到最前，吸引注意
        self.root.lift()

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())


def main():
    root = tk.Tk()
    PomodoroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
