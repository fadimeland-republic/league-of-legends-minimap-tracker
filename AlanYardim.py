"""
zone_drawer.py
──────────────
Minimap ekran görüntüsü üzerinde TOP RIVER ve BOT RIVER zone'larını
tıklayarak çiz, zones.json olarak kaydet.

Kullanım:
  1. Bu scripti çalıştır
  2. "TOP RIVER" modu seçili — minimaptaki top river bölgesinin
     köşelerine sırayla tıkla (3-8 nokta)
  3. "BOT RIVER" düğmesine bas, aynı işlemi bot river için yap
  4. "Kaydet" → zones.json oluşturulur
  5. Ana uygulamada "↺ Zone Yükle" düğmesine bas
"""

import json
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import mss
import numpy as np
import cv2
from PIL import Image, ImageTk

# Ana uygulamayla aynı minimap koordinatları
MINIMAP_X = 1560
MINIMAP_Y = 740
MINIMAP_W = 350
MINIMAP_H = 350

ZONES_FILE = Path(__file__).parent / "zones.json"

# Renkler
COLOR_TOP    = "#00aaff"
COLOR_BOT    = "#ff6600"
COLOR_ACTIVE = "#ffffff"
BG           = "#0d1117"
CARD         = "#161b22"
FG           = "#e6edf3"
DIM          = "#8b949e"


class ZoneDrawer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zone Çizici")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._mode         = "top"          # "top" veya "bot"
        self._points       = {"top": [], "bot": []}
        self._mm_img       = None           # PIL image
        self._tk_img       = None
        self._canvas_size  = 500            # piksel — gösterim boyutu
        self._scale        = 1.0

        self._grab_minimap()
        self._build_ui()
        self._redraw()

    # ──────────── EKRAN YAKALA ────────────
    def _grab_minimap(self):
        with mss.mss() as sct:
            monitor = {"left": MINIMAP_X, "top": MINIMAP_Y,
                       "width": MINIMAP_W, "height": MINIMAP_H}
            shot = sct.grab(monitor)
            img  = np.array(shot)
            bgr  = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            rgb  = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            self._mm_img = Image.fromarray(rgb)
        # Ölçek: canvas'a sığdır
        self._scale = self._canvas_size / max(MINIMAP_W, MINIMAP_H)

    def _refresh_screenshot(self):
        self._grab_minimap()
        self._redraw()
        self._log("Ekran görüntüsü yenilendi.")

    # ──────────── UI ────────────
    def _build_ui(self):
        # Sol panel: canvas
        left = tk.Frame(self, bg=BG)
        left.pack(side="left", padx=10, pady=10)

        tk.Label(left, text="MİNİMAP", bg=BG, fg=DIM,
                 font=("Consolas", 8)).pack(anchor="w")

        self.canvas = tk.Canvas(left,
                                width=self._canvas_size,
                                height=self._canvas_size,
                                bg="#000000", highlightthickness=1,
                                highlightbackground="#21262d", cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Button-1>",   self._on_click)
        self.canvas.bind("<Button-3>",   self._on_right_click)
        self.canvas.bind("<Motion>",     self._on_motion)

        self._cursor_line_h = None
        self._cursor_line_v = None

        hint = tk.Label(left,
                        text="Sol tık: nokta ekle  |  Sağ tık: son noktayı sil  |  Sarı: imleç",
                        bg=BG, fg=DIM, font=("Consolas", 7))
        hint.pack(anchor="w", pady=(2, 0))

        # Sağ panel: kontroller
        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="y", padx=(0, 10), pady=10)

        # Mod seçimi
        self._card(right, "ÇİZİM MODU", self._mode_section)
        self._card(right, "İŞLEMLER",   self._actions_section)
        self._card(right, "NOKTA LİSTESİ", self._points_section)
        self._card(right, "LOG",        self._log_section)

    def _card(self, parent, title, builder):
        tk.Label(parent, text=title, bg=BG, fg=DIM,
                 font=("Consolas", 8)).pack(anchor="w", pady=(6, 0))
        frame = tk.Frame(parent, bg=CARD, highlightbackground="#21262d",
                         highlightthickness=1)
        frame.pack(fill="x")
        builder(frame)

    def _mode_section(self, f):
        self._mode_var = tk.StringVar(value="top")

        rb_top = tk.Radiobutton(f, text="TOP RIVER", variable=self._mode_var,
                                value="top", bg=CARD, fg=COLOR_TOP,
                                selectcolor="#21262d", activebackground=CARD,
                                font=("Consolas", 10, "bold"),
                                command=lambda: self._set_mode("top"))
        rb_top.pack(anchor="w", padx=8, pady=(6, 2))

        rb_bot = tk.Radiobutton(f, text="BOT RIVER", variable=self._mode_var,
                                value="bot", bg=CARD, fg=COLOR_BOT,
                                selectcolor="#21262d", activebackground=CARD,
                                font=("Consolas", 10, "bold"),
                                command=lambda: self._set_mode("bot"))
        rb_bot.pack(anchor="w", padx=8, pady=(2, 6))

    def _actions_section(self, f):
        btn_cfg = {"bg": "#21262d", "fg": FG, "relief": "flat",
                   "font": ("Consolas", 9, "bold"), "cursor": "hand2",
                   "activebackground": "#30363d", "activeforeground": FG}

        btns = [
            ("🗑  Mevcut Zone Temizle",  self._clear_current),
            ("📷  Ekranı Yenile",        self._refresh_screenshot),
            ("💾  Kaydet (zones.json)",  self._save),
        ]
        for text, cmd in btns:
            tk.Button(f, text=text, command=cmd, **btn_cfg).pack(
                fill="x", padx=8, pady=3)

        # Mevcut zones.json varsa yükle butonu
        tk.Button(f, text="📂  Mevcut Zoneları Yükle", command=self._load_existing,
                  **btn_cfg).pack(fill="x", padx=8, pady=(0, 6))

    def _points_section(self, f):
        self.points_box = tk.Text(f, width=24, height=8,
                                  bg="#0d1117", fg=FG, relief="flat",
                                  font=("Consolas", 8), state="disabled")
        self.points_box.pack(padx=6, pady=6)

    def _log_section(self, f):
        self.log_box = tk.Text(f, width=24, height=5,
                               bg="#0d1117", fg=DIM, relief="flat",
                               font=("Consolas", 8), state="disabled")
        self.log_box.pack(padx=6, pady=6)

    # ──────────── CANVAS ETKİLEŞİM ────────────
    def _on_click(self, e):
        # Canvas koordinatını normalize et
        nx = e.x / self._canvas_size
        ny = e.y / self._canvas_size
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))
        self._points[self._mode].append([nx, ny])
        self._log(f"{self._mode.upper()} nokta eklendi: ({nx:.3f}, {ny:.3f})")
        self._redraw()
        self._update_points_box()

    def _on_right_click(self, e):
        pts = self._points[self._mode]
        if pts:
            removed = pts.pop()
            self._log(f"Son nokta silindi: ({removed[0]:.3f}, {removed[1]:.3f})")
            self._redraw()
            self._update_points_box()

    def _on_motion(self, e):
        # İnce crosshair çizgileri
        cs = self._canvas_size
        if self._cursor_line_h:
            self.canvas.delete(self._cursor_line_h)
        if self._cursor_line_v:
            self.canvas.delete(self._cursor_line_v)
        self._cursor_line_h = self.canvas.create_line(0, e.y, cs, e.y,
                                                       fill="#ffff00", width=1, dash=(2, 4))
        self._cursor_line_v = self.canvas.create_line(e.x, 0, e.x, cs,
                                                       fill="#ffff00", width=1, dash=(2, 4))

    # ──────────── ÇİZİM ────────────
    def _redraw(self):
        self.canvas.delete("zone")

        # Arkaplan: minimap görüntüsü
        if self._mm_img:
            resized = self._mm_img.resize(
                (self._canvas_size, self._canvas_size), Image.NEAREST)
            self._tk_img = ImageTk.PhotoImage(resized)
            self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img, tags="zone")

        cs = self._canvas_size

        for mode, color_hex in (("top", COLOR_TOP), ("bot", COLOR_BOT)):
            pts = self._points[mode]
            if not pts:
                continue

            # Piksele çevir
            screen_pts = [(int(x * cs), int(y * cs)) for x, y in pts]

            # Dolu polygon (yarı saydam efekt için stipple)
            if len(screen_pts) >= 3:
                flat = [c for p in screen_pts for c in p]
                self.canvas.create_polygon(flat, fill=color_hex, outline=color_hex,
                                           stipple="gray25", width=2, tags="zone")

            # Kenar çizgileri
            for i in range(len(screen_pts)):
                p1 = screen_pts[i]
                p2 = screen_pts[(i + 1) % len(screen_pts)]
                self.canvas.create_line(p1, p2, fill=color_hex, width=2, tags="zone")

            # Noktalar
            for i, (px, py) in enumerate(screen_pts):
                r = 5
                is_active = (mode == self._mode)
                dot_color = COLOR_ACTIVE if is_active else color_hex
                self.canvas.create_oval(px-r, py-r, px+r, py+r,
                                        fill=dot_color, outline="#000000",
                                        width=1, tags="zone")
                self.canvas.create_text(px + 8, py - 8, text=str(i+1),
                                        fill=dot_color, font=("Consolas", 7),
                                        tags="zone")

        # Mod etiketi
        color = COLOR_TOP if self._mode == "top" else COLOR_BOT
        label = "TOP RIVER çiziliyor" if self._mode == "top" else "BOT RIVER çiziliyor"
        self.canvas.create_text(cs//2, cs - 12, text=label,
                                fill=color, font=("Consolas", 8, "bold"), tags="zone")

    def _update_points_box(self):
        self.points_box.configure(state="normal")
        self.points_box.delete("1.0", "end")
        for mode, color in (("top", "🔵"), ("bot", "🟠")):
            pts = self._points[mode]
            self.points_box.insert("end", f"{color} {mode.upper()}: {len(pts)} nokta\n")
            for i, (x, y) in enumerate(pts):
                self.points_box.insert("end", f"  {i+1}: ({x:.3f}, {y:.3f})\n")
        self.points_box.configure(state="disabled")

    # ──────────── KONTROLLER ────────────
    def _set_mode(self, mode: str):
        self._mode = mode
        self._redraw()

    def _clear_current(self):
        self._points[self._mode] = []
        self._log(f"{self._mode.upper()} zone temizlendi.")
        self._redraw()
        self._update_points_box()

    def _load_existing(self):
        if not ZONES_FILE.exists():
            self._log("zones.json bulunamadı.")
            return
        try:
            with open(ZONES_FILE) as f:
                data = json.load(f)
            self._points["top"] = data["top_river"]
            self._points["bot"] = data["bot_river"]
            self._log("zones.json yüklendi.")
            self._redraw()
            self._update_points_box()
        except Exception as e:
            self._log(f"Yükleme hatası: {e}")

    def _save(self):
        top = self._points["top"]
        bot = self._points["bot"]

        if len(top) < 3:
            messagebox.showwarning("Uyarı", "TOP RIVER için en az 3 nokta gerekli!")
            return
        if len(bot) < 3:
            messagebox.showwarning("Uyarı", "BOT RIVER için en az 3 nokta gerekli!")
            return

        data = {"top_river": top, "bot_river": bot}
        with open(ZONES_FILE, "w") as f:
            json.dump(data, f, indent=2)

        self._log(f"Kaydedildi → {ZONES_FILE.name}")
        messagebox.showinfo(
            "Kaydedildi",
            f"zones.json oluşturuldu!\n\n"
            f"TOP RIVER: {len(top)} nokta\n"
            f"BOT RIVER: {len(bot)} nokta\n\n"
            f"Ana uygulamada '↺ Zone Yükle' düğmesine bas."
        )

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


if __name__ == "__main__":
    ZoneDrawer().mainloop()