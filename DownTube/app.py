import os
import ctypes
import queue
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_dlp

APP_NAME = 'DownTube'


def ffmpeg_location():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    candidates = [base / 'bin', Path(__file__).resolve().parent / 'bin']
    for folder in candidates:
        if (folder / 'ffmpeg.exe').is_file() or (folder / 'ffmpeg').is_file():
            return str(folder)
    found = shutil.which('ffmpeg')
    return str(Path(found).parent) if found else None


class Cancelled(Exception):
    pass


class Logger:
    def __init__(self, emit):
        self.emit = emit

    def debug(self, msg):
        if not msg.startswith('[debug]') and ('[download]' not in msg):
            self.emit('log', msg)

    def info(self, msg):
        self.emit('log', msg)

    def warning(self, msg):
        self.emit('log', 'Попередження: ' + msg)

    def error(self, msg):
        self.emit('log', 'Помилка: ' + msg)


class DownTube(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('900x770')
        self.minsize(750, 650)
        self.configure(bg='#101827')
        self.events = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.url = tk.StringVar()
        self.folder = tk.StringVar(value=str(Path.home() / 'Downloads'))
        self.mode = tk.StringVar(value='merged')
        self.quality = tk.StringVar(value='Найкраща')
        self.audio_type = tk.StringVar(value='MP3')
        self.container_type = tk.StringVar(value='MP4')
        self.playlist = tk.BooleanVar(value=False)
        self.subtitles = tk.BooleanVar(value=False)
        self.metadata = tk.BooleanVar(value=False)
        self.thumbnail = tk.BooleanVar(value=False)
        self.setup_style()
        self.build_ui()
        self.set_window_appearance()
        self.after(100, self.process_events)

    def set_window_appearance(self):
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        icon = assets / 'downtube_logo.png'
        if icon.is_file():
            self._window_icon = tk.PhotoImage(file=str(icon))
            self.iconphoto(True, self._window_icon)
        if sys.platform != 'win32':
            return
        ico = assets / 'downtube_logo.ico'
        if ico.is_file():
            self.iconbitmap(str(ico))
        self.update_idletasks()
        get_parent = ctypes.windll.user32.GetParent
        get_parent.argtypes = [ctypes.c_void_p]
        get_parent.restype = ctypes.c_void_p
        hwnd = get_parent(self.winfo_id())
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dwm.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        dwm.restype = ctypes.c_long
        dark = ctypes.c_int(1)
        if dwm(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
            dwm(hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark))
        for attribute, color in ((35, 0x271810), (36, 0xFFFFFF)):
            value = ctypes.c_uint32(color)
            dwm(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))

    def setup_style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background='#101827', foreground='#e7edf8', font=('Segoe UI', 10))
        s.configure('TFrame', background='#101827')
        s.configure('TLabel', background='#101827', foreground='#e7edf8')
        s.configure('Header.TLabel', font=('Segoe UI Semibold', 21), foreground='#ffffff')
        s.configure('Hint.TLabel', foreground='#9caecb', font=('Segoe UI', 9))
        s.configure('TButton', background='#293b58', foreground='#ffffff', padding=(10, 8), borderwidth=0)
        s.map('TButton',
              background=[('disabled', '#233045'), ('pressed', '#233045'), ('active', '#375178')],
              foreground=[('disabled', '#9caecb'), ('!disabled', '#ffffff')])
        s.configure('Accent.TButton', background='#3578ed', foreground='#ffffff', padding=(18, 11), font=('Segoe UI Semibold', 10))
        s.map('Accent.TButton',
              background=[('disabled', '#283a53'), ('pressed', '#2057b3'), ('active', '#2669d8')],
              foreground=[('disabled', '#9caecb'), ('!disabled', '#ffffff')])
        s.configure('TEntry', fieldbackground='#18263c', foreground='#ffffff', insertcolor='#ffffff', borderwidth=1, padding=8)
        s.configure('TCombobox', fieldbackground='#18263c', background='#18263c', foreground='#ffffff', arrowcolor='#ffffff', padding=6)
        s.map('TCombobox',
              fieldbackground=[('disabled', '#233045'), ('readonly', '#18263c')],
              background=[('disabled', '#233045'), ('pressed', '#293b58'), ('active', '#375178')],
              foreground=[('disabled', '#9caecb'), ('!disabled', '#ffffff')],
              arrowcolor=[('disabled', '#9caecb'), ('!disabled', '#ffffff')],
              selectbackground=[('!disabled', '#375178')],
              selectforeground=[('!disabled', '#ffffff')])
        self.option_add('*TCombobox*Listbox.background', '#18263c')
        self.option_add('*TCombobox*Listbox.foreground', '#ffffff')
        self.option_add('*TCombobox*Listbox.selectBackground', '#375178')
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        s.configure('TRadiobutton', background='#101827', foreground='#e7edf8')
        s.configure('TCheckbutton', background='#101827', foreground='#e7edf8')
        for style in ('TRadiobutton', 'TCheckbutton'):
            s.configure(style, indicatorbackground='#18263c', indicatorforeground='#ffffff')
            s.map(style,
                  background=[('disabled', '#101827'), ('active', '#18263c')],
                  foreground=[('disabled', '#9caecb'), ('!disabled', '#e7edf8')],
                  indicatorbackground=[('disabled', '#233045'), ('selected', '#3578ed'),
                                       ('pressed', '#293b58'), ('active', '#375178')],
                  indicatorforeground=[('disabled', '#9caecb'), ('!disabled', '#ffffff')])
        s.configure('TProgressbar', troughcolor='#23344d', background='#4b96ff', thickness=16)

    def build_ui(self):
        outer = ttk.Frame(self, padding=23)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=APP_NAME, style='Header.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Посилання → формат → завантажити. Відео, аудіо або обидва окремо.', style='Hint.TLabel').pack(anchor='w', pady=(0, 15))

        ttk.Label(outer, text='ПОСИЛАННЯ НА ВІДЕО / ПЛЕЙЛИСТ').pack(anchor='w')
        row = ttk.Frame(outer)
        row.pack(fill='x', pady=(5, 12))
        ttk.Entry(row, textvariable=self.url).pack(side='left', fill='x', expand=True)
        self.inspect_btn = ttk.Button(row, text='Перевірити формати', command=self.inspect)
        self.inspect_btn.pack(side='left', padx=(8, 0))
        self.info_label = ttk.Label(outer, text='Встав посилання та натисни «Перевірити формати»', style='Hint.TLabel', wraplength=820)
        self.info_label.pack(anchor='w', pady=(0, 13))

        ttk.Label(outer, text='РЕЖИМ ЗАВАНТАЖЕННЯ').pack(anchor='w')
        modes = ttk.Frame(outer)
        modes.pack(fill='x', pady=(6, 15))
        for text, value in [('Відео + звук', 'merged'), ('Тільки відео', 'video'), ('Тільки аудіо', 'audio'), ('Відео й аудіо окремо', 'separate')]:
            ttk.Radiobutton(modes, text=text, value=value, variable=self.mode, command=self.on_mode).pack(side='left', padx=(0, 15))

        options = ttk.Frame(outer)
        options.pack(fill='x', pady=(0, 13))
        for idx in range(3):
            options.columnconfigure(idx, weight=1)
        ttk.Label(options, text='Якість відео').grid(row=0, column=0, sticky='w')
        ttk.Label(options, text='Аудіо / конвертація').grid(row=0, column=1, sticky='w')
        ttk.Label(options, text='Контейнер відео').grid(row=0, column=2, sticky='w')
        self.quality_cb = ttk.Combobox(options, textvariable=self.quality, state='readonly', values=['Найкраща', '2160p', '1440p', '1080p', '720p', '480p', '360p'])
        self.quality_cb.grid(row=1, column=0, sticky='ew', padx=(0, 12), pady=(5, 0))
        self.audio_cb = ttk.Combobox(options, textvariable=self.audio_type, state='readonly', values=['MP3', 'M4A', 'OPUS', 'WAV', 'FLAC', 'Оригінал'])
        self.audio_cb.grid(row=1, column=1, sticky='ew', padx=(0, 12), pady=(5, 0))
        self.container_cb = ttk.Combobox(options, textvariable=self.container_type, state='readonly', values=['MP4', 'MKV'])
        self.container_cb.grid(row=1, column=2, sticky='ew', pady=(5, 0))

        ttk.Label(outer, text='ЗБЕРЕГТИ В ПАПКУ').pack(anchor='w')
        folder_row = ttk.Frame(outer)
        folder_row.pack(fill='x', pady=(5, 12))
        ttk.Entry(folder_row, textvariable=self.folder).pack(side='left', fill='x', expand=True)
        ttk.Button(folder_row, text='Обрати папку', command=self.choose_folder).pack(side='left', padx=(8, 0))
        extras = ttk.Frame(outer)
        extras.pack(fill='x', pady=(0, 12))
        for name, var in [('Увесь плейлист', self.playlist), ('Субтитри (за наявності)', self.subtitles), ('Метадані', self.metadata), ('Мініатюра окремим файлом', self.thumbnail)]:
            ttk.Checkbutton(extras, text=name, variable=var).pack(side='left', padx=(0, 15))

        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(0, 12))
        self.download_btn = ttk.Button(controls, text='⬇ Завантажити', style='Accent.TButton', command=self.download)
        self.download_btn.pack(side='left')
        self.cancel_btn = ttk.Button(controls, text='Скасувати', command=self.stop, state='disabled')
        self.cancel_btn.pack(side='left', padx=(10, 0))
        ttk.Button(controls, text='Відкрити папку', command=self.open_folder).pack(side='right')
        self.progress = ttk.Progressbar(outer, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(0, 7))
        self.status = ttk.Label(outer, text='Готово до роботи', style='Hint.TLabel')
        self.status.pack(anchor='w', pady=(0, 8))
        ttk.Label(outer, text='ЖУРНАЛ').pack(anchor='w')
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill='both', expand=True, pady=(5, 0))
        self.log = tk.Text(log_frame, height=7, bg='#18263c', fg='#cbd8ef', insertbackground='white', relief='flat', wrap='word', font=('Consolas', 9), state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        scrollbar.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scrollbar.set)
        self.on_mode()

    def on_mode(self):
        mode = self.mode.get()
        self.audio_cb.configure(state='readonly' if mode in ('audio', 'separate') else 'disabled')
        self.container_cb.configure(state='readonly' if mode in ('merged', 'video') else 'disabled')
        self.quality_cb.configure(state='readonly' if mode != 'audio' else 'disabled')

    def choose_folder(self):
        path = filedialog.askdirectory(initialdir=self.folder.get() if Path(self.folder.get()).is_dir() else str(Path.home()))
        if path:
            self.folder.set(path)

    def open_folder(self):
        path = Path(self.folder.get()).expanduser()
        if not path.is_dir():
            messagebox.showerror('Немає папки', 'Спочатку оберіть наявну папку.')
            return
        if sys.platform == 'win32':
            os.startfile(str(path))
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', str(path)])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(path)])

    def emit(self, kind, data):
        self.events.put((kind, data))

    def append_log(self, msg):
        self.log.configure(state='normal')
        self.log.insert('end', str(msg).strip() + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def set_busy(self, busy):
        self.busy = busy
        self.inspect_btn.configure(state='disabled' if busy else 'normal')
        self.download_btn.configure(state='disabled' if busy else 'normal')
        self.cancel_btn.configure(state='normal' if busy else 'disabled')

    def valid_url(self):
        url = self.url.get().strip()
        if not url.startswith(('https://', 'http://')):
            messagebox.showerror('Неправильне посилання', 'Встав повне посилання, що починається з https://')
            return None
        return url

    def inspect(self):
        url = self.valid_url()
        if not url or self.busy:
            return
        self.set_busy(True)
        self.cancel.clear()
        self.status.configure(text='Отримую доступні формати…')
        self.append_log('Перевірка: ' + url)
        threading.Thread(target=self.inspect_worker, args=(url,), daemon=True).start()

    def inspect_worker(self, url):
        try:
            opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'skip_download': True,
                    'extract_flat': False, 'socket_timeout': 20}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError('Сервіс не повернув дані.')
            if info.get('entries'):
                info = next((item for item in info['entries'] if item), None)
                if info is None:
                    raise ValueError('Плейлист порожній.')
            heights = sorted({fmt['height'] for fmt in info.get('formats', [])
                              if fmt.get('vcodec') not in (None, 'none')
                              and isinstance(fmt.get('height'), int)}, reverse=True)
            self.emit('inspect', (info.get('title', 'Без назви'), info.get('duration'), heights))
        except Exception as exc:
            self.emit('error', str(exc))
        finally:
            self.emit('done', 'inspect')

    def build_options(self, dest):
        mode = self.mode.get()
        q = self.quality.get()
        height = int(q[:-1]) if q.endswith('p') and q[:-1].isdigit() else None
        limit = f'[height<={height}]' if height else ''
        if mode == 'merged':
            fmt = f'bestvideo{limit}+bestaudio/best{limit}/best'
        elif mode == 'video':
            fmt = f'bestvideo{limit}/best{limit}'
        else:
            fmt = 'bestaudio/best'
        ff = ffmpeg_location()
        opts = {
            'format': fmt, 'paths': {'home': str(dest)},
            'outtmpl': {'default': '%(title).180B [%(id)s].%(ext)s'},
            'noplaylist': not self.playlist.get(),
            'ignoreerrors': False,
            'windowsfilenames': True,
            'continuedl': True,
            'overwrites': False,
            'retries': 5, 'fragment_retries': 5,
            'logger': Logger(self.emit),
            'progress_hooks': [self.progress_hook],
            'postprocessor_hooks': [self.postprocess_hook],
            'writethumbnail': self.thumbnail.get(),
            'writesubtitles': self.subtitles.get(),
            'writeautomaticsub': False,
            'subtitleslangs': ['uk', 'en'],
            'embedmetadata': self.metadata.get(),
            'socket_timeout': 30,
        }
        if ff:
            opts['ffmpeg_location'] = ff
        if mode in ('merged', 'video'):
            opts['merge_output_format'] = self.container_type.get().lower()
            if mode == 'merged':
                opts['format_sort'] = ['vcodec:h264', 'acodec:aac'] if self.container_type.get() == 'MP4' else []
        if mode == 'audio' or mode == 'separate':
            codec = self.audio_type.get().lower()
            if codec != 'оригінал':
                opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': codec, 'preferredquality': '192'}]
        return opts

    def download(self):
        url = self.valid_url()
        if not url or self.busy:
            return
        dest = Path(self.folder.get()).expanduser()
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror('Помилка папки', str(exc))
            return
        if not ffmpeg_location():
            messagebox.showerror('Потрібен FFmpeg', 'Не знайдено FFmpeg. Поклади ffmpeg.exe і ffprobe.exe в папку bin біля app.py (або біля exe), чи встанови FFmpeg у PATH. Для готового exe використай build_windows.bat.')
            return
        try:
            opts = self.build_options(dest)
        except Exception as exc:
            messagebox.showerror('Помилка налаштувань', str(exc))
            return
        self.cancel.clear()
        self.progress['value'] = 0
        self.set_busy(True)
        self.status.configure(text='Починаю завантаження…')
        self.append_log('Завантаження: ' + url + ' (' + self.mode.get() + ')')
        threading.Thread(target=self.download_worker, args=(url, opts, dest), daemon=True).start()

    def progress_hook(self, data):
        if self.cancel.is_set():
            raise Cancelled('Завантаження скасовано користувачем.')
        state = data.get('status')
        if state == 'downloading':
            done = data.get('downloaded_bytes') or 0
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            pct = done / total * 100 if total else 0
            speed = data.get('speed')
            eta = data.get('eta')
            desc = f'{pct:.1f}% | {speed / 1024 / 1024:.2f} МБ/с' if speed else f'{pct:.1f}%'
            if eta is not None:
                desc += f' | залишилось {eta:.0f} с'
            self.emit('progress', (pct, desc))
        elif state == 'finished':
            self.emit('status', 'Потік отримано, обробка FFmpeg…')

    def postprocess_hook(self, data):
        if data.get('status') == 'started':
            self.emit('status', 'Конвертація / об’єднання файлів…')

    def download_worker(self, url, opts, dest):
        try:
            if self.mode.get() == 'separate':
                video_opts = dict(opts)
                height = int(self.quality.get()[:-1]) if self.quality.get().endswith('p') and self.quality.get()[:-1].isdigit() else None
                video_opts['format'] = 'bestvideo' + (f'[height<={height}]' if height else '')
                video_opts.pop('postprocessors', None)
                video_opts['paths'] = {'home': str(dest / 'video')}
                audio_opts = dict(opts)
                audio_opts['paths'] = {'home': str(dest / 'audio')}
                for options in (video_opts, audio_opts):
                    if self.cancel.is_set():
                        raise Cancelled()
                    with yt_dlp.YoutubeDL(options) as ydl:
                        code = ydl.download([url])
                    if code:
                        raise RuntimeError('yt-dlp завершився з помилкою.')
            else:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    code = ydl.download([url])
                if code:
                    raise RuntimeError('yt-dlp завершився з помилкою.')
            if self.cancel.is_set():
                raise Cancelled()
            self.emit('success', str(dest))
        except Cancelled:
            self.emit('cancelled', None)
        except Exception as exc:
            if self.cancel.is_set():
                self.emit('cancelled', None)
            else:
                self.emit('error', str(exc))
        finally:
            self.emit('done', 'download')

    def stop(self):
        self.cancel.set()
        self.status.configure(text='Скасовую після найближчої перевірки…')

    def process_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'log':
                    self.append_log(data)
                elif kind == 'status':
                    self.status.configure(text=data)
                elif kind == 'progress':
                    pct, msg = data
                    self.progress['value'] = pct
                    self.status.configure(text=msg)
                elif kind == 'inspect':
                    title, duration, heights = data
                    mins = f' | {int(duration) // 60}:{int(duration) % 60:02d}' if duration else ''
                    quality = ' | Доступна якість: ' + ', '.join(f'{height}p' for height in heights) if heights else ''
                    self.info_label.configure(text=title + mins + quality)
                    self.status.configure(text='Формати отримано — можна завантажувати')
                    self.append_log('Доступні формати завантажено')
                elif kind == 'success':
                    self.progress['value'] = 100
                    self.status.configure(text='Готово! Файли у: ' + data)
                    self.append_log('УСПІШНО: ' + data)
                    messagebox.showinfo('Завантажено', 'Готово!\n' + data)
                elif kind == 'cancelled':
                    self.status.configure(text='Скасовано')
                    self.append_log('Операцію скасовано (частковий .part файл може лишитися)')
                elif kind == 'error':
                    self.status.configure(text='Помилка — дивись журнал')
                    self.append_log('ПОМИЛКА: ' + data)
                    messagebox.showerror('Помилка', data)
                elif kind == 'done':
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self.process_events)


if __name__ == '__main__':
    DownTube().mainloop()
