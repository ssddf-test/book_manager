import tkinter as tk
from tkinter import filedialog, ttk
import os
import zipfile
import io
import json
import stat
from PIL import Image, ImageTk

# Note: このコードを実行するには、以下のライブラリが必要です。
# pip install ttkbootstrap Pillow

class BookManagerApp:
    def __init__(self, master):
        self.master = master
        master.title("自炊本管理ソフト")
        
        # 'superhero'テーマはモダンで先進的な外観を提供します。
        try:
            import ttkbootstrap as ttkb
            self.style = ttkb.Style(theme="superhero") 
            try:
                # ttkbootstrapのダイアログを使用
                from ttkbootstrap.dialogs import Messagebox
                self.Messagebox = Messagebox
            except ImportError:
                self.Messagebox = None
        except ImportError:
            # ttkbootstrapがない場合は標準のttkを使用
            self.style = ttk.Style()
            self.Messagebox = None

        # 対応する画像拡張子を定義 (webpを含む)
        self.IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp') 
        # 対応する書籍ファイル拡張子を定義
        self.BOOK_EXTENSIONS = ('.zip', '.cbz')

        # 画面レイアウトの設定
        master.grid_columnconfigure(0, weight=1) # フォルダ/ファイルリスト (左パネル)
        master.grid_columnconfigure(1, weight=3) # プレビューエリア (右パネル)
        master.grid_rowconfigure(0, weight=1)

        self.current_folder = ""
        self.files = [] # ファイルフルパスのリスト
        self.preview_image = None
        self.original_image = None
        
        # 読書状態/設定の管理
        self.current_file_path = ""        # 現在開いている本のフルパス
        self.current_book_images = []      # 現在の本の全画像ファイル名リスト
        self.current_page_index = -1       # 現在のページインデックス
        self.settings_file = "settings.json" # 設定ファイル名
        self.reading_progress = {}         # 読書進捗 {ファイルパス: ページインデックス}
        self.folder_history = []           # フォルダ履歴リスト
        self.history_max = 10              # 履歴の最大数
        self.settings = {
            'is_animation_enabled': False,  # ページめくりアニメーション (デフォルト: OFF)
            'page_turn_direction': 'L2R',   # 'L2R': 左で次頁, 'R2L': 右で次頁 
            'sort_key': 'name',             # 現在のソートキー
            'sort_reverse': False           # 降順 (True) か昇順 (False) か
        } 

        self.load_settings() # 設定（進捗と履歴）をロード

        # スクロール/アニメーション状態管理
        self.scroll_start_x = 0
        self.scroll_start_y = 0
        self.current_image_coords = (0, 0) # 画像の現在位置 (キャンバス内の左上座標)
        self.image_item_id = None          # キャンバス内の画像アイテムID
        self.is_dragging = False           # ドラッグ中フラグ
        self.is_animating = False          # アニメーション中フラグ
        self.old_image_item_id = None      # 遷移前の画像ID
        self.settings_window = None        # 設定ウィンドウの参照

        # ----------------------------------------------------
        # 1. フォルダ/ファイル管理パネル
        # ----------------------------------------------------
        self.control_frame = ttk.Frame(master, padding="10")
        self.control_frame.grid(row=0, column=0, sticky="nsew")
        # Treeviewがあるrow=6にweightを設定
        self.control_frame.grid_rowconfigure(6, weight=1) 

        # フォルダ選択ドロップダウンメニュー (履歴機能用) (row=0)
        self.folder_menubutton = ttk.Menubutton(
            self.control_frame, 
            text="📁 フォルダを選択/履歴", 
            bootstyle="primary"
        )
        self.folder_menu = tk.Menu(self.folder_menubutton, tearoff=0)
        self.folder_menubutton["menu"] = self.folder_menu
        self.folder_menubutton.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        
        self.update_folder_menu() # 履歴メニューを初期化
        
        # 設定ボタン (row=1)
        self.settings_button = ttk.Button(
            self.control_frame, 
            text="⚙️ 設定", 
            command=self.open_settings_window, 
            bootstyle="secondary-outline"
        )
        self.settings_button.grid(row=1, column=0, pady=(0, 10), sticky="ew")

        # 現在のフォルダ表示 (row=2)
        self.folder_label = ttk.Label(self.control_frame, text="選択されていません", bootstyle="info")
        self.folder_label.grid(row=2, column=0, pady=(0, 10), sticky="ew")

        # ----------------------------------------------------
        # ソートコントロール (row=3, 4)
        # ----------------------------------------------------
        self.sort_frame = ttk.Frame(self.control_frame)
        self.sort_frame.grid(row=3, column=0, pady=(0, 5), sticky="ew")
        self.sort_frame.grid_columnconfigure(0, weight=1)
        self.sort_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(self.sort_frame, text="ソート:", bootstyle="secondary").grid(row=0, column=0, sticky="w")
        
        self.sort_key_var = tk.StringVar(value=self.settings['sort_key'])
        
        self.sort_combobox = ttk.Combobox(
            self.sort_frame, 
            textvariable=self.sort_key_var,
            values=["名前順", "日付順", "サイズ順"],
            state="readonly"
        )
        self.sort_combobox.grid(row=0, column=1, sticky="ew")
        self.sort_combobox.bind("<<ComboboxSelected>>", self.on_sort_change)
        self.sort_combobox.set({"name": "名前順", "date": "日付順", "size": "サイズ順"}.get(self.settings['sort_key'], "名前順"))

        # 昇順/降順切り替えボタン
        self.sort_reverse_var = tk.BooleanVar(value=self.settings['sort_reverse'])
        self.sort_toggle_button = ttk.Checkbutton(
            self.sort_frame,
            text="降順",
            variable=self.sort_reverse_var,
            bootstyle="square-toggle"
        )
        self.sort_toggle_button.grid(row=1, column=0, columnspan=2, pady=(5, 5), sticky="ew")
        self.sort_toggle_button.bind("<ButtonRelease-1>", self.on_sort_toggle)

        # ファイルリストのタイトル (row=5)
        self.file_list_label = ttk.Label(self.control_frame, text="ファイル一覧:", bootstyle="secondary")
        self.file_list_label.grid(row=5, column=0, sticky="nw", pady=(5, 0))
        
        # Treeviewとそのスクロールバーを保持するフレーム (row=6)
        self.file_list_frame = ttk.Frame(self.control_frame)
        self.file_list_frame.grid(row=6, column=0, sticky="nsew")
        self.file_list_frame.grid_columnconfigure(0, weight=1)
        self.file_list_frame.grid_rowconfigure(0, weight=1)
        
        # ファイルリスト（Treeviewを使用）
        self.file_list = ttk.Treeview(
            self.file_list_frame, 
            columns=('Format', 'Size', 'Date'), 
            show='tree headings', 
            selectmode='browse',
            height=15
        )
        self.file_list.heading('#0', text='ファイル名')
        self.file_list.column('#0', width=150, stretch=tk.YES)
        self.file_list.heading('Format', text='形式')
        self.file_list.column('Format', width=50, stretch=tk.NO)
        self.file_list.heading('Size', text='サイズ')
        self.file_list.column('Size', width=70, stretch=tk.NO, anchor='e')
        self.file_list.heading('Date', text='更新日')
        self.file_list.column('Date', width=100, stretch=tk.NO, anchor='w')
        
        # Treeviewタグの設定
        self.file_list.tag_configure('read', foreground='green')
        self.file_list.tag_configure('reading', foreground='yellow')
        self.file_list.tag_configure('normal', foreground='white')
        
        # スクロールバー
        self.scrollbar = ttk.Scrollbar(self.file_list_frame, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=self.scrollbar.set)
        
        self.file_list.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 選択イベントを設定
        self.file_list.bind('<<TreeviewSelect>>', self.on_file_select)
        
        # ----------------------------------------------------
        # 2. プレビューパネル
        # ----------------------------------------------------
        self.preview_frame = ttk.Frame(master, padding="10")
        self.preview_frame.grid(row=0, column=1, sticky="nsew")
        self.preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_frame.grid_rowconfigure(1, weight=1) 

        self.preview_title = ttk.Label(
            self.preview_frame, 
            text="プレビューエリア", 
            font=('Helvetica', 16, 'bold'),
            bootstyle="primary"
        )
        self.preview_title.grid(row=0, column=0, pady=(0, 10), sticky="ew")

        # プレビュー表示用キャンバス（画像表示に使用）
        self.preview_canvas = tk.Canvas(
            self.preview_frame, 
            bg=self.master.cget('bg'), 
            highlightthickness=0,
            cursor="fleur" 
        )
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        
        # キャンバスのサイズ変更に対応するためのバインディング
        self.preview_canvas.bind('<Configure>', self.resize_image_preview)
        
        # スクロール機能とクリックページめくりのバインディング
        self.preview_canvas.bind("<ButtonPress-1>", self.start_scroll)
        self.preview_canvas.bind("<B1-Motion>", self.do_scroll)
        self.preview_canvas.bind("<ButtonRelease-1>", self.stop_scroll) # クリックページめくり
        
        # マウスホイールによるページ移動のバインディング
        self.preview_canvas.bind("<MouseWheel>", self.handle_mouse_wheel) # Windows/Linux
        self.preview_canvas.bind("<Button-4>", self.handle_mouse_wheel)   # macOS (Scroll Up)
        self.preview_canvas.bind("<Button-5>", self.handle_mouse_wheel)   # macOS (Scroll Down)
        
        # ----------------------------------------------------
        # 3. ページめくりコントロール
        # ----------------------------------------------------
        self.nav_frame = ttk.Frame(self.preview_frame, padding="10 0")
        self.nav_frame.grid(row=2, column=0, pady=(10, 0), sticky="ew")
        self.nav_frame.grid_columnconfigure(0, weight=1) # 次頁ボタン
        self.nav_frame.grid_columnconfigure(1, weight=1) # ページラベル
        self.nav_frame.grid_columnconfigure(2, weight=1) # 前頁ボタン

        # 次頁ボタン (左側に配置)
        self.next_button = ttk.Button(
            self.nav_frame, 
            text="⏪ 次のページ", 
            command=self.next_page, # 次頁へ進む
            bootstyle="info-outline",
            state=tk.DISABLED
        )
        self.next_button.grid(row=0, column=0, padx=(0, 5), sticky="e")

        # ページラベル
        self.page_label = ttk.Label(
            self.nav_frame, 
            text="ページ: - / -",
            anchor="center",
            bootstyle="primary"
        )
        self.page_label.grid(row=0, column=1, sticky="ew")
        
        # 前頁ボタン (右側に配置)
        self.prev_button = ttk.Button(
            self.nav_frame, 
            text="前のページ ⏩", 
            command=self.prev_page, # 前頁へ戻る
            bootstyle="info",
            state=tk.DISABLED
        )
        self.prev_button.grid(row=0, column=2, padx=(5, 0), sticky="w")
        
        # キーボードバインディング (一般的な操作を維持)
        master.bind('<Left>', lambda e: self.prev_page())
        master.bind('<Right>', lambda e: self.next_page())
        
        # 初期ソート状態の適用（昇順/降順ボタンのテキストを設定）
        self.sort_toggle_button.config(text="降順" if self.settings['sort_reverse'] else "昇順")

        # 初期プレースホルダーの表示
        master.after(100, self.display_placeholder)

    # ====================================================
    # ソート機能メソッド
    # ====================================================

    def on_sort_change(self, event=None):
        """ソート方法が変更されたときに設定を更新し、ファイルを再ロードします。"""
        sort_map = {"名前順": "name", "日付順": "date", "サイズ順": "size"}
        selected_text = self.sort_key_var.get()
        new_key = sort_map.get(selected_text, 'name')
        
        # ソートキーが変わったら降順はリセットし、UIも同期させる
        self.settings['sort_key'] = new_key
        self.settings['sort_reverse'] = False 
        self.sort_reverse_var.set(False) 
        self.sort_toggle_button.config(text="昇順") # 昇順にリセット

        self.save_settings()
        if self.current_folder:
            self.load_files()

    def on_sort_toggle(self, event=None):
        """昇順/降順が切り替えられたときに設定を更新し、ファイルを再ロードします。"""
        # Checkbuttonの変数が既に切り替わっているので、その値を使う
        is_reverse = self.sort_reverse_var.get()
        self.settings['sort_reverse'] = is_reverse
        self.sort_toggle_button.config(text="降順" if is_reverse else "昇順")

        self.save_settings()
        if self.current_folder:
            self.load_files()
            
    # ====================================================
    # 設定/進捗/履歴管理メソッド
    # ====================================================

    def load_settings(self):
        """JSONファイルから読書進捗、フォルダ履歴、およびアプリ設定をロードします。"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.reading_progress = data.get('progress', {})
                    self.folder_history = data.get('history', [])
                    
                    # 設定をロードし、存在しないキーはデフォルト値を維持
                    loaded_settings = data.get('settings', {})
                    self.settings.update(loaded_settings)
            except Exception:
                self.reading_progress = {}
                self.folder_history = []
        
        if not self.folder_history:
            self.folder_history.append(os.path.expanduser("~")) 

    def save_settings(self):
        """現在の進捗、フォルダ履歴、およびアプリ設定をJSONファイルに保存します。"""
        data = {
            'progress': self.reading_progress,
            'history': self.folder_history,
            'settings': self.settings
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"設定ファイル書き込みエラー: {e}")
            
    def update_progress(self, index):
        """現在のファイルの読書進捗を更新し、保存します。"""
        if self.current_file_path:
            self.reading_progress[self.current_file_path] = index
            self.save_settings()

    def update_folder_history(self, path):
        """フォルダ履歴を更新します。"""
        if path in self.folder_history:
            self.folder_history.remove(path)
        
        self.folder_history.insert(0, path)
        self.folder_history = self.folder_history[:self.history_max]
        self.save_settings()
        self.update_folder_menu()

    def update_folder_menu(self):
        """フォルダ選択メニューボタンのドロップダウンメニューを更新します。"""
        self.folder_menu.delete(0, tk.END)
        self.folder_menu.add_command(label="新しいフォルダを選択...", command=self.select_new_folder)
        self.folder_menu.add_separator()
        
        for path in self.folder_history:
            # フォルダ名のみを表示するためにパスを短縮
            display_name = os.path.basename(path) or path
            self.folder_menu.add_command(
                label=display_name, 
                command=lambda p=path: self.set_folder(p)
            )

    def select_new_folder(self):
        """新しいフォルダを選択するダイアログを開きます。"""
        # 初期のディレクトリ設定
        initial_dir = self.current_folder if self.current_folder and os.path.isdir(self.current_folder) else os.path.expanduser("~")
        
        folder_path = filedialog.askdirectory(initialdir=initial_dir)
        if folder_path:
            self.set_folder(folder_path)

    def set_folder(self, path):
        """フォルダを設定し、ファイルをロードします。"""
        if not os.path.isdir(path):
            self.display_text_message("エラー: フォルダが存在しません。")
            return

        self.current_folder = path
        self.folder_label.config(text=f"フォルダ: {os.path.basename(path)}")
        self.update_folder_history(path)
        self.load_files()

    def load_files(self):
        """現在のフォルダからZIP/CBZファイルを読み込み、リストに表示します。"""
        self.files = []
        self.file_list.delete(*self.file_list.get_children())
        
        file_info = []

        try:
            for item in os.listdir(self.current_folder):
                # BOOK_EXTENSIONSを使用してZIP/CBZファイルをフィルタリング
                if item.lower().endswith(self.BOOK_EXTENSIONS): 
                    file_path = os.path.join(self.current_folder, item)
                    stat_info = os.stat(file_path)
                    
                    # サイズをKB, MB形式にフォーマット
                    size_bytes = stat_info[stat.ST_SIZE]
                    if size_bytes > 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    elif size_bytes > 1024:
                        size_str = f"{size_bytes / 1024:.0f} KB"
                    else:
                        size_str = f"{size_bytes} B"
                        
                    # 最終更新日時
                    date_mod = stat_info[stat.ST_MTIME]
                    
                    file_info.append({
                        'path': file_path,
                        'name': item,
                        'size_bytes': size_bytes,
                        'size_str': size_str,
                        'date_mod': date_mod,
                        'date_str': self.format_date(date_mod)
                    })
            
            if not file_info:
                self.display_text_message("フォルダ内にZIP/CBZファイルが見つかりません。")
                return
            
            # ソート処理
            sort_key = self.settings['sort_key']
            reverse = self.settings['sort_reverse']
            
            if sort_key == 'name':
                # 拡張子を除いたファイル名でソート
                file_info.sort(key=lambda x: os.path.splitext(x['name'])[0].lower(), reverse=reverse)
            elif sort_key == 'size':
                file_info.sort(key=lambda x: x['size_bytes'], reverse=reverse)
            elif sort_key == 'date':
                file_info.sort(key=lambda x: x['date_mod'], reverse=reverse)

            # Treeviewに挿入
            for info in file_info:
                self.files.append(info['path'])
                
                # 進捗に基づいてタグを設定
                file_path = info['path']
                tag = 'normal'
                if file_path in self.reading_progress:
                    if self.reading_progress[file_path] > 0:
                        tag = 'reading'

                self.file_list.insert(
                    '', 
                    'end', 
                    text=info['name'], 
                    values=('ZIP/CBZ', info['size_str'], info['date_str']), 
                    tags=(tag,)
                )

        except Exception as e:
            self.display_text_message(f"ファイル読み込みエラー: {e}")

    def format_date(self, timestamp):
        """タイムスタンプをYYYY/MM/DD hh:mm形式にフォーマットします。"""
        import datetime
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y/%m/%d %H:%M")

    def display_text_message(self, message):
        """プレビューキャンバスにテキストメッセージを表示します。"""
        self.preview_canvas.delete("all")
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        
        if canvas_width == 1 or canvas_height == 1:
            # ウィンドウがまだ描画されていない場合は後で実行
            self.master.after(50, lambda: self.display_text_message(message))
            return
            
        self.preview_canvas.create_text(
            canvas_width / 2, 
            canvas_height / 2, 
            text=message, 
            fill="gray", 
            font=('Helvetica', 20)
        )
        self.preview_title.config(text="プレビューエリア")
        self.update_nav_controls(0, 0)

    def display_placeholder(self):
        """初期画面のプレースホルダーを表示します。"""
        self.display_text_message("フォルダを選択して、自炊本を読み込みます。")


    # ====================================================
    # 設定画面の処理
    # ====================================================

    def open_settings_window(self):
        """設定画面（トップレベルウィンドウ）を開きます。"""
        # 既存のウィンドウが開いていたら何もしない
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
            
        self.settings_window = tk.Toplevel(self.master)
        self.settings_window.title("設定")
        self.settings_window.transient(self.master) # 親ウィンドウの上に表示
        self.settings_window.grab_set() # 親ウィンドウの操作を一時的に無効化
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_settings_window)
        
        frame = ttk.Frame(self.settings_window, padding="15")
        frame.pack(fill="both", expand=True)

        # 1. アニメーション設定
        ttk.Label(frame, text="アニメーション設定", font=('Helvetica', 12, 'bold')).pack(anchor='w', pady=(0, 5))
        
        self.animation_var = tk.BooleanVar(value=self.settings.get('is_animation_enabled', False))
        self.animation_check = ttk.Checkbutton(
            frame, 
            text="ページめくりアニメーション (スライド) を有効にする", 
            variable=self.animation_var, 
            bootstyle="primary-round-toggle"
        )
        self.animation_check.pack(anchor='w', pady=(5, 15))
        
        # 2. ページめくり方向設定（クリック/ボタンの動作）
        ttk.Separator(frame, bootstyle="secondary").pack(fill='x', pady=10)
        ttk.Label(frame, text="ページめくり方向 (クリック/ボタン)", font=('Helvetica', 12, 'bold')).pack(anchor='w', pady=(10, 5))

        self.direction_var = tk.StringVar(value=self.settings.get('page_turn_direction', 'L2R'))
        
        # L2R: 左クリック/ボタン -> 次頁 (現在の設定)
        ttk.Radiobutton(
            frame, 
            text="左クリック/ボタンで次頁、右クリック/ボタンで前頁", 
            variable=self.direction_var, 
            value='L2R', 
            bootstyle="info"
        ).pack(anchor='w', pady=2)

        # R2L: 右クリック/ボタン -> 次頁 
        ttk.Radiobutton(
            frame, 
            text="右クリック/ボタンで次頁、左クリック/ボタンで前頁", 
            variable=self.direction_var, 
            value='R2L', 
            bootstyle="info"
        ).pack(anchor='w', pady=2)


        # 保存ボタン
        save_button = ttk.Button(
            frame, 
            text="設定を保存して閉じる", 
            command=self.close_settings_window, 
            bootstyle="success"
        )
        save_button.pack(fill='x', pady=20)
        
        self.settings_window.focus_set()

    def close_settings_window(self):
        """設定を保存し、設定画面を閉じます。"""
        # 設定を更新
        self.settings['is_animation_enabled'] = self.animation_var.get()
        self.settings['page_turn_direction'] = self.direction_var.get()

        self.save_settings()
        
        # ウィンドウを閉じる
        self.settings_window.grab_release()
        self.settings_window.destroy()


    # ====================================================
    # プレビュー/スクロール/アニメーションメソッド 
    # ====================================================
    
    def on_file_select(self, event):
        """ファイルリストで本が選択されたときにプレビューを表示します。"""
        selected_item = self.file_list.focus()
        if not selected_item:
            return

        book_name = self.file_list.item(selected_item)['text']
        file_path = os.path.join(self.current_folder, book_name)
        
        # 安定的な再読み込みのため、既に開いているかのガード句を削除。
        # 進捗がある限り、常に再開確認ダイアログの判定を行う。

        resume_index = self.reading_progress.get(file_path, 0)
        
        if resume_index > 0:
            # 続きから読むか確認 (選択されたファイルパスを渡す)
            self.ask_resume_dialog(file_path, book_name, resume_index)
        else:
            # 最初からロード
            self.display_preview(file_path, 0)

    def display_preview(self, file_path, resume_index=0):
        """選択されたZIP/CBZファイルを展開し、画像リストを初期化します。"""
        # ファイルパスが異なる場合のみ、現在のステータスをリセット
        if file_path != self.current_file_path:
            self.current_file_path = file_path
            self.current_book_images = []
            self.current_page_index = -1
        
        try:
            # 新しいファイルを開く場合は画像を再読み込み
            if not self.current_book_images:
                with zipfile.ZipFile(file_path, 'r') as z:
                    # 画像ファイルのみをフィルタリング (self.IMAGE_EXTENSIONSを使用)
                    images = [name for name in z.namelist() if name.lower().endswith(self.IMAGE_EXTENSIONS)]
                    # ファイル名を自然順にソート（01.jpg, 02.jpg, ..., 10.jpg の順にするため）
                    self.current_book_images = sorted(images, key=str.lower)

                if not self.current_book_images:
                    self.display_text_message("エラー: このファイルには画像が含まれていません。")
                    return

            self.preview_title.config(text=self.get_book_name(file_path))
            
            # 再開インデックスの調整
            start_index = min(resume_index, len(self.current_book_images) - 1)
            
            # 最初のページ（または再開ページ）をロード
            # 初回ロード時はアニメーションを無効にする
            self.load_page_image(start_index, is_animation=False) 

        except zipfile.BadZipFile:
            self.display_text_message("エラー: 無効なZIP/CBZファイルです。")
            self.update_nav_controls(0, 0)
        except Exception as e:
            self.display_text_message(f"ファイル展開エラー: {e}")
            self.update_nav_controls(0, 0)

    def load_page_image(self, index, is_animation=True):
        """指定されたインデックスの画像をZipから読み込み、表示します。"""
        if self.is_animating:
            return

        if not self.current_book_images or index < 0 or index >= len(self.current_book_images):
            return

        direction = 'next' if index > self.current_page_index else 'prev'
        
        image_name = self.current_book_images[index]
        file_path = self.current_file_path
        
        # 設定に基づいてアニメーションを有効にするか最終決定
        use_animation = is_animation and self.settings['is_animation_enabled']
        
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                with z.open(image_name) as image_file:
                    image_data = image_file.read()
                
                # Pillowがwebpに対応しているため、Image.openで直接読み込めます。
                img = Image.open(io.BytesIO(image_data))
                self.original_image = img
                
                if use_animation:
                    self.start_page_turn_animation(img, index, direction)
                else:
                    # アニメーションなしで即時表示 (初回ロードなど)
                    self.current_page_index = index
                    self.update_progress(index)
                    self.resize_image_preview(None)
                    self.update_nav_controls(index + 1, len(self.current_book_images))
                    self.update_file_list_tag(file_path, index)
                
        except Exception as e:
            print(f"画像ロードエラー: {e}")
            self.display_text_message(f"ページロードエラー: {e}")
            self.update_nav_controls(0, 0)

    def get_resized_photoimage(self, img):
        """画像をキャンバスサイズに合わせてリサイズし、PhotoImageを返します。"""
        if not img: return None

        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()

        if canvas_width < 10 or canvas_height < 10: 
            return None # サイズが小さすぎる場合は無視

        # アスペクト比を維持してリサイズ
        img_w, img_h = img.size
        ratio_w = canvas_width / img_w
        ratio_h = canvas_height / img_h
        
        # 常に画像の全てが見えるように、小さい方の比率を採用
        ratio = min(ratio_w, ratio_h)
        
        # 最大サイズはオリジナルサイズの100%まで
        if ratio > 1:
            ratio = 1 

        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)
        
        # リサイズ後の画像を保持
        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(resized_img)
        return self.preview_image

    def resize_image_preview(self, event):
        """キャンバスのサイズ変更時、または画像がロードされたときに画像を中央に再配置します。"""
        if not self.original_image:
            self.display_placeholder()
            return
            
        self.preview_canvas.delete("all")
        
        photo_image = self.get_resized_photoimage(self.original_image)
        if not photo_image: return

        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        img_w = photo_image.width()
        img_h = photo_image.height()
        
        # 画像をキャンバスの中央に配置
        x = (canvas_w - img_w) // 2
        y = (canvas_h - img_h) // 2
        
        self.current_image_coords = (x, y)
        
        self.image_item_id = self.preview_canvas.create_image(
            x, y, 
            anchor=tk.NW, 
            image=photo_image
        )
        # 画像がキャンバスに収まりきらない場合のみ、ドラッグを許可する領域を設定
        if img_w > canvas_w or img_h > canvas_h:
            self.preview_canvas.config(scrollregion=(0, 0, img_w, img_h), cursor="fleur")
        else:
            self.preview_canvas.config(scrollregion=(0, 0, canvas_w, canvas_h), cursor="arrow") # 中央揃え

    def start_page_turn_animation(self, new_img, new_index, direction):
        """ページめくりアニメーションを開始します。"""
        self.is_animating = True
        self.preview_canvas.delete("all")

        # 1. 前のページを表示
        if self.original_image:
            # 現在表示中の画像をリサイズして保持
            prev_photo = self.get_resized_photoimage(self.original_image)
            # 画像の中央位置を取得
            x, y = self.current_image_coords
            self.old_image_item_id = self.preview_canvas.create_image(x, y, anchor=tk.NW, image=prev_photo)
        
        # 2. 次のページを非表示の位置に準備
        self.original_image = new_img # 新しい画像をセット
        self.preview_image = self.get_resized_photoimage(new_img)
        
        canvas_w = self.preview_canvas.winfo_width()
        x, y = self.current_image_coords
        
        # アニメーションの開始位置を設定
        if direction == 'next':
            start_x = x + canvas_w 
            end_x = x
        else: # direction == 'prev'
            start_x = x - canvas_w
            end_x = x

        self.image_item_id = self.preview_canvas.create_image(start_x, y, anchor=tk.NW, image=self.preview_image)
        
        # 3. アニメーション開始
        self.animate_page_turn(new_img, new_index, direction, step=0)

    def animate_page_turn(self, new_image, new_index, direction, step=0):
        """ページめくりアニメーションを実行します。"""
        if step > 20: # アニメーション終了
            self.is_animating = False
            if self.old_image_item_id:
                self.preview_canvas.delete(self.old_image_item_id)
                self.old_image_item_id = None
            
            # 最終的な状態を更新
            self.current_page_index = new_index
            self.original_image = new_image
            self.resize_image_preview(None) # 画像をリセットして中央に再配置
            self.update_progress(new_index)
            self.update_nav_controls(new_index + 1, len(self.current_book_images))
            self.update_file_list_tag(self.current_file_path, new_index)
            return

        # 1ステップあたりの移動量 (キャンバス幅 / ステップ数)
        canvas_w = self.preview_canvas.winfo_width()
        delta_x = canvas_w / 20
        
        move_amount = delta_x
        if direction == 'next':
            move_amount *= -1 # 左へ移動
            
        # 前のページと新しいページを同時に移動
        if self.old_image_item_id:
            self.preview_canvas.move(self.old_image_item_id, move_amount, 0)
        self.preview_canvas.move(self.image_item_id, move_amount, 0)
        
        self.master.after(10, self.animate_page_turn, new_image, new_index, direction, step + 1)

    def start_scroll(self, event):
        """スクロール操作（ドラッグ）の開始を記録します。"""
        if not self.image_item_id or self.is_animating:
            return
            
        self.scroll_start_x = event.x
        self.scroll_start_y = event.y
        self.is_dragging = False # ドラッグ開始フラグはまだFalseに保つ

    def do_scroll(self, event):
        """ドラッグ中に画像を移動します。"""
        if not self.image_item_id or self.is_animating or not self.preview_image:
            return
        
        dx = event.x - self.scroll_start_x
        dy = event.y - self.scroll_start_y
        
        # わずかな移動でもドラッグとみなす
        if abs(dx) > 5 or abs(dy) > 5:
            self.is_dragging = True
            
        # 画像アイテムの現在の座標を取得
        current_x, current_y = self.preview_canvas.coords(self.image_item_id)
        img_w, img_h = self.preview_image.width(), self.preview_image.height()
        canvas_w, canvas_h = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        
        new_x = current_x + dx
        new_y = current_y + dy
        
        # X軸の境界チェック
        if img_w > canvas_w:
            # 左右にドラッグ可能
            max_right = 0 # 画像の左端がキャンバスの左端まで
            min_left = canvas_w - img_w # 画像の右端がキャンバスの右端まで

            if new_x > max_right: new_x = max_right
            if new_x < min_left: new_x = min_left
        else:
            # 画像がキャンバス幅に収まっている場合は中央に固定
            new_x = (canvas_w - img_w) // 2

        # Y軸の境界チェック
        if img_h > canvas_h:
            # 上下にドラッグ可能
            max_top = 0 # 画像の上端がキャンバスの上端まで
            min_bottom = canvas_h - img_h # 画像の下端がキャンバスの下端まで
            
            if new_y > max_top: new_y = max_top
            if new_y < min_bottom: new_y = min_bottom
        else:
            # 画像がキャンバス高さに収まっている場合は中央に固定
            new_y = (canvas_h - img_h) // 2
        
        # 移動
        self.preview_canvas.coords(self.image_item_id, new_x, new_y)
        self.current_image_coords = (new_x, new_y)

        # 次の移動のために現在の位置を更新
        self.scroll_start_x = event.x
        self.scroll_start_y = event.y

    def stop_scroll(self, event):
        """マウスリリース時にドラッグでなかった場合、クリックとしてページ移動を処理します。"""
        if not self.image_item_id or self.is_animating:
            self.is_dragging = False
            return
            
        # ドラッグ操作が行われなかった場合のみクリックとして処理
        if not self.is_dragging:
            canvas_width = self.preview_canvas.winfo_width()
            
            # 設定された方向に基づいてページめくりを決定
            if self.settings['page_turn_direction'] == 'L2R':
                # L2R (左クリック:次頁 / 右クリック:前頁)
                if event.x < canvas_width / 2:
                    self.next_page() # 左クリックゾーン -> 次頁
                else:
                    self.prev_page() # 右クリックゾーン -> 前頁
            else:
                # R2L (右クリック:次頁 / 左クリック:前頁)
                if event.x > canvas_width / 2:
                    self.next_page() # 右クリックゾーン -> 次頁
                else:
                    self.prev_page() # 左クリックゾーン -> 前頁

        self.is_dragging = False

    def handle_mouse_wheel(self, event):
        """マウスホイールでページを切り替えます。"""
        if self.current_file_path == "":
            return
            
        # Windows/Linuxではevent.deltaが±120
        # macOSではevent.numが4または5 (4=Up, 5=Down)
        
        direction = 0 # 0:なし, 1:前へ, -1:次へ
        
        if event.num == 4 or (event.delta > 0 and event.num != 5):
            # スクロールアップ (前へ)
            direction = 1
        elif event.num == 5 or (event.delta < 0 and event.num != 4):
            # スクロールダウン (次へ)
            direction = -1
            
        if direction == 1:
            self.prev_page()
        elif direction == -1:
            self.next_page()

    def next_book(self):
        """次の本に移動します。"""
        if not self.current_file_path or not self.files:
            return
            
        try:
            current_index = self.files.index(self.current_file_path)
            next_index = current_index + 1
            if next_index < len(self.files):
                next_file_path = self.files[next_index]
                resume_index = self.reading_progress.get(next_file_path, 0)
                self.display_preview(next_file_path, resume_index)
        except ValueError:
            # 現在のファイルパスがリストに見つからない場合
            pass

    def prev_book(self):
        """前の本に移動します。"""
        if not self.current_file_path or not self.files:
            return
            
        try:
            current_index = self.files.index(self.current_file_path)
            prev_index = current_index - 1
            if prev_index >= 0:
                prev_file_path = self.files[prev_index]
                resume_index = self.reading_progress.get(prev_file_path, 0)
                self.display_preview(prev_file_path, resume_index)
        except ValueError:
            pass


    # ====================================================
    # ページめくりメソッド
    # ====================================================

    def next_page(self):
        """次のページに移動します。（アニメーション制御はload_page_image内）"""
        if self.is_animating: return
        if self.current_page_index < len(self.current_book_images) - 1:
            next_index = self.current_page_index + 1
            self.load_page_image(next_index, is_animation=True)
            
            # 最終ページに到達したか確認
            if next_index == len(self.current_book_images) - 1:
                self.master.after(50, self.ask_next_book_dialog) 

    def prev_page(self):
        """前のページに移動します。（アニメーション制御はload_page_image内）"""
        if self.is_animating: return
        if self.current_page_index > 0:
            self.load_page_image(self.current_page_index - 1, is_animation=True)

    def update_nav_controls(self, current, total):
        """ページ番号ラベルとボタンの状態を更新します。"""
        if total > 0:
            self.page_label.config(text=f"ページ: {current} / {total}")
            # ボタンの状態は、ページインデックスが0未満か最大値以上かで判断
            self.next_button.config(state=tk.NORMAL if current < total else tk.DISABLED)
            self.prev_button.config(state=tk.NORMAL if current > 1 else tk.DISABLED)
        else:
            self.page_label.config(text="ページ: - / -")
            self.next_button.config(state=tk.DISABLED)
            self.prev_button.config(state=tk.DISABLED)

    def update_file_list_tag(self, file_path, index):
        """ファイルリストのタグを進捗に合わせて更新します。"""
        # 現在のフォルダにあるファイルのみ処理
        if not file_path.startswith(self.current_folder):
            return

        book_name = os.path.basename(file_path)
        
        # Treeviewを検索して該当アイテムを見つける
        item_id = None
        for item in self.file_list.get_children():
            if self.file_list.item(item, 'text') == book_name:
                item_id = item
                break
        
        if item_id:
            total_pages = len(self.current_book_images)
            if index == total_pages - 1 and total_pages > 0:
                tag = 'read' # 読了
            elif index > 0:
                tag = 'reading' # 読書中
            else:
                tag = 'normal' # 未読または最初から

            self.file_list.item(item_id, tags=(tag,))

    def get_book_name(self, file_path):
        """ファイルパスから拡張子を除いたファイル名を返します。"""
        return os.path.splitext(os.path.basename(file_path))[0]

    # ====================================================
    # ダイアログ
    # ====================================================
    
    # 修正: file_pathを引数に追加し、on_file_selectから渡されたパスを使用するように変更
    def ask_resume_dialog(self, file_path, book_name, resume_index):
        """続きから読むかを確認するダイアログ。"""
        if self.Messagebox:
            result = self.Messagebox.yesnocancel(
                f"「{book_name}」\n続き({resume_index + 1}ページ)から読みますか？", 
                title="読書再開の確認",
            )
            
            if result == 'Yes':
                self.display_preview(file_path, resume_index) # 渡されたfile_pathを使用
            elif result == 'No':
                self.display_preview(file_path, 0)           # 渡されたfile_pathを使用
            # Cancelの場合は何もしない
        else:
            # ttkbootstrapがない場合の簡易的な動作
            self.display_preview(file_path, resume_index) # 渡されたfile_pathを使用

    def ask_next_book_dialog(self):
        """最終ページに達したとき、次の本へ進むかを確認するダイアログ。"""
        if not self.current_file_path or not self.files:
            return

        try:
            current_index = self.files.index(self.current_file_path)
            next_index = current_index + 1
            if next_index < len(self.files):
                next_book_name = self.get_book_name(self.files[next_index])
                
                if self.Messagebox:
                    result = self.Messagebox.yesno(
                        f"最終ページです。次の本「{next_book_name}」に進みますか？",
                        title="次の本へ",
                    )
                    
                    if result == 'Yes':
                        self.next_book()
                else:
                    # ttkbootstrapがない場合の簡易的な動作
                    self.next_book()
        except ValueError:
            pass # リストにない場合はスキップ


if __name__ == '__main__':
    # ttkbootstrapをインポート
    try:
        import ttkbootstrap as ttkb
        root = ttkb.Window(themename="superhero")
    except ImportError:
        root = tk.Tk()
        
    root.geometry("1200x800")
    
    # キーボードイベントを受け取るためにフォーカスを設定
    root.focus_set() 
    
    app = BookManagerApp(root)
    root.mainloop()