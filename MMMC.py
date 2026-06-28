#!/usr/bin/env python3

import sys
import os
import struct
import gzip
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageEnhance, ImageSequence
import cv2

# ========== 1.20.1 地图调色板 ==========
BASE_COLORS = [
    (0,0,0),(0,0,0),(0,0,0),(0,0,0),
    (89,125,39),(109,153,48),(127,178,56),(67,94,29),
    (174,164,115),(213,201,140),(247,233,163),(130,123,86),
    (140,140,140),(171,171,171),(199,199,199),(105,105,105),
    (180,0,0),(220,0,0),(255,0,0),(135,0,0),
    (112,112,180),(138,138,220),(160,160,255),(84,84,135),
    (117,117,117),(144,144,144),(167,167,167),(88,88,88),
    (0,87,0),(0,106,0),(0,124,0),(0,65,0),
    (180,180,180),(220,220,220),(255,255,255),(135,135,135),
    (115,118,129),(141,144,158),(164,168,184),(86,89,97),
    (106,76,54),(130,94,66),(151,109,77),(79,57,40),
    (79,79,79),(96,96,96),(112,112,112),(59,59,59),
    (45,45,180),(55,55,220),(64,64,255),(33,33,135),
    (100,84,50),(123,102,62),(143,119,72),(75,63,38),
    (180,177,172),(212,210,204),(248,248,248),(135,133,129),
    (152,89,36),(186,109,44),(216,127,51),(114,67,27),
]

def color_distance(c1, c2):
    return (c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2

def find_closest_color_index(r, g, b):
    best_idx = 4
    best_dist = float('inf')
    for i in range(4, len(BASE_COLORS)):
        cr, cg, cb = BASE_COLORS[i]
        d = color_distance((r, g, b), (cr, cg, cb))
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx

def adjust_saturation(img, factor):
    if factor == 1.0:
        return img
    enhancer = ImageEnhance.Color(img)
    return enhancer.enhance(factor)

def image_to_map_colors(img, dither_mode="none"):
    img = img.resize((128, 128), Image.LANCZOS)
    pixels = img.load()
    colors = bytearray(128 * 128)

    if dither_mode == "none":
        for y in range(128):
            for x in range(128):
                r, g, b = pixels[x, y]
                colors[y * 128 + x] = find_closest_color_index(r, g, b)
    elif dither_mode == "2x2":
        bayer = [[0, 2], [3, 1]]
        for y in range(128):
            for x in range(128):
                r, g, b = pixels[x, y]
                best_dist = float('inf')
                second_dist = float('inf')
                best_idx = 0
                second_idx = 0
                for i in range(4, len(BASE_COLORS)):
                    cr, cg, cb = BASE_COLORS[i]
                    d = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
                    if d < best_dist:
                        second_dist = best_dist
                        second_idx = best_idx
                        best_dist = d
                        best_idx = i
                    elif d < second_dist:
                        second_dist = d
                        second_idx = i
                if best_dist < second_dist * 0.3:
                    colors[y * 128 + x] = best_idx
                else:
                    threshold = bayer[x % 2][y % 2] / 4.0
                    total = best_dist + second_dist
                    if total == 0:
                        colors[y * 128 + x] = best_idx
                    else:
                        ratio_best = 1 - best_dist / total
                        if threshold < ratio_best:
                            colors[y * 128 + x] = best_idx
                        else:
                            colors[y * 128 + x] = second_idx
    return bytes(colors)

def build_map_nbt(colors, scale=0, locked=1, tracking=0):
    buffer = bytearray()
    def write_byte(v): buffer.append(v & 0xFF)
    def write_short(v): buffer.extend(struct.pack('>h', v))
    def write_int(v): buffer.extend(struct.pack('>i', v))
    def write_string(s):
        encoded = s.encode('utf-8')
        write_short(len(encoded))
        buffer.extend(encoded)
    def write_byte_array(data):
        write_int(len(data))
        buffer.extend(data)

    write_byte(10); write_string("")
    write_byte(10); write_string("data")

    write_byte(1); write_string("scale"); write_byte(scale)
    write_byte(2); write_string("height"); write_short(128)
    write_byte(2); write_string("width"); write_short(128)
    write_byte(1); write_string("locked"); write_byte(locked)
    write_byte(1); write_string("trackingPosition"); write_byte(tracking)
    write_byte(3); write_string("xCenter"); write_int(0)
    write_byte(3); write_string("zCenter"); write_int(0)
    write_byte(7); write_string("colors"); write_byte_array(colors)
    write_byte(1); write_string("dimension"); write_byte(0)
    write_byte(1); write_string("unlimitedTracking"); write_byte(0)
    write_byte(0); write_byte(0)
    return bytes(buffer)

def save_map_file(output_path, colors, scale=0, locked=1, tracking=0):
    nbt_data = build_map_nbt(colors, scale, locked, tracking)
    with gzip.open(output_path, 'wb') as f:
        f.write(nbt_data)

# ========== 帧加载（已移除帧数限制） ==========
def load_frames_from_file(path, log_func=None):

    if log_func is None:
        log_func = print
    ext = os.path.splitext(path)[1].lower()
    log_func(f"文件扩展名: {ext}")

    if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'):
        img = Image.open(path).convert("RGB")
        log_func(f"静态图片尺寸: {img.size}")
        return [img]

    elif ext == '.gif':
        try:
            gif = Image.open(path)
            n_frames = getattr(gif, 'n_frames', 0)
            log_func(f"GIF 总帧数: {n_frames if n_frames else '未知'}")
            frames = []
            for frame in ImageSequence.Iterator(gif):
                frames.append(frame.copy().convert("RGB"))
            gif.close()
            if not frames:
                log_func("警告：未提取到 GIF 帧，退化为静态读取")
                return [Image.open(path).convert("RGB")]
            log_func(f"GIF 实际加载帧数: {len(frames)}")
            return frames
        except Exception as e:
            log_func(f"GIF 读取异常: {e}")
            raise

    elif ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm'):
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                raise RuntimeError("无法打开视频，请检查路径或编码格式")
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            log_func(f"视频总帧数: {total}")
            frames = []
            count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                frames.append(img)
                count += 1
                # 每100帧输出一次进度，避免日志刷屏
                if count % 100 == 0:
                    log_func(f"已读取 {count} 帧...")
            cap.release()
            log_func(f"视频实际加载帧数: {len(frames)}")
            return frames
        except Exception as e:
            log_func(f"视频读取异常: {e}")
            raise
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

# ========== GUI ==========
class MapConverterGUI:
    def __init__(self, root):
        self.root = root
        root.title("M~M~M")
        root.geometry("750x900")
        root.resizable(False, False)

        self.file_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.locked = tk.BooleanVar(value=True)
        self.tracking = tk.BooleanVar(value=False)
        self.saturation = tk.DoubleVar(value=1.0)
        self.split_enabled = tk.BooleanVar(value=False)
        self.split_cols = tk.IntVar(value=2)
        self.split_rows = tk.IntVar(value=2)
        self.start_id = tk.IntVar(value=0)
        self.dither_mode = tk.StringVar(value="none")
        self.convert_all_frames = tk.BooleanVar(value=True)

        self.frames_cache = []
        self.preview_index = 0

        self.create_widgets()

    def create_widgets(self):
        tk.Label(self.root, text="M M M", font=("Arial", 16)).pack(pady=10)

        f1 = tk.Frame(self.root); f1.pack(fill="x", padx=20, pady=2)
        tk.Label(f1, text="输入文件:", width=10).pack(side="left")
        tk.Entry(f1, textvariable=self.file_path, width=30).pack(side="left", expand=True, fill="x")
        tk.Button(f1, text="浏览...", command=self.browse_file).pack(side="right")

        f2 = tk.Frame(self.root); f2.pack(fill="x", padx=20, pady=2)
        tk.Label(f2, text="输出目录:", width=10).pack(side="left")
        tk.Entry(f2, textvariable=self.output_dir, width=30).pack(side="left", expand=True, fill="x")
        tk.Button(f2, text="浏览...", command=self.browse_output).pack(side="right")

        f3 = tk.Frame(self.root); f3.pack(fill="x", padx=20, pady=5)
        tk.Checkbutton(f3, text="锁定地图", variable=self.locked).pack(side="left", padx=5)
        tk.Checkbutton(f3, text="追踪玩家位置", variable=self.tracking).pack(side="left", padx=5)

        f_sat = tk.Frame(self.root); f_sat.pack(fill="x", padx=20, pady=5)
        tk.Label(f_sat, text="饱和度:").pack(side="left")
        sat_scale = tk.Scale(f_sat, from_=0.5, to=3.0, resolution=0.1, orient=tk.HORIZONTAL,
                             variable=self.saturation, length=180, command=self.on_saturation_change)
        sat_scale.pack(side=tk.LEFT, padx=10)
        tk.Label(f_sat, textvariable=self.saturation, width=4).pack(side=tk.LEFT)

        f_split = tk.Frame(self.root); f_split.pack(fill="x", padx=20, pady=5)
        tk.Checkbutton(f_split, text="分割成多张地图", variable=self.split_enabled).pack(side=tk.LEFT, padx=5)
        tk.Label(f_split, text="列数:").pack(side=tk.LEFT, padx=(10,0))
        tk.Entry(f_split, textvariable=self.split_cols, width=4).pack(side=tk.LEFT, padx=2)
        tk.Label(f_split, text="行数:").pack(side=tk.LEFT, padx=(5,0))
        tk.Entry(f_split, textvariable=self.split_rows, width=4).pack(side=tk.LEFT, padx=2)

        f_id = tk.Frame(self.root); f_id.pack(fill="x", padx=20, pady=5)
        tk.Label(f_id, text="起始地图 ID:").pack(side=tk.LEFT)
        tk.Entry(f_id, textvariable=self.start_id, width=6).pack(side=tk.LEFT, padx=5)
        tk.Label(f_id, text="(编号递增)").pack(side=tk.LEFT)

        f_dither = tk.Frame(self.root); f_dither.pack(fill="x", padx=20, pady=5)
        tk.Label(f_dither, text="混色模式:").pack(side=tk.LEFT)
        dither_opts = [("无", "none"), ("2x2 抖动", "2x2")]
        for text, val in dither_opts:
            tk.Radiobutton(f_dither, text=text, variable=self.dither_mode, value=val).pack(side=tk.LEFT, padx=5)

        f_frame = tk.Frame(self.root); f_frame.pack(fill="x", padx=20, pady=5)
        tk.Button(f_frame, text="◀ 上一帧", command=self.prev_frame).pack(side=tk.LEFT, padx=2)
        tk.Button(f_frame, text="下一帧 ▶", command=self.next_frame).pack(side=tk.LEFT, padx=2)
        self.frame_label = tk.Label(f_frame, text="帧: 0/0")
        self.frame_label.pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(f_frame, text="转换所有帧", variable=self.convert_all_frames).pack(side=tk.LEFT, padx=15)

        self.preview_label = tk.Label(self.root, text="预览区域", bg="gray")
        self.preview_label.pack(pady=10, expand=True, fill=tk.BOTH, padx=20)

        self.btn_convert = tk.Button(self.root, text="生成地图 (.dat)", command=self.start_conversion,
                                     bg="#4CAF50", fg="white", font=("Arial", 12))
        self.btn_convert.pack(pady=10)

        self.log = tk.Text(self.root, height=8, state="disabled")
        self.log.pack(fill="both", expand=True, padx=20, pady=5)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=5)

    def log_msg(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.root.update()

    def browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("所有支持格式", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff *.mp4 *.avi *.mov *.mkv *.webm"),
                       ("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff"),
                       ("视频", "*.mp4 *.avi *.mov *.mkv *.webm")]
        )
        if path:
            self.file_path.set(path)
            self.output_dir.set(os.path.dirname(path))
            self.frames_cache = []
            self.preview_label.config(image="", text="预览区域")
            self.load_frames()

    def browse_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir.set(path)

    def load_frames(self):
        path = self.file_path.get().strip()
        if not path or not os.path.exists(path):
            return
        try:
            self.log_msg("加载文件...")
            self.frames_cache = load_frames_from_file(path, log_func=self.log_msg)  # 已移除 max_frames 参数
            self.log_msg(f"加载完成，总帧数: {len(self.frames_cache)}")
            if self.frames_cache:
                self.preview_index = 0
                self.preview_frame(0)
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
            self.log_msg(f"错误: {e}")

    def on_saturation_change(self, val):
        if self.frames_cache:
            self.preview_frame(self.preview_index)

    def get_processed_image(self, idx):
        if not self.frames_cache:
            return None
        img = self.frames_cache[idx].copy()
        sat = self.saturation.get()
        if sat != 1.0:
            img = adjust_saturation(img, sat)
        return img

    def preview_frame(self, idx):
        if not self.frames_cache:
            return
        if idx < 0:
            idx = 0
        if idx >= len(self.frames_cache):
            idx = len(self.frames_cache) - 1
        self.preview_index = idx
        img = self.get_processed_image(idx)
        if img is None:
            return
        img.thumbnail((400, 400), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(img)
        self.preview_label.config(image=self.tk_img, text="")
        self.frame_label.config(text=f"帧: {idx+1}/{len(self.frames_cache)}")

    def prev_frame(self):
        if self.frames_cache:
            self.preview_index = (self.preview_index - 1) % len(self.frames_cache)
            self.preview_frame(self.preview_index)

    def next_frame(self):
        if self.frames_cache:
            self.preview_index = (self.preview_index + 1) % len(self.frames_cache)
            self.preview_frame(self.preview_index)

    def start_conversion(self):
        path = self.file_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请选择有效文件")
            return

        out_dir = self.output_dir.get().strip()
        if not out_dir:
            out_dir = os.path.dirname(path)
            self.output_dir.set(out_dir)

        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except:
                messagebox.showerror("错误", f"无法创建目录: {out_dir}")
                return

        self.btn_convert.config(state="disabled", text="转换中...")
        self.progress.start(10)
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        def callback(msg):
            self.root.after(0, self.log_msg, msg)

        def worker():
            try:
                if not self.frames_cache:
                    callback("正在加载帧...")
                    self.frames_cache = load_frames_from_file(path, log_func=callback)  # 无限制
                    callback(f"加载了 {len(self.frames_cache)} 帧")

                if not self.frames_cache:
                    raise RuntimeError("未能提取任何帧")

                do_all = self.convert_all_frames.get() and len(self.frames_cache) > 1
                frames_to_convert = []
                if do_all:
                    callback(f"批量转换模式：共 {len(self.frames_cache)} 帧")
                    frames_to_convert = list(range(len(self.frames_cache)))
                else:
                    callback(f"转换当前预览帧：第 {self.preview_index+1} 帧")
                    frames_to_convert = [self.preview_index]

                start_id = self.start_id.get()
                dither = self.dither_mode.get()
                split = self.split_enabled.get()
                cols = self.split_cols.get() if split else 1
                rows = self.split_rows.get() if split else 1

                id_offset = 0
                for frame_idx in frames_to_convert:
                    img = self.get_processed_image(frame_idx)
                    if img is None:
                        continue
                    current_id = start_id + id_offset
                    if split:
                        callback(f"--- 帧 {frame_idx+1}/{len(self.frames_cache)} 分割 {cols}x{rows} ---")
                        self._convert_split(img, out_dir, cols, rows, current_id, dither, callback)
                        id_offset += cols * rows
                    else:
                        out_path = os.path.join(out_dir, f"map_{current_id}.dat")
                        callback(f"帧 {frame_idx+1}: 生成地图 {out_path}")
                        colors = image_to_map_colors(img, dither_mode=dither)
                        save_map_file(out_path, colors, scale=0,
                                      locked=1 if self.locked.get() else 0,
                                      tracking=1 if self.tracking.get() else 0)
                        id_offset += 1
                callback(f" 全部完成，共生成了 {id_offset} 个地图文件")
                self.root.after(0, lambda: messagebox.showinfo("成功", f"转换完成！\n共生成 {id_offset} 个地图文件"))
            except Exception as e:
                callback(f" 错误: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
            finally:
                self.root.after(0, self.finish_conversion)

        threading.Thread(target=worker, daemon=True).start()

    def _convert_split(self, img, out_dir, cols, rows, start_id, dither, callback):
        w, h = img.size
        tile_w = w // cols
        tile_h = h // rows
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                map_id = start_id + idx
                out_path = os.path.join(out_dir, f"map_{map_id}.dat")
                left = col * tile_w
                top = row * tile_h
                right = left + tile_w
                bottom = top + tile_h
                tile = img.crop((left, top, right, bottom))
                callback(f"  块 ({col+1},{row+1}) → map_{map_id}.dat")
                colors = image_to_map_colors(tile, dither_mode=dither)
                save_map_file(out_path, colors, scale=0,
                              locked=1 if self.locked.get() else 0,
                              tracking=1 if self.tracking.get() else 0)

    def finish_conversion(self):
        self.progress.stop()
        self.btn_convert.config(state="normal", text="生成地图 (.dat)")

def main():
    root = tk.Tk()
    app = MapConverterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()


# WHly5pivTeaLieaLiQ==