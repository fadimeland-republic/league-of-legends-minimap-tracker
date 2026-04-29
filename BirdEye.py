"""
LoL Minimap Watcher - YOLOv11 tabanlı düşman tespiti ve alarm sistemi
"""

import sys
import time
import threading
import wave
import tempfile
import os
import json
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import mss
import cv2
from PIL import Image, ImageTk
import winsound

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics yüklü değil! Lütfen: pip install ultralytics")
    sys.exit(1)


# ─────────────────────────────────────────────
#  AYARLAR
# ─────────────────────────────────────────────
MINIMAP_X = 1560
MINIMAP_Y = 740
MINIMAP_W = 350
MINIMAP_H = 350

DEFAULT_TOP_ZONE = np.array([[0.35, 0.33], [0.46, 0.33],
                              [0.46, 0.41], [0.35, 0.41]], dtype=np.float32)
DEFAULT_BOT_ZONE = np.array([[0.60, 0.49], [0.68, 0.49],
                              [0.68, 0.57], [0.60, 0.57]], dtype=np.float32)

ZONES_FILE     = Path(__file__).parent / "zones.json"
ALARM_COOLDOWN = 8.0
DETECTION_CONF = 0.50
FPS_TARGET     = 10

# Varsayılan label filtresi — bu kelime label'da geçmiyorsa alarm çalmaz
DEFAULT_FILTER = "enemy"


# ─────────────────────────────────────────────
#  ZONE YÜKLEME
# ─────────────────────────────────────────────
def load_zones():
    if ZONES_FILE.exists():
        try:
            with open(ZONES_FILE) as f:
                data = json.load(f)
            return (np.array(data["top_river"], dtype=np.float32),
                    np.array(data["bot_river"],  dtype=np.float32))
        except Exception:
            pass
    return DEFAULT_TOP_ZONE.copy(), DEFAULT_BOT_ZONE.copy()


def point_in_polygon(cx: float, cy: float, poly: np.ndarray) -> bool:
    pts = (poly * 1000).astype(np.int32)
    return cv2.pointPolygonTest(pts, (int(cx * 1000), int(cy * 1000)), False) >= 0


# ─────────────────────────────────────────────
#  SES ÜRETİCİ  (WAV — gerçek volume kontrolü)
# ─────────────────────────────────────────────
class SoundPlayer:
    def __init__(self):
        self._lock   = threading.Lock()
        self._volume = 0.02

    def set_volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))

    def _make_wav(self, freq: int, dur_ms: int, repeats: int, gap_ms: int) -> str:
        rate   = 44100
        t      = np.linspace(0, dur_ms / 1000, int(rate * dur_ms / 1000), False)
        beep   = (np.sin(2 * np.pi * freq * t) * 32767 * self._volume).astype(np.int16)
        gap    = np.zeros(int(rate * gap_ms / 1000), dtype=np.int16)
        full   = np.concatenate([np.concatenate([beep, gap])] * repeats)
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(full.tobytes())
        return path

    def _play(self, freq, dur_ms, repeats, gap_ms):
        with self._lock:
            path = self._make_wav(freq, dur_ms, repeats, gap_ms)
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME)
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass

    def play_top_river(self):
        threading.Thread(target=self._play, args=(1200, 150, 3, 60), daemon=True).start()

    def play_bot_river(self):
        threading.Thread(target=self._play, args=(600, 180, 3, 60), daemon=True).start()


# ─────────────────────────────────────────────
#  ALGILAMA MOTORU
# ─────────────────────────────────────────────
class DetectionEngine:
    def __init__(self, model_path: str, conf: float = DETECTION_CONF):
        self.model   = YOLO(model_path)
        self.conf    = conf
        self.monitor = {
            "left": MINIMAP_X, "top": MINIMAP_Y,
            "width": MINIMAP_W, "height": MINIMAP_H
        }

    def grab_minimap(self, sct) -> np.ndarray:
        shot = sct.grab(self.monitor)
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

    def detect(self, frame: np.ndarray):
        results    = self.model(frame, conf=self.conf, verbose=False)[0]
        detections = []
        h, w = frame.shape[:2]
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx    = ((x1 + x2) / 2) / w
            cy    = ((y1 + y2) / 2) / h
            conf  = float(box.conf[0])
            cls   = int(box.cls[0])
            label = results.names[cls] if results.names else str(cls)
            detections.append({
                "cx": cx, "cy": cy,
                "conf": conf, "label": label
            })
        return detections, results


# ─────────────────────────────────────────────
#  LABEL FİLTRELEME
# ─────────────────────────────────────────────
def filter_enemy(detections: list, keyword: str) -> list:
    """
    Only returns detections whose label contains the filter keyword.
    If the keyword is empty, no filtering is applied (all detections are returned).
    """
    kw = keyword.strip().lower()
    if not kw:
        return detections
    return [d for d in detections if kw in d["label"].lower()]


# ─────────────────────────────────────────────
#  ANA GUI
# ─────────────────────────────────────────────
class MinimapWatcherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LoL Minimap Watcher")
        self.configure(bg="#0d1117")
        self.resizable(False, False)

        self.model_path   = tk.StringVar(value="")
        self.running      = False
        self.engine       = None
        self.sound        = SoundPlayer()
        self.volume_var   = tk.DoubleVar(value=0.1)
        self.conf_var     = tk.DoubleVar(value=DETECTION_CONF)
        self.cooldown_var = tk.DoubleVar(value=ALARM_COOLDOWN)
        self.filter_var   = tk.StringVar(value=DEFAULT_FILTER)

        self._last_alarm  = {"top": 0.0, "bot": 0.0}
        self._alarm_lock  = threading.Lock()

        self.mm_x = tk.IntVar(value=MINIMAP_X)
        self.mm_y = tk.IntVar(value=MINIMAP_Y)
        self.mm_w = tk.IntVar(value=MINIMAP_W)
        self.mm_h = tk.IntVar(value=MINIMAP_H)

        self.top_zone, self.bot_zone = load_zones()
        self._zone_source = "zones.json" if ZONES_FILE.exists() else "varsayılan"

        # Algılama istatistikleri (thread-safe)
        self._stats_lock   = threading.Lock()
        self._total_dets   = 0   # total detections in last frame
        self._enemy_dets   = 0   # filtered detections
        self._last_labels  = []  # all labels in the last frame

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log(f"Zone source: {self._zone_source}")
        self._log(f"Label filter: '{self.filter_var.get()}'")

        # İstatistik güncelleme döngüsü
        self._update_stats_ui()

    # ──────────── UI ────────────
    def _build_ui(self):
        ACCENT = "#00d4ff"
        BG     = "#0d1117"
        CARD   = "#161b22"
        FG     = "#e6edf3"
        DIM    = "#8b949e"

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",  background=CARD)
        style.configure("TLabel",  background=CARD, foreground=FG, font=("Consolas", 10))
        style.configure("TScale",  background=CARD, troughcolor="#21262d", sliderlength=14)
        style.configure("TButton", background="#21262d", foreground=FG,
                        font=("Consolas", 10, "bold"), relief="flat", borderwidth=0)
        style.map("TButton", background=[("active", "#30363d")])

        hdr = tk.Frame(self, bg=BG, pady=8)
        hdr.pack(fill="x", padx=10)
        tk.Label(hdr, text="⬡  LOL MINIMAP WATCHER", bg=BG, fg=ACCENT,
                 font=("Consolas", 14, "bold")).pack(side="left")
        tk.Label(hdr, text="YOLOv11", bg=BG, fg=DIM,
                 font=("Consolas", 9)).pack(side="right", padx=4)

        self._card("MODEL",           self._model_section)
        self._card("MINIMAP AREA",   self._minimap_section)
        self._card("SETTINGS",         self._settings_section)
        self._card("LIVE PREVIEW", self._preview_section)
        self._controls()

    def _card(self, title, builder_fn):
        outer = tk.Frame(self, bg="#0d1117", padx=8, pady=4)
        outer.pack(fill="x", padx=6)
        tk.Label(outer, text=title, bg="#0d1117", fg="#8b949e",
                 font=("Consolas", 8)).pack(anchor="w")
        inner = tk.Frame(outer, bg="#161b22", bd=0, relief="flat",
                         highlightbackground="#21262d", highlightthickness=1)
        inner.pack(fill="x")
        builder_fn(inner)

    def _model_section(self, f):
        row = tk.Frame(f, bg="#161b22")
        row.pack(fill="x", padx=8, pady=6)
        tk.Label(row, text="Model File:", bg="#161b22", fg="#e6edf3",
                 font=("Consolas", 9)).pack(side="left")
        tk.Entry(row, textvariable=self.model_path, bg="#21262d", fg="#e6edf3",
                 insertbackground="white", relief="flat", font=("Consolas", 9),
                 width=32).pack(side="left", padx=6)
        ttk.Button(row, text="Browse", command=self._browse_model).pack(side="left")

    def _minimap_section(self, f):
        fields = [("Left (X)", self.mm_x), ("Up (Y)", self.mm_y),
                  ("Width", self.mm_w), ("Height", self.mm_h)]
        row = tk.Frame(f, bg="#161b22")
        row.pack(fill="x", padx=8, pady=6)
        for label, var in fields:
            tk.Label(row, text=label, bg="#161b22", fg="#8b949e",
                     font=("Consolas", 8)).pack(side="left", padx=(4, 0))
            tk.Spinbox(row, textvariable=var, from_=0, to=3840, width=5,
                       bg="#21262d", fg="#e6edf3", relief="flat",
                       font=("Consolas", 9), buttonbackground="#30363d").pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Apply", command=self._apply_minimap).pack(side="left")

    def _settings_section(self, f):
        # ── Label Filtresi ──────────────────────────────────────
        fil_row = tk.Frame(f, bg="#161b22")
        fil_row.pack(fill="x", padx=8, pady=(6, 2))

        tk.Label(fil_row, text="Label filter", bg="#161b22", fg="#e6edf3",
                 font=("Consolas", 9), width=22, anchor="w").pack(side="left")

        fil_entry = tk.Entry(fil_row, textvariable=self.filter_var,
                             bg="#21262d", fg="#00d4ff",
                             insertbackground="white", relief="flat",
                             font=("Consolas", 9), width=14)
        fil_entry.pack(side="left", padx=6)

        # Filtre durumu göstergesi
        self._filter_status = tk.Label(fil_row, text="✓ active", bg="#161b22",
                                       fg="#3fb950", font=("Consolas", 8))
        self._filter_status.pack(side="left")

        def on_filter_change(*a):
            kw = self.filter_var.get().strip()
            if kw:
                self._filter_status.config(text=f"✓ '{kw}'", fg="#3fb950")
            else:
                self._filter_status.config(text="⚠ empty=all", fg="#f0a500")

        self.filter_var.trace_add("write", on_filter_change)

        # Filtre açıklama
        tk.Label(f, text="  Only detections whose label contains the filter keyword will trigger alarms.\n",
                 bg="#161b22", fg="#8b949e", font=("Consolas", 7)).pack(anchor="w", padx=8)

        # ── Tespit İstatistikleri ────────────────────────────────
        stats_row = tk.Frame(f, bg="#1a1f27",
                             highlightbackground="#21262d", highlightthickness=1)
        stats_row.pack(fill="x", padx=8, pady=(4, 2))

        tk.Label(stats_row, text="Last frame:", bg="#1a1f27", fg="#8b949e",
                 font=("Consolas", 8)).pack(side="left", padx=6, pady=3)
        self._stat_total = tk.Label(stats_row, text="total: 0", bg="#1a1f27",
                                    fg="#e6edf3", font=("Consolas", 8))
        self._stat_total.pack(side="left", padx=4)
        self._stat_enemy = tk.Label(stats_row, text="| enemy: 0", bg="#1a1f27",
                                    fg="#00d4ff", font=("Consolas", 8, "bold"))
        self._stat_enemy.pack(side="left", padx=4)

        # Son görülen label'lar
        labels_row = tk.Frame(f, bg="#161b22")
        labels_row.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(labels_row, text="Seen labels:", bg="#161b22", fg="#8b949e",
                 font=("Consolas", 7)).pack(side="left")
        self._seen_labels_lbl = tk.Label(labels_row, text="—", bg="#161b22",
                                         fg="#f0a500", font=("Consolas", 7),
                                         wraplength=280, justify="left")
        self._seen_labels_lbl.pack(side="left", padx=4)

        # ── Ses Seviyesi ─────────────────────────────────────────
        vol_row = tk.Frame(f, bg="#161b22")
        vol_row.pack(fill="x", padx=8, pady=3)
        tk.Label(vol_row, text="Volume level", bg="#161b22", fg="#e6edf3",
                 font=("Consolas", 9), width=22, anchor="w").pack(side="left")
        ttk.Scale(vol_row, variable=self.volume_var, from_=0.0, to=1.0,
                  orient="horizontal", length=160,
                  command=lambda v: self.sound.set_volume(float(v))).pack(side="left", padx=6)
        vol_lbl = tk.Label(vol_row, text=f"{self.volume_var.get():.2f}",
                           bg="#161b22", fg="#00d4ff", font=("Consolas", 9), width=5)
        vol_lbl.pack(side="left")
        self.volume_var.trace_add("write",
            lambda *a: vol_lbl.config(text=f"{self.volume_var.get():.2f}"))

        # ── Diğer Sliderlar ──────────────────────────────────────
        for label, var, mn, mx in [
            ("Min. confidence",          self.conf_var,     0.1,  0.95),
            ("Alarm cooldown (s)", self.cooldown_var, 1.0, 30.0),
        ]:
            r = tk.Frame(f, bg="#161b22")
            r.pack(fill="x", padx=8, pady=3)
            tk.Label(r, text=label, bg="#161b22", fg="#e6edf3",
                     font=("Consolas", 9), width=22, anchor="w").pack(side="left")
            ttk.Scale(r, variable=var, from_=mn, to=mx,
                      orient="horizontal", length=160).pack(side="left", padx=6)
            vl = tk.Label(r, bg="#161b22", fg="#00d4ff",
                          font=("Consolas", 9), width=5)
            vl.pack(side="left")
            var.trace_add("write", lambda *a, l=vl, v=var: l.config(text=f"{v.get():.2f}"))
            vl.config(text=f"{var.get():.2f}")

        # ── Alt Butonlar ─────────────────────────────────────────
        tr = tk.Frame(f, bg="#161b22")
        tr.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(tr, text="🔔 Top Test",   command=self._test_top).pack(side="left", padx=4)
        ttk.Button(tr, text="🔔 Bot Test",   command=self._test_bot).pack(side="left", padx=4)
        ttk.Button(tr, text="↺ Zone load", command=self._reload_zones).pack(side="left")

    def _preview_section(self, f):
        self.canvas = tk.Canvas(f, width=300, height=300,
                                bg="#0d1117", highlightthickness=0)
        self.canvas.pack(side="left", padx=8, pady=8)

        log_f = tk.Frame(f, bg="#161b22")
        log_f.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        tk.Label(log_f, text="ALARM LOG", bg="#161b22", fg="#8b949e",
                 font=("Consolas", 8)).pack(anchor="w")
        self.log_box = tk.Text(log_f, width=30, height=18,
                               bg="#0d1117", fg="#e6edf3", relief="flat",
                               font=("Consolas", 8), state="disabled")
        self.log_box.pack(fill="both", expand=True)

        ind_f = tk.Frame(f, bg="#161b22")
        ind_f.pack(side="left", padx=(0, 8), pady=8)
        tk.Label(ind_f, text="ZONE", bg="#161b22", fg="#8b949e",
                 font=("Consolas", 8)).pack()
        self.top_ind = tk.Label(ind_f, text="TOP\nRIVER", width=8,
                                bg="#1a2332", fg="#3d5a80",
                                font=("Consolas", 9, "bold"), pady=10)
        self.top_ind.pack(pady=(4, 2))
        self.bot_ind = tk.Label(ind_f, text="BOT\nRIVER", width=8,
                                bg="#1a2332", fg="#3d5a80",
                                font=("Consolas", 9, "bold"), pady=10)
        self.bot_ind.pack(pady=(2, 4))
        tk.Label(ind_f, text="FPS", bg="#161b22", fg="#8b949e",
                 font=("Consolas", 8)).pack(pady=(8, 0))
        self.fps_lbl = tk.Label(ind_f, text="—", bg="#161b22", fg="#00d4ff",
                                font=("Consolas", 11, "bold"))
        self.fps_lbl.pack()

    def _controls(self):
        f = tk.Frame(self, bg="#0d1117")
        f.pack(fill="x", padx=12, pady=8)
        self.start_btn = ttk.Button(f, text="▶  START", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn  = ttk.Button(f, text="■  STOP", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.status_lbl = tk.Label(f, text="⏸  WAITING", bg="#0d1117", fg="#8b949e",
                                   font=("Consolas", 10))
        self.status_lbl.pack(side="right", padx=8)

    # ──────────── YARDIMCI ────────────
    def _browse_model(self):
        path = filedialog.askopenfilename(
            title="YOLOv11 model seç",
            filetypes=[("YOLO model", "*.pt *.onnx"), ("Hepsi", "*.*")]
        )
        if path:
            self.model_path.set(path)

    def _apply_minimap(self):
        if self.engine:
            self.engine.monitor = {
                "left": self.mm_x.get(), "top": self.mm_y.get(),
                "width": self.mm_w.get(), "height": self.mm_h.get()
            }
        self._log("Minimap bölgesi güncellendi.")

    def _reload_zones(self):
        self.top_zone, self.bot_zone = load_zones()
        src = "zones.json" if ZONES_FILE.exists() else "default"
        self._log(f"ZONES UPDATED ({src}).")

    def _test_top(self):
        self.sound.set_volume(self.volume_var.get())
        self.sound.play_top_river()

    def _test_bot(self):
        self.sound.set_volume(self.volume_var.get())
        self.sound.play_bot_river()

    def _log(self, msg: str):
        ts   = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _flash_indicator(self, zone: str):
        lbl      = self.top_ind if zone == "top" else self.bot_ind
        color_on = "#ff4444"    if zone == "top" else "#ff8800"
        def flash(n=0):
            if n < 6:
                lbl.config(bg=color_on if n % 2 == 0 else "#1a2332",
                           fg="#ffffff" if n % 2 == 0 else "#3d5a80")
                self.after(180, lambda: flash(n + 1))
            else:
                lbl.config(bg="#1a2332", fg="#3d5a80")
        flash()

    def _update_stats_ui(self):
        """500ms'de bir istatistik etiketlerini güncelle (ana thread)."""
        with self._stats_lock:
            total  = self._total_dets
            enemy  = self._enemy_dets
            labels = list(self._last_labels)

        self._stat_total.config(text=f"total: {total}")
        self._stat_enemy.config(text=f"| enemy: {enemy}")

        if labels:
            # Unique label'ları say
            from collections import Counter
            counts = Counter(labels)
            txt = "  ".join(f"{lbl}×{n}" for lbl, n in counts.most_common(6))
        else:
            txt = "—"
        self._seen_labels_lbl.config(text=txt)

        self.after(500, self._update_stats_ui)

    # ──────────── BAŞLAT / DURDUR ────────────
    def _start(self):
        path = self.model_path.get().strip()
        if not path or not Path(path).exists():
            messagebox.showerror("Error", "Please select a valid model file.")
            return
        try:
            self.engine = DetectionEngine(path, conf=self.conf_var.get())
            self.engine.monitor = {
                "left": self.mm_x.get(), "top": self.mm_y.get(),
                "width": self.mm_w.get(), "height": self.mm_h.get()
            }
        except Exception as e:
            messagebox.showerror("Model Error", str(e))
            return

        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_lbl.config(text="🟢  WORKING", fg="#3fb950")
        kw = self.filter_var.get().strip() or "(no filter)"
        self._log(f"DETECTION STARTED. Filter: '{kw}'")
        threading.Thread(target=self._detection_loop, daemon=True).start()

    def _stop(self):
        self.running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_lbl.config(text="⏸  STOPPED", fg="#8b949e")
        self._log("DETECTION STOPPED.")

    def _on_close(self):
        self._stop()
        self.destroy()

    # ──────────── ALGILAMA DÖNGÜSÜ ────────────
    def _detection_loop(self):
        interval = 1.0 / FPS_TARGET
        with mss.mss() as sct:
            while self.running:
                t0 = time.time()
                try:
                    frame = self.engine.grab_minimap(sct)
                    all_dets, results = self.engine.detect(frame)

                    # ── Label filtresi ──────────────────────────
                    keyword      = self.filter_var.get()
                    enemy_dets   = filter_enemy(all_dets, keyword)

                    # İstatistikleri güncelle (thread-safe)
                    with self._stats_lock:
                        self._total_dets  = len(all_dets)
                        self._enemy_dets  = len(enemy_dets)
                        self._last_labels = [d["label"] for d in all_dets]
                    # ────────────────────────────────────────────

                    # Sadece filtreden geçen tespitler zone kontrolüne girer
                    top_hit = any(point_in_polygon(d["cx"], d["cy"], self.top_zone)
                                  for d in enemy_dets)
                    bot_hit = any(point_in_polygon(d["cx"], d["cy"], self.bot_zone)
                                  for d in enemy_dets)

                    now      = time.time()
                    cooldown = self.cooldown_var.get()

                    if top_hit:
                        with self._alarm_lock:
                            if now - self._last_alarm["top"] > cooldown:
                                self._last_alarm["top"] = now
                                # Hangi label tetikledi?
                                trigger = next(
                                    d["label"] for d in enemy_dets
                                    if point_in_polygon(d["cx"], d["cy"], self.top_zone)
                                )
                                self.sound.set_volume(self.volume_var.get())
                                self.sound.play_top_river()
                                self.after(0, lambda lb=trigger:
                                    self._log(f"⚠ TOP RIVER — {lb}"))
                                self.after(0, lambda: self._flash_indicator("top"))

                    if bot_hit:
                        with self._alarm_lock:
                            if now - self._last_alarm["bot"] > cooldown:
                                self._last_alarm["bot"] = now
                                trigger = next(
                                    d["label"] for d in enemy_dets
                                    if point_in_polygon(d["cx"], d["cy"], self.bot_zone)
                                )
                                self.sound.set_volume(self.volume_var.get())
                                self.sound.play_bot_river()
                                self.after(0, lambda lb=trigger:
                                    self._log(f"⚠ BOT RIVER — {lb}"))
                                self.after(0, lambda: self._flash_indicator("bot"))

                    self._update_preview(results.plot())

                    fps = 1.0 / max(time.time() - t0, 1e-6)
                    self.after(0, lambda f=fps: self.fps_lbl.config(text=f"{f:.1f}"))

                except Exception as e:
                    self.after(0, lambda err=e: self._log(f"Hata: {err}"))

                time.sleep(max(0, interval - (time.time() - t0)))

    def _update_preview(self, frame_bgr: np.ndarray):
        h, w    = frame_bgr.shape[:2]
        display = frame_bgr.copy()

        def draw_poly(poly, color, label):
            pts = (poly * np.array([w, h])).astype(np.int32)
            cv2.polylines(display, [pts], isClosed=True, color=color, thickness=1)
            cx = int(pts[:, 0].mean())
            cy = int(pts[:, 1].mean())
            cv2.putText(display, label, (cx - 10, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        draw_poly(self.top_zone, (0, 180, 255), "TOP")
        draw_poly(self.bot_zone, (255, 100, 0), "BOT")

        img_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb).resize((300, 300), Image.NEAREST)
        tk_img  = ImageTk.PhotoImage(pil_img)

        def _draw():
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=tk_img)
            self.canvas._img_ref = tk_img

        self.after(0, _draw)


if __name__ == "__main__":
    app = MinimapWatcherApp()
    app.mainloop()