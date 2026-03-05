#!/usr/bin/env python3
# encoding: utf-8

"""
Live preview renderer for QET Terminal Block drawings.
Translates the XML element tree from TerminalBlock.drawTerminalBlock()
into tkinter Canvas draw calls.
"""

import tkinter as tk
import customtkinter as ctk


def parse_style(style_str):
    """Parse a QET style string into a dict."""
    props = {}
    if not style_str:
        return props
    for part in style_str.split(';'):
        if ':' in part:
            key, val = part.split(':', 1)
            props[key.strip()] = val.strip()
    return props


def style_to_line_width(props):
    weight = props.get('line-weight', 'normal')
    return 2 if weight == 'bold' else 1


def style_to_fill(props):
    filling = props.get('filling', 'none')
    if filling == 'none' or not filling:
        return ''
    return filling


def style_to_outline(props):
    return props.get('color', 'black')


class PreviewWindow(ctk.CTkToplevel):
    """A separate window that renders a live preview of terminal blocks."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Terminal Block Preview")
        self.geometry("1200x700")
        self.transient(master)

        self.scale = 1.5
        self.offset_x = 20
        self.offset_y = 40

        # Toolbar
        toolbar = ctk.CTkFrame(self, height=40)
        toolbar.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(toolbar, text="Refresh", width=80, command=self.render_preview).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="+", width=35, command=self.zoom_in).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="-", width=35, command=self.zoom_out).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="Reset", width=50, command=self.fit_view).pack(side="left", padx=2)

        self.zoom_label = ctk.CTkLabel(toolbar, text=f"{int(self.scale*100)}%")
        self.zoom_label.pack(side="left", padx=10)

        self.block_var = tk.StringVar(value="-- ALL --")
        self.block_menu = ctk.CTkOptionMenu(toolbar, variable=self.block_var, values=["-- ALL --"],
                                            command=lambda _: self.render_preview())
        self.block_menu.pack(side="left", padx=10)

        # Canvas with scrollbars
        canvas_frame = tk.Frame(self, bg="white")
        canvas_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.h_scroll.pack(side="bottom", fill="x")
        self.v_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Pan with right-click drag
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        self.after(100, self.render_preview)

    def zoom_in(self):
        self.scale = min(self.scale * 1.25, 10.0)
        self._update_zoom_label()
        self.render_preview()

    def zoom_out(self):
        self.scale = max(self.scale / 1.25, 0.2)
        self._update_zoom_label()
        self.render_preview()

    def fit_view(self):
        self.scale = 1.5
        self.offset_x = 20
        self.offset_y = 40
        self._update_zoom_label()
        self.render_preview()

    def _update_zoom_label(self):
        self.zoom_label.configure(text=f"{int(self.scale*100)}%")

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_mousewheel(self, event):
        if event.delta > 0:
            self.scale = min(self.scale * 1.1, 10.0)
        else:
            self.scale = max(self.scale / 1.1, 0.2)
        self._update_zoom_label()
        self.render_preview()

    def render_preview(self):
        """Generate terminal block XML and render it onto the canvas."""
        self.canvas.delete("all")

        try:
            from terminalblock import TerminalBlock
        except ImportError:
            from .terminalblock import TerminalBlock

        # Update block selector
        tb_names = self.app.qet_project.tb_names
        self.block_menu.configure(values=["-- ALL --"] + tb_names)

        # Sync current row data
        for r in self.app.rows:
            r.get_data()

        all_data = self.app.qet_project.terminals
        selected_block = self.block_var.get()

        chosen = tb_names if selected_block == "-- ALL --" else [selected_block]

        if not chosen:
            self._draw_placeholder("No terminal blocks found")
            return

        x_offset_cumulative = 0
        split_val = int(self.app.settings.get('-CFG_SPLIT-', 30))

        for tb_name in chosen:
            block_terminals = [t for t in all_data if t['block_name'] == tb_name]
            if not block_terminals:
                continue

            # Split into segments
            segments = []
            current_seg = []
            for t in block_terminals:
                if len(current_seg) >= split_val:
                    segments.append(current_seg)
                    current_seg = []
                current_seg.append(t)
            if current_seg:
                segments.append(current_seg)

            for seg_idx, seg_data in enumerate(segments):
                head_text = f"{tb_name}({seg_idx+1})" if len(segments) > 1 else tb_name
                tb_obj = TerminalBlock(head_text, seg_data, self.app.settings, debug_mode=False)
                xml_root = tb_obj.drawTerminalBlock()

                definition = xml_root.find('definition')
                if definition is None:
                    continue
                description = definition.find('description')
                if description is None:
                    continue

                total_width = int(definition.get('width', '0'))
                self._render_xml_to_canvas(description, x_offset_cumulative)
                x_offset_cumulative += total_width + 30

        if x_offset_cumulative == 0:
            self._draw_placeholder("No data to preview")
            return

        total_h = 800
        margin = 50
        self.canvas.configure(scrollregion=(
            -margin, -margin,
            x_offset_cumulative * self.scale + margin + self.offset_x,
            total_h * self.scale + margin + self.offset_y
        ))

    def _draw_placeholder(self, text):
        self.canvas.create_text(
            self.canvas.winfo_width() // 2 or 400,
            self.canvas.winfo_height() // 2 or 300,
            text=text, fill="#999", font=("Arial", 14)
        )

    def _render_xml_to_canvas(self, description, x_extra_offset):
        """Walk XML children and draw each primitive on the canvas."""
        s = self.scale
        ox = self.offset_x + x_extra_offset * s
        oy = self.offset_y

        for elem in description:
            tag = elem.tag

            if tag == 'line':
                x1 = float(elem.get('x1', 0)) * s + ox
                y1 = float(elem.get('y1', 0)) * s + oy
                x2 = float(elem.get('x2', 0)) * s + ox
                y2 = float(elem.get('y2', 0)) * s + oy
                props = parse_style(elem.get('style', ''))
                width = style_to_line_width(props)
                color = style_to_outline(props)
                self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width)

            elif tag == 'rect':
                x = float(elem.get('x', 0)) * s + ox
                y = float(elem.get('y', 0)) * s + oy
                w = float(elem.get('width', 0)) * s
                h = float(elem.get('height', 0)) * s
                props = parse_style(elem.get('style', ''))
                outline = style_to_outline(props)
                fill = style_to_fill(props)
                width = style_to_line_width(props)
                self.canvas.create_rectangle(x, y, x + w, y + h,
                                             outline=outline, fill=fill if fill else '', width=width)

            elif tag == 'circle':
                x = float(elem.get('x', 0)) * s + ox
                y = float(elem.get('y', 0)) * s + oy
                d = float(elem.get('diameter', 0)) * s
                props = parse_style(elem.get('style', ''))
                outline = style_to_outline(props)
                fill = style_to_fill(props)
                self.canvas.create_oval(x, y, x + d, y + d,
                                        outline=outline, fill=fill if fill else '')

            elif tag == 'dynamic_text':
                x = float(elem.get('x', 0)) * s + ox
                y = float(elem.get('y', 0)) * s + oy
                font_size = max(6, int(float(elem.get('font_size', 9)) * s * 0.75))
                rotation = float(elem.get('rotation', 0))

                text_elem = elem.find('text')
                text = text_elem.text if text_elem is not None and text_elem.text else ''

                color_elem = elem.find('color')
                text_color = 'black'
                if color_elem is not None and color_elem.text:
                    text_color = color_elem.text

                anchor = "sw" if rotation == 270 else "nw"

                self.canvas.create_text(x, y, text=text, fill=text_color,
                                        font=("Arial", font_size),
                                        angle=rotation, anchor=anchor)

            elif tag == 'terminal':
                x = float(elem.get('x', 0)) * s + ox
                y = float(elem.get('y', 0)) * s + oy
                orient = elem.get('orientation', 'n')
                sz = 3 * s
                if orient == 'n':
                    pts = [x, y - sz, x - sz/2, y, x + sz/2, y]
                else:
                    pts = [x, y + sz, x - sz/2, y, x + sz/2, y]
                self.canvas.create_polygon(pts, fill='#2196F3', outline='#1565C0')
