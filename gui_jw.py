#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Segments + Special Points + Punctures (Tkinter) with AUTO-FIT GRID

World box: [-WORLD_RANGE, +WORLD_RANGE]^2 always fully visible
Modes:
- [1] Segments: click P0 then P1 to add segment Lk
- [2] Special Points: click near a segment to drop a point (orthogonal projection, clamped)
- [3]/[P] Punctures: GUI-only hollow points (NOT exported)

Chain Mode [L]:
- When ON, each new segment starts at previous segment's P1 (exactly).
- When OFF, first click snaps to nearest existing endpoint within SNAP_PX.

Exports:
- C = copy text summary (segments + special points)
- J = copy JSON to clipboard (segments + special points)
- Shift+J or Ctrl+S = SAVE JSON to disk

Other:
- R = reset, G = grid toggle

Tested on Python 3.13. Fractions are constructed with integer math only.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from math import sqrt
from fractions import Fraction
import json
import copy  # NEW: for undo/redo deep copies

# -------- Config --------
WORLD_RANGE = 30                 # world coords are clamped to [-WORLD_RANGE, +WORLD_RANGE]
GRID_MAJOR_EVERY = 1             # major grid step in world units
DEFAULT_PX_PER_UNIT = 40         # fallback px/unit if window is very small
BORDER_PADDING_PX = 16           # inner padding so border is not glued to the edge
SNAP_PX = 12                     # px radius to snap to an existing endpoint (when picking P0/P1)

ROUND_DP = 6

SNAP_TO_INTEGER = True     # default ON
WORLD_BORDER_VISIBLE = False  # hide the box unless you want it

# -------- Helpers --------
def frac_fmt(v):
    if isinstance(v, Fraction):
        return f"{v.numerator}/{v.denominator}" if v.denominator != 1 else f"{v.numerator}"
    return f"{v:.{ROUND_DP}f}"

def frac_min(a, b): return a if a <= b else b
def frac_max(a, b): return a if a >= b else b

def dot(ax, ay, bx, by):
    return ax * bx + ay * by  # supports Fractions

def to_float(v):
    return float(v.numerator) / float(v.denominator) if isinstance(v, Fraction) else float(v)

# -------- App --------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Segments, Special Points & Punctures — Auto-fit [-30,30]^2")

        # Layout
        self.frame = tk.Frame(root)
        self.frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            self.frame, bg="white", width=900, height=680,
            highlightthickness=1, highlightbackground="#ccc", cursor="crosshair"
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.info = tk.Text(
            self.frame, width=50, height=34, bg="#0b1021", fg="#e8f0fe",
            insertbackground="white", padx=10, pady=10, wrap="word", state="normal"
        )
        self.info.grid(row=0, column=1, sticky="nsew")

        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(0, weight=4)
        self.frame.columnconfigure(1, weight=0)

        # State
        self.mode = "segment"          # "segment" | "point" | "puncture"
        self.pending_p0 = None
        self.segments = []             # [{id, p0:(x,y), p1:(x,y), color}]
        self.special_points = []       # [{id, seg_id, t, xy:(x,y)}]
        self.punctures = []            # [{id, xy:(x,y)}]
        self.next_seg_id = 1
        self.next_sp_id = 1
        self.next_puncture_id = 1
        self.grid_on = True
        self.chain_mode = False

        # dynamic pixels-per-unit so [-WORLD_RANGE, WORLD_RANGE]^2 always fits
        self.px_per_unit = DEFAULT_PX_PER_UNIT

        # History (Undo/Redo)
        self.history = []   # stack of snapshots
        self.future  = []   # stack of undone states
        self._restoring = False

        # Bindings
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button>", self.on_click)
        # Recompute px/unit whenever the canvas size changes
        self.canvas.bind("<Configure>", self.on_resize)

        root.bind("<Key-1>", lambda e: self.set_mode("segment"))
        root.bind("<Key-2>", lambda e: self.set_mode("point"))
        root.bind("<Key-3>", lambda e: self.set_mode("puncture"))
        root.bind("<Key-p>", lambda e: self.set_mode("puncture"))
        root.bind("<Key-P>", lambda e: self.set_mode("puncture"))

        root.bind("<Key-r>", lambda e: self.reset())
        root.bind("<Key-R>", lambda e: self.reset())
        root.bind("<Key-g>", lambda e: self.toggle_grid())
        root.bind("<Key-G>", lambda e: self.toggle_grid())
        root.bind("<Key-l>", lambda e: self.toggle_chain())
        root.bind("<Key-L>", lambda e: self.toggle_chain())

        # Copy & Save
        root.bind("<Key-c>", lambda e: self.copy_text())
        root.bind("<Key-C>", lambda e: self.copy_text())
        root.bind("<Key-j>", lambda e: self.copy_json())
        root.bind("<Key-J>", lambda e: self.save_json())
        root.bind("<Control-s>", lambda e: self.save_json())

        # Snap-to-integer toggle
        self.snap_to_integer = SNAP_TO_INTEGER
        self.root.bind("<Key-s>", lambda e: self.toggle_snap())
        self.root.bind("<Key-S>", lambda e: self.toggle_snap())

        # Undo/Redo bindings
        root.bind("<Control-z>", lambda e: self.undo())
        root.bind("<Control-y>", lambda e: self.redo())
        root.bind("<Key-u>",     lambda e: self.undo())
        root.bind("<Key-U>",     lambda e: self.undo())
        root.bind("<Key-Y>",     lambda e: self.redo())

        self.root.update_idletasks()
        # initialize px/unit and draw
        self.on_resize(None)
        # initial snapshot for undo
        self.push_state("init")

    # ----- Auto-fit pixels-per-unit -----
    def on_resize(self, event):
        w = max(self.canvas.winfo_width(), 2)
        h = max(self.canvas.winfo_height(), 2)
        usable_w = max(w - 2*BORDER_PADDING_PX, 2)
        usable_h = max(h - 2*BORDER_PADDING_PX, 2)
        # choose limiting dimension: we need 2*WORLD_RANGE units across
        # ensure integer px/unit (for integer-only Fractions in screen_to_world)
        self.px_per_unit = max(1, min(usable_w, usable_h) // (2 * WORLD_RANGE))
        self.redraw()

    # ----- Coordinate transforms (integer-only Fractions for 3.13 compatibility) -----
    def world_to_screen(self, x, y):
        w = max(self.canvas.winfo_width(), 2)
        h = max(self.canvas.winfo_height(), 2)
        cx, cy = w/2, h/2
        sx = cx + to_float(x) * self.px_per_unit
        sy = cy - to_float(y) * self.px_per_unit
        return sx, sy

    def screen_to_world(self, sx, sy):
        w = max(self.canvas.winfo_width(), 2)
        h = max(self.canvas.winfo_height(), 2)

        # Fractions with integer numerators/denominators (Py 3.13-safe)
        num_x = 2 * int(sx) - int(w)
        den_x = 2 * self.px_per_unit
        x = Fraction(num_x, den_x)

        num_y = int(h) - 2 * int(sy)
        den_y = 2 * self.px_per_unit
        y = Fraction(num_y, den_y)

        # Optional snap to nearest integer lattice
        if getattr(self, "snap_to_integer", False):
            x = Fraction(round(float(x)), 1)
            y = Fraction(round(float(y)), 1)

        # Clamp to world box [-WORLD_RANGE, WORLD_RANGE]
        if x < -WORLD_RANGE: x = Fraction(-WORLD_RANGE, 1)
        if x >  WORLD_RANGE: x = Fraction( WORLD_RANGE, 1)
        if y < -WORLD_RANGE: y = Fraction(-WORLD_RANGE, 1)
        if y >  WORLD_RANGE: y = Fraction( WORLD_RANGE, 1)

        return x, y

    # ----- History (Undo/Redo) -----
    def snapshot(self):
        return {
            "mode": self.mode,
            "pending_p0": copy.deepcopy(self.pending_p0),
            "segments": copy.deepcopy(self.segments),
            "special_points": copy.deepcopy(self.special_points),
            "punctures": copy.deepcopy(self.punctures),
            "next_seg_id": self.next_seg_id,
            "next_sp_id": self.next_sp_id,
            "next_puncture_id": self.next_puncture_id,
            "grid_on": self.grid_on,
            "chain_mode": self.chain_mode,
        }

    def restore_state(self, s):
        self._restoring = True
        try:
            self.mode = s["mode"]
            self.pending_p0 = copy.deepcopy(s["pending_p0"])
            self.segments = copy.deepcopy(s["segments"])
            self.special_points = copy.deepcopy(s["special_points"])
            self.punctures = copy.deepcopy(s["punctures"])
            self.next_seg_id = s["next_seg_id"]
            self.next_sp_id = s["next_sp_id"]
            self.next_puncture_id = s["next_puncture_id"]
            self.grid_on = s["grid_on"]
            self.chain_mode = s["chain_mode"]
            self.redraw()
            self.render_sidebar(status="State restored.")
        finally:
            self._restoring = False

    def push_state(self, label=None):
        if self._restoring:
            return
        self.history.append(self.snapshot())
        self.future.clear()  # invalidate redo on new action

    def undo(self):
        if len(self.history) <= 1:
            self.render_sidebar(status="Nothing to undo.")
            return
        cur = self.history.pop()
        prev = self.history[-1]
        self.future.append(cur)
        self.restore_state(prev)

    def redo(self):
        if not self.future:
            self.render_sidebar(status="Nothing to redo.")
            return
        nxt = self.future.pop()
        # Keep stack monotonic forward
        self.history.append(nxt)
        self.restore_state(nxt)

    # ----- Mode / UI -----
    def set_mode(self, mode):
        self.mode = mode
        if mode == "segment":
            if not self.chain_mode:
                self.pending_p0 = None
        self.render_sidebar(status=f"Mode set to {mode.title()}.")

    def toggle_chain(self):
        self.chain_mode = not self.chain_mode
        if self.chain_mode and self.segments:
            self.pending_p0 = self.segments[-1]["p1"]
        elif not self.chain_mode:
            self.pending_p0 = None
        self.render_sidebar(status=f"Chain Mode {'ON' if self.chain_mode else 'OFF'}")
        self.redraw()

    def reset(self):
        # Make reset undoable: push current state first
        self.push_state("pre-reset")
        self.pending_p0 = None
        self.segments.clear()
        self.special_points.clear()
        self.punctures.clear()
        self.next_seg_id = 1
        self.next_sp_id = 1
        self.next_puncture_id = 1
        self.redraw()
        self.render_sidebar(status="Cleared all. (Undo with Ctrl+Z)")
        # Snapshot the blank state for redo
        self.push_state("post-reset")

    def toggle_grid(self):
        self.grid_on = not self.grid_on
        self.redraw()

    # ----- Endpoint SNAP logic -----
    def list_endpoints(self):
        eps = []
        for seg in self.segments:
            eps.append((seg["p0"], f"{seg['id']}.P0"))
            eps.append((seg["p1"], f"{seg['id']}.P1"))
        return eps

    def nearest_endpoint_within_px(self, sx, sy, max_px=SNAP_PX):
        best = None
        for world_xy, label in self.list_endpoints():
            ex, ey = self.world_to_screen(world_xy[0], world_xy[1])
            d2 = (ex - sx) ** 2 + (ey - sy) ** 2
            if best is None or d2 < best[2]:
                best = (world_xy, label, d2)
        if best is None:
            return None
        d = sqrt(best[2])
        if d <= max_px:
            return best[0], best[1], d
        return None

    # ----- Click handling -----
    def on_click(self, event):
        if event.widget is not self.canvas:
            return
        sx, sy = event.x, event.y
        p = self.screen_to_world(sx, sy)
        if self.mode == "segment":
            self.handle_segment_click(p, sx, sy)
        elif self.mode == "point":
            self.handle_point_click(p)
        else:  # puncture
            self.handle_puncture_click(p)

    def handle_segment_click(self, p, sx, sy):
        # Chain Mode: p0 forced to last p1; allow snapping of p1
        if self.chain_mode and self.segments:
            p0 = self.segments[-1]["p1"]
            snapped = self.nearest_endpoint_within_px(sx, sy)
            p1 = snapped[0] if snapped else p
            seg = {
                "id": f"L{self.next_seg_id}",
                "p0": p0,
                "p1": p1,
                "color": "#111827",
            }
            self.next_seg_id += 1
            self.segments.append(seg)
            self.push_state("add-segment")  # NEW
            self.pending_p0 = seg["p1"]
            msg = f"Added segment {seg['id']} (Chain Mode)."
            if snapped:
                msg += f" P1 snapped to {snapped[1]}."
            self.render_sidebar(status=msg)
            self.redraw()
            return

        # Chain Mode OFF
        if self.pending_p0 is None:
            snapped = self.nearest_endpoint_within_px(sx, sy)
            self.pending_p0 = snapped[0] if snapped else p
            msg = "P0 placed."
            if snapped:
                msg += f" Snapped to {snapped[1]}."
            self.render_sidebar(status=msg + " Click P1 to finish the segment.")
            self.redraw()
        else:
            p0 = self.pending_p0
            snapped = self.nearest_endpoint_within_px(sx, sy)
            p1 = snapped[0] if snapped else p
            if p0 == p1:
                self.render_sidebar(status="Ignored zero-length segment; pick a different P1.")
                self.pending_p0 = None
                return
            seg = {
                "id": f"L{self.next_seg_id}",
                "p0": p0,
                "p1": p1,
                "color": "#111827",
            }
            self.next_seg_id += 1
            self.segments.append(seg)
            self.push_state("add-segment")  # NEW
            self.pending_p0 = None
            msg = f"Added segment {seg['id']}."
            if snapped:
                msg += f" P1 snapped to {snapped[1]}."
            self.render_sidebar(status=msg)
            self.redraw()

    def toggle_snap(self):
        self.snap_to_integer = not self.snap_to_integer
        self.render_sidebar(status=f"Snap-to-integer {'ON' if self.snap_to_integer else 'OFF'}")

    def handle_point_click(self, q):
        if not self.segments:
            self.render_sidebar(status="No segments yet. Switch to mode [1] to add one.")
            return
        best = None
        for seg in self.segments:
            p0x, p0y = seg["p0"]
            p1x, p1y = seg["p1"]
            vx, vy = (p1x - p0x), (p1y - p0y)
            vv = dot(vx, vy, vx, vy)
            if vv == 0:
                continue
            q0x, q0y = (q[0] - p0x), (q[1] - p0y)
            t_star = dot(q0x, q0y, vx, vy) / vv
            # clamp to [0,1]
            if t_star < 0:
                t = Fraction(0, 1)
            elif t_star > 1:
                t = Fraction(1, 1)
            else:
                t = t_star
            x = p0x + t * vx
            y = p0y + t * vy
            sx, sy = self.world_to_screen(x, y)
            qsx, qsy = self.world_to_screen(q[0], q[1])
            d2 = (sx - qsx) ** 2 + (sy - qsy) ** 2
            if (best is None) or (d2 < best["d2"]):
                best = {"seg": seg, "t": t, "xy": (x, y), "d2": d2}

        if best is None:
            self.render_sidebar(status="Could not place point (no valid segment).")
            return

        sp = {
            "id": f"S{self.next_sp_id}",
            "seg_id": best["seg"]["id"],
            "t": best["t"],
            "xy": best["xy"],
        }
        self.next_sp_id += 1
        self.special_points.append(sp)
        self.push_state("add-special-point")  # NEW
        self.redraw()
        self.render_sidebar(status=f"Added special point {sp['id']} on {sp['seg_id']} at t={frac_fmt(sp['t'])}.")

    # --- Punctures ---
    def handle_puncture_click(self, p):
        pu = {"id": f"P{self.next_puncture_id}", "xy": p}
        self.next_puncture_id += 1
        self.punctures.append(pu)
        self.push_state("add-puncture")  # NEW
        self.redraw()
        self.render_sidebar(status=f"Added puncture {pu['id']}.")

    # ----- Drawing -----
    def redraw(self):
        self.canvas.delete("all")
        if self.grid_on:
            self.draw_grid()
        self.draw_axes()

        # Pending P0 marker (when not chaining)
        if self.mode == "segment" and self.pending_p0 is not None and not self.chain_mode:
            self.draw_point(self.pending_p0, fill="#1d4ed8")

        # Segments
        for seg in self.segments:
            self.draw_segment(seg)

        # Special points
        for sp in self.special_points:
            self.draw_point(sp["xy"], fill="#ef4444")
            sx, sy = self.world_to_screen(*sp["xy"])
            self.canvas.create_text(sx + 10, sy - 8, text=sp["id"], fill="#ef4444",
                                    font=("TkDefaultFont", 10, "bold"))

        # Punctures
        for pu in self.punctures:
            self.draw_puncture(pu["xy"], label=pu["id"])

    def draw_grid(self):
        # lines at every integer from -WORLD_RANGE to +WORLD_RANGE
        for i in range(-WORLD_RANGE, WORLD_RANGE + 1):
            sx, _ = self.world_to_screen(i, 0)
            color = "#f3f4f6" if i % GRID_MAJOR_EVERY == 0 else "#fafafa"
            self.canvas.create_line(sx, 0, sx, self.canvas.winfo_height(), fill=color)
        for j in range(-WORLD_RANGE, WORLD_RANGE + 1):
            _, sy = self.world_to_screen(0, j)
            color = "#f3f4f6" if j % GRID_MAJOR_EVERY == 0 else "#fafafa"
            self.canvas.create_line(0, sy, self.canvas.winfo_width(), sy, fill=color)
        # visible border for the world box (optional)
        if WORLD_BORDER_VISIBLE:
            xL, yT = self.world_to_screen(-WORLD_RANGE,  WORLD_RANGE)
            xR, yB = self.world_to_screen( WORLD_RANGE, -WORLD_RANGE)
            self.canvas.create_rectangle(xL, yT, xR, yB, outline="#cbd5e1")

    def draw_axes(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.create_line(0, h/2, w, h/2, fill="#94a3b8", width=1.5)
        self.canvas.create_line(w/2, 0, w/2, h, fill="#94a3b8", width=1.5)

    def draw_point(self, p, fill="#1d4ed8"):
        sx, sy = self.world_to_screen(to_float(p[0]), to_float(p[1]))
        r = 4
        self.canvas.create_oval(sx-r, sy-r, sx+r, sy+r, fill=fill, outline="")

    def draw_segment(self, seg):
        x0, y0 = seg["p0"]; x1, y1 = seg["p1"]
        s0 = self.world_to_screen(x0, y0)
        s1 = self.world_to_screen(x1, y1)
        self.canvas.create_line(*s0, *s1, fill=seg["color"], width=2)
        mx = (x0 + x1)/2
        my = (y0 + y1)/2
        smx, smy = self.world_to_screen(mx, my)
        self.canvas.create_text(smx, smy - 12, text=seg["id"], fill="#111827",
                                font=("TkDefaultFont", 10, "bold"))
        # endpoint dots (aid snapping)
        self.draw_point((x0, y0), fill="#1f2937")
        self.draw_point((x1, y1), fill="#1f2937")

    def draw_puncture(self, p, label=None):
        sx, sy = self.world_to_screen(to_float(p[0]), to_float(p[1]))
        r = 6
        self.canvas.create_oval(sx-r, sy-r, sx+r, sy+r, outline="#f59e0b", width=2)
        if label:
            self.canvas.create_text(sx + 10, sy + 10, text=label, fill="#f59e0b",
                                    font=("TkDefaultFont", 10, "bold"))

    # ----- Sidebar content -----
    def render_sidebar(self, status=None):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")

        mode_name = {"segment": "Segments [1]", "point": "Special Points [2]", "puncture": "Punctures [3/P]"}[self.mode]
        self.info.insert("end", f"Mode: {mode_name}\n")
        self.info.insert("end", f"Chain Mode [L]: {'ON' if self.chain_mode else 'OFF'}\n")
        self.info.insert("end", f"Snap-to-integer [S]: {'ON' if self.snap_to_integer else 'OFF'}\n")
        self.info.insert("end", f"px/unit: {self.px_per_unit}\n")
        # Undo/Redo availability
        avail = f"Undo:{'Y' if len(self.history)>1 else 'N'}  Redo:{'Y' if bool(self.future) else 'N'}"
        self.info.insert("end", f"{avail}\n")
        if status:
            self.info.insert("end", f"{status}\n")
        self.info.insert("end", "Keys: 1=Segments, 2=Points, 3/P=Punctures, L=Chain, S=Snap, R=Reset, G=Grid, "
                                "C=Copy Text, J=Copy JSON, Shift+J/Ctrl+S=Save JSON, Ctrl+Z=Undo, Ctrl+Y=Redo\n\n")

        if self.segments:
            self.info.insert("end", "Segments:\n")
            for seg in self.segments:
                p0 = seg["p0"]; p1 = seg["p1"]
                vx, vy = (p1[0] - p0[0]), (p1[1] - p0[1])
                x0s, y0s = frac_fmt(p0[0]), frac_fmt(p0[1])
                vxs, vys = frac_fmt(vx), frac_fmt(vy)
                xmin = frac_min(p0[0], p1[0]); xmax = frac_max(p0[0], p1[0])
                ymin = frac_min(p0[1], p1[1]); ymax = frac_max(p0[1], p1[1])
                self.info.insert("end", f"  {seg['id']}: r(t)=({x0s},{y0s}) + t·({vxs},{vys}),  t∈[0,1]\n")
                self.info.insert("end", f"       x∈[{frac_fmt(xmin)}, {frac_fmt(xmax)}],  y∈[{frac_fmt(ymin)}, {frac_fmt(ymax)}]\n")
            self.info.insert("end", "\n")
        else:
            self.info.insert("end", "No segments yet. Press [1] and click P0, then P1.\n\n")

        if self.special_points:
            self.info.insert("end", "Special points:\n")
            for sp in self.special_points:
                x, y = sp["xy"]
                self.info.insert("end",
                    f"  {sp['id']}: on {sp['seg_id']} at t={frac_fmt(sp['t'])},  "
                    f"coords=({frac_fmt(x)}, {frac_fmt(y)})\n")
            self.info.insert("end", "\n")
        else:
            self.info.insert("end", "No special points yet. Press [2] and click near a segment.\n")

        if self.punctures:
            self.info.insert("end", "Punctures:\n")
            for pu in self.punctures:
                x, y = pu["xy"]
                self.info.insert("end", f"  {pu['id']}: ({frac_fmt(x)}, {frac_fmt(y)})\n")
            self.info.insert("end", "\n")
        else:
            self.info.insert("end", "No punctures yet. Press [3] or [P], then click to place.\n")

        self.info.configure(state="disabled")

    # ----- Clipboard & File exports -----
    def export_text(self):
        # punctures intentionally omitted from text copy
        lines = []
        lines.append("Segments:")
        if not self.segments:
            lines.append("  (none)")
        for seg in self.segments:
            p0 = seg["p0"]; p1 = seg["p1"]
            vx, vy = (p1[0] - p0[0]), (p1[1] - p0[1])
            xmin = frac_min(p0[0], p1[0]); xmax = frac_max(p0[0], p1[0])
            ymin = frac_min(p0[1], p1[1]); ymax = frac_max(p0[1], p1[1])
            lines.append(
                f"  {seg['id']}: r(t)=({frac_fmt(p0[0])},{frac_fmt(p0[1])}) + t·({frac_fmt(vx)},{frac_fmt(vy)}), t∈[0,1]"
            )
            lines.append(
                f"     x∈[{frac_fmt(xmin)}, {frac_fmt(xmax)}], y∈[{frac_fmt(ymin)}, {frac_fmt(ymax)}]"
            )
        lines.append("")
        lines.append("Special points:")
        if not self.special_points:
            lines.append("  (none)")
        for sp in self.special_points:
            x, y = sp["xy"]
            lines.append(
                f"  {sp['id']}: on {sp['seg_id']} at t={frac_fmt(sp['t'])}, coords=({frac_fmt(x)}, {frac_fmt(y)})"
            )
        return "\n".join(lines)

    def export_json(self):
        
        data = {
            "segments": [
                {
                    "id": seg["id"],
                    "p0": (float(seg["p0"][0]), float(seg["p0"][1])),
                    "p1": (float(seg["p1"][0]), float(seg["p1"][1]))
                }
                for seg in self.segments
            ],
            "special_points": [
                {
                    "id": sp["id"],
                    "seg_id": sp["seg_id"],
                    "t": float(sp["t"]),
                    "coor": (float(sp["xy"][0]), float(sp["xy"][1]))
                }
                for sp in self.special_points
            ],
            "punctures": [
                {
                    "id": pu["id"],
                    "coor": (float(pu["xy"][0]), float(pu["xy"][1]))
                }
                for pu in self.punctures
            ],
        }
        return json.dumps(data, indent=2)

    def copy_text(self):
        text = self.export_text()
        self.root.clipboard_clear(); self.root.clipboard_append(text); self.root.update()
        self.render_sidebar(status="Copied summary to clipboard (C).")

    def copy_json(self):
        js = self.export_json()
        self.root.clipboard_clear(); self.root.clipboard_append(js); self.root.update()
        self.render_sidebar(status="Copied JSON to clipboard (J).")

    def save_json(self):
        js = self.export_json()
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save JSON"
        )
        if not filename:
            self.render_sidebar(status="Save canceled.")
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(js)
            messagebox.showinfo("Saved", f"JSON saved to:\n{filename}")
            self.render_sidebar(status=f"Saved JSON to {filename}.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save:\n{e}")
            self.render_sidebar(status="Error saving JSON. See dialog for details.")

# Utility: convert world point to screen px (for distance calc)
def event_px(app, world_pt, axis='x'):
    sx, sy = app.world_to_screen(world_pt[0], world_pt[1])
    return sx if axis == 'x' else sy

def main():
    root = tk.Tk()
    root.minsize(900, 520)
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
