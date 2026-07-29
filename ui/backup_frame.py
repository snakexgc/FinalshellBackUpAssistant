"""
备份操作界面模块
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Callable, Optional
from email.utils import parsedate_to_datetime

from core import WebDAVClient, BackupManager


class BackupFrame(ttk.Frame):
    """备份操作面板"""

    def __init__(self, master, webdav_client: Optional[WebDAVClient] = None,
                 log_callback: Optional[Callable] = None,
                 source_variable: Optional[tk.StringVar] = None, **kwargs):
        """
        初始化备份操作面板

        Args:
            master: 父窗口
            webdav_client: WebDAV客户端实例
            log_callback: 日志回调函数
        """
        super().__init__(master, **kwargs)

        self.webdav_client = webdav_client
        self.log_callback = log_callback
        self.backup_manager: Optional[BackupManager] = None
        self.source_path = source_variable or tk.StringVar(value="D:/finalshell")

        self._create_widgets()

    def _create_widgets(self):
        """创建界面组件"""
        source_frame = ttk.LabelFrame(self, text="源目录 (Finalshell安装目录)")
        source_frame.pack(padx=10, pady=5, fill="x")

        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_path)
        self.source_entry.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        self.browse_btn = ttk.Button(source_frame, text="浏览...", command=self._select_source)
        self.browse_btn.pack(side="right", padx=5, pady=5)

        self._create_backup_section()
        self._create_restore_section()
        self._create_cloud_list_section()

        self._set_enabled(False)

    def _create_backup_section(self):
        """创建备份操作区域"""
        self.backup_frame = ttk.LabelFrame(self, text="备份操作")
        self.backup_frame.pack(padx=10, pady=5, fill="x")

        self.include_config_backup = tk.BooleanVar(value=True)
        self.config_backup_cb = ttk.Checkbutton(
            self.backup_frame,
            text="包含 config.json（全局配置文件）",
            variable=self.include_config_backup
        )
        self.config_backup_cb.pack(anchor="w", padx=5, pady=2)

        base_frame = ttk.Frame(self.backup_frame)
        base_frame.pack(fill="x", padx=5, pady=2)
        self.base_label = ttk.Label(base_frame, text="基准云端备份（可选）:")
        self.base_label.pack(side="left")
        self.backup_base_combo = ttk.Combobox(base_frame, state="readonly", width=40)
        self.backup_base_combo.pack(side="left", padx=5, fill="x", expand=True)

        btn_frame = ttk.Frame(self.backup_frame)
        btn_frame.pack(pady=5)

        self.full_backup_btn = ttk.Button(btn_frame, text="本地完整备份", command=self._full_backup)
        self.full_backup_btn.pack(side="left", padx=5)
        self._create_tooltip(self.full_backup_btn, "将本地conn文件夹和config.json（可选）完整打包上传到云端\n适用于首次备份或需要完整独立备份的情况")

        self.local_priority_backup_btn = ttk.Button(btn_frame, text="本地优先备份", command=self._local_priority_backup)
        self.local_priority_backup_btn.pack(side="left", padx=5)
        self._create_tooltip(self.local_priority_backup_btn, "基于选中的云端备份，用本地文件替换同名文件\n本地文件优先，适合本地有更新的情况")

        self.cloud_priority_backup_btn = ttk.Button(btn_frame, text="云端优先备份", command=self._cloud_priority_backup)
        self.cloud_priority_backup_btn.pack(side="left", padx=5)
        self._create_tooltip(self.cloud_priority_backup_btn, "基于选中的云端备份，保留云端同名文件\n云端文件优先，适合保留云端版本的情况")

    def _create_restore_section(self):
        """创建恢复操作区域"""
        self.restore_frame = ttk.LabelFrame(self, text="恢复操作")
        self.restore_frame.pack(padx=10, pady=5, fill="x")

        self.include_config_restore = tk.BooleanVar(value=True)
        self.config_restore_cb = ttk.Checkbutton(
            self.restore_frame,
            text="恢复 config.json（全局配置文件）",
            variable=self.include_config_restore
        )
        self.config_restore_cb.pack(anchor="w", padx=5, pady=2)

        btn_frame = ttk.Frame(self.restore_frame)
        btn_frame.pack(pady=5)

        self.overwrite_restore_btn = ttk.Button(btn_frame, text="云端覆盖恢复", command=self._cloud_overwrite_restore)
        self.overwrite_restore_btn.pack(side="left", padx=5)
        self._create_tooltip(self.overwrite_restore_btn, "用云端备份完全覆盖本地文件\n会删除本地conn文件夹所有内容后恢复\n适用于需要完全还原到云端状态")

        self.cloud_priority_restore_btn = ttk.Button(btn_frame, text="云端优先恢复", command=self._cloud_priority_restore)
        self.cloud_priority_restore_btn.pack(side="left", padx=5)
        self._create_tooltip(self.cloud_priority_restore_btn, "云端文件覆盖本地同名文件\n本地独有的文件保留不变\n适合需要云端配置覆盖本地的情况")

        self.local_priority_restore_btn = ttk.Button(btn_frame, text="本地优先恢复", command=self._local_priority_restore)
        self.local_priority_restore_btn.pack(side="left", padx=5)
        self._create_tooltip(self.local_priority_restore_btn, "保留本地同名文件，只恢复云端独有的文件\n适合需要补充云端文件但保留本地修改的情况")

    def _create_cloud_list_section(self):
        """创建云端备份列表区域"""
        self.list_frame = ttk.LabelFrame(self, text="云端备份文件列表")
        self.list_frame.pack(padx=10, pady=5, fill="both", expand=True)

        btn_frame = ttk.Frame(self.list_frame)
        btn_frame.pack(fill="x", padx=5, pady=2)
        self.refresh_btn = ttk.Button(btn_frame, text="刷新列表", command=self.refresh_backup_list)
        self.refresh_btn.pack(side="left", padx=2)
        self.delete_btn = ttk.Button(btn_frame, text="删除选中备份", command=self._delete_backup)
        self.delete_btn.pack(side="left", padx=2)

        columns = ("filename", "created_time", "type", "size")
        self.zip_tree = ttk.Treeview(self.list_frame, columns=columns, show="headings", height=6)
        self.zip_tree.heading("filename", text="文件名")
        self.zip_tree.heading("created_time", text="创建时间")
        self.zip_tree.heading("type", text="类型")
        self.zip_tree.heading("size", text="大小")
        self.zip_tree.column("filename", width=250)
        self.zip_tree.column("created_time", width=150)
        self.zip_tree.column("type", width=100)
        self.zip_tree.column("size", width=80)

        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.zip_tree.yview)
        self.zip_tree.configure(yscrollcommand=scrollbar.set)

        self.zip_tree.pack(side="left", padx=5, pady=5, fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _set_enabled(self, enabled: bool):
        """设置控件启用状态"""
        state = "normal" if enabled else "disabled"

        self.source_entry.config(state=state)
        self.browse_btn.config(state=state)

        self.config_backup_cb.config(state=state)
        self.backup_base_combo.config(state="readonly" if enabled else "disabled")
        self.full_backup_btn.config(state=state)
        self.local_priority_backup_btn.config(state=state)
        self.cloud_priority_backup_btn.config(state=state)

        self.config_restore_cb.config(state=state)
        self.overwrite_restore_btn.config(state=state)
        self.cloud_priority_restore_btn.config(state=state)
        self.local_priority_restore_btn.config(state=state)

        self.refresh_btn.config(state=state)
        self.delete_btn.config(state=state)

    def _create_tooltip(self, widget, text):
        """创建工具提示"""
        def show_tooltip(event):
            if hasattr(widget, '_tooltip') and widget._tooltip.winfo_exists():
                return

            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

            label = ttk.Label(tooltip, text=text, background="#ffffe0",
                              relief="solid", borderwidth=1, padding=5)
            label.pack()

            widget._tooltip = tooltip

        def hide_tooltip(event):
            if hasattr(widget, '_tooltip') and widget._tooltip.winfo_exists():
                widget._tooltip.destroy()

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    def set_webdav_client(self, client: WebDAVClient):
        """设置WebDAV客户端"""
        self.webdav_client = client
        self.backup_manager = BackupManager(client)
        self._set_enabled(True)
        self._clear_list()
        self._log("WebDAV已连接；需要查看云端备份时请点击“刷新列表”")

    def set_source_path(self, path: str):
        """设置源目录路径"""
        self.source_path.set(path)

    def get_source_path(self) -> str:
        """获取源目录路径"""
        return self.source_path.get()

    def _select_source(self):
        """选择源目录"""
        path = filedialog.askdirectory(title="选择源目录")
        if path:
            missing = []
            if not os.path.exists(os.path.join(path, "config.json")):
                missing.append("config.json")
            if not os.path.isdir(os.path.join(path, "conn")):
                missing.append("conn 文件夹")
            if not os.path.exists(os.path.join(path, "finalshell.exe")):
                missing.append("finalshell.exe")

            if missing:
                messagebox.showerror(
                    "目录选择错误",
                    f"所选目录不是有效的 Finalshell 安装目录\n\n缺少: {', '.join(missing)}"
                )
                return

            self.source_path.set(path)
            self._log(f"源目录已设置为: {path}")

    def _log(self, message: str):
        """输出日志"""
        if self.log_callback:
            self.log_callback(message)

    def refresh_backup_list(self):
        """刷新备份列表"""
        if not self.webdav_client or not self.webdav_client.connected:
            self._log("WebDAV未连接，无法获取备份列表")
            self._clear_list()
            return

        if not self.backup_manager:
            self.backup_manager = BackupManager(self.webdav_client)

        try:
            self._log("正在从WebDAV获取备份列表...")
            success, message, files = self.backup_manager.get_backup_list()

            if not success:
                self._log(f"获取备份列表失败: {message}")
                return

            self._update_list_display(files)
            self._log(f"找到 {len(files)} 个云端备份文件")

        except Exception as e:
            self._log(f"刷新备份列表失败: {str(e)}")

    def _clear_list(self):
        """清空列表"""
        for item in self.zip_tree.get_children():
            self.zip_tree.delete(item)
        self.backup_base_combo['values'] = []
        self.backup_base_combo.set('')

    def _update_list_display(self, files: list):
        """更新列表显示"""
        for item in self.zip_tree.get_children():
            self.zip_tree.delete(item)

        files.sort(key=lambda x: x['modified'], reverse=True)

        base_names = [""]
        for file_info in files:
            filename = file_info['filename']
            size_mb = file_info['size'] / (1024 * 1024)

            backup_type = "备份"
            if "完整备份" in filename:
                backup_type = "完整备份"
            elif "本地优先备份" in filename:
                backup_type = "本地优先备份"
            elif "云端优先备份" in filename:
                backup_type = "云端优先备份"
            elif "增量备份" in filename:
                backup_type = "增量备份"
            elif "覆盖备份" in filename:
                backup_type = "覆盖备份"

            try:
                dt = parsedate_to_datetime(file_info['modified'])
                created_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                created_time = file_info['modified']

            self.zip_tree.insert("", "end", values=(
                filename, created_time, backup_type, f"{size_mb:.2f} MB"
            ))
            base_names.append(filename)

        self.backup_base_combo['values'] = base_names
        if base_names:
            self.backup_base_combo.set(base_names[0])

    def _validate_prerequisites(self) -> bool:
        """验证前提条件"""
        if not self.source_path.get():
            messagebox.showerror("错误", "请选择源目录")
            return False
        if not self.webdav_client or not self.webdav_client.connected:
            messagebox.showerror("错误", "请先登录WebDAV")
            return False
        return True

    def _get_selected_backup(self) -> Optional[str]:
        """获取选中的备份文件名"""
        selected_items = self.zip_tree.selection()
        if not selected_items:
            return None
        item = selected_items[0]
        values = self.zip_tree.item(item, 'values')
        return values[0]

    def _full_backup(self):
        """本地完整备份"""
        if not self._validate_prerequisites():
            return

        self._log("\n----- 开始本地完整备份 -----")

        try:
            success, message = self.backup_manager.full_backup(
                self.source_path.get(),
                self.include_config_backup.get(),
                self.log_callback
            )

            if success:
                self._log(f"备份成功: {message}")
                messagebox.showinfo("成功", f"备份操作已完成\n文件名: {message}")
                self.refresh_backup_list()
            else:
                self._log(f"备份失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"备份过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"备份过程中发生错误: {str(e)}")

    def _local_priority_backup(self):
        """本地优先备份"""
        if not self._validate_prerequisites():
            return

        base_filename = self.backup_base_combo.get()
        if not base_filename:
            messagebox.showerror("错误", "本地优先备份需要选择一个云端备份作为基准")
            return

        self._log("\n----- 开始本地优先备份 -----")

        try:
            success, message = self.backup_manager.local_priority_backup(
                self.source_path.get(),
                base_filename,
                self.include_config_backup.get(),
                self.log_callback
            )

            if success:
                self._log(f"备份成功: {message}")
                messagebox.showinfo("成功", f"备份操作已完成\n文件名: {message}")
                self.refresh_backup_list()
            else:
                self._log(f"备份失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"备份过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"备份过程中发生错误: {str(e)}")

    def _cloud_priority_backup(self):
        """云端优先备份"""
        if not self._validate_prerequisites():
            return

        base_filename = self.backup_base_combo.get()
        if not base_filename:
            messagebox.showerror("错误", "云端优先备份需要选择一个云端备份作为基准")
            return

        self._log("\n----- 开始云端优先备份 -----")

        try:
            success, message = self.backup_manager.cloud_priority_backup(
                self.source_path.get(),
                base_filename,
                self.include_config_backup.get(),
                self.log_callback
            )

            if success:
                self._log(f"备份成功: {message}")
                messagebox.showinfo("成功", f"备份操作已完成\n文件名: {message}")
                self.refresh_backup_list()
            else:
                self._log(f"备份失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"备份过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"备份过程中发生错误: {str(e)}")

    def _cloud_overwrite_restore(self):
        """云端覆盖恢复"""
        if not self._validate_prerequisites():
            return

        filename = self._get_selected_backup()
        if not filename:
            messagebox.showerror("错误", "请从列表中选择一个备份文件")
            return

        if not messagebox.askyesno("确认",
                                   f"确定要从 {filename} 云端覆盖恢复吗？\n\n"
                                   "这将完全覆盖本地的conn文件夹内容！"):
            return

        self._log(f"\n----- 开始云端覆盖恢复 -----")
        self._log(f"从云端备份恢复: {filename}")

        try:
            success, message = self.backup_manager.cloud_overwrite_restore(
                filename,
                self.source_path.get(),
                self.include_config_restore.get(),
                self.log_callback
            )

            if success:
                self._log("恢复操作成功完成")
                messagebox.showinfo("成功", "恢复操作已完成")
            else:
                self._log(f"恢复失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"恢复过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"恢复过程中发生错误: {str(e)}")

    def _cloud_priority_restore(self):
        """云端优先恢复"""
        if not self._validate_prerequisites():
            return

        filename = self._get_selected_backup()
        if not filename:
            messagebox.showerror("错误", "请从列表中选择一个备份文件")
            return

        if not messagebox.askyesno("确认",
                                   f"确定要从 {filename} 云端优先恢复吗？\n\n"
                                   "云端同名文件将覆盖本地文件，本地独有文件保留不变。"):
            return

        self._log(f"\n----- 开始云端优先恢复 -----")
        self._log(f"从云端备份恢复: {filename}")

        try:
            success, message = self.backup_manager.cloud_priority_restore(
                filename,
                self.source_path.get(),
                self.include_config_restore.get(),
                self.log_callback
            )

            if success:
                self._log("恢复操作成功完成")
                messagebox.showinfo("成功", "恢复操作已完成")
            else:
                self._log(f"恢复失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"恢复过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"恢复过程中发生错误: {str(e)}")

    def _local_priority_restore(self):
        """本地优先恢复"""
        if not self._validate_prerequisites():
            return

        filename = self._get_selected_backup()
        if not filename:
            messagebox.showerror("错误", "请从列表中选择一个备份文件")
            return

        if not messagebox.askyesno("确认",
                                   f"确定要从 {filename} 本地优先恢复吗？\n\n"
                                   "本地同名文件将保留不变，只恢复云端独有的文件。"):
            return

        self._log(f"\n----- 开始本地优先恢复 -----")
        self._log(f"从云端备份恢复: {filename}")

        try:
            success, message = self.backup_manager.local_priority_restore(
                filename,
                self.source_path.get(),
                self.include_config_restore.get(),
                self.log_callback
            )

            if success:
                self._log("恢复操作成功完成")
                messagebox.showinfo("成功", "恢复操作已完成")
            else:
                self._log(f"恢复失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"恢复过程中发生错误: {str(e)}")
            messagebox.showerror("错误", f"恢复过程中发生错误: {str(e)}")

    def _delete_backup(self):
        """删除备份"""
        if not self.webdav_client or not self.webdav_client.connected:
            messagebox.showerror("错误", "WebDAV未连接")
            return

        filename = self._get_selected_backup()
        if not filename:
            messagebox.showerror("错误", "请从列表中选择一个备份文件")
            return

        if not messagebox.askyesno("确认", f"确定要删除云端备份 {filename} 吗？"):
            return

        try:
            success, message = self.backup_manager.delete_backup(filename)

            if success:
                self._log(f"已删除云端备份: {filename}")
                self.refresh_backup_list()
                messagebox.showinfo("成功", "云端备份已删除")
            else:
                self._log(f"删除失败: {message}")
                messagebox.showerror("错误", message)

        except Exception as e:
            self._log(f"删除备份失败: {str(e)}")
            messagebox.showerror("错误", f"删除备份失败: {str(e)}")
