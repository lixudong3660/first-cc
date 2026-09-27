# -*- coding: utf-8 -*-
"""桌面番茄钟（Pomodoro Timer）

一个零依赖的桌面番茄钟，使用 Python 自带的 Tkinter 实现。
默认节奏：专注 25 分钟 → 短休息 5 分钟，每完成 4 个番茄进入一次长休息 15 分钟。

用法：`python pomodoro.py`
快捷键：空格 = 开始/暂停，R = 重置，S = 跳过
"""

import math
import tkinter as tk
import tkinter.font as tkfont
from enum import Enum

# ---------------------------------------------------------------------------
# 可自定义的参数（单位：分钟）
# ---------------------------------------------------------------------------
WORK_MIN = 25           # 专注时长
SHORT_BREAK_MIN = 5     # 短休息时长
LONG_BREAK_MIN = 15     # 长休息时长
POMODOROS_BEFORE_LONG = 4   # 每完成多少个番茄后进入长休息

# ---------------------------------------------------------------------------
# 配色：一张纸、一方墨、一颗番茄
#
# 刻意避开“米色背景 + 白卡片 + 柔和投影”那套通用暖色模板：窗口底色是偏灰的
# 黏土纸，表盘是一块更亮的象牙面，两者只靠明度差和一根细线分开，不用投影。
# 阶段色取自番茄本身 —— 果实的红、叶的绿、暮色的蓝。
# ---------------------------------------------------------------------------
GROUND = "#E4DCD1"      # 窗口底色：温暖偏灰的黏土纸
FACE = "#FBF7F1"        # 表盘面：象牙纸
EDGE = "#D9CFC2"        # 表盘轮廓
EDGE_BTN = "#7E7364"    # 次级按钮描边 / 空心刻度
INK = "#3A322B"         # 主墨色：时间数字
INK_SOFT = "#5F564C"    # 次要文字：快捷键提示、置顶开关
TICK_OFF = "#E2D8CB"    # 已经走过的刻度

TOMATO = "#C4442C"      # 番茄红：专注阶段，同时是“已完成一个番茄”的标记色
LEAF = "#4F6B45"        # 叶绿：短休息
DUSK = "#4E5F75"        # 暮蓝：长休息

# ---------------------------------------------------------------------------
# 窗口、表盘与字体
# ---------------------------------------------------------------------------
WIN_W, WIN_H = 384, 452
DIAL = 250                          # 表盘直径
DIAL_TOP = 22                       # 表盘上边缘距窗口顶部的距离
STRIP_GAP = 26                      # 表盘下边缘到计数条的间距
CANVAS_H = DIAL_TOP + DIAL + STRIP_GAP + 28

NUM_PT = 50             # 时间数字字号（pt）
PHASE_PT = 13           # 阶段名字号
UI_PT = 12              # 按钮字号
SMALL_PT = 10           # 计数条与提示文字字号

# 字体候选链：按优先级挑选系统里真实存在的字体，缺失时逐级回退。
UI_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "DengXian", "SimHei")
# Georgia / Constantia 都带老式数字（3、4、5、7、9 会沉到基线以下），
# 让计时器读起来像印刷品而不是 LED。
NUM_FAMILIES = ("Georgia", "Constantia", "Cambria", "Palatino Linotype",
                "Times New Roman")


def pick_family(root: tk.Tk, candidates, fallback: str) -> str:
    """返回候选列表里第一个系统已安装的字体族。"""
    available = {name.lower() for name in tkfont.families(root)}
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


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
PHASE_STYLE = {
    Phase.WORK: (TOMATO, "专注", WORK_MIN),
    Phase.SHORT_BREAK: (LEAF, "短休息", SHORT_BREAK_MIN),
    Phase.LONG_BREAK: (DUSK, "长休息", LONG_BREAK_MIN),
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
        root.configure(bg=GROUND)

        # 字体：先挑系统里真正存在的族，再建可复用的 Font 对象
        self.f_ui = pick_family(root, UI_FAMILIES, "TkDefaultFont")
        self.f_num = pick_family(root, NUM_FAMILIES, "TkDefaultFont")
        self.num_font = tkfont.Font(root=root, family=self.f_num, size=NUM_PT)
        self.small_font = tkfont.Font(root=root, family=self.f_ui, size=SMALL_PT)

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
        self.card = tk.Frame(self.root, bg=GROUND)
        self.card.pack(expand=True)

        # 表盘与计数条画在同一张画布上，整个 _render 只重绘它
        self.canvas = tk.Canvas(
            self.card, width=WIN_W, height=CANVAS_H,
            bg=GROUND, highlightthickness=0)
        self.canvas.pack()

        # 按钮：实心的主操作 + 描边的次要操作，用填充方式建立层级
        btns = tk.Frame(self.card, bg=GROUND)
        btns.pack(pady=(2, 0))

        # takefocus=0：空格已经绑在窗口上，按钮再抢焦点会让空格触发两次
        self.start_btn = tk.Button(
            btns, text="开始", command=self.toggle, takefocus=0,
            font=(self.f_ui, UI_PT, "bold"), relief="flat", borderwidth=0,
            padx=30, pady=9, bg=TOMATO, fg="#ffffff", cursor="hand2",
            highlightthickness=1, highlightbackground=TOMATO)
        self.start_btn.pack(side="left", padx=(0, 10))

        self.reset_btn = self._outline_button(btns, "重置", self.reset)
        self.reset_btn.pack(side="left", padx=(0, 10))

        self.skip_btn = self._outline_button(btns, "跳过", self.skip)
        self.skip_btn.pack(side="left")

        # 置顶开关
        self.topmost_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self.card, text="窗口置顶", variable=self.topmost_var, takefocus=0,
            command=self._toggle_topmost, bg=GROUND, fg=INK_SOFT,
            activebackground=GROUND, activeforeground=INK,
            font=(self.f_ui, SMALL_PT), selectcolor=FACE,
            highlightthickness=0, borderwidth=0).pack(pady=(14, 0))

        tk.Label(
            self.card, text="空格 开始/暂停    R 重置    S 跳过",
            font=(self.f_ui, SMALL_PT), bg=GROUND, fg=INK_SOFT
        ).pack(pady=(8, 16))

    def _outline_button(self, parent, text, command) -> tk.Button:
        """次要操作：不填色，只用一根墨线勾边。"""
        return tk.Button(
            parent, text=text, command=command, takefocus=0,
            font=(self.f_ui, UI_PT), relief="flat", borderwidth=0,
            padx=18, pady=9, bg=GROUND, fg=INK, cursor="hand2",
            activebackground=FACE, activeforeground=INK,
            highlightthickness=1, highlightbackground=EDGE_BTN,
            highlightcolor=EDGE_BTN)

    def _center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - WIN_W) // 2
        y = (self.root.winfo_screenheight() - WIN_H) // 3
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

    # ---------------------------------------------------------------- 渲染
    def _render(self):
        color, name, _ = PHASE_STYLE[self.phase]
        c = self.canvas
        c.delete("all")

        cx = WIN_W / 2
        cy = DIAL_TOP + DIAL / 2
        r_face = DIAL / 2 - 1

        # 表盘面：一块象牙纸，靠明度差浮在黏土纸底色上，不加投影
        c.create_oval(cx - r_face, cy - r_face, cx + r_face, cy + r_face,
                      fill=FACE, outline=EDGE, width=1)

        self._draw_ticks(c, cx, cy, r_face, color)
        self._draw_time(c, cx, cy - 16)

        # 阶段名刻在盘内，像仪表上的铭牌，取代“高亮底片 + 文字”的药丸标签
        c.create_text(cx, cy + 46, text=name, anchor="center",
                      font=(self.f_ui, PHASE_PT), fill=color)

        self._draw_cycle(c, DIAL_TOP + DIAL + STRIP_GAP)

        self.start_btn.config(text="暂停" if self.running else "开始",
                              bg=color, activebackground=shade(color, 0.86),
                              highlightbackground=color)

    def _draw_ticks(self, c, cx, cy, r_face, color):
        """刻度环：一分钟一格。走过的刻痕褪色，剩下的用阶段色。

        刻度数随阶段时长变化（专注 25 格、短休息 5 格），所以每一格都对应
        一分钟，可以数；也比一条平滑圆弧更诚实地表达“还剩几分钟”。
        """
        minutes = max(1, round(self.total / 60))
        spent = int((self.total - self.remaining) // 60)
        r_out = r_face - 15
        for i in range(minutes):
            angle = math.radians(90 - i * 360.0 / minutes)
            major = i % 5 == 0
            r_in = r_out - (13 if major else 8)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            c.create_line(cx + r_in * cos_a, cy - r_in * sin_a,
                          cx + r_out * cos_a, cy - r_out * sin_a,
                          fill=TICK_OFF if i < spent else color,
                          width=3 if major else 2, capstyle=tk.ROUND)

    def _draw_time(self, c, cx, y):
        """时间：逐字放进固定格位。

        Georgia 的老式数字宽度不等（1 比 0 窄很多），整串居中会让秒数每跳一次
        就左右晃一下；拆成五格、每格各自居中，数字就是稳的。
        """
        text = mmss(self.remaining)
        sw = self.num_font.measure("0")
        cw = max(6, self.num_font.measure(":"))
        x0 = cx - (4 * sw + cw) / 2
        slots = (
            (x0 + sw * 0.5, text[0]),
            (x0 + sw * 1.5, text[1]),
            (x0 + sw * 2 + cw * 0.5, text[2]),
            (x0 + sw * 2 + cw + sw * 0.5, text[3]),
            (x0 + sw * 2 + cw + sw * 1.5, text[4]),
        )
        for sx, ch in slots:
            c.create_text(sx, y, text=ch, anchor="center",
                          font=self.num_font, fill=INK)

    def _draw_cycle(self, c, y):
        """计数条：四格表示本轮进度，细线右边是累计完成的番茄数。"""
        n = POMODOROS_BEFORE_LONG
        done = self.completed % n
        # 休息阶段意味着这一轮刚刚走完，该显示满格；进入下一个专注阶段才归零
        if self.phase is not Phase.WORK and done == 0 and self.completed:
            done = n

        total_text = f"共 {self.completed} 个"
        r, gap, sep_gap = 5, 22, 20
        slots_w = gap * (n - 1) + r * 2
        tw = self.small_font.measure(total_text)
        x = (WIN_W - (slots_w + sep_gap * 2 + 1 + tw)) / 2

        for i in range(n):
            sx = x + r + i * gap
            if i < done:
                c.create_oval(sx - r, y - r, sx + r, y + r,
                              fill=TOMATO, outline="")
            else:
                c.create_oval(sx - r, y - r, sx + r, y + r,
                              fill="", outline=EDGE_BTN, width=1)

        sep_x = x + slots_w + sep_gap
        c.create_line(sep_x, y - 9, sep_x, y + 9, fill=EDGE, width=1)
        c.create_text(sep_x + sep_gap, y, text=total_text, anchor="w",
                      font=self.small_font, fill=INK_SOFT)

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
