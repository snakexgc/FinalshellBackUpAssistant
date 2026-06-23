"""FinalShell 连接配置解密界面。"""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Tuple

from core import FinalShellDecryptError, decrypt_password


class DecryptFrame(ttk.Frame):
    """选择单个连接 JSON 或 conn 目录，并显示解密后的连接信息。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.selected_path = tk.StringVar()
        self._create_widgets()

    def _create_widgets(self):
        select_frame = ttk.LabelFrame(self, text="选择需要解密的配置")
        select_frame.pack(padx=20, pady=15, fill="x")

        ttk.Label(
            select_frame,
            text="可选择单个 .json 连接配置，或整个 conn 文件夹（递归处理其中的 JSON 文件）。",
            wraplength=720,
        ).pack(anchor="w", padx=10, pady=(10, 5))

        path_frame = ttk.Frame(select_frame)
        path_frame.pack(fill="x", padx=10, pady=5)
        ttk.Entry(path_frame, textvariable=self.selected_path, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(path_frame, text="选择 JSON 文件", command=self._select_json_file).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(path_frame, text="选择 conn 文件夹", command=self._select_conn_folder).pack(
            side="left", padx=(8, 0)
        )

        action_frame = ttk.Frame(self)
        action_frame.pack(pady=(0, 10))
        ttk.Button(action_frame, text="解密", command=self._decrypt, width=16).pack(side="left", padx=5)
        ttk.Button(action_frame, text="复制全部", command=self._copy_all, width=16).pack(side="left", padx=5)

        result_frame = ttk.LabelFrame(self, text="解密结果")
        result_frame.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.result_columns = ("file", "name", "host", "port", "user_name", "password", "status")
        headings = {
            "file": "来源文件",
            "name": "name",
            "host": "host",
            "port": "port",
            "user_name": "user_name",
            "password": "password",
            "status": "状态",
        }
        widths = {
            "file": 180,
            "name": 130,
            "host": 150,
            "port": 70,
            "user_name": 130,
            "password": 260,
            "status": 180,
        }

        table_frame = ttk.Frame(result_frame)
        table_frame.pack(padx=8, pady=(8, 4), fill="both", expand=True)
        self.result_tree = ttk.Treeview(table_frame, columns=self.result_columns, show="headings")
        for column in self.result_columns:
            self.result_tree.heading(column, text=headings[column])
            self.result_tree.column(column, width=widths[column], minwidth=70, stretch=column != "port")
        self.result_tree.pack(side="left", fill="both", expand=True)

        vertical_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.result_tree.yview)
        vertical_scrollbar.pack(side="right", fill="y")
        horizontal_scrollbar = ttk.Scrollbar(result_frame, orient="horizontal", command=self.result_tree.xview)
        horizontal_scrollbar.pack(padx=8, fill="x")
        self.result_tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        self.result_tree.bind("<ButtonRelease-1>", self._copy_clicked_cell)

        self.copy_value = tk.StringVar(value="点击任意单元格即可自动复制该字段。")
        copy_frame = ttk.Frame(result_frame)
        copy_frame.pack(padx=8, pady=(4, 8), fill="x")
        ttk.Label(copy_frame, text="当前复制内容：").pack(side="left")
        self.copy_entry = ttk.Entry(copy_frame, textvariable=self.copy_value, state="readonly")
        self.copy_entry.pack(side="left", fill="x", expand=True)

    def _select_json_file(self):
        path = filedialog.askopenfilename(
            title="选择 FinalShell 连接 JSON 文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if path:
            self.selected_path.set(path)

    def _select_conn_folder(self):
        path = filedialog.askdirectory(title="选择 FinalShell conn 文件夹")
        if path:
            self.selected_path.set(path)

    def _decrypt(self):
        selected = Path(self.selected_path.get())
        if not self.selected_path.get() or not selected.exists():
            messagebox.showerror("错误", "请选择存在的 .json 文件或 conn 文件夹")
            return

        try:
            json_files = self._get_json_files(selected)
        except ValueError as error:
            messagebox.showerror("错误", str(error))
            return

        if not json_files:
            self._set_results([], "未在所选 conn 文件夹中找到 JSON 文件。")
            return

        results: List[Tuple[str, str, str, str, str, str, str]] = []
        for json_file in json_files:
            results.append(self._decrypt_json_file(json_file, selected))
        self._set_results(results, f"共处理 {len(results)} 个 JSON 文件；点击任意单元格可自动复制。")

    def _get_json_files(self, selected: Path) -> List[Path]:
        if selected.is_file():
            if selected.suffix.lower() != ".json":
                raise ValueError("请选择 .json 文件")
            return [selected]

        if selected.is_dir():
            return sorted(
                path for path in selected.rglob("*")
                if path.is_file() and path.suffix.lower() == ".json"
            )

        raise ValueError("所选路径不是文件或文件夹")

    def _decrypt_json_file(self, json_file: Path, selected: Path) -> Tuple[str, str, str, str, str, str, str]:
        file_label = json_file.name if selected.is_file() else str(json_file.relative_to(selected))
        try:
            with json_file.open("r", encoding="utf-8-sig") as file:
                connection = json.load(file)
            if not isinstance(connection, dict):
                raise ValueError("JSON 根节点不是对象")

            encrypted_password = connection.get("password")
            password = decrypt_password(encrypted_password)
            return (
                file_label,
                str(connection.get("name", "")),
                str(connection.get("host", "")),
                str(connection.get("port", "")),
                str(connection.get("user_name", "")),
                password,
                "成功",
            )
        except (FinalShellDecryptError, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            return (file_label, "", "", "", "", "", f"失败：{error}")

    def _set_results(self, rows: List[Tuple[str, str, str, str, str, str, str]], copy_hint: str):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        for row in rows:
            self.result_tree.insert("", "end", values=row)
        self.copy_value.set(copy_hint)

    def _copy_all(self):
        rows = [self.result_tree.item(item, "values") for item in self.result_tree.get_children()]
        if not rows:
            return
        content = "\n".join("\t".join(row) for row in rows)
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        self.copy_value.set("已复制全部表格内容。")

    def _copy_clicked_cell(self, event):
        if self.result_tree.identify_region(event.x, event.y) != "cell":
            return
        item = self.result_tree.identify_row(event.y)
        column = self.result_tree.identify_column(event.x)
        if not item or not column:
            return

        column_index = int(column[1:]) - 1
        value = self.result_tree.item(item, "values")[column_index]
        self.result_tree.selection_set(item)
        self.result_tree.focus(item)
        self.copy_value.set(value)
        self.copy_entry.selection_range(0, tk.END)
        self.copy_entry.focus_set()
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()
